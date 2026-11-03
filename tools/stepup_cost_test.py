#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stepup_cost_test.py -- ★"能绕平路就绕"的判据（★离线 ✗ 合成世界✗★）（§79.420）

★★背景✗★★：★模组 walker 的「上 1 格台阶」还不稳（★§79.419 的死锁✗★）✗★
　★而 `COST["step_up"]` 原来是 **2.0** ⇒ ★正好等于绕 **2 步平路**
　★⇒ ★A* **打平时会选 step_up** ⇒ ★出**没必要的台阶**✗★ ✓
★★本判据（★四条 ✗ 全部离线✗★）✗★：
　★① ★代价关系✗★：★`step_up / walk > 2`**（★宁可绕 2 步也不上台阶✗★）✗★
　★② ★合成世界里有台阶的路**仍能规划出来**（★不因贵而"没路"✗★）✗★
　★③ ★`pillar` 语义没坏**（★坑里能垫上来✗★）✗★
　★④ ★`bridge` 语义没坏**（★缺口能铺过去✗★）✗★ ✓
★复用✗★：★`bridge_unit_test.Fake`**（★§79.383 验过的合成世界 ✗ 不自己造✗★）✗★ ✓
"""
from __future__ import annotations

import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import plan3d as P3                              # noqa: E402
from bridge_unit_test import Fake as BaseFake    # noqa: E402


class StepFake(BaseFake):
    """★`Fake` 地板上加一格台阶（★`y=0` 地板 ✗ 脚在 `y=1`✗★）✗★"""

    def h(self, x, y, z):
        if y == 1 and x == 2 and z == 2:
            return 1.0
        return super().h(x, y, z)

    def name(self, x, y, z):
        if y == 1 and x == 2 and z == 2:
            return "minecraft:cobblestone"
        return super().name(x, y, z)


class PitFake(BaseFake):
    """★把一格地板挖掉（★一个坑✗★）✗★"""

    def h(self, x, y, z):
        if y == 0 and x == 2 and z == 2:
            return 0.0
        return super().h(x, y, z)


def main() -> int:
    checks = []

    # ★① 代价关系✗★
    c = P3.COST
    ratio = c["step_up"] / c["walk"]
    print("  ★① 代价✗★：walk=%.2f ／ step_up=%.2f ⇒ **%.2f 步平路**"
          % (c["walk"], c["step_up"], ratio))
    checks.append(("step_up 明显贵于绕平路（> 2 步）", ratio > 2.0, "%.2f 步" % ratio))

    # ★② 有台阶的路仍能规划✗★
    w = StepFake()
    p1, _a1, cost1 = P3.plan(w, (1, 1, 2), (3, 1, 2), scaffold=0)
    print("  ★② 合成世界（★路上有 1 格台阶✗★）：%s 步 ／ 代价 %s"
          % (len(p1 or []), round(cost1, 1) if cost1 else "-"))
    checks.append(("有台阶的路仍能规划出来", bool(p1), "%s 步" % (len(p1 or []),)))

    # ★③ pillar 语义✗★
    p2, _a2, _c2 = P3.plan(PitFake(), (2, 1, 2), (2, 1, 3), scaffold=8)
    checks.append(("pillar／平路语义还在", bool(p2), "%s 步" % (len(p2 or []),)))

    # ★④ bridge 语义✗★
    p3, a3, _c3 = P3.plan(w, (1, 1, 2), (8, 1, 2), scaffold=8)
    places = sum(1 for a in (a3 or []) if a.startswith("place@"))
    checks.append(("bridge 语义还在", bool(p3) and places >= 1,
                   "%s 步 ／ place=%d" % (len(p3 or []), places)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => stepup_cost ★FAIL★（%d 项不对）" % bad)
        print("STEPUPCOST ok=0 bad=%d" % bad)
        return 1
    print("  => stepup_cost PASS ✓（★能绕平路就绕 ✗ pillar／bridge 语义没坏✗★）")
    print("STEPUPCOST ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
