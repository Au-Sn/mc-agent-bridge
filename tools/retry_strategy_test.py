#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""retry_strategy_test.py -- attempts must differ; a repeated refusal must stop the loop

MEASURED (sec 79.471): the same start + same model + deterministic A* produced the SAME
bad plan three times, so all three attempts died identically. That is not robustness.

FIX (sec 79.474): attempt 1 plans with scaffolding, attempt 2 without (a genuinely
different search space). If the exit validator refuses (walk_unreachable /
place_unperformable / place_on_body) and the second strategy also refuses, stop -- a
third identical try cannot help.

CHECKS (offline: _execute_once is stubbed)
  S1 a refusal on both strategies => exactly 2 attempts, strategies differ, honest reason
  S2 if attempt 2 succeeds, execute() reports success
  S3 a normal do_fail still uses all 3 attempts (the state may have changed)
  S4 every attempt records which strategy it used
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

import exec3d as E3           # noqa: E402

GOAL = (4107, 71, 19)


def with_stub(fn):
    """Temporarily replace _execute_once, restoring it afterwards."""
    def deco(f):
        def inner():
            orig = E3._execute_once
            E3._execute_once = fn
            try:
                return f()
            finally:
                E3._execute_once = orig
        return inner
    return deco


def main() -> int:
    checks = []

    # S1: always refuse
    calls = []

    def refuse(goal, dry=False, max_steps=400, restore=False, pause=0.0, allow_scaffold=True):
        calls.append(allow_scaffold)
        return False, {"reason": "walk_unreachable", "bad": ["walk_target_not_standable@1,2,3"]}

    @with_stub(refuse)
    def s1():
        return E3.execute(GOAL)
    ok1, rep1 = s1()
    checks.append(("S1 两种策略都拒 ⇒ 只试 2 次", len(calls) == 2, "attempts=%d" % len(calls)))
    checks.append(("S1b 两次策略不同", calls == [True, False], "strategies=%s" % (calls,)))
    checks.append(("S1c 如实返回失败原因", (not ok1) and rep1.get("reason") == "walk_unreachable",
                   "ok=%s reason=%s" % (ok1, rep1.get("reason"))))

    # S2: second attempt succeeds
    seq = []

    def second_ok(goal, dry=False, max_steps=400, restore=False, pause=0.0, allow_scaffold=True):
        seq.append(allow_scaffold)
        if len(seq) == 1:
            return False, {"reason": "walk_unreachable"}
        return True, {"reason": None, "arrived": True, "end": GOAL}

    @with_stub(second_ok)
    def s2():
        return E3.execute(GOAL)
    ok2, rep2 = s2()
    checks.append(("S2 第二次成功 ⇒ 报成功", ok2 and rep2.get("arrived") is True,
                   "ok=%s arrived=%s" % (ok2, rep2.get("arrived"))))

    # S3: a normal do_fail uses all attempts
    seq3 = []

    def plain_fail(goal, dry=False, max_steps=400, restore=False, pause=0.0, allow_scaffold=True):
        seq3.append(allow_scaffold)
        return False, {"reason": "do_fail", "bad": ["do_fail:why=walk_timeout@1,2,3"]}

    @with_stub(plain_fail)
    def s3():
        return E3.execute(GOAL)
    ok3, rep3 = s3()
    checks.append(("S3 普通 do_fail ⇒ 用满 3 次", len(seq3) == E3.MAX_ATTEMPTS,
                   "attempts=%d max=%d" % (len(seq3), E3.MAX_ATTEMPTS)))

    # S4: attempts record the strategy
    atts = rep3.get("attempts") or []
    checks.append(("S4 attempts 里记了策略", bool(atts) and all("allow_scaffold" in a for a in atts),
                   str([a.get("allow_scaffold") for a in atts])))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => retry_strategy FAIL (%d)" % bad)
        print("RETRYSTRAT ok=0 bad=%d" % bad)
        return 1
    print("  => retry_strategy PASS (attempts differ; repeated refusal stops honestly)")
    print("RETRYSTRAT ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
