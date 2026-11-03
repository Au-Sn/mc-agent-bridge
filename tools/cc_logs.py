#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cc_logs.py — 直接读游戏内计算机的磁盘文件（这是"磁盘才是可靠通道"的落地工具）

为什么需要它：
  命令计算机 cmd0 一旦关机 ✓ 所有 `/` 指令与 `survey`/`block_state` 全部失效 ✗
  但**游戏内计算机的文件就躺在宿主磁盘上** ✓（`saves/<世界>/computercraft/computer/<id>/` ✓）
  → 只要机器自己往磁盘写日志 ✓ 我们的观测通道就**不依赖任何命令通道** ✓✓
  （本项目已经靠这条原则救过好几次场 ✓）

用法：
    py tools/cc_logs.py                     # 列出每台计算机的文件（名称/大小/修改时间）
    py tools/cc_logs.py 1                   # 看计算机 1（海龟）的所有 *.log 尾部
    py tools/cc_logs.py 1 clean_stray.log   # 看指定文件的尾部
    py tools/cc_logs.py 1 -n 40             # 尾部行数（默认 20）
"""

from __future__ import annotations

import sys, paths as PA
import time
from pathlib import Path

SAVE = PA.SAVE_DIR
CC = SAVE / "computercraft" / "computer"

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def _stamp(ts: float) -> str:
    return time.strftime("%m-%d %H:%M:%S", time.localtime(ts))


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("-")]
    n = 20
    for a in argv:
        if a.startswith("-n"):
            try:
                n = int(a.split("=", 1)[1]) if "=" in a else int(argv[argv.index(a) + 1])
            except Exception:
                pass

    if not CC.is_dir():
        print("[X] 找不到计算机目录：%s" % CC)
        return 1

    if not args:
        for d in sorted(CC.iterdir(), key=lambda p: p.name):
            if not d.is_dir():
                continue
            files = sorted(d.iterdir(), key=lambda p: p.name)
            print("computer/%s  (%d 个文件)" % (d.name, len(files)))
            for f in files:
                if f.is_file():
                    st = f.stat()
                    print("    %-22s %8d B   %s" % (f.name, st.st_size, _stamp(st.st_mtime)))
        return 0

    cid = args[0]
    d = CC / cid
    if not d.is_dir():
        print("[X] 没有这台计算机：%s" % d)
        return 1

    names = [args[1]] if len(args) > 1 else [f.name for f in sorted(d.iterdir())
                                             if f.is_file() and f.suffix == ".log"]
    if not names:
        print("（computer/%s 下没有 *.log ✓ 可用 py tools/cc_logs.py %s 看全部文件）" % (cid, cid))
        return 0
    for name in names:
        p = d / name
        if not p.is_file():
            print("[X] 没有这个文件：%s" % p)
            continue
        st = p.stat()
        print("=" * 70)
        print("computer/%s/%s   %d B   最后写入 %s" % (cid, name, st.st_size, _stamp(st.st_mtime)))
        print("-" * 70)
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            print("  读取失败：%r" % (e,))
            continue
        for ln in lines[-n:]:
            print("  " + ln[:200])
        print("  （共 %d 行）" % len(lines))
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
