#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reason_read_test.py -- the ASCII reason token must be readable end to end (sec 79.461)

CHAIN THIS GUARDS:
  mod reply  -> `reason=<token>` is the only ASCII-readable part (CC console drops the
             Chinese) -> mcp_core.kv() parses it -> mcp_walk surfaces it in the
             rejection message so "failure says why" actually works.

Checks (offline):
  R1 kv() extracts reason= from a realistic mod reply
  R2 kv() extracts at= (machine-readable target) too
  R3 mcp_walk's goto_route rejection path mentions reason (source discipline)
  R4 the mod source still emits reason=no_stand for the dshgoto rejection
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C          # noqa: E402


def main() -> int:
    checks = []

    # R1/R2
    fake = "dshgoto reason=no_stand at=4122, 71, 16 站不住"
    kv = C.kv(fake)
    checks.append(("R1 kv reason=", kv.get("reason") == "no_stand", str(kv)))
    checks.append(("R2 kv at=", bool(kv.get("at")), str(kv.get("at"))))

    # R3
    w = (ROOT / "tools" / "mcp_walk.py").read_text(encoding="utf-8")
    i = w.find("goto_route 被拒")
    window = w[max(0, i - 420):i + 200] if i >= 0 else ""
    checks.append(("R3 mcp_walk 报 reason", ("reason" in window) and ("kv(r)" in window),
                   "ok" if "kv(r)" in window else "缺"))

    # R4
    j = (ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge" / "DshBridgeMod.java")
    jt = j.read_text(encoding="utf-8")
    checks.append(("R4 模组仍发 reason=no_stand", "reason=no_stand at=" in jt,
                   "有" if "reason=no_stand at=" in jt else "缺"))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => reason_read FAIL (%d)" % bad)
        print("REASONREAD ok=0 bad=%d" % bad)
        return 1
    print("  => reason_read PASS (ASCII reason token readable end to end)")
    print("REASONREAD ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
