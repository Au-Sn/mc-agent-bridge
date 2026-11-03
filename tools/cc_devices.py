#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cc_devices.py — 从日志里的 survey 回传中汇总所有 ComputerCraft 设备的位置/名字

为什么需要：
  要布 GPS 网络就得知道"现在哪里已经有什么" ✗（计算机 id、海龟、调制解调器各自在哪 ✓），
  否则新放的主机会和已有设备撞位、或者把 modem 放到不连通的面上 ✓。
  逐条 last_result 读会把几十条回传灌进上下文 ✗ → 让脚本读日志、只打结论 ✓。

用法：
    py tools/cc_devices.py                # 汇总最近 20 分钟内 survey 到的 CC 设备
    py tools/cc_devices.py --fresh 600
"""
from __future__ import annotations

import argparse
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


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", type=float, default=1200)
    args = ap.parse_args(argv)

    now = time.time()
    seen = {}
    surveys = 0
    for p in LOGS:
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                d = e.get("data") or {}
                res = d.get("result")
                if not isinstance(res, dict):
                    continue
                if now - float(e.get("ts") or 0) > args.fresh:
                    continue
                blocks = res.get("blocks")
                if not isinstance(blocks, list):
                    continue
                hit = [b for b in blocks if isinstance(b, dict)
                       and str(b.get("name", "")).startswith("computercraft:")]
                if not hit:
                    continue
                surveys += 1
                for b in hit:
                    seen[(int(b["x"]), int(b["y"]), int(b["z"]))] = b["name"]

    print("聚合了 %d 条含 CC 设备的 survey 回传（最近 %.0f 秒）" % (surveys, args.fresh))
    print("CC 设备 %d 个：" % len(seen))
    for k in sorted(seen, key=lambda t: (t[2], t[0], t[1])):
        print("   x=%-6d y=%-4d z=%-5d %s" % (k[0], k[1], k[2], seen[k]))
    kinds = {}
    for nm in seen.values():
        kinds[nm] = kinds.get(nm, 0) + 1
    print("按类型：")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print("   %-46s %d" % (k, v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
