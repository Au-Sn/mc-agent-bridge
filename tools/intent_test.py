#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intent_test.py -- 模块 L1 意图判别的判据（★离线 ✗ 20 句混合测试集✗★）

用户口径（规格 §10.3 / L-a~L-f）：
  「对话的需要判断哪些需要去执行 ✗ 哪些是聊天」
  ★chat／query 绝不许动世界**（L-a／L-b）✗★
  ★`task` 必须落到 `jobs/`**（L-c）✗★
  ★`mixed` 必须拆成"一句回复 ＋ 一条 job"**（L-d）✗★
  ★混合 20 句判别 100%**（L-e）✗★

CHECKS
  I1 20 句测试集判别 **全对**（★逐条打印错误✗★）
  I2 ★分类器是**纯文本**的 ⇒ 一次 dsh 都不发★（用计数器证明 0 往返）
  I3 chat／query 的 `need_exec` 必须是 False（★不许让闲聊触发执行✗★）
  I4 task／mixed 的 `need_exec` 必须是 True（★不许漏掉要干活的✗★）
  I5 mixed 必须能拆出 chat_part 与 task_part 两段
  I6 空话 ⇒ chat（★默认不动手✗★）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import intent as I          # noqa: E402

# ★混合测试集（★chat 8 ／ query 4 ／ task 6 ／ mixed 2✗★）
CASES = [
    # chat
    ("你好呀", "chat"),
    ("在吗", "chat"),
    ("谢谢，辛苦了", "chat"),
    ("哈哈你真好玩", "chat"),
    ("你叫什么名字", "chat"),
    ("你觉得这个整合包好玩吗", "chat"),
    ("晚上好", "chat"),
    ("嗯，明白了", "chat"),
    # query
    ("你现在在哪", "query"),
    ("背包里有什么", "query"),
    ("现在几点了", "query"),
    ("附近有箱子吗", "query"),
    # task
    ("去把门关上", "task"),
    ("帮我挖三个铁矿", "task"),
    ("把箱子里的东西存好", "task"),
    ("去砍两棵树", "task"),
    ("回到家里", "task"),
    ("把这块地铺平", "task"),
    # mixed
    ("你好啊，顺便去把门关上", "mixed"),
    ("谢谢！然后去砍两棵树", "mixed"),
]


def main() -> int:
    checks = []

    # I1 20 句全对
    wrong = []
    for text, want in CASES:
        got = I.classify(text)["intent"]
        if got != want:
            wrong.append((text, want, got))
    checks.append(("I1 20 句测试集全对", not wrong,
                   "%d/%d 对 ｜ 错的 %s" % (len(CASES) - len(wrong), len(CASES), wrong[:3])))

    # I2 纯文本 ⇒ 零往返（用 import 检查：模块里不许 import mcp_core）
    src = (ROOT / "tools" / "intent.py").read_text(encoding="utf-8")
    no_net = ("mcp_core" not in src) and ("agent_gateway" not in src) and (".dsh(" not in src)
    checks.append(("I2 ★分类器纯文本 ✗ 零往返★", no_net,
                   "含 mcp_core=%s" % ("mcp_core" in src)))

    # I3 chat/query 不许触发执行
    bad3 = [(t, r["need_exec"]) for t, want in CASES if want in ("chat", "query")
            for r in [I.classify(t)] if r["need_exec"]]
    checks.append(("I3 chat/query 的 need_exec 必须 False", not bad3, str(bad3[:3])))

    # I4 task/mixed 必须 need_exec
    bad4 = [(t, r["need_exec"]) for t, want in CASES if want in ("task", "mixed")
            for r in [I.classify(t)] if not r["need_exec"]]
    checks.append(("I4 task/mixed 的 need_exec 必须 True", not bad4, str(bad4[:3])))

    # I5 mixed 要能拆两段
    bad5 = []
    for t, want in CASES:
        if want != "mixed":
            continue
        r = I.classify(t)
        if not (r.get("chat_part") and r.get("task_part")):
            bad5.append((t, r.get("chat_part"), r.get("task_part")))
    checks.append(("I5 mixed 能拆成 chat_part ＋ task_part", not bad5, str(bad5[:2])))

    # I6 空话 ⇒ chat
    r6 = I.classify("")
    checks.append(("I6 空话 ⇒ chat（默认不动手）",
                   r6["intent"] == "chat" and r6["need_exec"] is False, r6["why"][:50]))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:120]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => intent FAIL (%d)" % bad)
        print("INTENT ok=0 bad=%d" % bad)
        return 1
    print("  => intent PASS (20/20, pure text = zero round trips, chat never triggers execution)")
    print("INTENT ok=1 checks=%d cases=%d" % (len(checks), len(CASES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
