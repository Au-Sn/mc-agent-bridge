"""chest_probe.py -- find the island chest and read its receipt format (ASCII-only output)

Why: the brain has no tool to put things into a container, which blocks organising/production
long tasks. The mod already has /dshbox peek|take|put (see docs/模组-容器存取与假人手.md),
so before wrapping it as an MCP tool I must read its REAL receipt format (discipline 1).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ch = Channel("cmd0", verbose=False)


def ab(t: str, tmo: float = 120.0) -> str:
    return (ch.cmd("execute as Bot at Bot run " + t, timeout=tmo, allow_str=True).text() or "").strip()


def main() -> int:
    s = ab('dshscan 4080 50 -40 4170 100 60 "chest" 4 1')
    print("SCAN_OUT:")
    for line in s.splitlines():
        print("   ", line.strip()[:300])
    m = re.findall(r"(-?\d+),(-?\d+),(-?\d+)", s)
    print("POSITIONS FOUND:", m[:6])
    # try the likely chest position with peek
    for p in m[:3]:
        out = ab("dshbox peek %s %s %s" % p)
        print("PEEK %s -> %s" % (",".join(p), out[:300]))
    return 0


raise SystemExit(main())
