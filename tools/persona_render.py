#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""persona_render.py -- ★人设退化成一份**渲染配置**★（2026-09-30 ✓ 用户第 6 条 ✓ 纯逻辑 ✓ 离线 ✓）

## 用户原话要点 ✗
  「人设退化成**渲染配置**（词表／句长／emoji 率／错字率 ✗），**时序最后渲染**✗」
  ⇒ ★人设**不再**靠"每句话让模型重写一遍人格"✗★（那必然走形 ✓ 而且烧 token ✓）
    而是：台词库出**底句** ✓ ⇒ 按配置**过一遍渲染管线** ✗ ⇒ 出口 ✓

## 管线顺序（★顺序本身是设计✗★ ✓ 一步都不能换 ✓）
  ```
  库里的底句（含 {真值} ✓）
    ① 词表替换      : 口头禅／称呼（★绝不动数字与物品名✗★）
    ② 句长上限      : 超了就在**标点处**截 ✓（不在字中间砍 ✗）
    ③ emoji         : 按概率缀一个 ✓（★上限 1 个 ✗ 堆砌立刻变廉价 ✓★）
    ④ 错字          : 按概率换一个字 ✓（★只换**汉字**✗ 不碰数字/英文/物品名 ✓★）
    ⑤ ★时序最后渲染✗★ : 出 `delay`（秒 ✓）—— 说什么**先定** ✓ 什么时候说**最后算** ✓
  ```

## 两条铁律（★违反任何一条，这个模块就该被删掉✗★）
  ① ★**真值一个字符都不许动**✗★ —— `{left_s}` 填出来的 `21` ✓ `minecraft:emerald` ✓
     是**世界真值** ✓ ⇒ 词表替换／错字／截断**都不许碰**它们 ✗（★编一个数字 ＝ 本项目最恨的事✗★）
  ② ★**配置是数据**✗★ ⇒ 换人设 ＝ 换一个 json ✓ 不动代码 ✓（同 `personas/<名>.lines.txt` ✓）
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "personas" / "dafeiyu.render.json"

# ★"不许被渲染碰"的东西✗★：数字（含小数 ✓）／物品 id（含 `:` `_` ✓）／坐标 ✓
PROTECT = re.compile(r"(\d+(?:\.\d+)?|[a-z_]+:[a-z_]+|[A-Za-z_]{3,})")
HAN = re.compile(r"[\u4e00-\u9fff]")
PUNCT = "，。！？；、…,.!?;:"

DEFAULT_CFG = {
    "名字": "大肥鱼",
    "称呼玩家": "你",
    "词表": {"我们": "咱们", "我": "本鲸"},   # ★长词条写在前面（最长匹配 ✓ 见 `_sub_word` 注释 ✓）
    "句长": 42,                        # 超过就在标点处截 ✓
    "emoji率": 0.25,                   # ★上限 1 个 ✗★
    "emoji": ["🐟", "✨", "🍚"],
    "错字率": 0.0,                     # ★默认 0✗★：错字是**性格选项** ✓ 不是默认行为 ✗
    "错字表": {"的": "得", "在": "再", "很": "狠", "真": "珍"},
    "基础延迟": 0.8,                   # 秒 ✓（★时序最后算✗★）
    "每字延迟": 0.06,
    "最长延迟": 6.0,
}


def load(path=None) -> dict:
    """★读配置 ✓（没有文件 ⇒ 用默认 ✓ 缺字段 ⇒ 补上 ✓）★ ✗"""
    p = Path(path) if path else DEFAULT
    cfg = dict(DEFAULT_CFG)
    if p.is_file():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            # 记录：配置读坏 ⇒ 静默退回默认渲染参数（等于用错的默认值）
            print("[记录] 渲染配置读不到（退回默认）：%s: %s"
                  % (type(e).__name__, str(e)[:80]), file=sys.stderr)
    return cfg


def _protect_spans(text: str) -> list:
    """★真值／英文／数字的**位置区间**✗★ ✓ ⇒ 后面所有替换都绕开它们 ✓"""
    return [(m.start(), m.end()) for m in PROTECT.finditer(text or "")]


def _untouchable(i: int, spans: list) -> bool:
    return any(a <= i < b for (a, b) in spans)


def _sub_word(text: str, table: dict) -> str:
    """★词表替换（★绕开真值 ✓ 且**不许把词切碎**✗★）★ ✓

    ★不许用"子串替换"✗★（P105/P107 同族 ✓）。两条口径 ✓：
      ① **多字词条**（`"我们": "咱们"` ✓）：按**最长匹配**原样替 ✓
      ② **单字词条**（`"我": "本鲸"` ✓）：只在**词首**替 ✗
         ⇒ 即"前一个字不是汉字"✓ ⇒ `我先去干活` ⇒ `本鲸先去干活` ✓；
           `给我一点时间` ⇒ **一个字都不动** ✗（`我` 是宾语 ✓ 替了就别扭 ✓）
      ③ ★想处理"我们"这种合成词 ⇒ **往词表里写更长的词条**✗★（数据解决 ✓ 不许在代码里放停用词表 ✗
         —— 停用词表就是 P105「子串匹配」那一类错误的温床 ✓）
    """
    if not table:
        return text
    spans = _protect_spans(text)
    keys = sorted(table, key=len, reverse=True)      # ★最长优先✗★
    out, i = [], 0
    while i < len(text):
        if _untouchable(i, spans):
            out.append(text[i])
            i += 1
            continue
        hit = ""
        for k in keys:
            if not k or not text.startswith(k, i):
                continue
            if _untouchable(i + len(k) - 1, spans):   # ★词条尾部压到真值 ⇒ 不替 ✗★
                continue
            if len(k) == 1 and i > 0 and HAN.match(text[i - 1] or ""):
                continue                              # ★单字只认词首✗★
            hit = k
            break
        if hit:
            out.append(str(table[hit]))
            i += len(hit)
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def clip(text: str, limit: int) -> str:
    """★句长上限：**在标点处**截✗★ ✓（★不在字中间砍 ✗ 也不许把真值砍掉半截 ✗★）"""
    if limit <= 0 or len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind(p) for p in PUNCT)
    if cut >= max(4, limit // 3):
        return head[:cut + 1]
    return head.rstrip() + "…"


def maybe_typo(text: str, rate: float, table: dict, rng) -> str:
    """★错字（★只换**汉字**✗ 且绕开真值 ✓ 最多换一个 ✓）★ ✓"""
    if rate <= 0 or not table:
        return text
    spans = _protect_spans(text)
    cand = [i for i, ch in enumerate(text) if ch in table and not _untouchable(i, spans)]
    if not cand or rng.random() > float(rate):
        return text
    i = rng.choice(cand)
    return text[:i] + table[text[i]] + text[i + 1:]


def maybe_emoji(text: str, rate: float, pool: list, rng) -> str:
    """★emoji（★最多一个 ✗ 且不重复加 ✗★）★ ✓"""
    if rate <= 0 or not pool or rng.random() > float(rate):
        return text
    if any(e in text for e in pool):
        return text
    return text + rng.choice(pool)


def timing(text: str, cfg: dict) -> float:
    """★★时序**最后**渲染✗★★ ✓（★说什么先定 ✗ 什么时候说最后算 ✓ 用户第 6 条 ✓）

    · 底：`基础延迟` 秒 ✓（像人在打字／在反应 ✓ 不是机器秒回 ✓）
    · 加上"按字数"的那一份 ✓（长句子说得久 ✓）
    · **封顶**：`最长延迟` ✓（★不许因为一句话长就让人干等 ✗★）
    """
    d = float(cfg.get("基础延迟", 0.8)) + float(cfg.get("每字延迟", 0.06)) * len(text or "")
    return round(min(float(cfg.get("最长延迟", 6.0)), max(0.0, d)), 2)


def render(line: str, cfg: dict = None, rng: random.Random = None, mood: str = "") -> tuple:
    """★底句 ⇒ 说出口的样子★ ✓（返回 `(文本, 延迟秒)` ✓）

    ★为什么返回**两个**✗★：用户第 6 条"时序最后渲染"✗ ⇒
      文本与延迟**同一次调用**出来 ✓ 但延迟是**最后一步**算的 ✓
      ⇒ 调用方拿到就能"先说文本、再按延迟睡眠"✓ 不必自己拼一套计时 ✗
    """
    cfg = cfg or load()
    rng = rng or random.Random()
    t = str(line or "")
    t = _sub_word(t, cfg.get("词表") or {})
    t = clip(t, int(cfg.get("句长") or 0))
    t = maybe_emoji(t, float(cfg.get("emoji率") or 0), list(cfg.get("emoji") or []), rng)
    t = maybe_typo(t, float(cfg.get("错字率") or 0), dict(cfg.get("错字表") or {}), rng)
    return t, timing(t, cfg)
