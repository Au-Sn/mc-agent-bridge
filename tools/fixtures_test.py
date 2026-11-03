#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixtures_test.py -- ★★测试件清单／快照／复原／复核 的判据✗★★（欠账 ⑦ 第 2 层 ✓ 离线 ✓）

判据（★先写死✗★）
  F1 ★快照只记非空气✗★（★空气是默认 ✗ 记满会淹掉真信息✓★）
  F2 ★计划**最小**✗★：★一模一样的格子 ⇒ **不进 ops**✗★
  F3 ★挖／放两种都出得来✗★（★被挖掉的 ⇒ dig ✗ 被改动的 ⇒ place ✓★）
  F4 ★★异动必须可见✗★★：★快照里是空气 ✗ 后来有东西 ⇒ 标 `foreign` ✗ **不自动进 ops**✗★
  F5 ★复核只认世界真值✗★：★改回原样 ⇒ `verify` 空 ✗ 还差一格 ⇒ 报出来✓★
  F6 ★清单✗★：★加一件 ⇒ 读得回来 ✓ 重名 ⇒ **抛**✗（★不许静默覆盖✓★）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import fixtures as F  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


BOX = {"x0": 1, "x1": 3, "y0": 1, "y1": 1, "z0": 1, "z1": 1}
world = {F.key(1, 1, 1): "cobble", F.key(2, 1, 1): "torch"}


def scan(x, y, z):
    return world.get(F.key(x, y, z), "air")


print("== fixtures_test：快照／复原／复核 F1~F6 ==")
snap = F.snapshot(scan, BOX)
# ★F1 改口径✗★（2026-10-02 ✓ 被 F3 逼出来的）：★快照必须记**全部**格子（含空气✗★）——
#   ★只记非空气 ⇒ "该挖哪一格"**永远推不出来**✗（★空气没被记 ⇒ 要挖的只会被当成异动✓★）
check("F1", len(snap) == 3 and snap[F.key(3, 1, 1)] == "air",
      "记**全部** 3 格 ✓（含空气 ✓ 不然「该挖」没有依据 ✗）")

ops, foreign = F.plan_restore(snap, scan, BOX)
check("F2", ops == [] and foreign == [], "一样的格子不进计划 ✓")

world[F.key(1, 1, 1)] = "air"          # ★被挖掉 ⇒ 要**放回去**✗★
world[F.key(3, 1, 1)] = "dirt"         # ★本来是空气 ⇒ 要**挖掉**✗★
ops, _ = F.plan_restore(snap, scan, BOX)
by = {o["at"]: o["op"] for o in ops}
check("F3", by.get(F.key(1, 1, 1)) == "place" and by.get(F.key(3, 1, 1)) == "dig",
      "被挖 ⇒ **place**（放回去 ✓）✗ 本来空的被占 ⇒ **dig** ✓（%s ✓）" % ops)

ops, foreign = F.plan_restore(snap, scan, BOX)
fo = [o for o in ops if o.get("foreign")]
check("F4", len(foreign) == 1 and len(fo) == 1 and fo[0]["at"] == F.key(3, 1, 1),
      "★异动**标出来**（op 上带 foreign ✗ 也在 foreign 清单里✗）★（%s ✓）"
      % foreign[0]["why"][:34])

world[F.key(1, 1, 1)] = "cobble"
world[F.key(2, 1, 1)] = "torch"
world.pop(F.key(3, 1, 1), None)
check("F5", F.verify(snap, scan, BOX) == [], "复原后复核为空 ✓")
world[F.key(2, 1, 1)] = "air"
bad = F.verify(snap, scan, BOX)
check("F5b", len(bad) == 1 and bad[0]["want"] == "torch", "★还差一格 ⇒ 报出来✗★（%s ✓）" % bad[0])

mp = ROOT / "tmp" / "_fixtures_probe.json"
if mp.exists():
    mp.unlink()
F.add_fixture("校准网格", BOX, "§79.8 ✓", "bot", mp)
got = F.list_fixtures(mp)
dup = False
try:
    F.add_fixture("校准网格", BOX, "重复 ✓", "bot", mp)
except RuntimeError:
    dup = True
check("F6", len(got) == 1 and got[0]["id"] == "校准网格" and dup,
      "加了读得回来 ✓ 重名 ⇒ 抛 ✓（★不静默覆盖✗★）")
mp.unlink()
print("=> fixtures %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
