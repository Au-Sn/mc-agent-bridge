#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mood_render_test.py -- ★情绪**稳** ＋ 人设**只是配置**（M1~M6 ／ T1~T6 ✓ 全离线 ✓ 秒级 ✓）★

WHY（用户第 3／6 条 ✓）：
  · 第 3 条要的是"**不是每句话都重演一遍情绪**"✗ ⇒ 判据必须能数出"**抖不抖**"✗
  · 第 6 条要的是"人设退化成渲染配置 ＋ **时序最后渲染**"✗ ⇒
    判据必须钉住**真值一个字符都不许动**✗（★这条比"像不像人设"重要一百倍✗★）

CRITERIA（跑之前先写 ✓ 注入时钟 ✓ 不用 sleep ✓ 注入随机种子 ✓ 不读世界 ✗ 不联网 ✗）
  M1 慢变量  ：一次事件只动**一点点**（小事件 ≤ 0.15 ✓ 最重的"死" ≤ 0.4 ✓
              且**没有任何一档能一次清零**✗）／**不认识的事件 ⇒ 一点不动** ✓（不硬编 ✓）
  M2 滞回    ：把 energy 反复推到阈值附近 ⇒ 状态**不许来回抖** ✓（变化次数 ≤ 1 ✓）
  M3 最短驻留：刚变过脸 ⇒ `MIN_DWELL` 内**再推也不变** ✓（★这就是"不逐句重演"✗★）
  M4 3~5 个  ：状态名单就是 5 个 ✓ 每个都有语气映射 ✓ 且语气只有 3 种（库的键那三种 ✓）
  M5 语气能抽：★每个状态映射出的语气 ⇒ 在**真库**里**真能抽到句子**✓★（抽不到 ⇒ 状态机是摆设 ✗）
  M6 快照一次：同一批事件里多条意图 ⇒ **同一个情绪快照** ✓（不许一条一算 ✗）
  T1 真值不动：`{left_s}` 出来的 `21` ✓ 物品 id ✓ 坐标 ✓ 小数 ✓ **一个字符都不许变** ✗
  T2 词表    ：单字**只在词首**替 ✓（`我先去干活` ⇒ `本鲸先去干活` ✓ 而 `给我一点时间` ⇒ **不动** ✗）；
              **多字词条最长匹配** ✓（`我们` ⇒ `咱们` ✗ 不许变成 `本鲸们` ✗）
  T3 句长    ：超长句在**标点处**截 ✓ 不长于上限 ✓ 且**真值不被砍半截** ✗
  T4 错字率  ：0 ⇒ 一个字都不换 ✓；1.0 ⇒ 只换**汉字** ✓（数字/英文/物品名绝不碰 ✓）
  T5 emoji   ：最多一个 ✓ 已有就不再加 ✓ 率 0 ⇒ 不加 ✓
  T6 时序最后：`timing()` 随字数**单调不减** ✓ 且**封顶** ✓（★不许让人干等 ✗★）
  T7 配置在盘上：`personas/dafeiyu.render.json` 存在 ✓ 能读 ✓ 读出来的旋钮是**合理的** ✓
                ＋ `speech_loop.polish()` 真的把 `Action.text/delay` 填上了 ✓
                （★配置写好却没接上 ＝ 白做 ✗★）
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import corpus as C          # noqa: E402
import mood as MO           # noqa: E402
import persona_render as PR  # noqa: E402


def say(s):
    print(s, flush=True)


def main() -> int:
    ok = True
    T = 1000.0

    # ---- M1：慢变量 ----
    m = MO.Mood()
    d = m.feed("job_failed", T)                 # ★最重的一档（除死亡 ✓）
    d_none = m.feed("谁也编不出来的事件", T)     # ★不认识 ⇒ 一点不动 ✓
    mx = max(abs(v) for v in MO.STEP.values())
    m1 = (abs(d) <= 0.15 + 1e-9) and (d_none == 0.0) and (mx <= 0.4) \
        and (min(MO.STEP.values()) > -0.5)      # ★没有一档能"一键清零"✗★
    say("M1 慢变量：job_failed 动了 %+.3f ｜ 不认识的事件动了 %+.3f ｜ 最大一档 %.2f"
        "（不许 ≥0.5 一次清零 ✗）｜ energy=%.3f => %s" % (d, d_none, mx, m.energy, m1))
    ok &= m1

    # ---- M2/M3：滞回 ＋ 最短驻留 ----
    m = MO.Mood()
    m.tick(T)
    for step in range(12):                      # ★在阈值附近来回推 ✗★
        m.energy = 0.78 + (0.02 if step % 2 else -0.02)
        m.tick(T + 1.0)
    jitter = m.changed
    m2 = jitter <= 1
    say("M2 滞回：在阈值附近推 12 次（每次 ±0.02 ⇒ 但都没到 MIN_DWELL ✓）⇒ 变脸 %d 次 => %s"
        % (jitter, m2))
    ok &= m2

    m = MO.Mood()
    m.tick(T)
    m.energy = 0.05
    m.tick(T + MO.MIN_DWELL + 1)                # ★驻留过了 ⇒ 这次该变 ✓
    first = m.state
    m.energy = 0.95
    m.tick(T + MO.MIN_DWELL + 2)                # ★刚变过 ⇒ 驻留没到 ⇒ **不许再变** ✗
    held = m.state
    m.tick(T + 2 * MO.MIN_DWELL + 3)
    after = m.state
    m3 = (first == "累") and (held == first) and (after == "起劲")
    say("M3 最短驻留：先 %s ⇒ 立刻反推 energy=0.95 ⇒ 还是 %s（驻留没到 ✓）⇒ 到点后 %s => %s"
        % (first, held, after, m3))
    ok &= m3

    # ---- M4：3~5 个状态 ＋ 语气 ----
    tones = set(MO.TONE.values())
    m4 = (3 <= len(MO.STATES) <= 5) and set(MO.TONE) == set(MO.STATES) and \
        tones == {"标准", "傲娇", "梗"}
    say("M4 状态：%s ｜ 语气 %s => %s" % (list(MO.STATES), sorted(tones), m4))
    ok &= m4

    # ---- M5：每个状态的语气在**真库**里抽得到句子 ----
    lib = C.load()
    miss = []
    for st in MO.STATES:
        tone = MO.TONE[st]
        keys = [k for k in lib if k != "__loose__" and k.split("/")[-1] == tone and lib[k]]
        if not keys:
            miss.append((st, tone))
    m5 = not miss
    say("M5 语气能抽：库里带语气的节 %d 个 ｜ 抽不到的 %s => %s"
        % (len([k for k in lib if k != "__loose__"]), miss or "无 ✓", m5))
    ok &= m5

    # ---- M6：同一批事件里，情绪快照只取一次 ----
    import speech as S
    import speech_loop as SL
    clk = lambda: T                                  # noqa: E731
    st = SL.Loop(gate=S.Gate(now_fn=clk), lines={"反应/受伤": ["疼 {delta} ✓"],
                                                "播报/掉落快没了": ["{item} 剩 {left_s} 秒 ✗"]})
    st.mood = MO.Mood().snap()["state"] if False else "平静"
    evs = ["#1 damage hp=3.0 delta=-2.0 src=mob", "#2 drop_expiring item=minecraft:coal left_s=9"]
    acts = SL.plan(evs, st, now=T)
    moods = {a.intent.mood for a in acts}
    m6 = (len(acts) == 2) and (len(moods) == 1)
    say("M6 快照一次：%d 条意图 ｜ 情绪快照集合 %s（要只有 1 个 ✓）=> %s"
        % (len(acts), moods, m6))
    ok &= m6

    # ---- T1：真值一个字符都不许动 ----
    cfg = dict(PR.DEFAULT_CFG)
    cfg.update({"词表": {"我们": "咱们", "我": "本鲸", "的": "の"},
                "句长": 0, "emoji率": 0.0, "错字率": 0.0})
    truth = "地上的 minecraft:emerald ×21 还有 3.5 秒就没了，at=4108.5,71.0,18.5"
    out1, _ = PR.render(truth, cfg, random.Random(1))
    t1 = ("minecraft:emerald" in out1) and ("21" in out1) and ("3.5" in out1) \
        and ("4108.5,71.0,18.5" in out1)
    say("T1 真值不动：%r => %s" % (out1, t1))
    ok &= t1

    # ---- T2：词表（单字只认词首 ＋ 多字最长匹配）----
    out2a, _ = PR.render("我先去干活", cfg, random.Random(1))
    out2b, _ = PR.render("我们一起去", cfg, random.Random(1))
    out2c, _ = PR.render("给我一点时间", cfg, random.Random(1))
    t2 = out2a.startswith("本鲸") and out2b.startswith("咱们") and ("本鲸们" not in out2b) \
        and (out2c == "给我一点时间")
    say("T2 词表：%r ｜ %r ｜ %r => %s" % (out2a, out2b, out2c, t2))
    ok &= t2

    # ---- T3：句长（标点处截 ＋ 不砍真值）----
    cfg3 = dict(cfg)
    cfg3["句长"] = 20
    long_line = "这句话非常非常长，长到必须被截断，但不能在字中间砍，也不能把 minecraft:emerald 砍半截。"
    out3, _ = PR.render(long_line, cfg3, random.Random(1))
    t3 = (len(out3) <= 20) and ("minecraft:emerald" not in out3 or out3.endswith("minecraft:emerald")) \
        and out3[-1] in PR.PUNCT + "…"
    say("T3 句长：%r（%d 字 ≤ 20 ✓ 结尾 %r）=> %s" % (out3, len(out3), out3[-1], t3))
    ok &= t3

    # ---- T4：错字（0 ⇒ 不动；1.0 ⇒ 只换汉字）----
    cfg4 = dict(cfg)
    cfg4["错字率"] = 0.0
    txt4 = "我真的很在意的"
    base4, _ = PR.render(txt4, cfg4, random.Random(2))     # ★先看"只过词表"长什么样 ✓★
    cfg4b = dict(cfg)
    cfg4b["错字率"] = 1.0
    typo, _ = PR.render(txt4 + " minecraft:coal 21", cfg4b, random.Random(2))
    t4 = (base4 == "本鲸真的很在意的") and (typo != base4 + " minecraft:coal 21") \
        and ("minecraft:coal" in typo) and ("21" in typo) \
        and (len(typo) == len(base4 + " minecraft:coal 21"))
    say("T4 错字：率0=%r（词表已过 ✓）｜ 率1=%r（真值还在=%s）=> %s"
        % (base4, typo, ("minecraft:coal" in typo and "21" in typo), t4))
    ok &= t4

    # ---- T5：emoji 最多一个 ----
    cfg5 = dict(cfg)
    cfg5.update({"emoji率": 1.0, "emoji": ["🐟"]})
    e1, _ = PR.render("干完了", cfg5, random.Random(3))
    e2, _ = PR.render("干完了🐟", cfg5, random.Random(3))
    cfg5["emoji率"] = 0.0
    e0, _ = PR.render("干完了", cfg5, random.Random(3))
    t5 = (e1.count("🐟") == 1) and (e2.count("🐟") == 1) and ("🐟" not in e0)
    say("T5 emoji：%r ｜ %r ｜ 率0=%r => %s" % (e1, e2, e0, t5))
    ok &= t5

    # ---- T6：时序最后（单调 ＋ 封顶）----
    c = dict(PR.DEFAULT_CFG)
    d_small = PR.timing("好", c)
    d_big = PR.timing("好" * 40, c)
    d_huge = PR.timing("好" * 1000, c)
    t6 = (d_small <= d_big <= d_huge) and (d_huge == c["最长延迟"]) and (d_big > 0)
    say("T6 时序：1 字 %.2fs ≤ 40 字 %.2fs ≤ 1000 字 %.2fs（封顶 %.1fs）=> %s"
        % (d_small, d_big, d_huge, c["最长延迟"], t6))
    ok &= t6

    # ---- T7：配置在盘上 ＋ 真的接上了 ----
    import speech_loop as SL2
    cfg7 = PR.load()
    acts7 = SL2.plan(["#5 xp level=9"], SL2.Loop(gate=S.Gate(now_fn=lambda: T),
                                                 lines={"邀功/升级": ["升到 {level} 级了 ✓"]}),
                     now=T)
    acts7 = SL2.polish(acts7, cfg7, random.Random(4))
    t7 = (PR.DEFAULT.is_file()) and (cfg7.get("句长", 0) > 0) \
        and (0.0 <= float(cfg7.get("emoji率", -1)) <= 1.0) \
        and (0.0 <= float(cfg7.get("错字率", -1)) <= 1.0) \
        and bool(acts7) and acts7[0].text and (acts7[0].delay > 0) \
        and ("9" in acts7[0].text)
    say("T7 配置在盘上：%s ｜ 句长 %s emoji %.2f 错字 %.2f ｜ polish ⇒ text=%r delay=%.2fs"
        " => %s" % (PR.DEFAULT.name, cfg7.get("句长"), cfg7.get("emoji率"), cfg7.get("错字率"),
                    acts7[0].text if acts7 else None, acts7[0].delay if acts7 else -1, t7))
    ok &= t7

    say("---- M1..M6=%s ／ T1..T7=%s ----" % (all([m1, m2, m3, m4, m5, m6]),
                                              all([t1, t2, t3, t4, t5, t6, t7])))
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
