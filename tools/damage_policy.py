#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""damage_policy.py -- 伤害来源 → 对策（★用户口径✗★）

用户原话：
  「N7 应该**明确伤害来源** ✗ **根据伤害来源给到不同对策** ✗ 比如
   **有怪就打或跑** ✗ **窒息就上浮** ✗ **卡墙就传送出来** ✗ **饿掉血就找食物**」

本模块只回答一个问题：★"受了这个伤 ⇒ 下一步该干什么"✗★
不执行 ✗ 只给建议（★执行归模块 D 的行为库 ✗ 这里只做决策表✗★）
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

# ★来源 → (立即动作, 该做什么, 为什么)  ★数据驱动的地方：血量/食物/装备由 ctx 决定✗★
POLICY = {
    # ── 战斗类：打或跑 ────────────────────────────────────────────────
    "mob": ("fight_or_flee", "血多就打 ✗ 血少就跑", "有怪 ✗ 不能站着挨打"),
    "player": ("fight_or_flee", "同上（★对玩家优先跑 ✗ 别硬拼✗★）", "玩家仇恨"),
    "arrow": ("flee", "找掩体 ✗ 别站开阔地", "远程伤害"),
    "thorns": ("flee", "别贴那个东西", "反伤"),
    # ── 环境类：垂直/水平脱困 ──────────────────────────────────────────
    "drown": ("surface", "上浮到空气格", "★窒息就上浮★"),
    "in_wall": ("unstick", "找相邻空位挪出去（★必要时 tp ✗ 但先试挪✗★）", "★卡墙就传送出来★"),
    "cramming": ("unstick", "同上", "实体挤压 = 卡墙一族"),
    "suffocation": ("unstick", "同上", "窒息（方块里）"),
    "fall": ("step_back", "别再往高的地方跳 ✗ 记录该高度禁止再跳",
             "摔伤 ✗ 高度别再来一次"),
    "fly_into_wall": ("step_back", "别贴着飞", "撞墙"),
    # ── 火/热/冷 ─────────────────────────────────────────────────────
    "lava": ("escape_hazard", "立刻离开岩浆 ✗ 水/方块垫脚", "岩浆"),
    "fire": ("escape_hazard", "离开火源 ✗ 有水就跳水里", "着火"),
    "on_fire": ("escape_hazard", "同上", "着火"),
    "hot_floor": ("escape_hazard", "离开那一格", "烫脚"),
    "freeze": ("escape_hazard", "离开细雪/冰面", "冻伤"),
    # ── 饿 / 毒 / 魔法 ────────────────────────────────────────────────
    "starve": ("eat", "找食物吃掉（★背包没有就回箱子✗★）", "★饿掉血就找食物★"),
    "magic": ("flee", "离开源头 ✗ 别靠近", "魔法伤害"),
    "wither": ("flee", "同上", "凋零"),
    "poison": ("heal", "找牛奶/治疗", "中毒"),
    # ── 其它 ─────────────────────────────────────────────────────────
    "explosion": ("flee", "离开爆炸范围", "爆炸"),
    "lightning": ("shelter", "进屋躲", "雷击"),
    "cactus": ("step_back", "离远点", "仙人掌"),
    "sweet_berry_bush": ("step_back", "离远点", "甜浆果丛"),
    "falling_block": ("flee", "躲开", "落方块"),
    "out_of_world": ("unstick", "★紧急：回到安全点★", "掉出世界"),
    "generic": ("retreat_safe", "回安全点（★家✗★）", "不明来源"),
}

SAFE_SPOT = ("home", "回家里")


def advise(src: str, ctx=None) -> dict:
    """★伤害来源 ⇒ 对策✗★

    ★未知来源 ⇒ **不静默** ✗ 明确报 `unknown_src` 并给最保守的对策（回安全点）✗★
    """
    key = (src or "").strip().lower().replace(" ", "_")
    if key in POLICY:
        act, what, why = POLICY[key]
        return {"src": key, "action": act, "do": what, "why": why,
                "known": True, "ctx": ctx or {}}
    # ★未知来源：退到安全点 ✗ 但**必须标出来**（★判据会拿这个字段验✗★）
    return {"src": key or "(empty)", "action": "retreat_safe",
            "do": "回安全点", "why": "★未知伤害来源 ✗ 保守：回安全点★",
            "known": False, "ctx": ctx or {}}


def main(argv) -> int:
    if argv and argv[0] == "--advise":
        src = argv[1] if len(argv) > 1 else ""
        a = advise(src)
        print("DAMAGE src=%s known=%s action=%s do=%s why=%s"
              % (a["src"], a["known"], a["action"], a["do"], a["why"]))
        return 0
    print("已知伤害来源 %d 种：" % len(POLICY))
    for k in sorted(POLICY):
        print("  %-18s ⇒ %-16s %s" % (k, POLICY[k][0], POLICY[k][1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
