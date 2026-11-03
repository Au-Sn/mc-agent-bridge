#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
http_proxy.py — 极简本地转发代理（唯一目的：让 Gradle 能下载）

为什么需要（实测数据 ✓ 不是猜的 ✗）：
    从同一台机器、同一时刻发起请求：
      * curl   → maven.minecraftforge.net 的 ForgeGradle 制品  ✓ 拿到
      * python → bmclapi2.bangbang93.com / services.gradle.org   ✓ 拿到
      * python → maven.minecraftforge.net                        ✗ HTTP 403 Forbidden
      * Gradle(Java) → 上述两个仓库                              ✗ 全部失败
    ⇒ 出口本身是通的 ✓ 只有 **Java/Gradle 那条通道**不行 ✗
    ⇒ 那就让 Gradle 把流量交给 Python 代跑 ✓：
        gradle -Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=8788 …

实现：一个最小的转发代理
    * CONNECT（HTTPS 隧道）✓ —— Gradle 的 https 请求走这条
    * 明文 HTTP 也转 ✓（保险起见）
用法：py tools/http_proxy.py 8788
"""

from __future__ import annotations

import select
import socket
import sys
import threading
from urllib.parse import urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def pipe(a: socket.socket, b: socket.socket) -> None:
    """两个 socket 之间来回搬运字节，直到任一端关闭 ✓"""
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 30)
            if not r:
                continue
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except Exception:
                pass


def handle(client: socket.socket) -> None:
    try:
        req = b""
        while b"\r\n\r\n" not in req:
            chunk = client.recv(4096)
            if not chunk:
                return
            req += chunk
        first = req.split(b"\r\n", 1)[0].decode("latin1")
        parts = first.split(" ")
        if len(parts) < 2:
            return
        method, target = parts[0], parts[1]

        if method.upper() == "CONNECT":
            host, _, port = target.partition(":")
            upstream = socket.create_connection((host, int(port or 443)), timeout=30)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            print("[proxy] CONNECT %s" % target, flush=True)
            pipe(client, upstream)
        else:
            u = urlparse(target)
            upstream = socket.create_connection((u.hostname, u.port or 80), timeout=30)
            path = u.path + (("?" + u.query) if u.query else "")
            head = req.split(b"\r\n")
            head[0] = ("%s %s HTTP/1.1" % (method, path)).encode()
            upstream.sendall(b"\r\n".join(head))
            print("[proxy] %s %s" % (method, u.hostname), flush=True)
            pipe(client, upstream)
    except Exception as e:  # noqa: BLE001
        print("[proxy] 失败: %r" % (e,), flush=True)
        try:
            client.close()
        except Exception:
            pass


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(64)
    print("[proxy] 已监听 127.0.0.1:%d（Gradle 请用 -Dhttps.proxyHost/Port）" % port, flush=True)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    raise SystemExit(main())
