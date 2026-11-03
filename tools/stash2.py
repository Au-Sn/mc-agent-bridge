#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stash2.py —— 清包（★这次按真实用法发命令 ✗★）

读到的真实用法 ✓（`DshBridgeMod` 264~285 行 ✓）：
    /dshbox put <pos> <item> [count]
    item 是 **StringArgumentType.string()** ✓ ⇒ 带冒号**必须加引号** ✗（项目早有这条 P14 ✓）
⇒ 我上一轮失败的真因就是**没加引号** ✗（不是我先前判断的"够不着" ✗）
★为了不再被 shell 吃引号 ✗：引号在代码里用 chr(34) 生成 ✓ 源码里一个引号都不写 ✓

前提检查（硬规矩 ✓ 前 6 次都栽在这 ✗）：假人不在 ⇒ 立刻停并说明 ✓
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

Q = chr(34)
BARREL = "4122 71 3"
KEEP = ("hammer", "mesh", "pickaxe", "axe", "shovel", "sword", "shears", "bucket",
        "beef", "porkchop", "wheat", "sapling", "coal", "flint", "stick", "planks",
        "crafting_table", "furnace", "chest", "hopper", "diamond", "iron_ingot",
        "inferium", "torch", "log", "lead", "sand")
JUNK = ("iron_boots", "iron_helmet", "iron_chestplate", "iron_leggings",
        "leather_", "chainmail_", "golden_", "copper_")

ch = Channel("cmd0", verbose=False)
out: list[str] = []


def r(t: str, tmo: float = 90.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def ab(t: str, tmo: float = 90.0) -> str:
    return r("execute as Bot at Bot run %s" % t, tmo)


def kv(txt: str, key: str, default="-"):
    m = re.search(key + r"=([^\s]+)", txt or "")
    return m.group(1) if m else default


# ── 前提检查（★必须的 ✗★）
dig = ab("dshdigest 4", 40.0)
if "name=Bot" not in dig:
    out.append("PRECHECK FAIL: no fake player Bot")
    (ROOT / "logs" / "stash2.txt").write_text("\n".join(out), encoding="utf-8")
    print("STASH2: PRECHECK FAIL (no bot)")
    raise SystemExit(1)
free0, items0 = kv(dig, "free"), kv(dig, "items")
out.append("before free=%s items=%s pos=%s" % (free0, items0, kv(dig, "pos")))

# ── 先走到桶边（触及 4.5 ✓）
out.append("walk -> %s" % ab("dshwalk 4121 71 3 20000", 90.0)[:120])
time.sleep(5.0)
out.append("pos now = %s" % kv(ab("dshdigest 4", 40.0), "pos"))

# ── 塞东西（★名字加引号 ✗★）
for item in ("minecraft:iron_boots", "minecraft:iron_helmet"):
    cmd = "dshbox put %s %s%s%s" % (BARREL, Q, item, Q)
    res = ab(cmd, 120.0)
    out.append("put %-24s -> %s" % (item, res[:170]))

dig2 = ab("dshdigest 4", 40.0)
free1, items1 = kv(dig2, "free"), kv(dig2, "items")
out.append("after  free=%s items=%s" % (free1, items1))

# ── KEEP 一件都没动吗（从背包逐格核对 ✓）
lst = ab("dshinv list", 90.0).replace(" ", "")
after = {}
for m in re.finditer(r"\d+:([a-z_]+:[\w_]+)x(\d+)", lst):
    after[m.group(1)] = after.get(m.group(1), 0) + int(m.group(2))
touched = [k for k in after if any(w in k.split(":")[-1] for w in KEEP)]
out.append("KEEP 类还在的：%s" % (touched or "（一件都没有 ✗ 要查 ✗）"))

ok = (free1.isdigit() and int(free1) >= 2)
out.append("")
out.append("判据 free>=2 => %s" % ("PASS" if ok else "FAIL"))
(ROOT / "logs" / "stash2.txt").write_text("\n".join(out), encoding="utf-8")
print("STASH2: free %s -> %s ; result=%s" % (free0, free1, "PASS" if ok else "FAIL"))
