#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edge_hop_test.py -- walking the rim? then walk it carefully (R1..R4)

WHY (2026-09-29, round 26): last round the planner learned to avoid the rim by
default. But when the ONLY way is along the rim it still has to walk it -- and
the 2026-09-23 fall happened exactly there. So a hop that touches rim cells now
gets a shorter jump distance (<=4 instead of <=8) and one extra probe. It is
NOT rerouted: the planner already avoided what it could, and "no other way" is
precisely the case where rerouting is impossible.

CRITERIA (declared BEFORE running):
  R1 fires right : a hop whose cells are rim-only must come back with a jump cap
                   of <= 4 and one extra probe; a hop through the middle must
                   come back unchanged (8 / 4).
  R4 accounting  : when it fires, the reason string must say the hop hugs the
                   rim AND that it still walks it (no silent slowdown) AND -- added
                   in round 31 after a real death (2026-09-29 18:56:26, the game log
                   says "Bot fell out of the world" while THIS test was running) --
                   that it stays on ONE level: near the rim a step up means standing
                   on the step/wall with the void right behind it.
  R3 no harm     : the middle case must be byte-identical to the old policy
                   (chunk 8, sweep 4, empty reason).
  R2 world truth : live -- a real walk_route to a target 8..14 blocks away must
                   still ARRIVE (measured by this script) and end inside the
                   connected platform (not on a rim cell, not in the void).

ASCII-only output.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
# ★出口编码★ ✗（2026-09-29 第 26 轮 ✓ 我这条测试要打印**工具原文** ✓ 而原文里有 `✗`/`✓` ✗
#   本机控制台是 **GBK** ✗ ⇒ 直接 `UnicodeEncodeError` 崩掉 ✓ —— 与 `install_mod.py` 那次同款 ✓
#   口径 ✓：**要打非 ASCII 就先 reconfigure** ✓（要么就只打 ASCII ✓ 二选一 ✗ 别两头都占 ✗）
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import mc_mcp as M      # noqa: E402
import mapread as MR    # noqa: E402
import pathplan as PP   # noqa: E402


def say(s):
    print(s, flush=True)


def strip(w, h):
    m = MR.Map(0, 60, 0, w - 1, 70, h - 1)
    for x in range(w):
        for z in range(h):
            m.cols[(x, z)] = {69: "minecraft:grass_block"}
    return m, 70


def main():
    ok = True

    # ---------------- R1 / R3 / R4 offline --------------------------------
    m3, L = strip(3, 9)
    pl = PP.Planner(m3, level=L)
    mid = [(1, L, z) for z in range(0, 6)]
    edge = [(0, L, z) for z in range(0, 6)]
    c_mid, s_mid, why_mid = M._hop_policy(pl, mid, 8, 4)
    c_edge, s_edge, why_edge = M._hop_policy(pl, edge, 8, 4)
    r1a = (c_edge <= 4) and (s_edge == 5)
    say("R1a rim hop -> chunk=%s sweep=%s (want <=4 / 5) => %s" % (c_edge, s_edge, r1a))
    r1b = (c_mid == 8) and (s_mid == 4)
    say("R1b middle hop -> chunk=%s sweep=%s (want 8 / 4) => %s" % (c_mid, s_mid, r1b))
    r1 = r1a and r1b
    ok &= r1
    r3 = (why_mid == "") and (c_mid, s_mid) == (8, 4)
    say("R3 no harm: middle is unchanged and has no reason string => %s" % r3)
    ok &= r3
    # ★★R4 口径（第 31 轮补 ✓）：★"照走"之外还要**说清"只走同层"**★★ ✗
    #   为什么 ✗：2026-09-29 18:56:26 游戏日志写着 `Bot 掉出了这个世界` ✗ ——
    #     当时正是在跑**这个**测试（故意沿边走 ✓）✓
    #   真因 ✓：`ok()` 修好之后规划**允许抬一级** ✓ 而**边上一格抬一级 = 踩到台阶/墙头** ✓
    #     它外侧**就是虚空** ✗ ⇒ 跳空一次就掉下去 ✗
    #   ⇒ 政策改了 ✓：贴边那一跳**只走同层** ✓（同层真没路 ⇒ **不走** ✓）
    #     ⇒ 判据要同时认这两句 ✓（不然"改好的政策"会被旧判据判红 ✗ —— 实测就是这么红的 ✓）
    r4 = ("贴着边" in why_edge) and ("照走" in why_edge) and ("只走同层" in why_edge)
    say("R4 accounting: reason says it hugs the rim, still walks it, and stays on ONE "
        "level => %s" % r4)
    say("   reason: " + why_edge[:120])
    ok &= r4

    # ---------------- R2 live (regression) --------------------------------
    p = M._pos_now()
    if not p:
        say("R2 INCONCLUSIVE: no bot position")
        say("---- R1 / R2 / R3 / R4 = %s / - / %s / %s ----" % (r1, r3, r4))
        return 0 if ok else 1
    M.t_freeze(True)
    try:
        sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
        r, m, _b = M._route_map(sx, sz, sx + 8, sz, sy)
        L0 = M._stand_level(m, sx, sz, float(p[1]))
        pl0 = PP.Planner(m, level=L0, blocked=M.BLOCKED, avoid_edge=True)
        reg = pl0.region(sx, sz)
        tg = [c for c in pl0.safe_targets(sx, sz, 8.0, 14.0, reg, min_n=1)]
        # ★★目标必须**同层**✗★★（2026-09-30 修 ✓ ⇒ P140/P141 ✓）
        #   ✗ 原来取"8~14 格内**任意**目标"✗ ⇒ 实测挑到 `(4114,71,4)`＝假人脚下 **2 层** ✗
        #     ⇒ ★中间层**正确地**把它拦下了**✗★（P120「下得去上不来 ⇒ 拦住」✓ 位移 0 ✓）
        #       ⇒ 而这条测试的 R4 自己写着"**只走同层**"✗ ⇒ ★是**前提**不自洽✗★
        #     ⇒ 结果：模组**一条事件都没发** ✗ ⇒ 判据失败却**没有对面的理由** ✗（假红 ✓）
        #   ⇒ 口径 ✓：这里只挑**与 `L0` 同层**的目标 ✓；一个都没有 ⇒ **INCONCLUSIVE** ✓
        #     （★"没得测"与"测不过"必须分清✗★ P116 ✓）
        tg_same = [c for c in tg if int(c[2]) == int(L0)]
        if not tg_same:
            say("R2 INCONCLUSIVE: 8~14 格内**没有同层**目标（%d 个候选都不在 L=%d ✓）"
                % (len(tg), L0))
            say("   ★这条测试的前提本来就是「只走同层」✗ ⇒ 不拿跨层目标硬测 ✓"
                "（跨层会被中间层**正确地**拦下 ✓ 那样测出来的只是拦得对 ✓）★")
            M.t_freeze(False)
            say("---- R1 / R2 / R3 / R4 = %s / INCONCLUSIVE / %s / %s ----" % (r1, r3, r4))
            return 0 if ok else 1
        tg = tg_same
        if not tg:
            say("R2 INCONCLUSIVE: no target in the 8..14 block band")
            return 0 if ok else 1
        (d, gx, gy, gz) = tg[0]
        say("R2 walking to (%d,%d,%d) %.1f blocks away" % (gx, gy, gz, d))
        wtxt, werr = M.t_walk_route(gx, L0, gz, 25000, 2, None, 4, "on")
        end = M._pos_now()
        if end is None:
            say("R2 ABORT: cannot read the position afterwards")
            return 1
        dist = math.dist((end[0], end[2]), (gx, gz))
        arrived = dist <= 2.0
        r2, mm, _bb = M._route_map(int(end[0]), int(end[2]), int(end[0]) + 8,
                                   int(end[2]), int(end[1]))
        LL = M._stand_level(mm, int(end[0]), int(end[2]), float(end[1]))
        pl2 = PP.Planner(mm, level=LL, blocked=M.BLOCKED)
        on_platform = (int(end[0]), int(end[2])) in pl2.region(int(end[0]), int(end[2]))
        fired = "贴着边" in wtxt
        # 在平台上 ⇒ 它没掉下去 ✓（掉下去的话 region 里不会有它 ✓）
        r2ok = bool(arrived and on_platform) and (not werr or arrived)
        say("R2 world truth: distance %.2f arrived=%s on-platform=%s | policy fired "
            "during this walk=%s => %s" % (dist, arrived, on_platform, fired, r2ok))
        ok &= r2ok
        # ★★判据**失败时必须带上对面自己的理由**✗★★（2026-09-30 ✓ ⇒ P140 ✓）：
        #   ✗ 原来这条只印"没到 ✗"✗ ⇒ 独立诊断拿不到模组那句 `why=` ⇒ 只能标 INCONCLUSIVE ✗
        #   ⇒ 口径 ✓：失败时去**事件流**（纯 ASCII ✓ 不过 CC 终端 ⇒ 中文不会变 `?` ✓）
        #     里把最后一条 `walk_done … why=…` 捞出来印上 ✓（`M.walk_why` ✓）
        if not r2ok:
            say("R2 ☆模组自己的理由（事件流 ✓）☆：%s"
                % (M.walk_why() or "（事件里没有 `why=` ✗ 那就要看是不是没进模组 ✓）"))
        r2ok_result = r2ok
    finally:
        M.t_freeze(False)

    say("---- R1 / R2 / R3 / R4 = %s / %s / %s / %s ----" % (r1, r2ok_result, r3, r4))
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
