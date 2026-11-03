#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mapcache_test.py -- ★连通区缓存：**快**✗ 而且**不许读到旧图**✗★（M1~M4 ✓ 全离线 ✓ 秒级 ✓）

WHY（2026-09-30 第 40 轮 ✓ ⇒ P148 ✓）：
  `Planner.region()`（连通区洪泛 ✓）实测 **0.79 秒** ✗ 而 `walk_route` **每一跳新建 Planner** ✗
  ⇒ 一张图被反复洪泛 ✗（一腿 4 跳 ≈ 3 秒 × 4 ✗）
  ⇒ 想缓存 ⇒ ★必须能判断"图变没变"✗★ —— 而"逐个改动点失效缓存"是**错的路子** ✗
    （漏一个 ⇒ 静默用旧连通区 ✗ ⇒ 又造出"假 unreachable" ✗ ★本项目最恨的那种✗★）
  ⇒ 做法 ✓：`Map` 自带**版本号** `rev` ✗（任何改动 +1 ✓ `bump()` ✓）⇒ 缓存键带上它 ✓

CRITERIA（跑之前先写 ✓ 全离线 ✓ 合成图 ✓ 不读世界 ✗）
  M1 第二次要快 ：同一张图、同一个起点 ⇒ `region()` 第 2 次 **≤ 第 1 次的 1/3** ✓
                  且两次**结果完全相同** ✓（★快而不一样 ＝ 缓存串味✗★）
  M2 改了图就重算：改图 ⇒ `bump()` ⇒ 缓存**必须失效** ✗ ⇒ 结果要反映**改后**的图 ✓
                  （★这条是**正确性**✗★：宁可慢 ✗ 也不许拿旧连通区去规划 ✓）
  M3 配置不串味 ：`level` 不同 ⇒ 键不同 ⇒ 各自算各自 ✓（不许拿别的层的连通区 ✗）
  M4 与"全新建图"一致：缓存出来的结果 必须 ＝ 用**一张全新的等价图**算出来的结果 ✓
                  （★"等价图"＝同样的格子 ✓ 只是没走过缓存 ✓★）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mapread as MR      # noqa: E402
import pathplan as PP     # noqa: E402


def say(s):
    print(s, flush=True)


def grid(size: int = 30, y: int = 70, hole=None):
    """★合成一张**平地**（`size×size` ✓ 地板 y ✓）✗★ —— 离线 ✓ 确定性 ✓ 且够大（≈900 格 ✓）"""
    m = MR.Map(0, y - 6, 0, size - 1, y + 6, size - 1)
    for x in range(size):
        for z in range(size):
            if hole and (x, z) == hole:
                continue
            m.cols[(x, z)] = {y: "minecraft:grass_block"}
    m.meta.update({"blevel": y + 1, "has_offsets": True})
    return m


def main() -> int:
    ok = True

    # ---- M1：第二次要快（且结果一致）----
    m = grid()
    pl = PP.Planner(m, level=71)
    t0 = time.time(); r1 = pl.region(15, 15); t1 = time.time()
    r2 = pl.region(15, 15); t2 = time.time()
    s1, s2 = t1 - t0, t2 - t1
    m1 = (r1 == r2) and (len(r1) > 700) and (s2 <= max(0.02, s1 / 3.0))
    say("M1 第二次要快：第1次 %.3fs ⇒ %d 格 ｜ 第2次 %.4fs ｜ 结果相同=%s "
        "（要 ≤ 第1次/3 = %.3fs）=> %s"
        % (s1, len(r1), s2, r1 == r2, max(0.02, s1 / 3.0), m1))
    ok &= m1

    # ---- M2：改了图就重算 ----
    #   ★判据自己错过一次✗★（第 40 轮 ✓ 第一版只在 `z=10` 挖 **x 10..20 那一段** ✗
    #     ⇒ 那面墙**切不断**连通区 ✓（可以从两头绕过去 ✓）⇒ 900→889 ✗ ⇒ 假红 ✓）
    #   ⇒ 口径 ✓：要**横贯整幅**地挖掉一整排柱子 ✗ 才能真的把区域切开 ✓
    for x in range(0, 30):
        m.cols.pop((x, 10), None)
    m.bump()
    r3 = PP.Planner(m, level=71).region(15, 15)
    # 起点 (15,15) 在 z=10 的**另一侧** ⇒ 区域该只剩**那半边** ✓（30 宽 × 19 排 = 570 ✓）
    #   ★判据自己又错一次✗★：第一版写"必须掉一半以上"✗ —— 可 570 恰好是**正确**的 ✓
    #     （墙在 z=10 ⇒ z ≥ 11 有 **19** 排 ✓ 30×19 = 570 ✓）⇒ 假红 ✓
    #   ⇒ 口径 ✓：**别数格子** ✗ 改成**语义检查**：墙对面那一格**必须不在**区域里 ✗★
    m2 = (len(r3) < len(r1)) and ((0, 0) not in r3) and ((15, 15) in r3)
    say("M2 改了图就重算：横贯挖掉 z=10 那一排 ＋ `bump()` ⇒ %d 格（原来 %d ✓）｜ "
        "墙对面 (0,0) 在不在=%s（要 **不在** ✗）=> %s"
        % (len(r3), len(r1), (0, 0) in r3, m2))
    ok &= m2

    # ---- M3：配置不串味 ----
    #   ★判据自己也错过一次✗★：第一版拿 `level=72` 当"那一层是空气" ✗ ——
    #     可 `reachable_floor` 允许**往下 3 格** ✓ ⇒ 72 照样能找到 y=70 的地板 ✓ ⇒ 900 格 ✗ 假红 ✓
    #   ⇒ 口径 ✓：挑一个**超出落差窗口**的层 ✗（76 − 70 = 6 > down=3 ✓）⇒ 那才是真的站不住 ✓
    #   ★第二次也错✗★：断言"缓存键 ≥2" ✗ —— ★空结果**不入缓存**✗★（提前 return ✓ 正确 ✓）
    #   ⇒ 口径 ✓：只查**语义** ✓ ＋ "另一个层的调用**不许污染**这一层的结果" ✗★
    m3b = grid()
    a = PP.Planner(m3b, level=71).region(15, 15)
    b = PP.Planner(m3b, level=76).region(15, 15)
    a2 = PP.Planner(m3b, level=71).region(15, 15)      # ★再问一次 71 ⇒ 必须和第一次一致✗★
    m3 = (len(a) > 0) and (len(b) == 0) and (a2 == a)
    say("M3 配置不串味：level=71 ⇒ %d 格 ｜ level=76（超出落差窗口 ✗）⇒ %d 格 ｜ "
        "再问 71 ⇒ %d 格（要和第一次**一致** ✗）=> %s" % (len(a), len(b), len(a2), m3))
    ok &= m3

    # ---- M4：与"全新建图"一致 ----
    m4a = grid()
    _ = PP.Planner(m4a, level=71).region(15, 15)     # 先走一次缓存 ✓
    cached = PP.Planner(m4a, level=71).region(15, 15)
    fresh = PP.Planner(grid(), level=71).region(15, 15)   # ★另建一张等价图 ⇒ 没缓存✗★
    m4 = (cached == fresh)
    say("M4 与全新建图一致：缓存 %d 格 ｜ 全新建图 %d 格 ｜ 相同=%s => %s"
        % (len(cached), len(fresh), cached == fresh, m4))
    ok &= m4

    say("---- M1..M4 = %s ----" % ok)
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
