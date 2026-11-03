#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut_final.py -- ★★"★现在可以放心切★"的**一句话结论**✗★★（★§79.197 ✗ 离线✗★）

★★三条审并成一张✗★★（★每条都是**独立**的一问 ✗ 不互相代替✗★）✗★：
  ★① **铁律②**（★`u1_declared` ✗ 这个模组的不一致里有多少**没声明**✗★）✗★
  ★② **改动量**（★`cut_measure` ✗ 切了会改几个方块✗★）✗★
  ★③ **高度可信度**（★改的那些方块 ✗ 是不是都在 `full` 族 ✗ 本族主值 1.0 ✗ 99% 一致✓★）✗★
★★分三句✗★★
  ★**放心切**✗★：★未声明 0 ✗ 且（★零改动 或 改动**全部**落在 `full` 族✗★）✗★ ✓
  ★**要世界**✗★：★未声明 0 ✗ 改动落在**别的族**（★那些族的高度是"★少数的★" ✗ 得实地看✓★）✗★ ✓
  ★**先别切**✗★：★未声明 > 0（★铁律②没过✗★）✗★ ✓
★★口径✗★★：★这三句**都只到"★导出 ＋ 三条签名★"这一层**✗★ ⇒
★世界侧与 `table` 下的规划 ✗ **仍要游戏**✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import cut_measure as CM  # noqa: E402
import kb_export as KX  # noqa: E402
import u1_declared as U1  # noqa: E402


def main(argv):
    top = int(argv[0]) if argv else 30
    exp = json.loads(KX.find_export("").read_text(encoding="utf-8"))
    blocks = exp.get("blocks") or {}
    print("== 最终结论 ✗ 三条审并成一张 ==")
    print("   ★正在算铁律②（★走标签管线✗★）✗ 稍等✗★")
    u = U1.u1_numbers(verbose=True)
    per_ns_und = {}
    for sp in u["undeclared"]:
        per_ns_und[sp.split(":")[0]] = per_ns_und.get(sp.split(":")[0], 0) + 1

    by_ns = {}
    for sp in blocks:
        by_ns.setdefault(sp.split(":")[0], []).append(sp)

    ok_rows, world_rows, no_rows = [], [], []
    print("   ★正在算改动量与高度族 ✗ 稍等✗★")
    for ns, mine in sorted(by_ns.items(), key=lambda kv: -len(kv[1])):
        if len(mine) < 40:
            continue
        und = per_ns_und.get(ns, 0)
        if und:
            no_rows.append((ns, len(mine), und))
            continue
        cmp_n, skip_n, diff_n, diffs = CM.diff_of(sorted(mine))
        if skip_n:
            no_rows.append((ns, len(mine), -skip_n))     # ★有跳过 ⇒ 不许放心✗★
            continue
        if diff_n == 0:
            ok_rows.append((ns, len(mine), 0, 0))
            continue
        # ★改动落在哪些族✗★
        fams = {}
        for sp in diffs:
            f = (blocks.get(sp) or {}).get("family") or "?"
            fams[f] = fams.get(f, 0) + 1
        full_n = fams.get("full", 0)
        if full_n == diff_n:
            ok_rows.append((ns, len(mine), diff_n, diff_n))
        else:
            world_rows.append((ns, len(mine), diff_n, full_n,
                               ",".join("%s:%d" % kv for kv in
                                        sorted(fams.items(), key=lambda kv: -kv[1])[:3])))

    print("")
    print("★★★放心切（★%d 个✗★）✗★：★未声明 0 ✗ 且零改动或改动全在 full 族✗★★★" % len(ok_rows))
    print("   %-26s %7s %8s %8s" % ("模组", "方块", "改动", "其中 full"))
    for ns, n, d, f in ok_rows[:top]:
        print("   %-26s %7d %8d %8d%s" % (ns, n, d, f, "   ★零改动✗★" if d == 0 else ""))
    print("")
    print("★要世界（★%d 个✗★）✗ 改动落在别的族 ⇒ 那些族的高度是「少数的」 ✗ 得实地看✗★："
          % len(world_rows))
    for ns, n, d, f, fams in world_rows[:12]:
        print("   %-26s %7d 改动 %5d ✗ full 只占 %4d ✗ 别的族 %s" % (ns, n, d, f, fams))
    print("")
    print("★先别切（★%d 个✗★）✗★：★铁律②没过或**有跳过**✗★" % len(no_rows))
    for ns, n, und in sorted(no_rows, key=lambda t: t[2])[:10]:
        tag = "跳过 %d" % (-und) if und < 0 else "未声明 %d" % und
        print("   %-26s %7d ✗ ★%s✗★" % (ns, n, tag))
    print("")
    print("★口径✗★：★这三句**都只到「★导出 ＋ 三条签名★」这一层**✗★ ⇒ "
          "★世界侧与 table 下的规划**仍要游戏**✗★ ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
