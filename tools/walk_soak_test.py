#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""walk_soak_test.py -- short walk-soak as a world_regress member

WHY: the 12-minute soak (tools/d3_walk_soak.py) found the pillar problem (sec 79.476:
a "walk" that placed a block, took fall damage and consumed an item). But a 12-minute
observer can never be part of the regression. This wrapper runs a SHORT soak and reports
the same checks, so every world_regress run keeps a live guard on:
  W1 no deaths, W2 no lost items, W3 not stuck, W4 no falling, W5 really walked,
  W6 refusals honest, W7 ★the walk must not change the world★ (mod 2.44.0 reports pillar=N)

W5/W7 thresholds scale with --minutes, so 3 minutes is meaningful (that is why
d3_walk_soak.py's W5 was made duration-aware in the same change).

Output: `SOAK ok=1 checks=N` on success (world_regress parses SUMMARY-style lines).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOAK = ROOT / "tools" / "d3_walk_soak.py"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MINUTES = "3"


def main() -> int:
    r = subprocess.run([sys.executable, "-B", "-u", "-X", "utf8", str(SOAK),
                        "--minutes", MINUTES],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    # print the verdict block so the log is readable
    keep = []
    started = False
    for line in out.splitlines():
        if "判定" in line:
            started = True
        if started:
            keep.append(line)
    print("\n".join(keep) if keep else out[-1500:])

    ok = ("D3-长走/贴边 PASS" in out)
    checks = len(re.findall(r"(?m)^\s*W\d ", out))
    print("SOAK ok=%d checks=%d rc=%d" % (1 if ok else 0, checks, r.returncode))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
