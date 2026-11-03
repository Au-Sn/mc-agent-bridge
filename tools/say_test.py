#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""say_test.py -- 模块 F 自述层的判据

规格（§2.3 / §6.1 / §19）：
  * 回执必须带**有限集**里的机器码（★CC 控制台只认 ASCII ✗ 中文只能是附属✗★）
  * 有后果的事件要留痕（★无意义动作**不需要**理由 ⇒ 不许乱记✗★）
  * 一条任务只该有 **2 条**消息（开始＋结束）

CHECKS
  S1 已知码 ⇒ 原样输出 + 回执里有 reason=<码>
  S2 带坐标 ⇒ 回执里有 at=x,y,z
  S3 ★自造码 ⇒ 降级 unknown ＋ 明确标出降级✗★（不许静默通过）
  S4 留痕：say(log=True) 必须往理由日志写一条（★N8' 靠它✗★）
  S5 ★log=False 不写✗★（无意义动作用的）
  S6 全部机器码都是**纯 ASCII**（★CC 才能显示✗★）
  S7 一条任务只发 2 条：start ＋ done（★判据形式✗★）
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import say as S            # noqa: E402
import reasons as R        # noqa: E402


def main() -> int:
    checks = []

    # S1 已知码
    rec = S.say("no_path", at=(4100, 71, 5), log=False)
    checks.append(("S1 已知码原样输出", rec["code"] == "no_path" and rec["known"]
                   and "reason=no_path" in rec["text"], rec["text"]))

    # S2 坐标
    ok2 = "at=4100,71,5" in rec["text"]
    checks.append(("S2 回执带 at=x,y,z", ok2, rec["text"]))

    # S3 自造码降级
    bad = S.say("totally_made_up_code", log=False)
    checks.append(("S3 自造码降级为 unknown 并标出",
                   bad["code"] == "unknown" and bad.get("downgraded") is True
                   and "reason=unknown" in bad["text"],
                   bad["text"]))

    # S4/S5 留痕开关（用临时目录，不碰真日志）
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        old_dir = R.LOGDIR
        R.LOGDIR = d
        try:
            r1 = S.say("no_dig_zone", at=(4120, 72, 25), mission="m-test",
                       detail="命中家", log=True, important=True)
            n1 = len(R.load(days=1))
            r2 = S.say("blocked", log=False)
            n2 = len(R.load(days=1))
        finally:
            R.LOGDIR = old_dir
    checks.append(("S4 留痕：log=True 写了一条", r1.get("logged") is True and n1 == 1,
                   "logged=%s 条数=%d" % (r1.get("logged"), n1)))
    checks.append(("S5 log=False 不写", r2.get("logged") is None and n2 == 1,
                   "条数仍为 %d" % n2))

    # S6 机器码纯 ASCII
    non_ascii = [c for c in S.CODES if not c.isascii()]
    checks.append(("S6 机器码全是纯 ASCII", not non_ascii, str(non_ascii[:4])))

    # S7 一条任务只 2 条
    start = S.say("start", mission="m7", log=False)
    done = S.say("done", at=(4122, 71, 8), mission="m7", log=False)
    msgs = [start["text"], done["text"]]
    checks.append(("S7 一条任务只发 2 条（start ＋ done）",
                   len(msgs) == 2 and "reason=start" in msgs[0] and "reason=done" in msgs[1],
                   " ｜ ".join(m[:46] for m in msgs)))

    badn = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            badn += 1
    print("  ---- %d/%d ----" % (len(checks) - badn, len(checks)))
    if badn:
        print("  => say FAIL (%d)" % badn)
        print("SAY ok=0 bad=%d" % badn)
        return 1
    print("  => say PASS (finite ASCII codes, unknown downgraded loudly, logs only when asked)")
    print("SAY ok=1 checks=%d codes=%d" % (len(checks), len(S.CODES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
