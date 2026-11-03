#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world_alive.py -- 世界还活着吗（★直连优先 ✗ 2026-11-02 迁移自旧 CC 车道✗★）

★为什么有它✗★：玩家离开去吃个饭 ⇒ 若游戏停在暂停菜单 ✓ 单机世界就**真的停** ✗
  ⇒ 表现不是报错 ✓ 而是"假人不动了 ✓ 指令没回执" ✗ —— 这种"静默停摆"最容易被我误判成 bug ✗
★判据✗★（不变）：连读两次 `dshdigest`，看 `time=`（世界刻）有没有在走 ✓
  · 走 ⇒ 世界在跑 ✓
  · 不走 ⇒ 世界停了（暂停菜单/卡死）✓
  · 读不到 ⇒ 分三种如实说：直连不可达（游戏关了/模组没起/正在重启）／
    桥在但回执没有 `time=`（命令失败或格式变了）／旧后备路也断 ✗

★★2026-11-02 迁移✗★★（审计 §2.3 第 4 条）：
  ★旧版走 `agent.channel.Channel`（CC 计算机车道）✗ 实测 `dshver -> ERR:BridgeError` ✗
  ⇒ 主路早就换成**直连** `127.0.0.1:8766`（`tools/direct.py` ✓ 2~4 ms）✗
  ⇒ 旧版就永远"读不到 time" ⇒ 把"桥路换了"误报成"世界停了"✗★ ✓
★口径✗★：★直连优先✗★；直连不可达且**旧路还能 import** 时，才走一次旧路并在输出里**标明是后备** ✓
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import direct as D  # ★直连：POST 127.0.0.1:8766/cmd（主路 ✓）★

LOG = Path(r"D:\pcl2\.minecraft\versions\All the Mods 9 - To the Sky - atm9sky\logs\latest.log")


def raw_direct(cmd: str, timeout: float = 30.0) -> str:
    """★主路✗★：直连回执；连不上 ⇒ 空串（调用方据此换后备/如实说）"""
    r = D.post(cmd, timeout=timeout)
    return (r or "").strip()


def raw_channel(cmd: str, timeout: float = 40.0) -> str:
    """★后备✗★：旧 CC 车道（`agent/channel.py`）—— 只在直连不可达时试一次"""
    try:
        sys.path.insert(0, str(ROOT / "agent"))
        from channel import Channel  # noqa: E402  ★旧路，只作后备★
        ch = Channel("cmd0", verbose=False)
        return (ch.cmd(cmd, timeout=timeout, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def main() -> int:
    h = D.health(timeout=1.5)
    use_direct = bool(h and "ok" in h)
    lane = "直连 127.0.0.1:8766（主路 ✓）" if use_direct else "旧 CC 车道（后备 —— 主路直连不可达）"
    print("health=%r ⇒ 通道=%s" % (h, lane))
    raw = raw_direct if use_direct else raw_channel

    a = raw("execute as Bot at Bot run dshver")
    print("dshver -> %s" % (a.splitlines()[0][:100] if a else "(空)"))
    if not use_direct and (not a or a.startswith("ERR:")):
        print("★直连不可达 ＋ 后备路也断 ⇒ 最可能是**游戏关了/正在重启**（≠世界停）✗★")
        j = latest_log()
        if j:
            print("游戏日志最后 6 行（时间戳能看出它是不是刚关）：")
            for ln in j[-6:]:
                print("   ", ln[:150])
        return 1

    d1 = raw("execute as Bot at Bot run dshdigest 1", 30.0)
    t1 = re.search(r"time=(\d+)", d1)
    print("digest#1 -> %s" % (d1.splitlines()[0][:150] if d1 else "(空)"))
    time.sleep(6.0)
    d2 = raw("execute as Bot at Bot run dshdigest 1", 30.0)
    t2 = re.search(r"time=(\d+)", d2)
    print("digest#2 -> %s" % (d2.splitlines()[0][:150] if d2 else "(空)"))

    if t1 and t2:
        dt = int(t2.group(1)) - int(t1.group(1))
        if dt > 50:
            print("世界刻 6 秒里走了 %d 刻 ⇒ 世界在跑 ✓" % dt)
            return 0
        print("★世界刻 6 秒里只走了 %d 刻 ⇒ 世界停着/被暂停★ ✗" % dt)
        return 1
    # ★★"读到了回执但没有 time=" 与 "完全读不到" 是两件事✗★★（别把它们混成"世界停了"）
    got_any = bool((d1 or "").strip() or (d2 or "").strip())
    if got_any:
        print("★桥在（有回执）但回执里没有 `time=` ⇒ 不是世界停，是**命令失败/回执格式变了**✗★")
    else:
        print("★读不到任何回执 ⇒ 通道断了 或 世界停了★ ✗（两种都要当场查 ✗）")
    j = latest_log()
    if j:
        print("游戏日志最后 6 行：")
        for ln in j[-6:]:
            print("   ", ln[:150])
    return 1


def latest_log():
    """⇒ 游戏日志最后若干行；读不到就**说出原因**（★不许静默吞✗★）"""
    try:
        return LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        print("★读不到游戏日志✗★ %s ⇒ %s: %s" % (LOG, type(e).__name__, str(e)[:120]))
        return None


raise SystemExit(main())
