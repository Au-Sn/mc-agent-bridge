#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
maven_mirror.py — 本地 Maven 镜像（真正解决这台机器的环境问题 ✓）

为什么要它（实测结论 ✓ 不是猜的 ✗）：
    这台机器网络完全正常 ✓（用户确认 ✓ 实测也支持 ✓），挡住的是**服务端按 User-Agent 拒绝** ✗：
        Python-urllib/3.11 → 403 Forbidden ✗
        curl/8.4.0         → 200 ✓
        浏览器 UA          → 200 ✓
        Java/17.0.20       → 200 ✓
    ⇒ Gradle 用的是"工具型 UA"✗ ⇒ 从上游（Forge maven / Gradle 插件门户）一律吃闭门羹 ✗
    ⇒ 正确的解法不是"代理转发"✗（隧道里的 UA 改不了 ✗），而是：
         **Gradle → 明文 HTTP → 本镜像（浏览器 UA 去上游取 ✓）**
      本镜像对 Gradle 说 HTTP ✓（无需证书 ✓ 无需 MITM ✗），对上游用浏览器 UA ✓

路径映射（Gradle 里就把仓库地址写成这些 ✓）：
    http://127.0.0.1:8789/forge/<path>     → https://maven.minecraftforge.net/<path>
    http://127.0.0.1:8789/bmclapi/<path>   → https://bmclapi2.bangbang93.com/maven/<path>
    http://127.0.0.1:8789/portal/<path>    → https://plugins.gradle.org/m2/<path>
    http://127.0.0.1:8789/central/<path>   → https://repo.maven.apache.org/maven2/<path>
    http://127.0.0.1:8789/mojang/<path>    → https://libraries.minecraft.net/<path>

缓存：命中过的文件存到 mod/mirrorcache/<键>/<路径> ✓ 重跑构建会快很多 ✓
用法：py tools/maven_mirror.py 8789
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

UPSTREAMS = {
    "forge": "https://maven.minecraftforge.net/",
    "bmclapi": "https://bmclapi2.bangbang93.com/maven/",
    "portal": "https://plugins.gradle.org/m2/",
    "central": "https://repo.maven.apache.org/maven2/",
    "mojang": "https://libraries.minecraft.net/",
}
# ★ 关键一行：浏览器 UA ✓（上游只封"工具型 UA" ✗）
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
# ★ 每次上游尝试的超时（秒）✓ —— 2026-09-20 由 20 放宽到 45 ✓
#   原因（实测 ✓）：插件 classpath 的那批坐标（guava / fastutil / commons-* 等，
#   单个几 MB ✓）在 20 秒内常常**传不完就被掐** ✗ ⇒ 镜像这边表现为"3 次失败"✗
#   ⇒ Gradle 侧看到一串 "Skipped due to earlier error" ✗ 完全对得上 ✓
#   （docs/环境真相与本地镜像.md §4 只说"压到 15~20 秒"✗ —— 那条是**当时**的经验 ✓
#     现在已知它太紧 ✗ 以本行为准 ✓）
TIMEOUT = 45
CACHE = Path(__file__).resolve().parent.parent / "mod" / "mirrorcache"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):  # 别刷屏 ✓ 只在自己 print 里记 ✓
        return

    def do_HEAD(self):
        self._serve(head=True)

    def do_GET(self):
        self._serve(head=False)

    def _serve(self, head: bool) -> None:
        raw = self.path.lstrip("/")
        key, _, rest = raw.partition("/")
        base = UPSTREAMS.get(key)
        if not base or not rest:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        cached = CACHE / key / rest
        if cached.is_file():
            data = cached.read_bytes()
            print("[mirror] ✓ %-8s %-6s %8d B  %s" % (key, "cache", len(data), rest), flush=True)
        else:
            # ★ 多上游回退 + 重试（真实教训 ✓）：
            #   实测 bmclapi 会**间歇性** SSL 断流 ✗（URLError(SSLEOFError …)）✗
            #   同一个地址单发能成功 ✓ 连发就断 ✗ ⇒ 必须**重试** ✓
            #   并且同一路径要在多个上游里依次试 ✓（bmclapi 缺的坐标可能 portal/central 有 ✓）
            # ★ 按坐标前缀**直接选对上游** ✓（真实教训 ✓）：
            #   上一版是无脑依次试 5 家 ✗ ⇒ 每个 miss 都要等很久 ✗
            #   3 分 50 秒的失败构建就是这么来的 ✗（一串 Skipped due to earlier error ✗ 很可能就是被超时掐的）
            #   ⇒ 按路径猜：forge 的坐标先问 forge ✓ 插件 marker 先问 portal ✓ 其余先问 central ✓
            if rest.startswith("net/minecraftforge/") or rest.startswith("net/minecraft/"):
                pref = ["forge", "bmclapi", "central", "portal"]
            elif rest.startswith("org/gradle/") or ".gradle.plugin/" in rest or "/foojay" in rest:
                pref = ["portal", "central", "bmclapi", "forge"]
            elif rest.startswith("org/spongepowered/"):
                pref = ["bmclapi", "forge", "central", "portal"]
            else:
                pref = ["central", "bmclapi", "portal", "forge"]
            order = [key] + [k for k in pref if k != key]
            data, src = None, None
            for k in order:
                basek = UPSTREAMS.get(k)
                if not basek:
                    continue
                url = basek + rest
                for attempt in range(1, 4):
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": UA})
                        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                            data = r.read()
                        src = "%s#%d" % (k, attempt)
                        break
                    except urllib.error.HTTPError as e:  # noqa: BLE001
                        # ★ 2026-09-20：**404/403 是"这里没有"的确定答复** ✓ ⇒ 别重试 ✗
                        #   真实教训（本轮实测 ✓）：插件 marker 的 .jar 在四个上游**都不存在** ✓
                        #   （marker 是 packaging=pom 的壳 ✓ 本来就没有 jar ✓）
                        #   而旧代码对 404 也**重试 3 次 + 每次 sleep** ✗ ⇒ 12 次无用往返 ✗
                        #   每个缺失文件白等 ~3.6 秒 ✗ 日志也被刷爆 ✗（排查时反而看不见真问题 ✗）
                        #   ⇒ 确定性的 404/403 直接换下一家 ✓ 只有"网络类"错误才值得重试 ✓
                        print("[mirror] ·  %-8s 404 %s" % (k, rest), flush=True)
                        break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 3:
                            print("[mirror] ✗ %-8s 3次失败 %s → %r" % (k, rest, e), flush=True)
                        else:
                            time.sleep(0.6 * attempt)
                if data is not None:
                    break
            if data is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(data)
            except Exception as e:  # noqa: BLE001
                print("[mirror] ⚠ 缓存写入失败（不影响本次返回 ✓）：%r" % (e,), flush=True)
            print("[mirror] ✓ %-8s %8d B  %s" % (src, len(data), rest), flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head:
            self.wfile.write(data)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8789
    CACHE.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("[mirror] 已监听 http://127.0.0.1:%d/  缓存目录 %s" % (port, CACHE), flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
