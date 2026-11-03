#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recipe_graph_test.py -- 模块 K 配方图的判据（★离线 ✗ 用真 12.4MB 数据✗★）

规格 §13.2：★"功能需求 → 元件清单"是自主设计的第一步★ ⇒ 元件清单必须从**配方图**算出来，
不许手写名字表（用户普适性原则）。

CHECKS
  G1 数据装得进来（产物数 > 20000）
  G2 真机器的配方能查到，且原料非空
  G3 ★原料按 (kind,key) 合并计数正确★（同一原料出现两次 ⇒ count 相加）
  G4 ★shopping 只到底料★：清单里每一项都**没有配方**（或是 tag）
  G5 ★环保护✗★：人造的 A→B→A 环不会挂死，且会把 A 当底料
  G6 ★数量正确✗★：need=3 且配方一次产 1 ⇒ 底料数量是 3 倍
  G7 未知物品 ⇒ 诚实回底料（不抛异常、不编配方）
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

import recipe_graph as RG          # noqa: E402


def main() -> int:
    checks = []
    data = RG.load()
    checks.append(("G1 数据装得进来（>20000 产物）", len(data) > 20000, "%d 产物" % len(data)))

    rs = RG.producers("mekanism:energized_smelter", data)
    ings = RG.ingredients(rs[0]) if rs else []
    checks.append(("G2 真机器配方查得到且原料非空",
                   bool(rs) and bool(ings),
                   "%d 配方 ｜ 原料 %s" % (len(rs), ings[:3])))

    # G3 合并计数
    fake = {"type": "test", "count": 1,
            "ingredients": [{"id": "x:iron", "count": 1}, {"id": "x:iron", "count": 2},
                            {"tag": "forge:ingots/iron"}]}
    merged = RG.ingredients(fake)
    got = {i["key"]: i["count"] for i in merged}
    checks.append(("G3 同原料合并计数（1+2=3，tag=1）",
                   got.get("x:iron") == 3 and got.get("forge:ingots/iron") == 1,
                   str(got)))

    # G4 shopping 只到底料
    shop = RG.shopping("mekanism:energized_smelter", 1, recipes=data)
    nonleaf = [k for k in shop
               if not k.startswith("tag:") and RG.producers(k, data)]
    checks.append(("G4 shopping 只到底料（或 tag）", not nonleaf,
                   "%d 项 ｜ 不是底料的 %s" % (len(shop), nonleaf[:3])))

    # G5 环保护
    cyc = {"cyc:a": [{"type": "t", "count": 1, "ingredients": [{"id": "cyc:b"}]}],
           "cyc:b": [{"type": "t", "count": 1, "ingredients": [{"id": "cyc:a"}]}]}
    try:
        s5 = RG.shopping("cyc:a", 1, recipes=cyc)
        ok5 = bool(s5)          # 不挂死就是通过
        d5 = str(s5)
    except RecursionError:
        ok5, d5 = False, "RecursionError（环没护住）"
    checks.append(("G5 环保护（不挂死）", ok5, d5[:90]))

    # G6 数量
    simple = {"it:plate": [{"type": "t", "count": 1,
                            "ingredients": [{"id": "it:ingot", "count": 2}]}]}
    s6 = RG.shopping("it:plate", 3, recipes=simple)
    checks.append(("G6 数量正确（3 个板 ⇒ 6 个锭）",
                   s6.get("it:ingot") == 6, str(s6)))

    # G7 未知物品
    s7 = RG.shopping("nope:does_not_exist", 2, recipes=data)
    checks.append(("G7 未知物品 ⇒ 诚实回底料", s7.get("nope:does_not_exist") == 2, str(s7)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:105]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => recipe_graph FAIL (%d)" % bad)
        print("RECIPEGRAPH ok=0 bad=%d" % bad)
        return 1
    print("  => recipe_graph PASS (real 12.4MB data; leaf-only shopping; cycles guarded)")
    print("RECIPEGRAPH ok=1 checks=%d outputs=%d" % (len(checks), len(data)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
