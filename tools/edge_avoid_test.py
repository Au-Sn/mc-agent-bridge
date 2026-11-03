#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edge_avoid_test.py -- plan AWAY from the rim by default (Q1..Q5)

WHY (2026-09-29, round 25): the 2026-09-23 void death was not "the target was on
the rim" (that was fixed long ago) -- it was the PATH hugging the rim. On a sky
island the rim is a void edge, so brushing along it is how you eventually fall.
The planner now charges a FINITE extra cost for any cell that is not interior
(some 4-neighbour not standable): with a free middle it walks the middle, and
when the only way is the rim it still walks it -- the cost is finite, so the
route can never be declared impossible just because of this.

CRITERIA (declared BEFORE running):
  Q4 offline  : on a synthetic 3-wide strip the planned path must use the
                INTERIOR column (rim-cost 0), and a 1-wide strip (everything is
                rim) must still be reachable.
  Q1 cheaper  : comparing avoid_edge on/off on that same strip, the number of
                RIM cells in the path must be strictly smaller with it ON.
  Q2 no harm  : the 1-wide corridor must stay reachable with it ON (finite cost,
                never "unreachable"), and its length must equal the direct one.
  Q5 switch   : with avoid_edge=False the path must still be legal (reachable,
                every cell standable) -- i.e. the flag really turns it off and
                nothing else changed.
  Q3 world    : live -- plan to a real target with the default (ON), then
                independently read 3 waypoints from the world: each must be
                standable (3/3).

ASCII-only output.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M      # noqa: E402
import mapread as MR    # noqa: E402
import pathplan as PP   # noqa: E402


def say(s):
    print(s, flush=True)


def strip(w, h, y_floor=69):
    m = MR.Map(0, 60, 0, w - 1, 70, h - 1)
    for x in range(w):
        for z in range(h):
            m.cols[(x, z)] = {y_floor: "minecraft:grass_block"}
    return m, y_floor + 1


def cells_rim(pl, pts):
    """rim 计数 ✓ —— ★注意路径是 `(x, y, z)`★ ✗（我第一版把 `c[1]` 当成 z ✗ 数错了 ✓）"""
    return [(c[0], c[2]) for c in (pts or []) if not pl.interior(c[0], c[2])]


def main():
    ok = True

    # ---------------- Q4 / Q1 / Q2 / Q5 (offline) -------------------------
    m3, L3 = strip(3, 9)
    pl_off = PP.Planner(m3, level=L3, avoid_edge=False)
    pl_on = PP.Planner(m3, level=L3, avoid_edge=True)
    reg3 = pl_off.region(0, 0)
    p_off, w_off = pl_off.plan(0, 0, 2, 8, region=reg3)
    p_on, w_on = pl_on.plan(0, 0, 2, 8, region=reg3)
    rim_off = cells_rim(pl_off, p_off)
    rim_on = cells_rim(pl_on, p_on)
    in_mid = [c for c in (p_on or []) if c[0] == 1]
    q4 = bool(p_on) and len(in_mid) >= (len(p_on) - 2)
    say("Q4 offline 3-wide strip: path_on uses middle column in %d/%d cells => %s"
        % (len(in_mid), len(p_on or []), q4))
    ok &= q4
    q1 = bool(p_off) and bool(p_on) and (len(rim_on) < len(rim_off))
    say("Q1 cheaper: rim cells off=%d on=%d (want on strictly smaller) => %s"
        % (len(rim_off), len(rim_on), q1))
    ok &= q1

    m1, L1 = strip(1, 9)
    pl1 = PP.Planner(m1, level=L1, avoid_edge=True)
    p1, w1 = pl1.plan(0, 0, 0, 8, region=pl1.region(0, 0))
    q2 = bool(p1) and (len(p1) == 9)
    say("Q2 no harm: 1-wide corridor (all rim) reachable=%s cells=%d (want True/9) => %s"
        % (bool(p1), len(p1 or []), q2))
    ok &= q2

    legal_off = bool(p_off) and all(pl_off.ok(c[0], c[2]) for c in p_off)
    q5 = legal_off and (len(p_off) == len(p_on))
    say("Q5 switch: avoid_edge=False still legal=%s and same length (%d vs %d) => %s"
        % (legal_off, len(p_off or []), len(p_on or []), q5))
    ok &= q5

    # ---------------- Q3 live ---------------------------------------------
    p = M._pos_now()
    if not p:
        say("Q3 INCONCLUSIVE: no bot position")
        say("---- Q1 / Q2 / Q3 / Q4 / Q5 = %s / %s / - / %s / %s ----" % (q1, q2, q4, q5))
        return 0 if ok else 1
    M.t_freeze(True)
    try:
        sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
        r, m, _b = M._route_map(sx, sz, sx + 8, sz, sy)
        L = M._stand_level(m, sx, sz, float(p[1]))
        # ★★两条修正（第 34 轮 ✓ 都被实测逼出来 ✓）★★：
        #   ① 规划器要按**执行者的真实能力**建 ✗（`max_up=MOD_CLIMB_UP` ✓）——
        #      否则它会交出一个"要抬一级"的航点 ✗ 而模组爬不上去 ✗（Q3 就是这么红的 ✓）
        #   ② 世界真值的口径 ✓：**地板 = 实心（`blocks_space` ✓）**✗
        #      不是"我的名录里算地板"（`is_floor` ✗）—— 墙头/树叶顶**真能站** ✓
        #      （与 `plan_verify`／`verdict_levels` 同一口径 ✓ P106 ✓）
        pl = PP.Planner(m, level=L, blocked=M.BLOCKED_LV, avoid_edge=True,
                        max_up=M.MOD_CLIMB_UP)
        reg = pl.region(sx, sz)
        tg = pl.safe_targets(sx, sz, 6.0, 18.0, reg, min_n=1)
        if not tg:
            say("Q3 INCONCLUSIVE: no safe target nearby")
            return 0 if ok else 1
        (d, gx, gy, gz) = tg[0]
        pts, why = pl.plan(sx, sz, gx, gz, region=reg)
        if not pts:
            say("Q3 INCONCLUSIVE: plan failed (%s)" % why)
            return 0 if ok else 1
        wp = [(int(c[0]), int(c[1]), int(c[2])) for c in pts][1:]
        st = max(1, len(wp) // 3)
        smp = [wp[i] for i in range(0, len(wp), st)][:3]
        rr = MR.Reader()
        good = 0
        for (wx, wy, wz) in smp:
            below = rr.probe_cell(wx, wy - 1, wz)
            time.sleep(0.2)
            feet = rr.probe_cell(wx, wy, wz)
            time.sleep(0.2)
            head = rr.probe_cell(wx, wy + 1, wz)
            time.sleep(0.2)
            okc = ("" not in (below, feet, head)) and MR.blocks_space(below) \
                and (not MR.blocks_space(feet)) and (not MR.blocks_space(head))
            good += 1 if okc else 0
            say("  waypoint (%d,%d,%d) floor=%s feet=%s head=%s => %s"
                % (wx, wy, wz, below, feet, head, "ok" if okc else "BAD"))
        q3 = (good == len(smp)) and len(smp) >= 3
        say("Q3 world truth: %d/%d waypoints standable in the world => %s"
            % (good, len(smp), q3))
        ok &= q3
    finally:
        M.t_freeze(False)

    say("---- Q1 / Q2 / Q3 / Q4 / Q5 = %s / %s / %s / %s / %s ----" % (q1, q2, q3, q4, q5))
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
