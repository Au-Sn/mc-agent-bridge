#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rv_diag.py -- why did the route view call (4118,6) walkable while the world
says 71/72/73 are all air?  (diagnose with DATA, not guesses)

Loads the newest map cache from disk (no channel use), prints the raw column
contents for the suspicious cells, prints the cell_kind picture for a small
window, then reads the TRUE vertical profile of two columns from the world
(a handful of paced reads -- the bridge is single-channel).

ASCII-only output.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mapread as MR   # noqa: E402

LEVEL = 72
SUSPECT = [(4118, 6), (4118, 7), (4119, 6), (4118, 10), (4117, 6)]


def load_newest():
    fs = glob.glob(str(ROOT / "logs" / "map_cache" / "*.json"))
    if not fs:
        return None, None
    f = max(fs, key=os.path.getmtime)
    rec = json.load(open(f, encoding="utf-8"))
    bx = rec["box"]
    m = MR.Map(*bx)
    m.meta = rec.get("meta") or {}
    for k, v in (rec.get("cols") or {}).items():
        a, b = k.split(",")
        m.cols[(int(a), int(b))] = {int(y): nm for y, nm in v.items()}
    return m, (f, time.time() - os.path.getmtime(f))


def main():
    m, info = load_newest()
    if m is None:
        print("no map cache on disk")
        return 1
    f, age = info
    print("cache file: %s" % os.path.basename(f))
    print("age %.0fs  box=%s  cells=%d" % (age, m.box, len(m.cols)))
    print("meta.source=%s meta.calls=%s meta.sec=%s standable=%s"
          % (m.meta.get("source"), m.meta.get("calls"), m.meta.get("sec"),
             m.meta.get("dshmap_standable")))
    print("")
    print("== raw map columns (what the map believes) ==")
    for (x, z) in SUSPECT:
        c = m.cols.get((x, z))
        k = m.cell_kind(x, z, LEVEL)
        if not c:
            print("  (%d,%d): NO COLUMN  -> cell_kind char = %s" % (x, z, k[0]))
            continue
        ys = sorted(c)
        print("  (%d,%d): ys=%s" % (x, z, ", ".join("%d:%s" % (y, c[y]) for y in ys)))
        print("           surface(below=%d)=%s  cell_kind char=%s name=%s"
              % (LEVEL + 1, m.surface(x, z, below=LEVEL + 1), k[0], k[1]))
    print("")
    print("== cell_kind picture, x %d..%d  z %d..%d (LEVEL=%d) =="
          % (4115, 4122, 2, 12, LEVEL))
    print("       " + "".join(str(x % 10) for x in range(4115, 4123)))
    for z in range(2, 13):
        row = "".join(m.cell_kind(x, z, LEVEL)[0] for x in range(4115, 4123))
        print("  %+4d %s" % (z, row))
    print("")
    print("== kind census over the whole map ==")
    cnt = {}
    for (x, z) in m.cols:
        ch = m.cell_kind(x, z, LEVEL)[0]
        cnt[ch] = cnt.get(ch, 0) + 1
    print("  " + "  ".join("%s=%d" % (k, v) for k, v in sorted(cnt.items())))
    print("")
    print("== TRUE vertical profile from the world (independent reads) ==")
    r = MR.Reader()
    first = True
    for (x, z) in [(4118, 6), (4118, 10)]:
        names = []
        for y in range(69, 74):
            if not first:
                time.sleep(0.25)
            first = False
            nm = r.probe_cell(x, y, z)
            if nm == "":
                print("  READ FAILED (empty) at (%d,%d,%d) -- bridge issue" % (x, y, z))
                return 1
            names.append("%d:%s" % (y, nm.replace("minecraft:", "")))
        print("  (%d,%d): %s" % (x, z, "  ".join(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
