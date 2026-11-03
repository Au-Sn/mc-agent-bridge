#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_loop.py -- ★"主动扳机"的**决策**那一半★ ✓（纯函数 ✓ 离线可测 ✓ 2026-09-30 ✓ 用户第 1／5 条 ✓）

## 为什么单开一层 ✗（用户第 1 条要点 ✓）
  「把闸门从**被动应答**改成**主动扳机**」✓
  · `talk.should_reply()` ⇒ 只管"**别人说话** ⇒ 我接不接" ✗
  · `talk.events_since()` ⇒ 事件流一直在拉 ✓ 可**除了 `chat` 全被丢掉** ✗✗
    （★受击／掉落快过期／升级／被 tp ／走完一趟 ⇒ **一律没人看**✗★）
  ⇒ 这一层就干"**事件流 ⇒ 该说什么**"✗，而且**不碰世界**✗ 不调模型 ✗ 不发消息 ✗
  ⇒ ★`talk.py` 只负责"把动作发出去"✗★（决策与副作用分开 ⇒ 决策**能被离线判据**✓）

## 分工（一张图 ✓）
  ```
  talk.events_since()          # 有 I/O（网关 ⇒ 模组 ✓）
        ↓  ['#12 damage hp=3.0 …', '#13 chat …', …]
  speech_loop.plan(evs, st)    # ★纯函数★ ✓ ⇒ [Action,…]（含"为什么"✓）
        ↓
  talk.emit(action)            # 出口只有 `/dshsay` ✓（`Action.line` 已经是**填好真值**的句子 ✓）
        ↓
  logs/speech_log.jsonl        # ★审计：为什么说了这句★ ✓（用户第 5 条 ✓）
  ```

## 三条硬规矩（★这一层最容易犯的错✗★）
  ① **不硬编事件名** ✗ ⇒ 名字只从 `speech.EVENT_KINDS` 来 ✓（它由 E11 与模组源码对账 ✓ P131 ✓）
  ② **不编内容** ✗ ⇒ 台词里的 `{槽位}` 只填**事件里真有的字段** ✓（`inv` 事件**没有物品名**✗
     ⇒ 绝不许说"捡到了铁"✗ ⇒ 那种句子在库里直接**用不上** ✓ 而不是"我说说看"✗）
  ③ **说出声才算数** ✗ ⇒ 过闸之后必须调 `st.spoke(a)` ✓ 不然冷却／额度／退避全成了摆设 ✓
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import corpus as C
import mood as MO
import speech as S

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass



@dataclass
class Action:
    """★一条"该说但还没发"的话★ ✓（★发出去之后 `talk.py` 拿这行写审计 ✓★）"""
    intent: S.Intent
    line: str = ""
    source: str = "corpus"          # `corpus:<键>` ✓ ／ `llm` ✓
    text: str = ""                  # ★过完**渲染配置**的样子✗★ ✓（词表/句长/emoji/错字 ✓ 用户第 6 条 ✓）
    delay: float = 0.0              # ★时序**最后**算出来的那一份✗★ ✓（用户第 6 条 ✓）
    sent: bool = False              # ★真发出去了吗✗★ ✓（`Loop.spoke()` 标它 ✓ 审计里看得见 ✓）
    deny: str = ""                  # **没过闸**的原因 ✓（留痕 ✓ 不许静默丢弃 ✗）

    def audit(self) -> dict:
        """★审计一行★ ✓（用户第 5 条："为什么说了这句话"要可查 ✓）"""
        it = self.intent
        return {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": it.kind,
                "why": it.why, "who": it.who, "mood": it.mood, "rel": it.relationship,
                "payload": it.payload, "source": self.source, "line": self.line,
                "delay_s": self.delay, "sent": self.sent, "deny": self.deny}


@dataclass
class Loop:
    """★决策状态★ ✓（纯数据 ✓ 不持有世界 ✓ 不持有网络 ✓）"""
    gate: S.Gate = field(default_factory=S.Gate)
    lines: dict = field(default_factory=dict)       # 台词库 ✓（`corpus.load()` 的产物 ✓）
    mood_state: "MO.Mood" = field(default_factory=MO.Mood)   # ★一个慢变量✗★ ✓（用户第 3 条 ✓）
    mood: str = "平静"                              # ★语气快照✗★ ✓（可能是 `标准/傲娇/梗` ✓）
    rel: str = "陌生人"
    last_speech: float = 0.0                        # 上次"出过声"（含模组自己出的 ✓）
    last_player: float = 0.0                        # 上次玩家说话 ✓（退避靠它归零 ✓）
    job_phase: dict = field(default_factory=dict)   # 事件里推出来的"在干什么" ✓
    seen_seq: int = 0                               # ★水位★ ✗（同一行事件不许说两遍 ✓）
    quiet_since: float = 0.0                        # idle 的起点 ✓
    idlesaid: float = 0.0                           # 上次"没话找话"的时刻 ✓
    min_idle: float = 180.0                         # ★安静多久才允许找话✗★（用户要的节流 ✓）
    skipped: list = field(default_factory=list)     # ★"看见了但故意不说"的留痕✗★ ✓（判据要能数 ✓）

    def tell(self, intent: S.Intent) -> Action:
        """★过闸 ⇒ 定稿（抽台词 ✓）★ ✗（传**意图** ✓ 返回**动作**✓）

        ★★"说了"必须在**决策那一刻**记账✗★★（2026-09-30 **实机**撞到 ✓ ⇒ P135 ✓）：
          ✗ 原来记账在 `talk.proactive` **发完之后** ✗ ⇒ 同一批里 5 条意图
            **全都看到"还没说过"**✗ ⇒ 一起过闸 ✗ ⇒ 实测**一秒钟冒出 3 句**✗
            （★正是用户第 1 条最恨的那种刷屏★ ✓）
          ⇒ 口径 ✓：**过闸 ⇒ 当场记账**✗（冷却／额度／退避立刻生效 ✓）
            `spoke()` 只确认"真发出去了" ✓ 不再改账 ✗（否则退避会被加两遍 ✓）

        ★★一道额外的闸✗★：**非开放对话不许走模型** ✗（用户第 2 条 ✓）
          ⇒ 库里没有这一类的台词 ⇒ 不是"那就让模型写"✗ 而是**明确拒掉 ＋ 记原因**✓
        """
        a = Action(intent=intent)
        ok, why = self.gate.should_speak(intent)
        if not ok:
            a.deny = why
            return a
        line, src = S.render(intent, self.lines)
        if line:
            a.line, a.source, a.deny = line, src, ""
            self.gate.spoke(intent)                    # ★当场记账✗★
            self.last_speech = float(self.gate.now_fn())
            self.idlesaid = self.last_speech
            return a
        a.line, a.source = "", src
        a.deny = ("库里没有 `%s` 这一类的句子 ✗（★这一类**不许**走模型 ✓ 用户第 2 条 ✓★）"
                  % intent.kind)
        return a

    def spoke(self, a: Action) -> None:
        """★确认"这一句真发出去了"✗★ ✓ —— ★记账**已经在 `tell()` 里做完了**✗★

        ⚠ 这里**不许**再动 `gate` ✗：一调动 ⇒ 同一句会让退避加两次 ✓ 冷却被拉长一倍 ✓
        """
        a.sent = True

    def heard_player(self) -> None:
        """★玩家说话了 ⇒ 退避**立刻归零**★ ✓（用户点名 ✓）"""
        self.gate.heard(True)
        self.last_player = float(self.gate.now_fn())


def _cues(st: Loop) -> str:
    """★"由头"是什么✗★ ✓ —— ★没有由头就不许没话找话✗★（用户原话 ✓）

    由头 = 我们**真知道**的事 ✓：手里在干什么 ✓（事件／账本推出来的 ✓）
    ★一律**不编**✗★：没有由头 ⇒ 空串 ⇒ `on_idle` 返回 None ⇒ 就不出声 ✓
    """
    job = str(st.job_phase.get("job") or "").strip()
    if job:
        return "手里的活：%s" % job
    return ""


def plan(evs: list, st: Loop, now: float = None, transitions: list = None) -> list:
    """★事件流（＋任务账本的迁移）⇒ 该说的动作★ ✓（★纯函数✗★：不发消息 ✓ 只改 `st` 自己的账 ✓）

    ★★三件必须做对的事★★ ✗：
      ① **水位**（`st.seen_seq`）✗ —— 事件流是**增量**拉的 ✓ 但重连会从旧序号再来一遍 ✓
         ⇒ 认序号 ⇒ ★同一行事件**绝不说第二遍**✗★（不然一重启就复读 ✓）
      ② **模组出过声 ⇒ 我们闭嘴**✗ —— `auto_reply`／`idle_line` 是**模组自己说的**✓
         ⇒ 当成"刚出过声"✓（`last_speech` 推进 ✓）⇒ ★不跟它抢话✗★
      ③ **任务迁移走"我们自己的账本"** ✗ —— `walk_*` 是**模组**的事件 ✓（照抄它的名字 ✓）
         而"任务"是**我们这一侧**的概念 ✓（`jobs` 账本 ✓ 见 `talk.py` ✓）
         ⇒ 用 `transitions=[(任务名, 旧阶段, 新阶段)]` **显式喂进来** ✓
         ★绝不为了它去编一个模组事件名✗★（P131 ✓）
    """
    now = float(now if now is not None else st.gate.now_fn())
    out: list = []
    # ★★情绪：**一次 plan 只变一次脸**✗★ ✓（用户第 3 条："不是每句话都重演一遍"✗ ✓）
    #   ⇒ 口径 ✓：先把这批事件喂给慢变量 ✓ 走完最短驻留 ✓ **再取一次语气快照**✓
    #     ⇒ 这一批里**所有**意图用的是**同一个**语气 ✓（M6 判据钉的就是这件事 ✓）
    for raw in (evs or []):
        _seq, _kind, _f = S.parse_event_line(raw)
        it0 = S.on_event_line(raw) if _kind else None
        if it0 is not None:
            st.mood_state.feed(MO.from_intent(it0), now)
    for (_job, _prev, nowp) in (transitions or []):
        st.mood_state.feed(MO.from_phase(nowp), now)
    st.mood_state.tick(now)
    st.mood = st.mood_state.tone()                  # ★语气层✗★（台词库键里的那一层 ✓）
    for raw in evs or []:
        seq, kind, facts = S.parse_event_line(raw)
        if seq is None:
            continue
        if seq <= int(st.seen_seq):
            continue                       # ★水位以下 ⇒ 早就处理过了 ✗（不复读 ✓）
        st.seen_seq = seq
        low = str(kind).lower()
        if low == "chat":
            st.heard_player()
            st.mood_state.feed("player_said", now)   # ★有人搭理 ⇒ 精神点 ✓（很小的量 ✓）★
            continue
        if low in ("auto_reply", "idle_line"):
            st.last_speech = now           # ★模组出过声 ⇒ 我们不叠一句 ✗★
            st.gate.heard(True)            # 有人（模组）回应过 ⇒ 退避归零 ✓
            st.skipped.append({"seq": seq, "kind": low, "why": "模组自己出了声 ⇒ 不叠一句"})
            continue
        if low in S.SKIP_EVENTS:
            # ★"看见了但故意不说"✗★ —— **留痕** ✓（判据要能数出来 ✓ 不静默丢 ✓）
            st.skipped.append({"seq": seq, "kind": low, "why": S.SKIP_EVENTS[low]})
            continue
        it = S.on_event_line(raw)
        if it is None:
            st.skipped.append({"seq": seq, "kind": low, "why": "★不在触发表里 ✗（不硬编 ✓）"})
            continue
        _note_job(st, it)
        it.mood, it.relationship = st.mood, st.rel
        out.append(st.tell(it))
    # ── 我们自己的任务账本 ⇒ 播报／邀功／求助（★用户第 1 条第一个扳机✗★）────────
    for (job, prev, nowp) in (transitions or []):
        it = S.on_job_transition(prev, nowp, job)
        if it is None:
            continue
        st.job_phase["job"] = str(job)
        it.mood, it.relationship = st.mood, st.rel
        out.append(st.tell(it))
    # ── 没话找话（★必须有由头 ✗ 宁可不说话 ✗★）──────────────────────────────
    idle_s = now - max(st.last_speech or now, st.quiet_since or 0.0)
    if idle_s >= st.min_idle:
        it2 = S.on_idle(idle_s, _cues(st), min_idle=st.min_idle)
        if it2 is not None:
            it2.mood, it2.relationship = st.mood, st.rel
            out.append(st.tell(it2))
    return out


def _note_job(st: Loop, it: S.Intent) -> None:
    """★从事件里**顺手**记下"在干什么"✗★ ✓ —— 给 `on_idle` 当**由头** ✓（不编 ✓）

    ⚠ 只有**真带得出**"在干什么"的事件才记 ✓：
      `walk_done want=x,y,z` ⇒ 记成"走到 x,y,z" ✓（位置是**事件里真有的** ✓）
      别的（受伤／升级／背包变了）⇒ 说明不了"手上的活" ✗ ⇒ **不记** ✗（宁可由头为空 ✓）
    """
    pl = it.payload
    if "want" in pl:
        st.job_phase["job"] = "走到 %s" % pl["want"]
    elif "item" in pl and "left_s" in pl:
        st.job_phase["job"] = "盯着 %s" % pl["item"]


# ── 任务账本 ⇒ 迁移（★纯函数✗★ ⇒ 判据能离线跑 ✓）──────────────────────────────
# ★为什么单独放这儿✗★：账本是**我们自己**的（`tools/jobs_store.py` ✓ 状态 `open/done/…` ✓）
#   ★不是模组事件✗★ ⇒ 不许为了它去编一个模组事件名 ✗（P131 ✓）
#   ⇒ 口径 ✓：读账本 ⇒ 和上次快照比 ⇒ 出 `(任务名, 旧状态, 新状态)` ✓ 喂给 `plan` ✓
JOB_START = "start"          # ★"第一次看见这个任务" ⇒ 出发✗★（`speech.on_job_transition` 认这个词 ✓）


def job_transitions(prev: dict, jobs: list) -> tuple:
    """★`(旧快照, 任务清单) ⇒ (迁移列表, 新快照)` ✓★ —— ★纯函数 ✓ 不读文件 ✓ 不碰世界 ✓★

    · 任务**第一次出现** ⇒ `("新任务", …)` ⇒ 当 `start` 处理 ✓（播报"出发"✓）
    · 状态**变了** ⇒ 原样报出来 ✓（`done` ⇒ 邀功 ✓ `failed`/`stuck`/`blocked` ⇒ 播报/求助 ✓）
    · ★状态名**照抄账本**✗★（`open/done/failed/…` ✓）—— 不许换个我更喜欢的词 ✗（P122/P131 ✓）
    """
    out = []
    snap = {}
    for j in jobs or []:
        jid = str(j.get("id") or "")
        if not jid:
            continue
        st_now = str(j.get("status") or "open")
        snap[jid] = st_now
        name = str(j.get("goal") or jid)
        old = (prev or {}).get(jid)
        if old is None:
            if st_now == "open":                 # ★只有"正开着"的新任务才算出发✗★
                out.append((name, "新任务", JOB_START))
            continue
        if old != st_now:
            out.append((name, old, st_now))
    return out, snap


def polish(actions: list, cfg: dict = None, rng=None) -> list:
    """★过一遍**渲染配置**✗★ ✓（词表 → 句长 → emoji → 错字 → **时序最后** ✓ 用户第 6 条 ✓）

    ★为什么放在 `plan` **外面**✗★：`plan` 要保证**纯**（同样的输入 ⇒ 同样的输出 ✓ 判据好写 ✓）
      而渲染带**随机**（emoji／错字 ✓）⇒ 分开 ⇒ 判据能分别钉住两件事 ✓
    ★真值铁律✗★：`persona_render` 绝不碰数字／物品 id／坐标 ✓（T1 判据钉着 ✓）
    """
    import persona_render as PR
    cfg = cfg or PR.load()
    rng = rng or __import__("random").Random()
    for a in actions:
        if not a.line:
            continue
        a.text, a.delay = PR.render(a.line, cfg, rng, mood=a.intent.mood)
    return actions


def run(evs: list, st: Loop, say_fn, transitions: list = None, cfg: dict = None, rng=None,
        audit=None, tag: str = "主动说", verbose: bool = True) -> int:
    """★★"决策 ⇒ 发出去"的**唯一实现**✗★★（返回说了几句 ✓）

    ★为什么必须只有一份✗★（2026-09-30 实机撞出来的教训 ✓ 同 P134 一族 ✓）：
      ✗ `talk.Talk.proactive()` 里有"发"的逻辑 ✓ 而**真正在跑的是 `acp_talk.py`** ✗ ——
        它有**自己的一套**（自己轮询 `dshevents` ✓ 自己 `/dshsay` ✗）
        ⇒ ★我在测试里验的是 `Talk` ✗ 而你在游戏里遇到的是 `acp_talk` ✗★
        ⇒ 于是"语言层全绿"和"你根本听不到它主动说话"**可以同时成立** ✗✗
      ⇒ 口径 ✓：**决策在 `plan` ✓ 渲染在 `polish` ✓ 发送在 `run`** ✗ ——
        两个调用方（`talk.py` ✓ `acp_talk.py` ✓）**都只调这三个** ✓ 谁也不许自己再写一遍 ✗（P106 ✓）

    ★时序最后渲染✗★（用户第 6 条 ✓）：`polish` 已经算好 `delay` ✓ 这里**发之前**才 sleep ✓
      ⚠ 会挡住调用方的轮询 ✓ ⇒ 上限就是配置里的 `最长延迟`（默认 6 秒 ✓）✓
    """
    acts = plan(evs, st, transitions=transitions)
    polish(acts, cfg, rng)
    n = 0
    for a in acts:
        if not a.line:
            if verbose:
                print("      （%s**没说** ✗ %s）" % (tag, a.deny or "没台词"))
            continue
        if a.delay > 0:
            time.sleep(float(a.delay))              # ★时序最后✗★
        try:
            say_fn(a)
        except Exception as e:
            print("      （%s发不出去 ✗：%s）" % (tag, e))
            continue
        st.spoke(a)
        n += 1
        if verbose:
            print("      ★%s ✓（%s ｜ 语气 %s ｜ 等了 %.1fs）%s"
                  % (tag, a.intent.kind, a.intent.mood, a.delay, a.text or a.line))
    if audit:
        try:
            append_audit(audit, acts)
        except Exception as e:
            print("      （审计写不进去 ✗：%s）" % e)
    return n


def audit_rows(actions: list) -> str:
    """★一串动作 ⇒ 审计用的 jsonl（**每行一条** ✓ 含被拦下的 ✓）★ ✗"""
    return "".join(json.dumps(a.audit(), ensure_ascii=False) + "\n" for a in actions)


def append_audit(path, actions: list) -> int:
    """★写审计（**只追加**✓）★ ✗ —— ★连"被拦下"的也写✗★：不然"它为什么没说话"查不出来 ✓"""
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [a for a in actions]
    if not rows:
        return 0
    with p.open("a", encoding="utf-8") as f:
        f.write(audit_rows(rows))
    return len(rows)


def load_lines(path=None) -> dict:
    """★台词库（文件不在 ⇒ 空库 ⇒ 全走 LLM ✓ 也是一种合法状态 ✓）★"""
    return C.load(path) if path else C.load()
