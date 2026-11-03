#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_walk.py —— ★走：规划 ＋ 分跳 ＋ 每跳验真值 ＋ 偏了重规划★（v2.19 **第四刀** ✓）

搬过来的（逐字 ✓）：`_walk` / `t_walk_to` / `t_come_to` / 上下台阶 / `_make_plan` /
`_plan_verified` / `_route_map` 的调用方 / `t_plan_route` / `t_route_view` / `t_walk_route` /
`t_check_path`-的规划半边 / `t_platform` / `t_safe_spots`-的落脚半边 / 冻结与溜达 /
障碍记忆（`BLOCKED*`/`OBST_*` ✓）/ 长走心跳（`_walk_prog` ✓）…

★为什么这层能单独成一块✗★：它要的量测全在 `mcp_geo` ✓ 要看的事件流在 `mcp_percept` ✓
  两个方向都是**单向**（`mc_mcp` ⇒ `mcp_walk` ⇒ `mcp_percept` ⇒ `mcp_geo` ⇒ `mcp_core` ✓）

★走路的判据（这一层最贵的几条 ✓ 都在代码里 ✗ 一条都不许松 ✗）★
  · 单发长走上限 `SAFE_WALK`（实测定的 ✓ 见 `w1_gate_test` ✓）
  · 一跳 ≤ 8 格（`walk_route` 的 `chunk` ✓ 掉过两次虚空的教训 ✓）
  · 到没到按**格按层**判 ✗（不是看距离 ✗ P32/P104 ✓）
  · 没到必须说**为什么**（`why=` ＋ 怎么绕 ✓ P116 ✓）
  · ★动世界之前先 `freeze`✗★（`t_freeze` ✓ 幂等 ✓ 解冻**原样还原** ✓）

⚠ `_LIVE.<名>`：让打进 `mc_mcp` 的桩打得中（`dsh`/`_walk`/`_pos_now`/`_near` ✓
  见 `mcp_core._LIVE` ✓ —— `mc_mcp_smoke.py` 与 `chest_many_test.py` 就靠这个 ✓）
"""

from __future__ import annotations

import sys

# ★★2026-10-18（★§79.321✗★）✗★★：★这个模块现在会 `print`（「建了几张图 ＋ 为什么」✗★）✗★
#   ★⇒ 按项目规矩必须**pin 住 stdout**（★`stdio_guard_test` 的 S3 ✗ 我把它弄红过一次✗★）✗★ ✓
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import json, re, time

from mcp_core import (
    BLOCKED,
    BLOCKED_LV,
    MOD_CLIMB_UP,
    PLAYER,
    _LIVE,
    _MISSION,
    _inv_items,
    arrive_flags,
    arrived_at,
    cut,
    errlog,
    kv,
    ok_of,
)
from mcp_geo import (
    WALK_PROG_FILE,
    _bearing,
    _boundary_cells,
    _hop_policy,
    _hull_verify,
    _need_verify,
    _obst_add,
    _obst_save,
    _plan_verified,
    _route_map,
    _stand_level,
    _verify_band,
    _vline,
    _vlog,
    _walk_prog,
)


def _walk(x, y, z, timeout_ms=20000, exact=False, dist_hint=None) -> tuple:
    """走一条腿 ✓ 并**等到真的停** ✗ —— "发了指令"和"走到了"是两件事 ✗（本项目最贵的教训 ✓）

    ★2026-09-23 提速（实测 ✓）：原来每 **0.4 秒**轮询一次 ✓ 而一次桥往返 ≈ 0.6 秒 ✗
      ⇒ 走 5 秒的一条腿要读十几次状态 ⇒ 一条腿实际 7~10 秒 ✗
      ⇒ 改成：**先按距离估时睡一下，再看一次** ✓ 近腿一条腿只需 2 次往返 ✓
    """
    import math as _m
    cmd = "dshwalk %d %d %d %d%s" % (int(x), int(y), int(z), int(timeout_ms),
                                     " exact" if exact else "")
    t0 = _LIVE.dsh(cmd, 60.0)
    if not ok_of(t0, "dshwalk"):
        return ("开走失败 ✗：%s" % (t0[:200] or "（没有回执 ✗ 模组版本低于 v2.6？）")), True
    dist = float(dist_hint) if dist_hint is not None else 8.0
    if dist_hint is None:
        cur = _LIVE._pos_now()
        dist = _m.dist(cur, (x, y, z)) if cur else 8.0
    # ★估时按**实测速度**来★ ✗（`hop_cost.py` 量的：8 格 2.7~6.6 秒 ⇒ 约 **1.2~3 格/秒** ✓）
    #   0.18/格 ⇒ 太乐观 ⇒ 睡醒还没走完 ⇒ 多poll 一次（≈1.2 秒 ✗）
    #   0.45/格 ⇒ 近了 ✓ 但 5 格的短跳仍常差一点点 ⇒ 再加一点 ✓
    #   ⇒ 0.60/格 ＋ 0.8 ✓：5 格估 3.8 秒 ✓ 第一次看基本就 done ✓（宁可多等 0.3 秒 ✗ 也别多一次往返 ✓）
    est = min(max(0.8, dist * 0.60 + 0.8), max(0.8, float(timeout_ms) / 1000.0))
    deadline = time.time() + max(4.0, float(timeout_ms) / 1000.0 + 3.0)
    last = ""
    sleep_s = est if dist <= 5 else min(est, 2.0)
    while True:
        time.sleep(sleep_s)
        st = _LIVE.dsh("dshwalk", 30.0)
        if st:
            last = st
        d = kv(st)
        if d.get("status") == "done":
            res = d.get("result", "?")
            good = (res == "reached")
            # ★★模组说"到了" ⇒ **我也要自己复核一遍**★★ ✗（第 32 轮 ✓ 实测抓到假"到了" ✓）
            #   现场 ✗：目标 `(4121,72,5)`（**抬一级**的格子 ✓）⇒ 模组回 `到达 ✓ 偏差 0.82 格` ✗
            #     而独立读是 `(4121.70, **71.00**, 4.70)` ✗ ——
            #     ★人在**旁边那一格**、而且**低一层**★ ✗（差 0.82 格 ⇒ 它的判据过了 ✗）
            #   为什么危险 ✗：大脑拿到"到了"就会**接着动手**（开箱子/挖/放 ✓）⇒ 那一下必然落空 ✗
            #     —— ★"假到"比"假没到"更贵★ ✗（假没到只是再走一次 ✓）
            #   ⇒ 口径 ✓（与 `walk_route` **同一套** ✓ P106 ✓）：**格子对 ＋ 层对**才算到 ✓
            false_arrive = None
            if good:
                q = _LIVE._pos_now()
                if q:
                    in_cell = (int(_m.floor(float(q[0]))) == int(x)) \
                        and (int(_m.floor(float(q[2]))) == int(z))
                    same_lv = abs(int(round(float(q[1]))) - int(y)) <= 0
                    if not (in_cell and same_lv):
                        false_arrive = (q, in_cell, same_lv)
                        good = False
            txt = ("走到 (%d,%d,%d)：%s ｜ 停在 %s 偏差 %s 格 ｜ 驱动=%s ｜ 绕障=%s ｜ 下台阶=%s ｜ 原因=%s ｜ tick=%s"
                   % (x, y, z, "到达 ✓" if good else "**没到** ✗（%s）" % res,
                      d.get("at"), d.get("dist"), d.get("mode"),
                      d.get("detours", "0"), d.get("step_downs", "0"),
                      d.get("why", "none"), d.get("ticks", "?")))
            if false_arrive:
                q, in_cell, same_lv = false_arrive
                txt += ("\n★★模组说「到了」、实测**不算到**★★ ✗：它停在 `(%.2f,%.2f,%.2f)` ✓ "
                        "在目标那一格里 = %s ✗ ｜ 层对得上 = %s ✗ ⇒ "
                        "★它按「离目标点 ≤1 格」算到 ✗ 而站到**旁边那一格／低一层**也算进去了 ✗★ ⇒ "
                        "要动手就再走一次（拆小的 `walk_route` ✓）或挪到目标旁边 ✓"
                        % (q[0], q[1], q[2], in_cell, same_lv))
            if not good:
                txt += {"edge": " ｜ 说明：前面**没有落脚点** ⇒ 再走就掉虚空 ✗",
                        "blocked": " ｜ 说明：被挡住了 ✗ 换个方向或先清障 ✓",
                        "timeout": " ｜ 说明：时间用完 ✗ 目标可能太远 ✓"}.get(res, "")
            return txt, (not good)
        if time.time() > deadline:
            break
        sleep_s = 1.2
    _LIVE.dsh("dshwalk stop", 30.0)
    return ("走去 (%d,%d,%d) **超时** ✗（已发 stop ✓）最后状态：%s" % (x, y, z, last[:200])), True

def _planner_exec(m, level, **kw):
    """★"**要真去走**"的那条路用的规划器★ ✗（第 33 轮 ✓ 一处入口 ✓ 不许到处写 `max_up` ✗）"""
    import pathplan as PP
    return PP.Planner(m, level=level, max_up=MOD_CLIMB_UP, **kw)

def _return_ok(m, level, fx, fz, tx, tz, feet_t, feet_s):
    """★下得去、上得来吗★ ✗（第 33 轮 ✓ 零调用 ✓ 本地算 ✓）

    为什么要它 ✗：`MAX_DOWN=3` 允许往下走三层 ✓ —— 可**模组爬不上去**✗
      ⇒ 走进一个"只有下坡、没有坡道回来"的坑 ⇒ ★**出不来**★ ✗
        （与"掉虚空"同一族 ✓ 都是"去了就回不来"✗ —— 只是这个更隐蔽 ✓）
    口径 ✓：**用执行者的能力**算回程（`max_up=MOD_CLIMB_UP` ✓ 起点 = 目标的脚层 ✓）
    返回 ✓：`True` 回得来 ✓／`False` 回不来 ✗
    """
    import pathplan as PP
    try:
        back = PP.Planner(m, level=int(feet_t), max_up=MOD_CLIMB_UP, avoid_edge=True)
        pts, _why = back.plan(int(tx), int(tz), int(fx), int(fz))
        return bool(pts)
    except Exception as e:                     # ★★§79.402✗★ 算不出要**留痕** ✗ 不静默✗★
        errlog("mcp_walk._climb_can 算不出：%r" % (e,))
        return None          # 算不出来 ⇒ 不假装知道 ✓（★但已经留痕✓★）

def _climb_diagnosis(m, level, tx, tz):
    """★"规划不通"到底是**哪一种**不通★ ✗（第 33 轮 ✓ 零调用 ✓ 本地算 ✓）

    为什么要有它 ✗：`plan_route` 被拒之后，大脑只看到"不通"两个字 ✗ ⇒
      分不清"**隔着虚空**"（真去不了 ✗）和"**要抬一级，而模组爬不上去**"（垫一格就行 ✓）✗
      ——★这两件事的下一步完全不同★ ✗（P116 那条 ✓）
    口径 ✓：**几何说得通（`max_up=1` ✓）而执行者说不行（`max_up=0` ✓）** ⇒ 就是"要爬"✓
    返回 ✓：一句话（不是这种情况 ⇒ 空串 ✓）
    """
    import pathplan as PP
    try:
        geo = PP.Planner(m, level=int(level), max_up=1)
        can = PP.Planner(m, level=int(level), max_up=MOD_CLIMB_UP)
        if not (geo.ok(tx, tz) and not can.ok(tx, tz)):
            return ""
        fy = geo.y(tx, tz)
        blk = (m.cols.get((int(tx), int(tz))) or {}).get(int(fy)) if fy is not None else None
        return ("\n★★不通的原因查到了：**要抬一级**★★ ✗ —— 那一格几何上站得住"
                "（脚层 %s ✓ 地板 `%s` ✓）✗ 可上去要**抬一级** ✗ ⇒ ★模组爬不上去★"
                "（实测停在 0.8~1.7 格外 ✗）\n"
                "  ⇒ 怎么办 ✓：① 在旁边**垫一格半砖**（0.5 格是**自动上**的 ✓ 不用跳 ✓）"
                "② 把那一格**挖掉**（变同层 ✓）③ 换一个**同层**的目标 ✓ ④ 等模组 v2.17 ✓"
                % ((int(fy) + 1) if fy is not None else "?", blk or "?"))
    except Exception:
        return ""

def _descent_guard(m, level, sx, sz, dst):
    """★这一步会不会把我送到"回不来"的地方★ ✗（第 33 轮 ✓ 一处口径 ✓ 可离线单测 ✓）

    判据 ✓：目的地的**脚层**比我现在**低** ⇒ 问回程（`_return_ok` ✓ 按执行者的能力算 ✓）
      · 回得来 ⇒ `(True, "")` ✓ 照走 ✓
      · **回不来** ⇒ `(False, 原因)` ✗ ★不去★ ✗
      · 同层/更高 ⇒ 不关它的事 ✓（"抬一级"那条由 `max_up` 管 ✓）
    返回 ✓：`(ok, why)` ✓
    """
    try:
        dfeet = int(dst[1])
    except Exception:
        return True, ""
    if dfeet >= int(level):
        return True, ""
    back = _return_ok(m, level, sx, sz, int(dst[0]), int(dst[2]), dfeet, int(level))
    if back is False:
        return False, (
            "★这一步**不去** ✗（第 33 轮 ✓）：目的地是**低 %d 层**（脚层 %d ✓ 我在 %d ✓）"
            "★而回来的路要**抬 %d 级**★ ✗ —— 模组**爬不上去**（实测停在 0.8~1.7 格外 ✗）"
            "⇒ ★去了就出不来★ ✗\n"
            "  怎么办 ✓：① 先在那底下**垫一格半砖**做坡道 ✓ ② 换一个**同层**的目标 ✓ "
            "③ 等模组 v2.17 会跳一级 ✓"
            % (int(level) - dfeet, dfeet, int(level), dfeet - int(level)))
    return True, ""

def _stairs_up(ty: int, max_steps: int = 6, toward=None, timeout_ms: int = 8000) -> tuple:
    """★一步一层地往上走✗★ —— ★与 `_stairs_down` 镜像✗★（2026-09-30 第 38 轮 ✓ ⇒ P146 ✓）

    ## 为什么两个方向都要 ✗
      · **往下** ✗：模组的规划允许降 2~3 格 ✓ 而执行闸只认降 1 格 ✗ ⇒ 要替它拆（P140/P142 ✓）
      · **往上** ✗：模组**只能爬 1 层**✓（实测 `71→72` 走通 ✓ 而"爬 2 层"它做不到 ✗ P140 ✓）
        ⇒ 目标在头上 2 层时 ⇒ 直接发 ✗ ⇒ 它**根本爬不上去** ✗ ⇒ 同样要拆 ✓
    ★为什么它比"往下"安全✗★：**爬上去一定能回来** ✓（降 1 格模组会做 ✓ P140 的对照 ✓）
      ⇒ 所以这一条**不需要**过 `_descent_guard` ✗（那道闸管的是"下得去上不来"✓）
    ★它的来由✗★：本轮假人掉进 2 格小坑 ✗（P145 ✓）—— 而纯读探测发现
      `(4126,69,12) → (4126,70,11) → (4126,71,13)` 每步只差 **1 层** ✓
      ⇒ ★"爬出去"不需要放方块✗★（★那是最省事、也最不碰世界的一条路✗★）
    """
    import math as _m
    p = _LIVE._pos_now()
    if p is None:
        return cut("读不到 Bot 坐标 ⇒ 不发台阶 ✓"), True
    x0, y0, z0 = int(p[0]), int(p[1]), int(p[2])
    log = ["★逐格上台阶（模组只会上 1 层 ✗ ⇒ 中间层替它拆 ✗）：从 (%d,%d,%d) 去 y=%d ✓"
           % (x0, y0, z0, int(ty))]
    steps = 0
    while y0 < int(ty) and steps < int(max_steps):
        plan = []
        for r in (3, 2, 1):
            for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cx, cz = x0 + dx * r, z0 + dz * r
                d = _m.dist((cx, cz), toward) if toward else 0.0
                plan.append((r * -1, d, cx, cz))
        plan.sort()
        nxt = None
        for (_nr, _d, cx, cz) in plan:
            if _cand_stand(cx, y0 + 1, cz):
                nxt = (cx, cz)
                break
        if nxt is None:
            log.append("✗ 在 (%d,%d,%d) 的**上一层**（y=%d）四邻没有能站的格 ✗ ⇒ 停 ✓"
                       "（★不许硬爬✗★ —— 模组爬不了 2 层 ✓ P140 ✓）" % (x0, y0, z0, y0 + 1))
            return cut("\n".join(log)), True
        (cx, cz) = nxt
        txt, bad = _LIVE._walk(cx, y0 + 1, cz, int(timeout_ms), True)
        _p2 = _LIVE._pos_now()
        if _p2 is None:
            log.append("✗ 走完读不到坐标 ⇒ 停 ✓（★不许当「到了」✗★）")
            return cut("\n".join(log)), True
        nx, ny, nz = int(_p2[0]), int(_p2[1]), int(_p2[2])
        rise = ny - y0
        log.append("  第 %d 步：(%d,%d,%d) → (%d,%d,%d) ｜ 世界真值上升 %d ｜ 模组说：%s"
                   % (steps + 1, x0, y0, z0, nx, ny, nz, rise, (txt or "").splitlines()[0][:60]))
        if rise != 1:
            log.append("✗ 这一跳**没上 1 层**（上升 %d ✗）⇒ 停 ✓ 并如实报 ✗" % rise)
            return cut("\n".join(log)), True
        x0, y0, z0 = nx, ny, nz
        steps += 1
    ok_up = y0 >= int(ty)
    log.append("%s 结束于 (%d,%d,%d) ｜ 共 %d 步 ｜ ★目标 y=%d %s✗★"
               % ("✓" if ok_up else "✗", x0, y0, z0, steps, int(ty),
                  "**上去了**" if ok_up else "**没上去**"))
    return cut("\n".join(log)), (not ok_up)

def _stairs_down(ty: int, max_steps: int = 6, toward=None, timeout_ms: int = 8000) -> tuple:
    """★一步一层地往下走✗★ —— ★因为模组**只肯走降 1 格**✗★（2026-09-30 ✓ ⇒ P140/P142 ✓）

    ## 为什么必须有它 ✗（本轮实测的根因 ✓）
      模组内部**两套落差口径** ✗：A* 搜路允许降 **2~3 格**（`DshBridgeMod.java:3323` ✓）
      而每 tick 的执行闸只认降 **1 格**（`:3671-3678` ✓）
      ⇒ 交给它一个"降 2 格"的目标 ⇒ `result=edge` ✗ **位移 0.00** ✗ 而且**不重规划** ✗
      ⇒ ★中间层**能干**的事就是把那一跳拆成 N 个"降 1 格"✗★ ——
        诊断已实测这条路**真能走通** ✓（`73→72` 位移 2.51 ✓ 再 `72→71` 位移 2.04 ✓）

    ## 做法 ✓（★每一步都验真值✗★ 不信自述 ✓）
      ① 读当前格 ✓ ② 在 `y-1` 层里找**真能站**的邻格（`_cand_stand` ✓ 世界真值 ✓）
      ③ 走一格 ⇒ **读一次 `_pos_now()`** ✗ 确认真降了 1 层 ✓
      ④ 到不了 ⇒ **当场停 ＋ 说清是哪一步**✗（★绝不闷头循环✗★）
    `toward=(x,z)` ✓：多个候选时挑**离最终目标更近**的那个 ✓（免得横着乱走 ✓）
    返回 ✓：`(文本, bad)` ✓
    """
    import math as _m
    p = _LIVE._pos_now()
    if p is None:
        return cut("读不到 Bot 坐标 ⇒ 不发台阶 ✓"), True
    x0, y0, z0 = int(p[0]), int(p[1]), int(p[2])
    log = ["★逐格台阶（模组只认降 1 格 ✗ ⇒ 中间层替它拆 ✗）：从 (%d,%d,%d) 去 y=%d ✓"
           % (x0, y0, z0, int(ty))]
    # ★★下之前**先问"回得来吗"**✗★★（2026-09-30 第 38 轮 ✓ ⇒ P145 ✓）
    #   ★这是我自己造的洞✗★：上一轮加台阶时**没接这道闸**✗ ⇒ 它只会往下 ✗
    #     ⇒ 实测把假人送进了 `(4126,69,12)` 的**2 格小坑** ✗（比平台低 3 层 ✗ 爬不上来 ✗）
    #     ⇒ ★连累整轮电池✗★：`route_view`／`r3_verify` 报"挑不到目标"✗（连通区只剩 2 格 ✓）
    #   ⇒ 口径 ✓：**每下一步都过 `_descent_guard`** ✗（★项目里早就有这道闸✗★ 见 P120/P124 ✓）
    #     回不来 ⇒ **不走** ✗ 并如实说"下去就出不来" ✓ 给出替代办法 ✓
    try:
        _gm = _MISSION.get("map")
        if _gm is not None:
            okd, whyd = _descent_guard(_gm, y0, x0, z0, (x0, int(ty), z0))
            if not okd:
                log.append("✗ 台阶**第一层就不下** ✗：%s" % whyd)
                return cut("\n".join(log)), True
    except Exception as e:
        errlog("stairs descent guard failed", type(e).__name__, str(e))
    steps = 0
    while y0 > int(ty) and steps < int(max_steps):
        # ★候选：脚下那一层（y-1）里**真能站**的格 ✗（世界真值 ✓）
        #   ★★为什么要**够远**✗★★（2026-09-30 实测 ✓ ⇒ P142 ✓）：
        #     ✗ 第一版只找**紧邻**那一格（半径 1 ✓）⇒ 实测：模组报 `reached` ✓ 而世界真值
        #       **落差 0** ✗ —— 它停在**相邻列**没下去 ✗（★因为模组的"到了"**只算水平距离**✗★
        #       ⇒ 见 P140 §5.1 ✓ 站在目标旁边一格就算到 ✓）
        #     ✓ 而诊断里那条**成功**的对照是 `dshwalk 4122 72 7 exact`（从 73 ✓）——
        #       目标是**下一层、水平隔了 3 格** ✓ ⇒ ★它得**走出去**才"顺路掉下去"✗★
        #   ⇒ 口径 ✓：优先挑**半径 2~3 且朝目标方向**的那一格 ✓；实在没有才退回紧邻 ✓
        # ★★懒扫✗★★（2026-09-30 实测 ✓ ⇒ P142 ✓）：
        #   ✗ 第一版把所有候选（3 半径 × 4 方向 = 最多 12 格 ✗）**全扫一遍**✗
        #     ⇒ 每格 2 次 `dshscan` ✗ ⇒ 一步台阶最多 24 次往返 ✗✗
        #     ⇒ 实测代价：`r3_verify` T2 里 `walk_route` 的调用数 **28** ✗（判据要 ≤ walk_to 的 1.5 倍 ✗）
        #   ⇒ 口径 ✓：**先按偏好排序（半径大优先 ✓ 朝目标方向优先 ✓）✗ 再逐格扫到第一个能站的为止✗**
        #     ⇒ 正常情况下只扫 1~2 格 ✓（★"问世界"这条规矩不变✗★ 只是**少问几格** ✓）
        plan = []
        for r in (3, 2, 1):
            for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cx, cz = x0 + dx * r, z0 + dz * r
                d = _m.dist((cx, cz), toward) if toward else 0.0
                plan.append((r * -1, d, cx, cz))       # ★半径大的优先✗★
        plan.sort()
        cands = []
        for (neg_r, d, cx, cz) in plan:
            if _cand_stand(cx, y0 - 1, cz):            # ★扫到第一个能站的 ⇒ 立刻停✗★
                cands = [(-neg_r, d, cx, cz)]
                break
        if not cands:
            log.append("✗ 在 (%d,%d,%d) 的下一层（y=%d）**四邻没有能站的格** ✗ ⇒ 停 ✓"
                       "（★不许硬跳✗★ —— 那正是「一步降 2 格」被模组拒掉的那种 ✗）"
                       % (x0, y0, z0, y0 - 1))
            return cut("\n".join(log)), True
        cands.sort()
        (_r, _d, cx, cz) = cands[0]
        txt, bad = _LIVE._walk(cx, y0 - 1, cz, int(timeout_ms), True)
        _p2 = _LIVE._pos_now()
        if _p2 is None:
            log.append("✗ 走完读不到坐标 ⇒ 停 ✓（★不许当「到了」✗★）")
            return cut("\n".join(log)), True
        nx, ny, nz = int(_p2[0]), int(_p2[1]), int(_p2[2])
        drop = y0 - ny
        log.append("  第 %d 步：(%d,%d,%d) → (%d,%d,%d) ｜ 世界真值落差 %d ｜ 模组说：%s"
                   % (steps + 1, x0, y0, z0, nx, ny, nz, drop, (txt or "").splitlines()[0][:60]))
        if drop != 1:
            log.append("✗ 这一跳**没降 1 层**（落差 %d ✗）⇒ 停 ✓ 并如实报 ✗（不硬试 ✗）" % drop)
            return cut("\n".join(log)), True
        x0, y0, z0 = nx, ny, nz
        steps += 1
    ok_down = y0 <= int(ty)
    log.append("%s 结束于 (%d,%d,%d) ｜ 共 %d 步 ｜ ★目标 y=%d %s✗★"
               % ("✓" if ok_down else "✗", x0, y0, z0, steps, int(ty),
                  "**到了**" if ok_down else "**没到**"))
    return cut("\n".join(log)), (not ok_down)

def t_walk_to(x, y, z, timeout_ms=20000, exact=False, force=False):
    """★短距离单发一条 `dshwalk`★ —— **长距离一律拒** ✗（2026-09-23 血的教训 ✓）

    实测（两次都记在案 ✓）：一条长的 `dshwalk` 让模组自己走 ⇒ 它的**局部**寻路会贴着平台边绕 ✗
      · 18:18 目标挑在平台外 ⇒ `Bot掉出了这个世界` ✓ 丢掉钻石/漏斗/煤… ✗
      · 20:34 目标**在平台内**（13 格）也一样掉 ✗ 丢掉刚收的麦子 ✗
      ⇒ 结论 ✓：**在空岛上，"单发一条长走"这个用法本身就不安全** ✗
        （模组侧的修法在 v2.15 ✓：A* 预算 ↑ ✓ 搜索框罩住起终点 ✓ **贴边惩罚** ✓ —— 但要重启才生效 ✗）
      ⇒ 中间层这一步是**兜底** ✓：超过 `SAFE_WALK` 格就不发 ✓ 让它改用 `walk_route`
        （规划 ＋ 拆跳 ＋ **每跳验位置** ✓ 且**拒绝跨虚空的目标** ✓）
    """
    p = _LIVE._pos_now()
    if p is None:
        return cut("读不到 Bot 坐标 ⇒ 没走 ✓"), True
    import math as _m
    d = _m.dist(p, (float(x), float(y), float(z)))
    # ★★跨 ≥2 层 ⇒ **改成逐格台阶**✗★★（2026-09-30 ✓ ⇒ P142 ✓）
    #   ★为什么✗★：模组**只肯走降 1 格**✗ ⇒ 直接发过去 ⇒ `edge` ✗ 位移 0.00 ✗ 且不重规划 ✗
    #     ⇒ ★中间层唯一的杠杆就是**替它拆**✗★（诊断实测这条路能走通 ✓）
    #   ⚠ 只在**往下**时拆 ✓：往上 2 格模组一样上不去 ✗，但"往上"要先有台阶可爬 ✓
    #     ⇒ 往上先照旧发一次 ✓ 失败就**如实报"要搭台阶"** ✗（不许假装能爬 ✓）
    if (not force) and int(round(float(p[1]))) - int(y) >= 2:
        txt, bad = _stairs_down(int(y), toward=(float(x), float(z)),
                                timeout_ms=min(int(timeout_ms), 8000))
        head = ("★目标在你下面 %d 层 ✗ ⇒ **不发改道逐格台阶**✗（模组只认降 1 格 ✓ P142 ✓）\n"
                % (int(round(float(p[1]))) - int(y)))
        return cut(head + txt), bad
    # ★★目标在**头上 ≥2 层** ⇒ 同样要拆✗★★（2026-09-30 第 38 轮 ✓ ⇒ P146 ✓）
    #   ★为什么✗★：模组**只能爬 1 层**✗（实测 `71→72` 走通 ✓ 爬 2 层做不到 ✓ P140 ✓）
    #     ⇒ 直接发一条 ⇒ 它停在下面**根本不上** ✗（而它可能还会报"到了"✗ 见 P140 §5.1 ✓）
    if (not force) and int(y) - int(round(float(p[1]))) >= 2:
        txt, bad = _stairs_up(int(y), toward=(float(x), float(z)),
                              timeout_ms=min(int(timeout_ms), 8000))
        head = ("★目标在你头上 %d 层 ✗ ⇒ **不发改道逐格上台阶**✗"
                "（模组只会上 1 层 ✓ P146 ✓ ｜ ★爬上去一定能回来 ⇒ 不需要下降守卫✗★）\n"
                % (int(y) - int(round(float(p[1])))))
        return cut(head + txt), bad
    if d > SAFE_WALK and not force:
        return cut("★拒发★：目标 %.1f 格 **超过单发上限 %d 格** ✗\n"
                   "  为什么要拦 ✓：单发一条长走在空岛上会**贴边绕** ⇒ 实测掉过两次虚空 ✗\n"
                   "  ⇒ 请改用 `walk_route`（它会全局规划 ✓ 拆成短跳 ✓ 每跳验一次真实位置 ✓ "
                   "并**拒绝**跨虚空的目标 ✓）" % (d, SAFE_WALK)), True
    # ★第二道闸：目标那一格**站得住吗**★ ✗（2026-09-23 实测 ✓）
    #   现象 ✗：`walk_to` 去一个"地图看着能站"的坐标 ⇒ 模组走 28 秒 ✓ **停在 4.9 格开外** ✗
    #     （老路 1/3 成功 ✓ 而 `walk_route` 3/3 ✓ —— 差别就在它**先在地图上把落点定下来** ✓）
    #   ⇒ 中间层能做的 ✓：**发之前先问地图"那格能站吗"** ✓ 不能就别发 ✗ 并指路 ✓
    #     代价 ✓：地图新鲜时**全是内存操作** ≈0 秒 ✓（`walk_route` 建的任务图正好复用 ✓）
    mb, mm = _MISSION.get("box"), _MISSION.get("map")
    if (not force) and mb and mm is not None \
            and (time.time() - float(_MISSION.get("at") or 0)) < 900.0 \
            and mb[0] <= int(x) <= mb[3] and mb[2] <= int(z) <= mb[5]:
        import pathplan as PP
        pl = PP.Planner(mm, level=int(round(float(p[1]))))
        if not pl.ok(int(x), int(z)):
            # ★★拒之前必须**独立复核一次**★★ ✗（2026-09-23 实测撞到 ✓）
            #   现象 ✗：`r8`/`r9` 里"地图挑出来的安全目标"竟被这道闸拒了 ✗
            #     ⇒ 因为地图是**快照**（可能过时 ✓ 也可能那一列本来就没扫到 ✓）
            #     ⇒ 拿一张可能过时的图去**拒**一次正常短走 ⇒ 把好用法也拦死了 ✗
            #   ⇒ 规矩 ✓：**"拒"这种动作不能靠近似做**✗ ——
            #     拒之前用一次 1x1 独立读取（0.6 秒 ✓）把那一格**问实**✓
            #     读不出来（`""` ⇒ 通道问题 ✓）⇒ **不拒** ✓（宁可放行也不误伤 ✓）
            real = _scan_one(int(x), int(round(float(p[1]))), int(z))
            if real:
                return cut("★拒发★：目标那一格 (%d,%d) **站不住** ✗"
                           "（独立读取＝%s ✓ 地图也说没有地板 ✓）\n"
                           "  ⇒ 请用 `walk_route` ✓ 它会**自动挪到旁边能站的格子**并说明 ✓"
                           % (int(x), int(z), real)), True
    return _LIVE._walk(x, y, z, timeout_ms, exact, dist_hint=d)

def _scan_one(x, y, z) -> str:
    """独立读一格 ✓ 返回方块名 ✓；**读不出来返回空串** ✓（调用方要**区别对待** ✗ 见 t_walk_to ✓）"""
    out = _LIVE.dsh("dshscan %d %d %d %d %d %d" % (int(x), int(y), int(z), int(x), int(y), int(z)), 60.0)
    m = re.search(r"counts\[([^\]]*)\]", out or "")
    if m and m.group(1):
        name, _, _c = m.group(1).rpartition(":")
        return name
    if re.search(r"kinds=0\b", out or ""):
        return "minecraft:air"
    return ""

def _stand_levels(x: int, y_lo: int, y_hi: int, z: int) -> list:
    """★这一柱**哪几层能站**✗★（不是"最高那层" ✗ 也不是一个布尔 ✗）⇒ P149 ✓

    ★为什么要它✗★（2026-09-30 ✓ 用户一句话点破 ✓）：
      ✗ 我诊断坑的时候，每格只印了**最高的那一层**能不能站 ✗
      ⇒ ★"**一格高的台阶**"（＝只有 `y+1` 能站的那一格 ✓）**印不出来**✗★
      ⇒ 于是我下了个**错结论**："跑起来再上"这条路不存在 ✗ ⇒ 宣布"软件救援到此为止" ✗
      ⇒ 而实际上台阶就在旁边 ✓ 假人**自己两步就走出来了** ✓（世界真值 69→70→71 ✓）
    ⇒ 口径 ✓：★**"能站"是有层的✗ 问它就要回"哪几层"**✗★（回一个布尔一定丢信息 ✓）
    返回 ✓：能站的层号列表（升序 ✓）✓
    """
    out = []
    for y in range(int(y_lo), int(y_hi) + 1):
        if _cand_stand(int(x), y, int(z)):
            out.append(y)
    return out

def _cand_stand(x: int, y: int, z: int) -> bool:
    """★那一格**真能站**吗 —— 用**世界真值**问服务器 ✗ 不许按几何猜 ✓★

    ★为什么要有它✗★（2026-09-30 实机诊断 ✓ ⇒ P140 ✓）：
      ✗ `_near` 原来写死 `(x+1, y, z)` / `(x, y, z+1)` —— 用的是**容器自己的那一层** ✗
      ⇒ 实测（`(4122,72,4)` 那只桶旁边 ✓）：
        · `(4123,72,4)` 脚下是 **air** ✗（真的站不住 ✓）
        · `(4122,72,5)` 是 `computercraft:wireless_modem_normal`（薄板 ✗ 脚层被占 ✓）
      ⇒ ★那两个"候选格"**天生不存在**✗★ ⇒ `_near` 必失败 ⇒ `put_many` 连 `dshbox`
        都没发就退出 ✗（电池里 `dshbox=0` ✓ 就是它 ✓）
    口径 ✓：**只用这文件里**已经在用的**原语**✗（`_scan_one` ✓ P106 ✓）——
      ★而且命令**必须是空格写法**✗★（`dshscan x y z x y z` ✓）：
        我第一版写成 `dshlook x y z feet` / `dshmap 0 x,y,z` ✗ ⇒ 全被 Brigadier 参数层拒 ✗
        ⇒ 连老箱子都判"旁边没落脚点"✗（★现成的反例：同一个错我刚写进 P138/§Q1 又犯一次✗★）
    判据 ✓：**脚那一格是空气** ＋ **它下面那一格不是空气**（有地板 ✓）⇒ 才算能站 ✓
      （★不查"顶高"✗ —— 薄板顶高那件事归模组 ✓ 这里只用"有没有地板"这个最粗的真值 ✓）
    """
    feet = _scan_one(x, y, z)
    if feet == "":
        return False                       # ★读不出来 ⇒ **不算能站**✗（宁可不猜 ✓ P111 ✓）
    if feet != "minecraft:air":
        return False
    floor = _scan_one(x, y - 1, z)
    return bool(floor) and (floor != "minecraft:air")

def _stand_beside(x: int, y: int, z: int, span: int = 1) -> list:
    """★容器四邻里**真能站**的格子✗★（★`y`／`y−1`／`y+1` 三档都试✗★ ✓）

    返回 ✓：`[(格子, 为什么)]` ✓（空 ⇒ **这个容器旁边没有落脚点** ✗ ⇒ 如实报 ✓ P116 ✓）
    ★为什么是三档✗★：那只桶旁边的真实行走层比桶**低一格** ✗（诊断 §3 ✓）
      ⇒ 只试容器自己那一层 ⇒ 永远找不到 ✓
    """
    out = []
    for dy in (0, -1, 1):
        for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cx, cy, cz = int(x) + dx, int(y) + dy, int(z) + dz
            if _cand_stand(cx, cy, cz):
                out.append(((cx, cy, cz), "容器旁边 y%+d 那一档 ✓" % dy))
    return out

def _near(x, y, z, reach: float = 4.0):
    """走到目标**够得着**的位置 ✓（够不着就如实说走到哪了 ✗ 不硬做 ✗）

    ★2026-09-30 修（P140 ✓）：候选落脚格改成**先问世界**✗（`_stand_beside` ✓）——
      原来那两个写死的格子经常**根本站不住** ✓ ⇒ 表现是"没走到容器旁边"✗
      而真因是"**那两个候选格不存在**"✗（两者要能分清 ✓ P116 ✓）
    """
    import math
    st = _LIVE.dsh("dshdigest 1", 40.0) or ""
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", st)
    if m:
        p = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
        if math.dist(p, (float(x), float(y), float(z))) <= reach:
            return ("已经在够得着的范围里 ✓（%.1f 格）"
                    % math.dist(p, (float(x), float(y), float(z)))), False
    cands = _stand_beside(int(x), int(y), int(z))
    if not cands:
        return ("★这个容器**旁边没有落脚点**✗★：`(x±1, z)` 与 `(x, z±1)` 在 y+0／y-1／y+1 "
                "三档都站不住 ✓ ⇒ **不动手** ✓（★这不是「没走到」✗ 而是「没有能站的格」✗★ "
                "P116/P140 ✓）"), True
    tries = []
    for (c, why) in cands:
        txt, bad = _LIVE._walk(c[0], c[1], c[2], 25000)
        tries.append("%s（%s）：%s" % (c, why, txt))
        if not bad:
            return ("走过去 ✓ ｜ " + " ｜ ".join(tries)), False
    return ("四邻候选格**都走不到** ✗ ｜ " + " ｜ ".join(tries)), True

def t_goto_route(route, timeout_ms=60000):
    """★路点表导航（§79.400）✗★：★一次给**一串路点** ⇒ 模组 tick 里**连续走**✗★

    ★`route` 两种写法✗★：★"x,y,z;x,y,z;…" 或 [[x,y,z], [x,y,z], …]✗★
    ★比 `walk_to` 好✗★：★`walk_to` 只 ≤8 格 ✗ 而且**一格一发**（★0.6 秒/条往返✗★）✗★
      ★这个**一条命令走完整段**（★实测 41 路点 9.3 秒 ✗ 约 6 倍✗★）✗★ ✓
    ★回执✗★：★`arrived=` ✗ `cells=` ✗ `seconds=` ✗ `end=`✗★ ✓
    """
    if isinstance(route, str):
        text = route.strip()
        if text.startswith("["):
            try:
                route = json.loads(text)
            except Exception as e:                 # ★不许静默✗★
                return cut("goto_route 解析失败：%r" % (e,))
        else:
            route = [p for p in text.split(";") if p.strip()]
    pts = []
    for p in route or []:
        if isinstance(p, str):
            v = [q for q in re.split(r"[,\s]+", p.strip()) if q]
        else:
            v = list(p)
        if len(v) != 3:
            return cut("goto_route 路点格式错：%r" % (p,))
        pts.append((int(float(v[0])), int(float(v[1])), int(float(v[2]))))
    if not pts:
        return cut("goto_route 没有路点")
    s = ";".join("%d,%d,%d" % p for p in pts)
    r = _LIVE.dsh('dshgoto "%s"' % s, 150.0) or ""
    if "dshgoto start" not in r:
        # sec 79.461: 模组现在把 ASCII key=value 放在**最前面**（★reason=… ✗ at=…✗★）
        #   ★因为 CC 控制台只渲染 ASCII ✗ 中文全变 ?✗★ ⇒ 这几个键才是能读的部分✗★
        _kv = kv(r)
        _why = (" reason=%s" % _kv["reason"]) if _kv.get("reason") else ""
        _at = (" at=%s" % _kv["at"]) if _kv.get("at") else ""
        return cut("goto_route 被拒%s%s｜%r" % (_why, _at, r[:160],))
    last = pts[-1]
    t0 = time.time()
    budget = max(6.0, min(180.0, float(timeout_ms) / 1000.0))
    while time.time() - t0 < budget:
        time.sleep(1.0)
        p = _LIVE._pos_now()
        if p and max(abs(p[0] - last[0]), abs(p[2] - last[2])) <= 1.5:
            return ("goto_route arrived=True cells=%d seconds=%.1f end=%d,%d,%d"
                    % (len(pts), time.time() - t0, int(p[0]), int(p[1]), int(p[2])))
    p = _LIVE._pos_now()
    return ("goto_route arrived=False cells=%d seconds=%.1f end=%s"
            % (len(pts), time.time() - t0, (tuple(int(v) for v in p) if p else None),))


def t_come_to(player=PLAYER, timeout_ms=20000):
    """走到玩家旁边 ✓ —— 先**问服务器要玩家的真实坐标** ✓（不听任何自述 ✗）"""
    import math
    raw = _LIVE.dsh("data get entity %s Pos" % player, 30.0)
    m = re.search(r"\[\s*(-?[\d.]+)d?\s*,\s*(-?[\d.]+)d?\s*,\s*(-?[\d.]+)d?\s*\]", raw or "")
    if not m:
        return ("读不到玩家 %s 的坐标 ✗（回执：%s）⇒ **不会瞎走** ✓"
                % (player, (raw or "空")[:200])), True
    px, py, pz = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    tx, ty, tz = int(math.floor(px)) + 1, int(math.floor(py)), int(math.floor(pz))
    txt, bad = _LIVE._walk(tx, ty, tz, timeout_ms)
    return ("玩家 %s 在 (%.1f,%.1f,%.1f) ✓ ⇒ %s" % (player, px, py, pz, txt)), bad

def t_stop():
    a = _LIVE.dsh("dshwalk stop", 30.0)
    return cut("已发 stop ✓ %s" % (a or "（没有回执 ✗）")), False

def t_idle(on):
    txt = _LIVE.dsh("dshidle %s" % ("on" if on else "off"), 30.0)
    return cut(txt or "（没有回执 ✗）"), (not ok_of(txt, "dshidle"))

def t_freeze(on=True):
    """★冻结/解冻★ ✓：把假人的**自行走动**关掉（解冻时**原样恢复** ✓ 不弄丢设置 ✗）

    `on=True` ⇒ 冻结 ✓（关自行走动 ＋ **记下原来是什么样** ✓）
    `on=False` ⇒ 解冻 ✓（回到**原来那个值** ✓ 原来开着就还它开着 ✓）
    ★幂等★ ✓：连着冻两次 ✓ 只记第一次的原值 ✓（不然会把"关"当成原值记下来 ✗ 就还错了 ✓）
    ⚠ 它**只关自行走动** ✗ —— 别的活（别的进程/玩家/别的任务）它管不了 ✓
      ⇒ 所以真正的判据还得靠"**工具窗口内的读数**"✓（见交接 §40.7 ② ✓）
    """
    if on:
        if _FROZEN["was"] is None:
            dig = _LIVE.dsh("dshdigest 1", 40.0) or ""
            m = re.search(r"idle=(\w+)", dig)
            _FROZEN["was"] = (m.group(1) if m else "unknown")
        txt = _LIVE.dsh("dshidle off", 30.0)
        ok = ok_of(txt, "dshidle")
        return cut("★冻结★：已关掉自行走动 ✓（原值记着 = %s ✓ 解冻时还回去 ✓）｜ %s"
                   % (_FROZEN["was"], txt or "（没有回执 ✗）")), (not ok)
    was = _FROZEN["was"]
    _FROZEN["was"] = None
    if was == "on":
        txt = _LIVE.dsh("dshidle on", 30.0)
        return cut("★解冻★：原来开着 ⇒ **还它开着** ✓ ｜ %s" % (txt or "（没有回执 ✗）")), (
            not ok_of(txt, "dshidle"))
    return cut("★解冻★：原来不是开着的（记的是 %s ✓）⇒ 保持关闭不越权 ✓" % was), False

def t_go_to_drop(item=None, radius=16, timeout_ms=20000):
    """★去捡掉落物★：找最近的那个走过去 ✓ 用世界真值自证（背包 items 涨了 ✓）"""
    import math
    dig = _LIVE.dsh("dshdrop %d" % int(radius), 60.0) or ""
    want = (item or "").lower()
    cands = []
    for m in re.finditer(r"\(?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)?", dig):
        x, y, z = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
        cands.append((x, y, z, "?"))
    if not cands:
        return cut("半径 %d 内**没有**%s掉落物 ✓（回执：%s）"
                   % (radius, ("指定的 " if item else ""), dig[:300])), False
    p = _LIVE._pos_now() or (0, 0, 0)
    cands.sort(key=lambda c: math.dist(p, c[:3]))
    x, y, z, name = cands[0]
    before = _inv_items()
    txt, bad = _LIVE._walk(int(x), int(y), int(z), timeout_ms)
    after = _inv_items()
    got = (after - before) if (before is not None and after is not None) else None
    okline = ("背包 items %s -> %s（%+d ✓）" % (before, after, got)) if got is not None \
        else "背包数读不到 ✗"
    return cut("去捡 %s @ (%.0f,%.0f,%.0f)：%s ｜ %s" % (name, x, y, z, txt, okline)), (
        got is None or got <= 0)

def _make_plan(sx, sz, gx, gz, sy, max_leg: float = 6.0, level=None,
               same_level_only: bool = False, max_up=None):
    """建图 ＋ 规划 ✓ 返回 (Planner, 航点, 原因, 图信息) ✓

    三道安全闸 ✓：① 目标必须在**连通区**里 ✓ ② 目标要在**内陆**（四邻都能站 ✓）否则就近挪 ✓
                  ③ 每条腿 ≤6 格 ✓（腿短 ⇒ 模组那个局部寻路没多少地方乱走 ✓）
    """
    import pathplan as PP
    import math as _m
    r, m, box = _route_map(sx, sz, gx, gz, sy)
    # ★规划器要带上"已知障碍"★ ✗（实地探到的挡路格 ✓ 见 BLOCKED ✓）
    # ★默认按**模组的真实能力**算 ✓（第 33 轮 ✓ 见 `MOD_CLIMB_UP` ✓）——
    #   要看"几何上能不能站"的调用方（地图/判据 ✓）显式传 `max_up=1` ✓
    pl = PP.Planner(m, level=int(level) if level else (int(sy) + 1), blocked=BLOCKED_LV,
                    same_level_only=same_level_only,
                    max_up=(MOD_CLIMB_UP if max_up is None else int(max_up)))
    reg = pl.region(sx, sz)
    note = ""
    gx2, gz2 = int(gx), int(gz)
    if (gx2, gz2) in reg and not pl.interior(gx2, gz2):
        best = None
        for (x, z) in reg:
            if pl.interior(x, z):
                d = (x - gx2) ** 2 + (z - gz2) ** 2
                if best is None or d < best[0]:
                    best = (d, x, z)
        if best and best[0] <= 4.0:
            note = "★目标 (%d,%d) 在平台边上 ⇒ 已挪到内陆格 (%d,%d)（防踩空 ✓）★ " % (
                gx2, gz2, best[1], best[2])
            gx2, gz2 = best[1], best[2]
    pts, why = pl.plan(sx, sz, gx2, gz2, region=reg)
    # ★图的"名字"退化要**大声报**★ ✗（第 30 轮 ✓）：快图若没解析出图例 ⇒ 每格地板名是一个**字母**✗
    #   ⇒ ASCII 视图整张 `?` ✗（用户要的"看得懂"没了 ✗）＋ `surface()` 的方块名全是假的 ✗
    #   这种退化**不影响能不能走** ✗ ⇒ 只靠走动判据永远发现不了 ✗ ⇒ 必须在这里说出来 ✓
    warn = ""
    if m.meta.get("truncated"):
        warn += " ｜ ★图被截断（空洞 ⇒ 可能冤枉地报「不通」✗）★"
    if int(m.meta.get("letters_kept") or 0) > 0:
        warn += (" ｜ ★图上的地板名是**字母**（%d 格 ✗ 图例没解析出来 ⇒ "
                 "ASCII 视图/名字全是假的 ✗）★" % int(m.meta["letters_kept"]))
    info = ("图 box=%s 覆盖 %.0f%% ｜ 建图 %s 次 %s 秒 缓存=%s%s"
            % (box, m.coverage() * 100, m.meta.get("calls"), m.meta.get("sec"),
               m.meta.get("from_cache"), warn))
    if not pts:
        # ★★"为什么不通"必须说**真的那一种**★★ ✗（第 33 轮 ✓ 实测抓到的误导 ✓）
        #   现象 ✗：目标其实**就在我脚下这块平台上** ✓ 只是**要抬一级** ✗ ——
        #     而 `Planner.plan()` 的第一句话是「**不在你脚下这块连通区域里** ⇒ 中间隔着虚空」✗
        #     ⇒ ★把"要爬一级"说成了"隔着虚空"★ ✗ —— 两件事的下一步完全不同 ✗（P116 ✓）
        #   口径 ✓（一处 ✓）：**几何能站（`max_up=1` ✓）而执行者到不了（`max_up=0` ✗）** ⇒
        #     那句"隔着虚空"**换掉** ✗ 改成"要抬一级"✓；真隔着虚空时才保留原话 ✓
        geo = None
        try:
            geo = PP.Planner(m, level=int(level) if level else (int(sy) + 1), max_up=1)
        except Exception:
            geo = None
        if geo is not None and geo.in_box(gx2, gz2) and geo.ok(gx2, gz2):
            # ★★整句替换 ✗ 不做字符串匹配 ★★（第 33 轮 ✓ 实测教训 ✓）：
            #   `plan()` 对"不通"有**好几种说法**（"不在你脚下这块连通区域"／
            #   "能站，但和你不在同一块连通的平台上"…✗）⇒ 只匹配其中一种 ✗
            #   ⇒ 另一种原样漏出去 ⇒ 判据当场抓到"**你还在怪虚空**"✗
            #   ⇒ 口径 ✓：**只要判定是"要爬"⇒ 那句话整句换成真的原因** ✗（一处写清 ✓）
            fy = geo.y(gx2, gz2)
            blk = (m.cols.get((int(gx2), int(gz2))) or {}).get(int(fy)) if fy is not None else None
            why = ("目标 (%d,%d) ★要**抬一级**才上得去★ ✗ —— 它**就在你脚下这块平台上** ✓"
                   "（脚层 %s ✓ 地板 `%s` ✓）✓ 只是要爬 ✗ 而 **%s** ✗\n"
                   "  ★这与「隔着虚空」不是一回事★ ✗ —— 不是过不去 ✓ 是**爬不上去** ✗\n"
                   "  ⇒ 怎么办 ✓：① 在旁边**垫一格半砖**（0.5 格是自动上的 ✓ 不用跳 ✓）"
                   "② 把那一格**挖掉**（就变同层了 ✓）③ 换一个**同层**的目标 ✓ ④ 等模组 v2.17 ✓"
                   % (gx2, gz2, (int(fy) + 1) if fy is not None else "?", blk or "?",
                      "模组爬不上去（实测停在 0.8~1.7 格外 ✗）" if MOD_CLIMB_UP < 1
                      else "落差太大"))
        return pl, None, note + why, info
    sp = PP.Planner.simplify(pts)
    outpts = [sp[0]]
    for (wx, wy, wz) in sp[1:]:
        px, _py, pz = outpts[-1]
        seg = _m.hypot(wx - px, wz - pz)
        n = max(1, int(_m.ceil(seg / max_leg)))
        for k in range(1, n + 1):
            cx = int(round(px + (wx - px) * k / n))
            cz = int(round(pz + (wz - pz) * k / n))
            cy = pl.y(cx, cz)
            outpts.append((cx, (cy + 1) if cy is not None else int(wy), cz))
    ded = [outpts[0]]
    for q in outpts[1:]:
        if (q[0], q[2]) != (ded[-1][0], ded[-1][2]):
            ded.append(q)
    return pl, ded, note + why, info

def t_plan_route(x, y, z, verify="auto"):
    p = _LIVE._pos_now()
    if not p:
        return cut("读不到 Bot 坐标 ⇒ 没规划 ✓"), True
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    _r, _m, _b = _route_map(sx, sz, int(x), int(z), sy)
    # ★★必须传**浮点脚高**★★ ✗（2026-09-28 实测抓到的真 bug ✓ 错题本 P101 ✓）：
    #   站在**耕地**上 ⇒ 脚高 = 70.94 ✓ `int()` 会给 **70** ✗ 而**脚占的格是 71** ✓
    #   ⇒ LEVEL 低一格 ⇒ 图描述的是"你下面那一层"✗ ⇒ `walk_to` 会**假 unreachable** ✗
    #     长走会出现"走完了还差 1 格 ⇒ 两边都判没到"✗（正是 P89 那个症状 ✓）
    LEVEL = _stand_level(_m, sx, sz, float(p[1]))
    # ★规划**之前**先求真★ ✓（第 17 轮 ✓）：图的高度是推的 ⇒ 规划就在错地面上做 ✗
    vinfo = _hull_verify(_r, _m, sx, sz, int(x), int(z), LEVEL, verify)
    # ★规划**之后**再按"路真正经过的框"补验 ⇒ 重规划★ ✗（第 18 轮 ✓ 治 P103 ✓）
    def _mp():
        # `_make_plan` 回 **4** 个值（第一个是规划器 ✓ 这里用不上 ✗）
        #   ⇒ 包装成 3 个 ✓（`_plan_verified` 的约定 ✓ 不许它去猜长度 ✗）
        _pl0, q, w, i = _make_plan(sx, sz, int(x), int(z), LEVEL, level=LEVEL)
        return q, w, i
    pts, why, info, vlog = _plan_verified(_r, _m, LEVEL, _mp, verify=verify)
    if not pts:
        # ★"规划不通"要说清是**哪一种不通**★ ✗（第 33 轮 ✓）：
        #   最常见的一种是"**要抬一级，而模组爬不上去**"✗ —— 那和"隔着虚空"完全是两回事 ✓
        #     ⇒ 说清楚 ＋ 给出**怎么办**（垫一格/挖掉/换同层 ✓）
        climb_hint = _climb_diagnosis(_m, LEVEL, int(x), int(z))
        return cut("规划**没成** ✗：%s\n%s%s%s%s" % (why, climb_hint, info, _vline(vinfo),
                                                    _vlog(vlog))), True
    # ★★"下得去、上得来"★★ ✗（第 33 轮 ✓）：往**低层**去的路要先问回程 ✓（一处口径 ✓）
    _okd, _whyd = _descent_guard(_m, LEVEL, sx, sz, pts[-1])
    if not _okd:
        return cut("%s\n%s" % (_whyd, info)), True
    lines = ["从 (%d,%d) 到 (%d,%d)：%s\n%s%s%s" % (sx, sz, int(x), int(z), why, info,
                                                    _vline(vinfo), _vlog(vlog)),
             "航点 %d 个（已把直线上的多余点去掉 ✓ 少发指令 ✓）：" % len(pts)]
    for i, (wx, wy, wz) in enumerate(pts):
        lines.append("  %d) (%d,%d,%d)" % (i + 1, wx, wy, wz))
    return cut("\n".join(lines)), False

def t_route_view(x, y, z, margin=1, max_cells=1200, verify="auto"):
    """★「这条路上挡着什么」★ —— 把规划出的路**画出来** ＋ 列出道中障碍（2026-09-28 ✓）

    ★与 `check_path` 的分工★ ✗（别当成同一个东西 ✗）：
      `check_path` = **逐格**实地探 ✓（每格 ≈0.6 秒 ✗ 世界真值 ✓）
                     ⇒ 回答「**图上没有的**方块有没有挡路」✓
      `route_view` = **看图** ✓（**零额外通道调用** ✓）
                     ＋ **可选地**把这条走廊**一次性扫回来验一遍** ✓（`verify` ✓）
                     ⇒ 回答「这条路画出来长什么样 ✓ 哪里有 `X`（走不通）✗ 哪里是 `?`（没看到）✗」
      ⇒ 正确用法 ✓：`route_view` 先看 ✓（便宜 ✓ 该验的它自己会验 ✓）
        图上还有 `X` / `?` ⇒ 再 `check_path` 逐格探（贵但更细 ✓）

    ★`verify` 为什么存在★ ✗（错题本 **P99** ✓）：旧模组的快图**只给一个字母** ✗
      ⇒ 高度只能**推**（"就当在你脚下一格"✗）⇒ 落差与"你这一层站着什么"**全看不见** ✗
      ⇒ 危险方向是"**说能走、其实是坑**"✗ ⇒ 那就**别推了** ✗ **扫回来** ✓：
        用 `dshscan <走廊> ":"`（`:` 匹配一切非空气 id ✓）**一次调用**拿回整片真实坐标 ✓
      ⇒ 图被就地改正 ✓ 且**后面的规划也吃到真值** ✓（同一张图 ✓ 已回写缓存 ✓）
    """
    p = _LIVE._pos_now()
    if not p:
        return cut("读不到 Bot 坐标 ⇒ 没画 ✓"), True
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    t0 = time.time()
    b0 = int(_MISSION.get("builds") or 0)
    _b0 = int(_MISSION.get("builds") or 0)
    r, m, _b = _route_map(sx, sz, int(x), int(z), sy)
    _b1 = int(_MISSION.get("builds") or 0)
    # ★★§79.321✗★★：★这一次到底建没建图 ✗ 没建**为什么**✗★ ⇒ ★让判据自己说出来✗★ ✓
    if _b1 > _b0:
        print("  ★route_view 建了 %d 张图✗★（★原因：%s✗★）"
              % (_b1 - _b0, _MISSION.get("last_miss") or "（没记到原因）"))
    LEVEL = _stand_level(m, sx, sz, float(p[1]))      # ★浮点脚高★ ✗ 见 P101 ✓
    _, pts, why, info = _make_plan(sx, sz, int(x), int(z), LEVEL, level=LEVEL)
    if not pts:
        return cut("规划**没成** ✗ ⇒ 也就没有「道」可画 ✓：%s\n%s" % (why, info)), True
    rcells = []
    for q in pts:
        c = (int(q[0]), int(q[2]))
        if c not in rcells:
            rcells.append(c)
    # ★先把"验之前"的结论记下来★ ✓ ⇒ 验完才能**如实报"地图错了几格"**✗（不是自我表扬 ✓）
    before = {c: m.cell_kind(c[0], c[1], LEVEL)[0] for c in rcells}
    mg = int(margin or 1)
    vinfo = None
    vskip = ""
    if _need_verify(m, verify):
        x0 = min(c[0] for c in rcells) - mg
        x1 = max(c[0] for c in rcells) + mg
        z0 = min(c[1] for c in rcells) - mg
        z1 = max(c[1] for c in rcells) + mg
        # 层范围与"清段"的口径统一在 `_verify_band` 里 ✓（`level-6 .. level+2` ✓）
        #   ★那段注释要看★ ✗：段选窄了会**清掉真值在段外的格**✗（图反而更差 ✗）
        vinfo = _verify_band(r, m, x0, z0, x1, z1, LEVEL, max_pages=6)
    else:
        vskip = ("模组 v2.16 自带**真高度** ✓（`has_offsets=True` ✓）⇒ 不必再扫 ✓ 省调用 ✓"
                 if m.meta.get("has_offsets") else "verify 被显式关掉了 ✓")
    kinds = {}
    bad = []
    ok_n = 0
    for i, (wx, wy, wz) in enumerate(pts):
        ch, name, whyk = m.cell_kind(wx, wz, LEVEL)
        kinds[ch] = kinds.get(ch, 0) + 1
        if ch in m.ROUTE_OK:
            ok_n += 1
        else:
            bad.append((i + 1, wx, wy, wz, ch, name, whyk))
    fixed = [c for c in rcells if m.cell_kind(c[0], c[1], LEVEL)[0] != before[c]]
    art, ncell = m.route_ascii(pts, LEVEL, margin=mg, max_cells=int(max_cells or 1200))
    builds = int(_MISSION.get("builds") or 0) - b0
    sec = time.time() - t0
    _ab = getattr(m, "last_art_box", None)
    L = ["★道剖面★ (%d,%d) ⇒ (%d,%d) ｜ 你站在 (%d,%d,%d) ⇒ **脚占的那一格 = %d** ｜ "
         "这次建图 **%d** 次（0 = 用的缓存 ✓ 通道一次没占 ✓）｜ 耗时 %.2f 秒"
         " ｜ ★图框=%s★"
         % (sx, sz, int(x), int(z), sx, sy, sz, LEVEL, builds, sec,
            ("%d,%d,%d,%d" % _ab) if _ab else "?"),
         info,
         "路 ✓：航点 %d 个 ⇒ 画出来 **%d** 个路线格 ｜ 走得通 **%d** ✓ ｜ "
         "★走不通 %d ✗★" % (len(pts), sum(kinds.values()), ok_n, len(bad))]
    if vinfo:
        L.insert(2, "★★实地验过★ ✓：走廊 %d×%d（y %d..%d）用 `dshscan \"\\:\"` **%d 次调用 "
                    "%.2f 秒**扫回来 ✓ ｜ 清掉旧值 **%d** 处 ✓ 写入真值 **%d** 处 ✓ ｜ "
                    "★结论被改正 **%d** 格✗★（这些格以前是**错的** ✗ —— 差额就是地图的错 ✓）"
                    % (vinfo["box"][3] - vinfo["box"][0] + 1,
                       vinfo["box"][5] - vinfo["box"][2] + 1,
                       vinfo["y"][0], vinfo["y"][1], vinfo["calls"], vinfo["sec"],
                       vinfo["cleared"], vinfo["inserted"], len(fixed)))
        if vinfo["truncated"]:
            L.insert(3, "⚠★没扫完（truncated ✓）⇒ 没扫到的地方**不算验过** ✗★"
                        "（`dshscan` 分页没取完 / 中途读失败 ⇒ 我**不假装**扫过了 ✗）"
                        " ⇒ 那几格仍按「图上推的」✗看 ✓ 出处见下面的逐格标注 ✓")
    else:
        L.insert(2, "没再花调用去验 ✓：%s" % vskip)
    # ★这张图到底有没有"高度"和"你这一层被占"★ ✗ —— 旧模组没有 ⇒ **大声说** ✗
    #   （静默降级的代价实测过 ✓：整张图 979 格全变"能走"✗ 落差和栅栏全看不见 ✗）
    if not m.meta.get("has_offsets") and not vinfo:
        L.insert(1, "★★警告 ✗：这张图**没有高度信息** ✗（模组还是旧版 ⇒ 没有 `y`/`b` 行 ✓）"
                    " ⇒ 字母格的高度是**按你脚高推的** ✗ ⇒ **落差看不见** ✗ 而且"
                    " **你这一层上站着什么也看不见** ✗（栅栏/机器会被跳过 ✗）"
                    " ⇒ ★走之前务必用 `check_path` 实地探 ✓★")
    elif not m.meta.get("has_offsets") and vinfo:
        L.insert(1, "高度 ✓：**这条走廊上的地面是实地扫回来的** ✓（不是推的 ✓）"
                    " —— 旧模组没有 `y` 行 ✗ 所以我自己扫 ✓；★走廊以外仍是推的**✗**★"
                    "（出处逐格标注见下 ✓）")
    else:
        L.insert(1, "高度 ✓：**真高度** %s 格 ✓（模组 v2.16 的 `y` 行 ✓ 不再是推的 ✓）｜ "
                    "★你这一层被占的格 %s 处★ ✓（`b` 行 ✓ 碰撞箱判定 ✓ "
                    "这才是「道中障碍」的真身 ✓）"
                    % (m.meta.get("y_exact"), m.meta.get("blocked")))
    if bad:
        L.append("★★道中障碍★（按走到的先后 ✓ — 这就是「识别道中障碍物」要的东西 ✓）★")
        for (i, wx, wy, wz, ch, name, whyk) in bad[:24]:
            # ★逐格标出处★ ✗（X4 ✓）：**探过** ✓ 与 **推的** ✗ 混在一起 ⇒ 我又会分不清 ✓
            prov = "实地扫过 ✓" if m.is_verified(wx, wz, LEVEL) else "图上推的 ✗"
            L.append("  %2d) 路线第 %d 格 (%d,%d,%d) ⇒ `%s` %s ｜ **出处：%s**%s"
                     % (i, i, wx, wy, wz, ch, whyk, prov,
                        (" ｜ 方块 = %s" % name) if name else ""))
        if len(bad) > 24:
            L.append("  …（还有 %d 处 ✓ 只列前 24 ✓）" % (len(bad) - 24))
        sug = []
        if any(b[4] == "?" for b in bad):
            sug.append("有 `?` ⇒ **地图没这一柱** ✗ ⇒ 那是「我没看到」不是「没有」✓ "
                       "⇒ 走之前用 `check_path` 实地探一探 ✓")
        if any(b[4] == "#" for b in bad):
            sug.append("有 `#` ⇒ 真挡着 ⇒ **绕**（`walk_route` 会重规划 ✓）或**挖**（`dig_block` ✓）")
        if any(b[4] in (".", "~") for b in bad):
            sug.append("有 `.`/`~` ⇒ 坑/液体 ⇒ **别硬走** ✗ 一定绕 ✓")
        L.append("建议 ✓：" + "；".join(sug) if sug else "建议 ✓：这条路的路线格有高度差 ✓ 正常走 ✓")
    else:
        L.append("★★这条路上**没有走不通的格** ✓★（图上能看见的都是 `*`/`^`/`v`/`+` ✓）"
                 + ("｜★这条走廊的地面已经**实地扫过** ✓ ⇒ 上面这句话是有底气的 ✓★"
                    if vinfo else
                    "—— 但「纸上没问题」不等于「道上真没问题」✗：地图是按**方块种类**建的 ✗ "
                    "⇒ 第一次去的地方、或上次半路被挡 ⇒ 仍要 `check_path` 实地探 ✓"))
    if art is None:
        L.append("图 ✗：包围盒 **%d** 格 > 上限 %d ⇒ **不画半张** ✗（宁可只给上面那份清单 ✓）"
                 % (ncell, int(max_cells or 1200)))
    else:
        side = art.count("#") + art.count("~")
        L.append("图 ✓（北在上 ✓ 左边是 x 的个位 ✓ 行首是 z ✓ 包围盒 %d 格 ｜ "
                 "★路两侧另有 %d 处 `#`/`~`★ —— 这就是「道中/道旁」的全貌 ✓）："
                 % (ncell, side))
        L.append(art)
        L.append(m.ROUTE_LEGEND)
    return cut("\n".join(L)), False

def t_walk_route(x, y, z, timeout_ms=25000, max_replan=2, chunk=None, sweep=4,
                 verify="auto"):
    """★走过去（长跳 ＋ 短补 ＋ 每步验真值 ＋ 偏了重规划）★

    `chunk` 默认 **= SAFE_WALK（8 格）** ✗：一跳超过 8 格就重新落回"单发长走"那个坑 ✗
      （实测掉过两次虚空 ✓ 见 `t_walk_to` ✓）⇒ 上限跟单发闸保持一致 ✓
    """
    import math as _m
    if chunk is None:
        chunk = SAFE_WALK
    p = _LIVE._pos_now()
    if not p:
        return cut("读不到 Bot 坐标 ⇒ 没走 ✓"), True
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    gx, gy, gz = int(x), int(y), int(z)
    _r0, _m0, _b0 = _route_map(sx, sz, gx, gz, sy)
    LEVEL = _stand_level(_m0, sx, sz, float(p[1]))     # ★浮点脚高★ ✗ 见 P101 ✓
    # ★开走**之前**先求真★ ✓（第 17 轮 ✓）：图的高度是推的 ⇒ **规划与分跳全建在错地面上** ✗
    #   ⇒ 这正是"假 unreachable ✗"与"走完还差 1 格 ✗"的温床 ✓
    #   只验**一次**（外接框 ✓）⇒ 之后的重规划都在已求真的图上做 ✓ 不重复花通道 ✓
    vinfo = _hull_verify(_r0, _m0, sx, sz, gx, gz, LEVEL, verify)
    log_lines = []
    hops = legs = replans = 0
    used_legs = False
    degraded = False
    guard = 0
    cur_hint = None
    last_dist = None
    ARRIVE = 1.6
    _walk_prog("start", 0, (sx, sy, sz), (gx, gy, gz), "开走")
    while guard < 40:
        guard += 1
        cur = cur_hint if cur_hint is not None else _LIVE._pos_now()
        if not cur:
            log_lines.append("★为什么停★：读不到位置 ✗（假人还在不在？先跑 `respawn_bot.py` ✓）")
            return cut("\n".join(log_lines)), True
        cx, cy, cz = int(cur[0]), int(cur[1]), int(cur[2])
        d_now = _m.dist(cur, (gx, gy, gz))
        if last_dist is not None and d_now > 0.05 + last_dist - 0.2 and guard > 2:
            log_lines.append("★停★：连着两步几乎没靠近（%.2f → %.2f 格 ✓）⇒ 再走就是原地打转 ✗"
                             % (last_dist, d_now))
            break
        last_dist = d_now
        if d_now <= ARRIVE:
            break
        # ★每一跳也"按路求真"★ ✗（第 18 轮 ✓）：第一跳几乎总是命中外接框 ⇒ 0 次调用 ✓
        #   少数绕出去的跳 ⇒ 补验一次并重规划 ✓（`rounds=2` ⇒ 最多 1 次补验 ✓）
        # ⚠ **每一跳重新量层**这件事**先不启用** ✗（第 34 轮 ✓ 纪律 ✓）：
        #   它只在"真的上了半步／下了台阶"时才有意义 ✓ 而那条路**默认关着** ✓
        #   （见 `pathplan.Planner.max_rise` 的长注释 ✓）
        #   ⇒ 先退回"开走前算一次" ✓ 保守 ✓ —— ★不许把没验过的行为放进生产路径★ ✗
        #     等"半步"被**自己垫的那块半砖**实测证明之后 ⇒ 两件事一起开 ✓
        LV = LEVEL

        def _mp_hop(cx=cx, cz=cz, sl=False, LV=LV):
            _pl0, q, w, i = _make_plan(cx, cz, gx, gz, LV, level=LV,
                                       same_level_only=sl)
            return q, w, i
        pts, why, info, vlog = _plan_verified(_r0, _m0, LV, _mp_hop,
                                              verify=verify, rounds=2)
        if not pts:
            # ★★早退也必须说"为什么" ＋ "现在离目标多远"★★ ✗（第 31 轮 ✓ P116 ✓）：
            #   原来只有"规划没成 ✗：<原因>"✗ ⇒ 调用方**不知道人在哪、也不知道下一步怎么办** ✗
            log_lines.append("规划**没成** ✗：%s ｜ %s" % (why, info))
            log_lines.append("★为什么停★：这一跳**规划不出来** ✗（原因见上一行 ✓）"
                             "—— 现在离目标 **%.2f 格** ✓ ⇒ "
                             "换一个**同层**的目标 ✓ 或者先自己走到别处再让它走 ✓"
                             % _m.dist(cur, (gx, gy, gz)))
            return cut("\n".join(log_lines)), True
        for ln in vlog:
            log_lines.append("  " + ln)
        # ★★走之前先"探路"：把这一跳的格子实地探一遍★★ ✗（2026-09-23 ✓ 用户点的方向 ✓）
        #   为什么 ✗：地图按**种类**建 ✓ 稀有方块（`computercraft:computer_command` 那类 ✓）
        #     压根不在图里 ✗ ⇒ "图上没障碍"不等于"道上没障碍" ✗
        #   ⇒ 探到挡路的 ⇒ 记进 `BLOCKED` ✓ ⇒ **立刻重规划绕开** ✓（这才是"识别道中障碍物"✓）
        #   预算 ✓：`sweep` 格（默认 6 ✓）—— ★它是有价格的★ ✗（2026-09-28 实测 ✓）：
        #     探 6 格 ≈ **3.5~4 秒** ⇒ 同一段 5~7 格的路会从"打平老路"变成 **2.6 倍**✗
        #     这是**用户点名要的取舍** ✓（「重点是识别道中的障碍物，不一定说一定要快」✓）
        #     ⇒ 所以给调用方留一个"路熟/赶时间"的开关 ✓：`sweep=0` ⇒ 跳过探路 ✓
        _mr = _MISSION.get("reader")            # ★先取图与 reader★ ✗（第 26 轮 ✓）
        _mm2 = _MISSION.get("map")              #   （我第一版把它们放在策略**后面** ✗
        #                                           ⇒ 策略里引用未定义的 `_mm2` ⇒ 被 except 吞掉 ⇒
        #                                             **静默失效** ✗ —— 这正是本项目最忌讳的那种降级 ✗）
        # ★★"贴着边的那一跳"要走小心点★★ ✗（2026-09-29 第 26 轮 ✓）
        #   判据 ✓：这一跳的航点里**有没有不是内陆的格**✓（四邻有站不住的 ✓）
        #   ⇒ 有 ⇒ 跳距压到 ≤`EDGE_HOP_CHUNK`（4 ✓）＋ 探路多探一格 ✓
        #   ★照走 ✗ 不改道 ✗★：规划器已经避过边了 ✓ 而"只有边路"时无路可选 ✓（上一轮 Q2 ✓）
        try:
            import pathplan as _PP
            _plp = _PP.Planner(_mm2, level=LV, blocked=BLOCKED_LV, avoid_edge=True)
            _c2, _s2, _edge_why = _hop_policy(_plp, pts, chunk, sweep)
        except Exception as e:
            errlog("hop policy failed", type(e).__name__, str(e))
            _c2, _s2, _edge_why = chunk, sweep, ""
        if _edge_why:
            log_lines.append("  " + _edge_why)
            chunk_use, sweep_use = _c2, _s2
            # ★★贴边那一跳：**只走同层**★★ ✗（第 31 轮 ✓ 用一次真事故换来的 ✓ 见 `_hop_policy` ✓）
            #   做法 ✓：拿"同层规划器"**重规划一次**（本地算 ✓ 不花调用 ✓）
            #     · 成功 ⇒ 用这条同层的路走 ✓（宁可靠不过去 ✓ 也别往边上踩台阶 ✗）
            #     · 失败 ⇒ **这一跳不走** ✗ 并如实说清 ✓（掉虚空的代价远大于走不到 ✓）
            pts2, why2, info2, _vl2 = _plan_verified(
                _r0, _m0, LV, lambda: _mp_hop(sl=True), verify="off", rounds=1)
            if pts2:
                log_lines.append("  ★改成**同层**的路走 ✓（%s ✓）★" % why2)
                pts = pts2
            else:
                log_lines.append("★这一跳**不走了** ✗：贴着边 ✓ 而同层又没有路可走"
                                 "（%s ✓）—— ★不掉下去比走到更重要★ ✗" % why2)
                break
        else:
            chunk_use, sweep_use = chunk, sweep
        hop_cells = pts[1:1 + max(0, int(sweep_use or 0))] if int(sweep_use or 0) > 0 else []
        sw = _mr.scan_route(_mm2, hop_cells, LV, budget=max(1, int(sweep_use or 0)),
                            known=BLOCKED) \
            if (hop_cells and _mr and _mm2) \
            else {"found": [], "cells": 0, "probed": 0, "left": 0, "sec": 0.0}
        if sw["found"]:
            names = ", ".join("%s@(%d,%d)" % (n, bx, bz) for (bx, bz, n) in sw["found"][:3])
            log_lines.append("★探路发现道中障碍 %d 处（%s）⇒ 记下来并绕开 ✓★" % (len(sw["found"]), names))
            for (bx, bz, n) in sw["found"]:
                _obst_add(bx, bz, n, LV)
            _obst_save()                  # ★落盘 ✓（跨进程/跨重启都记得 ✓ 见 _obst_load ✓）
            continue                      # ← 回到循环顶部：这次会用 `blocked` 重规划 ✓
        if guard == 1 or "mission" not in str(info):
            log_lines.append("图：%s ｜ 航点 %d 个" % (info, len(pts)))
        step_cap = 3.0 if degraded else float(chunk)
        hop = None
        for (wx, wy, wz) in pts[1:]:
            d = _m.hypot(wx - cx, wz - cz)
            if d <= step_cap:
                hop = (wx, wy, wz)
            else:
                break
        if hop is None:
            hop = pts[1] if len(pts) > 1 else pts[-1]
        if hop is None:
            break
        where = "长跳" if (not degraded and _m.hypot(hop[0] - cx, hop[2] - cz) > 4) else "短补"
        t_step = time.time()
        txt, bad = _LIVE._walk(hop[0], hop[1], hop[2], timeout_ms, dist_hint=_m.dist(cur, hop))
        step_s = time.time() - t_step
        # ★每步的"现在在哪"优先用**模组自报的落点**★ ✗（2026-09-23 提速 ✓）
        #   为什么可以 ✓：`dshwalk` 回执里的 `at=x,y,z` 是**服务器侧**的真实坐标 ✓
        #     和 `dshdigest` 读的是**同一个世界真值** ✓ 不是模型自述 ✗
        #   ⇒ 省掉一次 `dshdigest` 往返（≈0.6 秒/跳 ✓）⇒ R3 的比值从 1.72 压到 ~1.4 ✓
        #   但**没到**的时候必须独立读 ✗（那时要知道"到底停在哪了" ✓）⇒ 走 `_pos_now()` ✓
        at = kv(txt).get("at")
        after = None
        src = "模组自报"
        if not bad and at:
            mm2 = re.findall(r"(-?[\d.]+)", at)
            if len(mm2) >= 3:
                after = (float(mm2[0]), float(mm2[1]), float(mm2[2]))
        if after is None:
            after = _LIVE._pos_now()
            src = "独立读"
        cur_hint = after if after is not None else cur_hint
        moved = (None if not after else round(_m.dist(cur, after), 2))
        tag = ("跳 %d" % hops) if where == "长跳" else ("腿 %d" % (legs + 1))
        if where == "长跳":
            hops += 1
        else:
            legs += 1
            used_legs = True
        log_lines.append("%s -> (%d,%d,%d) %s：%s ｜ 本步 %.1fs ｜ 实测位移 %s 格 ｜ 现在 %s（%s ✓）"
                         % (tag, hop[0], hop[1], hop[2], where,
                            "到位 ✓" if not bad else "**没到** ✗", step_s, moved,
                            None if not after else "(%.1f,%.1f,%.1f)" % after, src))
        # ★★每一步都写一次心跳★★ ✗（2026-09-29 第 27 轮 ✓ 治"超时后一片空白"✗）：
        #   为什么要它 ✗：`walk_route` 是**阻塞**的 ✓ 长走要几分钟 ✓
        #     调用方（大脑/MCP）一旦**超时**✗ ⇒ 它**完全不知道人走到哪了** ✗ ⇒ 只能瞎猜或重来 ✗
        #   ⇒ 每跳落地就落一次盘 ✓（位置＝**独立读到的实测位置** ✓ 不是我推测的 ✗）
        _walk_prog("hop" if not bad else "miss", guard,
                   (int(after[0]), int(after[1]), int(after[2])) if after else (cx, cy, cz),
                   (gx, gy, gz),
                   "%s 到 (%d,%d,%d) %s" % (tag, hop[0], hop[1], hop[2],
                                            "到位 ✓" if not bad else "没到 ✗"))
        if not bad:
            continue
        if not degraded:
            degraded = True
            log_lines.append("=> 长跳没成 ⇒ ★改走法：之后一路逐段（每步 ≤3 格 ✓）★")
            continue
        if replans >= int(max_replan):
            log_lines.append("★放弃★：重规划已 %d 次 ✗ 最后卡在 (%d,%d,%d)：%s"
                             % (replans, hop[0], hop[1], hop[2], txt[:150]))
            break
        replans += 1
        log_lines.append("=> 短补也没到 ⇒ 从实测位置重规划（第 %d 次 ✓）" % replans)
    end = _LIVE._pos_now()
    dist = None if not end else _m.dist(end, (gx, gy, gz))
    # ★"到没到"必须判"**人在不在目标那一格里**"★ ✗（2026-09-28 第 18 轮 ✓ 实测抓到一次假"没到"✗）：
    #   原来只判"到目标**角点**的水平距离 ≤ 1.6"✗
    #   ⇒ 实测：目标格 = (4108,3) ✓ 人停在 (4108.9, 3.9) —— **就在那一格里**✓
    #     可角点距离是 **1.64** ✗ ⇒ 判"**还没到**"✗ ⇒ 大脑会再走一遍／报失败 ✗
    #   ⇒ 与"假 unreachable ✗"同一族 ✓（P89／P101／P103 ✓ 全是"明明对却判错"✗）
    #   口径 ✓：**在格子里 ✓ 或 距离够近 ✓** —— 两个满足一个就算到 ✓
    in_cell = False
    same_lv = False
    ok_arrive = False
    # ★★§79.438（★task-8 ✗ 2026-10-27✗★）✗★★：★"★到没到★"判定**收口**到 `mcp_core`✗★
    #   ★这里只是**取用**✗★：★`arrive_flags` 给两个分量（★下面的日志要把它们分开说✗★）✗
    #     ★`arrived_at` 是**唯一判定**（★`in_cell and same_lv` ✗ **绝不看距离**✗★）✗★ ✓
    #   ★语义没变✗★：★旧代码就是这里那两行（★x／z 落格 ＋ y 取整✗★）⇒ **逐字等价**✗★ ✓
    if end:
        in_cell, same_lv = arrive_flags(end, (gx, gy, gz))
        ok_arrive = arrived_at(end, (gx, gy, gz))
    # ★★"到没到" = **在目标那一格里 ＋ 层也对**★★ ✗（第 32 轮 ✓ 实测抓到假"到了" ✓）
    #   第 18 轮加的"或者距离 ≤1.6 也算到"✗ **现在必须去掉那半条** ✗：
    #     当时是为了治"人在格子里、可角点距离 1.64 ⇒ 判没到"✗（假**没**到 ✓）
    #     可它同时把"**站到旁边那一格、还低一层**"也算成到了 ✗（假**到了** ✗）
    #   现场 ✗：目标 `(4121,72,5)`（抬一级 ✓）⇒ 人停在 `(4121.70, **71.00**, 4.70)` ✗
    #     格不对 ✗ 层也不对 ✗ —— 而距离 0.76 ≤ 1.6 ⇒ 老代码报"到了"✗
    #   ★两种错的代价不一样★ ✗：假"没到" ⇒ 再走一次 ✓；假"到了" ⇒ **大脑接着动手，必然落空** ✗
    #   ⇒ 口径 ✓：**格子 ＋ 层**才算到 ✓；只是"到了旁边"就**如实说旁边**✗（P116 ✓）
    #   ★（★判定已经在上面的 `arrived_at` 那一次算完 ✗ 这里**不再自己算一遍**✗★）✓
    log_lines.append("★共 %d 跳 ＋ %d 腿 ✓ 重规划 %d 次 ✓ ｜ 最终位置 %s ⇒ 离目标 %.2f 格 ｜ "
                     "**在目标格里 = %s** ｜ **层对得上 = %s**%s★"
                     % (hops, legs, replans, None if not end else "(%.1f,%.1f,%.1f)" % end,
                        -1 if dist is None else dist, in_cell, same_lv,
                        "  ✓ 到了" if ok_arrive else "  ✗ 还没到"))
    if (not ok_arrive) and end is not None and dist is not None and dist <= 1.6:
        log_lines.append("★只到了**旁边** ✗：%.2f 格（很近 ✓）但**不在目标那一格里**"
                         "（格对=%s ✗）或者**层不对**（层对=%s ✗）⇒ "
                         "★「近」不等于「到」✗ —— 要动手就得先站到那一格／那一层上 ✓★"
                         % (dist, in_cell, same_lv))
    if vinfo:
        # 把"开工前求过真"这件事**留在最终报告里** ✓（不然事后复盘只看到"没到"✗）
        log_lines.insert(0, "开工前：%s" % _vline(vinfo).strip())
    # ★★没到 ⇒ **必须把原因说出来**★★ ✗（第 31 轮 ✓ 实测抓到的现场 ✓）
    #   现象 ✗：走 `(4114,7)`（那一格的**墙头**在 `y=72` ✓ 计划最后一段是"抬一级"✓）
    #     ⇒ 模组停在 `(4114.9,7.6)` ✗ 离目标 **1.09 格** ✓ 报"没到"✗ ——
    #       数字都对 ✓ 可**大脑拿到这句话没法行动** ✗（不知道是"图不通"还是"模组爬不上去"✗）
    #   ⇒ 口径 ✓：按**目标层与实测层的高度差**给结论 ✗（三种情况说三种话 ✓）
    if (not ok_arrive) and end is not None:
        _ey = int(round(float(end[1])))
        _dy = int(gy) - _ey
        if _dy > 0:
            log_lines.append(
                "★为什么没到★：目标是**你上面 %d 层**（现在 %d ✓ 目标 %d ✓）"
                "而模组停在了 %.2f 格外 ⇒ **它爬不上去** ✗ ⇒ "
                "要么把那一格挖掉／在旁边垫一格再走 ✓ 要么换一个**同层**的目标 ✓"
                "（★注意：这不是「图上不通」✗ —— 规划说这条路是通的 ✓）★"
                % (_dy, _ey, int(gy), -1 if dist is None else dist))
        elif _dy < 0:
            log_lines.append(
                "★为什么没到★：目标是**你下面 %d 层**（现在 %d ✓ 目标 %d ✓）"
                "而模组停在 %.2f 格外 ⇒ 多半是**不敢往下跳** ✗ ⇒ "
                "换成同层目标 ✓ 或者先自己走到那一段的边上再让它走 ✓"
                % (-_dy, _ey, int(gy), -1 if dist is None else dist))
        else:
            log_lines.append(
                "★为什么没到★：目标与你现在**同一层**（%d ✓）却差 %.2f 格 ⇒ "
                "是**水平方向被挡住了** ✗ ⇒ 用 `check_path` / `route_view` 看那一段 ✓"
                % (_ey, -1 if dist is None else dist))
    # ★收尾心跳★ ✗（第 27 轮 ✓）：★没有它，"走完了"与"被杀了"就分不出来 ✗★
    #   （`walk_progress` 看到 `phase=done` ⇒ 那是**正常结束** ✓；看到 `hop` 却很久没更新 ⇒
    #     那是**中途断了** ✓ —— 这两种在排查时是完全不同的结论 ✓）
    _walk_prog("done" if ok_arrive else "ended",
               hops + legs, (end[0], end[1], end[2]) if end else None, (gx, gy, gz),
               "共 %d 跳 ＋ %d 腿 ｜ 离目标 %.2f 格 ｜ %s"
               % (hops, legs, -1 if dist is None else dist,
                  "到了 ✓" if ok_arrive else "没到 ✗"))
    return cut("\n".join(log_lines)), (dist is None or not ok_arrive)

def t_platform(radius=20):
    """★我脚下这块平台：多大、**边在哪**、我离边多近★ ✓（2026-09-29 第 24 轮 ✓）

    ★为什么必须有它★ ✗：`safe_spots` 只说"哪些落脚点可以放心去"✓
      而"**边在哪**"从来没人说过 ✗ —— 可**掉虚空正是从踩边开始**的 ✗
      （2026-09-23 真掉过一次 ✓ 丢掉：钻石 x2 ✓ 钻石斧 ✓ 漏斗 ✓ 煤 x8 ✓ 铁锭 ✓ 锤子 ✓ 麦子/种子 ✓）
    """
    import pathplan as PP
    p = _LIVE._pos_now()
    if not p:
        return cut("读不到 Bot 坐标 ⇒ 没量 ✓"), True
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    r, m, box = _route_map(sx, sz, sx + 8, sz, sy)
    LEVEL = _stand_level(m, sx, sz, float(p[1]))
    # ★★"我的平台"是**同层**概念 ⇒ 用 `same_level_only`★ ✗（第 31 轮 ✓ 实测抓到 ✓）：
    #   `ok()` 修好之后它按窗口允许抬一级 ✓ ⇒ 不开关的话**墙头（+1 层 ✓）会被算进我的平台** ✗
    #   ⇒ 实测：`platform_test` 的 P1 拿**同层**去独立探那些"边格"✗ ⇒ 世界说站不住 ⇒ 判据红 ✗
    #     —— 可工具说的是**另一层** ✓（不是工具错 ✓ 是**两个问题被混成一个口径** ✗）
    #   ⇒ "**我这一层连着多大一片、边在哪**" ✓（踩空是**同层**的事 ✓）
    pl = PP.Planner(m, level=LEVEL, blocked=BLOCKED_LV, same_level_only=True)
    reg = pl.region(sx, sz)
    if not reg:
        return cut("连通区是空的 ✗（图不对？先 `map_area` 看一眼 ✓）"), True
    bnd = _boundary_cells(pl, reg)
    inner = [c for c in reg if pl.interior(c[0], c[1])]
    dist = {}
    for (x, z) in bnd:
        dist[(x, z)] = ((x - sx) ** 2 + (z - sz) ** 2) ** 0.5
    near = sorted(bnd, key=lambda c: dist[c])
    (nx, nz) = near[0] if near else (sx, sz)
    d_near = dist.get((nx, nz), 0.0)
    bear = _bearing(nx - sx, nz - sz)
    L = ["★平台★ 你站在 (%d,%d,%d) 脚格=%d ｜ 连通 **%d** 格（内陆 %d ✓ ／ 边 **%d** 格）｜ 图 box=%s"
         % (sx, sy, sz, LEVEL, len(reg), len(inner), len(bnd), box),
         "★最近的边★：(%d,%d) 距你 **%.1f** 格 ⇒ 方向 **%s**" % (nx, nz, d_near, bear)]
    if near and d_near <= 2.0:
        L.append("★★警告 ✗：你**贴着边**（%.1f 格）—— 空岛上一步踩空就是虚空 ✗"
                 "（那次丢掉：钻石/钻石斧/漏斗/煤/铁/锤子/麦子 ✓）"
                 "⇒ 要动就往 **%s** 的反方向走 ✓ 或先用 `safe_spots` 挑落脚点 ✓★"
                 % (d_near, bear))
    else:
        L.append("（离边 %.1f 格 ✓ 你现在是安全的 ✓）" % d_near)
    L.append("边界最近几个（★别把它们当目标★）："
             + ", ".join("(%d,%d)%.1f" % (x, z, dist[(x, z)]) for (x, z) in near[:6]))
    return cut("\n".join(L)), False

def t_walk_progress(fresh_s=90.0):
    """★上一次走**走到哪了**★ ✓ —— 超时之后就用它 ✓（2026-09-29 第 27 轮 ✓）

    ★为什么必须有它★ ✗：`walk_route` 一阻塞就是几分钟 ✓ 调用方超时后**手里什么都没有** ✗
      ⇒ 只能"整段重来"（白走一遍 ✗ 还可能把人送进危险区 ✓）
    它给你 ✓：**最后一次落地的实测位置** ✓ 目标 ✓ 走到第几步 ✓ **多久以前**（新鲜度 ✓）
      ＋ **现在人又在哪**（1 次独立读 ✓）—— ★两件事分开说 ✗ 不许混成一个"应该在哪" ✗★
    """
    if not WALK_PROG_FILE.is_file():
        return cut("还没有任何走动的记录 ✓（说明这一进程里没人用 `walk_route` 走过 ✓）"), False
    try:
        rec = json.loads(WALK_PROG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        return cut("进度文件读不动 ✗：%s" % type(e).__name__), True
    age = max(0.0, time.time() - float(rec.get("at") or 0))
    fresh = age <= float(fresh_s or 90.0)
    cur = _LIVE._pos_now()
    L = ["★上次走动★ %s ｜ 阶段=%s ｜ 第 %d 步 ｜ 最后落地的**实测位置** %s"
         % (rec.get("when") or "?", rec.get("phase") or "?",
            int(rec.get("step") or 0),
            ("(%.1f,%.1f,%.1f)" % tuple(rec["pos"])) if rec.get("pos") else "?"),
         "目标 %s ｜ 说明：%s"
         % (("(%.1f,%.1f,%.1f)" % tuple(rec["target"])) if rec.get("target") else "?",
            rec.get("note") or "-")]
    if fresh:
        L.append("★这是 **%.0f 秒前**的事 ⇒ 看起来**还在走**（或刚结束）✓★" % age)
    else:
        L.append("★★这是 **%.0f 秒前**的事 ⇒ **早就过去了** ✗ 别把它当成「正在走」 ✗★"
                 % age)
    if cur:
        L.append("现在人在 (%.1f,%.1f,%.1f)（**这一次**独立读的 ✓）" % cur)
        if rec.get("pos"):
            d = ((cur[0] - rec["pos"][0]) ** 2 + (cur[2] - rec["pos"][2]) ** 2) ** 0.5
            L.append("⇒ 与「最后落地」差了 %.1f 格 %s"
                     % (d, "（说明那次之后还在动 ✓）" if d > 1.0 else "（基本没动 ✓）"))
    else:
        L.append("⚠ 现在**读不到**假人位置 ✗（它还在不在？先跑 `respawn_bot.py` ✓）")
    if rec.get("target") and cur:
        dt = ((cur[0] - rec["target"][0]) ** 2 + (cur[2] - rec["target"][2]) ** 2) ** 0.5
        L.append("⇒ 离那个目标还剩 **%.1f** 格" % dt)
    return cut("\n".join(L)), False


# ── ★★v2.19 第三/四刀：跟着搬过来的常量★★ ✗（★同一个对象只有一份✗★）
SAFE_WALK = 10.0


# ── ★★v2.19 第三/四刀：跟着搬过来的常量★★ ✗（★同一个对象只有一份✗★）
_FROZEN = {"was": None}          # 记住"冻之前是什么样" ✓ 解冻时原样还回去 ✗
