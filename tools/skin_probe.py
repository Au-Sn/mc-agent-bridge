#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skin_probe.py —— 皮肤链路逐环测穿（★全 ASCII 输出 ✗★）

环 1 模组版本 ✓  环 2 注册表/端口 ✓  环 3 TCP 能连回环吗 ✓（A7 的复核）
环 4 **我自己 GET 那张 PNG** ✓（拿得到且是 PNG ⇒ 服务端没问题 ✓）
环 5 换皮肤的回执 ✓  环 6 局域网地址**连不上** ✓（G4：只绑回环 ✓）
"""
from __future__ import annotations

import re
import socket
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)


def raw(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


out: list[str] = []
ver = raw("dshver")
out.append("R1 version   : %s" % ver[:90])

lst = raw("dskskin list")
out.append("R2 list      : %s" % lst[:260])
port = (re.search(r"port=(\d+)", lst) or [0, "0"])[1]
base = (re.search(r"base=(\S+)", lst) or [0, "-"])[1]
out.append("R2 port=%s base=%s" % (port, base))

try:
    s = socket.create_connection(("127.0.0.1", int(port)), timeout=3)
    s.close()
    out.append("R3 tcp 127.0.0.1:%s : OK (connectable)" % port)
    r3 = True
except Exception as e:
    out.append("R3 tcp 127.0.0.1:%s : FAIL %s" % (port, type(e).__name__))
    r3 = False

r4 = None
try:
    with urllib.request.urlopen("http://127.0.0.1:%s/skin/deepseek.png?v=probe" % port, timeout=5) as fp:
        body = fp.read()
    r4 = (len(body), body[:8] == b"\x89PNG\r\n\x1a\n")
    out.append("R4 http GET  : %d bytes, png_magic=%s" % r4)
except Exception as e:
    out.append("R4 http GET  : FAIL %s: %s" % (type(e).__name__, str(e)[:80]))

setr = raw("dskskin deepseek")
out.append("R5 set skin  : %s" % setr[:220])

try:
    ip = socket.gethostbyname(socket.gethostname())
    if ip.startswith("127."):
        out.append("R6 lan bind  : skip (no lan ip)")
    else:
        try:
            s2 = socket.create_connection((ip, int(port)), timeout=3)
            s2.close()
            out.append("R6 lan bind  : FAIL -> reachable from %s (should NOT be)" % ip)
        except Exception:
            out.append("R6 lan bind  : OK -> not reachable from %s" % ip)
except Exception as e:
    out.append("R6 lan bind  : skip %s" % type(e).__name__)

out.append("")
out.append("VERDICT: server-side chain = %s"
           % ("WORKS (R3+R4 ok)" if (r3 and r4) else "BROKEN at R3/R4"))
(ROOT / "logs" / "skin_probe.txt").write_text("\n".join(out), encoding="utf-8")
for l in out:
    print(l.encode("ascii", "replace").decode("ascii")[:150])
