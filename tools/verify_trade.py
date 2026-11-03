#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_trade.py —— 村民交易的正向验收（重启后一键跑 ✓）

为什么单拎出来（都是踩过的坑 ✓）：
  * 重启后**假人一定不在** ✗ ⇒ 必须 spawn ✓
  * 而 `/player Bot spawn` 出来的是**创造模式** ✗（挖掘不掉落 ⇒ 自给证据失真 ✗ 见错题本 P17 ✓）
    ⇒ 所以 spawn 之后**必须核对并纠正** ✓
  * 交易成没成**不能听模组那句话** ✓（它不返回值 ✗）⇒ 看**报价 uses ＋ 背包实增** ✓（P19 ✓）
  * 满背包会把玩家丢的东西**晾在地上** ✗（N3 ✓）⇒ 跑之前先看空位 ✓

用法：py tools/verify_trade.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel  # noqa: E402
from world import World      # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

SPAWN = (4123, 72, 11)
SPOT = (4120, 4)          # 村民 (4119.5, 71, 3.5) 旁边的可站格 ✓
VILLAGER = "@e[type=villager,limit=1,sort=nearest]"


def main() -> int:
    ch = Channel("cmd0")
    w = World(ch)

    def game(text: str, t: float = 60.0) -> str:
        r = ch.cmd(text, timeout=t, allow_str=True)
        t2 = (r.text() or "").strip()
        return t2.splitlines()[0] if t2 else "(no reply)"

    def bot(text: str, t: float = 120.0) -> str:
        return game("execute as Bot at Bot run " + text, t)

    # ① 假人在不在
    # ⚠ 判据要**看回传里的 `success` 字段** ✗ —— 我第一版拿 `"success" in str(r.result)` 判 ✗
    #   `r.result` 是一张表（不是字符串 ✗）⇒ 判据恒为假 ✓ ⇒ 它**跳过 spawn** ✗
    #   于是后面每一条都打在空气上 ✓ 而回执只是一串 `0` ✗ —— 典型的"判据写错、现象像别的问题"✗（P6 同族 ✓）
    r0 = ch.cmd("data get entity Bot Pos", timeout=30.0, allow_str=True)
    alive = bool((r0.result or {}).get("success")) if isinstance(r0.result, dict) else False
    if not alive:
        print("[1] 假人不在 ⇒ spawn")
        game("player Bot spawn at %d %d %d" % SPAWN)
        time.sleep(2)
    else:
        print("[1] 假人已在 ✓")

    # ② ★模式核对★（P17 ✓ 不查就会毁掉所有挖掘证据 ✗）
    gm = game("data get entity Bot playerGameType")
    print("[2] playerGameType = %s（0=生存 ✓）" % gm[-1:])
    if gm.strip().endswith("1"):
        print("    [!] 是创造模式 ✗ ⇒ 切回生存 ✓")
        game("gamemode survival Bot")
        time.sleep(1)
        print("    现在 =", game("data get entity Bot playerGameType")[-1:])

    # ③ 站到村民旁边（触及距离 4.5 格 ✓）
    game("tp Bot %d.5 71.0 %d.5" % SPOT)
    time.sleep(2)
    print("[3] 站位：", game("data get entity Bot Pos")[:70])

    # ★ ④ 背包前置检查 ✗（用户明确要求 ✓ 见错题本 P19.1 ✓）★
    #   满包 ⇒ 交易余料掉地上**捡不回来** ✗ ⇒ 兑换出来的东西也接不住 ✗
    #   ⇒ 所以任何"会接东西"的流程，**开头先跑一遍背包守卫** ✓ 不靠"记得" ✗
    print("[4] 背包前置检查（满就自动塞箱子 ✓）")
    subprocess.run([sys.executable, str(HERE / "inv_guard.py"), "--auto"], check=False)

    print("[5] 自己报状态：", bot("dshstats"))

    b = w.counts()
    print("[5] 交易前：绿宝石=%s 铁靴=%s 头盔=%s ｜ 共 %d 件 / %d 种"
          % (b.get("minecraft:emerald"), b.get("minecraft:iron_boots"),
             b.get("minecraft:iron_helmet"), sum(b.values()), len(b)))
    print("[6] 报价：", bot("dshtrade list " + VILLAGER))

    print("[7] 买 2 双铁靴 …")
    print("    ->", bot("dshtrade do %s 0 2" % VILLAGER, 150.0))
    time.sleep(1)
    print("[8] 买 1 顶头盔 …")
    print("    ->", bot("dshtrade do %s 1 1" % VILLAGER, 150.0))
    time.sleep(1)

    f = w.counts()
    print("-" * 70)
    print("[9] 交易后：绿宝石=%s 铁靴=%s 头盔=%s ｜ 共 %d 件 / %d 种"
          % (f.get("minecraft:emerald"), f.get("minecraft:iron_boots"),
             f.get("minecraft:iron_helmet"), sum(f.values()), len(f)))
    print("    变化：绿宝石 %+d ｜ 铁靴 %+d ｜ 头盔 %+d ｜ 总件数 %+d"
          % (f.get("minecraft:emerald", 0) - b.get("minecraft:emerald", 0),
             f.get("minecraft:iron_boots", 0) - b.get("minecraft:iron_boots", 0),
             f.get("minecraft:iron_helmet", 0) - b.get("minecraft:iron_helmet", 0),
             sum(f.values()) - sum(b.values())))
    print("[10] 报价 uses：", bot("dshtrade list " + VILLAGER))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
