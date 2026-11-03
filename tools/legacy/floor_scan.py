#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""floor_scan.py —— 量"岛的地面在哪" ✓（判断目标点是否可达 ✗）

用模组的原生扫描 ＋ **方块标签**筛 ✓（`#minecraft:dirt` 覆盖泥土/草方块/砂土 ✓ 一次问清 ✓）
输出：`logs/floor_scan.txt`（含每个地面格的坐标 ✓ 与统计 ✓）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)


def d(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd("execute as Bot at Bot run %s" % t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR %s" % str(e)[:100]


out: list[str] = []
out.append("dshver: %s" % d("dshver"))
out.append("digest: %s" % d("dshdigest 8")[:260])
for tag in ("#minecraft:dirt", "minecraft:grass_block", "#minecraft:slabs",
            "#minecraft:stairs", "#minecraft:fences", "exdeorum:sieve",
            "exdeorum:barrel", "minecraft:crafting_table", "minecraft:water",
            "minecraft:lava", "minecraft:chest", "exdeorum:crushed_netherrack"):
    r = d('dshscan 4096 55 -16 4160 96 48 "%s" 160 1' % tag)
    out.append("")
    out.append("=== %s ===" % tag)
    out.append(r[:1500])
dest = ROOT / "logs" / "floor_scan.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("written %s (%d lines)" % (dest, len(out)))
