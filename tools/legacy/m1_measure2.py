"""m1_measure2.py -- match 查询到底给不给**坐标**（给 ⇒ 地图就能几次调用建完 ✓）

判据（事先写死 ✓）：
  · 若 match 回执里出现 `x,y,z` 形式的**方块坐标**（不是 box= 那两个角 ✓）⇒ 记为 GIVE_POS ✓
  · 否则记为 NO_POS ✗ ⇒ 逐格探测是唯一办法 ⇒ 必须靠模组侧 /dshmap
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


def ab(t: str, tmo: float = 60.0) -> str:
    return (ch.cmd("execute as Bot at Bot run " + t, timeout=tmo, allow_str=True).text() or "").strip()


def main() -> int:
    d = ab("dshdigest 1")
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", d)
    bx, by, bz = (int(float(m.group(1))), int(float(m.group(2))), int(float(m.group(3))))
    box = "%d %d %d %d %d %d" % (bx - 14, by - 8, bz - 14, bx + 14, by + 6, bz + 14)
    for mat in ("grass_block", "wheat", "#minecraft:mineable/shovel"):
        out = ab('dshscan %s "%s" 6 1' % (box, mat))
        # 只看 box= 头之外的坐标对 ✓
        head, _, rest = out.partition("counts[")
        coords = re.findall(r"(-?\d+),(-?\d+),(-?\d+)", rest or out)
        print("=== match=%s ===" % mat)
        print("  全文长度=%d 行数=%d" % (len(out), len(out.splitlines())))
        for line in out.splitlines():
            print("  |", line[:400])
        print("  counts 段之后的坐标对:", coords[:8])
        print("  =>", "GIVE_POS" if coords else "NO_POS")
    return 0


raise SystemExit(main())
