#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collision_classes_test.py -- ★碰撞高度**按类**对账（★离线 ✗ 进闸门✗★）（§79.401）

★★为什么要有它✗★★（★2026-10-26 那次教训✗★）✗★：
  ★`model_check.py` 抽 **24 个随机格** 去核模型 ✗ **一直是 100%**✗★
  ★但随机抽样**几乎不会**抽到**稀有方块**（★花瓣／火把／矮草 ✗ 平台上零星几格✗★）✗★
  ★而**恰恰是它们**出过事✗★：★`collision_h()` 只切了 `[…]` 没切 **`,状态`**
  ⇒ ★带状态的**小方块**查表 miss ⇒ 兜底 **1.0** ⇒ **能站的地方被判成墙**✗★ ✓
★★所以这条判据✗★★：★**按"类"逐项对账**（★不随机 ✗ 每类都点名✗★）✗★ ✓
★关键回归点✗★：★`grass_block` **必须 1.0**（★有人用"包含 grass"的写法会把它变 0 ✗ 地面穿透✗★）✗★ ✓
"""
from __future__ import annotations

import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import world3d as W3            # noqa: E402

# ★(★名字（★带状态 ✗ 仿真 `dshscan` 的格式✗★）✗ 期望 h ✗ 说明✗★)✗★
CASES = [
    # ── ★小方块：碰撞为空 ⇒ 0.0✗★ ──
    ("minecraft:pink_petals,facing=north,flower_amount=4", 0.0, "花瓣（★那次出事的方块✗★）"),
    ("minecraft:torch", 0.0, "火把"),
    ("minecraft:wall_torch,facing=north", 0.0, "墙上火把（★带状态✗★）"),
    ("minecraft:poppy", 0.0, "花"),
    ("minecraft:dandelion", 0.0, "蒲公英"),
    ("minecraft:short_grass", 0.0, "矮草（★1.20.3 改名 ✗ 导出里没有✗★）"),
    ("minecraft:oak_sapling", 0.0, "树苗"),
    ("minecraft:redstone_wire,power=0", 0.0, "红石线（★带状态✗★）"),
    # ── ★整块：1.0✗★ ──
    ("minecraft:stone", 1.0, "石头"),
    ("minecraft:dirt", 0.0 if False else 1.0, "泥土"),
    ("minecraft:grass_block,snowy=false", 1.0, "草方块（★带状态 ✗ **必须 1.0**✗★）"),
    ("minecraft:flowering_azalea_leaves", 1.0, "杜鹃树叶（★名字里有 flower ✗ **必须 1.0**✗★）"),
    ("minecraft:oak_planks", 1.0, "木板"),
    ("minecraft:sand", 1.0, "沙"),
    # ── ★半高／矮块✗★ ──
    ("minecraft:oak_slab,type=bottom", 0.5, "半砖（★带状态✗★）"),
    ("minecraft:snow", 0.0, "雪层（★导出按真碰撞盒算是 0.0 ✗ 我的期望值原先是猜的✗★）"),
    # ── ★空气✗★ ──
    ("minecraft:air", 0.0, "空气"),
    ("", 0.0, "空名字"),
]


def main() -> int:
    bad = 0
    for name, want, why in CASES:
        got = W3.collision_h(name)
        ok = abs(got - want) < 1e-6
        if not ok:
            bad += 1
        print("  %s %-52s ⇒ %-6s（★期望 %s✗★）｜ %s"
              % ("✓" if ok else "★✗★", name[:52] or "（空）", got, want, why))
    print("  ---- %d/%d ----" % (len(CASES) - bad, len(CASES)))
    if bad:
        print("  => collision_classes ★FAIL★（%d 类不对 ✗ **规划层会把它们判错**✗★）" % bad)
        print("COLLCLASS ok=0 bad=%d" % bad)
        return 1
    print("  => collision_classes PASS ✓（★小方块 0 ✗ 整块 1 ✗ 半砖 0.5 ✗ 带状态的也切干净了✗★）")
    print("COLLCLASS ok=1 checks=%d" % len(CASES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
