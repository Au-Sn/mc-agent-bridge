#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dsh_live2.py —— ★一步定下 SDK 的真实形状★（不猜 ✗ 直接试 ✓ 全落盘 ✓）

上一轮拿到的关键错误 ✓：
    session/prompt -> -32603: agent id "undefined" does not match session id "session-1"
⇒ 反推 ✓：服务端**自己**有会话 `session-1` ✓，而它要一个 **agent id** ✗（我给的名字不对 ✓）
⇒ 本轮 ✓：按**候选名依次试** ✓（agentId / agent / sessionId+agentId … ✓）谁不报 undefined 就用谁 ✓
   成了一句之后 ✓ **继续收 20 秒事件** ✓ ⇒ 顺便把 `SessionEvent` 的真实形状拿到 ✓✓

产出：logs/live2.jsonl（每条原始帧 ✓）＋ 控制台 ASCII 摘要 ✓
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
LOG = ROOT / "logs" / "live2.jsonl"
# ★不写死本机 node 路径✗★：用环境变量 DSH_NODE > PATH；都没有 ⇒ 明确报错退出
NODE = os.environ.get("DSH_NODE", "")
PROVIDER = "deepseek-official"
MODEL = "deepseek-v4-flash-vision-exp"
TEXT = "只回四个字：协议通了"


def _node() -> str:
    if NODE:
        return NODE
    import shutil
    n = shutil.which("node") or shutil.which("node.exe")
    if not n:
        print("需要配置 DSH_NODE（node 可执行文件路径）或把 node 加进 PATH",
              file=sys.stderr)
        raise SystemExit(2)
    return n


def find_dsh() -> str:
    envf = os.environ.get("DSH_BIN_JS", "")
    if envf and Path(envf).is_file():
        return envf
    cache = Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
    hits = sorted(cache.glob("*/node_modules/@deepseek-ai/dsh/lib/bin.js"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not hits:
        print("需要配置 DSH_BIN_JS（dsh 的 lib/bin.js 路径）或先安装 dsh",
              file=sys.stderr)
        raise SystemExit(2)
    return str(hits[0])


class Live:
    def __init__(self) -> None:
        self.p = subprocess.Popen([_node(), find_dsh(), "--profile", "sdk"], cwd=str(ROOT),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                  errors="replace", bufsize=1)
        self.q: queue.Queue = queue.Queue()
        self.err: list[str] = []
        self.n = 0
        threading.Thread(target=self._out, daemon=True).start()
        threading.Thread(target=self._er, daemon=True).start()
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self.log = LOG.open("w", encoding="utf-8", newline="\n")

    def _rec(self, d: str, line: str) -> None:
        try:
            self.log.write(json.dumps({"t": round(time.time(), 2), "dir": d, "raw": line},
                                      ensure_ascii=False) + "\n")
            self.log.flush()
        except Exception:
            print("★忽略异常（位置已记录，供排查）✗★", file=sys.stderr)

    def _out(self) -> None:
        for line in self.p.stdout:                    # type: ignore[union-attr]
            self._rec("in", line.rstrip("\n"))
            self.q.put(line)

    def _er(self) -> None:
        for line in self.p.stderr:                    # type: ignore[union-attr]
            self.err.append(line.rstrip())
            self._rec("err", line.rstrip())

    def req(self, method: str, params: dict, timeout: float = 25.0) -> dict | None:
        self.n += 1
        raw = json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method,
                          "params": params}, ensure_ascii=False)
        self._rec("out", raw)
        assert self.p.stdin
        self.p.stdin.write(raw + "\n")
        self.p.stdin.flush()
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                m = json.loads(self.q.get(timeout=0.5))
            except queue.Empty:
                if self.p.poll() is not None:
                    return None
                continue
            if m.get("id") == self.n:
                return m
        return None

    def drain(self, seconds: float) -> dict:
        kinds: dict = {}
        samples: dict = {}
        t0 = time.time()
        while time.time() - t0 < seconds:
            try:
                m = json.loads(self.q.get(timeout=1.0))
            except queue.Empty:
                print("★跳过一条坏数据（已记录，供排查）✗★", file=sys.stderr); continue
            k = m.get("method") or ("resp:%s" % m.get("id"))
            kinds[k] = kinds.get(k, 0) + 1
            if k not in samples:
                samples[k] = json.dumps(m, ensure_ascii=False)[:600]
        return {"kinds": kinds, "samples": samples}

    def close(self) -> None:
        try:
            self.req("shutdown", {}, 5.0)
        except Exception:
            pass
        try:
            if self.p.stdin:
                self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()
        self.log.close()


def main() -> int:
    lv = Live()
    try:
        init = lv.req("initialize", {"provider": PROVIDER, "model": MODEL, "cwd": str(ROOT)}, 60.0)
        print("INIT: %s" % json.dumps(init, ensure_ascii=False)[:400])
        if not init or "error" in init:
            for l in lv.err[-4:]:
                print("   ERR: " + l.encode("ascii", "replace").decode("ascii")[:180])
            return 1
        res = init.get("result") or {}
        sid = res.get("sessionId") or res.get("session") or res.get("id")
        print("INIT: result_keys=%s sid=%s" % (sorted(res.keys()), sid))

        # ★候选参数名依次试 ✓（谁不报 undefined 就用谁 ✓）
        cands = []
        for nm in ("agentId", "agent", "id"):
            cands.append((nm, {nm: "session-1", "content": [{"type": "text", "text": TEXT}]}))
            cands.append((nm + "+sid", {nm: "session-1", "sessionId": "session-1",
                                        "content": [{"type": "text", "text": TEXT}]}))
        cands.append(("content-only", {"content": [{"type": "text", "text": TEXT}]}))

        winner = None
        for name, params in cands:
            r = lv.req("session/prompt", params, 20.0)
            s = json.dumps(r, ensure_ascii=False)[:220]
            ok = bool(r and "error" not in r)
            print("TRY %-14s -> %s %s" % (name, "OK" if ok else "err", s))
            if ok:
                winner = (name, params)
                break
        if winner:
            print("WINNER: %s" % winner[0])
            got = lv.drain(20.0)
            print("EVENTS: %s" % json.dumps(got["kinds"], ensure_ascii=False))
            for k, v in list(got["samples"].items())[:6]:
                print("SAMPLE %s: %s" % (k, v.encode("ascii", "replace").decode("ascii")[:300]))
        else:
            print("NO WINNER (all candidates rejected)")
    finally:
        lv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
