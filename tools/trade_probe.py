#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trade_probe.py —— 交易"到底成了几笔"的**测量探针**（只测不修 ✓ 2026-09-19 晚）

为什么要写它 ✗（不是"再跑一遍 verify_trade" ✗）：
  verify_trade.py 已经抓出了一个**真实缺陷** ✓ —— `dshtrade do … 0 2`（要 2 笔）
  回执是 `trades=1` ✗（只成 1 笔 ✗）而更怪的是 **`gained=0`** ✗
  —— 可整轮跑完，背包里**确实多了 1 双铁靴** ✓（215 件 → 208 件，账目严丝合缝 ✓）
  ⇒ 两个矛盾同时存在 ⇒ 不能靠推理 ✗ 必须**测得出来** ✓（纪律①：不猜先测 ✓）

本探针要回答的三个问题（每一个都对应一条可判读的证据 ✓）：
  Q1 `times=1` 单笔到底稳不稳？            判据：每次 `gained=?` ＋ **背包实增** ✓
  Q2 `times=2` 第 2 笔为什么不成交？        判据：`trades` 与 `uses` 增量 ✓
  Q3 成品是不是**先挂在光标上、关菜单时掉到地上再被捡起来**？
     判据：★交易后**立刻**查身边的 `@e[type=item]`★ ✗
     —— 掉落物有**拾取延迟**（`player.drop` 是 40 tick ✓）⇒ 有半秒以上的窗口能看见 ✓
     看到 `minecraft:iron_boots` 躺在地上 ⇒ 机制坐实（成品走过"地面"这一趟 ✗）
     看不到 ⇒ 机制不成立 ✗ 得换解释 ✓（**两种结果都有用** ✓ 这才叫可判读 ✓）

⚠ 只用 ASCII 回执做判据 ✗（中文过 CC 通道会变 `?` ✓ P13 ✓）
⚠ 开跑前先过背包守卫（P19.1 ✓）—— 满包时掉落物**根本捡不起来** ✗ 会把结论带偏 ✗
⚠ 会**真的花钱** ✓：每次交易 4 绿宝石 ✓（A/B 各 1 笔 ＋ C 请求 2 笔 ⇒ 最多 16 ✓）

用法：py tools/trade_probe.py
"""
from __future__ import annotations

import json
import re
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

VILLAGER = "@e[type=villager,limit=1,sort=nearest]"
OFFER = 0                       # [0] 4 绿宝石 -> 1 铁靴 ✓
WATCH = "minecraft:iron_boots"


def main() -> int:
    ch = Channel("cmd0", verbose=False)
    w = World(ch)

    def game(text: str, t: float = 60.0) -> str:
        r = ch.cmd(text, timeout=t, allow_str=True)
        t2 = (r.text() or "").strip()
        return t2.splitlines()[0] if t2 else "(no reply)"

    def bot(text: str, t: float = 120.0) -> str:
        return game("execute as Bot at Bot run " + text, t)

    # ① 假人 + 模式（P17 ✓ 创造模式会让**一切**证据失真 ✗）
    r0 = ch.cmd("data get entity Bot Pos", timeout=30.0, allow_str=True)
    if not (isinstance(r0.result, dict) and r0.result.get("success")):
        print("[0] 假人不在 ✗ ⇒ spawn + 切生存")
        game("player Bot spawn at 4123 72 11")
        time.sleep(2)
        game("gamemode survival Bot")
    gm = game("data get entity Bot playerGameType")
    print("[0] 模式 = %s（0=生存 ✓）" % gm[-1:])

    # ② 背包守卫（P19.1 ✓ 满包 ⇒ 掉落物捡不起来 ⇒ 结论会被带偏 ✗）
    subprocess.run([sys.executable, str(HERE / "inv_guard.py"), "--auto"], check=False)

    # ③ 站到村民旁边（触及 4.5 格 ✓）
    game("tp Bot 4120.5 71.0 4.5")
    time.sleep(2)
    print("[0] 站位 %s" % game("data get entity Bot Pos", 30)[:60])
    print("[0] 报价 %s" % bot("dshtrade list " + VILLAGER))

    def ground() -> str:
        """★身边的掉落物★ —— 交易后**立刻**问一次 ✓（拾取延迟给的那点窗口 ✓）"""
        return bot("data get entity @e[type=item,limit=1,sort=nearest,distance=..8] Item.id", 30)

    def counts() -> dict:
        return w.counts()

    def field(reply: str, key: str, default=None):
        """从模组回执里抠一个 `key=value` ✓（全 ASCII ✓ 好抠 ✓）"""
        m = re.search(r"(?:^|\s)" + re.escape(key) + r"=([^\s\]]+)", reply or "")
        if not m:
            return default
        v = m.group(1)
        try:
            return int(v)
        except ValueError:
            return v

    def step(label: str, times: int) -> dict:
        """一组对照 ✓：请求 N 笔 ⇒ **账目必须两边都对得上** ✗（不是"看它说成了"✓）"""
        print("-" * 72)
        b = counts()
        t0 = time.time()
        reply = bot("dshtrade do %s %d %d" % (VILLAGER, OFFER, times), 150.0)
        dt = time.time() - t0
        g = ground()
        time.sleep(1.8)
        a = counts()
        uses = bot("dshtrade list " + VILLAGER)
        d_em = a.get("minecraft:emerald", 0) - b.get("minecraft:emerald", 0)
        d_bo = a.get(WATCH, 0) - b.get(WATCH, 0)
        trades = field(reply, "trades", -1)
        gained = field(reply, "gained", -1)
        paid = field(reply, "paid", -1)
        refunded = field(reply, "refunded", -1)
        carried = field(reply, "carried", "?")
        diag = ""
        md = re.search(r"diag\[(.*)\]$", reply or "")
        if md:
            diag = md.group(1)
        print("[%s] 请求 times=%d ｜ 用时 %.1fs" % (label, times, dt))
        print("      回执   : %s" % reply)
        print("      背包   : 绿宝石 %+d ｜ 铁靴 %+d ｜ 总件数 %+d" % (
            d_em, d_bo, sum(a.values()) - sum(b.values())))
        print("      模组自报: trades=%s gained=%s paid=%s refunded=%s carried=%s"
              % (trades, gained, paid, refunded, carried))
        print("      诊断   : %s" % (diag or "(v2.4 没有这个字段 ✓ 说明跑的还是旧版 ✗)"))
        print("      地上   : %s" % g[:150])
        print("      报价   : %s" % uses[:220])

        # ★★ 逐项判据（**两边对账** ✗ 这是本探针的核心 ✓）★★
        # ⚠ `paid=` 这个字段**目前不可信** ✗（2026-09-19 深夜实测更正 ✓ 见错题本 P26 ✓）：
        #   它测的是"**被临时搬进付款槽的量**"✗ 而不是"真实扣款"✗
        #   实测 ✓：A 组 `paid=16` ✗ 可背包只少了 **2** ✓（diag 里 `{pay=16/0,…}` ✓）
        #   根因 ✓：`tryMoveItems` 会搬**整堆**材料进付款槽 ✗（那一次是 16 个 ✓）
        #   ⇒ 余款随后被还回背包 ✓（Forge 的 `MerchantMenu.removed()` ✓）⇒ 真实花费只有成交价 ✓
        #   ⇒ 修法排进 **v2.7** ✓：改成"**只搬正好够的量**"（`getCostA()` ✗ 而非 `getBaseCostA()` ✓）
        #     —— 那一改顺带让"余款"这一整类问题**消失** ✓
        #   ⇒ 所以本探针**不拿 paid 当账** ✗，改用一个**诚实的"没有丢钱"不变式** ✓：
        #     花费必须落在 **0 与 times×基准价** 之间 ✓（不许凭空多花 ✗ 也不许白得 ✗）
        base_price = 4
        spent_ok = (-int(base_price) * times) <= d_em <= 0
        # ★★★ v2.7 起 `paid` 变成**可信** ✓ 于是把**严格对账**加回来 ✗ ★★★
        #   v2.7 改成"按 `getCostA()` **只搬正好够的量**"✓ ⇒ 付款槽不再堆一大堆 ✓
        #   ⇒ `paid`（＝退回余款之后背包真实的减少量 ✓）就是这一笔的真实花费 ✓
        #   ⚠ 这条判据在 **v2.6 及更早**会**必然挂** ✗ —— 那不是回归 ✓ 是**版本差异** ✓
        #     版本探测法 ✓：回执里有没有 `fill=exact` ✓ 有就是 v2.7 ✓
        exact_fill = "fill=exact" in (reply or "")
        checks = [
            ("笔数 == times", trades == times),
            ("产物实增 == trades", gained == trades),
            ("铁靴实增 == times", d_bo == times),
            ("光标干净", str(carried) == "none"),
            ("地上没有掉落物", "minecraft:" not in (g or "")),
            ("有 refunded 字段（= v2.5+ ✓）", refunded != -1),
            ("★没有丢钱★：0 >= 花费 >= -times×基准价", spent_ok),
            ("paid 字段存在", paid != -1),
            ("★paid == 真实扣款（v2.7 ✓；旧版**必然不准** ✗ 见 P26 ✓）",
             (d_em == -int(paid)) if (exact_fill and paid != -1) else True),
        ]
        bad = [n for n, okk in checks if not okk]
        print("      判读   : %s" % ("★全部通过 ✓★" if not bad else "★不通过 ✗★ " + "／".join(bad)))
        return {"label": label, "times": times, "reply": reply, "ground": g,
                "d_em": d_em, "d_bo": d_bo, "trades": trades, "gained": gained,
                "paid": paid, "refunded": refunded, "carried": carried,
                "diag": diag, "bad": bad, "uses": uses}

    # ★ 预算内的三组（每笔 4 绿宝石 ✓ 共 4 笔 = 16 ✓ 手上 25 个够 ✓）★
    #   A：单笔基准 ✓（v2.4 时代它也是好的 ✓ 用作对照 ✓）
    #   B：★`times=2` 就是 v2.5 的**验收题**★（v2.4 实测只成 1 笔 ✗）
    #   C：多笔之后再单笔 ✓（v2.4 的第 2 笔废掉 ⇒ 残留在光标上 ⇒ 这一组会暴露它 ✗）
    out = [step("A times=1", 1), step("B times=2", 2), step("C times=1", 1)]

    print("=" * 72)
    print("汇总（只列判据 ✓ 不加工 ✗）")
    for o in out:
        print("  %-10s times=%d trades=%s 铁靴%+d 绿宝石%+d 地上=%s ⇒ %s"
              % (o["label"], o["times"], o["trades"], o["d_bo"], o["d_em"],
                 "有" if "minecraft:" in (o["ground"] or "") else "无",
                 "★通过 ✓★" if not o["bad"] else "不通过 ✗ " + "／".join(o["bad"])))
    allbad = [b for o in out for b in o["bad"]]
    print("=" * 72)
    print("结论：%s" % ("★v2.5 全部判据通过 ✓★" if not allbad
                        else "**仍有 %d 项不通过 ✗**：%s" % (len(allbad), "／".join(allbad))))
    print(json.dumps({"note": "全 ASCII 判据 ✓ 中文只作注释 ✓"}, ensure_ascii=False))
    return 0 if not allbad else 1


if __name__ == "__main__":
    raise SystemExit(main())
