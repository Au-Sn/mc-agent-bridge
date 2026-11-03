#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
world.py — 感知层：把"假人现在所处的世界"压缩成模型能读、且读得准的一段文本

为什么单独一层：
  大模型看不到屏幕。给它一段 Goodhart 式的自述（"我已经在挖矿了"）就是喂幻觉。
  这一层的职责只有一个：**只放可从权威来源核实的事实**。
  来源有三类：
    a) 服务端权威：命令计算机执行 data get ... / execute ... （真假人、真方块）
    b) 周边扫描：survey / geoScanner（方块清单）
    c) 聊天气泡：游戏日志 latest.log（别人说了什么）

刻意不做的事：
  - 不猜小地图（假人没有小地图；要看地图就读 region 文件生成 PNG，见 tools/mca_map.py）
  - 不把"动作自述"当事实（place_at 曾经在方块落到邻格时报告 placed:false，已记录在错题本）

用法：
    py agent/world.py            # 打印一次完整快照（只读，不下发任何改变世界的指令）
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channel import Channel, BridgeError, _extract_items  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

import paths as PA                     # noqa: E402（channel 已把 tools/ 加进 sys.path）

# ★这里**不写死本机路径**✗★：没配 dsh.env/环境变量 ⇒ `NotConfigured` 直接抛（明确报错）
GAME_DIR = PA.require_home()
LATEST_LOG = PA.LATEST_LOG

# 值得单独提示模型的方块：能用的设施、危险物、可采集资源
NOTABLE = {
    "facility": ["crafting_table", "furnace", "chest", "barrel", "anvil", "hopper",
                 "sieve", "barrel", "campfire", "bed", "enchanting_table",
                 "computercraft", "advancedperipherals", "sophisticatedstorage",
                 "create:", "mekanism:", "immersiveengineering:", "ae2:", "exdeorum:"],
    "danger": ["lava", "fire", "magma", "cactus", "sweet_berry", "powder_snow", "void"],
    "resource": ["_log", "_leaves", "gravel", "sand", "dirt", "stone", "cobblestone",
                 "ore", "clay", "water", "_sapling"],
}

CHAT_RE = re.compile(r"^\[[^\]]*\]\s*(?:\[[^\]]*\]\s*)*<([A-Za-z0-9_]{2,16})>\s*(.*)$")


def _classify(name: str) -> str | None:
    n = name.lower()
    for kind, pats in NOTABLE.items():
        for p in pats:
            if p in n:
                return kind
    return None


# --------------------------------------------------------------------------- #
# 解析服务端回传。**绝对不要靠英文短语定位**：
#   - 服务端可能是中文（本地化后那句 "has the following entity data:" 会变成中文）
#   - CC 终端渲染不了 CJK，中文会整段变成 '?'
# 所以只能按数值本身的形状来认。
# --------------------------------------------------------------------------- #

def _first_line_of(r) -> str:
    ls = r.lines()
    return ls[0] if ls else ""


def _last_number(txt: str, float_hint: bool = False) -> float | None:
    pat = r"(-?\d+(?:\.\d+)?)f" if float_hint else r"(-?\d+(?:\.\d+)?)"
    m = re.findall(pat, txt or "")
    if not m:
        return None
    try:
        return float(m[-1])
    except ValueError:
        return None


def _slot_of(it: dict) -> int | None:
    """把物品字典里的槽位解析成整数。

    为什么要单独写：NBT 里是 `5b`（带类型后缀）✓ 别的视图可能是纯数字 5 ✓
    或者字符串 "5b" ✓ —— 写死字符串比较会在某个视图上静默失配 ✗ 然后给出错答案 ✗。
    """
    raw = it.get("slot", it.get("Slot"))
    if raw is None:
        return None
    m = re.search(r"-?\d+", str(raw))
    return int(m.group(0)) if m else None


def _cmd_success(r) -> bool:
    """指令是否真的成功 —— 以 commands.exec 的 success 为准，而不是看回传文本里有没有某个词。"""
    res = r.result
    if isinstance(res, dict):
        return bool(res.get("success", r.ok))
    return bool(r.ok)


class World:
    def __init__(self, ch: Channel, bot: str = "Bot"):
        self.ch = ch
        self.bot = bot

    # -- 自身 ---------------------------------------------------------------- #

    def status(self, timeout: float = 25.0) -> dict:
        """机器侧自述（生命/饥饿/位置/朝向…）：只作为线索，不作为证据。"""
        try:
            return self.ch.call("status", timeout=timeout, allow_str=True).as_dict()
        except BridgeError:
            return {}

    def pos(self, timeout: float = 25.0) -> tuple[float, float, float] | None:
        """权威坐标：直接问服务端要实体 NBT。"""
        try:
            r = self.ch.cmd("data get entity %s Pos" % self.bot, timeout=timeout, allow_str=True)
        except BridgeError:
            return None
        txt = json.dumps(r.result, ensure_ascii=False)
        m = re.search(r"\[\s*(-?\d+(?:\.\d+)?)d?,\s*(-?\d+(?:\.\d+)?)d?,\s*(-?\d+(?:\.\d+)?)d?\s*\]", txt)
        return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None

    def vitals(self, timeout: float = 45.0) -> dict:
        """生命 / 饥饿 / 是否在线。反射层每次心跳都要用，所以只发两条指令。"""
        out = {"alive": False, "health": None, "food": None}
        try:
            r = self.ch.cmd("data get entity %s Health" % self.bot, timeout=timeout, allow_str=True)
        except BridgeError:
            return out
        if not _cmd_success(r):
            return out                       # 指令失败 = 实体不存在（比解析文本可靠得多）
        hp = _last_number(_first_line_of(r), float_hint=True)
        if hp is None:
            return out
        out["health"] = hp
        out["alive"] = hp > 0
        try:
            r2 = self.ch.cmd("data get entity %s foodLevel" % self.bot, timeout=timeout, allow_str=True)
            if _cmd_success(r2):
                f = _last_number(_first_line_of(r2))
                if f is not None:
                    out["food"] = int(f)
        except BridgeError:
            pass
        return out

    def inventory(self, timeout: float = 30.0) -> list[dict]:
        return self.ch.inventory(self.bot, timeout=timeout)

    def counts(self, inv: list[dict] | None = None) -> dict[str, int]:
        """背包计数。**必须按 (槽位, 物品名) 去重** ✗

        实测：`bot_inv` 会把同一件物品从多个视图重复返回 ✓
        （给 64 个木板报成 128 ✓ 只有 1 把斧头报成 2 ✗）→ 不去重会让
        "材料够不够"的判断直接算错 ✓ 这类"看起来合理的错数字"最危险 ✓
        去重键同时含槽位与名字，避免把真的分占两个槽的同种物品合并掉 ✓
        """
        inv = self.inventory() if inv is None else inv
        out: dict[str, int] = {}
        seen: set = set()
        for it in inv:
            name = str(it.get("name") or it.get("id") or "?")
            slot = _slot_of(it)
            if slot is not None:
                key = (slot, name)
                if key in seen:
                    continue
                seen.add(key)
            cnt = it.get("count", it.get("Count", 1))
            try:
                cnt = int(cnt)
            except Exception:
                cnt = 1
            out[name] = out.get(name, 0) + cnt
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def selected_slot(self, timeout: float = 30.0) -> int | None:
        """读玩家**选中的快捷栏格**（权威字段 SelectedItemSlot）。

        为什么必须问服务端：主手会随"选定槽位"变化 ✓
        曾经把主手槽位写死成 5 ✗ → 既漏报又误报 ✓（真实发生过：附魔因此没生效 ✓）。
        """
        try:
            r = self.ch.cmd("data get entity %s SelectedItemSlot" % self.bot,
                            timeout=timeout, allow_str=True)
        except BridgeError:
            return None
        if not _cmd_success(r):
            return None
        v = _last_number(_first_line_of(r))
        return int(v) if v is not None else None

    @staticmethod
    def _held_from(inv: list[dict], slot: int | None = None) -> str | None:
        """按选定槽位取主手物品。槽位拿不到就退回"第一个快捷栏物品"（0..8）✓"""
        for it in inv or []:
            s = _slot_of(it)
            if s is None:
                continue
            if slot is not None:
                if s == slot:
                    return str(it.get("name") or it.get("id"))
            elif 0 <= s <= 8:
                return str(it.get("name") or it.get("id"))
        return None

    def held(self, timeout: float = 30.0) -> str | None:
        return self._held_from(self.inventory(timeout=timeout),
                               self.selected_slot(timeout=timeout))

    def held_verified(self, timeout: float = 30.0) -> tuple:
        """返回 (主手物品, 是否可信) —— 读不到 SelectedItemSlot 时可信度为 False ✓"""
        inv = self.inventory(timeout=timeout)
        slot = self.selected_slot(timeout=timeout)
        return self._held_from(inv, slot), slot is not None

    # -- 周边 ---------------------------------------------------------------- #

    def survey(self, radius: int = 6, timeout: float = 60.0, only: str | None = None,
               center: tuple | None = None) -> dict:
        """方块扫描。

        radius 越大越慢（要分块批量查 + 逐格统计），先用 6 保证反应速度。
        `only` 是只查某一类方块（Lua 侧支持），**正因为筛了类别，才敢用大半径搜"东西在哪"** ✓
        `center` 是**扫描中心**（默认用假人当前位置 ✓）。
        —— 为什么必须能指定中心 ✗：Lua 把半径**钳到 12** ✓
        所以"搜索比 12 格更大的范围"的唯一办法就是**换中心多扫几次** ✓✓
        （真实用途：找那个能救活整条链的工作台 ✓）
        """
        known = self.ch.action_args("survey") or {}
        args: dict = {}
        if "radius" in known:
            args["radius"] = radius
        elif "r" in known:
            args["r"] = radius
        if only and "only" in known:
            args["only"] = only
        if "x" in known:
            p = center if center is not None else self.pos()
            if p:
                args.update({"x": int(p[0]), "y": int(p[1]), "z": int(p[2])})
        try:
            return self.ch.call("survey", args, timeout=timeout, allow_str=True).as_dict()
        except BridgeError:
            return {}

    def entities(self, radius: int = 24, limit: int = 8, timeout: float = 30.0,
                 with_nbt: bool = False) -> list[dict]:
        """附近非玩家实体：先拿 id（判断是不是敌对），再拿坐标。

        ⚠ 这里过去用**英文短语** `entity data:` 去定位返回值 ✗ —— 而**服务端是中文** ✓
          那句话会被本地化 ✓ 于是正则**永不匹配** ✗ → 静默返回空列表 ✗✗
          （后果：明明旁边站着一只实体 ✓ `perceive` 却一直报"附近实体：无" ✗ —— 这和错题本 F2 是同一类病 ✓）
        现在改成**按形状解析** ✓：只认"带引号的命名空间 id"（`"minecraft:xxx"` ✓ ASCII ✓ 与语言无关 ✓）
        """
        out: list[dict] = []
        # ⚠ tag=!dsh_jade：排除"准星 HUD"那个悬浮文字实体 ✓
        #   它是**实体** ✗ 会进 @e 选择器 ✗ —— 不排除的话"最近的实体"永远是它 ✓
        #   （后果：`perceive` 报告旁边有东西 ✓ 而实际上什么都没有 ✓ = 假阳性 ✗）
        sel = "@e[distance=..%d,type=!player,type=!item,tag=!dsh_jade,limit=%d]" % (radius, limit)
        # ⚠ 关于"实体类型"的一个重要实测 ✗：`data get entity @s id` **不是合法路径** ✗
        #   实测直接 `success: false` ✓（我为它白排查了一轮 ✓）
        #   → 所以这里**只取坐标** ✓（`Pos` 查询实测可用 ✓ 一次能回 8 个实体的坐标 ✓✓）
        #   想把类型也拿到 ✓ 得取**完整 NBT**：`data get entity @s` ✓ 里含 `id: "minecraft:xxx"` ✓
        #   （会长 ✓ 所以只在 with_nbt=True 时才取 ✓）
        try:
            r2 = self.ch.cmd("execute as %s run data get entity @s Pos" % sel,
                             timeout=timeout, allow_str=True)
            poss = re.findall(r"\[\s*(-?\d+(?:\.\d+)?)d?,\s*(-?\d+(?:\.\d+)?)d?,\s*(-?\d+(?:\.\d+)?)d?\s*\]",
                              " ".join(r2.lines()))
        except BridgeError:
            poss = []

        ids: list[str] = []
        if with_nbt and poss:
            try:
                r3 = self.ch.cmd("execute as %s run data get entity @s" % sel,
                                 timeout=timeout, allow_str=True)
                # NBT 里的 id 是 ASCII ✓ 与界面语言无关 ✓
                ids = re.findall(r'id:\s*"([a-z0-9_]+:[a-z0-9_/]+)"', " ".join(r3.lines()))
            except BridgeError:
                ids = []
        if not ids:
            ids = ["?"] * len(poss)
        for i, name in enumerate(ids):
            p = poss[i] if i < len(poss) else None
            out.append({"id": name, "pos": [float(x) for x in p] if p else None,
                        "hostile": any(k in name for k in (
                            "zombie", "skeleton", "spider", "creeper", "slime", "witch",
                            "enderman", "pillager", "vindicator", "blaze", "ghast",
                            "phantom", "drowned", "husk", "stray", "silverfish", "piglin"))})
        return out

    def chat(self, lines: int = 12) -> list[str]:
        """从游戏日志里读玩家聊天。假人没有小地图也没有聊天窗口，这是唯一的"听见"途径。"""
        if not LATEST_LOG.is_file():
            return []
        try:
            with open(LATEST_LOG, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.readlines()[-400:]
        except OSError:
            return []
        out: list[str] = []
        for ln in raw:
            m = CHAT_RE.match(ln.strip())
            if m:
                out.append("<%s> %s" % (m.group(1), m.group(2).strip()))
        return out[-lines:]

    # -- 汇总 ---------------------------------------------------------------- #

    def snapshot(self, survey_radius: int = 6, with_entities: bool = True) -> dict:
        inv = self.inventory()
        slot = self.selected_slot()
        snap = {
            "pos": self.pos(),
            "vitals": self.vitals(),
            "inventory": self.counts(inv),
            "held": self._held_from(inv, slot),
            "held_slot": slot,
            "machine_status": self.status(),
            "survey": self.survey(survey_radius),
        }
        if with_entities:
            snap["entities"] = self.entities()
        snap["chat"] = self.chat()
        return snap

    def text(self, survey_radius: int = 6) -> str:
        """给模型看的紧凑文本。宁可短，也不要塞进无用的原始 JSON。"""
        s = self.snapshot(survey_radius)
        L: list[str] = []
        p = s["pos"]
        L.append("位置：%s" % ("(%.1f, %.1f, %.1f)" % p if p else "未知（假人可能不在线）"))
        v = s["vitals"]
        L.append("状态：生命=%s 饥饿=%s %s"
                 % (v.get("health"), v.get("food"), "" if v.get("alive") else "【不在线/已死】"))
        inv = s["inventory"]
        if inv:
            L.append("背包：" + "，".join("%s×%d" % (k.split(":")[-1], n) for k, n in list(inv.items())[:18]))
        else:
            L.append("背包：空")
        L.append("主手：%s" % (s["held"] or "未知"))

        # 方块扫描：按用途分类，只报数量前若干项
        by: dict = {}
        for k, val in (s["survey"].get("by_name") or s["survey"].get("counts") or {}).items():
            if isinstance(val, int) and val > 0:
                by[k] = val
        if by:
            cats: dict[str, list[str]] = {}
            for name, n in by.items():
                c = _classify(name) or "other"
                cats.setdefault(c, []).append("%s×%d" % (name.split(":")[-1], n))
            for c in ("facility", "resource", "danger", "other"):
                if c in cats:
                    L.append("%s：%s" % ({"facility": "设施", "resource": "资源",
                                          "danger": "危险", "other": "其他"}[c],
                                         "，".join(sorted(cats[c])[:14])))
        else:
            L.append("方块扫描：无数据")

        ents = s.get("entities") or []
        if ents:
            L.append("附近实体：" + "，".join(
                "%s%s%s" % (e["id"].split(":")[-1], "【敌对】" if e.get("hostile") else "",
                            ("@%s" % e["pos"]) if e.get("pos") else "")
                for e in ents[:6]))
        else:
            L.append("附近实体：无（24 格内）")

        ch = s.get("chat") or []
        if ch:
            L.append("最近聊天：" + " | ".join(ch[-6:]))
        return "\n".join(L)


def main() -> int:
    ch = Channel("cmd0")
    w = World(ch)
    if not ch.alive():
        print("[!] 假人 Bot 似乎不在线（用 data get entity 查不到）")
    print(w.text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
