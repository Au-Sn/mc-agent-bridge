"""find_machines.py -- where are the processing machines? (ASCII-only output)

Why: the brain scanned for `exdeorum` and found 0 => it could not go sifting, and told the
user "I don't see a sifter nearby". Before writing that into memory/bot.md as a fact, verify
with world truth (discipline 2: never trust a single self-report).
"""
from __future__ import annotations

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
    for mat in ("sieve", "exdeorum", "mesh", "barrel", "crucible", "compost", "anvil",
                "furnace", "chest", "crafting_table"):
        s = ab('dshscan 4080 50 -40 4170 100 60 "%s" 8 1' % mat)
        m = re.search(r"matched=(\d+)", s)
        n = m.group(1) if m else "?"
        print("%-16s matched=%s" % (mat, n))
        if m and n != "0":
            for part in s.splitlines():
                if "shown" in part or "@" in part:
                    print("     ", part.strip()[:200])
    return 0


raise SystemExit(main())
