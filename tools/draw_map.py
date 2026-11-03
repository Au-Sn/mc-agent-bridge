#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""draw_map.py —— 把 Bot 周围一层地形**画成 ASCII 图** ✓（诊断"为什么走不过去" ✗）

为什么要它 ✗（本项目纪律：别猜 ✓ 要量 ✓）：
  `walkStatus` 只会说 `blocked` ＋ 几个布尔值 ✓
  而"为什么四向都走不了"要看**地形** ✓ —— 一张图比十行布尔值有用得多 ✓

画法 ✓：对每个 (x,z) 查三层 ✓
  脚下（feet-1）有没有支撑 ✓ ｜ 脚层（feet）通不通 ✓ ｜ 头层（feet+1）通不通 ✓
  符号 ✓：`#`＝脚层被占 ✗ ｜ `.`＝能站 ✓ ｜ `^`＝脚层空但**没有支撑**（＝虚空边 / 要垫方块 ✓）
          `?`＝读不出来 ✓（一个格子读不到就标出来 ✗ 不假装知道 ✓）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)


def cell(x: int, y: int, z: int) -> dict:
    try:
        r = ch.verify_block(x, y, z)
        return r if isinstance(r, dict) else {}
    except Exception as e:
        return {"err": str(e)[:60]}


def main(argv: list[str]) -> int:
    x0 = int(argv[0]) if len(argv) > 0 else 4128
    x1 = int(argv[1]) if len(argv) > 1 else 4136
    z0 = int(argv[2]) if len(argv) > 2 else 6
    z1 = int(argv[3]) if len(argv) > 3 else 14
    y = int(argv[4]) if len(argv) > 4 else 72
    out: list[str] = []
    out.append("地形图 ✓ y(feet)=%d ｜ x=%d..%d ｜ z=%d..%d ｜ 每格 3 次查询（脚下/脚/头）✓"
               % (y, x0, x1, z0, z1))
    out.append("列=x（从左到右）✓ 行=z（从上到下＝由北到南 ✓）")
    try:
        d = ch.cmd("execute as Bot at Bot run dshdigest 4", timeout=40.0, allow_str=True).text()
        out.append("Bot 实况：%s" % (d or "").strip()[:200])
    except Exception as e:
        out.append("digest 失败：%s" % e)
    out.append("")
    header = "      " + "".join("%4d" % x for x in range(x0, x1 + 1))
    out.append(header)
    for z in range(z0, z1 + 1):
        row = []
        for x in range(x0, x1 + 1):
            below = cell(x, y - 1, z)
            feet = cell(x, y, z)
            head = cell(x, y + 1, z)
            if not feet or feet.get("err"):
                row.append("?")
                continue
            fsolid = bool(feet.get("solid"))
            fempty = not fsolid
            hsolid = bool(head.get("solid"))
            bsolid = bool(below.get("solid")) if below and not below.get("err") else False
            if fsolid or hsolid:
                row.append("#")
            elif not bsolid:
                row.append("^")
            else:
                row.append(".")
        out.append("z=%3d " % z + "".join("%4s" % c for c in row))
    out.append("")
    out.append("图例 ✓ `#`＝过不去（脚层或头层被占 ✗）｜ `.`＝能站能走 ✓ ｜ "
               "`^`＝脚层空但**脚下没支撑**（虚空边 ✗ 要垫方块 ✓）｜ `?`＝读不到 ✓")
    dest = ROOT / "logs" / "terrain_map.txt"
    dest.write_text("\n".join(out), encoding="utf-8")
    print("written %s (%d lines)" % (dest, len(out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
