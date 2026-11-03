#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generated_docs_test.py -- 拿数去撞**生成物**（G1~G6 离线 2026-10-05 §79.214）

为什么要它（§79.213 那条口径的机械形态）：
  凡「生成物」（文档／报表／名单），每次都要拿一个「它该包含什么」的断言去撞它。
  这一路「上游更新了，下游没接线」已出现三次（§79.188 §79.196 §79.213）。
六条（只撞**能重算**的；重算不了的明说）：
  G1 乙档-改动对账清单.md 的头条数 == 重算
  G2 只有语义声明-清单.md 的个数 == 重算
  G3 对模组的要求-清单.md 里那份名录 == 重算
  G4 DoD-对账表.md 里的未声明数 == 重算
  G5 文档索引.md 里带★的 == 文件真的在
  G6 挑刀表那三个数（甲／乙／丙）与重算一致（闸门里没有它，这里只查文档里写死的）
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import exception_table as ET
import kb_export as KX
import export_guard as _EG  # B1：缺输入硬红＋一句人话
import u1_declared as U1

D = ROOT / "docs"
ok = [True]


RESULTS = []      # ★★2026-10-18（★§79.280✗★）✗★：每条**逐小条记结果**✗
                  #   ★这样才能说清"★红的是**哪几条**★" —— ★只红在 G1／G2／G3（★缺导出✗★）
                  #     就该报"★有东西没拿到★" ✗ 不是"★判据坏了★"✓★


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    RESULTS.append((tag, bool(cond)))
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


def read(name):
    p = D / name
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


print("== generated_docs：G1~G6（拿数撞生成物）==")
# ★★2026-10-18（★复核 P0-1 抓的**掩盖**✗★）✗★★：
#   ★现象✗★：★`_EG.require(...)` 写在**模块级** ✗ 缺导出时整条判据在跑到 `G4` **之前**就崩✗★ ⇒
#     ★而 `G4`（★DoD 表里的未声明数 == 重算✗★）**根本不读导出**（★它只用 `U1.u1_numbers()`✓★）✗★ ⇒
#     ★★一条真红被"缺输入"的 traceback 掩盖了**三个月**✗★★ ✓
#   ★口径✗★：★"★缺输入★"只该影响**真的读输入的那几条**（G1／G2／G3✓★）✗
#     ★不读输入的（G4／G5／G6）**必须照跑**✗ —— ★一条判据里"★一条崩 ✗ 全条埋★"就是欺骗✓★ ✓
_export_err = ""
try:
    blocks = json.loads(_EG.require("generated_docs_test.py").read_text(encoding="utf-8")).get("blocks") or {}
except Exception as _e:
    blocks = None
    _export_err = "%s: %s" % (type(_e).__name__, str(_e)[:160])
rows = ET.load()
by_sp = {}
for e in rows:
    by_sp.setdefault(e.get("species"), {})[e.get("claim")] = e
sem_only = sorted(sp for sp, c in by_sp.items()
                  if "family" in c and "blocks_space" not in c and "is_floor" not in c)
absent = [sp for sp in sem_only if sp not in blocks] if blocks is not None else None

# ---- G1 乙档对账清单的头条数（★**读导出**的那条 ⇒ 缺输入就硬红 ✗ 但不许连坐别人✗★）
t1 = read("乙档-改动对账清单.md")
m1 = re.findall(r"\*\*(\d+)\*\* 处改动待世界确认", t1)
if blocks is None:
    check("G1", False, "★缺输入（硬红）✗ 这一条**读导出** ✗ 不是判据坏★：%s" % _export_err)
else:
    import cut_measure as CM  # noqa: E402
    B = ["rechiseled", "allthecompressed", "mcwroofs", "mcwdoors", "luminax", "exdeorum",
         "connectedglass", "croptopia", "xycraft_override", "alltheores", "crystalix"]
    tot = 0
    for ns in B:
        mine = sorted(sp for sp in blocks if sp.startswith(ns + ":"))
        if mine:
            _c, _s, d, _dd = CM.diff_of(mine)
            tot += d
    check("G1", bool(m1) and int(m1[-1]) == tot,
          "乙档清单写 **%s** 处 ✗ 重算 **%d** 处" % (m1[-1] if m1 else "没匹配到", tot))

# ---- G2 只有语义声明清单的个数（★读导出 ✗ 缺输入就硬红✗★）
t2 = read("只有语义声明-清单.md")
m2 = re.findall(r"\*\*(\d+)\*\* 个物种", t2)
if absent is None:
    check("G2", False, "★缺输入（硬红）✗ 这一条**读导出** ✗ 不是判据坏★：%s" % _export_err)
else:
    check("G2", bool(m2) and int(m2[0]) == len(absent),
          "那份清单写 **%s** 个 ✗ 重算 **%d** 个" % (m2[0] if m2 else "没匹配到", len(absent)))

# ---- G3 要求单里的名录（★读导出 ✗ 缺输入就硬红✗★）
t3 = read("对模组的要求-清单.md")
if absent is None:
    check("G3", False, "★缺输入（硬红）✗ 这一条**读导出** ✗ 不是判据坏★：%s" % _export_err)
else:
    n3 = sum(1 for sp in absent if ("| `%s` |" % sp) in t3)
    check("G3", n3 == len(absent),
          "要求单附录里点了 **%d** / %d 个名字" % (n3, len(absent)))

# ---- G4 DoD 表里的未声明数
u = U1.u1_numbers()
t4 = read("DoD-对账表.md")
m4 = re.findall(r"未声明 (\d+)", t4)
check("G4", bool(m4) and int(m4[-1]) == u["no"],
      "DoD 表写未声明 **%s** ✗ 重算 **%d**" % (m4[-1] if m4 else "没匹配到", u["no"]))

# ---- G5 索引里带★的 == 文件真的在
t5 = read("文档索引.md")
# 索引里的行长这样： | ★[名字](名字) | 是什么 |
starred = re.findall(r"\| (★?)\[([^\]]+)\]\(", t5)
bad = [n.strip() for s, n in starred
       if (s == "★") != ((D / n.strip()).is_file())]
check("G5", not bad, "索引里**标错**的：%s" % (bad[:5] or "（没有 ✓）"))

# ---- G6 例外表条数 vs DoD 表里写的
m6 = re.findall(r"例外表 (\d+) 条", t4)
check("G6", bool(m6) and int(m6[-1]) == len(rows),
      "DoD 表写例外表 **%s** 条 ✗ 现在是 **%d** 条" % (m6[-1] if m6 else "没匹配到", len(rows)))

# ★★2026-10-18（★§79.280✗★）✗★★：★"★缺输入★"与"★判据坏★"要说清✗★ ——
#   ★红的**只有** `G1／G2／G3`（★它们只是读不到导出✗★）⇒ ★真类别是"★有东西没拿到★"✗★
#   ⇒ ★`INCONCLUSIVE` ＋ **rc=4**✗★（★与全项目的口径一致✗★）✗★ ✓
_reds = [t for (t, o) in RESULTS if not o]
_missing_only = [t for t in _reds if t in ("G1", "G2", "G3")]
if blocks is None and _reds and (_reds == _missing_only):
    print("INCONCLUSIVE: ★缺输入（硬红 ✗ 不是判据坏）★ ⇒ 红的只有 %s ✗ "
          "★G4／G5／G6 已经跑过且通过✗★" % _reds)
    sys.exit(4)
print("=> generated_docs %s" % ("PASS ✓" if ok[0] else "FAIL"))
print("   查不了的（如实）：生成物里那些需要**世界／游戏**才能重算的数，本条判据不碰")
sys.exit(0 if ok[0] else 1)
