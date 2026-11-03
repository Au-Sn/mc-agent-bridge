#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut_ready.py -- ★★现在**真正能切**的模组清单✗★★（★阶段 4 的可执行名单 ✗ 2026-10-05✗★）

★★为什么要有它✗★★（★§79.189 的结论✗★）✗★：
  ★"★先切★"（★`switch_plan` 排的✗★）只是"★风险低 ✗ 判据齐★"✗★ ⇒
  ★★而铁律②还要求"★不一致**一条都不许没声明**★"✗★★ ⇒
  ★所以真正能切的 ✗ 是"★**先切 ∩ 未声明表为空**★"✗★ ✓
★★三个数并排（★各说各的量的是什么✗★）✗★★
  · ★`会改`（★`kb_risk` ✗ 名字模型 ↔ 导出 ✗ 上界✓★）✗★
  · ★`实测差异`（★`cut_verify` ✗ 关↔开开关 ✗ 实际✓★）✗★
  · ★`未声明`（★`u1_declared` ✗ 铁律②的分母✓★）✗★
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

import json  # noqa: E402
import kb_export as KX  # noqa: E402
import u1_declared as U1  # noqa: E402


def main(argv):
    exp = json.loads(KX.find_export("").read_text(encoding="utf-8"))
    blocks = exp.get("blocks") or {}
    print("== 真正能切的模组 ✗ 先切 ∩ 未声明为空 ==")
    print("   ★正在算「★决策级里多少条没声明★」✗ 要走一遍标签管线 ✗ 稍等✗★")
    u = U1.u1_numbers(verbose=True)
    per_ns = {}
    for sp in u["undeclared"]:
        per_ns[sp.split(":")[0]] = per_ns.get(sp.split(":")[0], 0) + 1

    # ★候选：≥40 个方块 ✗ 且未声明为 0（★"★先切★"那一栏由 `switch_plan` 排 ✗
    #   这里只做**硬条件**：★铁律②过关✗★ ✓）
    cand = []
    by_ns = {}
    for sp in blocks:
        by_ns.setdefault(sp.split(":")[0], []).append(sp)
    for ns, v in by_ns.items():
        if len(v) < 40:
            continue
        if per_ns.get(ns, 0) == 0:
            cand.append((ns, len(v)))
    cand.sort(key=lambda t: -t[1])

    # ★★两个条件并排（★§79.191✗★）✗★★：★铁律②（★未声明✗★）＋ ★实测会改多少✗★
    import cut_measure as CM
    print("   ★正在算「★切了会改多少★」✗ 逐方块比三条签名 ✗ 稍等✗★")
    meas = CM.per_ns_diff(blocks, min_blocks=40)

    print("")
    print("★★现在就能切（★未声明 0 条✗★）✗ %d 个模组✗★★" % len(cand))
    print("   %-26s %7s %9s %9s %s" % ("模组", "方块", "未声明", "★实测会改✗★", "占比"))
    for ns, n in cand:
        _m = meas.get(ns)
        _d = _m[3] if _m else -1
        _pct = ("%.0f%%" % (100.0 * _d / max(1, n))) if _d >= 0 else "?"
        flag = "★零改动✗★" if _d == 0 else ""
        print("   %-26s %7d %9d %9d %5s  %s" % (ns, n, 0, _d, _pct, flag))
    print("")
    blocked = sorted([(ns, c) for ns, c in per_ns.items() if c], key=lambda t: -t[1])[:10]
    print("★被铁律②挡住的（★未声明 > 0✗★）✗ 前 10✗★：")
    for ns, c in blocked:
        print("   %-28s ★%4d 条未声明✗★" % (ns, c))
    print("")
    print("★口径✗★：★这份名单只保证「★导出 ＋ 三条签名 ＋ 铁律②★」✗★ ⇒ "
          "★世界侧与 table 下的规划**仍要游戏**（★§79.187✓★）✗★ ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
