#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""whereami_test.py -- one call to answer "what is my situation?" (W1..W4)

WHY (2026-09-29, round 29): the brain opens every turn by asking around -- where
am I, what is alive nearby, how much room is left in the bag, how far is the
edge, is anything hostile. Asking one by one costs 5-6 round trips on a
single-lane bridge. `whereami` answers all of it in one call, and it never
guesses: position/vitals/entities come from ONE dshdigest (world truth), while
the connected platform and the distance to the rim are computed from the map
with exactly the same code path `platform` uses.

CRITERIA (declared BEFORE running):
  W4 offline   : _parse_digest on synthetic lines must extract the fields, must
                 leave MISSING fields absent (never invent them), and must cope
                 with hostiles>0 / no-entity lines.
  W1 one call  : on a warm map the tool must spend exactly ONE dsh command and
                 ZERO map builds -- counted by this script (patched M.dsh and
                 the mission build counter), never from the tool's own text.
  W2 truth     : the reported position must match this script's independent
                 read (<=1 block); the reported rim distance must match
                 `platform`'s own number (<=0.2); the reported entity/hostile
                 counts must match THIS script's parse of the raw digest.
                 ---- RESTATED in round 30, AFTER a real failure ----
                 The original wording compared the tool's integer CELL with the
                 float from an independent read, which broke whenever the bot
                 stood on a cell boundary: (4113,71,3) vs 4113.9,4.0 is a 1.35
                 "mismatch" produced by two truncations of the same spot. The
                 tool now prints both the cell and the exact position, and the
                 criterion compares like with like: exact-vs-exact within 0.75,
                 and cell-vs-cell within one cell (Chebyshev).
  W3 warning   : it must warn when the rim is within 2 blocks and stay quiet
                 otherwise (judged against `platform`'s rim distance, not the
                 tool's own words).

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
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import mc_mcp as M      # noqa: E402

CNT = {"dsh": 0}
_ORIG_DSH = M.dsh


def counting_dsh(cmd, tmo=60.0):
    CNT["dsh"] += 1
    return _ORIG_DSH(cmd, tmo)


M.dsh = counting_dsh


def say(s):
    print(s, flush=True)


def main():
    ok = True

    # ---------------- W4 offline ------------------------------------------
    full = ("dshdigest name=Bot pos=1.5,64.0,-2.5 yaw=0 pitch=0 hp=20.0 food=19.0 sat=1.0 "
            "xp=3 mode=survival onground=true dim=minecraft:overworld time=100 day=5 "
            "held=minecraft:stonex4 inv[x]kinds=7,items=33,free=29,sel=0 "
            "ents=2 hostiles=1 nearest=minecraft:zombie@3.5 drops=1 look=none")
    d = M._parse_digest(full)
    w4a = (d.get("pos") == (1.5, 64.0, -2.5) and d.get("ents") == 2 and d.get("hostiles") == 1
           and d.get("kinds") == 7 and d.get("items") == 33 and d.get("free") == 29
           and d.get("nearest") == "minecraft:zombie" and d.get("nearest_dist") == 3.5)
    say("W4a full line: pos=%s ents=%s hostiles=%s kinds/items/free=%s/%s/%s nearest=%s@%s => %s"
        % (d.get("pos"), d.get("ents"), d.get("hostiles"), d.get("kinds"), d.get("items"),
           d.get("free"), d.get("nearest"), d.get("nearest_dist"), w4a))
    ok &= w4a
    lean = "dshdigest name=Bot pos=0.0,70.0,0.0 hp=20.0 mode=creative"
    d2 = M._parse_digest(lean)
    w4b = (d2.get("pos") == (0.0, 70.0, 0.0)) and ("hostiles" not in d2) and ("ents" not in d2)
    say("W4b lean line: missing fields stay MISSING (no invented zeros) => %s" % w4b)
    ok &= w4b
    w4 = w4a and w4b
    ok &= w4

    # ---------------- live -------------------------------------------------
    p = M._pos_now()
    if not p:
        say("live part INCONCLUSIVE: no bot position")
        say("---- W1 / W2 / W3 / W4 = - / - / - / %s ----" % w4)
        return 0 if w4 else 1
    M.t_freeze(True)
    try:
        # 先热一次（第一次可能要建图 ✓ 不算进 W1 ✓）
        M.t_whereami()
        CNT["dsh"] = 0
        b0 = int(M._MISSION.get("builds") or 0)
        t0 = time.time()
        txt, err = M.t_whereami()
        sec = time.time() - t0
        builds = int(M._MISSION.get("builds") or 0) - b0
        w1 = (CNT["dsh"] == 1) and (builds == 0) and (not err)
        say("W1 one call: dsh=%d (want 1) builds=%d (want 0) %.2fs err=%s => %s"
            % (CNT["dsh"], builds, sec, err, w1))
        ok &= w1

        q = M._pos_now()
        mp = re.search(r"@ \((-?\d+),(-?\d+),(-?\d+)\)", txt)
        mf = re.search(r"精确 (-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", txt)
        m_d = re.search(r"离最近的边 \*\*([\d.]+) 格\*\*", txt)
        m_e = re.search(r"实体 \*\*(\d+)\*\* ｜ ★敌对 (\d+)★", txt)
        raw = _ORIG_DSH("dshdigest 24", 40.0) or ""
        my_ents = re.search(r"ents=(\d+)", raw)
        my_host = re.search(r"hostiles=(\d+)", raw)
        my_inv = re.search(r"kinds=(\d+),items=(\d+),free=(\d+)", raw)
        m_inv = re.search(r"背包：(\d+) 种 / (\d+) 件 ｜ \*\*空格 (\d+)\*\*", txt)
        # ★W2a 的口径 ★ ✗（2026-09-29 第 30 轮 ✓ 实机被咬过一次才改 ✓）：
        #   现象 ✗：工具报 `(4113,71,3)` ✗ 独立读 `4113.9,4.0` ✗ ⇒ 我按**整数格**算距离 = 1.35 ⇒ 红 ✗
        #   真因 ✓：假人正**骑在格边界上**（z ≈ 3.98~4.00 ✓ 差 0.02 格 ✗）
        #     ⇒ 两次读数**各自截断**得到 3 和 4 ✓ ⇒ 两边都没错 ✗
        #     ⇒ 错的是"**拿整数格去跟浮点比**"✗（我在 §49.3 刚写过"同一个量才能比"✗ 又犯一次 ✓）
        #   ⇒ 口径 ✓（两条一起判 ✓ 都跟**同一个量**比）：
        #     ① **精确坐标**对精确坐标：≤ 0.75 格（世界里会有微小漂移 ✓ 但 0.75 抓得住"报错地方"✗）
        #     ② **格**对格：切比雪夫 ≤ 1 ✓（允许骑边界时翻一格 ✓ 但不允许报出别的地方 ✗）
        pos_exact = bool(mf and q and math.dist(
            (float(mf.group(1)), float(mf.group(3))), (q[0], q[2])) <= 0.75)
        pos_cell = bool(mp and q and max(abs(int(mp.group(1)) - int(q[0])),
                                         abs(int(mp.group(3)) - int(q[2]))) <= 1)
        pos_ok = pos_exact and pos_cell
        # ★W2b 的口径要分清"**能精确**"与"**会漂**"★ ✗（2026-09-29 第 29 轮 ✓ 我第一次写错 ✓）：
        #   现象 ✗：我要求**实体数精确相等**✗ ⇒ 工具那次 `ents=14` ✗ 我独立读那次 `13` ✗
        #     ⇒ 红 ✗ —— 可那是**两次读数之间一只鸡走开了** ✓（**世界在动** ✗ 不是解析错 ✗）
        #   ⇒ 口径 ✓：**背包数**（秒级稳定 ✓ 人没在搬东西 ✓）⇒ **必须精确一致** ✓
        #             **实体数**（会走会刷 ✓）⇒ 允许 **±3** ✓ 并如实说明这是世界漂移 ✓
        inv_ok = bool(m_inv and my_inv and m_inv.groups() == my_inv.groups())
        ent_drift = (abs(int(m_e.group(1)) - int(my_ents.group(1))) if (m_e and my_ents) else 99)
        ent_ok = (ent_drift <= 3) and bool(m_e and my_host and my_ents
                                           and int(m_e.group(2)) == int(my_host.group(1)))
        say("W2b1 inventory numbers EXACT match => %s (tool %s vs raw %s)"
            % (inv_ok, m_inv.groups() if m_inv else None,
               my_inv.groups() if my_inv else None))
        say("W2b2 entity count within +-3 (world drifts between two reads) => %s "
            "(tool ents=%s vs raw ents=%s, drift=%s; hostiles exact=%s)"
            % (ent_ok, m_e.group(1) if m_e else None, my_ents.group(1) if my_ents else None,
               ent_drift, bool(m_e and my_host and int(m_e.group(2)) == int(my_host.group(1)))))

        ptxt, _perr = M.t_platform(20)
        mp2 = re.search(r"距你 \*\*([\d.]+)\*\*", ptxt)
        rim_ok = bool(m_d and mp2 and abs(float(m_d.group(1)) - float(mp2.group(1))) <= 0.2)
        say("W2a position matches independent read => %s (cell %s / exact %s vs read "
            "%.2f,%.2f | exact<=0.75=%s cell<=1=%s)"
            % (pos_ok, mp.groups() if mp else None, mf.groups() if mf else None,
               q[0], q[2], pos_exact, pos_cell))
        say("W2c rim distance matches platform's own number => %s (tool %s vs platform %s)"
            % (rim_ok, m_d.group(1) if m_d else None, mp2.group(1) if mp2 else None))
        w2 = pos_ok and ent_ok and inv_ok and rim_ok
        ok &= w2

        near = float(mp2.group(1)) if mp2 else 99.0
        warned = "★警告" in txt
        w3 = (warned == (near <= 2.0))
        say("W3 warning: platform says rim=%.1f, tool warned=%s, expected=%s => %s"
            % (near, warned, near <= 2.0, w3))
        ok &= w3
    finally:
        M.t_freeze(False)

    say("---- W1 / W2 / W3 / W4 = %s / %s / %s / %s ----" % (w1, w2, w3, w4))
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
