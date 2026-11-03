#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stdio_guard_test.py -- ★"印得出吗"的专项判据★（离线 ✓ 秒级 ✓ 不需要游戏 ✓）

WHY ✓（P151 那一族 ✗ —— 2026-10-01 晚补 ✓）：
  Windows 上 `py` 的 stdout 默认是 **cp936（GBK）** ✗（实测 `getpreferredencoding=cp936` ✓
  `PYTHONUTF8`／`PYTHONIOENCODING` **都没设** ✓）⇒ 脚本只要印一个 GBK 编不出的字符
  （★最典型 ✓ `✓` U+2713 ／ `✗` U+2717★ —— 本项目**每一条回执**都在用它们 ✗）
  ⇒ `print` 当场抛 `UnicodeEncodeError` ✗ ⇒ ★整条闸门红 ✗ 而东西本身是好的 ✗★

  P151 当时只修了 `mc_mcp.py` **一个文件** ✗ ⇒ 这一族**没有闸门** ✗
  ⇒ 2026-10-01 晚实测：`cut34_seam_check.py`（离线闸门里的一项 ✓）**当场红** ✗
  ⇒ 全仓审计：79 个脚本"真会印危险字符" ✗ 其中 **12 个没 pin** ✗（已逐个补 ✓）

判据（先写死 ✓ 不许事后改 ✗）
  S1 扫到的 `tools/*.py` **>= 150** ✓（★判据不许因为 glob 写错而**假绿**✗★ P152 ✓）
  S2 每个文件都 **parse 得动** ✓（读文件用 `utf-8-sig` ✗ —— 带 BOM 的源文件
     ★Python 自己是认的✗★ ✓ 第一版判据用 `utf-8` 读 ⇒ 把 `_ua_probe.py` 误报成坏 ✓
     这是**尺子错**不是东西错 ✓ 与 P22/P110 同族 ✓）
  S3 ★真会印危险字符的脚本，必须 pin 了 stdout✗★
     ——"真会印"＝危险字符落在 **`print`/`say`/`out`/`log`/… 的实参表达式里** ✓
     （文档字符串／注释里的**不算** ✗ —— 不然会把 `floor_test.py` 那种**假红** ✗）
  S4 ★判据自己要能红✗★：拿**合成源码**跑一遍扫描器 ⇒ 没 pin 的**必须被抓出来** ✓
     加了 pin 的**必须不被抓** ✓（P123/P149 同族：一个永远绿的判据等于没有 ✓）
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PRINTERS = {"print", "say", "out", "log", "err", "warn", "note", "die"}
PIN = "reconfigure(encoding="

ok = [True]


def say(s: str) -> None:
    print(s)


def check(name: str, cond: bool, note: str = "") -> None:
    ok[0] &= bool(cond)
    say("  %-4s %s %s" % (name, "✓" if cond else "★不符✗★", note))


def gbk_ok(ch: str) -> bool:
    try:
        ch.encode("gbk")
        return True
    except Exception:
        return False


def danger_in(node: ast.AST) -> str:
    hits = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            for ch in sub.value:
                if ord(ch) > 127 and not gbk_ok(ch):
                    hits.append(ch)
    return "".join(sorted(set(hits)))


def is_stdout_call(node: ast.Call) -> bool:
    f = node.func
    if isinstance(f, ast.Name) and f.id in PRINTERS:
        return True
    if isinstance(f, ast.Attribute) and f.attr in ("write", "writelines"):
        base = f.value
        if isinstance(base, ast.Attribute) and base.attr in ("stdout", "stderr"):
            return True
        if isinstance(base, ast.Name) and base.id in ("stdout", "stderr"):
            return True
    return False


def scan(src: str) -> tuple:
    """⇒ (危险字符, 有没有 pin ✓)。★src 必须已经 decode 过（判据本体不碰磁盘 ✗）★"""
    has_pin = PIN in src
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None, has_pin
    hits = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and is_stdout_call(node):
            for a in list(node.args) + [k.value for k in node.keywords]:
                hits += danger_in(a)
    return "".join(sorted(set(hits))), has_pin


say("== stdio_guard：★「印得出吗」✗★（P151 那一族 ✓ 离线 ✓） ==")

files = sorted((ROOT / "tools").glob("*.py"))
check("S1", len(files) >= 150, "扫到 %d 个 tools/*.py ✓（下限 150 ✓）" % len(files))

bad_parse = []
danger_all = []
nopin = []
for p in files:
    src = p.read_text(encoding="utf-8-sig", errors="replace")
    hits, has_pin = scan(src)
    if hits is None:
        bad_parse.append(p.name)
        continue
    if hits:
        danger_all.append(p.name)
        if not has_pin:
            nopin.append((p.name, hits))

check("S2", not bad_parse, "parse 不了：%s" % (", ".join(bad_parse) if bad_parse else "0 个 ✓"))
check("S3", not nopin,
      "会印危险字符的 %d 个 ✓ ★没 pin 的 %d 个✗★ %s"
      % (len(danger_all), len(nopin),
         ("⇒ " + ", ".join("%s(%s)" % (n, "".join("U+%04X" % ord(c) for c in h))
                           for n, h in nopin[:8])) if nopin else ""))

# ★S4：负向自检✗★ —— 判据得**证明自己会红** ✓（合成的两段源码 ✓ 不碰真文件 ✓）
fake_bad = 'print("  %s ✓" % x)\n'
fake_good = ('import sys\ntry:\n    sys.stdout.reconfigure(encoding="utf-8")\n'
             'except Exception:\n    pass\nprint("  %s ✓" % x)\n')
hb, pb = scan(fake_bad)
hg, pg = scan(fake_good)
check("S4", bool(hb) and not pb and bool(hg) and pg,
      "合成样例：没 pin 的%s被抓 ✓ 有 pin 的%s不被抓 ✓"
      % (" 已" if (hb and not pb) else " ★没✗★",
         " 也" if (hg and pg) else " ★错✗★"))

say("=> stdio_guard %s（危险脚本 %d ／ 检查文件 %d ✓）"
    % ("PASS ✓" if ok[0] else "★FAIL✗★", len(danger_all), len(files)))
sys.exit(0 if ok[0] else 1)
