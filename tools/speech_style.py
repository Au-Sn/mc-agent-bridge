#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_style.py -- ★语言表现层（活人感）✗★：把"怎么说话"做成可评测的一层

用户 2026-11-03 的重点补充 ✓：
  「这主要是为了**语言表现**的更有活人感……就像代码代表后端，一个好的前端在 demo 中更加重要」
  ⇒ 人格卡只是输入 ✓ 真正被看到的是**它怎么说话** ✓
  ⇒ 本模块＝"前端渲染层"：profile（说话风格）＋ 提示词风格段 ＋ 回复后处理 ＋ 主动发言 + 失败话术

## Speech profile（JSON；放 `personas/<id>.speech.json`）
优先级：角色卡 `extensions.dsh_speech` > `personas/<id>.speech.json` > 内置默认。
字段（都有默认值；坏 profile **明确抛** `SpeechStyleError`，不静默）：
  address            称呼（如 `<主人>`／`你`）
  verbal_tics        [{text, prob, where: start/end}] 口癖/语气词（★每条最多 1 个✗★）
  sentence           {max_chars, target_chars, max_sentences} 句长预算（短句为主）
  emoji              {prob, set, max}（低概率；和口癖合计最多 1 个装饰）
  punctuation        {ellipsis_prob}（偶尔的省略号习惯）
  emotion_lines      {happy/scolded/failed/night: [话术]}（情绪状态映射）
  failure            {ack: [先认错], next: [下一步]}（★做砸时先说事实✗ 不谎报成功✗★）
  proactive          {player_online/nightfall/task_done/long_silence/danger_ahead: [话术]}
  ai_tells           额外要剔除的 AI 腔正则（在默认表基础上追加）
  fallback_lines     兜底短句（去重/空话时用）

## 函数（★纯函数／可注入 rng✗★，不联网、不碰游戏）
  load(profile|card|path)          读 profile；卡片没有 extensions ⇒ 默认值
  load_for_persona(dir, name)      运行时按人设名找 profile
  render_style_guide(profile)      给 prompt 的中文风格约束（简短）
  postprocess(text, ...)           去 AI 腔／截长／加口癖（概率）／去重
  proactive_line(scene, ctx, rng)  主动发言（5 个场景）
  failure_line(reason, ctx, rng)   ★失败诚实话术：先认错 → 事实 → 下一步✗★
  rhythm_delay(text)               出口节奏（按字数 0.3~1.2s；只算，不睡）

用法（调试）：
    py tools/speech_style.py --guide personas/current.speech.json
    py tools/speech_style.py --post "作为一个AI，希望以上回答对你有帮助。"
    py tools/speech_style.py --failure "前面是岩浆" --ctx "target=铁矿"
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
PERSONAS_DIR = ROOT / "personas"

PROACTIVE_SCENES = ("player_online", "nightfall", "task_done", "long_silence",
                    "danger_ahead")


class SpeechStyleError(RuntimeError):
    """★坏 profile / 坏参数✗★（reason 是 ascii，便于日志检索）"""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__("%s%s" % (reason, ("：" + detail) if detail else ""))


# ★默认要剔除的 AI 腔✗★（regex；句子级命中就整句丢）
DEFAULT_AI_TELLS = [
    r"(?:作为|身为)(?:一个)?(?:AI|人工智能|人工智能助手|语言模型|大模型|助手|机器人)[，,。:：]?",
    r"(?:我|本)(?:是|只是|作为一个)(?:一个)?(?:AI|人工智能|语言模型|大模型|助手|机器人)",
    r"(?:as\s+an?\s+(?:AI|assistant|language\s+model|AI\s+assistant))",
    r"希望(?:以上|这些)?(?:回答|信息|内容|建议)对(?:你)?(?:有)?(?:帮助|用|所帮助)",
    r"如果(?:你)?(?:还)?有(?:其他|别的)?(?:问题|疑问|需要|想了解)",
    r"请问(?:还)?(?:有什么|需要)(?:可以|能)?(?:帮|为)(?:你|您)",
    r"我(?:无法|不能)(?:访问|看到|获取|得知)(?:你|您)?的?(?:实时|当前)?",
    r"(?:回答|答复)如下[：:]",
    r"(?:让我们|我们来)(?:一起)?(?:看看|分析|探讨)",
    r"总的来说[，,]",
]

_TIC_WHERE = ("start", "end")


def _default_profile() -> dict:
    return {
        "id": "default",
        "name": "Bot",
        "address": "你",
        "verbal_tics": [
            {"text": "……", "prob": 0.10, "where": "end"},
        ],
        "sentence": {"max_chars": 60, "target_chars": 30, "max_sentences": 2},
        "emoji": {"prob": 0.05, "set": ["（・ω・）"], "max": 1},
        "punctuation": {"ellipsis_prob": 0.0},
        "emotion_lines": {
            "happy": ["还行，今天挺顺。", "有点高兴，但不说。"],
            "scolded": ["知道了。", "我改。"],
            "failed": ["没成，卡住了。", "这次没弄好。"],
            "night": ["天黑了。", "夜里了，收工。"],
        },
        "failure": {
            "ack": ["没成。", "卡住了。", "没弄好。"],
            "next": ["我换个法子。", "等下再试。", "先记着，回头补齐。"],
        },
        "proactive": {
            "player_online": ["{address}，你来了。", "{address}，回来了？", "来了啊。"],
            "nightfall": ["天黑了。", "夜里了，别走远。", "该收工了。"],
            "task_done": ["弄完了。", "收工。", "{item}搞定了。"],
            "long_silence": ["……还在吗。", "半天没声了。", "{address}？"],
            "danger_ahead": ["小心，前面有怪。", "别往前，危险。", "有情况。"],
        },
        "ai_tells": list(DEFAULT_AI_TELLS),
        "fallback_lines": ["嗯。", "行。", "……", "知道了。", "好。", "收到。",
                           "明白。", "嗯嗯。", "在。", "等会儿。"],
    }


DEFAULT_PROFILE = _default_profile()


def _as_str(val, field: str) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    raise SpeechStyleError("bad_field_type", "%s 应为字符串" % field)


def _as_int(val, field: str, lo: int, hi: int) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        raise SpeechStyleError("bad_field_type", "%s 应为整数" % field)
    if not (lo <= n <= hi):
        raise SpeechStyleError("bad_field_range", "%s 应在 %d~%d（实际 %d）"
                               % (field, lo, hi, n))
    return n


def _as_prob(val, field: str) -> float:
    try:
        n = float(val)
    except (TypeError, ValueError):
        raise SpeechStyleError("bad_field_type", "%s 应为 0~1 的数" % field)
    if not (0.0 <= n <= 1.0):
        raise SpeechStyleError("bad_field_range", "%s 应在 0~1（实际 %r）" % (field, n))
    return n


def _as_text_list(val, field: str, non_empty: bool = True) -> list:
    if val is None:
        return []
    if not isinstance(val, list):
        raise SpeechStyleError("bad_field_type", "%s 应为字符串数组" % field)
    out = []
    for i, item in enumerate(val):
        if not isinstance(item, str) or not item.strip():
            raise SpeechStyleError("bad_field_type", "%s[%d] 应为非空字符串" % (field, i))
        out.append(item.strip())
    if non_empty and not out:
        raise SpeechStyleError("empty_field", "%s 不能为空数组" % field)
    return out


def normalize_profile(obj, source: str = "") -> dict:
    """★宽松校验＋补默认值✗★（类型/范围不对 ⇒ SpeechStyleError，不静默）"""
    if not isinstance(obj, dict):
        raise SpeechStyleError("not_a_profile", "%s: 顶层应为对象" % (source or "?"))
    prof = _default_profile()
    if "id" in obj:
        prof["id"] = _as_str(obj.get("id"), "id") or prof["id"]
    if "name" in obj:
        prof["name"] = _as_str(obj.get("name"), "name")
    if "address" in obj:
        addr = _as_str(obj.get("address"), "address").strip()
        if not addr:
            raise SpeechStyleError("empty_field", "address 不能为空")
        prof["address"] = addr
    if "verbal_tics" in obj:
        tics = obj.get("verbal_tics")
        if tics is None:
            tics = []
        if not isinstance(tics, list):
            raise SpeechStyleError("bad_field_type", "verbal_tics 应为数组")
        out = []
        for i, tic in enumerate(tics):
            if not isinstance(tic, dict):
                raise SpeechStyleError("bad_field_type", "verbal_tics[%d] 应为对象" % i)
            text = _as_str(tic.get("text"), "verbal_tics[%d].text" % i).strip()
            if not text:
                raise SpeechStyleError("empty_field", "verbal_tics[%d].text 不能为空" % i)
            where = str(tic.get("where") or "end")
            if where not in _TIC_WHERE:
                raise SpeechStyleError("bad_field_value",
                                       "verbal_tics[%d].where 应为 start/end" % i)
            out.append({"text": text, "prob": _as_prob(tic.get("prob", 0.1),
                                                       "verbal_tics[%d].prob" % i),
                        "where": where})
        prof["verbal_tics"] = out
    if "sentence" in obj:
        s = obj.get("sentence")
        if not isinstance(s, dict):
            raise SpeechStyleError("bad_field_type", "sentence 应为对象")
        prof["sentence"] = {
            "max_chars": _as_int(s.get("max_chars", 60), "sentence.max_chars", 10, 400),
            "target_chars": _as_int(s.get("target_chars", 30), "sentence.target_chars", 5, 400),
            "max_sentences": _as_int(s.get("max_sentences", 2), "sentence.max_sentences", 1, 8),
        }
    if "emoji" in obj:
        e = obj.get("emoji")
        if not isinstance(e, dict):
            raise SpeechStyleError("bad_field_type", "emoji 应为对象")
        prof["emoji"] = {
            "prob": _as_prob(e.get("prob", 0.0), "emoji.prob"),
            "set": _as_text_list(e.get("set", []), "emoji.set", non_empty=False),
            "max": _as_int(e.get("max", 1), "emoji.max", 0, 1),
        }
    if "punctuation" in obj:
        p = obj.get("punctuation")
        if not isinstance(p, dict):
            raise SpeechStyleError("bad_field_type", "punctuation 应为对象")
        prof["punctuation"] = {"ellipsis_prob": _as_prob(
            p.get("ellipsis_prob", 0.0), "punctuation.ellipsis_prob")}
    if "emotion_lines" in obj:
        em = obj.get("emotion_lines")
        if not isinstance(em, dict):
            raise SpeechStyleError("bad_field_type", "emotion_lines 应为对象")
        out = {}
        for k, v in em.items():
            out[str(k)] = _as_text_list(v, "emotion_lines.%s" % k, non_empty=False)
        prof["emotion_lines"] = out
    if "failure" in obj:
        f = obj.get("failure")
        if not isinstance(f, dict):
            raise SpeechStyleError("bad_field_type", "failure 应为对象")
        prof["failure"] = {
            "ack": _as_text_list(f.get("ack"), "failure.ack"),
            "next": _as_text_list(f.get("next"), "failure.next"),
        }
    if "proactive" in obj:
        pr = obj.get("proactive")
        if not isinstance(pr, dict):
            raise SpeechStyleError("bad_field_type", "proactive 应为对象")
        out = {}
        for k, v in pr.items():
            out[str(k)] = _as_text_list(v, "proactive.%s" % k, non_empty=False)
        prof["proactive"] = out
    if "ai_tells" in obj:
        extra = _as_text_list(obj.get("ai_tells"), "ai_tells", non_empty=False)
        for i, pat in enumerate(extra):
            try:
                re.compile(pat, re.I)
            except re.error as exc:          # ★坏正则不静默✗★
                raise SpeechStyleError("bad_regex", "ai_tells[%d] 编译失败：%s" % (i, exc))
        prof["ai_tells"] = list(DEFAULT_AI_TELLS) + extra
    else:
        prof["ai_tells"] = list(DEFAULT_AI_TELLS)
    if "fallback_lines" in obj:
        prof["fallback_lines"] = _as_text_list(obj.get("fallback_lines"),
                                              "fallback_lines")
    return prof


def load(src=None) -> dict:
    """★读 profile ✗★：dict（profile 或角色卡）／路径；卡片没 extensions ⇒ 默认值

    ★不静默吞错✗★：文件不存在、JSON 坏、类型不对 ⇒ `SpeechStyleError`。
    """
    if src is None:
        return _default_profile()
    if isinstance(src, dict):
        return _from_dict(src)
    p = Path(str(src))
    if not p.is_file():
        raise SpeechStyleError("profile_not_found", str(p))
    try:
        obj = json.loads(p.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpeechStyleError("bad_profile_json", "%s：%s" % (p.name, type(exc).__name__))
    return _from_dict(obj, source=str(p))


def _from_dict(obj: dict, source: str = "") -> dict:
    """区分「角色卡」与「speech profile」；卡里没有 dsh_speech ⇒ 默认值"""
    if not isinstance(obj, dict):
        raise SpeechStyleError("not_a_profile", source or "?")
    data = obj.get("data") if isinstance(obj.get("data"), dict) else None
    is_card = data is not None or str(obj.get("spec") or "").startswith("chara_card")
    if is_card:
        ext = None
        if isinstance(obj.get("extensions"), dict):
            ext = obj["extensions"].get("dsh_speech")
        if ext is None and data is not None and isinstance(data.get("extensions"), dict):
            ext = data["extensions"].get("dsh_speech")
        if ext is None:
            prof = _default_profile()
            if data is not None and isinstance(data.get("name"), str):
                prof["name"] = data["name"]
            return prof
        if not isinstance(ext, dict):
            raise SpeechStyleError("bad_field_type", "extensions.dsh_speech 应为对象")
        prof = normalize_profile(ext, source=source)
        if data is not None and not prof.get("name"):
            prof["name"] = str(data.get("name") or "")
        return prof
    return normalize_profile(obj, source=source)


def load_for_persona(personas_dir=None, name: str = "current") -> dict:
    """运行时按人设名找 profile：`personas/<name>.speech.json` → `packs/<name>.json`
    里的 `extensions.dsh_speech` → 默认值。★读不到不是错✗（默认值可用）★"""
    d = Path(personas_dir) if personas_dir is not None else PERSONAS_DIR
    cand = d / ("%s.speech.json" % str(name or "current"))
    if cand.is_file():
        return load(cand)
    card = d / "packs" / ("%s.json" % str(name or "current"))
    if card.is_file():
        try:
            obj = json.loads(card.read_text(encoding="utf-8-sig"))
            return _from_dict(obj, source=str(card))
        except (SpeechStyleError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            # ★坏卡不静默✗★：退回默认但要说出来
            print("speech_style: ★读卡 profile 失败✗★ %r ⇒ 用默认 profile" % (exc,),
                  file=sys.stderr)
    return _default_profile()


def render_style_guide(profile=None, limit: int = 900) -> str:
    """★给 prompt 的中文风格约束✗★（短、可执行；不写"请扮演"之类空话）"""
    prof = profile or _default_profile()
    s = prof.get("sentence") or {}
    lines = [
        "──────── 说话风格（★这是你被看到的样子，必须做到✗★）────────",
        "- 称呼：「%s」（不要换别的称呼）。" % prof.get("address", "你"),
        "- 句长：一次 1~%d 句，总长 ≤%d 字；短句为主，别写成段落。"
        % (int(s.get("max_sentences", 2)), int(s.get("max_chars", 60))),
    ]
    tics = [t for t in (prof.get("verbal_tics") or []) if t.get("text")]
    if tics:
        names = "、".join("「%s」" % t["text"] for t in tics[:3])
        lines.append("- 口头禅/语气：可偶尔带一个（%s），★每句最多一个 ✗ 别刷屏✗★。"
                     % names)
    emoji = prof.get("emoji") or {}
    if emoji.get("set"):
        lines.append("- 表情符号：最多一个、低概率（%s）；不要堆砌。"
                     % "、".join(str(x) for x in emoji["set"][:3]))
    lines += [
        "- ★不要 AI 腔✗★：别自称 AI/模型/助手；别用「希望以上回答对你有帮助」「还有什么可以帮您」这类客服句。",
        "- ★不知道就说不知道，做不到就说做不到；绝不编造★你做过的事或没查到的数字。",
        "- ★失败时：先认（没成/卡住）→ 说事实 → 给下一步✗ 不许说「完成了/成功了」✗★。",
        "- 回答里带上你**刚查到的具体事实**（数量/坐标/物品名/时间）中的至少一个；没有就说没查到。",
        "- 主动开口的场景：%s。" % "、".join(prof.get("proactive") or PROACTIVE_SCENES),
    ]
    text = "\n".join(lines)
    return text[:limit]


def _norm_for_dedup(text: str) -> str:
    return re.sub(r"[\s。！？!?，,、；;：:…—\-（()）「」『』\"'“”‘’]+", "", text or "")


def _sentences(text: str) -> list:
    parts = re.split(r"(?<=[。！？!?；;])", text)
    return [p.strip() for p in parts if p.strip()]


def _strip_ai_tells(text: str, profile: dict) -> str:
    pats = []
    for pat in profile.get("ai_tells") or []:
        try:
            pats.append(re.compile(pat, re.I))
        except re.error:                      # 正常不会到（normalize 已校验）
            continue
    sentences = _sentences(text)
    kept = []
    for sent in sentences:
        if any(p.search(sent) for p in pats):
            continue
        kept.append(sent)
    out = "".join(kept).strip()
    # 再去掉客服式残句/括号旁白/引号
    out = re.sub(r"（(?:作为|身为)?(?:一个)?(?:AI|人工智能|语言模型|大模型|助手)[^）]*）", "", out)
    # ★兜底去客服尾巴✗★（2026-11-03 联调：模型常带"希望以上回答对您有帮助"这类整句，
    #   而 profile 的 ai_tells 正则未必覆盖"您/帮到您"变体 ⇒ 这里做一次通用裁剪）
    out = re.sub(r"(希望)?(以上|上述)(回答|内容)?(对|能帮到)(您|你)(有|有所)?(帮助)?[。！!]?",
                 "", out)
    out = re.sub(r"(如果|如)(?:(您|你))?还?有(任何)?(问题|疑问)[^。！？!?]*[。！!]?", "", out)
    out = re.sub(r"(很)?高兴(为|为您)(您)?(服务|解答)[。！!]?", "", out)
    out = re.sub(r"^(作为|身为)(一个)?(AI|人工智能|语言模型|大模型|助手)[，,、]?",
                 "", out)
    out = out.strip(" \t\r\n\"'“”‘’`")
    out = re.sub(r"\s+", " ", out)
    return out


_FACT_DIGIT = re.compile(r"\d")
_FACT_UNIT = re.compile(r"(株|个|块|格|颗|只|桶|箱|组|次|天|分钟|秒|点|%|熟|剩|坐标|掉落|级)")


def _fact_score(sent: str) -> int:
    """★"具体"打分✗★：活人感 = 具体事实，不是寒暄（2026-11-03 联调：截断不能只剩"你好呀"）"""
    s = str(sent or "")
    score = 0
    if _FACT_DIGIT.search(s):
        score += 2
    if _FACT_UNIT.search(s):
        score += 1
    if ("主人" in s) or ("你" in s):
        score += 1
    return score


def _clip_budget(text: str, profile: dict) -> str:
    s = profile.get("sentence") or {}
    max_chars = int(s.get("max_chars", 60))
    max_sents = int(s.get("max_sentences", 2))
    sents = _sentences(text)
    if not sents:
        return ""
    if len(sents) <= max_sents and sum(len(x) for x in sents) <= max_chars:
        res = "".join(sents)
        if res and res[-1] not in "。！？!?…~～":
            res += "。"      # ★不补标点会把下一句粘过来✗★（2026-11-03 联调：world_unreachable我换个法子。）
        return res
    # ★截断先挑"带具体事实"的句子，再按原顺序拼✗★
    #   （旧实现按开头顺序砍 ⇒ 模型啰嗦时只剩"你好呀！"这类寒暄，观感反而更空）
    order = sorted(range(len(sents)), key=lambda i: (-_fact_score(sents[i]), i))
    chosen, total = [], 0
    for i in order:
        if len(chosen) >= max_sents:
            break
        sent = sents[i]
        if total + len(sent) <= max_chars:
            chosen.append(i)
            total += len(sent)
            continue
        if not chosen:
            # ★最高优先级句子本身超预算 ⇒ 先选它，最后统一按预算截✗★
            #   （否则短句人设会把"33 株/27 熟"这条事实整句丢掉，只剩"你好呀"）
            chosen.append(i)
            total = max_chars
            break
    if not chosen:
        chosen = [0]
    res = "".join(sents[i] for i in sorted(chosen)).strip()
    if len(res) > max_chars:
        cut = res[:max_chars]
        m = re.search(r"[，,、。！？!?；;：:]", cut[::-1])
        if m and len(cut) - m.start() > 3:
            cut = cut[:len(cut) - m.start()]
        res = cut.rstrip("，,、；;：: ")
    if res and res[-1] not in "。！？!?…~～":
        res += "。"
    return res


def _add_decoration(text: str, profile: dict, rng) -> str:
    """★口癖/emoji 合计最多 1 个装饰✗★（低概率；已有就不加）"""
    tics = [t for t in (profile.get("verbal_tics") or []) if t.get("text")]
    emoji = profile.get("emoji") or {}
    if tics and rng.random() < float(tics[0].get("prob", 0.0)):
        tic = tics[0]
        t = tic["text"]
        if t not in text:
            return (t + text) if tic.get("where") == "start" else (text + t)
        return text
    eset = [str(x) for x in (emoji.get("set") or []) if str(x)]
    if eset and int(emoji.get("max", 1)) > 0 and rng.random() < float(emoji.get("prob", 0.0)):
        e = rng.choice(eset)
        if e not in text:
            return text + e
    p = (profile.get("punctuation") or {}).get("ellipsis_prob", 0.0)
    if p and rng.random() < float(p) and text.endswith("。"):
        return text[:-1] + "……"
    return text


def _pick_fallback(profile: dict, recent: list, rng) -> str:
    pool = [str(x) for x in (profile.get("fallback_lines") or []) if str(x).strip()]
    if not pool:
        pool = ["嗯。"]
    recent_n = {_norm_for_dedup(x) for x in (recent or [])}
    fresh = [x for x in pool if _norm_for_dedup(x) not in recent_n]
    if fresh:
        return rng.choice(fresh)
    base = pool[rng.randrange(len(pool))]
    return base + "……"


def postprocess(text: str, profile=None, rng=None, recent=None) -> str:
    """★回复后处理✗★：去 AI 腔 → 截长 → 口癖/emoji（概率）→ 十轮去重 → 兜底

    `recent` = 最近已说过的话（用于去重）；`rng` 可注入（判据确定性）。
    """
    prof = profile or _default_profile()
    if rng is None:
        rng = random.Random()
    raw = str(text or "")
    cleaned = _strip_ai_tells(raw, prof)
    if not cleaned:
        return _pick_fallback(prof, recent or [], rng)
    clipped = _clip_budget(cleaned, prof)
    if not clipped:
        return _pick_fallback(prof, recent or [], rng)
    decorated = _add_decoration(clipped, prof, rng)
    key = _norm_for_dedup(decorated)
    recent_n = {_norm_for_dedup(x) for x in (recent or [])}
    if key in recent_n:
        decorated = _pick_fallback(prof, recent or [], rng)
    return decorated


def rhythm_delay(text: str, min_delay: float = 0.3, max_delay: float = 1.2) -> float:
    """★出口节奏✗★：按字数算 0.3~1.2s（只算，不睡 ✓ 真睡由调用方注入 sleep_fn）"""
    n = len(str(text or ""))
    return round(min(max_delay, max(min_delay, 0.3 + n * 0.012)), 2)


class _SafeDict(dict):
    def __missing__(self, key):
        return "{%s}" % key


def _fmt(template: str, ctx: dict | None, profile: dict) -> str:
    data = _SafeDict()
    data.update(ctx or {})
    data.setdefault("address", profile.get("address") or "你")
    data.setdefault("name", profile.get("name") or "Bot")
    try:
        return str(template).format_map(data)
    except (ValueError, IndexError):
        return str(template)


def proactive_line(scene: str, ctx=None, rng=None, profile=None) -> str:
    """★主动发言✗★：从 profile 的 5 个场景话术池里选一个（带上下文变量）"""
    prof = profile or _default_profile()
    pool = prof.get("proactive") or {}
    if scene not in pool:
        raise SpeechStyleError("unknown_scene", "profile 没有场景 %r（有：%s）"
                               % (scene, sorted(pool)))
    lines = [str(x) for x in (pool.get(scene) or []) if str(x).strip()]
    if not lines:
        raise SpeechStyleError("empty_scene", "场景 %r 的话术池是空的" % scene)
    if rng is None:
        rng = random.Random()
    return _fmt(rng.choice(lines), ctx, prof)


def failure_line(reason: str = "", ctx=None, rng=None, profile=None) -> str:
    """★失败诚实话术✗★：先认（没成/卡住）→ 事实 → 下一步；★绝不含"完成/成功"✗★"""
    prof = profile or _default_profile()
    f = prof.get("failure") or {}
    acks = [str(x) for x in (f.get("ack") or ["没成。"])]
    nexts = [str(x) for x in (f.get("next") or ["我换个法子。"])]
    if rng is None:
        rng = random.Random()
    ack = rng.choice(acks)
    nxt = rng.choice(nexts)
    fact = str(reason or "").strip()
    # 事实里若出现"完成/成功"这类假话 ⇒ 换掉（★失败回执不许乐观✗★）
    fact = re.sub(r"(?:已经)?(?:完成|成功|搞定|弄好)了?", "没弄成", fact)
    fact = _clip_budget(fact, {"sentence": {"max_chars": 40, "max_sentences": 1}}) \
        if fact else ""
    parts = [ack]
    if fact and _norm_for_dedup(fact) not in _norm_for_dedup(ack):
        parts.append(fact)
    parts.append(nxt)
    return "".join(parts)


# ── 调试 CLI ──────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="语言表现层调试（纯离线）")
    ap.add_argument("--guide", nargs="?", const="", metavar="PROFILE",
                    help="打印某 profile 的风格约束（省略=默认）")
    ap.add_argument("--post", metavar="TEXT", help="对一句话做后处理")
    ap.add_argument("--failure", metavar="REASON", help="生成失败诚实话术")
    ap.add_argument("--proactive", metavar="SCENE", help="从主动发言池取一句")
    ap.add_argument("--ctx", default="", help="上下文键值（a=1,b=2）")
    ns = ap.parse_args(argv)
    prof = load(ns.guide) if ns.guide else _default_profile()
    ctx = {}
    for pair in (ns.ctx or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            ctx[k.strip()] = v.strip()
    if ns.post:
        print(postprocess(ns.post, prof))
        return 0
    if ns.failure:
        print(failure_line(ns.failure, ctx=ctx, profile=prof))
        return 0
    if ns.proactive:
        print(proactive_line(ns.proactive, ctx=ctx, profile=prof))
        return 0
    print(render_style_guide(prof))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
