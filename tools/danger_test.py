#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""danger_test.py -- 危险要拦住, 而水要照旧能过（D1~D4 离线 2026-10-13 §79.222）

用户裁决 C5: 政策默认"回避进入"。
这一条守的是"补危险"的两头:
  一头: 岩浆/火/岩浆块 必须被拦住(DANGER)
  另一头: ★水必须照旧能过★ —— 补危险最容易误伤的就是水(它在碰撞上是 lava 的同类)
另加 D4: 政策不许动物理(blocks_space 只听碰撞)。
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import environment as ENV
import mapread as MR
import passclass as PC
import reach_probe as RP

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


print("== danger: D1~D4 ==")

# ---- D1 岩浆/火/岩浆块 判 DANGER
bad = []
for sp in ("minecraft:lava", "minecraft:magma_block"):
    c = PC.class_of(sp)[0]
    if c != "DANGER":
        bad.append((sp, c))
check("D1", not bad,
      "岩浆/岩浆块 判 DANGER ⇒ %s" % (bad or "两个都对"))

# ---- D2 探针不许穿过危险格
k_lava = RP._kind("minecraft:lava")
check("D2", k_lava == "solid",
      "探针 _kind(岩浆) ＝ %s（★必须 solid ⇒ 不许穿过✓★）" % k_lava)

# ---- D3 ★水必须照旧能过★（补危险最容易误伤的就是它）
k_water = RP._kind("minecraft:water")
w_cls = PC.class_of("minecraft:water")[0]
check("D3", k_water == "pass" and w_cls == "LIQUID",
      "水 ⇒ class=%s ✗ _kind=%s（★必须 pass ✓ 不许被岩浆连坐✗★）" % (w_cls, k_water))

# ---- D4 政策不许动物理：blocks_space 只听碰撞
sp_l, sp_w = "minecraft:lava", "minecraft:water"
before = (MR.blocks_space(sp_l), MR.blocks_space(sp_w))
ENV.safe((0, 0, 0))                     # 问一次政策
after = (MR.blocks_space(sp_l), MR.blocks_space(sp_w))
check("D4", before == after,
      "问过政策之后 blocks_space 不变 ⇒ %s ⇒ %s" % (before, after))

# ---- D5 safe() 三态
s_lava = ENV.safe((0, 0, 0))            # 没绑定 ⇒ 应当 None
check("D5", s_lava is None,
      "没绑定格子时 safe() ＝ %s（★不许假装安全✗★）" % (s_lava,))

print("=> danger %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
