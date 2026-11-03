#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entity_nbt_diff.py — 对比任意两个实体的 NBT 标签，回答"假人和真玩家到底一不一样"

为什么需要它：
  "假人是不是和玩家一样"这种问题，靠印象答一定会错。原版 /data get entity 能直接把
  两边的 NBT 打出来，那就把标签名集合取出来做差集——**差集就是答案**，
  比任何"应该一样"的说法都硬。

用法：
    py tools/entity_nbt_diff.py Bot Au_Sn          # 对比两个实体
    py tools/entity_nbt_diff.py --raw Bot          # 打印某个实体的原始 NBT 全文
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BRIDGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bridge")

# 只看这些"玩家特征"标签，避免被几十个通用实体标签淹没
PLAYER_TAGS = [
    "Inventory", "SelectedItemSlot", "EnderItems", "abilities", "XpLevel", "XpP",
    "XpTotal", "XpSeed", "foodLevel", "foodSaturationLevel", "foodExhaustionLevel",
    "Health", "AbsorptionAmount", "Air", "Score", "recipeBook", "warden_spawn_tracker",
    "enteredNetherPosition", "seenCredits", "ShoulderEntityLeft", "ShoulderEntityRight",
    "RootVehicle", "SleepTimer", "SpawnX", "SpawnY", "SpawnZ", "SpawnForced",
    "SpawnAngle", "SpawnDimension", "Brain", "HurtByTimestamp", "DeathTime",
    "LastDeathLocation", "current_explosion_impact_pos", "ignore_fall_damage_from_current_explosion",
    "Team", "Motion", "Pos", "Rotation", "FallDistance", "OnGround", "UUID", "Tags",
    "Attributes", "ActiveEffects", "equipment", "CuriosInventory", "cardinal_components",
    "forge:attachments", "neoforge:attachments", "DataVersion", "Dimension", "PortalCooldown",
]


def load_cmd_results(want_texts):
    logfile = os.path.join(BRIDGE, "log.jsonl")
    lines = open(logfile, encoding="utf-8", errors="replace").read().splitlines()
    out = {}
    for raw in reversed(lines):
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if d.get("who") != "cmd0":
            continue
        dd = d.get("data") or {}
        if dd.get("cmd") != "cmd":
            continue
        res = dd.get("result")
        if not isinstance(res, dict):
            continue
        t = res.get("text")
        if t in want_texts and t not in out:
            out[t] = " ".join(res.get("lines") or [])
        if len(out) == len(want_texts):
            break
    return out


def top_tags(text):
    """从 NBT 文本里抽出"看起来是顶层标签"的名字。

    原版 /data get entity 的输出是 `Name has the following entity data: {Tag: ...}`，
    顶层标签都紧跟在 `{` 或 `, ` 之后。这里用位置+括号深度做粗筛，
    目的不是完整解析 NBT，而是拿到"有哪些标签"这个集合去做对比。
    """
    body = text
    m = re.search(r"\{", text)
    if m:
        body = text[m.start():]
    depth = 0
    tags = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        elif depth == 1 and (c == "{" or body[i - 1: i] == ", "):
            m2 = re.match(r"[A-Za-z0-9_:.\-]+(?=:)", body[i + 1:])
            if m2:
                tags.append(m2.group(0))
                i += len(m2.group(0))
        i += 1
    return tags


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("a", nargs="?", help="实体名 A（如 Bot）")
    ap.add_argument("b", nargs="?", help="实体名 B（如 Au_Sn）")
    ap.add_argument("--raw", help="直接打印该实体的 NBT 全文")
    args = ap.parse_args(argv)

    if args.raw:
        got = load_cmd_results({"data get entity " + args.raw})
        t = got.get("data get entity " + args.raw)
        print(t[:6000] if t else "[X] 没找到 %s 的 NBT 回传" % args.raw)
        return 0

    if not args.a or not args.b:
        print(__doc__)
        return 2

    keys = ["data get entity " + args.a, "data get entity " + args.b]
    got = load_cmd_results(set(keys))
    ta, tb = got.get(keys[0]), got.get(keys[1])
    if not ta or not tb:
        print("[X] 缺少回传：%s=%s  %s=%s" % (keys[0], bool(ta), keys[1], bool(tb)))
        print("    （先把这两条指令投递到 bridge/inbox 并等它们回传）")
        return 1

    sa, sb = set(top_tags(ta)), set(top_tags(tb))
    print("=" * 74)
    print("对比 %s (%d 个标签)  vs  %s (%d 个标签)" % (args.a, len(sa), args.b, len(sb)))
    print("=" * 74)

    print("\n【两边都有】(玩家通用特征)")
    common = sorted(sa & sb)
    print("  " + (", ".join(common) if common else "（无）"))

    print("\n【只有 %s 有】" % args.a)
    onlya = sorted(sa - sb)
    print("  " + (", ".join(onlya) if onlya else "（无）"))

    print("\n【只有 %s 有】" % args.b)
    onlyb = sorted(sb - sa)
    print("  " + (", ".join(onlyb) if onlyb else "（无）"))

    print("\n【重点玩家标签逐项核对】")
    for tg in PLAYER_TAGS:
        ia, ib = tg in sa, tg in sb
        if ia or ib:
            print("  %-34s %s=%-5s %s=%-5s %s" % (
                tg, args.a, ia, args.b, ib,
                "" if ia == ib else "  <-- 不一致"))

    inv_pat = re.compile(r'id: "([^"]+)"')
    print("\n【背包物品】")
    print("  %s (%d 件): %s" % (args.a, len(inv_pat.findall(ta)), inv_pat.findall(ta)))
    print("  %s (%d 件): %s" % (args.b, len(inv_pat.findall(tb)), inv_pat.findall(tb)))
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
