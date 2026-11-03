#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wait_for_item.py —— 等玩家把某样东西**丢到假人附近**，假人自己走过去捡起来

为什么需要它（2026-09-18 晚）：
  整条自给链唯一的外部输入是"第一个工作台" ✓ 而且已经用**全档扫描**证明：
  世界里一个工作台方块都没有 ✓ 唯一一个在玩家背包里 ✓（见 tools/find_item_in_save.py）。
  玩家愿意"丢在假人旁边"——那就需要一个**自动接手**的动作 ✓：
    轮询假人周围的掉落物 → 走过去 → 捡起来 → 用背包 NBT 验收 ✓
  全程不需要玩家再操作 ✓ 也不需要 /give ✓（只是"把东西放进世界"而已 ✓）。

用法：
    py tools/wait_for_item.py crafting_table                 # 等最多 15 分钟
    py tools/wait_for_item.py crafting_table --seconds 1800
    py tools/wait_for_item.py oak_log --bot Bot --radius 12
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel, BridgeError  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

POS_RE = re.compile(r"\[\s*(-?\d+(?:\.\d+)?)d?,\s*(-?\d+(?:\.\d+)?)d?,\s*(-?\d+(?:\.\d+)?)d?\s*\]")


def bot_has(ch: Channel, bot: str, needle: str) -> bool:
    """假人背包里有没有这样东西（读**背包 NBT** ✓ 不看自述 ✓）。"""
    try:
        r = ch.cmd("data get entity %s Inventory" % bot, allow_str=True, timeout=30.0)
    except BridgeError:
        return False
    return needle in " ".join(r.lines())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("item", help="物品 id 片段，例如 crafting_table")
    ap.add_argument("--bot", default="Bot")
    ap.add_argument("--radius", type=float, default=12.0, help="在假人多大范围内找掉落物")
    ap.add_argument("--seconds", type=float, default=900.0, help="最多等多久")
    ap.add_argument("--poll", type=float, default=3.0)
    args = ap.parse_args()

    ch = Channel()
    t0 = time.time()
    print("=" * 64)
    print("等 %s 出现在 %s 周围 %.0f 格内（最多 %.0f 秒）…" % (args.item, args.bot, args.radius, args.seconds))
    print("=" * 64)
    last_note = 0.0
    while time.time() - t0 < args.seconds:
        if bot_has(ch, args.bot, args.item):
            print("[OK] %s 已经在 %s 的背包里了（NBT 验收 ✓）" % (args.item, args.bot))
            return 0
        # 在假人位置上执行查询：sort=nearest 才会以**假人**为中心 ✓
        try:
            r = ch.cmd("execute at %s run data get entity @e[type=minecraft:item,distance=..%d,sort=nearest,limit=1] Pos"
                       % (args.bot, int(args.radius)), allow_str=True, timeout=30.0)
            m = POS_RE.search(" ".join(r.lines()))
        except BridgeError as exc:
            m = None
            print("[!] 查询失败（继续等）：%s" % exc)
        if m:
            x, y, z = (float(g) for g in m.groups())
            print("[..] 发现掉落物 @ (%.1f, %.1f, %.1f) —— 让 %s 走过去" % (x, y, z, args.bot))
            try:
                ch.cmd("tp %s %.2f %.2f %.2f" % (args.bot, x, y + 0.2, z), allow_str=True, timeout=30.0)
            except BridgeError as exc:
                print("[!] 传送失败：%s" % exc)
            time.sleep(2.0)
            if bot_has(ch, args.bot, args.item):
                print("[OK] 捡到了 ✓ %s 的背包里出现 %s（NBT 验收 ✓）" % (args.bot, args.item))
                return 0
            print("[..] 还没进背包（可能被别的实体/玩家拿走，或还没靠近）")
        else:
            waited = time.time() - t0
            if waited - last_note > 30:
                last_note = waited
                print("[..] 已等 %.0f 秒，还没看到掉落物" % waited)
        time.sleep(args.poll)
    print("[X] 超时：%.0f 秒内没等到 %s" % (args.seconds, args.item))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
