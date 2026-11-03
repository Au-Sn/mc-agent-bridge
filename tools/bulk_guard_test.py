#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bulk_guard_test.py -- ★批量改方块守卫的判据（★含 2026-11-01 那次事故的回归测试✗★）

规格（事故后新增的铁律）：
  ★① 区域里任何一格命中 `no_dig` 禁区 ⇒ 拒绝✗
  ★② 区域里有**方块实体**（★计算机/箱子/机器✗★）⇒ 拒绝✗
  ★③ **没扫过**的区域 ⇒ 拒绝（不许盲填）✗★

CHECKS
  G1 ★回归：我事故里填的那个盒子 **必须被拒绝**★（4116,71,2 → 4127,71,13）
  G2 干净虚空（扫过、没禁区、没方块实体）⇒ 允许
  G3 没扫过 ⇒ 拒绝（region_not_scanned）
  G4 盒子里有 CC 计算机 ⇒ 拒绝且 hit 里点名它
  G5 盒子里有箱子 ⇒ 拒绝（★方块实体✗★）
  G6 命中断区要报出**哪一个区**（可追溯）
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import no_dig as ND          # noqa: E402
import bulk_guard as BG      # noqa: E402


def main() -> int:
    checks = []

    # 先把"CC 计算机"登记成禁区（★正是这次要写死的禁令✗★）
    ND.forbid("CC计算机", (4119, 71, 10, 4119, 71, 10),
              "★桥接计算机 ✗ 挖了整套系统就断（2026-11-01 踩过一次）✗★")
    ND.forbid("CC计算机邻", (4118, 71, 10, 4118, 71, 10),
              "★旁边那台计算机（网关外设 left(computer)）✗★")
    for p, why in ((( 4121, 71, 16), "GPS 主机"), ((4124, 72, 16), "GPS 主机"),
                   ((4131, 71, 16), "GPS 主机")):
        ND.forbid("CC计算机@%d,%d,%d" % p, p + p, "★" + why + " ✗ 不许动✗★")

    # G1 事故回归：那个盒子必须被拒
    cells1 = [(4116 + i, 71, 2 + j) for i in range(12) for j in range(12)]
    scan1 = {p: "minecraft:air" for p in cells1}
    r1 = BG.check_cells(cells1, what="事故回放", scan=scan1)
    hit_cc = [h for h in r1["hits"] if "CC" in str(h.get("zone", "")) or "comput" in str(h.get("block", ""))]
    checks.append(("G1 ★事故回归：那个盒子必须被拒绝★",
                   r1["ok"] is False and r1["why"] == "protected_hit",
                   "ok=%s hits=%d ｜ 其中 CC 相关=%d" % (r1["ok"], len(r1["hits"]), len(hit_cc))))

    # G2 干净虚空 ⇒ 允许
    cells2 = [(4200 + i, 71, 200 + j) for i in range(4) for j in range(4)]
    scan2 = {p: "minecraft:air" for p in cells2}
    r2 = BG.check_cells(cells2, what="干净虚空", scan=scan2)
    checks.append(("G2 干净虚空 ⇒ 允许", r2["ok"] is True, r2["message"]))

    # G3 没扫过 ⇒ 拒绝
    r3 = BG.check_cells(cells2, what="没扫", scan=None)
    checks.append(("G3 ★没扫过 ⇒ 拒绝（不许盲填）★",
                   r3["ok"] is False and r3["why"] == "region_not_scanned", r3["why"]))

    # G4 盒子里有计算机 ⇒ 拒绝且点名
    cells4 = [(4119, 71, 10)]
    scan4 = {cells4[0]: "computercraft:computer_advanced"}
    r4 = BG.check_cells(cells4, what="计算机", scan=scan4)
    checks.append(("G4 有 CC 计算机 ⇒ 拒绝且点名",
                   r4["ok"] is False and any(h["pos"] == [4119, 71, 10] for h in r4["hits"]),
                   str(r4["hits"][:1])))

    # G5 有箱子 ⇒ 拒绝（方块实体）
    cells5 = [(4300, 71, 300)]
    scan5 = {cells5[0]: "minecraft:chest"}
    r5 = BG.check_cells(cells5, what="箱子", scan=scan5)
    checks.append(("G5 有箱子 ⇒ 拒绝（方块实体）",
                   r5["ok"] is False and r5["hits"][0]["kind"] == "block_entity",
                   str(r5["hits"][:1])))

    # G6 命中断区要报出哪一个区
    checks.append(("G6 命中区要报出**哪个区**",
                   bool(r1["hits"]) and any(h.get("zone") for h in r1["hits"]),
                   str([h.get("zone") for h in r1["hits"]][:3])))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:115]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => bulk_guard FAIL (%d)" % bad)
        print("BULKGUARD ok=0 bad=%d" % bad)
        return 1
    print("  => bulk_guard PASS (accident replay is refused; unscanned regions are refused)")
    print("BULKGUARD ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
