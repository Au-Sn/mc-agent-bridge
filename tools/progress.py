#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""progress.py —— ★"它现在想到哪一步了"★（用户要求 ✓ 一条命令看清 ✓）

用户原话 ✓：「容易中断进程，而且无从得知目前思考到哪一步」

这一条就是**第二半句**的解药 ✓：所有数据都来自**已经落盘**的东西 ✓ ——

| 来源 | 是什么 | 谁写的 |
|---|---|---|
| `logs/round.json` | 当前（最后一次）回合：pid ✓ 起始时刻 ✓ 任务开头 ✓ 状态 ✓ | `dshrun.start()` ✓ |
| `logs/runs/<rid>.err` | `dsh: reasoning:`（它在想什么 ✓）＋ `[mc_mcp] <工具> <秒> ok`（它真调了什么 ✓） | **子进程自己** ✓ |
| `logs/runs/<rid>.out` | 最终回答 ✓ | 子进程 ✓ |
| `logs/mc_mcp.jsonl` | 每一次工具调用的**结构化**记录 ✓ | MCP 工具层 ✓ |

★为什么值得单独做一个命令★ ✗：`dshrun.py status` 是"顺手看一眼" ✓
这里则是**给人用的**：算好"跑了多久 / 调了几次 / 卡在哪一步" ✓ 还能 `--watch` 每秒刷新 ✓

用法：
    py tools/progress.py            # 看一次 ✓
    py tools/progress.py --watch    # 每秒刷新 ✓（Ctrl+C 退出 ✓）
    py tools/progress.py --json     # 机器可读 ✓（给别的工具用 ✓）
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)   # type: ignore[attr-defined]
except Exception:
    pass

import dshrun  # noqa: E402

TOOL_LINE = re.compile(r"\[mc_mcp\]\s+(\w+)\s+([\d.]+)s\s+(\w+)")


def snapshot() -> dict:
    """把"现在到哪一步"算成一份数据 ✓（纯读文件 ✓ 不碰游戏 ✓）"""
    rec = dshrun.load_round()
    if not rec:
        return {"has_round": False}
    alive = dshrun._alive(rec.get("pid") or 0)
    out, err = dshrun.read_round_text(rec)
    steps: list[dict] = []
    thoughts: list[str] = []
    pending_thought = False
    for line in err.splitlines():
        s = line.strip()
        if s.startswith("dsh: reasoning") or s.endswith("reasoning:"):
            pending_thought = True
            continue
        m = TOOL_LINE.search(s)
        if m:
            steps.append({"tool": m.group(1), "sec": float(m.group(2)),
                          "ok": m.group(3) == "ok"})
            pending_thought = False
            continue
        if pending_thought and s:
            thoughts.append(s[:200])
            pending_thought = False
    # 工具层 JSONL 里"属于这一轮"的调用 ✓（双重证据 ✓）
    t0 = float(rec.get("t0") or 0)
    jl = 0
    try:
        p = ROOT / "logs" / "mc_mcp.jsonl"
        if p.is_file():
            for x in p.read_text(encoding="utf-8").splitlines()[-40:]:
                try:
                    r = json.loads(x)
                    ts = time.mktime(time.strptime(r.get("at", ""), "%Y-%m-%d %H:%M:%S"))
                except Exception:
                    continue
                if ts >= t0 - 2:
                    jl += 1
    except Exception:
        pass
    return {"has_round": True, "rid": rec.get("rid"), "pid": rec.get("pid"),
            "alive": alive, "status": rec.get("status"), "spoken": rec.get("spoken"),
            "force": rec.get("force"), "task": (rec.get("task") or "")[:120],
            "elapsed": round(time.time() - t0, 1) if t0 else None,
            "sec": rec.get("sec"), "steps": steps, "thoughts": thoughts[-3:],
            "jsonl_calls": jl, "answer": out.strip()[:400]}


def render(s: dict) -> str:
    if not s.get("has_round"):
        return ("[progress] 还没有任何回合 ✓\n"
                "           起一轮：py tools\\talk.py --watch（游戏里说一句 ✓）\n"
                "           或：py tools\\dshrun.py --task-file T.txt --detached ✓")
    head = ("[progress] rid=%s pid=%s ｜ %s ｜ 已跑 %.0fs ｜ 工具调用 %d 次 ｜ 说过了=%s"
            % (s.get("rid"), s.get("pid"),
               "★还在跑★" if s.get("alive") else "已结束", s.get("elapsed") or 0,
               len(s.get("steps") or []), s.get("spoken")))
    lines = [head, "[progress] 任务：%s" % (s.get("task") or "").replace("\n", " ")]
    steps = s.get("steps") or []
    if not steps:
        lines.append("[progress] ⚠ 还没看到任何工具调用 ✓ ⇒ 它这会儿在**想**（还没动手）"
                     "—— 上面的 thoughts 就是它在想什么 ✓")
    for i, st in enumerate(steps, 1):
        lines.append("   %2d. %-14s %5.1fs %s" % (i, st["tool"], st["sec"],
                                                  "ok" if st["ok"] else "★FAIL★"))
    for th in s.get("thoughts") or []:
        lines.append("   …思考：%s" % th)
    if s.get("answer"):
        lines.append("[progress] 最终回答：%s" % s["answer"])
    else:
        lines.append("[progress] 还没有最终回答 ✓（它还在忙 ✓ 上面那几行就是进度 ✓）")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if "--json" in argv:
        print(json.dumps(snapshot(), ensure_ascii=False, indent=1))
        return 0
    if "--watch" in argv:
        try:
            while True:
                sys.stdout.write("\033[2J\033[H")      # 清屏 ✓ 免得刷一屏历史 ✗
                print(render(snapshot()))
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[progress] 退出 ✓")
            return 0
    print(render(snapshot()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
