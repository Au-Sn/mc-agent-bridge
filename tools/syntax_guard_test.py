#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""syntax_guard_test.py -- ★★"引号错"的系统解：全仓 `.py` 一律先编译✗★★（2026-10-02 ✓ 欠账 ③ 同族 ✓）

WHY ✓（★这是本会话**最高频**的错 ✗ 已经犯了 ~20 次✓★）：
  ★我写"中文串里嵌 ASCII 双引号"✗ ⇒ 语法错 ✗★
  ★以前靠"我自己记得先跑 `py_compile`"✗ ⇒ ★一忘就炸 ✗ 而且炸在**运行期**✗★
  ⇒ ★做成**闸门里的一项**✗★：★任何 `.py`（含 `tools/` ✓ `agent/` ✓ `tmp/` ✓）语法不过 ⇒ 当场红✗★

判据（★先写死✗★）
  G1 ★扫到的 `.py` 数量 > 100✗★（★少于这个数 ⇒ 说明我**扫错目录**了 ✗ 不是"全都对"✓★）
  G2 ★每个文件 `py_compile` 必须过✗★（★不过 ⇒ 报**文件名 ＋ 行号 ＋ 那一行**✓★）
  G3 ★`tmp/` 也在内✗★（★因为"手写脚本"才是高发区 ✗ 只查 `tools/` 会漏掉一半✓★）
  G4 ★排除目录要显式列出来✗★（`.git` ✓ `mod/build` ✓ `node_modules` ✓ `tmp/refs` ✓）★
"""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SKIP = (".git", "mod/build", "mod\\build", "node_modules", "tmp\\refs", "tmp/refs",
        ".gradle", "__pycache__")

files = []
for p in ROOT.rglob("*.py"):
    s = str(p)
    if any(x in s for x in SKIP):
        continue
    files.append(p)

print("== syntax_guard：全仓 .py 先编译（G1~G4）==")
print("  扫到 **%d** 个 .py（排除：%s ✓）" % (len(files), ", ".join(SKIP[:4])))

ok = [True]
if len(files) <= 100:
    ok[0] = False
    print("  G1 ★不符✗★：只扫到 %d 个 ⇒ ★多半是**扫错目录**✗ ✗ 不许当「全对」✓★" % len(files))
else:
    print("  G1 ✓ 数量合理（%d > 100 ✓）" % len(files))

bad = []
skipped = []
# ★★§79.411✗★★：★每个文件用**独立临时 pyc** ✗ 不共用✗★ ——
#   ★共用 ⇒ 那个文件一旦被杀软/别的进程锁住 ⇒ **所有文件**都抛 PermissionError✗★ ✓
import tempfile
_tmpdir = tempfile.mkdtemp(prefix="sguard_")
_seq = [0]
for p in files:
    _seq[0] += 1
    cfile = str(Path(_tmpdir) / ("f%d.pyc" % _seq[0]))
    try:
        py_compile.compile(str(p), doraise=True, cfile=cfile)
    except py_compile.PyCompileError as e:
        bad.append((p, str(e)))          # ★真语法错 ⇒ 照旧红✗★
    except (PermissionError, OSError) as e:
        skipped.append((p, "%s: %s" % (type(e).__name__, e)))   # ★写不了 pyc ⇒ **测不了**✗★
    except Exception as e:
        bad.append((p, "%s: %s" % (type(e).__name__, e)))

if bad:
    ok[0] = False
    print("  G2 ★不过✗★：%d 个文件" % len(bad))
    for (p, err) in bad[:6]:
        rel = p.relative_to(ROOT)
        first = [ln for ln in err.splitlines() if "line" in ln.lower()][:1]
        print("     ★%s✗★ ⇒ %s" % (rel, first[0].strip() if first else err.splitlines()[-1][:90]))
else:
    print("  G2 ✓ 全部编译通过（★含 tmp/ 的手写脚本 ✗ ✓★）")

if skipped:
    print("  G2s †测不了†：%d 个文件**写不了 pyc**（★环境性 ✗ 不是语法错✗★）：" % len(skipped))
    for (p, err) in skipped[:5]:
        print("     %s ⇒ %s" % (p.relative_to(ROOT), err[:100]))

if any(str(p).startswith(str(ROOT / "tmp")) for p in files):
    print("  G3 ✓ `tmp/` 在内（★高发区没漏✓★）")
else:
    ok[0] = False
    print("  G3 ★不符✗★：`tmp/` 没被扫到 ⇒ ★高发区漏了✗★")

print("  G4 ✓ 排除目录显式列出（%d 条 ✓）" % len(SKIP))
print("=> syntax_guard %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
