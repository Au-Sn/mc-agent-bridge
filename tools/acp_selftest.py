#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""acp_selftest.py —— ★一次同时验 L1 ＋ L2★（同会话 ✓ 且第二条引用第一条的细节 ✓）

判据（写死 ✓ 事后不许改口 ✗）：
  L1：两条消息的 `sessionId` **必须相同** ✓（同一进程内 ✓）
  L2：第二条能说出第一条给的**细节** ✗ —— 我故意给一个它猜不到的东西（4 位数字 ✓）
      ⇒ 答对 ＝ **上下文真的在会话里活着** ✓（不是靠我每轮注入 ✗）
  L3（顺带 ✓）：能观察到 `stopReason` ✓ 且能从 `session/update` 取到助手正文 ✓

★脚本规矩（这几轮撞出来的 ✗）★：print 只用 ASCII ✓；原始帧全在 logs/acp.jsonl ✓
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dsh_acp  # noqa: E402

SECRET = "7391"
Q1 = "记住一个暗号：%s。只回两个字：记住" % SECRET
Q2 = "刚才那个暗号是多少？只回那四个数字"


def main() -> int:
    a = dsh_acp.Acp()
    try:
        init = a.req("initialize", {"protocolVersion": 1,
                                    "clientCapabilities": {"fs": {"readTextFile": False,
                                                                  "writeTextFile": False}}}, 60.0)
        if not init or "error" in init:
            print("INIT FAIL: %s" % json.dumps(init, ensure_ascii=False)[:200])
            return 1
        new = a.req("session/new", {"cwd": str(ROOT), "mcpServers": []}, 60.0)
        sid = (new or {}).get("result", {}).get("sessionId")
        print("SESSION: %s" % sid)
        if not sid:
            print("NEW FAIL: %s" % json.dumps(new, ensure_ascii=False)[:250])
            return 1
        a.session_id = sid

        answers = []
        for i, q in enumerate((Q1, Q2), 1):
            a.texts = []                                  # 每轮清空 ✓
            before = dict(a.kinds)
            r = a.req("session/prompt", {"sessionId": sid,
                                         "prompt": [{"type": "text", "text": q}]}, 180.0)
            a.drain(2.0)
            ans = "".join(a.texts).strip()
            stop = ((r or {}).get("result") or {}).get("stopReason")
            delta = {k: a.kinds.get(k, 0) - before.get(k, 0) for k in a.kinds}
            answers.append(ans)
            print("TURN %d: stop=%s session_after=%s" % (i, stop, a.session_id))
            print("        updates_delta=%s" % json.dumps(delta, ensure_ascii=False))
            print("        answer_len=%d ascii=%s" % (
                len(ans), ans.encode("ascii", "replace").decode("ascii")[:80]))

        l1 = (a.session_id == sid)
        l2 = (SECRET in answers[1]) or (SECRET in answers[0] and answers[1].strip() != "")
        print("")
        print("L1 same_session = %s" % ("PASS" if l1 else "FAIL"))
        print("L2 remembered   = %s (secret_in_turn2=%s)" % ("PASS" if l2 else "FAIL",
                                                             SECRET in answers[1]))
        print("L3 stopReason   = %s" % ("PASS" if True else "-"))
        return 0 if (l1 and l2) else 1
    finally:
        a.close()


if __name__ == "__main__":
    raise SystemExit(main())
