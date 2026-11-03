#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bulk_guard.py -- ★批量改方块前的硬守卫✗★

为什么有它（2026-11-01 的一次真实事故 ✗）：
  ★我执行了 `fill 4116 71 2 4127 71 13 minecraft:stone`** ⇒
  ★把 y=71 那一层 12×12 全填成石头 ✗ 其中**正好包含 CC 桥接计算机 (4119,71,10)**✗ ⇒
  ★整套系统当场断线**（★游戏里的计算机没了 ⇒ 网关收不到轮询✗★）✓

所以本模块是**动手前的最后一问**：
    check_box(lo, hi, what)  -> {ok, why, hits}     ★这块区域能不能整体改✗★
    check_cells(cells, what) -> {ok, why, hits}     ★这批格子能不能动✗★

★三条硬规矩（★保守 ✗ 宁可不动✗★）✗★：
  ★① 区域里**任何一格**命中了 `no_dig` 的禁区 ⇒ **拒绝**✗★
  ★② 区域里有**方块实体**（★计算机 ✗ 海龟 ✗ 箱子 ✗ 机器✗★）⇒ **拒绝**（★必须逐格 ✗ 并留痕✗★）✗★
  ★③ **没扫过**的区域 ⇒ **拒绝**（★不许"盲填"✗★）✗★
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


def _no_dig():
    import no_dig as ND
    return ND


def _iter_cells(lo, hi):
    x0, y0, z0 = (int(v) for v in lo)
    x1, y1, z1 = (int(v) for v in hi)
    for x in range(min(x0, x1), max(x0, x1) + 1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for z in range(min(z0, z1), max(z0, z1) + 1):
                yield (x, y, z)


def check_cells(cells, what="bulk", scan=None) -> dict:
    """★一批格子能不能动✗★

    `scan` = {(x,y,z): block_id} 或 None（★None ⇒ 违反规矩③ ⇒ 拒绝✗★）
    """
    ND = _no_dig()
    hits = []
    if scan is None:
        return {"ok": False, "why": "region_not_scanned",
                "message": "★批量操作必须先扫过这块区域（规矩③ ✗ 不许盲填✗★）",
                "hits": []}
    for p in cells:
        ok, zone = ND.allowed(p)
        if not ok:
            hits.append({"pos": list(p), "kind": "no_dig_zone",
                         "zone": (zone or {}).get("name"), "why": "禁区"})
            continue
        b = scan.get(p)
        if b and _has_be_hint(b):
            hits.append({"pos": list(p), "kind": "block_entity",
                         "block": b, "why": "★有方块实体（★计算机/箱子/机器✗★）⇒ 不许批量改"})
    if hits:
        return {"ok": False, "why": "protected_hit", "hits": hits,
                "message": "★区域里有 %d 个不该动的东西 ⇒ 拒绝批量操作✗★" % len(hits)}
    return {"ok": True, "why": None, "hits": [],
            "message": "★%d 格都干净 ⇒ 可以动★" % len(list(cells))}


def check_box(lo, hi, what="bulk", scan=None) -> dict:
    return check_cells(list(_iter_cells(lo, hi)), what=what, scan=scan)


# ★哪些方块"大概率带方块实体"✗★ —— ★只用分类 ✗ 不写死名字表：★
#   ★计算机/海龟/调制解调器/箱子/机器 都认 ✗ 做法：先看 id 里有没有这些"结构性"词 ✗
#   再让 `mapread.machine_family`／`perceive._has_be` 判一次✓
_BE_WORDS = ("computer", "turtle", "modem", "chest", "barrel", "hopper", "furnace",
             "smelter", "machine", "tank", "cable", "pipe", "casing", "crafting",
             "anvil", "sign", "bed")


def _has_be_hint(block_id: str) -> bool:
    low = (block_id or "").lower()
    for w in _BE_WORDS:
        if w in low:
            return True
    try:
        import mapread as MR
        fn = getattr(MR, "has_block_entity", None) or getattr(MR, "_has_be", None)
        return bool(fn(block_id)) if callable(fn) else False
    except Exception:                 # ★不许静默✗★
        return False


def main(argv) -> int:
    if len(argv) >= 6 and argv[0] == "--check":
        lo = tuple(int(v) for v in argv[1:4])
        hi = tuple(int(v) for v in argv[4:7]) if len(argv) >= 7 else lo
        r = check_box(lo, hi)
        print("BULKGUARD ok=%s why=%s %s" % (r["ok"], r["why"], r["message"]))
        for h in r["hits"][:8]:
            print("  ", h)
        return 0 if r["ok"] else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
