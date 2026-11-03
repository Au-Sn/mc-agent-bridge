#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_round.py —— 验"回合独立化 ＋ 进度可见"这两块的**纯逻辑** ✓

★为什么要它★ ✗（防漂移 ✓）：
  以后往 `mc_mcp.py` 里加一个工具 ✓ 而忘了在 `talk.py` 的 `PROGRESS_PHRASES` 里配人话 ✓
  ⇒ 那一类动作**永远不会在游戏里漏进度** ✗ —— 而且**不会有任何报错** ✗（沉默的漏 ✓）
  ⇒ 这种"以后悄悄变坏"的事，必须由**测试**来挡 ✗ 不能靠记性 ✓
"""
from __future__ import annotations

import tempfile

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))

import talk      # noqa: E402
import dshrun    # noqa: E402
import mc_mcp    # noqa: E402

fails: list[str] = []
lines: list[str] = []

# ① 每个 MCP 工具都要有进度人话（除了几个"不该出声"的 ✓）
SILENT = {"say", "stop", "idle", "bot_state2"}          # say 是它自己说话 ✓ 别重复 ✗
missing = [t["name"] for t in mc_mcp.TOOLS
           if t["name"] not in talk.PROGRESS_PHRASES and t["name"] not in SILENT]
lines.append("%s 进度句覆盖：工具 %d 个 ｜ 没配的（除已知静默的）= %s"
             % ("ok  " if not missing else "FAIL", len(mc_mcp.TOOLS), missing))
if missing:
    fails.append("缺进度句：%s" % missing)

# ② 进度句本身要短（进游戏聊天 ✗ 太长难看 ✓）
for k, v in talk.PROGRESS_PHRASES.items():
    if not (0 < len(v) <= 12):
        fails.append("进度句太长：%s=%r" % (k, v))
lines.append("%s 进度句长度都 ≤12 字：%d 句" % ("ok  " if not fails else "FAIL",
                                                len(talk.PROGRESS_PHRASES)))

# ③ `progress_lines()` 要从 err 文件里挑出"有用的那几行" ✓
tmp = ROOT / "logs" / "runs" / "TESTPROBE.err"
tmp.parent.mkdir(parents=True, exist_ok=True)
tmp.write_text("noise line\n"
               "[mc_mcp] bot_state 0.3s ok\n"
               "dsh: reasoning:\n"
               "[mc_mcp] walk_to 3.1s ok\n"
               "more noise\n", encoding="utf-8")
got = dshrun.progress_lines({"err": str(tmp)}, 6)
want_has = any("walk_to" in g for g in got) and any("reasoning" in g for g in got)
lines.append("%s progress_lines 挑出 %d 行：%s" % ("ok  " if want_has else "FAIL", len(got), got))
if not want_has:
    fails.append("progress_lines")
tmp.unlink(missing_ok=True)

# ④ 进程存活判定 ✓（自己一定活着 ✓ 一个不可能存在的 pid 一定死 ✓）
a1 = dshrun._alive(os.getpid())
a2 = dshrun._alive(999999)
lines.append("%s _alive(self)=%s _alive(999999)=%s" % ("ok  " if (a1 and not a2) else "FAIL", a1, a2))
if not (a1 and not a2):
    fails.append("_alive")

# ⑤ `last_round_brief()`：★跨轮记忆★ ✓ 从"上一轮的落盘记录"里拼一句给新会话 ✓
tmp2 = ROOT / "logs" / "runs" / "TESTBRIEF.err"
tmp3 = ROOT / "logs" / "runs" / "TESTBRIEF.out"
tmp2.write_text("[mc_mcp] bot_state 0.3s ok\n"
                "[mc_mcp] walk_to 3.1s ok\n"
                "[mc_mcp] walk_to 2.0s FAIL\n", encoding="utf-8")
tmp3.write_text("没走到，卡在 4131.5 被挡\n", encoding="utf-8")
br = talk.last_round_brief({"err": str(tmp2), "out": str(tmp3), "out_text": ""})
ok5 = ("walk_to(失败)" in br) and ("被挡" in br) and ("上一轮" in br)
lines.append("%s last_round_brief = %r" % ("ok  " if ok5 else "FAIL", br[:150]))
if not ok5:
    fails.append("last_round_brief")
tmp2.unlink(missing_ok=True)
tmp3.unlink(missing_ok=True)

# ⑥ `prune_runs()`：旧回合文件会被清掉 ✓ 但**当前那个绝不动** ✗
import time as _t  # noqa: E402
maketmp = ROOT / "logs" / "runs" / "TESTOLD.keep"
maketmp.write_text("x", encoding="utf-8")
n_pruned = dshrun.prune_runs(keep=100000)          # keep 很大 ⇒ **什么也不该删** ✓
still = maketmp.is_file()
lines.append("%s prune_runs(keep=100000) 删了 %d 个 ✓ 临时文件还在=%s"
             % ("ok  " if (n_pruned == 0 and still) else "FAIL", n_pruned, still))
if not (n_pruned == 0 and still):
    fails.append("prune_runs")
maketmp.unlink(missing_ok=True)

lines.append("")
lines.append("FAILS=%d" % len(fails))
Path(tempfile.gettempdir()) / "round_test.txt".write_text(
    "\n".join(lines), encoding="utf-8")
print("round tests: %d FAIL" % len(fails))
raise SystemExit(1 if fails else 0)
