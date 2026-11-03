#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mood.py -- ★情绪状态机：**一个慢变量** ＋ 3~5 个有名状态★（2026-09-30 ✓ 用户第 3 条 ✓ 纯逻辑 ✓ 离线 ✓）

## 用户原话要点 ✗
  「情绪状态机（3~5 个有名状态 ＋ **一个慢变量**注入 ✗ ⇒ **不是每句话都重演一遍**✗）」
  ⇒ ★这一层要防的是"**每句话都重新决定一遍情绪**"✗★：
    那种做法看起来"有情绪"✓ 实则**句句跳变**✗ ⇒ 像个坏掉的表情包 ✗（质感立刻变负 ✓）

## 设计（三条规矩 ✗ 都是为"稳"服务的 ✓）
  ① **只有一个慢变量** ✗：`energy ∈ [0,1]` ✓
     · 一次事件只让它动**一点点**（`STEP` 表 ✓ 最大 0.15 ✓）
     · 时间本身会让它**缓慢回落**向 `REST`（`DECAY_PER_MIN` ✓）
     ⇒ ★其余全是它的函数✗★（不许再塞第二个状态值进来 ✓ 那就会开始互相打架 ✓）
  ② **滞回**（`HYSTERESIS` ✓）：状态在阈值附近**不许来回抖** ✗
     ⇒ 上下阈值分开 ✓ 这就是"迟到地变脸"✓ 而不是"每句话变一次脸"✗
  ③ **最短驻留**（`MIN_DWELL` ✓）：刚变过 ⇒ `MIN_DWELL` 秒内**不再变**✗
     ⇒ ★用户那句"不是每句话都重新反应一遍"✗ 就落在这一条上 ✓★

## 5 个状态（★有名有姓✗★ ✓ ⇒ 台词库里也能按它分节 ✓）
  `起劲`（energy 高 ✓ 干活顺 ✓）｜`平静`（中 ✓ 常态 ✓）｜`累`（低 ✓ 但仍干 ✓）
  ｜`烦`（连续吃亏 ✓ 嘴硬 ✓）｜`得意`（刚办成事 ✓ 短暂 ✓）
  ★语气映射★ ✗：`tone_of()` ⇒ `标准／傲娇／梗` ✓（**就是台词库键里的那一层** ✓ 库已经按它分好节了 ✓）
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ★状态（3~5 个 ✓ 就 5 个 ✗ 再多就没人分得清 ✓）★
STATES = ("起劲", "平静", "累", "烦", "得意")

# ★状态 ⇒ 台词库的**语气层**✗★ ✓（库里的键是 `<类型>/<为什么>/<语气>` ✓ 语气只有三种 ✓）
TONE = {"起劲": "标准", "平静": "标准", "累": "标准", "烦": "傲娇", "得意": "梗"}

# ★慢变量的刻度和步长✗★ ✓（★每一步都小 ✗ 这样才叫"慢"✓★）
STEP = {
    "job_done": +0.12,       # 干成一件事 ✓
    "walk_done": +0.05,      # 走完一趟 ✓（小事 ✓）
    "xp": +0.08,             # 升级 ✓
    "player_said": +0.06,    # 玩家跟我说话 ✓（有人搭理就精神点 ✓）
    "job_start": +0.02,      # 出发 ✓
    "idle_long": -0.10,      # 闲太久了 ✓
    "walk_replan": -0.06,    # 路又得重算 ✓（磨人 ✓）
    "damage": -0.09,         # 掉血 ✓
    "item_lost": -0.08,      # 掉了东西 ✓
    "job_failed": -0.15,     # 一件事彻底失败 ✓（最伤 ✓）
    "stuck": -0.12,          # 卡住 ✓
    "death": -0.40,          # 死了一次 ✓（★最重的一档 ✓ 但也不许一键清零 ✗★）
}
REST = 0.55                  # ★什么都不发生时，它会慢慢往这儿回落✗★
DECAY_PER_MIN = 0.05         # 每分钟回落多少 ✓（★很慢 ✓ 这就是"慢变量"✓★）
HYSTERESIS = 0.06            # ★滞回带宽✗★ ✓（上下阈值差这么多 ✓ 不许在阈值上抖 ✓）
MIN_DWELL = 45.0             # ★状态最短驻留（秒 ✓）✗★ —— 用户要的"不是每句重演一遍"✓

# ★阈值（★上／下两套✗★ ⇒ 滞回 ✓）——
#   高：≥HI 进"起劲" ✓ ／ 低：≤LO 进"累" ✓ ／ 刚办成事 ⇒ 短暂"得意" ✓
HI = 0.78
LO = 0.30


@dataclass
class Mood:
    """★状态机的全部内存★ ✓（★就这几个数 ✗ 别再加了 ✓）"""
    energy: float = 0.55
    state: str = "平静"
    since: float = 0.0               # 当前状态是什么时候进的 ✓
    last_ev: str = ""                # 上一个动过它的事件 ✓（审计用 ✓）
    changed: int = 0                 # 一共变过几次脸 ✓（判据用它数"抖没抖" ✓）
    proud_until: float = 0.0         # ★"得意"是个**短暂**状态✗★（过了就回落 ✓）

    # ── 慢变量 ────────────────────────────────────────────────────────────
    def feed(self, event: str, now: float, times: int = 1) -> float:
        """★喂一个事件 ⇒ 只动**一点点**★ ✗（★不认识的事件 ⇒ **一点不动**✗ 不硬编 ✓ P131 ✓）"""
        d = STEP.get(str(event or "").strip().lower())
        if not d:
            return 0.0
        before = self.energy
        self.energy = _clamp(self.energy + d * max(1, int(times)))
        self.last_ev = event
        if event == "job_done":
            self.proud_until = now + 90.0       # ★办了件事 ⇒ 允许"得意"一会儿 ✓
        self.tick(now)
        return self.energy - before

    def tick(self, now: float) -> str:
        """★时间流逝 ⇒ 往 `REST` 缓慢回落 ＋ 按滞回决定要不要变脸★ ✓

        ★它是**纯函数式**的✗★：给同样的 (energy, state, since, now) ⇒ 给同样的结果 ✓
        ⇒ 判据不用 sleep ✓（注入 `now` ✓ 与 `speech.Gate` 一个套路 ✓）
        """
        if not self.since:
            self.since = now
        mins = max(0.0, (now - self.since) / 60.0)
        if self.energy > REST:
            self.energy = max(REST, self.energy - DECAY_PER_MIN * mins)
        elif self.energy < REST:
            self.energy = min(REST, self.energy + DECAY_PER_MIN * mins)
        want = self._want(now)
        # ★最短驻留 ＋ 滞回✗★：两条都过了才准变 ✓
        if want != self.state and (now - self.since) >= MIN_DWELL:
            self.state = want
            self.since = now
            self.changed += 1
        return self.state

    def _want(self, now: float) -> str:
        """★"该是什么脸"✗★ ✓（★这里只用 energy ＋ 一个短暂的得意窗 ✗★）"""
        if now < self.proud_until and self.energy >= 0.5:
            return "得意"
        # ★滞回：已经在这两个极端上时，掉出去要比进去更难✗★
        if self.state == "起劲":
            return "起劲" if self.energy >= HI - HYSTERESIS else \
                ("平静" if self.energy > LO + HYSTERESIS else "累")
        if self.state == "累":
            return "累" if self.energy <= LO + HYSTERESIS else \
                ("起劲" if self.energy >= HI - HYSTERESIS else "平静")
        if self.energy >= HI:
            return "起劲"
        if self.energy <= LO:
            return "累"
        if self.last_ev in ("damage", "item_lost", "stuck", "job_failed") and self.energy < 0.45:
            return "烦"        # ★连着吃亏 ⇒ 嘴硬 ✗★（也是 energy 的函数 ✓ 没加新变量 ✓）
        return "平静"

    def tone(self) -> str:
        """★情绪 ⇒ 台词库里的**语气层**★ ✓（★库不用改一个字✗★ —— 键那一层本来就这么写的 ✓）"""
        return TONE.get(self.state, "标准")

    def snap(self) -> dict:
        """★情绪快照✗★ ✓ —— 写进每条意图 ✓（用户第 5 条："为什么说这句"要可查 ✓）"""
        return {"state": self.state, "tone": self.tone(), "energy": round(self.energy, 3)}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def from_intent(intent) -> str:
    """★意图 ⇒ 该喂哪个事件✗★ ✓（★认不出 ⇒ 空串 ⇒ **一点不动**✗ 不硬编 ✓ P131 ✓★）

    ★为什么让 `mood` 自己认，而不是让 `speech_loop` 挨个判断✗★：
      ⇒ "什么事件动情绪"这件事**只有一处定义** ✗（P106 ✓）
      否则以后加个事件，很容易出现"某个地方在喂、另一个地方没喂"✗
    """
    p = dict(getattr(intent, "payload", None) or {})
    ev = str(p.get("event") or "")
    if ev == "damage":
        return "death" if p.get("dead") else "damage"
    if ev == "inv":
        # ★只认"掉了东西"✗★（捡到不算伤情绪 ✓；而且 `inv` **没有物品名**✗ ⇒ 也不许编 ✓）
        return "item_lost" if isinstance(p.get("delta"), int) and p["delta"] < 0 else ""
    return {"xp": "xp", "walk_done": "walk_done", "walk_replan": "walk_replan"}.get(ev, "")


def from_phase(phase: str) -> str:
    """★任务迁移的"新阶段" ⇒ 该喂哪个事件✗★ ✓（阶段名是 `speech` 认的那几个 ✓ 同一套 ✓）"""
    return {"start": "job_start", "出发": "job_start", "开走": "job_start",
            "done": "job_done", "完成": "job_done", "成功": "job_done",
            "failed": "job_failed", "失败": "job_failed",
            "stuck": "stuck", "卡住": "stuck", "blocked": "stuck"}.get(
        str(phase or "").strip().lower(), "")
