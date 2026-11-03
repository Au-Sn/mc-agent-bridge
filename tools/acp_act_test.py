"""acp_act_test.py -- does the resident ACP brain actually MOVE the fake player?

Hard criteria (declared before running):
  A1 the brain's answer contains START=x,y,z END=x,y,z
  A2 START matches world truth (read independently through CC cmd0) within 1.5 blocks
  A3 world truth shows displacement >= 3.0 blocks  -> the bot really moved
  A4 END matches the final world-truth position within 2.5 blocks -> claim == truth
Any of A1..A4 false => FAIL. ASCII-only output (lesson P39/P50).
"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ch = Channel("cmd0", verbose=False)


def raw(t: str, tmo: float = 40.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def pos() -> tuple:
    s = raw("execute as Bot at Bot run dshdigest 4")
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", s)
    if not m:
        return None
    return tuple(float(g) for g in m.groups())


def dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def main() -> int:
    out = []
    prompt = (ROOT / "tools" / "_acp_act_prompt.txt").read_text(encoding="utf-8").strip()
    p0 = pos()
    out.append("POS0 world-truth = %s" % (p0,))
    if p0 is None:
        out.append("=> FAIL: cannot read Bot position (bot missing?)")
        print("\n".join(out))
        return 1

    rid = "act-" + uuid.uuid4().hex[:6]
    with (ROOT / "logs" / "acp_inbox.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"id": rid, "text": prompt}, ensure_ascii=False) + "\n")
    out.append("ASK id=%s (chars=%d)" % (rid, len(prompt)))

    t0, ans = time.time(), None
    while time.time() - t0 < 300:
        time.sleep(2.0)
        try:
            lines = (ROOT / "logs" / "acp_outbox.jsonl").read_text(encoding="utf-8").splitlines()
            for line in lines[-60:]:
                r = json.loads(line)
                if r.get("id") == rid:
                    ans = r.get("answer") or ""
            if ans is not None:
                break
        except Exception:
            pass
    p1 = pos()
    out.append("POS1 world-truth = %s (after %.0fs)" % (p1, time.time() - t0))
    a = ans or ""
    out.append("ANSWER len=%d ascii=%s" % (len(a), a.encode("ascii", "replace").decode("ascii")[:500]))

    ms = re.search(r"START=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", a)
    me = re.search(r"END=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", a)
    A1 = bool(ms and me)
    A3 = p1 is not None and dist(p0, p1) >= 3.0
    A2 = A4 = False
    if A1 and p1 is not None:
        S = tuple(float(g) for g in ms.groups())
        E = tuple(float(g) for g in me.groups())
        A2 = dist(S, p0) <= 1.5
        A4 = dist(E, p1) <= 2.5
        out.append("claimed START=%s END=%s" % (S, E))
        out.append("moved_truth=%.2f blocks" % dist(p0, p1))
    out.append("A1 answer_parsable=%s" % A1)
    out.append("A2 start_matches_truth=%s" % A2)
    out.append("A3 really_moved=%s" % A3)
    out.append("A4 end_matches_truth=%s" % A4)
    ok = A1 and A2 and A3 and A4
    out.append("=> %s" % ("PASS" if ok else "FAIL"))
    (ROOT / "logs" / "acp_act_test.txt").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    return 0 if ok else 1


raise SystemExit(main())
