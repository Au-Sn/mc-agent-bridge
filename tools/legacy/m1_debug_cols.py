"""m1_debug_cols.py -- 看几个柱子的**真实分层**（判"最高那个=地表"这条假设对不对 ✓）

为什么必须看 ✗：图里北半边整片是 W（木头 ✓）—— 要么真有一层木平台 ✓
要么我把"屋顶/树冠"当成了地表 ✗。不看清楚就往下做寻路 ⇒ 会规划到屋顶上去 ✗
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
sys.path.insert(0, str(ROOT / "tools"))
import mapread as MR  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

box = (4111, 63, -8, 4135, 77, 16)
r = MR.Reader()
m = r.get(box)
print("bot pos:", r.pos())
for (x, z) in [(4123, -5), (4123, 0), (4123, 4), (4123, 8), (4115, -4), (4130, 2), (4120, 12)]:
    ys = m.solid_ys(x, z)
    print("(%d,%d) 共 %d 个已知方块:" % (x, z, len(ys)))
    for y in ys:
        print("      y=%d %s" % (y, m.cols[(x, z)][y]))
