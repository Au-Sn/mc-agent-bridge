#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_audit_test.py -- ★语言错题环的判据（Q1~Q6 ✓ 全离线 ✓ 用临时文件 ✓ 秒级 ✓）★

WHY（用户第 5 条 ✓）："语言错题环"要成立，必须同时**看得到**（审计 ✓）和**改得动**（禁用 ✓）
  ⇒ 而"改"这件事最容易出的错是**改得没痕迹**✗（半年后没人知道为什么少了一句 ✓ P129 同族 ✓）

CRITERIA（跑之前先写 ✓ 全部在临时目录里做 ✓ 不碰真台词库/真错题本 ✗）
  Q1 看得到   ：审计回放能读出 `kind/why/source/line` ✓ ★含"想说但没说"的（有 `deny`）✗★
  Q2 禁要理由 ：`--bad` 不给 `--why` ⇒ **拒绝** ✗（不许悄悄禁 ✓）
  Q3 禁是精确 ：只禁**那一整句** ✓ 同节里**别的句子照常能抽到** ✓（绝不子串 ✗ P105/P107 ✓）
  Q4 禁要留痕 ：`docs/语言错题本.md`（这里是临时本 ✓）追加一行 ✓ ★而库里的原句**一个字都没删**✗★
  Q5 重复不记 ：同一句禁两次 ⇒ 第二次**拒绝** ✓（账本不许灌水 ✓）
  Q6 禁空要报 ：把某一节**全部**禁掉 ⇒ 覆盖账（`--coverage`）**必须**报出那一节 ✗
"""
from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import corpus as C          # noqa: E402
import speech as S          # noqa: E402
import speech_audit as A    # noqa: E402


def say(s):
    print(s, flush=True)


def main() -> int:
    ok = True
    d = Path(tempfile.mkdtemp(prefix="audit_"))
    # ★全部搬到临时目录 ✗★（不碰真库 ✓ 不碰真错题本 ✓）
    #   ⚠ fixture 里**故意留** `✗`（禁名单那条 ✓ 要验"名单也归一化"✗ P136 ✓）；
    #     而 `播报/干活` 那条**不带标记** ✗ —— 它出库时不带 ✓ 比较时才对得上 ✓
    lib = d / "p.lines.txt"
    lib.write_text("## 反应/受伤\n- 疼 ✗ 掉了 {delta} 点血\n- 哎！谁打我 ✗\n"
                   "## 播报/干活\n- 先把活做完\n", encoding="utf-8")
    A.BAN = d / "p.banned.txt"
    A.BOOK = d / "语言错题本.md"
    A.LOG = d / "speech_log.jsonl"
    A.LOG.write_text(
        '{"at":"2026-09-30 02:00:00","kind":"反应","why":"游戏事件 damage","who":"",'
        '"mood":"标准","rel":"陌生人","payload":{"hp":7.0},"source":"corpus:反应/受伤",'
        '"line":"疼 ✗ 掉了 -4.0 点血","delay_s":1.2,"deny":""}\n'
        '{"at":"2026-09-30 02:00:05","kind":"邀功","why":"游戏事件 xp","who":"",'
        '"mood":"标准","rel":"陌生人","payload":{"level":9},"source":"llm","line":"",'
        '"delay_s":0.0,"deny":"库里没有 `邀功` 这一类的句子 ✗"}\n', encoding="utf-8")

    # ---- Q1：看得到（含"没说"的）----
    rows = A.tail(10)
    rows_d = A.tail(10, only_denied=True)
    txt = "\n".join(A.fmt(r) for r in rows)
    q1 = (len(rows) == 2) and (len(rows_d) == 1) and ("why=" in txt) and ("**没说**" in txt) \
        and ("拦住" in txt)
    say("Q1 看得到：读到 %d 条 ｜ 只看被拦 %d 条 ｜ 文本里有 why/没说/拦住=%s => %s"
        % (len(rows), len(rows_d), ("why=" in txt and "**没说**" in txt and "拦住" in txt), q1))
    ok &= q1

    # ---- Q2：禁要理由 ----
    bad_no_why, why_no = A.ban_line("哎！谁打我 ✗", "")
    q2 = (not bad_no_why) and ("理由" in why_no) and (not A.BAN.exists())
    say("Q2 禁要理由：不给理由 ⇒ %s（%s）｜ 名单文件**没被创建**=%s => %s"
        % (bad_no_why, why_no[:20], not A.BAN.exists(), q2))
    ok &= q2

    # ---- Q3/Q4/Q5：禁是精确 ＋ 留痕 ＋ 不重复 ----
    okk, why_okk = A.ban_line("哎！谁打我 ✗", "太油了 ✗", "试")
    lib_after = lib.read_text(encoding="utf-8")
    loaded = C.load(lib, A.BAN)
    again, why_again = A.ban_line("哎！谁打我 ✗", "再来一次")
    # ★禁了那一句 ⇒ 同节别的句子照样抽得到 ✓；而且被禁的**绝不会**被抽出来 ✓
    hits = set()
    for _ in range(40):
        line, _src = S.render(S.Intent("反应", "t", {"why_key": "受伤", "delta": -4.0}),
                              loaded)
        hits.add(line)
    # ★★期望值也要**过一遍归一化**✗★★（P136 ✓）：库里的句子出库时标记被剥 ✓
    #   ⇒ 判据里写的"原句"必须**同样剥过** ✗ 不然就是拿两个口径比 ✓（本项目最恨的那种 ✓）
    leftover = C.strip_marks("疼 ✗ 掉了 {delta} 点血").replace("{delta}", "-4.0")
    banned_raw = "哎！谁打我 ✗"
    banned_norm = C.strip_marks(banned_raw)
    q3 = okk and (hits == {leftover}) and ("谁打我" not in "".join(hits))
    say("Q3 禁是精确：抽 40 次拿到 %s（被禁那句**一次都没出现** ✓）=> %s" % (hits, q3))
    ok &= q3

    book = A.BOOK.read_text(encoding="utf-8") if A.BOOK.is_file() else ""
    q4 = ("太油了 ✗" in book) and (banned_raw in book) and (banned_raw in lib_after) \
        and (A.BAN.read_text(encoding="utf-8").strip() == banned_norm)
    say("Q4 禁要留痕：账本里有这一行=%s ｜ ★库里的原句**还在**=%s★ ｜ 名单%r（★存的是**剥过的**✓★）=> %s"
        % ("太油了 ✗" in book, banned_raw in lib_after,
           A.BAN.read_text(encoding="utf-8").strip(), q4))
    ok &= q4

    q5 = (not again) and ("已经在名单里" in why_again) \
        and (A.BOOK.read_text(encoding="utf-8").count("| 哎！谁打我 ✗ |") == 1)
    say("Q5 重复不记：第二次 ⇒ %s（%s）｜ 账本里只有 1 行=%s => %s"
        % (again, why_again[:14], A.BOOK.read_text(encoding="utf-8").count("| 哎！谁打我 ✗ |") == 1,
           q5))
    ok &= q5

    # ---- Q6：禁空要报 ----
    A.ban_line("疼 ✗ 掉了 {delta} 点血", "这句也油 ✗")
    # ★`speech_audit.coverage()` 走的是**真库路径**✗★ ⇒ 这里照它的同一段逻辑、
    #   换成临时库跑一遍 ✓（★口径一样 ✗ 换的只是路径 ✓★）
    raw = C.parse_lines_text(lib.read_text(encoding="utf-8"))
    nowc = C.load(lib, A.BAN)
    cov = {k: (len(raw[k]), len(nowc.get(k) or [])) for k in raw
           if k != "__loose__" and len(raw[k]) != len(nowc.get(k) or [])}
    q6 = (cov == {"反应/受伤": (2, 0)}) and (nowc.get("播报/干活") == ["先把活做完"])
    say("Q6 禁空要报：受影响的小节 %s（该报出被禁空的那一节 ✓）｜ 别的小节没事=%s => %s"
        % (cov, nowc.get("播报/干活") == ["先把活做完"], q6))
    ok &= q6

    say("---- Q1..Q6 = %s ----" % ok)
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
