#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plan_platform.py — 从普查结果里自动测出地表与边缘，生成"在外面搭平台"的投递文件

为什么要有这个脚本（真实教训）：
  我两次"在外面搭平台"都失败了，原因都是**我凭印象填了 Y 坐标**：
  第一次按 y=70 去铺，结果那片早就铺满了（0 铺 0 失败）；第二次按 y=70 放筛子，
  被自己的动作正确地拒绝（目标格已被 chipped:flat_andesite_tiles 占用）。
  基地是多层的，任何"我记得地面在 y=??"都必须换成"从普查数据里测出来"。

做法：
  1. 读桥接日志里最近一次半径足够大的 survey 结果；
  2. 取"实心格数最多的那一层"作为地表高程（不是猜）；
  3. 找与 ≥2 个实心格相邻的空格（= 平台边缘外侧），按到锚点的距离排序；
  4. 以它为中心取 3×3（要求全空），生成投递文件：
     给木板 → 搭平台 → 放筛子 → 装筛网 → 开筛。

用法：
    py tools/plan_platform.py --radius 14 --anchor 4125 70 17
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BRIDGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bridge")
INBOX = os.path.join(BRIDGE, "inbox")


def latest_survey(min_radius=8):
    log = os.path.join(BRIDGE, "log.jsonl")
    lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
    for raw in reversed(lines):
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if d.get("who") != "cmd0":
            continue
        dd = d.get("data") or {}
        if dd.get("cmd") != "survey" or not isinstance(dd.get("result"), dict):
            continue
        r = dd["result"]
        if r.get("radius", 0) >= min_radius and not r.get("capped"):
            return r
    return None


def write(name, obj):
    os.makedirs(INBOX, exist_ok=True)
    with open(os.path.join(INBOX, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=int, default=14)
    ap.add_argument("--anchor", nargs=3, type=int, default=[4125, 70, 17],
                    help="用来排序的锚点（通常是机器人附近）")
    ap.add_argument("--size", type=int, default=3)
    ap.add_argument("--dry", action="store_true", help="只分析，不下发")
    args = ap.parse_args(argv)

    r = latest_survey(min_radius=min(8, args.radius))
    if not r:
        print("[X] 日志里没有足够大的、未截断的 survey 结果，先跑一次：")
        print('    {"who":"cmd0","cmd":"survey","args":{"x":4125,"y":70,"z":20,'
              '"radius":14,"radius_y":1,"only":"","max_list":3000}}')
        return 1

    box = r["box"]
    solid = {}
    for bl in r["blocks"]:
        if bl["name"].endswith("air"):
            continue
        solid[(bl["x"], bl["y"], bl["z"])] = bl["name"]

    print("survey box = %s   returned=%s scanned=%s capped=%s" % (box, r.get("returned"), r.get("scanned"), r.get("capped")))

    # 1) 地表高程：正确定义是"该格实心、且**正上方是空的**"（可行走的顶面），
    #    而不是"实心最多的一层"。真实教训：按"实心最多"判会选中 y=69 基层
    #    （619 格）而不是 y=70 地表（617 格）—— 只差 2 格就把判据带偏了 ✗。
    tops = {}
    for (x, y, z) in solid:
        if (x, y + 1, z) not in solid:
            tops[y] = tops.get(y, 0) + 1
    if not tops:
        print("[X] 这一箱里找不到任何顶面")
        return 1
    print("各层顶面格数：", dict(sorted(tops.items())))
    surface = max(tops, key=lambda y: tops[y])
    print("→ 判定可行走地表 y = %d（%d 格顶面）" % (surface, tops[surface]))

    # 2) 找边缘外侧的空格（与 ≥2 个同层实心格相邻）
    solid_here = {k for k in solid if k[1] == surface}
    ax, _, az = args.anchor
    cands = []
    for x in range(box["x0"], box["x1"] + 1):
        for z in range(box["z0"], box["z1"] + 1):
            if (x, surface, z) in solid_here:
                continue
            n = 0
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + dx, surface, z + dz) in solid_here:
                    n += 1
            if n >= 2:
                cands.append((abs(x - ax) + abs(z - az), x, z, n))
    if not cands:
        print("[X] 没找到边缘外侧的格子（或许这一箱全是实地）")
        return 1
    cands.sort()
    print("边缘候选（距离, x, z, 相邻实心数）前 8：", [c[1:] for c in cands[:8]])

    # 3) 取离锚点最近的候选作为中心。
    #    刻意**不要求** 3×3 全空：build_platform 本身只填空格，
    #    要求全空只会把本来可用的边缘位置全部排除掉（真实踩到：一个都选不出来）。
    cx, cz = cands[0][1], cands[0][2]
    print("→ 平台中心 = (%d, %d, %d)，尺寸 %d×%d（已实心的格子会被自动跳过）"
          % (cx, surface, cz, args.size, args.size))

    # 平台上的第一个格子：离机器人最近的那个，用来放筛子
    half = (args.size - 1) // 2
    cells = [(cx + dx, cz + dz) for dx in range(-half, half + 1) for dz in range(-half, half + 1)]
    cells.sort(key=lambda c: abs(c[0] - ax) + abs(c[1] - az))
    sx, sz = cells[0]
    print("→ 筛子计划放在 (%d, %d, %d)（地面上方一格）" % (sx, surface + 1, sz))
    # 机器人可能离得很远——放置距离只有 4.5 格，所以先走过去
    dist = abs(cx - ax) + abs(cz - az)
    print("→ 机器人与平台中心的曼哈顿距离 = %d 格" % dist)
    if dist > 4:
        print("   （超过 4 格，需要先走位：投递里已包含 walk_to）")

    if args.dry:
        return 0

    n = 0

    def emit(name, obj):
        nonlocal n
        n += 1
        write("%02d-%s" % (n, name), obj)

    emit("walk", {"who": "cmd0", "cmd": "walk_to",
                  "args": {"bot": "Bot", "x": cx, "y": surface + 1, "z": cz,
                           "range": 2.5, "timeout": 60, "clear": True, "max_clear": 8}})
    emit("planks", {"who": "cmd0", "cmd": "give_slot",
                    "args": {"bot": "Bot", "slot": 7, "item": "minecraft:oak_planks", "count": 64}})
    emit("platform", {"who": "cmd0", "cmd": "build_platform",
                      "args": {"bot": "Bot", "x": cx, "y": surface, "z": cz,
                               "size": args.size, "item": "oak_planks"}})
    emit("say", {"who": "cmd0", "cmd": "cmd",
                 "args": {"text": "say [agent] building a platform outside at %d %d %d" % (cx, surface, cz)}})
    emit("sieve", {"who": "cmd0", "cmd": "give_slot",
                   "args": {"bot": "Bot", "slot": 7, "item": "exdeorum:oak_sieve", "count": 1}})
    emit("place", {"who": "cmd0", "cmd": "place_at",
                   "args": {"bot": "Bot", "x": sx, "y": surface, "z": sz, "item": "oak_sieve"}})
    emit("mesh", {"who": "cmd0", "cmd": "give_slot",
                  "args": {"bot": "Bot", "slot": 7, "item": "exdeorum:iron_mesh", "count": 1}})
    emit("install", {"who": "cmd0", "cmd": "install_mesh",
                     "args": {"bot": "Bot", "x": sx, "y": surface + 1, "z": sz, "item": "iron_mesh"}})
    emit("sift", {"who": "cmd0", "cmd": "sift",
                  "args": {"bot": "Bot", "x": sx, "y": surface + 1, "z": sz,
                           "item": "gravel", "seconds": 12}})
    print("已生成 %d 个投递文件到 %s" % (n, INBOX))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
