#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""switch_plan_test.py -- ★切换计划的判据★（P1~P4 ✓ 全离线 ✓ 注入 ✓ 2026-10-04）"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import switch_plan as SP  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== switch_plan_test：P1~P4 ==")
check("P1", SP.advise(100, 80, 20, 0) == "★先切✗★",
      "★准备度高 ＋ 风险低 ⇒ 先切✗★ ⇒ {}".format(SP.advise(100, 80, 20, 0)))
check("P2", SP.advise(100, 45, 55, 0) == "★先看清✗★",
      "★风险 > 50% ⇒ **先看清**（★不许跳 ✗ 见 §79.122 的 mcwdoors✓★）✗★ ⇒ {}"
      .format(SP.advise(100, 45, 55, 0)))
check("P3", SP.advise(100, 10, 10, 90) == "★等导出覆盖✗★",
      "★表中无 > 50% ⇒ 等覆盖（★切了也没依据✓★）✗★ ⇒ {}"
      .format(SP.advise(100, 10, 10, 90)))
check("P4", SP.advise(100, 60, 35, 5) == "可切",
      "★两头都不极端 ⇒ 可切✗★ ⇒ {}".format(SP.advise(100, 60, 35, 5)))
print("=> switch_plan %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
