#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inv_guard.py —— 背包守卫：**先看空位** ✓ **快满了就往箱子塞** ✓

用户明确要求的常备动作 ✓：「**记得加检查背包，还需要记得把东西放箱子**」✓

为什么必须是"常备动作"而不是"记得就做" ✗（都实测过 ✓）：
  * 满包 ⇒ 玩家丢的东西**一件都捡不起来** ✗（栽过两次：麦子 ✗ 绿宝石 64 个 ✗ 见错题本 N3 / P19 ✓）
  * 满包 ⇒ **交易余料掉在地上也捡不回来** ✗（P19 ✓）
  * 满包 ⇒ 收割/筛矿的产出接不住 ✗
  * 满包 ⇒ ★**合成"扣料不给货"**★ ✗（错题本 **L1** ✓ `player.give` 在满包时**静默失败** ✗✓）
  * 而"丢在地上腾位置"是**错的** ✗：掉脚边会被它**自己捡回去** ✗（I12 ✓）；
    丢远一点又会 **5 分钟消失** ✗（J6 ✓ 已经丢过两次货 ✗）
  ⇒ 唯一正确：**放进容器** ✓✓（这也正是真人干的事 ✓）

★★ 2026-09-19 晚：从"一个 CLI"升级成"**一个可被调用的前置检查**" ★★
  用户的要求 ✓：「把 inv_guard 接到**收割/筛矿等所有会接东西的流程**前」✗
  ⇒ 光有 CLI 是不够的 ✗ —— CLI 需要"人记得去敲"✗ ⇒ 那就一定会漏 ✗
  ⇒ 所以本文件现在导出 **`ensure_free(...)`** ✓（`agent/skills.py` 直接在
     `s_sift` / `s_chop` / `s_make` / `s_box_take` / `s_box_slot` / `s_entbox` / `s_trade`
     的**入口**调用它 ✓）—— 把"记得"换成"**写在代码里**"✓

用法（CLI ✓ 保留）：
    py tools/inv_guard.py                      # 只看（只读 ✓ 不动任何东西）
    py tools/inv_guard.py --auto               # 空位 ≤ 阈值就自动塞箱子
    py tools/inv_guard.py --auto --keep-free 4 # 自定义阈值
    py tools/inv_guard.py --chest 4122 71 3    # 指定容器（默认就是那个 132 格的桶 ✓）

用法（Python ✓ 新）：
    from inv_guard import ensure_free
    r = ensure_free(ch, bot="Bot", need=2, auto=True)
    if not r["ok"]:
        return 拒绝开工(r["why"])      # ★ 放不下就**拒绝**✓ 绝不"边干边丢"✗
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel  # noqa: E402
from world import World      # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

DEFAULT_CHEST = (4122, 71, 3)      # 132 格的模组桶 ✓（原版 /item 认不了它 ✗ 见模组文档 ✓）
TOTAL_SLOTS = 36                   # 主背包 36 格（快捷栏 9 ＋ 主区 27 ✓）

# ★ 什么该进箱子 ✗（都是"攒着以后用"的原料/建材 ✓ 放桶里最自然 ✓）
#   ⚠ 反过来 ✓：工具 / 食物 / 种子 / 工作台 **必须留在身上** ✗（要用的时候不能还得跑回来拿 ✗）
STASH_PREFIX = (
    "exdeorum:",            # 矿物碎块 ✓ 各种碎石 ✓ 筛网等（都要攒着以后用 ✓）
    "minecraft:gravel",     # 沙砾（筛矿原料 ✓ 用的时候再拿 ✓）
    "minecraft:flint",      # 燧石
    "minecraft:coal",       # 煤（燃料 ✓ 留一点也行 ✓）
    "minecraft:lapis_lazuli",
    "minecraft:amethyst_shard",
    "minecraft:raw_",
)
STASH_KEEP = {              # 身上至少留这么多 ✓（留一点应急 ✓ 其余进桶 ✓）
    "minecraft:coal": 8,
    "minecraft:flint": 4,
}
NEVER_STASH = (             # 这些**永远不进箱子** ✗
    "_pickaxe", "_axe", "_shovel", "_sword", "_hoe",
    "crafting_table", "wheat_seeds", "cooked_", "bread", "torch",
    # ★2026-09-19 深夜补★ ✗：**工具/器械一律不许进箱子** ✗
    #   实测 ✓：我自己的守卫把一把 `exdeorum:wooden_hammer` **塞进了桶** ✗
    #   （幸好是"进箱子"✓ 不是"丢地上"✗ ⇒ 取回来就行 ✓ 一点没丢 ✓）
    #   ⇒ 判据必须**按用途列全** ✗ 不能只列原版那几样 ✗（模组的工具也是工具 ✓）
    "hammer", "crook", "_mesh", "shears", "fishing_rod", "flint_and_steel",
    "bucket", "wrench", "_wand", "sprayer", "_drill",
)


def parse_list(text: str):
    """把 `dshinv list` 的输出解析成 [(slot, item, count)] ✓
    实测格式 ✓：`dshinv list selected=5 => 0:minecraft:wheat_seedsx62 1:... (31 used)` ✓
    （全程 ASCII ✓ 所以好解析 ✓ —— 这正是当初定"回执只用 ASCII"那条纪律的红利 ✓ P13 ✓）
    """
    items = []
    for m in re.finditer(r"(\d+):([A-Za-z0-9_:.\-]+)x(\d+)", text):
        items.append((int(m.group(1)), m.group(2), int(m.group(3))))
    used = 0
    mu = re.search(r"\((\d+) used\)", text)
    if mu:
        used = int(mu.group(1))
    return items, used


def inventory(ch: Channel, bot: str = "Bot"):
    """读一次背包（只读 ✓）→ (items, used, 原始回执)"""
    r = ch.cmd("execute as %s at %s run dshinv list" % (bot, bot),
               timeout=60.0, allow_str=True)
    txt = (r.text() or "").strip().splitlines()
    txt = txt[0] if txt else ""
    items, used = parse_list(txt)
    return items, used, txt


def bot_cmd(ch: Channel, bot: str, text: str, t: float = 90.0) -> str:
    r = ch.cmd("execute as %s at %s run %s" % (bot, bot, text), timeout=t, allow_str=True)
    s = (r.text() or "").strip()
    return s.splitlines()[0] if s else "(no reply)"


def stash_plan(items, keep_free_now: int = 0):
    """从背包清单里挑出"该进箱子"的（按数量从多到少 ✓ 先塞最占地方的 ✓）"""
    plan = []
    for slot, item, cnt in items:
        if any(x in item for x in NEVER_STASH):
            continue
        if not any(item.startswith(p) for p in STASH_PREFIX):
            continue
        keep = STASH_KEEP.get(item, 0)
        move = max(0, cnt - keep)
        if move > 0:
            plan.append((slot, item, cnt, move))
    plan.sort(key=lambda t: -t[3])
    return plan


def ensure_free(ch: Channel, bot: str = "Bot", need: int = 2, auto: bool = True,
                chest=None, verbose: bool = True) -> dict:
    """★ 前置守卫：确保背包至少有 `need` 个空位 ✓

    语义（用户定的 ✓ 见错题本 P19.1 ✓）：
      * 空位够 ⇒ 直接放行 ✓（**不做任何多余动作** ✓ 尤其**不搬东西** ✗）
      * 空位不够 ⇒ ① 把"该攒的原料"塞进容器 ✓ ② 重新数一次 ✓
                    ③ 还是不够 ⇒ **ok=False ＋ 说清为什么** ✗（让调用者拒绝开工 ✓）
    返回值：{ok, free, used, before_free, stashed, replies, why}
      · ok=True  ⇒ 放行 ✓（free = 现在的空位数 ✓）
      · ok=False ⇒ **调用方必须拒绝"会接东西"的那一步** ✗（别边干边丢 ✗）
    """
    chest = tuple(chest or DEFAULT_CHEST)
    items, used, listing = inventory(ch, bot)
    if not listing:
        return {"ok": False, "free": -1, "used": -1, "before_free": -1, "stashed": [],
                "why": "读不到背包 ✗（dshinv list 没有回执 ⇒ 假人不在？模组没加载？）"}

    free0 = TOTAL_SLOTS - used
    res = {"ok": free0 >= int(need), "before_free": free0, "free": free0,
           "used": used, "stashed": [], "replies": [], "why": ""}
    if res["ok"] or not auto:
        if not res["ok"]:
            res["why"] = ("背包只剩 %d 个空位 ✗（需要 %d）—— 只演算，没塞箱子（auto=False）"
                          % (free0, need))
        if verbose:
            print("[inv_guard] 空位 %d ✓ 阈值 %d ✓（干净放行，没动任何东西 ✓）" % (free0, need))
        return res

    plan = stash_plan(items)
    if verbose:
        print("[inv_guard] 空位只剩 %d ✗（需要 %d）⇒ 先往容器 %s 塞：" % (free0, need, chest))
        for slot, item, cnt, move in plan:
            print("           slot %-2d %-38s 有 %-3d ⇒ 存走 %d" % (slot, item, cnt, move))
    for slot, item, cnt, move in plan:
        if res["free"] >= int(need):
            break
        # ⚠ 物品名**必须加引号** ✗（Brigadier 的 string() 不吃冒号 ✓ 见错题本 P14 ✓）
        out = bot_cmd(ch, bot, 'dshbox put %d %d %d "%s" %d' % (*chest, item, move))
        res["replies"].append(out)
        res["stashed"].append({"item": item, "count": move, "reply": out})
        if verbose:
            print("           put %-38s %-3d -> %s" % (item, move, out))
        items, used, _ = inventory(ch, bot)
        res["used"], res["free"] = used, TOTAL_SLOTS - used

    res["ok"] = res["free"] >= int(need)
    if not res["ok"]:
        res["why"] = ("塞完箱子仍然只有 %d 个空位 ✗（需要 %d）—— 背包里已经没有"
                      "可攒进箱子的原料了 ✗ ⇒ **拒绝开工** ✓"
                      "（绝不丢地上 ✗ 那会自己捡回来或 5 分钟消失 ✗）"
                      % (res["free"], need))
    if verbose:
        print("[inv_guard] 结果：%d 格已用 / **%d 格空** ✓ %s"
              % (res["used"], res["free"], "放行 ✓" if res["ok"] else "**仍然不够 ✗**"))
    return res


def main(argv: list[str]) -> int:
    auto = "--auto" in argv
    keep_free = 2
    if "--keep-free" in argv:
        keep_free = int(argv[argv.index("--keep-free") + 1])
    chest = list(DEFAULT_CHEST)
    if "--chest" in argv:
        i = argv.index("--chest")
        chest = [int(argv[i + 1]), int(argv[i + 2]), int(argv[i + 3])]

    ch = Channel("cmd0")
    items, used, _ = inventory(ch)
    free = TOTAL_SLOTS - used
    print("=" * 68)
    print("背包：%d 格已用 / %d 格空（共 %d）" % (used, free, TOTAL_SLOTS))
    print("容器 %s：%s" % (tuple(chest), bot_cmd(ch, "Bot", "dshbox peek %d %d %d" % tuple(chest))[:90]))
    print("=" * 68)

    # ★ 注意语义 ✓：`--auto` 是"**该塞就塞**"✗ 不是"**一定塞**"✗
    #   `ensure_free` 只在 `free <= need` 时才动手 ✓ ⇒ 空位够时它**一个字节都不动** ✓
    #   （这才是可以挂在每个流程前面的前置检查 ✓ —— 前置检查要是每次都搬东西 ✗
    #     那它自己就成了新的故障源 ✗）
    if not auto and free <= keep_free:
        plan = stash_plan(items)
        print("[!] 空位只剩 %d 格 ✗（阈值 %d）⇒ 计划把下面这些存进箱子：" % (free, keep_free))
        for slot, item, cnt, move in plan:
            print("    slot %-2d %-38s 有 %-3d ⇒ 存走 %d" % (slot, item, cnt, move))
        if not plan:
            print("    （没有可存的 ⇒ 只能手工处理 ✗ 别丢地上 ✗ 会自己捡回来或 5 分钟消失 ✗）")
            return 1
        print("\n[--dry] 只演算 ✓ 要真塞请加 --auto ✓")
        return 0

    res = ensure_free(ch, bot="Bot", need=keep_free, auto=auto, chest=chest)
    if not res["ok"]:
        print("[X] %s" % (res.get("why") or "空位不足 ✗"))
        return 1
    if res["stashed"]:
        print("容器现在：%s" % bot_cmd(ch, "Bot", "dshbox peek %d %d %d" % tuple(chest))[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
