#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_percept.py —— ★看：观察 ＋ 地图读取 ＋ 容器/背包的手★（v2.19 **第三刀** ✓）

搬过来的（逐字 ✓）：
  · 观察：`t_bot_state` / `t_bot_inventory` / `t_bot_events` / `walk_why` / `t_look` / `t_scan`
  · 地图与查询：`t_map_area` / `t_find_block` / `t_survey` / `t_whereami` /
    `t_check_path` / `t_safe_spots` ＋ `_parse_digest`
  · 容器/背包：`_box` / `_box_many` / `_box_peek_map` / `_reconcile` / `_resolve_item` /
    `_collide_set` / `_parse_items` / `_inv_ids` / `_inv_count` ＋ 四个 `chest_*` 工具

★依赖方向✗★：`mc_mcp` ⇒ `mcp_walk` ⇒ `mcp_percept` ⇒ `mcp_geo` ⇒ `mcp_core`（单向 ✓ 无环 ✓）
  —— 所以 `walk_why`（读事件流 ✓）在这一层 ✓ 而 `t_walk_route`（要用它 ✓）在 `mcp_walk` ✓

⚠ `walk_why` 里的 `t_bot_events` 指向**本模块** ✓（不是 `mc_mcp` 那个名字 ✓ 那边会 import 回来 ✓）
⚠ `_LIVE.<名>`：让打进 `mc_mcp` 的桩打得中（见 `mcp_core._LIVE` ✓）

★★纪律：一个字都没改✗★★（只有 `_LIVE.` 那一处故意的 ✓）
"""

from __future__ import annotations

import re, time

from mcp_core import (
    BLOCKED,
    BLOCKED_LV,
    _LIVE,
    _MISSION,
    cut,
    dsh,          # ★2026-10-03 补✗★：槽位移动要直接问模组 ✓（★原来没导入 ✗ 一写就 NameError✓★）
    errlog,
    ok_of,
)
from mcp_geo import (
    _boundary_cells,
    _fill_names,
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
)


PRESETS = {
    "筛子": "sieve", "筛网": "mesh", "农场": "farmland", "田": "farmland",
    "庄稼": "wheat", "麦子": "wheat", "箱": "chest", "箱子": "chest",
    "桶": "barrel", "熔炉": "furnace", "机器": "machine", "坩锅": "crucible",
    "水": "water", "岩浆": "lava", "矿石": "ore", "树": "log", "原木": "log",
    "工作台": "crafting_table", "铁砧": "anvil", "漏斗": "hopper", "电脑": "computer",
    "地毯": "carpet", "火把": "torch", "钻机": "drill", "太阳能": "solar",
}

def t_bot_state():
    txt = _LIVE.dsh("dshdigest 8", 60.0)
    return cut(txt or "（没有回执 ✗ 模组在不在？用 dshver 看 ✓）"), (not txt)

def t_bot_inventory():
    txt = _LIVE.dsh("dshinv list", 60.0)
    return cut(txt or "（没有回执 ✗）"), (not txt)

def t_bot_events(since=None):
    txt = _LIVE.dsh("dshevents" if not since else "dshevents %d" % int(since), 60.0)
    return cut(txt or "（没有回执 ✗）"), (not txt)

def walk_why(since=None) -> str:
    """★把模组**自己**那句 `why=` 捞出来✗★（诊断/判据失败时必须带上 ✓ ⇒ P140 ✓）

    ★为什么要有它✗★：`edge_hop_test` 的 R2 与 `plan_verify_test` 的 Z6 两个红项
      **没把模组那句 `why` 落盘**✗ ⇒ 独立诊断只能老实标 **INCONCLUSIVE** ✗
      （★"缺证据 ⇒ 不猜"是对的 ✓ 但**判据的失败本来就该自带对面的理由**✗★）
    口径 ✓：从**事件流**（纯 ASCII ✓ 不过 CC 终端 ⇒ 中文不会变 `?` ✓）里取最后一条
      `walk_done … why=…` ✓；没有 ⇒ 返回空串 ✓（不许编 ✓）
    """
    txt, bad = t_bot_events(since)
    if bad:
        return ""
    out = ""
    for seg in str(txt).split("|"):
        s = seg.strip()
        if "walk_done" in s:
            m = re.search(r"why=(.*)$", s)
            out = (m.group(1).strip() if m else s.strip())
    return out

def t_look(reach=4.5):
    txt = _LIVE.dsh("dshlook %.2f" % float(reach), 60.0)
    return cut(txt or "（没有回执 ✗）"), (not txt)

def t_scan(x0, y0, z0, x1, y1, z1, match=None, max_=48):
    cmd = "dshscan %d %d %d %d %d %d" % (int(x0), int(y0), int(z0), int(x1), int(y1), int(z1))
    if match:
        cmd += ' "%s" %d 1' % (str(match), int(max_))
    txt = _LIVE.dsh(cmd, 60.0)
    return cut(txt or "（没有回执 ✗）"), (not ok_of(txt, "dshscan"))

def _inv_count(item: str) -> int:
    """背包里这个物品有多少 ✓ —— ★先按**完整 id**算★ ✗（2026-09-28 第 19 轮 ✓）

    原来按**子串**算 ✗ ⇒ 问 `wheat` 会把 `wheat_seeds` 一起算进去 ✗
    实测 ✓：`_inv_count("wheat")` 给 **464** ✗ 而背包里真正的 wheat 只有 128 ✓（seeds 286 ✓）
    ⇒ 对账和"够不够搬"全都会被这个数骗 ✗ ⇒ 改成"**先解析出唯一完整 id** ✓ 再数" ✓
    """
    ids = _inv_ids()
    full, _cands = _resolve_item(item, ids)
    if full:
        return int(ids.get(full, 0))
    n = str(item or "").split(":")[-1].lower()
    return sum(v for k, v in ids.items() if k.split(":")[-1].lower() == n)

def _box(op: str, x, y, z, item=None, count=None):
    nav, bad = _LIVE._near(x, y, z)
    if bad:
        return cut("✗ 没走到容器旁边 ⇒ **没动手** ✓（%s）" % nav), True
    # ★单件路径也要先把名字定死★ ✗（第 19 轮 ✓ 与批量同一条规矩 ✓）：
    #   模组那边是**子串**匹配 ✗ ⇒ 写 `wheat` 会搬 `wheat_seeds` ✗（实测 ✓）
    if item:
        cand = _box_peek_map(x, y, z) if op == "take" else _inv_ids()
        full, cands = _resolve_item(item, cand)
        if full is None:
            if cands:
                return cut("%s ｜ ✗ **没动手** ✓：`%s` **有歧义** ✗ 同时匹配 %s "
                           "⇒ 请写完整 id ✓（模组是子串匹配 ✗）" % (nav, item, ", ".join(cands[:6]))), True
            return cut("%s ｜ ✗ **没动手** ✓：`%s` 在%s里找不到 ✗"
                       % (nav, item, "容器" if op == "take" else "背包")), True
        item = full
        # ★单件路径也要"**动手之前**"查分不分得开★ ✗（第 24 轮 ✓ 与批量同一条规矩 ✓）
        sib = _collide_set(item, cand)
        if sib:
            return cut("%s ｜ ★★没动手 ✓★：★撞名✗★ `%s` 会被模组按**子串**匹配 ⇒ "
                       "同时命中 %s ✓ ⇒ 换成更长的 id ✓ 或先把撞名的那一种搬走 ✓"
                       "（搬错再搬回来会真的改过世界 ✗ P105 ✓）"
                       % (nav, item, ", ".join(sib[:4]))), True
    before = _inv_count(item) if item else 0
    cmd = "dshbox %s %d %d %d" % (op, int(x), int(y), int(z))
    if item:
        cmd += ' "%s"' % str(item)
        if count:
            cmd += " %d" % int(count)
    txt = (_LIVE.dsh(cmd, 60.0) or "").strip()
    if "too far" in txt or "not a block entity" in txt:
        return cut("%s ｜ 模组拒绝：%s" % (nav, txt[:200])), True
    after = _inv_count(item) if item else 0
    delta = after - before
    tail = ""
    if item:
        tail = " ｜ 背包里 %s：%d -> %d（%+d）" % (item, before, after, delta)
        if op == "put" and count and delta >= 0:
            tail += " ★注意：一个都没少 ⇒ 可能没放进去 ✗ 以容器内容为准 ✓"
        if op == "take" and count and delta <= 0:
            tail += " ★注意：一个都没多 ⇒ 可能没拿出来 ✗ 以容器内容为准 ✓"
    return cut("%s ｜ %s%s" % (nav, txt[:220] or "（没有回执 ✗）", tail)), (not txt)

def t_chest_peek(x, y, z):
    return _box("peek", x, y, z)

def t_chest_put(x, y, z, item, count=1):
    return _box("put", x, y, z, item, count)

def t_chest_take(x, y, z, item, count=1):
    return _box("take", x, y, z, item, count)

def _inv_ids() -> dict:
    """★背包里每个**完整 id** 有多少个★ ✓（解析 `dshinv list` ✓ 不按子串猜 ✗）"""
    txt = _LIVE.dsh("dshinv list", 60.0) or ""
    out = {}
    for m in re.finditer(r"\d+:([a-z0-9_:.]+)x(\d+)", txt):
        out[m.group(1)] = out.get(m.group(1), 0) + int(m.group(2))
    return out

def _collide_set(item: str, ids) -> list:
    """★"模组那边**分不开**的同名兄弟"★ ✗（2026-09-29 第 24 轮 ✓ 治 P105 的正面 ✓）

    ★为什么要"提前"判 ✗★：P105 那次我是"**先搬错、再按差额搬回来**"✗ ——
      能用 ✓ 但**白花通道**（单车道很贵 ✗）而且**中途世界真的被改过** ✗
      ⇒ 更好的做法 ✓：**动手之前就知道"这一趟分不开"**⇒ **干脆不动** ✗ 并说清楚为什么 ✓

    判据 ✓（与模组那边的行为**对齐** ✗ 见 `put`/`take` 的 `idOf(slot).contains(filter)` ✓）：
      模组是**子串**匹配 ⇒ 只要**别的 id 里含有**这个 filter ✓ 它就可能被一起搬走 ✓
      ⇒ 所以撞名集 = `{k : filter ⊆ k 且 k ≠ filter}` ✓（**大小写不敏感** ✓）
    ⚠ 只算"**真的有东西**"的 id（传进来的 `ids` 就是背包/容器里真实存在的 ✓）
      —— 不在场的东西搬不走 ✓ 不必因为它拒绝 ✓（少拒绝才是好工具 ✓）
    """
    f = str(item or "").lower()
    if not f:
        return []
    return sorted({k for k in ids if k.lower() != f and f in k.lower()})

def _resolve_item(name, ids) -> tuple:
    """★把"人写的名字"解析成**唯一**的完整 id★ ✗（第 19 轮 ✓ **实测抓到的真坑** ✗）

    ★为什么必须有它★ ✗（实测现场 ✓）：
      模组 `dshbox` 的 `filter` 是**子串匹配** ✗ ⇒ 我说"放 **wheat**"✗
      它把 **`minecraft:wheat_seeds`** 放进去了 ✗（背包里 `wheat` 与 `wheat_seeds` **同时存在** ✗）
      ⇒ 表现 ✓：**要的东西一个没动 ✗ 不要的东西搬了 4 个** ✗ —— 而且**一声不响** ✗
      ⇒ 这种"**悄悄搬错东西**"必须在**中间层**挡住 ✓（往下改模组要重启 ✗ 后置 ✓）

    口径 ✓（写死在这里 ✗）：
      · 完全相等（或等于最后一个 `:` 段 ✓）⇒ 唯一 ✓ 用它 ✓
      · 只有一个 id **含**这个名字 ⇒ 就它 ✓
      · **多个** ⇒ 返回 `(None, 候选)` ✗ ⇒ 调用方**必须拒绝**并让人写全 ✓ **不许瞎猜** ✗
    """
    n = str(name or "").strip().lower()
    if not n:
        return None, []
    keys = list(ids.keys())
    exact = [k for k in keys if k.lower() == n or k.lower().split(":")[-1] == n]
    if len(exact) == 1:
        return exact[0], exact
    hits = [k for k in keys if n in k.lower()]
    if len(hits) == 1:
        return hits[0], hits
    if not hits:
        return None, []
    # 名字正好是最后一个 : 段 ⇒ 只有一个才算数 ✓；否则**歧义** ✗
    return None, hits

def _parse_items(spec) -> list:
    """`"dirt:64,wheat:16"` ⇒ `[("dirt", 64), ("wheat", 16)]` ✓（没写数量 ⇒ 1 ✓）"""
    out = []
    for part in re.split(r"[,;]", str(spec or "")):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            nm, _, ct = part.rpartition(":")
            try:
                n = int(ct)
            except Exception:
                nm, n = part, 1
        else:
            nm, n = part, 1
        nm = nm.strip()
        if nm:
            out.append((nm, max(1, n)))
    return out

def _box_peek_map(x, y, z, max_pages=4) -> dict:
    """★把容器**逐件**读回来★ ✓（分页取全 ✓ 读失败 ⇒ 返回 `{}` 并让调用方别乱判 ✗）

    回执形状 ✓（见模组 `peekHandler` ✓）：
      `dshbox peek x,y,z slots=27 items=42 kinds=3 page=1/2 [0]minecraft:dirtx32 …`
    """
    got = {}
    total = None
    page, pages = 1, 1
    calls = 0
    while page <= pages and calls < int(max_pages):
        txt = (_LIVE.dsh("dshbox peek %d %d %d %d" % (int(x), int(y), int(z), page), 60.0) or "").strip()
        calls += 1
        if not txt or "dshbox" not in txt:
            return {}
        m = re.search(r"page=(\d+)/(\d+)", txt)
        if m:
            page, pages = int(m.group(1)), int(m.group(2))
        mt = re.search(r"items=(\d+)", txt)
        if mt:
            total = int(mt.group(1))
        for mm in re.finditer(r"\[\d+\]([a-z0-9_:.]+)x(\d+)", txt):
            got[mm.group(1)] = got.get(mm.group(1), 0) + int(mm.group(2))
        if page >= pages:
            break
        page += 1
    if total is not None:
        got["__total__"] = total
    return got

def _reconcile(op: str, req: list, inv_b: dict, inv_a: dict, box_b: dict, box_a: dict) -> list:
    """★逐件对账（**纯函数** ✓ 好离线单测 ✗）★

    口径 ✓（写死在这里 ✗）：
      · `put`  ⇒ 期望 **背包减 = 容器增** ✓
      · `take` ⇒ 期望 **背包增 = 容器减** ✓
      判定 ✓：`ok`（数目对得上 ✓）／`partial`（动了但没到数 ✓）／`none`（一点没动 ✗）
      另外**必须**把"背包里本来就没这么多"单列出来 ✓（那是**请求的问题**✗ 不是工具的 ✗）
    """
    rows = []
    for (item, want) in req:
        key = None
        for k in list(inv_b.keys()) + list(box_b.keys()):
            if k.endswith(item) or item.endswith(k.split(":")[-1]):
                key = k
                break
        kk = key or item
        ib, ia = int(inv_b.get(kk, 0)), int(inv_a.get(kk, 0))
        bb, ba = int(box_b.get(kk, 0)), int(box_a.get(kk, 0))
        if op == "put":
            moved = ib - ia
            gained = ba - bb
            verdict = "ok" if (moved == gained and moved > 0) else (
                "partial" if (moved > 0 or gained > 0) else "none")
            note = "" if verdict == "ok" else "（背包少的 %d ≠ 容器多的 %d ✗ 以容器为准 ✓）" % (
                moved, gained)
        else:
            moved = ia - ib
            gained = bb - ba
            verdict = "ok" if (moved == gained and moved > 0) else (
                "partial" if (moved > 0 or gained > 0) else "none")
            note = "" if verdict == "ok" else "（背包多的 %d ≠ 容器少的 %d ✗ 以容器为准 ✓）" % (
                moved, gained)
        rows.append({"item": kk, "want": want, "have_before": ib if op == "put" else bb,
                     "moved": moved, "gained": gained, "verdict": verdict, "note": note})
    return rows

def _box_many(op: str, x, y, z, spec) -> tuple:
    """★批量：**走一趟** ⇒ 前后各读一次 ⇒ 逐件发指令 ⇒ 逐件对账★ ✓"""
    req0 = _parse_items(spec)
    if not req0:
        return cut("没给要搬什么 ✗（写法：`\"minecraft:dirt:64,wheat:16\"` ✓）"), True
    nav, bad = _LIVE._near(x, y, z)
    if bad:
        return cut("✗ 没走到容器旁边 ⇒ **没动手** ✓（%s）" % nav), True
    box_b = _box_peek_map(x, y, z)
    if not box_b:
        return cut("%s ｜ ✗ 容器**读不出来** ⇒ 不敢动手 ✓（读不到就不猜 ✗）" % nav), True
    # ★名字先解析成**唯一完整 id**★ ✗（第 19 轮 ✓）：不然"wheat"会命中 wheat_seeds ✗
    ids = _inv_ids() if op == "put" else {k: v for k, v in box_b.items() if k != "__total__"}
    req, amb, miss = [], [], []
    for (nm, n) in req0:
        full, cands = _resolve_item(nm, ids)
        if full is None:
            (amb if cands else miss).append((nm, cands))
            continue
        req.append((full, n))
    if amb or miss:
        L = ["%s ｜ ✗ **没动手** ✓（名字没定下来 ✗）" % nav]
        for (nm, cands) in amb:
            L.append("   ★`%s` **有歧义** ✗★：同时匹配 %s ⇒ 请写**完整 id** ✓"
                     "（实测坑：写 `wheat` 会命中 `wheat_seeds` ✗ 模组那边是**子串**匹配 ✗）"
                     % (nm, ", ".join(cands[:6])))
        for (nm, _c) in miss:
            L.append("   `%s` 在%s里**找不到** ✗ ⇒ 没法搬 ✓"
                     % (nm, "背包" if op == "put" else "容器"))
        return cut("\n".join(L)), True
    inv_b = {it: int(ids.get(it, 0)) if op == "put" else _inv_count(it) for (it, _w) in req}
    # ★★动手之前先查"分不分得开"★★ ✗（2026-09-29 第 24 轮 ✓ 把 P105 的兜底升级成"提前避开"✓）
    coll = []
    for (item, _w) in req:
        sib = _collide_set(item, ids)
        if sib:
            coll.append((item, sib))
    if coll:
        L = ["%s ｜ ★★没动手 ✓ —— 因为**模组那边分不开**✗★" % nav]
        for (item, sib) in coll:
            L.append("   ★撞名✗★ `%s` 会被模组按**子串**匹配 ⇒ 它同时命中 %s ✓"
                     % (item, ", ".join(sib[:4])))
        L.append("  ⇒ 处置 ✓：① 换一个**不撞名**的物品名 ✓（例如写更长的那个 id ✓）"
                 "② 先把撞名的那一种搬走或搬进来 ⇒ 不在场的就撞不上 ✓ "
                 "③ 或者等模组改成**整段匹配**（v2.17 候选 ✓ 后置 ✓）")
        L.append("  ★为什么宁可不做 ✗：搬错再搬回来**真的改过世界**✗ 而且白花单车道 ✓（P105 ✓）★")
        return cut("\n".join(L)), True
    lines = ["%s ｜ ★批量 %s★ %d 种（**走一趟** ✓ 不再来回跑 ✓）｜ 容器动手前 %d 件 ✓"
             % (nav, "存入" if op == "put" else "取出", len(req),
                box_b.get("__total__", sum(v for k, v in box_b.items() if k != "__total__")))]
    for (item, want) in req:
        # ★★前缀撞名 ⇒ 模组会搬错东西 ⇒ 每件都核对 ＋ 搬错就搬回来★★ ✗
        #   （2026-09-28 第 19 轮 ✓ **实测抓到的真坑** ✗）
        #   为什么 ✗：模组的 filter 是 `id.contains(filter)` ✗
        #     而 `minecraft:wheat` 是 `minecraft:wheat_seeds` 的**前缀** ✗
        #     ⇒ 传完整 id 也**分不开** ✗ ⇒ 我说放 wheat ✗ 它把 seeds 搬走了 4 个 ✗（实测 ✓）
        #   中间层能做的 ✓：搬完**立刻核对**（背包 ＋ 容器 ✓）⇒ 只许目标 id 动 ✓
        #     动了别的 ⇒ **反向搬回去** ✓ 并把这件事**大声报** ✗（世界必须留在正确状态 ✓）
        #   ⚠ 只在**真有撞名风险**时才做这一步 ✗（不然每件都要多两次读 ✗ 白花通道 ✓）
        risky = [k for k in ids if k != item and k.lower().startswith(item.lower())]
        b_ids = _inv_ids() if op == "put" else {}
        b_box = _box_peek_map(x, y, z) if risky else {}
        txt = (_LIVE.dsh('dshbox %s %d %d %d "%s" %d' % (op, int(x), int(y), int(z), item, want),
                   60.0) or "").strip()
        note = ""
        if "too far" in txt:
            note = "★模组说够不着 ✗★"
        elif "inventory full" in txt:
            note = "★背包满了 ⇒ 余量已原样放回/掉脚下 ✗（模组原文 ✓）★"
        if risky:
            a_ids = _inv_ids() if op == "put" else {}
            a_box = _box_peek_map(x, y, z)
            wrong = []
            for k in (risky if op == "put" else list(a_box.keys())):
                if k == "__total__":
                    continue
                if op == "put":
                    d = int(b_ids.get(k, 0)) - int(a_ids.get(k, 0))     # 从背包搬走多少 ✓
                else:
                    d = int(a_box.get(k, 0)) - int(b_box.get(k, 0))     # 从容器搬走多少 ✓
                if d > 0:
                    wrong.append((k, d))
            if wrong:
                fixed = []
                for (k, d) in wrong:
                    inv_op = "take" if op == "put" else "put"
                    # ★必须按**实测差额**搬回★ ✗（2026-09-28 第 19 轮 ✓ 我自己先栽过一次 ✗）：
                    #   我第一版图省事写了 `9999` ✗ ⇒ 把容器里**原先就有**的同名物品
                    #   也一起掏出来了 ✗ ⇒ **次生伤害** ✗（世界被弄得更乱 ✓）
                    #   ⇒ 只搬"**这一次错手搬走的那几个**"✓ 多一个都不许 ✗
                    _LIVE.dsh('dshbox %s %d %d %d "%s" %d' % (inv_op, int(x), int(y), int(z), k, d),
                        60.0)
                    fixed.append("%s×%d" % (k, d))
                    time.sleep(0.25)
                note = ("★★模组**搬错了东西** ✗（子串撞名：`%s` 命中了 %s ✗）"
                        "⇒ 我已按实测差额**精确搬回** ✓（%s ✓）；★这条要真修得改模组 ✗（后置 ✓）★"
                        % (item, ", ".join(k for (k, _d) in wrong), ", ".join(fixed)))
        mm = re.search(r"moved kinds=(\d+) items=(\d+)", txt)
        lines.append("   %-28s 要 %-4d ⇒ 模组报 moved_items=%s %s%s"
                     % (item, want, mm.group(2) if mm else "?", note,
                        "" if mm else "（回执看不懂 ✗ 原文：%s）" % txt[:80]))
        time.sleep(0.25)                      # ★单车道 ⇒ 逐件之间歇一下 ✗
    inv_a = {it: (_inv_count(it)) for (it, _w) in req}
    box_a = _box_peek_map(x, y, z)
    if not box_a:
        return cut("%s ｜ ⚠ 动手**之后**容器读不出来 ⇒ **对不了账** ✗（不许报成功 ✗）"
                   % "\n".join(lines)), True
    rows = _reconcile(op, req, inv_b, inv_a, box_b, box_a)
    ok_n = sum(1 for r in rows if r["verdict"] == "ok")
    lines.append("★对账（容器 ＋ 背包 前后各读一次 ✓）★：%d/%d 件对得上 ✓" % (ok_n, len(rows)))
    for r in rows:
        tag = {"ok": "✓ 对得上", "partial": "✗ **只动了一部分**",
               "none": "✗ **一点没动**"}[r["verdict"]]
        lines.append("   %-28s %s ｜ 移动 %-4d ｜ 容器 %+d %s%s"
                     % (r["item"], tag, r["moved"], r["gained"],
                        ("（动手前背包里只有 %d ⇒ 我最多能搬这么多 ✓）"
                         % r["have_before"]) if r["verdict"] != "ok" and op == "put"
                        and r["have_before"] < r["want"] else "", r["note"]))
    if ok_n < len(rows):
        lines.append("★有 %d 件**没到数** ✗ ⇒ 别当成了 ✓（要重试就把这些再来一次 ✓）"
                     % (len(rows) - ok_n))
    return cut("\n".join(lines)), (ok_n == 0)

def t_chest_put_many(x, y, z, items):
    return _box_many("put", x, y, z, items)

def t_chest_take_many(x, y, z, items):
    return _box_many("take", x, y, z, items)

def t_map_area(radius=10, below=None, max_age=180, verify="auto"):
    import mapread as MR
    r = MR.Reader()
    p = r.pos()
    if not p:
        return cut("读不到 Bot 的坐标 ⇒ **没建图** ✓"), True
    bx, by, bz = int(p[0]), int(p[1]), int(p[2])
    rad = max(2, min(int(radius or 10), 32))     # ★上限 20 → 32★ ✗（2026-09-25 ✓ 有快图了 ✓）
    if below is None:
        below = int(round(p[1]))
    # ★优先用 `/dshmap`（v2.15 ✓ 一次调用一张图 ✓）★ —— 地图完整性靠它 ✓
    fast = None
    try:
        fast = r.build_dshmap(radius=min(rad, 32), max_age=float(max_age))
    except Exception:
        fast = None
    if fast is not None:
        m = fast
        lvl = int(below)
        box = m.box
        # ★v2.16 前必须"实地验"★ ✗（2026-09-28 第 16 轮 ✓）：快图的高度是**推的** ✗
        #   ⇒ 这一片会画成"全平"✗ 落差/障碍全看不见 ✗（错题本 P99 ✓）
        #   ⇒ 用 `dshscan ":"` 把这一片的地面**扫回来** ✓ 就地改正 ✓（`verify` 见 `_need_verify` ✓）
        vinfo = _verify_band(r, m, box[0], box[2], box[3], box[5], lvl,
                             max_pages=10) if _need_verify(m, verify) else None
        stands = sum(1 for (x, z) in m.cells() if m.standable(x, z, lvl))
        head = ("★快图（/dshmap ✓ 一次调用 ✓）★ box=%s 你站在 (%d,%d,%d) 层=%d ｜ 调用 %s 次 "
                "%.0f ms ｜ 与假人同层能站 %s 格 ｜ 图例 %d 种方块（★含稀有方块 ✓ 不再只有 top-40 ✓）"
                % (box, bx, by, bz, lvl, m.meta.get("calls") or "-",
                   (m.meta.get("sec") or 0) * 1000, m.meta.get("dshmap_standable"),
                   len(m.meta.get("legend") or {})))
        if vinfo:
            head += ("\n★这一片的地面**实地扫过了** ✓（`dshscan \":\"` %d 次调用 %.2f 秒 ✓"
                     " 清掉旧值 %d 处 ✓ 写入真值 %d 处 ✓）⇒ **高度/落差/障碍是真的** ✓"
                     "（模组 v2.16 起自带真高度 ⇒ 会自动省掉这一步 ✓）"
                     % (vinfo["calls"], vinfo["sec"], vinfo["cleared"], vinfo["inserted"]))
            if vinfo["truncated"]:
                head += "\n⚠★没扫完（truncated）⇒ 没扫到的地方**不算验过** ✗★"
        elif m.meta.get("has_offsets"):
            head += "\n高度 ✓：模组 v2.16 **自带真高度** ⇒ 不必再扫 ✓（省调用 ✓）"
        # ★★"看得出来是什么"也要补★★ ✗（2026-09-29 第 30 轮 ✓）
        #   上面那一步（整段实扫）会把名字一并带回来 ✓；**真高度**那条捷径则**只管高度** ✗
        #   ⇒ 走捷径时另补**一层**名字即可 ✓（模组对"与你同层"的格子不发名字 ✗ 实测占 93% ✓）
        ninfo = None
        miss0, _per = m.names_missing()
        if miss0 and not vinfo:
            try:
                ninfo = _fill_names(r, m, lvl)
            except Exception as e:
                errlog("fill_names failed", type(e).__name__, str(e))
                ninfo = None
        miss1, _per1 = m.names_missing()
        if ninfo:
            head += ("\n★名字补过 ✓（%d 格" % ninfo["names"]
                     + ("，⚠没扫完 ⇒ 剩下的仍是 `x` ✗" if ninfo.get("truncated") else "")
                     + "）：模组对「能站的层就是你那一层」的柱子只印 `@` ✓ 不发方块名 ✗ "
                       "⇒ 一层实扫（%d 次调用 %.2f 秒 ✓ 层 y=%d ✓）⇒ 现在知道**是什么方块**了 ✓"
                     % (ninfo["calls"], ninfo["sec"], ninfo["layer"]))
        if miss0:
            head += ("\n★图上有 %d 格「有地板但名字不知道」（渲染成 `x` ✗）⇒ 补完还剩 %d 格 ✓"
                     % (miss0, miss1))
        return cut("%s\n%s\n%s" % (head, m.ascii(mark=(bx, bz), below=lvl),
                                   "legend: " + ", ".join(
                                       "%s=%s" % (k, v) for k, v in
                                       sorted((m.meta.get("legend") or {}).items())[:14]))), False
    rad = max(2, min(int(radius or 10), 20))     # 回落老办法：半径仍压 20 ✓（慢 ✗ 见注释 ✓）
    box = (bx - rad, by - 8, bz - rad, bx + rad, by + 6, bz + rad)
    lvl = (by + 1) if below is None else int(below)
    m = r.get(box, max_age=float(max_age))
    stands = sum(1 for (x, z) in m.cells() if m.standable(x, z, lvl))
    head = ("地图 box=%s 你站在 (%d,%d,%d) 层=%d ｜ 建图 %s 次调用 %s 秒 ｜ 覆盖 %.0f%% ｜ "
            "这层能站的格子 %d ｜ 缓存=%s"
            % (box, bx, by, bz, lvl, m.meta.get("calls"), m.meta.get("sec"),
               m.coverage() * 100, stands, m.meta.get("from_cache")))
    return cut("%s\n%s\n%s\n%s" % (head, m.ascii(mark=(bx, bz), below=lvl),
                                   m.legend(), m.height_ascii(below=lvl))), False

def t_find_block(match, radius=24, max_=6):
    import mapread as MR
    r = MR.Reader()
    p = r.pos()
    if not p:
        return cut("读不到 Bot 的坐标 ⇒ 没找 ✓"), True
    # ★别名先翻译★ ✓（用户说的"特定方块查找器"✓ 别名表见 PRESETS ✓）
    raw = str(match)
    want = PRESETS.get(raw.strip()) or raw
    bx, by, bz = int(p[0]), int(p[1]), int(p[2])
    rad = max(4, min(int(radius or 24), 64))
    box = (bx - rad, by - 24, bz - rad, bx + rad, by + 16, bz + rad)
    kvv, coords = r.scan(box, match=want, max_=1000, page=1)
    matched = int(kvv.get("matched") or 0)
    if matched == 0:
        return cut("半径 %d 内**没有**名字里含 %r 的方块（扫描范围 y=%d..%d ✓ 只算已加载区块 ✓）"
                   % (rad, want, box[1], box[4])), False
    d = sorted(coords, key=lambda c: (c[0] - bx) ** 2 + (c[1] - by) ** 2 + (c[2] - bz) ** 2)
    lines = ["半径 %d 内 matched=%d（子串匹配 ✓ 查的是 %r%s ✓ 分页 %s）最近 %d 个："
             % (rad, matched, want,
                ("（别名 %r ⇒ %r ✓）" % (raw, want)) if want != raw else "",
                kvv.get("page") or "?", min(len(d), int(max_ or 6)))]
    for (x, y, z) in d[:int(max_ or 6)]:
        dist = ((x - bx) ** 2 + (y - by) ** 2 + (z - bz) ** 2) ** 0.5
        lines.append("   (%d,%d,%d) 距离 %.1f 格" % (x, y, z, dist))
    lines.append("⇒ 要过去：近的（≤8 格）用 `walk_to` ✓ 远的用 `walk_route` ✓"
                 "（路上有障碍它会绕 ✓ 想先看看路上挡什么就用 `check_path` ✓）"
                 "★别用 dig 开路 ✗★")
    return cut("\n".join(lines)), False

def t_check_path(x, y, z, budget=24, verify="auto"):
    """★走之前先"探路"★ ✓：规划 ＋ **把这条路实地探一遍** ＋ 报告**道中的障碍物** ✓（**不动手** ✓）

    为什么必须有它 ✗（用户点的方向 ✓ 2026-09-23 ✓）：地图是**按方块种类**建的 ✓
      而模组回执的 `counts[...]` **只列 top-40** ✗ ⇒ 稀有方块**地图根本不知道** ✗
      （实测：`computercraft:computer_command` ✓ 地图完全没记 ✓）
      ⇒ 光"看图规划"看不出道上的障碍 ✗ ⇒ 必须**走之前实地探一遍** ✓
    """
    import mapread as MR
    import pathplan as PP
    p = _LIVE._pos_now()
    if not p:
        return cut("读不到 Bot 坐标 ⇒ 没探 ✓"), True
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    r, m, box = _route_map(sx, sz, int(x), int(z), sy)
    LEVEL = _stand_level(m, sx, sz, float(p[1]))       # ★浮点脚高★ ✗ 见 P101 ✓
    # ★探路之前先求真★ ✓（第 17 轮 ✓）：不然"这条路上有没有障碍"是在错地面上问的 ✗
    vinfo = _hull_verify(r, m, sx, sz, int(x), int(z), LEVEL, verify)
    pl = PP.Planner(m, level=LEVEL, blocked=BLOCKED_LV)
    reg = pl.region(sx, sz)
    # ★按路求真★ ✗（第 18 轮 ✓）：路可能绕出外接框 ⇒ 补验 + 重规划 ✓（有界 ＋ 有账 ✓）
    def _cp_plan():
        t = pl.plan(sx, sz, int(x), int(z), region=reg)
        # ⚠ `box` 是**元组** ⇒ 必须写 `% (box,)` ✗（写 `% box` ⇒ 元组被当成多参数 ⇒ TypeError ✓
        #   2026-09-28 实测炸过一次 ✓ 这与 P102 的"锚点空格"同一族：**看着对的写法 ✗ 类型不对** ✗）
        return t[0], t[1], "图 box=%s" % (box,)
    pts, why, _info2, vlog = _plan_verified(r, m, LEVEL, _cp_plan, verify=verify)
    if not pts:
        return cut("规划**没成** ✗：%s%s%s" % (why, _vline(vinfo), _vlog(vlog))), True
    lines = ["规划 ✓ %s ｜ 航点 %d 个 ｜ 图 box=%s%s%s"
             % (why, len(pts), box, _vline(vinfo), _vlog(vlog))]
    lines.append("★障碍记忆★：手里已经有 %d 格" % len(BLOCKED)
                 + ("（`logs/obstacles.json` 里读回来的 ✓ 跨进程有效 ✓ 超过 24 小时自动作废 ✗）"
                    if BLOCKED else "（还没有 ✓ 第一次去某个地方会全探 ✓）"))
    sw = r.scan_route(m, pts, LEVEL, budget=int(budget or 12), known=BLOCKED)
    lines.append("★实地探路★：这条路 %d 格 ✓ 探了 %d 格"
                 "（每格一次独立读 ✓ 之间歇一下 ✓；**已知道的障碍跳过 %d 格 ✓**）｜ 用 %.1f 秒"
                 % (sw["cells"], sw["probed"], sw.get("skipped_known") or 0, sw["sec"]))
    if sw.get("aborted"):
        lines.append("★★通道出问题了：探到 %d 次就**读不到回执** ⇒ 立刻收手 ✗（再发只会把队列堆高 ✗）★"
                     % sw["probed"])
    if sw["found"]:
        lines.append("★★道中障碍物 %d 处★★：" % len(sw["found"]))
        for (bx, bz, name) in sw["found"][:8]:
            _obst_add(bx, bz, name, LEVEL)      # ★带层记★ ✗（第 31 轮 ✓）
            lines.append("   (%d,%d) 被 **%s** 挡着 ✗（已记进「要绕开的格子」✓ 并落盘 ✓）"
                         % (bx, bz, name))
        _obst_save()          # ★落盘 ⇒ 下次（哪怕换了进程/重启 ✓）不用重探 ✓
        pl2 = PP.Planner(m, level=LEVEL, blocked=BLOCKED_LV)
        reg2 = pl2.region(sx, sz)
        pts2, why2 = pl2.plan(sx, sz, int(x), int(z), region=reg2)
        if pts2:
            lines.append("⇒ 绕开之后再规划：航点 %d 个 ✓（%s）" % (len(pts2), why2))
        else:
            lines.append("⇒ 绕开之后**仍然不通** ✗：%s（如实说 ✗ 不硬走 ✓）" % why2)
    else:
        lines.append("这条路**没探到障碍** ✓（≠ 绝对没有 ✗ —— 只探了脚层与头层 ✓）")
    if sw["left"]:
        lines.append("⚠ 预算用完：还有 **%d 格没探** ✗（不许当成「整条路都干净」✗）" % sw["left"])
    lines.append("⇒ 要过去就用 `walk_route` ✓（它也会先探路 ✓ 撞到障碍会绕 ✓）")
    return cut("\n".join(lines)), False

def t_safe_spots(dmin=4, dmax=16, max_=12):
    """★可以放心去的落脚点★ ✓（连通区域内陆格 ✓ —— 专治"平台边上一脚踩空"✗）"""
    import mapread as MR
    import pathplan as PP
    r = MR.Reader()
    p = r.pos()
    if not p:
        return cut("读不到 Bot 的坐标 ⇒ 没列 ✓"), True
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    rad = max(int(dmax) + 6, 12)
    box = (sx - rad, sy - 8, sz - rad, sx + rad, sy + 6, sz + rad)
    m = r.get(box, max_age=300.0)
    cell = m.stand_cell(sx, sz, sy + 2) or (sx, sy, sz)
    pl = PP.Planner(m, level=cell[1])
    reg = pl.region(sx, sz)
    tg = pl.safe_targets(sx, sz, float(dmin), float(dmax), reg, min_n=3)
    if not tg:
        return cut("这块平台里 %s~%s 格范围内**没有**可放心去的落脚点 ✗"
                   "（连通区 %d 格 ｜ 图 box=%s 覆盖 %.0f%%）"
                   % (dmin, dmax, len(reg), box, m.coverage() * 100)), False
    lines = ["你 (%.1f,%.1f,%.1f) 站的那一格 %s ｜ 这块连通平台 %d 格 ✓ 其中「离边至少一格」的 %d 格 ✓"
             % (p[0], p[1], p[2], cell, len(reg), len([c for c in reg if pl.interior(*c)]))]
    if getattr(pl, "last_relaxed", False):
        lines.append("★注意：安全走廊里的目标不够 ⇒ 有几个是**放宽**挑的（终点内陆但路可能贴边 ✗）★")
    lines.append("可以放心去（%s~%s 格，最多列 %s 个）：" % (dmin, dmax, max_))
    for (d, x, y2, z) in tg[:int(max_ or 12)]:
        lines.append("   (%d,%d,%d) 距离约 %.1f 格" % (x, y2, z, d))
    lines.append("⇒ 要去就用 walk_route ✓（它会拆跳并逐跳验位置 ✓）")
    return cut("\n".join(lines)), False

def t_survey(radius=14, verify="auto"):
    """★落点勘察★：一张图 ＋ 这一片有什么（各给最近坐标 ✓）"""
    import mapread as MR
    import pathplan as PP
    import math as _m
    r = MR.Reader()
    p = r.pos()
    if not p:
        return cut("读不到 Bot 坐标 ⇒ 没勘察 ✓"), True
    bx, by, bz = int(p[0]), int(p[1]), int(p[2])
    rad = max(4, min(int(radius or 14), 32))     # ★上限 20 → 32★ ✗（2026-09-28 ✓ 快图一次就够 ✓）
    LEVEL0 = int(round(float(p[1])))
    # ★优先走 `/dshmap`（v2.15 ✓ 一次调用一张大图 ✓）★ —— 勘察"一片"时它比按种类扫描强得多 ✓
    fast = None
    try:
        fast = r.build_dshmap(radius=min(rad, 32), max_age=300.0)
    except Exception:
        fast = None
    if fast is not None:
        m = fast
        box = m.box
        # ★跟 `map_area` 同一条规矩★ ✗：快图的高度是推的 ⇒ **实地扫回来改正** ✓
        vinfo = _verify_band(r, m, box[0], box[2], box[3], box[5], LEVEL0,
                             max_pages=10) if _need_verify(m, verify) else None
    else:
        box = (bx - rad, by - 8, bz - rad, bx + rad, by + 6, bz + rad)
        m = r.get(box, max_age=300.0)
        vinfo = None                       # 慢图是按真实方块建的 ✓ 不用验 ✓
    cell = m.stand_cell(bx, bz, LEVEL0 + 2) or (bx, LEVEL0, bz)
    pl = PP.Planner(m, level=cell[1])
    reg = pl.region(bx, bz)
    tg = pl.safe_targets(bx, bz, 2.0, float(rad), reg, min_n=3)
    lines = ["勘察 box=%s 覆盖 %.0f%% ｜ 你 (%d,%d,%d) ｜ 连通平台 %d 格（内陆 %d 格）"
             % (box, m.coverage() * 100, bx, by, bz, len(reg),
                len([c for c in reg if pl.interior(*c)]))]
    if vinfo:
        lines.append("★这一片的地面**实地扫过了** ✓（%d 次调用 %.2f 秒 ✓ 清旧 %d ／ 写真 %d ✓）"
                     "⇒ 连通/内陆/落脚点都是按**真高度**算的 ✓%s"
                     % (vinfo["calls"], vinfo["sec"], vinfo["cleared"], vinfo["inserted"],
                        "（⚠没扫完 ⇒ 没扫到的地方不算验过 ✗）" if vinfo["truncated"] else ""))
    elif m.meta.get("has_offsets"):
        lines.append("高度 ✓：模组 v2.16 自带真高度 ⇒ 不必再扫 ✓")
    seen: dict = {}
    for (x, z), col in m.cols.items():
        s = m.surface(x, z, by + 1)
        if s and s[0] in col:
            seen.setdefault(col[s[0]], []).append((x, s[0], z))
    keys = [k for k in seen if any(t in k for t in
                                   ("water", "lava", "chest", "barrel", "furnace", "sieve",
                                    "wheat", "carrot", "potato", "torch", "hopper", "crafting"))]
    if keys:
        lines.append("这一片值得注意的（各给最近一个坐标 ✓）：")
        for k in sorted(keys):
            pts = sorted(seen[k], key=lambda c: (c[0] - bx) ** 2 + (c[2] - bz) ** 2)
            x, y, z = pts[0]
            lines.append("   %-40s x%-3d 最近 (%d,%d,%d)  %.1f 格"
                         % (k, len(pts), x, y, z, _m.dist((x, y, z), (bx, by, bz))))
    else:
        lines.append("这一片没扫到水/机器/庄稼之类的显眼东西 ✓")
    dig = _LIVE.dsh("dshdigest %d" % max(6, rad), 40.0) or ""
    mm = re.search(r"drops=(\d+)", dig)
    lines.append("地上掉落物 = %s（要捡用 go_to_drop ✓）" % (mm.group(1) if mm else "?"))
    lines.append("能安全去的落脚点 %d 个（最近的：%s）"
                 % (len(tg), ", ".join("(%d,%d,%d)" % (t[1], t[2], t[3]) for t in tg[:4]) or "-"))
    return cut("\n".join(lines)), False

def _parse_digest(txt) -> dict:
    """★把 `dshdigest` 那一行拆成结构化字段★ ✓（**纯函数** ✓ 好离线单测 ✗）

    回执形状 ✓（实测 ✓）：
      `dshdigest name=Bot pos=x,y,z yaw=… hp=… food=… mode=… onground=… dim=… time=…
        day=… held=…x… inv[x]kinds=32,items=589,free=4,sel=0
        ents=13 hostiles=0 nearest=minecraft:chicken@2.2 drops=0 look=none`
    ★为什么值得单独抽出来 ✗★：这个文本以后会加字段（模组一改就变 ✓）
      ⇒ 解析必须是**一处** ✓ 而且**缺字段要如实缺** ✗（不许用默认值假装有 ✓）
    """
    t = str(txt or "")
    out = {}
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", t)
    if m:
        out["pos"] = tuple(float(g) for g in m.groups())
    for key in ("hp", "food", "sat", "xp"):
        mm = re.search(r"%s=(-?[\d.]+)" % key, t)
        if mm:
            out[key] = float(mm.group(1))
    for key in ("name", "mode", "dim", "onground", "held", "look"):
        mm = re.search(r"%s=(\S+)" % key, t)
        if mm:
            out[key] = mm.group(1)
    mm = re.search(r"kinds=(\d+),items=(\d+),free=(\d+),sel=(\d+)", t)
    if mm:
        out["kinds"], out["items"], out["free"], out["sel"] = (int(g) for g in mm.groups())
    for key in ("ents", "hostiles", "drops", "time", "day"):
        mm = re.search(r"%s=(\d+)" % key, t)
        if mm:
            out[key] = int(mm.group(1))
    mm = re.search(r"nearest=(\S+?)(?:@([\d.]+))?(?:\s|$)", t)
    if mm:
        out["nearest"] = mm.group(1)
        if mm.group(2):
            out["nearest_dist"] = float(mm.group(2))
    return out

def t_whereami():
    """★★现状速览：一次调用说完"我现在什么样"★★ ✗（2026-09-29 第 29 轮 ✓）

    ★为什么要有它★ ✗：大脑每轮开工前要问一圈 —— 我在哪 ✓ 周围有什么活的 ✓
      背包还剩几格 ✓ 我离边几步 ✓ 危不危险 ✓ —— 一件件问要 5~6 次往返 ✗（单车道很贵 ✗）
    ★口径★ ✗：**能算的算 ✓ 能读的读 ✗ 不许猜** ✗ ——
      位置／生命／饱食／实体／掉落物 ⇒ 来自**一次 `dshdigest`** ✓（世界真值 ✓）
      连通平台与"离边几格" ⇒ 来自**地图**（算 ✓ 与 `platform` 同一套 ✓）
    """
    import pathplan as PP
    t0 = time.time()
    CNT0 = {"dsh": 0}
    dig = _LIVE.dsh("dshdigest 24", 40.0) or ""
    CNT0["dsh"] += 1
    d = _parse_digest(dig)
    if "pos" not in d:
        return cut("读不到自己的状况 ✗（回执：%s）" % (dig[:120] or "空")), True
    px, py, pz = d["pos"]
    sx, sy, sz = int(px), int(py), int(pz)
    b0 = int(_MISSION.get("builds") or 0)
    # ★`margin=0`★ ✗（2026-09-29 第 30 轮 ✓ 实测抓到的脆弱点 ✓）：
    #   `whereami` **不规划路** ✓ 它只要"脚下这块平台 ＋ 边在哪" ✓ ⇒ 不需要路线两边那圈余量 ✓
    #   而余量留 8 ⇒ 复用判据变成"任务图必须比 `你±8..你+16` 还大"✗ ⇒
    #     建图那一刻与读的那一刻假人差 **1 格**就判不复用 ✗ ⇒ 又建一张图 ✗
    #     （实测 ✓：`whereami_test` 的 W1「0 次建图」就是被这个卡成红 ✗ 而工具其实没做错什么 ✗）
    #   ⇒ 余量给 0 ✓（地图本身是半径 16 的一大块 ✓ 够用 ✓）⇒ 复用不再依赖"世界纹丝不动"✓
    r, m, box = _route_map(sx, sz, sx + 8, sz, sy, margin=0)
    LEVEL = _stand_level(m, sx, sz, float(py))
    builds = int(_MISSION.get("builds") or 0) - b0
    # ★同层口径 ✓（与 `platform` 同一套 ✓ 第 31 轮 ✓）："离最近的边"问的是**我这一层**的边 ✗
    pl = PP.Planner(m, level=LEVEL, blocked=BLOCKED_LV, avoid_edge=True, same_level_only=True)
    reg = pl.region(sx, sz)
    bnd = _boundary_cells(pl, reg)
    d_near = None
    if bnd:
        d_near = min(((x - sx) ** 2 + (z - sz) ** 2) ** 0.5 for (x, z) in bnd)
    # ★★把**精确坐标**也印出来★★ ✗（2026-09-29 第 30 轮 ✓ 实测被"格边"咬了一口 ✓）：
    #   现象 ✗：判据 W2a 红 ✗ —— 工具报 `z=3` ✗ 独立读那次是 `4.0` ✗
    #   真因 ✓：`int(3.98)` = 3 ✓ 而 `int(4.00)` = 4 ✓ ⇒ 假人正**骑在格边界上**（差 0.1 格 ✓）
    #     ⇒ 两边都没错 ✗ —— 错的是"**我拿整数格去跟浮点比**"✗
    #   ⇒ 口径 ✓：**同一件事要跟同一件事比** ✗ ⇒ 工具把"格"和"精确位置"**都**报出来 ✓
    #     （格是规划用的 ✓ 精确值是"我到底站在哪"✓ 两个都有用 ✓）
    L = ["★现状★ %s @ (%d,%d,%d) 精确 %.2f,%.2f,%.2f ｜ %s ｜ 血 %.0f 饱食 %.0f ｜ %s"
         % (d.get("name", "?"), sx, sy, sz, px, py, pz, d.get("dim", "?"),
            d.get("hp", -1), d.get("food", -1), d.get("mode", "?")),
         "背包：%s 种 / %s 件 ｜ **空格 %s** ｜ 手上 %s"
         % (d.get("kinds", "?"), d.get("items", "?"), d.get("free", "?"),
            d.get("held", "?")),
         "周围（24 格内）：实体 **%s** ｜ ★敌对 %s★ ｜ 最近 %s%s ｜ 地上掉落物 %s"
         % (d.get("ents", "?"), d.get("hostiles", "?"), d.get("nearest", "?"),
            ("@%.1f 格" % d["nearest_dist"]) if "nearest_dist" in d else "",
            d.get("drops", "?"))]
    if reg:
        L.append("脚下这块平台：连通 **%d** 格 ｜ 离最近的边 **%s**"
                 % (len(reg), ("%.1f 格" % d_near) if d_near is not None else "?"))
        if d_near is not None and d_near <= 2.0:
            L.append("★★警告 ✗：你**贴着边**（%.1f 格）—— 一步踩空就是虚空 ✗"
                     "（2026-09-23 真掉过一次 ✓ 丢了钻石/斧子/漏斗/煤/铁/锤子/麦子 ✓）"
                     "⇒ 要动先用 `platform` 看方向 ✓ 或 `safe_spots` 挑落脚点 ✓★" % d_near)
    else:
        L.append("⚠ 连通平台算不出来 ✗（图不对？先 `map_area` 看一眼 ✓）")
    if int(d.get("hostiles") or 0) > 0:
        L.append("★有敌对生物 %s 只 ✗ ⇒ 先 `platform` 看退路 ✓ 或先清掉再干活 ✓★"
                 % d.get("hostiles"))
    L.append("（代价：**%d 条指令 ＋ 建图 %d 次** ｜ 用时 %.2f 秒 ✓ —— "
             "0 次建图 ＝ 图是缓存里的 ✓）" % (CNT0["dsh"] + builds, builds, time.time() - t0))
    return cut("\n".join(L)), False


def t_move_slot(from_slot, to_slot, count=None):
    """★★槽位移动✗★★：把背包里 `from` 槽的东西挪到 `to` 槽（2026-10-03 ✓ 欠账 ⑳ ✓）

    ★为什么要有它✗★：★`equip` 只换**选中那一个槽**✗★ ⇒ ★两把工具**放不进同一个快捷栏**✗★
      ⇒ ★⑯-① 那条"`switch(…)` 换手"的判据**验不了**✗★（★见 §79.33 ✓★）
      而模组里 `dshinv move` 一直有 ⇒ ★这里只是把它接出来✗★ ✓

    ★判据✗★（★按 N1~N3 ✓ 只听世界真值✓）★
      ★动手前后各读一次 `bot_inventory`✗ ⇒ ★`to` 槽必须变成**那件东西**✗✗ 否则**判红**✗★
    """
    try:
        a, b = int(from_slot), int(to_slot)
    except Exception:
        return cut("★槽号必须是整数 ✗ 收到 %r / %r✗★" % (from_slot, to_slot)), True
    if not (0 <= a <= 40 and 0 <= b <= 40):                     # ★N3：发之前就拒✓★
        return cut("★槽号越界✗★（★只收 0..40 ✗ 收到 %d / %d ✓ —— ★连发都不发✗★）" % (a, b)), True
    if a == b:
        return cut("★`from` 和 `to` 是同一个槽（%d）⇒ **没动** ✓★" % a), True

    def _slots():
        # ★★直接问模组✗★★（2026-10-03 ✓ P180 的教训当场用上 ✓）：
        #   ★我第一版写 `BY_NAME["bot_inventory"]`✗ ⇒ ★而 `BY_NAME` 住在 **`mc_mcp.py`**✗
        #     本模块**没有它**（★编译能过 ✗ 运行必炸 ✗ 正是 P180 那个形状✓★）
        #   ⇒ ★改成 `dsh("dshinv list")`✗：★同一份数据 ✗ 少一个跨模块依赖✓★
        try:
            t = dsh("dshinv list", 40.0) or ""
        except Exception as e:                 # ★★§79.402✗★ 读失败要**留痕** ✗ 不静默✗★
            errlog("mcp_percept 读背包失败：%r" % (e,))
            return None
        # ★★"读不到"与"是空的"必须**分开**✗★★（2026-10-03 ✓ 被判据 N4 抓出来 ✓）：
        #   ★回执里连 `dshinv list` 都没有 ⇒ ★这是**读失败**✗ ⇒ 回 `None`✗★
        #   （★否则空串会被解析成"背包是空的" ✗ 于是"读不到"被冒充成"没东西"✗ ✓）
        if "dshinv list" not in t:
            return None
        d = {}
        for m in re.finditer(r"(\d+):([a-z0-9_]+:[a-z0-9_]+)(?:x(\d+))?", t):
            d[int(m.group(1))] = (m.group(2), int(m.group(3) or 1))
        return d

    before = _slots()
    if before is None:
        return cut("★读不到背包 ✗ verified=false✗★（★没发命令 ✓★）"), True
    item = before.get(a)
    if item is None:
        return cut("★`from` 槽（%d）**是空的**✗ ⇒ 没动 ✓（★现在：%s✓★）"
                   % (a, ", ".join("%d:%s" % (k, v[0].split(":")[-1])
                                   for k, v in sorted(before.items())[:8]) or "（空 ✓）")), True
    cmd = "dshinv move %d %d" % (a, b) + ((" %d" % int(count)) if count else "")
    import time as _t
    try:
        out = dsh(cmd, 40.0) or ""
    except Exception as e:
        return cut("★命令没发出去 ✗ verified=false✗★（%s）" % type(e).__name__), True
    _t.sleep(0.25)
    after = _slots()
    if after is None:
        return cut("★发完了但**读不回**背包 ✗ verified=false✗★（★回执：%s✓★）"
                   % str(out).strip()[:70]), True
    got = after.get(b)
    want_short = item[0].split(":")[-1]
    ok = bool(got) and (want_short in got[0])
    return cut("★槽位移动✗★ %d -> %d ｜ 搬的是 `%s`x%d ✗ 回读 `to` 槽＝%s "
               "｜ ★verified=%s✗★ ｜ 回执 %s"
               % (a, b, item[0], item[1], ("%s x%d" % (got[0], got[1])) if got else "（空 ✗）",
                  "true" if ok else "false", str(out).strip()[:70])), (not ok)


_BY_NAME_READY = True
