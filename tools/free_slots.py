#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""free_slots.py —— 把假人背包里"暂时不用的东西"存进旁边的桶，腾出空位。

为什么要有它（用户当场指出的前提 ✗）：
    假人背包 **36/36 满** ✗ ⇒ 玩家丢给它的东西**一件都捡不起来** ✗
    （实测过两次：收的麦子捡不到 ✗ 见错题本 N3 / P17 ✓）
    ⚠ 绝对不能"丢在地上"✗ —— 掉在脚边的会被它**自己捡回去** ✗（I12 ✓）
      而丢远一点又会 **5 分钟消失** ✗（J6 ✓ 已经丢过两次货 ✗）
    ⇒ 唯一正确的做法 ✓：**放进容器** ✓（这正是真人干的事 ✓ 也正是模组要补的能力 ✓）

用法：
    py tools/free_slots.py [--dry]      # 默认真跑；--dry 只看不动
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel, BridgeError  # noqa: E402
from world import World                   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BARREL = (4122, 71, 3)          # 132 格的模组桶（模组容器 ⇒ 原版 /item 认不了 ✗ 见模组文档 ✓）
# ★ "暂时用不着"的东西（都是**攒着以后用**的建材 ✓ 放桶里最自然 ✓）
JUNK = [
    "exdeorum:diorite_pebble",
    "exdeorum:blackstone_pebble",
    "exdeorum:andesite_pebble",
    "exdeorum:basalt_pebble",
    "exdeorum:deepslate_pebble",
]


def main(argv: list[str]) -> int:
    dry = "--dry" in argv
    ch = Channel("cmd0")
    w = World(ch)

    def run(text: str, t: float = 90.0) -> str:
        r = ch.cmd("execute as Bot at Bot run " + text, timeout=t, allow_str=True)
        t2 = (r.text() or "").strip()
        return t2.splitlines()[0] if t2 else "(no reply)"

    before = w.counts()
    print("=" * 70)
    print("假人背包：%d 件 / %d 种" % (sum(before.values()), len(before)))
    print("桶 %s 现状：%s" % (BARREL, run("dshbox peek %d %d %d" % BARREL)[:100]))
    print("=" * 70)

    if dry:
        print("[--dry] 只会做这些：")
        for it in JUNK:
            print("   dshbox put %d %d %d \"%s\"" % (*BARREL, it))
        return 0

    for it in JUNK:
        # ⚠ 物品名**必须加引号** ✗（Brigadier 的 string() 不带引号时不吃冒号 ✗ 见错题本 P14 ✓）
        out = run('dshbox put %d %d %d "%s"' % (*BARREL, it))
        print("  put %-34s -> %s" % (it, out))

    after = w.counts()
    print("-" * 70)
    print("桶现在的真值：%s" % run("dshbox peek %d %d %d" % BARREL)[:220])
    print("假人背包：%d 件 / %d 种（之前 %d 种 ⇒ 腾出 **%d** 格 ✓）"
          % (sum(after.values()), len(after), len(before), len(before) - len(after)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
