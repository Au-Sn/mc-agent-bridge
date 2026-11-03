#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_probe.py —— ★独立探针：不经过 harness，直接跟 mc_mcp.py 说 MCP 协议★

为什么要有它 ✗（纪律①：别猜，要测 ✓）：
  如果只在 harness 里试 ✗，一旦不通就分不清是**协议写错了**还是**接线错了** ✗
  ⇒ 先用这个探针把服务器**单独**验一遍 ✓ 再去验接线 ✓ 失败点唯一的那个 ✓

它做的事：起 mc_mcp.py 子进程 ⇒ `initialize` ⇒ `tools/list` ⇒ 调指定的工具 ⇒ 关掉
输出：`logs/mcp_probe.txt`（UTF-8 ✓ GBK 控制台打不了中文 ✗ 见 P39 ✓）

用法：
    py tools/mcp_probe.py                     # 只列表
    py tools/mcp_probe.py bot_state look      # 顺带调这几个工具
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "logs" / "mcp_probe.txt"
SRV = str(HERE / "mc_mcp.py")


class Client:
    def __init__(self) -> None:
        self.p = subprocess.Popen([sys.executable, "-u", SRV], cwd=str(ROOT),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True,
                                  encoding="utf-8", errors="replace", bufsize=1)
        self.q: queue.Queue = queue.Queue()
        self.err: list[str] = []
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._errreader, daemon=True).start()
        self.n = 0

    def _reader(self) -> None:
        for line in self.p.stdout:            # type: ignore[union-attr]
            self.q.put(line)

    def _errreader(self) -> None:
        for line in self.p.stderr:            # type: ignore[union-attr]
            self.err.append(line.rstrip())

    def send(self, obj: dict) -> None:
        assert self.p.stdin
        self.p.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.p.stdin.flush()

    def call(self, method: str, params: dict | None = None, timeout: float = 240.0) -> dict:
        self.n += 1
        self.send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                line = self.q.get(timeout=0.5)
            except queue.Empty:
                if self.p.poll() is not None:
                    raise RuntimeError("服务器进程已退出 ✗ rc=%s stderr=%s"
                                       % (self.p.returncode, "\n".join(self.err[-5:])))
                continue
            msg = json.loads(line)
            if msg.get("id") == self.n:
                return msg
            # 服务器的通知/日志（正常 ✓）
        raise TimeoutError("等 %s 超时 ✗ %.0fs" % (method, timeout))

    def notify(self, method: str, params: dict | None = None) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        try:
            if self.p.stdin:
                self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def textof(res: dict) -> str:
    try:
        return "\n".join(c.get("text", "") for c in res["result"]["content"])
    except Exception:
        return json.dumps(res, ensure_ascii=False)[:600]


def main(argv: list[str]) -> int:
    lines: list[str] = []

    def say(s: str = "") -> None:
        lines.append(s)
        print(s.encode("ascii", "replace").decode("ascii"))    # 控制台只打 ASCII ✓（P39 ✓）

    c = Client()
    try:
        r = c.call("initialize", {"protocolVersion": "2024-11-05",
                                  "capabilities": {}, "clientInfo": {"name": "probe", "version": "1"}})
        info = (r.get("result") or {}).get("serverInfo") or {}
        say("[1] initialize ✓ serverInfo=%s proto=%s"
            % (info.get("name"), (r.get("result") or {}).get("protocolVersion")))
        c.notify("notifications/initialized")

        r = c.call("tools/list")
        tools = (r.get("result") or {}).get("tools") or []
        say("[2] tools/list ✓ 共 %d 个" % len(tools))
        for t in tools:
            say("      - %-16s %s" % (t["name"], (t.get("description") or "")[:56]))

        bad = 0
        for name in [a for a in argv if not a.startswith("-")]:
            t0 = time.time()
            r = c.call("tools/call", {"name": name, "arguments": {}})
            iserr = bool((r.get("result") or {}).get("isError"))
            if iserr:
                bad += 1
            say()
            say("[3] call %s ⇒ %.1fs ｜ isError=%s" % (name, time.time() - t0, iserr))
            say(textof(r)[:1200])
        say()
        say("[4] 服务器 stderr 最后几行：")
        for ln in c.err[-6:]:
            say("      " + ln)
    finally:
        c.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    # ★最后这行必须纯 ASCII★ ✗ —— 实测：写中文/`✓` 到 GBK 控制台会
    #   `UnicodeEncodeError` 把整个探针的退出码搞成 1 ✗（探针本身其实全过了 ✓ 见 P39 ✓）
    print("[probe] details written to %s (UTF-8)" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
