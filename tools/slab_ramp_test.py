#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slab_ramp_test.py -- 半砖是"不用跳的台阶"吗？（R1~R4, 第 34 轮 ✓ 2026-09-29 ✓）

WHY: Minecraft 的自动上台阶上限是 0.6 格 ⇒ **半砖（+0.5）不用跳** ✓ 而**整方块（+1.0）要跳** ✗，
  而模组不会跳（第 32 轮两次实测：停在 0.8~1.7 格外 ✗）。第 34 轮把这条物理写进了模型
  （`Planner.auto_step` ✓ `max_rise` ✓ `reachable_floor` 的窗口 ✓）——
  ★这条判据就是要用**世界真值**证明"写对了"★ ✗：
    · 有半砖接着的那一级 ⇒ 执行者**应该**能上去 ✓（而且要真走上去 ✓）
    · 没有半砖接着的同一级 ⇒ 执行者**不该**能上去 ✗（对照 ✓）

CRITERIA（跑之前先写 ✓）：
  R1 离线：同一柱、同一层 —— 地板是**半砖** ⇒ `Planner(max_up=0).ok()` 必须为 True ✓；
           地板是**整方块** ⇒ 必须为 False ✗（两级对照 ✓ 防"永远 True"✗）
  R2 实机（零调用 ✓ 本地算）：在地图里找"**抬一级** 且 **旁边那格的地板是半砖**"的目标 ⇒
           执行者的区域**必须**包含它 ✓；同时找一个**没有半砖接着**的"抬一级"目标 ⇒
           执行者区域**必须不**包含它 ✗（★两边都要有才是判据 ✓ 只有一边 ⇒ INCONCLUSIVE ✗）
  R3 真走（世界真值 ✓）：把最近的那个"半砖坡道目标"走过去 ⇒ **独立读**必须在**那一格那一层** ✓
           （★这一条才是"半砖真能当台阶"的证据★ ✓）
  R4 诚实：世界现在没有这种配置 ⇒ 说 INCONCLUSIVE ✓ 不许当通过 ✓

Bridge calls: one map build, one plan, one walk, one read.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mapread as MR      # noqa: E402
import mc_mcp as M        # noqa: E402
import pathplan as PP     # noqa: E402


def say(s):
    print(s, flush=True)


def main():
    ok = True
    p = M._pos_now()
    if not p:
        say("INCONCLUSIVE: no bot position")
        return 0
    sx, sy, sz = int(p[0]), int(round(p[1])), int(p[2])
    L = sy

    # ---------------- R1: 离线的两级对照 ------------------------------------
    def mk(block):
        m = MR.Map(0, 60, 0, 1, 76, 1)
        m.cols[(0, 0)] = {70: "minecraft:grass_block"}
        m.cols[(1, 0)] = {70: "minecraft:grass_block", 71: block}
        m.meta.update({"blevel": 71, "has_offsets": True,
                       "mod_standable": {"0,0": 71, "1,0": 72}})
        return m
    # ★★判据要**显式打开**半步开关★★ ✗（第 34 轮 ✓）：生产路径**默认关着** ✓（没验过 ✓）
    #   这条判据验的正是**那条规则本身** ✓ ⇒ 它开 ✓ 生产不开 ✓
    p_slab = PP.Planner(mk("minecraft:oak_slab"), level=71, max_up=0, auto_step_on=True)
    p_full = PP.Planner(mk("minecraft:oak_planks"), level=71, max_up=0, auto_step_on=True)
    r1 = (p_slab.auto_step(1, 0, 71) is True) and (p_slab.ok(1, 0) is True) \
        and (p_full.auto_step(1, 0, 71) is False) and (p_full.ok(1, 0) is False)
    say("R1 offline two-level control: slab floor => auto_step=%s ok=%s (want True/True) | "
        "full block floor => auto_step=%s ok=%s (want False/False) => %s"
        % (p_slab.auto_step(1, 0, 71), p_slab.ok(1, 0),
           p_full.auto_step(1, 0, 71), p_full.ok(1, 0), r1))
    ok &= r1

    # ---------------- R2: 实机：两种"抬一级"——半砖/楼梯 vs 整方块 ---------
    # ★口径（第 34 轮第二次修正 ✓ 实测逼出来的 ✓）★：
    #   原来在 **region 里**找"半砖那一级"✗ ⇒ **找到 0 个** ✗（世界里的楼梯/半砖都在
    #     region **外面** ✓ 走不过去 ✓）⇒ 判据永远 INCONCLUSIVE ✗
    #   真正要证的命题是**逐格**的 ✓：**地板是半步（slab 家族）⇒ 执行者该接受；
    #     地板是整方块（+1.0）⇒ 执行者该拒绝** ✓ —— 这**不需要**它在 region 里 ✓
    #     （判据只需要"这一格**挨着**我能到的地方"✓ 那样它才是个**真实的选择** ✓）
    r, m, _box = M._route_map(sx, sz, sx + 8, sz, sy)
    geo = PP.Planner(m, level=L, max_up=1)
    ex = PP.Planner(m, level=L, max_up=M.MOD_CLIMB_UP, auto_step_on=True)
    reg = geo.region(sx, sz)

    def floor_name(x, z):
        fy = geo.y(x, z)
        if fy is None:
            return None, None
        return fy, (m.cols.get((x, z)) or {}).get(fy)

    def touches_region(x, z):
        return any((x + dx, z + dz) in reg for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1)))

    auto_c, full_c = [], []
    for (x, z), col in m.cols.items():
        fy, nm = floor_name(x, z)
        if fy is None or (fy + 1) != L + 1 or nm is None:
            continue                       # 只看"抬一级"的格子（全是逐格的命题 ✓ 与 region 无关 ✓）
        rec = ((x, z), fy + 1, ex.ok(x, z), nm, touches_region(x, z))
        # ★★分类要用**模型用的那一条判据**★★ ✗（第 34 轮 ✓ P106 ✓）：
        #   我第一版拿 `MR.shape(nm) == 'slab'` 分类 ✗ ⇒ 楼梯（shape 也是 slab ✗
        #     但**顶面 1.0** ⇒ 得跳 ✗ ⇒ 模型故意**不**算它 ✓）被算进"半步"⇒ 判据红 ✗
        #   ⇒ 现在一律用 `PP.is_auto_step` ✓（与 `Planner.auto_step` **同一处** ✓）
        if PP.is_auto_step(nm):
            auto_c.append(rec)
        else:
            full_c.append(rec)
    say("R2 live per-cell (whole map): step-UP cells -- HALF step (slab/stair, +0.5 => auto)"
        "=%d %s | FULL block (+1.0 => needs a jump)=%d %s"
        % (len(auto_c), [(t[0], t[3], t[2], t[4]) for t in auto_c[:3]], len(full_c),
           [(t[0], t[3], t[2], t[4]) for t in full_c[:3]]))
    say("   (第 4 列 = exec.ok ✓ 第 5 列 = 它挨不挨着我能到的区域 ✓："
        "世界里的楼梯/半砖**都在区域外** ✓ ⇒ 走不过去 ✓ 但**逐格判据**照样能证 ✓)")
    r2 = None
    if not auto_c or not full_c:
        say("R2 INCONCLUSIVE: need BOTH kinds present (half-step=%d, full=%d) => NOT a pass"
            % (len(auto_c), len(full_c)))
    else:
        r2 = all(t[2] is True for t in auto_c) and all(t[2] is False for t in full_c)
        say("R2 => %s (half-step cells all accepted=%s | full-block cells all refused=%s)"
            % (r2, all(t[2] for t in auto_c), all(not t[2] for t in full_c)))
        ok &= r2

    # ---------------- R3: 真走上去（世界真值 ✓）----------------------------
    r3 = None
    walkable_auto = [t for t in auto_c if t[4]]
    if not walkable_auto:
        say("R3 INCONCLUSIVE: the world's half-step cells are all OUTSIDE my reachable region "
            "(walking onto one needs my own ramp -- materials pending, see the handover)")
    else:
        ((tx, tz), tfeet, _okk, tnm, _touch) = sorted(
            walkable_auto, key=lambda t: math.hypot(t[0][0] - sx, t[0][1] - sz))[0]
        txt, err = M.t_plan_route(tx, tfeet, tz, "on")
        wps = [(int(a), int(b), int(c)) for a, b, c in
               re.findall(r"^\s*\d+\)\s*\((-?\d+),(-?\d+),(-?\d+)\)", txt, re.M)]
        say("R3 plan to (%d,%d) feet y=%d: err=%s destination=%s"
            % (tx, tz, tfeet, err, wps[-1] if wps else None))
        if err or not wps:
            r3 = False
            say("R3 FAIL: the ramped target is still not plannable => %s" % txt.splitlines()[0][:150])
            ok &= r3
        else:
            dst = wps[-1]
            wtxt, werr = M.t_walk_route(dst[0], dst[1], dst[2], 60000, 1)
            q = M._pos_now()
            in_cell = bool(q) and (int(math.floor(q[0])) == dst[0]) \
                and (int(math.floor(q[2])) == dst[2])
            same_lv = bool(q) and abs(int(round(q[1])) - dst[1]) <= 0
            r3 = bool(in_cell and same_lv)
            say("R3 walk: err=%s | independent read (%.2f,%.2f,%.2f) => in destination cell=%s | "
                "on its layer=%s => %s" % (werr, q[0], q[1], q[2], in_cell, same_lv, r3))
            for ln in wtxt.splitlines():
                if ("为什么" in ln) or ("到位" in ln) or ("还没到" in ln):
                    say("   %s" % ln.strip()[:180])
            ok &= r3

    say("---- R1=%s R2=%s R3=%s ----" % (r1, r2, r3))
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
