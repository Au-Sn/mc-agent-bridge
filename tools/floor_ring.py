#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""floor_ring.py — 从 region 文件算出"平台该往外扩的目标格清单"（边界环）

为什么需要它（今晚的教训）：地形边缘是**斜的/不规则的** ✗，所以"朝一个方向直线推进"必然
有的地方撞虚空、有的地方还在岛内 ✗。正解是**由文件算出边界环**：某格在 y=FLOOR 是空的、
且四邻里有地面格 → 它就是"往外扩一格"的目标 ✓。这份清单直接交给放置作业逐格执行 ✓。

用法：py tools/floor_ring.py --y 70 --x0 4100 --x1 4150 --z0 -12 --z1 32
"""
from __future__ import annotations
import argparse, glob, os, sys
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

    def solid(x, z):
        ch = chunks.get((x >> 4, z >> 4))
        if ch is None:
            return None                       # 区块不存在（未生成）
        nm = block_at(ch, x, args.y, z)
        return bool(nm) and nm != "minecraft:air"

    ring = []
    for x in range(args.x0, args.x1 + 1):
        for z in range(args.z0, args.z1 + 1):
            if solid(x, z) is not False:      # 有地面 / 未生成 → 跳过
                continue
            nb = [solid(x + 1, z), solid(x - 1, z), solid(x, z + 1), solid(x, z - 1)]
            if any(v is True for v in nb):    # 空、且贴着一块地面 → 边界环
                ring.append((x, z))

    print("y=%d 的边界环：%d 格（x %d..%d, z %d..%d）" % (args.y, len(ring), args.x0, args.x1, args.z0, args.z1))
    byz = {}
    for x, z in ring:
        byz.setdefault(z, []).append(x)
    for z in sorted(byz):
        xs = sorted(byz[z])
        # 压缩成连续区间，便于直接下指令
        runs, s = [], xs[0]
        for a, b in zip(xs, xs[1:] + [None]):
            if b != (a + 1):
                runs.append((s, a)); s = b
        print("  z=%-4d x: %s" % (z, ", ".join(("%d-%d" % r) if r[0] != r[1] else str(r[0]) for r in runs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
