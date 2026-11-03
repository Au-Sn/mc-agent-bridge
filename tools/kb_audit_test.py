#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_audit_test.py -- ★新轴的离线判据★（A1~A4 ✓ 不碰世界 ✓ 秒级 ✓ 2026-10-03）

★为什么要有它✗★：★`kb_audit` 是**只报数**的工具 ✗ ⇒ ★它**不会**用自己的红来提醒你它算错了**✗★ ✓
  ⇒ ★所以"★怎么分档★"和"★怎么算矛盾★"必须**离线**钉住 ✗ 否则报出来的数**没人质疑**✗★ ✓

★判据（先写死）★
  A1 ★"★知识表说不知道★"**不算矛盾**✗★（★它是 `unknown` 一栏 ✗ 纪律 ③✓★）
  A2 ★两边都有意见且不同 ⇒ 才算 `disagree`✗★（★＝任务书的 **contradicted** 第五状态✓★）
  A3 ★分层**顺序**是写死的✗★：★`walked` ＞ `changed` ＞ `multi_layer` ＞ `under_canopy`
     ＞ `near_liquid` ＞ `plain`✗★（★第一次命中就算 ✓ 顺序一乱 ✗ 同一个格会被算进不同的层✗★）
  A4 ★六层**一个都不许少**✗★（★少一层 ⇒ 那种几何**永远不被看到**✗★）
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

import kb_audit as KA  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== kb_audit_test：A1~A4 ==")

# ---- A1／A2 比较的口径 ----
check("A1a", KA.compare("full", {"fam": None}) == "unknown",
      "★知识表说不知道 ⇒ `unknown` ✗ **不是**矛盾✗★")
check("A1b", KA.compare("full", {}) == "unknown", "★空结果 ⇒ `unknown`✗★")
check("A2a", KA.compare("full", {"fam": "pass"}) == "disagree",
      "★两边都有意见且不同 ⇒ `disagree`（★contradicted✓★）✗★")
check("A2b", KA.compare("slab", {"fam": "slab"}) == "agree", "★一样 ⇒ `agree`✗★")

# ---- A3 分层顺序（★写死 ✗ 一次命中✓★）----
world = {"0,0,0": "minecraft:oak_planks", "0,2,0": "minecraft:oak_leaves",
         "1,0,0": "minecraft:water", "0,0,1": "minecraft:stone"}
# ★(0,0,0)：脚下有地板 ✓ 旁边有水（★在 (1,0,0)✓★）⇒ 应当落 `near_liquid`✗★
#   ★★注意✗★★：★这份合成世界里**不许有树冠**✗★ —— ★第一版我顺手放了 `0,2,0=oak_leaves` ✗
#   于是 `under_canopy` 按**写死的顺序先命中** ✗ 红的是**判据**不是代码✗★ ✓
_w_liquid = {"0,0,0": "minecraft:oak_planks", "1,0,0": "minecraft:water",
             "0,0,1": "minecraft:stone"}
check("A3a", KA.stratum_of((0, 0, 0), _w_liquid) == "near_liquid",
      "★贴液体 ⇒ `near_liquid`✗★ ⇒ %s" % KA.stratum_of((0, 0, 0), _w_liquid))
# ★而 `walked` 最优先 ✗ 同一格只要在走过集合里就该落 `walked`✗★
check("A3b", KA.stratum_of((0, 0, 0), world, walked={(0, 0, 0)}) == "walked",
      "★`walked` 最优先✗★ ⇒ %s" % KA.stratum_of((0, 0, 0), world, walked={(0, 0, 0)}))
# ★`changed` 次优先（★快照说它是 air ✗ 现在有东西✓★）
check("A3c", KA.stratum_of((0, 0, 0), world, snap={"0,0,0": "air"}) == "changed",
      "★快照之后变过 ⇒ `changed`✗★ ⇒ %s"
      % KA.stratum_of((0, 0, 0), world, snap={"0,0,0": "air"}))
# ★`multi_layer`：那一柱有 ≥2 层 ✗ 且前面几条都不命中✗★
check("A3d", KA.stratum_of((9, 9, 9), {"9,9,9": "minecraft:stone"},
                           map_layers={(9, 9): 2}) == "multi_layer",
      "★多层柱 ⇒ `multi_layer`✗★")
# ★`under_canopy`：头上两格是树叶✗★
check("A3e", KA.stratum_of((5, 0, 5), {"5,0,5": "minecraft:stone",
                                       "5,2,5": "minecraft:oak_leaves"}) == "under_canopy",
      "★树冠下 ⇒ `under_canopy`✗★")
check("A3f", KA.stratum_of((7, 0, 7), {"7,0,7": "minecraft:stone"}) == "plain",
      "★都不命中 ⇒ `plain`（★对照组✓★）✗★")

# ---- A4 六层一个都不许少 ----
check("A4", len(KA.STRATA) == 6 and set(KA.STRATA) == {
    "walked", "multi_layer", "under_canopy", "near_liquid", "changed", "plain"},
    "★六层齐 ✗ 一层都不许少✗★ ⇒ %s" % "／".join(KA.STRATA))


# ---- A5 ★★"回落到名字兜底"**不许**算"同意"✗★★（★2026-10-03 的假数就在这儿✓★）----
check("A5a", KA.compare("full", {"fam": "full", "level": "name_fallback"}) == "fallback",
      "★兜底给的结论 ⇒ `fallback` ✗ **不是** `agree`✗★")
check("A5b", KA.compare("full", {"fam": "full", "level": "registry"}) == "agree",
      "★知识表自己给的 ⇒ 才算 `agree`✗★")
check("A5c", KA.compare("full", {"fam": None, "level": "unknown"}) == "unknown",
      "★`table` 模式下查不到 ⇒ `unknown`✗★")

print("=> kb_audit %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
