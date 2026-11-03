#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ring_order.py — 把 floor_ring 的目标格排成一条「绕岛一圈」的走法，直接当作业参数用。

为什么需要：
  海龟没有 GPS，只能"按步数推算位置"（每走一步返回成功与否 ✓）。
  若把 80 个格子按 (z,x) 排序，海龟会来回横穿岛内 —— 而岛内 y=71 全是玩家的建筑 ✗，
  一步就被挡住，整条作业当场废掉 ✗。
  正解是把目标格排成**沿岛缘的环形顺序**（贪心最近邻），相邻两格通常只差 1~2 步 ✓。

输出：
  · 终端：顺序清单 + 总曼哈顿步数 + 最大单步跨度
  · 文件：build/ring_cells.json —— [{"x":..,"z":..}, ...]，可直接塞进作业参数 cells

用法：
    py tools/ring_order.py --start 4119 3
    py tools/ring_order.py --start 4119 3 --y 70 --limit 25 --offset 0
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mca_map import BASE, read_chunk, block_at  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--y", type=int, default=70)
    ap.add_argument("--x0", type=int, default=4100)
    ap.add_argument("--x1", type=int, default=4150)
    ap.add_argument("--z0", type=int, default=-12)
    ap.add_argument("--z1", type=int, default=32)
    ap.add_argument("--start", type=int, nargs=2, default=[4119, 3], metavar=("X", "Z"))
    ap.add_argument("--limit", type=int, default=0, help="只输出前 N 格（分批跑用）")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--out", default=r"build\ring_cells.json")
    args = ap.parse_args(argv)

    world = glob.glob(os.path.join(BASE, "* (1)"))[0]
    rd = os.path.join(world, "region")
    chunks = {}
    for rx in range(args.x0 >> 9, (args.x1 >> 9) + 1):
        for rz in range(args.z0 >> 9, (args.z1 >> 9) + 1):
            p = os.path.join(rd, "r.%d.%d.mca" % (rx, rz))
            if not os.path.isfile(p):
                continue
            mca = open(p, "rb").read()
            for lx in range(32):
                for lz in range(32):
                    cx, cz = rx * 32 + lx, rz * 32 + lz
                    if not (args.x0 >> 4 <= cx <= args.x1 >> 4 and args.z0 >> 4 <= cz <= args.z1 >> 4):
                        continue
                    chunks[(cx, cz)] = read_chunk(mca, lx, lz)

    def nm(x, y, z):
        ch = chunks.get((x >> 4, z >> 4))
        if ch is None:
            return None
        return block_at(ch, x, y, z)

    y = args.y
    ring = []
    for x in range(args.x0, args.x1 + 1):
        for z in range(args.z0, args.z1 + 1):
            v = nm(x, y, z)
            if v is None or v != "minecraft:air":
                continue
            nb = False
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                w = nm(x + dx, y, z + dz)
                if w is not None and w != "minecraft:air":
                    nb = True
                    break
            if nb:
                ring.append((x, z))

    # ⚠ 顺序决定了作业能不能跑完（真实教训）：
    #   纯贪心最近邻在**闭环**上会在末尾留下一段横穿岛内的长跳（实测最大跨度 38 格 ✗），
    #   而岛内 y=71 全是玩家建筑，38 步必被挡死 ✗。
    #   改用**绕质心的角度排序**：环上相邻格的角度也相邻 → 跨度几乎恒为 1~3 ✓。
    import math
    cx0 = sum(c[0] for c in ring) / len(ring)
    cz0 = sum(c[1] for c in ring) / len(ring)
    import math as _m
    ang = sorted(ring, key=lambda c: _m.atan2(c[1] - cz0, c[0] - cx0))
    # 旋转到离海龟起点最近的格子开头
    best_i, best_d = 0, None
    for i, c in enumerate(ang):
        d = abs(c[0] - args.start[0]) + abs(c[1] - args.start[1])
        if best_d is None or d < best_d:
            best_i, best_d = i, d
    order = ang[best_i:] + ang[:best_i]
    total = 0
    px, pz = args.start
    worst = 0
    for c in order:
        d = abs(c[0] - px) + abs(c[1] - pz)
        total += d
        worst = max(worst, d)
        px, pz = c

    sel = order[args.offset: (args.offset + args.limit) if args.limit else None]
    print("边界环 %d 格；环形顺序总步数 %d；最大单步跨度 %d" % (len(order), total, worst))
    print("本批：offset=%d limit=%d → 取 %d 格" % (args.offset, args.limit, len(sel)))
    print("  起点 (start) = %s，本批首格 = %s，本批末格 = %s" %
          (tuple(args.start), sel[0] if sel else None, sel[-1] if sel else None))
    print("  首 12 格：" + ", ".join("(%d,%d)" % c for c in sel[:12]))

    outp = args.out
    os.makedirs(os.path.dirname(os.path.abspath(outp)), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as fh:
        json.dump([{"x": c[0], "z": c[1]} for c in sel], fh, ensure_ascii=False)
    print("  已写：%s" % os.path.abspath(outp))

    # 全量顺序也存一份，便于分批推进时对照
    full = os.path.join(os.path.dirname(os.path.abspath(outp)), "ring_cells_full.json")
    with open(full, "w", encoding="utf-8") as fh:
        json.dump([{"x": c[0], "z": c[1]} for c in order], fh, ensure_ascii=False)
    print("  全量顺序：%s" % full)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
