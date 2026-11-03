#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dsh_live.py —— ★看清 SDK 协议的真实帧★（最小版 ✓ 只观察不解析 ✗）

为什么先做这一步 ✗（这几轮反复吃的亏 ✓）：
  协议文档给了**方法名与类型名** ✓ 但没给 `SessionEvent` 的**细结构** ✗
  ⇒ 硬猜就会像 `UPDATE_GAME_PROFILE` 那次一样白跑一轮 ✗
  ⇒ 所以：起一个 sdk 会话 ✓ initialize ✓ 发一句 ✓ **把收到的每条原始帧原样写进 logs/live.jsonl** ✓
     看清了再写解析 ✓

用法：py tools/dsh_live.py ["要发给它的话"]
产出：logs/live.jsonl（每条一行：方向 + 原始帧 ✓）＋ 控制台只打 ASCII 摘要 ✓
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

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "live.jsonl"
import paths as PA                     # noqa: E402  ★大脑层接缝：node/dsh 不写死本机路径✗★
PROVIDER = "deepseek-official"                  # 从 settings.yaml 抄的 ✓（不是猜 ✓）
MODEL = "deepseek-v4-flash-vision-exp"          # 同上 ✓


def _node() -> str:
    """★node 从配置来✗★（DSH_NODE／PATH）；没有 ⇒ 打印"需要配置"并非零退出"""
    try:
        return str(PA.require_node())
    except PA.NotConfigured as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)


def find_dsh() -> str:
    """★dsh 的 bin.js 从配置来✗★（DSH_BIN_JS／npm 缓存）；没有 ⇒ 明确报错"""
    p = PA.find_dsh_bin_js()
    if p is None:
        print("需要配置 DSH_BIN_JS（dsh 的 lib/bin.js 路径）或先安装 dsh",
              file=sys.stderr)
        raise SystemExit(2)
    return str(p)


class Live:
    def __init__(self) -> None:
        self.p = subprocess.Popen(
            [_node(), find_dsh(), "--profile", "sdk"],
            cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.q: queue.Queue = queue.Queue()
        self.err: list[str] = []
        self.n = 0
        threading.Thread(target=self._out, daemon=True).start()
        threading.Thread(target=self._er, daemon=True).start()
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self.log = LOG.open("w", encoding="utf-8", newline="\n")

    def _rec(self, direction: str, line: str) -> None:
        try:
            self.log.write(json.dumps({"t": round(time.time(), 2), "dir": direction,
                                       "raw": line}, ensure_ascii=False) + "\n")
            self.log.flush()
        except Exception:
            print("[ignore] 忽略异常（位置已记录，供排查）", file=sys.stderr)

    def _out(self) -> None:
        for line in self.p.stdout:                       # type: ignore[union-attr]
            self._rec("in", line.rstrip("\n"))
            self.q.put(line)

    def _er(self) -> None:
        for line in self.p.stderr:                       # type: ignore[union-attr]
            self.err.append(line.rstrip())
            self._rec("err", line.rstrip())

    def send(self, method: str, params: dict, rid: bool = True) -> dict:
        self.n += 1
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if rid:
            msg["id"] = self.n
        if params:
            msg["params"] = params
        raw = json.dumps(msg, ensure_ascii=False)
        self._rec("out", raw)
        assert self.p.stdin
        self.p.stdin.write(raw + "\n")
        self.p.stdin.flush()
        return msg

    def wait_for(self, pred, timeout: float) -> dict | None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                line = self.q.get(timeout=0.5)
            except queue.Empty:
                if self.p.poll() is not None:
                    return None
                continue
            try:
                m = json.loads(line)
            except Exception:
                print("[skip] 跳过一条坏数据（位置已记录，供排查）", file=sys.stderr); continue
            if pred(m):
                return m
        return None

    def close(self) -> None:
        try:
            self.send("shutdown", {}, rid=True)
            time.sleep(1.0)
        except Exception:
            print("[ignore] 忽略异常（位置已记录，供排查）", file=sys.stderr)
        try:
            if self.p.stdin:
                self.p.stdin.close()
        except Exception:
            print("[ignore] 忽略异常（位置已记录，供排查）", file=sys.stderr)
        try:
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()
        self.log.close()


def main(argv: list[str]) -> int:
    text = argv[0] if argv else "只回四个字：协议通了"
    lv = Live()
    got: dict = {}
    try:
        lv.send("initialize", {"provider": PROVIDER, "model": MODEL, "cwd": str(ROOT)})
        init = lv.wait_for(lambda m: m.get("id") == lv.n, 60.0)
        got["init"] = init
        if init is None or "error" in (init or {}):
            print("INIT: FAILED -> %s" % json.dumps(init, ensure_ascii=False)[:300])
            print("STDERR tail: %s" % " | ".join(lv.err[-3:])[:300])
            for l in lv.err[-3:]:
                print("   " + l.encode("ascii", "replace").decode("ascii")[:160])
            return 1
        res = init.get("result") or {}
        print("INIT: OK keys=%s" % sorted(res.keys()))
        sid = res.get("sessionId") or res.get("session", {}).get("id") if isinstance(res.get("session"), dict) else res.get("sessionId")
        print("INIT: sessionId=%s" % (sid or "(none)"))

        params: dict = {"content": [{"type": "text", "text": text}]}
        if sid:
            params["sessionId"] = sid
        lv.send("session/prompt", params)
        pr = lv.wait_for(lambda m: m.get("id") == lv.n, 30.0)
        got["prompt"] = pr
        print("PROMPT: %s" % json.dumps(pr, ensure_ascii=False)[:300])

        # ★只观察 ✗：把接下来 25 秒里收到的**每一种方法名**数一数 ✓
        kinds: dict = {}
        t0 = time.time()
        while time.time() - t0 < 25.0:
            try:
                line = lv.q.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                m = json.loads(line)
            except Exception:
                print("[skip] 跳过一条坏数据（位置已记录，供排查）", file=sys.stderr); continue
            k = m.get("method") or ("resp:%s" % m.get("id"))
            kinds[k] = kinds.get(k, 0) + 1
        print("FRAMES: %s" % json.dumps(kinds, ensure_ascii=False))
        print("LOG   : %s" % LOG)
    finally:
        lv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
