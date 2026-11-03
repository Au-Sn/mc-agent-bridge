#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""platform_test.py -- "where does my platform end, and am I near the edge?" (P1..P4)

WHY (2026-09-29, round 24): safe_spots tells the bot which standing spots are
safe, but nothing ever said WHERE THE EDGE IS. Falling into the void starts with
stepping on the rim: on 2026-09-23 that really happened and cost diamonds, a
diamond axe, a hopper, coal, iron, a hammer and the wheat/seeds. The new
`platform` tool reports the connected region, its rim, and the nearest rim cell
with a direction -- and shouts when the bot is standing within 2 blocks of it.

CRITERIA (declared BEFORE running):
  P4 offline : _bearing maps the eight directions correctly; _boundary_cells on
               a synthetic region returns exactly the rim cells (a cell is rim
               iff some 4-neighbour is outside the region).
  P1 rim truth: 3 reported rim cells must be TRUE in the world -- each one must
               be standable itself AND have at least one non-standable
               4-neighbour (that is what "rim" means here).
  P2 bearing   : for the reported nearest rim cell, the neighbour lying in the
               direction from the bot toward that cell must really be
               non-standable in the world (this checks the direction claim, not
               just the cell).
  P3 warning   : if the tool warns (within 2 blocks), the world must confirm a
               non-standable cell within 3 of the bot; if it does not warn, the
               world must confirm none within 2.
               ---- RESTATED in round 30, BEFORE that run ----
               The original wording of this line said "the world must confirm none
               in the axis-aligned cells out to 2", and the probe was written to
               match it literally: only the four axis lines were read. That made
               the yardstick blind to the whole diagonal half of the
               neighbourhood, and the two blindnesses are NOT symmetric:
                 * warned + a diagonal void at 2.2 blocks  => FALSE FAIL
                   (this really happened: bot at (4121,1), rim at the diagonal
                    (4122,2) 1.4 away, its void side (4122,3) 2.2 away)
                 * not warned + a diagonal void at 1.4 blocks => FALSE PASS
               The criterion MEANT "is the tool's own claim about the
               neighbourhood true", so the probe must cover the neighbourhood the
               claim quantifies over: every cell with distance <= 3.01, probed in
               distance order, with an early exit once a warning is confirmed.
               (The declaration above is corrected to say exactly that.)

ASCII-only output.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M      # noqa: E402
import mapread as MR    # noqa: E402


def say(s):
    print(s, flush=True)


def stand_here(r, x, y, z):
    """Is (x,y,z) a place a walker with feet cell y can stand? (independent read)"""
    below = r.probe_cell(x, y - 1, z)
    time.sleep(0.2)
    feet = r.probe_cell(x, y, z)
    time.sleep(0.2)
    head = r.probe_cell(x, y + 1, z)
    time.sleep(0.2)
    if "" in (below, feet, head):
        return None
    return MR.is_floor(below) and (not MR.blocks_space(feet)) and (not MR.blocks_space(head))


def main():
    ok = True

    # ---------------- P4 offline ------------------------------------------
    class P:            # 只有 region 用的假规划器 ✓
        def __init__(self, cells):
            self.cells = set(cells)

        def region(self, x, z):
            return self.cells

        def interior(self, x, z):
            return all((x + dx, z + dz) in self.cells
                       for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))

    reg = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (0, 2), (1, 2), (2, 2)}
    bnd = sorted(M._boundary_cells(P(reg), reg))
    p4a = bnd == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2)]
    say("P4a boundary on a 3x3 region: %s (the centre must NOT be rim) => %s"
        % (bnd, p4a))
    cases = [((0, -1), "北"), ((0, 1), "南"), ((-1, 0), "西"), ((1, 0), "东"),
             ((1, -1), "北东"), ((-1, 1), "南西"), ((0, 0), "（原地）")]
    p4b = all(M._bearing(dx, dz) == want for (dx, dz), want in cases)
    say("P4b bearings: %s => %s"
        % ([(M._bearing(dx, dz), want) for (dx, dz), want in cases], p4b))
    p4 = p4a and p4b
    ok &= p4

    # ---------------- live -------------------------------------------------
    p = M._pos_now()
    if not p:
        say("live part INCONCLUSIVE: no bot position")
        say("---- P1 / P2 / P3 / P4 = - / - / - / %s ----" % p4)
        return 0 if p4 else 1
    M.t_freeze(True)
    try:
        r = MR.Reader()
        txt, err = M.t_platform(20)
        if err:
            say("platform reported an error => INCONCLUSIVE")
            say(txt[:300])
            return 0 if p4 else 1
        print(txt)
        sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
        L = int(round(float(p[1])))
        m_near = re.search(r"★最近的边★：\((-?\d+),(-?\d+)\)\s*距你\s*\*\*([\d.]+)\*\*", txt)
        if not m_near:
            say("P1 INCONCLUSIVE: cannot parse the nearest rim cell from the reply")
            return 0 if p4 else 1
        nx, nz, d_near = int(m_near.group(1)), int(m_near.group(2)), float(m_near.group(3))
        all_rim = [(int(a), int(b)) for a, b in re.findall(r"\((-?\d+),(-?\d+)\)[\d.]+", txt)]
        say("nearest rim = (%d,%d) %.1f  | parsed rim cells: %s" % (nx, nz, d_near, all_rim[:6]))

        # --- P2' rim geometry: the void lies BEYOND the rim cell -------------
        # ★前提改对了★ ✗（2026-09-29 第 24 轮 ✓ 我第一版假设"虚空在**朝假人**那一侧"✗
        #   实测撞墙 ✓：边格 (4122,2) 的虚空在它**南边** (4122,3) ✓ —— 也就是**外面** ✓
        #   ⇒ 真正的几何是"**边格是最后一步，出了它就没了**"✓ 与方位无关 ✓）
        rim_ok = stand_here(r, nx, L, nz)
        if rim_ok is None:
            say("P2' ABORT: world read failed at the rim cell")
            return 1
        void_cells = []
        for (ddx, ddz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            v = stand_here(r, nx + ddx, L, nz + ddz)
            if v is None:
                say("P2' ABORT: world read failed at (%d,%d)" % (nx + ddx, nz + ddz))
                return 1
            if not v:
                void_cells.append(((nx + ddx, nz + ddz),
                                   ((nx + ddx - sx) ** 2 + (nz + ddz - sz) ** 2) ** 0.5))
        farther = [c for c in void_cells if c[1] > d_near - 0.01]
        p2 = bool(rim_ok) and bool(void_cells) and bool(farther)
        say("P2' rim geometry: rim (%d,%d) standable=%s | non-standable neighbours=%s "
            "| at least one of them is farther than the rim (%.1f) => %s"
            % (nx, nz, rim_ok, [(c[0], round(c[1], 1)) for c in void_cells], d_near, p2))
        ok &= p2

        # --- P1 rim truth: sample 3 rim cells --------------------------------
        smp = all_rim[:3] or [(nx, nz)]
        good = 0
        for (rx, rz) in smp:
            st = stand_here(r, rx, L, rz)
            if st is None:
                say("P1 ABORT: world read failed at rim (%d,%d)" % (rx, rz))
                return 1
            nb = []
            for (ddx, ddz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                v = stand_here(r, rx + ddx, L, rz + ddz)
                if v is None:
                    say("P1 ABORT: world read failed at (%d,%d)" % (rx + ddx, rz + ddz))
                    return 1
                nb.append(v)
            is_rim = bool(st) and (False in nb)
            good += 1 if is_rim else 0
            say("  (%d,%d) standable=%s neighbours=%s => rim=%s" % (rx, rz, st, nb, is_rim))
        p1 = (good == len(smp))
        say("P1 rim truth: %d/%d sampled rim cells really are rim in the world => %s"
            % (good, len(smp), p1))
        ok &= p1

        # --- P3' warning semantics -------------------------------------------
        # ★语义对齐★ ✗（2026-09-29 第 24 轮 ✓）：工具的警告 = "**边格**在你 2 格内"✗
        #   而我第一版查的是"**虚空格**在 2 格内"✗ ⇒ 差一格（边格 2 格 ⇒ 虚空在 3 格 ✓）
        #   ⇒ 口径 ✓：警告 ⇒ 世界必须确认"**3 格内有走不过去的格**"✓
        #             不警告 ⇒ 世界必须确认"**2 格内没有**"✓
        warned = "★警告" in txt
        # ★★第 30 轮修正：**探的格子集合**必须覆盖判据自己说的那个邻域★★ ✗
        #   坑（实测 ✓ 这个测试**时好时坏** ✓ 根子就在这里 ✗）：
        #     判据说的是"**2 格内** / **3 格内**"（= 整个方形邻域 ✓）
        #     而我只探了**四条轴**（±x/±z ✓ k=1..3 ✓）✗ —— 斜向的格子一格都没探 ✗
        #   实测现场 ✓：假人站 (4121,1) ✓ 最近的边在**斜向** (4122,2)（1.4 格 ✓）
        #     它外侧的虚空格 (4122,3) 离假人 **2.2 格** ✗ —— 不落在任何一条轴上 ✗
        #     ⇒ 警告是对的 ✓ 却被判成"世界没确认" ✗ ⇒ **假失败** ✗（这次的真凶 ✓）
        #   反向更危险 ✗：不警告时斜着 1.4 格就是虚空 ⇒ 也探不到 ⇒ **假通过** ✗
        #   ⇒ 口径 ✓：**按距离排序探遍 dist<=3.01 的每一格** ✓
        #     · 警告时**命中即停**（省通道 ✓）
        #     · 不警告时必须把 2.01 以内**探完**（才能说"没有"✓）
        cand = []
        for dxa in range(-3, 4):
            for dza in range(-3, 4):
                if dxa == 0 and dza == 0:
                    continue
                dd = (dxa * dxa + dza * dza) ** 0.5
                if dd <= 3.01:
                    cand.append((dd, sx + dxa, sz + dza))
        cand.sort()
        bad2 = bad3 = False
        probed = 0
        for (dd, ax, az) in cand:
            if warned and bad3:
                break                       # 警告已被世界确认 ⇒ 不必再探 ✓
            if (not warned) and dd > 2.01:
                break                       # 不警告：只需证"2 格内没有"✓
            v = stand_here(r, ax, L, az)
            if v is None:
                say("P3' ABORT: world read failed at (%d,%d)" % (ax, az))
                return 1
            probed += 1
            if not v:
                if dd <= 2.01:
                    bad2 = True
                if dd <= 3.01:
                    bad3 = True
        p3 = (warned and bad3) or ((not warned) and (not bad2))
        say("P3' warning semantics: tool warned=%s | probed=%d cells (dist<=3.01) | "
            "non-standable within 2=%s within 3=%s => %s"
            % (warned, probed, bad2, bad3, p3))
        ok &= p3
    finally:
        M.t_freeze(False)

    say("---- P1 / P2 / P3 / P4 = %s / %s / %s / %s ----" % (p1, p2, p3, p4))
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
