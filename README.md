# 📮 MailTrace — 邮件投递路径检查器

一个轻量的 Python Flask 网页应用，帮助开发者检查邮件**原始头部**（raw headers）的投递路径：

- 自动处理 **折行（folding）字段**，按 RFC 5322 展开续行；
- 提取每一个 `Received` 字段中的时间戳，统一换算为 **UTC**；
- 按邮件**实际投递先后**排列中继节点（发件方 → 收件方），而不是按头部里的书写顺序；
- 计算并展示**相邻节点耗时**（含端到端总耗时）；
- **无法解析的时间标记为异常，但保留原始字段**（可展开查看）；
- **缺少时间的节点仍然列出**，不会被丢弃；
- 识别时钟偏移/时间倒灌（上一节点时间晚于本节点）并告警；
- 提取 `from` / `by` / `via` / `with` / `id` 与对端 IPv4/IPv6 地址；
- **双邮件头路径对照**：分别粘贴两份头部，复用同一套 Received 解析结果，
  按投递结构顺序对中继节点做**保序全局对齐**，并列展示**共有 / 新增（仅 B）/ 缺失（仅 A）**节点；
  共有节点展示两份各自的相邻耗时与差值（B−A），任一侧时间无效时明确显示“不可比较”。
- **多封邮件慢段归因**：页面一次粘贴**至少三份**用分隔行分开的原始头部
  （`===== 下一封邮件 =====`，也支持 `---`、`###`、`***` 等分隔行），
  或调用 `POST /api/batch-delays`（`headers` 字符串数组），复用同一套
  Received 解析，按各邮件投递顺序中**实际相邻的两个节点**聚合慢段，
  输出每段的样本数、中位耗时、最大耗时（从慢到快排序），并统计
  因时间无效 / 时间倒灌被排除的区段数。
- **单封邮件脱敏分享**：分析页点击 **“下载脱敏报告”**（或调用
  `POST /api/analyze/share`，输入 `headers` 字符串），按投递顺序为不同
  主机名、IP 分别分配**本次请求内稳定**的 `H1`、`IP1` 等别名；同一值在
  节点、来源与上一跳标签中保持一致，缺失值留空。报告**仅白名单输出**
  路径顺序、别名、UTC 时间、相邻耗时及异常级别与说明，不含原始头部、
  邮件摘要、Received ID 等可识别文本；没有 `Received` 字段时返回 400。
- **ARC 链结构检查**：页面 **“🔏 ARC 链结构检查”** 区块（或调用
  `POST /api/arc/check`，输入 `headers` 字符串）按
  `ARC-Seal` / `ARC-Message-Signature` /
  `ARC-Authentication-Results` 三类字段的 `i` 标签归组：要求每个实例
  三类字段**各一条**、实例号从 **1 连续**；首个（i=1）Seal 的 `cv` 必须为
  `none`、后续实例必须为 `pass`。对**非法 i、缺失 i、重复 / 缺失字段、
  跳号、cv 异常**逐项给出带头部出现序号的定位信息；字段折行与标签书写
  顺序变化仍能识别（复用同一套折行解析）。头部中**完全没有 ARC 字段时
  返回“无 ARC 链”（`status:"absent"`），不判通过**。仅做结构检查，
  不验证 DKIM 签名本身的密码学有效性。

解析核心（`mailtrace/`）仅依赖 Python 标准库，可脱离 Flask 单独使用或被其他程序导入。

---

## 一条命令启动

### 方式一：Docker Compose（推荐）

```bash
docker compose up -d --build
```

然后浏览器访问：

```
http://localhost:8000
```

ARC 链检查即位于首页的 **“🔏 ARC 链结构检查”** 区块；本地接口地址为
`http://localhost:8000/api/arc/check`（默认端口 **8000**，由 Compose
环境变量 `HOST_PORT` 控制宿主机映射端口，改端口后同步替换 URL 中的端口）。

### 方式二：仅用 Docker

```bash
docker build -t mailtrace . && docker run --rm -p 8000:8000 mailtrace
```

访问 `http://localhost:8000`。

> 容器在**启动时**会执行一次 `pip install -r requirements.txt`（见 `entrypoint.sh`），
> 因此即使基础镜像内没有预装依赖，依赖也会随容器启动自动安装；
> Dockerfile 在构建阶段也会预装一次以加速常规启动。
> 离线或希望跳过启动安装时，设置环境变量 `SKIP_STARTUP_INSTALL=1`。

停止服务：`docker compose down`。

---

## 使用方法

1. 打开 `http://localhost:8000`；
2. 把邮件的**原始头部**（Gmail 的“显示原始邮件”、Outlook 的“查看邮件来源”等）完整粘贴到
   **头部 A** 文本框（也可以点“填入示例”，会同时填入 A、B 两份示例）；
3. 点击 **分析投递路径（A）** 查看单份头部的投递时间线；
   需要把路径**脱敏后分享**（如发给同事排查、贴到工单）时，直接点
   **“下载脱敏报告”**，浏览器会保存 `mailtrace-share-report.json`
   （基于当前“头部 A”，无需先分析；原始主机名 / IP 不会出现在报告里）；
4. 或在 **头部 B** 中粘贴另一份头部，点击 **对照 A / B 路径** 查看双邮件头对照结果；
5. 需要在**多封邮件之间定位慢段**时，把至少三份原始头部粘贴到
   **“多封邮件慢段归因”** 文本框，邮件之间单独一行写分隔符
   `===== 下一封邮件 =====`（可点“填入 3 封示例”参考格式），
   点击 **慢段归因（多封）**。
6. 需要检查 **ARC 链结构**时，把含 `ARC-Seal` /
   `ARC-Message-Signature` / `ARC-Authentication-Results` 的原始头部
   粘贴到 **“🔏 ARC 链结构检查”** 文本框（或点“复制头部 A”），
   点击 **检查 ARC 链**：页面逐个实例展示三类字段与 cv 状态及总状态；
   完全没有 ARC 字段时显示“无 ARC 链”，不会判通过。

慢段归因的聚合口径：

- 聚合单位是每封邮件投递顺序中**实际相邻的两个节点**组成的有向区段（上游 → 下游），
  不会跳过中间节点拼接耗时；
- 节点身份是**规范化 `by` 主机名与对端 IP 的完整已知字段组合**：
  主机名忽略大小写与末尾点，缺失字段保留为“未知”——因此 `(mx, 1.2.3.4)` 与
  `(mx, 未知 IP)` 属于不同节点；区段任一端完全没有身份（by 与 IP 都缺失）时，
  该区段会被计数但**不与其他邮件合并**；
- 同一封邮件里同一区段重复出现（退信、重试、绕环）时，只把其中**最大的有效非负耗时**
  作为该邮件在这一区段上的唯一样本（界面会显示归并掉的重复区段数）；
- 相邻两跳任一时间缺失 / 无法解析 → 计入“时间无效”；
  下游时间早于上游（负耗时，时间倒灌 / 时钟偏移）→ 计入“时间倒灌”，两者均不进入统计；
- 每个区段输出 **样本数、中位耗时、最大耗时**，整体按中位耗时**从慢到快**排序。

单份分析页面以时间线形式展示每个中继节点：节点名称、UTC 时间、from/by/协议、对端 IP、
距上一节点耗时、异常/告警，以及可展开的**原始 `Received` 文本（保留折行）**。

对照结果以表格并列展示（行顺序为投递顺序：发件方 → 收件方）：

- **共有**：两侧身份一致的节点（匹配依据为 `by` 主机与对端 IP，任一冲突即视为不同节点；
  同名节点重复出现时按结构顺序保序全局对齐，而非首次命中；
  `by` 与对端 IP 都缺失的节点没有身份，不会仅凭时间相近配对）；
- **新增**：仅出现在 B 侧的节点；**缺失**：仅出现在 A 侧的节点；
- 共有节点展示 A、B 各自到上一相邻节点的耗时及差值（B−A）；
  任一侧时间无效时显示“不可比较”，不会跳过中间无效节点拼接耗时。

也提供 JSON 接口，便于脚本调用：

```bash
# 单份头部分析
curl -s -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"headers": "Received: by mx.example; Tue, 23 Sep 2026 10:00:00 +0800"}'

# 单份头部脱敏分享报告（别名化，可安全外发）
curl -s -X POST http://localhost:8000/api/analyze/share \
  -H 'Content-Type: application/json' \
  -d '{"headers": "Received: by mx.example; Tue, 23 Sep 2026 10:00:00 +0800"}'

# 双邮件头路径对照
curl -s -X POST http://localhost:8000/api/compare \
  -H 'Content-Type: application/json' \
  -d '{
        "headers_a": "Received: by mx.example; Tue, 23 Sep 2026 10:00:00 +0800",
        "headers_b": "Received: by mx.example; Tue, 23 Sep 2026 10:00:05 +0800"
      }'
```

`/api/analyze/share` 返回脱敏报告：主机名按投递顺序得到 `H1`、`H2`……，
IP 独立编号为 `IP1`、`IP2`……（别名仅在**本次请求内**稳定）。主机名比较
忽略大小写与末尾点，方括号 IP 字面量（`[10.0.0.1]`、`[IPv6:…]`）与解析出的
同一 IP 共享别名；同一值在 `node` / `from_host` / `delay_from` 中始终一致，
缺失身份、时间或耗时时对应字段为 `null`。输出字段为固定白名单，
**不含**原始 Received 文本、邮件摘要、Received `id`、`via` / `with` 等内容：

```json
{
  "host_aliases": ["H1", "H2"],
  "ip_aliases": ["IP1"],
  "path": [
    {
      "path_index": 1,
      "node": "H1",
      "from_host": "IP1",
      "ip": "IP1",
      "time_utc": "2026-09-23 02:02:00 UTC",
      "delay_from": null,
      "delay_seconds": null,
      "delay_human": null,
      "anomalies": []
    },
    {
      "path_index": 2,
      "node": "H2",
      "from_host": "H1",
      "ip": "IP1",
      "time_utc": "2026-09-23 02:03:00 UTC",
      "delay_from": "H1",
      "delay_seconds": 60.0,
      "delay_human": "1 分 0 秒",
      "anomalies": [
        {"level": "warn", "message": "……（仅通用解析说明，不含原文）……"}
      ]
    }
  ]
}
```

- 输入复用 `/api/analyze` 的同一套限制：`headers` 必须是字符串，
  空白输入、超过 `MAX_INPUT_KB` 上限或没有 `Received` 字段时返回 400；
- 页面 **“下载脱敏报告”** 按钮即以当前“头部 A”调用该接口，
  成功后把 JSON 保存为 `mailtrace-share-report.json`。

`/api/compare` 返回 `alignment.rows`（每行 `kind` 为 `common` / `added` / `missing`）
及 `common_count` / `added_count` / `missing_count` 统计；共有行内含
`delay_a_seconds`、`delay_b_seconds`、`delay_diff_seconds` 与可读形式。
任一侧没有 `Received` 字段时返回 400 及明确错误，例如：

```json
{"error": "B 侧头部中未找到 Received 字段，无法进行路径对照",
 "side_errors": {"b": "B 侧头部中未找到 Received 字段"}}
```

多封邮件慢段归因（接收 `headers` **字符串数组**，至少两项；每封邮件的完整
原始头部作为一个数组元素，分隔符切分在页面端完成）：

```bash
curl -s -X POST http://localhost:8000/api/batch-delays \
  -H 'Content-Type: application/json' \
  -d '{
        "headers": [
          "Received: by mid.example ...; ...\nReceived: by edge.example ...; ...",
          "Received: by mid.example ...; ...\nReceived: by edge.example ...; ...",
          "Received: by mid.example ...; ...\nReceived: by edge.example ...; ..."
        ]
      }'
```

返回结果（节选）：

```json
{
  "message_count": 3,
  "analyzed_count": 3,
  "message_errors": [],
  "segment_count": 2,
  "sample_count": 4,
  "excluded": {"invalid_time": 1, "backflow": 1, "identity_less": 0},
  "duplicate_collapsed": 0,
  "segments": [
    {
      "rank": 1,
      "from": {"node": "edge.example", "by_host": "edge.example", "ip": "203.0.113.50"},
      "to":   {"node": "mid.example",  "by_host": "mid.example",  "ip": "198.51.100.10"},
      "sample_count": 3,
      "median_seconds": 150.0, "median_human": "2 分 30 秒",
      "max_seconds": 600.0,    "max_human": "10 分 0 秒"
    }
  ]
}
```

- `segments` 已按**中位耗时从慢到快**排序；`from` / `to` 分别是该相邻区段的上游、
  下游节点（`ip` 为该节点在其上游 `Received` 中记录的对端 IP，可能为 `null`）；
- `excluded.invalid_time` = 因本节点或上游时间缺失 / 无法解析而排除的区段数，
  `excluded.backflow` = 因负耗时（时间倒灌）而排除的区段数，
  `excluded.identity_less` = 任一端无 by/IP 身份、未参与合并的区段数；
- `duplicate_collapsed` = 同一封邮件内同键区段重复出现、按“取最大有效非负耗时”
  归并掉的额外出现次数；
- 某封邮件没有 `Received` 字段时记入 `message_errors`（含其在数组中的序号），
  其余邮件继续分析；所有邮件都没有 `Received`、数组少于两项、元素不是字符串
  或存在空白项时返回 400。

### ARC 链结构检查

页面在 **“🔏 ARC 链结构检查”** 文本框粘贴含 ARC 字段的完整原始头部
（可点“复制头部 A”直接复用上方输入，或点“填入 ARC 示例”），点击
**检查 ARC 链**；也可调用 JSON 接口：

```bash
curl -s -X POST http://localhost:8000/api/arc/check \
  -H 'Content-Type: application/json' \
  -d '{"headers": "ARC-Seal: i=1; cv=none; a=rsa-sha256; b=...\nARC-Message-Signature: i=1; ...\nARC-Authentication-Results: i=1; mx.example; spf=pass"}'
```

返回结构（与页面渲染使用同一结构）：

```json
{
  "present": true,
  "status": "pass",
  "message": "ARC 链结构正常：2 个实例（i=1..i=2），三类字段齐全，首个 Seal cv=none、其余 cv=pass",
  "summary": {
    "instance_count": 2, "field_count": 6,
    "seal_count": 2, "ams_count": 2, "aar_count": 2,
    "expected_count": 2, "issue_count": 0
  },
  "instances": [
    {
      "instance": 1, "expected_cv": "none", "seal_cv": "none", "seal_status": "present",
      "field_count": 3, "duplicate_count": 0,
      "fields": {
        "seal": {"kind": "seal", "kind_label": "ARC-Seal", "order": 4,
                 "instance": 1, "cv": "none", "cv_raw": "none", "issues": [], "raw": "ARC-Seal: i=1; ..."},
        "ams":  {"kind": "ams",  "kind_label": "ARC-Message-Signature", "order": 5, "...": "..."},
        "aar":  {"kind": "aar",  "kind_label": "ARC-Authentication-Results", "order": 6, "...": "..."}
      },
      "issues": []
    }
  ],
  "ungrouped": [],
  "issues": []
}
```

- `status` 取值：
  - `pass`：实例号从 1 连续、每实例三类字段各一条、cv 全部符合要求；
  - `fail`：存在任一结构问题（HTTP 仍为 200，问题在 `issues` 中逐项列出）；
  - `absent`：**完全没有任何 ARC 字段**——明确返回“无 ARC 链”，
    **不会**判为通过；
  - 仅当输入超过 `MAX_INPUT_KB` 或 `headers` 不是字符串时返回 400。
- `issues[].code` 包括：`invalid_i`（i 非正整数）、`missing_i`（缺 i 标签，
  字段进入 `ungrouped`）、`duplicate_field`（同实例同类字段多条）、
  `missing_field`（实例缺某类字段）、`gap`（实例跳号）、
  `bad_cv` / `missing_cv`（Seal cv 值不对或缺失）；
  每条问题的 `order` 指向该字段在全部头部中的**出现序号**（1 起；全局
  问题如跳号为 `null`），`message` 为可直接展示的中文定位说明。
- 解析复用主分析的 RFC 5322 折行展开与标签解析：字段跨多行折行、
  标签顺序变化（如 `cv=...; i=1`）、字段名大小写混合均不影响识别；
  本检查只校验链的**结构**，不做 DKIM 签名验签。
- 也支持 `application/x-www-form-urlencoded` 表单（字段名 `headers`）；
  页面表单提交到 `POST /arc/check`（字段名 `headers_arc`）。

健康检查：`GET http://localhost:8000/healthz`。

---

## 排序原理（为什么要反转）

邮件每经过一台服务器，该服务器就把自己的 `Received` 字段**追加到头部最前面**。
因此头部文本里第一条 `Received` 是最后一跳（最靠近收件方），最后一条才是第一跳。
本工具按这一“嵌套结构”将 `Received` **反转**后呈现，得到真实投递顺序，
再用时间戳校验该顺序并计算相邻耗时。当解析出的时间出现倒挂（时钟偏差或伪造）时，会明确告警。

---

## 配置（环境变量）

| 变量 | 默认值 | 作用范围 | 说明 |
| --- | --- | --- | --- |
| `HOST_PORT` | `8000` | Compose | 宿主机映射端口（容器内服务固定监听 8000） |
| `APP_PORT` | `8000` | 容器/本地 | 容器内 gunicorn 绑定端口；改它需同步调整端口映射 |
| `APP_HOST` | `0.0.0.0` | 本地 | 直接用 Flask 开发服务器运行时的监听地址 |
| `MAX_INPUT_KB` | `256` | 容器/本地 | 单次粘贴头部的大小上限（KB），超出返回错误 |
| `SKIP_STARTUP_INSTALL` | `0` | 容器 | 设为 `1` 跳过容器启动时的 `pip install`，直接用镜像内依赖 |

### 访问端口

- Compose 默认把宿主机 **8000** 端口映射到容器 8000。
- 想换宿主机访问端口，在项目根目录创建 `.env`（或先导出环境变量再 `up`）：

```bash
echo "HOST_PORT=9000" > .env
docker compose up -d --build
# 访问 http://localhost:9000
```

也可以在运行时直接覆盖，例如：

```bash
docker run --rm -e MAX_INPUT_KB=512 -p 8080:8000 mailtrace
# 访问 http://localhost:8080
```

---

## 本地开发（不使用容器）

需要 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python wsgi.py            # Flask 开发服务器，默认 http://localhost:8000
# 或
gunicorn -b 0.0.0.0:8000 wsgi:app
```

运行解析器测试（**仅需标准库，无需安装 Flask**）：

```bash
python -m unittest discover -s tests -v
```

---

## 项目结构

```
.
├── app/                    # Flask 应用（路由、模板）
│   ├── __init__.py         # create_app()：页面 + 对照 + ARC + JSON API + 健康检查
│   └── templates/index.html
├── mailtrace/              # 纯标准库解析核心（可独立复用）
│   └── parsing/
│       ├── parser.py       # 折行展开、时间解析、路径排序、耗时与异常
│       ├── arc.py          # ARC 链结构检查：按 i 归组、连续性 / 三件套 / cv 校验
│       ├── compare.py      # 双邮件头对照：保序全局对齐、耗时差值
│       ├── batch.py        # 多封慢段归因：相邻节点对聚合、中位/最大耗时、排除计数
│       ├── share.py        # 单封脱敏分享：H1/IP1 别名化、白名单报告
│       └── sample.py       # 页面“填入示例”数据（A / B、多封批量三份及 ARC 链）
├── wsgi.py                 # gunicorn / flask 启动入口
├── entrypoint.sh           # 容器启动时安装依赖并启动 gunicorn
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── tests/                  # 解析核心、对照、脱敏、慢段归因与 ARC 单元测试
    ├── test_parser.py
    ├── test_arc.py
    ├── test_compare.py
    ├── test_share.py
    └── test_batch.py
```

## 安全与隐私

应用只在本地/你的服务器内解析粘贴内容，不向任何外部服务发送邮件头；
请仍按敏感信息对待原始头部（其中可能含内网主机名与 IP）。
需要外发排查结果时，使用**“下载脱敏报告”**（`/api/analyze/share`）：
报告只含投递顺序、`H1` / `IP1` 等本次请求内的匿名别名、UTC 时间、相邻耗时
与通用异常说明，原始头部、邮件摘要与 Received ID 等均被排除。
