#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""skin_server.py —— ★给客户端拉皮肤用的本地 HTTP 服务★ ✓（纯标准库 ✓）

为什么需要它 ✗（2026-09-20 实测结论 ✓）：
  · 假人的 UUID 是 **v4**（`49e96464-…-46b3-…` ✓）而名字 "Bot" 的**离线** UUID 是 v3
    （`bb19ef2f-2f95-39a8-8bad-bda3ed373847` ✓）⇒ **两者不同** ✗
    ⇒ 说明这个假人挂的是**真实身份** ⇒ 客户端会按那个身份拉**真皮肤** ✗
    ⇒ 所以"覆盖默认皮肤"的资源包**对它天然无效** ✗（包加载成功也没用 ✓ 已实测 ✓）
  · 正解 ✓：由模组给它的 GameProfile 塞一个 `textures` 属性 ✓
    属性里是一段 base64 的 JSON：`{"textures":{"SKIN":{"url":"<这个服务提供的地址>"}}}`
    ⇒ 客户端会**自己去这个 URL 拉 PNG** ✓ ⇒ 于是我们得有个地方放 PNG ✓ ⇒ 就是这个服务 ✓

★最值钱的一点★ ✓：**访问日志就是判据** ✓
  · 客户端真去拉了 ⇒ 日志里会出现一条 `GET /deepseek.png` ✓ ⇒ 注入成功 ✓✓
  · 日志一直空 ⇒ 说明客户端**根本没认那个 URL** ✗（很可能是它拒绝非 https ✗）
  ⇒ 这条判据**不用猜** ✓ 一眼就能分叉 ✓

用法：
    py tools/skin_server.py                 # 默认 127.0.0.1:8791，根目录 = 仓库的 skins/
    py tools/skin_server.py --port 8899 --root <目录>
    py tools/skin_server.py --probe         # ★只自检一次★：起服务 → 自己拉一张 → 报结果 → 退出 ✓
"""
from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
import threading
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_ROOT = ROOT / "skins"

try:
    # ★控制台必须重配 UTF-8★ ✗（见 tools/persona.py 的注释 ✓ 我踩过两次 ✓）
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)   # type: ignore[attr-defined]
except Exception:
    pass


class Handler(http.server.SimpleHTTPRequestHandler):
    """普通静态文件 ✓ 但**每条请求都大声打出来** ✓（它就是判据 ✓）

    ⚠ 别用 `global` 改模块常量 ✗ —— 实测（2026-09-20 ✓）：`global DEFAULT_ROOT` 写在
      `str(DEFAULT_ROOT)` 之后 ⇒ `SyntaxError: name 'DEFAULT_ROOT' is used prior to
      global declaration` ✗ ⇒ 整个脚本**一行都没跑起来** ✗
      ⇒ 改成**类属性** ✓（`Handler.root_dir = …` ✓ 不需要 global ✓）
    """

    root_dir = str(DEFAULT_ROOT)

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=Handler.root_dir, **kw)

    def log_message(self, fmt: str, *args) -> None:
        print("[skin] %s - %s" % (self.address_string(), fmt % args), flush=True)

    def do_GET(self) -> None:                      # noqa: N802
        print("[skin] ★客户端来拉了★ path=%s ua=%s"
              % (self.path, self.headers.get("User-Agent")), flush=True)
        super().do_GET()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--probe", action="store_true", help="起服务、自己拉一张、报结果、退出")
    a = ap.parse_args(argv)

    root = Path(a.root)                 # ★不要用 global 改模块常量★ ✗（见 Handler 的注释 ✓）
    if not root.is_dir():
        print("[X] 根目录不存在 ✗：%s" % root)
        return 2
    Handler.root_dir = str(root)
    files = sorted(p.name for p in root.glob("*.png"))
    print("[skin] 根目录 = %s" % root)
    print("[skin] 可拉的 PNG：%s" % (", ".join(files) if files else "（一张都没有 ✗）"))

    srv = Server((a.host, a.port), Handler)
    base = "http://%s:%d/" % (a.host, a.port)
    print("[skin] 服务已起 ✓ %s（Ctrl+C 退 ✓）" % base)
    for f in files:
        print("[skin]   %s%s" % (base, f))

    if a.probe:
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        name = files[0] if files else None
        if not name:
            print("[X] 没有 PNG 可测 ✗")
            srv.shutdown()
            return 2
        try:
            with urllib.request.urlopen(base + name, timeout=5) as r:
                data = r.read()
            print("[probe] 自拉 %s ⇒ %d 字节 ✓ 状态 %s ✓" % (name, len(data), r.status))
        except Exception as e:
            print("[probe] [X] 自拉失败 ✗：%s" % e)
            srv.shutdown()
            return 1
        srv.shutdown()
        print("[probe] 服务本身没问题 ✓（★客户端来不来拉，还得看它认不认这个 http 地址★ ✓）")
        return 0

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[skin] 退出 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
