#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_ring.py — 用**回传里的 survey 结果**逐格核对一份锁定清单（验收工具）

为什么必须这样验收（本项目铁律 2 + 教训 D2/D3）：
  · 海龟/作业的**自报成功不算证据** ✗ —— 只有"读世界"算 ✓；
  · 但世界存档 region 文件**会滞后** ✗（刚放的方块常常还没落盘：本轮实测 80 格清单里
    磁盘只认了 36 格实心，而世界里其实已经放了 64 格）→ 磁盘版本**不能**用作验收 ✓；
  · 逐格发 block_state 又会把几十条回传灌进上下文 ✗ → 正解是**让脚本读日志**、
    只把结论（哪些格还是空气）打出来 ✓。

做法：扫描 bridge/log.jsonl(+.1)，取**最新的那一批** y 恒定的 survey 结果（radius_y=0），
      把其中出现的空气格合并成一张表，再与锁定清单比对。

用法：
    py tools/verify_ring.py                       # 默认核对 build/ring_cells_full.json（原始 80 格）
    py tools/verify_ring.py --cells build/ring_cells_full.json --y 70 --want solid
    py tools/verify_ring.py --fresh 600           # 只看最近 600 秒内的 survey（避免混入旧数据）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = [os.path.join(BASE, "bridge", "log.jsonl.1"), os.path.join(BASE, "bridge", "log.jsonl")]


def load_log():
    out = []
    for p in LOGS:
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default=os.path.join("build", "ring_cells_full.json"))
    ap.add_argument("--y", type=int, default=70)
    ap.add_argument("--want", default="solid", choices=["solid", "air"])
    ap.add_argument("--fresh", type=float, default=1800, help="只看最近 N 秒内的 survey")
    args = ap.parse_args(argv)

    cpath = args.cells
    if not os.path.isabs(cpath):
        cpath = os.path.join(BASE, cpath)
    with open(cpath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    cells = data if isinstance(data, list) else data.get("cells", [])
    want = [(int(c["x"]), int(c["z"])) for c in cells]

    now = time.time()
    air = {}
    scanned_boxes = []
    used = 0
    # ⚠ 必须**按时间顺序**逐次 survey 覆盖，而且"这一批 air"要先**清掉同格的旧结论** ✓。
    #   踩过的坑：早先把所有批次的空气格**并集**起来 ✗ —— 于是"改造前是空气、改造后是实心"
    #   的格子永远停在"空气"状态 ✓，验收结论直接判错 ✗（本轮实测：真值 79/80，工具报 64/80 ✗）。
    entries = [e for e in load_log() if isinstance((e.get("data") or {}).get("result"), dict)]
    entries.sort(key=lambda e: float(e.get("ts") or 0))
    for e in entries:
        d = e.get("data") or {}
        res = d.get("result")
        if not isinstance(res, dict):
            continue
        if now - float(e.get("ts") or 0) > args.fresh:
            continue
        box = res.get("box")
        if not isinstance(box, dict):
            continue
        if box.get("y0") != args.y or box.get("y1") != args.y:
            continue
        if res.get("capped"):
            print("⚠ 有一次 survey 被截断（capped=true），结果可能不完整：%s" % box)
        if res.get("failed"):
            print("⚠ 有一次 survey 有失败块：%s" % res.get("failed"))
        used += 1
        scanned_boxes.append((box, res.get("scanned"), res.get("counts")))
        # 先清掉这一批覆盖范围内的旧结论，再写入本批的 air
        for key in [k for k in air if box["x0"] <= k[0] <= box["x1"] and box["z0"] <= k[1] <= box["z1"]]:
            del air[key]
        for b in res.get("blocks") or []:
            if b.get("name") == "minecraft:air":
                air[(int(b["x"]), int(b["z"]))] = True

    print("参与核对的最新 survey：%d 次（最近 %.0f 秒内，y=%d）" % (used, args.fresh, args.y))
    for box, scanned, counts in scanned_boxes:
        print("   box x%d..%d z%d..%d  扫描 %s 格  counts=%s"
              % (box["x0"], box["x1"], box["z0"], box["z1"], scanned, counts))

    def covered(x, z):
        for box, _s, _c in scanned_boxes:
            if box["x0"] <= x <= box["x1"] and box["z0"] <= z <= box["z1"]:
                return True
        return False

    still_air, now_solid, unseen = [], [], []
    for (x, z) in want:
        if (x, z) in air:
            still_air.append((x, z))
        elif covered(x, z):
            now_solid.append((x, z))
        else:
            unseen.append((x, z))

    total = len(want)
    ok = len(now_solid) if args.want == "solid" else len(still_air)
    print()
    print("清单 %d 格：实心 %d，仍是空气 %d，未被任何 survey 覆盖 %d"
          % (total, len(now_solid), len(still_air), len(unseen)))
    if still_air:
        print("仍是空气（=未完成）：")
        for c in still_air:
            print("   (%d,%d)" % c)
    if unseen:
        print("未被覆盖（要补一次 survey）：")
        for c in unseen:
            print("   (%d,%d)" % c)
    print()
    print("结论：%s（目标 %s；实心 %d/%d）"
          % ("通过 ✓" if (ok == total and not unseen) else "未通过 ✗",
             "全实心" if args.want == "solid" else "全空气", ok, total))
    return 0 if (ok == total and not unseen) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
