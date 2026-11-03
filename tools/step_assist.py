#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step_assist.py -- 把"上不去的台阶"变成**能走上去**的（半砖坡道 ✓ 2026-09-29 第 34 轮 ✓）

WHY (为什么这条路走得通 ✓ 物理 ✓ 不是取巧 ✓)：
  Minecraft 的**自动上台阶**上限是 **0.6 格** ✓
    · **整方块**（+1.0 ✗）⇒ 必须跳 ✗ ⇒ ★模组不会跳★（第 32 轮两次实测 ✓ 停在 0.8~1.7 格外 ✓）
    · **半砖**（顶面 +0.5 ✓）⇒ **自动就走上去** ✓ ⇒ 半砖铺一级 = **不用跳的台阶** ✓
  ⇒ 做法 ✓：在"要上去的那一格"**旁边**垫一块半砖 ⇒ 原来爬不上去的那一格
    **就变成同层可达** ✓（第 34 轮的计划器已经按这条物理改过 ✓ `auto_step` ✓）
  ★不动别人的建筑★ ✗：只**加**一块半砖 ✓ 不挖任何东西 ✓

CRITERIA（跑之前先写 ✓）：
  A1 前提   ：目标格**现在**是"几何能站、执行者到不了"的（`geo.ok` ✓ 而 `exec.ok` ✗）
              ＋ 它旁边有一格**能垫**（同层、脚/头两格空 ✓）——没有 ⇒ 如实说 INCONCLUSIVE ✓
  A2 材料   ：手上要有半砖；没有 ⇒ 用**木板**在工作台做（工作台先用 4 木板在**背包 2x2**做 ✓）
              每一步都要 `dshcraft` 的回执 ✓ 拿不到 ⇒ 如实报 ✗ 不硬来 ✓
  A3 垫上   ：半砖必须**真的出现在世界里**（独立读那一格 ✓ 不是采信回执 ✓）
  A4 真上去 ：垫完之后 —— ① 规划**必须**能到那一格 ✓（目的地 = 目标格 ✓）
              ② 真走 ⇒ **独立读**：人必须在**目标那一格的脚层** ✓✓（★本轮的硬判据★）
  A5 诚实   ：任何一步没过 ⇒ 说清卡在哪 ✓ ＋ 世界被改成了什么样（垫了没垫 ✓）

用法 ✓：`py tools/step_assist.py --dry`（只找不动作 ✓）／`--target x z`（指定目标 ✓）
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mapread as MR      # noqa: E402
import mc_mcp as M        # noqa: E402
import pathplan as PP     # noqa: E402


def say(s):
    print(s, flush=True)


def main(argv) -> int:
    dry = "--dry" in argv
    want = None
    if "--target" in argv:
        i = argv.index("--target")
        try:
            want = (int(argv[i + 1]), int(argv[i + 2]))
        except Exception:
            want = None
    p = M._pos_now()
    if not p:
        say("INCONCLUSIVE: no bot position")
        return 0
    sx, sy, sz = int(p[0]), int(round(p[1])), int(p[2])
    L = sy
    say("bot at (%d,%s,%d) feet L=%d" % (sx, p[1], sz, L))

    r, m, _box = M._route_map(sx, sz, sx + 8, sz, sy)
    geo = PP.Planner(m, level=L, max_up=1)
    ex = PP.Planner(m, level=L, max_up=M.MOD_CLIMB_UP)
    reg = geo.region(sx, sz)

    # ---------------- A1: 找"爬不上去、但旁边能垫"的目标 ---------------------
    cands = []
    for (x, z) in sorted(reg, key=lambda c: math.hypot(c[0] - sx, c[1] - sz)):
        if want and (x, z) != want:
            continue
        d = math.hypot(x - sx, z - sz)
        if d < 2.0 or d > 14.0:
            continue
        fy = geo.y(x, z)
        if fy is None or (fy + 1) != L + 1:
            continue                      # 只处理"抬一级"的那种
        if ex.ok(x, z):
            continue                      # 执行者已经能到 ⇒ 不用帮
        # 旁边能垫的那一格：同层、我的层与上一层都空、且**是我能站的那一层**（≈ 我脚下这一层）
        for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ax, az = x + dx, z + dz
            col = m.cols.get((ax, az)) or {}
            if (ax, az) in M.BLOCKED:
                continue
            if col.get(L) or col.get(L + 1):
                continue                  # 那两格得有空间 ✓
            # 垫的那一格**必须在执行者够得着的范围内**（同层 ✓）
            if not ex.ok(ax, az):
                continue
            if ex.y(ax, az) + 1 != L:
                continue                  # 只垫**同层**的格子 ✓（不制造新的台阶 ✗）
            cands.append(((x, z), fy + 1, (ax, az)))
            break
    say("A1 candidates (climb-only target with a place to put a slab beside it): %d %s"
        % (len(cands), cands[:3]))
    if not cands:
        say("A1 INCONCLUSIVE: nothing to help right now => NOT a pass")
        return 0
    (gx, gz), gfeet, (ax, az) = cands[0]
    say("A1 chosen: target (%d,%d) feet y=%d | slab goes to (%d,%d) cell y=%d"
        % (gx, gz, gfeet, ax, az, L))
    if dry:
        say("--dry: stopping before touching the world")
        return 0

    # ---------------- A2: 材料（半砖；没有就现做 ✓）--------------------------
    def pack_has(name):
        raw = M.dsh("dshinv list", 40.0) or ""
        body = raw.split("=>", 1)[1] if "=>" in raw else raw
        return name in body
    def pack_count(name):
        raw = M.dsh("dshinv list", 40.0) or ""
        body = raw.split("=>", 1)[1] if "=>" in raw else raw
        n = 0
        for part in body.split():
            if part.endswith("x" + "") or ":" not in part:
                continue
            i, _, rest = part.partition(":")
            if not i.isdigit():
                continue
            nm, _, cnt = rest.rpartition("x")
            if nm == name and cnt.isdigit():
                n += int(cnt)
        return n

    def craft(item, times=1):
        """★合成走模组的 `/dshcraft do <item> [times]`★ ✓（中间层**还没有**这条工具 ⇒ 直接发 ✓）
        ⚠ 记一笔 ✗：MCP 工具表里**没有** craft（41 件里没有 ✓）⇒ 这一轮先用裸调用 ✓
          下一轮可以把它包成工具（`t_craft` ✓ 与其它工具同一套返回 ✓）
        """
        txt = M.dsh('dshcraft do "%s" %d' % (item, int(times)), 60.0) or ""
        # ★★判据按**回执里真有的字段**写 ✗（第 34 轮 ✓ 实测两份回执是**不一样的** ✓）：
        #   · `dshcraft can … ok=true out=… x6 reason=none`      ⇒ 有 `ok=` ✓
        #   · `dshcraft <item> done=1 out=… now_have=2`          ⇒ ★是 `done=` ✗ 没有 `ok=`★
        #   ⇒ 我第一版只认 `ok=true` ✗ ⇒ **把成功判成失败** ✗ ⇒ 白花 8 木板 ✓（P122 ✓）
        #   ⇒ 口径 ✓：**两个都认 ✓ 一个都不认才叫失败** ✗
        err = ("ok=true" not in txt) and ("done=" not in txt)
        return txt, err

    slab = None
    for name in ("minecraft:oak_slab", "minecraft:spruce_slab", "minecraft:birch_slab",
                 "minecraft:stone_slab", "minecraft:cobblestone_slab"):
        if pack_count(name) > 0:
            slab = name
            break
    say("A2 materials: slab in pack = %s" % slab)
    table_placed = None
    if slab is None:
        planks = pack_count("minecraft:oak_planks")
        say("A2 no slab yet; planks in pack = %d (need 4 for a table + 3 for a slab)" % planks)
        if planks < 7:
            say("A2 INCONCLUSIVE: not enough planks -- reported honestly, nothing touched")
            return 0
        ctab, etab = craft("minecraft:crafting_table", 1)
        say("   craft table -> %s (err=%s)" % ((ctab or "").strip().splitlines()[-1][:120], etab))
        if etab:
            say("A2 FAIL: cannot craft the table -- stop honestly")
            return 1
        # 放在自己旁边（同层、空的一格 ✓）
        spot = None
        for (dx, dz) in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            cx2, cz2 = sx + dx, sz + dz
            col = m.cols.get((cx2, cz2)) or {}
            if not col.get(L) and not col.get(L + 1) and (cx2, cz2) not in M.BLOCKED:
                spot = (cx2, cz2)
                break
        if not spot:
            say("A2 FAIL: no free cell beside me for the table -- stop honestly")
            return 1
        pt, ep = M.t_place_block(spot[0], L, spot[1], "minecraft:crafting_table")
        got = r.probe_cell(spot[0], L, spot[1])
        say("   place table at (%d,%d,%d) -> %s | world read = %r"
            % (spot[0], L, spot[1], (pt or "").strip().splitlines()[-1][:110], got))
        if "crafting_table" not in str(got):
            say("A2 FAIL: the table is not really there -- stop honestly")
            return 1
        table_placed = spot
        cslab, eslab = craft("minecraft:oak_slab", 1)
        say("   craft slab -> %s (err=%s)" % ((cslab or "").strip().splitlines()[-1][:130], eslab))
        if eslab or pack_count("minecraft:oak_slab") <= 0:
            say("A2 FAIL: cannot craft a slab -- stop honestly (the table stays where I put it)")
            return 1
        slab = "minecraft:oak_slab"

    # ---------------- A3: 垫上（并且**独立读**确认 ✓）----------------------
    pt, ep = M.t_place_block(ax, L, az, slab)
    got = r.probe_cell(ax, L, az)
    say("A3 place %s at (%d,%d,%d) -> %s" % (slab, ax, L, az,
                                              (pt or "").strip().splitlines()[-1][:130]))
    say("A3 world read at that cell = %r (want the slab) => %s"
        % (got, str(slab) in str(got)))
    if str(slab) not in str(got):
        say("A3 FAIL: the slab is not really in the world -- reported honestly")
        return 1

    # ---------------- A4: 现在规划必须能到 + 真走上去 -----------------------
    # 半砖加进世界了 ⇒ 地图要重读一次（拿新的一列 ✓）
    r2, m2, _b2 = M._route_map(ax, az, ax + 1, az, sy)      # 复用任务图 ✓ 通常 0 调用 ✓
    ex2 = PP.Planner(m2, level=L, max_up=M.MOD_CLIMB_UP)
    say("A4 after the ramp: exec.ok(target)=%s (want True) | exec.y=%s"
        % (ex2.ok(gx, gz), ex2.y(gx, gz)))
    txt, err = M.t_plan_route(gx, gfeet, gz, "on")
    wps = [(int(a), int(b), int(c)) for a, b, c in
           re.findall(r"^\s*\d+\)\s*\((-?\d+),(-?\d+),(-?\d+)\)", txt, re.M)]
    say("A4 plan: err=%s destination=%s" % (err, wps[-1] if wps else None))
    if err or not wps:
        say("A4 FAIL: still cannot plan to it -- reported honestly")
        for ln in txt.splitlines()[:3]:
            say("   %s" % ln.strip()[:180])
        return 1
    dst = wps[-1]
    wtxt, werr = M.t_walk_route(dst[0], dst[1], dst[2], 60000, 1)
    q = M._pos_now()
    in_cell = bool(q) and (int(math.floor(q[0])) == gx) and (int(math.floor(q[2])) == gz)
    same_lv = bool(q) and abs(int(round(q[1])) - gfeet) <= 0
    say("A4 walk done (err=%s): independent read (%.2f,%.2f,%.2f) => in target cell=%s | "
        "on the target layer=%s" % (werr, q[0], q[1], q[2], in_cell, same_lv))
    for ln in wtxt.splitlines():
        if ("为什么" in ln) or ("到位" in ln) or ("还没到" in ln):
            say("   %s" % ln.strip()[:180])
    a4 = bool(in_cell and same_lv)
    say("A4 => %s" % ("★真的上去了★ ✓" if a4 else "★还是没上去★ ✗（按 A5 如实报 ✓）"))
    say("A5 world state: added %s at (%d,%d,%d)%s -- nothing was dug"
        % (slab, ax, L, az,
           ("; also a crafting table at (%d,%d,%d)" % (table_placed[0], L, table_placed[1]))
           if table_placed else ""))
    say("=> %s" % ("PASS" if a4 else "FAIL"))
    return 0 if a4 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
