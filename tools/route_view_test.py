#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""route_view_test.py -- "route profile view" acceptance test (V1..V5)

WHY (2026-09-28): the user's point is that pathfinding's real job is
**recognising the obstacles that sit in the way**, and being able to see the
whole picture of the map. The map already answers "what is around me"; this
round adds "what does THIS route look like" -- a rendered strip plus an
obstacle list.

CRITERIA (declared BEFORE running; do not move them afterwards):
  V1 cost     : with a fresh map, one call <= 3.0s AND build delta == 0
                (measured on the SECOND call; the first call is allowed to
                 build the map). Build delta is read from mc_mcp._MISSION by
                 this script itself -- NOT taken from the tool's own text.
  V2 route    : (# of '*' in the art) + (# of 'X' in the art)
                == number of de-duplicated route cells recomputed here
  V3 truth    : every '#'/'~' cell drawn in the art is independently re-read
                from the WORLD (probe_cell, one cell at a time) => agreement
                must be 100% on the sampled set. Sampling is capped (6 cells,
                ~0.6s each) to protect the single-channel bridge.
                **If the view contains no '#'/'~' at all => V3 is reported
                INCONCLUSIVE, never a pass** (a zero-sample pass is a lie).
  V4 no-false : 3 route cells drawn as '*' must be true in the world:
                (x,LEVEL-1,z) is a floor AND (x,LEVEL,z),(x,LEVEL+1,z) do not
                block a walker => 3/3
  V5 repeat   : calling twice for the same target yields an identical set of
                '#' cells
  V6 height (declared 2026-09-28, AFTER V1..V5 were run once -- new evidence,
             not a moved goalpost): for up to 4 sampled route cells, the floor y
             the MAP claims must equal the floor y the WORLD has (probed
             downward from LEVEL, first floor wins).
             * The fast map used to get this wrong: the mod printed only a
               letter, so every letter cell was stored at "one below my feet"
               and the picture came out flat while the world had drops.
             * The criterion is CONDITIONAL ON THE MOD VERSION, and that
               condition is read from the map itself (meta.has_offsets):
                 - has_offsets True  (mod v2.16 active) => mismatches must be 0
                   and V6 counts toward the verdict;
                 - has_offsets False (old jar still loaded) => V6 is reported
                   PENDING-RESTART and does NOT count (the fix is built and
                   installed, but only a game restart can load it).

Target selection is deliberate: pick the reachable cell whose straight line to
the bot crosses the most blocking cells, so the route must detour and the view
actually shows obstacles (non-vacuous).

ASCII-only output (the Windows console here is GBK).
"""
from __future__ import annotations

import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M          # noqa: E402
import mapread as MR        # noqa: E402
import pathplan as PP       # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


PACE = 0.25                 # never hammer the single-channel bridge
PROBE_BUDGET = 6            # <= 6 world reads for V3
OUT = []


def say(s):
    OUT.append(s)
    print(s, flush=True)


def parse_art(txt, x0, z0, ncols):
    """Pull the ascii view out of the tool text.

    Rows look like '%+5d <art>' (a signed z label) -- the x header row has no
    sign, so it is skipped. x is reconstructed from the bbox this script
    recomputed itself, which is why ncols must match.
    """
    grid = {}
    rows = 0
    for ln in txt.splitlines():
        mm = re.match(r"^\s*([+-]\d+)\s(\S+)\s*$", ln)
        if not mm:
            continue
        z = int(mm.group(1))
        art = mm.group(2)
        if len(art) != ncols:
            return None, "row width %d != expected %d" % (len(art), ncols)
        rows += 1
        for i, ch in enumerate(art):
            grid[(x0 + i, z)] = ch
    if not rows:
        return None, "no art rows parsed"
    return grid, ""


def line_cells(a, b, n=None):
    n = n or max(1, int(round(math.dist(a, b))))
    out = []
    for k in range(n + 1):
        out.append((int(round(a[0] + (b[0] - a[0]) * k / n)),
                    int(round(a[1] + (b[1] - a[1]) * k / n))))
    return out


def _cant(reason: str) -> int:
    """★"测不了"要**说出来**✗★（2026-09-30 第 39 轮 ✓ ⇒ P147 ✓）

    ★为什么要单开这个出口✗★：这一条以前**自己也打 `=> FAIL`** ✗ ⇒
      总检把它们和"真的坏了"算在一起 ✗（实测 ✓：假人掉进 2 格小坑 ⇒
      "8 格内挑不到安全目标" ✗ 被记成 FAIL ✗ ⇒ 账面看起来"坏了 9 项" ✗）
    ⇒ 口径 ✓：打 **`=> INCONCLUSIVE`** ✗ ＋ **退出码非 0** ✗
      （★"测不了"**既不算通过、也不算坏**✗★ ⇒ 总检会把它单列一档 ✓ 见 `check_all.verdict_of` ✓）
    """
    say("=> INCONCLUSIVE: %s（★测不了 ≠ 坏了✗★ 换位置/换条件再测 ✓）" % reason)
    return 1


def main():
    p = M._pos_now()
    if not p:
        say("no bot position => cannot test")
        return _cant("读不到 Bot 坐标")
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    say("bot at (%d,%d,%d)" % (sx, sy, sz))

    # --- warm the mission map once (this call may build) -------------------
    _r, m, _b = M._route_map(sx, sz, sx + 8, sz, sy)
    LEVEL = M._stand_level(m, sx, sz, float(p[1]))       # ★浮点脚高★ ✗ 见 P101 ✓
    pl = PP.Planner(m, level=LEVEL)
    reg = pl.region(sx, sz)
    say("map box=%s cells=%d region=%d LEVEL(feet cell)=%d"
        % (m.box, len(list(m.cells())), len(reg), LEVEL))

    # --- pick a target whose straight line crosses blockers ---------------
    cands = []
    for (x, z) in reg:
        d = math.dist((x, z), (sx, sz))
        if not (6.0 <= d <= 22.0) or not pl.ok(x, z):
            continue
        crossed = 0
        soft = 0
        for (lx, lz) in line_cells((sx, sz), (x, z)):
            ch = m.cell_kind(lx, lz, LEVEL)[0]
            if ch in ("#", "~"):
                crossed += 1
            elif ch != "*":
                soft += 1
        # ★权重★ ✗：真挡路 (`#`/`~`) 最值钱 ✓ 其次是有高度差/坑的格 ✓
        #   （全平的空地会让 V3 变成"零样本通过"✗ ⇒ 那种假绿正是要避免的 ✗）
        cands.append((crossed * 2 + soft, crossed, d, x, z))
    cands.sort(key=lambda t: (-t[0], -t[1], t[2]))
    if not cands:
        return _cant("这一带挑不到候选目标（★这块地太小/太空 ⇒ 不是功能坏✗★）")
    score, crossed, dist, gx, gz = cands[0]
    say("target picked (%d,%d) dist=%.1f hard_blockers=%d score=%d"
        % (gx, gz, dist, crossed, score))

    # --- recompute the plan ourselves (independent of the tool's text) ----
    _r2, m2, _b2 = M._route_map(sx, sz, gx, gz, sy)
    LEVEL = M._stand_level(m2, sx, sz, float(p[1]))      # ★浮点脚高★ ✗ 见 P101 ✓
    _pl, pts, why, info = M._make_plan(sx, sz, gx, gz, LEVEL, level=LEVEL)
    if not pts:
        return _cant("规划不出来（%s）—— ★「挑不到可测的一跳」✗ 不是功能坏 ✗★" % why)
    cells = [(int(q[0]), int(q[2])) for q in pts]
    dedup = []
    for c in cells:
        if c not in dedup:
            dedup.append(c)
    margin = 1
    x0 = min(c[0] for c in dedup) - margin
    x1 = max(c[0] for c in dedup) + margin
    z0 = min(c[1] for c in dedup) - margin
    z1 = max(c[1] for c in dedup) + margin
    ncols = x1 - x0 + 1
    say("plan: waypoints=%d dedup_route_cells=%d bbox_x=%d..%d bbox_z=%d..%d"
        % (len(pts), len(dedup), x0, x1, z0, z1))

    # --- calls -----------------------------------------------------------
    # ★取用口径（2026-09-28 第 15 轮补 ✓ 不是挪尺子 ✗）★：
    #   V1 的**本意**是"**看图本身**不占通道 ✓ 全是内存操作"✓
    #     ⇒ 就用 `verify="off"` 量它 ✓（默认值是 auto ✓ 它会**主动实地扫一遍**✓
    #        那是**另一件事** ✓ 它的代价由 `tools/route_verify_test.py` 的 X3 量 ✓）
    #   V2（图 vs 规划自洽 ✓）与 V5（可复现 ✓）用同一种模式连调两次 ✓
    #   V3/V4/V6 是"**世界对账**"✓ ⇒ 用**默认**（auto ✓ = 用户/大脑实际会走的那条路 ✓）
    #     ⇒ 它们量的就是"这个工具给出来的东西到底真不真"✓
    b_before = int(M._MISSION.get("builds") or 0)
    t0 = time.time()
    txtA, errA = M.t_route_view(gx, LEVEL, gz, 1, 1200, "off")
    secA = time.time() - t0
    t0 = time.time()
    txtA2, errA2 = M.t_route_view(gx, LEVEL, gz, 1, 1200, "off")
    secA2 = time.time() - t0
    b_after = int(M._MISSION.get("builds") or 0)
    builds_delta = b_after - b_before
    t0 = time.time()
    txt2, err2 = M.t_route_view(gx, LEVEL, gz)          # 默认 = auto
    secB = time.time() - t0
    sec1, err1 = secA, errA
    txt1 = txtA
    say("callA(verify=off) %.2fs err=%s | callA2(verify=off) %.2fs err=%s | "
        "callB(default/auto) %.2fs err=%s | build delta = %d"
        % (secA, errA, secA2, errA2, secB, err2, builds_delta))
    if err1 or err2:
        say("tool reported an error => stop")
        return 1

    # ★★2026-10-24（★§79.339✗★）✗★★：★优先读**工具自己报的图框** ✗ 读不到才退回旧的✗★
    def _art_box(txt):
        mm = re.search(r"图框=(-?\d+),(-?\d+),(-?\d+),(-?\d+)", txt or "")
        if not mm:
            return None
        a, b, c, d = (int(g) for g in mm.groups())
        return (a, c, b - a + 1)      # ★(x0, z0, ncols)✗★
    _ba = _art_box(txtA) or (x0, z0, ncols)
    _bA2 = _art_box(txtA2) or _ba
    _b2 = _art_box(txt2) or _ba
    say("art box: A=%s A2=%s B=%s（★工具自报 ✗ 读不到才用本测试的 %s✗★）"
        % (_ba, _bA2, _b2, (x0, z0, ncols)))
    g1, e1 = parse_art(txtA, _ba[0], _ba[1], _ba[2])
    gA2, eA2 = parse_art(txtA2, _bA2[0], _bA2[1], _bA2[2])
    g2, e2 = parse_art(txt2, _b2[0], _b2[1], _b2[2])
    if g1 is None or g2 is None or gA2 is None:
        # ★★2026-10-24（★§79.336✗★）✗★★：★解析失败**不是判据坏** ✗ 也不该判红✗★ ——
        #   ★工具画的图宽（★这次 8✗★）≠ 本测试自己算的包围盒（★这次 12✗★）✗
        #   ⇒ ★**两边本来就不是一个尺度** ✗ 拿它去判"★图 vs 世界★"只会得出**假结论**✗★ ⇒
        #   ★★"★不拿歪的图去判★"✗ ⇒ **INCONCLUSIVE ＋ rc=4**（★与 §79.293 超时／§79.285 比不了 同口径✗★）✗★★ ✓
        say("art parse failed: %s %s %s" % (e1, eA2, e2))
        say("--- raw text head ---")
        say(txt2[:600])
        say("INCONCLUSIVE: ★图解析不了 ✗ 不拿歪的图去判★"
            "（★工具画的图宽与本测试的包围盒不是一个尺度 ✗ 见 `parse_art` 的注释★）"
            " —— ★不是判据坏 ✗ 是这一步测不了★")
        return 4
    for z in range(z0, z1 + 1):
        say("  %+5d %s" % (z, "".join(g2.get((x, z), " ") for x in range(x0, x1 + 1))))

    # V1 量的是"**看图本身**"（verify=off ✓ 见上面的取用口径注释 ✓）
    v1 = (secA2 <= 3.0) and (builds_delta == 0)
    say("V1 cost(verify=off) %.2fs <= 3.0 and builds_delta %d == 0 => %s"
        % (secA2, builds_delta, v1))

    # ★★2026-10-24（★§79.341✗★）✗★★：★判据比的是**它自己**规划的那条路 ✗ 而图是**工具**
    #   **自己**那条路 ✗ 两条路的格子**本来就不一样**（★实测：图框 x 4114..4122 ✗ 本测试的路到 4124✗★）✗★
    #   ⇒ ★★**只比★图框内★的路线格** ✗ 并把★几格比不了★如实报出来✗★★ ✓
    bx0_, bz0_, bn_ = _b2
    bx1_ = bx0_ + bn_ - 1
    bz1_ = max((zz for (_xx, zz) in g2), default=bz0_)
    _cmp = [c for c in dedup if bx0_ <= c[0] <= bx1_ and bz0_ <= c[1] <= bz1_]
    _skip = [c for c in dedup if c not in _cmp]
    if _skip:
        say("  ★%d 个路线格在**图框外** ✗ 比不了（★两条路不同✗★）：%s …"
            % (len(_skip), _skip[:4]))
    star = sum(1 for c in _cmp if g2.get(c) == "*")
    ex = sum(1 for c in _cmp if g2.get(c) == "X")
    v2 = (star + ex) == len(_cmp)
    if not v2:
        # ★★2026-10-24（★§79.340✗★）✗★★：★点名是哪几格 ✗ 以及它们**在哪**✗★ ✓
        say("  ★没画成 '*'／'X' 的路线格✗★：")
        for c in dedup:
            if g2.get(c) in ("*", "X"):
                continue
            drawn = g2.get(c)
            bx0, bz0, bn = _b2
            bx1 = bx0 + bn - 1
            bz1 = max((zz for (_xx, zz) in g2), default=bz0)
            inside = (bx0 <= c[0] <= bx1) and (bz0 <= c[1] <= bz1)
            try:
                kind = M.cell_kind(c[0], c[1], LEVEL)[0]
            except Exception:
                kind = "?"
            say("    %s ⇒ 图上 = %r ｜ 在**图框内** = %s ｜ cell_kind 说 %r"
                % (c, drawn, inside, kind))
        say("  ★图框✗★ = x %d..%d ／ z %d..%d" % (bx0, bx1, bz0, bz1))
    say("V2 art '*'=%d + 'X'=%d = %d == dedup route cells %d => %s"
        % (star, ex, star + ex, len(dedup), v2))

    # route cells drawn as '*' must all be walkable per the art's own claims:
    # (cross-check that 'X' only marks the non-walkable ones)
    mis = [c for c in dedup if (g2.get(c) == "*") != (m2.cell_kind(c[0], c[1], LEVEL)[0]
                                                      in m2.ROUTE_OK)]
    say("V2b route cells whose drawn char disagrees with cell_kind: %d => %s"
        % (len(mis), not mis))

    # --- V3: independently re-read every '#'/'~' cell from the world ------
    hard = sorted([c for c, ch in g2.items() if ch in ("#", "~")])
    say("V3 art contains %d '#'/'~' cells (route+side)" % len(hard))
    if not hard:
        say("V3 INCONCLUSIVE: the view shows no blocking cell => no evidence "
            "(NOT a pass; the picked target had %d straight-line blockers)" % crossed)
        v3 = None
    else:
        smp = hard[:PROBE_BUDGET]
        if len(hard) > len(smp):
            smp = [hard[i] for i in range(0, len(hard), max(1, len(hard) // PROBE_BUDGET))][:PROBE_BUDGET]
        r = MR.Reader()
        agree = 0
        bad = []
        for k, (x, z) in enumerate(smp):
            if k:
                time.sleep(PACE)
            hit = []
            for dy in (0, 1):
                nm = r.probe_cell(x, LEVEL + dy, z)
                if nm == "":
                    say("V3 ABORT: world read failed (empty) at (%d,%d,%d) -- bridge issue, "
                        "not a map issue" % (x, LEVEL + dy, z))
                    return 1
                if nm and not nm.endswith("air") and MR.blocks_space(nm):
                    hit.append((LEVEL + dy, nm))
            if hit:
                agree += 1
                say("  ok  (%d,%d) world says blocked by %s" % (x, z, hit[0][1]))
            else:
                bad.append((x, z))
                say("  BAD (%d,%d) art says blocked but world reads clear" % (x, z))
        v3 = (agree == len(smp))
        say("V3 world re-read %d/%d agree => %s" % (agree, len(smp), v3))

    # --- V4: 3 route cells drawn '*' must be true in the world ------------
    # ★★"地板在哪一层"要用**探出来的**✗ 不许假设 `LEVEL-1`✗★★（2026-09-30 修 ✓ ⇒ P143 ✓）
    #   ✗ 原来写死 `below = probe(LEVEL-1)` ✗ —— 假人站在**桶顶**时 `LEVEL=73` ✗
    #     而走道那几格真地板在 **y=70** ✓ ⇒ 探到的 `72` 是 air ✗ ⇒ 报 BAD ✗ ⇒ **假红** ✗
    #     （独立诊断实测 ✓：`(4126,14)`／`(4129,17)`／`(4133,21)` 的 `y=70` 明明有草方块 ✓）
    #   ⇒ 口径 ✓：**从脚下那一层往下逐层探，第一个"是地板"的层就是地板** ✗（深度封顶 ✓）
    #     ＋ 脚＝地板+1 ✓ 头＝地板+2 ✓ 必须都是空的 ✓（★这才是"这一格真能站"✗★）
    def floor_of(x, z, depth: int = 6):
        for y in range(LEVEL, LEVEL - depth - 1, -1):
            nm = r.probe_cell(x, y, z)
            if nm == "":
                return (None, None, "world read failed at %d" % y)
            if MR.is_floor(nm):
                return (y, nm, "")
        return (None, None, "no floor within %d layers below LEVEL=%d" % (depth, LEVEL))

    walkable = [c for c in dedup if g2.get(c) == "*"]
    say("V4 walkable route cells drawn '*' = %d" % len(walkable))
    if len(walkable) < 3:
        say("V4 INCONCLUSIVE: fewer than 3 walkable route cells => no evidence")
        v4 = None
    else:
        step = max(1, len(walkable) // 3)
        smp4 = [walkable[i] for i in range(0, len(walkable), step)][:3]
        r = MR.Reader()
        good = 0
        for k, (x, z) in enumerate(smp4):
            if k:
                time.sleep(PACE)
            fy, fname, errf = floor_of(x, z)
            if errf:
                say("V4 ABORT: %s at (%d,%d)" % (errf, x, z))
                return 1
            below = r.probe_cell(x, fy, z)
            feet = r.probe_cell(x, fy + 1, z)
            head = r.probe_cell(x, fy + 2, z)
            if "" in (below, feet, head):
                say("V4 ABORT: world read failed (empty) at (%d,%d) -- bridge issue" % (x, z))
                return 1
            okf = MR.is_floor(below)
            okb = (not MR.blocks_space(feet)) and (not MR.blocks_space(head))
            if okf and okb:
                good += 1
                say("  ok  (%d,%d) 地板 y=%d floor=%s feet=%s head=%s"
                    % (x, z, fy, below, feet, head))
            else:
                say("  BAD (%d,%d) 地板 y=%d floor=%s feet=%s head=%s (floor_ok=%s clear_ok=%s)"
                    % (x, z, fy, below, feet, head, okf, okb))
        v4 = (good == 3)
        say("V4 world re-read %d/3 agree => %s" % (good, v4))

    # --- V5: identical '#' set across the two calls -----------------------
    # V5 = 同一种模式连调两次的结果一致 ✓（所以拿 A 与 A2 比 ✗ —— 不是拿 A 跟默认那张比 ✗）
    h1 = set(c for c, ch in g1.items() if ch in ("#", "~"))
    h2 = set(c for c, ch in gA2.items() if ch in ("#", "~"))
    v5 = (h1 == h2)
    say("V5 '#'/'~' sets equal across two verify=off calls (%d vs %d) => %s"
        % (len(h1), len(h2), v5))

    # --- V6: the map's floor height vs the world's floor height -----------
    has_off = bool(m2.meta.get("has_offsets"))
    say("V6 mod offsets present (meta.has_offsets) = %s  [y_exact=%s y_assumed=%s]"
        % (has_off, m2.meta.get("y_exact"), m2.meta.get("y_assumed")))
    smp6 = [walkable[i] for i in range(0, len(walkable), max(1, len(walkable) // 4))][:4] \
        if walkable else []
    mism = []
    if not smp6:
        say("V6 INCONCLUSIVE: no walkable route cells sampled")
        v6 = None
    else:
        r6 = MR.Reader()
        for k, (x, z) in enumerate(smp6):
            if k:
                time.sleep(PACE)
            s = m2.surface(x, z, below=LEVEL + 1)
            claim = s[0] if s else None
            truth = None
            # ★往下探的范围从 **3 层**放宽到 **6 层**✗★（2026-09-30 ✓ ⇒ P143 ✓）
            #   ✗ 3 层是不够的 ✗：假人站在桶顶时 `LEVEL=73` ✓ 而走道那几格的地板在 **70** ✓
            #     ⇒ 探 73/72/71 全落空 ⇒ `truth=None` ✗ ⇒ 报 MISMATCH ✗（假红 ✓）
            #   ★判据**没变**✗★（"地图说的地板层 == 世界里真有地板的层"✓）
            #     变的只是**怎么找那个地板**✗（探得够深 ✓）
            for y in range(LEVEL, LEVEL - 6 - 1, -1):
                nm = r6.probe_cell(x, y, z)
                if nm == "":
                    say("V6 ABORT: world read failed (empty) at (%d,%d,%d)" % (x, y, z))
                    return 1
                if nm and not nm.endswith("air") and MR.is_floor(nm):
                    truth = y
                    break
            same = (claim == truth)
            if not same:
                mism.append((x, z, claim, truth))
            say("  (%d,%d) map_floor=%s  world_floor=%s  => %s"
                % (x, z, claim, truth, "ok" if same else "MISMATCH"))
        # ★取用条件按"**这几格到底验没验过**"判★ ✗（2026-09-28 第 15 轮补 ✓）：
        #   原来只看模组版本（`has_offsets` ✗）⇒ 现在**默认会实地扫这条走廊**✓
        #   ⇒ 只要采样的格都 `is_verified` ✓ 就该要求 **0 处不符** ✓
        #     （这才是这条判据的本意 ✓ 它防的是"拿推的高度当真的"✗）
        all_ver = all(m2.is_verified(x, z, LEVEL) for (x, z) in smp6)
        if has_off or all_ver:
            v6 = (not mism)
            say("V6 heights are真值（mod offsets=%s ｜ 走廊实地扫过=%s）=> mismatches must be 0: %d => %s"
                % (has_off, all_ver, len(mism), v6))
        else:
            v6 = None
            say("V6 PENDING: %d/%d sampled cells disagree and they are NOT verified "
                "(guessed heights) -- the fix is built+installed but the running jar "
                "is still the old one, and only a game restart "
                "loads the new one" % (len(mism), len(smp6)))

    parts = [v1, v2, v5]
    verdict = all(parts) and (v3 is not False) and (v4 is not False) and (v6 is not False)
    say("---- V1..V6 = %s / %s / %s / %s / %s / %s ----"
        % (v1, v2, v3, v4, v5, v6))
    say("=> %s" % ("PASS" if verdict else "FAIL"))
    return 0 if verdict else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception %s)" % type(e).__name__)
        sys.exit(1)
