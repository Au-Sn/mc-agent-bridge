#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mc_mcp.py —— ★给 Bot 的那双手★（把 `dsh*` 指令包成 MCP 工具，stdio ✓ 一行一条 JSON ✓）

★这份文件在 2026-09-23 被我自己弄坏过一次★ ✗（事故与修法见 `docs/错题本.md` P91 ✓）：
  我用 `Get-Content -Raw`（**没带 -Encoding** ✗）读它、再用 `Set-Content -Encoding utf8` 写回 ✗
  ⇒ PowerShell 5.1 按 cp936 解码 UTF-8 字节 ⇒ **所有中文全花** ⇒ 文件没法解析 ✗
  救法 ✓：坏前的字节码 `tools/__pycache__/mc_mcp.cpython-314.pyc`（19:57 ✓ 早于事故 ✓）
    ⇒ 把 **31 件工具的名字与说明逐字倒出来**（`tools/pyc_tools_text.py` ⇒ `logs/tool_descriptions.txt` ✓）
    ⇒ 再照它重写本文件 ✓ **工具名与说明一字不改** ✓（大脑看的就是这些字 ✓）
  坏文件留在 `tools/mc_mcp.broken.py` ✓（证据不删 ✗）
  ⚠ 代价 ✓：原注释没有副本 ✗ 一并丢失 ⇒ 现在这些注释是重写的 ✓（行为以工具说明为准 ✓）

## 这一层是什么 ✗
  · 大脑（常驻 ACP 会话 ✓）只会说 MCP ✓；模组只会听 `dsh*` 指令 ✓ ⇒ 这里做翻译 ✓
  · 每个工具都**如实回报** ✓：做不到要说清为什么 ✗（"没回执"也是一种回执 ✓）
  · 日志 ✓：每次调用写一行到 `logs/mc_mcp.jsonl` ✓（这就是"它到底动没动手"的**客观证据** ✓）

## 依赖（本文件不该自己造轮子 ✓）
  · `tools/mapread.py` ✓ 地图（按方块种类批量取坐标 ＋ 缓存 ✓）
  · `tools/pathplan.py` ✓ 全局 A* ＋ 连通区/内陆/安全走廊 ✓
  · `tools/jobs_store.py` ✓ 长任务账本（`jobs/*.json` ✓）
  · `agent/jobs.py` ✓ 整条作业（收庄稼 ✓ 筛矿 ✓ —— 那边是老实现 ✓ 复用不重写 ✓）
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# ★★v2.19：把"人人都在用的那一小撮原语"抽到 `tools/mcp_core.py`★★ ✗
#   WHY ✓：本文件约 2800 行、且 **2026-09-23 被手工替换毁过一次** ✗（**P91** ✓）⇒ 拆成四块 ✓
#   ★第一刀必须是**原语**✗★ —— 实测枢纽（用 ast 量出来的 ✓）：
#     `cut` 被 **39** 个函数用 ✓ `dsh` 26 ✓ `errlog` 11 ✓ `_pos_now` 11 ✓ `ok_of` 8 ✓
#     ⇒ 先抽它们 ⇒ 后面三块（感知／走路／动作）各自 import 就**不会循环依赖** ✓
#   ⚠ ★**名字与原义一个字不改**✗★（工具名与说明是大脑直接读的那些字 ✓ 见 P91 ✓）
#   ⚠ `ROOT` 与两行 `sys.path` 也搬去了 core ✗ —— core 在 import 期就把它们设好 ✓
#     （`from mcp_core import …` 会**先跑完** core 再往下走 ✓）
from mcp_core import (  # noqa: E402
    BOT, LOG, PLAYER, ROOT,
    ascii_or_note, ch, cut, dsh, errlog, esc, kv, log, looks_mangled, ok_of,
    _inv_items, _pos_now,
)
from mcp_jobs import (  # noqa: E402
    t_job_plan,
    t_job_next,
    t_job_step,
    t_job_open,
    t_job_list,
    t_job_close,
)


# ★★v2.19 第三/四刀：这一份现在只放「动作 ＋ 记忆 ＋ JSON-RPC」✗★★
#   走路 ⇒ `tools/mcp_walk.py` ✓ 看/地图/容器 ⇒ `tools/mcp_percept.py` ✓
#   量测（两边共用 ✓）⇒ `tools/mcp_geo.py` ✓ 原语 ⇒ `tools/mcp_core.py` ✓
#   ★依赖单向✗★：mc_mcp ⇒ walk ⇒ percept ⇒ geo ⇒ core（无环 ✓）
#
# ★★为什么还要 `import *`（本文件最容易被"清理"掉的一段 ✗）★★
#   测试与冒烟桩打的是 **`mc_mcp.<名>`** ✗（实测点过名的：
#     `M._descent_guard`（errata_guard E5 ✓）／`M._MISSION`（r9_target_guard ✓）
#     `M._near`（chest_many ✓ 还要**猴补**它 ✓）／`M._walk`・`M._pos_now`・`M.dsh`
#     （mc_mcp_smoke ✓）／`M._bearing`・`M._fill_names`・`M._hop_policy`・`M._make_plan`
#     `M._obst_save`・`M._parse_digest`・`M._return_ok`・`M._route_map`・`M._stand_level`
#     `M._walk_prog`・`M.BLOCKED*`・`M.SAFE_WALK`・`M.MOD_CLIMB_UP`・`M.WALK_PROG_FILE`… ✓）
#   ⇒ ★搬家**不许改调用方的名字**✗★（判据：`mcp_surface --diff` 逐字节 ＋ 全量电池 ✓）
#   ⇒ 所以这里把四块的**全部名字**原样再导出一次 ✓（**这不是死代码 ✗ 是兼容面** ✓）
#   ⚠ 顺序＝依赖顺序 ✓（后面的覆盖前面的同名 ✓ 与"原来的一个模块"语义一致 ✓）
from mcp_core import *  # noqa: E402,F401,F403
from mcp_geo import *  # noqa: E402,F401,F403
from mcp_percept import *  # noqa: E402,F401,F403
from mcp_walk import *  # noqa: E402,F401,F403
from mcp_gesture import *  # noqa: E402,F401,F403   ★动作即语言（P2 ✓ 2026-10-02 ✓）★
# ⚠ `import *` **不带下划线开头的**✗（Python 的规矩 ✓ `__all__` 也没给 ✓）
#   ⇒ 那一族（`_walk`/`_near`/`_pos_now`/`_MISSION`/`_route_map`/`_stand_level`/… ✓
#     测试点名要用的**全在下划线里** ✗）必须**显式**再绑一遍 ✓
# ★别删✗★：删了 ⇒ `chest_many_test` 的 `M._near = 计数桩` 会**打空**（假绿 ✗）
#   ＋ `errata_guard` 的 `M._descent_guard` 会 `AttributeError` ✗（判据当场变红 ✓ 还好 ✓）
from mcp_core import (  # noqa: E402,F401
    _CH, _LIVE, _inv_items, _pos_now, _MISSION,
)
from mcp_geo import (  # noqa: E402,F401
    _bearing, _boundary_cells, _fill_names, _hop_policy, _hull_verify, _need_verify,
    _obst_add, _obst_load, _obst_save, _plan_verified, _planner_for_hop, _route_map,
    _stand_level, _verify_band, _vline, _vlog, _walk_prog, OBST_FILE,
    OBST_TTL, EDGE_HOP_CHUNK,
)
from mcp_percept import (  # noqa: E402,F401
    _box, _box_many, _box_peek_map, _collide_set, _inv_count, _inv_ids, _parse_digest,
    _parse_items, _reconcile, _resolve_item, PRESETS,
)
from mcp_walk import (  # noqa: E402,F401
    _cand_stand, _climb_diagnosis, _descent_guard, _make_plan, _near, _planner_exec,
    _return_ok, _scan_one, _stairs_down, _stairs_up, _stand_beside, _stand_levels,
    _walk, _FROZEN, SAFE_WALK,
)


# ── 走路（★本层最要紧的一块★ ✓）─────────────────────────────────────────────
# （★v2.19 第三/四刀✗★：走路的实现已搬去 `tools/mcp_walk.py` ✓ 地理/量测的辅助在 `tools/mcp_geo.py` ✓ —— 这一层现在只留「动作 ＋ 记忆 ＋ JSON-RPC」✗）


# ── 观察 ─────────────────────────────────────────────────────────────────────
# （★v2.19✗★：观察与地图读取搬去了 `tools/mcp_percept.py` ✓ —— `bot_state`/`look`/`scan`/`map_area`/`survey`/`whereami` 都在那边 ✓）


def t_dig_block(x, y, z, wait_s=25.0):
    """挖掉那一格 ✓（先走到够得着 ✓ 模组自己会挑工具 ✓）

    ★★2026-10-01 实测两条 ✗ 都把"信回执"堵死了★★：
      ① ★`dshdig` **会生效，但可能要等十几秒**✗★ —— 我先拿 **5+5 秒**的窗口判过它是
         "no-op / 指令不存在"✗ ⇒ ★三十秒后回头看世界：那两格**真的变成 air 了**✗★
         ⇒ ★"够快"不是判据 ✗ **"最终一致"才是** ✓★（P140/P154 那一族：判据要看世界真值 ✓）
      ② 所以这里 ★发完**回头问世界真值、并等它**✗★（默认最多 25 秒 ✓）——
         等到变化 ⇒ 成功 ✓；等到超时还没变 ⇒ ★报错✗★（不许再"发完就宣布成功"✗）
    """
    import time as _t
    nav, bad = _near(x, y, z)
    if bad:
        return cut("✗ 没走到那格旁边 ⇒ **没挖** ✓（%s）" % nav), True

    def _blk():
        t = str(t_scan(int(x), int(y), int(z), int(x), int(y), int(z), max_=2)[0])
        m = re.search(r"counts\[([^\]]*)\]", t)
        if not m or not m.group(1).strip():
            return "air"
        return m.group(1).split(",")[0]

    before = _blk()
    if before == "air":
        return cut("那一格 (%d,%d,%d) **本来就是 air** ⇒ 没东西可挖 ✓（%s）" % (x, y, z, nav)), False
    txt = dsh("dshdig %d %d %d" % (int(x), int(y), int(z)), 60.0)
    after, waited = before, 0.0
    while waited < float(wait_s):
        _t.sleep(1.5)
        waited += 1.5
        after = _blk()
        if after != before:
            break
    if after == before:
        return cut("★挖了但等了 %.0f 秒世界还是没变✗★：(%d,%d,%d) 仍是 %s ｜ 回执=%s"
                   % (waited, x, y, z, after, (txt or "（没有回执）")[:110])), True
    return cut("挖 (%d,%d,%d)：%s ⇒ 世界真值 %s → %s（等了 %.1f 秒 ✓）｜ %s"
               % (x, y, z, nav, before, after, waited, (txt or "（没有回执 ✗）")[:80])), False


# ★★"先看再放"✗★★（欠账 ㉕ ✓ 2026-10-03 ✓ 世界实测换来的 ✓）
#   ★实测✗★：★`(4121,70,9)` 是空气 ✗ 下面两格**都是实心土**✗ 手上也有方块✗
#     ★可 `dshplace` 反复挑侧面支撑 ⇒ `useItemOn=FAIL`✗★
#     ★而**先 `point_at` 那一格** ⇒ **一次就成**✗★（★回读 `crafting_table`✓★）
#     ⇒ ★模组的 `useItemOn` 要求"★假人**真的看着那一面**✗"✗
#       而放置这条路**从来没保证过视线**✗★ ✓
#   ★⇒ 口径✗★：★放置**之前**必须先把视线对准那一格（★像真人✗★）✗
#     ★而且"对准失败"要**写在回执里**✗ ✗ 不许静默跳过✗★ ✓
AIM = None          # ★注入缝：判据里换成假的 ✓ 默认走 `t_point_at`✓★


def _aim_before_place(x, y, z):
    """★把视线对准那一格 ✗ 回 `(回执文本, 是否没对上)`✗★（★异常**不吞**✗★）"""
    try:
        f = AIM if AIM else t_point_at
        out, bad = f(float(x) + 0.5, float(y) + 0.2, float(z) + 0.5)
        return str(out), bool(bad)
    except Exception as e:
        # ★★不许静默吞✗★★（★§79.52 的教训：★吞掉的是"我代码写错"就最糟✓★）
        return "★对准那一步炸了✗★（%s: %s）" % (type(e).__name__, e), True


def _idle_busy():
    """★"我忙不忙"✗★ —— ★归**上层**判（★下层 `mcp_gesture` 不认识 mutex／移动✓★）★

    ★三条算忙✗★：★① 有改世界动作在飞（★互斥被占✓★）
      ② **它在动**（★0.5 秒里挪了 > 0.05 格 ⇒ 走路中 ✗ 而移动中朝向归移动 ✗ §79.55✓★）
      ③ 读不到坐标 ⇒ ★也算忙 ✗ 宁可不动✗★ ✓
    """
    import time as _t
    try:
        import mcp_policy as _P
        st = _P.mutex_state()
        # ★★口径✗★★（2026-10-03 ✓ 世界里当场吃到）：★`mutex_state()` **空闲时也回一个 dict**✗
        #   （★`{'tool': None, 'since': 0.0}`✓★）⇒ ★我第一版见 dict 就当"占用"✗
        #   ⇒ ★于是**永远忙** ✗ 挂机小动作一次都做不了✗★ ✓
        #   ⇒ ★只有 `tool` 非空才算真占用✗★ ✓
        if st and st.get("tool"):
            return True, "有改世界动作在飞（%s）" % str(st.get("tool"))[:40]
    except Exception:
        pass
    a = _pos_now()
    _t.sleep(0.5)
    b = _pos_now()
    if not a or not b:
        return True, "读不到坐标（★宁可不动✓★）"
    d = ((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
    if d > 0.05:
        return True, "它在动（0.5 秒挪了 %.2f 格）" % d
    return False, "闲着"


def t_place_block(x, y, z, item):
    aim_txt, aim_bad = _aim_before_place(x, y, z)
    txt = dsh('dshplace %d %d %d "%s"' % (int(x), int(y), int(z), str(item)), 60.0)
    note = "★先看✗★ %s%s ｜ %s" % (
        "★没对上✗★" if aim_bad else "对上 ✓", "", txt or "（没有回执 ✗）")
    return cut(note), (not ok_of(txt, "dshplace"))


def t_move_relative(forward=0.0, right=0.0, timeout_ms=20000):
    """★相对位移✗★（前／右以**当前朝向**为准 ✓ 2026-10-02 补 ✓ 外部同题项目有、我们原来没有 ✓）

    ★做法✗★：★算出**绝对目标** ✗ 再走既有那条 `walk_route`✓★ ——
      ⇒ ★不用改模组 ✗ 也不用教它新动作 ✓（★P168：动手前先看**已有的路**能不能复用✓★）
    ★坐标约定（写在这儿 ✗ 免得下次再推一遍✓★）：
      MC 的 `yaw=0` ＝ 朝 **+Z** ✓ yaw 增大 ＝ 从上往下看**顺时针** ✓ ⇒
      ★前 ＝ `(-sin(yaw), +cos(yaw))` ✗ 右 ＝ `(+cos(yaw), +sin(yaw))`✓★
    ★回执里**把算出来的绝对目标也印出来**✗★（★"前 3 格"到底指哪 ✗ 当场可见 ✓ P152 ✓）
    """
    import math as _m
    p = _pos_now()
    if not p:
        return cut("读不到 Bot 坐标 ⇒ **没动** ✓"), True
    st = dsh("dshdigest 1", 40.0) or ""
    mm = re.search(r"yaw=(-?[\d.]+)", st)
    yaw = float(mm.group(1)) if mm else 0.0
    y = _m.radians(yaw)
    dx = -_m.sin(y) * float(forward) + _m.cos(y) * float(right)
    dz = _m.cos(y) * float(forward) + _m.sin(y) * float(right)
    tx, tz = int(round(p[0] + dx)), int(round(p[2] + dz))
    ty = int(p[1])
    if abs(dx) < 0.05 and abs(dz) < 0.05:
        return cut("前后左右都是 0 ⇒ **没动** ✓（要动就给 forward 或 right ✓）"), True
    out, bad = t_walk_route(tx, ty, tz, timeout_ms=timeout_ms)
    return cut("相对位移：从 (%.2f,%.2f,%.2f) 朝 yaw=%.1f ⇒ **前 %.1f 右 %.1f** "
               "＝ 绝对目标 (%d,%d,%d) ｜ %s" % (p[0], p[1], p[2], yaw, forward, right,
                                                tx, ty, tz, out)), bad


def t_jump(times=1):
    """★跳✗★（★走 **Carpet 自带**的 `/player … jump`✗ ✗ 不自己造✓★ 2026-10-02 ✓）

    ★为什么换路✗★：我先在模组里写了 `/dshjump`（硬塞 `setDeltaMovement`）✗ ⇒
      ★实测 y 一点没升 ✗ 而回执照旧报成功✗★（**P164/P172** 同族 ✓）；
      ★换成已有的路 ⇒ 干净前提（onground=true ＋ 整格 y ✓）下实测 **71.0 → 72.00**✗★ ✓
    ★判据（P172 ✓）✗★：★跳完**回读 y**✗★ ⇒ 升了 `verified=true` ✗ 没升**当场说没升** ✓
    """
    import time as _t
    p0 = _pos_now()
    y0 = p0[1] if p0 else None
    n = max(1, min(4, int(times or 1)))
    outs = []
    for _ in range(n):
        try:
            outs.append(str(ch().cmd("player %s jump" % BOT, timeout=30.0,
                                     allow_str=True).text() or "").strip()[:30])
        except Exception as e:
            outs.append("ERR:%s" % type(e).__name__)
        _t.sleep(0.7)
    peak = y0
    for _ in range(14):
        _t.sleep(0.06)
        p = _pos_now()
        if p and y0 is not None and p[1] > (peak or 0):
            peak = p[1]
    if y0 is None or peak is None:
        return cut("★跳✗★：读不到 y ⇒ ★没验成 ✗ verified=false✗★（%s）" % " ｜ ".join(outs)), True
    up = peak - y0
    return cut("★跳✗★ jumps=%d ⇒ y %.2f → %.2f（升 **%.2f** 格 ✓）｜ ★verified=%s✗★ ｜ %s"
               % (n, y0, peak, up, "true" if up > 0.3 else "false", " ｜ ".join(outs))), (up <= 0.3)


def t_look_at(yaw=None, pitch=None, x=None, y=None, z=None):
    """★主动设朝向✗★（★用原生 `tp … ~ ~ ~ yaw pitch`✗ ✗ 不写模组 ✓ 2026-10-02 ✓）

    ★为什么重要✗★：这是"★**我去看看**✗★"那条玩家行为的前提（★信息不够就转头/走过去✗★）
    ★判据（P172 ✓）✗★：★发完**回读** `dshdigest` 的 yaw/pitch✗★ ⇒ 对上 `verified=true` ✓
    ★也可以给坐标看向某点✗★（★角度算法与 `move_relative` 同一套约定 ✓★）
    """
    import math as _m
    import time as _t
    p = _pos_now()
    if p is None:
        return cut("读不到坐标 ⇒ **没转** ✓"), True
    if x is not None and y is not None and z is not None:
        dx, dy, dz = (x + 0.5) - p[0], (y + 0.5) - (p[1] + 1.62), (z + 0.5) - p[2]
        yaw = _m.degrees(_m.atan2(-dx, dz))
        pitch = _m.degrees(_m.atan2(-dy, _m.hypot(dx, dz)))
    if yaw is None or pitch is None:
        return cut("★要么给 yaw/pitch ✗ 要么给 x/y/z✗★（两个都不给 ⇒ 没转 ✓）"), True
    try:
        ch().cmd("tp %s ~ ~ ~ %.1f %.1f" % (BOT, float(yaw), float(pitch)), timeout=30.0,
                 allow_str=True)
    except Exception as e:
        return cut("★tp 失败 ✗ %s⇒ verified=false✗★" % type(e).__name__), True
    _t.sleep(0.4)
    st = dsh("dshdigest 1", 40.0) or ""
    m = re.search(r"yaw=(-?[\d.]+) pitch=(-?[\d.]+)", st)
    if not m:
        return cut("★tp 发了 ✗ 但读不回 yaw/pitch ⇒ verified=false✗★"), True
    got = (float(m.group(1)), float(m.group(2)))
    want_y = ((float(yaw) + 180.0) % 360.0) - 180.0
    dphi = abs(((got[0] - want_y + 180.0) % 360.0) - 180.0)
    okv = dphi < 15.0 and abs(got[1] - float(pitch)) < 10.0
    return cut("★设朝向✗★ want=(%.1f,%.1f) ⇒ 回读=(%.1f,%.1f)（差 %.1f/%.1f）｜ ★verified=%s✗★"
               % (want_y, float(pitch), got[0], got[1], dphi, abs(got[1] - float(pitch)),
                  "true" if okv else "false")), (not okv)
def t_drop_item(times=1):
    """★把手上的东西丢出去✗★（★2026-10-03 改走 **模组侧 `/dshthrow`**✗ ✗ 不再用 Carpet 的 `drop`✓★）

    ★为什么换✗★（欠账 ⑪ ✓ 实测 ✓）：★Carpet 的 `/player Bot drop` ⇒ 背包 86⇒85 ✓
      而 **3 格内掉落实体 ＝ fail** ✗ 走回去也**没捡回来**✗★ ⇒ ★"地上没有"＝这条语言的地基是空的✗★
    ★模组侧 `/dshthrow`✗★：★`held.shrink(1)` ＋ `Player#drop(one,false,true)`✗★
      ⇒ ★2026-10-03 实测✗★：★`thrown=1 item=cobblestone` ✗ 背包 80⇒79 ✗
      **且** `@e[type=item,distance=..3]` ＝ **pass**✗★ ✓ ⇒ ★地基有了✗★
    ★判据仍在框架那边✗★：★回读背包件数 ✗ 少了对不上就**判红**✗★ ✓
    """
    import time as _t
    n = max(1, int(times or 1))
    outs = []
    for _ in range(n):
        try:
            outs.append(str(dsh("dshthrow 1", 40.0) or "").strip()[:60])
        except Exception as e:
            outs.append("ERR:%s" % type(e).__name__)
        _t.sleep(0.5)
    return cut("★丢物品✗★ times=%d（★走模组 `/dshthrow` ✗ 真的会在地上生成✓★）｜ %s"
               % (n, " ｜ ".join(outs))), False


def t_action_status():
    """★动作句柄：一次调用看**现在在干什么**✗★（2026-10-02 ✓ 抄他们 `action_id/status` 的形状 ✓）

    ★为什么要有它✗★：外部同题项目的**长动作**都能查状态 ✗ 而我们只有走路的 `walk_progress` ✗
      ＋ 任务级 `job_*` ✗ ⇒ ★这里把它们 ＋ 策略/互斥状态**合成一个回执**✗★（★一次往返 ✓ P97 ✓★）
    """
    import mcp_policy as _P
    parts = []
    for key, label in (("walk_progress", "walk"), ("job_list", "jobs")):
        try:
            out, _bad = BY_NAME[key]["fn"]({})
            parts.append("%s: %s" % (label, str(out).replace("\n", " | ")[:240]))
        except Exception as e:
            parts.append("%s: ★ERR %s✗★" % (label, type(e).__name__))
    st = _P.load()
    parts.append("★互斥✗★=%s ｜ policy=%s grant=%s"
                 % (_P.mutex_state().get("tool") or "空",
                    "on" if st["enabled"] else "off（机制没开 ✓）",
                    "+".join(sorted(st.get("grant") or [])) or "（空）"))
    return cut("★动作状态✗★ " + " ｜ ".join(parts)), False


def t_cancel():
    """★取消当前动作✗★：停走路输入 ＋ ★释放改世界互斥✗★ ＋ **如实报它停了什么** ✓"""
    import mcp_policy as _P
    out = []
    try:
        r, _bad = BY_NAME["stop"]["fn"]({})
        out.append("stop ⇒ " + str(r).replace("\n", " | ")[:200])
    except Exception as e:
        out.append("★stop 失败 ✗ %s✗★" % type(e).__name__)
    st = _P.mutex_state()
    if st.get("tool"):
        _P.release_mutating(st["tool"])
        out.append("★释放了改世界互斥✗★（原持有 %s ✓）" % st["tool"])
    else:
        out.append("改世界互斥当时是空的 ✓")
    return cut("★取消✗★ " + " ｜ ".join(out)), False


def t_use_block(x, y, z, face="up", aimy=0.5):
    txt = dsh("dshuse %d %d %d %s %.2f" % (int(x), int(y), int(z), str(face), float(aimy)), 60.0)
    return cut(txt or "（没有回执 ✗）"), (not ok_of(txt, "dshuse"))


def t_equip(item):
    txt = dsh('dshequip "%s"' % str(item), 60.0)
    return cut(txt or "（没有回执 ✗）"), (not ok_of(txt, "dshequip"))


def t_say(text):
    txt = dsh("dshsay %s" % esc(str(text)), 60.0)
    return cut(txt or "（没有回执 ✗）"), (not ok_of(txt, "dshsay"))


# ── 整条作业（复用 `agent/jobs.py` 的老实现 ✓ 不重写 ✗）──────────────────────
def t_harvest(x0, y0, z0, x1, y1, z1):
    from jobs import harvest_and_replant
    box = {"x0": int(x0), "y0": int(y0), "z0": int(z0), "x1": int(x1), "y1": int(y1), "z1": int(z1)}
    try:
        res = harvest_and_replant(ch(), box, bot=BOT, verbose=False)
    except Exception as e:
        return ("收成作业**抛异常** ✗：%s: %s" % (type(e).__name__, e)), True
    if isinstance(res, dict):
        txt = ("收成作业：%s ｜ 收 %s 株 ｜ 补种 %s ｜ 成熟 %s ｜ 原因：%s"
               % ("成功 ✓" if res.get("ok") else "**失败** ✗", res.get("harvested"),
                  res.get("planted"), res.get("ripe"), res.get("why") or "none"))
        return cut(txt), (not res.get("ok"))
    return cut(str(res)), False


def t_sift(x, y, z, uses=8, item="minecraft:gravel"):
    from jobs import sift_job
    try:
        res = sift_job(ch(), int(x), int(y), int(z), uses=int(uses), bot=BOT,
                       item=item, verbose=False)
    except Exception as e:
        return ("筛矿作业**抛异常** ✗：%s: %s" % (type(e).__name__, e)), True
    txt = ("筛矿作业：%s ｜ 筛了 %s 下 ｜ 在 (%s,%s,%s) ｜ 原因：%s"
           % ("成功 ✓" if res.get("ok") else "**失败** ✗", res.get("uses"), x, y, z,
              res.get("why") or "none"))
    return cut(txt), (not res.get("ok"))

# ── ★容器的手★（长任务要"整理/存放/产线"就必须有它 ✗）──────────────────────────
# （★v2.19✗★：容器/背包那一族搬去了 `tools/mcp_percept.py` ✓）


# ── ★地图读取★ ──────────────────────────────────────────────────────────────
# （★v2.19✗★：地图读取本身（`map_area`/`find_block`/`survey`）搬去了 `tools/mcp_percept.py` ✓；它依赖的量测辅助（`_verify_band`/`_fill_names` 等）在 `tools/mcp_geo.py` ✓）


# ★★"特定方块查找器"的别名表★★ ✓（用户点的方向 ✓ 2026-09-23 ✓）
#   用户的原话 ✓：「标记特定方块的位置… 写一个特定方块查找器，需要的时候去那个位置就行了」
#   ⇒ 设计 ✓：**不登记所有方块** ✗ 只把"值得跑一趟"的几种登记成**别名** ✓
#     需要的时候 `find_block(match="筛子")` 就去找 ✓ 找到坐标再去 ✓（不用把整张图塞满 ✗）

# ── ★规划 ＋ 分跳走 ＋ 每跳验真值 ＋ 偏了重规划★ ──────────────────────────────
# （★v2.19✗★：规划＋分跳走＋路线视图整块搬去了 `tools/mcp_walk.py` ✓）




# ★"贴着边的那一跳"跳距上限★ ✗（2026-09-29 第 26 轮 ✓）：8 → **4**
#   一跳到 8 格 ⇒ 模组跑到一半被挡/绕一下 ⇒ 它自己再找路 ⇒ **冲刺余地大** ✗
#   贴边时最怕的就是"冲过头"✗（那一次掉虚空就是这么掉的 ✓）⇒ 压到 4 ✓ 走慢点 ✓


def t_remember(text):
    """★记进长期记忆★ ✓（每轮都会注入 ✓ 跨重启 ✓）—— 写 `memory/bot.md` ✓ 去重 ✓"""
    mem = ROOT / "memory" / "bot.md"
    t = str(text or "").strip()
    if not t:
        return cut("空话不记 ✓"), True
    old = mem.read_text(encoding="utf-8") if mem.is_file() else ""
    if t in old:
        return cut("这条已经在记忆里了 ✓（没重复写 ✓ 纪律：会每轮注入的东西不许重复 ✗）"), False
    mem.parent.mkdir(parents=True, exist_ok=True)
    with mem.open("a", encoding="utf-8", newline="\n") as f:
        f.write("- " + t + "\n")
    return cut("记住了 ✓（memory/bot.md 现在 %d 行 ✓ 以后每轮都会看到 ✓）"
               % len(mem.read_text(encoding="utf-8").splitlines())), False


# ── ★长任务账本★（落盘 ✓ 跨会话/重启 ✓）────────────────────────────────────────






# ── 工具表（说明**逐字**照抄自坏前的字节码 ✓ 见文件头 ✓）──────────────────────


def t_nav3d(x, y, z, max_steps=12, dry=False, restore=True, pause=1.8):
    """★3D 长距离导航（§79.389）✗★：★`plan3d` 规划 ⇒ `exec3d` 执行✗★

    ★和 `walk_to` 的区别✗★：★`walk_to` 只 ≤8 格 ✗ 且走的是**模组自己的** A\*✗★ ⇒
      ★这个走**我们 Python 侧的 3D A\***（★知道"能过但要交互"／"能挖"／"能垫脚"／危险代价✗★）✗★ ✓
    ★回执✗★：★`arrived=` ✗ `steps=` ✗ `actions=` ✗ `cost=` ✗ `end=`✗★ ✓
    """
    try:
        import exec3d as E
    except Exception as e:                       # ★不许静默✗★
        return "nav3d import 失败：%r" % (e,)
    ok, rep = E.execute((x, y, z), dry=bool(dry), max_steps=int(max_steps),
                        restore=bool(restore), pause=float(pause))
    return ("nav3d arrived=%s dry=%s steps=%s cost=%s actions=%s end=%s"
            % (rep.get("arrived"), bool(dry), rep.get("steps"),
               round(rep["cost"], 1) if rep.get("cost") else None,
               rep.get("actions"), rep.get("end")))


TOOLS = [
    dict(name="bot_state", description="看 Bot 自己的实况：坐标/朝向/血/饱食/模式/手持/背包格数/附近实体/地上掉落物/准星命中。做任何决定前先看它。",
         inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
         fn=lambda a: t_bot_state()),
    dict(name="bot_inventory", description="看 Bot 背包的逐格明细（槽位:物品x数量）。",
         inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
         fn=lambda a: t_bot_inventory()),
    dict(name="bot_events", description="读增量事件流：受伤/吃掉东西/背包增减/模式变化/被瞬移/地上掉落物（含快消失的）。传 since 只拿新的。",
         inputSchema={"type": "object", "properties": {"since": {"type": "integer", "description": "上次回执里的 cursor，省略=最近一段"}}, "additionalProperties": False},
         fn=lambda a: t_bot_events(a.get("since"))),
    dict(name="walk_to", description="★短距离（≤8 格）让 Bot 自己走过去★（不瞬移，服务器逐 tick 推进）。到达/没到都会如实回报（edge=前面是虚空 / blocked=被挡 / timeout）。★超过 8 格会被**拒绝**★ ✗ —— 空岛上单发长走会贴着平台边绕、**实测掉过两次虚空** ✗ ⇒ 远距离请用 `walk_route`（全局规划＋拆跳＋每跳验真实位置＋拒绝跨虚空 ✓）。",
         inputSchema={"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
                                                       "timeout_ms": {"type": "integer", "description": "预算，默认 20000"},
                                                       "exact": {"type": "boolean", "description": "true=必须精确到那一格"},
                                                       "force": {"type": "boolean", "description": "true=明知超 8 格也强行发（危险 ✗ 只在你自己盯着时用）"}},
                       "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_walk_to(a["x"], a["y"], a["z"], a.get("timeout_ms", 20000),
                                bool(a.get("exact")), bool(a.get("force")))),
               dict(name="nav3d", description="★3D 长距离导航（无距离上限）★：Python 侧 3D A* 规划（知道能过但要交互/能挖/能垫脚/危险代价）⇒ 逐跳执行并验位。dry=true 只规划不动手；restore=true 会把挖/垫的方块还原。回执：arrived=/steps=/cost=/actions=/end=。",
                inputSchema={"type": "object", "properties": {
                    "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
                    "max_steps": {"type": "integer", "description": "最多走几跳，默认 12"},
                    "dry": {"type": "boolean", "description": "true=只规划不执行"},
                    "restore": {"type": "boolean", "description": "true=把改动还原（默认 true）"},
                    "pause": {"type": "number", "description": "每跳后等几秒，默认 1.8"}},
                    "required": ["x", "y", "z"], "additionalProperties": False},
                fn=lambda a: t_nav3d(a["x"], a["y"], a["z"], a.get("max_steps", 12),
                                     bool(a.get("dry")), bool(a.get("restore", True)),
                                     float(a.get("pause", 1.8)))),
           dict(name="goto_route", description="★路点表导航（无距离上限）★：一次给一串路点，模组在 tick 里**连续走**（比 walk_to 逐格快约 6 倍，实测 41 路点 9.3 秒）。route 写 x,y,z;x,y,z;… 或 [[x,y,z],…]。回执：arrived=/cells=/seconds=/end=。",
                inputSchema={"type": "object", "properties": {
                    "route": {"type": "string", "description": "路点表：x,y,z;x,y,z;…"},
                    "timeout_ms": {"type": "integer", "description": "预算，默认 60000"}},
                    "required": ["route"], "additionalProperties": False},
                fn=lambda a: t_goto_route(a["route"], a.get("timeout_ms", 60000))),
dict(name="move_relative", description="★相对位移★：以**当前朝向**为准往前走/往右走若干格（前正后负、右正左负）；回执会印出换算后的绝对目标。",
         inputSchema={"type": "object", "properties": {"forward": {"type": "number", "description": "前（正）后（负）几格"},
                                                       "right": {"type": "number", "description": "右（正）左（负）几格"},
                                                       "timeout_ms": {"type": "integer"}},
                       "required": ["forward", "right"], "additionalProperties": False},
         fn=lambda a: t_move_relative(a.get("forward", 0.0), a.get("right", 0.0),
                                      a.get("timeout_ms", 20000))),
    dict(name="jump", description="★跳★：走 Carpet 自带的 /player Bot jump，并**回读 y** 报 verified（升了才算成功；没升就当场说没升）。",
         inputSchema={"type": "object", "properties": {"times": {"type": "integer", "description": "跳几次，最多 4"}},
                       "additionalProperties": False},
         fn=lambda a: t_jump(a.get("times", 1))),
    dict(name="look_at", description="★主动设朝向★（原生 tp）：给 yaw/pitch，或给 x/y/z 自动算角；发完回读 dshdigest 报 verified。",
         inputSchema={"type": "object", "properties": {"yaw": {"type": "number"}, "pitch": {"type": "number"},
                                                       "x": {"type": "integer"}, "y": {"type": "integer"},
                                                       "z": {"type": "integer"}},
                       "additionalProperties": False},
         fn=lambda a: t_look_at(a.get("yaw"), a.get("pitch"), a.get("x"), a.get("y"), a.get("z"))),
    dict(name="drop_item", description="★丢物品★：走 Carpet 的 /player Bot drop，把**手上**的东西丢出去；框架会回读背包件数，少了对不上就判红（★「地上看不看得见」仍欠账 ⑪★）。",
         inputSchema={"type": "object", "properties": {"times": {"type": "integer", "description": "丢几次，默认 1"}},
                       "additionalProperties": False},
         fn=lambda a: t_drop_item(a.get("times", 1))),
    dict(name="gesture", description="★动作即语言·点头/摇头★：点头＝「是」、摇头＝「不是」；每一步都回读 yaw/pitch，对不上就报 verified=false。",
         inputSchema={"type": "object", "properties": {"kind": {"type": "string", "description": "nod（点头／是）或 shake（摇头／不是）"},
                                                       "times": {"type": "integer", "description": "来几遍，默认 1"}},
                       "additionalProperties": False},
         fn=lambda a: t_gesture(a.get("kind", "nod"), a.get("times", 1))),
    dict(name="idle_beat", description="★挂机小动作★：闲着时轻看一眼别处再转回原处（幅度有上限、必须回到原位、有冷却；忙或在走路时【不做】并说明原因）。",
         inputSchema={"type": "object", "properties": {"amplitude": {"type": "number", "description": "幅度（度），默认 20，上限 45"},
                                                       "hold": {"type": "number", "description": "看一眼停多久（秒），默认 1.2"}},
                       "additionalProperties": False},
         fn=lambda a: t_idle_beat(float(a.get("amplitude", 20.0)), float(a.get("hold", 1.2)),
                                  busy=_idle_busy)),
    dict(name="follow_gaze", description="★跟着你的视线看★：读**玩家自己**的 yaw/pitch（世界真值）⇒ 假人朝同一方向看 ⇒ 回读自证（读不到就明写 unavailable，不猜 0,0）。",
         inputSchema={"type": "object", "properties": {"player": {"type": "string", "description": "看谁，默认 Au_Sn"},
                                                       "tol": {"type": "number", "description": "容差（度），默认 6"}},
                       "additionalProperties": False},
         fn=lambda a: t_follow_gaze(a.get("player", "Au_Sn"), float(a.get("tol", 6.0)))),
    dict(name="point_at", description="★动作即语言·指路★：看向某个点（给 x/y/z）或某个方向（给 yaw），可以顺带说一句；回读姿态报 verified。",
         inputSchema={"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
                                                       "z": {"type": "integer"}, "yaw": {"type": "number"},
                                                       "pitch": {"type": "number"},
                                                       "text": {"type": "string", "description": "要说的那一句（可选）"}},
                       "additionalProperties": False},
         fn=lambda a: t_point_at(a.get("x"), a.get("y"), a.get("z"), a.get("yaw"),
                                 a.get("pitch"), a.get("text"))),
    dict(name="lead_to", description="★动作即语言·带路回头★：走到目标，然后回头看玩家（回读 yaw/pitch 报 verified；读不到玩家坐标会明写 unavailable）。",
         inputSchema={"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
                                                       "z": {"type": "integer"},
                                                       "look_back": {"type": "boolean", "description": "到了要不要回头看玩家，默认 true"},
                                                       "timeout_ms": {"type": "integer"}},
                       "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_lead_to(a["x"], a["y"], a["z"], a.get("look_back", True),
                                a.get("timeout_ms", 60000))),
    dict(name="move_slot", description="★槽位移动★：把背包 from 槽的东西挪到 to 槽（0..40）；动手前后各读一次背包，to 槽没变成那件东西就判红。",
         inputSchema={"type": "object", "properties": {"from_slot": {"type": "integer"},
                                                       "to_slot": {"type": "integer"},
                                                       "count": {"type": "integer", "description": "搬几件，不填＝全搬"}},
                       "required": ["from_slot", "to_slot"], "additionalProperties": False},
         fn=lambda a: t_move_slot(a["from_slot"], a["to_slot"], a.get("count"))),
    dict(name="action_status", description="★动作句柄★：一次调用看现在在干什么（走路进度 ＋ 未结账任务 ＋ 改世界互斥 ＋ 策略状态）。",
         inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
         fn=lambda a: t_action_status()),
    dict(name="cancel", description="★取消★：停掉走路输入并**释放改世界互斥**，并如实报它到底停了什么。",
         inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
         fn=lambda a: t_cancel()),
    dict(name="come_to", description="走到某个玩家身边（先问服务器要他的真实坐标，读不到就**不动**）。",
         inputSchema={"type": "object", "properties": {"player": {"type": "string", "description": "玩家名，默认 Au_Sn"},
                                                       "timeout_ms": {"type": "integer"}}, "additionalProperties": False},
         fn=lambda a: t_come_to(a.get("player") or PLAYER, a.get("timeout_ms", 20000))),
    dict(name="look", description="看准星射线打到什么：方块/实体、哪个面、距离、**够不够得着**（真人 4.5 格）。动手前先问它。",
         inputSchema={"type": "object", "properties": {"reach": {"type": "number", "description": "触及距离，默认 4.5"}}, "additionalProperties": False},
         fn=lambda a: t_look(a.get("reach", 4.5))),
    dict(name="dig_block", description="挖掉指定坐标的方块（自动挑工具；走的是老桥的 dig_at）。",
         inputSchema={"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}},
                       "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_dig_block(a["x"], a["y"], a["z"])),
    dict(name="place_block", description="把手上的/背包里的方块放到指定坐标（模组会做触及距离检查，够不着会说**为什么**）。",
         inputSchema={"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
                                                       "item": {"type": "string", "description": "如 minecraft:cobblestone"}},
                       "required": ["x", "y", "z", "item"], "additionalProperties": False},
         fn=lambda a: t_place_block(a["x"], a["y"], a["z"], a["item"])),
    dict(name="use_block", description="对着某个方块的某个面右键（拉杆/按钮/门/播种/筛矿都走这条）。face 可为 up/down/north/south/east/west。",
         inputSchema={"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
                                                       "face": {"type": "string"}, "aimy": {"type": "number"}},
                       "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_use_block(a["x"], a["y"], a["z"], a.get("face", "up"), a.get("aimy", 0.5))),
    dict(name="equip", description="把手持物换成指定物品（会自动找背包里的；找不到会明说）。",
         inputSchema={"type": "object", "properties": {"item": {"type": "string"}}, "required": ["item"], "additionalProperties": False},
         fn=lambda a: t_equip(a["item"])),
    dict(name="scan", description="扫描一个长方体区域里的方块（原生、毫秒级），可按方块名筛。",
         inputSchema={"type": "object", "properties": {"x0": {"type": "integer"}, "y0": {"type": "integer"}, "z0": {"type": "integer"},
                                                       "x1": {"type": "integer"}, "y1": {"type": "integer"}, "z1": {"type": "integer"},
                                                       "match": {"type": "string", "description": "方块名，如 wheat"},
                                                       "max": {"type": "integer"}},
                       "required": ["x0", "y0", "z0", "x1", "y1", "z1"], "additionalProperties": False},
         fn=lambda a: t_scan(a["x0"], a["y0"], a["z0"], a["x1"], a["y1"], a["z1"], a.get("match"), a.get("max", 48))),
    dict(name="harvest_crop", description="★整条作业★：把一片田收干净并补种（先过背包守卫=放不下就不开工；只收成熟的；逐株走过去；最后用世界真值自证）。",
         inputSchema={"type": "object", "properties": {"x0": {"type": "integer"}, "y0": {"type": "integer"}, "z0": {"type": "integer"},
                                                       "x1": {"type": "integer"}, "y1": {"type": "integer"}, "z1": {"type": "integer"}},
                       "required": ["x0", "y0", "z0", "x1", "y1", "z1"], "additionalProperties": False},
         fn=lambda a: t_harvest(a["x0"], a["y0"], a["z0"], a["x1"], a["y1"], a["z1"])),
    dict(name="sift", description="★整条作业★：走到筛子前、确认网和原料都在、一下一下筛、并用筛子的 NBT 判成功（打的是上面那个面）。",
         inputSchema={"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
                                                       "uses": {"type": "integer", "description": "筛几下，默认 8"},
                                                       "item": {"type": "string", "description": "原料，默认 minecraft:gravel"}},
                       "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_sift(a["x"], a["y"], a["z"], a.get("uses", 8), a.get("item", "minecraft:gravel"))),
    dict(name="say", description="在游戏聊天里说一句短话（用来先说一句再去干活）。★收尾那句话不要用这个★ —— 你最后的回答会自动被说出来。",
         inputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
         fn=lambda a: t_say(a["text"])),
    dict(name="stop", description="立刻停下正在走的动作。",
         inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
         fn=lambda a: t_stop()),
    dict(name="freeze", description="★★冻结／解冻：让「世界在我手里不动」★★ ✗（做**会改变世界**的事之前先冻结 ✓ 之后解冻 ✓）。★为什么要它★ ✗：读两次读数之间假人会**自己溜达** ⇒ 前后对不上 ⇒ 会误判成「丢东西」✗。`on=true` 冻结（关自行走动 ✓ 并**记下原值**✓）／`on=false` 解冻（**原样还回去**✓ 原来开着就还它开着 ✓）；**幂等** ✓。⚠ 它只关自行走动 ✗ 管不了别的玩家／别的活 ✓。",
          inputSchema={"type": "object", "properties": {
              "on": {"type": "boolean", "description": "true=冻结 ✓ false=解冻并还原 ✓"}},
              "required": ["on"], "additionalProperties": False},
          fn=lambda a: t_freeze(bool(a.get("on")))),
    dict(name="idle", description="打开/关掉 Bot 的**自行走动**（拟人化：原地溜达、看四周、自言自语）。别人要跟它说话时关掉更稳。",
         inputSchema={"type": "object", "properties": {"on": {"type": "boolean"}}, "required": ["on"], "additionalProperties": False},
         fn=lambda a: t_idle(bool(a.get("on")))),
    dict(name="go_to_drop", description="★去捡掉落物★：找到最近的（可指定物品名的）掉落物并走过去捡，用世界真值自证（背包数涨了 或 那个掉落物消失）。★捡东西一律用它★ —— 不要为了够到掉落物去挖旁边的方块 ✗（除非你确认那是唯一办法，并说清理由）。",
         inputSchema={"type": "object", "properties": {
             "item": {"type": "string", "description": "只要这种物品（子串匹配），省略=任意最近的一个"},
             "radius": {"type": "integer", "description": "搜索半径，默认 16"},
             "timeout_ms": {"type": "integer", "description": "走路预算，默认 20000"}},
             "additionalProperties": False},
         fn=lambda a: t_go_to_drop(a.get("item"), a.get("radius", 16), a.get("timeout_ms", 20000))),
    dict(name="job_open", description="★开一件长活★：把目标记到账本上（落盘 ✓ 换会话/重启都不丢 ✓）。凡是**不止一步**的事（挖一批矿、筛一箱沙砾、盖点东西）都先开一件，再一步步做。",
         inputSchema={"type": "object", "properties": {
             "goal": {"type": "string", "description": "要做成什么，一句话"},
             "next_step": {"type": "string", "description": "你打算先做哪一步"}},
             "required": ["goal"], "additionalProperties": False},
         fn=lambda a: t_job_open(a["goal"], a.get("next_step", ""))),
    dict(name="job_plan", description="★给一件活写「步骤清单」★ ✗：一行一步，行内用 ｜ 或 | 分开「做什么 ｜ 怎么算做成了」。★为什么要它★ ✗：账本原来只有一句自由文本的下一步 ⇒ 多步的活（取料 ⇒ 加工 ⇒ 送回去）跨会话就不知道自己做到第几步 ✗。写完用 `job_next` 看下一步 ✓ 做完用 `job_step` 带 `plan_i` 和**世界真值证据**标上 ✓。",
          inputSchema={"type": "object", "properties": {
              "job_id": {"type": "string"},
              "steps": {"type": "string", "description": "一行一步，如：去箱子取 8 个沙砾｜背包 gravel >= 8"}},
              "required": ["job_id", "steps"], "additionalProperties": False},
          fn=lambda a: t_job_plan(a["job_id"], a["steps"])),
    dict(name="job_next", description="★★这件活的下一步是哪一步★★ ✗：按**计划顺序**给出第一个**还没做成**的步骤 ＋ 全程进度 ＋ 每步的判据与证据。★做了的不再催 ✓（免得反复干同一件）★。还没写过计划 ⇒ 它会告诉你先 `job_plan` ✓。",
          inputSchema={"type": "object", "properties": {"job_id": {"type": "string"}},
                       "required": ["job_id"], "additionalProperties": False},
          fn=lambda a: t_job_next(a["job_id"])),
    dict(name="job_list", description="看账本：还有哪些活没做完、每件做到哪一步了。★每轮开始时先看它★ —— 别把上次没做完的活忘了。",
         inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
         fn=lambda a: t_job_list()),
    dict(name="job_step", description="★记一步★：这步做完了/做成什么样，写一句，并写下**下一步**。证据那一栏尽量填**世界真值**（工具回执原文/背包数变化/坐标）。★下一步要等一会儿才做的话填 wait_s（秒）★ —— 中继会照着等到时候再叫你，别自己空转。",
         inputSchema={"type": "object", "properties": {
             "job_id": {"type": "string"},
             "note": {"type": "string", "description": "这一步做了什么、成了没有"},
             "next_step": {"type": "string", "description": "下一步做什么"},
             "evidence": {"type": "string", "description": "客观证据（回执/数字/坐标）"},
             "wait_s": {"type": "integer", "description": "这一步之后要等多少秒再来做（等麦子熟/等出料）；不需要等就不填"},
             "plan_i": {"type": "integer", "description": "★顺便把「计划」里的第 i 步标成做成了★ ✗（i 从 1 起 ✓）；★标完成必须同时给 evidence（世界真值）✗ 没证据会被拒 ✓"}},
             "required": ["job_id", "note"], "additionalProperties": False},
         fn=lambda a: t_job_step(a["job_id"], a["note"], a.get("next_step", ""),
                                 a.get("evidence", ""), a.get("wait_s", 0),
                                 a.get("plan_i", 0))),
    dict(name="job_close", description="收尾一件活。status=done（做成了）/failed（做不成，说清为什么）/dropped（不做了）。★不许不写结果就关★ ✗",
         inputSchema={"type": "object", "properties": {
             "job_id": {"type": "string"},
             "result": {"type": "string", "description": "最终结果，一句话"},
             "status": {"type": "string", "enum": ["done", "failed", "dropped"]}},
             "required": ["job_id", "result"], "additionalProperties": False},
         fn=lambda a: t_job_close(a["job_id"], a["result"], a.get("status", "done"))),
    dict(name="chest_peek", description="看一眼容器（箱子/桶…）里有什么。★会自己先走过去★（够不着模组会拒绝）。",
         inputSchema={"type": "object", "properties": {
             "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}},
             "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_chest_peek(a["x"], a["y"], a["z"])),
    dict(name="chest_put", description="把背包里的东西**放进**容器（会先走过去；动完报背包数量前后差 ✓ 一个没少会明确提醒你 ✗）。整理/存放/产线都用它。",
         inputSchema={"type": "object", "properties": {
             "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
             "item": {"type": "string", "description": "如 minecraft:wheat_seeds"},
             "count": {"type": "integer", "description": "放几个，默认 1"}},
             "required": ["x", "y", "z", "item"], "additionalProperties": False},
         fn=lambda a: t_chest_put(a["x"], a["y"], a["z"], a["item"], a.get("count", 1))),
    dict(name="chest_take", description="从容器里**取出**东西（会先走过去；动完报背包数量前后差 ✓ 一个没多会明确提醒你 ✗）。",
         inputSchema={"type": "object", "properties": {
             "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
             "item": {"type": "string"},
             "count": {"type": "integer", "description": "取几个，默认 1"}},
             "required": ["x", "y", "z", "item"], "additionalProperties": False},
         fn=lambda a: t_chest_take(a["x"], a["y"], a["z"], a["item"], a.get("count", 1))),
    dict(name="chest_put_many", description="★★批量存放：走一趟，办多件★★ ✗（比一件一件 `chest_put` 省掉 N-1 趟路 ✓）。`items` 写法：`\"minecraft:dirt:64,wheat:16\"` ✓（不写数量 ⇒ 1 ✓）。★它会**动手前后各读一次容器与背包**做**逐件对账**★ ✓ ⇒ 每件都告诉你 移动了几个 ✓ 对不对得上 ✓；**对不上绝不报成功** ✗；背包本来不够 ⇒ 它会把「最多只能搬这么多」写出来 ✓。★返回里有「没到数」的就是真没到位 ✗ 要重试就把那几件再来一次 ✓★。",
          inputSchema={"type": "object", "properties": {
              "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
              "items": {"type": "string", "description": "要存的东西，如 \"dirt:64,wheat:16\"（名称可用子串 ✓）"}},
              "required": ["x", "y", "z", "items"], "additionalProperties": False},
          fn=lambda a: t_chest_put_many(a["x"], a["y"], a["z"], a["items"])),
    dict(name="chest_take_many", description="★★批量取出：走一趟，办多件★★ ✗（用法与 `chest_put_many` 一样 ✓ 方向相反 ✓）。★动手前后各读一次容器与背包 ⇒ 逐件对账★ ✓ **对不上绝不报成功** ✗。★一次取多种时它按你给的名字**子串**匹配 ✓（`dirt` 会匹配 `minecraft:dirt` ✓）★。",
          inputSchema={"type": "object", "properties": {
              "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
              "items": {"type": "string", "description": "要取的东西，如 \"dirt:64,wheat:16\""}},
              "required": ["x", "y", "z", "items"], "additionalProperties": False},
          fn=lambda a: t_chest_take_many(a["x"], a["y"], a["z"], a["items"])),
    dict(name="map_area", description="★看一眼周围的地图★（俯视图＋高度图 ✓）：每格画它地表是什么（G=草 D=土 #=石 W=木 c=庄稼 M=机器 ~=水 .=不知道），@ 是你。★做任何「往哪走/在哪盖」的决定前先看它★。第一次要几十秒 ✓ 之后有缓存很快 ✓。",
         inputSchema={"type": "object", "properties": {
             "radius": {"type": "integer", "description": "半径，默认 10，最大 32"},
              "verify": {"type": "string", "description": "auto（默认 ✓ 图上高度是推的才实地扫 ✓）/ on（一定扫 ✓）/ off（不扫 ✓ 最省 ✓）"},
             "below": {"type": "integer", "description": "画「这一层下方」的地表（默认你脚下一层＋1）★别填错：填了 74 你会看到树冠不是地面★"},
             "max_age": {"type": "integer", "description": "缓存多少秒内算新鲜，默认 180"}},
             "additionalProperties": False},
         fn=lambda a: t_map_area(a.get("radius", 10), a.get("below"), a.get("max_age", 180),
                                  a.get("verify", "auto"))),
    dict(name="find_block", description="★找最近的某种方块★（返回坐标＋距离 ✓ 按距离排序）。`match` 是**子串**：chest ✓ wheat ✓ water ✓。★找不到就说找不到★（只算已加载区块）。",
         inputSchema={"type": "object", "properties": {
             "match": {"type": "string", "description": "方块名的一部分，如 chest"},
             "radius": {"type": "integer", "description": "半径，默认 24，最大 64"},
             "max": {"type": "integer", "description": "最多列几个，默认 6"}},
             "required": ["match"], "additionalProperties": False},
         fn=lambda a: t_find_block(a["match"], a.get("radius", 24), a.get("max", 6))),
    dict(name="plan_route", description="★先看路线再走★：在地图上做全局 A*，告诉你它打算经过哪几个点（**不动手** ✓）。目标站不住它会自动改走旁边最近的落脚点 ✓ 并说明。规划不成会**说清原因**（目标未知/真的不通/超出范围）✗ 不编路 ✗。",
         inputSchema={"type": "object", "properties": {
             "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
             "verify": {"type": "string", "description": "auto（默认 ✓ 图上高度是推的才实地扫 ✓）/ on（一定扫 ✓）/ off（不扫 ✓ 最省 ✓）"}},
             "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_plan_route(a["x"], a["y"], a["z"], a.get("verify", "auto"))),
    dict(name="route_view", description="★「这条路上挡着什么」★：把规划出的路**画成图** ＋ 列出★道中障碍★。图里 `*`=路线格且走得通 ✓ `X`=★路线格但走不通★ ✗ `#`=挡死(要绕/要挖) ✓ `+`=矮半砖(能自动上) ✓ `~`=液体 ✓ `^`=要抬一格 ✓ `v`=要降下去 ✓ `.`=没地板(坑) ✗ `?`=★未知（**没看到 ≠ 没有**）★。★`verify=auto`（默认 ✓）：老模组的图**高度是推的**✗ ⇒ 它会用 `dshscan` **一次调用把这条走廊的地面实地扫回来** ✓ 就地改正图（并回写缓存 ✓ 后面的规划也吃到真值 ✓）✦ 新模组 v2.16 自带真高度 ✓ ⇒ 自动跳过 ✓ 不浪费调用 ✓★。★逐格标出处★（实地扫过 ✓ / 图上推的 ✗）。",
          inputSchema={"type": "object", "properties": {
              "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
              "margin": {"type": "integer", "description": "路两侧多画几列，默认 1 ⇒ 能看见紧邻的挡路方块 ✓"},
              "max_cells": {"type": "integer", "description": "图的最大格数，默认 1200；超了★不画半张★ ✗ 只给障碍清单 ✓"},
              "verify": {"type": "string", "description": "auto（默认 ✓ 图上高度是推的才实地扫 ✓）/ on（一定扫 ✓ 双保险 ✓）/ off（不扫 ✓ 最省 ✓）"}},
              "required": ["x", "y", "z"], "additionalProperties": False},
          fn=lambda a: t_route_view(a["x"], a["y"], a["z"],
                                    a.get("margin", 1), a.get("max_cells", 1200),
                                    a.get("verify", "auto"))),
    dict(name="walk_route", description="★走过去（比 walk_to 稳 ★）：先全局规划 ⇒ 拆成几条腿 ⇒ 一条一条走 ⇒ ★每条腿都用 dshdigest 验一次真实位置★ ⇒ 被挡了就从新位置重规划。远目标、绕障、跨高差用它 ✓。★它会拒绝去「和你不在同一块平台上的地方」★（空岛中间隔着虚空 ⇒ 走过去会掉下去 ✗）。",
         inputSchema={"type": "object", "properties": {
             "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
             "timeout_ms": {"type": "integer", "description": "每一跳/每条腿的走路预算，默认 25000"},
             "max_replan": {"type": "integer", "description": "最多重规划几次，默认 2"},
             "chunk": {"type": "integer", "description": "一跳最多走多少格，默认 8（**上限 8** —— 一跳超过 8 格就重新落回「单发长走」那个掉虚空的坑 ✗）"},
             "sweep": {"type": "integer", "description": "★走之前探几格找障碍★ 默认 4（每格约 0.6 秒 ⇒ 约 3.5 秒 ✗ 这是「识别道中障碍」的价格 ✓）；路熟/赶时间填 0 跳过 ✓"},
             "verify": {"type": "string", "description": "auto（默认 ✓ 图上高度是推的才实地扫 ✓）/ on（一定扫 ✓）/ off（不扫 ✓ 最省 ✓）"}},
             "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_walk_route(a["x"], a["y"], a["z"],
                                   a.get("timeout_ms", 25000), a.get("max_replan", 2),
                                   min(int(a.get("chunk") or 8), 8), a.get("sweep", 4),
                                    a.get("verify", "auto"))),
    dict(name="check_path", description="★走之前先探路★：先规划 ✓ 再把**这条路上的格子实地探一遍** ✓ ⇒ 报告**道中的障碍物**（哪个方块、在哪一格 ✓）。★地图是按方块种类建的、稀有方块可能不在图上★ ✗ ⇒ 所以「图上没障碍」不等于「道上没障碍」 ✓ ⇒ 要去一个新地方、或上次半路被挡，先问它 ✓（它**不动手** ✓ 还会告诉你「绕开之后通不通」✓）。",
         inputSchema={"type": "object", "properties": {
             "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
             "budget": {"type": "integer", "description": "最多独立探几格，默认 12（每格约 0.6 秒；★别调太大 —— 通道是一台电脑一次只吃一条，堆多了会超时 ✗）"},
             "verify": {"type": "string", "description": "auto（默认 ✓ 图上高度是推的才实地扫 ✓）/ on（一定扫 ✓）/ off（不扫 ✓ 最省 ✓）"}},
             "required": ["x", "y", "z"], "additionalProperties": False},
         fn=lambda a: t_check_path(a["x"], a["y"], a["z"], a.get("budget", 24),
                                    a.get("verify", "auto"))),
    dict(name="whereami", description="★★现状速览：一次调用说完「我现在什么样」★★ ✗（大脑每轮开工前的那一圈问题 ✓）。给你：坐标／维度／血／饱食／模式 ✓ 背包**几种几件、还剩几格** ✓ 手上拿着什么 ✓ 周围 24 格内**实体数／★敌对数★／最近那个是什么、多远** ✓ 地上掉落物数 ✓ 脚下平台**连通多大** ✓ **离最近的边几格**（★贴边 ≤2 格会明确警告 ✗★）✓ ｜ ★代价：1 条指令 ＋ 至多 1 次建图（0 ＝ 用的缓存 ✓）★。★要动手之前先问它；要挑落脚点再问 `safe_spots`／要挑路问 `plan_route`★ ✓。",
          inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
          fn=lambda a: t_whereami()),
    dict(name="walk_progress", description="★★上一次走「走到哪了」★★ ✗（★调用超时之后就用它★ ✗）：给你**最后一次落地的实测位置** ✓ 目标 ✓ 走到第几步 ✓ **多久以前**（新鲜度 ✓ —— 陈旧的不许当成「正在走」✗）＋ **现在人又在哪**（这一次独立读的 ✓）＋ 离目标还剩几格 ✓。★`walk_route` 是阻塞的、长走要几分钟 ⇒ 超时后别整段重来，先问它★ ✓。",
          inputSchema={"type": "object", "properties": {
              "fresh_s": {"type": "integer", "description": "多少秒内算「还在走」，默认 90"}},
              "additionalProperties": False},
          fn=lambda a: t_walk_progress(a.get("fresh_s", 90))),
    dict(name="platform", description="★★我脚下这块平台：多大、**边在哪**、我离边多近★★ ✗（★掉虚空都是从踩边开始的★ ✗ —— 2026-09-23 真掉过一次，丢了钻石／钻石斧／漏斗／煤／铁／锤子／麦子 ✓）。给你：连通格数 ✓ 内陆格数 ✓ **边有多少格** ✓ **最近那个边格在哪个方向、离你几格** ✓ —— ★离边 ≤2 格时它会**明确警告**★ ✓。★用它判「我现在站的地方安不安全、该往哪边走」★ ✓（挑落脚点用 `safe_spots` ✓ 看地形用 `map_area` ✓）。",
          inputSchema={"type": "object", "properties": {
              "radius": {"type": "integer", "description": "预留（现在按连通平台算 ✓ 不按半径截断 ✓）"}},
              "additionalProperties": False},
          fn=lambda a: t_platform(a.get("radius", 20))),
    dict(name="safe_spots", description="★列出「可以放心去」的落脚点★（在你脚下这块连通平台里 ✓ 且离边至少一格 ✓ 带距离 ✓）。想找地方站/盖/放东西时先问它 ✓ —— 别自己挑平台边上的格子（一脚踩空就掉虚空 ✗ 2026-09-23 真掉过一次 ✗）。",
         inputSchema={"type": "object", "properties": {
             "dmin": {"type": "integer", "description": "最近多少格，默认 4"},
             "dmax": {"type": "integer", "description": "最远多少格，默认 16"},
             "max": {"type": "integer", "description": "最多列几个，默认 12"}},
             "additionalProperties": False},
         fn=lambda a: t_safe_spots(a.get("dmin", 4), a.get("dmax", 16), a.get("max", 12))),
    dict(name="survey", description="★落点勘察★：一张图 ＋ 这一片**有什么**（水/机器/庄稼/箱子 各给最近坐标 ＋ 地上掉落物数 ＋ 能安全去的落脚点）。★想找活干、想找地方放东西、想看看周围有什么资源，先问它★。",
         inputSchema={"type": "object", "properties": {
             "radius": {"type": "integer", "description": "半径，默认 14，最大 32（走 /dshmap ⇒ 一次调用就够 ✓）"},
              "verify": {"type": "string", "description": "auto（默认 ✓ 图上高度是推的才实测扫回来改正 ✓）/ on（一定扫 ✓）/ off（不扫 ✓ 最省 ✓）"}},
             "additionalProperties": False},
         fn=lambda a: t_survey(a.get("radius", 14), a.get("verify", "auto"))),
    dict(name="remember", description="★把一件事记进长期记忆★（写 `memory/bot.md` ✓ 以后**每轮都会看到** ✓ 跨重启 ✓）。值得记的：用户的偏好、你自己定下的决定、踩过的坑。★同一句只会记一次★（不重复 ✗）。",
         inputSchema={"type": "object", "properties": {
             "text": {"type": "string", "description": "要记的一句话（会原样存 ✓ 写清楚 ✓）"}},
             "required": ["text"], "additionalProperties": False},
         fn=lambda a: t_remember(a["text"])),
]
BY_NAME = {t["name"]: t for t in TOOLS}


# ── JSON-RPC（stdio ✓ 一行一条 JSON ✓ **不是** LSP 那种 Content-Length ✗）──────
def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def reply(mid, result) -> None:
    send({"jsonrpc": "2.0", "id": mid, "result": result})


def reply_err(mid, code, message) -> None:
    send({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})


def handle(msg: dict) -> None:
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        reply(mid, {"protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "mc-bridge", "version": "1.0.0"}})
        return
    if method in ("notifications/initialized", "initialized"):
        return
    if method == "tools/list":
        reply(mid, {"tools": [{"name": t["name"], "description": t["description"],
                               "inputSchema": t["inputSchema"]} for t in TOOLS]})
        return
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        t = BY_NAME.get(name)
        if t is None:
            reply_err(mid, -32601, "unknown tool: %s" % name)
            return
        # ★★接入策略（参考外部同题项目的**机制** ✗ 2026-10-02 ✓）★★
        #   ① ★动作边界硬闸✗★（治"从一些地方掉下去" ✓ 用户原话 ✓）
        #   ② ★分层授权✗★（不在表里 ⇒ 明确拒绝 ✓ 不静默忽略 ✓）
        #   ③ ★目的留痕✗★（策略要求时 ⇒ 感知类调用必须写 purpose ✓）
        import mcp_policy as _POL
        allowed, why = _POL.check(name, args)
        if not allowed:
            txt = "★拒绝✗★：%s" % why
            log({"tool": name, "args": str(args)[:300], "ok": False, "sec": 0.0,
                 "text": txt[:600], "audit": _POL.audit_line(name, args, False, 0.0)})
            reply(mid, {"content": [{"type": "text", "text": txt}], "isError": True})
            return
        if _POL.purpose_missing(name, args):
            txt = ("★拒绝✗★：capability_not_granted —— ★感知类调用必须写 `purpose`✗★"
                   "（策略文件要求了 ✓ ⇒ 请带上 purpose=「为什么看这一眼」 ✓）")
            log({"tool": name, "args": str(args)[:300], "ok": False, "sec": 0.0,
                 "text": txt[:600], "audit": _POL.audit_line(name, args, False, 0.0)})
            reply(mid, {"content": [{"type": "text", "text": txt}], "isError": True})
            return
        # ★限流（抄 dsh-mc-bridge 的形状 ✓）：★超限 ⇒ `rate_limited` ＋ retryAfterMs✗★
        r_ok, r_ms = _POL.rate_ok(name)
        if not r_ok:
            txt = ("★拒绝✗★：rate_limited —— ★%s 距上次调用太近✗★ ⇒ 请等 **%d ms** 再来 ✓"
                   % (name, r_ms))
            log({"tool": name, "args": str(args)[:300], "ok": False, "sec": 0.0,
                 "text": txt[:600], "audit": _POL.audit_line(name, args, False, 0.0)})
            reply(mid, {"content": [{"type": "text", "text": txt}], "isError": True})
            return
        # ★改世界动作**互斥**（抄他们的 `ActionScheduler` ✓）：★重入 ⇒ 明确拒 ✗ 不排队✓★
        got, holder = _POL.acquire_mutating(name)
        if not got:
            txt = ("★拒绝✗★：busy_action —— ★同一时刻只允许一个**改世界**动作✗★"
                   "（★现在 %s 占着锁 ✗ 要么等它完 ✗ 要么先 `cancel`✗★）" % holder)
            log({"tool": name, "args": str(args)[:300], "ok": False, "sec": 0.0,
                 "text": txt[:600], "audit": _POL.audit_line(name, args, False, 0.0)})
            reply(mid, {"content": [{"type": "text", "text": txt}], "isError": True})
            return
        t0 = time.time()
        # ★★P1-c：动作**之前**先取"动手前快照"✗★★（2026-10-02 ✓ 给"前后对比"那类读数用 ✓）
        _pre = None
        try:
            import mcp_verify as _VER0
            _pre = _VER0.pre(name, args)
        except Exception:
            _pre = None
        try:
            txt, bad = t["fn"](args)
            ok = not bad
        except Exception as e:
            txt, ok = ("工具**抛异常** ✗：%s: %s" % (type(e).__name__, e)), False
            errlog("tool %s crashed" % name, type(e).__name__, str(e))
        finally:
            _POL.release_mutating(name)
        # ★★统一回执包装（★欠账 ③ ✗ P164 家族的**系统解**✗★ 2026-10-02 ✓）★★
        #   ★口径✗★：★动作返回之后 ✗ **框架**再去读一次世界✗★ ——
        #   ★读数说"和工具声称的不一致" ⇒ **框架把这一次标红**✗★（★工具自己说成功也没用 ✓★）
        try:
            import mcp_verify as _VER
            _v = _VER.check(name, args, _pre)
            if _v is not None:
                _vok, _vnote = _v
                txt = ((txt or "") + "\n" + _vnote)
                if _vok is False:
                    ok = False
        except Exception as _e:
            txt = ((txt or "") + "\n★verified=error✗★（包装本身抛了 %s ✗ ★不静默✗★）"
                   % type(_e).__name__)
        log({"tool": name, "args": str(args)[:300], "ok": ok,
             "sec": round(time.time() - t0, 2), "text": (txt or "")[:600],
             "audit": _POL.audit_line(name, args, ok, time.time() - t0)})
        reply(mid, {"content": [{"type": "text", "text": txt or "(空回执 ✗)"}],
                    "isError": (not ok)})
        return
    if mid is not None:
        reply_err(mid, -32601, "unknown method: %s" % method)


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:                 # ★★§79.402✗★★ 坏 JSON ✗ 必须**回错误**✗
            #   ★不然后果✗★：★客户端发了一条坏行 ✗ **一直在等回执**✗
            #   ★按 JSON-RPC 标准回 `-32700 Parse error` ✗★ ✓
            errlog("mc_mcp 收到坏 JSON 行：%r" % (e,))
            reply_err(None, -32700, "Parse error: %s" % (e,))
            continue
        try:
            handle(msg)
        except Exception as e:
            errlog("handle crashed", type(e).__name__, str(e))
            if msg.get("id") is not None:
                reply_err(msg.get("id"), -32603, "internal error: %s" % type(e).__name__)
    return 0


if __name__ == "__main__":
    # ★★v2.19：stdio 的编码必须**钉死成 UTF-8**★★ ✗（2026-10-01 实测抓到的**真 bug** ✓）
    #
    # 现场 ✗：`tools/list` **整个失效** —— 回的是
    #   `{"id":2,"error":{"code":-32603,"message":"internal error: UnicodeEncodeError"}}` ✗
    # 真因 ✓：本机**控制台/管道的默认编码是 GBK** ✗（P39 ✓），而工具说明里
    #   有 `✓` `✗` `★` `｜` 这些 **GBK 里没有的字符** ✗ ⇒ `json.dumps(..., ensure_ascii=False)`
    #   一写 stdout 就抛 `UnicodeEncodeError` ✗ ⇒ 整个 `tools/list` 死掉 ✓
    # ★它为什么特别毒✗★：伪装成"**内部错误**"✗ ⇒ 接入者只会以为**自己接错了** ✗
    #   （★而这正是"接入契约"最不该有的失败形状✗★ ✓）
    # ⚠ 口径 ✓：★**只钉编码，一个字都不改工具名与说明**✗★（P91：那是大脑直接读的字 ✓）
    #   也**不用** `ensure_ascii=True` 绕 ✗ —— 那会把 JSON 变成一堆 `\uXXXX` ✓
    #   好读性没了 ✓ 而且**没治根**（stdin 那头的中文照样会被 GBK 解错 ✗）
    for _stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main())
