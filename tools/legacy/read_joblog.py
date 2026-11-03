#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""read_joblog.py — 读 CC 电脑自己写的作业日志（不依赖网络回传）

为什么需要它：作业的**回传可能丢失**（重启、崩溃、队列表述异常），
但机器上的文件是**磁盘事实**。这轮就是靠它才第一次拿到了"作业真的跑到哪一步"。
用法：
    py tools/read_joblog.py            # 读 2 号机（指令电脑）
    py tools/read_joblog.py 0 10       # 读 0 号机的最后 10 行
"""
from __future__ import annotations
import glob, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ★历史脚本：环境事实只从 paths 来（★没配 dsh.env 就**明确报错** ✗ 不猜本机存档路径✗★）
_TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_TOOLS))
import paths as PA  # noqa: E402
try:
    SAVE = PA.require_save_dir()
except PA.NotConfigured as exc:              # ★明确报错 ✗ 不用本机路径✗★
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)


def main(argv):
    cid = argv[0] if argv else "2"
    n = int(argv[1]) if len(argv) > 1 else 14
    pats = glob.glob(str(SAVE / "computercraft" / "computer" / cid / "job.log"))
    if not pats:
        print("（id %s 上没有 job.log）" % cid)
        return 1
    lines = open(pats[0], encoding="utf-8", errors="replace").read().splitlines()
    print("job.log  (%s)  共 %d 行：" % (pats[0], len(lines)))
    for l in lines[-n:]:
        print("  " + l[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
