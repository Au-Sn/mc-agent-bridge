#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ring_path.py — 离线把「绕岛填边界环」算成一条可执行走法（BFS 绕开玩家建筑）

为什么必须离线算（本轮实测教训）：
  · 海龟在 y=71 行走，而**岛内 y=71 全是玩家的建筑** ✗ —— 按曼哈顿距离直线走必被挡死；
  · 岛南 z>=44 是一片**完全空的走廊** ✓（实测 y=71 全空气）→ 绕南边就能从东环走到西环；
  · 海龟没有 GPS ✗，只能推算步数 ✓ → 路线必须是"事先算好、每格唯一确定"的 ✓，
    现场只做"照走 + 每格位置自检" ✓。

算法：在 y=71 的「空气格」上做 BFS，目标格按**最近邻（真实 BFS 距离，不是直线距离）**排序，
      逐段输出 {t="f",d=方向,n=步数} 与 {t="p",x=,z=}（放置）。

用法：
    py tools/ring_path.py --start 4119 3 --limit 25
    py tools/ring_path.py --start 4119 3 --limit 25 --offset 0 --out build/ring_path.json
"""
from __future__ import annotations

import argparse
import collections
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

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--y", type=int, default=70, help="目标层（放置层）")
    ap.add_argument("--walk", type=int, default=None, help="行走层，默认 = y+1")
    ap.add_argument("--x0", type=int, default=4095)
    ap.add_argument("--x1", type=int, default=4152)
    ap.add_argument("--z0", type=int, default=-2)
    ap.add_argument("--z1", type=int, default=56)
    ap.add_argument("--start", type=int, nargs=2, required=True, metavar=("X", "Z"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--exclude", nargs="*", default=[],
                    help="已确认完成的格：ring_path 输出的 JSON 或 [{\"x\":..,\"z\":..}] 清单（可给多个）")
    ap.add_argument("--tx0", type=int, default=4100, help="目标窗口（默认与 floor_ring.py 相同）")
    ap.add_argument("--tx1", type=int, default=4150)
    ap.add_argument("--tz0", type=int, default=-12)
    ap.add_argument("--tz1", type=int, default=32)
    ap.add_argument("--targets", default="",
                    help="锁定目标清单（[{\"x\":..,\"z\":..}]）；给了就不再用窗口重算，防止一环比一环外扩")
    ap.add_argument("--open", type=int, nargs=2, action="append", default=[], metavar=("X", "Z"),
                    help="把某格强制当作可通行（磁盘滞后时用；可重复）")
    ap.add_argument("--out", default=r"build\ring_path.json")
    args = ap.parse_args(argv)

    walk = args.walk if args.walk else args.y + 1

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

    def air(x, y, z):
        v = nm(x, y, z)
        return v == "minecraft:air"

    def solid(x, y, z):
        v = nm(x, y, z)
        return v is not None and v != "minecraft:air"

    # 目标格 = floor_ring 的定义（y=70 空、且有实心 4 邻居）
    # ⚠ 目标窗口**独立于**行走图范围：目标就是 floor_ring.py 默认窗口内那 80 格（验收清单 ✓），
    #   而行走图要开得更大 —— 因为绕开玩家建筑必须走岛南 z>=44 的空走廊 ✓。
    #
    # ⚠⚠ 另一条实测教训：**填完第一环后外圈又会冒出新的"环"** ✗（环的定义就是"空且贴着实心"）。
    #   所以要验收的那 80 格必须**锁死成一份清单**（--targets），不能每批重新算，
    #   否则作业会一环比一环往外扩，把方块耗在验收单之外的格子上 ✗。
    if args.targets:
        with open(args.targets, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        cells = data if isinstance(data, list) else data.get("cells", [])
        locked = [(int(c["x"]), int(c["z"])) for c in cells]
        print("目标清单锁定（来自 %s）：%d 格" % (os.path.basename(args.targets), len(locked)))
        targets = [t for t in locked if air(t[0], args.y, t[1])]
        already_solid = [t for t in locked if not air(t[0], args.y, t[1])]
        print("  其中 y=%d 仍是空气（要填）: %d；已经是实心（已完成）: %d"
              % (args.y, len(targets), len(already_solid)))
    else:
        targets = []
        for x in range(args.tx0, args.tx1 + 1):
            for z in range(args.tz0, args.tz1 + 1):
                if not air(x, args.y, z):
                    continue
                if any(solid(x + dx, args.y, z + dz) for dx, dz in DIRS.values()):
                    targets.append((x, z))
        print("目标格（y=%d 边界环，窗口 x%d..%d z%d..%d）: %d"
              % (args.y, args.tx0, args.tx1, args.tz0, args.tz1, len(targets)))

    # 行走图：y=walk 的空气格
    passable = {}
    for x in range(args.x0, args.x1 + 1):
        for z in range(args.z0, args.z1 + 1):
            passable[(x, z)] = air(x, walk, z)

    # ⚠ 实测坑：region 文件是**滞后**的 —— 海龟自己站过的格子会被当成"实心"记在磁盘上，
    #   于是"回到刚才那个格子"会被规划器判成不可达 ✗（真实踩到：(4120,3)）。
    #   给它一个显式开口：--open X Z（可重复），把那些格子强制当作空气 ✓。
    for pair in (args.open or []):
        passable[(pair[0], pair[1])] = True
        print("强制开口：(%d,%d)（磁盘上记的是 %s）" % (pair[0], pair[1], nm(pair[0], walk, pair[1])))

    blocked_target = [t for t in targets if not passable.get(t)]
    targets = [t for t in targets if passable.get(t)]
    print("其中「行走层 (x,%d,z) 是空气」(可到位) : %d" % (walk, len(targets)))
    if blocked_target:
        print("行走层被占、无法从上方放置的目标格 %d 个：" % len(blocked_target))
        for t in blocked_target:
            print("   (%d,%d) 上方 = %s" % (t[0], t[1], nm(t[0], walk, t[1])))

    start = tuple(args.start)
    if not passable.get(start):
        print("⚠ 起点 %s 在行走层不是空气（磁盘数据可能过期 / 海龟自己就在那）: %s"
              % (start, nm(start[0], walk, start[1])))

    done = set()
    for ex in (args.exclude or []):
        if not os.path.isfile(ex):
            print("⚠ 排除文件不存在，忽略：%s" % ex)
            continue
        with open(ex, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        # 两种格式都收：ring_path 输出（{steps:[{t="p",x,z}]}）与纯清单（[{x,z}]）
        if isinstance(data, dict) and "steps" in data:
            cells = [(int(s["x"]), int(s["z"])) for s in data["steps"] if s.get("t") == "p"]
        else:
            cells = [(int(c["x"]), int(c["z"])) for c in data]
        done |= set(cells)
        print("排除（来自 %s）：%d 格" % (os.path.basename(ex), len(cells)))
    if done:
        print("累计排除已确认完成的格：%d" % len(done))
    todo = [t for t in targets if t not in done]
    print("待填目标 %d 格" % len(todo))

    def bfs(src):
        dist = {src: 0}
        prev = {}
        q = collections.deque([src])
        while q:
            cur = q.popleft()
            for d, (dx, dz) in DIRS.items():
                nxt = (cur[0] + dx, cur[1] + dz)
                if nxt in dist or not passable.get(nxt):
                    continue
                dist[nxt] = dist[cur] + 1
                prev[nxt] = (cur, d)
                q.append(nxt)
        return dist, prev

    # 最近邻（真实 BFS 距离）排序，从海龟当前格出发
    order, reach_check = [], []
    cur = start
    while todo:
        dist, _prev = bfs(cur)
        reach = [t for t in todo if t in dist]
        if not reach:
            break
        tgt = min(reach, key=lambda t: dist[t])
        order.append(tgt)
        todo.remove(tgt)
        cur = tgt
    unreachable = list(todo)
    if unreachable:
        print("⚠ BFS 到不了的目标格 %d 个：%s" % (len(unreachable), unreachable[:20]))

    sel_order = order[:(args.limit or len(order))]
    steps, cur, path_moves = [], start, 0
    for tgt in sel_order:
        dist, prev = bfs(cur)
        if tgt not in dist:
            print("⚠ 分批后 (%d,%d) 不可达，跳过" % tgt)
            continue
        path, node = [], tgt
        while node != cur:
            p, d = prev[node]
            path.append((p, d, node))
            node = p
        path.reverse()
        for (_p, d, _n) in path:
            if steps and steps[-1]["t"] == "f" and steps[-1]["d"] == d:
                steps[-1]["n"] += 1
            else:
                steps.append({"t": "f", "d": d, "n": 1})
        steps.append({"t": "p", "x": tgt[0], "z": tgt[1]})
        path_moves += len(path)
        cur = tgt

    print("本批目标 %d 格；行走 %d 步；输出 %d 条动作" % (len(sel_order), path_moves, len(steps)))
    print("本批末格 = %s" % (cur,))
    print("全环可达顺序共 %d 格" % len(order))

    outp = args.out
    os.makedirs(os.path.dirname(os.path.abspath(outp)), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as fh:
        json.dump({"steps": steps, "y": args.y, "walk": walk}, fh, ensure_ascii=False)
    print("已写：%s（%d 字节）" % (os.path.abspath(outp), os.path.getsize(outp)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
