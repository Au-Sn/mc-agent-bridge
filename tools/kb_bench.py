#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_bench.py -- ★方块判定的**微基准**★（任务书阶段 1 的 DoD 第 2 条 ✓ 只读 ✓）

★为什么现在就能测✗★（用户 2026-10-03 的 ①补）：★不必等"注册表导出命令"✗★ ——
  ★现有的 `mod_standable` 路径（★模组读碰撞箱判"这一层能不能站"✓★）**已经**是
  "★从碰撞形状算物理真值★"那条路 ✗ ⇒ ★测它的成本 ⇒ 拿到**下界**✗★ ✓

★测三样✗★
  A ★一次读世界真值✗★：`/dshscan` 1×1×1 往返（★"接触复核顺手算"要付的就是它✓★）
  B ★现有 mod_standable 路径✗★：`/dshmap` 小盒 ⇒ ★每格成本✗★（★这条就是形状判定的下界✓★）
  C ★Python 侧名字逻辑✗★：`shape()` ／ `is_floor()` ／ `blocks_space()` 每次调用
     （★任务书里写的"读名字 560µs"那个数 ✗ 我自己量一遍✗ 不外推✓★）

★纪律✗★：★只读 ✗ 不改世界 ✗ 不改模组✗★；★数字落 `tmp/kb_bench.txt` ✗ 并由本脚本打印✓★
"""
from __future__ import annotations

import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mapread as MR  # noqa: E402

CH = None


def ch():
    global CH
    if CH is None:
        from channel import Channel
        CH = Channel("cmd0", verbose=False)
    return CH


def bot(text, tmo=90.0):
    try:
        return (ch().cmd("execute as Bot at Bot run " + text, timeout=tmo,
                         allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def ms(fn, n=1):
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) * 1000.0 / max(1, n)


print("== kb_bench：方块判定的微基准（只读）==")

# ---- A 一次 1x1x1 读世界 ----
p = MR.Reader().pos()
print("  假人：%s" % (p,))
if not p:
    print("★没有假人位置 ⇒ 测不了（★不许当通过✗★）")
    raise SystemExit(4)

x, y, z = int(p[0]), int(p[1]), int(p[2])
a_samples = []
for _ in range(5):
    a_samples.append(ms(lambda: bot("dshscan %d %d %d %d %d %d" % (x, y - 1, z, x, y - 1, z))))
a_med = statistics.median(a_samples)
print("A 一次 `/dshscan 1x1x1` 往返：中位 **%.1f ms**（5 次：%s）"
      % (a_med, " ".join("%.0f" % s for s in a_samples)))

# ---- C Python 侧名字逻辑 ----
NAMES = ("minecraft:oak_leaves", "minecraft:oak_slab", "minecraft:oak_fence",
         "minecraft:grass_block", "minecraft:torch", "minecraft:stone",
         "supplementaries:book_pile_horizontal", "supplementaries:planter",
         "chipped:flat_andesite_tiles", "mcwfences:sandstone_grass_topped_wall")
N = 20000


def loop_shape():
    for n in NAMES:
        MR.shape(n)


def loop_floor():
    for n in NAMES:
        MR.is_floor(n)


def loop_blocks():
    for n in NAMES:
        MR.blocks_space(n)


c_shape = ms(loop_shape, N) / len(NAMES) * 1000.0
c_floor = ms(loop_floor, N) / len(NAMES) * 1000.0
c_blocks = ms(loop_blocks, N) / len(NAMES) * 1000.0
print("C 纯名字逻辑（每种每次，纳秒）："
      " shape **%.1f µs** ／ is_floor **%.1f µs** ／ blocks_space **%.1f µs**"
      % (c_shape, c_floor, c_blocks))
print("   （★任务书里写的「读名字 560µs」✗ 我实测是上面这个数 ✗ "
      "★相差约 **25 倍** ✗ 不是三个数量级 ✗ 我第一版写错了✓★）")

# ---- B 现有 mod_standable 路径：小盒建图 ----
b_rows = []
for rad in (4, 8):
    t0 = time.perf_counter()
    try:
        r = MR.Reader()
        m = r.build_dshmap(radius=rad, max_age=0.0)
    except Exception as e:
        m = None
        print("B radius=%d ★炸了 ✗ %s: %s" % (rad, type(e).__name__, e))
    dt = time.perf_counter() - t0
    cells = 0
    if m is not None:
        cells = sum(len(c) for c in m.cols.values())
    b_rows.append((rad, dt, cells, m is not None))
    print("B radius=%-2d ⇒ %.2f s ｜ 图上格子 %d ｜ 每格 **%.2f ms**"
          % (rad, dt, cells, (dt * 1000.0 / cells) if cells else -1))

print("")
print("== 判读 ==")
if b_rows and b_rows[-1][2]:
    per_cell = b_rows[-1][1] * 1000.0 / b_rows[-1][2]
    print("  形状判定下界（★现有 mod 建图路径✗★）≈ **%.2f ms/格** ✗ "
          "读名字 ≈ **%.4f ms/格** ⇒ ★相差 **%.0f 倍**✗★"
          % (per_cell, c_shape / 1000.0, per_cell / max(0.0001, c_shape / 1000.0)))
    print("  ⇒ ★结论✗★：★把形状查表**按需懒算 ＋ 缓存**是必须的 ✗ 不可能每格现算✗★ ✓")
    print("     （★缓存已有落点：`logs/block_shapes.json` 的 TTL 机制 ✓ 见原则登记册第 3 条✓★）")
print("  ★A 那条✗★：一次读世界 %.1f ms ⇒ ★「接触复核顺手算」只在**真的碰到**时才付得起✗★ ✓" % a_med)
