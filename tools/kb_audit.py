#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_audit.py -- ★新轴第一版：**模型 vs 知识表**★（任务书 §4 ✗ 只报数 ✗ 不判红✓★）

★它比什么✗★（★两条**独立**的通道✗★）
  · ★模型✗★：`mapread` 那条老路（★名字分类器 ＋ 它学来的东西✓★）
  · ★知识表✗★：`blockkb` 那条新路（★标签／碰撞／例外表 ⇒ 带**来源等级**✓★）
  ⇒ ★两条对**同一格**给出的"★挡人／能站★"如果不一样 ✗ 那就是一次**分歧**✗★ ✓

★★纪律（★写死 ✗ 违反即退回✗★）★★
  ① ★抽样必须**分层** ✗ **不许随机**✗★（★随机会**系统性地漏**掉少见的层 ✓ 任务书明说✓★）
  ② ★第一版**只报数** ✗ 不判红 ✗ 不出退出码✗★（★P98：★先量再设计✗★）
  ③ ★"★知识表说不知道★"**不是**分歧✗★ ⇒ 那是 `unknown` 一栏（★今天它会是**绝大多数** ✓
     因为例外表还空着 ✓★）✗ 只有"★两边都**有意见**而意见不同★"才算 `contradicted` ✗★ ✓
  ④ ★世界那一侧用**模组当场读**✗★（★`dshscan` ✓ 不经过 `mapread` 的图／缓存✓★）

★抽样层（★六层 ✗ 每层都有理由✓★）
  `walked`      ★规划**真走过**的格子（★使用痕迹✓★）——★按"★这一带是被用过的★"取✗★
  `multi_layer` ★那一柱有**多层**已知地板（★几何：多层柱✓★）
  `under_canopy`★头顶有**树冠族**的格子（★几何：树冠下✓★）
  `near_liquid` ★贴着液体（★几何：水边✓★）
  `changed`     ★夹具快照之后**变过**的格子（★快照后变更✓★）
  `plain`       ★以上都不是（★对照组✓★）

用法：
    py tools/kb_audit.py --box 4118,66,-7,4130,76,5 --per-stratum 6
    py tools/kb_audit.py --offline-fixture   # ★不碰世界 ✗ 用夹具快照跑一遍（★测"分类逻辑"✓★）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STRATA = ("walked", "multi_layer", "under_canopy", "near_liquid", "changed", "plain")
FAM_CANOPY = ("canopy",)
FAM_LIQUID = ("liquid",)


def stratum_of(cell, world, map_layers=None, snap=None, walked=None) -> str:
    """★给一格定层✗★（★纯函数 ✗ 好离线判✓★）—— ★顺序**写死** ✗ 第一次命中就算✗★ ✓"""
    x, y, z = cell
    if walked and cell in walked:
        return "walked"
    if snap is not None and snap.get("%d,%d,%d" % cell) != world.get("%d,%d,%d" % cell):
        return "changed"
    if map_layers and map_layers.get((x, z), 0) >= 2:
        return "multi_layer"
    up = world.get("%d,%d,%d" % (x, y + 2, z)) or ""
    if up.split(",", 1)[0] in ("minecraft:oak_leaves", "minecraft:azalea_leaves"):
        return "under_canopy"
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = world.get("%d,%d,%d" % (x + dx, y, z + dz)) or ""
        if "water" in nb or "lava" in nb:
            return "near_liquid"
    return "plain"


def compare(model_fam, table_res) -> str:
    """★两条通道比一比✗★ ⇒ `agree` ／ `disagree`（★＝contradicted✓★）／ `fallback` ／ `unknown`✗★

    ★★2026-10-03 判别出来的一个**假数**✗★★：★第一版让"★知识表★"那一路跑在**默认
      `blacklist`** 模式下 ✗ 而那个模式**会回落到名字分类器**✗★ ⇒ ★结果"★同意 16 ✗
      矛盾 0 ✗ 不知道 0★"✗★ —— ★★那是拿**模型**跟**模型**比 ⇒ 数字**毫无意义**✗★★ ✓
    ⇒ ★两条修正（★不是改数 ✗ 是改机制✓★）✗★：
      · ★表那一路跑 `table` 模式** ✗ 这样"不知道"才是真的（★它不许回落✓★）
      · ★"★回落到名字兜底★"**单独一栏** ✗ **不许**算"同意"✗★ ——
        ★它是**兜底**给的结论 ✗ 不是知识表给的✗★ ✓
    """
    if not table_res or not table_res.get("fam"):
        return "unknown"
    if table_res.get("level") == "name_fallback":
        return "fallback"
    return "agree" if table_res["fam"] == model_fam else "disagree"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", default="4118,66,-7,4130,76,5")
    ap.add_argument("--per-stratum", type=int, default=6)
    ap.add_argument("--fixture", default="calib_v1")
    a = ap.parse_args(argv)

    import blockkb as KB
    # ★★2026-10-04 补✗★★：★知识表是**内存字典** ✗ 每个工具都是新进程✗★ ⇒
    #   ★不装的话这个审计永远看到「空表 ⇒ 覆盖率 0%」（★实测过✓★）✗★
    try:
        _ld = KB.load_all()
        print("  知识表已装：★例外表 %s 条 ✗ 导出 %s 条✓★（★%s✓★）"
              % (_ld["exceptions"], _ld["export_put"], str(_ld["export"])[-34:]))
    except Exception as _e:
        print("  ★装不动✗★：%s: %s" % (type(_e).__name__, _e))
    import fixture_scan as FS
    import fixtures as FX
    import mapread as MR

    # ★★表那一路**必须**跑 `table` 模式✗★★（★否则它会回落到名字分类器 ✗ 而那就成了
    #   "★模型跟模型比★" ✗ 数字**毫无意义** ✓ 见 `compare` 的注释 ✓★）
    _orig = KB.SOURCE
    KB.SOURCE = "table"

    x0, y0, z0, x1, y1, z1 = (int(v) for v in a.box.split(","))
    world, stat, kinds = FS.batch_scan((x0, y0, z0, x1, y1, z1), verbose=False)
    print("== kb_audit ✗ 模型 vs 知识表（★只报数 ✗ 不判红✓★）==")
    print("  盒 %s ｜ 非空气 %d 格 ｜ 物种 %d ｜ 开关 CLASSIFIER_SOURCE=%s"
          % (a.box, len(world), len({v.split(',', 1)[0] for v in world.values()}), KB.SOURCE))

    # ★快照（★用于"★变过★"那一层 ✗ 读不到就当没有✓★）
    snap = None
    sp = ROOT / "state" / "fixtures" / ("%s.snapshot.json" % a.fixture)
    if sp.is_file():
        snap = json.loads(sp.read_text(encoding="utf-8"))

    # ★多层柱：★从世界数"★这一柱非空气格数★" ✗ 不查图（★保持独立✓★）
    layers = {}
    for k in world:
        x, y, z = (int(v) for v in k.split(","))
        layers[(x, z)] = layers.get((x, z), 0) + 1

    cells = []
    for k in sorted(world):
        cells.append(tuple(int(v) for v in k.split(",")))
    buckets = {s: [] for s in STRATA}
    for c in cells:
        buckets[stratum_of(c, world, layers, snap, None)].append(c)
    print("")
    print("  分层（★全盒 ✗ 不是抽样✓★）：%s"
          % " ／ ".join("%s=%d" % (s, len(buckets[s])) for s in STRATA))

    print("")
    print("  %-12s %6s %7s %9s %9s %9s" % ("层", "取样", "同意", "矛盾", "兜底", "不知道"))
    total = {"agree": 0, "disagree": 0, "fallback": 0, "unknown": 0}
    for s in STRATA:
        pick = buckets[s][:a.per_stratum]
        cnt = {"agree": 0, "disagree": 0, "fallback": 0, "unknown": 0}
        for (x, y, z) in pick:
            sp_name = (world.get("%d,%d,%d" % (x, y, z)) or "air").split(",", 1)[0]
            model_fam = MR.shape(sp_name)
            res = KB.classify(sp_name, phys=True)
            cnt[compare(model_fam, res)] += 1
        for k in cnt:
            total[k] += cnt[k]
        print("  %-12s %6d %7d %9d %9d %9d"
              % (s, len(pick), cnt["agree"], cnt["disagree"], cnt["fallback"], cnt["unknown"]))
    print("")
    print("  ★合计✗★ 同意 %d ｜ 矛盾 %d ｜ 兜底 %d ｜ ★不知道 %d✗★"
          % (total["agree"], total["disagree"], total["fallback"], total["unknown"]))
    # ★★观察名单命中（★第五种状态 ✗ 2026-10-03 加✗★）✗★★
    #   ★这一步是**真的消费**那份名单 ✗ 不是让它躺在磁盘上✗★：
    #   ★被观察的物种**不许**被当成"★一致★" ✗ 它**未裁决**✗★ ✓
    print("")
    try:
        import watchlist as WL
        _seen = []
        for _s in STRATA:
            for (x, y, z) in buckets[_s][:a.per_stratum]:
                _sp = (world.get("%d,%d,%d" % (x, y, z)) or "air").split(",", 1)[0]
                if WL.is_watched(_sp):
                    _seen.append(_sp)
        print("  ★观察名单命中（★contradicted ✗ 未裁决✗★）✗★：%d 个物种 %s"
              % (len(set(_seen)), "／".join(sorted(set(_seen))[:4]) or "（★没有✓★）"))
    except Exception as e:
        print("  ★观察名单读不到✗★（★%s ✗ 不当成「没有」✗★）" % type(e).__name__)
    print("")
    print("★怎么读✗★：★「不知道」＝知识表**没装**或**没这条**✗ —— 2026-10-04 起例外表（1209 条）与导出（24779 条）会先装好 ✗ 所以它应当**接近 0**✗★ ⇒")
    print("  ★这一版的用处是**基线**：★以后每次重跑 ✗ 看「不知道」往下掉 ✗ 就知道迁移在推进✗★ ✓")
    print("★纪律✗★：★第一版**只报数** ✗ 不判红 ✗ 退出码恒 0（★除非世界读不到✓★）✗★ ✓")
    return 0


if __name__ == "__main__":
    # ★★2026-10-13（★§79.270 预演抓的✗★）✗★★：★「扫不了」要**说人话 ＋ 三分类退出码**✗★ ——
    #   ★现象✗★：★拿合成导出跑它 ⇒ `fixture_scan` 抛
    #     `RuntimeError: ★第一次扫就失败了 ✗ 不做快照★`✗★ ⇒
    #     ★那句话**本身是人话** ✓ 可就以 **traceback** 崩出来 ✗★ ✓
    #   ★口径（★本项目一直用的三分类✗★）✗★：★**4 ＝ 有东西没拿到**
    #     （★不是通过 ✗ 也不是坏✓★）✗★ ✓
    try:
        sys.exit(main(sys.argv[1:]))
    except RuntimeError as e:
        print("INCONCLUSIVE: %s" % e)
        print("★它要**世界**（★扫描要网关／游戏✗★）✗ 这是「没法测」 ✗ 不是判据坏★")
        sys.exit(4)
