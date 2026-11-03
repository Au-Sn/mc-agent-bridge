#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""events_log.py -- ★把模组的 **ASCII 事件**捞出来、落盘、可判✗★（欠账 ⑬ ✓ 2026-10-02 ✓）

WHY ✓（★2026-10-02 那次事故✗★）：★假人被我跑下平台之后 ✗ 我**拿不出**一条可读证据✗★
  —— ★日志里没有 `bot_died` ✗ CC 回执过通道读出来是 `????`（★中文被吃 ✗ P13/P38✓★）★
  ⇒ ★而模组**本来就在发 ASCII 事件**✗★（`DshBridgeMod.java:275/302/1154` 的
    `ev("bot_died", "phase=stashed who=Bot kept_items=81")` ✓）
  ⇒ ★缺口不在"发" ✗ 在"**没人接、没人存、没人判**"✗★ ✓

口径 ✓
  ① ★只收 **ASCII 事件行**✗★（★含非 ASCII 的整行**一律丢**✗ —— ★不许把 `?` 存进账本✓★）
  ② ★去重✗★（同一行在"最近见过"的窗口里只记一次 ✓ 免得轮询把同一事件记十遍 ✓）
  ③ ★落盘格式✗★：`<ISO 时刻>\t<原始事件行>\n` ✓ 一行一条 ✓ 纯 ASCII ＋ 时间戳 ✓
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOG = ROOT / "logs" / "bot_events.log"
# ★事件行的形状✗★：★小写名字 ＋ 若干个 `k=v`✗★（`v` 里不许有空白 ✓）
EVENT = re.compile(r"^([a-z][a-z_0-9]{2,})((?: [a-z_0-9]+=[^\s]+)+)$")
HEXOK = re.compile(r"^[\x20-\x7e]+$")
KEEP_SEEN = 400


def extract_ascii(text: str):
    """从一段**可能很脏**的回执里捞出 ASCII 事件行 ✓（★非 ASCII 整行丢 ✗ 并计数✓★）

    ★★2026-10-03 修两处✗★★（★欠账 ㉑ ✓ 世界里实测✓★）：
      ① ★事件**不是一行一条**✗★ —— 模组把整段摊在**一行**里 ✗ 用 **`|`** 分隔✗★
         （★形状✗★：`dshevents watched=Bot total=15 new=15 cursor=15 | #1 auto_greet who=… | #2 …`✓★）
         ⇒ ★先按 `|` 与换行**都**切开✓★
      ② ★每条带 **`#<n>`** 前缀✗★ ⇒ ★允许它 ✗ 否则全被当"不认识"丢掉✗★ ✓
    """
    found, dropped = [], 0
    for piece in re.split(r"[|\n]", text or ""):
        ln = piece.strip()
        if not ln:
            continue
        if not HEXOK.match(ln):
            dropped += 1
            continue
        ln = re.sub(r"^#\d+\s+", "", ln)          # ★剥掉 `#3 ` 这种序号✗★
        m = EVENT.match(ln)
        if m and ln.startswith("dshevents") is False:
            found.append(ln)
        else:
            dropped += 1
    return found, dropped


def append(lines, log: Path = LOG, seen=None):
    """★落盘 ✗ 去重 ✓ 只写 ASCII✓★ ⇒ (写了几条, 跳了几条)"""
    log.parent.mkdir(parents=True, exist_ok=True)
    seen = seen if seen is not None else load_seen(log)
    wrote = skipped = 0
    import time as _t
    with log.open("a", encoding="ascii", errors="strict", newline="\n") as f:
        for ln in lines:
            if ln in seen:
                skipped += 1
                continue
            if not HEXOK.match(ln):
                skipped += 1
                continue
            f.write("%s\t%s\n" % (_t.strftime("%Y-%m-%dT%H:%M:%S"), ln))
            seen.add(ln)
            wrote += 1
    if len(seen) > KEEP_SEEN:
        for old in list(seen)[:len(seen) - KEEP_SEEN]:
            seen.discard(old)
    return wrote, skipped


def load_seen(log: Path = LOG):
    s = set()
    if log.is_file():
        for ln in log.read_text(encoding="ascii", errors="replace").splitlines()[-KEEP_SEEN:]:
            if "\t" in ln:
                s.add(ln.split("\t", 1)[1])
    return s


def poll_once(timeout: float = 25.0):
    """★问一次模组 ✗ 捞一遍 ✗ 落盘✓★（★走 `mcp_core.dsh` ✗ 与别的工具同一条路✓★）

    ★★2026-10-03 修✗★★（★欠账 ㉑ ✓ 实测✓★）：★命令是 **`dshevents`（不带参数）**✗★ ——
      ★我先前写的是 `dshevents tail`✗ ⇒ ★原生报"参数不对"✗ ⇒ 过 CC 变 `????` ＋ `<--[??]`✗★
      ⇒ ★于是"读不到事件流"被误读成"**没有事件**"✗★ ✓（★又是"我的窗口"那个形状 ✓ P170 ✓★）
    ★回执形状✗★：`dshevents watched=Bot total=15 **new=15 cursor=15** | #1 auto_greet who=… | …` ✓
      ⇒ ★它自带 `cursor`（★只给**新**的✓★）⇒ ★轮询正合适 ✗ 去重那层是双保险✓★
    """
    from mcp_core import dsh
    raw = dsh("dshevents", timeout) or ""
    found, dropped = extract_ascii(raw)
    wrote, skipped = append(found)
    return {"found": len(found), "dropped": dropped, "wrote": wrote, "skipped": skipped,
            "raw_len": len(raw)}


def death_evidence(path=None):
    """★★⑬ 的解锁器✗★★：★一次**真死**之后 ✗ 这条会说清"保险到底还了多少"✗★（2026-10-03 ✓）

    ★判据（★先写死 ✗ 全是世界真值给的✗★）★
      ① ★`bot_died` 必须带 `kept_items=N`✗★（★"扣下了一包" ✗ N 件✓★）
      ② ★`bot_revived` 必须带 `back_items=M`✗★（★"还回去"✗★）
      ③ ★成对才算答完✗★（★只有死没复活 ⇒ 明写"**还缺复活**" ✗ 不许说"没事"✗★）
      ④ ★还的件数**少于**扣的 ⇒ 明写差额✗★（★不许只报"复活了"✗★）
    ★没发生过真死 ✗ 就老实说"**还没发生**"✗★ —— ★这不是红 ✗ 是"待发生"✗★ ✓
    （★不许为了让它变绿去故意弄死假人 ✓★）
    """
    import pathlib
    p = pathlib.Path(path) if path else (pathlib.Path(__file__).resolve().parent.parent
                                        / "logs" / "bot_events.log")
    if not p.is_file():
        return {"state": "no-log", "note": "★还没有事件账本（★说明连事件都没落过盘✓★）"}
    died, revived = [], []
    for ln in p.read_text(encoding="ascii", errors="replace").splitlines():
        if "\tbot_died " in "\t" + ln or ln.startswith("bot_died "):
            died.append(ln)
        elif "bot_revived" in ln and ("\t" in ln or ln.startswith("bot_revived")):
            revived.append(ln)

    def _n(line, key):
        m = re.search(key + r"=(\d+)", line)
        return int(m.group(1)) if m else None

    kept = [_n(x, "kept_items") for x in died]
    back = [_n(x, "back_items") for x in revived]
    d = {"state": "none", "deaths": len(died), "revived": len(revived),
         "kept_items": kept, "back_items": back}
    if not died:
        d["note"] = "★还没发生过真死 ✗ 待发生（★不许为了它去弄死假人✓★）"
        return d
    if not revived:
        d["state"] = "died-no-revive"
        d["note"] = ("★死了 %d 次 ✗ 而**一条复活都没有**✗ ⇒ ★这不是「没事」 ✗ "
                     "是**还缺复活**✗★（★先查 D3 那三档 ✓★）" % len(died))
        return d
    # ★★2026-10-24（★§79.344 ✗ 真死当天修✗★）✗★★：★真事件流是**两个阶段**✗★ ——
    #   ot_died phase=enter（★死亡开始 ✗ **没有**件数，它本来就不该有✗★）✗
    #   ot_died phase=stashed … kept_items=95（★保险扣下了多少 ✗ **这才是有数的那个**✗★）✗★
    #   ⇒ ★**取最后一个非空** ✗ 不再要求每一条 ot_died 都带 kept_items=✗★ ✓
    #   ★（★这不是放宽判据 ✗ 是把判据**对准真实的凭证形状** ✗ 依据：今天拉到的 #141/#142✗★）✗★ ✓
    _kk = [x for x in kept if x is not None]
    _bb = [x for x in back if x is not None]
    k0 = _kk[-1] if _kk else None
    b0 = _bb[-1] if _bb else None
    if k0 is None or b0 is None:
        d["state"] = "unreadable"
        d["note"] = "★凭证里**缺 `kept_items=` 或 `back_items=`**✗ ⇒ ★读不到就不许判「还了」✗★"
        return d
    if b0 < k0:
        d["state"] = "short"
        d["note"] = "★扣了 **%d** 件 ✗ 只还回 **%d** 件 ✗ 差 **%d**✗★（★据实 ✗ 不许说「复活了」就完✓★）" % (
            k0, b0, k0 - b0)
        return d
    d["state"] = "ok"
    d["note"] = "★成对 ✓ 扣 **%d** 件 ✗ 还 **%d** 件✗★ ✓（★⑬ 的答案就是这个✗★）" % (k0, b0)
    return d


if __name__ == "__main__":
    print("★events_log 自检（★不连世界 ✗ 只验「怎么捞、怎么存」✗ ✓）★")
    sample = ("bot_died phase=stashed who=Bot kept_items=81\n"
              "★中文事件★（该被丢 ✓）\n"
              "bot_revived phase=done who=Bot back_items=81\n"
              "walk_refuse kind=edge why=step_down=2\n"
              "???\n")
    f, d = extract_ascii(sample)
    print("  捞到 %d 条 ✓ 丢掉 %d 行 ✓" % (len(f), d))
    for ln in f:
        print("    %s" % ln)
