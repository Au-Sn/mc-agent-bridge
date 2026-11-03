#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jobs.py — 「作业」层：把**一串动作**打包成**一件事** ✓

用户明确要求 ✓（2026-09-19 晚）：「把**收割 → 补种**做成**一条作业**」✗

为什么必须单独有这一层 ✗（不是"再写一个脚本"✗）：
  现状的毛病是**碎片化** ✗：
    · `tools/harvest.py` = 收 ＋ 顺手补种 ✓（但只在"有成熟植株"时才跑得起来 ✗）
    · `tools/replant.py` = 只补种空耕地 ✓（田里没庄稼时才有意义 ✗）
    ⇒ 想干成"这一片田恢复了"，得**人记得**按顺序跑、记得带对参数 ✗
    ⇒ 而"记得"在本项目的战绩是 **0 次生效** ✗（丢过 30 株小麦 ✗ 丢过 64+25 绿宝石 ✗）
  ⇒ 作业的定义（本文件照这个写 ✓）：
      ① **一个入口** ✓ 一条指令 = 一整件事 ✓
      ② **自带前置检查** ✓（背包守卫 ✓ —— 收成接不住就等于没干 ✗ 见错题本 P19.1 ✓）
      ③ **自带自证** ✓（干完**重扫世界** ＋ **数背包** ✗ 不看动作自述 ✗）
      ④ **失败大声** ✓（哪一株没成、为什么、还剩几株 ✓ 别只回一个"完成"✗）
      ⑤ **中途失败不放弃整件事** ✓（补种失败绝不能中断收割 ✗ 见 J5 ✓）

本文件现在有的作业 ✓：
    * `harvest_and_replant` —— 收成熟小麦 → 逐个补种 → 顺手把**本来就空着**的耕地也种上 ✓
    * 用法（CLI ✓）：py agent/jobs.py harvest --x0 4104 --y0 70 --z0 4 --x1 4120 --y1 71 --z1 16
    * 用法（技能层 ✓）：py agent/run.py do harvest x0=4104 y0=70 z0=4 x1=4120 y1=71 z1=16
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

from channel import Channel, BridgeError          # noqa: E402
from inv_guard import ensure_free, inventory      # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


# --------------------------------------------------------------------------- #
# 底层小工具（都**容忍失败** ✓ 单点失败不许打断整个作业 ✗ 见 J5 ✓）
# --------------------------------------------------------------------------- #

def call(ch: Channel, cmd: str, args: dict, timeout: float = 240.0) -> dict:
    """发一个桥接动作 ✓ 失败时返回 `{"__error__": …}` **而不是抛异常** ✓

    ⚠ 为什么要吞异常 ✗（真实事故 ✓）：失败时 `r.result` 是**错误字符串** ✗
      ⇒ 直接 `as_dict()` 会抛 ✗ ⇒ **整个作业被打断** ✗
      —— 实测后果：33 株小麦只收了 1 株 ✗（错题本 J5 ✓）
    """
    cid = ch.send(cmd, args)
    r = ch.wait(cid, timeout=timeout, cmd=cmd)
    try:
        d = r.as_dict()
    except BridgeError:
        return {"__error__": str(r.result)}
    payload = d.get("result")
    if not isinstance(payload, dict):
        payload = d if isinstance(d, dict) else None
    return payload if isinstance(payload, dict) else {"__error__": str(payload)}


def ensure_in_hotbar(ch: Channel, bot: str, want: str):
    """把含 `want` 的那一堆挪进快捷栏 ✓ → 返回目标槽号（搬不了返回 None ✓）

    为什么要这一步 ✗：假人**自己搬不动槽位** ✗（只能靠原版 `/item replace` ✓）
     ⚠ 搬不了**不等于**作业失败 ✗ —— 调用者应当"跳过补种、继续收割" ✓（收割才是正事 ✓）

    ★2026-09-19 深夜补★ ✗：**快捷栏满**时不能直接放弃 ✗ —— 实测就栽在这儿 ✓
      （假人快捷栏 9/9 满 ⇒ `free=[]` ⇒ 我第一版直接返回 None ✗
        而**真人遇到这种情况是"交换"** ✓ 不是"放弃" ✗）
      ⇒ 改用模组那条**真人的路** ✓：`dshinv hotbar <src>` = 把那一堆**换到选中的手上** ✓
        （它自己会回 `swapped 20 <-> 0` ✓ 零丢失 ✓）⇒ **不需要有空槽** ✓✓
    """
    items, _used, _txt = inventory(ch, bot)
    hot = [s for s, i, _c in items if 0 <= s <= 8 and want in i]
    if hot:
        return hot[0]
    src = next((s for s, i, _c in items if want in i and 9 <= s <= 35), None)
    if src is None:
        return None
    occupied = {s for s, _i, _c in items if 0 <= s <= 8}
    free = [s for s in range(9) if s not in occupied]
    if free:
        dst = free[0]
        call(ch, "cmd", {"text": "item replace entity %s hotbar.%d from entity %s inventory.%d"
                                 % (bot, dst, bot, src - 9)})
        return dst
    # ★快捷栏没有空槽 ⇒ **交换**✓（真人就是这么做的 ✓ 模组的 `dshinv hotbar` 也是这么做的 ✓）
    _mod_bot(ch, bot, "dshinv hotbar %d" % int(src))
    return 0                                  # 交换的目标是"当前选中的那一格"（就是 0 ✓）


def _mod_bot(ch: Channel, bot: str, text: str, t: float = 60.0) -> str:
    """发一条**模组指令**（必须套 `execute as … at …` ✗ 见 P14/18.3 ✓）"""
    r = ch.cmd("execute as %s at %s run %s" % (bot, bot, text), timeout=t, allow_str=True)
    s = (r.text() or "").strip()
    return s.splitlines()[0] if s else "(no reply)"


def go_to(ch: Channel, bot: str, x: int, y: int, z: int, ms: int = 6000,
          exact: bool = True, allow_tp: bool = True) -> dict:
    """★走位：**优先用脚走**★ ✗（模组 v2.6 的原生行走 ✓ 一条指令走一整段 ✓）

    为什么这条改法值钱 ✗（本项目**一直在用 `tp` 挪假人** ✗ 见错题本多处 ✓）：
      · 真人**不会瞬移** ✗ ⇒ `tp` 是"人感"上最大的一个洞 ✓（也是 v2.6 要补的第一层 ✓）
      · 它会**污染证据** ✗ —— 与 P17（创造模式挖不掉落 ✗）同一族 ✓：
        "它走到了"和"它被瞬移过去了"在录像里是两件事 ✓ 可记录里长得一样 ✗
      · 而且模组现在**会记一条 `warp` 事件** ✗ ⇒ 偷偷 tp 也会被抓出来 ✓
        ⇒ 那还不如**自己先如实记账** ✓（本函数返回 `used_tp` ✓ 上层把它统计出来 ✓）

    返回值 ✓：`{"ok":bool, "used_tp":bool, "why":str, "at":str, "mode":str}`
    """
    st = _mod_bot(ch, bot, "dshwalk %d %d %d %d%s" % (int(x), int(y), int(z), int(ms),
                                                      " exact" if exact else ""), 60.0)
    why = ""
    if st.startswith("dshwalk start"):
        deadline = time.time() + max(4.0, float(ms) / 1000.0 + 4.0)
        while time.time() < deadline:
            time.sleep(0.4)
            line = _mod_bot(ch, bot, "dshwalk", 30.0)
            kv = {}
            for tok in line.split():
                if "=" in tok:
                    k, _, v = tok.partition("=")
                    kv[k] = v
            if kv.get("status") == "done":
                if kv.get("result") == "reached":
                    return {"ok": True, "used_tp": False, "why": "", "at": kv.get("at", "?"),
                            "mode": kv.get("mode", "?")}
                why = "walk %s (%s)" % (kv.get("result", "?"), kv.get("why", "none"))
                break
        else:
            _mod_bot(ch, bot, "dshwalk stop", 30.0)
            why = "walk timeout"
    else:
        why = "mod v2.6 not loaded? (%s)" % st[:80]

    if not allow_tp:
        return {"ok": False, "used_tp": False, "why": why, "at": "?", "mode": "?"}
    # ★兜底 `tp` ✓ 但**绝不静默** ✗：把"这一步是瞬移过去的"写进返回值 ✓ 上层统计 ✓
    call(ch, "cmd", {"text": "tp %s %.4f %d %.4f" % (bot, x + 0.5, y, z + 0.5)})
    return {"ok": True, "used_tp": True, "why": why, "at": "?", "mode": "tp"}


def _snapshot(ch: Channel, box: dict, match: str | None = None, maxcells: int = 400) -> dict:
    args = dict(box)
    if match:
        args["match"] = match
    args["maxcells"] = maxcells
    return call(ch, "snapshot", args)


# --------------------------------------------------------------------------- #
# 作业：收割 → 补种
# --------------------------------------------------------------------------- #

def harvest_and_replant(ch: Channel, box: dict, bot: str = "Bot",
                        replant: bool = True, verbose: bool = True) -> dict:
    """★一条作业★：把一片田"收干净、再种回去" ✓ 并**用世界真值自证** ✓

    顺序（每一步都有理由 ✗ 别调换 ✓）：
      ① 背包守卫（**最先** ✗）—— 收成接不住 = 白干 ✗ 而且掉落物 5 分钟消失 ✗（P19.1 ✓）
      ② 扫描：成熟的小麦（`age>=7` ✓ 只收熟的 ✗ 青苗只掉种子 ✗）
      ③ 逐株：**先走到它跟前**（`tp` ✓）→ 挖 → 立刻补种
         —— "走到跟前"这条是**丢过 30 株**换来的 ✗（错题本 M4 ✓）
      ④ 再补一遍**本来就空着**的耕地 ✓（= replant.py 那件事 ✓ 顺手做掉 ✓）
      ⑤ 自证：重扫小麦 ＋ 数背包 ✓（**动作自述不算数** ✗）
    """
    t0 = time.time()
    res: dict = {"ok": False, "harvested": 0, "planted": 0, "failed": [],
                 "ripe": 0, "empty_farmland": 0, "why": "", "stages": [],
                 "walks": 0, "tp_fallbacks": 0}

    def stage(name: str, note: str = "") -> None:
        res["stages"].append({"stage": name, "t": round(time.time() - t0, 2), "note": note})
        if verbose and note:
            print("[作业 %-12s] %s" % (name, note))

    # ① 背包守卫 ✓（纪律⑤：放不下就**拒绝开工** ✗ 绝不边干边丢 ✗）
    g = ensure_free(ch, bot=bot, need=2, auto=True, verbose=verbose)
    res["guard"] = {"ok": g.get("ok"), "free": g.get("free"), "stashed": g.get("stashed")}
    stage("guard", "空位 %s（塞进容器 %d 种 ✓）"
          % (g.get("free"), len(g.get("stashed") or [])))
    if not g.get("ok"):
        res["why"] = "背包守卫不放行：%s" % (g.get("why") or "空位不足")
        return res

    # ② 扫描成熟的小麦 ✓（`match=` 按方块名筛 ✓ M1 ✓ 带 state ✓）
    snap = _snapshot(ch, box, match="wheat")
    cells = snap.get("cells") or []
    ripe = []
    for c in cells:
        st = c.get("state") or {}
        age = st.get("age")
        if age is None or int(str(age)) >= 7:      # 没给 age 的（别的模组小麦）也收 ✓ 保守起见
            ripe.append(c)
    res["ripe"] = len(ripe)
    stage("scan", "区域 %s ｜ 小麦 %d 株 ｜ 成熟 %d 株"
          % (json.dumps(snap.get("box") or box, ensure_ascii=False), len(cells), len(ripe)))

    # ③ 收 → 补种（逐株 ✓ 每株都先站到跟前 ✓）
    seed_slot = ensure_in_hotbar(ch, bot, "wheat_seeds") if replant else None
    if replant and seed_slot is None:
        stage("seeds", "⚠ 种子的堆搬不进快捷栏 ✗ ⇒ **跳过补种**（收割继续 ✓ 补种失败不许中断收割 ✗ J5 ✓）")
    held_ok = False
    for c in ripe:
        x, y, z = int(c["x"]), int(c["y"]), int(c["z"])
        # ★ 收与捡必须在**同一个位置** ✗（否则收成够不着 ⇒ 5 分钟消失 ✗ M4 ✓）
        #   ★★v2.6：这一句改成**用脚走**★★ ✗（原来是 `tp` ✓ 真人不会瞬移 ✗）
        #   走不到才兜底 tp ✓ 而**兜底次数会被统计并如实报出来** ✓（见 res["tp_fallbacks"] ✓）
        g = go_to(ch, bot, x, y, z, ms=4000, exact=True)
        res["walks"] += 1
        if g.get("used_tp"):
            res["tp_fallbacks"] += 1
            res["failed"].append({"at": [x, y, z], "why": "走路失败⇒兜底 tp：" + str(g.get("why"))[:90]})
        # ★★2026-10-03 改走**模组侧**✗★★（欠账 ② 收尾 ✓ 用户拍板：往模组侧并 ✗ Lua `dig_at` 正式冻结 ✓）
        #   ★为什么✗★：★模组 `/dshdig` 现在按**游戏自己的破坏速度**挑工具✗（★不再靠方块名匹配✓★）
        #     ＋ ★按玩家语义掉战利品✗★（★`dig_contract` D0~D4 全过 ✓ 见 §79 ✓★）
        #   ★口径✗★：★"成没成"**只看回执里的世界真值**✗（`now=air` ✓）✗ 不听自述（P164 ✓）★
        try:
            _rt = ch.cmd("execute as %s at %s run dshdig %d %d %d" % (bot, bot, x, y, z),
                         timeout=120.0, allow_str=True)
            _txt = str(_rt.text() or "")
        except Exception as _e:
            _txt = "ERR:%s" % type(_e).__name__
        if "now=air" in _txt:
            res["harvested"] += 1
        else:
            res["failed"].append({"at": [x, y, z], "why": "收割：" + _txt[:110]})
            continue
        if not replant or seed_slot is None:
            continue
        # 补种：① 把种子拿在手上 ✓ ② 对着**下方那格耕地**用一次 ✓
        if not held_ok:
            h = call(ch, "hold_item", {"bot": bot, "item": "wheat_seeds"})
            held_ok = "seeds" in str(h.get("held_item", ""))
            if not held_ok:
                res["failed"].append({"at": [x, y, z], "why": "拿不住种子：" + str(h)[:90]})
                continue
        # ★走模组那条"真人服务端路径"★（`/dshuse` ✓ 已验收播种 ✓ 见模组文档 §6.3 ✓）
        out = _mod_bot(ch, bot, "dshuse %d %d %d up" % (x, y - 1, z))
        if out.startswith("dshuse"):
            res["planted"] += 1
        else:
            res["failed"].append({"at": [x, y, z], "why": "补种：" + out[:110]})

    # ④ 顺手补**本来就空着**的耕地 ✓（= replant.py 那件事 ✓ 一个作业里做完 ✓）
    if replant and seed_slot is not None:
        farm = _snapshot(ch, box, match="farmland")
        fc = farm.get("cells") or []
        empty = []
        if fc:
            xs = [int(c["x"]) for c in fc]
            ys = [int(c["y"]) for c in fc]
            zs = [int(c["z"]) for c in fc]
            above = _snapshot(ch, {"x0": min(xs), "y0": min(ys) + 1, "z0": min(zs),
                                   "x1": max(xs), "y1": max(ys) + 1, "z1": max(zs)},
                              maxcells=2000)
            occ = {(int(c["x"]), int(c["y"]), int(c["z"])) for c in (above.get("cells") or [])}
            empty = [c for c in fc if (int(c["x"]), int(c["y"]) + 1, int(c["z"])) not in occ]
        res["empty_farmland"] = len(empty)
        for c in empty:
            x, y, z = int(c["x"]), int(c["y"]), int(c["z"])
            g = go_to(ch, bot, x, y + 1, z, ms=4000, exact=True)
            res["walks"] += 1
            if g.get("used_tp"):
                res["tp_fallbacks"] += 1
                res["failed"].append({"at": [x, y, z], "why": "空耕地走位失败⇒兜底 tp：" + str(g.get("why"))[:80]})
            if not held_ok:
                h = call(ch, "hold_item", {"bot": bot, "item": "wheat_seeds"})
                held_ok = "seeds" in str(h.get("held_item", ""))
                if not held_ok:
                    break
            out = _mod_bot(ch, bot, "dshuse %d %d %d up" % (x, y, z))
            if out.startswith("dshuse"):
                res["planted"] += 1
            else:
                res["failed"].append({"at": [x, y, z], "why": "空耕地补种：" + out[:110]})
        stage("replant", "空耕地 %d 块 ⇒ 补种后累计种下 %d 株" % (len(empty), res["planted"]))

    # ⑤ 自证（**世界真值 ＋ 背包真值** ✗ 不听自述 ✗）
    after = _snapshot(ch, box, match="wheat")
    wheat_now = len(after.get("cells") or [])
    # ⚠ 解析背包**必须用现成的解析器** ✗ —— 我第一版在这里手搓了个 `partition("x")` ✗
    #   而 `dshinv list` 的每一项是 `槽号:物品id x数量`（如 `0:minecraft:wheat_seedsx62`）✗
    #   ⇒ 手搓版切出来的名字是 `"0:minecraft:wheat_seeds"` ✗
    #     `startswith("minecraft:")` **恒为假** ✗ ⇒ tally 永远是空的 ✗
    #   ⇒ 自证输出"背包：小麦 0 ✓ 种子 0 ✓" ✗ —— **作业其实干对了 ✓ 报数报错了 ✗**
    #     ★这正是本项目最恨的一类：看起来有自证 ✗ 其实自证是坏的 ✗（同 N1：把失败的返回值当数据 ✗）★
    #   ⇒ 修法：复用 `inv_guard.parse_list` ✓ 全项目**一个解析器** ✓（已在多处验证过 ✓）
    items, _used, _txt = inventory(ch, bot)
    tally: dict = {}
    for _slot, name, cnt in items:
        tally[name] = tally.get(name, 0) + int(cnt)
    res["wheat_after"] = wheat_now
    res["wheat_seeds"] = tally.get("minecraft:wheat_seeds", 0)
    res["wheat"] = tally.get("minecraft:wheat", 0)
    res["inventory_kinds"] = len(tally)
    res["inventory_items"] = sum(tally.values())
    res["elapsed"] = round(time.time() - t0, 2)
    # 判"成没成"✗：**收了 ≥1 株** 或 **本来就没得收**（空田也是正常收工 ✓）都算 ok ✓
    #   ⇒ 而"补种失败"只降级为**如实记录** ✗ 不谎报成功 ✓ 也不谎报失败 ✓
    res["ok"] = (res["harvested"] > 0 or res["ripe"] == 0) and not any(
        str(f.get("why", "")).startswith("收割") for f in res["failed"])
    if res["ripe"] == 0:
        res["why"] = ("没有成熟的庄稼 ✓ 不需要收割（重扫 %d 株 ✓ 都在长 ✓）" % wheat_now)
    else:
        res["why"] = res["why"] or ("收下 %d 株 ✓ 种下 %d 株 ✓ 失败 %d 处"
                                    % (res["harvested"], res["planted"], len(res["failed"])))
    # ★ 走位账目 ✓（v2.6 ✓）：**用脚走了几次 ✓ 有几次兜底瞬移了** ✗ —— 必须如实报 ✗
    res["why"] += " ｜ 走位 %d 次（其中**兜底 tp %d 次** ✗）" % (res["walks"], res["tp_fallbacks"])
    stage("verify", "重扫小麦 %d 株 ✓ ｜ 背包：小麦 %d ✓ 种子 %d ✓"
          % (wheat_now, res["wheat"], res["wheat_seeds"]))
    return res


# --------------------------------------------------------------------------- #
# 作业：筛矿（★P16 的正解★：**用 `/dshuse` 显式指定 `up` 面** ✗ 不再依赖准星 ✓）
# --------------------------------------------------------------------------- #

def sift_job(ch: Channel, x: int, y: int, z: int, uses: int = 16, bot: str = "Bot",
             item: str = "minecraft:gravel", verbose: bool = True) -> dict:
    """★一条作业★：把"走到筛子前 → 确认能筛 → 一下一下筛 → 用世界真值自证"打包 ✓

    为什么必须是"作业"而不是"再调一次 `sift`"✗（每一条都踩过 ✓）：
      ① **背包守卫**（纪律⑤ ✓）：产出接不住就等于白干 ✗（P19.1 ✓）
      ② **网没装 ⇒ 直接拒绝** ✗：没网筛不出东西 ✓ 而它**一声不响** ✗
      ③ **原料不够 ⇒ 直接拒绝** ✗（沙砾要从"石砾→圆石→锤子砸"那条链来 ✓ 见文档 ✓）
      ④ **站位用脚走** ✓（v2.6 ✓ 走不到才兜底 tp ✓ 且记账 ✓）
      ⑤ ★**打哪个面是显式参数**★ ✗ —— 这一步是本作业存在的**根本理由** ✓：
         P16 实测：打**侧面**时 `use` 每一下都回 `success:true` ✓ 而筛子 NBT **一个字节不变** ✗✗
         ⇒ 旧路（靠准星）**能不能筛全看站位** ✗ ⇒ 而 `/dshuse <pos> up` 把面**钉死** ✓
      ⑥ 每一下都用**筛子自己的 NBT** 判（`progress` 归零 ＋ `contents` 消失 ＝ 真成了 ✓）✗
         —— 不听"指令成功"那句话 ✗（P16 就是被那句话骗了 ✓）
    """
    t0 = time.time()
    res: dict = {"ok": False, "x": int(x), "y": int(y), "z": int(z), "uses": 0,
                 "chunks": {}, "gravel_before": 0, "gravel_after": 0,
                 "effect_seen": False, "walks": 0, "tp_fallbacks": 0,
                 "failed": [], "stages": [], "why": ""}

    def stage(name: str, note: str = "") -> None:
        res["stages"].append({"stage": name, "t": round(time.time() - t0, 2), "note": note})
        if verbose and note:
            print("[作业 %-12s] %s" % (name, note))

    # ① 背包守卫 ✓
    g = ensure_free(ch, bot=bot, need=2, auto=True, verbose=verbose)
    res["guard"] = {"ok": g.get("ok"), "free": g.get("free"), "stashed": g.get("stashed")}
    stage("guard", "空位 %s" % g.get("free"))
    if not g.get("ok"):
        res["why"] = "背包守卫不放行：%s" % (g.get("why") or "空位不足")
        return res

    # ② 筛子真值：是不是筛子 ✓ 装了网没有 ✓（都是**读方块状态 ＋ NBT** ✓ 不是猜 ✓）
    st = ch.verify_block(int(x), int(y), int(z))
    txt = json.dumps(st, ensure_ascii=False)
    res["sieve_state"] = txt[:400]
    if "sieve" not in txt:
        res["why"] = "(%d,%d,%d) 不是筛子 ✗ 真值：%s" % (x, y, z, txt[:200])
        stage("check", res["why"])
        return res
    has_mesh = "mesh" in txt
    res["has_mesh"] = has_mesh
    # ★筛子里**已经装着料**也算"有料"★ ✗（2026-09-19 深夜实测 ✓）：
    #   现象 ✓：第一次按下去只是把沙砾**装进筛子**（NBT 出现 `contents` ✓）而 progress 仍是 0.0 ✗
    #   ⇒ 那之后**背包里没有沙砾了** ✗ 可我明明"还有料"（在筛子里 ✓）
    #   ⇒ 所以我第一版的"背包里没有就拒绝"✗ 会把**正干到一半的活**判成不能干 ✗
    loaded = ("contents" in txt) and (item.split(":")[-1] in txt)
    res["sieve_loaded"] = loaded
    stage("check", "筛子 ✓ 网：%s ✓ 筛子里已有料：%s"
          % ("已装" if has_mesh else "**没装** ✗", "是 ✓" if loaded else "否"))
    if not has_mesh:
        res["why"] = ("筛子没装网 ✗ ⇒ **拒绝开工** ✓（没网筛不出东西 ✓ 而且它**一声不响** ✗ —— "
                      "先 install_mesh ✓）")
        return res

    # ③ 原料：手里/背包里得有**要筛的东西** ✓
    #   ★v1 我把它写死成 gravel ✗ ⇒ 一查配方就知道错了 ✓★：
    #     筛子能筛的不止沙砾 ✓ —— Ex Deorum 里**泥土**也能筛 ✓ 而且只有**泥土**才出
    #     `exdeorum:stone_pebble` ✓（4 个 → 原石 ✓ 原石 → 锤子 → 沙砾 ✓）
    #     ⇒ 所以"筛什么"必须是**参数** ✗ 不能写死 ✓
    items, _used, _t = inventory(ch, bot)
    stock = sum(c for _s, i, c in items if i == item)
    res["item"] = item
    res["gravel_before"] = stock
    stage("stock", "背包 %s %d" % (item, stock))
    if stock <= 0 and not loaded:
        res["why"] = ("背包里**没有 %s** ✗ ⇒ 拒绝开工 ✓。来源提示："
                      "泥土（岛上到处是 ✓）→ 筛 → `stone_pebble` → 4 个合成**原石** → "
                      "锤子砸 → 沙砾 → 再筛 → 矿物碎块 ✓" % item)
        return res

    # ④ 走到够得着（**用脚走** ✓）
    w = go_to(ch, bot, int(x), int(y), int(z), ms=8000, exact=False)
    res["walks"] += 1
    if w.get("used_tp"):
        res["tp_fallbacks"] += 1
        res["failed"].append({"at": [x, y, z], "why": "走位失败⇒兜底 tp：" + str(w.get("why"))[:80]})
    stage("walk", "走位：%s（兜底 tp＝%s）" % (w.get("at", "?"), w.get("used_tp")))

    # ⑤ 拿着要筛的东西 ✓
    #   ★先把它挪进快捷栏★ ✗ —— 实测栽过两次 ✓（diorite ✓ 锤子 ✓）：
    #     Lua 的 `hold_item` **只翻快捷栏**（0..8）✗ 而物品常在主背包（9..35）✗
    #     ⇒ 回执是"快捷栏里没有含 X 的物品"✗ —— 看着像"没这东西"✗ 其实是"没拿在手上"✗
    #   ★"料在筛子里"时**不用找料** ✗ —— 只要**接着按** ✓（手上的东西不影响继续推进 ✓）
    slot = ensure_in_hotbar(ch, bot, item) if not (stock <= 0 and loaded) else None
    if slot is None and not (stock <= 0 and loaded):
        res["why"] = ("%s 不在身上 ✗（背包与快捷栏里都没有）⇒ 拒绝开工 ✓" % item)
        stage("hold", res["why"])
        return res
    if stock <= 0 and loaded:
        stage("hold", "料在**筛子里** ✓ ⇒ 直接接着按（手不必拿料 ✓）")
    else:
        h = call(ch, "hold_item", {"bot": bot, "item": item})
        if item.split(":")[-1] not in str(h.get("held_item", "")):
            res["why"] = "%s 拿不到手上 ✗（槽 %s）：%s" % (item, slot, str(h)[:150])
            stage("hold", res["why"])
            return res
        stage("hold", "主手：%s（快捷栏槽 %s ✓）" % (h.get("held_item"), slot))

    # ⑥ 一下一下筛 ✓ ★**每一下都用世界真值判"这一下到底吃没吃料"**★ ✗（P16 的解药 ✓）
    #
    # 判据怎么选 ✗（这里我改过一稿 ✓ 第一稿是错的 ✗）：
    #   我第一稿想用"筛子 NBT 里有没有 `progress`"判 ✗ —— **不行** ✗：
    #     筛成的**那一刻** `progress` 正好归零 ✓ 且 `contents` 消失 ✓ ⇒ 快照**看起来像空的** ✗
    #     ⇒ 会把"筛成了"判成"没效果" ✗（同族：P22/N1 把中间态当结论 ✗）
    #   ⇒ 改用**两件最硬的事** ✓：
    #     ① 筛子**吃掉了沙砾**（每成一下必耗 1 ✓）—— 沙砾数不变 ＝ 这一下什么都没发生 ✗
    #     ② 背包里**多了碎块/矿物**（＝真正的产出 ✓）
    #   两件都是**背包真值** ✓ 一条 `dshinv list` 就能读到 ✓（比读 NBT 还便宜 ✓）
    items_now, _u0, _t0 = inventory(ch, bot)
    gravel_pre = sum(c for _s, i, c in items_now if i == item)
    chunks_pre = {i: c for _s, i, c in items_now
                  if ("chunk" in i or "_ore" in i or "pebble" in i)}
    no_effect = 0
    last_txt = ""
    last_prog = -1.0
    for k in range(int(uses)):
        out = _mod_bot(ch, bot, "dshuse %d %d %d up 0.15" % (int(x), int(y), int(z)), 60.0)
        res["uses"] += 1
        if not out.startswith("dshuse"):
            res["failed"].append({"at": [x, y, z], "why": "dshuse 第 %d 下：%s" % (k + 1, out[:110])})
            break
        # ★★必须**一下一下**来 ✗ 而且要给它时间 ★★（2026-09-19 深夜实测更正 ✓）
        #   我第一次写成"密排连按 + 看背包少了就算成"✗ ⇒ 结论完全错 ✗：
        #     第一下只是把料**装进筛子**（NBT 出现 `contents` ✓）而 `progress` 还是 0.0 ✗
        #     —— 我把"装料"当成了"筛完"✗（同族：P22/N1 把中间态当结论 ✗）
        #   文档里那条**验证过的**用法是 `use interval 1` 连按 6 秒 ✓
        #   ⇒ 所以：**每次按完等 1 秒** ✓ 而且判据只看**筛子真值**（contents 消失 ✓ progress 动过 ✓）
        time.sleep(1.0)
        if k % 3 == 2 or k == int(uses) - 1:
            st2 = ch.verify_block(int(x), int(y), int(z))
            txt2 = json.dumps(st2, ensure_ascii=False)
            items_now, _u0, _t0 = inventory(ch, bot)
            chunks_now = {i: c for _s, i, c in items_now
                          if ("chunk" in i or "_ore" in i or "pebble" in i)}
            gained_now = {i: chunks_now.get(i, 0) - chunks_pre.get(i, 0)
                          for i in set(list(chunks_now) + list(chunks_pre))
                          if chunks_now.get(i, 0) - chunks_pre.get(i, 0) > 0}
            if gained_now or ("contents" not in txt2):
                res["effect_seen"] = True
                no_effect = 0
            else:
                # ★★第三条判据：**`progress` 在变**也算"有进展"★★ ✗
                #   实测教训 ✓（就在刚才 ✗）：我只认"碎块进背包 ✓ 或 `contents` 消失 ✓"
                #   ⇒ 而筛矿**就是这样一段一段涨的** ✓（实测 0.0 → 0.8 ✓ 每一按约 +0.1 ✓）
                #   ⇒ 结果我在 **progress 0.8、就差两下** 的时候判了"没效果"✗ 然后停手 ✗✗
                #   ⇒ 同族：P22/N1（把**中间态**当成结论 ✗）；本条记进错题本 **P28** ✓
                mp = re.search(r"progress:\s*([0-9.]+)", txt2)
                prog = float(mp.group(1)) if mp else -1.0
                if prog >= 0 and abs(prog - last_prog) > 1e-6:
                    res["effect_seen"] = True
                    res["progress_seen"] = prog
                    no_effect = 0
                else:
                    no_effect += 1
                last_prog = prog
            last_txt = txt2
            if no_effect >= 3:
                res["why"] = ("连着三批**筛子真值一点没动** ✗（既没有 `contents` 消失 ✓ "
                              "也没有碎块进背包 ✓）⇒ 停手 ✓ 最后真值：%s" % txt2[:220])
                break
        items_now, _u0, _t0 = inventory(ch, bot)
        gravel_now = sum(c for _s, i, c in items_now if i == item)
        gravel_pre = gravel_now
        if gravel_now <= 0 and not res["effect_seen"]:
            # 料进了筛子（＝`contents`）也走这条路 ✓ ⇒ **别停** ✗ 要继续按 ✓
            st3 = ch.verify_block(int(x), int(y), int(z))
            if "contents" not in json.dumps(st3, ensure_ascii=False):
                stage("stock", "手上与筛子里都没有料了 ✓ 停手")
                break
    if last_txt:
        res["sieve_after"] = last_txt

    # ⑦ 自证：碎块实增 ✓ 沙砾实耗 ✓ 筛子最终 NBT ✓
    items3, _u3, _t3 = inventory(ch, bot)
    after_inv = dict((i, c) for _s, i, c in items3)
    before_inv = dict((i, c) for _s, i, c in items)
    gained = {k2: after_inv.get(k2, 0) - before_inv.get(k2, 0)
              for k2 in set(list(before_inv) + list(after_inv))
              if after_inv.get(k2, 0) - before_inv.get(k2, 0) > 0}
    lost = {k2: before_inv[k2] - after_inv.get(k2, 0) for k2 in before_inv
            if before_inv[k2] > after_inv.get(k2, 0)}
    res["gravel_after"] = after_inv.get(item, 0)
    res["lost"] = lost
    res["elapsed"] = round(time.time() - t0, 2)
    chunks = {k2: v for k2, v in gained.items() if "chunk" in k2 or "ore" in k2 or "pebble" in k2}
    res["ok"] = bool(chunks) or bool(res["effect_seen"])
    res["why"] = res["why"] or ("筛了 %d 下 ✓ 产出实增：%s ｜ %s %d → %d ｜ 走位 %d 次（兜底 tp %d ✗）"
                                % (res["uses"],
                                   "，".join("%s×%d" % t for t in chunks.items()) or "（无 ✗）",
                                   item,
                                   res["gravel_before"], res["gravel_after"],
                                   res["walks"], res["tp_fallbacks"]))
    stage("verify", res["why"])
    return res


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "list"):
        print(__doc__)
        return 2
    job = argv[0]
    if job not in ("harvest", "harvest_and_replant", "sift"):
        print("[X] 没有这个作业：%s（只有 harvest ✓ sift ✓）" % job)
        return 2
    a, i = {}, 1
    while i < len(argv):
        k = argv[i].lstrip("-")
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            a[k] = argv[i + 1]
            i += 2
        else:
            a[k] = True
            i += 1
    ch0 = Channel(who=a.get("who", "cmd0"))
    bot0 = a.get("bot", "Bot")
    if job == "sift":
        if not all(k in a for k in ("x", "y", "z")):
            print("用法：py agent/jobs.py sift --x 4127 --y 71 --z 11 [--uses 16]")
            return 2
        r = sift_job(ch0, int(a["x"]), int(a["y"]), int(a["z"]),
                     uses=int(a.get("uses", 16)), bot=bot0)
        print("-" * 70)
        print("作业结果：%s ｜ %s" % ("成功 ✓" if r.get("ok") else "**失败 ✗**", r.get("why")))
        for f in r.get("failed", [])[:8]:
            print("   ✗ %s" % json.dumps(f, ensure_ascii=False)[:160])
        print("   自证：碎块 %s ｜ 沙砾 %s → %s ｜ 筛子 %s"
              % (json.dumps(r.get("chunks", {}), ensure_ascii=False),
                 r.get("gravel_before"), r.get("gravel_after"),
                 str(r.get("sieve_after") or r.get("sieve_state"))[:160]))
        return 0 if r.get("ok") else 1
    if not all(k in a for k in ("x0", "y0", "z0", "x1", "y1", "z1")):
        print(__doc__)
        return 2
    box = {k: int(a[k]) for k in ("x0", "y0", "z0", "x1", "y1", "z1")}
    bot = a.get("bot", "Bot")
    replant = not a.get("no-replant")
    ch = Channel(who=a.get("who", "cmd0"))
    r = harvest_and_replant(ch, box, bot=bot, replant=bool(replant))
    print("-" * 70)
    print("作业结果：%s" % ("成功 ✓" if r["ok"] else "**失败 ✗**"))
    print("  %s" % r["why"])
    for f in r["failed"][:8]:
        print("  ✗ %s" % json.dumps(f, ensure_ascii=False)[:160])
    print("  自证：小麦 %d 株 ｜ 背包 小麦 %d ／ 种子 %d ｜ 用时 %ss"
          % (r.get("wheat_after", -1), r.get("wheat", -1), r.get("wheat_seeds", -1),
             r.get("elapsed")))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
