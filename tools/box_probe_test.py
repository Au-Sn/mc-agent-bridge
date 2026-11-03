#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""box_probe_test.py -- ★★"我改的世界动了没有"的判据✗★★（B1~B6 ✓ 离线 ✓）

★它守的是 ① 那六跑换来的三条口径✗★（★§79.48✓★）
  B1 ★放上去 ⇒ `solid` **+1**✗★
  B2 ★多重集（★解析后排序的 counts✗★）**也** +1✗★
  B3 ★挖掉 ⇒ **逐项**回基线✗★（★不是"solid 对了就行" ✗ 要**每一项**都对✓★）
  B4 ★★"读不到"必须回 `None`／判红✗★★（★不许冒充"盒里是空的"✗★）
  B5 ★"安静"＝多重集一致 ✗ **排列顺序不同也算安静**✗★（★§79.45 的假红修掉✓★）
  B6 ★"脚下是不是整方块"✗★：★薄板（★CC 薄板那类✓★）不许算 ✓
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import box_probe as P  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


B = "dshscan vol=27 solid=5 air=22 kinds=5 matched=0 shown=0 counts[a:2,b:1,c:1,d:1]"
AP = "dshscan vol=27 solid=6 air=21 kinds=6 matched=0 shown=0 counts[a:2,b:1,c:1,d:1,e:1]"
AD = "dshscan vol=27 solid=5 air=22 kinds=5 matched=0 shown=0 counts[a:2,b:1,c:1,d:1]"

print("== box_probe_test：B1~B6 ==")
v, d = P.verdict(B, AP, AD, "e")
check("B1", v and d["M8a solid+1"], "★放上去 ⇒ solid +1✗★（%s）" % d["solid"])
check("B2", v and d["M8b 多重集+1"], "★多重集也 +1✗★（%s）" % d["counts 项数"])

# ★B3：★`solid` 对了 ✗ 但多出来一个**别的**方块 ⇒ 也是"没逐项回基线"✗★
AD2 = "dshscan vol=27 solid=5 air=22 kinds=5 matched=0 shown=0 counts[a:2,b:1,c:1,z:1]"
v2, d2 = P.verdict(B, AP, AD2, "e")
check("B3", (not v2) and (d2["M8d 逐项回基线"] is False),
      "★挖掉后多出一个 `z` ⇒ **不许**判过✗★（★逐项比 ✗ 不是只比 solid✓★）")

check("B4", P.parse_scan("") is None and P.fingerprint("") is None
      and P.is_quiet("", B) is None,
      "★读不到 ⇒ `None`（★不冒充「盒里是空的」✓★）")

# ★B5：★同一批方块 ✗ 排列顺序不同 ⇒ **算安静**✗★（★§79.45 的假红就是这个✓★）
Q1 = "dshscan vol=27 solid=5 air=22 kinds=5 counts[a:2,b:1,c:1,d:1]"
Q2 = "dshscan vol=27 solid=5 air=22 kinds=5 counts[d:1,c:1,b:1,a:2]"
check("B5", P.is_quiet(Q1, Q2) is True,
      "★顺序不同 ⇒ 还是安静✗★ ✓（★这才是 §79.45 要的✓★）")

# ★★B6 的样本要**写全**✗★★（2026-10-03 ✓ 当场吃到）：★`parse_scan` 要 `counts/air/kinds` 齐全✗★
#   ⇒ ★我第一版只写了 `solid=` ⇒ 它回 `None` ⇒ `full_cube_below` 判 false ⇒ **假红**✗★
#   ⇒ ★而"读不到 ⇒ 不算整方块"这条**规则是对的**（★宁可保守 ✓★）✗ 该修的是**样本**✓★
_SOLID = "dshscan vol=1 solid=1 air=0 kinds=1 counts[%s:1]"
check("B6", P.full_cube_below(_SOLID % "minecraft:grass_block")
      and not P.full_cube_below(_SOLID % "computercraft:wireless_modem_normal"),
      "★草算整方块 ✗ CC 薄板不算✗★ ✓")

print("=> box_probe %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
