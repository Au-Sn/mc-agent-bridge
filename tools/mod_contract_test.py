#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mod_contract_test.py -- ★契约围栏的**离线判据**★（M1~M4 ✓ 不碰世界 ✓ 秒级 ✓ 2026-10-03）

★为什么要有它✗★：`mod_contract.py` 的 `--check` 要**世界**才跑得了 ✗ ⇒
  ★"★差异怎么算★"这件事必须**离线**钉住✗★（★注入两份契约 ✗ 看它列不列得出来✓★）✓
  ★否则等世界出事那天 ✗ 才发现"★原来是差异逻辑写错了★"✗★ ✓

★判据（先写死）★
  M1 ★一模一样 ⇒ 差异为空✗★（★不许"★总有几条噪音★"✗★）
  M2 ★每个计数器都要看得见✗★（vol／solid／air／kinds 各改一个 ⇒ 各报一条✓★）
  M3 ★逐种计数与逐格物种都要看得见✗★（★换掉一格东西 ⇒ 要指出**哪一格 ✗ 从什么到什么**✓★）
  M4 ★`species_of()` 切状态✗★（★`minecraft:chest,facing=east,type=SINGLE,…` ⇒ `minecraft:chest`✓★）
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

import fixtures as FX  # noqa: E402  ★判据自己 import ✗ 不蹭被测模块的命名空间✓★
import mod_contract as MC  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def mk(**kw):
    base = {"fixture": "f", "box": {"x0": 1}, "captured_at": "t",
            "counters": {"vol": 100, "solid": 10, "air": 90, "kinds": 2},
            "counts": {"minecraft:stone": 8, "minecraft:dirt": 2},
            "species_per_cell": {"1,1,1": "minecraft:stone", "2,1,1": "minecraft:dirt"}}
    base.update(kw)
    return base

print("== mod_contract_test：M1~M4 ==")

# ---- M1 一模一样 ----
check("M1", MC.diff_contract(mk(), mk()) == [], "★同一份契约 ⇒ 差异必须为空✗★")

# ---- M2 四个计数器各改一个 ----
for i, k in enumerate(("vol", "solid", "air", "kinds")):
    a = mk()
    b = mk()
    b["counters"] = dict(a["counters"])
    b["counters"][k] = a["counters"][k] + 1
    d = MC.diff_contract(a, b)
    check("M2%d" % (i + 1), len(d) == 1 and ("计数器 %s" % k) in d[0],
          "★改 %s ⇒ 报一条✗★ ⇒ %s" % (k, d[0] if d else "★没报✗★"))

# ---- M3 逐种计数 ＆ 逐格物种 ----
a = mk()
b = mk(counts={"minecraft:stone": 7, "minecraft:dirt": 2, "minecraft:coal_ore": 1})
d = MC.diff_contract(a, b)
check("M3a", any("逐种计数" in x for x in d), "★逐种计数变了 ⇒ 要报✗★ ⇒ %s" % (d[:2] or "★没报✗★"))
b2 = mk(species_per_cell={"1,1,1": "minecraft:coal_ore", "2,1,1": "minecraft:dirt"})
d2 = MC.diff_contract(a, b2)
check("M3b", len(d2) == 1 and ("1,1,1" in d2[0]) and ("stone" in d2[0]) and ("coal_ore" in d2[0]),
      "★换掉一格 ⇒ 要指出哪一格 ✗ 从什么到什么✗★ ⇒ %s" % (d2[0] if d2 else "★没报✗★"))

# ---- M4 species_of 切状态 ----
cases = (("minecraft:chest,facing=east,type=SINGLE,waterlogged=false", "minecraft:chest"),
         ("minecraft:grass_block,snowy=false", "minecraft:grass_block"),
         ("minecraft:stone", "minecraft:stone"),
         ("air", "air"))
bad = [(n, MC.species_of(n), w) for n, w in cases if MC.species_of(n) != w]
check("M4", not bad, "★切状态✗★ %s" % (bad or "全对 ✓（★含大写值 `SINGLE`✓★）"))

# ---- M5 站位：从**快照**里算（★纯函数 ✗ 注入即可✓★）
#   ★★注意✗★★：盒子 y1 必须**够高** ✗ 否则"头那格"落在盒外 ⇒ 快照读不到 ⇒
#   ★按规则**拒绝**（★安全方向：拿不到就不站✓★）—— ★第一版判据的盒子写窄了 ⇒ 红的是**判据**✗★ ✓
box = {"x0": 0, "y0": 0, "z0": 0, "x1": 4, "y1": 4, "z1": 4}
snap = {}
for (x, y, z) in FX.cells_of(box):
    snap[FX.key(x, y, z)] = "air"
# ★只在 (2,2) 铺一块地板 ✗ 其它地方都是空气 ⇒ 能站的只有 (2,3)✗★
snap[FX.key(2, 2, 2)] = "minecraft:oak_planks"
snap[FX.key(1, 2, 1)] = "minecraft:stone"
st, why = MC.stance_for(snap, box, keyfn=FX.key)
check("M5a", st is not None, "★算得出站位✗★ ⇒ %s（%s）" % (st, why))
if st:
    x, y, z = st
    check("M5b", snap[FX.key(x, y - 1, z)] != "air" and snap[FX.key(x, y, z)] == "air"
          and snap[FX.key(x, y + 1, z)] == "air",
          "★站位必须是「脚下实心 ＋ 脚头空气」✗★ ⇒ (%d,%d,%d)" % (x, y, z))
    # ★两个候选里 (2,3,2) 离中心更近（中心 (2,2)）✗ 应当选它✗★
    check("M5c", (x, z) == (2, 2), "★离中心近的优先✗★ ⇒ 实得 (%d,%d)" % (x, z))

# ---- M5d 算不出来 ⇒ 必须说原因（★不许瞎给一个✗★）
snap0 = {FX.key(x, y, z): "air" for (x, y, z) in FX.cells_of(box)}
st0, why0 = MC.stance_for(snap0, box, keyfn=FX.key)
check("M5d", (st0 is None) and ("站不了" in why0), "★全是空气 ⇒ 站不了 ＋ 说原因✗★ ⇒ %s" % why0)

# ---- M6 地图那一半：原文变了要报（★一边没成功时**不算差异** ✗ 由调用方判测不了✓★）
a = mk()
a["map"] = {"ok": True, "stance": [1, 2, 3], "raw": "line1\nline2"}
b = mk()
b["map"] = {"ok": True, "stance": [1, 2, 3], "raw": "line1\nLINE-TWO-CHANGED"}
d3 = MC.diff_contract(a, b)
check("M6a", any("地图原文变了" in x for x in d3), "★地图变了要报✗★ ⇒ %s" % (d3[-2:] or "★没报✗★"))
b2 = mk()
b2["map"] = {"ok": False, "why": "站不回去"}
d4 = MC.diff_contract(a, b2)
check("M6b", not any("地图" in x for x in d4),
      "★一边没成功 ⇒ **不算差异**（★要由调用方判「测不了」✓★）✗★ ⇒ %s" % (d4 or "★空 ✓★"))

print("=> mod_contract %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
