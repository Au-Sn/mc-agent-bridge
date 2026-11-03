#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ring_plan.py — 把 floor_ring 的目标格按「怎么放得进去」分类，产出可直接执行的分组清单。

为什么需要（本轮实测发现的真问题）：
  floor_ring.py 只回答「哪些格该填」✓，但不回答「**海龟站哪儿才能填**」✗。
  y=70 的边界环里，有一部分格子的**正上方 (x,71,z) 是实心的**（岛缘是阶梯状的，
  或者玩家在上面砌了墙/栅栏）——这些格子从上方放不进去，
  若照抄清单盲跑，海龟会一次次"无法到达"或"放置失败" ✗。

本工具对每个目标格报告三件事（全部离线从 region 算，不打扰游戏）：
  · up_air        : (x,71,z) 是空气 → 可"悬停上方 placeDown"
  · below_solid   : (x,69,z) 是实心 → placeDown 有依附面
  · side_solid    : y=70 的四个水平邻居里有实心 → 至少有一个侧面可依附

用法：
    py tools/ring_plan.py                 # 默认 y=70 与 floor_ring 相同的范围
    py tools/ring_plan.py --x0 4100 --x1 4150 --z0 -12 --z1 32
"""
from __future__ import annotations

import argparse
import glob
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

    def open_(x, y, z):
        v = nm(x, y, z)
        return v is None or v == "minecraft:air"

    def solid(x, y, z):
        v = nm(x, y, z)
        return v is not None and v != "minecraft:air"

    y = args.y
    ring = []
    for x in range(args.x0, args.x1 + 1):
        for z in range(args.z0, args.z1 + 1):
            if not open_(x, y, z):
                continue
            nb = any(solid(x + dx, y, z + dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if nb:
                ring.append((x, z))

    groups = {"A_up_ok": [], "B_up_blocked": [], "C_unknown": []}
    for x, z in ring:
        row = {"x": x, "z": z,
               "up": nm(x, y + 1, z), "below": nm(x, y - 1, z),
               "side": [nm(x + dx, y, z + dz) for dx, dz in ((1, 0), (-1, 0), (0, -1), (0, 1))]}
        if row["up"] is None:
            groups["C_unknown"].append(row)
        elif row["up"] == "minecraft:air":
            groups["A_up_ok"].append(row)
        else:
            groups["B_up_blocked"].append(row)

    print("y=%d 边界环 %d 格" % (y, len(ring)))
    print("  A 上方是空气（可悬停上方 placeDown）: %d" % len(groups["A_up_ok"]))
    print("  B 上方被占（放不进去/需另想办法）  : %d" % len(groups["B_up_blocked"]))
    print("  C 未生成/读不到                    : %d" % len(groups["C_unknown"]))
    print()

    for key, title in (("A_up_ok", "A 组（可直接从上方放）"),
                       ("B_up_blocked", "B 组（上方被占）"),
                       ("C_unknown", "C 组")):
        rows = groups[key]
        if not rows:
            continue
        print("== %s : %d ==" % (title, len(rows)))
        byz = {}
        for r in rows:
            byz.setdefault(r["z"], []).append(r)
        for z in sorted(byz):
            rs = sorted(byz[z], key=lambda r: r["x"])
            segs, cur = [], [rs[0]]
            for r in rs[1:]:
                if r["x"] == cur[-1]["x"] + 1:
                    cur.append(r)
                else:
                    segs.append(cur); cur = [r]
            segs.append(cur)
            desc = []
            for sg in segs:
                below = sum(1 for r in sg if r["below"] not in (None, "minecraft:air"))
                desc.append("x%d-%d(below_solid %d/%d, up=%s)" % (
                    sg[0]["x"], sg[-1]["x"], below, len(sg),
                    (sg[0]["up"] or "?") if key != "A_up_ok" else "air"))
            print("  z=%-4d %s" % (z, "  ".join(desc)))
        print()

    # 也顺便列出"上方被占"的方块名，便于判断那是天然地形还是玩家建筑
    names = {}
    for r in groups["B_up_blocked"]:
        names[r["up"]] = names.get(r["up"], 0) + 1
    if names:
        print("B 组「上方方块」名字统计（天然地形 = 岛缘阶梯；玩家方块 = 建筑）：")
        for k, v in sorted(names.items(), key=lambda kv: -kv[1]):
            print("   %-46s %d" % (k, v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
