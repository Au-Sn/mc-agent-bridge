#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mapfind.py -- ★"★这个物种，我够得着哪一片？★"✗★（★带**层高**的地图读取 ✗ 2026-10-05）

★★它修的缺陷（★§79.148 实测✗★）✗★★
  ★`Planner.region(x,z)` 给的是**二维**连通区✗★ ⇒ ★"★这一列连通★"**不等于**"★那片树叶够得着★"✗★
  （★实测：地图说有 20 个够得着的树叶格 ✗ 而它们都在 y=74 ✗ 假人在 71 ✗ 走手只上 1 层✓★）✗★
★⇒ 口径分**两句**✗★（★判据写死✗★）
  · ★`列连通`✗★：★`(x,z)` 在 `region` 里✗★
  · ★`够得着`✗★：★列连通 **且** `|实例的 y − 连通区那一层的 y| ≤ 爬升上限`✗★ ✓
  ★两句**分开报** ✗ 绝不把"★列连通★"说成"★够得着★"✗★ ✓

用法：`py tools/mapfind.py <物种> [--near x,z] [--max N]`
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def level_ok(inst_y: int, base_y: int, climb: int) -> bool:
    """★层够不够得着✗★（★纯函数 ✗ 好离线判✓★）

    ★口径✗★：★**往上**受 `climb` 限制（★走手只会上那么多层✓★）✗
      ★**往下**放宽到 `climb + 1`（★走下去比爬上去容易 ✗ 而且下落不受"★上台阶能力★"限制✓★）✗★ ✓
    """
    dy = inst_y - base_y
    if dy >= 0:
        return dy <= climb
    return (-dy) <= (climb + 1)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("species")
    ap.add_argument("--near", default="")
    ap.add_argument("--max", type=int, default=8)
    a = ap.parse_args(argv)

    import mc_mcp  # noqa: F401  （接线：`_LIVE._walk` 在它导入时建立）
    import mcp_geo as G
    import mcp_walk as MW
    import pathplan as PP
    import mcp_percept as P

    st, _ = P.t_bot_state()
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", st or "")
    if not m:
        print("INCONCLUSIVE: ★读不到假人位置✗★")
        return 4
    bx, by, bz = float(m.group(1)), float(m.group(2)), float(m.group(3))
    climb = int(getattr(MW, "MOD_CLIMB_UP", 1))
    print("== 找 %s ✗ 假人 (%.1f,%.0f,%.1f) ✗ 爬升上限 %d ==" % (a.species, bx, by, bz, climb))

    # ★目标区：先用扫描拿到该物种的实例（★地图读取的**输入** ✗ 不是判据✓★）
    if a.near:
        nx, nz = (int(v) for v in a.near.split(","))
    else:
        nx, nz = int(bx), int(bz)
    r, _bad = P.t_scan(int(bx) - 40, max(0, int(by) - 20), int(bz) - 40,
                       int(bx) + 40, int(by) + 20, int(bz) + 40, match=a.species, max_=40)
    cells = [(int(x), int(y), int(z)) for x, y, z, _s in re.findall(
        r"(-?\d+),(-?\d+),(-?\d+):([a-z0-9_]+:[a-z0-9_/]+)", r or "")]
    print("   扫描到 %d 个实例" % len(cells))
    if not cells:
        print("   ★测不了✗★：这一带没有 %s" % a.species)
        return 3
    if not a.near:
        cells.sort(key=lambda c: ((c[0] - bx) ** 2 + (c[2] - bz) ** 2))
        nx, nz = cells[0][0], cells[0][2]

    _r, mp, box = G._route_map(int(bx), int(bz), nx, nz, int(by))
    pl = PP.Planner(mp, level=int(by) + 1, max_up=climb)
    reg = pl.region(int(bx), int(bz))
    base_y = int(by)
    print("   图 box=%s ｜ 连通区 **%d** 格 ｜ 连通区所在层 y=%d" % (box, len(reg), base_y))

    in_col, ok = [], []
    for (x, y, z) in cells:
        col_ok = (x, z) in reg
        if col_ok:
            in_col.append((x, y, z))
            if level_ok(y, base_y, climb):
                ok.append((x, y, z))
    print("   ① 列连通：%d 个 ｜ ② ★真的够得着✗★（★层差 ≤ %d✗★）：**%d** 个"
          % (len(in_col), climb, len(ok)))
    if ok:
        print("   ⇒ ★够得着的实例✗★（★可拿去取证✗★）：")
        for c in ok[:a.max]:
            print("      (%d,%d,%d) 层差 %+d" % (c[0], c[1], c[2], c[1] - base_y))
        return 0
    print("   ⇒ ★测不了✗★：**列连通但层够不着** %d 个 ｜ **列都不连通** %d 个"
          % (len(in_col) - len(ok), len(cells) - len(in_col)))
    if in_col:
        dys = sorted(set(c[1] - base_y for c in in_col))
        print("      ★列连通那些的层差✗★：%s（★上限 %d✗★）" % (dys[:8], climb))
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
