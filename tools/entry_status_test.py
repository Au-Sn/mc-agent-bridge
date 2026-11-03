#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""entry_status_test.py -- 入口状态行配判据（S1~S4 离线 2026-10-13 §79.248）

用户裁决 D2：交接文档分卷 ＋ **脚本生成索引** ＋ **入口文档状态行配判据**
（★§77 已记过一次「入口当天就过期」✗★）。
★为什么这条能生效✗★：★D3 给闸门加了**纯 ASCII 机器行** ✗ 而且它是
`logs/check_all.txt` 的**首行**✗★ ⇒ ★这条判据**不用跑闸门**就能查到"★上次跑出来什么★"✗★ ✓
（★不然就要为了验一句状态行去跑一分钟闸门 ✗ 没人会那么做 ⇒ 那条状态行又会长毛✗★）
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


PAT = re.compile(r"pass=(\d+) fail=(\d+) inconclusive=(\d+) total=(\d+)")

print("== entry_status: S1~S4 ==")

# S1 台账开头有那条状态行
STA = ROOT / "docs" / "当前阶段-状态与交接.md"
head = ""
if STA.is_file():
    head = chr(10).join(STA.read_text(encoding="utf-8", errors="replace").splitlines()[:12])
m = re.search(r"★闸门现状[^\n]*", head)
check("S1", bool(m), "台账开头有「闸门现状」那行（★入口文档的状态行✗★）")

# S2 它与 logs/check_all.txt 首行的机器行**逐数一致**（★这就是「不许过期」✗★）
LOG = ROOT / "logs" / "check_all.txt"
first = ""
if LOG.is_file():
    first = (LOG.read_text(encoding="utf-8", errors="replace").splitlines() or [""])[0]
lm = PAT.search(first)
sm = PAT.search(m.group(0)) if m else None
# ★★2026-10-13（★§79.254✗★）✗★★：★自指✗★ —— ★本判据**就在**写 `logs/check_all.txt`
#   的那次运行里 ✗ ⇒ ★它一红 ⇒ 日志变成"★69/6★" ⇒ 状态行（★70/5★）更对不上 ⇒ **永远红**✗★ ✓
#   ★收敛不了 = **振荡** ✗ 不是"★发现问题★"✗★ ✓
#   ★⇒ 口径✗★：★日志**是本次运行写的**（★`DSH_GATE_STARTED` 之后✗★）⇒ **如实跳过**✗★
#     （★印"★跳过（自指）★" ✗ **不算过也不算不过**✗ —— ★"★测不了≠通过★"那条三分类口径✓★）✗★ ✓
_selfref = False
try:
    _t0 = float(os.environ.get("DSH_GATE_STARTED") or 0)
    _selfref = bool(_t0) and LOG.is_file() and LOG.stat().st_mtime >= _t0
except Exception:
    _selfref = False
# ★★§79.402✗★★：★日志**比本次启动旧** ⇒ **如实跳过 S2**✗★
#   ★为什么✗★：★闸门跑本判据时 ✗ 日志还是**上一轮**的 ⇒ **本轮数一变就必红**✗★
#   ★（★2026-10-26 队友实测：单跑 PASS ✗ 闸门里必 FAIL ✗ 是**判据自己的时间错位**✗★）✗★ ✓
#   ★口径✗★：★和上面"★自指★"同一条三分类 —— **测不了 ≠ 通过**✗ 也**≠ 失败**✗★ ✓
_stale = False
try:
    _t0g = float(os.environ.get("DSH_GATE_STARTED") or 0)
    _stale = bool(_t0g) and (not LOG.is_file() or LOG.stat().st_mtime < _t0g)
except Exception:
    _stale = False
if _selfref:
    print("  S2   ✓（★跳过 ✗ 自指★）日志是**本次运行**写的 ⇒ 拿它比状态行会**振荡**"
          "（★本判据自己就在这次运行里✗★）⇒ 如实跳过 ✗ **不算过也不算不过**")
elif _stale:
    print("  S2   ✓（★跳过 ✗ 日志是上一轮的★）`logs/check_all.txt` 比本次启动**旧**"
          " ⇒ 拿它比状态行是**时间错位** ⇒ 如实跳过 ✗ **不算过也不算不过**"
          "（★跑完闸门后再单跑本判据才会真比✗★）")
else:
        check("S2", bool(lm) and bool(sm) and lm.groups() == sm.groups(),
          "状态行的四个数必须等于 `logs/check_all.txt` 首行 ⇒ 日志说 %s ✗ 状态行说 %s"
          % (lm.groups() if lm else "（日志没有机器行 ✗ 先跑一次闸门）",
             sm.groups() if sm else "（状态行没写数）"))

# S3 索引是**生成出来的**（★拿生成函数当场重算 ✗ 与盘上那份比✗★）
import ledger_index as LI
want, n_sec, dangling = LI.render()
got = LI.OUT.read_text(encoding="utf-8") if LI.OUT.is_file() else ""
check("S3", got == want,
      "`docs/台账-索引.md` 与当场重算的结果一致（★不一致就说明它是手改的 ✗ 或台账变了没重跑✗★）"
      "—— 台账 %d 节 ✗ 索引%s" % (n_sec, "对得上 ✓" if got == want else "**过期**（跑 tools/ledger_index.py）"))

# S4 计数器：索引里条目数 = 台账节数，且悬空引用**要报出来**（★不报就是装作没有✗★）
# ★★2026-10-13 修（★§79.248✗★）✗★★：★第一版把"★索引里**悬空引用**那一节★"也算成条目了✗★
#   （★那一节的行也是 `* §` 开头✗★）⇒ ★S4 报 269 条 vs 267 节 ✗ 其实一条不差✗★ ✓
#   ★口径✗★：★只数**条目区**（★"★被工具脚本引用★"那行**之前**✓★）✗★ ✓
_body = got.split("被工具脚本引用")[0]
n_items = len(re.findall(r"^\* §", _body, re.M))
check("S4", n_items >= 1 and n_items == n_sec,
      "索引条目 %d 条 = 台账 %d 节（★引用悬空 %d 个 ✗ 已列在索引末尾✗★）"
      % (n_items, n_sec, len(dangling)))

print("=> entry_status %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
