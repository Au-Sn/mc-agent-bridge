#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""react_probe.py —— ★反应逻辑的最小验证★（★一次状态读都不许落在窗口里✗★）

为什么重写 ✗（上一版 `v2112_check.py` 的教训 ✓ 我自己的错 ✗）：
  上一版每步都用 `dshevents`/`dshdigest` 去读状态 ✓ 而这些**都是 dsh 指令** ✗
  ⇒ 它们刷新 `LAST_CMD_TICK` ⇒ `isQuiet()`（安静 300 tick ＝ 15 秒）**永远达不到** ✗
  ⇒ 反应进不了门 ⇒ 四条反应测试全 FAIL ✗ —— **测的是我自己，不是模组** ✗（P57 家族 ✓）

这一版的纪律 ✓：
  ① 先把游标读出来（**唯一**一次 dsh 调用 ✓）
  ② 然后**纯粹安静 20 秒**（一条 dsh 都不发 ✓ 只用原版 `damage` / `summon` ✓ 它们不碰 LAST_CMD_TICK ✓）
  ③ 窗口结束**才**一次性把事件流读回来 ✓ ＋ 聊天尾部从 `latest.log` 读（**读文件**✗ 不是游戏指令 ✓）
"""
from __future__ import annotations

import re
import sys, paths as PA
import time
from pathlib import Path

ROOT = PA.ROOT
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)
LOG = PA.LATEST_LOG
out: list[str] = []


def raw(t: str, tmo: float = 45.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR %s: %s" % (type(e).__name__, str(e)[:90])


def nchat() -> int:
    try:
        return len([l for l in LOG.read_text(encoding="utf-8", errors="replace").splitlines()
                    if "[CHAT]" in l])
    except Exception:
        return 0


def chat_since(mark: int) -> list[str]:
    try:
        txt = LOG.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        # 记录：读不到 ≠ 没有聊天（不许把"读不了"当成"没说话"）
        print("[记录] 聊天日志读不到（≠ 没有聊天）：%s" % type(e).__name__,
              file=sys.stderr)
        return []
    lines = [l for l in txt.splitlines() if "[CHAT]" in l]
    return [l.split("[CHAT]", 1)[1].strip()[:120] for l in lines[mark:]]


# ── ① 唯一的一次"前置读"：游标 ＋ 假人在不在 ✓（读完之后**再也不碰 dsh** ✗）
dig = raw("execute as Bot at Bot run dshdigest 4")
if "name=Bot" not in dig:
    out.append("假人不在 ⇒ spawn ✓")
    raw("player Bot spawn")
    time.sleep(2.5)
    raw("gamemode survival Bot")
    time.sleep(1.0)
    dig = raw("execute as Bot at Bot run dshdigest 4")
ev0 = raw("execute as Bot at Bot run dshevents")
cur = int((re.search(r"cursor=(\d+)", ev0) or [0, 0])[1])
free = (re.search(r"free=(\d+)", dig) or [0, "?"])[1]
out.append("前置 ✓ free=%s cursor=%s ｜ 假人：%s" % (free, cur, dig[:120]))
out.append("★★ 从这里开始**一条 dsh 都不发** ✗ —— 先安静 20 秒让 isQuiet 成立 ✓（要 300 tick ✓）")
mark = nchat()
time.sleep(20.0)

# ── ② 窗口：只用**原版**指令（不刷新 LAST_CMD_TICK ✓）
out.append("")
out.append("打：drown -> %s" % raw("damage Bot 2 drown")[:50])
time.sleep(6.5)
out.append("打：starve -> %s" % raw("damage Bot 2 starve")[:50])
time.sleep(6.5)
out.append("打：mob_attack -> %s" % raw("damage Bot 2 mob_attack")[:50])
time.sleep(6.5)
out.append("地上放一个快消失的（Age=5990）-> %s"
           % raw('summon item 4120 72 10 {Age:5990s,Item:{id:"minecraft:dirt",Count:1b}}')[:50])
time.sleep(6.5)

# ── ③ 窗口结束：**一次性**读回来 ✓
ev = raw("execute as Bot at Bot run dshevents %d" % cur)
chats = chat_since(mark)
reacts = re.findall(r"react [^#]*", ev)   # ★v2.11.3：打**整行**✓（上次正则把 src=/said= 吞了 ✗）
out.append("")
out.append("===== 事件流里的 react =====")
out.append("\n".join(reacts) or "（一条都没有 ✗）")
out.append("")
out.append("===== 窗口内的聊天（latest.log ✓ 读文件不是指令 ✓）=====")
out.append("\n".join(chats) or "（空 ✗）")

body = "\n".join(chats)
checks = [
    ("C3 溺水", ("差点栽水里" in body) or ("呛到" in body) or ("换口气" in body),
     ("谁打我" in body) or ("打我干嘛" in body)),
    ("C4 挨打", ("谁打我" in body) or ("打我干嘛" in body) or ("哎！" in body), ()),
    ("C5 饿", ("饿得慌" in body) or ("肚子空了" in body) or ("找点吃的" in body), ()),
    ("C6 没空位", ("没空位" in body) or ("塞不下" in body), ()),
]
out.append("")
for name, ok, bad in checks:
    out.append("%s ⇒ %s%s" % (name, "PASS" if (ok and not bad) else "FAIL ✗",
                              "（★还命中了禁词✗★）" if bad else ""))
out.append("")
out.append("react 事件条数 = %d ✓（>0 才说明反应真的响了 ✓）" % len(reacts))

(ROOT / "logs" / "react_probe.txt").write_text("\n".join(out), encoding="utf-8")
print("REACT: react_events=%d lines=%d" % (len(reacts), len(out)))
