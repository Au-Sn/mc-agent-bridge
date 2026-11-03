#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ascii_machine_test.py -- 机器那一行必须纯 ASCII（A1~A4 离线 2026-10-13 §79.240）

用户裁决 D3：面向机器的输出必须纯 ASCII（logs／回执／判据结论行）；人读的文档保持现状。
★口径✗★：★不是把中文删掉✗★ —— ★中文那行保留 ✗ 另加**纯 ASCII** 那一行✗★ ✓
  （★这样"人读的"与"机器读的"**各有一行** ✗ 谁也不用迁就谁✓★）
★A2 看的是**真跑出来的日志首行**✗★（★不是看源码里写了什么 ✗
  因为"写了"与"真产出了"是两件事 ✓ 见 §79.213 那条口径✓★）✗★ ✓
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


def ascii_only(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except Exception:
        return False


print("== ascii_machine: A1~A4 ==")

# A1 ★源码里**有**那条机器行** ✗ 而且它的**字面**是 ASCII
# ★2026-10-18（★P0-3✗★）✗★：★`missing=N` 追加在 `total=` **之后**（★现有那些前缀匹配的
#   解析器不会断 ✓ 而这里带 `$` 的正则**必须**跟着改✓★）✗★ ✓
src = (ROOT / "tools" / "check_all.py").read_text(encoding="utf-8", errors="replace")
m = re.search(r'SUMMARY pass=%d fail=%d inconclusive=%d total=%d missing=%d', src)
check("A1", bool(m),
      "源码里有 `SUMMARY pass=… fail=… inconclusive=… total=… missing=…` 那条机器行")

# A2 ★真跑出来的日志**首行**是不是那条 ✗ 且纯 ASCII
log = ROOT / "logs" / "check_all.txt"
first = ""
if log.is_file():
    first = (log.read_text(encoding="utf-8", errors="replace").splitlines() or [""])[0]
check("A2", bool(re.match(r"^SUMMARY pass=\d+ fail=\d+ inconclusive=\d+ total=\d+ missing=\d+$",
                          first))
      and ascii_only(first),
      "日志首行 ＝ %r（★纯 ASCII✗★：%s）" % (first[:70], ascii_only(first)))

# A3 ★日志里**逐条行**允许带中文（★那是人读的✓★）✗ 但机器行不许
lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.is_file() else []
machine = [l for l in lines if l.startswith("SUMMARY ")]
check("A3", bool(machine) and all(ascii_only(l) for l in machine),
      "日志里所有 `SUMMARY ` 行纯 ASCII（★%d 行✗★）✗ 其余行**允许**中文（★人读✓★）"
      % len(machine))

# A4 ★计数器✗★：日志非空 ＋ 逐条行数 ≥ 1（★别拿空日志冒充"检查过"✗★）
check("A4", len(lines) > 5, "日志 %d 行（★不是空的✗★）" % len(lines))

print("=> ascii_machine %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
