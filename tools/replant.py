#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
replant.py — 补种空着的耕地（种子由玩家提供 ✓ 如实记账 ✓）

★ 2026-09-19 晚：**已被作业吸收** ✓（`agent/jobs.py` 的 `harvest_and_replant` ✓
   在收完之后会**顺手把本来就空着的耕地也种上** ✓ ⇒ 日常不再需要单独跑这个 ✗）
   保留它 ✓ 只作**排查/单点补种**用 ✓（比如"只想种、不想收"的场合 ✓）

为什么单独写一个（而不是复用 harvest.py）：
    harvest.py 是"收 + 顺手补种" ✓ 可如今田里**只剩耕地、没有庄稼** ✗
    ⇒ 它的循环里没有"可收的株" ⇒ 什么也不会做 ✗
    而"把玩家给的种子种回去"是**独立的一件事** ✓ 值得单独一个动作 ✓

它做什么（三步，都自证 ✓）：
    1) 扫 `minecraft:farmland` ✓ 找出所有耕地
    2) 其中**正上方是空气**的那些 = 空着的耕地 ✓ 需要补种
    3) 逐格：站到跟前（**收/种必须与拾取同位置** ✓ 这是丢过 30 株的教训 ✗）
       → 手持种子 → 瞄下方耕地 → 右键 ✓ → 最后重扫小麦确认 ✓

用法：
    py tools/replant.py --x0 4104 --y0 70 --z0 4 --x1 4120 --y1 71 --z1 16
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel, BridgeError  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def call(ch: Channel, cmd: str, args: dict, timeout: float = 240.0) -> dict:
    cid = ch.send(cmd, args)
    r = ch.wait(cid, timeout=timeout, cmd=cmd)
    try:
        d = r.as_dict()
    except BridgeError:
        return {"__error__": str(r.result)}
    payload = d.get("result")
    if not isinstance(payload, dict):
        payload = d if isinstance(d, dict) else None
    return payload if isinstance(payload, dict) else {"__error__": str(payload)}


def ensure_in_hotbar(ch: Channel, bot: str, want: str):
    """把含 want 的那堆挪进快捷栏 ✓（假人自己搬不动槽位 ✗ 用原版 /item ✓）"""
    inv = call(ch, "bot_inv", {"bot": bot})
    items = inv.get("items") or []
    hot = [it for it in items if 0 <= int(it.get("slot", -1)) <= 8]
    for it in hot:
        if want in it["id"]:
            return int(it["slot"])
    src = next((int(it["slot"]) for it in items
                if want in it["id"] and 9 <= int(it.get("slot", -1)) <= 35), None)
    if src is None:
        return None
    occupied = {int(it["slot"]) for it in hot}
    free = [s for s in range(9) if s not in occupied]
    if not free:
        return None
    dst = free[0]
    call(ch, "cmd", {"text": "item replace entity %s hotbar.%d from entity %s inventory.%d"
                             % (bot, dst, bot, src - 9)})
    return dst


def main(argv: list[str]) -> int:
    a, i = {"bot": "Bot", "who": "cmd0"}, 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            a[k] = argv[i + 1]; i += 2
        else:
            a[k] = True; i += 1
    if not all(k in a for k in ("x0", "y0", "z0", "x1", "y1", "z1")):
        print(__doc__)
        return 2
    bot = a["bot"]
    box = {k: int(a[k]) for k in ("x0", "y0", "z0", "x1", "y1", "z1")}
    ch = Channel(who=a["who"])

    # ① 耕地（含状态 ✓）
    snap = call(ch, "snapshot", dict(box, match="farmland", maxcells=400))
    farm = snap.get("cells") or []
    print("耕地 %d 块 ✓" % len(farm))
    if not farm:
        print("[=] 这区域没有耕地 ✓ 收工")
        return 0

    # ② 只看"上方是空气"的（= 空着的 ✓）
    xs = [c["x"] for c in farm]; ys = [c["y"] for c in farm]; zs = [c["z"] for c in farm]
    above = call(ch, "snapshot", {"x0": min(xs), "y0": min(ys) + 1, "z0": min(zs),
                                  "x1": max(xs), "y1": max(ys) + 1, "z1": max(zs),
                                  "maxcells": 2000})
    occupied = {(c["x"], c["y"], c["z"]) for c in (above.get("cells") or [])}
    empty = [c for c in farm if (c["x"], c["y"] + 1, c["z"]) not in occupied]
    print("其中空着 %d 块 ✓（上面已有东西的算种过了 ✓）" % len(empty))
    if not empty:
        print("[=] 全都种上了 ✓ 收工")
        return 0

    # ③ 逐格补种（先确保种子在手上 ✓ 搬不进就明确放弃 ✗ 不乱试 ✗）
    if ensure_in_hotbar(ch, bot, "wheat_seeds") is None:
        print("[X] 种子的堆搬不进快捷栏 ✗（背包满？）—— 拒绝乱种 ✗")
        return 1
    planted, failed = 0, []
    for c in empty:
        x, y, z = c["x"], c["y"], c["z"]
        # ★ 站到跟前 ✓（收/种必须与拾取同位置 —— 这条是丢过 30 株收成的教训 ✗）
        call(ch, "cmd", {"text": "tp %s %.4f %d %.4f" % (bot, x + 0.5, y + 1, z + 0.5)})
        h = call(ch, "hold_item", {"bot": bot, "item": "wheat_seeds"})
        if "__error__" in h or not str(h.get("held_item", "")).find("seeds") >= 0:
            failed.append({"at": [x, y, z], "why": "手里没有种子"})
            continue
        call(ch, "cmd", {"text": "player %s look at %.2f %.2f %.2f" % (bot, x + 0.5, y + 0.95, z + 0.5)})
        call(ch, "cmd", {"text": "player %s use once" % bot})
        planted += 1
    print("补种 %d 格 ✓ 失败 %d ✗" % (planted, len(failed)))
    for f in failed[:5]:
        print("   ✗ %s" % json.dumps(f, ensure_ascii=False))

    # ④ 自证：重扫小麦，看是不是真的长出来了 ✓
    after = call(ch, "snapshot", dict(box, match="wheat", maxcells=400))
    print("现在小麦 %d 株 ✓（含原本就有的 ✓）" % len(after.get("cells") or []))
    inv = call(ch, "bot_inv", {"bot": bot})
    for it in inv.get("items") or []:
        if "wheat_seeds" in it["id"]:
            print("剩余种子: %d ✓" % it["count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
