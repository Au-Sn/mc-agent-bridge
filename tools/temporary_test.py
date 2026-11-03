#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""temporary_test.py -- 临时的东西必须带替换触发（T1~T6 离线 2026-10-13 §79.243）

任务书要的「TEMPORARY 强制标签」（登记册第 4 条）。
口径：临时不是罪，「没写什么时候删」才是。
T4 是要害：不许条目只描述「当初为什么这样」，还必须说清什么条件下删掉它，
而且那条触发要能被别人认出来。
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


print("== temporary: T1~T6 ==")
p = ROOT / "state" / "temporary.json"
if not p.is_file():
    check("T1", False, "临时声明表不在：state/temporary.json")
    sys.exit(1)
d = json.loads(p.read_text(encoding="utf-8"))
rows = d.get("entries") or []

check("T1", bool(rows), "表在，有 **%d** 条临时声明" % len(rows))

_need = ("id", "what", "where", "why_temporary", "today_state", "since",
         "replace_trigger", "watched_by")
_bad = [r.get("id") for r in rows if any(not str(r.get(k) or "").strip() for k in _need)]
check("T2", not _bad, "每条都要有：%s ⇒ 缺字段的：%s"
      % ("／".join(_need), _bad or "（没有 ✓）"))

_wishy = []
for r in rows:
    trig = str(r.get("replace_trigger") or "")
    if ("删" not in trig) and ("去掉" not in trig) and ("改" not in trig):
        _wishy.append(r.get("id"))
check("T3", not _wishy, "替换触发里要有动作（删／去掉／改）⇒ 缺动作的：%s"
      % (_wishy or "（没有 ✓）"))

_unwatched = [r.get("id") for r in rows if not str(r.get("watched_by") or "").strip()]
check("T4", not _unwatched,
      "每条都要有看着它的判据（没人看着的临时就是永久）⇒ 没人的：%s"
      % (_unwatched or "（没有 ✓）"))

for r in rows:
    print("      %-26s 起于 %-12s 触发：%s"
          % (r.get("id"), str(r.get("since"))[:12], str(r.get("replace_trigger"))[:42]))

# ★★T5（★§79.252 ✗ 审计缺陷④✗★）✗★★：★"★声明对得上现实★"就必须**真的读声明**✗★ ✓
#   ★审计怎么打脸的✗★：★它把 `canopy_deletes_cell` 那条**整条删掉** ⇒ T5 **照样绿** ✗
#     ★改成反话 ⇒ 也绿 ✗ —— ★因为原来的 T5 只量 `mapread` 三个函数 ✗
#     **一个字节都没读 `temporary.json`**✗★ ✓
#   ★⇒ 现在两半都要✗★：① ★声明在不在 ✗ 它的 `today_state` 有没有说清"★今天不生效★"✗★
#     ② ★现实对不对✗（★`is_landing ＝ is_floor ∧ ¬canopy` ✗ 而今天 `is_floor(叶子)=False`✓★）✗★ ✓
import mapread as MR
_leaf = "minecraft:oak_leaves"
_phys = bool(MR.is_floor(_leaf))
_can = bool(MR._kb_canopy(_leaf))
_land = bool(MR.is_landing(_leaf))
_rows = {str(r.get("id")): r for r in rows}
_e = _rows.get("canopy_deletes_cell")
_today = str((_e or {}).get("today_state") or "")
# sec 79.457: is_landing/is_canopy are the same under both classifier sources;
#   is_floor(leaves) is True under export and False under blacklist, so it must
#   not be part of the pass condition (it is printed instead).
_reality_ok = (_land is False) and (_can is True)
_decl_ok = bool(_e) and ("不生效" in _today)
check("T5", _reality_ok and _decl_ok,
      ("★声明对得上现实★：声明在=%s ✗ today_state 说清了「今天不生效」=%s ｜ "
       "现实：is_landing=%s is_canopy=%s is_floor=%s")
      % (bool(_e), ("不生效" in _today), _land, _can, _phys))

print("=> temporary %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
