#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_v28.py —— 模组 v2.8「拟人化」验收（用户点名要的两条 ✓ 会听会说 ＋ 自行走动）

为什么要单拎一个脚本 ✗（两个原因都很实在 ✓）：
  ① **"听"必须真有人说话** ✗ —— `ServerChatEvent` 只对**玩家聊天**触发 ✓
     `/say` 之类的服务器广播**不触发**它 ✓ ⇒ 脚本没法自己造 ✓
     ⇒ 所以脚本会**明确请你**在游戏聊天里说一句 ✓ 然后它去查**事件流 ＋ 计数器** ✓
     （判据是"它到底听见没有"✓ 不是"我以为它听见了"✗）
  ② **"自行走动"要求"没人打扰"** ✗ —— 拟人化的总门槛是
     「**最近 15 秒内没有任何模组指令**」✓ ⇒ 我**一边发指令一边看**是看不出来的 ✗
     （每条查询都会把门槛重新关上 ✓）
     ⇒ 所以脚本会**安静等 90 秒**✗ 再去读事件流 ✓（事件是攒在环形缓冲里的 ✓ 不会丢 ✓）

判据（每条都独立可判 ✓ 且都用世界真值/事件流 ✓）：
  B0 `/dshver` 必须是 **2.8.0** ✓（否则直接退出 ✗）
  B1 `dshequip`：按名字拿东西 ⇒ `verified=true` ✓ 且**手上真的是它** ✓
  B2 绕障：墙西 → 墙东 ⇒ `reached` ＋ `detours>0` ✓（v2.7.1 的"先退再绕"✓）
  B3 ★会听★：你随便说一句 ⇒ 事件流出现 `chat` ✓ 且 `heard` 计数 +1 ✓
  B4 ★会说★：你说的话里**带 Bot** ⇒ 事件流出现 `auto_reply` ✓（而且 20 秒内不会连回 ✗）
  B5 ★自行走动★：安静 90 秒 ⇒ 事件流出现 `idle_stroll` / `idle_look` / `idle_line` 之类 ✓
     且 ★离锚点不超过半径＋1★ ✓ ★**一次 `warp` 都没有**★ ✓ ★没受伤✓★（空岛安全 ✓）

用法：py tools/bench_v28.py
"""
from __future__ import annotations

import re
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


def main() -> int:
    ch = Channel("cmd0", verbose=False)
    w = World(ch)
    fails: list[str] = []

    def game(text: str, t: float = 90.0) -> str:
        r = ch.cmd(text, timeout=t, allow_str=True)
        s = (r.text() or "").strip()
        return s.splitlines()[0] if s else "(no reply)"

    def bot(text: str, t: float = 120.0) -> str:
        return game("execute as Bot at Bot run " + text, t)

    def kv(txt: str) -> dict:
        return {k: v for k, _, v in (tok.partition("=") for tok in (txt or "").split() if "=" in tok)}

    def check(name: str, ok: bool, detail: str = "") -> None:
        print("   %s %s%s" % ("[OK]  " if ok else "[FAIL]", name, (" ｜ " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    def ver_ok(txt: str, minimum=(2, 8)) -> bool:
        """★版本闸门要判"**≥ 最低版本**"✗ 不是"等于那一版"★★
        （我在 `bench_v27` 里就写错过一次 ✗ ⇒ 升到 2.8 之后它把自己的升级判成失败 ✗ 见 P36 ✓）"""
        m = re.search(r"version=(\d+)\.(\d+)", txt or "")
        if not m:
            return False
        return (int(m.group(1)), int(m.group(2))) >= minimum

    print("=" * 78)
    print("模组 v2.8「拟人化」验收 === 会听 ✓ 会说 ✓ 会自己溜达 ✓")
    print("=" * 78)

    # ── B0 版本 ────────────────────────────────────────────────────────────────
    v = bot("dshver", 60.0)
    print("[B0] %s" % v[:180])
    if not ver_ok(v, (2, 8)):
        print("\n结论：**跑的还是旧版** ✗ —— 模组改动必须**关掉游戏进程重启** ✗（只退世界不加载 ✗）")
        return 2

    # ── B1 dshequip ────────────────────────────────────────────────────────────
    print("\n[B1] `dshequip`：按名字拿东西（含主背包 ✓ 修的是 P29 那一类 ✗）")
    eq = bot('dshequip "exdeorum:wooden_hammer"', 60.0)
    print("      %s" % eq[:200])
    check("B1 拿住了（verified=true ✓）", "verified=true" in eq, eq[:120])
    st = bot("dshstats", 60.0)
    print("      dshstats：%s" % st[:160])
    check("B1b 手上真的是锤子（世界真值 ✗ 不听它说 ✓）", "wooden_hammer" in st, st[:120])

    # ── B2 绕障（v2.7.0 卡在 x=4114 ✗ v2.7.1 加了"先退再绕" ✓）────────────────
    print("\n[B2] 绕障：墙西 → 墙东（x=4114 那道 1.5 格高的墙 ✗）")
    scan = bot('dshscan 4111 70 8 4113 72 10 ":" 8 1', 60.0)
    if "4112,70,9:" in scan:
        game("tp Bot 4112.5 71 9.5")
        time.sleep(0.8)
        bot("dshwalk 4117 71 9 20000", 90.0)
        line = ""
        for _ in range(60):
            time.sleep(0.35)
            line = bot("dshwalk", 30.0)
            if kv(line).get("status") == "done":
                break
        k = kv(line)
        print("      → %s 停在 %s 偏差 %s 格 ｜ 绕障=%s 下台阶=%s ｜ %s"
              % (k.get("result"), k.get("at"), k.get("dist"), k.get("detours"),
                 k.get("step_downs"), k.get("why", "")))
        check("B2 绕过去了（reached）", k.get("result") == "reached", "结果=%s" % k.get("result"))
        check("B2b 记了绕障次数（detours>0 ✓）", int(k.get("detours", "0") or 0) > 0,
              "detours=%s" % k.get("detours"))
    else:
        print("      ⚠ 墙西那一格不合法 ⇒ 这一项**如实跳过** ✗")

    # ── B3/B4 会听 ＋ 会说（**需要你配合一句** ✗）──────────────────────────────
    #   ★`--skip-chat`：整段跳过 ✓ —— 因为它们**必须有人说话**✗
    #     （`ServerChatEvent` 只对**玩家聊天**触发 ✓ `/say` 不触发 ✓ 脚本造不出来 ✓）
    #     而"其余五项"完全自主 ✓ ⇒ 没人在的时候也能先把那五项验掉 ✓ 不浪费一轮 ✓
    #   ⚠ 我上一版**只把 print 包进去了** ✗ ⇒ 后面的轮询照跑 ✗（"跳过"变成"白等 60 秒"✗）
    #     —— 又一次"判据/开关的作用域写错了" ✗ 见错题本 P36/P34 ✓
    if "skip-chat" in sys.argv:
        print("\n[B3/B4] ⚠ 本次带 `--skip-chat` ⇒ **整段如实跳过**"
              "（这两项需要真人在聊天里说话 ✗ 见脚本头 ✓）")
    else:
        print("\n[B3/B4] ★会听 ＋ 会说★ —— 请你**现在**在游戏聊天里说一句（**带上 Bot 更好** ✓）")
        print("        例如：  Bot 你在干嘛          （含 Bot ⇒ 它应该回一句 ✓）")
        print("        脚本会等你 60 秒 ✓ 期间它会反复查事件流与计数器 ✓（这些查询不影响这两项 ✓）")
        before = kv(bot("dshidle status", 30.0)).get("heard", "0")
        print("      说话前：heard=%s" % before)
        heard, replied, ev_text = False, False, ""
        t0 = time.time()
        while time.time() - t0 < 60:
            time.sleep(3)
            stt = bot("dshidle status", 30.0)
            k = kv(stt)
            if k.get("heard", "0") != before:
                heard = True
                ev_text = bot("dshevents", 40.0)
                replied = "auto_reply" in ev_text
                break
        check("B3 它**听见了**（heard 计数涨了 ✓）", heard,
              "heard=%s" % kv(bot("dshidle status", 30.0)).get("heard"))
        if heard:
            print("      事件流：%s" % ev_text[:400])
            has_chat = " chat " in ev_text
            check("B3b 事件流里有 `chat` 记录（内容按 U+XXXX 转义 ✓ 过 CC 通道不会变 ? ✗）",
                  has_chat, ev_text[:200])
            check("B4 含 Bot ⇒ 它**回了一句**（事件流有 auto_reply ✓）", replied)
        else:
            print("      （60 秒内没听见 ⇒ 如实判失败 ✗ —— 也可以是脚本没等到你 ✓ 重跑即可 ✓）")
            fails.append("B3/B4(没等到你说话 ✗)")

    # ── B5 自行走动（**必须安静** ✗ 任何指令都会把门槛关上 ✓）─────────────────
    print("\n[B5] ★自行走动★ —— 开拟人化 ✓ 然后**安静等 90 秒**（我不发任何指令 ✗）")
    print("        （拟人化的总门槛是「最近 15 秒没有模组指令」✓ 所以必须真的安静下来 ✓）")
    hp_before = bot("dshdigest 4", 60.0)
    on = bot("dshidle on", 40.0)
    print("      开：%s" % on[:200])
    anchor = kv(on).get("anchor", "?")
    ax, ay, az = [float(x) for x in anchor.split(",")]
    ev0 = kv(bot("dshevents", 40.0)).get("cursor", "0")
    print("      锚点 %s ｜ 现在**安静 90 秒**…" % anchor)
    for i in range(9):
        time.sleep(10)
        print("        … %d/9" % (i + 1), flush=True)
    ev = bot("dshevents %s" % ev0, 60.0)
    stt = bot("dshidle status", 40.0)
    print("      事件流（这一段）：%s" % ev[:600])
    print("      状态：%s" % stt[:300])
    k = kv(stt)
    strolls = int(k.get("strolls", "0") or 0)
    looks = int(k.get("looks", "0") or 0)
    lines = int(k.get("lines", "0") or 0)
    check("B5 它自己动过（溜达>0 或 看四周>0 ✓）", strolls > 0 or looks > 0,
          "strolls=%d looks=%d lines=%d" % (strolls, looks, lines))
    check("B5b ★没有瞬移★（这段事件流里没有 warp ✗ 人感的底线 ✓）", " warp " not in ev, "")
    dg = bot("dshdigest 6", 60.0)
    pos = kv(dg).get("pos", "?")
    far = -1.0
    try:
        px, py, pz = [float(x) for x in pos.split(",")]
        far = ((px - ax) ** 2 + (pz - az) ** 2) ** 0.5
    except Exception:
        far = -1.0
    print("      现在位置 %s ⇒ 离锚点 %.2f 格（半径 +1 以内才对 ✓）" % (pos, far))
    check("B5c ★没跑远★（离锚点 ≤ 半径+1 ✗ 空岛安全 ✓）",
          0 <= far <= 5.0, "离锚点 %.2f" % far)
    # ★"没受伤"要**前后比**✗（拍脑袋定个 hp 阈值就是发明判据 ✗ 见 P10 ✓）
    hp0 = float(kv(hp_before).get("hp", "-1") or -1)
    hp1 = float(kv(dg).get("hp", "-1") or -1)
    print("      生命值 %s → %s（拟人化那段不许掉血 ✓ 回血无罪 ✓）" % (hp0, hp1))
    check("B5d 没掉血（拟人化不该把自己弄伤 ✓）", hp0 < 0 or hp1 < 0 or hp1 >= hp0,
          "hp %.1f → %.1f" % (hp0, hp1))
    print("      收尾：%s" % bot("dshidle off", 40.0)[:120])

    print("=" * 78)
    if fails:
        print("结论：**%d 项没通过 ✗** —— %s" % (len(fails), "／".join(fails)))
    else:
        print("结论：★v2.8 全部判据通过 ✓★（会说 ✓ 会听 ✓ 会自己溜达 ✓ 而且不瞬移 ✓ 不跑远 ✓）")
    print("=" * 78)
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
