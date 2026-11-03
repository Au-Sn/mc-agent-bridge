#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""passclass_test.py -- ★类别层的判据✗★（P1~P7 ✗ 全离线 ✓ 2026-10-05）

★★这一层最容易出的错是"★政策越界影响物理★"✗★★ ⇒ 判据的**一半**是查这个✗★ ✓
★★而另一半是那条铁律✗★★：★`UNKNOWN` **永不**静默当 `AIR`✗★ ✓
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

import blockkb as KB  # noqa: E402
import passclass as PC  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== passclass_test：P1~P7 ==")

# ---- P1 基本类别
_c = {sp: PC.class_of(sp)[0] for sp in
      ("minecraft:air", "minecraft:stone", "minecraft:water", "minecraft:oak_leaves")}
check("P1", _c["minecraft:air"] == "AIR" and _c["minecraft:stone"] == "SOLID"
      and _c["minecraft:water"] == "LIQUID" and _c["minecraft:oak_leaves"] == "CANOPY",
      "★air⇒AIR ✗ stone⇒SOLID ✗ water⇒LIQUID ✗ leaves⇒CANOPY✗★ ⇒ %s" % _c)

# ---- P2 ★★`UNKNOWN` 一等公民：没读到**永不**当 `AIR`★★
_u = PC.class_of(None)
check("P2", _u[0] == "UNKNOWN" and _u[1] == "not_read",
      "★★`None`（★没读到✗★）⇒ **`UNKNOWN`** ✗ **不是** `AIR`✗★★ ⇒ %s" % (_u,))

# ---- P3 每类自带栏，且栏只有三种
# ★★2026-10-13（★用户裁决 C2✗★）✗★★：★`none` 这一栏**退役**✗★ ——
#   ★`UNKNOWN` 已归 `phys`✗ 而"★认不出★"如实回 `None` ✗ 不再有第三栏✗★ ✓
_bad = [c for c, f in PC.FAMILY.items() if f not in ("phys", "policy")]
check("P3", not _bad, "★每个类别都带栏（phys／policy／none）✗★ ⇒ 坏的 %s" % (_bad or "无"))

# ---- P4 ★★政策**不许**越界：类别层的存在不改物理★★
_sp = "minecraft:oak_leaves"
_before = KB.blocks_space(_sp)
PC.class_of(_sp)
_after = KB.blocks_space(_sp)
check("P4", _before == _after,
      "★★问过类别层之后 ✗ `blocks_space` **必须不变**✗★★ ⇒ %s ⇒ %s" % (_before, _after))

# ---- P5 ★树冠是**政策**类 ✗ 而它的**物理**仍由碰撞说了算
check("P5", PC.family_of("CANOPY") == "policy" and KB.blocks_space(_sp) is True,
      "★`CANOPY` 归**政策栏** ✗ 而树叶**照样挡人**（★碰撞✓★）✗★")

# ---- P6 ★`DANGER` 现在**没有声明来源** ⇒ 不许命中（★已查实：27 类里没有 岩浆／火✓★）
_d = PC.class_of("minecraft:lava")
_lava = PC.class_of("minecraft:lava")
_water = PC.class_of("minecraft:water")
check("P6",
      _lava[0] == "DANGER" and PC.family_of(_lava[0]) == "policy",
      "lava 归 DANGER（政策栏），凭标签类别 岩浆 —— 2026-10-13 改（用户裁决 C5 / §79.221）："
      "这条**原来断言的是缺口**（lava 按碰撞归 LIQUID，类别表 27 个里没有 岩浆/火，§79.176）；"
      "C5 把 岩浆 补上了（显式标签 id：farmersdelight:heat_sources、"
      "amendments:cauldron_heat_source、create:passive_boiler_heaters、"
      "minecraft:strider_warm_blocks），所以改成断言**修好之后的样子**。"
      "★这不是放宽判据：判据的主张从「这个洞还在」变成「这个洞补上了」★ ⇒ %s" % (_lava,))

check("P6b",
      _water[0] == "LIQUID" and PC.family_of(_water[0]) == "phys",
      "water 仍是 LIQUID（不许因为补危险而把水也当岩浆） —— 凭什么：选标签时"
      "**故意不收** minecraft:replaceable（水也命中它），只收四个热源标签；"
      "实测 water 一个热源标签都不命中 ⇒ %s" % (_water,))

# ---- P7 ★`plan_view` 能把一盒压成类别（★将来落盘缓存的形态✗★）
_pv = PC.plan_view({(0, 1, 0): "minecraft:stone", (0, 2, 0): None})
check("P7", _pv.get((0, 1, 0)) == "SOLID" and _pv.get((0, 2, 0)) == "UNKNOWN",
      "★`plan_view` 压出来的类别对✗★ ⇒ %s" % (_pv,))

check("P8",
      PC.FAMILY.get("UNKNOWN") == "phys" and PC.family_of("UNKNOWN") == "phys",
      "UNKNOWN 归 **phys**（物理层「答不出」是**合法结论**，一等公民）"
      " —— 2026-10-13 改（用户裁决 C2）：原来它在 `none` 那一栏，"
      "而 `none` 谁也不属于 => 没有栏去管「不许静默当空气」这条规矩。"
      "★这条与 P2 配对★：P2 管「UNKNOWN 不是 AIR」，P8 管「它属于物理栏」")

check("P9",
      PC.family_of("★这不是一个类别✗★") is None,
      "认不出的类别 ⇒ family_of 回 **None**（★不许默默归到某一栏✗★）"
      " —— 原来是兜底回 `none`；C2 之后 `none` 退役，"
      "「没有栏」与「有栏但答不出」必须分得开")

print("=> passclass %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
