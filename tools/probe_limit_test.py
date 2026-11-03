#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_limit_test.py -- 探针两条红线**真的**执行（L1~L5 离线 2026-10-13 §79.233）

用户裁决 E2：实现 `timeout_ms/budget`（★安慰剂 API 比没有更坏✗★）。
口径：两条红线**都报 `timeout`**（闭集冻结，不许加成员），`evidence["limit"]` 说清哪条。
★守三件事✗★：红线**真的**踩得住／踩住时 `reachable` **必须 `unknown`**／没踩住时答案照旧。
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import reach_probe as RP

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


def world():
    """★一条三格长的走廊✗★（★地板 ＋ 空气✗★）—— 注入的**完整**世界"""
    cells = {}
    for x in range(-10, 13):
        for z in range(-10, 13):
            for y in range(-4, 5):
                cells[(x, y, z)] = "minecraft:stone" if y <= -3 else "minecraft:air"
    return cells


S, Tt = (0, -2, 0), (2, -2, 0)
print("== probe_limit: L1~L5 ==")

d_ok = RP.reach_probe(S, Tt, timeout_ms=60000, budget=None, scan_fn=lambda b: world())
check("L3", d_ok.get("reachable") == "yes" and d_ok.get("why_not") is None,
      "红线没踩时答案照旧 ⇒ reachable=%s layers=%s why_not=%s"
      % (d_ok.get("reachable"), d_ok.get("layers"), d_ok.get("why_not")))

d_t = RP.reach_probe(S, Tt, timeout_ms=0, budget=None, scan_fn=lambda b: world())
check("L1", d_t.get("reachable") == "unknown" and d_t.get("why_not") == "timeout"
      and (d_t.get("evidence") or {}).get("limit") == "wall_clock",
      "墙钟 0 ⇒ reachable=%s why_not=%s limit=%s"
      % (d_t.get("reachable"), d_t.get("why_not"), (d_t.get("evidence") or {}).get("limit")))

d_b = RP.reach_probe(S, Tt, timeout_ms=60000, budget=0, scan_fn=lambda b: world())
check("L2", d_b.get("reachable") == "unknown" and d_b.get("why_not") == "timeout"
      and (d_b.get("evidence") or {}).get("limit") == "budget",
      "预算 0 ⇒ reachable=%s why_not=%s limit=%s"
      % (d_b.get("reachable"), d_b.get("why_not"), (d_b.get("evidence") or {}).get("limit")))

# ★★2026-10-13（★第三轮扫描 PL-L4-closed 抓的**真缺陷**✗★）✗★★：
#   ★现象✗★：★我往 `WHY_NOT` 里加一个成员 ✗ 这条判据**照样绿**✗★ ✓
#   ★真因✗★：★它只查"★**观测到的**理由在闭集里★"＋"★那两个理由都是 `timeout`★"✗★ ⇒
#     ★而它的**判词**写的是"★闭集没被加成员★"✗★ ⇒ ★★**主张超出了实现**✗★★ ✓
#   ★⇒ 口径✗★：★主张什么 ✗ 就查什么✗★ —— ★把**闭集本身**的成员与条数写死✗★ ✓
_WHY_NOT_EXPECT = ("step_too_high", "wall_too_high", "gap", "sealed",
                   "outside_box", "unknown_region", "timeout", "not_implemented")
check("L4a", tuple(RP.WHY_NOT) == _WHY_NOT_EXPECT,
      "★闭集**本身**必须是那 8 个 ✗ 不许加也不许减★（★§79.233 冻结✗★）⇒ 现在 %d 个：%s"
      % (len(RP.WHY_NOT), "／".join(RP.WHY_NOT)))
_whys = {d_t.get("why_not"), d_b.get("why_not")}
check("L4", _whys <= set(RP.WHY_NOT) and _whys == {"timeout"},
      "两条红线都报闭集成员 `timeout` ⇒ %s（★闭集没被加成员✗★：%d 个）"
      % (_whys, len(RP.WHY_NOT)))

# ★★L5：注入纯度✗★★（★§79.234✗★）—— ★注入了扫描就**不许**再去连世界✗★ ✓
#   判法：把 `_is_air_by_height` 单独问一次（★不给来源✗★）⇒ 必须**立刻**回 `None`
import time as _t
_t0 = _t.monotonic()
_h = RP._is_air_by_height((0, -2, 0), None)
_el = _t.monotonic() - _t0
check("L5", _h is None and _el < 1.0,
      "没给列顶来源 ⇒ `_is_air_by_height` 回 **None** 且**立刻**（%.3f 秒）"
      " —— 原来它会自己去 `mapread.Reader().get(...)`（★实测 17.2 秒✓★）"
      "⇒ ★注入式扫描其实一直在偷偷读世界✗★" % _el)

print("=> probe_limit %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
