#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""relay_guard_test.py -- ★★"自己给自己排班"的四条骨架✗★★（R1~R5 ✓ 离线 ✓ 2026-10-03 ✓）

★它护的是中继的**自动续跑**✗（★`tools/acp_talk.py`✓★）✗ 而那东西**会自己动手**✗★
  ⇒ ★所以判据不是"它跑不跑" ✗ 而是"★它凭什么跑 ✗ 撞到什么会停 ✗ 能不能关✗★" ✓

★四条骨架（★先写死 ✗ 少一条都是隐患✓★）★
  ★R1 ★**有上限**✗★：★一轮里连着推的次数有**硬上限**✗（★`--continue-max` ✗ 且落在 1..50✓★）
  ★R2 ★**要有活才推**✗★：★续跑那一支必须**依赖未完成的活**✗★
     （★否则就是"没人说话它自己找话说" ✗ 那是空转烧钱✓★）
  ★R3 ★**干跑就停**✗★：★推了它**一个工具都没调** ⇒ 停下来✗★（★不许无限推✓★）
  ★R4 ★**能关**✗★：★有 `--continue-off` 这类开关✗★（★出事时人得能一下子摁住✓★）
  ★R5 ★★它**现在是活的**✗★★：★跑着的中继日志里要有 `CONTINUE:` 那行✗★
     （★写着"能自动"与"真的在自动"是两件事 ✗ §79.60 刚教过✓★）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "acp_talk.py"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== relay_guard_test：自动续跑的骨架 R1~R5 ==")
t = SRC.read_text(encoding="utf-8", errors="replace")

m = re.search(r'continue-max"?\s*\)\s*or\s*(\d+)', t)
dflt = int(m.group(1)) if m else None
check("R1", dflt is not None and 1 <= dflt <= 50,
      "★`--continue-max` 默认＝%s ⇒ ★必须有上限 ✗ 且落在 1..50✗★" % dflt)

check("R2", bool(re.search(r"RUNNABLE_JOBS|open_jobs", t)) and ("open jobs exist" in t),
      "★续跑要**有活才推**✗★：★源码用 `RUNNABLE_JOBS()` ✗ 而那行日志也写着 "
      "「if open jobs exist」✗★ ✓")

check("R3", bool(re.search(r"dry round|dry_round|no tool calls", t)),
      "★「干跑就停」✗★ 那句在源码里 ✓（★推了没动手 ⇒ 停 ✗ 不许无限推✓★）")

# ★★R4 改口径✗★★（2026-10-03 ✓ 我第一版猜的是 `--continue-off` ✗ 而真码里是
#   ★`HOLD` **停止文件** ＋ `cont_on`✗★ ⇒ ★判据要认**机制** ✗ 别认我猜的那个名字✗★）★
check("R4", ("HOLD" in t) and ("cont_on" in t),
      "★有两条**摁住**的路✗★：★`HOLD` 停止文件（★放个文件就停 ✓ 最硬✓★）＋ `cont_on` 开关 ✓")

# ★R6：★跳过"在等"的活✗★（★`wait_s` 还没到 ⇒ 别去戳它 ✓ 这条是我读真码才看出来的✓★）
check("R6", "RUNNABLE_JOBS" in t and bool(re.search(r"wait", t)),
      "★只推「**现在就该动**」的活✗★：★在 `wait_s` 里等的会被 `RUNNABLE_JOBS()` 跳过✗★ ✓")

# ★R5：★跑着的中继日志里有没有那行✗★
logs = sorted((ROOT / "logs").glob("*relay*")) + sorted((ROOT / "logs").glob("*talk*"))
line = None
for f in logs:
    try:
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if "CONTINUE:" in ln:
                line = (f.name, ln.strip())
    except Exception:
        pass
check("R5", line is not None,
      ("★日志 %s ⇒ %s✗★" % (line[0], line[1][:120])) if line
      else "★**没找到**带 `CONTINUE:` 的日志✗★ ⇒ ★「能自动」与「在自动」必须分开 ✗ 这条**测不了**✗★")

print("=> relay_guard %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
