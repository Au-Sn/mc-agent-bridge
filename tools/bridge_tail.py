#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bridge_tail.py — 看"我下发的指令到底回传了什么"，并与游戏日志对照

为什么需要它：
  验证机器人行为时，最容易犯的错是只看一侧证据——
  只看桥接回传，可能被自己代码的 bug 骗（例如 pcall 吞掉了输出表）；
  只看游戏现象，又不知道是哪条指令造成的。两侧一起看才叫证据。

用法：
    py tools/bridge_tail.py                     # 最近 12 条带 result 的回传
    py tools/bridge_tail.py --who cmd0 -n 6     # 只看某台机器
    py tools/bridge_tail.py --grep TOKEN        # 顺便在游戏日志里找这个字符串
    py tools/bridge_tail.py --all               # 连心跳也显示
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys, paths as PA
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BRIDGE = str(PA.BRIDGE_DIR)
GAME_LOGS = str(PA.MC_LOG_DIR)


def log_files() -> list[str]:
    """
    按"从旧到新"的顺序返回所有桥接日志文件，含轮转出来的 log.jsonl.1 / .2 ...

    为什么必须带上轮转文件：
      log.jsonl 会滚动，而心跳极其频繁（cc0 每秒 4 条），所以**刚刚执行完的指令
      常常已经被挤进 log.jsonl.1**。只看 log.jsonl 就会得出"指令没回传 / 没执行"
      的错误结论。这个坑已经踩过两次（一次误判成"文件桥没开"，一次误判成
      "补给失败"），所以这里一次性修死。
    """
    cur = os.path.join(BRIDGE, "log.jsonl")
    rots = []
    for p in glob.glob(cur + ".*"):
        m = re.search(r"\.(\d+)$", p)
        if m:
            rots.append((int(m.group(1)), p))
    rots.sort(key=lambda t: -t[0])           # 数字越大越旧
    return [p for _, p in rots] + ([cur] if os.path.isfile(cur) else [])


def read_all_lines() -> tuple[list[str], list[str]]:
    files = log_files()
    out: list[str] = []
    for p in files:
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                out.extend(fh.read().splitlines())
        except Exception:
            pass
    return out, files


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", help="只看某台机器（cc0 / cmd0 / ...）")
    ap.add_argument("-n", type=int, default=12, help="显示条数")
    ap.add_argument("--all", action="store_true", help="连心跳一起显示")
    ap.add_argument("--grep", help="在游戏 latest.log 里查找该字符串")
    ap.add_argument("--grep-ctx", type=int, default=0, help="grep 命中行前后各保留几行")
    args = ap.parse_args(argv)

    lines, files = read_all_lines()
    if not lines:
        print("[X] 桥接日志为空或找不到（%s）" % os.path.join(BRIDGE, "log.jsonl"))
        return 1

    print("=" * 74)
    print("桥接回传（%s）" % ("全部" if not args.who else args.who))
    print("来源 %d 个日志文件（含轮转）：%s"
          % (len(files), ", ".join(os.path.basename(p) for p in files)))
    print("-" * 74)
    shown = 0
    for raw in reversed(lines):
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if args.who and d.get("who") != args.who:
            continue
        data = d.get("data") or {}
        interesting = ("result" in data) or ("ok" in data) or d.get("kind") in ("push", "next")
        if not args.all and not interesting:
            continue
        tag = time.strftime("%H:%M:%S", time.localtime(d.get("ts", 0)))
        print("%s %-6s %-6s %s" % (tag, d.get("kind"), d.get("who"),
                                   json.dumps(data, ensure_ascii=False)[:600]))
        shown += 1
        if shown >= args.n:
            break
    if shown == 0:
        print("  （没有匹配的回传——指令可能还没被取走，或 who 名字不对）")

    # 队列深度：能立刻回答"指令卡在网关还是卡在机器上"
    st = os.path.join(BRIDGE, "state.json")
    if os.path.isfile(st):
        try:
            snap = json.load(open(st, encoding="utf-8"))
            age = time.time() - snap.get("ts", 0)
            print("-" * 74)
            print("state.json 年龄 %.1f 秒，队列 %s" % (age, snap.get("queues")))
        except Exception as e:
            print("  （state.json 读取失败：%r）" % (e,))

    if args.grep:
        print("-" * 74)
        path = os.path.join(GAME_LOGS, "latest.log")
        txt = open(path, "r", encoding="utf-8", errors="replace").read().splitlines()
        hits = [i for i, l in enumerate(txt) if args.grep.lower() in l.lower()]
        print("游戏日志中 %r 命中 %d 行" % (args.grep, len(hits)))
        for i in hits[:20]:
            lo = max(0, i - args.grep_ctx)
            hi = min(len(txt), i + args.grep_ctx + 1)
            for j in range(lo, hi):
                mark = ">>" if j == i else "  "
                print("   %s L%-6d %s" % (mark, j + 1, txt[j][:190]))
        if not hits:
            print("    （没命中 → 这条指令没有在游戏里产生任何痕迹，说明它没真正执行）")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
