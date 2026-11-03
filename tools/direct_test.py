#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""direct_test.py -- 直连客户端的判据（★离线 ✗ 起一个假 HTTP 服务器✗★）

规格（用户：「优化成直连」）：
  ★① 能 POST 一条指令并把回执原样拿回来✗
  ★② 能 GET /health✗
  ★③ **连不上时回 None ✗ 不抛异常**（★调用方要能安静地走后备✗★）✗
  ★④ 超时要如实失败（★不许挂死✗★）✗
  ★⑤ 非 ASCII（中文）原样往返（UTF-8）✗★

CHECKS
  D1 health 拿到 ok
  D2 POST 回执原样（含中文）
  D3 ★端口没人听 ⇒ 回 None ✗ 不抛★
  D4 ★服务器不回应 ⇒ 超时后回 None ✗ 不挂死★
  D5 available() 只是"能不能连" ✗ 不含业务语义✗★
"""
from __future__ import annotations

import http.server
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import direct as D          # noqa: E402


class _H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b"ok dshbridge-http"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", errors="replace")
        if raw == "SLOW":
            time.sleep(3.0)
        out = ("dshver version=2.53.0 echoed=" + raw).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class _TS(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _serve(port=0):
    srv = _TS(("127.0.0.1", port), _H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, srv.server_address[1]


def main() -> int:
    checks = []
    srv, port = _serve()
    D.BASE = "http://127.0.0.1:%d" % port

    # D1 health
    h = D.health()
    checks.append(("D1 health 拿到 ok", bool(h and "ok" in h), repr(h)))

    # D2 POST 原样（含中文）
    r = D.post("dshstate 4120 71 7 中文测试")
    checks.append(("D2 POST 回执原样（含中文）",
                   bool(r) and "echoed=dshstate 4120 71 7 中文测试" in r, repr(r)[:90]))

    # D3 端口没人听 ⇒ None
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    free_port = sock.getsockname()[1]
    sock.close()
    old = D.BASE
    D.BASE = "http://127.0.0.1:%d" % free_port
    r3 = D.post("dshver", timeout=2.0)
    checks.append(("D3 ★端口没人听 ⇒ 回 None ✗ 不抛★", r3 is None, repr(r3)))

    # D4 服务器不回应 ⇒ 超时回 None
    D.BASE = old
    t0 = time.time()
    r4 = D.post("SLOW", timeout=1.0)
    dt = time.time() - t0
    checks.append(("D4 ★不回应 ⇒ 超时回 None ✗ 不挂死★",
                   r4 is None and dt < 2.5, "回=%r 用时=%.1fs" % (r4, dt)))

    # D5 available()
    D.BASE = "http://127.0.0.1:%d" % port
    ok5 = D.available()
    D.BASE = "http://127.0.0.1:%d" % free_port
    ok5b = D.available(timeout=0.3)
    checks.append(("D5 available() 只判连通", ok5 is True and ok5b is False,
                   "在=%s 不在=%s" % (ok5, ok5b)))

    srv.shutdown()

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => direct FAIL (%d)" % bad)
        print("DIRECT ok=0 bad=%d" % bad)
        return 1
    print("  => direct PASS (roundtrip incl. UTF-8; offline returns None, never raises)")
    print("DIRECT ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
