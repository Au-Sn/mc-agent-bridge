#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reach_probe.py -- ★可达性探针✗★（★第 1 步：框／读／判／搜✗★ 2026-10-05）

★★契约冻结于 `docs/方案-可达性探针.md` ✗ 本文件**只实现契约**✗★★
  ```python
  reach_probe(start, target, *, timeout_ms, budget, scan_fn=None) -> dict
  { "reachable": "yes"|"no"|"unknown", "layers": int|None,
    "evidence": dict, "why_not": str|None }
  ```
★★★两条硬约束✗★★
  ★① **判的那一步全走 `blockkb`**✗★ —— ★本文件**没有一行新分类**✗★
    （★"★格子能不能走★"由 `blockkb` 回答 ✗ 探针只负责"★从哪来到哪去★"✓★）
  ★② ★**骨架／数据不足时只许 `unknown`**✗★★ —— ★绝不给假 `yes`／`no`✗★ ✓
★世界读取**可注入**（★`scan_fn`✓★）✗★ ⇒ ★判据能**离线**跑假扫描 ✗ 不必碰游戏✗★ ✓
"""
from __future__ import annotations

import pathlib
import time          # ★E2：两条红线要读墙钟（★§79.233✗★）

ROOT = pathlib.Path(__file__).resolve().parent.parent

REACHABLE = ("yes", "no", "unknown")
WHY_NOT = (
    "step_too_high", "wall_too_high", "gap", "sealed",
    "outside_box", "unknown_region", "timeout", "not_implemented",
)
BOX_MAX = (64, 32, 64)

# ★执行者系数（★校准时标的 ✗ 每条**必须**标 theoretical／measured✗★）
EXECUTOR = {
    "step_up":      {"value": 1,    "kind": "measured", "note": "★模组只会上 1 格✗★"},
    "jump":         {"value": 1.25, "kind": "measured", "note": "★校准场✗★"},
    "wall_no_jump": {"value": 1.5,  "kind": "measured", "note": "★不可跳✗★"},
    "down_max":     {"value": 3,    "kind": "measured", "note": "★下落比上爬容易 ✗ 但有上限✗★"},
}


def _out(start, target, why, **ev):
    """★唯一的出口✗★（★保证四键齐 ✗ 且 `why_not` 在闭集里✗★）"""
    assert why is None or why in WHY_NOT, why
    d = {"reachable": "unknown", "layers": None,
         "evidence": {"start": tuple(start), "target": tuple(target)}, "why_not": why}
    d["evidence"].update(ev)
    return d


def box_of(start, target, pad=2):
    """★①框✗★：★`start→target` 的走廊包围盒✗★（★上下多给 pad ✗ 水平按两点✗★）"""
    xs = sorted((int(start[0]), int(target[0])))
    zs = sorted((int(start[2]), int(target[2])))
    ys = sorted((int(start[1]), int(target[1])))
    return (xs[0] - 2, ys[0] - pad - 1, zs[0] - 2,
            xs[1] + 2, ys[1] + pad + 2, zs[1] + 2)


def _default_scan(box, match=None):
    """★(2)读★：盒内 3D 扫描 —— **按种 ＋ 每种逐页**（§79.165）

    ★模组真规则（`DshBridgeMod.java:621`）：/dshscan <from> <to> [match] [max] [page]
      · 分页：pages = max(1, ceil(hits/max)) ｜ from = (pg-1)*max
      · **不带 match 不列格子**（只回汇总 ＋ counts[…]）⇒ 必须**按种**扫
      · counts[…] 最多 COUNT_SHOW=40 个种名，而且**可能被截断**（容忍）
    ★★这一步**没有一行新分类**✗★ —— 它只把"格子上有什么"读回来 ✓
    ★读不到 ⇒ **响亮地说**（不许静默回 0 格，那会变成"读到了空气"）。
    """
    import re
    import mcp_percept as P
    x0, y0, z0, x1, y1, z1 = box
    PAGE = 400          # 每页格数（回执长度与调用数的折中）
    MAXPAGES = 8        # 每种最多翻几页（成本红线）
    MAXSPEC = 24        # 最多扫几种（成本红线）

    def _cmd(m, mx, pg):
        c = "dshscan %d %d %d %d %d %d" % (x0, y0, z0, x1, y1, z1)
        if m:
            c += ' "%s" %d %d' % (m, mx, pg)
        return P._LIVE.dsh(c, 60.0) or ""

    def _cells(txt):
        out = {}
        for x, y, z, sp in re.findall(
                r"(-?\d+),(-?\d+),(-?\d+):([a-z0-9_]+:[a-z0-9_/]+)", txt or ""):
            out[(int(x), int(y), int(z))] = sp
        return out

    def _pages_of(txt):
        mm = re.search(r"page=(\d+)/(\d+)", txt or "")
        return int(mm.group(2)) if mm else 1

    head = _cmd(None, PAGE, 1)              # ★空扫 ⇒ 只要汇总✗★
    if match:
        sp_list = [match]
    else:
        sp_list = []
        mm = re.search(r"counts\[", head)
        tail = (head[mm.end():] if mm else "").split("]")[0]
        for item in tail.split(","):
            item = item.strip()
            if item.count(":") >= 2:
                nm = item.rsplit(":", 1)[0].strip()
                if re.match(r"^[a-z0-9_]+:[a-z0-9_/]+$", nm):
                    sp_list.append(nm)
    if not sp_list:
        return {"ok": False, "cells": {}, "raw": head[:2000],
                "header": (head.splitlines()[0][:300] if head else ""),
                "err": "no_species_from_counts"}

    # 2026-10-05 修（§79.168）：dshscan 只列非空气的格，所以「缺失」＝空气／虚空／没读到
    # 三者之一，分不清。必须把三种 air 也扫，才能把「读到是空气」与「没读到」分开。
    # （这也正是用户方案里那句：三种 air 分开记，cave_air 柱子顺手标下方疑似空腔）
    for _a in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
        if _a not in sp_list:
            sp_list.append(_a)

    cells, scanned = {}, 0
    for sp in sp_list[:MAXSPEC]:
        first = _cmd(sp, PAGE, 1)
        got = _cells(first)
        cells.update(got)
        scanned += 1
        pages = _pages_of(first)
        pg = 1
        while pg < min(pages, MAXPAGES) and got:
            pg += 1
            more = _cmd(sp, PAGE, pg)
            got = _cells(more)
            cells.update(got)
    if not cells:
        return {"ok": False, "cells": {}, "raw": head[:2000],
                "header": (head.splitlines()[0][:300] if head else ""),
                "err": "no_cells_from_scan", "species": len(sp_list)}
    return {"ok": True, "cells": cells, "raw": head[:2000],
            "header": (head.splitlines()[0][:300] if head else ""),
            "cells_n": len(cells), "species": len(sp_list), "species_scanned": scanned}


def _kind(sp):
    """★(3)判★：★一格是"★可站／能穿过／挡人／不知道★"✗★

    ★★2026-10-05（★§79.184✗★）✗★★：★改成**吃类别**✗★ —— ★先问 `passclass.class_of`✗★ ✓
      ★（★Baritone 那条借法的精髓不是 2 bit ✗ 是"★**规划只吃类别**★"✓★）✗★ ✓
    ★★于是"★政策★"只可能通过**已有声明**进来 ✗ **不可能**偷偷改物理✗★★ ✓
    ★★`UNKNOWN` 永不静默当空气✗★★ ✓
    """
    if sp is None:
        return "unknown"
    try:
        import passclass as PC
        cls = PC.class_of(sp)[0]
    except Exception:
        return "unknown"                  # ★类别层读不了 ⇒ `unknown` ✗ 不许猜✗★ ✓
    if cls == "UNKNOWN":
        return "unknown"
    if cls == "AIR":
        return "air"
    if cls == "LIQUID":
        return "pass"                     # ★能穿 ✗ （★岩浆那个已知缺口见 §79.171✓★）
    if cls == "CANOPY":
        return "solid"                    # ★挡人 ✗ 且政策上**不算落脚点**✗★ ✓
    if cls == "DANGER":
        return "solid"                    # ★保守：★不许穿过✗★ ✓
    # ★`SOLID` ⇒ ★能不能站由**政策层**说了算（★树冠已在上面拦掉✓★）✗★
    try:
        import mapread as MR
        return "floor" if MR.is_landing(sp) else "solid"
    except Exception:
        return "unknown"

def _height(sp):
    """★这一格的**碰撞高度**✗★（★找不到就按 0✗★）—— ★同样只问 `blockkb`✗★ ✓"""
    import json
    import kb_export as KX
    exp = json.loads(KX.find_export("").read_text(encoding="utf-8"))
    e = (exp.get("blocks") or {}).get(sp) or {}
    try:
        return float(e.get("max_height") or 0.0)
    except Exception:
        return 0.0


# ##########################################################################
# ★★列顶（★"★真高度★"✗★）✗★ —— ★§79.181 "甲" ✗ 分「空气」与「虚空」✗★
#   ★★为什么需要✗★★：★`dshscan` **只列非空气**✗★ ⇒ ★"★缺失★"＝空气／虚空／没读到✗★
#     ★三者之一 ✗ 分不清✗★ ⇒ ★★探针在真世界里**一步都走不动**✗★★（§79.177 实测）✗★
#   ★口径✗★：★`surface(x,z)` 有值 ✗ 且该格**在列顶之上** ⇒ **空气**（★可走✓★）✗★
#     ★`None`（★空列✗★）⇒ **虚空**（★不可走✓★）✗★
#     ★列顶**以下**的空气（★洞穴✗★）⇒ ★甲**分不出** ✗ 按 `missing` 保守处理✗★ ✓
#   ★★它**不产生**任何"★能不能站★"的新事实✗★★ ✗ 只回答"★这一格是不是空★"✗★ ✓
# ##########################################################################
_COL = {"map": None, "reader": None, "at": 0.0, "err": None}


def _col_top(x, z):
    """★这一列的**最高实心** y ✗ 空列 ⇒ `None`（★虚空✗★）✗★ ✓

    ★★真跑才建图 ✗ 判据走注入✗★ ✓
    """
    import time as _t
    if _COL["map"] is None or (_t.time() - float(_COL["at"] or 0)) > 900.0:
        try:
            import mapread as MR
            r = MR.Reader()
            m = r.get((int(x) - 34, 40, int(z) - 34, int(x) + 34, 100, int(z) + 34),
                      max_age=1800.0)
            _COL.update({"map": m, "reader": r, "at": _t.time(), "err": None})
        except Exception as e:
            _COL.update({"map": None, "at": _t.time(), "err": type(e).__name__})
            return None
    try:
        s = _COL["map"].surface(int(x), int(z))
    except Exception:
        return None
    if not s:
        return None
    try:
        return int(s[0])
    except Exception:
        return None


def _is_air_by_height(p, col_fn=None):
    """★按"★列顶★"判这一格是不是**空气**✗★ ⇒ ★`True`／`False`／`None`（★判不了✗★）✗★ ✓"""
    # ★★2026-10-13（★§79.234 ✗ E2 的作业撞出来的✗★）✗★★：
    #   ★现象✗★：★`_is_air_by_height(T, None)` **一个人吃 17.2 秒**✗★ ⇒
    #     ★而 `reach_probe(scan_fn=注入)` 一共才 17 秒 ⇒ 超时是被**它**踩的✗★ ✓
    #   ★真因✗★：★`col_fn=None` 时它**自己去连活世界**（★`_col_top` ⇒ `mapread.Reader().get(...)`✓★）✗★ ✓
    #   ★★这比慢更糟✗★★：★它意味着**注入式扫描并不纯**✗★ ——
    #     ★判据每次都在**偷偷读世界** ✗ 只是盒内格子齐时看不出来（★`free()` 没走到那条✓★）✗
    #     ★而**目标那一问**（★下面那句✗★）**每次都走** ⇒ ★离线判据其实一直在外连✗★ ✓
    #   ★口径（★§79.171 那条：★"★从哪读这一格★"必须是**给进来的** ✗ 不许猜✓★）✗★：
    #     ★**没给来源 ⇒ `None`（★判不了✗★）**✗★ ✓
    #     ★真跑那一侧**显式**把 `_col_top` 传进来（★见 `reach_probe` 里那句✓★）✗★ ✓
    if col_fn is None:
        return None
    f = col_fn
    top = None
    try:
        top = f(p[0], p[2])
    except Exception:
        return None
    if top is None:
        return False            # ★空列 ⇒ 虚空 ⇒ **不是空气**✗★ ✓
    return p[1] > int(top)      # ★列顶之上 ⇒ 空气✗★ ✓


# ##########################################################################
# ★★移动原语表✗★★（★借鉴① ✗ 2026-10-05✗★）
#   ★每条原语 ＝ 独立小对象 ✗ 自带**前置判定**（★全走 `blockkb` ✗ 没有一行新分类✓★）✗
#   **成本** ✗ **层差** ✗ **证据**✗★ ✓
#   ★★"★没验过的能力不许换覆盖率★"✗★★ ⇒ ★`JUMP_GAP_1` **默认关** ✗
#     因为**我们没测过跳缝**（★走手只上 1 格 ✗ 跳距是"★≥4 格★"那类观测 ✗ 不是校准值✓★）✗★ ✓
# ##########################################################################
PRIMITIVES = [
    {"name": "TRAVERSE", "kind": "traverse", "dz": 0, "layer": 0, "cost": 1.0,
     "measured": True, "enabled": True,
     "note": "★同层平走 ✗ 目标格可站 ＋ 头上有空✗★"},
    {"name": "ASCEND_1", "kind": "ascend", "dz": 1, "layer": +1, "cost": 1.4,
     "measured": True, "enabled": True, "block_max": 1,
     "note": "★上 1 格 ✗ 高差 ≤ **1 格**（★measured：走手实测只会上 1 格✓★）✗★"},
    {"name": "DESCEND_N", "kind": "descend", "dz": -1, "layer": None, "cost": 1.2,
     "measured": True, "enabled": True, "block_max": 3,
     "note": "★下落 ≤ **3** ✗ 落点可站 ＋ 中途无遮挡（★measured✓★）✗★"},
    {"name": "JUMP_GAP_1", "kind": "jump_gap", "dz": 0, "layer": 0, "cost": 2.0,
     "measured": False, "enabled": False, "gap_max": 1,
     "note": "★★**没验过**✗★★ ⇒ **默认关**（★要开先在校准场测 ✓ 2~4 格后议✓★）✗★"},
]


def _search(start, target, cells, want_layers=True, col_fn=None,
            deadline=None, budget=None):
    """★(4)搜★：盒内局部连通搜索 —— **按原语表走**（§79.174）

    ★★三条口径✗★★
      · ★**只有原语的前置成立才许走**✗★ ✗ 没有"★差不多★"的余地✗★ ✓
      · ★`layers` ＝ 原语序列的**层差累计**✗★（★一口气下 3 层 ⇒ +3 ✗ 不是 1✓★）✗★ ✓
      · ★`why_not` ＝ "★哪条原语 ✗ 在哪一格 ✗ 因为什么失败✗★"✗★ ✓
    """
    from collections import deque
    S = (int(start[0]), int(start[1]), int(start[2]))
    T = (int(target[0]), int(target[1]), int(target[2]))

    def kind_at(p):
        v = cells.get(p)
        return "missing" if v is None else _kind(v)

    def free(p):
        # ★★2026-10-05（§79.181 "甲"✗★）✗★★：★"★没读到★"要**再问一次高度图**✗★
        #   ★列顶之上 ⇒ **空气** ✗ 可走✗★ ✓
        #   ★空列 ⇒ **虚空** ✗ 不可走✗★ ✓
        #   ★列顶以下 ⇒ ★甲分不出（★洞穴✗★）⇒ 仍按 `missing` ✗ **保守不可走**✗★ ✓
        k = kind_at(p)
        if k == "missing":
            return _is_air_by_height(p, col_fn) is True
        return k in ("air", "pass")

    def unknown(p):
        return kind_at(p) in ("missing", "unknown")

    def stand(p):
        """★这一格能不能站✗★：★脚下是落脚点（★`mapread.is_landing` ✗ 政策层✓★）✗
        ★本格与头上都空✗★ ✓（★脚下 unknown ⇒ **不算可站** ✗ 不许猜✓★）"""
        below = (p[0], p[1] - 1, p[2])
        k = kind_at(below)
        if k in ("missing", "unknown"):
            return False
        if k != "floor":
            return False
        return free(p) and free((p[0], p[1] + 1, p[2]))

    def pre_traverse(cur, d):
        if not stand(d):
            return False, "dest_not_standable"
        return True, ""

    def pre_ascend(cur, d):
        if d[1] - cur[1] != 1:
            return False, "not_one_up"
        if not stand(d):
            return False, "dest_not_standable"
        # ★★"★净上 2 格★"就在这里被治死✗★★：★只许**上 1 格** ✗
        #   ★想上 2 格 ⇒ 必须有**两次** `ASCEND_1` ✗ 而中间那格**要可站**✗★ ✓
        #   ★没有中间格 ⇒ 判定失败 ⇒ `step_too_high`✗★ ✓
        return True, ""

    def pre_descend(cur, d, k):
        if not (1 <= (cur[1] - d[1]) <= 3):
            return False, "too_far_down"
        if not stand(d):
            return False, "dest_not_standable"
        for yy in range(d[1] + 1, cur[1]):        # ★中途无遮挡✗★
            if not free((d[0], yy, d[2])):
                return False, "blocked_fall"
        return True, ""

    def pre_jump_gap(cur, d, gap):
        if gap != 1:
            return False, "gap_too_wide"
        if not stand(d):
            return False, "dest_not_standable"
        if not free(cur) or not free((cur[0], cur[1] + 1, cur[2])):
            return False, "no_headroom_at_takeoff"
        return True, ""

    seen, q = {S}, deque([S])
    parent, parent_prim = {S: None}, {}
    frontier = []          # ★(原语 ✗ 那一格 ✗ 为什么)✗★
    # ★★2026-10-13（★用户裁决 E2✗★）✗★★：★`timeout_ms`／`budget` **真的**执行✗★ ✓
    #   ★用户原话✗★：★"★实现 `timeout_ms/budget`（★契约闭集里已有 `timeout` ✗
    #     ★删参数＝毁契约 ✗ 安慰剂 API 比没有更坏✓★）★"✗★ ✓
    #   ★口径✗★：★两条红线**都**报 `timeout`✗★（★闭集是冻结的 ✗ 不许加成员✓★）✗
    #     而 `evidence["limit"]` 说清是**哪条**踩的（★`wall_clock`／`budget`✓★）✗★ ✓
    #   ★★超时要**压过任何临时答案**✗★★：★截止之后算出来的 `yes` 是**无效的**✗★ ✓
    _nodes = 0
    while q:
        if deadline is not None and time.monotonic() > deadline:
            return None, None, frontier, ["wall_clock"]      # ★哨兵：None ⇒ 超时✗★
        _nodes += 1
        if budget is not None and _nodes > int(budget):
            return None, None, frontier, ["budget"]
        cur = q.popleft()
        if cur == T or (cur[0] == T[0] and cur[2] == T[2] and abs(cur[1] - T[1]) <= 1):
            layers, node = 0, cur
            seq = []
            while parent.get(node) is not None:
                pr = parent_prim.get(node) or {}
                seq.append(pr.get("name", "?"))
                layers += int(pr.get("layer") or 0)
                node = parent[node]
            return True, layers, frontier, list(reversed(seq))
        for pr in PRIMITIVES:
            if not pr["enabled"]:
                continue
            for dx, dz2 in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                x, z = cur[0] + dx, cur[2] + dz2
                if pr["kind"] == "traverse":
                    cands = [(x, cur[1], z)]
                elif pr["kind"] == "ascend":
                    cands = [(x, cur[1] + 1, z)]
                elif pr["kind"] == "descend":
                    cands = [(x, cur[1] - k, z) for k in range(1, pr["block_max"] + 1)]
                else:   # ★jump_gap ✗ 先只做 1✗★
                    for g in range(1, pr["gap_max"] + 1):
                        cands = [(cur[0] + dx * (g + 1), cur[1], cur[2] + dz2 * (g + 1))]
                for c in cands:
                    if c in seen:
                        continue
                    # ★`DESCEND_N` 的层差是**动态**的（★下 k 格 ⇒ −k✗★）✗★ ⇒
                    #   ★把**实际层差**记进这条边 ✗ 而不是在表里写死✗★ ✓（§79.175）
                    pr_used = pr
                    if pr["kind"] == "descend":
                        pr_used = dict(pr, layer=-(cur[1] - c[1]))
                    if pr["kind"] == "traverse":
                        ok, why = pre_traverse(cur, c)
                    elif pr["kind"] == "ascend":
                        ok, why = pre_ascend(cur, c)
                    elif pr["kind"] == "descend":
                        ok, why = pre_descend(cur, c, pr["block_max"])
                    else:
                        ok, why = pre_jump_gap(cur, c, pr["gap_max"])
                    if not ok:
                        # ★★挡路的**是什么**✗★★（★§79.174 补回：原语化时我把这段丢了✗★）✗★
                        #   ★口径与 §79.160 同：★墙高 ＝ **往上连续挡住了几格**✗★ ✓
                        #   ★（★单格的 `max_height` 只有 1.0 ✗ 整块摞起来的墙看它永远不够✓★）
                        if pr["kind"] == "traverse" and why == "dest_not_standable":
                            _st = 0
                            while _st < 8:
                                _c2 = cells.get((x, cur[1] + _st, z))
                                if _c2 is None or _kind(_c2) in ("air", "pass"):
                                    break
                                _st += 1
                            if _st >= 2:
                                why = "wall_too_high"
                                frontier.append(("STEP_2", c, why))
                                continue
                            if _st == 1:
                                why = "could_climb_one"
                        frontier.append((pr["name"], c, why))
                        continue
                    seen.add(c)
                    parent[c] = cur
                    parent_prim[c] = pr_used
                    q.append(c)
    return False, None, frontier, []


def reach_probe(start, target, *, timeout_ms: int = 8000, budget=None, scan_fn=None,
                col_fn=None) -> dict:
    """★可达性探针✗★（★四步流水线 ✗ 判的那步**全走 `blockkb`**✗★）"""
    try:
        s = tuple(int(v) for v in start)
        t = tuple(int(v) for v in target)
    except Exception:
        return _out((0, 0, 0), (0, 0, 0), "outside_box")
    if len(s) != 3 or len(t) != 3:
        return _out(s, t, "outside_box")

    box = box_of(s, t)                                   # ★①框✗★
    span = (box[3] - box[0] + 1, box[4] - box[1] + 1, box[5] - box[2] + 1)
    if any(span[i] > BOX_MAX[i] for i in range(3)):
        return _out(s, t, "outside_box", box=box, span=span)   # ★成本红线✗★

    # ★E2：两条红线（★墙钟 ✗ 预算✗★）—— ★截止之后算出的答案一律作废✗★ ✓
    # ★§79.234：★`0` ＝ **立刻到期**✗ `None` ＝ **不限**✗★（★原来 `0` 被当成"不限" ✗ 含糊✓★）
    _deadline = (None if timeout_ms is None
                 else time.monotonic() + max(0.0, float(timeout_ms) / 1000.0))

    def _run_search(cells_):
        return _search(s, t, cells_, col_fn=col_fn, deadline=_deadline, budget=budget)

    def _timeout_out(seq_, ev_):
        lim = (seq_ or ["wall_clock"])[-1]
        return {**_out(s, t, "timeout", **ev_, limit=lim, nodes=len(seq_ or [])),
                "reachable": "unknown"}

    if scan_fn is None:
        # ★§79.234：★真跑那一侧**显式**点名"★列顶从哪来★"✗★（★不再靠兜底偷偷连✓★）
        if col_fn is None:
            col_fn = _col_top
        try:
            got = _default_scan(box)                     # ★②读（★真跑才走这条✓★）
        except Exception as e:
            return _out(s, t, "unknown_region", box=box, err=type(e).__name__)
        if not got.get("ok"):
            # ★★失败要**自带对面理由**✗★★（★§79.164：上一版没带 `err` ✗ 我白找一轮✓★）
            return _out(s, t, "unknown_region", box=box, header=got.get("header", ""),
                        err=got.get("err"), species=got.get("species"))
        cells = got.get("cells") or {}
        ev = {"box": box, "header": got.get("header", ""), "cells": len(cells)}
    else:
        # ★★注入的扫描**也要**兜住异常✗★★（★§79.154 的 R6 抓到：读不到 ⇒ **只许**
        #   `unknown`＋`unknown_region` ✗ 不许崩 ✗ 更不许**猜**✗★ ✓）
        try:
            cells = dict(scan_fn(box))
        except Exception as e:
            return _out(s, t, "unknown_region", box=box, scan_fn=getattr(
                scan_fn, "__name__", "injected"), err=type(e).__name__)
        ev = {"box": box, "scan_fn": getattr(scan_fn, "__name__", "injected"),
              "cells": len(cells)}

    # ★★2026-10-05（★§79.181✗★）✗★★：★这条原来**只**看裸 `cells`✗★ ⇒
    #   ★而真世界里**空气不在 `cells` 里**✗★ ⇒ ★目标（★空气✗★）会被判成"★未知★"
    #   ★于是**每一步都到这** ✗ 探针照样不走✗★ ✓
    #   ★⇒ 补上：★目标若**按列顶算是空气** ✗ 也算"★已知★"✗★ ✓
    _t_air = _is_air_by_height(t, col_fn) is True
    if (not _t_air) and (t[0], t[1], t[2]) not in cells and not any(
            (t[0], t[1] + dy, t[2]) in cells for dy in (-1, 0, 1)):
        # ★目标格**读不到** ⇒ 可能是未知区域 ✗ 不许猜✗★
        ev["target_known"] = False
        hit, layers, fr, _seq = _run_search(cells)                      # ★④搜（★原语表✗★）
        if hit is None:
            return _timeout_out(_seq, ev)              # ★超时 ⇒ unknown＋timeout✗★
        if hit:
            return {**_out(s, t, None, **ev), "reachable": "yes", "layers": layers}
        kinds = [k for k, _c, _m in fr]
        why = "unknown_region"
        return {**_out(s, t, why, **ev), "reachable": "unknown"}

    hit, layers, fr, seq = _run_search(cells)                           # ★④搜（★原语表✗★）
    if hit is None:
        return _timeout_out(seq, ev)                   # ★超时 ⇒ unknown＋timeout✗★
    ev["frontier"] = len(fr)
    ev["primitives"] = seq
    ev["why_failed"] = [{"prim": a, "at": b, "why": c} for (a, b, c) in fr[:8]]
    if hit:
        return {"reachable": "yes", "layers": layers,
                "evidence": {"start": s, "target": t, **ev}, "why_not": None}

    # ★没命中 ⇒ 分析 frontier 给 `why_not`✗★（★分类照闭集✗★）
    # ★★`why_not` ＝ "★哪条原语 ✗ 在哪一格 ✗ 因为什么失败✗★"✗★★（★借鉴①✗★）
    _whys = [c for (_a, _b, c) in fr]
    if "wall_too_high" in _whys:
        return {"reachable": "no", "layers": None,
                "evidence": {"start": s, "target": t, **ev}, "why_not": "wall_too_high"}
    if "not_one_up" in _whys or "too_far_down" in _whys:
        why = "step_too_high"
        return {"reachable": "no", "layers": None,
                "evidence": {"start": s, "target": t, **ev}, "why_not": why}
    kinds = [k for k, _c, _m in fr]
    if "wall_too_high" in kinds:
        why = "wall_too_high"
    elif "step_too_high" in kinds:
        why = "step_too_high"
    elif not fr:
        why = "gap" if any(cells.get((t[0], t[1] + dy, t[2])) is None for dy in (-1, 0, 1)) \
            else "sealed"
    else:
        why = "gap"
    return {"reachable": "no", "layers": None,
            "evidence": {"start": s, "target": t, **ev}, "why_not": why}


if __name__ == "__main__":
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    if len(a) >= 6:
        print(json.dumps(reach_probe(tuple(int(x) for x in a[:3]),
                                     tuple(int(x) for x in a[3:6])),
                         ensure_ascii=False, indent=1))
    else:
        print("用法：py tools/reach_probe.py x1 y1 z1 x2 y2 z2")
