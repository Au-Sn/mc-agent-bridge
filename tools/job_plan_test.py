#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""job_plan_test.py -- a job can now carry a STEP LIST that survives sessions (W1..W5)

WHY (2026-09-29, round 22): the ledger only had a free-text `next`. A multi-step
job ("fetch 8 gravel -> sift -> put the output back") therefore could not be
registered: after a restart I had no way to know which step I was on, except by
re-reading the chat. This round adds a plan:

    job_plan(job_id, "step | how to tell it is done\n...")   -> stored in the job
    job_next(job_id)                                        -> first unfinished step
    job_step(..., plan_i=N, evidence=<world truth>)          -> marks that step done

A step may only be marked done WITH evidence: "I say I finished" is exactly the
disease this project keeps re-learning (P105 "moved the wrong item silently",
P106 "two definitions of walkable").

CRITERIA (declared BEFORE running; all offline, no game needed):
  W1 plan saved   : after job_plan, the on-disk job has N steps, each with `do`
                    and (when written) `judge`.
  W2 order stable : job_next returns the FIRST unfinished step and gives the
                    same answer twice in a row.
  W3 evidence     : job_step(plan_i=k, evidence=...) marks k done and job_next
                    moves on to k+1 -- it must not keep asking for k.
  W4 cross-process: a SEPARATE python process reading the same job sees the same
                    progress (that is the whole point of a ledger).
  W5 no faking    : marking a step done WITHOUT evidence is refused, and an
                    out-of-range index raises -- neither may silently mark
                    anything.

ASCII-only output.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import jobs_store as JS   # noqa: E402
import mc_mcp as M        # noqa: E402

SPEC = "\n".join([
    "去箱子取 8 个沙砾｜背包里 gravel >= 8（世界真值）",
    "到筛子前筛 8 下｜筛子产出增加 或 背包 items 增加",
    "把产出存回箱子｜容器读数对得上",
])


def say(s):
    print(s, flush=True)


def main():
    ok = True
    j = JS.open_job("自测：批量作业编排（可删）", "先写计划")
    jid = j["id"]
    say("opened job %s" % jid)

    # --- W1 plan saved ----------------------------------------------------
    try:
        M.t_job_plan(jid, SPEC)
    except Exception as e:
        say("W1 FAIL: job_plan raised %s: %s" % (type(e).__name__, e))
        return 1
    on_disk = json.loads((ROOT / "jobs" / (jid + ".json")).read_text(encoding="utf-8"))
    its = on_disk.get("plan") or []
    w1 = (len(its) == 3) and all(it.get("do") for it in its) and bool(its[0].get("judge"))
    say("W1 plan saved: steps=%d  first_do=%r  first_judge=%r => %s"
        % (len(its), (its[0].get("do") if its else None),
           (its[0].get("judge") if its else None), w1))
    ok &= w1

    # --- W2 order stable --------------------------------------------------
    a = JS.next_plan_step(JS.load(jid))
    b = JS.next_plan_step(JS.load(jid))
    w2 = (a and b and a["i"] == 1 and b["i"] == 1)
    say("W2 order stable: two calls -> %s / %s => %s"
        % ((a or {}).get("i"), (b or {}).get("i"), w2))
    ok &= w2

    # --- W5 no faking -----------------------------------------------------
    refused = False
    try:
        JS.mark_plan_step(jid, 1, "")
    except Exception as e:
        refused = "evidence" in str(e)
    oor = False
    try:
        JS.mark_plan_step(jid, 99, "背包 4->0")
    except Exception as e:
        oor = "out of range" in str(e)
    after = JS.load(jid)
    w5 = refused and oor and (JS.next_plan_step(after) or {}).get("i") == 1
    say("W5 no faking: empty-evidence refused=%s  out-of-range refused=%s  "
        "still on step 1=%s => %s"
        % (refused, oor, (JS.next_plan_step(after) or {}).get("i") == 1, w5))
    ok &= w5

    # --- W3 evidence-driven skipping --------------------------------------
    JS.mark_plan_step(jid, 1, "背包 gravel 0->8（dshinv 读数）")
    nxt = JS.next_plan_step(JS.load(jid))
    d, t = JS.plan_progress(JS.load(jid))
    w3 = (nxt or {}).get("i") == 2 and d == 1 and t == 3
    say("W3 evidence: after marking step 1 done -> next=%s progress=%d/%d => %s"
        % ((nxt or {}).get("i"), d, t, w3))
    ok &= w3

    # --- W4 cross-process -------------------------------------------------
    code = ("import sys,json;sys.path.insert(0,%r);import jobs_store as J;"
            "j=J.load(%r);n=J.next_plan_step(j);d,t=J.plan_progress(j);"
            "print('NEXT',n['i'] if n else 0,'PROG',d,t)"
            % (str(ROOT / "tools"), jid))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=str(ROOT))
    outp = (r.stdout or "").strip()
    w4 = ("NEXT 2" in outp) and ("PROG 1 3" in outp)
    say("W4 cross-process: a fresh python process says %r => %s" % (outp, w4))
    ok &= w4

    # clean up (keep the ledger honest)
    JS.close(jid, "自测完成（第 22 轮 W1~W5）", "done")
    p = ROOT / "jobs" / (jid + ".json")
    if p.is_file():
        p.unlink()
    say("cleaned up the self-test job")

    say("---- W1 / W2 / W3 / W4 / W5 = %s / %s / %s / %s / %s ----" % (w1, w2, w3, w4, w5))
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
