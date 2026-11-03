#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dsh_live3.py —— 扫"agent 标识字段名 × content 形状"（不猜 ✓ 直接试 ✓）

已知 ✓（上一轮实测）：
  · initialize 成功 ✓ 但不返回 sessionId ✓
  · 带 sessionId 时错误变成 `reading 'filter'` ⇒ sessionId 被认 ✓ 缺的是**下一处** ✓
  · 不带 sessionId 时每次都新建会话 ✓ 报 `agent id "undefined"` ⇒ 还缺 agent 标识 ✓
本轮 ✓：把可能的字段名（agentId/agent/agent_id/agentName/id/name ✓）与
        content 的几种形状（字符串 ✓ blocks ✓ messages ✓ content ✓）依次组合 ✓
        谁先不报错就用谁 ✓ 然后收 20 秒事件看清 SessionEvent ✓
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
LOG = ROOT / "logs" / "live3.jsonl"
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
        for line in self.p.stdout:                  # type: ignore[union-attr]
            self._rec("in", line.rstrip("\n"))
            self.q.put(line)

    def _er(self) -> None:
        for line in self.p.stderr:                  # type: ignore[union-attr]
            self.err.append(line.rstrip())
            self._rec("err", line.rstrip())

    def clean(self) -> None:
        """把队列里残留的响应/通知倒掉 ✓（免得下一个 req 认错回执 ✗）"""
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                return

    def req(self, method: str, params: dict, timeout: float = 20.0) -> dict | None:
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
            # 别的帧（通知）先记着 ✓ 但这里不阻塞 ✓
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
            samples.setdefault(k, json.dumps(m, ensure_ascii=False)[:700])
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
        print("INIT: %s" % json.dumps(init, ensure_ascii=False)[:300])
        if not init or "error" in init:
            return 1

        agent_names = ["agentId", "agent", "agent_id", "agentName", "name"]
        contents = [
            ("blocks", [{"type": "text", "text": TEXT}]),
            ("string", TEXT),
            ("messages", [{"role": "user", "content": TEXT}]),
        ]
        winner = None
        for an in agent_names:
            lv.clean()
            r = lv.req("session/prompt", {an: "default",
                                          "content": [{"type": "text", "text": TEXT}]}, 15.0)
            msg = json.dumps(r, ensure_ascii=False)
            print("TRY %-10s -> %s" % (an, msg[:170]))
            if r and "agent id" not in msg:
                winner = (an, "blocks")
                break
        if winner is None:
            print("NO AGENT FIELD WORKED")
            for l in lv.err[-3:]:
                print("  ERR: " + l.encode("ascii", "replace").decode("ascii")[:170])
            return 0

        an = winner[0]
        print("AGENT FIELD = %s" % an)
        # 再用几种 content 形状确认 ✓
        for cname, cval in contents:
            lv.clean()
            r = lv.req("session/prompt", {an: "default", "content": cval}, 15.0)
            msg = json.dumps(r, ensure_ascii=False)
            print("CONTENT %-9s -> %s" % (cname, msg[:190]))
            if r and "error" not in r:
                print("WINNER CONTENT = %s" % cname)
                got = lv.drain(20.0)
                print("EVENTS: %s" % json.dumps(got["kinds"], ensure_ascii=False))
                for k, v in list(got["samples"].items())[:5]:
                    print("SAMPLE %s: %s" % (k, v.encode("ascii", "replace").decode("ascii")[:280]))
                break
    finally:
        lv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
