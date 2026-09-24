import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mailtrace.parsing import check_arc_chain  # noqa: E402
from mailtrace.parsing.sample import SAMPLE_HEADERS_ARC  # noqa: E402

try:  # Flask 相关测试在未安装 Flask 时跳过（解析核心仅需标准库）
    from app import create_app
except ImportError:  # pragma: no cover
    create_app = None


def chain(n=2, *, folding=False, reorder=False, extra=""):
    """生成一个结构合法的 i=1..n ARC 链。

    folding=True 时让部分字段折行；reorder=True 时打乱标签顺序
    （Seal 中把 i 放到 cv 之后）。
    """
    lines = []
    order = range(n, 0, -1)
    for i in order:
        cv = "none" if i == 1 else "pass"
        if reorder:
            seal = (
                f"ARC-Seal: cv={cv}; i={i}; a=rsa-sha256; "
                f"d=mta{i}.example; s=k; t=1; b=BBBB{i}"
            )
        else:
            seal = (
                f"ARC-Seal: i={i}; cv={cv}; a=rsa-sha256; "
                f"d=mta{i}.example; s=k; t=1; b=BBBB{i}"
            )
        if folding and i == 2:
            seal = seal.replace("; a=rsa-sha256;", ";\n\ta=rsa-sha256;")
        lines.append(seal)
        lines.append(
            f"ARC-Message-Signature: i={i}; a=rsa-sha256; "
            f"d=mta{i}.example; s=ams; t=1;\r\n bh=hhhh{i}; b=AAAA{i}"
            if folding
            else f"ARC-Message-Signature: i={i}; a=rsa-sha256; t=1; b=AAAA{i}"
        )
        lines.append(
            f"ARC-Authentication-Results: i={i}; mta{i}.example; spf=pass"
        )
    lines.append(extra)
    return "\n".join(line for line in lines if line)


class ValidChainTests(unittest.TestCase):
    def test_single_instance_none_cv_passes(self):
        result = check_arc_chain(chain(1))
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["present"])
        self.assertEqual(result["summary"]["instance_count"], 1)
        self.assertEqual(result["instances"][0]["seal_cv"], "none")
        self.assertEqual(result["instances"][0]["expected_cv"], "none")
        self.assertEqual(result["issues"], [])

    def test_multi_instance_passes(self):
        result = check_arc_chain(chain(3))
        self.assertEqual(result["status"], "pass")
        self.assertEqual([i["instance"] for i in result["instances"]], [1, 2, 3])
        self.assertEqual(
            [i["seal_cv"] for i in result["instances"]], ["none", "pass", "pass"]
        )

    def test_folding_and_tag_reorder_still_recognized(self):
        result = check_arc_chain(chain(2, folding=True, reorder=True))
        self.assertEqual(result["status"], "pass", result["issues"])
        self.assertEqual(result["summary"]["seal_count"], 2)

    def test_sample_headers_are_valid_chain(self):
        result = check_arc_chain(SAMPLE_HEADERS_ARC)
        self.assertEqual(result["status"], "pass", result["issues"])
        self.assertEqual(result["summary"]["instance_count"], 2)


class AbsentTests(unittest.TestCase):
    def test_no_arc_fields_is_absent_not_pass(self):
        result = check_arc_chain(
            "Received: by mx.example; Tue, 23 Sep 2026 02:00:00 +0000\n"
            "Subject: nothing to see here\n"
        )
        self.assertFalse(result["present"])
        self.assertEqual(result["status"], "absent")
        self.assertIn("无 ARC 链", result["message"])
        self.assertEqual(result["instances"], [])

    def test_empty_input_is_absent(self):
        result = check_arc_chain("")
        self.assertEqual(result["status"], "absent")


class CvTests(unittest.TestCase):
    def test_first_seal_must_be_none(self):
        raw = chain(1).replace("i=1; cv=none", "i=1; cv=pass")
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "fail")
        codes = [i["code"] for i in result["issues"]]
        self.assertIn("bad_cv", codes)
        msg = result["instances"][0]["issues"][0]["message"]
        self.assertIn("i=1", msg)
        self.assertIn("none", msg)

    def test_later_seal_must_be_pass(self):
        raw = chain(2)
        raw = raw.replace("i=2; cv=pass", "i=2; cv=fail")
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "fail")
        inst2 = [i for i in result["instances"] if i["instance"] == 2][0]
        self.assertTrue(any(x["code"] == "bad_cv" for x in inst2["issues"]))
        self.assertIn("pass", inst2["issues"][0]["message"])

    def test_cv_value_case_insensitive(self):
        raw = chain(1).replace("cv=none", "cv=None")
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "pass")

    def test_missing_cv_flagged(self):
        raw = chain(1).replace("; cv=none", "")
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "fail")
        self.assertIn("missing_cv", [i["code"] for i in result["issues"]])


class StructureTests(unittest.TestCase):
    def test_missing_field_in_instance(self):
        # 去掉 i=1 的 AAR
        raw = "\n".join(
            line for line in chain(2).splitlines()
            if not line.startswith("ARC-Authentication-Results: i=1")
        )
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "fail")
        inst1 = result["instances"][0]
        self.assertIsNone(inst1["fields"]["aar"])
        self.assertTrue(
            any(x["code"] == "missing_field" for x in inst1["issues"])
        )

    def test_gap_in_instance_numbers(self):
        raw = "\n".join(
            line for line in chain(3).splitlines()
            if "i=2;" not in line
        )
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "fail")
        gaps = [i for i in result["issues"] if i["code"] == "gap"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("i=2", gaps[0]["message"])
        self.assertIn("i=3", gaps[0]["message"])

    def test_chain_starting_at_two_is_gap(self):
        # 链里只有 i=3、i=4（且 i=3 是“首个 Seal”却写了 pass）
        lines = []
        for i, cv in ((4, "pass"), (3, "pass")):
            lines.append(f"ARC-Seal: i={i}; cv={cv}; b=s{i}")
            lines.append(f"ARC-Message-Signature: i={i}; b=m{i}")
            lines.append(f"ARC-Authentication-Results: i={i}; mx{i}.example; spf=pass")
        result = check_arc_chain("\n".join(lines))
        self.assertEqual(result["status"], "fail")
        gap_messages = " ".join(
            i["message"] for i in result["issues"] if i["code"] == "gap"
        )
        self.assertIn("i=1", gap_messages)
        self.assertIn("i=2", gap_messages)
        # cv 要求只看实例号：i=3、i=4 要求 pass，故无 cv 问题
        self.assertFalse(
            any(i["code"] == "bad_cv" for i in result["issues"])
        )

    def test_duplicate_field_flagged_with_header_position(self):
        raw = chain(1) + "\n" + "ARC-Seal: i=1; cv=none; b=DUP"
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "fail")
        dup = [i for i in result["issues"] if i["code"] == "duplicate_field"]
        self.assertEqual(len(dup), 1)
        # 定位到具体头部出现序号（合法链 3 个字段 + 重复 Seal = 第 4 个）
        self.assertEqual(dup[0]["order"], 4)

    def test_invalid_i_is_ungrouped(self):
        raw = chain(1) + "\n" + "ARC-Seal: i=abc; cv=pass; b=BAD"
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(result["ungrouped"]), 1)
        bad = [i for i in result["issues"] if i["code"] == "invalid_i"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["order"], 4)
        self.assertIn("abc", bad[0]["message"])

    def test_zero_and_negative_like_i_are_invalid(self):
        raw = chain(1) + "\nARC-Authentication-Results: i=0; mx.example; spf=none"
        result = check_arc_chain(raw)
        self.assertTrue(
            any(i["code"] == "invalid_i" for i in result["issues"])
        )

    def test_missing_i_tag_is_ungrouped(self):
        raw = chain(1) + "\n" + "ARC-Message-Signature: a=rsa-sha256; b=NOI"
        result = check_arc_chain(raw)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(
            any(i["code"] == "missing_i" for i in result["issues"])
        )
        self.assertEqual(len(result["ungrouped"]), 1)

    def test_header_order_field_points_to_position(self):
        result = check_arc_chain(chain(2))
        # i=2 Seal 在原文最前，即第 1 个头部
        inst2 = [i for i in result["instances"] if i["instance"] == 2][0]
        self.assertEqual(inst2["fields"]["seal"]["order"], 1)
        # i=1 AAR 是第 6 个头部
        inst1 = result["instances"][0]
        self.assertEqual(inst1["fields"]["aar"]["order"], 6)


@unittest.skipIf(create_app is None, "未安装 Flask，跳过 API 测试")
class ArcApiTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_api_pass(self):
        resp = self.client.post("/api/arc/check", json={"headers": SAMPLE_HEADERS_ARC})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "pass")
        self.assertTrue(data["present"])

    def test_api_absent_is_200_not_pass(self):
        resp = self.client.post(
            "/api/arc/check", json={"headers": "Subject: no arc here\n"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "absent")
        self.assertIn("无 ARC 链", data["message"])

    def test_api_fail_is_200_with_issues(self):
        resp = self.client.post(
            "/api/arc/check", json={"headers": "ARC-Seal: i=1; cv=fail; b=x\n"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "fail")
        self.assertTrue(data["issues"])

    def test_api_form_encoded_supported(self):
        resp = self.client.post(
            "/api/arc/check",
            data={"headers": SAMPLE_HEADERS_ARC},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "pass")

    def test_api_rejects_non_string(self):
        resp = self.client.post("/api/arc/check", json={"headers": 123})
        self.assertEqual(resp.status_code, 400)

    def test_form_page_renders(self):
        resp = self.client.post(
            "/arc/check", data={"headers_arc": SAMPLE_HEADERS_ARC}
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ARC 链结构正常", html)
        self.assertIn("i=1", html)

    def test_form_page_absent_message(self):
        resp = self.client.post(
            "/arc/check", data={"headers_arc": "Received: by mx.example\n"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("无 ARC 链", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
