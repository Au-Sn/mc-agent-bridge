#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""harvest.py —— 收庄稼（小麦）：扫描 → 只收成熟 → 收完**补种** ✓

★ 2026-09-19 晚：**改成"作业层"的薄壳** ✗（原来是**第二份实现** ✗）★

为什么这么改 ✓（不是"换了个写法"✗）：
  用户的下一步要求是 ✓：「把**收割 → 补种**做成**一条作业**」✗
  ⇒ 作业落在 `agent/jobs.py` 的 `harvest_and_replant` ✓（技能层 `harvest` ✓ 也走它 ✓）
  ⇒ 那这个文件**就不该再有一份自己的实现** ✗ —— 两份实现的下场是
    "改了一份、忘了另一份" ✗ ⇒ 现场表现成"同一个操作、两种行为"✗
    （本项目已经因为"碎片化"丢过收成 ✗ 见错题本 M4 / P19.1 ✓）
  ⇒ 所以保留**参数一个不改** ✓ 只把里面的活**转发给作业** ✓
    （`--x0 … --z1` ✓ `--no-replant` ✓ `--bot` ✓ `--who` ✓ 都照旧 ✓）

它现在做的一整件事（全在一个作业里 ✓ 自带前置检查 ＋ 自带自证 ✓）：
   ① **背包守卫**：空位不够就往容器塞 ✓ 塞不出来就**拒绝开工** ✓（绝不丢地上 ✗ P19.1 ✓）
   ② 只收**成熟**的（`age>=7` ✓ 青苗只掉种子 ✗ 白收 ✗）
   ③ **逐株走到跟前**再收 ✓（收与捡必须同位置 ✗ 丢过 30 株 ✗ M4 ✓）
   ④ 收完**就地补种** ✓ 顺手把**本来就空着**的耕地也种上 ✓
   ⑤ **重扫世界 ＋ 数背包**自证 ✗（不听动作自述 ✗）

用法（**没变** ✓）：
    py tools/harvest.py --x0 4109 --y0 70 --z0 8 --x1 4113 --y1 71 --z1 11
    py tools/harvest.py --x0 ... --no-replant      # 只收不补种（仅在明确要求时用 ✗ 会把田收秃 ✗）
    py agent/jobs.py harvest --x0 ...              # 等价的直接入口 ✓
    py agent/run.py do harvest x0=... z1=...       # 技能层入口 ✓（大脑用这个 ✓）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel              # noqa: E402
from jobs import harvest_and_replant     # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def main(argv: list[str]) -> int:
    a, i = {}, 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            a[k] = argv[i + 1]
            i += 2
        else:
            a[k] = True
            i += 1
    if not all(k in a for k in ("x0", "y0", "z0", "x1", "y1", "z1")):
        print(__doc__)
        return 2
    box = {k: int(a[k]) for k in ("x0", "y0", "z0", "x1", "y1", "z1")}
    bot = a.get("bot", "Bot")
    replant = not a.get("no-replant")
    ch = Channel(who=a.get("who", "cmd0"))
    r = harvest_and_replant(ch, box, bot=bot, replant=bool(replant))
    print("-" * 70)
    print("作业结果：%s ｜ %s" % ("成功 ✓" if r["ok"] else "**失败 ✗**", r["why"]))
    for f in r["failed"][:8]:
        print("   ✗ %s" % json.dumps(f, ensure_ascii=False)[:160])
    print("   自证：重扫小麦 %s 株 ｜ 背包 小麦 %s ／ 种子 %s ｜ 用时 %ss"
          % (r.get("wheat_after", -1), r.get("wheat", -1), r.get("wheat_seeds", -1),
             r.get("elapsed")))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
