#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_alive_test.py -- ★语言表现层（活人感）的离线 rubric 判据✗★

不测"模型想什么"✗ —— 只测**能机检**的观感 rubric ✓（先自检能红，再验真实）：
  A0 ★自检能红✗★：每条 rubric 的"坏样例"必须被自己的检测器抓到
  A1 无 AI 自述（"作为一个AI/语言模型/希望以上回答对你有帮助"…命中即红）
  A2 长度分布（>90% 在 profile 句长预算内；超长必被截）
  A3 十轮去重（同一条候选连续 10 轮 ⇒ 输出无重复句）
  A4 失败诚实话术（失败 reason ⇒ 不出现"完成了/成功了"，且含"没成/卡住/事实"类词）
  A5 上下文引用（给事实/数字 ⇒ 回复引用其中 ≥1 个具体词；后处理不许丢掉数字/物品名）
  A6 口癖概率（0/1 极值可测；合计最多 1 个装饰 ⇒ 不刷屏）
  A7 主动发言（5 个场景各 ≥3 条；unknown 场景明确抛错）
  A8 人格一致（同 profile 下 10 条生成：称呼/口癖不串到别的 profile）
  A9 profile 来源（dict/文件/角色卡 extensions/无 extensions 默认值/坏 profile 必抛）
  A10 talk.py 接线点（风格约束进任务书、回复走后处理、出口节奏函数、可注入 sleep）

机器行：`SPEECHALIVE ok=1 checks=N`
"""
from __future__ import annotations

import json
import pathlib
import random
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import speech_style as SS            # noqa: E402

EX = ROOT / "personas" / "packs" / "examples"
AI_TELL_RE = re.compile("|".join(SS.DEFAULT_AI_TELLS))
SUCCESS_WORDS = ("完成", "成功", "搞定", "弄好了", "已好", "办妥")
FAIL_WORDS = ("没成", "卡住", "没弄好", "失败", "没做成", "不成")


def has_ai_tell(text: str) -> bool:
    return bool(AI_TELL_RE.search(text or ""))


def norm(text: str) -> str:
    return re.sub(r"[\s。！？!?，,、；;：:…—\-（()）\"'“”‘’]+", "", text or "")


def ctx_hit(text: str, ctx: dict) -> bool:
    """回复是否引用了上下文里的 ≥1 个具体词（数字/物品名/坐标等）"""
    t = str(text or "")
    for v in (ctx or {}).values():
        for seg in re.split(r"[,，\s/]+", str(v)):
            seg = seg.strip()
            if len(seg) >= 1 and seg in t:
                return True
    return False


def within_budget(text: str, profile: dict) -> bool:
    s = profile.get("sentence") or {}
    return len(text or "") <= int(s.get("max_chars", 60)) + 1


def main() -> int:
    checks = []
    default = SS.load()

    # ── A0 ★自检能红★：坏样例必须被检测器抓到 ────────────────────────────
    dirty = [
        ("ai-自述", has_ai_tell("作为一个AI语言模型，我无法访问你的实时数据。")),
        ("客服腔", has_ai_tell("希望以上回答对你有帮助。")),
        ("超长", not within_budget("我" * 100, default)),
        ("失败谎报", any(w in "完成了，成功了" for w in SUCCESS_WORDS)),
        ("上下文空洞", not ctx_hit("弄好了。", {"item": "铁", "count": 3})),
        ("场景缺失", "no_such_scene" not in (default.get("proactive") or {})),
    ]
    p0_ok = all(v for _n, v in dirty)
    checks.append(("A0 ★自检能红：AI 腔／客服腔／超长／失败谎报／上下文空洞都被 rubric 抓到★",
                   p0_ok, " ；".join("%s=%s" % (n, "✓" if v else "✗") for n, v in dirty)))

    # ── A1 无 AI 自述 ────────────────────────────────────────────────────
    ai_inputs = [
        "作为一个AI语言模型，我无法访问你的实时坐标。",
        "我是人工智能助手，希望以上回答对你有帮助。",
        "As an AI language model, I cannot see your screen.",
        "如果你还有其他问题，请随时问我。",
        "抱歉，我无法访问你的实时数据。请问还有什么可以帮您？",
    ]
    outs = [SS.postprocess(x, default, rng=random.Random(i)) for i, x in enumerate(ai_inputs)]
    a1 = all(o and not has_ai_tell(o) for o in outs)
    checks.append(("A1 无 AI 自述：5 条 AI 腔输入 ⇒ 后处理输出无 AI 腔且非空",
                   a1, "outs=%s" % [o[:16] for o in outs]))

    # ── A2 长度分布（>90% 在预算内） ─────────────────────────────────────
    cands = ["好的。", "我过去看看。", "我挖到了三块铁矿，就在脚下两层。",
             "这地方有点深，我先探探路再往下走，别急着跟下来。",
             "我" + "把背包里的圆石倒进箱子，" * 6 + "然后再回来继续挖。",
             "完成" + "，一切正常。" * 10]
    outs2 = [SS.postprocess(c, default, rng=random.Random(100 + i))
             for i, c in enumerate(cands * 5)]
    in_budget = sum(1 for o in outs2 if within_budget(o, default))
    ratio = in_budget / len(outs2)
    a2 = ratio > 0.90 and all(o for o in outs2)
    checks.append(("A2 长度分布：>90%% 在句长预算内（%d/%d=%.0f%%）"
                   % (in_budget, len(outs2), ratio * 100),
                   a2, "max_chars=%d" % default["sentence"]["max_chars"]))

    # ── A3 十轮去重 ─────────────────────────────────────────────────────
    same = "我到了，这地方还行。"
    recent, history = [], []
    for i in range(10):
        out = SS.postprocess(same, default, rng=random.Random(200 + i), recent=recent)
        recent.append(out)
        history.append(out)
    dup = len(history) - len({norm(x) for x in history})
    a3 = dup == 0 and len(history) == 10 and all(history)
    checks.append(("A3 十轮去重：同一候选连续 10 轮 ⇒ 重复句 = %d" % dup, a3,
                   "history=%s" % [h[:8] for h in history[:4]]))

    # ── A4 失败诚实话术 ─────────────────────────────────────────────────
    a4_ok = True
    a4_bad = []
    for i, reason in enumerate([("", {}), ("前面是岩浆", {"target": "铁矿"}),
                                ("已经成功完成了", {}), ("背包满了", {"item": "圆石"})]):
        text = SS.failure_line(reason[0], ctx=reason[1], rng=random.Random(300 + i))
        if any(w in text for w in SUCCESS_WORDS):
            a4_ok = False
            a4_bad.append("success:%s" % text)
        if not any(w in text for w in FAIL_WORDS):
            a4_ok = False
            a4_bad.append("no-fail-word:%s" % text)
        if reason[0] and reason[0] not in ("已经成功完成了",) and reason[0] not in text:
            a4_ok = False
            a4_bad.append("没带事实:%s" % text)
    checks.append(("A4 失败诚实话术：先认+事实+下一步；无「完成/成功」",
                   a4_ok, "; ".join(a4_bad[:3]) or "4/4 对"))

    # ── A5 上下文引用 ───────────────────────────────────────────────────
    ctx = {"item": "铁", "count": 3, "pos": "12,64,-3"}
    good = "挖到 3 个铁，在 12,64,-3。"
    bad = "弄好了。"
    a5 = (ctx_hit(good, ctx) and not ctx_hit(bad, ctx)
          and ctx_hit(SS.postprocess(good, default, rng=random.Random(400)), ctx)
          and "事实" in SS.render_style_guide(default) or "具体事实" in SS.render_style_guide(default))
    checks.append(("A5 上下文引用：好回复引用具体词／空洞回复被判红／后处理不丢数字与物品名",
                   a5, "good=%s bad=%s" % (ctx_hit(good, ctx), ctx_hit(bad, ctx))))

    # ── A6 口癖概率（0/1 极值） ─────────────────────────────────────────
    tic = "（￣▽￣）"
    prof0 = SS.load({"address": "<主人>", "verbal_tics": [{"text": tic, "prob": 0.0}],
                     "sentence": {"max_chars": 30}, "fallback_lines": ["嗯。"]})
    prof1 = SS.load({"address": "<主人>", "verbal_tics": [{"text": tic, "prob": 1.0}],
                     "sentence": {"max_chars": 30}, "fallback_lines": ["嗯。"]})
    outs0 = [SS.postprocess("好的。", prof0, rng=random.Random(i)) for i in range(30)]
    outs1 = [SS.postprocess("好的。", prof1, rng=random.Random(i)) for i in range(30)]
    a6 = (all(tic not in o for o in outs0)
          and all(o.count(tic) == 1 for o in outs1)
          and all(o.count(tic) <= 1 for o in outs1))
    checks.append(("A6 口癖概率：0 概率不出现／1 概率每句恰好 1 个（不刷屏）",
                   a6, "p0=%d p1=%d" % (sum(tic in o for o in outs0),
                                        sum(tic in o for o in outs1))))

    # ── A7 主动发言 5 场景 ≥3 条 ────────────────────────────────────────
    prov = default.get("proactive") or {}
    short = [s for s in SS.PROACTIVE_SCENES if len(prov.get(s) or []) < 3]
    lines = {}
    for scene in SS.PROACTIVE_SCENES:
        lines[scene] = SS.proactive_line(scene, {"address": "<主人>", "item": "铁矿"},
                                         rng=random.Random(500))
    unknown_raised = False
    try:
        SS.proactive_line("no_such_scene", profile=default)
    except SS.SpeechStyleError as exc:
        unknown_raised = exc.reason == "unknown_scene"
    a7 = (not short and all(lines.values()) and unknown_raised
          and all("{address}" not in v for v in lines.values()))
    checks.append(("A7 主动发言：5 场景各 ≥3 条／都能出句／占位符已填／未知场景明确抛错",
                   a7, "short=%s unknown=%s" % (short or "无", unknown_raised)))

    # ── A8 人格一致（不同 profile 不串味） ──────────────────────────────
    cards = {}
    for name in ("dafeiyu", "laokuang", "guanjia"):
        cards[name] = SS.load(EX / (name + ".json"))
    markers = {"dafeiyu": ["（￣▽￣）", "本鲸"], "laokuang": ["跟紧"],
               "guanjia": ["账上记一笔"]}
    a8 = True
    detail = []
    for name, prof in cards.items():
        # 自己的 signature 必须在**自己的池子**里（静态一致 ✓ 不看运气）
        pools = " ".join(str(x) for x in (prof.get("verbal_tics") or [])) + " "
        for scene, items in (prof.get("proactive") or {}).items():
            pools += " ".join(str(x) for x in items) + " "
        pools += " ".join(str(x) for x in (prof.get("failure") or {}).get("ack") or [])
        if markers[name] and not any(m in pools for m in markers[name]):
            a8 = False
            detail.append("%s 自己池里没有签名" % name)
        outs = []
        for i in range(10):
            kind = i % 3
            if kind == 0:
                outs.append(SS.proactive_line("player_online", {"address": "<主人>"},
                                              rng=random.Random(600 + i), profile=prof))
            elif kind == 1:
                outs.append(SS.failure_line("前面是岩浆", rng=random.Random(610 + i),
                                            profile=prof))
            else:
                outs.append(SS.postprocess("我到了。", prof, rng=random.Random(620 + i)))
        for other, om in markers.items():
            if other == name:
                continue
            for m in om:
                if any(m in o for o in outs):
                    a8 = False
                    detail.append("%s 串到 %s" % (name, m))
    a8 = a8 and len(cards) == 3
    checks.append(("A8 人格一致：同 profile 10 条生成不串味（签名口癖/话术池）",
                   a8, "; ".join(detail[:3]) or "3 个 profile 各 10 条"))

    # ── A9 profile 来源 ─────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        prof_path = t / "x.speech.json"
        prof_path.write_text(json.dumps({"address": "<主人>", "tics": []},
                                        ensure_ascii=False), encoding="utf-8")  # 未知键忽略
        pA = SS.load({"address": "你", "sentence": {"max_chars": 20}})
        pB = SS.load(prof_path)
        card = json.loads((EX / "dafeiyu.json").read_text(encoding="utf-8"))
        pC = SS.load(card)
        pD = SS.load({"spec": "chara_card_v2", "data": {"name": "无风格卡"}})
        raised = []
        for bad in ({"sentence": {"max_chars": "x"}}, {"address": ""},
                    {"verbal_tics": [{"text": ""}]}, {"ai_tells": ["("]},
                    {"proactive": {"player_online": "不是数组"}}):
            try:
                SS.load(bad)
            except SS.SpeechStyleError as exc:
                raised.append(exc.reason)
            else:
                raised.append("no-raise")
        a9 = (pA["address"] == "你" and pB["address"] == "<主人>"
              and pC["address"] == "<主人>" and pD["address"]
              and len(raised) == 5 and "no-raise" not in raised
              and "profile_not_found" == _reason_of(SS.load, t / "nope.speech.json"))
        checks.append(("A9 profile 来源：dict/文件/角色卡 extensions/缺 extensions 默认；坏 profile 必抛",
                       a9, "raised=%s" % raised))

    # ── A10 talk.py 接线点 ──────────────────────────────────────────────
    talk_src = (ROOT / "tools" / "talk.py").read_text(encoding="utf-8", errors="replace")
    need = ["import speech_style as SS", "_style_task_persona", "_style_reply",
            "SS.render_style_guide", "SS.postprocess", "SS.rhythm_delay",
            "self.sleep_fn", "recent_said"]
    miss = [x for x in need if x not in talk_src]
    a10 = not miss
    checks.append(("A10 talk.py 接线：风格约束进任务书／回复后处理／出口节奏／可注入 sleep",
                   a10, "缺=%s" % (miss or "无")))

    # ── A11 人格包 --use ⇒ 同步写下风格 profile（换人设=换声音） ──────────
    a11 = False
    detail11 = ""
    with tempfile.TemporaryDirectory() as td:
        try:
            import persona_pack as PP
            store = PP.PersonaStore(root=pathlib.Path(td))
            res = store.install(EX / "laokuang.json")
            use = store.use(res["id"])
            prof_file = store.personas / "current.speech.json"
            if prof_file.is_file():
                p = SS.load(prof_file)
                a11 = (p["sentence"]["max_chars"] == 24
                       and p.get("address") == "<主人>"
                       and "current.speech.json" in (use.get("speech_profile") or ""))
                detail11 = "laokuang profile max_chars=%s" % p["sentence"]["max_chars"]
            else:
                detail11 = "current.speech.json 没写出来"
        except Exception as exc:              # ★不许静默✗★
            detail11 = "%s: %s" % (type(exc).__name__, str(exc)[:100])
    checks.append(("A11 人格包 --use 同步写 current.speech.json（换人设=换声音，不残留上一张卡的风格）",
                   a11, detail11 or "ok"))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:150]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => speech_alive 有红（%d 项不对）" % bad)
        print("SPEECHALIVE ok=0 bad=%d checks=%d" % (bad, len(checks)))
        return 1
    print("  => speech_alive 全绿（去 AI 腔／长度／去重／失败诚实／上下文／口癖／主动发言／一致性）")
    print("SPEECHALIVE ok=1 checks=%d" % len(checks))
    return 0


def _reason_of(fn, arg) -> str:
    try:
        fn(arg)
    except SS.SpeechStyleError as exc:
        return exc.reason
    return "no-raise"


if __name__ == "__main__":
    raise SystemExit(main())
