#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
block_at.py — 一次问多个方块的权威状态，输出紧凑一行一格

为什么需要它（真实痛点）：
  验证世界状态是我最频繁的操作 ✓ 但一直靠"往收件箱写 JSON + 用正则从日志里抠字段" ✗
  而那个正则在长回传上**屡次漏匹配** ✗（一次查 4 格只打出 2 格 ✓ 每次都白白丢证据 ✗）。
  这个工具做三件事：
    1. 复用已经验证过的 `agent/channel.py` ✓（它自己会认领网关分配的 id ✓ 不用我猜）
    2. 直接读解析后的字典 ✓ **不碰正则** ✓
    3. 一行一格 + 可选的 NBT 摘要 ✓ 省上下文 ✓

用法：
    py tools/block_at.py 4109 70 1                 # 一格
    py tools/block_at.py 4109 70 1 4115 70 1      # 多格
    py tools/block_at.py --nbt 4109 71 1          # 附带方块实体 NBT（诊断神器 ✓）
    py tools/block_at.py --only-var 4109 70 1     # 只打印非 air 的格子
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from channel import Channel, BridgeError  # noqa: E402

AIR = {"minecraft:air", "air", "minecraft:cave_air", "minecraft:void_air"}


def main(argv: list[str]) -> int:
    want_nbt = "--nbt" in argv
    only_var = "--only-var" in argv
    nums = [a for a in argv if not a.startswith("--")]
    if len(nums) < 3 or len(nums) % 3 != 0:
        print(__doc__)
        return 2
    triples = []
    try:
        for i in range(0, len(nums), 3):
            triples.append((int(nums[i]), int(nums[i + 1]), int(nums[i + 2])))
    except ValueError:
        print("[X] 坐标必须是整数：x y z 三个一组")
        return 2

    ch = Channel("cmd0", verbose=False)
    bad = 0
    for (x, y, z) in triples:
        try:
            d = ch.verify_block(x, y, z)
        except (BridgeError, Exception) as e:      # 通道问题不该让整批失败
            print("(%d,%d,%d)  查询失败: %s: %s" % (x, y, z, type(e).__name__, e))
            bad += 1
            continue
        name = str(d.get("name") or "?")
        if only_var and name in AIR:
            continue
        line = "(%d,%d,%d)  %s" % (x, y, z, name)
        st = d.get("state")
        if st:
            bits = ",".join("%s=%s" % (k, v) for k, v in st.items() if v not in (False, None))
            if bits:
                line += "  [%s]" % bits
        if want_nbt and d.get("block_entity"):
            # ⚠ 这里曾经截断到 300 字符 ✗ —— 而海龟/计算机的方块实体 NBT 很长 ✓
            #   结果"Items 字段不见了"被我误读成"服务端没有库存" ✗✓（差一点又下一个错结论 ✗）
            #   → 截断必须**足够大** ✓ 而且最好把长度也报出来 ✓ 让人知道有没有被截 ✓
            raw = str(d["block_entity"])
            limit = 2000
            line += "\n            NBT(%d 字符): %s%s" % (
                len(raw), raw[:limit], "…【已截断】" if len(raw) > limit else "")
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
