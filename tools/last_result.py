#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
last_result.py — 打印桥接日志里"最近一条匹配的回传"，全文不截断

为什么需要它：
  bridge_tail.py 会截断长回传，而 NBT 类回传（背包、Pos）恰恰又长又关键——
  被截断的那一段往往正是答案（例如物品列表里到底有没有那颗钻石）。
  这个工具只做一件事：按子串找到最近一条匹配结果，原样全打出来。

用法：
    py tools/last_result.py "Bot Inventory"
    py tools/last_result.py "Bot Inventory" --who=cmd0
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BRIDGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bridge")
ID_RE = re.compile(r'id: "([^"]+)"')


def read_all_lines() -> list[str]:
    """
    读所有桥接日志（含轮转的 log.jsonl.1 / .2 ...），按从旧到新返回。

    为什么：心跳太密（每秒数条），刚执行完的指令往往已经被滚动到 log.jsonl.1。
    只看 log.jsonl 会误判成"指令没回传"。踩过两次，这里修死。
    """
    cur = os.path.join(BRIDGE, "log.jsonl")
    rots = []
    for p in glob.glob(cur + ".*"):
        m = re.search(r"\.(\d+)$", p)
        if m:
            rots.append((int(m.group(1)), p))
    rots.sort(key=lambda t: -t[0])
    out: list[str] = []
    for p in [x for _, x in rots] + ([cur] if os.path.isfile(cur) else []):
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                out.extend(fh.read().splitlines())
        except Exception:
            pass
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    needle = argv[0].lower()
    who = None
    for a in argv[1:]:
        if a.startswith("--who="):
            who = a[6:]

    lines = read_all_lines()
    if not lines:
        print("[X] 桥接日志为空或找不到（%s）" % os.path.join(BRIDGE, "log.jsonl"))
        return 1

    for raw in reversed(lines):
        try:
            d = json.loads(raw)
        except Exception:
            continue
        dd = d.get("data") or {}
        if "result" not in dd:
            continue
        if who and d.get("who") != who:
            continue
        blob = json.dumps(dd, ensure_ascii=False).lower()
        if needle not in blob:
            continue
        res = dd.get("result")
        print("=" * 74)
        print("who=%s  cmd=%s  ok=%s" % (d.get("who"), dd.get("cmd"), dd.get("ok")))
        print("=" * 74)
        if isinstance(res, dict):
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            print(res)
        # 顺手把物品 id 抽出来，省得每次人肉读长串 NBT
        text = json.dumps(res, ensure_ascii=False)
        ids = ID_RE.findall(text)
        if ids:
            print("-" * 74)
            print("物品 id：%d 件" % len(ids))
            for i, x in enumerate(ids):
                print("   [%2d] %s" % (i, x))
        print("=" * 74)
        return 0

    print("没有匹配 %r 的回传" % needle)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
