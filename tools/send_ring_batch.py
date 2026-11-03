#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""send_ring_batch.py — 把离线算好的走法（build/ring_path*.json）下发成一条 run_job 指令

为什么单独做成一个工具（教训 A2）：
  把一大坨 JSON 塞进 PowerShell 命令行/内联 Python 会被引号规则吃掉 ✗；
  写成文件、由脚本读文件拼装，才是本项目的标准做法 ✓。

用法：
    py tools/send_ring_batch.py --path build/ring_path_b1.json ^
        --start-x 4119 --start-z 3 --facing north --log ring_run.log
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
INBOX = os.path.join(BASE, "bridge", "inbox")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="ring_path.py 输出的 JSON")
    ap.add_argument("--start-x", type=int, required=True)
    ap.add_argument("--start-z", type=int, required=True)
    ap.add_argument("--facing", default="north")
    ap.add_argument("--job", default="fill_ring.lua")
    ap.add_argument("--log", default="ring_run.log")
    ap.add_argument("--max-moves", type=int, default=800)
    ap.add_argument("--budget-s", type=int, default=150)
    ap.add_argument("--wait-ms", type=int, default=240000)
    ap.add_argument("--who", default="cc0")
    ap.add_argument("--target", type=int, default=1)
    ap.add_argument("--name", default=None)
    args = ap.parse_args(argv)

    with open(args.path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    steps = data["steps"]
    fwd = sum(s.get("n", 0) for s in steps if s.get("t") == "f")
    places = sum(1 for s in steps if s.get("t") == "p")

    spec = {
        "who": args.who,
        "cmd": "run_job",
        "args": {
            "target": args.target,
            "name": args.job,
            "steps": steps,
            "y": data.get("walk", 71),
            "x0": args.start_x,
            "z0": args.start_z,
            "facing": args.facing,
            "log": args.log,
            "max_moves": args.max_moves,
            "budget_s": args.budget_s,
            "wait_ms": args.wait_ms,
        },
    }

    name = args.name or ("RING-%05d.json" % (int(time.time() * 1000) % 100000))
    outp = os.path.join(INBOX, name)
    with open(outp, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False)

    print("下发：%s" % outp)
    print("  作业 %s：%d 条动作（前进 %d 步 / 放置 %d 格）" % (args.job, len(steps), fwd, places))
    print("  起点 (%d,%d) 朝向 %s，行走层 y=%d" % (args.start_x, args.start_z, args.facing, data.get("walk", 71)))
    print("  本机日志 ring_run.log；预算 max_moves=%d budget_s=%d" % (args.max_moves, args.budget_s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
