#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ascii_reason_test.py -- every command reply with Chinese must carry an ASCII reason

BUG THIS GUARDS (sec 79.459): the CC captures the game console, which renders ASCII
only, so Chinese characters in a command reply arrive as '?'. Every dshdo/dshgoto error
was unreadable through the bridge.

FIX (sec 79.460): replies keep the Chinese (the Python side references some of those
strings) but now START with an ASCII `reason=<token>` field so a reader can parse a
stable key. This judge scans the mod source and fails if any bad()/ok() reply contains
non-ASCII but no `reason=` token.

Checks:
  R1 no reply call has non-ASCII without a `reason=` token
  R2 at least the known error replies do carry one (catches accidental removal)
  R3 dshgoto's no_stand rejection keeps its machine-readable at=<pos> field
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
J = ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge" / "DshBridgeMod.java"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def reply_calls(text):
    """Yield (line_no, kind, source blob) for bad(/ok( calls, with balanced parens."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.search(r"\b(bad|ok)\(", lines[i])
        if not m:
            i += 1
            continue
        depth = 0
        buf = []
        j = i
        while j < len(lines) and j < i + 14:
            buf.append(lines[j])
            depth += lines[j].count("(") - lines[j].count(")")
            # stop at the end of the statement: a Java call ends with ');'
            if depth <= 0 or lines[j].rstrip().endswith(";"):
                break
            j += 1
        yield i + 1, m.group(1), "\n".join(buf)
        i = j + 1


def main() -> int:
    text = J.read_text(encoding="utf-8")
    checks = []

    offenders = []
    for ln, kind, blob in reply_calls(text):
        # skip comment lines masquerading as calls
        stripped = blob.strip()
        if stripped.startswith("*") or stripped.startswith("//") or stripped.startswith("/*"):
            continue
        has_non_ascii = any(ord(ch) > 127 for ch in blob)
        if not has_non_ascii:
            continue
        if "reason=" in blob:
            continue
        offenders.append((ln, kind, blob.splitlines()[0].strip()[:110]))
    checks.append(("R1 中文回执都带 reason=", not offenders,
                   "%d 处裸中文" % len(offenders)))
    for ln, kind, first in offenders[:8]:
        print("   offender L%-5d %-4s %s" % (ln, kind, first))

    # R2 the known ones must still carry a token
    expect = ["reason=bad_step_format", "reason=bad_pos", "reason=bad_number",
              "reason=no_steps", "reason=needs_player", "reason=bad_point_format",
              "reason=no_points", "reason=no_stand"]
    missing = [e for e in expect if e not in text]
    checks.append(("R2 已知错误回执都有 reason=", not missing, "缺：%s" % (missing or "无")))

    # R3 no_stand keeps a machine readable target
    m = re.search(r'reason=no_stand at=" \+ ([A-Za-z0-9_.]+)', text)
    checks.append(("R3 no_stand 带 at=<pos>", bool(m), "匹配=%s" % (bool(m),)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => ascii_reason FAIL (%d)" % bad)
        print("ASCIIREASON ok=0 bad=%d" % bad)
        return 1
    print("  => ascii_reason PASS (every Chinese reply carries an ASCII reason token)")
    print("ASCIIREASON ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
