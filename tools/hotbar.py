#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hotbar.py — 把假人**主背包**里的东西挪进**快捷栏**（补上一个真实的根因缺口）

为什么需要（这条限制坑过好几次 ✓ 写清楚）：
    * Carpet 假人**没有客户端界面** ⇒ 它自己没法把物品在槽位之间移动 ✗
      （真人是拖一下鼠标 ✓ 假人没有鼠标 ✓）
    * 而"手持某物/放置某物"的桥接动作只认**快捷栏 0~8** ✓
      ⇒ 合成出来的熔炉/漏斗/箱子落在主背包里 ✗ 直接就是"拿不到" ✗
    * 解法不是模拟界面 ✗ 而是用**原版指令**替它搬家 ✓：
        /item replace entity Bot hotbar.<H> from entity Bot inventory.<S-9>
      （原版 /item 指令 ✓ 2 级权限 ✓ cmd0 够用 ✓）

槽位编号对照（**最容易错的一步** ✓ 实测 + 官方文档）：
    NBT Slot 0..8   = 快捷栏   → 指令名 hotbar.0 .. hotbar.8      （同号 ✓）
    NBT Slot 9..35  = 主背包   → 指令名 inventory.0 .. inventory.26（**减 9** ✓）
    NBT Slot 36..39 = 盔甲 ✗ 不碰；40 = 副手 ✗ 不碰

用法：
    py tools/hotbar.py --item hopper            # 挪进第一个空的快捷栏槽
    py tools/hotbar.py --item furnace --select  # 挪完顺手切到那一格（手持它）
    py tools/hotbar.py --item hopper --to 0     # 指定快捷栏槽位（0~8）

自证：搬完**重新读一次背包** ✓ 只看真实 NBT ✓ 不看指令回显 ✓
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel, BridgeError  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def read_inv(ch: Channel, bot: str) -> dict:
    cid = ch.send("bot_inv", {"bot": bot})
    r = ch.wait(cid, timeout=60.0, cmd="bot_inv")
    d = r.as_dict()
    # ⚠ 回传形状有**两种** ✗（真实踩过，就崩在这一行 ✓）：
    #   ① {"ok":…, "result": {…}}  ② 直接就是结果本身 {…}
    #   act.py 里本来就写了这个兜底 ✓ 我在这里漏了 ✗ ⇒ payload 变成 None ✗
    payload = d.get("result")
    if not isinstance(payload, dict):
        payload = d if isinstance(d, dict) else None
    if not isinstance(payload, dict):
        raise BridgeError("读背包失败：%s" % payload)
    return payload


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    bot, want, to_slot, select, out = "Bot", None, None, False, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--item":
            want = argv[i + 1]; i += 2
        elif a == "--to":
            to_slot = int(argv[i + 1]); i += 2
        elif a == "--select":
            select = True; i += 1
        elif a == "--out":
            out = True; i += 1
        elif a == "--bot":
            bot = argv[i + 1]; i += 2
        else:
            print("[X] 未知参数 %s" % a)
            return 2
    if not want:
        print(__doc__)
        return 2

    ch = Channel(who="cmd0")
    inv = read_inv(ch, bot)
    items = inv.get("items") or []
    held = inv.get("held_item")

    # ── 反向：把快捷栏里的东西收回主背包（腾格子用 ✓）──
    # 为什么需要：快捷栏只有 9 格 ✓ 而"手持/放置"只认快捷栏 ✓
    #   ⇒ 摆产线时要反复腾格子 ✓ 这个方向是刚需 ✓
    if out:
        src = None
        for it in items:
            if want in str(it.get("id", "")) and 0 <= int(it.get("slot", -1)) <= 8:
                src = it
                break
        if src is None:
            print("[=] 快捷栏里没有含 '%s' 的物品（无需腾）" % want)
            return 0
        used_main = {int(it["slot"]) for it in items if 9 <= int(it.get("slot", -1)) <= 35}
        free_main = [s for s in range(9, 36) if s not in used_main]
        if not free_main:
            print("[X] 主背包也满了，没处放")
            return 1
        dst = free_main[0]
        cmd = "item replace entity %s inventory.%d from entity %s hotbar.%d" % (
            bot, dst - 9, bot, int(src["slot"]))
        print("[→] %s" % cmd)
        cid = ch.send("cmd", {"text": cmd})
        r = ch.wait(cid, timeout=60.0, cmd="cmd")
        print("    回显：%s" % json.dumps(r.result, ensure_ascii=False)[:200])
        after = read_inv(ch, bot)
        a_items = after.get("items") or []
        hit = [it for it in a_items if want in str(it.get("id", "")) and int(it.get("slot", -1)) == dst]
        print("[%s] 已收到主背包 inventory.%d：%s ｜ 手持=%s" % (
            "OK" if hit else "X", dst - 9,
            (hit[0]["id"] + " ×" + str(hit[0]["count"])) if hit else "（空 ✗）",
            after.get("held_item")))
        return 0 if hit else 1

    # 1) 已经在快捷栏里 ⇒ 直接成功（幂等 ✓ 重跑安全 ✓）
    src = None
    for it in items:
        if want in str(it.get("id", "")) and 0 <= int(it.get("slot", -1)) <= 8:
            src = it
            print("[=] 已在快捷栏：%s 槽 %d（手上是 %s）" % (it["id"], it["slot"], held))
            break
    if src is None:
        for it in items:
            if want in str(it.get("id", "")) and 9 <= int(it.get("slot", -1)) <= 35:
                src = it
                break
    if src is None:
        print("[X] 背包里找不到含 '%s' 的物品" % want)
        return 1

    if 0 <= int(src["slot"]) <= 8 and to_slot is None:
        target = int(src["slot"])
    else:
        occupied = {int(it["slot"]) for it in items if 0 <= int(it.get("slot", -1)) <= 8}
        if to_slot is not None:
            # ⚠ 真实事故：`--to` 之前**无条件覆盖**目标槽 ✗
            #   `/item replace` 是"替换"语义 ✓ 目标槽里原有的东西会**直接消失** ✗✗
            #   本轮就疑似因此弄丢了一组 2 个箱子（当时 slot 1 里还有箱子 ✓ 我却把漏斗塞了进去 ✗）
            #   ⇒ 目标槽非空就拒绝 ✓ 让人显式先腾格（宁可失败，也不要静默吞掉物品 ✗）
            if to_slot in occupied:
                print("[X] hotbar.%d 里已经有东西了，拒绝覆盖（先 --out 腾格，或换一个槽）" % to_slot)
                return 1
            target = to_slot
        else:
            free = [s for s in range(9) if s not in occupied]
            if not free:
                print("[X] 快捷栏 9 格全满，没法搬（先用别的方式腾一格）")
                return 1
            target = free[0]

    if 9 <= int(src["slot"]) <= 35:
        cmd = "item replace entity %s hotbar.%d from entity %s inventory.%d" % (
            bot, target, bot, int(src["slot"]) - 9)
        print("[→] %s" % cmd)
        cid = ch.send("cmd", {"text": cmd})
        r = ch.wait(cid, timeout=60.0, cmd="cmd")
        print("    回显：%s" % json.dumps(r.result, ensure_ascii=False)[:200])

    if select:
        cid = ch.send("cmd", {"text": "player %s hotbar %d" % (bot, target + 1)})
        ch.wait(cid, timeout=60.0, cmd="cmd")
        print("[→] 已切到 hotbar %d（1 起算 ✓）" % (target + 1))

    # 2) 自证：重新读一次
    after = read_inv(ch, bot)
    a_items = after.get("items") or []
    hit = [it for it in a_items if want in str(it.get("id", "")) and int(it.get("slot", -1)) == target]
    ok = bool(hit)
    print("[%s] 目标槽 hotbar.%d 现在是 %s ｜ 手持=%s ｜ 选中槽=%s" % (
        "OK" if ok else "X", target,
        (hit[0]["id"] + " ×" + str(hit[0]["count"])) if hit else "（空 ✗）",
        after.get("held_item"), after.get("held_slot")))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
