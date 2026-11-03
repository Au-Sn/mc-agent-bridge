#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""a4_plan_test.py -- A4: planner must not emit place@ on the bot's own cell (sec 79.453)

Why this exists:
  changes() emits place@(x, y-1, z) to support a floating target cell.
  When that cell IS the bot's current cell (prev), the bot would have to stand
  inside it to place -> mod raises do_fail(place_on_body) -> the whole task dies.
  (sec 79.447: take-item hung exactly this way: place_on_body@4109,71,17)

Checks:
  A1 exec3d guard still refuses place_on_body (defence in depth)
  A2 a normal bridge plan has empty body_bad and correct step order
  A3 changes() does NOT emit place@ == prev (static, with stubbed stand_at)
  A4 changes() DOES emit place@ when the support cell is a neighbour cell
"""
from __future__ import annotations

import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import plan3d as P3          # noqa: E402
import exec3d as E3          # noqa: E402


class FakeW:
    """Minimal world: collision heights only (enough for support/passable)."""

    def __init__(self, heights):
        self.hh = heights

    def h(self, x, y, z):
        return self.hh.get((x, y, z), 0.0)

    def support(self, x, y, z):
        return self.h(x, y - 1, z) > 0.05

    def passable(self, x, y, z):
        return self.h(x, y, z) <= 0.05

    def pass_info(self, x, y, z):
        return {"kind": "free" if self.passable(x, y, z) else "blocked"}

    def get(self, x, y, z):
        return None


def main() -> int:
    checks = []

    # A1: guard refuses place_on_body
    path = [(4109, 71, 17), (4109, 72, 17)]
    acts = ["place@4109,71,17", "step_up"]
    _s, _t, _n, body = E3.table_from_plan(path, acts, "cobblestone", 400)
    checks.append(("A1 exec3d guard refuses place_on_body", body and "place_on_body" in body[0],
                   str(body)))

    # A2: normal bridge is clean + ordered place-before-walk
    path2 = [(4108, 71, 17), (4109, 71, 17), (4110, 71, 17)]
    acts2 = ["place@4109,70,17", "walk", "walk"]
    steps2, _t2, _n2, body2 = E3.table_from_plan(path2, acts2, "cobblestone", 400)
    ok2 = (not body2) and steps2 and steps2[0].startswith("place:")
    checks.append(("A2 normal bridge: no body_bad, place first", ok2, str(steps2[:3])))

    # A3/A4: changes() with stubbed stand_at / diggable
    orig_stand = P3.stand_at
    orig_dig = P3.diggable
    try:
        P3.stand_at = lambda w, x, y, z: (True, False)
        P3.diggable = lambda w, x, y, z: False
        # prev = (4109,71,17); moving to (4110,71,17); its support cell (4110,70,17) is
        # empty -> changes() wants to place there. That is a NEIGHBOUR cell -> allowed.
        w = FakeW({(4108, 70, 17): 1.0, (4109, 70, 17): 1.0})
        actsA = P3.changes(w, 4110, 71, 17, (4109, 71, 17))
        want_a = "place@4110,70,17" in actsA
        checks.append(("A3 changes() emits place@ for a neighbour support cell", want_a,
                       str(actsA)))

        # Now the impossible case: target (4109,72,17), support cell (4109,71,17) == prev.
        actsB = P3.changes(w, 4109, 72, 17, (4109, 71, 17))
        bad_b = [a for a in actsB if a == "place@4109,71,17"]
        checks.append(("A4 changes() does NOT emit place@ == prev", not bad_b, str(actsB)))
    finally:
        P3.stand_at = orig_stand
        P3.diggable = orig_dig

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", detail[:120]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => a4_plan FAIL (%d)" % bad)
        print("A4PLAN ok=0 bad=%d" % bad)
        return 1
    print("  => a4_plan PASS (planner never places on own cell; guard still in place)")
    print("A4PLAN ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
