#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ascii_slice.py — 把某一层（y=常数）的方块画成 ASCII 网格，便于"用眼睛验收"。

为什么需要它（本项目的教训）：
  · PNG 渲染在小区域只有几十像素 ✗，看不清哪一格是洞、哪一格是哪；
  · 而验收的铁律是"看世界真相"✓ —— 所以给一个**逐格可读**的文本视图 ✓，
    直接和 floor_ring.py 的目标格清单对照 ✓。

字符表：
    '#' 实心方块（非空气）        '.' 空气
    '?' 区块不存在 / 读取失败      '~' 非完整方块（草/花瓣/树苗/火把类，不算地面）

用法：
    py tools/ascii_slice.py --y 70
    py tools/ascii_slice.py --y 70 --x0 4115 --x1 4135 --z0 0 --z1 18
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

# 不完整方块（无完整碰撞箱）—— 与 agent_bridge.lua 的 standable 概念一致。
# 这些方块不能当地面/支撑用（用户明确指出的规则 C4）。
# ⚠ 匹配必须**精确到词**：早期版本用 `"grass" in n`，结果把 `grass_block`（**完整方块**）
#    也判成了不完整方块，整张图全是 `~`，几乎误判成"整个岛都不能站" ✗（真实踩到）。
#    现在改为"整名相等 或 以 `_词` / `_词s` 结尾"，并显式排除完整方块。
PARTIAL_WORDS = (
    "grass", "fern", "petal", "petals", "sapling", "torch", "flower", "dandelion",
    "poppy", "bluet", "bush", "vine", "lily", "seagrass", "kelp", "cane",
    "rail", "button", "lever", "tripwire", "carpet", "snow", "azalea",
)
FULL_OVERRIDE = (
    "grass_block", "snow_block", "dirt_path", "farmland", "podzol", "mycelium",
    "moss_block", "carpet_full", "rail_full",
)


def is_partial(name: str) -> bool:
    n = name.split(":")[-1]
    if n in FULL_OVERRIDE:
        return False
    for w in PARTIAL_WORDS:
        if n == w or n.endswith("_" + w) or n.endswith("_" + w + "s"):
            return True
    return False


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--y", type=int, default=70)
    ap.add_argument("--x0", type=int, default=4100)
    ap.add_argument("--x1", type=int, default=4146)
    ap.add_argument("--z0", type=int, default=0)
    ap.add_argument("--z1", type=int, default=34)
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

    names = {}

    def cell(x, z):
        ch = chunks.get((x >> 4, z >> 4))
        if ch is None:
            return "?"
        nm = block_at(ch, x, args.y, z)
        if nm is None:
            return "?"
        if nm == "minecraft:air":
            return "."
        names[(x, z)] = nm
        return "~" if is_partial(nm) else "#"

    # 列号表头（每 10 列一个标记）
    hdr1 = "      " + "".join(
        (str((x // 10) % 10) if x % 10 == 0 else " ") for x in range(args.x0, args.x1 + 1))
    hdr2 = "      " + "".join(
        (str(x % 10) if x % 10 == 0 else " ") for x in range(args.x0, args.x1 + 1))
    print("y=%d   x %d..%d  z %d..%d   （# 实心  . 空气  ~ 不完整方块  ? 未生成）"
          % (args.y, args.x0, args.x1, args.z0, args.z1))
    print(hdr1)
    print(hdr2)
    for z in range(args.z0, args.z1 + 1):
        row = "".join(cell(x, z) for x in range(args.x0, args.x1 + 1))
        print("z=%-4d%s" % (z, row))
    print()

    solid = sum(1 for v in names.values())
    print("实心格 %d；空气格 %d；未生成 %d"
          % (solid,
             sum(1 for z in range(args.z0, args.z1 + 1) for x in range(args.x0, args.x1 + 1)
                 if cell(x, z) == "."),
             sum(1 for z in range(args.z0, args.z1 + 1) for x in range(args.x0, args.x1 + 1)
                 if cell(x, z) == "?")))
    if names:
        cnt = {}
        for nm in names.values():
            cnt[nm] = cnt.get(nm, 0) + 1
        print("方块分布：")
        for k, v in sorted(cnt.items(), key=lambda kv: -kv[1]):
            print("   %-46s %d" % (k, v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
