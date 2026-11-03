#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sift_loop.py —— 让**假人自己**筛矿（闭环版：每轮先归位、再读筛子 NBT、再决定动作）

筛矿机制（2026-09-19 实测解出 ✓ 卡了两轮 ✗）：
    1. **拿着可筛物（gravel）右击** = 放料 ✓ 筛子 `contents` 只收 1 个 ✓
    2. **之后右击（手里不是可筛物）** = 推进进度 ✓ **每次 +0.1** ✓ 满 1.0 出料并清空 `contents` ✓
       （世界 NBT 实证：`progress 0.0f → 0.5f`（5 次）✓ 出料后回到 `0.0f` 且 `contents` 消失 ✓）

★两条把这一轮坑掉的血泪教训★（都已在 NBT 上验过 ✓）：
    A. **不 `look at` 筛子 = 右键全打在空气上** ✗
       表现极具迷惑性：筛子 NBT 一动不动 ✓ 沙砾一个不少 ✓ 看起来像"机制没生效" ✗
    B. **假人会被挤走** ✗（实测跑到 5 格外 ✓）→ 后面所有点击全部落空 ✗
       而"完成 16 次筛矿"这种自述照样打印 ✓ —— **只有读 NBT 才发现真相** ✗
       ⇒ 所以每轮**必须先归位（tp）+ 重新瞄准** ✓✓ 这就是"闭环"两个字的由来 ✓

用法：
    py tools/sift_loop.py --sifts 8
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

# ⚠ 带 tag 的物品在 NBT 里 id 与 Count 之间夹着 tag ✗ → 匹配要宽松 ✓（错题本 8.2 ✓）
def _count(txt: str, needle: str) -> int:
    total = 0
    for m in re.finditer(re.escape(needle) + r'"(?:, tag: \{[^}]*\})?, Count: (\d+)b', txt):
        total += int(m.group(1))
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sifts", type=int, default=8)
    ap.add_argument("--gravel", default="minecraft:gravel")
    ap.add_argument("--idle", default="minecraft:diamond_axe", help="推进进度时手里拿的（不能是可筛物）")
    ap.add_argument("--clicks", type=int, default=11, help="每轮最多点几次（一次 +0.1 ⇒ 11 次足够跑完一轮）")
    ap.add_argument("--bot", default="Bot")
    ap.add_argument("--sieve", default="4127 71 11")
    ap.add_argument("--stand", default="4128.5 71 11.5", help="每轮把假人拉回的站位")
    args = ap.parse_args()

    ch = Channel()
    sx, sy, sz = (float(v) for v in args.sieve.split())
    bx, by, bz = (float(v) for v in args.stand.split())
    sep = "=" * 62
    print(sep)
    print("假人闭环筛矿：目标 %d 次 ｜ 站 %s ｜ 筛子 (%g,%g,%g)" % (args.sifts, args.stand, sx, sy, sz))
    print(sep)

    def inv_text() -> str:
        try:
            return " ".join(ch.cmd("data get entity %s Inventory" % args.bot, allow_str=True, timeout=30.0).lines())
        except BridgeError:
            return ""

    def sieve_state() -> tuple[float, bool]:
        """读筛子 NBT：返回 (progress, 是否已装料) ✓ —— 这是**唯一可信**的进度来源 ✓"""
        try:
            txt = " ".join(ch.cmd("data get block %g %g %g" % (sx, sy, sz), allow_str=True, timeout=30.0).lines())
        except BridgeError:
            return -1.0, False
        mp = re.search(r"progress:\s*([\d.]+)f", txt)
        prog = float(mp.group(1)) if mp else -1.0
        return prog, ("contents:" in txt)

    def reset_bot():
        """★每轮必做★：拉回站位 + 瞄准筛子碗内 ✓（省了这一步，后面全白干 ✗）"""
        ch.cmd("tp %s %.2f %.2f %.2f" % (args.bot, bx, by, bz), allow_str=True, timeout=20.0)
        ch.cmd("player %s look at %.2f %.2f %.2f" % (args.bot, sx + 0.5, sy + 0.3, sz + 0.5),
               allow_str=True, timeout=20.0)

    peb0 = _count(inv_text(), "exdeorum:stone_pebble")
    gr0 = _count(inv_text(), args.gravel)
    print("起始：原料 %d 个 ｜ 石砾 %d 个" % (gr0, peb0))

    done = 0
    for k in range(args.sifts):
        reset_bot()
        prog, has = sieve_state()
        if prog < 0:
            print("[X] 读不到筛子 NBT → 停")
            break
        if not has:
            # 放料：手里拿可筛物点一下 ✓
            if _count(inv_text(), args.gravel) < 1:
                print("[!] 原料用完了 → 停")
                break
            ch.call("hold_item", {"bot": args.bot, "item": args.gravel}, timeout=20.0, allow_str=True)
            reset_bot()
            ch.call("use_once", {"bot": args.bot}, timeout=20.0, allow_str=True)
            time.sleep(0.3)
            prog, has = sieve_state()
            if not has:
                print("  [!] 第 %d 轮：放料后筛子 contents 仍为空 ✗（这一轮跳过）" % (k + 1))
                continue
        # 推进：**一次算好要点几下**（每次 +0.1 ✓ 少读 NBT ✓ 否则一轮要 35 条指令 ✗ 实测会超时 ✓）
        ch.call("hold_item", {"bot": args.bot, "item": args.idle}, timeout=20.0, allow_str=True)
        need = max(1, int(round((1.0 - prog) * 10)) + 2)
        n = 0
        for i in range(need):
            ch.call("use_once", {"bot": args.bot}, timeout=20.0, allow_str=True)
            n += 1
            time.sleep(0.12)
            if i % 4 == 3:                     # 每 4 次复核一次站位 ✓（被挤走就拉回来 ✓）
                try:
                    pos = " ".join(ch.cmd("data get entity %s Pos" % args.bot, allow_str=True, timeout=20.0).lines())
                    m = re.search(r"\[(-?[\d.]+)d,\s*(-?[\d.]+)d,\s*(-?[\d.]+)d\]", pos)
                    if m and (abs(float(m.group(1)) - bx) > 1.0 or abs(float(m.group(3)) - bz) > 1.0):
                        reset_bot()
                except BridgeError:
                    pass
        p2, h2 = sieve_state()
        done += 1
        print("  第 %2d 轮：点了 %d 次 ✓ 筛子 %.2f → %s" %
              (k + 1, n, prog, ("出料 ✓" if not h2 else "%.2f" % p2)))

    time.sleep(1.5)
    txt = inv_text()
    peb1, gr1 = _count(txt, "exdeorum:stone_pebble"), _count(txt, args.gravel)
    print("-" * 62)
    print("完成 %d 轮 ｜ 原料 %d → %d ｜ **石砾 %d → %d（+%d）**" % (done, gr0, gr1, peb0, peb1, peb1 - peb0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
