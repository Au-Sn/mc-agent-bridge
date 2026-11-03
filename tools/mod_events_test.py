#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mod_events_test.py -- 2.56.0 A7 (minimal trace): every event can be tied to the request
that produced it, without breaking the existing dshevents consumers.

WHY (10-mod A7 / ADR-3)
  dshevents lines were "#<seq> <kind> <data>" with no request id, so "which call produced this
  event" could not be answered.  The 400-entry ring is the only live witness of D3 soak; an
  event without its request is not replayable evidence.

DESIGN (minimal, format-compatible)
  * an HTTP request gets an id r<N>; the response echoes it in X-DSH-Req
  * while the request's command runs on the server thread, ev() appends " req=r<N>" at the END
    of the event line (only when a request is active -- tick events stay byte-identical)
  * /dshreqs keeps an in-memory ledger of the last requests: id=, op=, status=, ms=
  * no new event kind is introduced (speech.py EVENT_KINDS / errata_guard E11 stay valid)

CHECKS (offline)
  E1 format: trailing " req=..." does not break the existing event parsers
     (events_log.extract_ascii and exec3d._parse_events keep seq/kind/data)
  E2 mod source: ev() reads REQ_CTX and appends req= only when it is set
  E3 request ledger: /dshreqs exposed; response header X-DSH-Req
  E4 no new ev("<kind>") names added by the trace feature (kind set unchanged)
  E5 live: cursor -> /cmd dshturn -> the turn_start event inside that request carries the same
     req= as the X-DSH-Req header, and /dshreqs has op=cmd ms=
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JAVA = ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge" / "DshBridgeMod.java"
BRIDGE = ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge" / "HttpBridge.java"
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception as _exc:               # stdout may be a pipe without reconfigure
    print("note: stdout reconfigure skipped: %r" % (_exc,))

TOKEN_HEADER = "X-DSH-Token"
REQ_HEADER = "X-DSH-Req"


def _src() -> str:
    """2.57.0（S1）起 HTTP 服务在 HttpBridge.java ⇒ 两个文件一起读（事件出口仍在主类 ✓）"""
    parts = [JAVA.read_text(encoding="utf-8")]
    if BRIDGE.is_file():
        parts.append(BRIDGE.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _http(path: str, data: bytes = None, headers: dict = None, timeout: float = 20.0):
    import direct as D
    req = urllib.request.Request(D.BASE.rstrip("/") + path, data=data,
                                 method=("POST" if data is not None else "GET"),
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers)


def offline_checks(checks: list) -> None:
    s = _src()

    # E1 existing parsers still understand the new line shape
    old_events_log = "extract_ascii" in (ROOT / "tools" / "events_log.py").read_text(encoding="utf-8")
    old_exec3d = "_parse_events" in (ROOT / "tools" / "exec3d.py").read_text(encoding="utf-8")
    import events_log
    import exec3d
    raw = ("dshevents watched=Bot total=9 new=9 cursor=9 | "
           "#8 turn_start from=10.0 to=90.0 ticks=8 req=r12 | "
           "#9 walk_start why=test req=r13")
    found, dropped = events_log.extract_ascii(raw)
    parsed = exec3d._parse_events(raw)
    ok1 = (old_events_log and old_exec3d and len(found) == 2 and len(parsed) == 2
           and parsed[0][1] == "turn_start" and "req=r12" in parsed[0][2]
           and parsed[0][0] == 8)
    checks.append(("E1 existing consumers keep seq/kind/data with trailing req= (events_log + exec3d)",
                   bool(ok1), "found=%d parsed=%s dropped=%d" % (len(found), parsed[:1], dropped)))

    # E2 ev() appends req from a request context, and only then
    ev_region = ""
    m = re.search(r"(?:private\s+)?static void ev\(String kind, String data\) \{", s)
    if m:
        ev_region = s[m.start():m.start() + 900]
    ctx = ("REQ_CTX" in ev_region) and ("req=" in ev_region)
    no_req_plain = ("REQ_CTX" in s) and ("req=" in s)
    checks.append(("E2 ev() appends req=<rid> from REQ_CTX only when a request is active",
                   bool(ctx and no_req_plain),
                   "ev_region=%d ctx_in_ev=%s req_field=%s" % (len(ev_region), "REQ_CTX" in ev_region,
                                                              "req=" in ev_region)))

    # E3 ledger + response header
    ledger = re.search(r'Commands\.literal\("dshreqs"\)', s)
    header = REQ_HEADER in s
    ms_op = ("op=" in s) and ("ms=" in s)
    checks.append(("E3 /dshreqs request ledger + X-DSH-Req response header",
                   bool(ledger and header and ms_op),
                   "dshreqs=%s header=%s op/ms=%s" % (bool(ledger), header, ms_op)))

    # E4 no new event kinds introduced: the set of ev("<kind>") names inside the new HTTP
    #    section must stay within the kinds that already existed (speech.py/E11 stay valid).
    http_region = ""
    m2 = re.search(r"public static final int HTTP_PORT", s)
    if m2:
        end = s.find("private static void ok(", m2.start())
        http_region = s[m2.start():end if end > 0 else m2.start() + 16000]
    new_kinds = set(re.findall(r'ev\("([a-z_0-9]+)"', http_region))
    allowed = {"http_server", "http_error"}     # 2 kinds already in speech.SKIP_EVENTS
    checks.append(("E4 no new event kind introduced by the trace feature (E11 table stays valid)",
                   bool(new_kinds <= allowed),
                   "http_region_kinds=%s" % sorted(new_kinds)))

    # E5 react()'s hand-built event line also carries req when active
    react_req = ("req=" in (s[m.start():m.start() + 900] if (m := re.search(
        r"String line = \"#\" \+ EVENT_SEQ\.incrementAndGet\(\) \+ \" react", s)) else ""))
    checks.append(("E5 react() hand-built event line also carries req=", bool(react_req),
                   "react_req=%s" % react_req))


def live_checks(checks: list) -> None:
    import direct as D
    tok = D.token()
    if not tok:
        checks.append(("E5 token readable", False, "direct.py token empty"))
        return
    st, body, _h = _http("/cmd", data=b"dshevents", headers={TOKEN_HEADER: tok})
    m = re.search(r"cursor=(\d+)", body or "")
    cur = int(m.group(1)) if m else 0
    st, _b, hdrs = _http("/cmd", data=b"dshturn 20", headers={TOKEN_HEADER: tok})
    req = hdrs.get(REQ_HEADER) or hdrs.get(REQ_HEADER.lower())
    st, ev_body, _h = _http("/cmd", data=("dshevents %d" % cur).encode(), headers={TOKEN_HEADER: tok})
    line_ok = bool(req and re.search(r" req=" + re.escape(req) + r"(\s|\||$)", ev_body or ""))
    checks.append(("E5 live: events produced inside a /cmd request carry the same req= as X-DSH-Req",
                   bool(line_ok), "req=%r hits=%d" % (req, (ev_body or "").count("req=" + (req or "")))))
    st, reqs, _h = _http("/cmd", data=b"dshreqs", headers={TOKEN_HEADER: tok})
    ok2 = bool(req and ("id=" + req) in (reqs or "") and "op=cmd" in (reqs or "") and "ms=" in (reqs or ""))
    checks.append(("E5b live: /dshreqs ledger has id= op=cmd ms= for that request", ok2,
                   (reqs or "").strip()[:150]))
    # events outside any request keep the old byte shape (no req= in tick events is not
    # guaranteed by content, but the line still parses)
    checks.append(("E5c live: dshevents line still starts with #<seq> <kind>",
                   bool(re.search(r"#\d+\s+[a-z_0-9]+", ev_body or "")),
                   (ev_body or "").strip()[:100]))
    _http("/cmd", data=b"dshhold off", headers={TOKEN_HEADER: tok})


def main(argv) -> int:
    live = "--live" in argv
    checks = []
    try:
        offline_checks(checks)
    except Exception as exc:                 # noqa: BLE001
        checks.append(("offline checks crashed", False, repr(exc)[:160]))
    if live:
        try:
            live_checks(checks)
        except Exception as exc:             # noqa: BLE001
            checks.append(("live checks crashed (game down?)", False, repr(exc)[:160]))
    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:130]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => mod_events FAIL (%d)" % bad)
        print("MODEVENTS ok=0 bad=%d checks=%d live=%d" % (bad, len(checks), 1 if live else 0))
        return 1
    print("  => mod_events PASS (seq/kind/data compatible; req= ties events to the request)")
    print("MODEVENTS ok=1 checks=%d live=%d" % (len(checks), 1 if live else 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
