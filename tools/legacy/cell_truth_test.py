"""cell_truth_test.py -- 独立读"假人脚下/身上"那几格，跟地图对一遍（量 ✓ 别猜 ✗）"""
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

r = MR.Reader()
p = r.pos()
print("bot pos =", p)
bx, by, bz = int(p[0]), int(p[1]), int(p[2])
box = (bx - 12, by - 8, bz - 12, bx + 12, by + 6, bz + 12)
m = r.get(box, max_age=60.0)
for dy in (2, 1, 0, -1, -2):
    y = by + dy
    real = r.block(bx, y, bz)
    mapped = m.cols.get((bx, bz), {}).get(y, "(地图里没有)")
    print("  y=%d 独立读=%-42s 地图=%s" % (y, real or "(读失败)", mapped))
