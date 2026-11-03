#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2112_check.py —— v2.11.2 全套检测（★判据先说死 ✗★）

判据：
  C1 `/dshver` = 2.11.2 ✓
  C2 `/dshquiet` 连发两次 ⇒ `since_cmd` **变大**（因为中间没别的东西刷新它 ✓）
     ★这就是"探针不刷新 LAST_CMD_TICK"的硬证据★ ✗
  C3 `damage drown` ⇒ 出现「差点栽水里/呛到了/得上去换口气」✓ **绝不出现「谁打我」** ✗
  C4 `damage mob`   ⇒ 才允许出现「谁打我」那组 ✓
  C5 `damage starve` ⇒ 出现「饿得慌/肚子空了/得找点吃」✓
  C6 快消失的掉落物 ⇒ 因为 `free=0` ⇒ **必须**是「包里没空位」那句 ✓（不是"我去捡"✗）
  C7 干活期间不许插嘴 ⇒ 走着路（有 dsh 指令在刷新）时打它 ⇒ 事件流里 **不应出现 react** ✗
  C8 限流 ⇒ 连打 4 次 ⇒ react 条数应远小于 4 ✓（≥5 秒一条 ✓）
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


def asbot(t: str, tmo: float = 45.0) -> str:
    return raw("execute as Bot at Bot run %s" % t, tmo)


def cursor() -> int:
    r = asbot("dshevents")
    m = re.search(r"cursor=(\d+)", r)
    return int(m.group(1)) if m else 0


def events() -> str:
    return asbot("dshevents")


def chat_since(mark: int) -> str:
    try:
        txt = LOG.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return "读日志失败 %s" % e
    lines = [l for l in txt.splitlines() if "[CHAT]" in l]
    return "\n".join(l.split("[CHAT]", 1)[1].strip()[:120] for l in lines[mark:])


def nchat() -> int:
    try:
        return len([l for l in LOG.read_text(encoding="utf-8", errors="replace").splitlines()
                    if "[CHAT]" in l])
    except Exception:
        return 0


def react_count(since: int) -> int:
    r = asbot("dshevents %d" % since)
    return len(re.findall(r"\breact\b", r))


def main() -> int:
    ver = raw("dshver")
    out.append("C1 dshver -> %s ⇒ %s" % (ver, "PASS" if "2.11.2" in ver else "FAIL ✗（还没重启到 2.11.2 ⇒ 后面不算数 ✗）"))
    if "2.11.2" not in ver:
        (ROOT / "logs" / "v2112_check.txt").write_text("\n".join(out), encoding="utf-8")
        print("V2112: C1 FAIL（还没重开到 2.11.2）")
        return 1

    # 假人要在 ✓
    if "name=Bot" not in asbot("dshdigest 4"):
        out.append("假人不在 ⇒ spawn ✓")
        raw("player Bot spawn")
        time.sleep(2.5)
        raw("gamemode survival Bot")
        time.sleep(1.0)
    out.append("digest -> %s" % asbot("dshdigest 4")[:180])

    # C2 探针不刷新
    a = raw("dshquiet")
    time.sleep(2.5)
    b = raw("dshquiet")
    ga = int((re.search(r"since_cmd=(\d+)t", a) or [0, -1])[1]) if "since_cmd" in a else -1
    gb = int((re.search(r"since_cmd=(\d+)t", b) or [0, -1])[1]) if "since_cmd" in b else -1
    out.append("")
    out.append("C2 a -> %s" % a[:160])
    out.append("C2 b -> %s" % b[:160])
    out.append("C2 since_cmd %s ⇒ %s ⇒ %s" % (ga, gb, "PASS（探针没刷新它 ✓）" if gb > ga else "FAIL ✗"))

    # 等到真正安静（isQuiet 要 300 tick = 15 秒 ✓）
    out.append("")
    out.append("（等 18 秒让它真正安静 ✓ —— isQuiet 要 300 tick ✓）")
    time.sleep(18.0)

    # C3/C4/C5 受击来源
    for cid, src_, want_ok, want_bad in (
            ("C3", "drown", ("差点栽水里", "呛到", "换口气"), ("谁打我", "打我干嘛")),
            ("C4", "mob", ("谁打我", "打我干嘛", "哎", "疼"), ()),
            ("C5", "starve", ("饿得慌", "肚子空了", "找点吃的"), ())):
        c0, m0 = cursor(), nchat()
        out.append("")
        out.append("%s damage %s -> %s" % (cid, src_, raw("damage Bot 2 %s" % src_)[:60]))
        time.sleep(3.0)
        tail = chat_since(m0)
        ev = events()
        got = [w for w in want_ok if w in tail]
        bad = [w for w in want_bad if w in tail]
        evi = "react" in ev
        out.append("%s 聊天尾部 -> %s" % (cid, tail.replace("\n", " | ")[-200:] or "(空)"))
        out.append("%s 命中好词=%s ｜ 命中禁词=%s ｜ 事件流里有 react=%s ⇒ %s"
                   % (cid, got, bad, evi,
                      "PASS" if (got and not bad and evi) else "FAIL ✗"))
        time.sleep(6.0)   # 让开限流 ✓（≥5 秒一条 ✓）

    # C6 快消失的掉落物（free 现在是 0 ✓ ⇒ 必须是"没空位"那句 ✓）
    m0 = nchat()
    free = (re.search(r"free=(\d+)", asbot("dshdigest 4")) or [0, "?"])[1]
    out.append("")
    out.append("C6 当前 free=%s ✓ 生成一个 Age=5900 的掉落物 ✓" % free)
    out.append("   summon -> %s" % raw("summon item 4120 72 10 {Age:5900s,Item:{id:\"minecraft:dirt\",Count:1b}}")[:80])
    time.sleep(6.0)
    tail = chat_since(m0)
    ok6 = ("没空位" in tail) or ("塞不下" in tail)
    out.append("C6 聊天尾部 -> %s ⇒ %s" % (tail.replace("\n", " | ")[-200:] or "(空)",
                                        "PASS（说了没空位 ✓）" if ok6 else "FAIL ✗（可能说了'我去捡'✗）"))

    # C7 干活期间不许插嘴
    time.sleep(16.0)
    c0 = cursor()
    out.append("")
    out.append("C7 先起一条走路（让它有 dsh 指令在刷新 ✓）")
    out.append("   walk -> %s" % asbot("dshwalk 4131 71 22 15000")[:150])
    time.sleep(2.0)
    raw("damage Bot 2 mob")
    time.sleep(3.0)
    n7 = react_count(c0)
    out.append("C7 干活期间 react 条数 = %d ⇒ %s" % (n7, "PASS（没插嘴 ✓）" if n7 == 0 else "FAIL ✗"))
    asbot("dshwalk stop")
    time.sleep(16.0)

    # C8 限流
    c0 = cursor()
    for _ in range(4):
        raw("damage Bot 2 mob")
        time.sleep(0.4)
    time.sleep(3.0)
    n8 = react_count(c0)
    out.append("")
    out.append("C8 连打 4 次 ⇒ react 条数 = %d ⇒ %s" % (n8, "PASS（被限流 ✓）" if n8 <= 1 else "FAIL ✗"))

    (ROOT / "logs" / "v2112_check.txt").write_text("\n".join(out), encoding="utf-8")
    print("V2112: written %d lines; see logs/v2112_check.txt" % len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
