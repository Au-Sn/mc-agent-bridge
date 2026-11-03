#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_geo.py —— ★走路/看图**共用的那一层量测**★（v2.19 拆 god file **第三刀**的一半 ✓）

★为什么它单独成一层✗★（用 `ast` 量的 ✓ 不猜 ✓）：`_verify_band`/`_fill_names`/
`_need_verify`/`_route_map`/`_stand_level`/`_boundary_cells`/`_hull_verify` 这 7 个
**感知组要看图、走路组要规划** ✗ —— 放在任何一边，另一边就得反向 import ⇒ ★循环✗★
⇒ 单独一层 ✓ 两边都往下依赖 ✓（依赖方向：core ⇒ geo ⇒ percept ⇒ walk ⇒ mc_mcp ✓）

★它们是什么✗★：把"图上的高度/名字/边界/站哪一层"从**推测**换成**实测**的那几件 ✓
（`_verify_band` 用 `dshscan ":"` 把地面扫回来就地改正 ✓ `_fill_names` 补"同层不发名字"的洞 ✓
`_stand_level` 用**实测脚高**钉死站哪一层 ✓ —— 都是错题本里换来的 ✓）

★★纪律：一个字都没改✗★★（只搬家 ✓ 见 `tools/mcp_surface.py --diff` 的判据 ✓）
⚠ 这一层**自己不碰 `dsh`** ✗ —— 它只吃传进来的 `reader`/`map` ✓
  （★真正发指令那几个（`_walk_prog`/`_obst_load`）用的是 `mcp_core` 的 `dsh` ✗
    而测试打的是 `mc_mcp.dsh` ✗ ⇒ ★这一族"桩还打得中吗"由
    `tools/cut34_seam_check.py` 单独验✗★ ✓ 见 P156~P158 ✓）
"""

from __future__ import annotations

import json, time

from mcp_core import (
    BLOCKED,
    BLOCKED_LV,
    ROOT,
    _MISSION,
    errlog,
)


WALK_PROG_FILE = ROOT / "logs" / "walk_progress.json"

EDGE_HOP_CHUNK = 4

def _verify_band(r, m, x0, z0, x1, z1, level, max_pages=10,
                 band_lo=6, band_hi=2, force=False):
    """★把这一片的**地面**用 `dshscan` 实地扫回来 ✓ 并就地改正这张图 ✓

    ★为什么层范围是 `level-6 .. level+2`★ ✗（2026-09-28 ✓ 想清楚才敢清 ✗）：
      `absorb_true` 会**先清掉这一段**✗ ⇒ 段选窄了 ⇒ 真值在段外的格会被**清成空的**✗
      ⇒ 图反而更差 ✗（"清掉旧的、又没写回真的"✗）
      而模组自己的地表搜索范围就是 `dy = +2 .. -6` ✓（`mapCmd` 那个循环 ✓）
      ⇒ **按它的范围清** ✓ 才不会凭空制造空洞 ✓
      比 -6 还深的"地板" ⇒ 对走在 `level` 的人等于**不可达** ✓ ⇒ 记成"没地板"✓ 是实话 ✓

    返回 ✓：`{calls, sec, cleared, inserted, cols, no_floor, truncated, box, pages}`
      ＋ `learned` ⇒ **这一趟从模组的碰撞箱里学到的"其实不挡人"的方块** ✓（第 30 轮 ✓ 要报出来 ✓）
      ＋ `skipped=True` ⇒ **这个框已经验过** ✓ 一次调用都没花 ✓（`force=True` 可强制重扫 ✓）
    """
    y_hi = int(level) + int(band_hi)
    y_lo = int(level) - int(band_lo)
    box = (int(x0), y_lo, int(z0), int(x1), y_hi, int(z1))
    # ★已经在同一个框里验过 ⇒ 不必再扫★ ✗（2026-09-29 第 17 轮 ✓ 省通道 ✓）
    #   判据是 `box_verified` 的**包含**判定 ✓（有重叠不算 ✗ 见那里的注释 ✓）
    #   ★第 26 轮补★ ✗：还要看**跨地图**那份账（`mapread.vb_covered` ✓ 带 5 分钟 TTL ✓）——
    #     不然地图一重建（假人一动就重建 ✓）⇒ 验过的框就"忘了"✗ ⇒ 白扫一次 ✓（实测 ✓）
    import mapread as _MRV
    if (not force) and (m.box_verified(*box) or _MRV.vb_covered(box)):
        fresh = "本图" if m.box_verified(*box) else "跨地图（5 分钟内 ✓）"
        return {"calls": 0, "sec": 0.0, "cleared": 0, "inserted": 0,
                "cols": (box[3] - box[0] + 1) * (box[5] - box[2] + 1),
                "no_floor": 0, "truncated": False, "box": box, "pages": 0,
                "learned": [], "skipped": True, "skipped_by": fresh}
    scan = r.scan_truth(box, max_=600, max_pages=int(max_pages))
    info = m.absorb_true(scan, y_lo, y_hi)
    info.update({"calls": scan["calls"], "sec": scan["sec"], "box": scan["box"],
                 "pages": scan["pages"]})
    try:
        r.save(m, 300.0)          # ★回写缓存★ ✓ ⇒ 后面的规划/看图都吃到真值 ✓
    except Exception as e:
        errlog("verify_band save failed", type(e).__name__, str(e))
    return info

def _fill_names(r, m, level, max_pages=2, per_page=600):
    """★把"有地板但**不知道名字**"的那一层**实地扫一次**★ ✗（2026-09-29 第 30 轮 ✓）

    ★为什么要有它★ ✗（实测 ✓）：
      模组的 `/dshmap` 对"**能站的层正好是你自己那一层**"的柱子只印 `@` ✗
      ⇒ **不报那一柱地板是什么方块** ✗ ⇒ 假人一站到**平坦大平台**上 ✓
        图上 **425/458（93%）** 的格子"名字不知道"✓ ⇒ 俯视图只能画 `x` ✗（"看得懂"没了 ✗）
    ★为什么不是让模组改★ ✗：`mapCmd` 那一行改起来只有一句 ✓ **但要重启游戏** ✗
      ⇒ 按老规矩 ✓ **中间层先补上** ✗（与 `scan_truth` 当初补"旧模组没有真高度"是同一招 ✓）
    ★口径★ ✗：
      · 只扫**那一层**（不是整段 ✓）⇒ 面积 = 图面积 ⇒ 一张半径 12 的图 **2 页**（600/页 ✓）
      · 扫回来的就是**世界真值** ✓ ⇒ 名字**照写** ✓（不猜 ✓）
      · 只补名字 ✓ **不动**其它任何结论 ✓（`absorb_true` 按 `y_lo == y_hi == 那一层` 清写 ✓）
    返回 ✓：`{calls, sec, layer, cols, names, truncated}` 或 `None`（没有缺口/读失败 ✓）
    """
    import mapread as _MRF
    miss, per = m.names_missing()
    if not miss:
        return None
    layer = max(per.items(), key=lambda kv: kv[1])[0]        # 缺得最多的那一层 ✓
    x0, _, z0, x1, _, z1 = m.box
    area = (x1 - x0 + 1) * (z1 - z0 + 1)
    if area > per_page * int(max_pages):
        return {"calls": 0, "sec": 0.0, "layer": layer, "cols": area, "names": 0,
                "truncated": True, "why": "图太大（%d 格 > %d 页预算 ✓）⇒ 不扫 ✓"
                % (area, max_pages)}
    scan = r.scan_truth((x0, int(layer), z0, x1, int(layer), z1),
                        max_=int(per_page), max_pages=int(max_pages))
    info = m.absorb_true(scan, int(layer), int(layer))
    try:
        r.save(m, 300.0)
    except Exception as e:
        errlog("fill_names save failed", type(e).__name__, str(e))
    return {"calls": scan["calls"], "sec": scan["sec"], "layer": int(layer),
            "cols": area, "names": int(info.get("inserted") or 0),
            "truncated": bool(scan.get("truncated"))}

def _stand_level(m, x, z, y_hint):
    """★把"走哪一层"钉死★ ✗ —— **用实测脚高的四舍五入**，不是地图猜的那一格 ✗

    演进 ✓（三步都栽过 ✓ 2026-09-23 ✓）：
      ① 每轮重看 `pos.y` ⇒ 70/71 来回跳 ⇒ 图框跟着跳 ⇒ 任务图永不命中 ✗（每段白花 30 秒 ✗）
      ② 改成"用地图像模组那样算站的那一格"✗ ⇒ **又栽** ✓：地图按**方块名**判"能不能踩"✓
         而模组按**碰撞箱**判 ✗ ⇒ 遇到模组装饰方块（`mcwfences:…_wall` ✓）两边差一格 ✗
         ⇒ 目标 y 给成 72 ✓ 而假人站在 71 ✓ ⇒ 走完总差 1.5~1.8 格 ⇒ **两边都判"没到"** ✗
      ③ ★现在（对的口径 ✓）★：`round(脚高)` ✓ ——
         · 站在满方块上 ⇒ 脚高 = Y+1.000 ⇒ round ⇒ Y+1 ✓（正是"站的那一格" ✓）
         · 站在**耕地**上 ⇒ 脚高 = Y+0.9375 ⇒ round ⇒ Y+1 ✓（`int()` 会给 Y ✗ 这正是 P89 那个坑 ✓）
         ★脚高来自 `dshdigest` ⇒ 世界真值 ✓ 比任何按名字的猜测都准 ✓★
      地图只用来算**几何**（地面、连通、内陆 ✓）—— "人在哪一层"以**实测**为准 ✗
    """
    calc = m.stand_cell(int(x), int(z), int(y_hint) + 2)
    actual = int(round(float(y_hint)))
    if calc is not None and abs(calc[1] - actual) > 1:
        # 差得多 ⇒ 不是"差一格"那种小事 ⇒ 说出来 ✗（不然又变成静默的 1 格偏差 ✗）
        return actual
    return actual

def _route_map(sx, sz, gx, gz, sy, margin: int = 8, radius: int = 28):
    """★一趟任务只用一张图（大任务图）★ ✓（"这个框改过五次"的全过程见 docs/地图读取与寻路.md §7 ✓）

    ① 跨度框 ⇒ 对 ✓ 但假人一动框就变 ⇒ 每段重建 40 秒 ✗（三段 413 秒 ✗）
    ② 对齐 8/16 格网格 ⇒ 好一点 ✗ 走十几格又跨格 ⇒ 还是重建 ✗
    ③ 对齐 32 格 ＋ 半径 32 ⇒ 框太大 ⇒ 撞扫描预算 ⇒ **图被截断出空洞** ✗ ⇒ 又"目标不在连通区"✗
    ④ 任务图（起终点 ±12）⇒ 段内复用 ✓ 但**每换一个目标就换框** ✗
       ⇒ 实测 R3 三段 **1 跳**却要 34/38/66 秒 ✓ 时间全花在建图上 ✗
    ⑤ ★现在★：第一次就按**半径 28** 建一大张 ✓ 之后落在这张图里就直接复用 ✓
       ＋ `max_calls` 已抬到 400 ✓（这正是 ③ 失败的原因 ✓ 现在不会截断了 ✓）
       ＋ `sy` 吸到 4 的倍数 ✓（否则 70/71 差一格整张作废 ✗）
    """
    import mapread as MR
    sy = (int(sy) // 4) * 4
    need = (min(int(sx), int(gx)) - margin, max(int(sx), int(gx)) + margin,
            min(int(sz), int(gz)) - margin, max(int(sz), int(gz)) + margin)
    mb, mm = _MISSION.get("box"), _MISSION.get("map")
    fresh = (time.time() - float(_MISSION.get("at") or 0)) < 900.0
    # ★下标必须对上★ ✗（2026-09-23 实测抓到的真 bug ✓）：
    #   `need` 是 **4 元组** (x0,x1,z0,z1) ✓ 而 `box` 是 **6 元组** (x0,y0,z0,x1,y1,z1) ✗
    #   我原来写 `mb[1] >= need[1] and mb[3] >= need[3]` ✗ —— 那是在拿 **y0/y1** 跟 **x1/z1** 比 ✗
    #   ⇒ 复用判据**永远不成立** ⇒ 每一段都重建 ⇒ 实测"8 段 8 次建图 / 每段白花 30 秒"✗
    # ★★2026-10-18（★§79.321 ✗ 缺陷 ① 的嘴✗★）✗★★：★未命中**要说为什么**✗★ ——
    #   ★四个条件逐个判 ✗ 没过的那几条写进 `_MISSION["last_miss"]` ✗ 判定**一个字不改**✗★ ✓
    _why = []
    if not mb:
        _why.append("no_box")
    if mm is None:
        _why.append("no_map")
    if not fresh:
        _why.append("stale(at=%.0f)" % float(_MISSION.get("at") or 0))
    if mb and mm is not None:
        if not (mb[0] <= need[0]):
            _why.append("x0 %s > %s" % (mb[0], need[0]))
        if not (mb[3] >= need[1]):
            _why.append("x1 %s < %s" % (mb[3], need[1]))
        if not (mb[2] <= need[2]):
            _why.append("z0 %s > %s" % (mb[2], need[2]))
        if not (mb[5] >= need[3]):
            _why.append("z1 %s < %s" % (mb[5], need[3]))
    if mb and mm is not None and fresh and mb[0] <= need[0] and mb[3] >= need[1] \
            and mb[2] <= need[2] and mb[5] >= need[3]:
        mm.meta["from_cache"] = "mission"
        _MISSION["last_miss"] = ""
        return MR.Reader(), mm, mb
    _MISSION["last_miss"] = ";".join(_why) + " ｜ box=%s need=%s" % (mb, need)
    r = MR.Reader()
    # ★★先试 v2.15 的 `/dshmap`：一次调用一张图★★ ✓（2026-09-25 ✓ 用户点的"地图完整性"✓）
    #   为什么优先它 ✗：按种类扫描 42 次调用 / 36 秒 ✗ 且**漏掉 top-40 以外的方块**✗；
    #     `/dshmap` 一次调用 ✓ 逐格问服务器 ✓ 稀有方块也在 ✓（模组读**碰撞箱** ✓ 世界真值 ✓）
    #   半径取"这一趟够用"的 ✓（目标是 ≤8 格一跳 ✓ 取 16 够 ✓）；不支持就回落老办法 ✓
    fast = None
    try:
        nrad = int(max(abs(int(sx) - int(gx)), abs(int(sz) - int(gz)))) + 8
        if nrad <= 32:
            fast = r.build_dshmap(radius=nrad, max_age=300.0)
    except Exception as e:
        errlog("build_dshmap failed", type(e).__name__, str(e))
        fast = None
    if fast is not None:
        _MISSION.update({"box": fast.box, "map": fast, "reader": r, "at": time.time(),
                         "builds": int(_MISSION.get("builds") or 0) + 1})
        return r, fast, fast.box
    box = (int(sx) - radius, int(sy) - 8, int(sz) - radius,
           int(sx) + radius, int(sy) + 6, int(sz) + radius)
    r = MR.Reader()
    m = r.get(box, max_age=1800.0)
    _MISSION.update({"box": box, "map": m, "reader": r, "at": time.time(),
                     "builds": int(_MISSION.get("builds") or 0)
                     + (0 if m.meta.get("from_cache") else 1)})
    return r, m, box

def _hull_verify(r, m, sx, sz, gx, gz, level, verify="auto", pad=2, max_pages=8):
    """★规划**之前**先把"你→目标"的外接框实地验一遍★ ✓（2026-09-28 第 17 轮 ✓）

    为什么要有它 ✗：图的高度是推的时（旧模组 ✓）⇒ **规划本身就是在一个错的地面上做的** ✗
      ⇒ 表现就是用户长期抱怨的那两条 ✓：`walk_to` **假 unreachable** ✗ ／
        "走完了还差 1 格 ⇒ 两边都判没到"✗（P89／P101 同族 ✓）
      ⇒ 与其等走完再发现 ✓ 不如**规划前**把这一带的地面问实 ✓

    ⚠ **诚实说清楚** ✗：验的是**外接框**✓ 而**路可能绕到框外**✗
      ⇒ 绕出去的那一段仍是推的 ✗（`route_view` 那种"沿路框"更贴 ✓
        但**规划之前还不知道路在哪** ✗ ⇒ 只能先按外接框来 ✓ 并把这句话说出来 ✓）
    """
    if not _need_verify(m, verify):
        return None
    x0 = min(int(sx), int(gx)) - int(pad)
    x1 = max(int(sx), int(gx)) + int(pad)
    z0 = min(int(sz), int(gz)) - int(pad)
    z1 = max(int(sz), int(gz)) + int(pad)
    return _verify_band(r, m, x0, z0, x1, z1, int(level), max_pages=int(max_pages))

def _vline(vinfo, what="这一带"):
    """把 `_verify_band` 的结果说成一句人话 ✓（扫了就报数字 ✓ 跳过就说为什么 ✓）"""
    if not vinfo:
        return ""
    if vinfo.get("skipped"):
        return ("\n★%s 之前已经**实地验过** ✓ ⇒ 这次没再花调用 ✓（同一个框不重复扫 ✓）"
                % what)
    s = ("\n★%s 的地面**实地验过** ✓（`dshscan \":\"` %d 次调用 %.2f 秒 ✓ "
         "清旧 %d ／ 写真 %d ✓）⇒ 这份规划是按**真高度**做的 ✓"
         % (what, vinfo["calls"], vinfo["sec"], vinfo["cleared"], vinfo["inserted"]))
    if vinfo.get("truncated"):
        s += "（⚠没扫完 ⇒ 没扫到的地方**不算验过** ✗）"
    # ★「学到的假障碍」要**说出来**★ ✗（第 30 轮 ✓）：它改变了「什么算挡路」✓
    #   属于**影响后续每一步**的结论 ⇒ 不许静默 ✓（`learn_shape` 只在**改了结论**时才 True ✓）
    got = [str(x) for x in (vinfo.get("learned") or [])]
    if got:
        s += ("\n★顺手学到一个真值★：%s 这一层**能站**（模组的碰撞箱说的 ✓）"
              "⇒ 从「挡死」改判为**不挡人** ✓（名字猜 vs 碰撞箱 ✓ 以碰撞箱为准 ✓）"
              % "、".join(sorted(set(got))[:4]))
    return s

def _plan_verified(r, m, level, planfn, verify="auto", rounds=3, max_pages=8,
                   pad=1):
    """★规划 → **按"这条路真正经过的框"再验** → 补验 → 重规划（有界 ✓ 有账 ✓）★

    ★为什么必须有它★ ✗（2026-09-28 第 17 轮实测 ✓ 错题本 **P103** ✓）：
      上一步验的是"**你→目标的外接框**"✗ 而 A* 走出来的路会**绕到框外** ✗
      ⇒ 框外那几格**仍是推的**✗ ⇒ 航点 y 错一格 ✗（实测航点复核 **2/3** ✗）
      ⇒ 只验"我以为会走的范围"不够 ✗ 必须验"**它真要走的范围**" ✓

    ★三条纪律★ ✗：
      ① **有界** ✓（`rounds` 轮封顶 ✓ 默认 3 ⇒ 最多补验 **2** 次 ✓）
      ② **有账** ✓（每轮都往 `vlog` 里写"补验了哪一块 ✓ 花了多少次调用 ✓"✗ 不许静默 ✓）
      ③ **最后一轮一定重规划** ✓（补验完不重规划 ⇒ 交出去的还是旧路上的点 ✗）

    参数 ✓：`planfn()` 必须返回 `(pts, why, info)` ✓（谁调谁负责自己的规划器 ✓）
    返回 ✓：`(pts, why, info, vlog)` ✓
    """
    vlog = []
    pts = None
    why = ""
    info = ""
    n = max(1, int(rounds))
    for k in range(n):
        pts, why, info = planfn()
        if not pts:
            if k:
                vlog.append("第 %d 轮：重规划**失败** ✗（%s）⇒ 以这一轮的结论为准 ✓" % (k + 1, why))
            return None, why, info, vlog
        xs = [int(q[0]) for q in pts]
        zs = [int(q[2]) for q in pts]
        x0, x1 = min(xs) - int(pad), max(xs) + int(pad)
        z0, z1 = min(zs) - int(pad), max(zs) + int(pad)
        box = (x0, int(level) - 6, z0, x1, int(level) + 2, z1)
        if not _need_verify(m, verify):
            if k == 0:
                vlog.append("模组自带真高度 ✓ ⇒ 不必补验 ✓")
            break
        if m.box_verified(*box):
            vlog.append("第 %d 轮：路的框 x%d..%d z%d..%d **已经验过** ✓ ⇒ 不用补 ✓"
                        % (k + 1, x0, x1, z0, z1))
            break
        vin = _verify_band(r, m, x0, z0, x1, z1, int(level), max_pages=int(max_pages))
        vlog.append("第 %d 轮：路绕出了上一步验的框 ⇒ **补验** x%d..%d z%d..%d ✓"
                    "（%d 次调用 %.2f 秒 ✓ 清旧 %d ／ 写真 %d ✓）⇒ **按真地面重规划** ✓"
                    % (k + 1, x0, x1, z0, z1, vin["calls"], vin["sec"],
                       vin["cleared"], vin["inserted"]))
        if vin.get("truncated"):
            vlog.append("  ⚠ 这次**没扫完** ✗ ⇒ 这一段仍按「推的」算 ✗（不假装 ✓）")
    else:
        # ★轮数用光了但还想补★ ✗ ⇒ 如实说 ✗ 不许静默收工 ✓
        vlog.append("⚠ 补验轮数已用完（%d 轮 ✓）⇒ 最后这份计划可能仍有没验过的格 ✗" % n)
    return pts, why, info, vlog

def _vlog(vlog):
    """把补验的账说成人话 ✓（空 ⇒ 什么都不说 ✓）"""
    if not vlog:
        return ""
    return "\n★按路求真★：" + "\n   ".join(vlog)

def _need_verify(m, verify="auto"):
    """★要不要"把这条路上的地面**实地**验一遍"★ ✗ —— 口径写死在这里 ✓（好单测 ✓）

    `auto`（默认 ✓）：**只有当图上的高度是"推的"才验** ✓
      · 旧模组（快图没 `y` 行 ⇒ `has_offsets=False` ✓）⇒ 高度是推的 ✗ ⇒ **验** ✓
      · 新模组 v2.16（有真高度 ✓）⇒ 不必再花调用 ✓ ⇒ **不验** ✓（省 ✓）
    这条件的**来源是地图自己** ✓（`meta.has_offsets` ✓）⇒ 无法"事后挪尺子"✗
    """
    v = str(verify if verify is not None else "auto").strip().lower()
    if v in ("off", "no", "false", "0", "none"):
        return False
    if v in ("on", "yes", "true", "1", "force", "always"):
        return True
    return not bool(m.meta.get("has_offsets"))

def _why_map():
    """★"为什么挡"那张表**归上层**（`mc_mcp`）✗ ★ ----

    ★★2026-10-03 修的真 bug✗★★：
      · `mcp_geo` 里有 `BLOCKED`／`BLOCKED_LV` ✗ **唯独没有 `BLOCKED_WHY`**✗★
      · 于是 `_obst_add` 一调用就 `NameError`（★"记一条障碍"这条 API **根本不能用**✓★）
      · 而 `_obst_save` 也被同一个名字绊倒 ✗ ✗ 可它**外面裹着 `except … errlog`**✗
        ⇒ ★**静默失败**：文件里那 19 条是**旧的** ✗ 新障碍一条也写不进去✗★ ✓
      · ⇒ ★又一个"**静默失效的闸门**"✗（★P179 同族：★坏得没声的闸比没有闸更坏✓★）★
    ★修法✗★：★**懒取**上层的同一张表✗（★模块内直接 import 会成环 ✗
      而调用时上层早已加载完 ✓ 这正是本仓库别处用的写法✓★）
    """
    try:
        import mc_mcp as _M
        return _M.BLOCKED_WHY
    except Exception:
        # ★拿不到就**自己手里那张**（★宁可记不全 ✗ 也不许抛 ✗ 更不许**静默**✓★）
        g = globals().setdefault("_FALLBACK_WHY", {})
        return g


def _obst_add(x, z, why, level=None) -> None:
    """★记一条障碍（带上"在哪一层探到的"）★ ✗（第 31 轮 ✓ 一处入口 ✓）"""
    BLOCKED.add((int(x), int(z)))
    _why_map()[(int(x), int(z))] = str(why or "?")
    if level is not None:
        BLOCKED_LV[(int(x), int(z))] = int(level)

def _obst_load() -> None:
    """★把障碍记忆读回来★ ✓（跨进程/跨重启 ✓ —— 不然只是本会话的变量 ✗ 不叫记忆 ✓）"""
    try:
        if not OBST_FILE.is_file():
            return
        d = json.loads(OBST_FILE.read_text(encoding="utf-8"))
        now = time.time()
        for k, v in (d.get("cells") or {}).items():
            if now - float(v.get("at") or 0) > OBST_TTL:
                continue
            x, z = (int(t) for t in str(k).split(","))
            _obst_add(x, z, v.get("block") or "?", v.get("level"))
    except Exception as e:
        errlog("obst_load failed", type(e).__name__, str(e))

def _obst_save() -> None:
    """★把障碍记忆写回去★ ✓（哪一格、什么方块、什么时候记的 ✓ 全留档 ✓）"""
    try:
        now = time.time()
        old = {}
        try:
            if OBST_FILE.is_file():
                old = json.loads(OBST_FILE.read_text(encoding="utf-8")).get("cells") or {}
        except Exception:
            old = {}
        cells = {}
        for (x, z) in BLOCKED:
            k = "%d,%d" % (x, z)
            cells[k] = {"block": _why_map().get((x, z), "?"),
                        "level": BLOCKED_LV.get((x, z)),
                        "at": float((old.get(k) or {}).get("at") or now)}
        OBST_FILE.parent.mkdir(parents=True, exist_ok=True)
        OBST_FILE.write_text(json.dumps(
            {"note": "实地探到的挡路格（超过 24 小时自动作废 ✓）", "cells": cells},
            ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    except Exception as e:
        errlog("obst_save failed", type(e).__name__, str(e))

def _bearing(dx: int, dz: int) -> str:
    """★方位词★ ✓（北 = -Z ✓ 与本项目所有地图一致 ✓）；纯函数 ✓ 好离线单测 ✗"""
    ns = "北" if dz < 0 else ("南" if dz > 0 else "")
    ew = "西" if dx < 0 else ("东" if dx > 0 else "")
    return (ns + ew) or "（原地）"

def _boundary_cells(pl, reg) -> list:
    """★「边」= 连通区里**四邻有站不住**的那些格★ ✓（纯函数 ✓ 好离线单测 ✗）

    ⚠ 为什么"边"要按**四邻**判 ✗（2026-09-23 那次事故 ✓）：
      空岛上"能站"**不等于**"安全" ✗ —— 平台的**边上一格**正是"能站但一步踩空"✗
      ⇒ 所以"边"的定义必须是"**我有一个邻居走不过去**"✓ 而不是"我自己能不能站" ✗
    """
    out = []
    for (x, z) in reg:
        for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + dx, z + dz) not in reg:
                out.append((x, z))
                break
    return out

def _hop_policy(pl, pts, chunk, sweep):
    """★这一跳要不要"**走小心点**"★ ✓（纯函数 ✓ 好离线单测 ✗）（2026-09-29 第 26 轮 ✓）

    返回 `(chunk2, sweep2, why)` ✓
    判据 ✓：`pts` 里有任何一格**不是内陆格**（四邻有站不住的 ✓）⇒ 这一跳**贴着边** ✗

    ★为什么是"照走"✗ 而**不是**"改道"✗★：
      规划器**已经**带避边了（`avoid_edge` ✓ 上一轮 ✓）⇒ 这条路是它认为最安全的 ✓
      而"**只有边路可走**"时**根本没得选** ✗（这正是上一轮 Q2 那条 ✓）
      ⇒ 能做的只有"**走慢点、看仔细点**" ✓：跳距压到 ≤4 格 ✓（模组少一点冲刺余地 ✓）
        ＋ 探路多探一格 ✓（多一次独立读 ✓）
    """
    if not pts or len(pts) < 2:
        return chunk, sweep, ""
    rim = [(int(c[0]), int(c[2])) for c in pts[1:]
           if not pl.interior(int(c[0]), int(c[2]))]
    if not rim:
        return chunk, sweep, ""
    # ★★贴着边 ⇒ **不许再上下台阶**★★ ✗（第 31 轮 ✓ 用一次真事故换来的 ✓）
    #   事故 ✓：2026-09-29 18:56:26 游戏日志写着 `Bot 掉出了这个世界` ✗
    #     —— 当时正在跑**故意沿边走**的那个验收（`edge_hop_test` ✓）✓
    #   真因 ✓：这一轮我把 `ok()` 修成"允许抬一级/降三级"✓（**平地规划**上是对的 ✓）
    #     ⇒ 可在**边上一格**上，"抬一级"意味着**踩到墙头/台阶**上 ✓
    #       而那一格的外侧**就是虚空** ✗ ⇒ 一次跳空 = 掉下去 ✗
    #     ★本项目第一条血的教训就是"能站 ≠ 安全"★ ✗（R2 那次丢掉一整包东西 ✓）
    #   ⇒ 口径 ✓：**贴边的那一跳只走同层** ✗（`same_level_only` ✓ 宁可靠不过去也别掉下去 ✓）
    #     —— 内侧的路该抬还是抬 ✓（这只在"这一跳有非内陆格"时才收紧 ✓）
    return min(int(chunk), EDGE_HOP_CHUNK), int(sweep) + 1, (
        "★这一跳**贴着边** ✗（%d 格不是内陆 ✓ 例如 (%d,%d) ✓）⇒ "
        "跳距压到 ≤%d 格 ✓ 探路多探一格 ✓ ★照走 ✓（**只走同层** ✓ "
        "边上一格踩空就是虚空 ✗ —— 同层真没路才不走 ✓）★"
        % (len(rim), rim[0][0], rim[0][1], min(int(chunk), EDGE_HOP_CHUNK)))

def _planner_for_hop(pl, rim_hop: bool):
    """★贴边那一跳要一个"只走同层"的规划器★ ✗（第 31 轮 ✓ 见 `_hop_policy` 的事故注释 ✓）"""
    import pathplan as PP
    if not rim_hop:
        return pl
    return PP.Planner(pl.m, level=pl.level, blocked=pl.blocked_lv or pl.blocked,
                      avoid_edge=True, same_level_only=True)

def _walk_prog(phase, step, pos, target, note=""):
    """★写一次"走到哪了"的心跳★ ✓（2026-09-29 第 27 轮 ✓ 治"超时后一片空白"✗）

    ★为什么要它★ ✗：`walk_route` 是**阻塞**调用 ✓ 长走要几分钟 ✓
      调用方（大脑／MCP）一旦**超时** ✗ ⇒ 它**完全不知道人走到哪了** ✗ ⇒ 只能瞎猜或整段重来 ✗
    ★口径★ ✗：`pos` 一律是**独立读到的实测位置** ✓（不是我推测的 ✗）＋ 带 `at` 时间戳 ✓
      （供"新鲜度"判定 ✓ —— 陈旧的心跳**不许**被当成"正在走" ✗）
    """
    try:
        rec = {"at": time.time(), "when": time.strftime("%Y-%m-%d %H:%M:%S"),
               "phase": str(phase), "step": int(step or 0),
               "pos": [float(v) for v in pos] if pos else None,
               "target": [float(v) for v in target] if target else None,
               "note": str(note or "")}
        WALK_PROG_FILE.parent.mkdir(parents=True, exist_ok=True)
        WALK_PROG_FILE.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        errlog("walk_prog write failed", type(e).__name__, str(e))


# ── ★★v2.19 第三/四刀：跟着搬过来的常量★★ ✗（★同一个对象只有一份✗★）
OBST_FILE = ROOT / "logs" / "obstacles.json"
OBST_TTL = 24 * 3600.0     # ★障碍记忆有效期 24 小时★ ✗（2026-09-28 ✓）
#   为什么必须有过期 ✗：障碍**会消失**（玩家把它挖了/炸了 ✓）⇒ 永久记住 ⇒ 那块地**以后再也不敢走** ✗
#     （比不认识更糟 ✗）⇒ 过期就当没记过 ✓ 重新探一次 ✓ 宁可多探 ✓ 不留永久错误的封锁 ✓
