#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""a3_wired_test.py -- ★A3 的开关到底**接没接上**★（W1~W5 ✗ 离线 ✗ 2026-10-18 §79.304）

★为什么另写一条✗★：★`pathplan_height_test`（★H1~H5✗★）**自己内部**就把两臂都测了 ✗
  所以它在 `AUTO_STEP_BY_HEIGHT=0／1` 下**都 PASS** ✗★ ⇒ ★我那 `a3_ab.py` 的
  判法"★两臂结论必须不同★"**是错的**✗★ ✓（★它比的是**判据结论** ✗ 不是**行为**✗★）✗★ ✓

★★正确判法✗★★：★找一个 **"★名字与高度打架★"的方块** ✗ 两臂**必然给出相反答案**✗★ ✓
  ★比如 `mod:sneaky_slab`（★名字像半砖 ✗ 实际碰撞顶高 **1.4**✗★）✗★：
    · ★关（★名字档✗★）⇒ **True** ✗ ⇒ ★规划**以为**能抬腿上去 ✗ = **假可达**✗★（★A3 要治的就是这个✗★）
    · ★开（★高度档✗★）⇒ **False** ✓ ⇒ ★真话✗★ ✓
  ★反例 `mod:odd_thing`（★名字不带任何模式 ✗ 实际 **0.3** 高✗★）✗★：
    · ★关 ⇒ **False** ✗（★假不可达✗★）✗ ★开 ⇒ **True** ✓✗★ ✓

★`BY_HEIGHT` 是 **import 时**从环境算的**常量**✗★ ⇒ ★两臂必须**两个子进程**✗★ ✓
★口径✗★：★`高度拿不到 ⇒ False`（★保守 ✗ 绝不静默回落名字✗ 见 `pathplan.py:56`✓★）✗★ ✓
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★★例子：名字 ∨ 高度 谁说了算（★`height_of` 用注入 ✗ 不去读导出✗★）★★
CASES = [
    # (方块名, 注入的高度, 名字档期望, 高度档期望)
    ("mod:sneaky_slab", 1.4, True, False),      # ★名字像半砖 ✗ 实际 1.4 ⇒ 关=假可达✗★
    ("mod:odd_thing", 0.3, False, True),        # ★名字无模式 ✗ 实际 0.3 ⇒ 关=假不可达✗★
    ("mod:oak_slab", 0.5, True, True),          # ★两边都对 ⇒ **不**该有分歧（★防"永远相反"✗★）
    ("mod:oak_stairs", 1.0, False, False),      # ★两边都对✗★
    ("mod:unknown_height", None, False, False),  # ★高度拿不到 ⇒ 高度档**保守 False**✗★
]

_HELPER = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import pathplan as P
cases = json.loads(sys.argv[2])
P.height_of = lambda b: (None if cases[b][1] is None else float(cases[b][1]))
out = {}
for name in cases:
    try:
        out[name] = bool(P.is_auto_step(name))
    except Exception as e:
        out[name] = "ERR:%s" % type(e).__name__
print("@@RESULT@@" + json.dumps(out, ensure_ascii=False))
'''


def arm(flag: str) -> dict:
    """★一个臂 ✗ 一个子进程✗★（★`BY_HEIGHT` 在 import 时定✗★）"""
    payload = {c[0]: [c[0], c[1]] for c in CASES}
    env = dict(os.environ)
    env["AUTO_STEP_BY_HEIGHT"] = flag
    hp = os.path.join(ROOT, "tmp", "_a3_helper.py")
    with open(hp, "w", encoding="utf-8", newline="\n") as f:
        f.write(_HELPER)
    r = subprocess.run([sys.executable, "-B", "-X", "utf8", hp, TOOLS,
                        json.dumps(payload, ensure_ascii=False)],
                       cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    blob = (r.stdout or "") + (r.stderr or "")
    for line in blob.splitlines():
        if line.startswith("@@RESULT@@"):
            return json.loads(line[len("@@RESULT@@"):])
    raise RuntimeError("子进程没吐结果 ✗ %s" % blob.strip()[-300:])


ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


def main() -> int:
    print("== a3_wired: W1~W5（★A3 的开关到底接没接上✗★）==")
    off = arm("0")
    on = arm("1")
    print("  关（名字档）：%s" % json.dumps(off, ensure_ascii=False))
    print("  开（高度档）：%s" % json.dumps(on, ensure_ascii=False))
    print("")
    for i, (name, h, exp_off, exp_on) in enumerate(CASES, 1):
        got_off = off.get(name)
        got_on = on.get(name)
        check("W%d" % i, got_off is exp_off and got_on is exp_on,
              "%-20s 高 %-6s 关=%s（★应 %s✗★）✗ 开=%s（★应 %s✗★）"
              % (name, h, got_off, exp_off, got_on, exp_on))
    # ★★W6 关键✗★★：★两臂**必须**在"打架"的例子上给出**不同**答案 ✗
    #   ★否则就是"★开关没接上★"（★这才是 A3 要的证据 ✓ 而不是"两臂判据结论相同"✗★）✗★ ✓
    diff = [c[0] for c in CASES if off.get(c[0]) != on.get(c[0])]
    check("W6", len(diff) >= 2,
          "★两臂在**打架**的例子上不同✗★ ⇒ 不同的：%s（★≥2 ✗ 少于此就是没接上✗★）"
          % (diff or "（没有 ✗ 说明开关没接上✗★）"))
    # ★W7 计数器✗★：★至少跑了 5 个例子 × 2 臂 ✗ 不许空转✗★
    check("W7", len(CASES) >= 5 and len(off) == len(CASES) and len(on) == len(CASES),
          "★计数器✗★：%d 例 × 2 臂 = %d 次判断（★≥10 ✗ 不许空转✓★）"
          % (len(CASES), len(off) + len(on)))
    print("")
    print("=> a3_wired %s" % ("PASS ✓" if ok[0] else "FAIL"))
    sys.stdout.write("A3WIRED ok=%d diff=%d cases=%d\n" % (1 if ok[0] else 0, len(diff), len(CASES)))
    return 0 if ok[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
