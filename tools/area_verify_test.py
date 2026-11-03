#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""area_verify_test.py -- do the MAP-READING tools tell the truth too? (Y1..Y5)

WHY (2026-09-28, round 16): round 15 taught `route_view` to verify the corridor
it draws (one `dshscan <box> ":"` call returns the true coordinates of every
non-air block). But the two tools the brain is told to consult BEFORE deciding
anything -- `map_area` and `survey` -- still drew the raw fast map, whose
heights are GUESSED while the mod is still v2.15 (a letter cell is stored at
"one below my feet"). So the picture the agent reasons from was flat and blind
to anything standing at its own level.

This round wires the same verification into both, with the clearing band set to
the mod's own surface-search range (level-6 .. level+2) so that "clear the old
values" can never destroy truth that lives outside the band.

CRITERIA (declared BEFORE running):
  Y1 truth agree : after map_area(radius=12, verify="on"), sample 4 cells the map
                   calls standable and decide walkable/not-walkable INDEPENDENTLY
                   from the world (probe_cell) => 4/4.
  Y2 relief seen : the corrected map must contain at least one non-flat verdict
                   ('^' 'v' '#' '~' '.' '+') somewhere in the drawn area. If the
                   area is genuinely all-flat => INCONCLUSIVE (never a pass).
  Y3 cost        : the tool's verify calls must be 1..10 and the whole call
                   <= 12 s. Calls counted by a counter THIS SCRIPT installs
                   around mapread.Reader.ab (never from the tool's own text);
                   the lower bound of 1 prevents a vacuous "0 calls => pass".
  Y4 really fixed: the classification of the drawn cells must DIFFER before vs
                   after (>=1 cell). Zero difference means the scan bought
                   nothing. "Before" is snapshotted from a freshly built fast
                   map; "after" is read back from the CACHE, which also proves
                   the corrected map was written back (so later planning
                   inherits it).
  Y5 provenance  : the tool text must state that this area's ground was scanned.

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
# importing this test module is safe (main is guarded); it gives us the
# independent world verdict helper so both tests judge the world identically.
import route_verify_test as RV    # noqa: E402

# ---- independent channel-call counter (installed around Reader.ab) --------
_ORIG_AB = MR.Reader.ab
CNT = {"all": 0, "verify": 0}


def _counting_ab(self, cmd, tmo=60.0):
    CNT["all"] += 1
    if cmd.startswith("dshscan") and '":"' in cmd:
        CNT["verify"] += 1
    return _ORIG_AB(self, cmd, tmo)


MR.Reader.ab = _counting_ab          # ★必须真的装上★ ✗（round 15 差点忘 ✓）


def say(s):
    print(s, flush=True)


def tally(m, level):
    """Count cell_kind verdicts over the whole map."""
    t = {}
    for (x, z) in m.cells():
        ch = m.cell_kind(x, z, level)[0]
        t[ch] = t.get(ch, 0) + 1
    return t


def main():
    ok = True
    RAD = 12
    p = M._pos_now()
    if not p:
        say("no bot position => cannot test")
        return 1
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    # ★脚占的那一格 = round(脚高)★ ✗（**不是** int ✓ 见错题本 P101 ✓）
    #   `t_map_area` 内部也是这么算的 ✓（`below = int(round(p[1]))` ✓）⇒ 同一把尺子 ✓
    LEVEL = int(round(float(p[1])))
    say("bot at (%d,%.2f,%d)  LEVEL(feet cell) = %d" % (sx, p[1], sz, LEVEL))

    # --- "before": build a fresh fast map (no verification) ----------------
    r = MR.Reader()
    m0 = r.build_dshmap(radius=RAD, max_age=600.0)
    if m0 is None:
        say("fast map unavailable => cannot test")
        return 1
    box = m0.box
    cells = list(m0.cells())
    step = max(1, len(cells) // 60)
    sample = cells[::step][:60]
    before = {c: m0.cell_kind(c[0], c[1], LEVEL)[0] for c in sample}
    t0 = tally(m0, LEVEL)
    say("before: box=%s cells=%d  verdicts=%s  (has_offsets=%s)"
        % (box, len(cells), t0, m0.meta.get("has_offsets")))

    # --- the call under test ---------------------------------------------
    CNT["all"] = CNT["verify"] = 0
    ts = time.time()
    txt, err = M.t_map_area(RAD, LEVEL, 600, "on")
    sec = time.time() - ts
    print_done = CNT["verify"]
    say("map_area(radius=%d, verify=on): %.2fs err=%s  channel calls=%d (scan-truth=%d)"
        % (RAD, sec, err, CNT["all"], print_done))
    if err:
        say("tool reported an error => stop")
        say(txt[:400])
        return 1

    # --- "after": read the corrected map back from the CACHE --------------
    r2 = MR.Reader()
    m1 = r2.get(box, max_age=600.0)
    if m1 is None:
        say("Y4 FAIL: corrected map not found in the cache (was it saved?)")
        return 1
    after = {c: m1.cell_kind(c[0], c[1], LEVEL)[0] for c in sample}
    changed = [c for c in sample if before[c] != after[c]]
    t1 = tally(m1, LEVEL)
    say("after : verdicts=%s  verified_boxes=%d  verified_cells=%s"
        % (t1, len(m1.meta.get("verified_boxes") or []), m1.meta.get("verified_cells")))

    # --- Y3 cost ----------------------------------------------------------
    y3 = (1 <= print_done <= 10) and (sec <= 12.0)
    say("Y3 cost: verify calls %d (want 1..10) and total %.2fs <= 12.0 => %s"
        % (print_done, sec, y3))
    ok &= y3

    # --- Y4 really fixed --------------------------------------------------
    # ★口径要跟着"模组有没有真高度"走★ ✗（2026-09-29 第 24 轮 ✓ 重启后栽过一次 ✓）：
    #   现象 ✗：Y4 判"结论必须**有变化**"✗ 而新模组（v2.16 ✓）**自带真高度** ✓
    #     ⇒ 图**本来就没被抹平** ✓ ⇒ 没什么可改 ✓ ⇒ changed=0 ✗ ⇒ **假失败** ✓
    #   ⇒ 口径 ✓（与 `route_verify` 的 V6 同一条 ✓）：
    #     · 图是**推的**（没 offsets ✓）⇒ 必须**确实改掉了东西** ✓（changed ≥ 1 ✓）
    #     · 图是**真的**（有 offsets ✓）⇒ **不改才是对的** ✓（changed=0 也算过 ✓）
    has_off = bool(m1.meta.get("has_offsets"))
    y4 = (len(changed) >= 1) or has_off
    say("Y4 really fixed: %d/%d sampled cells changed verdict %s | mod offsets=%s "
        "cache carries the correction=%s => %s"
        % (len(changed), len(sample),
           [(c, before[c], after[c]) for c in changed[:4]], has_off,
           bool(m1.meta.get("verified_boxes")), y4))
    ok &= y4

    # --- Y5 provenance ----------------------------------------------------
    y5 = ("实地扫过" in txt) or ("实地扫过了" in txt)
    say("Y5 provenance: text says the ground was scanned => %s" % y5)
    ok &= y5

    # --- Y2 relief seen ---------------------------------------------------
    weird = sum(t1.get(ch, 0) for ch in ("^", "v", "#", "~", ".", "+"))
    y2 = weird >= 1
    if not y2:
        say("Y2 INCONCLUSIVE: the corrected map is entirely flat (%s) -- either this "
            "patch of island really is flat, or verification did nothing. NOT a pass."
            % t1)
    else:
        say("Y2 relief seen: %d non-flat cells (of %d) => %s"
            % (weird, sum(t1.values()), y2))
    ok &= y2

    # --- Y1 truth agree ---------------------------------------------------
    walk = [c for c in cells if m1.standable(c[0], c[1], LEVEL)]
    say("Y1 map-walkable cells = %d" % len(walk))
    if len(walk) < 3:
        say("Y1 INCONCLUSIVE: fewer than 3 standable cells => no evidence (NOT a pass)")
        y1 = False
    else:
        st = max(1, len(walk) // 4)
        smp = [walk[i] for i in range(0, len(walk), st)][:4]
        rr = MR.Reader()
        agree = 0
        for (x, z) in smp:
            wv, det = RV.world_walkable(rr, x, z, LEVEL)
            if wv is None:
                say("Y1 ABORT: %s (%d,%d) -- bridge issue, not a map issue" % (det, x, z))
                return 1
            mch = m1.cell_kind(x, z, LEVEL)[0]
            mv = mch in RV.WALKABLE
            if wv == mv:
                agree += 1
                say("  ok  (%d,%d) map=%s world_walkable=%s [%s]" % (x, z, mch, wv, det))
            else:
                say("  BAD (%d,%d) map=%s but world_walkable=%s [%s]"
                    % (x, z, mch, wv, det))
        y1 = (agree == len(smp))
        say("Y1 truth agree: %d/%d => %s" % (agree, len(smp), y1))
    ok &= y1

    say("---- Y1..Y5 = %s / %s / %s / %s / %s ----" % (y1, y2, y3, y4, y5))
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
