#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""freeze_test.py -- "freeze the world before touching it" (F1, F3, F4)

WHY (2026-09-29, round 23): the last full battery was 12/13 and the single
failure was a fake alarm: the tool's own reconciliation was right, but MY
before/after reads disagreed -- because between them the world kept moving
(the bot wanders on its own while `dshidle` is on, and other work may be
touching containers). Fixing that starts with being able to actually STOP the
bot, and with never stealing the user's setting in the process.

CRITERIA (declared BEFORE running):
  F1 frozen means frozen : after freeze(true), the bot must not move at all --
                           position identical across two reads 3 s apart.
  F3 restore, never steal: unfreeze must put the setting back the way it was;
                           if the original value is unknown it must NOT turn
                           wandering back on (no overreach).
  F4 offline state machine: freeze/unfreeze bookkeeping is idempotent -- the
                           remembered "was" value is captured once (freezing
                           twice must not overwrite it with "off"), and the
                           command sequence is idled-off then restored.

ASCII-only output.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M      # noqa: E402


def say(s):
    print(s, flush=True)


def main():
    ok = True

    # ---------------- F4 offline (stub the channel) -----------------------
    calls = []
    orig = M.dsh

    def fake(cmd, tmo=60.0):
        calls.append(cmd)
        if cmd.startswith("dshdigest"):
            return "dshdigest name=Bot pos=1.0,2.0,3.0 onground=true idle=on"
        return "dshidle humanoid=false radius=4"

    M.dsh = fake
    try:
        M._FROZEN["was"] = None
        M.t_freeze(True)
        first_was = M._FROZEN["was"]
        M.t_freeze(True)                       # 幂等：不许把 "off" 记成原值 ✗
        second_was = M._FROZEN["was"]
        off_calls = len([c for c in calls if c.startswith("dshidle off")])
        f4a = (first_was == "on") and (second_was == "on") and off_calls == 2
        say("F4a idempotent: was=%r kept=%r  idle-off sent %d times => %s"
            % (first_was, second_was, off_calls, f4a))
        calls.clear()
        M.t_freeze(False)
        restored = [c for c in calls if c.startswith("dshidle")]
        f4b = restored == ["dshidle on"]       # 原值是 on ⇒ 必须还它 on ✓
        say("F4b restore: after unfreeze the commands were %s (want ['dshidle on']) => %s"
            % (restored, f4b))
        # 原值未知 ⇒ 不许越权打开 ✗
        calls.clear()
        M._FROZEN["was"] = "unknown"
        M.t_freeze(False)
        f4c = not [c for c in calls if c.startswith("dshidle")]
        say("F4c no overreach: with was=unknown the commands were %s (want none) => %s"
            % (calls, f4c))
        f4 = f4a and f4b and f4c
    finally:
        M.dsh = orig
        M._FROZEN["was"] = None
    ok &= f4

    # ---------------- F1 / F3 live ----------------------------------------
    p = M._pos_now()
    if not p:
        say("F1/F3 INCONCLUSIVE: no bot position (game not running?)")
        say("---- F1 / F3 / F4 = - / - / %s ----" % f4)
        say("=> %s" % ("PASS (offline only)" if f4 else "FAIL"))
        return 0 if f4 else 1
    txt, err = M.t_freeze(True)
    say("freeze: err=%s | %s" % (err, (txt or "").splitlines()[0][:90]))
    a = M._pos_now()
    time.sleep(3.0)
    b = M._pos_now()
    moved = ((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5 if (a and b) else 99.0
    f1 = (moved <= 0.02) and ("★冻结★" in (txt or ""))
    say("F1 frozen means frozen: moved %.3f blocks over 3 s (want <=0.02) => %s"
        % (moved, f1))
    ok &= f1

    txt2, err2 = M.t_freeze(False)
    f3 = ("★解冻★" in (txt2 or "")) and (M._pos_now() is not None)
    say("F3 restore: err=%s | %s => %s" % (err2, (txt2 or "").splitlines()[0][:90], f3))
    ok &= f3

    say("---- F1 / F3 / F4 = %s / %s / %s ----" % (f1, f3, f4))
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
