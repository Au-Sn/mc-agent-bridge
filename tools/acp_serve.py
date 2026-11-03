#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""acp_serve.py —— ★常驻 ACP 服务★（一个会话一直活着 ✓ 别人靠文件跟它说话 ✓）

为什么用**文件**当通道 ✗（而不是端口/管道 ✓）：
  · 客户是**中继**（`talk.py`）✓ 而中继**随时可能被杀/重启** ✓（我们为此吃过一次亏 ✗）
  · 文件通道 ⇒ **谁都能来投递** ✓ 服务进程**不依赖任何调用者活着** ✓✓ ⇒ L5 天然成立 ✓
  · 好处之二 ✓：全部往来**天然落盘** ✓（可回放 ✓ 可核对 ✓ 符合本项目"原始回执一律留档" ✓）

通道约定 ✓
  · 收件箱 `logs/acp_inbox.jsonl`   —— 每行 `{"id": "...", "text": "要说的话"}` ✓
  · 发件箱 `logs/acp_outbox.jsonl`  —— 每行 `{"id": ..., "answer": ..., "stop": ..., "sec": ...}` ✓
  · 会话信息 `logs/acp_session.json` —— `sessionId` ＋ cwd ＋ 起于何时 ✓（重启后能据此 resume ✓）
  · 已处理的 id 记在内存里 ✓（同一行不会被答两遍 ✓）

用法：py tools/acp_serve.py            # 前台常驻（一般用后台任务跑 ✓）
      py tools/acp_serve.py --once X   # 投一句话、等答案、退出（自测用 ✓）
"""
from __future__ import annotations

import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception as _e:   # ★★§79.403✗★ pin 不住也不致命 ✗ 但**记一句**✗★
    sys.stderr.write("acp_serve: stdout pin 失败 %r\n" % (_e,))

import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dsh_acp  # noqa: E402
import paths as PA  # noqa: E402  ★大脑层接缝：节点/dsh 从配置来（不写死本机）✗★

INBOX = ROOT / "logs" / "acp_inbox.jsonl"
OUTBOX = ROOT / "logs" / "acp_outbox.jsonl"
META = ROOT / "logs" / "acp_session.json"
SEEN = ROOT / "logs" / "acp_seen.txt"     # ★处理过的 id 落盘★ ✓（见 load_seen 的说明 ✗）
MEM = ROOT / "memory" / "bot.md"          # ★长期记忆★（跨重启 ✓ 人可读可编 ✓）


# ══ ★★"重启就重放"这个 bug（实测 2026-09-23 ✓）★★ ═══════════════════════════
# 现象 ✗：`seen` 原来是个**内存里的 set** ✓ ⇒ 服务每次重启 ⇒ 它**从头把整个收件箱再答一遍** ✗
#   实测回执 ✓：110 条发件箱记录里 **17 个 id 重复** ✓ 最多的一个 id 出现 **9 次** ✓
#   （＝我重启了几次它就重做了几遍 ✓）
# 为什么这是**真事故** ✗（不只是浪费 ✓）：
#   ① 旧指令会被**再执行一遍** ✗ —— 收件箱里那句"用你的 Minecraft 工具真的做一次动作"✓
#      重启后**又让它走了一趟** ✓（世界真值能对上 ✓ 只是坐标已经不是上次那组 ✓）
#   ② 新消息会**排在一堆重放后面饿死** ✗ —— 实测我把提问投进去 ✓ 等了 150 秒没答上 ✓
#      因为前面还堵着十几条老请求 ✓（用户看到的就是"重启后它不理我"✗）
# 修法 ✓：**处理过的 id 落盘** ✓（`logs/acp_seen.txt` ✓ 一行一个 ✓ 启动时读回来 ✓）
#   语义上还是对的 ✓：**服务没起的时候投进来的消息，起来后照样会被处理** ✓（不会静默丢 ✓）
def load_seen() -> set:
    if not SEEN.is_file():
        return set()
    try:
        return {x.strip() for x in SEEN.read_text(encoding="utf-8").splitlines() if x.strip()}
    except Exception:
        return set()


def mark_seen(rid: str) -> None:
    try:
        with SEEN.open("a", encoding="utf-8", newline="\n") as f:
            f.write(rid + "\n")
    except Exception as e:          # ★★§79.403✗★ 去重账写不进 ⇒ **重启后会重复处理同一请求**✗★
        print("[acp_serve] ★mark_seen 写不进✗★（★重启后可能重复处理 %s★）：%r"
              % (rid, e), file=sys.stderr)



def mem_prefix() -> str:
    """每轮**现读**记忆文件 ✓（改了就立刻生效 ✓ 不用重启 ✓）；没有就当空 ✓"""
    try:
        if MEM.is_file():
            t = MEM.read_text(encoding="utf-8").strip()
            if t:
                return ("以下是你（Bot）的长期记忆，来自 memory/bot.md，"
                        "它是跨重启保留的事实，请当作你自己记得的事：\n" + t + "\n---\n")
    except Exception as e:
        # 记录：记忆读不到 ⇒ 这一轮的系统提示**少了长期记忆**（不许静默）
        print("[记录] 长期记忆读不到（本轮提示少一段）：%s: %s"
              % (type(e).__name__, str(e)[:80]), file=sys.stderr)
    return ""


def mem_append(text: str) -> int:
    """把一条事实追加进长期记忆 ✓ 返回写入后的行数 ✓

    ⚠ 去重（实测 2026-09-23 ✗）：同一句「我决定以后优先把沙砾筛成矿物碎块」被写了**三遍** ✗
      —— 早先那几轮记忆测试每轮都 remember 一次 ✓ 而我没查重 ✗
      ⇒ 记忆是会**每轮注入**的 ✓ 三遍就等于**对它强调三遍** ✗ ⇒ 行为被悄悄带偏 ✗
      ⇒ 纪律 ✓：**同一句只留一条** ✓（已经有 ⇒ 不写 ✓ 但要如实回报"已有"✓）
    """
    text = (text or "").strip()
    if not text:
        return len(MEM.read_text(encoding="utf-8").splitlines()) if MEM.is_file() else 0
    MEM.parent.mkdir(parents=True, exist_ok=True)
    old = MEM.read_text(encoding="utf-8") if MEM.is_file() else ""
    if ("- " + text) in old or text in old:
        return len(old.splitlines())
    with MEM.open("a", encoding="utf-8", newline="\n") as f:
        f.write("- " + text + "\n")
    return len(MEM.read_text(encoding="utf-8").splitlines())


def append(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def start_session() -> "dsh_acp.Acp | None":
    # ★大脑层接缝✗★：先问"node 与 dsh 配了吗" ⇒ 没配就**明确报**（不写死本机路径）
    try:
        PA.require_node()
        PA.require_dsh_bin_js()
    except PA.NotConfigured as exc:
        print("★需要配置大脑层✗★：%s" % (exc,), file=sys.stderr)
        print("（提示：在 dsh.env 里填 DSH_NODE／DSH_BIN_JS，或设同名环境变量）",
              file=sys.stderr)
        return None
    a = dsh_acp.Acp()
    init = a.req("initialize", {"protocolVersion": 1,
                                "clientCapabilities": {"fs": {"readTextFile": False,
                                                              "writeTextFile": False}}}, 60.0)
    if not init or "error" in init:
        print("INIT FAIL")
        a.close()
        return None
    new = a.req("session/new", {"cwd": str(ROOT), "mcpServers": []}, 60.0)
    sid = (new or {}).get("result", {}).get("sessionId")
    if not sid:
        print("NEW FAIL")
        a.close()
        return None
    a.session_id = sid
    # ★两个 pid 都要记★ ✗（2026-09-28 ✓）：`pid` = **会话子进程**（`node … dsh --profile mcacp` ✓）
    #   `serve_pid` = **acp_serve 自己** ✓
    #   为什么要多记一个 ✗：`start_all.ps1` 原来只拿 `pid` 去 `Get-Process` ✗
    #   ⇒ **pid 会被复用** ✗ ⇒ stale pidfile 撞上新进程 ⇒ 它报"acp serve alive" ✗
    #     而实际大脑早没了 ✗（本轮实测：acp_serve 其实一直没在跑 ✗ 我却被报告骗了 ✓）
    #   ⇒ 判定改成"**acp_serve 活着 ✓ 且 会话子进程是它的孩子**" ✓ —— 复用 pid 满足不了父子关系 ✓
    META.write_text(json.dumps({"sessionId": sid, "cwd": str(ROOT),
                                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "pid": a.p.pid, "serve_pid": os.getpid()},
                               ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("SESSION %s (session_pid=%s serve_pid=%s)" % (sid, a.p.pid, os.getpid()))
    return a


def answer(a, text: str, timeout: float = 300.0) -> dict:
    a.texts = []
    before = dict(a.kinds)
    t0 = time.time()
    r = a.req("session/prompt", {"sessionId": a.session_id,
                                 "prompt": [{"type": "text", "text": mem_prefix() + text}]}, timeout)
    a.drain(1.5)
    ans = "".join(a.texts).strip()
    stop = ((r or {}).get("result") or {}).get("stopReason")
    return {"answer": ans, "stop": stop, "sec": round(time.time() - t0, 2),
            "updates": {k: a.kinds.get(k, 0) - before.get(k, 0) for k in a.kinds},
            "sessionId": a.session_id}


def main(argv: list[str]) -> int:
    if "--once" in argv:
        i = argv.index("--once")
        text = argv[i + 1] if i + 1 < len(argv) else "在吗"
        a = start_session()
        if a is None:
            return 1
        try:
            out = answer(a, text)
            append(OUTBOX, dict(out, id="once", text=text))
            print(json.dumps({k: out[k] for k in ("stop", "sec", "sessionId")},
                             ensure_ascii=False))
            print("answer_len=%d" % len(out["answer"]))
            return 0
        finally:
            a.close()

    a = start_session()
    if a is None:
        return 1
    seen: set = load_seen()          # ★从盘上读回"已经答过的 id"★ ✓ 免得重启就重放 ✗
    print("SERVE ready; inbox=%s seen=%d (replays skipped)" % (INBOX, len(seen)))

    try:
        while True:
            time.sleep(0.5)
            if a.p.poll() is not None:                 # ★进程死了 ⇒ 重开一个会话 ✓（如实记 ✗）
                append(OUTBOX, {"id": "system", "note": "acp process died; restarting",
                                "at": time.strftime("%H:%M:%S")})
                a = start_session()
                if a is None:
                    time.sleep(5.0)
                    continue
            if not INBOX.is_file():
                continue
            for line in INBOX.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                except Exception:
                    print("★跳过一条坏数据（已记录，供排查）✗★", file=sys.stderr); continue
                rid = str(req.get("id") or "")
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                mark_seen(rid)               # ★落盘★ ✓ 重启后不再重放 ✓
                if req.get("remember"):
                    n = mem_append(str(req["remember"]))
                    append(OUTBOX, {"id": rid, "answer": "(remembered; lines=%d)" % n,
                                    "stop": "memory", "sec": 0.0,
                                    "sessionId": a.session_id, "memory_lines": n})
                    continue
                out = answer(a, str(req.get("text") or ""))
                out.update({"id": rid, "text": req.get("text")})
                append(OUTBOX, out)
                print("answered id=%s stop=%s sec=%s" % (rid, out["stop"], out["sec"]))
    except KeyboardInterrupt:
        print("bye")
    finally:
        a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
