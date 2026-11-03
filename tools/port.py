#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""port.py -- 模块 K 第 2 级：★把蓝图移植到现场✗★

规格（§10.2 / §13.1）：
  「产线蓝图**应该是可以搜索的**」⇒ 第 1 级检索已完成（`structures.py` ✓）
  本模块是**第 2 级**：★拿一张图 ✗ 对着现场算账 ✗ 按支撑顺序逐格放 ✗ 放完重算应为 0✗★

接口：
  plan(cells, origin, live)   -> {ok, need, missing, floating}   ★算账✗★
  order(cells, live)          -> [cell,...]  ★**自下而上** ＋ 优先有支撑的✗★
  execute(plan, prims)        -> {placed, failed, skipped}       ★逐格放 ✗ 不碰已对的格✗★

★三条纪律✗★：
  ★① **幂等**：已经对的格子**不放**（★省料 ✗ 也不产生多余动作✗★）✗★
  ★② **支撑优先**：悬空格**不硬放** ⇒ 标 `floating` 报出来✗★
  ★③ **只信真值**：每放一格由 `primitives.place` 走 L4 校验✗★
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

SOLID_HINT = ("stone", "dirt", "planks", "cobble", "glass", "brick", "concrete",
              "casing", "frame", "block", "ore", "log", "wood", "slab", "stairs")


def _is_solid(block_id: str) -> bool:
    """★粗判"能不能承重"✗★（★空气／水／火不算 ✗ 其余算✗★）"""
    if not block_id:
        return False
    low = block_id.lower()
    for a in ("air", "water", "lava", "fire", "torch", "flower", "grass", "vine",
              "carpet", "button", "lever", "sign", "banner"):
        if low.endswith(":" + a) or ("/" + a) in low:
            return False
    return True


def _placeable(cell) -> bool:
    """★这一格到底要不要放✗★（★空气／流体不是放✗★）"""
    b = (cell.get("block") or "").lower()
    if b.endswith(":air") or b.endswith(":cave_air") or b.endswith(":void_air"):
        return False
    if b.endswith(":water") or b.endswith(":lava"):
        return False
    return True


def _abs(cell, origin):
    ox, oy, oz = (int(v) for v in origin)
    return (ox + int(cell["dx"]), oy + int(cell["dy"]), oz + int(cell["dz"]))


def plan(cells, origin, live: dict) -> dict:
    """★对着现场算账✗★：`live` = {(x,y,z): block_id}"""
    # ★实测踩出来的两点✗★：
    #   ★① 蓝图里**大量空气格**（★结构文件是全尺寸包围盒✗★）⇒ 必须滤掉
    #   ★② 支撑不能只看现场 ✗ **蓝图自己将要放的格子**也算支撑（★否则全标悬空✗★）
    cells = [c for c in cells if _placeable(c)]
    future = {_abs(c, origin) for c in cells}
    ok, need, missing, floating = [], [], {}, []
    for c in cells:
        k = _abs(c, origin)
        want = c["block"]
        if live.get(k) == want:
            ok.append(c)
            continue
        need.append(c)
        missing[want] = missing.get(want, 0) + 1
        # ★支撑检查✗★：下／四侧任一为实体 ⇒ 站得住
        nb = [(k[0], k[1] - 1, k[2]), (k[0] + 1, k[1], k[2]), (k[0] - 1, k[1], k[2]),
              (k[0], k[1], k[2] + 1), (k[0], k[1], k[2] - 1)]
        supported = any(_is_solid(live.get(p) or "") for p in nb)
        if not supported:
            # ★现场没有 ✗ 但**蓝图自己**在那格里要放实体块 ⇒ 也算有支撑✗★
            supported = any(p in future for p in nb)
        if not supported:
            floating.append(c)
    return {"ok": ok, "need": need,
            "missing": dict(sorted(missing.items(), key=lambda kv: (-kv[1], kv[0]))),
            "floating": floating,
            "ok_n": len(ok), "need_n": len(need)}


def order(cells, live: dict, origin=(0, 0, 0)) -> list:
    """★自下而上 ✗ 有支撑的优先 ✗ 同层按到锚点距离✗★"""
    def key(c):
        k = _abs(c, origin)
        sup = 0 if _is_solid(live.get((k[0], k[1] - 1, k[2])) or "") else 1
        return (int(c["dy"]), sup, abs(c["dx"]) + abs(c["dz"]))
    return sorted(cells, key=key)


def execute(pl, prims, origin=(0, 0, 0), live=None, maxn: int = 500) -> dict:
    """★逐格放✗★（★已对的不放 ✗ 悬空的不放✗★）"""
    live = dict(live or {})
    floating = {_abs(c, origin) for c in (pl.get("floating") or [])}
    placed, failed, skipped = [], [], []
    todo = order(pl.get("need") or [], live, origin)
    for c in todo[:maxn]:
        k = _abs(c, origin)
        if k in floating:
            skipped.append({"pos": list(k), "why": "floating"})
            continue
        if live.get(k) == c["block"]:
            skipped.append({"pos": list(k), "why": "already_ok"})
            continue
        r = prims.place(k, c["block"], mission="port")
        if r.get("ok"):
            placed.append({"pos": list(k), "block": c["block"]})
            live[k] = c["block"]
        else:
            failed.append({"pos": list(k), "block": c["block"], "why": r.get("why")})
    return {"placed": placed, "failed": failed, "skipped": skipped,
            "placed_n": len(placed), "failed_n": len(failed), "skipped_n": len(skipped)}


def main(argv) -> int:
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
