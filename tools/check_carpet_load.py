#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_carpet_load.py — 重启游戏后，从日志里客观判定 Carpet 是否真的加载成功

为什么要有这个脚本：
  装模组的最大风险不是"装不上"，而是"装上了但和 308 个模组里的某一个打架"。
  那种失败常常表现为 mixin 应用失败或某处抛异常，游戏可能还能进，
  后面某次操作才突然崩。所以必须直接读日志，而不是靠"能进游戏"就下结论。

用法：
    py tools/check_carpet_load.py              # 检查最新会话
    py tools/check_carpet_load.py --since 15:20  # 只看该时刻之后写入的日志

判定标准（全部来自日志原文，不做推断）：
  [1] 日志是不是一次"新会话"（mtime 与首行时间）
  [2] forge-carpet 是否被 Forge 认到（版本行）
  [3] 是否有 mixin 应用失败（carpet 相关或其他）
  [4] 是否出现新的 crash-report
  [5] 世界是否加载完成
"""

from __future__ import annotations

import argparse
import os
import re
import sys, paths as PA
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE = str(PA.MC_HOME)

# 需要重点提取的证据行（正则，全部大小写不敏感）
PATTERNS = [
    ("模组数",        re.compile(r"Loading (\d+) mods", re.I)),
    ("Forge 就绪",     re.compile(r"Forge mod loading.*took", re.I)),
    ("carpet 版本",    re.compile(r"(forge-?carpet|carpet)[^\n]{0,120}", re.I)),
    ("mixin 失败",     re.compile(r"Mixin apply[^\n]*fail[^\n]*", re.I)),
    ("mixin 异常",     re.compile(r"(Critical injection failure|InvalidMixinException|MixinTransformerError)[^\n]*", re.I)),
    ("假人相关",       re.compile(r"(fake ?player|EntityPlayerMPFake|/player )[^\n]{0,120}", re.I)),
    ("规则加载",       re.compile(r"(Carpt?et[^\n]{0,80}(rule|setting|config)[^\n]{0,80})", re.I)),
    ("世界加载完成",   re.compile(r"(Preparing spawn area|Loaded \d+ advancements|Time elapsed)", re.I)),
    # 这一条是 /player 是否真的生效的铁证：Carpet 假人是服务端真实玩家实体，
    # 它上线时走的是原版登录流程，日志里必然出现登录行。
    # 注意：中文客户端会把 "joined the game" 本地化成"加入了游戏"，只按英文匹配会漏检（踩过）。
    ("玩家上下线",     re.compile(r"(logged in with entity id|joined the game|加入了游戏|logged out)", re.I)),
    ("严重错误",       re.compile(r"^\[[^\]]*\][^\n]*\b(ERROR|FATAL)\b[^\n]{0,160}", re.I)),
]

INTERESTING_ERROR = re.compile(
    r"(carpet|fakes|EntityPlayerActionPack|PlayerCommand)", re.I
)


def newest(paths):
    best = None
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if best is None or m > best[0]:
            best = (m, p)
    return best


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="只看 HH:MM[:SS] 之后写入的日志（今天）")
    ap.add_argument("--log", help="直接指定日志文件")
    ap.add_argument("--grep", help="额外正则，打印匹配行")
    args = ap.parse_args(argv)

    logdir = os.path.join(BASE, "logs")
    if args.log:
        log = args.log
    else:
        # 默认用 latest.log：它是"给人看"的那份，模组加载/世界加载的关键行都在里面。
        # debug.log 更详细但每秒都在写，按 mtime 取最新会永远选中它（踩过一次）。
        main_log = os.path.join(logdir, "latest.log")
        if os.path.isfile(main_log):
            log = main_log
        else:
            hit = newest([os.path.join(logdir, f) for f in os.listdir(logdir) if f.endswith(".log")])
            if not hit:
                print("[X] 找不到日志文件：%s" % logdir)
                return 1
            log = hit[1]

    mt = os.path.getmtime(log)
    print("=" * 74)
    print("日志      : %s" % log)
    print("最后写入  : %s（%d 字节）" % (time.strftime("%m-%d %H:%M:%S", time.localtime(mt)), os.path.getsize(log)))
    print("当前时间  : %s" % time.strftime("%m-%d %H:%M:%S"))

    with open(log, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    lines = text.splitlines()
    print("行数      : %d" % len(lines))
    print("-" * 74)

    # [1] 新会话判定：日志里最后一次 "Starting up"/"Loading Minecraft" 的位置
    starts = [i for i, l in enumerate(lines) if re.search(r"(Starting up|Loading Minecraft|Environment:)", l, re.I)]
    print("[1] 会话标记（最后 3 处）：")
    for i in starts[-3:]:
        print("      L%-7d %s" % (i + 1, lines[i][:150]))
    if not starts:
        print("      （没找到，可能是 debug 日志或文件被截断）")

    # [2][3][5] 关键证据
    print("-" * 74)
    hits = {name: [] for name, _ in PATTERNS}
    for name, rx in PATTERNS:
        for i, l in enumerate(lines):
            m = rx.search(l)
            if m:
                hits[name].append((i + 1, m.group(0).strip()[:190]))
    for name, _ in PATTERNS:
        got = hits[name]
        print("[%s] %d 条" % (name, len(got)))
        for ln, txt in got[:6 if name != "carpet 版本" else 12]:
            print("      L%-7d %s" % (ln, txt))
        if len(got) > 6 and name != "carpet 版本":
            print("      … 其余 %d 条略" % (len(got) - 6))

    # [4] 新崩溃报告
    print("-" * 74)
    crdir = os.path.join(BASE, "crash-reports")
    new_crash = []
    if os.path.isdir(crdir):
        for f in os.listdir(crdir):
            p = os.path.join(crdir, f)
            try:
                if os.path.getmtime(p) >= mt - 60:
                    new_crash.append((os.path.getmtime(p), f))
            except OSError:
                pass
    print("[4] 与本次日志同时段的崩溃报告：%d 个" % len(new_crash))
    for t, f in sorted(new_crash):
        print("      %s  %s" % (time.strftime("%m-%d %H:%M:%S", time.localtime(t)), f))
    if not new_crash:
        print("      （无 → 这次启动没有生成崩溃报告）")

    # 与 carpet/假人 有关的错误行（最关键：有则说明真的打架了）
    print("-" * 74)
    bad = [(i + 1, l) for i, l in enumerate(lines)
           if INTERESTING_ERROR.search(l) and re.search(r"(ERROR|FATAL|Exception|fail)", l, re.I)]
    print("[!] 与 carpet/假人路径相关的报错：%d 条" % len(bad))
    for ln, l in bad[:20]:
        print("      L%-7d %s" % (ln, l[:190]))
    if not bad:
        print("      （无）")

    if args.grep:
        rx = re.compile(args.grep, re.I)
        print("-" * 74)
        print("[grep] %s" % args.grep)
        n = 0
        for i, l in enumerate(lines):
            if rx.search(l):
                print("      L%-7d %s" % (i + 1, l[:190]))
                n += 1
                if n >= 40:
                    print("      … 截断")
                    break
        if n == 0:
            print("      （无匹配）")

    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
