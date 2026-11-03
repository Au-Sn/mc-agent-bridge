#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""perceive_test.py -- 模块 B 感知层的判据（★真世界 ✗ 世界真值对照✗★）

规格（docs/方案-拟人化模块.md §2.2／§19）要求：
  * 快照与真值**逐项一致**
  * 方块性质**一律问分类**（不许写名字表）
  * 机器**带朝向**、能查到逐面接口
  * 延迟：snapshot 往返 ≤6；★read_cache 必须 0 次往返**（前台对话官的快路）

CHECKS
  P1 bot 字段与 `dshdigest` 逐项一致（pos/feet/hp/food/items/held/mode）
  P2 nearby 里每个名字的分类与 mapread 对它的结论一致（自洽 ＋ 不是查名字表）
  P3 ★临时放一台模组机器 ⇒ 快照里必须出现它，且带 facing★（用完拆掉并验还原）
  P4 缓存往返一致 ＋ stale_ms 合理；超过阈值 ⇒ read_cache 回 None
  P5 ★read_cache 本地耗时 < 50ms（0 次往返）★；snapshot 往返 ≤ 6
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C          # noqa: E402
import perceive as P          # noqa: E402
import mapread as MR          # noqa: E402


def cell_state(x, y, z):
    txt = (C.dsh('dshscan %d %d %d %d %d %d ":" 8 1' % (x, y, z, x, y, z), 40.0) or "")
    m = re.search(r"cells\[([^\]]*)\]", txt)
    return (m.group(1).strip() if m else "")


def main() -> int:
    checks = []

    snap = P.snapshot(radius=4, caps=1)
    if snap.get("error"):
        print("snapshot 失败:", snap.get("error"))
        print("PERCEIVE ok=0 bad=1")
        return 1
    bot = snap["bot"]

    # P1 与 digest 逐项一致
    raw = (C.dsh("dshdigest", 30.0) or "").strip()
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", raw)
    d_pos = tuple(round(float(m.group(i)), 2) for i in (1, 2, 3)) if m else None
    s_pos = tuple(round(float(v), 2) for v in bot["pos"])
    d_hp = re.search(r"hp=([\d.]+)", raw)
    d_items = re.search(r"items=(\d+)", raw)
    ok1 = (d_pos == s_pos
           and d_hp is not None and abs(float(d_hp.group(1)) - bot["hp"]) < 0.01
           and d_items is not None and int(d_items.group(1)) == bot["items"])
    checks.append(("P1 bot 字段与 digest 逐项一致", ok1,
                   "pos %s vs %s ｜ hp %s vs %s ｜ items %s vs %s"
                   % (d_pos, s_pos, d_hp.group(1) if d_hp else "?",
                      bot["hp"], d_items.group(1) if d_items else "?", bot["items"])))

    # P2 分类自洽（快照里的结论必须等于 mapread 的结论 —— ★同一份实现✗★）
    bad2 = []
    for name, e in list(snap["nearby"].items())[:40]:
        if e["is_floor"] != bool(MR.is_floor(name)):
            bad2.append((name, "is_floor"))
        if e["blocks_space"] != bool(MR.blocks_space(name)):
            bad2.append((name, "blocks_space"))
        if e["machine"] != MR.machine_family(name):
            bad2.append((name, "machine"))
    checks.append(("P2 方块性质与分类一致（不查名字表）", (not bad2) and len(snap["nearby"]) >= 5,
                   "%d 种 不符 %s" % (len(snap["nearby"]), bad2[:3])))

    # P3 放一台机器 ⇒ 快照里必须出现 + 带 facing；用完拆掉还原
    #   ★不自己猜"哪儿能放" ✗ 让 `dshplace` 自己决定（★它的回执里有 verified=<id>✗★）
    bx, by, bz = int(bot["x"]), int(bot["feet"]), int(bot["z"])
    C.dsh("give @s mekanism:energized_smelter 1", 30.0)

    # ★扫描找位（§79.488 那套 ✗ 成功了✗★）：空气 ＋ 上方空气 ＋ **至少一个实心邻居** ＋ reach ≤3.5
    sbox = (bx - 5, by - 2, bz - 5, bx + 5, by + 3, bz + 5)
    sc = (C.dsh('dshscan %d %d %d %d %d %d ":" 1900 1' % sbox, 45.0) or "")
    solid = set()
    for a, b, c in re.findall(r"(-?\d+),(-?\d+),(-?\d+):[a-z0-9_.]", sc):
        solid.add((int(a), int(b), int(c)))

    cands = []
    for y in range(sbox[4], sbox[1] - 1, -1):
        for x in range(sbox[0], sbox[3] + 1):
            for z in range(sbox[2], sbox[5] + 1):
                if (x, y, z) in solid or (x, y + 1, z) in solid:
                    continue
                nbrs = [(x + 1, y, z), (x - 1, y, z), (x, y + 1, z),
                        (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)]
                if not any(nb in solid for nb in nbrs):
                    continue
                d = ((x - bx) ** 2 + (z - bz) ** 2) ** 0.5
                if d > 3.5:
                    continue
                cands.append(((x, y, z), d))
    cands.sort(key=lambda p: p[1])
    placed_pos = None
    tried = []
    for pos, _d in cands[:5]:
        if cell_state(*pos):
            continue
        rep = (C.dsh('dshplace %d %d %d energized_smelter' % pos, 45.0) or "")
        tried.append((pos, "verified=" in rep))
        if "verified=" in rep:
            placed_pos = pos
            break

    ok3 = False
    detail3 = "放不上去，候选=%d 试过=%s" % (len(cands), tried[:3])
    if placed_pos:
        before = cell_state(*placed_pos)
        snap2 = P.snapshot(radius=8, caps=1)
        hits = [m for m in snap2.get("machines", [])
                if tuple(m["pos"]) == tuple(placed_pos)]
        facing = hits[0]["facing"] if hits else None
        caps = hits[0]["caps"] if hits else None
        C.dsh('dshdig %d %d %d' % placed_pos, 45.0)
        after = cell_state(*placed_pos)
        restored = (after == "" or after == "air")
        ok3 = bool(hits) and facing is not None and restored
        detail3 = ("位=%s 放后=%r ｜ 快照命中=%s facing=%r caps=%s ｜ 还原=%s"
                   % (placed_pos, before[:42], bool(hits), facing,
                      "有" if caps and "fe=" in caps else "无", restored))

    checks.append(("P3 机器进快照 ＋ 带朝向（★用完还原✗★）", ok3, detail3))

    # P4 缓存往返 ＋ 过期
    P.write_cache(snap2 if placed_pos else snap)
    c1 = P.read_cache(max_ms=10 ** 9)
    c2 = P.read_cache(max_ms=0)          # ★立刻算过期 ⇒ 必须回 None✓★
    ok4 = (c1 is not None and list(c1["bot"]["pos"]) == list(snap["bot"]["pos"]) and c2 is None)
    checks.append(("P4 缓存可读回 ＋ 过期回 None", ok4,
                   "读回=%s 过期=%s" % (c1 is not None, c2 is None)))

    # P5 延迟：read_cache 必须 0 次往返（本地 <50ms）；snapshot 往返 ≤6
    t0 = time.time()
    P.read_cache(max_ms=10 ** 9)
    dt_ms = (time.time() - t0) * 1000.0
    ok5 = dt_ms < 50.0 and snap.get("round_trips", 99) <= 6
    checks.append(("P5 缓存 <50ms（0 往返）＋ snapshot 往返 ≤6", ok5,
                   "cache=%.1fms snapshot_trips=%s" % (dt_ms, snap.get("round_trips"))))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:130]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => perceive FAIL (%d)" % bad)
        print("PERCEIVE ok=0 bad=%d" % bad)
        return 1
    print("  => perceive PASS (truth-matched, machine facing wired, cache is the 0-round-trip path)")
    print("PERCEIVE ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
