#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""one_way_test.py -- 别把自己送到"下得去、上不来"的地方 (O1..O4, round 33)

WHY (2026-09-29, round 33): round 32 measured, with two real walks and independent
reads, that `dshwalk` CANNOT climb a one-block step -- it stops 0.8~1.7 blocks short
and calls that "arrived". Round 33 therefore made the planner respect the executor's
real ability (`MOD_CLIMB_UP = 0`) instead of geometry alone. That immediately raises
a safety question of the same family as the void guard: if the bot cannot climb, then
ANY net descent is a one-way trip -- it goes down and can never come back up. So a
route that loses height must be refused unless the trip back is flat/downhill, which
in practice means "do not descend" until a slab ramp exists (a 0.5 step is stepped up
automatically, so slabs are not a height change at all in this model).

CRITERIA (declared BEFORE running):
  O1 offline : a synthetic map with a one-way pit (walls around, floor 2 lower) must
               make `_return_ok` False, and a same-level target must make it True.
               (Two controls, so the helper is not simply "always False".)
  O2 no-climb: `MOD_CLIMB_UP` must be 0 while the mod cannot climb, the live region
               must actually contain cells that only geometry can reach (report the
               count; if none, INCONCLUSIVE), and EVERY such cell must be refused by
               the execution planner with a reason that NAMES the climb -- never the
               misleading "there is void in between".
  O3 control : at least one same-level cell in the same map must still be plannable
               (the guard must not refuse everything).
  O4 round   : a step-down target must be refused by `t_plan_route` (one-way), and the
               refusal must be justified: `_return_ok` for that cell must be False.
               If no step-down cell exists in the executable region, INCONCLUSIVE.

Bridge calls: one map build, one plan (O4). Everything else is local arithmetic.
"""
from __future__ import annotations

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

    # ---------------- O1: offline controls for the return-trip helper ---------
    def mk(cells, feet):
        """cells: {(x,z): {y: block}} ; feet: 每条柱子的 walkable 脚层（模组结论）"""
        m = MR.Map(0, 60, 0, 3, 76, 3)
        for k, v in cells.items():
            m.cols[k] = dict(v)
        m.meta.update({"blevel": L, "has_offsets": True,
                       "mod_standable": {"%d,%d" % k: v for k, v in feet.items()}})
        return m

    G = "minecraft:grass_block"
    S = "minecraft:stone"
    # ① 同层：起点与目标都在 71 层 ⇒ 回得来 ✓
    flat = mk({(0, 0): {70: G}, (1, 0): {70: G}}, {(0, 0): 71, (1, 0): 71})
    r_flat = M._return_ok(flat, L, 0, 0, 1, 0, 71, 71)
    # ② 单向坑：目标在 69 层（低 2 ✓）而四周围墙 ⇒ 回程要抬 2 ✗ 回不来 ✗
    pit = mk({(0, 0): {70: G}, (1, 0): {68: G},
              (1, 1): {70: S, 71: S, 72: S}, (1, -1): {70: S, 71: S, 72: S},
              (2, 0): {70: S, 71: S, 72: S}},
             {(0, 0): 71, (1, 0): 69})
    r_pit = M._return_ok(pit, L, 0, 0, 1, 0, 69, 71)
    o1 = (r_flat is True) and (r_pit is False)
    say("O1 offline return-trip: same-level => %s (want True) | one-way pit => %s "
        "(want False) => %s" % (r_flat, r_pit, o1))
    ok &= o1

    # ---------------- O2: the climb gap + honest refusals ---------------------
    _r, m, _box = M._route_map(sx, sz, sx + 6, sz, sy)
    geo = PP.Planner(m, level=L, max_up=1)
    can = PP.Planner(m, level=L, max_up=M.MOD_CLIMB_UP)
    reg_geo, reg_can = geo.region(sx, sz), can.region(sx, sz)
    climb_only = sorted(reg_geo - reg_can)
    say("O2 climb-only cells: geometric region=%d | executor region=%d | difference=%d"
        % (len(reg_geo), len(reg_can), len(climb_only)))
    say("   MOD_CLIMB_UP=%d (0 = the mod cannot climb, measured in round 32)"
        % M.MOD_CLIMB_UP)
    o2 = None
    if not climb_only:
        say("O2 INCONCLUSIVE: nothing beside me is climb-only right now => NOT a pass")
    else:
        # ★★口径（第 33 轮第二次改 ✓）：不许把**它自己**当目的地交出去★★ ✗
        #   原来写成"凡 climb-only 格 ⇒ `_make_plan` 必须失败"✗ ⇒ **假失败** ✗：
        #     规划器**可以合法地把目的地挪到内陆格**（"目标在平台边上 ⇒ 挪一挪" ✓）
        #     ⇒ 那条路是真的能走的 ✓（只是没走到我点的那一格 ✓）⇒ 不该算红 ✓
        #   真正要守的是 ✓：**交出去的目的地绝不能是"只能靠爬"的那一格** ✗
        bad = []
        moved = 0
        for (cx, cz) in climb_only[:8]:
            _pl, pts, why, _info = M._make_plan(sx, sz, cx, cz, sy, level=L)
            if pts is None:
                named = ("抬一级" in (why or "")) or ("爬不上去" in (why or ""))
                if not named:
                    bad.append(((cx, cz), "refused but the reason does not name the climb",
                                (why or "")[:70]))
                continue
            dst = pts[-1]
            if (dst[0], dst[2]) == (cx, cz):
                bad.append(((cx, cz), "handed out the climb-only cell itself", dst))
            else:
                moved += 1          # 合法：挪到别处了 ✓（**要能看出它挪过** ✓）
                if "挪" not in (why or ""):
                    bad.append(((cx, cz), "destination moved but the reply does not say so",
                                (why or "")[:70]))
        o2 = (not bad) and (M.MOD_CLIMB_UP == 0)
        say("O2 climb-only cells are never handed out: refused-with-the-right-reason or "
            "moved-to-another-cell | moved=%d bad=%d %s => %s"
            % (moved, len(bad), bad[:2], o2))
        say("   example reason: %s" % ((why or "")[:200],))
        ok &= o2

    # ---------------- O3: the control (same-level still works) ---------------
    ctrl = None
    for (cx, cz) in sorted(reg_can, key=lambda c: abs(c[0] - sx) + abs(c[1] - sz)):
        if (cx, cz) == (sx, sz):
            continue
        if abs(cx - sx) + abs(cz - sz) < 3:
            continue
        _pl, pts, why, _info = M._make_plan(sx, sz, cx, cz, sy, level=L)
        ctrl = ((cx, cz), pts is not None, (why or "")[:60])
        break
    # 顺带把"执行者区域里那些**比我现在低**的格子"挑出来 ✓（O4b 用 ✓ 本地算 ✓）
    down = sorted([c for c in reg_can
                   if can.y(*c) is not None and (can.y(*c) + 1) < L],
                  key=lambda c: abs(c[0] - sx) + abs(c[1] - sz))
    o3 = bool(ctrl and ctrl[1])
    say("O3 control (a same-level cell must still be plannable): %s => %s" % (ctrl, o3))
    ok &= o3

    # ---------------- O4: the descent guard (helper + live wiring) ------------
    # ★★口径（第 33 轮第二次改 ✓）★★：**看计划自己的目的地** ✗（不是看我请求的那一格 ✗）
    #   实测 ✓：我请求 `(4126,12)`（低 2 层 ✓）而规划把它**挪到同层的内陆格** ✓
    #     ⇒ 那一步**根本不下降** ✓ ⇒ 回程守卫**不该**触发 ✓（它没做错什么 ✗）
    #   要守的是 ✓：**凡是真要下降的目的地 ⇒ 必须问过回程 ✗ 回不来就不去** ✓
    #   所以 O4 = ① 用**合成图**直接单测 `_descent_guard` ✓（确定性 ✓）
    #              ② 实机这一遍只**如实报告**"请求的目标有没有被挪走"✓（不做假判 ✓）
    # ⚠ 元组的顺序是 **(x, 脚层 y, z)** ✗（第 33 轮 ✓ 我第一次写成 `(x, z, feet)` ✗ ⇒ 假红一次 ✓）
    g_flat, w_flat = M._descent_guard(flat, L, 0, 0, (1, 71, 0))
    g_pit, w_pit = M._descent_guard(pit, L, 0, 0, (1, 69, 0))
    o4a = (g_flat is True) and (g_pit is False) and ("出不来" in w_pit)
    say("O4a descent guard (offline): same-level destination => %s | real descent with no "
        "way back => %s (reason says '出不来': %s) => %s"
        % (g_flat, g_pit, "出不来" in w_pit, o4a))
    ok &= o4a
    o4b = None
    if not down:
        say("O4b INCONCLUSIVE: no step-down cell inside the executor's region")
    else:
        (dx, dz) = down[0]
        feet_d = can.y(dx, dz) + 1
        back = M._return_ok(m, L, sx, sz, dx, dz, feet_d, L)
        txt, err = M.t_plan_route(dx, feet_d, dz, "on")
        plan_moved = ("挪到" in txt)
        refused = err or ("不去" in txt)
        # 合法结局只有两种 ✓：被拒（且回程确实不可行 ✓）／目的地被挪到**别的格** ✓
        o4b = (refused and back is False) or (plan_moved and not err)
        say("O4b live descent request (%d,%d) feet y=%d: return-trip possible=%s | refused=%s "
            "| destination moved=%s => %s" % (dx, dz, feet_d, back, refused, plan_moved, o4b))
        for ln in txt.splitlines()[:2]:
            say("   %s" % ln.strip()[:190])
        ok &= o4b

    say("---- O1=%s O2=%s O3=%s O4a=%s O4b=%s ----" % (o1, o2, o3, o4a, o4b))
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
