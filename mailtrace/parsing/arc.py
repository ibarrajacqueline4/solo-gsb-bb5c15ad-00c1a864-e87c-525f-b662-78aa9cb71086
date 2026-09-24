"""ARC（Authenticated Received Chain，RFC 8617）链结构检查。

设计要点：
- 直接复用 :func:`mailtrace.parsing.parser.parse_header_blocks` 的头部
  切分与折行展开结果，不重复实现 RFC 5322 解析；因此折行（folding）
  与标签书写顺序变化不影响识别。
- 按 ``ARC-Seal`` / ``ARC-Message-Signature`` /
  ``ARC-Authentication-Results`` 三类字段中 ``i=`` 标签给出的**实例号**
  归组：合法 ARC 链中实例号必须从 ``1`` 起连续，且每个实例三类字段各一条。
- 仅做**结构**校验，不验证 DKIM 签名密码学有效性：``i=1`` 的
  ``ARC-Seal`` 的 ``cv`` 必须为 ``none``，其余实例的 Seal 必须为
  ``pass``；其余 ``cv`` 值（含 ``fail``）一律按结构异常定位。
- 对非法（非正整数）``i``、缺失 ``i``、同一实例同类字段重复、实例跳号、
  实例缺字段以及 ``cv`` 异常逐条给出可定位的问题项（标注头部出现序号）。
- 头部中**完全没有**任何 ARC 字段时返回 ``present=False`` 与
  “无 ARC 链”，不判通过（``status != "pass"``）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mailtrace.parsing.parser import parse_header_blocks

# 三类 ARC 字段（头部名大小写不敏感）
SEAL = "arc-seal"
MESSAGE_SIGNATURE = "arc-message-signature"
AUTHENTICATION_RESULTS = "arc-authentication-results"

KINDS = (SEAL, MESSAGE_SIGNATURE, AUTHENTICATION_RESULTS)
KIND_LABELS = {
    SEAL: "ARC-Seal",
    MESSAGE_SIGNATURE: "ARC-Message-Signature",
    AUTHENTICATION_RESULTS: "ARC-Authentication-Results",
}
# 页面与 JSON 中使用的稳定短名
KIND_KEYS = {
    SEAL: "seal",
    MESSAGE_SIGNATURE: "ams",
    AUTHENTICATION_RESULTS: "aar",
}

# 问题级别：结构不合法即 error
LEVEL_ERROR = "error"

# 标签解析：以分号或空白为界定位 tag=，tag 名仅由字母组成
# （i/cv/d/a/b...，数字开头的 b= 内容不会被误当成标签）。
_TAG_RE = re.compile(r"(?:^|[;\s])([A-Za-z]+)\s*=\s*([^;]*)")


@dataclass
class _Field:
    """一条 ARC 字段的解析视图。"""

    kind: str
    header_order: int          # 头部块的全局出现序号（1 起）
    raw: str                   # 原始折行文本（含字段名）
    instance_raw: str | None   # i 标签原文（strip 后）
    instance: int | None = None  # 解析出的实例号；非法或缺失时为 None
    cv: str | None = None      # 仅 ARC-Seal：规整后的 cv 值
    cv_raw: str | None = None  # 仅 ARC-Seal：cv 标签原文（strip 后）
    issues: list[dict] = field(default_factory=list)


def _parse_tags(value: str) -> dict[str, str]:
    """解析 ``tag=[;]tag=`` 形式的标签列表，标签名大小写不敏感。

    以标签名第一次出现为准（ARC 标签均不应重复）；值取到下一个分号前，
    与标签书写顺序无关。
    """
    tags: dict[str, str] = {}
    for m in _TAG_RE.finditer(value):
        name = m.group(1).lower()
        if name not in tags:
            tags[name] = m.group(2).strip()
    return tags


def _issue(code: str, message: str, order: int | None = None) -> dict:
    """构造一个可定位的问题项；order 为头部出现序号（1 起）。"""
    return {
        "level": LEVEL_ERROR,
        "code": code,
        "order": order,
        "message": message,
    }


def _build_field(kind: str, block) -> _Field:
    """从已折行展开的头部块解析一条 ARC 字段及其 i / cv 标签。"""
    fld = _Field(
        kind=kind,
        header_order=block.order + 1,
        raw=block.raw,
        instance_raw=None,
    )
    tags = _parse_tags(block.value)

    if "i" not in tags:
        fld.issues.append(
            _issue(
                "missing_i",
                f"第 {fld.header_order} 个头部 {KIND_LABELS[kind]}"
                "缺少 i 标签，无法归入任何 ARC 实例",
                fld.header_order,
            )
        )
        return fld

    i_raw = tags["i"].strip()
    fld.instance_raw = i_raw
    if not re.fullmatch(r"\d+", i_raw) or int(i_raw) < 1:
        fld.issues.append(
            _issue(
                "invalid_i",
                f"第 {fld.header_order} 个头部 {KIND_LABELS[kind]}"
                f"的 i 标签非法（{i_raw or '空'}），实例号必须是从 1 开始的正整数",
                fld.header_order,
            )
        )
        return fld
    fld.instance = int(i_raw)

    if kind == SEAL:
        # cv 是分号标签列表中的一个普通 tag（首个 Seal 常见 cv=none）
        if "cv" not in tags:
            fld.issues.append(
                _issue(
                    "missing_cv",
                    f"第 {fld.header_order} 个头部 ARC-Seal（i={fld.instance}）"
                    "缺少 cv 标签",
                    fld.header_order,
                )
            )
        else:
            fld.cv_raw = tags["cv"].strip()
            fld.cv = fld.cv_raw.lower()
    return fld


def check_arc_chain(headers: str) -> dict:
    """检查邮件头部中的 ARC 链结构，返回供页面/API 使用的结构化结果。

    返回顶层字段：
    - ``present``：是否出现任何 ARC 字段；False 时 ``status`` 为 ``"absent"``；
    - ``status``：``"pass"`` / ``"fail"`` / ``"absent"``；
    - ``summary``：实例数、各类字段计数、问题计数；
    - ``instances``：按实例号升序的逐实例视图（三类字段、期望/实际 cv、问题）；
    - ``ungrouped``：无法归入任何实例的字段（缺 i 或 i 非法）；
    - ``issues``：全部问题项（含全局与字段级，按头部出现顺序聚合）。
    """
    blocks = parse_header_blocks(headers)
    arc_blocks = [b for b in blocks if b.name.lower() in KINDS]

    if not arc_blocks:
        return {
            "present": False,
            "status": "absent",
            "message": "无 ARC 链：头部中未出现任何 ARC 字段"
            "（ARC-Seal / ARC-Message-Signature / "
            "ARC-Authentication-Results）",
            "summary": {
                "instance_count": 0,
                "field_count": 0,
                "seal_count": 0,
                "ams_count": 0,
                "aar_count": 0,
                "expected_count": 0,
                "issue_count": 0,
            },
            "instances": [],
            "ungrouped": [],
            "issues": [],
        }

    grouped: dict[int, dict[str, list[_Field]]] = {}
    ungrouped: list[_Field] = []
    counts = {SEAL: 0, MESSAGE_SIGNATURE: 0, AUTHENTICATION_RESULTS: 0}

    for block in arc_blocks:
        kind = block.name.lower()
        counts[kind] += 1
        fld = _build_field(kind, block)
        if fld.instance is None:
            ungrouped.append(fld)
            continue
        grouped.setdefault(fld.instance, {k: [] for k in KINDS})[kind].append(fld)

    instances: list[dict] = []
    instance_issues: list[dict] = []
    expected_cv = {1: "none"}  # i=1 必须 none，i>=2 必须 pass

    if grouped:
        max_i = max(grouped)
        expected = set(range(1, max_i + 1))
    else:
        expected = set()

    for i in sorted(grouped):
        fields = grouped[i]
        issues: list[dict] = []

        # 重复字段：同一实例同类字段多于一条
        for kind in KINDS:
            total = len(fields[kind])
            for dup in fields[kind][1:]:
                issues.append(
                    _issue(
                        "duplicate_field",
                        f"实例 i={i} 的 {KIND_LABELS[kind]} 字段重复"
                        f"（共 {total} 条；该条为第 {dup.header_order} 个头部），"
                        "每类字段每实例只允许一条",
                        dup.header_order,
                    )
                )

        # 缺失字段：实例应三类各一条
        for kind in KINDS:
            if not fields[kind]:
                issues.append(
                    _issue(
                        "missing_field",
                        f"实例 i={i} 缺少 {KIND_LABELS[kind]} 字段",
                    )
                )

        # cv 校验：i=1 的 Seal 为 none，其余为 pass；
        # 即使 Seal 重复，每一条 Seal 的 cv 都单独校验定位。
        seal_fields = fields[SEAL]
        seal_status = "present"
        if not seal_fields:
            seal_status = "missing"
        else:
            expected_cv_value = expected_cv.get(i, "pass")
            for seal in seal_fields:
                issues.extend(seal.issues)  # 缺 cv 等字段级问题
                if seal.cv is not None and seal.cv != expected_cv_value:
                    issues.append(
                        _issue(
                            "bad_cv",
                            f"实例 i={i} 的 ARC-Seal（第 {seal.header_order} 个头部）"
                            f"cv={seal.cv_raw}，应为 {expected_cv_value}"
                            + ("（首个实例的 cv 必须为 none）" if i == 1 else ""),
                            seal.header_order,
                        )
                    )

        instances.append(
            {
                "instance": i,
                "expected_cv": expected_cv.get(i, "pass"),
                "seal_cv": seal_fields[0].cv if seal_fields else None,
                "seal_status": seal_status,
                "fields": {
                    KIND_KEYS[kind]: _field_to_dict(fields[kind][0])
                    if fields[kind]
                    else None
                    for kind in KINDS
                },
                "field_count": sum(
                    1 for kind in KINDS if fields[kind]
                ),
                "duplicate_count": sum(
                    max(0, len(fields[kind]) - 1) for kind in KINDS
                ),
                "issues": issues,
            }
        )
        instance_issues.extend(issues)

    # 跳号：以已出现的最大实例号为准，1..max 中缺失的实例
    gap_issues: list[dict] = []
    for i in sorted(expected - set(grouped)):
        after = next((j for j in sorted(grouped) if j > i), None)
        if after is None:
            detail = f"实例 i={i} 缺失（跳号），实例号必须从 1 开始连续"
        else:
            detail = (
                f"实例 i={i} 缺失但存在 i={after}（跳号），"
                "实例号必须从 1 开始连续"
            )
        gap_issues.append(_issue("gap", detail))

    ungrouped_issues = [issue for fld in ungrouped for issue in fld.issues]

    all_issues = ungrouped_issues + gap_issues + instance_issues
    all_issues.sort(key=lambda x: (x["order"] is None, x["order"] or 0, x["code"]))

    status = "pass" if not all_issues and not gap_issues else "fail"
    message = (
        f"ARC 链结构正常：{len(instances)} 个实例（i=1..i={len(instances)}），"
        "三类字段齐全，首个 Seal cv=none、其余 cv=pass"
        if status == "pass"
        else f"ARC 链结构异常：发现 {len(all_issues)} 个问题"
    )

    return {
        "present": True,
        "status": status,
        "message": message,
        "summary": {
            "instance_count": len(instances),
            "field_count": len(arc_blocks),
            "seal_count": counts[SEAL],
            "ams_count": counts[MESSAGE_SIGNATURE],
            "aar_count": counts[AUTHENTICATION_RESULTS],
            "expected_count": len(expected),
            "issue_count": len(all_issues),
        },
        "instances": instances,
        "ungrouped": [_field_to_dict(fld) for fld in ungrouped],
        "issues": all_issues,
    }


def _field_to_dict(fld: _Field) -> dict:
    return {
        "kind": KIND_KEYS[fld.kind],
        "kind_label": KIND_LABELS[fld.kind],
        "order": fld.header_order,
        "instance_raw": fld.instance_raw,
        "instance": fld.instance,
        "cv": fld.cv,
        "cv_raw": fld.cv_raw,
        "issues": fld.issues,
        "raw": fld.raw,
    }
