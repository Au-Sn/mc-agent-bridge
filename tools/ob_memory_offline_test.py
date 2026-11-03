#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ob_memory_offline_test.py -- ★障碍记忆的**自足**判据★（T1~T4 ✓ 离线 ✓ 2026-10-03 ✓）

★为什么重写而不是改旧的★：★旧 `ob_memory_test.py` 直接戳真文件 `logs/obstacles.json`✗
  ⇒ ① 它会跟**当前世界状态**耦合（红着就进不了闸门）✗ ② 更糟：★我一验证就**把真记忆覆盖了**✗★
  ⇒ ★口径★：★判据**不许动真数据**，要用**临时文件**★（本仓库别处已经这么做）

★判据（先写死）★
  T1 ★落盘★：`_obst_add(...)` ＋ `_obst_save()` ⇒ **临时**文件里要有那一格（名字对、`at>0`）
     （★这条顺带守住 §79.66 那个真 bug：`mcp_geo` 缺 `BLOCKED_WHY` 时它会红★）
  T2 ★跨进程记得★：换个**新进程**（★也指向同一临时文件★）⇒ 读回来的 `BLOCKED` 里有它
  T3 ★过期的丢掉★：塞一条 25 小时前的 ⇒ 新进程**不该**读回它（TTL 24 小时）
  T4 ★★不碰真数据★★：整段跑完，真的 `logs/obstacles.json` **一个字节都没变**（含 mtime）
★沙盒注意★：子进程**不许用管道**（EPERM）⇒ stdout 重定向到**临时文件**
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_geo as G  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== ob_memory_offline_test：T1~T4 ==")
REAL = G.OBST_FILE
real_before = (REAL.stat().st_mtime_ns, REAL.stat().st_size) if REAL.is_file() else None
TMP = Path(tempfile.mkdtemp()) / "obstacles.json"
G.OBST_FILE = TMP                                  # ★只改**本模块**的那个常量✓★

G.BLOCKED.clear()
G.BLOCKED_LV.clear()
G._obst_add(4199, 199, "computercraft:computer_command", 199)
G._obst_save()
d = json.loads(TMP.read_text(encoding="utf-8")) if TMP.is_file() else {}
cell = (d.get("cells") or {}).get("4199,199") or {}
check("T1", cell.get("block") == "computercraft:computer_command" and float(cell.get("at") or 0) > 0,
      "★落盘里有那一格✗★：%s（★这条也守 §79.66 那个真 bug✓★）" % (cell or "（没有 ✗）"))

# ★T3 先塞一条过期的（25 小时前）★
d.setdefault("cells", {})["4000,4000"] = {"block": "minecraft:stone", "at": time.time() - 25 * 3600}
TMP.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8", newline="\n")

out = Path(tempfile.mkdtemp()) / "child.txt"
code = ("import sys, pathlib; sys.path.insert(0, r'%s');\n"
        "import mcp_geo as G; G.OBST_FILE = pathlib.Path(r'%s');\n"
        "import mc_mcp as M; M.BLOCKED.clear(); M._obst_load();\n"
        "print('LOADED', len(M.BLOCKED), sorted(M.BLOCKED)[:4])\n" % (str(ROOT / "tools"), str(TMP)))
with open(out, "w", encoding="utf-8") as fh:
    p = subprocess.run([sys.executable, "-c", code], stdout=fh, stderr=subprocess.STDOUT,
                       cwd=str(ROOT), timeout=180)
line = out.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1] if out.is_file() else ""
check("T2", "(4199, 199)" in line, "★新进程读回里有它✗★：%s" % (line[:110] or "（空 ✗）"))
check("T3", "(4000, 4000)" not in line, "★25 小时前那条**没被读回**✗★（TTL 24 小时 ✓）")
check("T3b", p.returncode == 0, "★子进程退出码 0✗★（%s）" % p.returncode)

real_after = (REAL.stat().st_mtime_ns, REAL.stat().st_size) if REAL.is_file() else None
check("T4", real_after == real_before,
      "★★真数据一个字节没动✗★★（之前＝%s ｜ 之后＝%s）" % (real_before, real_after))

G.OBST_FILE = REAL                                  # ★还原✓★
print("=> ob_memory_offline %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
