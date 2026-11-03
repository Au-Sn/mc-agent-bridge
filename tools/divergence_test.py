#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""divergence_test.py -- ★分歧清单的离线判据★（D1~D4 ✓ 全离线 ✓ 秒级 ✓ 2026-10-03）

★为什么要有它✗★：`divergence.py` 的判定**决定**"★哪些东西要进例外表★" ✗
  ★它错了 ✗ 阶段 3 的整张表就错了✗★ ⇒ 三件事必须钉住 ✓
    ① ★三栏的边界✗★（★一致／不一致／表中无 ✓ 尤其"★多族冲突★"要落哪栏✓★）
    ② ★`TAG_FAMILY` 是**显式数据**✗★（★不许悄悄变成正则／猜测✗★）
    ③ ★"★表中无★"**不许**被当成"一致" ✗ 也不许被当成"不一致"✗★ ✓

★判据（先写死）★
  D1 ★单族 ⇒ 对了就"一致" ✗ 不对就"不一致"✗★
  D2 ★多族**冲突** ⇒ 必须落"不一致" ✗ 而且理由里要写明**冲突**✗★（★不许挑一个了事✓★）
  D3 ★没有任何家族标签 ⇒ "表中无"✗★（★与"不一致"分开数 ✗ 这是任务书要求的三栏✓★）
  D4 ★`TAG_FAMILY` 里每个键都必须真的在家族模式表里✗★
     （★否则这张表会**悄悄失效** ✗ 比如家族改名了却没人知道✓★）
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

import divergence as DV  # noqa: E402
import tag_census as TC  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== divergence_test：D1~D4 ==")

# ---- D1 单族 ----
e, why, _c = DV.expected_from_tags(["叶子"])
check("D1a", (e == "canopy") and DV.bucket("canopy", e) == "一致",
      "★标签=叶子 ⇒ 期望 canopy ⇒ 黑名单也说 canopy ⇒ 一致✗★")
check("D1b", DV.bucket("pass", e) == "★不一致✗★",
      "★黑名单说 pass ⇒ 必须落「不一致」✗★")
e2, _w2, _c2 = DV.expected_from_tags(["半砖"])
check("D1c", (e2 == "slab") and DV.bucket("pass", e2) == "★不一致✗★",
      "★半砖 ⇒ 期望 slab ✗ 黑名单 pass ⇒ 不一致✗★（★这正是 `slab_brown_mushroom` 那一类✓★）")

# ---- D2 多族冲突 ----
e3, why3, c3 = DV.expected_from_tags(["叶子", "半砖"])
check("D2a", (e3 is None) and c3, "★冲突时**不许**挑一个 ✗ 要回 None ＋ 标成冲突✗★ ⇒ %s/%s" % (e3, c3))
check("D2b", "冲突" in why3, "★理由里要写明「冲突」✗★ ⇒ %s" % why3)
# ★★D2c（★判据第一版在这里**判错了**✗ ★后来改的是**代码**✗★）✗★★：
#   原来"冲突"和"表里没有"都落"表中无" ✗ ⇒ ★可它们是两件事✗★ ✓
#   ★冲突 ＝ 标签侧说了**两句矛盾的话** ⇒ 必须进"不一致"栏✗★ ✓
check("D2c", DV.bucket("canopy", e3, conflict=True) == "★不一致✗★",
      "★冲突必须落「不一致」 ✗ 不是「表中无」✗★ ⇒ %s" % DV.bucket("canopy", e3, conflict=True))
check("D2d", DV.bucket("canopy", None, conflict=False) == "★表中无✗★",
      "★而「真的没有」仍落「表中无」✗★（★三栏还是三栏✓★）")

# ---- D3 没有家族标签 ----
e4, why4, c4 = DV.expected_from_tags(["minecraft:mineable/pickaxe"])
check("D3a", (e4 is None) and ("没有" in why4) and (not c4), "★没有家族标签 ⇒ None ＋ 说原因 ✗ 且**不算冲突**✗★")
check("D3b", DV.bucket("full", e4, c4) == "★表中无✗★",
      "★「表中无」要与「不一致」**分开**✗★（★任务书三栏✓★）")

# ---- D4 TAG_FAMILY 与家族模式表必须**双向**对齐 ----
#   ★★2026-10-03 修✗★★：★第一版只查一个方向（★映射 ⊆ 模式✓★）✗ ⇒
#   ★我加了模式却忘了加映射 ✗ 它**没吭声** ✗ 于是 `minecraft:dirt` 被静默算成"表中无"✗★ ✓
#   ★口径✗★：★两个方向都要查 ✗ 缺哪边都拒✗★ ✓
pats = {f for f, _p in TC.FAMILY_PATTERNS}
only_pat = sorted(pats - set(DV.TAG_FAMILY))
only_map = sorted(set(DV.TAG_FAMILY) - pats)
check("D4a", not only_map, "★映射里有而模式表没有 ⇒ 那条映射是**死的**✗★（%s）" % (only_map or "没有 ✓"))
# ★D4b 允许**故意不映射**的那几个 ✗ 但它们必须**写在忽略表里**（★带理由✗★）✗
#   ★口径✗★：★"★忘了映射★"要拒 ✗ "★故意不映射★"要在 `NOT_SHAPE_FAMILY` 里**声明**✗★ ✓
_ign = set(getattr(TC, "NOT_SHAPE_FAMILY", {}) or {})
_undecided = sorted(set(only_pat) - _ign)
check("D4b", not _undecided,
      "★模式表里有而既没映射也没进忽略表 ⇒ 那一族会被**静默丢掉**✗★（%s）" % (_undecided or "没有 ✓"))
check("D4c", bool(_ign),
      "★忽略表**必须**存在且有理由 ✗ 不许空着（★空着就等于没有声明✓★）✗★（%d 条）" % len(_ign))

# ---- E1~E4 决策级／语义级（★这一刀只用来**排优先** ✗ 不许当"可以不管"✗★）----
#   ★两条判定的出处✗★：`mapread.py:105`（挡人）与 `mapread.py:361`（能站）✗ **照抄**不是猜 ✓
check("E1", DV.decision_delta("full", "machine").startswith("★语义级"),
      "★full 与 machine 两边都挡人都能站 ⇒ **语义级**✗★ ⇒ %s"
      % DV.decision_delta("full", "machine"))
d = DV.decision_delta("pass", "slab")
check("E2", d.startswith("★★决策级") and ("挡人" in d) and ("能站" in d),
      "★pass ↔ slab 是**真的会翻** ✗ 而且两条都要说清✗★ ⇒ %s" % d)
check("E3", DV.decision_delta("full", "pass").startswith("★★决策级"),
      "★反方向（★黑名单说挡人 ✗ 标签说能穿过去✓★）也是决策级✗★ ⇒ %s"
      % DV.decision_delta("full", "pass"))
check("E4", DV.decision_delta("full", None).startswith("★没法比"),
      "★一边没族名 ⇒ 如实说「没法比」 ✗ 不许硬算✗★ ⇒ %s" % DV.decision_delta("full", None))

print("=> divergence %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
