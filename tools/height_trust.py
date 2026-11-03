#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""height_trust.py -- ★高度数据**可不可信**的离线审✗★（★§79.196 ✗ 2026-10-05✗★）

★★为什么换这个判据✗★★（★§79.195 的教训✗★）✗★：
  ★方向（★「变松」✗★）**不**说明危险 ✗★ ⇒ ★真正的危险是「★**碰撞高度数据不可信**★」✗★ ✓
★★离线能查的第一条✗★★：★**族名与高度自不自洽**✗★ ✓
★★怎么做✗★★（★**不预设**范围 ✗ 先看数据自己长什么样✗★）✗★：
  ★统计每个族的**高度分布** ✗★ ⇒ ★★离群的那些就是可疑的✗★★ ✓
★★这份审**只用来排优先** ✗ 不是判错✗★★ ✓
  ★例✗★：★`snow_layer` 本来就一格到八格都有 ✗ 那几个 0.125／0.25 是**对的**✗★ ✓
  ★⇒ ★**最终判据仍然是世界**✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import kb_export as KX  # noqa: E402


def main(argv):
    exp = json.loads(KX.find_export("").read_text(encoding="utf-8"))
    blocks = exp.get("blocks") or {}
    print("== 高度可信度审 ✗ 导出 %d 个方块 ==" % len(blocks))

    per = {}
    for sp, e in blocks.items():
        if not isinstance(e, dict):
            continue
        fam = e.get("family") or "（无族）"
        per.setdefault(fam, []).append((sp, e.get("max_height")))

    print("")
    print("★每个族的高度分布（★出现最多的那个当「本族主值」✗★）✗★：")
    odd = []
    for fam, items in sorted(per.items(), key=lambda kv: -len(kv[1])):
        cnt = Counter(str(h) for _sp, h in items)
        top, n = cnt.most_common(1)[0]
        pct = 100.0 * n / len(items)
        print("   %-12s %6d 个 ✗ 主值 **%s**（%.1f%%）✗ 另有 %d 种"
              % (fam, len(items), top, pct, max(0, len(cnt) - 1)))
        for sp, h in items:
            if str(h) != top:
                odd.append((fam, sp, h, top))

    print("")
    print("★★与「本族主值」不同的 ✗ 共 **%d** 个✗★★" % len(odd))
    for fam, sp, h, top in sorted(odd, key=lambda t: t[0])[:14]:
        print("   %-12s %-44s h=%-10s（★本族主值 %s✗★）" % (fam, sp[:44], h, top))
    print("")
    print("★口径✗★：★这只说明「它在本族里是少数」✗ *不* 说明它错✗★ ✓")
    print("   ★⇒ 真正的判据仍是「世界」 ✗ 这份审只用来**排优先**✗★ ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
