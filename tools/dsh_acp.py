#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dsh_acp.py —— ★常驻 ACP 客户端★（把"假人的思维"接进 harness 的持久会话 ✓）

依据 ✓（全部**读自文档**✗ 不是记忆）：
  `dsh-acp-app`：初始化 → 用**绝对 cwd** 建 session → 选 `model`/`reasoning_effort` →
                 观察**标准语义更新** → 提交提示词 → `session/close` ✓
  `dsh-acp`   ：`session/new`＝全新持久 agent ✓｜`session/resume`＝恢复**已持久且非活跃**会话，
                **恢复日志但不回放旧更新** ✓｜`session/prompt`＝**每个会话一次一个提示词**，
                **Agent 空闲且有序更新交付后才结算** ✓｜`session/update`＝assistant 消息/thought/
                工具生命周期/配置变化/上下文用量，**按会话串行交付** ✓
                ｜`session/request_permission`＝**客户端可以自动回答** ✓（不答会卡住 ✗）
  ⇒ 设计要点 ✓：① 宽容解析（未知 update 一律当无事 ✓ 全帧落盘 ✓）
               ② **权限请求自动允许** ✗（否则长活会停在半路 ✓）
               ③ ACP 是公开协议 ✓ 所以"方法名/握手形状"照 ACP v1 写 ✓ 不逆向 ✗

用法：
  py tools/dsh_acp.py --probe "只回四个字：协议通了"   # 起会话 + 发一句 + 落盘所有帧 + 打 ASCII 摘要
产出：logs/acp.jsonl（每条原始帧 ✓）
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
LOG = ROOT / "logs" / "acp.jsonl"
SESSION_META = ROOT / "logs" / "acp_session.json"
import paths as PA                     # noqa: E402  ★大脑层接缝：node/dsh 不写死本机路径✗★


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


class Acp:
    def __init__(self, log_path: Path = LOG) -> None:
        # ★v2.14.1：剖面可换★ ✗ —— 实测：原版 `acp` 剖面**没有** mc 工具 ✓
        #   （问它"有哪些工具" ⇒ 它自己回答 `NO_MC_TOOLS` ✓ ⇒ 不是"不干"✗ 是"没有手"✗）
        #   默认用 `mcacp`（＝acp 的复制 ＋ 装了我们的 MCP ✓ 并关掉 shell/文件 ✓）
        self.profile = os.environ.get("DSH_ACP_PROFILE") or "mcacp"
        self.p = subprocess.Popen([_node(), find_dsh(), "--profile", self.profile], cwd=str(ROOT),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                  errors="replace", bufsize=1)
        self.q: queue.Queue = queue.Queue()
        self.err: list[str] = []
        self.n = 0
        self.session_id: str | None = None
        self.texts: list[str] = []          # 助手已提交的文本（从 update 里攒 ✓）
        self.kinds: dict = {}               # 观察用：每种 update 出现过几次 ✓
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = log_path.open("a", encoding="utf-8", newline="\n")
        threading.Thread(target=self._out, daemon=True).start()
        threading.Thread(target=self._er, daemon=True).start()

    # ── 帧进出 ────────────────────────────────────────────────────────────
    def _rec(self, d: str, line: str) -> None:
        try:
            self.log.write(json.dumps({"t": round(time.time(), 2), "dir": d, "raw": line},
                                      ensure_ascii=False) + "\n")
            self.log.flush()
        except Exception:
            pass

    def _out(self) -> None:
        for line in self.p.stdout:                       # type: ignore[union-attr]
            self._rec("in", line.rstrip("\n"))
            self.q.put(line)

    def _er(self) -> None:
        for line in self.p.stderr:                       # type: ignore[union-attr]
            self.err.append(line.rstrip())
            self._rec("err", line.rstrip())

    def raw_send(self, obj: dict) -> None:
        raw = json.dumps(obj, ensure_ascii=False)
        self._rec("out", raw)
        assert self.p.stdin
        self.p.stdin.write(raw + "\n")
        self.p.stdin.flush()

    def req(self, method: str, params: dict, timeout: float = 60.0) -> dict | None:
        self.n += 1
        self.raw_send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        return self.await_id(self.n, timeout)

    def await_id(self, rid: int, timeout: float) -> dict | None:
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
            if m.get("id") == rid:
                return m
            self.handle(m)                              # 通知/请求：边等边处理 ✓
        return None

    # ── 通知与"服务端发来的请求" ─────────────────────────────────────────
    def handle(self, m: dict) -> None:
        method = m.get("method")
        if not method:
            return
        if method == "session/update":
            self._on_update(m.get("params") or {})
            return
        if method == "session/request_permission":
            # ★必须自动回答 ✗（文档明说客户端可以自动回答 ✓ 不答会卡住 ✓）
            p = m.get("params") or {}
            opts = p.get("options") or []
            pick = None
            for o in opts:                              # 优先挑"允许"类 ✓
                oid = str(o.get("optionId") or o.get("id") or "")
                if any(k in oid.lower() for k in ("allow", "yes", "accept", "approve", "once", "ok")):
                    pick = oid
                    break
            if pick is None and opts:
                pick = str(opts[0].get("optionId") or opts[0].get("id") or "")
            if m.get("id") is not None:
                self.raw_send({"jsonrpc": "2.0", "id": m["id"],
                               "result": {"outcome": {"outcome": "selected", "optionId": pick}}})
            self._rec("note", "auto-answered permission with %s" % pick)
            return
        # 其它通知：只观察 ✓ 不回 ✓

    def _on_update(self, params: dict) -> None:
        if params.get("sessionId"):
            self.session_id = self.session_id or params["sessionId"]
        up = params.get("update") or {}
        kind = up.get("sessionUpdate") or up.get("type") or "?"
        self.kinds[kind] = self.kinds.get(kind, 0) + 1
        if kind in ("agent_message_chunk", "agent_message"):
            c = up.get("content") or {}
            if isinstance(c, dict) and c.get("type") == "text":
                self.texts.append(c.get("text") or "")
            elif isinstance(c, str):
                self.texts.append(c)
        elif kind == "agent_thought_chunk":
            c = up.get("content") or {}
            if isinstance(c, dict) and c.get("type") == "text":
                self.texts.append("")                   # 思考不算回答 ✓ 但记一笔 ✓

    # ── 生命周期 ──────────────────────────────────────────────────────────
    def drain(self, seconds: float) -> None:
        t0 = time.time()
        while time.time() - t0 < seconds:
            try:
                m = json.loads(self.q.get(timeout=1.0))
            except queue.Empty:
                print("[skip] 跳过一条坏数据（位置已记录，供排查）", file=sys.stderr); continue
            except Exception:
                print("[skip] 跳过一条坏数据（位置已记录，供排查）", file=sys.stderr); continue
            if m.get("method"):
                self.handle(m)
            time.sleep(0.0)

    def close(self) -> None:
        try:
            if self.session_id:
                self.req("session/close", {"sessionId": self.session_id}, 15.0)
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


def main(argv: list[str]) -> int:
    text = "只回四个字：协议通了"
    if "--probe" in argv:
        i = argv.index("--probe")
        if i + 1 < len(argv):
            text = argv[i + 1]
    a = Acp()
    try:
        init = a.req("initialize", {"protocolVersion": 1,
                                    "clientCapabilities": {"fs": {"readTextFile": False,
                                                                  "writeTextFile": False}}}, 60.0)
        print("INIT  : %s" % json.dumps(init, ensure_ascii=False)[:300])
        new = a.req("session/new", {"cwd": str(ROOT), "mcpServers": []}, 60.0)
        print("NEW   : %s" % json.dumps(new, ensure_ascii=False)[:400])
        if not new or "error" in new:
            for l in a.err[-4:]:
                print("  ERR: " + l.encode("ascii", "replace").decode("ascii")[:170])
            return 1
        a.session_id = (new.get("result") or {}).get("sessionId")
        print("SESSION: %s" % a.session_id)
        SESSION_META.write_text(json.dumps({"sessionId": a.session_id, "cwd": str(ROOT),
                                            "at": time.strftime("%Y-%m-%d %H:%M:%S")},
                                           ensure_ascii=False, indent=1), encoding="utf-8")

        t0 = time.time()
        r = a.req("session/prompt", {"sessionId": a.session_id,
                                     "prompt": [{"type": "text", "text": text}]}, 180.0)
        print("PROMPT: %s (%.1fs)" % (json.dumps(r, ensure_ascii=False)[:200], time.time() - t0))
        a.drain(3.0)
        print("UPDATES: %s" % json.dumps(a.kinds, ensure_ascii=False))
        ans = "".join(a.texts).strip()
        print("ANSWER (%d chars): %s" % (len(ans), ans.encode("ascii", "replace").decode("ascii")[:200]))
        print("LOG   : %s" % LOG)
    finally:
        a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
