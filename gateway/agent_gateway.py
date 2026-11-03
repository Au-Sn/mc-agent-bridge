#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MC Agent Bridge — 本地网关
================================

职责：在「外部 Agent」和「游戏内 CC:Tweaked 计算机」之间做一层稳定的接口。

  Agent  ──POST /api/command 或 GET /api/push──►  [指令队列]  ◄──GET /api/next──  游戏内计算机
  Agent  ◄──GET /api/state────────────────────────[状态存储]  ◄──POST /api/state── 游戏内计算机

为什么要有这一层（而不是让 Agent 直连游戏）：
  1. 指令是**队列**语义：断线/重启后不丢，可重放
  2. 所有交互都有**日志**：可审计、可回放、可复盘
  3. 换 Agent / 换模型 / 换游戏侧实现，另一边零改动

只依赖 Python 标准库，Python 3.8+ 直接跑：

    python agent_gateway.py --port 8765 --root ../cc-tweaked

界面：
    http://127.0.0.1:8765/            看板（状态 / 指令下发 / 日志）
    http://127.0.0.1:8765/files/agent_bridge.lua   给游戏内 wget 用
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Windows 控制台常是 GBK，强制 UTF-8，避免中文横幅变成乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

MAX_LOG = 800
MAX_QUEUE = 256
SERVE_EXT = (".lua", ".txt", ".md", ".json", ".cfg")


def repair_cc_text(value):
    """修复 CC:Tweaked 上报 JSON 时对非 ASCII 的「逐字节转义」造成的双重编码。

    背景（真实事故）：
      CC 的 `textutils.serializeJSON` 会把字符串里 0x7F–0xFF 的**每一个字节**
      转义成 \\u00XX（见其 rom/apis/textutils.lua 里的 hexify）。
      于是游戏里正常的 UTF-8 中文「我是」(E6 88 91) 在 JSON 里成了
      \\u00E6\\u0088\\u0091，Python 一解就是 3 个 Latin-1 字符 "æ\\x88\\x91"，
      看上去就是乱码（聊天/方块名/玩家名都会中招）。

    判据与安全性：
      - 只对「能按 latin-1 编回字节、且这些字节能按 UTF-8 解出」的字符串还原；
      - 纯 ASCII 原样返回；含 >U+00FF 的字符串（本来就是正常 Unicode）原样返回；
      - 真实的 Latin-1 文本（如 "café"）因 UTF-8 解码失败也会原样返回。
    """
    if isinstance(value, str):
        try:
            raw = value.encode("latin-1")
        except UnicodeEncodeError:
            return value
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return value
    if isinstance(value, dict):
        return {repair_cc_text(k): repair_cc_text(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [repair_cc_text(v) for v in value]
    return value


# --------------------------------------------------------------------------- #
# 中枢：指令队列 + 状态存储 + 日志
# --------------------------------------------------------------------------- #
class Hub:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.queues: dict[str, deque] = {}
        self.states: dict[str, dict] = {}
        self.log: deque = deque(maxlen=MAX_LOG)
        self.pending: dict[str, dict] = {}   # id -> 指令（等待结果）

    # -- 指令 ------------------------------------------------------------- #
    def push(self, who: str, cmd: str, args: dict | None = None) -> dict:
        item = {
            "id": uuid.uuid4().hex[:8],
            "cmd": cmd,
            "args": args or {},
            "ts": time.time(),
        }
        with self.lock:
            q = self.queues.setdefault(who, deque())
            if len(q) >= MAX_QUEUE:
                q.popleft()  # 队满丢最旧，避免游戏侧被压垮
            q.append(item)
            self.pending[item["id"]] = item
            self._log("push", who, item)
        self._after_change()
        return item

    def next_cmd(self, who: str) -> dict | None:
        with self.lock:
            q = self.queues.get(who)
            if q:
                item = q.popleft()
                self._log("next", who, item)
                return item
        return None

    def queue_len(self, who: str) -> int:
        with self.lock:
            return len(self.queues.get(who, ()))

    # -- 状态 ------------------------------------------------------------- #
    def set_state(self, who: str, payload: dict) -> None:
        with self.lock:
            payload = dict(payload)
            payload["_recv_ts"] = time.time()
            self.states[who] = payload
            cid = payload.get("id")
            if cid and cid in self.pending:
                self.pending.pop(cid, None)
            self._log("state", who, payload)
        self._after_change()

    def get_state(self, who: str) -> dict | None:
        with self.lock:
            return self.states.get(who)

    def all_states(self) -> dict:
        with self.lock:
            return dict(self.states)

    # -- 日志 ------------------------------------------------------------- #
    def _log(self, kind: str, who: str, data: dict) -> None:
        self.log.append({"ts": time.time(), "kind": kind, "who": who, "data": data})
        fb = globals().get("FILEBRIDGE")
        if fb is not None:
            try:
                fb.append_log(kind, who, data)
            except Exception:
                pass

    def dump_log(self, n: int = 50) -> list:
        with self.lock:
            return list(self.log)[-n:]

    # -- 变更后落盘（供文件桥使用） --------------------------------------- #
    def _after_change(self) -> None:
        fb = globals().get("FILEBRIDGE")
        if fb is not None:
            try:
                fb.persist()
            except Exception as exc:      # ★★§79.402✗★★ C 级 → **定级为真危险** ✗★
                #   ★为什么✗★：★`persist()` 里 `open(tmp)` **不在它自己的 try 里**✗★
                #   ★⇒ 磁盘满／权限问题 ⇒ **状态落盘静默失败**✗ ⇒ 重启后「以为写过」✗★ ✓
                #   ★处置✗★：★至少留痕 ✗ 不改控制流✗★ ✓
                print("[hub] ★状态落盘失败✗★（★重启后会丢★）：%r" % (exc,),
                      file=sys.stderr)


HUB = Hub()


# --------------------------------------------------------------------------- #
# 文件桥：给"只能读写文件、无法访问 HTTP"的 Agent 用
#   - 读 bridge/state.json  → 看游戏侧最新状态
#   - 读 bridge/log.jsonl   → 看事件流水
#   - 写 bridge/inbox/*.json → 下发指令（网关会自动取走并移到 processed/）
# 这样 Agent 不需要网络权限也能参与闭环。
# --------------------------------------------------------------------------- #
class FileBridge:
    def __init__(self, base: str) -> None:
        self.base = os.path.abspath(base)
        self.inbox = os.path.join(self.base, "inbox")
        self.proc = os.path.join(self.base, "processed")
        self.state_file = os.path.join(self.base, "state.json")
        self.log_file = os.path.join(self.base, "log.jsonl")
        os.makedirs(self.inbox, exist_ok=True)
        os.makedirs(self.proc, exist_ok=True)

    def persist(self) -> None:
        snap = {
            "ts": time.time(),
            # 状态也要过一遍修复：CC 侧的中文一律是逐字节转义的。
            # （HTTP 那条路已经在 set_state 时修过；这里修的是文件桥这条路的兜底，
            #   函数本身对已修复文本是幂等的，重复应用无害。）
            "states": repair_cc_text(HUB.all_states()),
            "queues": {k: HUB.queue_len(k) for k in list(HUB.queues.keys())},
        }
        tmp = self.state_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False, indent=2)
        # ⚠ 真实事故（2026-09-18 晚）：`os.replace` 在 Windows 上会因为**别的进程
        #   正好也拿着这两个文件**而抛 PermissionError(WinError 32) ✗ ——
        #   而它是**启动路径上的第一次 persist** ✗ ⇒ 整个网关在开始监听端口之前就崩了 ✗
        #   现场表现最容易误判：Agent 侧只看到"网关没在跑" ✗（其实是崩在写状态文件 ✓）。
        #   谁在抢：Agent 侧的文件桥兜底（`agent/channel.py` 写 inbox/state）✓ 或第二个网关实例 ✓
        #   ⇒ 处理：有限次重试 ✓ 仍不行就**退化成非原子写** ✓ ——
        #     状态文件晚一拍或半截都远好过"网关起不来" ✓（网络通道才是主路径 ✓）
        for attempt in range(6):
            try:
                os.replace(tmp, self.state_file)   # 原子替换，避免读到半截文件
                return
            except OSError as exc:
                if attempt == 5:
                    try:
                        with open(self.state_file, "w", encoding="utf-8") as fh:
                            json.dump(snap, fh, ensure_ascii=False, indent=2)
                        print("[gateway] 原子替换失败，已退化为直接写入 state.json：%s" % exc)
                    except OSError as exc2:
                        print("[gateway] 写 state.json 彻底失败（忽略，不影响通道）：%s" % exc2)
                    return
                time.sleep(0.15 * (attempt + 1))

    def append_log(self, kind: str, who: str, data: dict) -> None:
        try:
            if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > 2_000_000:
                os.replace(self.log_file, self.log_file + ".1")   # 简单轮转
        except OSError:
            pass
        with open(self.log_file, "a", encoding="utf-8") as fh:
            # 真实事故：指令回传里带中文时（例如原版报错、玩家名），
            # log.jsonl 里全是 ???? 之类的乱码——因为只有 HTTP 那条路做过修复。
            # 文件桥是 Agent 唯一能读的通道，这里不修等于"看不见游戏在说什么"。
            fh.write(json.dumps({"ts": time.time(), "kind": kind, "who": who,
                                 "data": repair_cc_text(data)}, ensure_ascii=False) + "\n")

    def watch(self) -> None:
        """轮询 inbox 目录，把 *.json 变成指令（处理完移到 processed/）"""
        _last_err = None          # ★同一条错只报一次 ✗ 免得每 0.5 秒刷屏把日志淹了✗★
        _move_errs = set()        # ★移文件失败也同样去重 ✗ 不然卡住的文件会刷屏✗★
        while True:
            try:
                for name in sorted(os.listdir(self.inbox)):
                    if not name.endswith(".json"):
                        continue
                    src = os.path.join(self.inbox, name)
                    try:
                        with open(src, "r", encoding="utf-8") as fh:
                            spec = json.load(fh)
                        who = str(spec.get("who", "mine1"))
                        cmd = str(spec.get("cmd", ""))
                        args = spec.get("args") or {
                            k: v for k, v in spec.items() if k not in ("who", "cmd", "args")
                        }
                        if cmd:
                            HUB.push(who, cmd, args)
                            print("[filebridge] 收下指令 %s -> %s" % (name, cmd))
                    except Exception as exc:
                        print("[filebridge] %s 解析失败：%s" % (name, exc))
                    try:
                        os.replace(src, os.path.join(self.proc, name))
                    except OSError as exc:
                        # ★不静默✗★：移不走 ⇒ ★这个文件下一轮还会被读到 ✗ 指令**再 push 一次**✗★
                        #   ⇒ 静默 pass 的话「同一件事被执行两遍」在外部完全看不出来 ✗★
                        #   ★同一条错只报一次 ✗ 免得 0.5 秒一次把日志淹了✗★ ✓
                        _m = "%s：%s" % (name, exc)
                        if _m not in _move_errs:
                            print("[filebridge] ★移入 processed 失败✗★（★可能重复下发✗★）："
                                  "%s → %s：%s" % (name, self.proc, exc), file=sys.stderr)
                            _move_errs.add(_m)
                    else:
                        _move_errs.clear()
            except Exception as exc:
                # ★不静默✗★：文件桥这**一整轮**都挂了（列目录／push／循环体意外）⇒
                #   ★不记录的话「指令一直没下发」在外部完全看不见✗★ ✓
                #   ★只在这个错误**变了**的时候报 ✗ 否则 0.5 秒一次的刷屏会把日志淹掉✗★ ✓
                _msg = "%s: %s" % (type(exc).__name__, exc)
                if _msg != _last_err:
                    print("[filebridge] ★这一轮轮询失败✗★（下一轮重试）：%s" % _msg,
                          file=sys.stderr)
                    _last_err = _msg
            else:
                _last_err = None          # ★这一轮没炸 ⇒ 下一条错重新报✗★
            time.sleep(0.5)


# --------------------------------------------------------------------------- #
# HTTP 处理器
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "MCAgentBridge/0.1"
    root_dir = "."
    quiet = False

    # ---- 工具方法 ------------------------------------------------------- #
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _read_body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {"value": data}
        except Exception:
            return {"_raw": raw.decode("utf-8", "replace")}

    def log_message(self, fmt, *args):  # 静音模式
        if not self.quiet:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---- 路由 ----------------------------------------------------------- #
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        p = u.path
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        if p == "/":
            return self._send(200, DASHBOARD.encode("utf-8"), "text/html; charset=utf-8")

        # 取指令：游戏内轮询这个（无指令时返回 idle，避免空响应导致 CC 端 http.get 报错）
        if p == "/api/next":
            who = q.get("who", "default")
            item = HUB.next_cmd(who)
            if item is None:
                return self._json({"cmd": "idle"})
            return self._json(item)

        # 读状态
        if p == "/api/state":
            who = q.get("who")
            if who:
                st = HUB.get_state(who)
                return self._json(st or {"known": False})
            return self._json({"states": HUB.all_states(), "queues": {k: HUB.queue_len(k) for k in HUB.queues}})

        # GET 形式下发指令（便于只有 GET 能力的 Agent 使用）
        if p == "/api/push":
            who = q.pop("who", "default")
            cmd = q.pop("cmd", "")
            if not cmd:
                return self._json({"ok": False, "error": "missing cmd"}, 400)
            item = HUB.push(who, cmd, q)
            return self._json({"ok": True, "queued": item})

        if p == "/api/log":
            try:
                n = int(q.get("n", "50"))
            except ValueError:
                n = 50
            return self._json({"log": HUB.dump_log(n)})

        # 把脚本文件发给游戏内计算机（wget run 用）
        if p.startswith("/files/"):
            # ⚠ 只用 basename 不够用了 ✗（真实需求：蓝图文件放 blueprints/ 子目录 ✓
            #   —— 相当于把"蓝图"塞进蓝图大炮 ✓）
            #   ⇒ 允许**安全的相对子路径** ✓ 并挡住 ../ 穿越 ✗
            rel = p[len("/files/"):].replace("\\", "/").lstrip("/")
            parts = [seg for seg in rel.split("/") if seg not in ("", ".", "..")]
            if not parts or len(parts) > 3:
                return self._send(403, b"forbidden", "text/plain; charset=utf-8")
            if not parts[-1].lower().endswith(SERVE_EXT):
                return self._send(403, b"forbidden", "text/plain; charset=utf-8")
            path = os.path.join(self.root_dir, *parts)
            if not os.path.isfile(path):
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            with open(path, "rb") as fh:
                return self._send(200, fh.read(), "text/plain; charset=utf-8")

        return self._json({"ok": False, "error": "no such endpoint", "path": p}, 404)

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        p = u.path
        body = self._read_body()

        if p == "/api/command":
            who = str(body.get("who", "default"))
            cmd = str(body.get("cmd", ""))
            args = body.get("args") or {k: v for k, v in body.items() if k not in ("who", "cmd", "args")}
            if not cmd:
                return self._json({"ok": False, "error": "missing cmd"}, 400)
            return self._json({"ok": True, "queued": HUB.push(who, cmd, args)})

        if p == "/api/state":
            who = str(body.get("who", "default"))
            HUB.set_state(who, repair_cc_text(body))
            return self._json({"ok": True})

        return self._json({"ok": False, "error": "no such endpoint"}, 404)


# --------------------------------------------------------------------------- #
# 看板
# --------------------------------------------------------------------------- #
DASHBOARD = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>MC Agent Bridge</title>
<style>
 body{font:14px/1.6 system-ui,"Segoe UI",sans-serif;margin:0;background:#111;color:#ddd}
 header{padding:14px 20px;background:#1b1b1b;border-bottom:1px solid #333}
 h1{font-size:16px;margin:0}
 main{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px}
 section{background:#1b1b1b;border:1px solid #333;border-radius:8px;padding:12px}
 h2{font-size:13px;margin:0 0 8px;color:#8fd}
 pre{white-space:pre-wrap;word-break:break-all;max-height:44vh;overflow:auto;margin:0;
     background:#111;border:1px solid #2a2a2a;border-radius:6px;padding:8px}
 input,select,button{background:#111;color:#ddd;border:1px solid #444;border-radius:6px;padding:6px 8px}
 button{cursor:pointer} button:hover{border-color:#8fd;color:#8fd}
 .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
 .muted{color:#888}
</style></head><body>
<header><h1>MC Agent Bridge · 控制台</h1></header>
<main>
 <section>
  <h2>下发指令</h2>
  <div class="row">
   <input id="who" value="mine1" size="8" title="目标计算机名">
   <input id="cmd" value="status" size="10" title="指令">
   <input id="args" value="" size="18" placeholder="参数 k=v&k2=v2" title="参数">
   <button onclick="push()">发送</button>
  </div>
  <div class="row muted">
   常用：
   <button onclick="quick('status')">status</button>
   <button onclick="quick('scan&radius=8')">scan</button>
   <button onclick="quick('forward')">forward</button>
   <button onclick="quick('turn_left')">turn_left</button>
   <button onclick="quick('inv_list')">inv_list</button>
   <button onclick="quick('say&text=hello')">say</button>
  </div>
 </section>
 <section>
  <h2>最新状态</h2>
  <pre id="state">加载中…</pre>
 </section>
 <section>
  <h2>事件日志（最近 40 条）</h2>
  <pre id="log"></pre>
 </section>
 <section>
  <h2>说明</h2>
  <pre>Agent 侧也可直接调用：
  POST /api/command   {"who":"mine1","cmd":"forward","args":{}}
  GET  /api/push?who=mine1&amp;cmd=scan&amp;radius=8
  GET  /api/state?who=mine1
游戏内计算机脚本：
  wget run http://&lt;本机IP&gt;:PORT/files/agent_bridge.lua</pre>
 </section>
</main>
<script>
async function push(){
  const who=document.getElementById('who').value.trim();
  const cmd=document.getElementById('cmd').value.trim();
  const argsRaw=document.getElementById('args').value.trim();
  const q=new URLSearchParams({who,cmd});
  if(argsRaw) new URLSearchParams(argsRaw).forEach((v,k)=>q.set(k,v));
  const r=await fetch('/api/push?'+q.toString());
  console.log(await r.json());
}
function quick(s){
  const who=document.getElementById('who').value.trim();
  const [c,a]=s.split('&');
  document.getElementById('cmd').value=c;
  document.getElementById('args').value=a||'';
  push();
}
async function tick(){
  try{
    const s=await (await fetch('/api/state')).json();
    document.getElementById('state').textContent=JSON.stringify(s,null,2);
    const l=await (await fetch('/api/log?n=40')).json();
    document.getElementById('log').textContent=(l.log||[]).map(e=>
      new Date(e.ts*1000).toLocaleTimeString()+' ['+e.kind+'] '+e.who+' '+
      JSON.stringify(e.data)).join('\\n');
  }catch(e){document.getElementById('state').textContent=String(e)}
}
setInterval(tick,1000); tick();
</script></body></html>
"""


# --------------------------------------------------------------------------- #
# CLI 模式：直接在终端敲指令
# --------------------------------------------------------------------------- #
def cli_loop(default_who: str) -> None:
    print("\n[CLI] 输入格式：  <cmd> [k=v ...]     （回车 = 发给 %s）" % default_who)
    print("[CLI] 例： forward / scan radius=8 / say text=hi / state / log\n")
    while True:
        try:
            line = input("bridge> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in ("quit", "exit"):
            return
        if line == "log":
            for e in HUB.dump_log(20):
                print("  [%s] %s %s" % (e["kind"], e["who"], json.dumps(e["data"], ensure_ascii=False)))
            continue
        if line == "state":
            print(json.dumps(HUB.all_states(), ensure_ascii=False, indent=2))
            continue
        parts = line.split()
        cmd, args = parts[0], {}
        for kv in parts[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                args[k] = v
        item = HUB.push(default_who, cmd, args)
        print("  → queued %s" % item["id"])


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="MC Agent Bridge gateway")
    ap.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0，游戏内需要访问）")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--root", default="cc-tweaked", help="供 /files/ 分发的脚本目录")
    ap.add_argument("--who", default="mine1", help="CLI 默认目标计算机名")
    ap.add_argument("--bridge-dir", default="bridge",
                    help="文件桥目录（state.json / log.jsonl / inbox/），设为空字符串可关闭")
    ap.add_argument("--cli", action="store_true", help="启动后进入交互命令行")
    ap.add_argument("--quiet", action="store_true", help="不打印每条 HTTP 访问日志")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    Handler.root_dir = root
    Handler.quiet = args.quiet

    if args.bridge_dir:
        fb = FileBridge(args.bridge_dir)
        globals()["FILEBRIDGE"] = fb
        threading.Thread(target=fb.watch, daemon=True).start()
        fb.persist()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("=" * 62)
    print(" MC Agent Bridge gateway")
    print("   看板      : http://127.0.0.1:%d/" % args.port)
    print("   脚本目录  : %s" % root)
    if os.path.isdir(root):
        for f in sorted(os.listdir(root)):
            if f.lower().endswith(SERVE_EXT):
                print("   可下发    : /files/%s" % f)
    else:
        print("   ⚠ 脚本目录不存在，/files/ 将不可用")
    print("   游戏内    : wget run http://<本机IP>:%d/files/agent_bridge.lua" % args.port)
    if args.bridge_dir:
        print("   文件桥    : %s   (state.json 可读 / inbox/*.json 可写)" % os.path.abspath(args.bridge_dir))
    print("=" * 62)

    if args.cli:
        t = threading.Thread(target=cli_loop, args=(args.who,), daemon=True)
        t.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n bye")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
