# -*- coding: utf-8 -*-
"""fastmap_diag.py —— ★快图（/dshmap）与慢图（按种类扫描）在"假人那一格"上到底差在哪★ ✗

为什么要它 ✗（2026-09-28 ✓）：R2/R3 都在同一步炸掉 —— `Planner.region()` 算出**空的/极小**的连通区 ✗
  ⇒ 所有目标都被"不在连通区"拒掉 ✗ ⇒ 走路验证全废 ✗
  而 R2/R3 现在走的是**快图**（我在 v2.15 之后把 `_route_map` 改成优先 `/dshmap` ✓）
  ⇒ 高度怀疑是**两边的 y 约定不一致** ✗（快图只给"与假人同层"的格 ✓ 慢图给地表层 ✗）
判据 ✓（打印，不下结论 ✗）：
  · 两张图在假人那一列（x,z）各存了哪些 y、什么名字 ✓
  · 两张图各自的 `standable(x,z,below=level+1)` 是 True 还是 False ✓
  · 两张图各自的 `region(x,z)` 有多大 ✓
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))
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
LEVEL = int(round(p[1]))
print("bx,bz=%d,%d  LEVEL=%d" % (bx, bz, LEVEL))

fast = r.build_dshmap(radius=16)
scan = None
for (lo, hi) in ((LEVEL, LEVEL), (0, 0)):
    pass
box = (bx - 12, LEVEL - 8, bz - 12, bx + 12, LEVEL + 6, bz + 12)
scan = r.get(box, max_age=0.001)

for tag, m in (("快图 /dshmap", fast), ("慢图 扫描", scan)):
    if m is None:
        print("%-14s = None ✗" % tag)
        continue
    col = m.cols.get((bx, bz)) or {}
    pl = PP.Planner(m, level=LEVEL)
    print("%-14s box=%s ｜ 列含 y=%s ｜ standable=%s ｜ region=%d 格 ｜ 覆盖 %.0f%%"
          % (tag, m.box, sorted(col.items())[:6], pl.ok(bx, bz),
             len(pl.region(bx, bz)), m.coverage() * 100))
    print("               surface(below=%d)=%s" % (LEVEL + 1, m.surface(bx, bz, LEVEL + 1)))

# 快图里"与假人同层"的格子到底存在哪个 y
if fast is not None:
    ys = {}
    for k, col in fast.cols.items():
        for y in col:
            ys[y] = ys.get(y, 0) + 1
    print("快图各 y 的格子数（说明它把地板记在哪一层）:", sorted(ys.items())[:8])
    print("快图 meta:", {k: fast.meta.get(k) for k in ("from", "dshmap_standable", "cells_at_level")})
