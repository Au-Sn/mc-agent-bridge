#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mapfind_test.py -- ★`level_ok` 的判据★（M1~M4 ✓ 全离线 ✓ 2026-10-05）

★守住 §79.148 那条口径✗★：★"★列连通★"与"★够得着★"是**两句不同的话**✗★ ⇒
  ★而"★够得着★"里**层高**这条必须**分开算** ✗ 不许被"★列连通★"吞掉✗★ ✓
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mapfind as MF  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== mapfind_test：M1~M4（★层高是不是真的算进去了✗★）==")

check("M1", MF.level_ok(71, 71, 1) and MF.level_ok(72, 71, 1),
      "★同层 ＋ 高 1 层 ⇒ 够得着✗★（★走手只上 1 层✓★）")
check("M2", not MF.level_ok(74, 71, 1),
      "★高 3 层 ⇒ **够不着**✗★（★这正是 §79.148 实测到的那些树叶✓★）")
check("M3", MF.level_ok(70, 71, 1) and MF.level_ok(69, 71, 1) and not MF.level_ok(68, 71, 1),
      "★往下：2 层内够得着 ✗ 3 层就不★（★下落比上爬容易 ✗ 但有上限✓★）")
check("M4", (MF.level_ok(72, 71, 0) is False) and (MF.level_ok(71, 71, 0) is True),
      "★爬升上限 0 ⇒ 只有同层★（★口径随上限走 ✗ 不是写死的 1✓★）")

print("=> mapfind %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
