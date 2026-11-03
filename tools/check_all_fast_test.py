#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_all_fast_test.py -- the --fast subset must stay a SUBSET and say so (F1/F3/F4)

WHY (2026-09-29, round 28): the battery grew to 22 items (~14 min). A fast subset
is needed for interactive use -- but a subset that reports plain "ALL PASS" is
exactly the kind of fake green this project keeps punishing. So: the subset must
contain only quick items, must never include the multi-hop/long-walk suites, and
must announce itself as a subset both at the top and at the bottom. The default
(no flags) composition must be unchanged.

CRITERIA (declared BEFORE running; all offline & instant):
  F1 subset only  : every FAST entry exists in QUICK, and none of the known
                    heavy ones (long walks / many hops) is in FAST.
  F3 says so      : the source must print the subset warning both at the header
                    and at the tail (so "ALL PASS" can never appear unqualified).
  F4 default same : QUICK + WALK still holds the full 22 scripts, and each FAST
                    entry is one of them (nothing was moved out of the default).

ASCII-only output.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import check_all as C   # noqa: E402

# ★这些是"会真走、可能走很久"的 ✓ ⇒ **永远不许**进 --fast ✗
HEAVY = {"plan_verify_test.py", "chest_many_test.py", "r8_guard_test.py",
         "r9_target_guard_test.py", "route_verify_test.py", "area_verify_test.py",
         "platform_test.py", "edge_avoid_test.py", "edge_hop_test.py",
         "prefix_guard_test.py", "m1_verify.py"}


def say(s):
    print(s, flush=True)


def main():
    ok = True
    quick = {s for s, _w in C.QUICK}
    fast = {s for s, _w in C.FAST}
    allp = {s for s, _w in (C.QUICK + C.WALK)}

    f1a = fast <= quick
    f1b = not (fast & HEAVY)
    f1 = f1a and f1b
    say("F1 subset only: FAST=%d all-inside-QUICK=%s none-heavy=%s (heavy overlap=%s) => %s"
        % (len(fast), f1a, f1b, sorted(fast & HEAVY), f1))
    ok &= f1

    src = io.open(ROOT / "tools" / "check_all.py", encoding="utf-8").read()
    f3a = "--fast **子集**" in src
    f3b = "--fast 子集：" in src
    f3 = f3a and f3b
    say("F3 says so: header warning=%s tail warning=%s => %s" % (f3a, f3b, f3))
    ok &= f3

    f4 = (len(allp) == len(C.QUICK) + len(C.WALK)) and (len(allp) >= 20) \
        and (fast <= allp) and (20 < len(allp))
    say("F4 default same: QUICK+WALK=%d (>=20) and FAST is inside it => %s"
        % (len(allp), f4))
    ok &= f4
    say("   (default plan = QUICK %d + WALK %d = %d)" % (len(C.QUICK), len(C.WALK), len(allp)))

    say("---- F1 / F3 / F4 = %s / %s / %s ----" % (f1, f3, f4))
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
