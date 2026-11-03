#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_policy_test.py -- ★政策层的判据★（J1~J6 ✓ 全离线 ✓ 2026-10-05）

★它守的是用户裁定 (a) 那句话✗★：
  ★"★is_floor 说真话（★树叶物理可站✓★）＋ 规划层另立规则「★不把树冠当落脚点★」"✗★ ✓
★以及 §79.143 那条口径✗★：
  ★语义槽存**标签类别**（★`叶子`✓★）✗ 而**类别 ⇒ 几何族**的映射**只声明有裁定的那几行**✗★ ✓
"""
from __future__ import annotations

import os
import pathlib
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
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== kb_policy_test：J1~J6 ==")

os.environ["CLASSIFIER_SOURCE"] = "table+fallback"
import blockkb as KB  # noqa: E402

KB.SOURCE = "table+fallback"
KB.load_all()
KB.load_categories()

# ---- J1 物理说真话：树叶在碰撞真值下**能站**（★政策不许碰它✓★）
_r = KB.classify("minecraft:oak_leaves", phys=True)
check("J1", KB.is_floor_fam(_r.get("fam") or "-") is True,
      "★`is_floor`（物理）说**真话**：树叶能站 ✗ 与政策无关✗★ ⇒ 族=%s" % _r.get("fam"))

# ---- J2 类别来自**标签**（★并带出处✗★）
check("J2", KB.category_of("minecraft:oak_leaves") == "叶子",
      "★类别=叶子✗★（★来自标签 ✗ 出处 %s✓★）" % (KB.category_evidence("minecraft:oak_leaves") or "★没有✗★"))

# ---- J3 政策：树冠**不当落脚点**（★而物理说能站 ✗ 两者并存✓★）
check("J3", (KB.is_canopy("minecraft:oak_leaves") is True)
      and (KB.is_landing_spot("minecraft:oak_leaves") is False),
      "★树冠不当落脚点✗★ ⇒ 能站=True 而落脚点=False ✓（★两个问题 ✗ 分开答✓★）")

# ---- J4 非树冠的整块 ⇒ 落脚点照旧可行
check("J4", KB.is_landing_spot("minecraft:oak_log") is True,
      "★原木（★类别=原木✓★）⇒ 落脚点=True✗★ ⇒ %s" % KB.category_of("minecraft:oak_log"))

# ---- J5 **没有类别** ⇒ 未知归属 ✗ 而**不影响物理**（★铁律 1✗★）
_sp = "supplementaries:book_pile_horizontal"
check("J5", (KB.category_of(_sp) is None) and (KB.is_canopy(_sp) is False)
      and (KB.is_landing_spot(_sp) is (KB.is_floor_fam(
          (KB.classify(_sp, phys=True).get("fam") or "-")))),
      "★没类别 ⇒ 未知归属 ✗ 而落脚点**跟着物理走**✗★（★缺失永不影响物理✓★）⇒ 类别=%s"
      % KB.category_of(_sp))

# ---- J6 **只声明**有裁定的映射（★加一条必须是有意为之 ✗ 不许顺理成章✗★）
check("J6", len(KB.CATEGORY_TO_FAMILY) == 1 and KB.CATEGORY_TO_FAMILY.get("叶子") == "canopy",
      "★类别⇒族 的映射**只声明了一条**（★`叶子`⇒`canopy`✓★）✗★ ⇒ %s"
      % ("／".join("%s⇒%s" % kv for kv in KB.CATEGORY_TO_FAMILY.items())))


# ---- J7 ★几何类声明必须**条条成立**（★拿碰撞真值当裁判✗★）
#   ★为什么✗★：★几何类声明是"★标签下的一个**可核验**声明★"✗★ ⇒
#     ★如果它和碰撞真值**对不上** ✗ 那就是一条**假的声明**✗
#     ★比"★没声明★"更坏（★没声明只是不知道 ✗ 假声明会骗人✗★）✗★ ✓
import json as _json  # noqa: E402
import kb_export as _KX
import export_guard as _EG  # B1：缺输入硬红＋一句人话  # noqa: E402
_exp = _json.loads(_EG.require("kb_policy_test.py").read_text(encoding="utf-8"))
_blocks = _exp.get("blocks") or {}
_bad, _n = [], 0
for _sp, _c in KB.CATEGORY.items():
    _cat = _c.get("cat") if isinstance(_c, dict) else None
    _want = KB.GEOMETRIC_CATEGORY.get(_cat or "")
    if not _want:
        continue
    _e = _blocks.get(_sp)
    if not _e:
        continue
    _n += 1
    if _e.get("family") != _want:
        _bad.append("%s（★%s⇒%s ✗ 实为 %s★）" % (_sp, _cat, _want, _e.get("family")))
check("J7", (len(_bad) == 0) and (_n > 0),
      "★几何类声明条条成立✗★ ⇒ 核验 **%d** 条 ✗ 矛盾 **%d** 条 ✗★ %s"
      % (_n, len(_bad), _bad[:3]))


# ---- J8 ★规划问的是"★落脚点★" ✗ 不是"★能不能站★"（★用户裁定 (a) 的那一句✗★）
#   ★口径✗★：★`mapread.is_landing` ＝ `is_floor` **且** 不是树冠✗★ ⇒
#     ★切换档下树叶：`is_floor=True` 而 `is_landing=False`✗★ ✓
#     ★出厂档下两者**同值**（★因为 `is_floor(树叶)` 本来就是 False✓★）⇒ **零变化**✗★ ✓
import mapread as _MR  # noqa: E402
_leaf_f = _MR.is_floor("minecraft:oak_leaves")
_leaf_l = _MR.is_landing("minecraft:oak_leaves")
_stone_f = _MR.is_floor("minecraft:stone")
_stone_l = _MR.is_landing("minecraft:stone")
check("J8", (_leaf_l is False) and (_leaf_f is True) and (_stone_l is True)
      and (_stone_l == _stone_f),
      "★树叶：物理能站=%s 而规划落脚点=%s✗★ ｜ 石头两者都 %s ⇒ ★规划问的是落脚点✗★"
      % (_leaf_f, _leaf_l, _stone_l))

print("=> kb_policy %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
