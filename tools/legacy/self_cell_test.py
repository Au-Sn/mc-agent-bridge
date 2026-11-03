"""self_cell_test.py -- 为什么"假人自己那一格"算不出连通区域（量 ✓ 别猜 ✗）"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
sys.path.insert(0, str(ROOT / "tools"))
import mapread as MR   # noqa: E402
import pathplan as PP  # noqa: E402

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
print("box =", box, "coverage = %.3f" % m.coverage(), "cols =", len(m.cols))
col = m.cols.get((bx, bz))
print("自己那一列 (x=%d,z=%d) 已知方块：" % (bx, bz))
if col:
    for y in sorted(col):
        print("    y=%d %s  (is_floor=%s blocks_space=%s)"
              % (y, col[y], MR.is_floor(col[y]), MR.blocks_space(col[y])))
else:
    print("    ★这一列一个已知方块都没有★ ⇒ 这一格「未知」⇒ 连通区域必空 ✗")
print("surface(below=%d) = %s" % (by + 1, m.surface(bx, bz, by + 1)))
print("standable =", m.standable(bx, bz, by + 1))
pl = PP.Planner(m, level=by + 1)
print("region(self) =", len(pl.region(bx, bz)))
# 找最近的能站格，看它离假人多元
best = None
for (x, z) in m.cells():
    if pl.ok(x, z):
        d = (x - bx) ** 2 + (z - bz) ** 2
        if best is None or d < best[0]:
            best = (d, x, z)
print("离自己最近的「能站」格 =", best, ("(距离 %.2f 格)" % (best[0] ** 0.5)) if best else "")
# 那一格附近的地面高度（诊断：假人是不是站在"图上没有的方块"上）
for (x, z) in [(bx - 1, bz), (bx, bz - 1), (bx + 1, bz), (bx, bz + 1)]:
    print("  邻居 (%d,%d): %s" % (x, z, m.surface(x, z, by + 1)))
