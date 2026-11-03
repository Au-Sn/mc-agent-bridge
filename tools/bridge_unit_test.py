#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bridge_unit_test.py -- ★搭桥（place 边）判据：**合成世界** ✗ 零风险（§79.383）

★★为什么要这条判据（★§79.376~382 五次世界里都白干✗★）✗★★：
  ★真世界里造"★必须搭桥★"的地形 ✗ 要么切不断（★能绕✗★）✗ 要么要挖 8 格还会**留洞**✗★ ⇒
  ★★风险高于价值 ✗ 所以把这件事实搬到**合成世界**里验 ✗ 不碰真世界✗★★ ✓

★判据（★"★先证无路 ✗ 再证有路★"✗★）✗★：
  ★① **没方块**（★`scaffold=0`✗★）⇒ ★`plan` **必须 None**✗★ ✓
  ★② **有方块**（★`scaffold=8`✗★）⇒ **有路** ✗ 且动作里**有 `place@`**✗★ ✓
  ★③ ★`place` 的目标格**正好在这 3 格沟里**✗★ ✓
  ★④ ★路末尾 ＝ 终点✗★ ✓
★★今天的关键教训（★写在判据里✗★）✗★★：
  ★`Fake.pass_info` **只能看这一格的碰撞** ✗ **不许**要求"★脚下有支撑★"✗★ ⇒
  ★否则**头上那格**永远判 blocked ⇒ `stand_at` 永远 False ⇒ "★看起来连上 ✗ 其实没连★"✗★ ✓
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

# ★fixture：地板 `x=1..8, z=1..3` ✗ **x=4..6 整段没地板**（★3 格宽沟✗★）✗★
FLOOR = {(x, z) for x in range(1, 9) for z in range(1, 4) if x not in (4, 5, 6)}


class Fake:
    """★`y=0` 地板 ✗ `y=1` 站人✗★"""

    def name(self, x, y, z):
        return "minecraft:cobblestone" if (y == 0 and (x, z) in FLOOR) else ""

    def h(self, x, y, z):
        return 1.0 if (y == 0 and (x, z) in FLOOR) else 0.0

    def support(self, x, y, z):
        return self.h(x, y - 1, z) > 0.05

    def pass_info(self, x, y, z):
        # ★只问"这一格有没有碰撞" ✗ 不要求脚下有支撑 ✗★
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
    s, g = (2, 1, 2), (7, 1, 2)
    checks = []
    # ★① 先证无路✗★
    p0, _a0, _c0 = P3.plan(w, s, g, scaffold=0)
    checks.append(("① 没方块 ⇒ 无路（fixture 合格）", p0 is None,
                   "有路=%s（★必须 None✗★）" % (p0 is not None)))
    # ★② 再证有路且带 place✗★
    p1, a1, c1 = P3.plan(w, s, g, scaffold=8)
    places = [a for a in (a1 or []) if a.startswith("place@")]
    checks.append(("② 有方块 ⇒ 有路", bool(p1),
                   "步数=%s 代价=%s" % (len(p1 or []), round(c1, 1) if c1 else "-")))
    checks.append(("② 有路且动作里有 place", bool(places),
                   "place=%s" % (places,)))
    # ★③ place 目标格都在沟里✗★
    if places:
        pts = [tuple(int(v) for v in a.split("@")[1].split(",")) for a in places]
        okc = all(p[0] in (4, 5, 6) and p[1] == 0 for p in pts)
        checks.append(("③ place 目标格都在沟里", okc, "目标格=%s" % (pts,)))
    else:
        checks.append(("③ place 目标格都在沟里", False, "没有 place 动作"))
    # ★④ 路末尾 = 终点✗★
    checks.append(("④ 路末尾 ＝ 终点", bool(p1) and p1[-1] == g,
                   "末尾=%s" % (p1[-1] if p1 else None,)))

    bad = 0
    print("  合成世界：地板 x=1..8 z=1..3 ✗ **x=4..6 没地板**（★3 格宽沟✗★）")
    print("  起点 %s ⇒ 终点 %s" % (s, g))
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => bridge_unit ★FAIL★（%d 项不对）" % bad)
        print("BRIDGEUNIT ok=0 bad=%d" % bad)
        return 1
    print("  => bridge_unit PASS ✓（先证无路 ⇒ 再证有路 ⇒ 铺满 3 格 ⇒ 到终点）")
    print("BRIDGEUNIT ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
