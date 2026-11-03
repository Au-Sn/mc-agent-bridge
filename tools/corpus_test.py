#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""corpus_test.py -- ★台词库能不能**扛住 80%**（K1~K7 ✓ 全离线 ✓ 秒级 ✓）★（2026-09-30 ✓）

WHY（用户第 2 条 ✓）：「**语料库扛 80%**，LLM 只接开放对话」
  ⇒ 这一层要能回答三个**能被跑出来**的问题 ✗（不是"我觉得库里够了"✗）：
    ① 库**解析得对吗** ✓（手写格式 ⇒ 解析器不能吞行 ✗）
    ② 库**真的覆盖**那 6 个"敞开说"的类型吗 ✓（覆盖账要能算 ✓）
    ③ 用户**改过的东西会不会被脚本冲掉** ✗（★"可编辑"的库被生成脚本覆盖 ＝ 不可编辑 ✗★）

CRITERIA（跑之前先写 ✓ 全离线 ✓ 不读世界 ✗ 不调模型 ✗ 不联网 ✗）：
  K1 往返   ：`parse(dump(c))` ⇒ 键与句子**一模一样** ✓（手写格式是**双向**的 ✓）
  K2 不吞行 ：没挂在任何 `##` 节里的句子 ⇒ **进 `__loose__`** ✓ ＋ `lint()` **必须报出来** ✗
  K3 死槽位 ：`{n}`／`{job}` 合法 ✓；`{zzz}` ⇒ `lint()` **必须报** ✗（★死句子 ✗ 写进去永远抽不到 ✓★）
  K4 覆盖账 ：合成库计数**对得上** ✓；★`接话` 空 ⇒ **不算**"该补"✗★（它是开放对话 ✓ 走模型 ✓）
  K5 口径   ：`corpus.KINDS`／`OPEN_KINDS` 与 `speech.py` **逐字一致** ✓
              （★两处抄了同一张清单 ⇒ 不许靠人记 ✗ 必须对账 ✗★）
  K6 手写区 ：`compose()` 之后 ⇒ **手改的句子还在** ✓ 而**自动区跟着 corpus 变** ✓
              （★"可编辑"这句话的证据 ★在盘上 ✗ 不在我嘴里 ✗★）
  K7 盘上真库：`personas/dafeiyu.lines.txt` 存在 ✓ 解析 ✓ 体检干净 ✓
              6 个"敞开说"的类型**各 ≥3 条** ✓ ＋ **端到端**：真库 ⇒ 意图 ⇒ `speech.render`
              的出处必须是 `corpus:` ✓（★库接了却没接上 ＝ 白做 ✗★）
  K8 槽位白名单：`{left_s}` 这类**模组真发的**字段必须**从模组源码读出来** ✓
              （★我手抄过一份 ⇒ 抄漏 ⇒ 库里的好句子被误判成"死句子" ✗ 实测撞到 ✓★）
  K9 扳机有台词：★**拿真库**把**每一条扳机**走一遍✗★ —— 合成每条 `speech.EVENT_KINDS` 的事件
              ⇒ `render` **必须**给出句子 ✓ ＋ 任务迁移（出发/完成/失败/卡住 ✓）
              ＋ 没话找话（有由头 ✓）各一条 ✓
              ★★为什么非要这一条✗★★（2026-09-30 **实机当场撞到** ✓ ⇒ P134 ✓）：
                K1~K8 **全绿** ✓ 而真游戏里**一句"反应"都说不出** ✗ ——
                因为那些判据用的是**我自己造的 fixtures**✗（fixture 里有那句 ⇒ 判据绿 ✓）
                而**真库**里 `反应/受伤`／`邀功/升级` **根本没有** ✗✗
                ⇒ ★离线判据必须落在**真库**上✗ 不许落在"我编的样本"上✗★
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import corpus as C          # noqa: E402
import corpus_import as CI  # noqa: E402
import speech as S          # noqa: E402


def say(s):
    print(s, flush=True)


def main() -> int:
    ok = True

    # ---- K1：往返 ----
    # ★fixture **不带** `✓✗★`✗★（P136 ✓）：库里那句是**给玩家看的** ✓
    #   ⇒ fixture 用干净句子 ✓ 另外**单独**验一条"带标记 ⇒ 写盘时被剥掉" ✓
    c1 = {"播报/挖矿": ["又去挖了", "这趟是第 {n} 趟"], "闲聊": ["嗯"]}
    round_trip = C.parse_lines_text(C.dump_lines_text(c1))
    dirty = C.parse_lines_text(C.dump_lines_text({"播报": ["干完了 ✓ 很好 ✗"]}))
    k1 = all(list(round_trip.get(k)) == list(v) for k, v in c1.items()) and \
        set(round_trip) - {"__loose__"} == set(c1) and \
        dirty.get("播报") == ["干完了 很好"]
    say("K1 往返：%s ｜ 带标记那句写盘后 ⇒ %s => %s"
        % (sorted(round_trip), dirty.get("播报"), k1))
    ok &= k1

    # ---- K2：松散行不许被吞 ----
    c2 = C.parse_lines_text("说明文字\n\n## 播报\n- 好 ✓\n这行忘了加减号 ✗\n")
    loose = c2.get("__loose__") or []
    k2 = ("这行忘了加减号 ✗" in loose) and any("松散行" in b for b in C.lint(c2)) \
        and ("说明文字" in loose)
    say("K2 不吞行：__loose__=%d 条 %s ｜ lint 报出=%s => %s"
        % (len(loose), loose, any("松散行" in b for b in C.lint(c2)), k2))
    ok &= k2

    # ---- K3：死槽位 ----
    c3 = {"播报/挖矿": ["第 {n} 趟", "去 {zzz} 了"], "闲聊": ["没有槽"]}
    bad3 = C.lint(c3)
    k3 = len(bad3) == 1 and ("死槽位" in bad3[0]) and ("zzz" in bad3[0])
    say("K3 死槽位：lint 报 %d 条 %s => %s" % (len(bad3), bad3[:1], k3))
    ok &= k3

    # ---- K3b：★文档标记不许进台词✗★（P136 ✓ 实机撞到 ✓）----
    c3b = C.lint({"播报": ["干完了 ✓", "很干净的一句话"]})
    k3b = (len(c3b) == 1) and ("文档标记" in c3b[0]) and ("?" in c3b[0])
    say("K3b 文档标记：lint 报 %d 条 %s => %s" % (len(c3b), c3b[:1], k3b))
    ok &= k3b

    # ---- K4：覆盖账 ----
    c4 = {"播报": ["a", "b"], "反应": ["c"], "闲聊": ["d"], "求助": ["e"],
          "邀功": ["f"], "承诺": ["g"], "__loose__": []}
    cov = C.coverage(c4)
    k4 = (cov["n"]["播报"] == 2) and (cov["total"] == 7) and (cov["empty"] == ["接话"]) \
        and (cov["empty_closed"] == [])
    say("K4 覆盖账：%s ｜ 空=%s ｜ **该补的**=%s => %s"
        % (cov["n"], cov["empty"], cov["empty_closed"], k4))
    ok &= k4

    # ---- K5：口径对账 ----
    k5 = (tuple(C.KINDS) == tuple(S.KINDS)) and (tuple(C.OPEN_KINDS) == tuple(S.OPEN_KINDS))
    say("K5 口径：corpus.KINDS==speech.KINDS=%s ｜ OPEN 一致=%s => %s"
        % (tuple(C.KINDS) == tuple(S.KINDS), tuple(C.OPEN_KINDS) == tuple(S.OPEN_KINDS), k5))
    ok &= k5

    # ---- K6：手写区**永不覆盖** ----
    #   ⚠ 句子**不带** `✓✗★`（P136 ✓）—— 带标记的句子写盘会被剥 ✗ ⇒ 拿它当"原样保留"的证据会假红 ✓
    old = CI.compose("头\n", {"播报": ["自动来的"]},
                     "\n\n## 播报\n- 【手写】我的句子\n", "（原有）")
    new = CI.compose("头\n", {"播报": ["自动来的", "新自动的"]},
                     CI.hand_zone(old), "（原有）")
    k6 = ("【手写】我的句子" in new) and ("新自动的" in new) \
        and (CI.hand_zone(old) == CI.hand_zone(new))
    say("K6 手写区：手改那句还在=%s ｜ 自动区跟着变=%s => %s"
        % ("【手写】我的句子" in new, "新自动的" in new, k6))
    ok &= k6

    # ---- K7：盘上真库 ＋ 端到端 ----
    lib = C.load()
    bad7 = C.lint(lib)
    cov7 = C.coverage(lib)
    thin = [k for k, v in cov7["n"].items() if k not in C.OPEN_KINDS and v < 3]
    # 端到端：真库里的句子**必须真的能落到某个意图上** ✗（库接了却没接上 ＝ 白做 ✓）
    it = S.Intent("播报", "test", {"job": "干活", "phase": "start"})
    line, src = S.render(it, lib)
    it2 = S.Intent("求助", "test", {"job": "干活", "phase": "stuck"})
    line2, src2 = S.render(it2, lib)
    k7 = (CI.OUT.is_file()) and (not bad7) and (not thin) and src.startswith("corpus:") \
        and bool(line) and src2.startswith("corpus:") and bool(line2)
    say("K7 盘上真库：%s ｜ %d 条 ｜ 体检 %s ｜ 少于 3 条的类型 %s"
        % (CI.OUT.name, cov7["total"], "干净 ✓" if not bad7 else bad7[:2], thin))
    say("     端到端：播报⇒%r（%s）｜ 求助⇒%r（%s） => %s"
        % (line, src, line2, src2, k7))
    ok &= k7

    # ---- K8：槽位白名单**从模组源码读**（不是手抄 ✗）----
    ms = C.mod_slots()
    # ★要哪些字段**也是从源码看来的**✗★：`drop_expiring` 带 `left_s`/`dist` ✓
    #   `damage` 带 `hp`/`delta` ✓ `xp` 带 `level` ✓ `inv` 带 delta ✓
    #   （★我第一版把 `count` 也写进来了 ✗ —— 模组发的是 `"x" + 件数`（**不是 `count=`**）✗
    #      ⇒ 判据当场报缺 ✓ 这就是"抄字段名"的纪律在起作用 ✓ P122 ✓）
    want8 = {"left_s", "dist", "level", "delta", "hp", "item"}
    missing8 = sorted(want8 - ms)
    k8 = (not missing8) and ("left_s" not in C.KNOWN_SLOTS) \
        and not C.lint({"播报": ["{left_s} 秒后 {item} 就没了"]}) \
        and bool(C.lint({"播报": ["{zzz_nope} 一定填不上"]}))
    say("K8 槽位白名单：模组字段 %d 个（含 left_s=%s dist=%s）｜ 我们自己那几个 %d 个"
        " ｜ 缺 %s ｜ 真槽位放行=%s ｜ 假槽位拦下=%s => %s"
        % (len(ms), "left_s" in ms, "dist" in ms, len(C.KNOWN_SLOTS), missing8 or "无 ✓",
           not C.lint({"播报": ["{left_s} 秒后 {item} 就没了"]}),
           bool(C.lint({"播报": ["{zzz_nope} 一定填不上"]})), k8))
    ok &= k8

    # ---- K9：★拿真库把每条扳机走一遍✗★（这条是实机撞出来的 ✓ P134 ✓）----
    lib9 = C.load()
    miss9 = []
    # ① 事件扳机（★样本照模组字段写 ✓ 但**判定用真库**✗★）
    #   ★★`*` 兜底**不算覆盖**✗★★（实测 ✓）：我第一次写 K9 时只判"有没有台词"✗
    #     ⇒ 把真库里 `反应/受伤` 拿掉 ⇒ 它掉到 `*` 说一句"我听着呢 ✓" ⇒ **判据照样绿** ✗✗
    #     —— ★那正是最坏的那种"答非所问"✗★（受伤了回一句"我听着呢" ✓ 谁受得了 ✓）
    #   ⇒ 口径 ✓：出处必须是 `<类型>` 或 `<类型>/<为什么>` 这一级 ✗ **不许是 `*`** ✗
    #     （`*` 留着当**运行时的安全网** ✓ 但它**不能证明**"这一类我们铺过句子"✗）
    def covered(it):
        line, src = S.render(it, lib9)
        return bool(line) and src.startswith("corpus:") and src != "corpus:*"

    miss9 = []
    samp = {"damage": "hp=18.0 delta=-2.0 src=generic", "inv": "delta=-3 items=80 held=none",
            "drop_expiring": "id=7 item=minecraft:emerald x44 left_s=21 dist=1.8",
            "xp": "level=8", "mode": "from=survival to=creative WARN_creative",
            "warp": "from=1.0,2.0,3.0 to=9.0,2.0,3.0 d=8.0",
            "walk_done": "result=reached at=1.00,2.00,3.00 want=2,2,3 dist=0.4",
            "walk_replan": "n=2 path=a,b", "auto_greet": "who=Au_Sn n=1"}
    for k_, data in sorted(samp.items()):
        for (mood, rel) in (("标准", "陌生人"), ("傲娇", "一起干过活"), ("梗", "老搭档")):
            it = S.on_game_event(k_, S.parse_facts(data))
            it.mood, it.relationship = mood, rel
            if not covered(it):
                miss9.append("%s/%s（语气 %s）" % (k_, it.payload.get("why_key"), mood))
    # ② 任务迁移（★为什么键是**任意任务名**✗ ⇒ 只要求掉到**裸 `<类型>`** 那一级 ✓ 仍不许 `*` ✗★）
    for (job, prev, nowp) in (("把沙砾筛完", "新任务", "start"), ("把沙砾筛完", "open", "done"),
                              ("把沙砾筛完", "open", "failed"), ("把沙砾筛完", "open", "stuck")):
        it = S.on_job_transition(prev, nowp, job)
        it.mood, it.relationship = "标准", "陌生人"
        if not covered(it):
            miss9.append("迁移 %s ⇒ %s" % (prev, nowp))
    # ③ 没话找话（★有由头 ✓ 靠裸 `闲聊` ✓ —— 但**不许靠 `*`** ✗）
    it = S.on_idle(999.0, "手里的活：走到 4112,71,18")
    it.mood, it.relationship = "标准", "陌生人"
    if not covered(it):
        miss9.append("没话找话（有由头）")
    k9 = not miss9
    say("K9 扳机有台词（★真库✗★，且**兜底 `*` 不算**✗）：事件 %d 条 × 3 语气 ＋ 迁移 4 ＋ idle 1"
        " ｜ 抽不到的 %s => %s" % (len(samp), miss9[:6] if miss9 else "无 ✓", k9))
    ok &= k9

    say("---- K1..K9 = %s ----" % ok)
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
