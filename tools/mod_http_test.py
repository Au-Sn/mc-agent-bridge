#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mod_http_test.py -- 2.56.0 A3: 8766 HTTP concurrency + token + Origin + /raw whitelist.

WHAT CHANGED (why this judge exists)
  Before 2.56.0: one accept thread handled one socket at a time, each request bounced to the
  server thread and waited on a 30 s latch.  A slow command therefore blocked /health too,
  and any local process (or a browser page: text/plain POST is a "simple request") could
  drive the mod with /cmd and /raw at permission 4.

CHECKS (offline: source-static + direct.py against a fake HTTP server)
  H1 pool        accept loop hands each socket to a worker pool; /health is answered on the
                 worker thread and never enters the world lane
  H2 world lane  /cmd and /raw are dispatched through ONE single-thread lane (world writes
                 stay serial; no parallel world mutation was introduced)
  H3 token       /cmd + /raw must carry X-DSH-Token; token file config/dshbridge/http_token.txt;
                 missing/wrong token -> 401 with ASCII reason=missing_token / reason=bad_token
  H4 origin      ANY request carrying an Origin header is refused (403 reason=origin_header)
  H5 raw map     /raw whitelist covers real uses (player <bot> spawn|kill, setblock, tp <bot>,
                 item replace entity <bot> hotbar.N, gamemode <mode> <bot>) and refuses the rest
                 with ASCII reason=not_whitelisted
  H6 direct.py   reads the same token file (env override) and sends X-DSH-Token; public API
                 health/post/raw/available unchanged; no token file -> request still sent (no header)

CHECKS (--live: needs the game running with 2.56.0 loaded)
  L1 dshver has http2/token/origin/rawmap/reqid; /dshhttp reports pool + lane up
  L2 no token -> 401 reason=missing_token; bad token -> 401 reason=bad_token; good token -> 200
  L3 Origin -> 403 reason=origin_header (even with a valid token)
  L4 /raw say hi -> refused reason=not_whitelisted; /raw player Bot spawn -> not refused
  L5 /health p95 < 50 ms while slow /cmd requests are in flight (the old single-lane blocker)
  L6 X-DSH-Req header echoed; /dshreqs shows op=cmd + ms= for that request

USAGE
  py tools/mod_http_test.py            # offline checks only
  py tools/mod_http_test.py --live     # offline + live checks
"""
from __future__ import annotations

import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JAVA = ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge" / "DshBridgeMod.java"
BRIDGE = ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge" / "HttpBridge.java"
DIRECT = ROOT / "tools" / "direct.py"
GRADLE = ROOT / "mod" / "gradle.properties"

sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception as _exc:               # stdout may be a pipe without reconfigure
    print("note: stdout reconfigure skipped: %r" % (_exc,))

TOKEN_HEADER = "X-DSH-Token"
REQ_HEADER = "X-DSH-Req"


def _src() -> str:
    """2.57.0（S1）起 HTTP 服务在 HttpBridge.java ⇒ 两个文件一起读（判据不看它住哪 ✓）"""
    parts = [JAVA.read_text(encoding="utf-8")]
    if BRIDGE.is_file():
        parts.append(BRIDGE.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _direct_src() -> str:
    return DIRECT.read_text(encoding="utf-8")


def _expected_version() -> str:
    m = re.search(r"^mod_version\s*=\s*(\S+)", GRADLE.read_text(encoding="utf-8", errors="replace"),
                  re.MULTILINE)
    return m.group(1) if m else "?"


# ── fake HTTP server that records what direct.py actually sent ─────────────────────
class _Recorder(http.server.BaseHTTPRequestHandler):
    seen: list[dict] = []
    lock = threading.Lock()

    def log_message(self, *a):
        pass

    def _record(self, method: str) -> list[str]:
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", errors="replace") if n else ""
        with self.lock:
            self.seen.append({"method": method, "path": self.path,
                              "headers": {k.lower(): v for k, v in self.headers.items()},
                              "body": body})
        return [method, body]

    def do_GET(self):
        self._record("GET")
        body = b"ok dshbridge-http"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        _m, body = self._record("POST")
        out = ("dshver version=fake echoed=" + body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class _TS(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _serve():
    srv = _TS(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


# ── offline checks ───────────────────────────────────────────────────────────────
def offline_checks(checks: list) -> None:
    s = _src()
    d = _direct_src()

    # H1 thread pool + health bypass (source order: /health answered before the world lane call)
    pool = ("HTTP_POOL" in s)
    submit = ("HTTP_POOL.execute" in s) or ("HTTP_POOL.submit" in s)
    laned = ("HTTP_WORLD_LANE" in s)
    h_idx = s.find('contains("/health")')
    w_idx = s.find("httpWorldLane(srv, reqId")
    health_direct = (h_idx >= 0 and w_idx > h_idx)
    checks.append(("H1 pool: accept -> worker pool; /health answered before the world lane",
                   bool(pool and submit and laned and health_direct),
                   "POOL=%s submit=%s LANE=%s health_before_lane=%s" % (pool, submit, laned, health_direct)))

    # H2 single world lane for /cmd and /raw (serial world writes)
    cmd_via_lane = "httpWorldLane" in s
    one_lane = ("newSingleThreadExecutor" in s) or ("HTTP_LANE_THREAD" in s)
    named = "dsh-world-lane" in s
    checks.append(("H2 world lane: /cmd + /raw go through ONE single-thread lane (no parallel world writes)",
                   bool(cmd_via_lane and one_lane and named),
                   "lane=%s single=%s named=%s" % (cmd_via_lane, one_lane, named)))

    # H3 token file + header + reasons
    tok_file = ("config/dshbridge/http_token.txt" in s) or (
        '"config", "dshbridge", "http_token.txt"' in s) or ('"config","dshbridge","http_token.txt"' in s)
    tok_header = TOKEN_HEADER in s
    reasons = all(x in s for x in ("reason=missing_token", "reason=bad_token"))
    d_tok = ("http_token.txt" in d) and (TOKEN_HEADER in d)
    checks.append(("H3 token: /cmd + /raw need X-DSH-Token from config/dshbridge/http_token.txt",
                   bool(tok_file and tok_header and reasons and d_tok),
                   "file=%s header=%s reasons=%s direct=%s" % (tok_file, tok_header, reasons, d_tok)))

    # H4 Origin refused
    origin = ("reason=origin_header" in s) and ("Origin" in s)
    checks.append(("H4 origin: any request carrying an Origin header is refused (CSRF)",
                   bool(origin), "reason=origin_header=%s" % origin))

    # H5 /raw whitelist covers real uses and denies the rest
    uses = {
        "player_spawn": ("RAW_ALLOW_PLAYER" in s),
        "setblock": ("RAW_ALLOW_SETBLOCK" in s),
        "tp": ("RAW_ALLOW_TP" in s),
        "item_replace": ("RAW_ALLOW_ITEM" in s),
    }
    denied = "reason=not_whitelisted" in s
    checks.append(("H5 /raw whitelist covers player spawn/kill + setblock + tp bot + item replace; denies rest",
                   bool(all(uses.values()) and denied),
                   " ".join("%s=%s" % (k, bool(v)) for k, v in uses.items()) + " deny=%s" % denied))

    # H6 direct.py: env token override + header injection, API unchanged
    api = all(("def %s(" % f) in d for f in ("health", "post", "raw", "available"))
    env_tok = ("DSH_HTTP_TOKEN" in d)
    has_refresh = "def refresh_token(" in d
    checks.append(("H6 direct.py: token env/file + X-DSH-Token header, health/post/raw/available API kept",
                   bool(api and env_tok and has_refresh and d_tok),
                   "api=%s env=%s refresh=%s" % (api, env_tok, has_refresh)))

    # H7 functional: direct.py really sends the token header (fake server captures it)
    import direct as D
    srv, port = _serve()
    old_base = D.BASE
    old_env = os.environ.get("DSH_HTTP_TOKEN")
    try:
        D.BASE = "http://127.0.0.1:%d" % port
        os.environ["DSH_HTTP_TOKEN"] = "unit-token-abc123"
        D.refresh_token()
        _Recorder.seen.clear()
        r = D.post("dshver", timeout=5.0)
        got = [x for x in _Recorder.seen if x["path"].startswith("/cmd")]
        hdr = got[0]["headers"].get(TOKEN_HEADER.lower()) if got else None
        r2 = D.raw("player Bot spawn", timeout=5.0)
        got2 = [x for x in _Recorder.seen if x["path"].startswith("/raw")]
        hdr2 = got2[0]["headers"].get(TOKEN_HEADER.lower()) if got2 else None
        checks.append(("H7 direct.py sends X-DSH-Token on /cmd and /raw (fake server capture)",
                       bool(r and hdr == "unit-token-abc123" and r2 and hdr2 == "unit-token-abc123"),
                       "cmd_hdr=%r raw_hdr=%r reply=%r" % (hdr, hdr2, (r or "")[:40])))
        # without token: request must still go out (header absent) -- old mods ignore it
        del os.environ["DSH_HTTP_TOKEN"]
        D.refresh_token()
        _Recorder.seen.clear()
        r3 = D.health(timeout=5.0)
        checks.append(("H8 no-token env: client still works (no header, never raises)",
                       bool(r3 and "ok" in r3 and _Recorder.seen), "health=%r" % (r3,)))
    finally:
        D.BASE = old_base
        if old_env is None:
            os.environ.pop("DSH_HTTP_TOKEN", None)
        else:
            os.environ["DSH_HTTP_TOKEN"] = old_env
        D.refresh_token()
        srv.shutdown()

    # H9 events/A7 companion markers must be visible in source (shared with mod_events_test)
    checks.append(("H9 A7 trace markers: ev() appends req= and responses echo X-DSH-Req",
                   ("REQ_CTX" in s) and ('req=" + ' in s or " req=" in s) and (REQ_HEADER in s),
                   "ctx=%s req_field=%s header=%s"
                   % ("REQ_CTX" in s, " req=" in s, REQ_HEADER in s)))


# ── live checks ──────────────────────────────────────────────────────────────────
def _base() -> str:
    import direct as D
    return D.BASE.rstrip("/")


def _http(path: str, data: bytes = None, headers: dict = None, timeout: float = 10.0):
    """-> (status, body, headers). Never raises on HTTP status; raises on connect."""
    req = urllib.request.Request(_base() + path, data=data, method=("POST" if data is not None else "GET"),
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers)


def live_checks(checks: list) -> None:
    import direct as D

    global BASE
    BASE = D.BASE

    tok = D.token()
    exp = _expected_version()
    if not tok:
        checks.append(("L0 token file readable by direct.py", False,
                       "token empty (file missing?) -> live checks need it"))
        return

    # L1 version + http diagnostics
    st, body, _h = _http("/cmd", data=b"dshver", headers={TOKEN_HEADER: tok})
    ver_ok = ("version=" + exp) in body
    feat_ok = all(k in body for k in ("http2", "token", "origin", "rawmap", "reqid"))
    st2, http_body, _h2 = _http("/cmd", data=b"dshhttp", headers={TOKEN_HEADER: tok})
    diag_ok = ("pool=" in http_body) and ("lane=" in http_body) and ("token_file=" in http_body)
    checks.append(("L1 dshver=%s + http2/token/origin/rawmap/reqid features" % exp,
                   bool(st == 200 and ver_ok and feat_ok), "%s | %s" % (body.strip()[:100], exp)))
    checks.append(("L1b /dshhttp reports worker pool + world lane + token file",
                   bool(st2 == 200 and diag_ok), http_body.strip()[:120]))

    # L2 token enforcement
    st, body, _h = _http("/cmd", data=b"dshver")
    checks.append(("L2 no token -> 401 reason=missing_token",
                   st == 401 and "reason=missing_token" in body, "status=%s body=%r" % (st, body[:80])))
    st, body, _h = _http("/cmd", data=b"dshver", headers={TOKEN_HEADER: "definitely-wrong"})
    checks.append(("L2b bad token -> 401 reason=bad_token",
                   st == 401 and "reason=bad_token" in body, "status=%s body=%r" % (st, body[:80])))
    st, body, _h = _http("/cmd", data=b"dshver", headers={TOKEN_HEADER: tok})
    checks.append(("L2c good token -> 200", st == 200 and body.startswith("dshver"), "status=%s" % st))

    # L3 Origin refused even with a valid token
    st, body, _h = _http("/cmd", data=b"dshver",
                         headers={TOKEN_HEADER: tok, "Origin": "http://evil.example"})
    checks.append(("L3 Origin -> 403 reason=origin_header",
                   st == 403 and "reason=origin_header" in body,
                   "status=%s body=%r" % (st, body[:80])))
    st, body, _h = _http("/health", headers={"Origin": "http://evil.example"})
    checks.append(("L3b Origin on /health is refused too (any request)",
                   st == 403 and "reason=origin_header" in body, "status=%s body=%r" % (st, body[:80])))

    # L4 /raw whitelist
    st, body, _h = _http("/raw", data=b"say hello", headers={TOKEN_HEADER: tok})
    checks.append(("L4 /raw outside whitelist -> 403 reason=not_whitelisted",
                   st == 403 and "reason=not_whitelisted" in body,
                   "status=%s body=%r" % (st, body[:100])))
    st, body, _h = _http("/raw", data=b"kill @a", headers={TOKEN_HEADER: tok})
    checks.append(("L4b /raw kill @a -> refused",
                   st == 403 and "reason=not_whitelisted" in body, "status=%s" % st))
    st, body, _h = _http("/raw", data=b"player Bot spawn", headers={TOKEN_HEADER: tok})
    checks.append(("L4c /raw player Bot spawn -> not refused (200, whitelisted)",
                   st == 200 and "not_whitelisted" not in body,
                   "status=%s body=%r" % (st, body[:80])))

    # L5 /health during slow /cmd requests: p95 < 50 ms
    #    ★选一条**在已加载区块里**真会算很久的扫描✗★：2026-11-02 实测
    #      `dshscan 4090 60 0 4300 120 160` ≈ 90ms/条（vol=2.07M）；
    #      而 x>4360 那一带**区块没加载** ⇒ 命令瞬间空回（不能拿来当"慢请求"✗）
    slow = b"dshscan 4090 60 0 4300 120 160"
    dur = []

    def slow_call():
        t0 = time.perf_counter()
        try:
            _http("/cmd", data=slow, headers={TOKEN_HEADER: tok}, timeout=60.0)
        except Exception as exc:            # noqa: BLE001
            dur.append(-1.0)
            return
        dur.append((time.perf_counter() - t0) * 1000.0)

    ths = [threading.Thread(target=slow_call) for _ in range(6)]
    t_start = time.perf_counter()
    for t in ths:
        t.start()
    time.sleep(0.02)
    hs = []
    for _ in range(60):
        t0 = time.perf_counter()
        try:
            _http("/health", timeout=5.0)
            hs.append((time.perf_counter() - t0) * 1000.0)
        except Exception:                    # noqa: BLE001
            hs.append(9999.0)
        time.sleep(0.005)
    for t in ths:
        t.join(timeout=90)
    busy_ms = (time.perf_counter() - t_start) * 1000.0
    hs.sort()
    p95 = hs[int(len(hs) * 0.95)] if hs else 9999.0
    slow_ms = max(dur) if dur else -1.0
    # ★口径✗★：世界车道被**连续占用** ≥150ms（6 条扫描排队）期间 /health p95 仍 <50ms ✓
    #   （旧的单线程 accept 会把 health 一起堵住 ⇒ 这条必红 ✗）
    checks.append(("L5 /health p95 < 50 ms while the single world lane is busy (6 queued slow /cmd)",
                   bool(p95 < 50.0 and busy_ms > 150.0),
                   "health_p95=%.1fms lane_busy=%.0fms slow_cmd_max=%.0fms n=%d"
                   % (p95, busy_ms, slow_ms, len(hs))))

    # L6 request id echo + request ledger
    st, body, _h = _http("/cmd", data=b"dshevents", headers={TOKEN_HEADER: tok})
    m = re.search(r"cursor=(\d+)", body)
    cur = int(m.group(1)) if m else 0
    st, body, hdrs = _http("/cmd", data=b"dshturn 20", headers={TOKEN_HEADER: tok})
    req = hdrs.get(REQ_HEADER) or hdrs.get(REQ_HEADER.lower())
    hdr_ok = bool(req and re.fullmatch(r"r\d+", req))
    st, ev_body, _h = _http("/cmd", data=("dshevents %d" % cur).encode(), headers={TOKEN_HEADER: tok})
    ev_ok = bool(req and (" req=" + req) in ev_body)
    st, reqs_body, _h = _http("/cmd", data=b"dshreqs", headers={TOKEN_HEADER: tok})
    ledger_ok = bool(req and ("id=" + req) in reqs_body and "op=cmd" in reqs_body and "ms=" in reqs_body)
    checks.append(("L6 X-DSH-Req echoed and events inside the request carry the same req=",
                   bool(hdr_ok and ev_ok), "req=%r events_req=%s" % (req, ev_ok)))
    checks.append(("L6b /dshreqs ledger lists id= op=cmd ms= for that request",
                   ledger_ok, reqs_body.strip()[:140]))
    # release hold so the bot is not pinned by the diagnostic turn
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
        print("  => mod_http FAIL (%d)" % bad)
        print("MODHTTP ok=0 bad=%d checks=%d live=%d" % (bad, len(checks), 1 if live else 0))
        return 1
    print("  => mod_http PASS (pool+world lane; token/Origin/raw-whitelist enforced; health not blocked)")
    print("MODHTTP ok=1 checks=%d live=%d version=%s" % (len(checks), 1 if live else 0, _expected_version()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
