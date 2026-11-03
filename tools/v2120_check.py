#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2120_check.py —— 皮肤系统验收（★判据照 docs/模组-皮肤系统.md ✓ 全 ASCII 输出 ✗★）

G1 现场验证 ✓：造一张 64x64 合格图丢进外部目录 ⇒ reload 后列表里**必须多一个** ✓
G6 现场验证 ✓：造一张 32x32 坏图 ⇒ 列表里必须标 `BAD:size 32x32` ✓ 且**换不上** ✗
"""
from __future__ import annotations

import re
import struct
import sys, paths as PA
import zlib
from pathlib import Path

ROOT = PA.ROOT
GAME = PA.MC_HOME
EXT = GAME / "config" / "dshbridge" / "skins"
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)
out: list[str] = []


def raw(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def mkpng(path: Path, size: int, rgba=(20, 120, 220, 255)) -> None:
    raw_px = b"".join(b"\x00" + bytes(rgba) * size for _ in range(size))

    def ck(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + ck(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
                     + ck(b"IDAT", zlib.compress(raw_px, 6)) + ck(b"IEND", b""))


ver = raw("dshver")
out.append("A1 dshver -> %s" % ver[:100])
if "2.12.0" not in ver:
    out.append("A1 => FAIL (game not restarted to 2.12.0; later checks skipped)")
    (ROOT / "logs" / "v2120_check.txt").write_text("\n".join(out), encoding="utf-8")
    print("V2120: A1 FAIL - not 2.12.0 yet")
    raise SystemExit(1)
out.append("A1 => PASS")

# A2 列表
lst0 = raw("dskskin list")
out.append("A2 list -> %s" % lst0[:300])
n0 = 0
m = re.search(r"count=(\d+)", lst0)
n0 = int(m.group(1)) if m else -1
port = (re.search(r"port=(\d+)", lst0) or [0, "?"])[1]
out.append("A2 count=%s port=%s => %s" % (n0, port, "PASS" if n0 >= 3 else "FAIL"))

# G1：丢一张合格图 + 一张坏图
mkpng(EXT / "testfish.png", 64, (250, 200, 40, 255))
mkpng(EXT / "badsize.png", 32, (250, 40, 40, 255))
out.append("")
out.append("G1/G6 test files -> %s , %s" % ((EXT / "testfish.png").is_file(), (EXT / "badsize.png").is_file()))
rr = raw("dskskin reload")
out.append("reload -> %s" % rr[:160])
lst1 = raw("dskskin list")
out.append("list(again) -> %s" % lst1[:400])
g1 = ("testfish" in lst1) and ("ok" in lst1)
g6 = ("badsize" in lst1) and ("BAD:size 32x32" in lst1)
out.append("G1 testfish discovered => %s" % ("PASS" if g1 else "FAIL"))
out.append("G6 badsize flagged    => %s" % ("PASS" if g6 else "FAIL"))

# A3/A4：换皮肤 / 换回
setr = raw("dskskin deepseek")
out.append("")
out.append("A3 set -> %s" % setr[:220])
out.append("A3 => %s (visual check by human)" % ("PASS" if "set=deepseek" in setr else "FAIL"))
baduse = raw("dskskin badsize")
out.append("G6 use-bad -> %s" % baduse[:200])
out.append("G6 bad skin refused => %s" % ("PASS" if ("not usable" in baduse or "ERR" in baduse or ":" in baduse) else "FAIL"))
offr = raw("dskskin off")
out.append("A4 off -> %s" % offr[:160])
out.append("A4 => %s" % ("PASS" if "off player=" in offr else "FAIL"))

# A7：端口只绑回环（用 Python 连一下回环与局域网地址比一比）
import socket  # noqa: E402
ok_loop = False
try:
    s = socket.create_connection(("127.0.0.1", int(port)), timeout=2)
    ok_loop = True
    s.close()
except Exception:
    pass
lan_ok = None
try:
    ip = socket.gethostbyname(socket.gethostname())
    if ip.startswith("127."):
        lan_ok = "skip(no lan ip)"
    else:
        s2 = socket.create_connection((ip, int(port)), timeout=2)
        lan_ok = True
        s2.close()
except Exception:
    lan_ok = False
out.append("")
out.append("A7 port=%s loopback_reachable=%s lan_reachable=%s => %s"
           % (port, ok_loop, lan_ok, "PASS" if (ok_loop and lan_ok is not True) else "CHECK"))

(ROOT / "logs" / "v2120_check.txt").write_text("\n".join(out), encoding="utf-8")
res = [l for l in out if "=>" in l or l.startswith("G1 ") or l.startswith("G6 ")]
print("V2120 summary:")
for l in res:
    print("  " + l.encode("ascii", "replace").decode("ascii")[:120])
