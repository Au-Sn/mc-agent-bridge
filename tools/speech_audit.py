#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_audit.py -- ★语言错题环：回放它说过的话 ＋ 禁掉不对味的那句★（2026-09-30 ✓ 用户第 5 条 ✓）

## 用户原话要点 ✗
  「意图对象 `{类型, 载荷, 对象, 情绪快照}` ⇒ 让"**为什么说了这句话**"**可审计**✗
   ＋ 一个**语言错题环**✗」
  ⇒ 两个动作 ✓：**看**（`--tail` ✓）＋ **改**（`--bad` ✓）

## 用法 ✓
  · `py tools\\speech_audit.py --tail 20`         看最近 20 条（含"想说但没说"的 ✓）
  · `py tools\\speech_audit.py --denied`          只看**被拦下**的 ＋ 为什么 ✗（调闸门用 ✓）
  · `py tools\\speech_audit.py --bad "<整句>" --why "太油了 ✗"`   禁掉这一句 ✓
  · `py tools\\speech_audit.py --list`            看现在禁了哪些 ✓
  · `py tools\\speech_audit.py --unban "<整句>"`  放回来 ✓（也要写进错题本 ✓）
  · `py tools\\speech_audit.py --coverage`        看每类还剩多少句 ✓（★禁多了会掏空某一类✗★）

## 三条规矩 ✗
  ① ★**禁是"整句精确匹配"**✗★（绝不子串 ✗ P105/P107 ✓）
  ② ★**禁必须留痕**✗★ ⇒ 同时追加一行到 `docs/语言错题本.md` ✓（**只增不减** ✓）
     并且**不删库里的句子**✗ —— 库照旧 ✓ 只是被过滤掉 ✓（导入重放也不会把它带回来 ✓）
  ③ ★**禁完要报覆盖**✗★ ⇒ 某一类被禁空 ⇒ 大声报出来 ✓
     （否则表现是"它忽然对这类事一声不吭"✗ 而你不知道为什么 ✓）
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import corpus as C      # noqa: E402

LOG = ROOT / "logs" / "speech_log.jsonl"
BOOK = ROOT / "docs" / "语言错题本.md"
BAN = C.DEFAULT_BAN
HEAD = """# 语言错题本（★它说过／想说但不对味的句子✗★）

> ★这不是"禁词表"而是**账**✗★：每一条都写清 **哪句／为什么／什么时候** ✓
> 禁用的句子进 `personas/dafeiyu.banned.txt` ✓（**整句精确匹配** ✓ 绝不子串 ✓）
> ★库里那句**不删**✗★ —— 删了下次导入又回来 ✓ 而且没人知道少过一句 ✓
> 生成 ✓：`py tools\\speech_audit.py --bad "<整句>" --why "<为什么>"` ✓

| 时间 | 句子 | 为什么 | 来源 |
| --- | --- | --- | --- |
"""


def tail(n: int = 20, only_denied: bool = False) -> list:
    """★回放最近 N 条★ ✓（★**被拦下的也读**✗★ —— "为什么没说"和"为什么说了"一样重要 ✓）"""
    if not LOG.is_file():
        return []
    rows = []
    for ln in LOG.read_text(encoding="utf-8").splitlines()[-max(1, n * 4):]:
        try:
            r = json.loads(ln)
        except Exception as e:
            # 记录：回放时丢一行 ⇒ "被拦下的"可能看不见（审计链不许静默断）
            print("[记录] 审计行读不了（回放少一行）：%s" % type(e).__name__,
                  file=sys.stderr)
            continue
        if only_denied and not r.get("deny"):
            continue
        rows.append(r)
    return rows[-n:]


def fmt(r: dict) -> str:
    tag = "说 ✓" if r.get("line") else "**没说** ✗"
    why = r.get("why") or ""
    extra = (" ｜ 拦住：%s" % r["deny"]) if r.get("deny") else ""
    return ("%s [%s] %s ｜ 语气 %s ｜ 出处 %s%s\n        why=%s\n        %s"
            % (r.get("at", "?"), r.get("kind", "?"), tag, r.get("mood", "?"),
               r.get("source", "?"), extra, why, r.get("line") or "（没有台词 ✓）"))


def ban_line(line: str, why: str, source: str = "手写") -> tuple:
    """★禁掉一整句 ＋ 记一笔账★ ✓（返回 `(成没成, 说明)` ✓）

    ★★两边都要归一化✗★★（P136 ✓ 判据 Q5 当场抓到 ✓）：
      ✗ 库里那句**出库时被 `strip_marks` 剥过** ✓ 而这里拿**用户原样打的**那句去比 ✗
        ⇒ 带 `✓✗★` 的那一版**永远匹配不上** ✗ ⇒ ★"禁了却没生效、还不报错"✗★（最阴 ✓）
      ⇒ 口径 ✓：**进名单前先剥** ✓（账本那一行**保留原文** ✓ 人看着方便 ✓）
    """
    raw = str(line or "").strip()
    s = C.strip_marks(raw)
    if not s:
        return False, "空句子 ✗"
    w = str(why or "").strip()
    if not w:
        return False, "★禁它也得给理由 ✗★（不然半年后没人知道为什么少了一句 ✓）"
    cur = C.banned(BAN)
    if s in cur:
        return False, "已经在名单里了 ✓（没有重复记一笔 ✗）"
    BAN.parent.mkdir(parents=True, exist_ok=True)
    with BAN.open("a", encoding="utf-8") as f:
        f.write(s + "\n")
    if not BOOK.is_file():
        BOOK.parent.mkdir(parents=True, exist_ok=True)
        BOOK.write_text(HEAD, encoding="utf-8")
    with BOOK.open("a", encoding="utf-8") as f:
        f.write("| %s | %s | %s | %s |\n"
                % (time.strftime("%Y-%m-%d %H:%M"), raw.replace("|", "/"), w.replace("|", "/"),
                   source))
    return True, "已禁 ✓（★库里的原句没删 ✗★ 只是读的时候被滤掉 ✓）"


def unban_line(line: str, why: str) -> tuple:
    """★放回来（也要写账 ✓）★ —— ★同样先归一化✗★（不然找不到名单里那条 ✓）"""
    raw = str(line or "").strip()
    s = C.strip_marks(raw)
    if s not in C.banned(BAN):
        return False, "它本来就不在名单里 ✓"
    keep = [x for x in BAN.read_text(encoding="utf-8").splitlines() if x.strip() != s]
    BAN.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    with BOOK.open("a", encoding="utf-8") as f:
        f.write("| %s | %s | ★放回来了 ✗★ %s | 手写 |\n"
                % (time.strftime("%Y-%m-%d %H:%M"), s.replace("|", "/"), why or ""))
    return True, "已放回 ✓"


def coverage() -> dict:
    """★禁完之后每类还剩几句✗★ ✓（★被禁空的类 ⇒ 会"忽然一声不吭"✗ 必须报出来 ✓）★"""
    raw = C.parse_lines_text(C.DEFAULT.read_text(encoding="utf-8")) if C.DEFAULT.is_file() else {}
    now = C.load()
    out = {}
    for k in raw:
        if k == "__loose__":
            continue
        a, b = len(raw[k]), len(now.get(k) or [])
        if a != b:
            out[k] = (a, b)
    return out


def main(argv: list) -> int:
    a = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            a[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            a[argv[i][2:]] = True
            i += 1
    if "bad" in a:
        okk, why = ban_line(a["bad"], a.get("why") or "", a.get("source") or "手写")
        print(("✓ " if okk else "✗ ") + why)
        cov = coverage()
        if cov:
            print("  受影响的小节（原本 → 现在）：%s" % cov)
        return 0 if okk else 1
    if "unban" in a:
        okk, why = unban_line(a["unban"], a.get("why") or "")
        print(("✓ " if okk else "✗ ") + why)
        return 0 if okk else 1
    if "list" in a:
        b = sorted(C.banned(BAN))
        print("禁了 %d 句 ✓" % len(b))
        for s in b:
            print("  - %s" % s)
        return 0
    if "coverage" in a:
        cov = coverage()
        print("被过滤的小节：%s" % (cov or "无 ✓"))
        c = C.coverage(C.load())
        print("还剩：%s ｜ 空的（允许 ✗）：%s" % (c["n"], c["empty"]))
        return 0
    rows = tail(int(a.get("tail") or 20), only_denied=bool(a.get("denied")))
    print("== 最近 %d 条（★含「没说」的✗★）== " % len(rows))
    for r in rows:
        print(fmt(r))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
