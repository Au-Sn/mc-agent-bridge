#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""passclass.py -- ★可通过性**类别层**✗★（★借鉴② ✗ 2026-10-05✗★）

★★为什么有这一层✗★★
  ★Baritone 的精髓**不是**"★2 bit★" ✗ 是"★**规划只吃类别**✗ 不直接消费碰撞枚举★"✗★ ⇒
  ★规划更快 ✗ 缓存更紧凑 ✗ 判据更好写✗★ ✓
★★我们的类别必须比 Baritone **多两个**✗★★（★用户原话✓★）✗★：
  · ★`CANOPY`✗★ —— ★**政策**类：★树冠能站 ✗ 但**不当落脚点**✗★ ✓
  · ★`UNKNOWN`✗★ —— ★★**一等公民**✗★★：★"★没读到★" **永不**静默当 `AIR`✗★ ✓
    ★（★Baritone 是客户端 ✗ 它没有"★服务端没给我这一格★"这个问题 ✗ 我们有✓★）
★★★两条纪律（★都是我自己提的那条反对落成的✗★）✗★★
  ★① **分两栏**✗★：★`AIR`／`SOLID`／`LIQUID` 是**物理**（★真值族 ✗ 只听碰撞／液体✓★）✗
    ★`CANOPY`／`DANGER` 是**政策**（★"★该不该去★" ✗ **不参与物理**✓★）✗★ ✓
    ★⇒ ★每个类别**自带它的栏**（★`FAMILY` ✓★）✗ 判据可以据此查"★政策有没有越界★"✗★ ✓
  ★② ★`DANGER` 从**声明过的标签**推 ✗ **不是**从名字✗★（★㉜ 口径 ✗ 与 `CANOPY` 同源✓★）✗★ ✓
★这一层**不产生**任何"★能不能站★"的新事实 ✗ 它只是把**已有**的真值**归类**✗★ ✓
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

# ★★类别表✗★★（★每项自带**栏**✗★）
FAMILY = {
    "AIR": "phys", "SOLID": "phys", "LIQUID": "phys",
    "CANOPY": "policy", "DANGER": "policy",
    # ★★2026-10-13（★用户裁决 C2✗★）✗★★：★`UNKNOWN` 从 `none` 改归 **`phys`**✗★ ✓
    #   ★用户原话✗★：★"★UNKNOWN 从 none 改归 phys（★物理层"答不出"的合法状态 ✗ 一等公民✓★）★"✗★ ✓
    #   ★为什么对✗★：★"★答不出★"**是**物理层的一个**合法结论** ✗★ ——
    #     ★它和"★这格是空气★"一样属于物理那一栏 ✗ 只是值不同✗★ ✓
    #   ★旧写法坏在哪✗★：★`none` 那一栏**谁也不属于**✗★ ⇒
    #     ★它把"★不知道★"变成了"★不属于任何栏★" ✗ 于是**没有栏**去管"★不许静默当空气★"这条规矩✗★ ✓
    "UNKNOWN": "phys",
}
# ★**政策**类别的判据来源 ✗ 一律走**标签类别**（★`blockkb.category_of` ✗ 声明过的✓★）✗★
POLICY_TAG = {
    "叶子": "CANOPY",        # ★树冠：★能站 ✗ 但不当落脚点✗★
    "岩浆": "DANGER",
    "火": "DANGER",
}


def class_of(species, read=None):
    """★一格的**规划用类别**✗★

    ★★返回✗★★：★`(cls, why)` ✗ `why` 说明**凭什么**这么判（★审计用✓★）✗★ ✓
    ★★`UNKNOWN` 的规矩✗★★：★`species is None`（★没读到✗★）⇒ **`UNKNOWN`**✗
    ★**不许**回 `AIR` ✗ 也**不许**回 `SOLID`✗★ ✓
    """
    if species is None:
        return "UNKNOWN", "not_read"
    import blockkb as KB
    import mapread as MR
    # ★政策栏先看 ✗ 但只对**声明过的标签类别**生效✗★
    try:
        cat = KB.category_of(species)
    except Exception:
        cat = None
    if cat in POLICY_TAG:
        return POLICY_TAG[cat], "policy_tag:" + str(cat)
    # ★物理栏 ✗ 只听碰撞／液体✗★
    try:
        if not KB.blocks_space(species):
            fam = KB.classify(species, phys=True).get("fam")
            return ("LIQUID" if fam == "liquid" else "AIR"), "collision:" + str(fam)
    except Exception:
        return "UNKNOWN", "blockkb_error"
    # ★能站的（★落地或挡人 ✗ 都算 SOLID ✓★）✗★
    return "SOLID", "collision:blocks_space"


def family_of(cls):
    """★这个类别属于哪一栏✗★ ⇒ ★认不出 ⇒ **`None`**✗★ ✓

    ★★2026-10-13（★用户裁决 C2／C1✗★）✗★★：★原来兜底回 `"none"`✗★ ⇒
    ★而 `none` 这一栏现在**不该存在**✗★（★`UNKNOWN` 已归 `phys`✓★）✗★ ⇒
    ★★认不出的类别**不许默默归到某一栏** ✗ 如实回 `None`✗★★ ✓
    （★口径✗★：★"★没有栏★"与"★有栏但答不出★"是**两件事** ✗ 不许混✓★）✗★ ✓
    """
    return FAMILY.get(cls)


def plan_view(cells):
    """★把一盒的**原始物种**压成**类别**✗★（★这就是将来落盘缓存的形态✗★）✗★"""
    out = {}
    for p, sp in (cells or {}).items():
        out[p] = class_of(sp)[0]
    return out


if __name__ == "__main__":
    import json
    tests = [None, "minecraft:air", "minecraft:cave_air", "minecraft:water",
             "minecraft:stone", "minecraft:oak_leaves", "minecraft:lava",
             "minecraft:oak_fence"]
    for sp in tests:
        c, why = class_of(sp)
        print("  %-28s ⇒ %-8s（%s 栏）✗★ 凭：%s"
              % (str(sp), c, family_of(c), why))
