#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""survey.py —— ★全岛普查：整座岛到底有什么 ＋ 背包里到底有什么★

为什么需要它 ✗（用户原话：「感觉还是没法扫描方块」✓）：
  `/dshscan` 不给 `match` 时**只列前十种**方块 ✗（`counts[… more_kinds=130]` ✓）
  ⇒ "岛的概况"其实问不出来 ✗ ⇒ 只能**逐类去问** ✓（本脚本就是干这个的 ✓）
  ★这也正是"该给模组加个 `counts <n>` 参数"的最好证据★ ✗（见回复 ✓）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)
BOX = "4096 55 -16 4160 96 48"


def raw(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR %s: %s" % (type(e).__name__, str(e)[:100])


def asbot(t: str, tmo: float = 60.0) -> str:
    return raw("execute as Bot at Bot run %s" % t, tmo)


out: list[str] = []
out.append("dshver -> %s" % raw("dshver"))
out.append("digest -> %s" % asbot("dshdigest 8"))
out.append("")
out.append("======== 背包（逐格）========")
out.append(asbot("dshinv list", 90.0)[:1200])

PROBES = [
    "#minecraft:dirt", "#minecraft:logs", "#minecraft:leaves", "#minecraft:planks",
    "#minecraft:saplings", "#minecraft:crops", "minecraft:water", "minecraft:lava",
    "minecraft:farmland", "minecraft:wheat", "minecraft:chest", "minecraft:furnace",
    "minecraft:crafting_table", "minecraft:torch", "minecraft:glass", "minecraft:stone",
    "minecraft:cobblestone", "minecraft:gravel", "minecraft:sand", "minecraft:clay",
    "minecraft:iron_ore", "minecraft:copper_ore", "minecraft:coal_ore",
    "exdeorum:sieve", "exdeorum:barrel", "exdeorum:wooden_hammer",
    "exdeorum:stone_pebble", "exdeorum:porcelain_crucible",
    "sophisticatedstorage:chest", "sophisticatedstorage:barrel",
    "minecraft:hopper", "minecraft:blast_furnace", "minecraft:anvil",
    "minecraft:bookshelf", "minecraft:enchanting_table", "minecraft:cauldron",
    "minecraft:composter", "minecraft:bee_nest", "minecraft:campfire",
]
out.append("")
out.append("======== 全岛普查（盒子 %s ✓ 逐类问 ✓）========" % BOX)
for p in PROBES:
    r = raw('dshscan %s "%s" 1 1' % (BOX, p))
    # 只留 matched 那一段 ✓（回执很长 ✗）
    m = ""
    for tok in r.split():
        if tok.startswith("matched=") or tok.startswith("solid=") or tok.startswith("kinds="):
            m += tok + " "
    out.append("%-38s %s" % (p, m.strip() or r[:80]))
out.append("")
out.append("======== 岛内前十种（不带 match 的原始回执 ✓）========")
out.append(raw("dshscan %s" % BOX)[:600])

dest = ROOT / "logs" / "survey.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("SURVEY written %s (%d lines)" % (dest, len(out)))
