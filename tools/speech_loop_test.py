#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_loop_test.py -- ★"主动扳机"的判据（L1~L8 ✓ 全离线 ✓ 秒级 ✓）★（2026-09-30 ✓ 用户第 1 条 ✓）

WHY：用户第 1 条要的是「**从被动应答改成主动扳机**」✓ —— 而"主动"最容易变成"刷屏" ✗
  ⇒ 这份判据盯的**不是**"会不会说"✗ 而是四件事：
    ① 事件流里**非聊天**的事件**真的被消费了** ✓（★不然"主动"是假的✗★）
    ② 同一行事件**绝不说第二遍** ✓（重连会重放旧序号 ✗）
    ③ **模组出过声 ⇒ 不叠一句** ✓（两层同时说话 ＝ 复读机 ✗）
    ④ ★不知道该说什么 ⇒ **什么都不说**✗★（不硬编事件名 ✗ 不编内容 ✗ 宁缺毋滥 ✓）

CRITERIA（跑之前先写 ✓ 全离线 ✓ 不读世界 ✗ 不调模型 ✗ 不联网 ✗）
  事件样本**逐字抄自模组源码** ✓（`DshBridgeMod.java` 的 `ev(...)` ✓ 不是我想的 ✗ P131 ✓）
  L1 事件⇒意图 ：`damage`／`drop_expiring`／`xp`／`warp`／`walk_done` 各出**对的动作** ✓
  L2 不管聊天   ：`chat` 行 ⇒ **不产生**动作 ✓（应答走 `talk.should_reply` ✓）但**退避归零** ✓
   L3 水位       ：同一批事件**再喂一遍** ⇒ **零动作** ✓（★不复读✗★）
   L4 模组出声   ：`auto_reply` ⇒ **零动作** ✓ ＋ `last_speech` 被推进 ✓（不跟它抢 ✓）
   L5 不认识     ：编一个模组没有的事件名 ⇒ **零动作** ✓ 且 **有留痕** ✓（不静默丢 ✓）
   L6 缺台词拒掉 ：库里**故意**不放 `反应/受伤` ⇒ 动作**有 deny** ✗ 而**不发** ✓
                  （★非开放对话**不许**走模型 ✗ 用户第 2 条 ✓★）
   L7 没由头不聊 ：idle 到点但**没有由头** ⇒ 零动作 ✓；**有由头** ⇒ 一条 `闲聊` ✓
   L8 审计       ：每条动作（含被拦的 ✓）都能落成一行 jsonl ✓ 且**带 why** ✓（用户第 5 条 ✓）
  L9 任务迁移   ：`job_transitions()`（纯函数 ✓）—— 新任务 ⇒ `start` ✓；状态变了 ⇒ **照抄账本** ✓；
                  ★状态没变 ⇒ **零迁移**✗★（不然每轮都播报一次 ＝ 刷屏 ✗）
  L10 同批要压住：★**同一批事件里同类型的意图只许出一条**✗★（2026-09-30 **实机**撞到 ✓ ⇒ P135 ✓）
                  ＋ `tell()` **过闸当场记账** ✓（`spoke()` 不许再改账 ✗ 否则退避会被加两遍 ✓）
  L11 唯一实现 ：★**在跑的那个进程**必须也走这一套✗★（⇒ P137 ✓）——
                  · `speech_loop.run()` 存在 ✓ 且**真的调了** `plan`／`polish`／`spoke` ✓
                  · ★`talk.py` 与 `acp_talk.py` **都调 `SL.run(`** ✗★（谁也不许自己再写一遍 ✗）
                  · ★`acp_talk.py` 往游戏里发主动话时**必须走它自己的 `say()`**✗★
                    （漏了 ⇒ 中文不过 `esc()` ⇒ 游戏里乱码 ✗ P13/P39 ✓ 我刚差点又漏一次 ✓）
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import speech as S          # noqa: E402
import speech_loop as SL    # noqa: E402


def say(s):
    print(s, flush=True)


class Clock:
    def __init__(self):
        self.t = 10_000.0

    def __call__(self):
        return self.t


# ★事件样本：**逐字抄自模组源码**✗★ ✓（`DshBridgeMod.java` 的 `ev(...)` ✓）
#   （★"凭印象编"过一次 ⇒ P131 ✓ 这份样本就是那次教训的产物 ✓）
EV = {
    "damage": "#41 damage hp=7.5 delta=-4.0 src=mob_attack",
    "drop_expiring": ('#42 drop_expiring id=77 item=minecraft:emerald x44 left_s=21 '
                      'at=4108.5,71.0,18.5 dist=1.8 (pickup needs a FREE SLOT - see inv_guard)'),
    "xp": "#43 xp level=12",
    "warp": "#44 warp from=4100.5,71.0,18.5 to=4108.5,71.0,18.5 d=8.0",
    "walk_done": ('#45 walk_done result=reached at=4108.50,71.00,18.50 want=4112,71,18 '
                  'dist=0.40 mode=auto detours=1 step_downs=0'),
    "chat": "#46 chat who=Au_Sn len=6 msg=\\u4f60\\u597d",
    "auto_reply": "#47 auto_reply to=Au_Sn n=2",
    "held": "#48 held from=minecraft:stone_pickaxe to=minecraft:iron_sword",
}
LIB = {
    "反应/受伤": ["疼 ✗ 谁打我（掉了 {delta} 点血 ✓）"],
    "播报/掉落快没了": ["地上的 {item} 还有 {left_s} 秒就没了 ✗ 我背包没空位 ✓"],
    "邀功/升级": ["升到 {level} 级了 ✓ 我允许你夸一下。"],
    "反应/被传送": ["我怎么瞬移了 {d} 格 ✗"],
    "播报/走完了": ["到了 ✓ 走了 {dist} 格。"],
    # ★裸的这两层是**降级兜底**✗★：任务名是"把沙砾筛完"这种**任意一句话** ✓
    #   ⇒ 库不可能为每个任务名写一节 ✗ ⇒ ★必须能掉到 `<类型>` 这一层 ✓★（降级顺序的意义 ✓）
    "播报": ["我去干活了 ✓（{phase}）"],
    "邀功": ["这活我干完了 ✓"],
    "闲聊": ["{reason} —— 要不我接着干？"],
}


def mk(now=None, **kw):
    st = SL.Loop(gate=S.Gate(now_fn=now or Clock()), lines=dict(LIB), **kw)
    return st


def main() -> int:
    ok = True

    # ---- L1：事件 ⇒ 意图 ----
    # ★口径（2026-09-30 实机后收紧 ✓ P135 ✓）：一批里**同类只许出一条**✗
    #   ⇒ 这 5 条里 `反应` 有两条（`damage` ✓ `warp` ✓）、`播报` 有两条
    #     （`drop_expiring` ✓ `walk_done` ✓）⇒ 真说 **3 条** ✓ 另外 **2 条**被同类冷却压住 ✗
    st = mk()
    acts = SL.plan([EV["damage"], EV["drop_expiring"], EV["xp"], EV["warp"], EV["walk_done"]], st)
    kinds = [(a.intent.kind, a.intent.payload.get("event")) for a in acts]
    said = [a for a in acts if a.line]
    held = [a for a in acts if not a.line]
    lines = [a.line for a in said]
    l1 = len(acts) == 5 and len(said) == 3 and len(held) == 2 \
        and all("刚说过" in a.deny for a in held) and \
        kinds[0] == ("反应", "damage") and kinds[1] == ("播报", "drop_expiring") and \
        kinds[2] == ("邀功", "xp") and kinds[3] == ("反应", "warp") and \
        kinds[4] == ("播报", "walk_done") and \
        all(a.source.startswith("corpus:") for a in said) and \
        ("emerald" in lines[1]) and ("21" in lines[1]) and ("12" in lines[2])
    say("L1 事件⇒意图：%d 条 %s" % (len(acts), kinds))
    say("     真说 %d 条／被同类冷却压住 %d 条（%s）=> %s"
        % (len(said), len(held), (held[0].deny[:22] if held else "无"), l1))
    say("     台词：%s" % lines)
    ok &= l1

    # ---- L2：chat 不产生动作，但退避归零 ----
    st = mk()
    st.gate.quiet = 5
    acts2 = SL.plan([EV["chat"]], st)
    l2 = (acts2 == []) and (st.gate.backoff() == 1.0) and (st.seen_seq == 46)
    say("L2 不管聊天：动作 %d 条 ｜ 退避 %.0f（玩家说话 ⇒ 归零 ✓）｜ 水位 %d => %s"
        % (len(acts2), st.gate.backoff(), st.seen_seq, l2))
    ok &= l2

    # ---- L3：水位 ⇒ 不复读 ----
    st = mk()
    first = SL.plan([EV["damage"]], st)
    again = SL.plan([EV["damage"]], st)
    l3 = (len(first) == 1) and (again == [])
    say("L3 水位：第一遍 %d 条 ｜ **再喂一遍** %d 条 => %s" % (len(first), len(again), l3))
    ok &= l3

    # ---- L4：模组出过声 ⇒ 不叠一句 ----
    clk = Clock()
    st = mk(now=clk)
    st.last_speech = 0.0
    acts4 = SL.plan([EV["auto_reply"]], st)
    l4 = (acts4 == []) and (st.last_speech == clk.t)
    say("L4 模组出声：动作 %d 条 ｜ last_speech 推到 %.0f => %s" % (len(acts4), st.last_speech, l4))
    ok &= l4

    # ---- L5：不认识的事件 ⇒ 零动作 ＋ 留痕 ----
    st = mk()
    acts5 = SL.plan(["#90 death who=Bot"], st)
    l5 = (acts5 == []) and any(s["kind"] == "death" for s in st.skipped)
    say("L5 不认识：动作 %d 条 ｜ 留痕 %s => %s" % (len(acts5), st.skipped[-1:] or "无", l5))
    ok &= l5

    # ---- L6：库里没有 ⇒ **拒掉**（不许偷偷走模型 ✓）----
    st = mk()
    st.lines.pop("反应/受伤", None)
    acts6 = SL.plan([EV["damage"]], st)
    l6 = (len(acts6) == 1) and (not acts6[0].line) and ("库里没有" in acts6[0].deny) \
        and (acts6[0].source == "llm")
    say("L6 缺台词：line=%r ｜ deny=%s => %s" % (acts6[0].line, acts6[0].deny[:40], l6))
    ok &= l6

    # ---- L7：没由头不聊 ----
    clk = Clock()
    st = mk(now=clk)
    st.min_idle = 100.0
    st.last_speech = clk.t - 999          # 安静很久了 ✓
    no_cue = SL.plan([], st)
    st.job_phase["job"] = "走到 4112,71,18"   # ★有由头（事件里真有的信息 ✓）★
    with_cue = SL.plan([], st)
    l7 = (no_cue == []) and len(with_cue) == 1 and with_cue[0].intent.kind == "闲聊" \
        and ("走到" in with_cue[0].line)
    say("L7 没由头：没由头 %d 条 ｜ 有由头 %d 条 %r => %s"
        % (len(no_cue), len(with_cue), with_cue[0].line if with_cue else None, l7))
    ok &= l7

    # ---- L8：审计 ----
    st = mk()
    acts8 = SL.plan([EV["damage"], EV["auto_reply"], "#91 death who=Bot"], st)
    st.lines.pop("反应/受伤", None)
    acts8b = SL.plan([EV["xp"]], st)          # 水位 91 之后 ⇒ 43 是旧的 ✗ 会被挡 ✓
    acts8c = SL.plan(["#92 damage hp=1.0 delta=-3.0 src=x"], st)
    tmp = Path(tempfile.gettempdir()) / "speech_audit_test.jsonl"
    tmp.unlink(missing_ok=True)
    n8 = SL.append_audit(tmp, acts8 + acts8c)
    rows = [json.loads(x) for x in tmp.read_text(encoding="utf-8").splitlines()]
    l8 = (n8 == len(acts8 + acts8c)) and bool(rows) and all(("why" in r) and ("kind" in r)
                                                            for r in rows) \
        and any(r["deny"] for r in rows) and any(r["line"] for r in rows) \
        and (acts8b == [])
    say("L8 审计：%d 条动作 ⇒ %d 行 jsonl ｜ 带 why=%s ｜ 含 deny=%s ｜ 含 line=%s"
        " ｜ 旧序号被挡=%s => %s"
        % (len(acts8 + acts8c), len(rows), all("why" in r for r in rows),
           any(r["deny"] for r in rows), any(r["line"] for r in rows), acts8b == [], l8))
    ok &= l8

    # ---- L9：任务账本 ⇒ 迁移（纯函数 ✓）----
    jobs1 = [{"id": "j1", "goal": "把沙砾筛完", "status": "open"}]
    tr1, snap1 = SL.job_transitions({}, jobs1)
    tr2, snap2 = SL.job_transitions(snap1, jobs1)                       # ★没变 ⇒ 零迁移 ✗★
    tr3, snap3 = SL.job_transitions(snap1, [{"id": "j1", "goal": "把沙砾筛完",
                                             "status": "done"}])
    tr4, _ = SL.job_transitions(snap1, [{"id": "j1", "goal": "把沙砾筛完",
                                         "status": "failed"}])
    # 迁移喂给 plan ⇒ 出对的动作 ✓
    # ★★这里**故意**把"出发＋失败"放在同一批✗★ ⇒ 按 L10 的新口径，
    #   第二条 `播报` **应当被同类冷却压住**✗（★这才是对的✗★：20 秒内不重复播报 ✓）
    #   ⇒ 期望从 `["播报","邀功","播报"]` 改成 `["播报","邀功"]` ✓（P135 的口径 ✓）
    st = mk()
    acts9 = SL.plan([], st, transitions=tr1 + tr3 + tr4)
    # ⚠ `plan` 返回的是**全部动作**（含被拦的 ✗ 审计要用 ✓）⇒ 数"说出去几句"必须**筛 `line`** ✗
    #   （第一版我漏了这一步 ⇒ 判据假红 ✓ —— 与实机 V5 的口径要一致 ✓）
    spoken9 = [a.intent.kind for a in acts9 if a.line]
    kinds9 = [a.intent.kind for a in acts9]
    l9 = (tr1 == [("把沙砾筛完", "新任务", "start")]) and (tr2 == []) \
        and (tr3 == [("把沙砾筛完", "open", "done")]) \
        and (tr4 == [("把沙砾筛完", "open", "failed")]) \
        and spoken9 == ["播报", "邀功"] and all(a.line for a in acts9 if a.line)
    say("L9 任务迁移：新任务 %s ｜ 没变 %s（要空 ✓）｜ 完成 %s ｜ 失败 %s"
        % (tr1, tr2, tr3, tr4))
    say("     ⇒ 全部动作 %s ｜ **真说的** %s（★同批第二条播报被冷却压住 ✓★）=> %s"
        % (kinds9, spoken9, l9))
    ok &= l9

    # ---- L10：同批要压住（★实机撞出来的 bug✗★ ⇒ P135 ✓）----
    st = mk()
    burst = ["#%d damage hp=%.1f delta=-1.0 src=generic" % (100 + i, 20.0 - i) for i in range(5)]
    actsA = SL.plan(burst, st)
    spokenA = [a for a in actsA if a.line]
    deniedA = [a for a in actsA if a.deny]
    # ★同批 5 条 `反应` ⇒ 只许 1 条真出 ✓ 其余**留痕**（deny 里看得见"刚说过"✓）
    #   ＋ `spoke()` **不许**再改账 ✓（退避只许加一档 ✗）
    before_quiet = st.gate.quiet
    for a in actsA:
        st.spoke(a)
    l10 = (len(spokenA) == 1) and (len(deniedA) == 4) \
        and all("刚说过" in a.deny for a in deniedA) \
        and (st.gate.quiet == before_quiet) and all(a.sent for a in actsA) \
        and (st.gate.backoff() == 2.0)
    say("L10 同批要压住：一批 5 条同类型事件 ⇒ 真说 %d 条 ✓（要 1）｜ 被拦 %d 条（都要说'刚说过'=%s）"
        " ｜ `spoke()` 没再改账=%s ｜ 退避=%.0f（一档 ✓）=> %s"
        % (len(spokenA), len(deniedA), all("刚说过" in a.deny for a in deniedA),
           st.gate.quiet == before_quiet, st.gate.backoff(), l10))
    ok &= l10

    # ---- L11：★"唯一实现"——在跑的那个进程也得走这一套✗★（P137 ✓）----
    src = (ROOT / "tools" / "speech_loop.py").read_text(encoding="utf-8")
    tk = (ROOT / "tools" / "talk.py").read_text(encoding="utf-8")
    ac = (ROOT / "tools" / "acp_talk.py").read_text(encoding="utf-8")
    run_body = src.split("def run(", 1)[1].split("\ndef ", 1)[0] if "def run(" in src else ""
    # ★口径 ✗：查的是"**代码里有没有真的发**"✗ —— 不是"文档里提没提"✗
    #   （第一版我写成 `"dshsay" not in run_body` ✗ ⇒ 注释里那句 `/dshsay` 把它判红了 ✓
    #     ★判据太粗 ⇒ 假红 ✓ 同样的坑 P132 那次也踩过 ✓★）
    no_send = ('"dshsay' not in run_body) and ("asbot(" not in run_body) and ("say_fn(" in run_body)
    l11 = ("plan(" in run_body) and ("polish(" in run_body) and ("spoke(" in run_body) \
        and ("SL.run(" in tk) and ("SL.run(" in ac) and no_send \
        and ("lambda a: say(" in ac) \
        and ('"dshsay %s" % a.text' not in ac)     # ★不许绕开 `esc()` 自己发 ✗★
    say("L11 唯一实现：run() 里 plan/polish/spoke=%s ｜ run() **自己不发**（只调 `say_fn`）=%s"
        " ｜ talk.py 调它=%s ｜ acp_talk.py 调它=%s ｜ acp_talk 走自己的 say()=%s"
        " ｜ 没人绕开 esc()=%s => %s"
        % (("plan(" in run_body and "polish(" in run_body and "spoke(" in run_body), no_send,
           "SL.run(" in tk, "SL.run(" in ac, "lambda a: say(" in ac,
           '"dshsay %s" % a.text' not in ac, l11))
    ok &= l11

    # ---- L12：★游标 ≠ 水位✗★（P139 ✓ 实机抓到的静默丢事件 ✓）----
    #   判据（源码级 ✓ 因为坏的是**调用方怎么问** ✗ 不是 `plan` 怎么算 ✓）：
    #   ① `talk.py`／`acp_talk.py` 都**不许**再用回执头的 `cursor=(\d+)` 当水位 ✗
    #   ② 水位必须来自**真收到的事件序号** `#(\d+)` ✓
    #   ③ `acp_talk.py` 必须写**心跳**（`relay_heartbeat.json` ✓）——
    #      ★没有心跳 ⇒ "它为什么不说话"就只能靠猜✗★（这一轮我猜错两次 ✓）
    bad_cursor = [n for (n, s) in (("talk.py", tk), ("acp_talk.py", ac))
                  if re.search(r"cursor=\(\\d\+\)", s) and '"dshevents" if cursor is None' in s
                  and "seen_seq" not in s.split("dshevents", 1)[1][:200]]
    seq_ok = ('re.match(r"#(\\d+)"' in tk) and ("loop.seen_seq" in ac)
    hb_ok = ("relay_heartbeat.json" in ac) and ("seen_seq" in ac)
    l12 = (not bad_cursor) and seq_ok and hb_ok
    say("L12 游标≠水位：乱用回执游标的文件 %s ｜ 水位取真序号=%s ｜ 有心跳=%s => %s"
        % (bad_cursor or "无 ✓", seq_ok, hb_ok, l12))
    ok &= l12

    say("---- L1..L12 = %s ----" % ok)
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
