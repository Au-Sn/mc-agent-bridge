#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""event_pump.py -- ★把**内存里的事件**拉出来落盘★（§79.344 ✗ 2026-10-24）

★★为什么必须有它✗★★：★模组的 `ev()`（`DshBridgeMod.java:1548`）**只写内存队列**✗★ ——
★事件是"★`/dshevents [since]` **增量拉取** ✗ 有界 ✗ 不涨内存★"的设计✗★ ⇒
★★**没有人拉 ⇒ 事件只在内存里活着** ✗ 掉线/重启就**永久丢**✗★★ ✓
★今天就是这么发现的：★真死**自然发生了** ✗ 而 `logs/bot_events.log` **21 天**没写过一行✗★ ⇒
★拉了内存才发现 **#141/#142 那两条 `bot_died` 一直在里面**✗★ ✓
★★⇒ ★这个泵：★拉一次 ⇒ 去掉 `#NNN ` 编号 ⇒ 按 `death_evidence()` 认的形状追加落盘✗★★ ✓
★用法✗★：`py tools/event_pump.py`（★建议每次世界侧操作后跑一次 ✗ 或定时跑✗★）
★（★它**不是判据** ✗ 只打印 `EVENTPUMP … done` ✗ 所以不进闸门、也不进反驳扫描✗★）✗★ ✓
"""
from __future__ import annotations

import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOG = ROOT / "logs" / "bot_events.log"
RAW = ROOT / "logs" / "bot_events_pulled.log"


def main() -> int:
    import mcp_core as C
    raw = C.dsh("dshevents", 25.0) or ""
    if not raw or "dshevents watched=" not in raw:
        print("EVENTPUMP ok=0 reason=no_channel")
        return 4                     # ★测不了 ✗ 不是坏（★口径同 §79.285✗★）
    RAW.write_text(raw, encoding="utf-8")
    head, _, body = raw.partition("|")
    evs = [p.strip() for p in body.split("|") if p.strip()]
    evs = [e for e in evs if not e.startswith("(older")]     # ★"★更早的没显示★"那行不是事件✗★
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    out = []
    for e in evs:
        m = re.match(r"^#(\d+)\s+(.*)$", e)
        out.append("%s\t%s" % (stamp, m.group(2) if m else e))
    if out:
        with LOG.open("a", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
    print("  ★包头✗★：%s" % head.strip()[:110])
    print("  ★落盘✗★：**%d** 条 ⇒ `logs/bot_events.log`" % len(out))
    died = [x for x in out if "bot_died" in x or "bot_revived" in x]
    for d in died[-4:]:
        print("    ★ %s" % d[:140])
    import events_log as E
    ev = E.death_evidence()
    print("  ★death_evidence✗★：state=%s deaths=%s revived=%s note=%s"
          % (ev.get("state"), ev.get("deaths"), ev.get("revived"), ev.get("note", "")[:70]))
    print("EVENTPUMP ok=1 pulled=%d died=%d" % (len(out), len(died)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
