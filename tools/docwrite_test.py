#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docwrite_test.py -- 生成物内容没变就不写（W1~W4 离线 2026-10-13 §79.238）

用户裁决 D4：生成物内容没变就不写（先哈希比对），免得每次跑闸门都脏工作区。
★这一条的真因不止"加个比对"✗★：★原来的生成物里写着**生成时间 %H:%M:%S**✗★ ——
★每秒都变 ⇒ 比对永远不相等✗★ ⇒ ★那句时间戳**才是**脏工作区的真因✗★ ✓
★W4 就是你踩的那个症状✗★：★渲染两次 ⇒ `git status` 里那两份文档**必须是干净的**✗★ ✓
"""
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import docwrite as DW

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


tmp = ROOT / "tmp" / "_docwrite_probe.md"
print("== docwrite: W1~W4 ==")

# W1 内容一样 ⇒ 不写（★连 mtime 都不变✗★）
tmp.write_text("甲\n", encoding="utf-8")
m1 = tmp.stat().st_mtime_ns
time.sleep(0.01)
w1 = DW.write_if_changed(tmp, "甲\n")
check("W1", w1 is False and tmp.stat().st_mtime_ns == m1,
      "内容一样 ⇒ 没写（★mtime 不变✓★）⇒ 返回 %s" % w1)

# W2 内容变了 ⇒ 照写
w2 = DW.write_if_changed(tmp, "乙\n")
check("W2", w2 is True and tmp.read_text(encoding="utf-8") == "乙\n",
      "内容变了 ⇒ 写了 ⇒ 返回 %s" % w2)

# W3 真渲染器：连着渲染两次 ⇒ 第二次**不写**
import exception_table as ET
import watchlist as WL
d1 = tmp.parent / "_exceptions_probe.md"
d2 = tmp.parent / "_watch_probe.md"
import json
rows = [{"species": "a:b", "claim": "family", "verdict": "full", "evidence": "registry",
         "source": "★判据自测✗★", "by": "docwrite_test", "at": "2026-10-13 00:00:00"}]
ET.render(rows, d1)
m3 = d1.stat().st_mtime_ns
time.sleep(0.01)
ET.render(rows, d1)
check("W3", d1.stat().st_mtime_ns == m3,
      "★例外表渲染两次 ⇒ 第二次没写★（mtime 不变）—— 原来里面有「生成时间 %H:%M:%S」")
WL.render(rows, d2)
m4 = d2.stat().st_mtime_ns
time.sleep(0.01)
WL.render(rows, d2)
check("W3b", d2.stat().st_mtime_ns == m4, "★观察名单渲染两次 ⇒ 第二次没写★")

# W4 ★你踩的那个症状★：跑过真渲染器之后，**再跑一遍**不许再动它
#   ★口径✗★：比的是"★两次渲染之间★"（哈希）✗ 不是"★与 HEAD 一致★" ——
#     后者在**这次**格式刚改过时本来就该不同（★那一次不算脏 ✗ 那一次是**迁移**✓★）✗★ ✓
def _h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


_truth = ROOT / "docs" / "例外表.md"
_watch = ROOT / "docs" / "观察名单.md"
if _truth.is_file():
    ET.render()
if _watch.is_file():
    WL.render()
_h1 = (_h(_truth), _h(_watch))
if _truth.is_file():
    ET.render()
if _watch.is_file():
    WL.render()
_h2 = (_h(_truth), _h(_watch))
check("W4", _h1 == _h2 and all(_h1),
      "★连着渲染两次 ⇒ 第二次一个字节都没动★（例外表／观察名单）⇒ %s"
      % ("稳定 ✓" if _h1 == _h2 else "★还在变✗★"))

for f in (tmp, d1, d2):
    f.unlink(missing_ok=True)
print("      （★已清✗★：临时探针文件都删了）")

print("=> docwrite %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
