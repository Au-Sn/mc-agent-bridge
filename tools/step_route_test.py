#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step_route_test.py -- 上下台阶的路，真的能走吗？(S1..S5, live)

WHY (2026-09-29, round 32): round 31 found and fixed the second real cause of the
user's "false unreachable": `Planner.ok()` allowed a walker to be one level up or
three levels down, then asked "can I stand AT MY OWN LAYER here?" -- so every cell
reachable only by a step up (the step/wall itself stands at my layer) or a step down
(my layer is air there) was refused. Offline checks and one live walk now cover the
fix, but the thing the user actually complains about is the WALK: `walk_to` and
`walk_route` on a route that has to change level. This test drives exactly that,
against the world, and it also checks the two limits that must keep refusing:
a drop of more than MAX_DOWN=3, and a cell that is genuinely not reachable.

CRITERIA (declared BEFORE running):
  S1 find steps : pick, from a fresh map, the nearest cell whose walkable layer is
                  exactly ONE LEVEL UP and the nearest one whose layer is BELOW the
                  bot's (a step down), both inside the connected region. Need at
                  least one of the two, else INCONCLUSIVE (never a pass). Also find,
                  if one exists, a cell whose floor is more than MAX_DOWN below
                  (the "must refuse" control).
  S2 plan       : `plan_route` to a step target must NOT refuse it for a MAP-side
                  reason (the reply must not say "not in your connected region" or
                  "really no path on the map"), and the destination it reports must
                  have the same feet layer as the target cell.
  S3 walk       : a real `walk_route` there. Judged against an independent read:
                  if the tool says arrived, the bot must really be inside the
                  destination cell (no false arrival); if it says not arrived, the
                  reply must carry the "why did I not arrive" line (round 31's rule).
  S4 limits     : if a drop-deeper-than-MAX_DOWN cell exists, `plan_route` there must
                  refuse (or move the destination), and the reply must explain --
                  the point is that the new level-awareness did not break the limit.
  S5 walk_to    : the SHORT-hop tool (<= 8 blocks, the mod's own pathfinder) to a
                  step target: never a false arrival (independent read), and its
                  outcome is printed verbatim -- this is the tool the user's
                  complaint names, so its behaviour is recorded, not assumed.

ASCII-only output (the console is GBK; Python writes UTF-8 and reconfigures stdout).
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


def pick_targets(m, level, sx, sz, region, rmax=12.0):
    """S1：从图里挑"抬一级 / 降下去 / 深坑"三类目标（**本地算** ✓ 不花调用 ✓）"""
    pl = PP.Planner(m, level=level, blocked=M.BLOCKED_LV)
    up, down, deep = [], [], []
    for (x, z) in region:
        d = math.hypot(x - sx, z - sz)
        if d < 2.0 or d > rmax:
            continue
        fy = pl.y(x, z)
        if fy is None:
            continue
        feet = fy + 1
        if feet == level + 1:
            up.append((round(d, 1), x, z, feet))
        elif feet < level:
            down.append((round(d, 1), x, z, feet))
            if level - feet > PP.MAX_DOWN:
                deep.append((round(d, 1), x, z, feet))
    up.sort()
    down.sort()
    deep.sort()
    return up, down, deep


def main():
    ok = True
    p = M._pos_now()
    if not p:
        say("INCONCLUSIVE: no bot position (bot alive? -> py tools/respawn_bot.py)")
        return 0
    sx, sy, sz = int(p[0]), int(round(float(p[1]))), int(p[2])
    say("bot at (%d,%s,%d) feet L=%d" % (sx, p[1], sz, sy))

    r = MR.Reader()
    _r, m, _box = M._route_map(sx, sz, sx + 6, sz, sy)
    level = M._stand_level(m, sx, sz, float(p[1]))
    say("map box=%s cols=%d | LEVEL=%d (MAX_UP=%d MAX_DOWN=%d)"
        % (m.box, len(m.cols), level, PP.MAX_UP, PP.MAX_DOWN))
    pl = PP.Planner(m, level=level, blocked=M.BLOCKED_LV)
    region = pl.region(sx, sz)
    say("connected region at my level: %d cells" % len(region))

    up, down, deep = pick_targets(m, level, sx, sz, region)
    say("S1 steps found: step-UP=%d %s | step-DOWN=%d %s | deeper-than-MAX_DOWN=%d %s"
        % (len(up), up[:2], len(down), down[:2], len(deep), deep[:2]))
    s1 = bool(up or down)
    no_sample = []                    # ★记下"哪几条是**没有样本**✗ 而不是坏了✗★（P147/P149 ✓）
    if not s1:
        say("S1 INCONCLUSIVE: no step cell beside me right now (flat ground) => NOT a pass")
        no_sample.append("S1")
    ok &= s1

    # ---------------- S2 / S3: the step target we will actually drive ----------
    s2 = s3 = None
    target = up[0] if up else (down[0] if down else None)
    if target:
        _d, tx, tz, tfeet = target
        say("--- step target (%d,%d) feet y=%d (mine is %d) ---" % (tx, tz, tfeet, level))
        txt, err = M.t_plan_route(tx, tfeet, tz, "on")
        mapside = [w for w in ("不在你脚下这块连通区域", "图上**真的不通**") if w in txt]
        wps = [(int(a), int(b), int(c)) for a, b, c in
               re.findall(r"^\s*\d+\)\s*\((-?\d+),(-?\d+),(-?\d+)\)", txt, re.M)]
        dst = wps[-1] if wps else None
        # ★★S2 改口径 ★ ✗（第 33 轮 ✓ 必须说清为什么改 ✓）：
        #   第 32 轮这条判据是"**必须是规划得出来**"✗（当时 `max_up=1` ✓ 抬一级交给规划 ✓）
        #   第 32 轮**实测**✓：模组爬不上"抬一级"✗（停在 0.8~1.7 格外 ✗ 还当"到了"✗）
        #     ⇒ 第 33 轮执行用的规划按模组真实能力算 ✓（`MOD_CLIMB_UP=0` ✓）
        #     ⇒ 现在**正确的行为是"拒"** ✓ —— 而且要**拒得对**：理由必须点到"抬一级/爬不上去"✗
        #       不许说"中间隔着虚空"✗（P116／P117 ✓）
        #   ⇒ 两种能力值下判据相反 ✓（都写在代码里 ✓ 不许凭印象 ✓）
        named = ("抬一级" in txt) or ("爬不上去" in txt)
        voids = ("中间隔着虚空" in txt) or ("走过去要跨虚空" in txt)
        if M.MOD_CLIMB_UP < 1:
            s2 = bool(err) and named and (not voids)
        else:
            s2 = (not err) and (not mapside) and bool(wps) and (dst is not None) \
                and (dst[1] == tfeet)
        say("S2 plan to a step cell: err=%s | names the climb=%s | blames the void=%s | "
            "destination=%s (want feet y=%d) | MOD_CLIMB_UP=%d => %s"
            % (err, named, voids, dst, tfeet, M.MOD_CLIMB_UP, s2))
        ok &= s2

        if s2 and dst is not None:
            wtxt, werr = M.t_walk_route(dst[0], dst[1], dst[2], 45000, 1)
            q = M._pos_now()
            in_cell = bool(q) and (int(math.floor(q[0])) == dst[0]) \
                and (int(math.floor(q[2])) == dst[2])
            great = math.hypot(q[0] - dst[0], q[2] - dst[2]) if q else -1
            said = ("到位 ✓" in wtxt) or ("**在目标格里 = True**" in wtxt)
            explained = ("为什么没到" in wtxt) or ("为什么停" in wtxt)
            s3 = (in_cell and great <= 1.6) if said else explained
            say("S3 walk to a step cell: tool said arrived=%s | why-line=%s | "
                "independent read (%.2f,%.2f) => in-cell=%s dist-to-cell-corner=%.2f => %s"
                % (said, explained, q[0] if q else -1, q[2] if q else -1, in_cell,
                   great, s3))
            for ln in wtxt.splitlines():
                if ("为什么" in ln) or ("到位" in ln) or ("还没到" in ln):
                    say("   %s" % ln.strip()[:190])
            ok &= bool(s3)
        # ★S3 的另一种合法结局（第 33 轮 ✓）：执行者能力=0 ⇒ 规划**就该拒** ✗
        #   ⇒ 没有目的地可走 ⇒ **如实说 INCONCLUSIVE**✗（不许当成"走过了"✓ 也不许当失败 ✗）
        if s2 and dst is None:
            say("S3 INCONCLUSIVE (not a pass): the step-up was correctly refused "
                "(MOD_CLIMB_UP=%d) => there is nothing honest to walk" % M.MOD_CLIMB_UP)

    # ---------------- S4: the drop limit must still refuse --------------------
    s4 = None
    if deep:
        _d, dx, dz, dfeet = deep[0]
        txt, err = M.t_plan_route(dx, dfeet, dz, "on")
        wps = re.findall(r"^\s*\d+\)\s*\((-?\d+),(-?\d+),(-?\d+)\)", txt, re.M)
        dst = tuple(int(v) for v in wps[-1]) if wps else None
        refused = err or (dst is not None and dst[1] != dfeet)
        s4 = bool(refused)
        say("S4 deeper-than-MAX_DOWN target (%d,%d) feet y=%d => refused-or-moved=%s "
            "(destination=%s) => %s" % (dx, dz, dfeet, refused, dst, s4))
        ok &= s4
    else:
        say("S4 INCONCLUSIVE: no cell deeper than MAX_DOWN=%d beside me" % PP.MAX_DOWN)
        no_sample.append("S4")

    # ---------------- S5: the short-hop tool (the one the user names) ---------
    s5 = None
    if target and math.hypot(target[1] - sx, target[2] - sz) <= 8.0:
        _d, tx, tz, tfeet = target
        wtxt, werr = M.t_walk_to(tx, tfeet, tz)
        q = M._pos_now()
        in_cell = bool(q) and (int(math.floor(q[0])) == tx) \
            and (int(math.floor(q[2])) == tz)
        line = (wtxt or "(no reply)").strip().splitlines()[0][:180]
        said = ("到达" in (wtxt or "")) and ("没到" not in (wtxt or ""))
        s5 = in_cell if said else True      # 不许假报"到了"✓；没到就如实记录 ✓
        say("S5 walk_to (short hop) to (%d,%d): reply=%s" % (tx, tz, line))
        say("   tool said arrived=%s | independent read in-cell=%s => %s"
            % (said, in_cell, s5))
        ok &= bool(s5)
    else:
        say("S5 INCONCLUSIVE: the step target is further than 8 blocks (walk_to's limit)")
        no_sample.append("S5")

    say("---- S1=%s S2=%s S3=%s S4=%s S5=%s ----" % (s1, s2, s3, s4, s5))
    # ★★"测不了"要**自己说出来**✗★★（2026-09-30 第 40 轮末 ✓ ⇒ P147/P149 ✓ 第 3 例 ✓）
    #   ✗ 实测（重启后 ✓）：这一带**是平地** ✗ ⇒ S1/S4/S5 **全都**自己印着 INCONCLUSIVE ✗
    #     可最后收在 `=> FAIL` ✗ ⇒ ★总检把它记成"坏了"✗★（而它输的是"**这地方没有台阶可测**"✓）
    #   ⇒ 口径 ✓ 与 `route_view`／`r3_verify`／`verdict_levels` **同一套** ✗ ——
    #     打 `=> INCONCLUSIVE` ✗ ＋ 退出码非 0 ✗ ⇒ 总检单列"★测不了✗★" ✓
    #   ⚠ `s1 = False` **也是"没有样本"**✗（"我旁边没有台阶格" ✓）⇒ 它已经记进 `no_sample` ✓
    #     ⇒ 这里**只看 S2~S5** ✗（★第一版把 s1 也当"失败"✗ ⇒ 又掉回 FAIL ✓ 自己抓到的 ✓★）
    if no_sample and not any(x is False for x in (s2, s3, s4, s5)):
        say("=> INCONCLUSIVE: 这一带**没有台阶样本**✗（%s ✓ —— ★平地/太远 ⇒ 测不了✗★）"
            " —— ★不是通过✗ 也不是坏✗★ 换个位置再测 ✓" % "／".join(no_sample))
        return 1
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
