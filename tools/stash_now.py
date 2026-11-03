#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stash_now.py —— ★靶向清包：把"占地方又没用"的东西塞进桶里★（解 free=0 ✗）

为什么需要它 ✗（实测 ✓）：背包 `free=0` ⇒ 收成/筛矿这类作业**一律拒绝开工** ✗
（模组自己写的规矩：接不住就不开工 ✓ 见 jobs.py 的背包守卫 ✓）
而现状是 **12 双铁靴子 ＋ 一堆重复护甲** 占着 ✗ —— 它们对进度毫无用处 ✓

★为什么不用改模组★ ✓：`/dshbox put <pos> <item>` 是现成的 ✓ ⇒ 靶向塞 2~3 种东西就够 ✓
（通用整理可以以后再做 ✓ 今天先把路打通 ✓）

判据（写死 ✓）：跑完之后 `free` **必须 ≥ 2** ✓（不然一切作业还是开不了工 ✓）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)
CHEST = (4122, 71, 3)                    # 模组桶 ✓（132 格 ✓ 早先量过 ✓）

# ★绝不塞走的东西★ ✗（工具/材料/吃的/种子 ✓ —— 塞错了它是真会丢进桶里 ✗）
KEEP = ("hammer", "mesh", "pickaxe", "axe", "shovel", "sword", "shears", "bucket",
        "beef", "porkchop", "bread", "wheat_seeds", "wheat", "sapling", "coal",
        "flint", "stick", "planks", "crafting_table", "furnace", "chest", "hopper",
        "diamond", "iron_ingot", "inferium", "torch", "bucket", "log", "lead", "sand")
# ★该塞走的东西★ ✓（占地方 ＋ 对进度没用 ✓）
JUNK = ("iron_boots", "iron_helmet", "iron_chestplate", "iron_leggings",
        "leather_", "chainmail_", "golden_", "copper_")


def raw(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd("execute as Bot at Bot run %s" % t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR %s: %s" % (type(e).__name__, str(e)[:80])


def inv() -> tuple[dict, int]:
    """→ ({item: 件数}, 空位数) ✓（`dshinv list` 的格式：`0:minecraft:x x62 1:…` ✓）"""
    r = raw("dshinv list", 90.0)
    counts: dict = {}
    for m in re.finditer(r"\d+:(minecraft:[\w_]+|[\w]+:[\w_]+)x(\d+)", r.replace(" ", "")):
        counts[m.group(1)] = counts.get(m.group(1), 0) + int(m.group(2))
    fm = re.search(r"free=(\d+)", raw("dshdigest 4"))
    return counts, int(fm.group(1)) if fm else -1


def main() -> int:
    out = []
    before, free0 = inv()
    out.append("清包前 free=%s ｜ 种类 %d ｜ 总件数 %d" % (free0, len(before), sum(before.values())))

    def is_junk(name: str) -> bool:
        base = name.split(":")[-1]
        if any(k in base for k in KEEP):
            return False
        return any(base.startswith(j) or j in base for j in JUNK)

    junk = {k: v for k, v in before.items() if is_junk(k)}
    out.append("判定为可塞走的：%s" % (junk or "（没有 ✓）"))
    if not junk:
        out.append("⇒ 没有可塞的东西 ✓ 收工 ✓")
        (ROOT / "logs" / "stash.txt").write_text("\n".join(out), encoding="utf-8")
        print("STASH: nothing to stash; free=%s" % free0)
        return 0

    for item in junk:
        r = raw("dshbox put %d %d %d %s" % (CHEST[0], CHEST[1], CHEST[2], item), 90.0)
        out.append("put %-34s -> %s" % (item, r[:130]))

    after, free1 = inv()
    out.append("")
    out.append("清包后 free=%s ｜ 种类 %d ｜ 总件数 %d" % (free1, len(after), sum(after.values())))
    lost = []
    for k, v in before.items():
        if k in KEEP and after.get(k, 0) < v:
            lost.append("%s %d->%d" % (k, v, after.get(k, 0)))
    out.append("★KEEP 名单里有没有被动到★ ✗：%s" % (lost or "没有 ✓（一个都没丢 ✓）"))
    ok = free1 >= 2 and not lost
    out.append("")
    out.append("判据：free ≥ 2 ✓ 且 KEEP 未被动 ✗ ⇒ %s" % ("PASS" if ok else "FAIL"))
    (ROOT / "logs" / "stash.txt").write_text("\n".join(out), encoding="utf-8")
    print("STASH: free %s -> %s ; keep_touched=%d ; result=%s"
          % (free0, free1, len(lost), "PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
