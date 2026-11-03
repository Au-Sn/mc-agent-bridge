#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jar_strings.py — 从模组 jar 的 class 里提取字符串常量，按关键词过滤

为什么需要它：
  判断"某个模组对假人的行为会怎样"这类问题，靠印象必然出错。而大多数模组的判定逻辑
  会以字符串常量的形式留在字节码里（类名、字段名、配置键、事件名）。把它们挖出来，
  就能直接看到触发条件，而不是猜。

  真实用途举例：
    · FTB Ultimine 到底靠什么触发（按键映射 / 附魔 / 潜行）
    · 某个模组有没有对 fake player 做特殊处理

用法：
    py tools/jar_strings.py <jar路径> "key,enchant,fake"
    py tools/jar_strings.py <jar路径> --all          # 全部字符串（可能很长）

注意：这是**粗筛**，不是反编译。命中只说明"这个字符串在 jar 里出现过"，
      要下结论还得结合上下文（必要时配合游戏内实测）。
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PRINTABLE = re.compile(rb"[\x20-\x7e]{4,}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jar")
    ap.add_argument("keywords", nargs="?", default="", help="逗号分隔的关键词（不区分大小写）")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=90)
    ap.add_argument("--show-class", action="store_true", help="同时显示命中所属的 class")
    ap.add_argument("--class", dest="klass", help="只在类名含该子串的 class 里查找")
    ap.add_argument("--all-strings-of", help="直接打印该类里的全部字符串（不看关键词）")
    args = ap.parse_args(argv)

    z = zipfile.ZipFile(args.jar)
    names = [n for n in z.namelist() if n.endswith(".class")]
    if args.klass:
        names = [n for n in names if args.klass.lower() in n.lower()]
    kws = [k.strip().lower() for k in args.keywords.split(",") if k.strip()]
    print("jar      : %s" % args.jar)
    print("class 数 : %d%s" % (len(names), "（已按 --class 过滤）" if args.klass else ""))

    hits: dict[str, str] = {}
    for n in names:
        try:
            data = z.read(n)
        except Exception:
            continue
        for m in PRINTABLE.findall(data):
            s = m.decode("utf-8", "replace")
            low = s.lower()
            if args.all_strings_of or args.all or any(k in low for k in kws):
                if s not in hits:
                    hits[s] = n

    print("命中     : %d 条\n" % len(hits))
    for s in sorted(hits)[: args.limit]:
        if args.show_class:
            print("  %-300s  <= %s" % (s[:300], hits[s]))
        else:
            print("  " + s[:300])
    if len(hits) > args.limit:
        print("  … 其余 %d 条（用 --limit 调整）" % (len(hits) - args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
