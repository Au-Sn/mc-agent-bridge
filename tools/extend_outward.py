#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extend_outward.py — 自动算出"岛屿边缘在哪个方向"，并下发往外扩的作业

为什么要有它：
  1) extend_platform 需要**方向**参数，而方向不能靠我猜——上一次我猜"east"，
     结果机器人在 (4126,70,7)、东边 6 格内全是实地，作业 0.3 秒就诚实地失败 ✓。
     方向必须从普查数据里**算**出来：找出与该层实心格相邻的空格（= 边缘外侧），
     取离机器人最近的那个，方向 = 它相对机器人的主轴向。
  2) 顺带消灭一个反复犯的错误：**把 Python 内联进 PowerShell 会被吃引号** ✗。
     规则：非平凡逻辑一律写成脚本文件，然后用 `py tools/xxx.py` 调用。

用法：
    py tools/extend_outward.py            # 自动定位并下发
    py tools/extend_outward.py --dry      # 只看算出来的方向
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BRIDGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bridge")
INBOX = os.path.join(BRIDGE, "inbox")


def last_big_survey(min_radius=10):
    best = None
    for f in sorted(glob.glob(os.path.join(BRIDGE, "log.jsonl*")), key=os.path.getmtime):
        for raw in open(f, encoding="utf-8", errors="replace").read().splitlines():
            try:
                d = json.loads(raw)
            except Exception:
                continue
            dd = d.get("data") or {}
            r = dd.get("result")
            if (isinstance(r, dict) and dd.get("cmd") == "survey"
                    and r.get("radius", 0) >= min_radius and not r.get("capped")):
                best = (d["ts"], r)
    return best


def last_bot_pos():
    """从最近的 walk_to / sift 结果里取机器人坐标（顺带兜底用 Pos 指令回传）。"""
    pos = None
    for f in sorted(glob.glob(os.path.join(BRIDGE, "log.jsonl*")), key=os.path.getmtime):
        for raw in open(f, encoding="utf-8", errors="replace").read().splitlines():
            try:
                d = json.loads(raw)
            except Exception:
                continue
            dd = d.get("data") or {}
            r = dd.get("result")
            if d.get("who") != "cmd0" or not isinstance(r, dict):
                continue
            if dd.get("cmd") in ("walk_to", "extend_platform") and isinstance(r.get("at"), dict):
                pos = (r["at"]["x"], r["at"]["y"], r["at"]["z"])
    return pos


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--rows", type=int, default=5)
    args = ap.parse_args(argv)

    sv = last_big_survey()
    if not sv:
        print("[X] 没有可用的大范围普查（radius>=10 且未截断）")
        return 1
    _, r = sv
    solid = {(b["x"], b["y"], b["z"]) for b in r["blocks"] if not b["name"].endswith("air")}
    box = r["box"]

    # 地表高程：正上方为空的实心层
    tops = {}
    for (x, y, z) in solid:
        if (x, y + 1, z) not in solid:
            tops[y] = tops.get(y, 0) + 1
    surf = max(tops, key=lambda y: tops[y])

    bp = last_bot_pos()
    if not bp:
        print("[X] 拿不到机器人坐标")
        return 1
    ax, ay, az = int(bp[0]), int(bp[1]), int(bp[2])
    print("机器人位置 = (%d, %d, %d)   地表 y = %d" % (ax, ay, az, surf))

    cands = []
    for x in range(box["x0"], box["x1"] + 1):
        for z in range(box["z0"], box["z1"] + 1):
            if (x, surf, z) in solid:
                continue
            n = sum(1 for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)) if (x + dx, surf, z + dz) in solid)
            if n >= 2:
                cands.append((abs(x - ax) + abs(z - az), x, z, n))
    if not cands:
        print("[X] 这一箱里找不到边缘外侧空格")
        return 1
    cands.sort()
    print("最近边缘候选:", [(c[1], c[2], c[3]) for c in cands[:6]])
    _, cx, cz, n = cands[0]
    dx, dz = cx - ax, cz - az
    direction = ("east" if dx > 0 else "west") if abs(dx) >= abs(dz) else ("south" if dz > 0 else "north")
    print("→ 目标边缘 (%d, %d, %d) 相邻实心 %d；方向 = %s" % (cx, surf, cz, n, direction))
    if args.dry:
        return 0

    os.makedirs(INBOX, exist_ok=True)
    jobs = [
        ("70-walk", {"who": "cmd0", "cmd": "walk_to",
                     "args": {"bot": "Bot", "x": cx, "y": surf + 1, "z": cz,
                              "range": 2.0, "timeout": 60, "clear": True}}),
        ("71-planks", {"who": "cmd0", "cmd": "give_slot",
                       "args": {"bot": "Bot", "slot": 7, "item": "minecraft:oak_planks", "count": 64}}),
        ("72-extend", {"who": "cmd0", "cmd": "extend_platform",
                       "args": {"bot": "Bot", "dir": direction, "rows": args.rows,
                                "item": "oak_planks", "budget": 150}}),
    ]
    for nm, obj in jobs:
        with open(os.path.join(INBOX, nm + ".json"), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
            fh.write("\n")
    print("已下发 %d 条：走位 → 给木板 → 往外扩 %s %d 行" % (len(jobs), direction, args.rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
