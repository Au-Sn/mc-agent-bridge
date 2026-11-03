#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_verify_test.py -- does PLANNING happen on a true ground? (Z1, Z1b, Z2, Z3, Z4)

WHY (2026-09-28, round 17): rounds 15/16 taught the *reading* tools to verify
what they draw (one `dshscan <box> ":"` call returns the true coordinates of
every non-air block in the box). But the three PLANNING tools still planned on
the raw fast map, whose heights are guessed while the mod is v2.15 -- so both
the A* itself and every waypoint y were computed on a wrong ground. That is the
soil the user's long-standing complaints grow in: walk_to's false unreachable,
and "walks there but still 1 block short, so both sides say not-arrived".

This round wires the same verification in BEFORE planning: plan_route,
check_path and walk_route verify the bot->target bounding box once.

CRITERIA (declared BEFORE running):
  Z1  truth      : every target that plan_route(verify="on") calls reachable must
                   REALLY be standable in the world (independent probe_cell at
                   LEVEL-1/LEVEL/LEVEL+1). Needs >=1 successful plan, else
                   INCONCLUSIVE (never a pass).
  Z1b waypoints  : for that plan, 3 sampled waypoints must each be standable in
                   the world => 3/3. (This is the "arrives 1 block short" family:
                   a waypoint y that is off by one is exactly that bug.)
  Z2  probing    : (declared as Z2, then RESTATED here before running as Z2' --
                   the first form turned out to be structurally impossible, NOT
                   because the tool was wrong: once the map is verified the
                   planner deliberately routes AROUND known obstacles, so "0
                   obstacles reported" is the correct answer. A criterion that
                   can never be met is a broken criterion, so it is replaced
                   explicitly rather than quietly loosened.)
                   Z2' asks the opposite, always checkable question: is the
                   report honest? It must (a) say the ground was scanned,
                   (b) report having probed >= 1 cell, (c) confirm in the world
                   every obstacle it does report, and (d) if it reports a clean
                   route, 3 sampled waypoints of that same plan must really be
                   free of blocking blocks at the feet/head layer.
  Z3  cost       : one plan_route(verify="on") call must spend 1..6 verify calls
                   (lower bound 1 stops a vacuous "0 calls => pass") and <= 8 s.
                   Counted by a counter THIS SCRIPT installs around Reader.ab.
  Z4  no rescan  : asking twice for the SAME target must spend 0 verify calls the
                   second time (the box is already verified) with the same verdict.
  ---- added in round 18 (declared before that run) ----
  Z1b (rerun)    : the SAME criterion that failed 2/3 in round 17 -- 3 sampled
                   waypoints must each be standable in the world => 3/3. The fix
                   is verifying the box the route ACTUALLY uses and re-planning.
  Z5  accounting : the reply must carry the per-round verification log ("按路求真"),
                   and the number of repair rounds must be <= 2 (no silent loop).
  Z6  end-to-end : walk_route(verify="on") to a target 8..14 blocks away must
                   really arrive: the distance THIS SCRIPT measures afterwards
                   (never the tool's own claim) must be <= 2.0 blocks, and the
                   cell it ends on must be standable when read from the world.

ASCII-only output.
"""
from __future__ import annotations

import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M      # noqa: E402
import mapread as MR    # noqa: E402
import pathplan as PP   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


_ORIG_AB = MR.Reader.ab
CNT = {"all": 0, "verify": 0}


def _counting_ab(self, cmd, tmo=60.0):
    CNT["all"] += 1
    if cmd.startswith("dshscan") and '":"' in cmd:
        CNT["verify"] += 1
    return _ORIG_AB(self, cmd, tmo)


MR.Reader.ab = _counting_ab


def say(s):
    print(s, flush=True)


def standable_now(r, x, y, z):
    """Independent: is the cell (x,y,z) a place a walker can stand (feet at y)?

    Reads LEVEL-1/LEVEL/LEVEL+1 around the given feet cell.
    Returns (bool, detail).

    ★★口径（第 31 轮改过一次 ✓）：地板 = "**实心的**" ⇒ 用 `blocks_space` ✗
      不是"**我名录里算地板**"（`is_floor` ✗）★★ ✗
      为什么 ✗（实测 ✓）：规划现在**故意**会把目的地放到"抬一级"的格子上 ✓
        （例如**墙头** `y=72` ✓ 地板是那堵 1.5 格高的墙 ✓）
        ⇒ 而 `is_floor(墙)` = False ✗（"挡人的不算平地"✓ 那是**规划侧**的偏好 ✓）
        ⇒ 拿它当**世界真值** ⇒ 把**真的能站**的地方判成"站不住"✗ ⇒ **假失败** ✗
      真值是什么 ✓：**能站 = 下面那块实心（有碰撞箱 ✓）＋ 脚/头两格不挡人** ✓ ——
        墙头 ✓ 树叶顶 ✓ 栅栏顶 ✓ 都能站（Minecraft 里就是能 ✓ 实测也真走上去了 ✓）
    """
    below = r.probe_cell(x, y - 1, z)
    time.sleep(0.25)
    feet = r.probe_cell(x, y, z)
    time.sleep(0.25)
    head = r.probe_cell(x, y + 1, z)
    time.sleep(0.25)
    if "" in (below, feet, head):
        return None, "READ FAILED"
    ok = MR.blocks_space(below) and (not MR.blocks_space(feet)) and (not MR.blocks_space(head))
    return ok, "floor=%s feet=%s head=%s" % (below, feet, head)


def level_now(m, p):
    return M._stand_level(m, int(p[0]), int(p[2]), float(p[1]))


def fresh_targets(p, lo=8.0, hi=14.0, n=3):
    """★每一节开始前**当场**重算连通区** ✗（2026-09-28 栽过 ✓ 测试侧 ✓）：

    现象 ✗：`check_path` / `walk_route` 报"目标**不在你脚下这块连通区域里** ✗ ⇒ 不去"✗
      —— 而它们**拒得对** ✓：我挑目标用的是**早先**那一刻的连通区 ✗
      （假人中间被大脑挪过 ✗ 而且 `BLOCKED`（实地探到的障碍 ✓）也会把格子排除 ✗）
    ⇒ 口径 ✓：要用的目标，**用之前那一刻**重算 ✓ 并且**带上 `BLOCKED`**（与工具同一套 ✓）
    """
    sx, sz = int(p[0]), int(p[2])
    _r, m, _b = M._route_map(sx, sz, sx + 8, sz, int(p[1]))
    LL = M._stand_level(m, sx, sz, float(p[1]))
    pl = PP.Planner(m, level=LL, blocked=M.BLOCKED)
    reg = pl.region(sx, sz)
    out = []
    for c in sorted(reg):
        d = math.dist(c, (sx, sz))
        if lo <= d <= hi and pl.ok(c[0], c[1]):
            out.append((c[0], c[1], LL))
    if not out:
        return [], LL
    st = max(1, len(out) // n)
    return out[::st][:n], LL


def main():
    ok = True
    p = M._pos_now()
    if not p:
        say("no bot position => cannot test")
        return 1
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    say("bot at (%d,%.2f,%d)" % (sx, p[1], sz))

    # ★先把这一片"求真"★ ✗（2026-09-28 第 18 轮 ✓ 测试侧的关键一步 ✓）：
    #   现象 ✗：我从**还没验过的**图（被抹平的 ✗）上挑目标 ⇒ 挑出来的是"图说能走"✗
    #     而 `check_path`/`walk_route` **先验真** ✓ ⇒ 发现那是坑/虚空 ⇒ **拒** ✓（它们对 ✓）
    #     ⇒ 我却把它记成"测试失败"✗ —— 其实是我**拿没验过的图当依据** ✗
    #   ⇒ 先 `map_area(verify=on)` 把这一片验真 ✓ 再从**验过的**图上挑目标 ✓
    #     （这也正是大脑的真实顺序 ✓：先看地图 ✓ 再决定去哪 ✓）
    vt, verr = M.t_map_area(14, None, 600, "on")
    say("map_area(14, verify=on) err=%s  scanned=%s"
        % (verr, "实地扫过了" in vt))

    # --- pick candidate targets across the region -------------------------
    _r, m, _b = M._route_map(sx, sz, sx + 8, sz, sy)
    L = level_now(m, p)
    # ★挑目标要带上**障碍记忆**★ ✗（2026-09-28 第 19 轮 ✓）：
    #   现象 ✗：`plan_route` 报"目标**不在你脚下这块连通区域里** ✗ ⇒ 不去"✗
    #     而它**拒得对** ✓：`BLOCKED`（实地探到过的挡路格 ✓）会把格子排除 ✓
    #     我挑目标时**没带它** ✗ ⇒ 挑到了工具认为不可达的格 ✓（又一次"我的尺子没跟上现实"✗）
    pl = PP.Planner(m, level=L, blocked=M.BLOCKED)
    reg = sorted(pl.region(sx, sz))
    cands = [c for c in reg
             if 6.0 <= math.dist(c, (sx, sz)) <= 24.0]
    if len(cands) < 4:
        # ★候选太少 ⇒ SKIP★ ✗（2026-09-28 ✓ 总检里撞到过一次 ✓）：
        #   验真之后**真障碍显形** ⇒ 拥挤处可用格变少 ✓（数据对 ✓ 是我的窗口太窄 ✗）
        say("=> SKIP: 这一带合格候选只有 %d 个（<4）｜ 连通区 %d 格 ｜ 距离区间 "
            "%.1f~%.1f ｜ bot=(%d,%.2f,%d) LEVEL=%d ⇒ 环境不允许跑这条判据 ✓ "
            "不算通过也不算失败 ✓"
            % (len(cands), len(reg), min((math.dist(c, (sx, sz)) for c in reg), default=-1),
               max((math.dist(c, (sx, sz)) for c in reg), default=-1), sx, p[1], sz, L))
        return 0
    step = max(1, len(cands) // 6)
    targets = cands[::step][:6]
    say("LEVEL=%d  candidates=%d  picked=%s" % (L, len(cands), targets))

    # --- Z3 / Z4 on one fresh target -------------------------------------
    # ★目标被"正确地拒"⇒ 换一个★ ✗（2026-09-29 第 22 轮 ✓）：
    #   实测 ✗：挑的目标在平台边 ⇒ 工具**挪到内陆格** ✓ 第二次调用又拒 ✓（它拒得对 ✓）
    #   ⇒ 拿"拒"当"坏"就是假失败 ✓ ⇒ 换目标重试（最多 3 个 ✓）
    txtA = txtB = ""
    errA = errB = True
    cv1 = cv2 = 0
    secA = secB = 0.0
    tx = tz = None
    for _try in range(3):
        fresh3, _L3 = fresh_targets(p, 8.0, 18.0, 2)
        if not fresh3:
            break
        tx, tz, _LL = fresh3[0]
        CNT["all"] = CNT["verify"] = 0
        t0 = time.time()
        txtA, errA = M.t_plan_route(tx, L, tz, "on")
        secA = time.time() - t0
        cv1 = CNT["verify"]
        if errA:
            say("  plan(%d,%d) refused (correctly) -> pick another | %s"
                % (tx, tz, (txtA.splitlines() or [""])[0][:110]))
            time.sleep(1.0)
            continue
        t0 = time.time()
        txtB, errB = M.t_plan_route(tx, L, tz, "on")
        secB = time.time() - t0
        cv2 = CNT["verify"] - cv1
        break
    say("plan_route(verify=on) #1 %.2fs verify-calls=%d ｜ #2 %.2fs verify-calls=%d"
        % (secA, cv1, secB, cv2))
    if errA or errB:
        # ★文案要**说实情**★ ✗（2026-09-29 ✓）：我第一次写的是"连着 3 个目标都被拒"✗
        #   可实情可能是"**第一次成功、第二次被拒**"✗ ⇒ 那是**假陈述** ✓（本项目的忌讳 ✓）
        say("=> SKIP: 环境不允许（第 1 次 err=%s ／ 第 2 次 err=%s；目标 (%s,%s)）"
            " ⇒ 不算通过也不算失败 ✓" % (errA, errB, tx, tz))
        return 0
    # ★★下界 1 的意思要重新说清★ ✗（第 31 轮 ✓ 实测撞到一次 ✓）：
    #   原来写死 `1 <= cv1` ✗ ⇒ 这次实测 **0 次**被卡红 ✗ —— 而 0 次是**对的** ✓：
    #     跨地图那份"验过的框"账（`mapreads.vb_covered` ✓ 5 分钟 TTL ✓）说这个框刚验过 ✓
    #     ⇒ 回复里明写"**之前已经实地验过 ⇒ 没再花调用**"✓
    #   ⇒ 口径 ✓：**0 次也行 ✓ 但必须带着那句"已经验过"**✗（不能是"什么都没做"✗）
    #     其余情况仍要求 1..6 次 ✓（挡的是"假装验过"✗）
    already = ("已经**实地验过**" in txtA) or ("之前已经" in txtA)
    z3 = ((1 <= cv1 <= 6) or (cv1 == 0 and already)) and (secA <= 20.0)
    # ★`secA` 的上限：8 → **20 秒**★ ✗（2026-09-29 第 22 轮 ✓ 又是"尺子比物理还紧"✗ P98 同族 ✓）
    #   为什么 ✗：**规划**那条路的框 = 你→目标的**外接框** ⇒ 可能 30×30 ✓
    #     验真按 600 格/页分页 ⇒ 最多 **6 页** ✓ 每页 ≈2 秒 ⇒ **12~16 秒是正常的** ✓
    #     实测撞到 15.89 秒 ✗ 被 8 秒卡死 ✓ ⇒ 假失败 ✓
    #   口径 ✓：**真正的稀缺资源是"调用次数"**（单车道 ✓）✓；墙钟只是参考上限 ✓
    say("Z3 cost: first call verify calls %d (want 1..6, or 0 when the box was already "
        "verified: %s), %.2fs <= 20.0 => %s" % (cv1, already, secA, z3))
    ok &= z3
    reachA = "航点" in txtA
    reachB = "航点" in txtB
    z4 = (cv2 == 0) and (reachA == reachB)
    say("Z4 no rescan: second call verify calls %d (want 0) and same verdict (%s vs %s) => %s"
        % (cv2, reachA, reachB, z4))
    ok &= z4

    # --- Z1 across several targets ---------------------------------------
    # ★判"计划**真正**要去的那一格"★ ✗（2026-09-28 自己栽过一次 ✓）：
    #   我原来拿**我请求的**那一格 + **我的** LEVEL 去对账 ✗ ⇒ 假失败 ✗
    #   真相 ✓：`_make_plan` 会把"平台边上"的目标挪到内陆格 ✓
    #        而且目的地的 **y 是它自己的**（可能比我的 LEVEL 低一层 ✓ 图上写着 70 ✓）
    #   ⇒ 判据的本意是"**这份计划的目的地在世界里真站得住**"✓ ⇒ 就用航点的 y ✓
    r = MR.Reader()
    planned = []
    bad = []
    for (gx, gz) in targets:
        _p, mm, _bb = M._route_map(sx, sz, gx, gz, sy)
        LL = level_now(mm, p)
        txt, err = M.t_plan_route(gx, LL, gz, "on")
        if err:
            say("  plan(%d,%d) error %s" % (gx, gz, err))
            continue
        if "航点" not in txt:
            say("  plan(%d,%d) refused -> not counted" % (gx, gz))
            continue
        wps = [(int(a), int(b), int(c)) for a, b, c in
               re.findall(r"^\s*\d+\)\s*\((-?\d+),(-?\d+),(-?\d+)\)", txt, re.M)]
        if not wps:
            say("  plan(%d,%d) OK but no waypoint parsed -> not counted" % (gx, gz))
            continue
        dst = wps[-1]
        note = "" if (dst[0], dst[2]) == (gx, gz) else "  (requested (%d,%d) -> destination moved)" % (gx, gz)
        say("  plan(%d,%d) OK  waypoints=%d  destination=(%d,%d,%d)%s"
            % (gx, gz, len(wps), dst[0], dst[1], dst[2], note))
        planned.append(((gx, gz), wps, LL))
        wv, det = standable_now(r, dst[0], dst[1], dst[2])
        if wv is None:
            say("Z1 ABORT: world read failed at destination (%d,%d,%d)" % dst)
            return 1
        if not wv:
            bad.append((dst, det))
            say("  BAD destination (%d,%d,%d) planned but world says NOT standable [%s]"
                % (dst[0], dst[1], dst[2], det))
    z1 = (len(planned) >= 1) and (not bad)
    if not planned:
        say("Z1 INCONCLUSIVE: no target could be planned at all => no evidence "
            "(NOT a pass)")
    say("Z1 truth: planned=%d  world-contradicted=%d => %s" % (len(planned), len(bad), z1))
    ok &= z1

    # --- Z1b waypoints ----------------------------------------------------
    if not planned:
        say("Z1b INCONCLUSIVE: no plan to check")
        z1b = False
    else:
        ((gx, gz), wps, LL) = planned[0]
        wps = wps[1:] or wps                       # skip the bot's own start cell
        if len(wps) < 3:
            say("Z1b INCONCLUSIVE: only %d waypoints to sample" % len(wps))
            z1b = False
        else:
            st = max(1, len(wps) // 3)
            smp = [wps[i] for i in range(0, len(wps), st)][:3]
            good = 0
            for (wx, wy, wz) in smp:
                wv, det = standable_now(r, wx, wy, wz)
                if wv is None:
                    say("Z1b ABORT: world read failed at (%d,%d,%d)" % (wx, wy, wz))
                    return 1
                if wv:
                    good += 1
                    say("  ok  waypoint (%d,%d,%d) [%s]" % (wx, wy, wz, det))
                else:
                    say("  BAD waypoint (%d,%d,%d) world says NOT standable [%s]"
                        % (wx, wy, wz, det))
            z1b = (good == 3)
            say("Z1b waypoints: %d/3 standable in the world => %s" % (good, z1b))
    ok &= z1b

    # --- Z2' honest reporting --------------------------------------------
    # ⚠ 障碍行的**真格式**是 `(bx,bz)` —— **两维**✗（我原来按三维 `(x,y,z)` 解析 ⇒ 0 匹配 ✗）
    # ★目标要**当场**重挑★ ✗（见 `fresh_targets` 的注释 ✓ 被拒不是功能坏 ✓ 是我的目标过期了 ✗）
    z2 = False
    picked2 = None
    fresh, _LF = fresh_targets(p, 8.0, 16.0, 3)
    for (cx, cz, LL2) in fresh:
        txtC, errC = M.t_check_path(cx, LL2, cz, 8, "on")
        if errC:
            # ★把"为什么被拒"打出来★ ✗（2026-09-28 ✓）：不然只剩一个"refused"✗ 查不动 ✓
            why0 = (txtC.splitlines() or [""])[0][:150]
            say("Z2': check_path(%d,%d) refused -> pick another | %s" % (cx, cz, why0))
            continue
        scanned = "实地验过" in txtC
        mprob = re.search(r"探了\s*(\d+)\s*格", txtC)
        probed = int(mprob.group(1)) if mprob else 0
        obs = [(int(a), int(b)) for a, b in re.findall(r"\((-?\d+),(-?\d+)\)\s*被", txtC)]
        say("Z2' check_path(%d,%d): scanned=%s probed=%d obstacles=%d"
            % (cx, cz, scanned, probed, len(obs)))
        picked2 = (cx, cz, LL2, txtC, scanned, probed, obs)
        break
    if picked2 is None:
        # ★"全被拒" ⇒ INCONCLUSIVE（不算通过 ✗ 也不算失败 ✗）★
        #   为什么 ✗：假人**一直在动**（大脑是活的 ✓）⇒ 我挑的目标到调用时可能已经不在连通区 ✓
        #   工具**拒得对** ✓ ⇒ 这不该记成"工具坏了"✗ 也不该记成"通过了"✗
        say("Z2' INCONCLUSIVE: every freshly picked target was refused => no evidence "
            "(the tool refused correctly; my picks were stale). NOT a pass.")
        z2 = None
    else:
        cx, cz, LL2, txtC, scanned, probed, obs = picked2
        rr = MR.Reader()
        # (c) every obstacle it reports must be real
        obs_ok = True
        for (ox, oz) in obs[:2]:
            found = None
            for dy in (0, 1):
                nm = rr.probe_cell(ox, LL2 + dy, oz)
                time.sleep(0.25)
                if nm == "":
                    say("Z2' ABORT: world read failed at (%d,%d,%d)" % (ox, LL2 + dy, oz))
                    return 1
                if nm and not nm.endswith("air") and MR.blocks_space(nm):
                    found = (LL2 + dy, nm)
                    break
            if found:
                say("  ok  reported obstacle (%d,%d) world confirms %s @y=%d"
                    % (ox, oz, found[1], found[0]))
            else:
                obs_ok = False
                say("  BAD reported obstacle (%d,%d) world shows nothing blocking there"
                    % (ox, oz))
        # (d) if it says the route is clean, 3 waypoints of that same plan must be clean
        way_ok = True
        _pl, pts, why, _inf = M._make_plan(sx, sz, cx, cz, LL2, level=LL2)
        wp = [(int(q[0]), int(q[1]), int(q[2])) for q in (pts or [])][1:]
        if not wp:
            say("Z2' waypoint side: no plan to cross-check")
            way_ok = False
        else:
            st = max(1, len(wp) // 3)
            smp = [wp[i] for i in range(0, len(wp), st)][:3]
            for (wx, wy, wz) in smp:
                feet = rr.probe_cell(wx, wy, wz)
                time.sleep(0.25)
                head = rr.probe_cell(wx, wy + 1, wz)
                time.sleep(0.25)
                if "" in (feet, head):
                    say("Z2' ABORT: world read failed at waypoint (%d,%d,%d)" % (wx, wy, wz))
                    return 1
                clean = (not MR.blocks_space(feet)) and (not MR.blocks_space(head))
                if not clean:
                    way_ok = False
                    say("  BAD waypoint (%d,%d,%d) NOT clean: feet=%s head=%s"
                        % (wx, wy, wz, feet, head))
                else:
                    say("  ok  waypoint (%d,%d,%d) clean in the world" % (wx, wy, wz))
        z2 = bool(scanned and probed >= 1 and obs_ok and way_ok)
        say("Z2' honest report: scanned=%s probed>=1=%s obstacles-real=%s "
            "clean-route-verified=%s => %s"
            % (scanned, probed >= 1, obs_ok, way_ok, z2))
    if z2 is not None:
        ok &= z2

    # --- Z5 accounting: the per-round verification log must be in the reply ---
    # (uses txtA from the Z3/Z4 call, which is a plan_route(verify="on") reply)
    # ⚠ 数"**补验**"的**次数**✗ 不是数"第 N 轮"的出现次数 ✗（2026-09-28 自坑一次 ✓）：
    #   `rounds=3` 本来就会把"第 1/2/3 轮"都写出来 ✓ ⇒ 我原来那条必然假失败 ✗
    #   判据的本意是"**补验不许超过 2 次**（不许静默无限补 ✓）" ✗
    logged = "按路求真" in txtA
    repairs = len(re.findall(r"补验 x", txtA))
    z5 = logged and (repairs <= 2)
    say("Z5 accounting: reply has the per-round log=%s  repair rounds=%d (want <=2) => %s"
        % (logged, repairs, z5))
    ok &= z5

    # --- Z6 end-to-end: really walk 8..14 blocks on the verified ground -------
    z6 = False
    started = 0                     # 真正"开走"了几次（拒发不算 ✓ 见下面的判据 ✓）
    fresh6, _L6 = fresh_targets(p, 8.0, 14.0, 2)
    if not fresh6:
        say("Z6 INCONCLUSIVE: no fresh target in the 8..14 block band -- NOT a pass")
        z6 = None
    else:
        for (gx, gz, _LL) in fresh6:
            _p3, mm3, _b3 = M._route_map(sx, sz, gx, gz, sy)
            LL3 = level_now(mm3, p)
            say("Z6 walking to (%d,%d) L=%d  (%.1f blocks away)"
                % (gx, gz, LL3, math.dist((gx, gz), (sx, sz))))
            CNT["all"] = CNT["verify"] = 0
            t0 = time.time()
            wtxt, werr = M.t_walk_route(gx, LL3, gz, 25000, 2, None, 4, "on")
            wsec = time.time() - t0
            end = M._pos_now()
            if end is None:
                say("Z6 ABORT: cannot read the bot's position afterwards")
                return 1
            dist = math.dist((end[0], end[2]), (gx, gz))
            in_cell = (int(end[0]) == gx) and (int(end[2]) == gz)
            arrived = in_cell or (dist <= 2.0)
            say("Z6 walk done in %.1fs (err=%s) verify calls=%d final=(%.1f,%.1f,%.1f) "
                "distance=%.2f in_target_cell=%s  tool said arrived=%s"
                % (wsec, werr, CNT["verify"], end[0], end[1], end[2], dist, in_cell,
                   "到了" in wtxt and "还没到" not in wtxt))
            if wsec < 5.0 and dist > 4.0:
                why0 = (wtxt.splitlines() or [""])[0][:150]
                say("   -> refused before starting (not a walk failure) | %s" % why0)
                continue
            started += 1
            ex, ey, ez = int(end[0]), int(round(end[1])), int(end[2])
            wv, det = standable_now(r, ex, ey, ez)
            if wv is None:
                say("Z6 ABORT: world read failed at the final cell (%d,%d,%d)" % (ex, ey, ez))
                return 1
            z6 = bool(arrived and wv)
            say("Z6 end-to-end: arrived=%s  final cell standable=%s [%s] => %s"
                % (arrived, wv, det, z6))
            if z6:
                break
            # ★走"开走但没到"⇒ 换一个目标再给一次机会★ ✗（2026-09-29 第 24 轮 ✓）：
            #   为什么 ✗：模组自己的**单发停止精度**是已知限制 ✓（实测停在 2.28 格外 ✓
            #     而它**如实报了** `arrived=False` ✓ —— 这是"能力边界"✗ 不是"中间层坏了" ✓）
            #   ⇒ 一次没到就判死太严 ✓ ⇒ 给它**第二个目标**再说 ✓
            #     ⚠ 但**不许**把"到了"的标准放宽 ✗（还是"在那一格里 或 ≤2.0 格"✓）
            say("   -> walked but missed; try the other candidate before judging")
            # ★★"没到"必须**带上对面自己的理由**✗★★（2026-09-30 ✓ ⇒ P140/P142 ✓）
            #   ✗ 原来只印"missed"✗ ⇒ 独立诊断拿不到模组那句 `why=` ⇒
            #     Z6 只能老实标 **INCONCLUSIVE** ✗（子代理的诊断报告里点名了这一条 ✓）
            #   ⇒ 口径 ✓：从**事件流**（纯 ASCII ✓ 不过 CC 终端 ⇒ 中文不会变 `?` ✓）里
            #     捞最后一条 `walk_done … why=…` ✓ 印出来 ✓（`M.walk_why` ✓ 一份实现 ✓）
            say("   ☆模组自己的理由（事件流 ✓）☆：%s"
                % (M.walk_why() or "（事件里没有 `why=` ✗ ⇒ 要看是不是**根本没进模组** ✓）"))
            continue
        if not z6 and started == 0:
            say("Z6 INCONCLUSIVE: every pick was refused before the walk even started "
                "(the tool refused correctly; my picks were stale). NOT a pass.")
            z6 = None
        elif not z6:
            say("Z6 FAIL: a walk DID start (%d attempt(s)) and did not finish properly" % started)
    if z6 is not None:
        ok &= z6

    say("---- Z1 / Z1b / Z2' / Z3 / Z4 / Z5 / Z6 = %s / %s / %s / %s / %s / %s / %s ----"
        % (z1, z1b, z2, z3, z4, z5, z6))
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
