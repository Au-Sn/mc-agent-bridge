#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_mod.py — 下载模组 jar / 任意文件，并校验哈希

为什么不用 curl / Invoke-WebRequest：
  本环境的沙箱禁止执行 curl.exe，Invoke-WebRequest 在部分网络下会中途断流。
  用 Python 标准库 urllib 最稳，且能顺便做完整性校验。

用法：
    py tools/fetch_mod.py <URL> <保存路径> [期望SHA1] [期望大小]

例：
    py tools/fetch_mod.py \
       "https://cdn.modrinth.com/data/SOw6jD6x/versions/h2HTYvNe/AdvancedPeripherals-1.20.1-0.7.46r.jar" \
       "downloads/AdvancedPeripherals-1.20.1-0.7.46r.jar" \
       "4a498b6afd73f43ae3a9bb7591208fe026b36e2c" 889945
"""

from __future__ import annotations

import hashlib
import os
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    url, out = argv[0], argv[1]
    want_sha1 = argv[2].lower() if len(argv) > 2 and argv[2] else None
    want_size = int(argv[3]) if len(argv) > 3 and argv[3] else None

    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)

    print("GET %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "mc-agent-bridge/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            status = resp.status
            total = int(resp.headers.get("Content-Length") or 0)
            print("HTTP %s   大小 %d 字节" % (status, total))
            h = hashlib.sha1()
            got = 0
            with open(out, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
    except urllib.error.HTTPError as e:
        print("[X] HTTP 错误：%s %s" % (e.code, e.reason))
        return 1
    except Exception as e:
        print("[X] 下载失败：%r" % (e,))
        print("    常见原因：沙箱禁止该程序联网 / 代理拦截 / TLS 拦截")
        return 1

    print("已保存 %s（%d 字节）" % (out, got))
    sha1 = h.hexdigest()
    print("SHA1      : %s" % sha1)

    ok = True
    if want_sha1:
        print("期望 SHA1 : %s" % want_sha1)
        if sha1 != want_sha1:
            print("[X] 哈希不匹配，文件可能损坏或被篡改，请勿使用")
            ok = False
        else:
            print("[OK] 哈希校验通过")
    if want_size and got != want_size:
        print("[X] 大小不符：实际 %d，期望 %d" % (got, want_size))
        ok = False

    # Jar 应当是 zip（PK 魔数）
    if out.lower().endswith(".jar"):
        with open(out, "rb") as fh:
            magic = fh.read(2)
        print("ZIP 魔数  : %r（应为 b'PK'）" % magic)
        if magic != b"PK":
            print("[X] 不是有效的 jar/zip")
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
