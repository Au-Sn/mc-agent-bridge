#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_live_test.py -- ★语言层**实机**验收（V1~V8 ✓ 走真的模组事件流 ✓ 真的 `/dshsay` ✓）★

## 为什么要它 ✗（交接 §58.5 ✓）
  语言层的 51 条判据**全是离线**的（合成事件流 ✓ 临时库 ✓ 注入时钟 ✓）
  ⇒ ★★"离线全绿"**不等于**"在游戏里能用"✗★★ ⇒ 这一份专测**真世界**：
    · 真的 `dshevents` 回执（模组发的 ✓ 不是我编的 ✓ P131 ✓）
    · 真的走 `talk.Talk.proactive()`（★**常驻大脑用的就是这一个方法**✗★ 不是另写一份 ✓）
    · 真的 `/dshsay` 出声（回执是模组给的 ✓ 不是我说"我说了"✓）
    · 真的审计落盘（`logs/speech_log.jsonl` ✓）

## CRITERIA（★跑之前先写✗★ ✓ 每条都能用**世界真值**判 ✓）
  V1 世界真值 ：`dshdigest` 必须**给出 `pos=`** ✓（返回 `0` ＝ 假人不在 ⇒ 当场停 ✗）
  V2 事件真值 ：`/damage Bot 2` 之后 ⇒ `dshevents` 里**真出现** `damage hp=… delta=… src=…`
                （★字段名逐字对齐模组源码 ✓ 不是我以为的 ✓★）
  V3 扳机活着 ：把这条事件喂给 `Talk.proactive()` ⇒ **≥1 句**真的被说出去 ✓
                （判据 ＝ `/dshsay` 回执里 `chars=` > 0 ✓ 而且审计里 `line` 非空 ✓）
  V4 出处是库 ：那一行的 `source` 必须是 `corpus:…` ✗ **不许是 `llm`** ✗（用户第 2 条 ✓）
  V5 不刷屏   ：连着打 5 下（同一秒内 ✓）⇒ 主动发言**总数 ≤ 2** ✓（反应类冷却 8s ✓）
  V6 第二种扳机：`/xp add Bot 1 levels` ⇒ 出一条**邀功** ✓（证明不是只有受伤那一条路 ✓）
  V7 缺台词拒掉：把台词库临时清空 ⇒ 同一事件 ⇒ **不发** ✓ 且审计里留下 `deny` ✓
                （★非开放类型不许偷偷走模型✗★ ✓ 世界真值：`dshsay` 一个字都没发 ✓）
  V8 情绪是慢的：整段跑完 ⇒ 审计里的 `mood` 快照**不许每句都变** ✓（≤ 状态数 ✓）

★安全✗★：唯一的动手是 `damage 2`（1 颗心 ✓ 会自然回复 ✓）与 `xp add 1`（1 级 ✓ 无害 ✓）
  破坏性动作（gamemode／挖方块／tp）**一个都不做** ✗
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import talk as T          # noqa: E402  ★就用常驻大脑的那一个类 ✓ 不另写一份 ✓

LOG = ROOT / "logs" / "speech_log.jsonl"


def say(s):
    print(s, flush=True)


def rows(n: int = 40) -> list:
    if not LOG.is_file():
        return []
    out = []
    for ln in LOG.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(ln))
        except Exception as e:
            # 记录：审计行读不了 ⇒ 少算一行（"≤2 句"这类上界判据可能假绿）
            print("[记录] 审计行读不了（少算一行 ⇒ 上界判据可能假绿）：%s"
                  % type(e).__name__, file=sys.stderr)
    return out


def mark() -> int:
    """★数一下现在审计里有多少行 ✗★ ⇒ 后面只看**新增**的 ✓（不拿旧账当证据 ✓）"""
    return len(rows(400))


def wait_events(t, sec: float = 4.0) -> list:
    time.sleep(sec)
    return t.events_since()


def main() -> int:
    ok = True
    t = T.Talk({})                      # ★与 `acp_talk.py` 同一个类 ✓（同一个 `proactive` ✓）
    n0 = mark()

    # ---- V1：世界真值 ----
    d = t.bot_cmd("dshdigest 6", 60.0)
    v1 = ("pos=" in d)
    say("V1 世界真值：digest=%r => %s" % (d[:120], v1))
    if not v1:
        say("★假人不在 ⇒ 后面的都不许跑 ✗（先说清楚，不许把 SKIP 当 PASS ✓）★")
        return 1
    ok &= v1

    t.events_since()                    # ★先把旧事件倒干净 ✗ 免得把历史当成我触发的 ✓
    time.sleep(0.5)

    # ---- V2：事件真值（受伤）----
    r = t.bot_cmd("damage @s 2", 60.0)
    evs = wait_events(t, 4.0)
    dm = [e for e in evs if " damage " in e]
    v2 = bool(dm) and ("hp=" in dm[0]) and ("delta=" in dm[0])
    say("V2 事件真值：damage 回执=%r ｜ 事件=%s => %s" % (r[:40], dm[:1], v2))
    if not dm:
        say("★没收到 damage 事件 ⇒ V3~V8 都无从谈起 ✗★")
        return 1
    ok &= v2

    # ---- V3/V4：扳机活着 ＋ 出处是库 ----
    n = t.proactive(evs)
    new = rows(400)[n0:]
    said = [x for x in new if x.get("line")]
    corpus_only = bool(said) and all(str(x.get("source", "")).startswith("corpus:") for x in said)
    v3 = (n >= 1) and bool(said)
    v4 = corpus_only
    say("V3 扳机活着：proactive 说了 %d 句 ｜ 审计新增 %d 行（有台词的 %d 行）=> %s"
        % (n, len(new), len(said), v3))
    say("V4 出处是库：%s => %s" % ([x.get("source") for x in said], v4))
    for x in new[:4]:
        say("     · [%s] %s ｜ %s" % (x.get("kind"), x.get("line") or ("（没说：%s）" % x.get("deny")),
                                     x.get("mood")))
    ok &= v3 and v4

    # ---- V5：不刷屏（连着打 5 下）----
    n1 = mark()
    for _i in range(5):
        t.bot_cmd("damage @s 1", 60.0)
    evs5 = wait_events(t, 6.0)
    n5 = t.proactive(evs5)
    new5 = rows(400)[n1:]
    spoken5 = [x for x in new5 if x.get("line")]
    v5 = (n5 <= 2) and (len(spoken5) <= 2)
    say("V5 不刷屏：打 5 下 ⇒ 主动说了 %d 句（要 ≤2 ✓）｜ 审计新增 %d 行 => %s"
        % (n5, len(new5), v5))
    ok &= v5

    # ---- V6：第二种扳机（升级）----
    n2 = mark()
    t.bot_cmd("xp add @s 1 levels", 60.0)
    evs6 = wait_events(t, 4.0)
    xp6 = [e for e in evs6 if " xp " in e]
    t.proactive(evs6)
    new6 = [x for x in rows(400)[n2:] if x.get("line")]
    v6 = bool(xp6) and any(x.get("kind") == "邀功" for x in new6)
    say("V6 第二种扳机：xp 事件=%s ｜ 新增说的：%s => %s"
        % (xp6[:1], [(x.get("kind"), x.get("line")) for x in new6], v6))
    ok &= v6

    # ---- V7：缺台词 ⇒ 拒掉（★不许偷偷走模型✗★）----
    #   ⚠ 第一版**没清冷却** ✗ ⇒ 拒的理由是"这类刚说过（冷却 16s）"✗ 而不是"库里没有"✗
    #     （★判据本身错了 ✓ 不是实现错了 ✓ —— 修判据也要写清楚为什么 ✓ P110 ✓）
    keep_lines = t.loop.lines
    t.loop.lines = {"__loose__": []}          # ★临时清空 ✓ 只动内存 ✗ 不碰盘上的库 ✓
    t.loop.gate.last.clear()                  # ★把冷却清零 ✗ 否则测的是冷却不是"缺台词" ✓★
    t.loop.gate.said = []
    t.loop.gate.quiet = 0
    n3 = mark()
    t.bot_cmd("damage @s 1", 60.0)
    evs7 = wait_events(t, 4.0)
    n7 = t.proactive(evs7)
    new7 = rows(400)[n3:]
    denied = [x for x in new7 if x.get("deny") and not x.get("line")]
    v7 = (n7 == 0) and bool(denied) and any("库里没有" in str(x.get("deny")) for x in denied)
    say("V7 缺台词拒掉：说了 %d 句（要 0 ✓ —— ★世界真值：`dshsay` 一次都没发✗★）"
        " ｜ 审计里有 deny 的 %d 行（%s）=> %s"
        % (n7, len(denied), (denied[0].get("deny")[:30] if denied else "无"), v7))
    t.loop.lines = keep_lines
    ok &= v7

    # ---- V8：情绪是慢的 ----
    all_new = rows(400)[n0:]
    moods = [x.get("mood") for x in all_new if x.get("line")]
    v8 = len(set(moods)) <= 5 and len(moods) <= 10
    say("V8 情绪是慢的：整段 %d 句的 `mood` 快照＝%s => %s" % (len(moods), set(moods), v8))
    ok &= v8

    say("---- V1..V8 = %s ----" % ok)
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
