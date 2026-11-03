#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_test.py -- ★"什么时候该开口"不许刷屏（S1~S8 ✓ 离线 ✓ 秒级 ✓）★

WHY（用户第 1 条 ✓ 原话要点 ✓）：
  「把闸门从**被动应答**改成**主动扳机**」✓ 而「★**主动开口没有节流就是刷屏**，
   质感瞬间变负**★」✓ —— 所以这份判据的重点**不是**"能不能说"✗ 而是"**该闭嘴时闭得住**"✗

CRITERIA（跑之前先写 ✓ 全部离线 ✓ 不读世界 ✗ 不调 LLM ✗）：
  S1 扳机→意图 ：job 四种迁移（出发／完成／失败／卡住）各出**对的类型** ✓；
                 不认识的事件 ⇒ **不硬编**（返回 None ✓）
  S2 有由头才聊：idle 到点**但没有由头** ⇒ ★不许开口✗★；有由头才给 `闲聊` ✓
  S3 冷却       ：同类第二次在冷却内 ⇒ 拦住 ✓（且理由里带"刚说过"✓）；过了冷却 ⇒ 放行 ✓
  S4 额度       ：一分钟内超过 `budget_per_min` ⇒ 拦住 ✓（★硬顶 ✗ 用户点名的那个闸 ✓★）
  S5 退避       ：玩家不理 ⇒ 下一次等得更久（`2^n` ✓）；★玩家一回应 ⇒ **立刻归零**✓★
  S6 台词库优先 ：库里有的 ⇒ 从库里出 ✓ 且**填的是真值** ✓；库里没有 ⇒ 出处必须是 `llm` ✓
  S7 缺真值不猜 ：槽位缺真值 ⇒ **这条不用** ✗（换下一条 ✓ 全不行 ⇒ 去 LLM ✓）—— ★绝不编数字✗★
  S8 意图可查   ：每条意图都带 `why` ✓ 且 `line()` 里能看见 why 与载荷 ✓（★回放能力 ✓★）

★时钟是**注入**的 ✗（`Gate(now_fn=…)` ✓）⇒ 判据不用 sleep ✓ 秒级 ✓（也是 S5 能测的前提 ✓）
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import speech as S      # noqa: E402


def say(s):
    print(s, flush=True)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def tick(self, dt):
        self.t += float(dt)
        return self.t


def main():
    ok = True

    # ---- S1：job 迁移 ⇒ 意图类型 ----
    s1 = True
    want = [("start", "播报"), ("done", "邀功"), ("failed", "播报"), ("stuck", "求助")]
    got = []
    for phase, kind in want:
        it = S.on_job_transition("running", phase, "挖矿")
        got.append((phase, it.kind if it else None))
        s1 &= bool(it) and (it.kind == kind)
    s1 &= (S.on_job_transition("start", "start", "x") is None)          # 没变 ⇒ 不说话 ✓
    s1 &= (S.on_game_event("谁也不知道的事件") is None)                    # ★不硬编 ✗★
    s1 &= (S.on_game_event("damage", {"hp": 3}) is not None)
    say("S1 扳机→意图: %s ｜ 未知事件=None=%s => %s"
        % (got, S.on_game_event("zzz") is None, s1))
    ok &= s1

    # ---- S2：idle 必须**有由头** ----
    no_reason = S.on_idle(999.0, reason="")
    short = S.on_idle(10.0, reason="手里的活：筛沙砾")
    with_reason = S.on_idle(999.0, reason="手里的活：筛沙砾")
    s2 = (no_reason is None) and (short is None) and bool(with_reason) \
        and (with_reason.kind == "闲聊")
    say("S2 有由头才聊: 没由头=%s 没到点=%s 有由头=%s => %s"
        % (no_reason, short, bool(with_reason), s2))
    ok &= s2

    # ---- S3/S4/S5：闸门（冷却 ✓ 额度 ✓ 退避 ✓）----
    clk = Clock()
    g = S.Gate(budget_per_min=3, now_fn=clk)
    it = S.on_job_transition("running", "start", "挖矿")
    first = g.should_speak(it)
    g.spoke(it)
    again = g.should_speak(S.on_job_transition("running", "start", "挖矿"))
    clk.tick(S.COOLDOWN["播报"] + 1)
    later = g.should_speak(S.on_job_transition("running", "start", "挖矿"))
    s3 = first[0] and (not again[0]) and ("刚说过" in again[1]) and later[0]
    say("S3 冷却: 第一次=%s ｜ 冷却内=%s（理由：%s）｜ 过了冷却=%s => %s"
        % (first[0], again[0], again[1][:34], later[0], s3))
    ok &= s3

    clk = Clock()
    g = S.Gate(budget_per_min=2, now_fn=clk)
    n_ok = 0
    for i in range(5):
        ev = S.on_game_event("damage", {"hp": 20 - i})
        okk, why = g.should_speak(ev)
        if okk:
            g.spoke(ev)
            n_ok += 1
            clk.tick(S.COOLDOWN["反应"] + 1)
    s4 = (n_ok == 2)
    say("S4 额度（每分钟 2 条）: 5 次尝试里放行 %d 条 => %s" % (n_ok, s4))
    ok &= s4

    clk = Clock()
    g = S.Gate(budget_per_min=99, now_fn=clk)
    waits = []
    for _i in range(4):          # 说话 ⇒ 没人理 ✓（不调 heard ✓）
        it2 = S.on_job_transition("running", "start", "挖矿")
        g.should_speak(it2)
        g.spoke(it2)
        waits.append(g.backoff())
        clk.tick(2000.0)         # 时间过去很久 ⇒ 冷却不再是瓶颈 ✓ 只看退避 ✓
    g.heard(True)                # ★玩家回应 ⇒ 归零 ✓
    s5 = (waits[0] < waits[1] < waits[2] < waits[3]) and (g.backoff() == 1.0)
    say("S5 退避: 连说没人理 ⇒ %s ｜ 玩家一回应 ⇒ %.0f => %s"
        % ([int(w) for w in waits], g.backoff(), s5))
    ok &= s5

    # ---- S6/S7：台词库优先 ＋ 缺真值不猜 ----
    corpus = {
        "播报/挖矿": ["又开始挖了 ✓", "去挖矿了 ✓（第 {n} 趟）"],     # ★缺 n ⇒ 这条用不了 ✗★
        "邀功": ["干完了 ✓ 挖到 {n} 个铁 ✓"],                        # ★这条填得上 ✓★
        "闲聊": ["{reason}，要不我接着干？"],
        "*": ["嗯 ✓"],
    }
    it_ok = S.Intent("邀功", "test", {"n": 7})
    line_ok, src_ok = S.render(it_ok, corpus, random.Random(1))
    it_slot = S.Intent("播报", "test", {"job": "挖矿"})               # 没有 n ⇒ 该跳过那条 ✓
    line_slot, src_slot = S.render(it_slot, corpus, random.Random(1))
    it_miss = S.Intent("接话", "test", {})                            # 库里没有接话 ✓
    line_miss, src_miss = S.render(it_miss, corpus, random.Random(1))
    s6 = (line_ok == "干完了 ✓ 挖到 7 个铁 ✓") and src_ok.startswith("corpus:") \
        and (line_slot == "又开始挖了 ✓") and (line_miss is None) and (src_miss == "llm")
    say("S6 台词库优先: 填真值=%r(%s) ｜ 跳过缺槽那条=%r ｜ 库里没有 ⇒ %s => %s"
        % (line_ok, src_ok, line_slot, src_miss, s6))
    ok &= s6

    bad, _why = S.pick_from_corpus({"播报": ["挖到 {n} 个铁 ✗"]}, S.Intent("播报", "t", {}))
    s7 = (bad is None) and (S.fill("还差 {n} 个", {"n": 3}) == "还差 3 个") \
        and (S.fill("还差 {n} 个", {}) is None)
    say("S7 缺真值不猜: 缺 n 的模板 ⇒ %r（want None）｜ 有 n ⇒ %r => %s"
        % (bad, S.fill("还差 {n} 个", {"n": 3}), s7))
    ok &= s7

    # ---- S8：意图可查 ----
    # ★事件名**必须是真的**✗★（原来是 `rare_drop` —— **我编的** ✗ 模组根本不发 ✗ ⇒ P131 ✓）
    it8 = S.on_game_event("drop_expiring",
                          {"item": "minecraft:emerald", "left_s": 21})
    l8 = it8.line()
    s8 = bool(it8.why) and ("why=" in l8) and ("emerald" in l8) and (it8.kind in S.KINDS) \
        and (S.on_event_line("#42 drop_expiring item=minecraft:emerald left_s=21").payload
             .get("left_s") == 21) \
        and (S.on_game_event("rare_drop") is None)      # ★编出来的事件名 ⇒ 不触发 ✗★
    say("S8 意图可查: %s => %s" % (l8[:110], s8))
    ok &= s8

    say("---- S1..S8 = %s ----" % ok)
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
