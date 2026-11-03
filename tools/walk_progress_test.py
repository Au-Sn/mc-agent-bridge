#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""walk_progress_test.py -- after a timeout you can still ask "where did it get
to?" (S1..S4)

WHY (2026-09-29, round 27): `walk_route` blocks. A long walk takes minutes, and
if the caller (the brain, or MCP itself) times out, it is left with NOTHING --
so the only options were "guess" or "redo the whole walk". Now every hop writes
a heartbeat with the position it MEASURED (not one it predicted), plus a
timestamp so a stale heartbeat can never be mistaken for a walk in progress.

CRITERIA (declared BEFORE running):
  S4 offline : write -> read round trip; an OLD record must be reported as
               "long past" (never as "still walking").
  S1 heartbeat is true: while a walk runs in a child process, the heartbeat's
               position must agree with THIS SCRIPT's independent reads
               (>= 2 comparisons, each within 2 blocks).
  S2 survives a kill: killing the child mid-walk must leave a RECENT heartbeat
               whose phase is NOT "done" (i.e. it really was interrupted), and
               the reported position must match the world (<= 10 blocks, because
               the mod may still be finishing the hop the child asked for).
  S3 no stale lie: a heartbeat older than the freshness window must be reported
               as past, with the current position reported separately.

ASCII-only output.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import mc_mcp as M      # noqa: E402
import pathplan as PP   # noqa: E402

PROG = M.WALK_PROG_FILE


def say(s):
    print(s, flush=True)


def read_prog():
    try:
        return json.loads(PROG.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    ok = True

    # ---------------- S4 offline ------------------------------------------
    M._walk_prog("selftest", 7, (1.0, 2.0, 3.0), (9.0, 2.0, 9.0), "自测")
    rec = read_prog()
    s4a = (rec or {}).get("phase") == "selftest" and (rec or {}).get("pos") == [1.0, 2.0, 3.0]
    say("S4a write/read round trip: phase=%s pos=%s => %s"
        % ((rec or {}).get("phase"), (rec or {}).get("pos"), s4a))
    old = {"at": time.time() - 999, "when": "old", "phase": "hop", "step": 2,
           "pos": [1.0, 2.0, 3.0], "target": [9.0, 2.0, 9.0], "note": "old"}
    PROG.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    txt_old, _e = M.t_walk_progress(30)
    s4b = ("早就过去了" in txt_old) and ("还在走" not in txt_old.replace("别把它当成", ""))
    say("S4b stale record is reported as past => %s" % s4b)
    say("   " + (txt_old.splitlines()[-3] if len(txt_old.splitlines()) > 3 else txt_old)[:120])
    s4 = s4a and s4b
    ok &= s4

    # ---------------- live -------------------------------------------------
    p = M._pos_now()
    if not p:
        say("live part INCONCLUSIVE: no bot position")
        say("---- S1 / S2 / S3 / S4 = - / - / - / %s ----" % s4)
        return 0 if s4 else 1
    M.t_freeze(True)
    try:
        sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
        r, m, _b = M._route_map(sx, sz, sx + 8, sz, sy)
        L = M._stand_level(m, sx, sz, float(p[1]))
        # ★★挑目标要按**执行者的真实能力**挑★★ ✗（第 33 轮 ✓ 实测撞到 ✓）：
        #   现象 ✗：这个测试自己用**默认**规划器（`max_up=1` ✓）挑了 `(4111,72,14)` ✗
        #     —— 那是"**抬一级**"的格子 ✓ 而 `MOD_CLIMB_UP=0`（模组爬不上去 ✗）
        #     ⇒ 孩子的 `walk_route` **当场被拒** ✗ ⇒ 它根本没走 ✗ ⇒
        #       ★心跳当然什么都没有★ ✗ ⇒ S1/S2 红 ✗ —— 而**功能其实是对的** ✓
        #   ⇒ 口径 ✓：**测试挑目标时也要问"这条能力下走不走得到"** ✗
        #     （这样模组 v2.17 会跳一级之后 ✓ 这条判据**自动**跟着放开 ✓ 不用再改 ✓）
        pl = PP.Planner(m, level=L, blocked=M.BLOCKED_LV, avoid_edge=True,
                        max_up=M.MOD_CLIMB_UP)
        reg = pl.region(sx, sz)
        tg = [c for c in pl.safe_targets(sx, sz, 10.0, 18.0, reg, min_n=1)]
        if not tg:
            say("live part INCONCLUSIVE: no target 10..18 blocks away")
            return 0 if ok else 1
        (d, gx, gy, gz) = tg[0]
        say("child will walk to (%d,%d,%d) %.1f blocks away" % (gx, gy, gz, d))
        code = ("import sys;sys.path.insert(0,r%r);import mc_mcp as M;"
                "M.t_walk_route(%d,%d,%d,25000,2,None,4,'off')"
                % (str(ROOT / "tools"), gx, L, gz))
        child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                 errors="replace", cwd=str(ROOT))
        # --- S1: poll the heartbeat against independent reads ---------------
        agrees = 0
        tries = 0
        while tries < 24 and child.poll() is None:
            tries += 1
            time.sleep(1.2)
            rec = read_prog()
            if not rec or not rec.get("pos"):
                continue
            hp = rec["pos"]
            q = M._pos_now()
            if not q:
                continue
            dd = math.dist((hp[0], hp[2]), (q[0], q[2]))
            if rec.get("phase") in ("hop", "miss", "start") and dd <= 2.0:
                agrees += 1
            if agrees >= 2:
                break
        s1 = agrees >= 2
        say("S1 heartbeat is true: %d independent agreements (want >=2, within 2 blocks) => %s"
            % (agrees, s1))
        ok &= s1

        # --- S2: kill it mid-walk and see what is left ----------------------
        if child.poll() is None:
            child.kill()
            try:
                child.wait(timeout=10)
            except Exception:
                pass
            killed = True
        else:
            killed = False
        M.t_stop()                      # ★别让模组把这一跳跑完★ ✗（不然人还在动 ✓）
        time.sleep(1.0)
        rec = read_prog()
        q = M._pos_now()
        age = time.time() - float((rec or {}).get("at") or 0)
        phase = (rec or {}).get("phase")
        s2a = killed and rec and rec.get("pos") and (phase != "done") and (age <= 40)
        dd = None
        if rec and rec.get("pos") and q:
            dd = math.dist((rec["pos"][0], rec["pos"][2]), (q[0], q[2]))
        s2b = (dd is not None) and (dd <= 10.0)
        s2 = bool(s2a and s2b)
        say("S2 survives a kill: killed=%s phase=%s age=%.0fs (want !=done, <=40s) "
            "| heartbeat vs world = %s blocks (want <=10) => %s"
            % (killed, phase, age, None if dd is None else round(dd, 1), s2))
        ok &= s2

        # --- S3: the tool reports staleness honestly ------------------------
        txt, _e = M.t_walk_progress(1)          # 1 秒的新鲜窗 ⇒ 必然算陈旧 ✓
        s3 = ("早就过去了" in txt) and ("现在人在" in txt)
        say("S3 no stale lie: with a 1s freshness window the tool says it is past "
            "AND still reports where the bot is now => %s" % s3)
        ok &= s3
    finally:
        M.t_freeze(False)

    say("---- S1 / S2 / S3 / S4 = %s / %s / %s / %s ----" % (s1, s2, s3, s4))
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
