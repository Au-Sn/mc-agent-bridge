#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dshrun.py —— ★用 Python 去调 DeepSeek Harness★（别再让 shell 碰中文 ✗）

## 为什么必须有它 ✗（实测环境事实 ✓ 2026-09-20 ✓）

第一次我是这么调的 ✗：
    $task = (Get-Content task.txt -Raw);  dsh --profile mcbot $task
⇒ 模型收到的是「**你这条消息到我这儿乱码又被截断了**」✗
   （前半段乱码 ✓ 后半段直接没了 ✗ —— 于是它诚实地拒绝开工 ✓ 这是对的 ✓）

根因 ✓：这台机器上我拿到的 shell 是 **Windows PowerShell 5.1** ✗
   ⇒ 它把**命令行参数**按 ANSI（本机 CP936/GBK）重新编码再交给原生程序 ✗
   ⇒ 非 ASCII 的 argv 必坏 ✗
   （旁证 ✓：它的 `>` 重定向写出的是 **UTF-16LE ＋ BOM** ✗ —— pwsh 7 不会这样 ✓ 见 P39 ✓）

正解 ✓：**用 Python 起进程** ✓ —— CPython 在 Windows 上用 `CreateProcessW` 传 UTF-16 命令行 ✓
   中文**原样**到达 ✓（并且 `text=True, encoding="utf-8"` 读回 stdout ✓）

## 它同时是"harness 大脑"的适配器 ✓

`talk.py --brain harness` 就是调这里的 `run()` ✓ —— 一份实现 ✓：
    游戏聊天 → run() 起一个 mcbot 会话 → 会话用 mc 工具做事 → **它的最终回答** → `/dshsay` 说出去 ✓

## 用法

    py tools/dshrun.py --task-file T.txt                 # 跑一次，stdout 结果写到 T.out.txt
    py tools/dshrun.py --task "..." --profile mcbot
    py tools/dshrun.py --list                             # 只列出可用的 profiles ✓
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import paths as PA  # noqa: E402  ★大脑层接缝：可执行路径不写死本机✗★
# ★控制台一定要重配 UTF-8 ＋ 行缓冲★ ✗（今天第 6 次踩同一个坑 ✓ P39/P47/P50 一家 ✓）
#   不重配 ⇒ 打中文/`✓` 到 GBK 控制台 ⇒ 崩 + **退出码变 1** ✗（而功能其实全对 ✓）
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)   # type: ignore[attr-defined]
except Exception:
    pass
LOG = ROOT / "logs" / "dshrun.jsonl"

# ★★回合要"打不断、看得见"★★（用户要求 ✓ 2026-09-21 凌晨 ✓）
# 用户原话 ✓：「容易中断进程，而且无从得知目前思考到哪一步」
# ⇒ 原来那个设计**有缺陷** ✗：会话是 talk.py 的**子进程** ✓
#   ⇒ talk.py 一被杀（或 Ctrl+C）⇒ 会话陪葬 ⇒ **这一轮的话就没了** ✗
#     （23:50 那次就是这么丢的 ✓ 见 docs 的 §15.1 ✓）
# ⇒ 现在改成 ✓：
#   ① `start()`：用**独立进程组**起会话 ✓ 输出**直接写文件** ✗（不走管道 ✗ 管道会跟着父进程断 ✓）
#   ② `logs/round.json`：**当前回合的状态**（pid ✓ 起始时刻 ✓ 任务开头 ✓ 输出文件路径 ✓ 状态 ✓）
#   ③ `wait()`：等它（可带回调 ⇒ 一边等一边**打进度** ✓）
#   ④ talk.py 重启后会**先看 round.json** ✓ ⇒ 没说完的答案**补说出去** ✓（不再丢 ✓）
ROUND = ROOT / "logs" / "round.json"
RUNS = ROOT / "logs" / "runs"


def _alive(pid: int) -> bool:
    """进程还活着吗 ✓ —— ★别用 `os.kill(pid, 0)`★ ✗

    实测常识 ✓：Windows 上 `os.kill` 只认 CTRL_C_EVENT / CTRL_BREAK_EVENT ✗
    其它信号值**会直接把进程干掉** ✗ —— 用错一次就把正在跑的回合杀了 ✗
    ⇒ 改用 `OpenProcess` **只查询**（PROCESS_QUERY_LIMITED_INFORMATION = 0x1000 ✓）
    """
    if not pid:
        return False
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    except Exception:
        return False


def _save(rec: dict) -> None:
    rec = {k: v for k, v in rec.items() if k != "out_text"}   # out_text 太长 ✗ 不落盘 ✓ 现读文件 ✓
    try:
        ROUND.parent.mkdir(parents=True, exist_ok=True)
        ROUND.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def load_round() -> dict | None:
    """读"当前（或最后一次）回合" ✓ —— 用来**重挂** ✓"""
    try:
        if ROUND.is_file():
            return json.loads(ROUND.read_text(encoding="utf-8"))
    except Exception as e:
        # 记录：回合账读坏 ⇒ 静默没法重挂（不许把"读不了"当成"没有回合"）
        print("[记录] 回合账读不到（没法重挂）：%s: %s"
              % (type(e).__name__, str(e)[:80]), file=sys.stderr)
    return None


def read_round_text(rec: dict) -> tuple[str, str]:
    """读那个回合的**输出**与**进度/推理**（都是它自己写的文件 ✓ 不经过管道 ✓）"""
    o = e = ""
    try:
        p = Path(rec.get("out") or "")
        if p.is_file():
            o = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        p = Path(rec.get("err") or "")
        if p.is_file():
            e = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return o, e


def prune_runs(keep: int = 60) -> int:
    """★只留最近 `keep` 个回合文件★ ✓（`logs/runs/` 会一直攒 ✗ 迟早一大坨 ✓）

    ⚠ 三条规矩 ✓：
      ① **别动当前回合的** ✗（它可能正在写 ✓）
      ② 一对 `.out/.err` 一起删 ✓（只删一个会留下一半 ✗ 更难查 ✓）
      ③ 删了多少要**说出来** ✓（静默清理 ＝ 你以后找不到证据还不知道为什么 ✗）
    """
    try:
        files = sorted(RUNS.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return 0
    cur = str((load_round() or {}).get("rid") or "")
    doomed = [p for p in files[keep:] if cur and cur not in p.name]
    n = 0
    for p in doomed:
        try:
            p.unlink()
            n += 1
        except Exception:
            pass
    return n


def start(task: str, profile: str = "mcbot", cwd: str | None = None) -> dict:
    """★起一个**独立**回合★ ✓（★父进程死了它照样跑完★ ✗ 这是关键 ✓）"""
    RUNS.mkdir(parents=True, exist_ok=True)
    gone = prune_runs()
    if gone:
        print("[dshrun] 顺手清掉 %d 个旧回合文件 ✓（logs/runs 只留最近 60 个 ✓）" % gone)
    rid = time.strftime("%Y%m%d-%H%M%S")
    out = RUNS / ("%s.out" % rid)
    err = RUNS / ("%s.err" % rid)
    fo = out.open("w", encoding="utf-8")
    fe = err.open("w", encoding="utf-8")
    # ★独立进程组★ ✗：Windows 用 CREATE_NEW_PROCESS_GROUP ＋ DETACHED_PROCESS ✓
    flags = 0
    for name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS"):
        flags |= int(getattr(subprocess, name, 0) or 0)
    p = subprocess.Popen([node_exe(), find_dsh(), "--profile", profile, task],
                         cwd=cwd or str(ROOT), stdout=fo, stderr=fe,
                         stdin=subprocess.DEVNULL, creationflags=flags)
    rec = {"rid": rid, "pid": p.pid, "profile": profile,
           "started": time.strftime("%Y-%m-%d %H:%M:%S"), "t0": time.time(),
           "task": task[:300], "out": str(out), "err": str(err),
           "status": "running", "rc": None, "spoken": False}
    _save(rec)
    return rec


def progress_lines(rec: dict, n: int = 3) -> list[str]:
    """★"它现在想到哪一步了"★ ✓ —— 从子进程的 stderr 里取最后几行有用的 ✓

    子进程 stderr 里本来就有两路现成的东西 ✓（实测 ✓）：
      · `dsh: reasoning: …`  ← 模型的思考 ✓
      · `[mc_mcp] <工具> <秒> ok/FAIL` ← **每一步工具调用** ✓
    ⇒ 它们**实时**写进 `logs/runs/*.err` ✓ ⇒ 我们只要读文件就能"看见" ✓
    """
    _, err = read_round_text(rec)
    keep = []
    for line in err.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("[mc_mcp]") or s.startswith("dsh: reasoning") or "reasoning:" in s:
            keep.append(s[:180])
    return keep[-n:]


def wait(rec: dict, timeout: float = 300.0, on_tick=None) -> dict:
    """等这个回合结束 ✓（`on_tick(rec)` 每 ~0.5 s 回调一次 ⇒ 拿它打进度 ✓）"""
    t0 = float(rec.get("t0") or time.time())
    while time.time() - t0 < timeout:
        if not _alive(rec.get("pid") or 0):
            break
        time.sleep(0.5)
        if on_tick:
            try:
                on_tick(rec)
            except Exception:
                pass
    out, _err = read_round_text(rec)
    still = _alive(rec.get("pid") or 0)
    rec.update({"status": "running" if still else "done",
                "sec": round(time.time() - t0, 2),
                # ⚠ 拿不到真实退出码 ✗（进程是独立的 ✓ 我们不是它的父进程 ✓）
                #   ⇒ **不假装知道** ✗：有输出就当 0 ✓ 没输出留 None ✓（纪律：失败要大声 ✓）
                "rc": 0 if out.strip() else (None if still else 1),
                "out_text": out.strip()})
    _save(rec)
    return rec


def run(task: str, profile: str = "mcbot", cwd: str | None = None,
        timeout: float = 300.0, verbose: bool = False, on_tick=None) -> dict:
    """★旧接口保持不变★ ✓（内部已换成"独立进程 ＋ 落盘"✓ 所以**结果不会再丢** ✓）"""
    rec = start(task, profile=profile, cwd=cwd)
    rec = wait(rec, timeout=timeout, on_tick=on_tick)
    out = rec.get("out_text") or ""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "rid": rec.get("rid"),
                                "pid": rec.get("pid"), "profile": profile, "sec": rec.get("sec"),
                                "task": task[:300], "out": out[:600]},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass
    if verbose:
        print("[dshrun] rid=%s pid=%s %s %.1fs" % (rec.get("rid"), rec.get("pid"),
                                                   rec.get("status"), rec.get("sec") or 0))
    return {"rc": rec.get("rc"), "out": out, "err": read_round_text(rec)[1],
            "sec": rec.get("sec"), "rid": rec.get("rid"), "rec": rec}



def find_dsh() -> str:
    """定位 dsh 的入口 js ✓（★不是 .cmd★ ✗ —— batch 文件又要经过一层转义 ✓ 麻烦 ✓）

    ★大脑层接缝✗★：DSH_BIN／DSH_BIN_JS／npm 缓存；★不写死本机路径✗★ ——
    找不到就打印"需要配置"并非零退出。
    """
    env = os.environ.get("DSH_BIN")
    if env and Path(env).is_file():
        return env
    p = PA.find_dsh_bin_js()
    if p is not None:
        return str(p)
    print("需要配置 DSH_BIN_JS（dsh 的 lib/bin.js 路径）或 DSH_BIN；"
          "也可以先安装 dsh", file=sys.stderr)
    raise SystemExit(2)


def node_exe() -> str:
    """★node 从配置来✗★（DSH_NODE／PATH）；没有 ⇒ 明确报错"""
    try:
        return str(PA.require_node())
    except PA.NotConfigured as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str]) -> int:
    a: dict = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            a[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            a[argv[i].lstrip("-")] = True
            i += 1

    if a.get("list"):
        import glob
        home = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
        print("[dshrun] dsh = %s" % find_dsh())
        print("[dshrun] DSH_HOME = %s" % home)
        for d in sorted((home / "profiles").glob("*")):
            if d.is_dir() and d.name != "node_modules":
                print("   profile: %s" % d.name)
        return 0

    # ★`status`：随时看"现在这个回合到哪一步了"★ ✓（用户要求 ✓）
    if a.get("status"):
        rec = load_round()
        if not rec:
            print("[dshrun] 还没有任何回合 ✓（logs/round.json 不存在 ✓）")
            return 0
        alive = _alive(rec.get("pid") or 0)
        out, _err = read_round_text(rec)
        print("[dshrun] rid=%s pid=%s 状态=%s 已跑=%.0fs"
              % (rec.get("rid"), rec.get("pid"),
                 "★还在跑★" if alive else "已结束", time.time() - float(rec.get("t0") or 0)))
        print("[dshrun] 任务开头：%s" % (rec.get("task") or "")[:80].replace("\n", " "))
        for ln in progress_lines(rec, 6):
            # ⚠ 别再 `encode("ascii","replace")` 了 ✗（我第一版就这么写的 ✓）
            #   ⇒ 中文全变 `?` ✗ ⇒ **读文件的人看不到结果** ✗（"保护"过头了 ✓）
            #   ⇒ 现在 stdout 已经重配成 UTF-8 ✓ 直接打中文就行 ✓
            print("   %s" % ln)
        if out.strip():
            print("[dshrun] 最终回答（前 300 字）：%s" % out.strip()[:300])
        else:
            print("[dshrun] 还没有最终回答 ✓（说明它还在想 ✓ 上面那几行就是进度 ✓）")
        return 0

    if a.get("task-file"):
        task = Path(str(a["task-file"])).read_text(encoding="utf-8").strip()
    elif a.get("task"):
        task = str(a["task"])
    else:
        print("用法: py tools/dshrun.py --task-file T.txt [--profile mcbot] [--out F] [--timeout 300]")
        return 2

    # ★`--detached`：起完就返回★ ✓（"回合独立进程"的入口 ✓ 这个命令退出了它照样跑完 ✓）
    if a.get("detached"):
        rec = start(task, profile=str(a.get("profile") or "mcbot"))
        print("[dshrun] ★已独立起一个回合★ rid=%s pid=%s" % (rec["rid"], rec["pid"]))
        print("         看进度 ✓：py tools/dshrun.py status ｜ 输出文件 ✓：%s" % rec["out"])
        return 0

    r = run(task, profile=str(a.get("profile") or "mcbot"),
            timeout=float(a.get("timeout") or 300.0), verbose=True)
    dest = Path(str(a["out"])) if a.get("out") else (
        Path(str(a["task-file"])).with_suffix(".out.txt") if a.get("task-file") else None)
    if dest:
        dest.write_text("<<<最终回答>>>\n%s\n\n<<<stderr 尾部>>>\n%s"
                        % (r["out"], "\n".join((r["err"] or "").splitlines()[-12:])),
                        encoding="utf-8")
        print("[dshrun] wrote %s" % dest)
    else:
        sys.stdout.write(r["out"] + "\n")
    return 0 if r["rc"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
