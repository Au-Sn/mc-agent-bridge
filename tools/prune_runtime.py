#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prune_runtime.py -- 给**运行痕迹**定个生命周期 ✓（2026-09-29 用户审计提出 ✓）

WHY（用户原话 ✓）：「`bridge/processed/` 堆积了 801 个 JSON —— 定个生命周期：N 天后归档或删除」
  ★为什么必须有人管它 ✗：这类文件**每天长一点** ✗ 而且**没人会想起来删** ✗
    ⇒ 一年后：仓库里 3 万个 json ✗、`git status` 一片红 ✗、"哪些是证据 ✓ 哪些是垃圾 ✗"分不清 ✓
  ★口径★ ✗：
    · **运行痕迹**（本次/上次跑留下的中间产物 ✓）⇒ **按天清理** ✓（默认 7 天 ✓）
    · **证据**（判据要引用、事故要复盘 ✓ 例如 `logs/check_*.log` ✓ `obstacles.json` ✓
      `block_shapes.json` ✓ `verified_boxes.json` ✓ `walk_progress.json` ✓）⇒ ★**一律不动**✗★
    · 删除前**先报数** ✓ 并支持 `--dry`（默认就是 dry ✓ 要真删得写 `--yes` ✓）

用法 ✓：
  py tools/prune_runtime.py                 # 只报（dry ✓ 默认 ✓）
  py tools/prune_runtime.py --days 3        # 换天数 ✓ 还是只报 ✓
  py tools/prune_runtime.py --yes           # 真删 ✓（只删白名单目录里的、超过 N 天的 ✓）
  py tools/prune_runtime.py --index         # 另外生成一份"会话索引"草稿 ✓（时间/目录/大小 ✓）
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ★白名单：**只清这些**（运行痕迹 ✓）✗ 别的目录一律不碰 ✓
TARGETS = [
    ("bridge/processed", "网关处理过的原始报文（运行痕迹 ✓ 不是证据 ✗）"),
    ("logs/runs", "每次跑的临时目录（运行痕迹 ✓）"),
    ("tmp", "临时目录（运行痕迹 ✓）"),
]
# ★黑名单：**就算在目标目录里也不许删** ✗（写死 ✓ 免得手滑 ✗）
KEEP_NAMES = ("obstacles.json", "block_shapes.json", "verified_boxes.json",
              "walk_progress.json", "check_all.txt")


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, u)
        n /= 1024
    return "%.1f TB" % n


def survey(days: float):
    now = time.time()
    rows = []
    for rel, why in TARGETS:
        d = ROOT / rel
        if not d.is_dir():
            continue
        old, fresh, total, size = [], 0, 0, 0
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            total += 1
            size += p.stat().st_size
            if p.name in KEEP_NAMES:
                continue
            age_d = (now - p.stat().st_mtime) / 86400.0
            (old if age_d > days else None) or None
            if age_d > days:
                old.append((p, age_d, p.stat().st_size))
            else:
                fresh += 1
        rows.append((rel, why, total, fresh, old, size))
    return rows


def main(argv) -> int:
    days = 7.0
    if "--days" in argv:
        try:
            days = float(argv[argv.index("--days") + 1])
        except Exception:
            pass
    yes = "--yes" in argv
    print("★运行痕迹的生命周期★（阈值 %.0f 天 ✓ %s）"
          % (days, "★真删★" if yes else "只报不删（dry ✓ 加 --yes 才真删 ✓）"))
    rows = survey(days)
    if not rows:
        print("  没有需要管的目录 ✓")
        return 0
    freed = 0
    for rel, why, total, fresh, old, size in rows:
        osz = sum(t[2] for t in old)
        print("  %-18s 共 %d 个 / %s ｜ 超过 %.0f 天 %d 个 / %s ｜ 保留 %d 个"
              % (rel, total, human(size), days, len(old), human(osz), fresh))
        print("     （%s）" % why)
        if yes and old:
            for (p, _a, _s) in old:
                try:
                    p.unlink()
                    freed += 1
                except Exception as e:
                    print("     ★删不掉★ %s（%s）" % (p.name, type(e).__name__))
    if yes:
        print("  => 删了 %d 个文件 ✓" % freed)
    else:
        print("  => 没动任何文件 ✓（要看清单加 --list ✓）")
    if "--list" in argv:
        for rel, _why, _t, _f, old, _s in rows:
            for (p, a, s) in sorted(old, key=lambda t: -t[1])[:30]:
                print("     %.1f 天  %8s  %s" % (a, human(s), p.relative_to(ROOT)))
    if "--index" in argv:
        out = ROOT / "docs" / "_会话索引草稿.md"
        lines = ["# 会话索引（草稿 ✓ 自动生成 ✓）", "",
                 "| 时间 | 目录 | 会话数 | 大小 |", "| --- | --- | --- | --- |"]
        base = Path(os.path.expanduser("~")) / ".dsh" / "sessions"
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if not d.is_dir():
                    continue
                fs = [p for p in d.iterdir() if p.is_file()]
                if not fs:
                    continue
                mt = max(p.stat().st_mtime for p in fs)
                lines.append("| %s | %s | %d | %s |"
                             % (time.strftime("%Y-%m-%d %H:%M", time.localtime(mt)),
                                d.name.replace("~0020", " "), len(fs),
                                human(sum(p.stat().st_size for p in fs))))
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("  => 会话索引草稿写到 %s（★时间/目录/大小 ✓ 主题与结果还没解析 ✗★）"
              % out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
