#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""direct.py -- ★直连：Python ⇄ 模组（★经 127.0.0.1:8766 ✗ **不经过 CC 计算机**✗★）

用户口径（原话）：
  「后续应当简化该流程，能不能优化成**直连**」

为什么值得做（2026-11-01 的事故）：
  ★原来是 Python → 网关 → **CC 计算机** → 模组** ⇒
  ★那次 fill 把 CC 计算机填掉 ⇒ **整套系统断线** ✗ ⇒
  ★2.53.0 起模组**自己开一个 HTTP 口** ⇒ Python **直连游戏** ⇒ ★少一个会坏的环节✗★ ✓

协议（★刻意最简✗★）：
    POST http://127.0.0.1:8766/cmd    body = 指令原文（UTF-8）⇒ 回模组回执文本
    GET  http://127.0.0.1:8766/health ⇒ "ok dshbridge-http"

接口：
    health(timeout)      -> str 或 None
    post(cmd, timeout)   -> str 或 None（★None ＝ 连不上 ✗ 调用方自己决定后备✗★）
    available()          -> bool（★快 ✗ 300ms 超时✗★）
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8766"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
def _req(path: str, data: bytes = None, timeout: float = 30.0):
    url = BASE + path
    req = urllib.request.Request(url, data=data, method=("POST" if data is not None else "GET"))
    _tok = token()
    if _tok: req.add_header("X-DSH-Token", _tok)
    if data is not None:
        req.add_header("Content-Type", "text/plain; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:      # ★服务器在 ✗ 但报错 ✗ 要如实说✗★
        try:
            return exc.read().decode("utf-8", errors="replace")
        except Exception:
            return None
    except Exception:
        return None


def health(timeout: float = 2.0):
    return _req("/health", timeout=timeout)


def post(cmd: str, timeout: float = 30.0):
    """★发一条指令 ✗ 回执文本✗★（★连不上回 None ✗ 不抛异常✗★）"""
    if not (cmd or "").strip():
        return None
    return _req("/cmd", data=cmd.strip().encode("utf-8"), timeout=timeout)


def available(timeout: float = 0.3) -> bool:
    h = health(timeout=timeout)
    return bool(h and "ok" in h)


def main(argv) -> int:
    if argv and argv[0] == "--health":
        h = health()
        print("DIRECT health=%r" % (h,))
        return 0 if h else 1
    if argv:
        r = post(" ".join(argv))
        print("DIRECT reply=%r" % (r,))
        return 0 if r is not None else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

def raw(cmd: str, timeout: float = 30.0):
    """★以**服务器身份**跑一条命令✗★（2.54.0 的 /raw）✗
    ★用途✗★：★player Bot spawn 这类★还没有假人★的命令 ✓
    """
    if not (cmd or "").strip():
        return None
    return _req("/raw", data=cmd.strip().encode("utf-8"), timeout=timeout)


# ══ ★★2.56.0（A3）✗★★ token：模组在 `config/dshbridge/http_token.txt` 生成/读取 ✓
#   ★为什么放在文件尾✗★：本文件 1~92 行的行号被 silent_except 的机器白名单按行号锚住 ✗
#   （`state/silent_allow.json` 里 tools/direct.py 的 47/49 两处）⇒ 中间插行会让白名单错位 ✗
#   ⇒ 新逻辑**只追加** ✓；对外 API（health/post/raw/available）**一个都没变** ✓
def _game_dir() -> str:
    import os
    # ★默认实例 + env 覆盖✗★（与全仓其它工具同一口径 ✓）
    return (os.environ.get("DSH_GAME_DIR")
            or r"D:\pcl2\.minecraft\versions\All the Mods 9 - To the Sky - atm9sky")


def _token_files():
    """token 候选路径（★有顺序✗★）：env 文件 → 游戏实例 config → 项目 state/ → 当前目录 config"""
    import os
    from pathlib import Path
    envf = (os.environ.get("DSH_HTTP_TOKEN_FILE") or "").strip()
    if envf:
        yield Path(envf)
    yield Path(_game_dir()) / "config" / "dshbridge" / "http_token.txt"
    yield Path(__file__).resolve().parent.parent / "state" / "http_token.txt"
    yield Path("config") / "dshbridge" / "http_token.txt"


_TOKEN_CACHE = {"file": None, "mtime": None, "token": "", "notes": []}


def refresh_token():
    """丢掉 token 缓存（换 env/换文件后调用；判据用）✓ 返回 None ✓"""
    _TOKEN_CACHE.update({"file": None, "mtime": None, "token": "", "notes": []})


def token() -> str:
    """当前 token ✓（找不到就回 "" ⇒ 请求照发、不带头 —— 老模组不认这个头，不破坏别人）"""
    import os
    v = (os.environ.get("DSH_HTTP_TOKEN") or "").strip()
    if v:
        return v
    for p in _token_files():
        try:
            st = p.stat()
        except OSError as exc:
            _TOKEN_CACHE["notes"].append("skip %s: %r" % (p, exc))
            continue
        if _TOKEN_CACHE["file"] == str(p) and _TOKEN_CACHE["mtime"] == st.st_mtime:
            return _TOKEN_CACHE["token"]
        try:
            t = p.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            _TOKEN_CACHE["notes"].append("read %s: %r" % (p, exc))
            continue
        if not t:
            _TOKEN_CACHE["notes"].append("empty %s" % (p,))
            continue
        _TOKEN_CACHE.update({"file": str(p), "mtime": st.st_mtime, "token": t})
        return t
    return ""

