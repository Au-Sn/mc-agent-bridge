#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech.py -- ★"什么时候该开口"＋"说什么"★ ✓（2026-09-30 ✓ 用户第 1／2／5 条 ✓ 纯逻辑 ✓ 离线 ✓）

## 为什么要有它 ✗（用户原话要点 ✓）
  「先把"闸门"从**被动应答**改成**主动扳机**」✓
    · `talk.should_reply()` 只管"**别人说话 ⇒ 我要不要接**"✗ ⇒ 它**只会应答** ✗
    · 而"**主动开口**"从来没闸门 ✗ ⇒ 真接上去就是**刷屏** ✗（★用户点得很准✓★）
  「分层生成：**语料库扛 80%**，LLM 只接开放对话」✓
    · 播报／反应／寒暄／没话找话 ⇒ 从**台词库**按 `(事件 × 情绪 × 关系)` 抽 ✓ 填**真值槽位** ✓
      ⇒ 毫秒级 ✓ 零 token ✓ 人设不漂 ✗
    · ★只有真正的开放对话**才走 LLM** ✗★ ✓
  「意图层：让"**为什么说了这句话**"可查」✓ ⇒ 每条话都带 `Intent` ✓（类型／载荷／对象／情绪快照／为什么 ✓）

## 这一层的边界（写清楚 ✗ 免得又混口径 ✓）
  · **纯逻辑** ✓：不读世界 ✗ 不调 LLM ✗ 不发消息 ✗ ⇒ **可以离线单测** ✓（`speech_test.py` ✓）
  · 谁负责"发" ✗：`talk.py`（它有 `/dshsay` ✓）—— 它把事件喂进来 ✓ 拿 `Intent` 去出口 ✓
  · 谁负责"状态" ✗：情绪（第 3 条 ✓）／记忆（第 4 条 ✓）／时序渲染（第 6 条 ✓）**还没做** ✓
    ⇒ 本文件先把**接口**留出来（`mood` ／ `relationship` ／ `render` 的钩子 ✓）不假装有 ✓

## 话痨抑制（★用户强调"没有节流就是刷屏，质感瞬间变负"★ ✓）三条都在 ✓
  ① **每类扳机各自的冷却** ✓（`COOLDOWN[kind]` ✓）
  ② **每分钟发言预算** ✓（`budget_per_min` ✓ 硬顶 ✓）
  ③ **玩家不回应 ⇒ 指数退避** ✓（`backoff` ✓ 倍数 `BACKOFF_MULT` ✓ 上限 `BACKOFF_MAX` ✓；
     玩家一回应 ⇒ **立刻归零** ✓）

## ★事件名**只许从模组源码抄**✗★（第 35 轮 ✓ ⇒ P131 ✓）
  见 `EVENT_KINDS` 那段注释 ✓：第一版表里一半事件**模组根本不发** ✗
  ⇒ 现在由 `errata_guard_test.py` **E11** 拿 `DshBridgeMod.java` 的 `ev("<名>"` 对账 ✓
  ⇒ 新事件进模组 ⇒ 判据逼我们在 `EVENT_KINDS`／`SKIP_EVENTS` 里**做个决定** ✗
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable

# ── 意图：★"为什么说这句"是可查的对象★ ✓（用户第 5 条 ✓）─────────────────────
KINDS = ("播报", "反应", "闲聊", "接话", "求助", "邀功", "承诺")

# ★开放对话＝**只有它该走模型**✗★ ✓（用户第 2 条 ✓）：这类**不吃**全局兜底台词 ✗
OPEN_KINDS = ("接话",)


@dataclass
class Intent:
    kind: str                      # KINDS 之一 ✓
    why: str                       # ★扳机 ＋ 一句话原因★ ✓（日志里能回放"它当时为什么想说"✓）
    payload: dict = field(default_factory=dict)   # ★真值槽位★ ✓（填进台词里 ✓ 不许编 ✗）
    who: str = ""                  # 对谁说 ✓（"" = 对所有人 ✓）
    mood: str = "平静"             # 情绪快照 ✓（第 3 条还没实现 ⇒ 先留位 ✓）
    relationship: str = "陌生人"    # 关系 ✓（第 4 条还没实现 ⇒ 先留位 ✓）
    at: float = 0.0                # 什么时候产生的 ✓（0 ⇒ 构造时填 ✓）

    def __post_init__(self):
        if not self.at:
            self.at = time.time()
        if self.kind not in KINDS:
            raise ValueError("不认识的意图类型 ✗：%r（只能是 %s ✓）" % (self.kind, KINDS))

    def line(self) -> str:
        """日志用的一行 ✓（★回放用★ ✓ 一眼看见"为什么想说这句"✓）"""
        return "[%s] kind=%s who=%s why=%s payload=%s" % (
            time.strftime("%H:%M:%S", time.localtime(self.at)), self.kind,
            self.who or "-", self.why, self.payload)


# ── 扳机：从**事件流**里看，而不是只看聊天 ✓（用户第 1 条 ✓）──────────────────
# ★冷却（秒）★ ✓：用户说"每类扳机带冷却"✓ —— 数字是**起点** ✓ 要按实测调 ✗（写在这里好改 ✓）
COOLDOWN = {
    "播报": 20.0,      # 出发/完成/失败/被卡住 ✓
    "反应": 8.0,       # 受伤/死亡/稀有掉落/天黑/被注视 ✓（这类最多 ✗ 冷却最短但预算扣得狠 ✓）
    "闲聊": 240.0,     # 没话找话 ✓（★最贵的那种 ✗ 冷却最长 ✓★）
    "接话": 2.0,       # 别人说话 ✓（沿用 `should_reply` 的 `gap` 口径 ✓）
    "求助": 60.0,
    "邀功": 90.0,
    "承诺": 5.0,
}
BACKOFF_MULT = 2.0     # ★玩家不理 ⇒ 下次等更久★ ✓
BACKOFF_MAX = 900.0    # ★上限 15 分钟★ ✓（不然会"越安静越闭嘴"✗ 那也不好 ✓）
DEFAULT_BUDGET = 6     # ★每分钟最多几条★ ✓（硬顶 ✓ 用户点名的"刷屏"闸 ✓）


@dataclass
class Gate:
    """★发言闸门★ ✓（把 `should_reply` 那套"叫我才答＋节流＋额度"**推广成通用**✓）"""
    budget_per_min: int = DEFAULT_BUDGET
    # ★必须**带注解**✗：不带注解的赋值在 dataclass 里只是类属性 ✗ ⇒ 构造参数里根本没有它 ✗
    #   （这个坑刚踩过 ✓ P127 ✓ —— 判据 S3 第一句就 TypeError 了 ✓）
    now_fn: "Callable[[], float]" = time.time

    last: dict = field(default_factory=dict)      # kind -> 上次什么时候说 ✓
    said: list = field(default_factory=list)      # 最近说过的时刻 ✓（滚动 60 秒 ✓）
    quiet: int = 0                                # ★连了几次"说了没人理"★ ✓
    last_backoff: float = 0.0

    def backoff(self) -> float:
        """★玩家不回应 ⇒ 等得更久★ ✓（`2^n` 封顶 ✓）"""
        return min(BACKOFF_MAX, float(BACKOFF_MULT) ** max(0, self.quiet))

    def should_speak(self, intent: Intent) -> tuple:
        """★核心判据 ✓：现在该不该开口 ✗ ⇒ (bool, 为什么) ✓"""
        now = float(self.now_fn())
        # ① 预算（硬顶 ✓ 先查最贵的那个 ✗）
        self.said = [t for t in self.said if now - t < 60.0]
        if len(self.said) >= int(self.budget_per_min):
            return False, "这一分钟的额度用完了（%d 条 ✓ 不刷屏 ✗）" % self.budget_per_min
        # ② 这一类自己的冷却 ✓（＋退避 ✓ —— 退避只加在"主动"那几类上 ✗：
        #    别人**点名跟我说话**时不该因为我退避就不理他 ✓）
        cd = float(COOLDOWN.get(intent.kind, 30.0))
        if intent.kind != "接话":
            cd = max(cd, self.backoff())
        last = self.last.get(intent.kind)
        if last is not None and now - float(last) < cd:
            return False, "这类刚说过（kind=%s 冷却 %.0fs ✓ 已经过了 %.0fs ✓）" % (
                intent.kind, cd, now - float(last))
        return True, "该说 ✓"

    def spoke(self, intent: Intent) -> None:
        """★记一条"我真的说了"★ ✓（过闸之后调 ✓）"""
        now = float(self.now_fn())
        self.last[intent.kind] = now
        self.said.append(now)
        # ★主动说了、没人回应 ⇒ 退避加一档★ ✓（`接话` 不算 —— 那是应答 ✓）
        if intent.kind != "接话":
            self.quiet += 1

    def heard(self, replied: bool = True) -> None:
        """★玩家说话了 / 回应了 ⇒ 退避**立刻归零**★ ✓（用户点名要的 ✓）"""
        if replied:
            self.quiet = 0


# ── 扳机：把事件变成意图 ✓（纯函数 ✓ 好单测 ✗）────────────────────────────────
def on_job_transition(prev: str, now: str, job: str, detail: str = "") -> Intent | None:
    """★job 状态迁移 ⇒ 播报★ ✓（用户第 1 条第一个 ✓）"""
    if prev == now:
        return None
    p, n = str(prev or "").strip(), str(now or "").strip()
    if not n:
        return None
    if n in ("start", "出发", "开走"):
        return Intent("播报", "job[%s] 出发（%s → %s）" % (job, p or "-", n),
                      {"job": job, "phase": n, "detail": detail})
    if n in ("done", "完成", "成功"):
        return Intent("邀功", "job[%s] 完成了（%s → %s）" % (job, p or "-", n),
                      {"job": job, "phase": n, "detail": detail})
    if n in ("failed", "失败"):
        return Intent("播报", "job[%s] 失败（%s → %s）" % (job, p or "-", n),
                      {"job": job, "phase": n, "detail": detail})
    if n in ("stuck", "卡住", "blocked"):
        return Intent("求助", "job[%s] 卡住了（%s → %s）" % (job, p or "-", n),
                      {"job": job, "phase": n, "detail": detail})
    return Intent("播报", "job[%s] 状态变了（%s → %s）" % (job, p or "-", n),
                  {"job": job, "phase": n, "detail": detail})


# ★游戏事件 ⇒ 反应★ ✓（用户第 1 条第二个 ✓）
#
# ★★这张表**必须**从模组的 `ev(...)` 调用点抄下来★★ ✗（2026-09-30 第 35 轮 ✓ ⇒ P131 ✓）：
#   ✗ 我第一版是**凭印象编的** ✗：`damage/death/rare_drop/night/watched/tamed` ——
#     其中 `death`／`rare_drop`／`night`／`watched`／`tamed` **模组根本不发** ✗
#     （★"编一个事件名"这件事，看着毫无破绽 ✗ 却让整条扳机**永远不会响**✗★）
#   ⇒ 口径 ✓：键＝`DshBridgeMod.java` 里 `ev("<名字>", …)` 的**名字原样** ✓
#     判据 ✓：`errata_guard_test.py` **E11** 每次跑都拿源码对账 ✗（多一个／少一个都报 ✗）
#   ⇒ ★新事件加进模组 ⇒ 判据会**逼着**我们在这张表或 `SKIP_EVENTS` 里做个决定 ✗★
#     （不决定 ⇒ 报红 ✓ 于是不会"悄悄漏掉一类事件" ✓）
#
# 值 ✓：`(意图类型, 为什么键, 一句话)` ✓ —— 为什么键就是台词库 `<类型>/<为什么>` 那一层 ✓
EVENT_KINDS = {
    "damage":        ("反应", "受伤", "掉血了"),
    "inv":           ("反应", "背包变了", "背包里件数变了（★没有物品名 ✗ ⇒ 绝不许说是什么 ✗★）"),
    "drop_expiring": ("播报", "掉落快没了", "脚边的掉落物快消失了"),
    "xp":            ("邀功", "升级", "经验等级变了"),
    "mode":          ("播报", "换模式", "游戏模式变了（★创造模式 ⇒ 挖掘不掉落 ⇒ 自给证据失真 ✓★）"),
    "warp":          ("反应", "被传送", "位置瞬移（★有人 tp 它 ✓ 项目纪律：主线不走 tp ✓★）"),
    "walk_done":     ("播报", "走完了", "一次走动结束（★`result=` 里有到底到没到 ✓★）"),
    "walk_replan":   ("播报", "重规划", "走动中途重新规划了（★卡住的先兆 ✓★）"),
    "auto_greet":    ("反应", "有人来了", "有玩家靠近（模组自己也会 greet ✓ 见 `SKIP_EVENTS` 的说法 ✓）"),
}
# ★★看见了但**故意不说**的事件★★ ✗（2026-09-30 第 35 轮 ✓）
#   ★为什么也要列出来✗★：不列 ⇒ 判据没法区分"**我们决定不说**"✓ 和"**我们压根不知道有它**"✗
#   —— 前者是设计 ✓ 后者是漏洞 ✗ 而它们**表现完全一样**（都不出声 ✓）✗
SKIP_EVENTS = {
    "http_server": "★直连 HTTP 服务器的启停事件 ✗ 不播报★",
    "http_error": "★直连 HTTP 的错误事件 ✗ 不播报★",
    "yaw_bracket": "★夹逼 yaw 写者的诊断事件 ✗ 不播报★",
    "turn_hold": "★保持朝向时压住外部写的诊断事件 ✗ 不播报★",
    "turn_reassert": "★转身末尾重申朝向的诊断事件 ✗ 不播报★",
    "yaw_write": "★yaw 被谁改的诊断事件 ✗ 只给排查用 ✗ 不播报★",
    "turn_trace": "★转身轨迹 ✗ 给判据用的数据 ✗ 不播报★",
    # ★2.46.0（§79.495）✗★：平滑转身的内部细节 ⇒ **故意不说**（★用户：回合流水进后台日志✗★）
    "turn_start": "★转身是内部动作 ✗ 没必要单独播报★",
    "turn_done": "★同上✗★",
    "chat": "★玩家说话 ⇒ 走 `talk.should_reply`（应答那条路 ✓ 不是这条 ✓）",
    "auto_reply": "★模组自己回过嘴了 ⇒ 只当成「已经出过声」✗（别叠一句 ✓ 而且退避要归零 ✓）",
    "idle_line": "★模组自己的自言自语 ⇒ 同上（别叠 ✓）",
    "idle_stroll": "自己溜达 ⇒ 可以当「由头」✓ 但不值得单独说一句 ✗",
    "hotbar": "换快捷栏格 ⇒ 太碎 ✗（`held` 才有意义 ✓）",
    "held": "换手持物 ⇒ 太碎 ✗ 攒着当「由头」用 ✓",
    "ate": "吃东西 ⇒ 模组有它自己的反应 ✓ 我们不抢 ✗",
    "auto_eat": "自动进食流程 ⇒ 内部细节 ✗",
    "walk_start": "出发 ⇒ 由 `walk_done` 收口 ✓（不然一次走动说两句 ✗）",
    "walk_detour": "绕路 ⇒ 一次走动能绕好几次 ✗ 说它必刷屏 ✗",
    "walk_mode": "内部模式探测 ⇒ 纯噪音 ✗",
    "path_plan": "规划回执 ⇒ 纯噪音 ✗",
    "skin_boot": "皮肤启动 ⇒ 与游戏内容无关 ✗",
    "skin_heal": "皮肤自愈 ⇒ 同上 ✗",
    "humanoid": "拟人化开关 ⇒ 那是**我们自己的**开关 ✗ 说它没意义 ✗",
    # ★★v2.17 新增的两个（模组侧 `dshwalk` 的拒绝/放宽）★★ ✗
    #   ★"看见了但故意不说"必须**列出来**✗★（本表开头那条理由 ✓）
    #   —— 它们是**诊断用**的 ✓（回执/`why`/事件流那边读 ✓）
    #      而"走路被安全闸拦下"这件事**不值得对着玩家说一句** ✗（长作业里它会被触发很多次 ✗）
    "walk_refuse": "走路被安全闸拦下 ⇒ ★内部诊断✗★ 由 `why` 与事件流读 ✓ 不对玩家说 ✗（E11 要求它必须被登记 ✓）",
    "walk_door":     "★开门★ ⇒ 内部诊断（§79.363 模组走到门口自动开门 ✓）✗ 不对玩家说 ✗（E11 要求它必须被登记 ✓）",
    "walk_pillar":   "★1by1tower★ ⇒ 内部诊断（§79.386 模组跳起来把方块垫到脚下 ✓）✗ 不对玩家说 ✗（E11 要求它必须被登记 ✓）",
    "goto_start":    "★路点表导航开始★ ⇒ 内部诊断（§79.392 `dshgoto` ✓）✗ 不对玩家说 ✗（E11 要求它必须被登记 ✓）",
    "goto_refuse":   "★路点表被拒★ ⇒ 内部诊断（§79.392 路点站不住 ✗ 整条拒发 ✓）✗ 不对玩家说 ✗（E11 要求它必须被登记 ✓）",
    "dig_refuse":    "★挖被脚下护栏拒绝★ ⇒ 内部诊断（§79.392 脚下那块下面没地板 ✓）✗ 不对玩家说 ✗（E11 要求它必须被登记 ✓）",
    "do_start":     "★dshdo 动作队列开始★ ⇒ 内部诊断（§79.407 模组侧动作队列 ✓）✗ 不对玩家说 ✗（E11 要求登记 ✓）",
    "do_done":      "★dshdo 队列走完★ ⇒ 内部诊断 ✓ 不对玩家说 ✗（E11 要求登记 ✓）",
    "do_fail":      "★dshdo 某步失败★ ⇒ 内部诊断 ✓ 不对玩家说 ✗（E11 要求登记 ✓）",
    "do_stop":      "★dshdo 被停★ ⇒ 内部诊断 ✓ 不对玩家说 ✗（E11 要求登记 ✓）",
    "do_cmd_err":   "★dshdo 内部命令抛异常★ ⇒ 内部诊断 ✓ 不对玩家说 ✗（E11 要求登记 ✓）",
    "do_span":       "★一步合并走几格（★内部诊断 ✗ 模组 2.33.0 §79.427 新增✗★）⇒ 不对玩家说 ✗（E11 要求登记 ✓）",
    "do_open":       "★动作类型 open_door 的开门口令结果（★内部诊断 ✗ 模组 2.38.0 §79.442 新增✗★）⇒ 不对玩家说 ✗（E11 要求登记 ✓）",
    "mut":           "★世界变了（写操作）★ ⇒ 内部诊断（§79.412 模组发 mut 事件 ✓）✗ 不对玩家说 ✗（E11 要求登记 ✓）",
    "walk_relaxed": "牢笼放宽（P124 出口）⇒ ★同上✗★ 内部诊断 ✓ 说它没意义 ✗",
    # ★★2026-10-03 新登记（★被 **E11** 当场抓到才想起 ✗ P169 同族✓）★★：
    #   ★`leash_stop` 是 `/dshleash` 那条**每 tick 紧围栏**发的 ✗ 两种 `why`：
    #     `fence`（★越界那一脚**被就地拦下**✗★）／ `duration`（★到点自己停✓★）★
    #   ⇒ ★与 `walk_refuse` 同一档✗★：★**内部诊断** ✗ 由事件流与 `dshleash status` 读 ✓
    #     ★不对玩家播报✗★（★但**必须登记** ✓ 否则 E11 红✓★）
    "leash_stop": "★紧围栏拦下一次连续输入★✗ ⇒ **内部诊断**（`why=fence/duration` ＋ `moved=` ✓）✗ 不对玩家说 ✗（E11 要求登记 ✓）",
    # ★★v2.18 新增的两个（模组侧的**死亡保险**）★★ ✗
    #   ★"看见了但故意不说"也必须**列出来**✗★（本表开头那条理由 ✓）
    #   ⚠ 但它们**不是噪音** —— 它们是 D3「身体不出事」的**正面计数依据** ✗：
    #     ★`bot_died` 的条数必须为 **0**✗★ ⇒ 这里"不说"只是"**不对玩家说**" ✓
    #     真正读它们的是**判据**（事件流 ✓）不是台词层 ✓ —— 这个区分要写清楚 ✗
    "bot_died": "★死亡保险扣下了一包★✗ ⇒ **不对玩家播报** ✓ 但它是 D3 的**计数依据**（条数必须为 0 ✓）",
    "bot_revived": "★保险把背包还回去了★✗ ⇒ **不对玩家播报** ✓ 同样是**判据用**的事件 ✓",
}


def parse_facts(data: str) -> dict:
    """★把事件那一行的 `k=v` **按真值**解出来 ✓★（`data` ＝ `ev()` 里那串 ✓）

    例 ✓：`hp=3.0 delta=-2.0 src=mob` ⇒ `{"hp": 3.0, "delta": -2.0, "src": "mob"}` ✓
    ★能当数字就当数字✗★（填进台词的 `{hp}` 要是 `3.0` 而不是 `"3.0"` 那种带引号的字符串 ✓）
    ★解不出来的**不猜**✗★：原样留字符串 ✓（下游 `speech.fill` 只在**缺**的时候拒绝 ✓）
    """
    out: dict = {}
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)=(\S+)", data or ""):
        k, v = m.group(1), m.group(2)
        if re.fullmatch(r"-?\d+", v):
            out[k] = int(v)
        elif re.fullmatch(r"-?\d+\.\d+", v):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def parse_event_line(line: str) -> tuple:
    """★`#12 damage hp=3.0 …` ⇒ `(序号, 事件名, 真值)` ✓★（`talk.events_since()` 给的就是这个 ✓）

    ★认不出 ⇒ `(None, "", {})`✗★ —— **不抛异常** ✗（事件流是外面来的 ✓ 一条脏行不该打断一轮 ✓）
    """
    m = re.match(r"#(\d+)\s+(\S+)\s*(.*)$", (line or "").strip())
    if not m:
        return None, "", {}
    return int(m.group(1)), m.group(2), parse_facts(m.group(3))


# ══ ★★§79.424✗★★：导航／任务的**汇报**（★纯函数 ✗ 不发声 ✗ 不需要游戏✗★）✗★★
#   ★为什么放在 speech 层✗★：★"★该不该说 ✗ 说什么★" 是**判断** ✗ 不是**出口**✗★
#     ★出口只有一个（`talk.py`／`acp_talk.py` 的 `/dshsay`**）✗ 这里只管**产出 `Intent` 或 `None`**✗★ ✓
_NAV_FAIL_WHY = {
    "no_plan": "规划不出路（★结构上过不去✗★）",
    "no_pos": "读不到自己在哪",
    "not_enough_scaffold": "方块不够铺路",
    "max_steps": "步数上限到了",
    "empty_table": "动作表是空的",
    "place_on_body": "计划里要往自己身上放方块（★拒了✗★）",
}


def nav_intent(rep) -> "Intent | None":
    """★导航／任务报告 ⇒ 该说的一句✗★（★不认识的 ⇒ None ✗ 不硬编✗★）✗★

    ★两种报告✗★：
      · `exec_task.run_goals` 的：★有 `segments`**（★多段✗★）
      · `exec3d.execute` 的：★有 `arrived`／`reason`**（★单段✗★）
    """
    if not isinstance(rep, dict):
        return None

    # ── ★多段任务✗★ ──
    if "segments" in rep and isinstance(rep.get("segments"), list):
        segs = rep["segments"]
        n_ok = rep.get("pass", sum(1 for s in segs if s.get("ok")))
        total = rep.get("total", len(segs))
        if rep.get("fail"):
            bad = next((s for s in segs if not s.get("ok")), {})
            why = _NAV_FAIL_WHY.get(str(bad.get("reason") or ""), "路上过不去")
            return Intent("播报", "任务分段失败",
                          {"done": n_ok, "total": total, "why_key": "任务卡住", "why": why,
                           "event": "task_fail"})
        if total and n_ok == total:
            return Intent("邀功", "多段任务全部完成",
                          {"done": n_ok, "total": total, "why_key": "到齐了", "event": "task_done"})
        return None

    # ── ★单段导航✗★ ──
    if "arrived" in rep or "reason" in rep or "bad" in rep:
        if rep.get("arrived"):
            return Intent("邀功", "导航到达",
                          {"end": rep.get("end"), "steps": rep.get("steps"),
                           "why_key": "到地方了", "event": "nav_arrived"})
        reason = str(rep.get("reason") or "")
        if reason in _NAV_FAIL_WHY:
            return Intent("播报", "导航失败：%s" % reason,
                          {"why_key": "走不过去", "why": _NAV_FAIL_WHY[reason],
                           "event": "nav_fail", "reason": reason})
        if rep.get("bad"):
            return Intent("播报", "导航失败（有坏消息）",
                          {"why_key": "走不过去", "why": "有步骤没成",
                           "event": "nav_fail", "bad": rep.get("bad")})
        return None

    return None


def on_game_event(kind: str, facts: dict | None = None) -> Intent | None:
    """★游戏事件 ⇒ 反应／邀功★ ✓（不认识的事件 ⇒ **不硬编** ✗ 返回 None ✓）

    ★两个"名字"都要带上 ✗★（实测 ✓ 少带一个 ⇒ **库里一条都抽不到** ✗ ⇒ 判据 L1 当场报 ✓）：
      · `event` ＝ **模组的事件名** ✓（`damage` ✓ 审计／对账用 ✓ 真值 ✓）
      · `why_key` ＝ **人话的为什么键** ✓（`受伤` ✓ **台词库的分层键**用它 ✓）
      ⇒ `why_key_of()` 先看 `why_key` ✓ ⇒ 库里的键写成 `<类型>/受伤` 就能抽到 ✓
    """
    k = str(kind or "").strip().lower()
    if k not in EVENT_KINDS:
        return None
    ik, why_key, why = EVENT_KINDS[k]
    pl = dict(facts or {})
    pl["event"] = k
    pl["why_key"] = why_key
    return Intent(ik, "游戏事件 %s（%s）" % (k, why), pl)


def on_event_line(line: str) -> Intent | None:
    """★一行**原始事件** ⇒ 意图 ✓★（不认识 ⇒ None ✓）—— 这是 `speech_loop` 的入口 ✓"""
    _seq, kind, facts = parse_event_line(line)
    if not kind:
        return None
    it = on_game_event(kind, facts)
    if it is None:
        return None
    # ★伤害到 0 ⇒ **死了**✗★（模组**没有** `death` 事件 ✓ ⇒ 只能从 `hp` 推 ✓ 不许编一个 `death` ✗）
    if kind == "damage" and isinstance(facts.get("hp"), (int, float)) and facts["hp"] <= 0:
        it.why = "游戏事件 damage（hp=0 ⇒ 死了 ✓ 模组没有 death 事件 ✗ 见 P131 ✓）"
        it.payload["dead"] = True
        it.kind = "反应"
        it.payload["event"] = "death_hp0"
    return it


def on_idle(seconds: float, reason: str = "", min_idle: float = 180.0) -> Intent | None:
    """★idle 超时 ⇒ 没话找话★ ✓ —— ★但必须**有由头**✗★（用户原话 ✓）

    由头 = 手里的活 ／ 附近的东西 ／ 上次的话题 ✓（`reason` 就是那句由头 ✓）
    ★没有由头 ⇒ **不开口** ✗★（空聊就是刷屏 ✓ 这一条是本文件最要紧的取舍 ✓）
    """
    if float(seconds) < float(min_idle):
        return None
    r = str(reason or "").strip()
    if not r:
        return None
    return Intent("闲聊", "安静了 %.0f 秒 ＋ 有由头：%s" % (float(seconds), r[:60]),
                  {"idle_s": float(seconds), "reason": r})


# ── 措辞：**台词库优先** ✓（用户第 2 条 ✓ 80% 的话不经过 LLM ✗）──────────────
SLOT = re.compile(r"\{([a-z_]+)\}")

# ★`<kind>/<为什么>` 里的"为什么"从哪来✗★ ✓：**改库的人得猜得到**✗ 才是好键 ✓
#   ⇒ 优先级固定 ✓（第一个非空的 ✓）：why_key（自己指定）→ event（游戏事件名 ✓）
#     → job（在干什么 ✓ ⇒ `播报/挖矿` ✓ 这种键最好写 ✓）→ item ✓
WHY_KEYS = ("why_key", "event", "job", "item")


def why_key_of(intent: Intent) -> str:
    """★这条意图"为了哪件事"✓★ —— 台词库的分层键就用它 ✓（空 ⇒ 只按类型抽 ✓）"""
    pl = intent.payload or {}
    for k in WHY_KEYS:
        v = str(pl.get(k) or "").strip()
        if v:
            return v
    return ""


def fill(template: str, payload: dict) -> str:
    """★把台词里的槽位填上**真值**★ ✓ —— ★缺什么就**不猜**✗★（缺真值的槽 ⇒ 整条不用 ✓）

    返回 ✓：填好的句子 ✓ ｜ `None` ⇒ **这条台词用不了** ✗（宁可换一条 ✓ 也不编数字 ✗）
    """
    def sub(m):
        return str(payload[m.group(1)])
    need = set(SLOT.findall(template or ""))
    if not need.issubset(set(payload.keys())):
        return None
    return SLOT.sub(sub, template).strip()


def pick_from_corpus(corpus: dict, intent: Intent, rng: random.Random | None = None):
    """★按 (事件 × 情绪 × 关系) 抽一条★ ✓（用户第 2 条 ✓ 桌宠那套 ✓）

    `corpus` 形如 ✓：`{"播报/挖矿": ["又去挖了 ✓（第 {n} 趟）"], "邀功": ["干完了 ✓ 挖到 {n} 个铁"]}` ✓
      ⇒ 键的查找顺序 ✓：**最具体的先来** ✗：
        ① `<kind>/<为什么键>/<mood>/<rel>` ② `<kind>/<为什么键>/<mood>` ③ `<kind>/<为什么键>`
        ④ `<kind>` ⑤ 全局 `"*"`
    ★第 ② 层是**后加的**✗★ ✓（2026-09-30 第 35 轮 ✓ 接语料时发现缺它 ✗ ⇒ 改尺子先记理由 ✓ P110 ✓）：
      上游桌宠语料的语气轴是 `standard/sharp/community` ✓ ⇒ 键写成
      `<类型>/<为什么>/<语气>` ✓ —— 而 `relationship` 我**故意留空** ✗ ⇒
      只写 4 层的话，语气那一层**永远轮不到** ✗（4 层键要 `rel` 也报上名 ✓ 而它报不出 ✓）
      ⇒ 补上"只有语气、没有关系"的这一层 ✓（少一层 ≠ 整类失声 ✓ 与降级顺序同一个道理 ✓）
    返回 ✓：`(台词, 用的哪个键)` ✓ ｜ `(None, "")` ⇒ 库里没有能用的 ✗（调用方去走 LLM ✓）
    ★为什么要有"降级顺序"✗★：用户改库不可能一次改全 ✓ ⇒ 少写一层不该**整类失声**✗

    ★★唯一一处例外 ✓（用户第 2 条"**LLM 只接开放对话**"✗ ⇒ 反过来就是**开放对话不许被兜底吃掉**✗）：
      `接话` **不吃** `"*"` 全局兜底 ✗ —— 否则库里写一句 `"*": ["嗯 ✓"]` 就会把**所有**玩家的话
      都变成"嗯 ✓"✗ ⇒ 模型永远轮不上 ✗ ⇒ ★80/20 直接作废 ✗★
      ⇒ 想让它接话走台词库 ✓ 就**明写** `接话` 或 `接话/<why键>` 那一层 ✓（明写＝用户真的写了 ✗）
    """
    rng = rng or random.Random()
    why_key = why_key_of(intent)
    keys = []
    if why_key:
        keys += ["%s/%s/%s/%s" % (intent.kind, why_key, intent.mood, intent.relationship),
                 "%s/%s/%s" % (intent.kind, why_key, intent.mood),
                 "%s/%s" % (intent.kind, why_key)]
    keys += [intent.kind]
    if intent.kind not in OPEN_KINDS:
        keys += ["*"]
    for k in keys:
        lines = corpus.get(k)
        if not lines:
            continue
        # ★一次抽一条 ⇒ 填真值 ✓ 填不了就换下一条 ✓ 全填不了 ⇒ 换下一层键 ✓
        order = list(lines)
        rng.shuffle(order)
        for t in order:
            got = fill(t, intent.payload)
            if got:
                return got, k
    return None, ""


def render(intent: Intent, corpus: dict, rng: random.Random | None = None) -> tuple:
    """★一句话：台词库先上，抽不到才让 LLM 接★ ✓（返回 (台词 或 None, 出处) ✓）

    出处 ✓：`corpus:<键>` ＝ 台词库 ✓ ／ `llm` ＝ 该走模型 ✓（★调用方据此决定要不要花钱 ✗★）
    """
    line, key = pick_from_corpus(corpus, intent, rng)
    if line:
        return line, "corpus:%s" % key
    return None, "llm"
