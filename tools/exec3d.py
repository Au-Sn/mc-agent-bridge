#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exec3d.py -- ★3D 计划**提交器** v3★（★执行交给模组 `dshdo`✗★）（§79.4xx）

★★v3 改了什么（★用户拍板：执行与感知都进模组 ✗ Python 只当大脑✗★）✗★★
  ★v2 在 Python 侧**自己执行**✗★：分段（`segment`）／分块（`CHUNK`）／失败折半（`walk_chunk`）／
    逐条发 `dshwalk`·`dshdig`·`dshplace`·`dshuse`／自己维护 `dug`·`placed` 记账／`setblock` 还原／
    `occupies_guard` 三格硬闸 ⇒ ★**全部退役**✗★ ✓
  ★为什么✗★：★Python 一条命令约 **0.6 秒**（★CC 轮询 500ms ＋ HTTP✗★）✗
    ⇒ ★"执行器"放在外面 ⇒ **每一步都可能对不上世界**✗★（★§79.405 头上放原石／§79.406 漏记账✗★）✗
    ⇒ ★**执行**必须在**同进程**里 ✗ 每 tick 用**实时**世界判 ✓ Python 只出**计划**✗★ ✓
  ★v3 只做三件事✗★：
    ① `plan3d` 规划 ⇒ `(path, acts)`
    ② `acts` 译成 `dshdo` **动作表**
    ③ 提交**一条** `dshdo` ⇒ 轮询事件流（`do_start`／`do_done`／`do_fail`）到结束 ⇒ 用模组回报的
       `log` 组装执行报告（★不再自己记账✗★）
  ★★模组侧语义（★照模组 v2.27.0 源码看准 ✗ 不是猜的✗★）✗★★
    · `/dshdo "<步骤1>;<步骤2>;…"`（★`StringArgumentType.string()` ⇒ 要引号✗★）
    · 步骤：`walk:x,y,z`（★要求**正好那一格** ✗ 不用 ±1✗★）／`dig:x,y,z`／
      `place:x,y,z:item`／`use:x,y,z:face`／`wait:n`
      ★⚠ 坑✗★：`place`／`use` 的参数是**冒号**分隔（★不是逗号✗★）——
        模组是 `rest.split(":")`，`arg = v[1]`；而 `xyz = v[0].split(",")` 必须**正好 3 段**✗
        ⇒ ★写成 `place:x,y,z,item`（★逗号✗★）会被判"坐标格式错"✗★ ✓
      ★⚠ 坑×2✗★：item 带 `minecraft:` 前缀会被 `split(":")` 截成 `"minecraft"` ✗
        而模组 `ensureHeld` 是**子串**匹配 ⇒ 会拿**任意**含 `minecraft` 的物品 ✗ ⇒
        ★所以这里传**短名**（如 `dirt` ✗ `grass_block`✓★）✗★ ✓
    · 每步上限 **240 tick（12 秒）**；`walk` 发之前**实时**验目标可站（或关着的门）；
      `place` 拒绝放在**脚／头／支撑**三格（★§79.407✗★）
    · 判成没成：★看**世界**✗ 不看命令回包★（dig⇒air ／ place⇒非空气 ／ walk⇒`blockPosition().equals`）
    · 结束事件：`do_done n=… at=… log=a|b|…` ／ 失败 `do_fail idx=… step=… why=…` ／
      命令失败 `do_cmd_err cmd=… rc=…` ／ 主动停 `do_stop idx=…`
    · 状态：`/dshdo status` ⇒ `dshdo status idx=i/N cur=kind@x,y,z ticks=T log=[a|b|…]`（无任务 ⇒ `idle`）
  ★★`--dry`✗★★：只打印**一条** `DSHDO <动作表>` ✗ 一个字都不动世界✗★ ✓
  ★★保留的语义✗★★：`--dry` ／ `--max` ／ 返回值 `(ok, rep)`（`arrived`·`steps`·`cost`·`actions`·`end`·`bad`）
  ★★保留但**已无作用**的参数✗★★：`restore` / `--no-restore` / `pause` —— 只为不破坏调用方
    （`mc_mcp.t_nav3d` 与 `house_nav_test` 传它们 ✓）；★还原语义退役 ✗ 模组侧不做还原✗★ ✓
"""
from __future__ import annotations

import argparse
import re
import sys
import time

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C            # noqa: E402
import plan3d as P3             # noqa: E402
import world3d as W3            # noqa: E402

MOVE_TAGS = ("walk", "diag", "step_up", "fall")
USE_FACE = "up"                  # ★门／活板门／栅栏门：任意面都能切换 ⇒ 用中性的「上」面✗★


# ── 世界只读：起点 ───────────────────────────────────────────────────────────
def bot_state():
    o = C.dsh("dshdigest", 20.0) or ""
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+).*?hp=([\d.]+).*?onground=(\w+)", o)
    return m.groups() if m else None


def bot_cell():
    b = bot_state()
    if not b:
        return None
    # ★★§79.431✗★★：★脚格走 `mcp_core.cell_of`**（★`ceil(y−ε)`✗★）
    #   ★旧写法 `int(float(y))` ＝ floor ⇒ ★站在 `dirt_path`／半砖上会读到**那方块自己**✗★
    #   ★⇒ ★**规划起点就错**（★整条路都错✗★）✗★ ✓
    import mcp_core as _MC
    return _MC.cell_of(b[0], b[1], b[2])


# ── ② acts ⇒ dshdo 动作表 ──────────────────────────────────────────────────
def _cell_of(act):
    """`dig@1,2,3` ⇒ (1,2,3)"""
    return tuple(int(v) for v in act.split("@")[1].split(","))


def pick_scaffold_item(items):
    """★从背包里挑一样能垫脚的方块 ✗ 返回**短名**（★模组 `ensureHeld` 按子串匹配✗★）✗★

    ★★§79.438（★task-8✗★）✗★★：★"★能不能垫／垫哪个★"这个**判断**已经收口到
      `plan3d.is_placeable`／`plan3d.pick_placeable`（★全仓唯一实现✗★）✗★
      ⇒ ★这里**只剩命令编码**：★去 `minecraft:` 前缀✗★ ✓
    ★为什么必须短名✗★：`dshdo` 的 place 参数按 `split(":")` 取 `v[1]` ⇒ 带 `minecraft:` 会被截成
      `minecraft` ✗ 再被**子串**匹配到任意物品 ⇒ ★放错方块✗★ ✓
    ★读不到背包（items None）⇒ 回 "" ✗ 不猜✗★ ✓
    """
    full = P3.pick_placeable(items)          # ★判断的唯一入口 ✗ 别在这里再写一遍 endswith✗★
    return full.lower().split(":", 1)[-1] if full else ""


class _OverlayWorld:
    """world + the blocks this trip has already placed (sec 79.471)

    A bridge place@(x, y-1, z) CREATES the support of the next walk target, so the
    standability check must overlay those cells or it would wrongly reject legal bridges.
    """

    def __init__(self, base, placed):
        self._b = base
        self._p = set(placed)

    def _over(self, x, y, z):
        return (x, y, z) in self._p

    def get(self, x, y, z):
        # sec 79.471: do NOT invent a block name here -- generic_rule_test forbids
        #   content-block literals in the planning layer, and that judge is right:
        #   the overlay only needs physics (h + pass_info), which are overridden below.
        return None if self._over(x, y, z) else self._b.get(x, y, z)

    def name(self, x, y, z):
        # sec 79.472: name() must be a STRING -- plan3d.forbidden() calls .lower() on it.
        #   "minecraft:air" is a structural name (allowed by generic_rule_test) and is the
        #   honest answer here: this overlays a just-placed block, whose exact identity we
        #   do not need -- only its physics (h + pass_info), which are overridden below.
        return "minecraft:air" if self._over(x, y, z) else self._b.name(x, y, z)

    def h(self, x, y, z):
        return 1.0 if self._over(x, y, z) else self._b.h(x, y, z)

    def support(self, x, y, z):
        return self.h(x, y - 1, z) > 0.05

    def passable(self, x, y, z):
        return (not self._over(x, y, z)) and self._b.passable(x, y, z)

    def pass_info(self, x, y, z):
        if self._over(x, y, z):
            return {"kind": "blocked", "subtype": "", "action": None, "why": "just placed"}
        return self._b.pass_info(x, y, z)


def validate_table(w, start, steps):
    """★动作表出口校验（§79.471／§79.473✗★）✗★ ⇒ `(walk_bad, place_bad)`**✗★

    ★为什么在**出口**校验✗★：★规划器允许产"★模组一定拒绝★"的步 ✗ 而模组一拒就**整任务死**✗★
      ★（★实测两种：`walk_target_not_standable@…` 与 `place_not_done@…`✗★）✗★
    ★两条口径✗★：
      · ★`walk` 目标**在执行到那一步时**必须 `stand_at` 通过（★叠上本趟之前放下的块✗★）✗★
      · ★`place` 目标必须**空** ＋ **至少一个面能点**（★模组 `dshplace` 要找 support✗★）✗★
        ＋ **在"★那一刻人站的位置★"的 4 格之内**（★读作：Chebyshev ≤ 4✗★）✗★
    ★返回空列表 ＝ 可以提交✗★ ✓
    """
    walk_bad = []
    place_bad = []
    dig_bad = []
    placed = set()
    pos = tuple(start) if isinstance(start, (list, tuple)) else None
    for s in steps:
        kind, _sep, rest = s.partition(":")
        if kind == "walk":
            try:
                pos = tuple(int(v) for v in rest.split(":")[0].split(","))
            except ValueError:
                walk_bad.append("walk_bad_cell@" + rest[:24])
                continue
            if not P3.stand_at(_OverlayWorld(w, placed), *pos)[0]:
                walk_bad.append("walk_target_not_standable@%d,%d,%d" % pos)
        elif kind == "dig":
            # ★★模块 I 施工许可（§79.490）✗★★：★挖之前必须问"★这里许不许挖★"✗★
            #   ★用户口径✗★：★"★申明哪些地方不能挖★"（★黑名单 ✗ 不是白名单限区✗★）✗
            try:
                c = tuple(int(v) for v in rest.split(":")[0].split(","))
            except ValueError:
                dig_bad.append("dig_bad_cell@" + rest[:24])
                continue
            try:
                import no_dig as _ND
                ok_zone, zone = _ND.allowed(c)
            except Exception as _exc:          # ★不许静默✗★
                print("  ★问施工许可失败：%r ⇒ **当禁止**（保守）✗★" % (_exc,))
                ok_zone, zone = False, {"name": "no_dig_broken"}
            if not ok_zone:
                dig_bad.append("no_dig_zone:%s@%d,%d,%d"
                               % ((zone or {}).get("name", "?"), c[0], c[1], c[2]))
        elif kind == "place":
            try:
                c = tuple(int(v) for v in rest.split(":")[0].split(","))
            except ValueError:
                place_bad.append("place_bad_cell@" + rest[:24])
                continue
            ow = _OverlayWorld(w, placed)
            if ow.h(*c) > 0.05:
                place_bad.append("place_target_occupied@%d,%d,%d" % c)
            elif not any(ow.h(c[0] + dx, c[1] + dy, c[2] + dz) > 0.05
                         for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                            (0, -1, 0), (0, 0, 1), (0, 0, -1))):
                place_bad.append("place_no_face@%d,%d,%d" % c)
            elif pos is not None and max(abs(c[0] - pos[0]),
                                        abs(c[1] - pos[1]),
                                        abs(c[2] - pos[2])) > 4:
                place_bad.append("place_out_of_reach@%d,%d,%d" % c)
            placed.add(c)
    return walk_bad, place_bad, dig_bad


def table_from_plan(path, acts, scaffold_item, max_steps=400):
    """★(path, acts) ⇒ dshdo 步骤表✗★ ⇒ `(steps, truncated, need_place, body_bad)`

    ★动作归属✗★（★照 `plan3d.changes()` 的 §79.391 口径✗★）：★动作是**下一跳的前提**✗
      ⇒ 执行到某个动作时，人还在 `path[i-1]` ✗ 目标格是 `path[i]`✗★ ✓
    ★`--max`✗★：★只放行**前 max_steps 次移动** ✗ 多的一律不进表✗★（★截断就如实标✗★）✓
    """
    steps = []
    i = 1
    moves = 0
    need_place = 0
    truncated = False
    body_bad = []
    for a in acts:
        if a.startswith("dig@"):
            q = _cell_of(a)
            steps.append("dig:%d,%d,%d" % q)
        elif a.startswith("place@"):
            q = _cell_of(a)
            need_place += 1
            # ★静态拦"往自己身上放"✗★：模组会 do_fail(place_on_body) 并**整个任务停掉** ✗
            #   ⇒ 与其提交一条注定失败的队列，不如**先拒绝**（★人不落地 ✗ 世界不动✗★）✓
            feet = path[i - 1] if i - 1 < len(path) else None
            if feet is not None and q in (feet, (feet[0], feet[1] + 1, feet[2]),
                                           (feet[0], feet[1] - 1, feet[2])):
                body_bad.append("place_on_body@%d,%d,%d" % q)
                continue
            steps.append("place:%d,%d,%d:%s" % (q[0], q[1], q[2], scaffold_item))
        elif a.startswith("open@"):
            q = _cell_of(a)
            # ★`use` 在模组里是**发射即算完成**✗（stepDone 默认 true）⇒ 开不开门不拦流程✗★
            #   后面那条 `walk` 的预检允许"关着的门" ✓ 模组自己的走路逻辑会开门 ✓
            steps.append("use:%d,%d,%d:%s" % (q[0], q[1], q[2], USE_FACE))
        else:
            if a not in MOVE_TAGS:
                # ★认不出的动作标签 ✗ 记下来不猜✗★
                body_bad.append("unknown_act=%s" % a)
                continue
            if i >= len(path):
                truncated = True
                break
            if moves >= max(1, int(max_steps)):
                truncated = True
                break
            nxt = path[i]
            steps.append("walk:%d,%d,%d" % (nxt[0], nxt[1], nxt[2]))
            i += 1
            moves += 1
    return steps, truncated, need_place, body_bad


def plan_str(steps):
    return ";".join(steps)


# ── ③ 提交 ＋ 轮询 ──────────────────────────────────────────────────────────
def _cursor():
    """★读事件游标✗★（★读不到回 None ✗ 不猜 0✗★）"""
    txt = C.dsh("dshevents", 20.0) or ""
    m = re.search(r"cursor=(\d+)", txt)
    return int(m.group(1)) if m else None


def _parse_events(txt):
    """`dshevents … | #29 do_start n=1 … | #30 do_done …` ⇒ [(seq, kind, rest)]

    ★★实测撞到的坑✗★★（★2026-10-27✗★）：模组的 `ok()` 回执**末尾会多一行返回码**（`"\\n1"`）✗
      ⇒ 若直接 `txt.split(" | ")` ✗ 最后一段会带 `"\\n1"` ⇒ `^…$` 的 `$` **匹配不上**（★`. ` 不吃换行✗★）
      ⇒ ★**每一批的最后一个事件被静默丢掉**✗★ —— 而 `do_done`／`do_fail` **恰好总是最后一条**✗
      ⇒ ★成功被报成 170 秒超时 ✗（★这就是"静默吞数据"在**我自己**手里又犯一次✗★）✓
    ★修法✗★：★先只取**第一行**（★把返回码行切掉✗★）再拆✗★ ✓
    """
    out = []
    if not txt:
        return out
    lines = txt.splitlines()
    first = lines[0] if lines else txt
    for part in first.split(" | ")[1:]:
        m = re.match(r"^#(\d+)\s+([a-z_]+)\s*(.*)$", part.strip())
        if m:
            out.append((int(m.group(1)), m.group(2), m.group(3).strip()))
    return out


def _terminal(events):
    """★从事件里认出"这条任务结束了吗"✗★ ⇒ `("done"|"fail"|"stop", payload)` 或 None

    ★★为什么单拎出来✗★★（★实测撞到✗★）：★超时那一秒 `do_done` **刚好到**✗
      ⇒ 只看循环里那次读数 ⇒ **把成功报成 wait_timeout** ✗（★2026-10-27 实测：3 步任务 53 秒✗★）
      ★⇒ 超时之后再**补读一次** ✗ 同一个判定函数✗★ ✓
    """
    fails = [r for (_s, k, r) in events if k == "do_fail"]
    if fails:
        return ("fail", fails[-1])
    dones = [r for (_s, k, r) in events if k == "do_done"]
    if dones:
        return ("done", dones[-1])
    stops = [r for (_s, k, r) in events if k == "do_stop"]
    if stops:
        return ("stop", stops[-1])
    return None


def _read_events(cursor, events, bad):
    """★把 `dshevents <cursor>` 的新事件追加进 `events` ✗ 返回新的 cursor✗★"""
    if cursor is None:
        return cursor
    txt = C.dsh("dshevents %d" % cursor, 20.0) or ""
    new = _parse_events(txt)
    if new:
        events.extend(new)
        cursor = max([cursor] + [s for (s, _k, _r) in new])
    for (_s, k, r) in events:
        if k == "do_cmd_err":
            item = "do_cmd_err:" + r[:60]
            if item not in bad:
                bad.append(item)
    return cursor


def _finish(kind, payload, events, bad, status, cursor):
    if kind == "fail":
        why = ""
        # ★`why=` 的值可以带空格/逗号（★`walk_target_not_standable@4119, 90, 11`✗★）
        #   ⇒ 抓到 ` at=` 或行尾为止 ✗ 别只抓第一个词✗★
        m = re.search(r"why=([^|]*?)(?:\s+at=|$)", payload)
        if m:
            why = m.group(1).strip()
        return {"done": True, "ok": False, "why": why or payload[:80],
                "log": "", "events": events, "status": status,
                "bad": bad + ["do_fail:" + payload[:80]], "cursor": cursor}
    if kind == "done":
        log = ""
        m = re.search(r"log=(.*)$", payload)
        if m:
            log = m.group(1).strip()
        at = None
        m2 = re.search(r"at=(-?\d+),\s*(-?\d+),\s*(-?\d+)", payload)
        if m2:
            at = (int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
        return {"done": True, "ok": True, "why": "", "log": log, "at": at,
                "events": events, "status": status, "bad": bad, "cursor": cursor}
    return {"done": True, "ok": False, "why": "do_stop:" + payload[:60],
            "log": "", "events": events, "status": status,
            "bad": bad + ["do_stop"], "cursor": cursor}


def wait_done(cursor, nsteps, timeout=None):
    """★等这条 dshdo 结束✗★ ⇒ dict（`done`／`ok`／`why`／`log`／`at`／`events`／`status`／`bad`／`cursor`）

    ★口径✗★：★只认**新事件**（`since=cursor`）✗ —— 不拿历史里的 `do_done` 冒充这一次★
    ★预算✗★：★每步按 **25 秒**给（★实测走路每跳 2~19 秒 ✗ 主要花在 `walk_pillar`✗★）✗ 再加 20 秒★
      （旧版 14 秒/步 ⇒ 实测 3 步任务在 **52 秒**卡线，`do_done` 刚好晚到 ✗ ⇒ 把成功报成超时✗★）
    ★兜底✗★：事件流读不到（cursor is None）⇒ 只看 `dshdo status`：
      ★见到 non-idle 之后又 idle ⇒ 当作结束 ✗ 但**如实标 `bad=no_event_stream`**（★判不出成败✗★）✓
    """
    if timeout is None:
        timeout = min(900.0, max(60.0, 25.0 * max(1, int(nsteps)) + 20.0))
    t0 = time.time()
    events, bad = [], []
    last_status = ""
    seen_running = False
    polls = 0
    while time.time() - t0 < timeout:
        cursor = _read_events(cursor, events, bad)
        term = _terminal(events)
        if term:
            return _finish(term[0], term[1], events, bad, last_status, cursor)
        # ★命令通道坏了（dshwalk 记不上）⇒ 别干等 12 秒×N ✗ 直接停✗★
        if len([b for b in bad if b.startswith("do_cmd_err")]) >= 3:
            C.dsh("dshdo stop", 20.0)
            return {"done": True, "ok": False, "why": "too_many_do_cmd_err",
                    "log": "", "events": events, "status": last_status,
                    "bad": bad, "cursor": cursor}
        # ★状态：每 ~4 次取一次（★给 rep 留 log／也在事件读不到时当兜底✗★）
        polls += 1
        if polls % 4 == 1 or cursor is None:
            last_status = (C.dsh("dshdo status", 20.0) or "").splitlines()[0]
            if "idle" not in last_status:
                seen_running = True
            elif seen_running:
                # ★任务已经不在队列里 ⇒ 事件应该已经落了 ⇒ **补读一次**再判✗★
                cursor = _read_events(cursor, events, bad)
                term = _terminal(events)
                if term:
                    return _finish(term[0], term[1], events, bad, last_status, cursor)
                if cursor is None:
                    return {"done": True, "ok": False, "why": "idle_without_events",
                            "log": "", "events": events, "status": last_status,
                            "bad": bad + ["no_event_stream"], "cursor": cursor}
        time.sleep(0.5)
    # ★★超时之后补最后一读✗★★（★`do_done` 常常就在这一秒到 ✗ 不能把它判成失败✗★）
    cursor = _read_events(cursor, events, bad)
    term = _terminal(events)
    if term:
        return _finish(term[0], term[1], events, bad, last_status, cursor)
    return {"done": False, "ok": False, "why": "timeout(%.0fs)" % (time.time() - t0),
            "log": "", "events": events, "status": last_status,
            "bad": bad + ["wait_timeout"], "cursor": cursor}


# ── 主流程 ──────────────────────────────────────────────────────────────────
MAX_ATTEMPTS = 3        # ★★§79.421✗★ 首发 ＋ 2 次重试✗★


def execute(goal, dry=False, max_steps=400, restore=False, pause=0.0):
    """★规划 → 提交 `dshdo` → 失败**用实时位置重规划**再试（★最多 3 次✗★）✗★

    ★为什么✗★：★`dshdo` 会**如实** `do_fail`（★某步过不去✗★）✗
      ★而一次性提交 ⇒ **一步失败就整趟报废** ⇒ 真实任务**卡在小障碍**上✗★ ✓
    ★口径✗★：★每次都**重新读 `bot_cell()`**（★不是拿旧起点✗★）✗
      ★`rep["attempts"]` 如实记录 ✗ **不许把失败掩饰成成功**✗★ ✓
    ★`dry` 不重试✗★（★没动手 ✗ 重试没意义✗★）✗★ ✓
    """
    attempts = []
    last = (False, {"reason": "never_ran"})
    # sec 79.474: attempts must differ. Same start + same model + same A* = same plan,
    #   so a second identical try only repeats the failure.
    REFUSALS = ("walk_unreachable", "place_unperformable", "place_on_body")
    for k in range(MAX_ATTEMPTS):
        allow_sc = (k == 0)          # try 1: normal routes; try 2+: no scaffolding
        ok, rep = _execute_once(goal, dry=dry, max_steps=max_steps,
                                restore=restore, pause=pause,
                                allow_scaffold=allow_sc)
        attempts.append({"try": k + 1, "ok": bool(ok),
                         "allow_scaffold": allow_sc,
                         "reason": rep.get("reason"),
                         "arrived": rep.get("arrived"),
                         "end": rep.get("end"),
                         "bad": rep.get("bad")})
        last = (ok, rep)
        if ok or dry:
            break
        if rep.get("reason") in REFUSALS and not allow_sc:
            # both strategies refused at the exit -> a third try would be identical input
            print("  ★两种策略都被出口拦下（★%s✗★）⇒ **不再重试**"
                  "（★同样的输入只会给同样的计划✗★）" % (rep.get("reason"),))
            break
        if k + 1 < MAX_ATTEMPTS:
            print("  ★第 %d 次没成（★%s✗★）⇒ 换策略＋实时位置重规划再试✗★"
                  % (k + 1, rep.get("reason") or rep.get("bad")))
            time.sleep(1.0)
    ok, rep = last
    rep["attempts"] = attempts
    if len(attempts) > 1:
        print("  ★共尝试 %d 次 ✗ 结果=%s✗★" % (len(attempts), "成" if ok else "没成"))
    return ok, rep


def _execute_once(goal, dry=False, max_steps=400, restore=False, pause=0.0,
                   allow_scaffold=True):
    """★规划 ⇒ 出动作表 ⇒ （非 dry）提交一条 dshdo ⇒ 等结束 ⇒ 组装报告✗★

    ★`restore`／`pause` 已退役✗★：只为兼容旧调用方（`mc_mcp.t_nav3d`／`house_nav_test`）★
    """
    del restore, pause                    # ★显式声明：这两个参数不再有用（★不是被我忘了✗★）
    goal = tuple(int(v) for v in goal)
    start = bot_cell()
    if not start:
        return False, {"reason": "no_pos"}
    lo = (min(start[0], goal[0]) - 6, min(start[1], goal[1]) - 8, min(start[2], goal[2]) - 6)
    hi = (max(start[0], goal[0]) + 6, max(start[1], goal[1]) + 8, max(start[2], goal[2]) + 6)
    w = W3.World3D()
    w.fetch_region((lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]))
            # sec 79.472: freeze() was tried here and REVERTED -- it turns every
            #   cell outside the fetched box into a wall and forces a longer detour
            #   (33 steps / arrived=True became 46 steps / place_not_done). The hang
            #   on a dead link is fixed by the fetch_fail breaker alone.
    items = P3.inv_items()
    # sec 79.474: a second strategy that DIFFERS -- no scaffold-based transitions.
    scaffold = P3.placeable_count(items) if allow_scaffold else 0
    scaffold_item = pick_scaffold_item(items)
    path, acts, cost = P3.plan(w, start, goal, scaffold=scaffold)
    rep = {"start": start, "goal": goal, "cost": cost, "steps": len(path or []),
           "actions": P3.summarize(acts or {}) if acts else {}, "dry": dry,
           "partial": len(w.partial), "restore": "retired"}
    print("  起点 %s ⇒ 目标 %s" % (start, goal))
    print("  模型 %s ｜ partial=%d ｜ 垫脚方块 %s（★样✗★ %r）"
          % (w.stats(), len(w.partial), scaffold, scaffold_item))
    if not path:
        rep["reason"] = "no_plan"
        print("  ★规划不出路 ✗ 如实报✗★")
        return False, rep
    steps, truncated, need_place, body_bad = table_from_plan(
        path, acts, scaffold_item, max_steps=max_steps)
    # ★已经在目标格 ⇒ **不用提交** ✗ 直接成功✗★（★旧版靠"最后再量一次位置"也会判到✓★）
    if not steps and tuple(start) == goal:
        rep.update({"arrived": True, "end": start, "reason": "already_there",
                    "bad": [], "table": [], "plan_str": "", "moves": 0})
        print("  ★已经在目标格 ✗ 不用提交 dshdo ✗★")
        if dry:
            print("DSHDO ")
        return True, rep
    rep.update({"need_place": need_place, "table": steps, "plan_str": plan_str(steps),
                "truncated": truncated, "moves": sum(1 for s in steps if s.startswith("walk:"))})
    print("  ★计划✗★：%d 步 ✗ 代价 %.1f ✗ %s" % (len(path), cost, rep["actions"]))
    print("  ★动作表✗★：%d 条 dshdo 步骤（★走 %d 步 ✗ 要垫 %d 格✗★）%s"
          % (len(steps), rep["moves"], need_place,
             "（★被 --max 截断✗★）" if truncated else ""))
    walk_bad, place_bad, dig_bad = validate_table(w, start, steps)

    # sec 79.471: a walk target the mod cannot stand on kills the whole task
    if walk_bad:
        print("  ★★拒提交✗★：动作表里有**站不住的 walk 目标**（模组会当场 do_fail）"
              "⇒ %s" % (walk_bad[:6],))
        rep["reason"] = "walk_unreachable"
        rep["bad"] = list(walk_bad)
        return False, rep

    # ★★模块 I（§79.490）✗★★：★命中不可挖区 ⇒ **不许提交**✗★
    if dig_bad:
        print("  ★★拒提交✗★：动作表里有**不可挖区域里的挖**（模块 I）⇒ %s"
              % (dig_bad[:6],))
        rep["reason"] = "no_dig_zone"
        rep["bad"] = list(dig_bad)
        return False, rep

    # sec 79.473: same for a place the mod cannot perform
    if place_bad:
        print("  ★★拒提交✗★：动作表里有**模组做不到的 place**（会 do_fail place_not_done）"
              "⇒ %s" % (place_bad[:6],))
        rep["reason"] = "place_unperformable"
        rep["bad"] = list(place_bad)
        return False, rep
    if truncated:
        rep["reason"] = "max_steps"
        print("  ★--max %s：表只到第 %d 次移动 ✗ 目标多半到不了（★如实标✗★）"
              % (max_steps, rep["moves"]))
    if dry:
        print("  ★--dry：只打印 ✗ 不动世界✗★")
        print("DSHDO " + rep["plan_str"])
        return True, rep
    if need_place > (scaffold or 0):
        print("  ★★材料不够✗★：计划要铺 **%d** 格 ✗ 背包只有 **%s** ✗ ⇒ **提前报 ✗ 不硬跑**✗★"
              % (need_place, scaffold))
        rep["reason"] = "not_enough_scaffold"
        return False, rep
    if not steps:
        rep["reason"] = "empty_table"
        return False, rep
    # ★★提交前先看有没有别人的 dshdo 在跑✗★★：`doStart` 是 `DOS.put` ⇒ **会静默顶掉**别人那条 ✗
    st0 = (C.dsh("dshdo status", 20.0) or "").splitlines()
    st0 = st0[0] if st0 else ""
    if "idle" not in st0:
        print("  ★★拒提交✗★：假人身上**已经有一条 dshdo 在跑**（★%s✗★）⇒ 提交会把它顶掉 ✗"
              "（★等它完 ✗ 或先 `dshdo stop`✗★）" % st0[:120])
        rep["reason"] = "busy"
        rep["bad"] = ["busy:" + st0[:80]]
        return False, rep
    # ── 提交前先拿游标（★只认提交之后的新事件✗★）─────────────────────────────
    cur = _cursor()
    if cur is None:
        print("  ★警告✗★：事件游标读不到 ⇒ 之后只能用 `dshdo status` 兜底（★成败判不准✗★）")
    t0 = time.time()
    r = C.dsh('dshdo "%s"' % rep["plan_str"], 40.0) or ""
    head = r.splitlines()[0] if r else ""
    ok_start = head.startswith("dshdo start")
    rep["submit"] = head
    print("  ★提交✗★：%s ⇒ %r（%.2f 秒）"
          % ("✓" if ok_start else "★✗", head[:160], time.time() - t0))
    if not ok_start:
        rep["reason"] = "submit_refused"
        rep["bad"] = ["submit_refused:" + head[:80]]
        rep["end"] = bot_cell()
        rep["arrived"] = False
        return False, rep
    res = wait_done(cur, len(steps))
    rep["do"] = {"ok": res["ok"], "why": res["why"], "log": res["log"],
                 "at": list(res.get("at") or []),
                 "events": ["#%d %s %s" % (s, k, rr) for (s, k, rr) in res["events"]],
                 "status": res["status"], "cursor": res["cursor"]}
    rep["bad"] = list(res["bad"])
    # ★★到达判定用**模组报的 `at=`**✗★★（★那是它自检 `blockPosition().equals` 通过那一刻的位置✗★）
    #   ★不用事后 `bot_cell()`✗★ —— 实测撞到：★do_done 之后**别人的 dshdo** 立刻把人挪走了✗★
    #   （★事件流里看到 `do_start n=6 from=…` ✗ 而我这边读到了已被挪走的格✗★）✓
    # ★★到达判定用 `mcp_core.arrived_at`（★§79.438 ✗ task-8 ✗ 全仓唯一实现✗★）✗★★
    #   ★语义没变✗★：★传进来的是**整数格子**（★模组 `at=` 权威 ✗ 或 `cell_of` 兜底✗★）
    #     ⇒ ★`floor/round` 恒等于原值 ⇒ 与旧写法 `tuple(end) == goal` **逐字等价**✗★ ✓
    if res.get("at"):
        rep["end"] = res["at"]
    else:
        rep["end"] = bot_cell()
    rep["arrived"] = C.arrived_at(rep["end"], goal)
    if res["ok"] and not rep["arrived"]:
        rep["bad"].append("goal_mismatch:at=%s" % (rep["end"],))
    ok = bool(res["ok"]) and rep["arrived"] and not rep["bad"]
    if not res["ok"]:
        rep["reason"] = rep.get("reason") or "do_fail"
    print("  ★结束✗★：%s ｜ why=%s ｜ %.1f 秒"
          % ("✓ do_done" if res["ok"] else "★没成✗", res["why"] or "无", time.time() - t0))
    print("     模组日志：%s" % (res["log"] or "（没有）"))
    if res["status"]:
        print("     最后状态：%s" % res["status"][:200])
    print("  最终 %s ｜ 目标 %s ｜ ★到达=%s ｜ 问题=%s"
          % (rep["end"], goal, rep["arrived"], rep["bad"] or "无"))
    return ok, rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("x", type=int)
    ap.add_argument("y", type=int)
    ap.add_argument("z", type=int)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--max", type=int, default=40)
    # ★退役参数：只为兼容旧写法（★传了不报错 ✗ 但不起作用✗★）
    ap.add_argument("--no-restore", action="store_true")
    ap.add_argument("--pause", type=float, default=0.0)
    ns = ap.parse_args()
    ok, rep = execute((ns.x, ns.y, ns.z), dry=ns.dry, max_steps=ns.max,
                      restore=not ns.no_restore, pause=ns.pause)
    print("EXEC3D ok=%d arrived=%s steps=%s dry=%d bad=%s"
          % (1 if ok else 0, rep.get("arrived"), rep.get("steps"), 1 if ns.dry else 0,
             rep.get("bad")))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
