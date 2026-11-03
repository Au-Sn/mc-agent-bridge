#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""free_inv.py —— 一步到位：确保假人在 ✓ -> 靶向清包 ✓ -> 校验 free ✓

★与 stash_now.py 的区别（它被我判为有缺陷 ✗）★：
  那一版**不做前提检查** ✗ ⇒ 假人不在时 `execute as Bot` 全失败 ✓
  它就报 "free=-1 / 没有可塞的" ✓ ＝ **假阴性** ✗（读不到 ≠ 没事可做 ✗）
  ⇒ 这一版：**读不到就大声失败** ✗ 并且**先把假人弄回来** ✓
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)
CHEST = (4122, 71, 3)
KEEP = ("hammer", "mesh", "pickaxe", "axe", "shovel", "sword", "shears", "bucket",
        "beef", "porkchop", "bread", "wheat_seeds", "wheat", "sapling", "coal",
        "flint", "stick", "planks", "crafting_table", "furnace", "chest", "hopper",
        "diamond", "iron_ingot", "inferium", "torch", "log", "lead", "sand")
JUNK = ("iron_boots", "iron_helmet", "iron_chestplate", "iron_leggings",
        "leather_", "chainmail_", "golden_", "copper_")
out: list[str] = []


def raw(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def asbot(t: str, tmo: float = 60.0) -> str:
    return raw("execute as Bot at Bot run %s" % t, tmo)


# ── 前提检查（★这一步就是上一版缺的✗★）
d = raw("data get entity Bot Pos", 40.0)
if "[" not in d:
    out.append("假人不在 ⇒ spawn + gamemode survival ✓")
    raw("player Bot spawn", 40.0)
    time.sleep(2.5)
    raw("gamemode survival Bot", 40.0)
    time.sleep(1.0)
dig = asbot("dshdigest 4", 40.0)
if "name=Bot" not in dig:
    out.append("★还是读不到假人 ✗ ⇒ 大声失败（绝不报'没事可做'✗）：%s" % dig[:120])
    (ROOT / "logs" / "free_inv.txt").write_text("\n".join(out), encoding="utf-8")
    print("FREE_INV: FAIL - bot unreadable")
    raise SystemExit(1)
out.append("前提 ✓ %s" % dig[:150])

fm = re.search(r"free=(\d+)", dig)
free0 = int(fm.group(1)) if fm else -1
if free0 < 0:
    out.append("★free 读不出来 ✗ ⇒ 大声失败 ✗（不猜 ✗）")
    (ROOT / "logs" / "free_inv.txt").write_text("\n".join(out), encoding="utf-8")
    print("FREE_INV: FAIL - free unreadable")
    raise SystemExit(1)

lst = asbot("dshinv list", 90.0)
counts: dict = {}
for m in re.finditer(r"\d+:([a-z_]+:[\w_]+)x(\d+)", lst.replace(" ", "")):
    counts[m.group(1)] = counts.get(m.group(1), 0) + int(m.group(2))
if not counts:
    out.append("★背包列表解析为空 ✗ ⇒ 大声失败 ✗（原文：%s）" % lst[:120])
    (ROOT / "logs" / "free_inv.txt").write_text("\n".join(out), encoding="utf-8")
    print("FREE_INV: FAIL - inventory unparseable")
    raise SystemExit(1)

out.append("清包前 free=%s ｜ 种类 %d ｜ 总件数 %d" % (free0, len(counts), sum(counts.values())))


def is_junk(name: str) -> bool:
    base = name.split(":")[-1]
    if any(k in base for k in KEEP):
        return False
    return any(base.startswith(j) or j in base for j in JUNK)


junk = {k: v for k, v in counts.items() if is_junk(k)}
out.append("可塞走：%s" % (junk or "（没有 ✓）"))
for item in junk:
    out.append("put %-32s -> %s" % (item, raw(
        "execute as Bot at Bot run dshbox put %d %d %d %s" % (CHEST[0], CHEST[1], CHEST[2], item), 90.0)[:120]))

dig2 = asbot("dshdigest 4", 40.0)
fm2 = re.search(r"free=(\d+)", dig2)
free1 = int(fm2.group(1)) if fm2 else -1
lst2 = asbot("dshinv list", 90.0)
after: dict = {}
for m in re.finditer(r"\d+:([a-z_]+:[\w_]+)x(\d+)", lst2.replace(" ", "")):
    after[m.group(1)] = after.get(m.group(1), 0) + int(m.group(2))
lost = ["%s %d->%d" % (k, v, after.get(k, 0)) for k, v in counts.items()
        if k in KEEP and after.get(k, 0) < v]
out.append("")
out.append("清包后 free=%s ｜ 总件数 %d" % (free1, sum(after.values())))
out.append("KEEP 被动到的：%s" % (lost or "没有 ✓"))
ok = free1 >= 2 and not lost and free1 > free0
out.append("判据 free>=2 且 KEEP 未动 且 free 变多 ⇒ %s" % ("PASS" if ok else "FAIL"))
(ROOT / "logs" / "free_inv.txt").write_text("\n".join(out), encoding="utf-8")
print("FREE_INV: free %s -> %s ; junk=%d ; keep_touched=%d ; %s"
      % (free0, free1, len(junk), len(lost), "PASS" if ok else "FAIL"))
