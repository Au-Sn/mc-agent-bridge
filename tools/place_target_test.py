#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""place_target_test.py -- the action-table exit must refuse impossible steps

WHY (sec 79.471 / 79.473, both measured in the real world):
  * walk_target_not_standable@4109,72,19 killed 3 attempts in a row
  * place_not_done@4118,71,14 killed a 46-step plan
In both cases the PLANNER emitted a step the mod must refuse, and one refusal fails the
whole queued task. So exec3d.validate_table() now checks, at the single exit:
  walk  -> stand_at must hold at the time that step runs (overlaying blocks placed
           earlier in the same table, so a legal bridge is not punished)
  place -> target must be empty, must have at least one solid face to click, and must be
           within 4 cells (Chebyshev) of where the bot stands when that step runs

CHECKS
  T1 place with no solid neighbour  -> place_no_face
  T2 place onto an existing block   -> place_target_occupied
  T3 place too far from the bot     -> place_out_of_reach
  T4 legal bridge (place, then walk onto it) -> NO bad (overlay works)
  T5 walk onto a cell with no support -> walk_target_not_standable
  T6 fully legal table -> NO bad
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import exec3d as E3           # noqa: E402
import world3d as W3          # noqa: E402


class FakeW:
    """A tiny world: `solid` is the set of solid cells, everything else is air."""

    def __init__(self, solid):
        self.solid = set(solid)

    def get(self, x, y, z):
        return "x:stone" if (x, y, z) in self.solid else ""

    def name(self, x, y, z):
        return "minecraft:air" if (x, y, z) not in self.solid else "x:stone"

    def h(self, x, y, z):
        return 1.0 if (x, y, z) in self.solid else 0.0

    def support(self, x, y, z):
        return self.h(x, y - 1, z) > 0.05

    def passable(self, x, y, z):
        return self.h(x, y, z) <= 0.05

    def pass_info(self, x, y, z):
        return {"kind": "free" if self.passable(x, y, z) else "blocked",
                "subtype": "", "action": None, "why": ""}


def main() -> int:
    checks = []

    # T1: isolated air target -> no face
    w = FakeW({(0, 70, 0)})
    wb, pb, _db = E3.validate_table(w, (0, 71, 0), ["place:5,71,5:x"])
    checks.append(("T1 没有可点的面 ⇒ place_no_face",
                   any("place_no_face" in b for b in pb), str(pb)))

    # T2: target already solid
    w2 = FakeW({(0, 70, 0), (1, 71, 0)})
    wb2, pb2, _db2 = E3.validate_table(w2, (0, 71, 0), ["place:1,71,0:x"])
    checks.append(("T2 目标已实心 ⇒ place_target_occupied",
                   any("place_target_occupied" in b for b in pb2), str(pb2)))

    # T3: reachable face but too far
    w3 = FakeW({(0, 70, 0), (10, 70, 10)})
    wb3, pb3, _db3 = E3.validate_table(w3, (0, 71, 0), ["place:10,71,10:x"])
    checks.append(("T3 太远 ⇒ place_out_of_reach",
                   any("place_out_of_reach" in b for b in pb3), str(pb3)))

    # T4: legal bridge: solid at (0,70,0), bot at (0,71,0); place (1,71,0)? needs a face.
    #    Use (1,70,0) whose face (0,70,0) is solid; then walk onto (1,71,0).
    # bot stands at (0,71,0) with floor (0,70,0); place (1,70,0) uses (0,70,0) as its
    # face; the later walk onto (1,71,0) is supported by the block we just placed.
    w4 = FakeW({(0, 70, 0)})
    steps4 = ["place:1,70,0:x", "walk:1,71,0"]
    wb4, pb4, _db4 = E3.validate_table(w4, (0, 71, 0), steps4)
    checks.append(("T4 合法搭桥不被冤枉", not wb4 and not pb4, "walk=%s place=%s" % (wb4, pb4)))

    # T5: walk onto a cell with no support
    w5 = FakeW({(0, 70, 0)})
    wb5, pb5, _db5 = E3.validate_table(w5, (0, 71, 0), ["walk:0,72,0"])
    checks.append(("T5 站不住的 walk 目标 ⇒ walk_target_not_standable",
                   any("walk_target_not_standable" in b for b in wb5), str(wb5)))

    # T6: fully legal table
    w6 = FakeW({(0, 70, 0), (1, 70, 0), (2, 70, 0)})
    wb6, pb6, _db6 = E3.validate_table(w6, (0, 71, 0), ["walk:1,71,0", "walk:2,71,0"])
    checks.append(("T6 合法表 ⇒ 不报", not wb6 and not pb6, "walk=%s place=%s" % (wb6, pb6)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => place_target FAIL (%d)" % bad)
        print("PLACETGT ok=0 bad=%d" % bad)
        return 1
    print("  => place_target PASS (impossible walk/place steps are refused before submit)")
    print("PLACETGT ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
