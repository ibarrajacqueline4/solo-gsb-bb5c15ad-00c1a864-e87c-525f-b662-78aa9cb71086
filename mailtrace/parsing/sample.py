"""页面“填入示例”按钮使用的示例邮件头。"""

SAMPLE_HEADERS = """\
Return-Path: <sender@example.com>
Received: from mailbox.final.example (127.0.0.1)
	by mailbox.final.example (Dovecot) with LMTP id zX92kQ
	for <user@final.example>; Tue, 23 Sep 2026 10:02:10 +0800 (CST)
Received: from mx1.final.example (mx1.final.example [198.51.100.10])
	by mailbox.final.example (Postfix) with ESMTPS id 7F3A2C9
	for <user@final.example>; Tue, 23 Sep 2026 10:02:10 +0800
Received: from relay2.provider.example (relay2.provider.example [203.0.113.22])
	by mx1.final.example (Postfix) with ESMTP id B4D91
	for <user@final.example>; Tue, 23 Sep 2026 10:02:05 +0800
Received: from relay1.provider.example (relay1.provider.example
	[203.0.113.11])
	by relay2.provider.example (Postfix) with ESMTP id 99C10
	for <user@final.example>; Tue, 23 Sep 2026 02:01:55 +0000 (UTC)
Received: from outgoing.example.org (outgoing.example.org [192.0.2.50])
	by relay1.provider.example (Postfix) with ESMTP id 41AB8
	for <user@final.example>; Tue, 23 Sep 2026 02:01:30 +0000
Received: from smtp01.corp.example.net (smtp01.corp.example.net [10.10.0.5])
	by outgoing.example.org with ESMTP
	for user@final.example
Received: from [10.10.0.5] (helo=smtp01.corp.example.net)
	by smtp01.corp.example.net with ESMTP id 88FF21
	for user@final.example; not-a-valid-date (server clock lost)
Date: Tue, 23 Sep 2026 02:00:00 +0000
From: Sender <sender@example.com>
To: User <user@final.example>
Subject: Delivery path demo
	with folding
Message-ID: <demo@example.com>
"""

# 对照示例（B 侧）：与 SAMPLE_HEADERS 同一条投递链路，但
# - 开头多一跳 smtp00 -> smtp01（新增节点，且与既有 smtp01 同名，演示保序对齐）；
# - 末尾少了 Dovecot LMTP 一跳（缺失节点）；
# - 各跳时间不同（演示相邻耗时差值），smtp01 一跳时间有效而 A 侧无效（不可比较）。
SAMPLE_HEADERS_B = """\
Return-Path: <sender@example.com>
Received: from mx1.final.example (mx1.final.example [198.51.100.10])
	by mailbox.final.example (Postfix) with ESMTPS id 8C11D2
	for <user@final.example>; Tue, 23 Sep 2026 10:02:12 +0800
Received: from relay2.provider.example (relay2.provider.example [203.0.113.22])
	by mx1.final.example (Postfix) with ESMTP id C5E20
	for <user@final.example>; Tue, 23 Sep 2026 10:02:06 +0800
Received: from relay1.provider.example (relay1.provider.example [203.0.113.11])
	by relay2.provider.example (Postfix) with ESMTP id A1B33
	for <user@final.example>; Tue, 23 Sep 2026 02:01:58 +0000 (UTC)
Received: from outgoing.example.org (outgoing.example.org [192.0.2.50])
	by relay1.provider.example (Postfix) with ESMTP id 55BC9
	for <user@final.example>; Tue, 23 Sep 2026 02:01:33 +0000
Received: from smtp01.corp.example.net (smtp01.corp.example.net [10.10.0.5])
	by outgoing.example.org with ESMTP id 77D21
	for user@final.example; Tue, 23 Sep 2026 02:00:40 +0000
Received: from [10.10.0.5] (helo=smtp01.corp.example.net)
	by smtp01.corp.example.net with ESMTP id 91AA02
	for user@final.example; Tue, 23 Sep 2026 02:00:12 +0000
Received: from smtp00.corp.example.net (smtp00.corp.example.net [10.10.0.9])
	by smtp01.corp.example.net with ESMTP id 02BB77
	for user@final.example; Tue, 23 Sep 2026 02:00:05 +0000
Date: Tue, 23 Sep 2026 02:00:00 +0000
From: Sender <sender@example.com>
To: User <user@final.example>
Subject: Delivery path demo
"""


# 多封慢段归因示例：三封走同一条 edge -> mid -> final 链路的邮件，
# 用页面规范分隔符 BATCH_DELIMITER（===== 下一封邮件 =====）分开。
# - 邮件 1：正常投递，mid->final 段耗时 150 秒；
# - 邮件 2：edge->mid 耗时 600 秒（最慢段），mid->final 时间倒灌 -20 秒（排除）；
# - 邮件 3：mid->final 段时间无效（排除）；退信后发件方从同一 IP 重新注入，
#   edge->mid 同键区段在本封内出现两次（60 秒、150 秒），仅取最大有效
#   非负耗时 150 秒作为该邮件样本；退信/重注入路径另有仅本封出现的
#   mid->edge 回流段（60 秒）。
SAMPLE_HEADERS_BATCH = """\
Received: from mid.example (mid.example [198.51.100.20])
\tby final.example with ESMTP id M1C
\t; Tue, 23 Sep 2026 02:06:30 +0000
Received: from edge.example (edge.example [198.51.100.10])
\tby mid.example with ESMTP id M1B
\t; Tue, 23 Sep 2026 02:04:00 +0000
Received: from sender.example (sender.example [203.0.113.50])
\tby edge.example with ESMTP id M1A
\t; Tue, 23 Sep 2026 02:03:00 +0000
Date: Tue, 23 Sep 2026 02:03:00 +0000
From: sender@example.com
To: user@final.example
Subject: batch message 1
===== 下一封邮件 =====
Received: from mid.example (mid.example [198.51.100.20])
\tby final.example with ESMTP id M2C
\t; Tue, 23 Sep 2026 02:13:40 +0000
Received: from edge.example (edge.example [198.51.100.10])
\tby mid.example with ESMTP id M2B
\t; Tue, 23 Sep 2026 02:14:00 +0000
Received: from sender.example (sender.example [203.0.113.50])
\tby edge.example with ESMTP id M2A
\t; Tue, 23 Sep 2026 02:04:00 +0000
Date: Tue, 23 Sep 2026 02:04:00 +0000
From: sender@example.com
To: user@final.example
Subject: batch message 2
===== 下一封邮件 =====
Received: from mid.example (mid.example [198.51.100.20])
\tby final.example with ESMTP id M3D
\t; not-a-valid-date (clock lost on final)
Received: from edge.example (edge.example [198.51.100.10])
\tby mid.example with ESMTP id M3C
\t; Tue, 23 Sep 2026 02:21:00 +0000
Received: from sender.example (sender.example [203.0.113.50])
\tby edge.example with ESMTP id M3B
\t; Tue, 23 Sep 2026 02:18:30 +0000
Received: from edge.example (edge.example [198.51.100.10])
\tby mid.example with ESMTP id M3A2
\t; Tue, 23 Sep 2026 02:17:30 +0000
Received: from sender.example (sender.example [203.0.113.50])
\tby edge.example with ESMTP id M3A
\t; Tue, 23 Sep 2026 02:16:30 +0000
Date: Tue, 23 Sep 2026 02:16:30 +0000
From: sender@example.com
To: user@final.example
Subject: batch message 3
"""

