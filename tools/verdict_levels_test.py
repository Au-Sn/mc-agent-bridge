#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verdict_levels_test.py -- does the mod's verdict make the map USABLE at that level?
(V1..V6, live; round 31, 2026-09-29)

WHY: round 30 started storing, per column, the layer the mod's collision-based
`standable()` said was walkable (`meta["mod_standable"]`), and made `standable()` /
`cell_kind()` / `Planner.y()` all consult it. But `ok=False` / `y=None` came back for
a whole class of those cells -- the wall tops
(`mcwfences:sandstone_grass_topped_wall` at y=71, verdict "you can stand at 72"):
the cells are now IN the map (round 30 stopped dropping them) yet the planner, fixed
at the bot's own level, still refuses them -- which is correct AT ITS LEVEL (a wall
is standing at 71) and wrong if the level is not taken into account.

So the claim to check is not "the bot can walk there now" but the precise one:
**a planner at the verdict's own level must accept that cell, and a planner at
another level must not let the verdict leak.** Everything below is that claim
made measurable -- and it is all zero-call except the two live calls at the end.

CRITERIA (declared BEFORE running):
  V1 inventory : the map must hold >= 10 verdict cells; count and report the class C
                 = verdict cells whose stored floor block is NOT `is_floor`
                 (wall tops / canopies -- the cells round 30 stopped dropping).
                 Fewer than 10 verdicts => INCONCLUSIVE (never a pass).
  V2 usable    : for EVERY cell in class C, a `Planner(m, level=verdict_y)` must say
                 ok() is True AND y() == verdict_y - 1. (Before round 30 the cell was
                 not in the map at all; this is the "the map lets you walk on it when
                 you are up there" half.)
  V3 no leak   : the verdict is a statement about ONE layer. For every class-C cell
                 whose verdict_y differs from the bot's level, `standable(x, z,
                 below=bot_level+1)` must be False whenever the map stores a blocking
                 block at the bot's level there (live case: the wall itself).
  V4 no None   : over every cell of the connected region, `ok(x,z)` and
                 `y(x,z) is not None` must agree -- `ok` True with `y` None is the
                 inconsistency that would crash a plan on `None + 1`.
  V5 plan      : `plan_route` to the nearest class-C cell must NOT refuse it for a
                 map-side reason (the reply must not say the target is unreachable /
                 not in the connected region). The destination it reports is printed.
  V6 walk      : a real `walk_route` attempt. Judged BOTH ways against an independent
                 read: if the tool says arrived, the bot must really end within 1.5
                 blocks of that cell (no false arrival); if it says not arrived, the
                 reply MUST say WHY (it must carry the "why did I not arrive" line
                 with the layer difference) -- a bare "did not arrive" leaves the
                 brain unable to act, which is the same family as the old
                 "walks there but both sides say not-arrived" complaint. The measured
                 distance is printed as-is; the mod's pathfinder may legitimately
                 refuse a 1.5-high step, and that is the world's answer, not the
                 map's.

Bridge calls: one map build, one plan, one walk, one probe. ASCII-only output.
"""
from __future__ import annotations

import math
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
    sx, sy, sz = int(p[0]), int(round(float(p[1]))), int(p[2])
    say("bot at (%d,%s,%d) feet cell L=%d" % (sx, p[1], sz, sy))

    r = MR.Reader()
    m = r.build_dshmap(radius=16)
    if m is None:
        say("INCONCLUSIVE: /dshmap unavailable (old mod)")
        return 0
    ms = m.meta.get("mod_standable") or {}
    bl = m.meta.get("blevel")
    say("map box=%s cols=%d blevel=%s verdicts=%d"
        % (m.box, len(m.cols), bl, len(ms)))

    # ---------------- V1: inventory + the interesting class ----------------
    rows = []
    for key, fy in ms.items():
        a, _, b = key.partition(",")
        try:
            x, z, fy = int(a), int(b), int(fy)
        except Exception as e:
            # 记录：一条模组结论解析不了 ⇒ 它既不进 V1 计数也不进 V2 检查（可能假绿）
            say("  ★记录✗★ V1/V2 少查一条结论（键解析不了 ⇒ 可能假绿）：%r（%s）"
                % (key, type(e).__name__))
            continue
        nm = (m.cols.get((x, z)) or {}).get(fy - 1)
        rows.append(((x, z), fy, nm))
    clsC = [t for t in rows if t[2] and not MR.is_floor(t[2])]
    v1 = len(rows) >= 10
    if not v1:
        say("V1 INCONCLUSIVE: only %d verdict cells" % len(rows))
    else:
        say("V1 inventory: verdicts=%d | class C (floor is NOT is_floor, i.e. wall tops "
            "/ canopies)=%d %s => %s"
            % (len(rows), len(clsC), sorted({t[2] for t in clsC})[:4], v1))
    ok &= v1

    # ---------------- V2: usable at the verdict's own level ----------------
    # ★口径★ ✗（第 31 轮第二次改 ✓）：这里问的是"**图让不让你站上去**"✗
    #   ⇒ **不许**把"本会话探到的挡路记忆"（`BLOCKED` ✓）算进来 ✗ —— 那是**另一件事** ✓
    #   （实测 ✓：上一次失败的走把那一堵墙记进了 `BLOCKED` ✗ ⇒ V2 就会红 ✗
    #     可几何上那一格**是能站的** ✓ ⇒ 判据把两件事混成了一个 ✗ 又是 P106 同族 ✓）
    bad2 = []
    for ((x, z), fy, nm) in clsC:
        pl = PP.Planner(m, level=fy)          # ★不带 `BLOCKED`★ ✗（只问几何 ✓）
        if not pl.ok(x, z) or pl.y(x, z) != fy - 1:
            bad2.append(((x, z), fy, nm, pl.ok(x, z), pl.y(x, z)))
    v2 = bool(clsC) and (not bad2)
    if not clsC:
        say("V2 INCONCLUSIVE: no class-C cell in this map (the bot is not near a wall "
            "top / canopy right now)")
    else:
        say("V2 usable at the verdict level: class-C cells=%d, refused or wrong floor=%d "
            "%s => %s" % (len(clsC), len(bad2), bad2[:3], v2))
        ok &= v2

    # ---------------- V3: the verdict must not leak to other layers --------
    bc = m.meta.get("blocked_cells") or {}
    leak = []
    for ((x, z), fy, nm) in clsC:
        if fy == sy:
            continue
        blocked_here = (m.cols.get((x, z)) or {}).get(sy)
        if blocked_here and MR.blocks_space(blocked_here) \
                and m.standable(x, z, below=sy + 1) is True:
            leak.append(((x, z), fy, blocked_here))
    v3 = (not leak)
    say("V3 no leak to the bot's level: cells where the verdict at y=%s made the map "
        "claim standable at the bot's layer even though a blocking block is stored "
        "there=%d %s => %s" % (bl, len(leak), leak[:3], v3))
    ok &= v3

    # ---------------- V4: ok <=> y is not None over the region -------------
    plb = PP.Planner(m, level=sy, blocked=M.BLOCKED_LV)
    reg = plb.region(sx, sz)
    inc = []
    for (x, z) in reg:
        a = plb.ok(x, z)
        b = plb.y(x, z) is not None
        if a != b:
            inc.append(((x, z), a, b))
    v4 = (not inc) and (len(reg) > 0)
    say("V4 ok/y agree over the region: region=%d cells, disagreements=%d %s => %s"
        % (len(reg), len(inc), inc[:3], v4))
    ok &= v4

    # ---------------- V5/V6: plan and walk to the nearest class-C cell -----
    fresh = [t for t in clsC if t[0] not in M.BLOCKED]
    skipped = len(clsC) - len(fresh)
    target = None
    if not clsC:
        say("V5/V6 INCONCLUSIVE: no class-C cell to aim at")
    elif not fresh:
        say("V5/V6 INCONCLUSIVE: all %d class-C cells are in the session obstacle memory "
            "(BLOCKED) -- from an earlier failed walk -- so there is no clean target"
            % len(clsC))
    else:
        # ★挑目标时要**跳过本会话已记为障碍的格子**★ ✗（第 31 轮 ✓）：
        #   上一次失败的走会把那一堵墙记进 `BLOCKED` ✓（24 小时 ✓ 这是**故意**的设计 ✓）
        #   ⇒ 判据要**接着用**这个现实 ✓ 而不是假装它不存在 ✗（并如实报出跳过了几个 ✓）
        say("V5/V6 pick a clean class-C target: %d available, %d skipped (already in BLOCKED)"
            % (len(fresh), skipped))
        target = sorted(fresh, key=lambda t: math.hypot(t[0][0] - sx, t[0][1] - sz))[0]
    if target is not None:
        (tx, tz), tfy, tnm = target
        d0 = math.hypot(tx - sx, tz - sz)
        txt, err = M.t_plan_route(tx, tfy, tz, "on")
        mapside = [w for w in ("不在你脚下这块连通区域", "图上**真的不通**",
                               "这一柱子**没有已知地板**") if w in txt]
        dst = None
        import re as _re
        wps = [(int(a), int(b_), int(c)) for a, b_, c in
               _re.findall(r"^\s*\d+\)\s*\((-?\d+),(-?\d+),(-?\d+)\)", txt, _re.M)]
        if wps:
            dst = wps[-1]
        # ★★V5 改口径 ★ ✗（第 33 轮 ✓ 必须说清为什么改 ✓）：
        #   原判据是"规划到那一格不许被因**图上**原因拒绝"✗（当时 `max_up=1` ✓ 抬一级给规划 ✓）
        #   第 32 轮实测 ✓：★模组**爬不上去**★（停在 0.8~1.7 格外 ✗ 还把这当"到了"✗）
        #     ⇒ 第 33 轮把**执行用的规划**按模组真实能力算 ✓（`MOD_CLIMB_UP=0` ✓）
        #     ⇒ 那这种目标**现在就该被拒** ✗ —— 而且**必须拒得对**：说"要抬一级／爬不上去"✗
        #       不许说"隔着虚空"✗（那是另一回事 ✗ P116／P117 ✓）
        #   ⇒ 新口径 ✓：`MOD_CLIMB_UP==0` ⇒ **必须拒 ＋ 理由点到"抬一级"** ✓
        #               `MOD_CLIMB_UP>=1`（模组 v2.17 之后 ✓）⇒ 必须规划得出来 ✓
        named = ("抬一级" in txt) or ("爬不上去" in txt)
        # ⚠ "错怪虚空"要认**那句错话本身** ✗ 不许只认"隔着虚空"四个字 ✗
        #   （第 33 轮 ✓ 我自己栽的 ✓：修好的正文里就写着"★这与「隔着虚空」不是一回事★"✗
        #     ⇒ 判据认字 ⇒ **把对的判成错的** ✗ —— 与"认错字符串"同一族 ✓ 见 §52.7 ✓）
        wrong_why = ("中间隔着虚空" in txt) or ("走过去要跨虚空" in txt)
        # ★★第 40 轮补✗★：拒发的原因要**分清是哪一种**✗ ——
        #   · "抬一级/爬不上去"⇒ 那是**能力边界** ✓（`MOD_CLIMB_UP<1` 时**应该**拒 ✓ = v5 真 ✓）
        #   · "**目标不在连通区／隔着虚空**"⇒ ★那是**这个样本本身不可达**✗★ ⇒
        #     ★与"模组能不能抬一级"无关 ⇒ 这一条**测不了**✗★（★不是坏了✗★）
        #   实测（第 40 轮 ✓）：`MOD_CLIMB_UP=1` ⇒ 走了 else 分支 ⇒ 要求 `not err` ✗
        #     可工具拒发的理由是"**目标不在你脚下这块连通区域里 ⇒ 间隔着虚空 ⇒ 不去**" ✓
        #     ⇒ ★它拒得**对**✗★（那格真的隔着虚空 ✓）⇒ 判据却把它记成 FAIL ✗ ⇒ 假红 ✓
        unreachable_sample = ("不在你脚下" in txt) or ("隔绝" in txt) or ("不在连通区" in txt)
        v5_inc = False
        if M.MOD_CLIMB_UP < 1:
            v5 = bool(err) and named and (not wrong_why)
        elif err and unreachable_sample and (not named):
            v5 = None                       # ★测不了✗★（样本自己不可达 ⇒ 与能力无关 ✓）
            v5_inc = True
        else:
            v5 = (not err) and (not mapside) and bool(wps)
        say("V5 plan to the nearest class-C (step-up) cell %s (verdict y=%d, block=%s, %.1f "
            "away): err=%s | reason names the climb=%s | wrongly blames the void=%s | "
            "destination=%s | ★样本自己不可达✗=%s★ | MOD_CLIMB_UP=%d => %s"
            % ((tx, tz), tfy, tnm, d0, err, named, wrong_why, dst, unreachable_sample,
               M.MOD_CLIMB_UP, "测不了" if v5_inc else v5))
        if not v5_inc:
            ok &= bool(v5)
        for ln in txt.splitlines()[:3]:
            say("   %s" % ln.strip()[:190])
        # ★V6（真走）只在"模组真能上去"时才有意义 ✗（第 33 轮 ✓ 否则它必然走不到 ✓）：
        #   现在 `MOD_CLIMB_UP=0` ⇒ 规划已经拒了 ✗ ⇒ 这一半**如实说 INCONCLUSIVE**✗
        #     （不许拿"没走"当成"走了并到了"✓ 也不许当成失败 ✗）
        if M.MOD_CLIMB_UP >= 1 and v5 and dst is not None:
            wtxt, werr = M.t_walk_route(dst[0], dst[1], dst[2], 60000, 1)
            q = M._pos_now()
            # ★★判"到没到"要拿**计划自己的目的地**★ ✗（第 31 轮第三次尺子修正 ✓）：
            #   实测 ✓：我请求 `(4114,8)` ✓ 而规划把目的地挪到了 `(4115,71,8)`（内陆格 ✓）
            #     ⇒ 它走到 `(4115.93,8.13)` = **就在目的地那一格里** ✓ 说"到了"✓ **说得对** ✓
            #   而我拿**原来请求的那一格**去量 ⇒ 1.93 格 ⇒ 判它"假到"✗ ⇒ **又是我的尺子错** ✗
            goal = (dst[0], dst[2])
            real_goal = math.hypot(q[0] - goal[0], q[2] - goal[1]) if q else None
            real_req = math.hypot(q[0] - tx, q[2] - tz) if q else None
            said = ("到位 ✓" in wtxt) or ("**在目标格里 = True**" in wtxt)
            in_goal_cell = bool(q) and (int(math.floor(q[0])) == goal[0]) \
                and (int(math.floor(q[2])) == goal[1])
            explained = ("为什么没到" in wtxt) or ("为什么停" in wtxt)
            if said:
                v6 = (real_goal is not None) and (real_goal <= 1.6 or in_goal_cell)
            else:
                v6 = explained          # 没到 ⇒ 必须**说出原因** ✓（光一句"没到"不算完 ✗）
            say("V6 walk: tool said arrived=%s | why-line present=%s | goal (plan's own "
                "destination)=%s | independent read at (%.2f,%.2f) => %.2f from the goal "
                "(in goal cell=%s) / %.2f from the requested cell | err=%s => %s"
                % (said, explained, goal, q[0] if q else -1, q[2] if q else -1,
                   real_goal if real_goal is not None else -1, in_goal_cell,
                   real_req if real_req is not None else -1, werr, v6))
            if not said:
                for ln in wtxt.splitlines():
                    if "为什么没到" in ln or "为什么停" in ln or "还没到" in ln:
                        say("   %s" % ln.strip())
            ok &= bool(v6)
        else:
            say("V6 INCONCLUSIVE (not a pass): MOD_CLIMB_UP=%d and the plan was refused "
                "(or produced no destination) => there is nothing honest to walk"
                % M.MOD_CLIMB_UP)
            # ★★"测不了"要**自己说出来**✗★★（2026-09-30 第 40 轮 ✓ ⇒ P147/P149 ✓）
            #   ✗ 原来这里只印一行 "INCONCLUSIVE (not a pass)" ✗ 然后**收在 `=> FAIL`** ✗
            #     ⇒ ★总检把它算成"坏了"✗★ —— 而它输的其实是
            #       "**工具正确地拒绝了一个跨虚空的规划**✓ ⇒ 没有诚实的样本可走**✗**"
            #   ⇒ 口径 ✓：与 `route_view`／`r3_verify` **同一套** ✗ ——
            #     打 `=> INCONCLUSIVE` ✗ ＋ 退出码非 0 ✗ ⇒ 总检单列"★测不了"✗★ 一档 ✓
            v6_inc = True

    say("---- V1=%s V2=%s V3=%s V4=%s ----" % (v1, v2, v3, v4))
    # ★★第 40 轮：这里刚抓到一个**假绿**✗★★ ——
    #   ✗ 我第一版写成**两条互斥**的判断（"只有 v6_inc" / "只有 v5_inc"）✗
    #     ⇒ ★两条**同时**成立时，两个分支都不命中 ⇒ 直接掉到 `=> PASS`✗★
    #     ⇒ ★那是"测不了"被印成"通过"✗ = 本项目最恨的假绿✗★
    #   ⇒ 口径 ✓：**任一**为真 ⇒ 就是测不了 ✗（★布尔组合要连"都成立"一起想✗★）
    if ok and (locals().get("v5_inc") or locals().get("v6_inc")):
        say("=> INCONCLUSIVE: V1~V4 通过 ✓ 而 V5/V6 **没有诚实的样本可走**✗"
            "（★工具**正确地**拒发了 ✓ —— 那个「最近的台阶格」本身隔着虚空 ✗★）——"
            " ★测不了 ≠ 坏了✗★ 换个位置再测 ✓")
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
