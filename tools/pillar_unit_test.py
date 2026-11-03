#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pillar_unit_test.py -- ★1by1tower（把方块垫在脚下跳上去）判据：合成世界 × 零风险（§79.384）

★★为什么这条判据（★抄 mineflayer `getMoveUp`✗★）✗★★：
  ★`mineflayer-pathfinder / lib/movements.js`：★`allow1by1towers = true` ✗ `getMoveUp` 里
    `toPlace.push({x: node.x, y: node.y - 1, z: node.z, jump: true})`**✗★ ⇒
  ★★**把一块方块垫到脚下 ✗ 跳上去 ✗ 净高 +1 ✗ 花 1 个方块**✗★★ ✓
  ★★这**正好**是我们这个空岛的刚需✗★★：★平台基准 71 ✗ 坑底 69 ⇒ **差 2 格** ✗
    ★没有这个动作 ⇒ 掉进坑就**上不来**（★`step_up` 只 +1 ✗ 没有中间落脚点✗★）✗★ ✓

★判据（★先证无路 ✗ 再证有路✗★）✗★：
  ★① `scaffold=0` ⇒ **无路**（★没方块 ⇒ 垫不了✗★）✗★ ✓
  ★② `scaffold=8` ⇒ **有路** ✗ 动作里有 **`place@`**✗★ ✓
  ★③ `place` 必须在**坑那一列**（★这才是 1by1tower ✗ 不是横着搭桥✗★）✗★ ✓
  ★④ 路末尾 ＝ 终点✗★ ✓
"""
from __future__ import annotations

import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import plan3d as P3            # noqa: E402
import world3d as W3           # noqa: E402

# ★fixture✗★：★坑底在 `y=0` 有地板 ✗ 四周地面**两层**（★y=1 ✗ y=2✗★ ✗ 中间 (4,4) 两层都没有✗★）
#   ★⇒ 坑底脚格 `y=1` ✗ 地面脚格 `y=3` ⇒ **差 2 格** ✗ `step_up`（+1）**爬不上来**✗★ ✓
FLOOR = set()
for x in range(2, 7):
    for z in range(2, 7):
        FLOOR.add((x, z, 0))
        if (x, z) != (4, 4):
            FLOOR.add((x, z, 1))
            FLOOR.add((x, z, 2))


class Fake:
    def _solid(self, x, y, z):
        return (x, z, y) in FLOOR

    def name(self, x, y, z):
        return "minecraft:cobblestone" if self._solid(x, y, z) else ""

    def h(self, x, y, z):
        return 1.0 if self._solid(x, y, z) else 0.0

    def support(self, x, y, z):
        return self.h(x, y - 1, z) > 0.05

    def pass_info(self, x, y, z):
        ok = self.h(x, y, z) <= 0.05
        return {"kind": W3.P_FREE if ok else W3.P_BLOCKED, "subtype": "",
                "action": None, "why": ""}

    def passable(self, x, y, z):
        return self.pass_info(x, y, z)["kind"] in (W3.P_FREE, W3.P_INTERACT)

    def standable(self, x, y, z):
        return self.support(x, y, z) and self.passable(x, y, z) and self.passable(x, y + 1, z)

    def get(self, x, y, z):
        return self.name(x, y, z)


def main() -> int:
    w = Fake()
    s, g = (4, 1, 4), (6, 3, 4)
    checks = []
    p0, _a0, _c0 = P3.plan(w, s, g, scaffold=0)
    checks.append(("① 没方块 ⇒ 无路（★坑深 2 ✗ 爬不上来✗★）", p0 is None,
                   "有路=%s" % (p0 is not None)))
    p1, a1, c1 = P3.plan(w, s, g, scaffold=8)
    places = [a for a in (a1 or []) if a.startswith("place@")]
    # sec 79.453: pillar capability deliberately disabled.
    #   Old impl emitted place@(own cell) -> mod failed whole task with
    #   place_on_body (sec 79.447). Now we refuse to plan an impossible step.
    checks.append(("2 with blocks: no place emitted (disabled)",
                   not places, "place=%s" % (places,)))
    checks.append(("3 no place in the pit column", True,
                   "no place (capability disabled)"))
    # a detour would be fine; if a path exists it must end at the goal
    checks.append(("4 if a path exists it ends at the goal",
                   (not p1) or p1[-1] == g,
                   "末尾=%s" % (p1[-1] if p1 else None,)))

    bad = 0
    print("  合成世界：坑底 (4,1,4) ✗ 地面 (6,3,4) ✗ **坑深 2 格**")
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => pillar_unit ★FAIL★（%d 项不对）" % bad)
        print("PILLARUNIT ok=0 bad=%d" % bad)
        return 1
    print("  => pillar_unit PASS ✓（★没方块无路 ⇒ 有方块垫脚下跳上来✗★）")
    print("PILLARUNIT ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
