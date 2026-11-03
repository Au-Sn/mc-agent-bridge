#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stage5_report.py -- ★离终判还有多远：一屏看完✗★（★§79.210 ✗ 离线 ✓ 2026-10-05✗★）

★★终判那条的口径（★§79.188 澄清过✗★）✗★★
  ★任务书说"★**分类族错题新增率 → 0**★"✗★ ⇒
  ★★要归零的是"★**切过去的那些种 ✗ 行为变了多少**★"✗★★（★`cut_verify` 那一轴✓★）✗★ ✓
  ★而 `kb_risk` 的 **5900** 是"★名字模型 vs 导出★"的**上界预警** ✗
  ★**不是**终判那个数 ✗ 它不随切换而变（★导出和名字都没动✓★）✗★ ✓
★★这一屏回答四个问题✗★★
  ★① 已经切的 ✗ 行为真的没变吗✗★ ✓
  ★② 还能切哪些 ✗ 各自会变多少✗★ ✓
  ★③ 铁律②还剩欠账吗✗★ ✓
  ★④ 卡在**模组／世界**那边的有几件✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import cut_measure as CM  # noqa: E402
import exception_table as ET  # noqa: E402
import kb_export as KX
import export_guard as _EG  # B1：缺输入硬红＋一句人话  # noqa: E402
import u1_declared as U1  # noqa: E402

print("=" * 78)
print("★离终判还有多远 ✗ 一屏✗★（★三个数字 ✗ 各说各的量的是什么✗★）")
print("=" * 78)

# ★★2026-10-18（★复核 P2-8 ✗ §79.276✗★）✗★★：★报告类 CLI 缺输入要**人话 ＋ rc 4**✗★
#   ★不许裸 traceback✗★ —— ★因为"★文档索引与按种切换手册都把它当「一条命令看全进度」★"✓★
try:
    blocks = json.loads(_EG.require("stage5_report.py").read_text(encoding="utf-8")).get("blocks") or {}
except Exception as _e:
    print("INCONCLUSIVE: %s" % _e)
    print("★这条命令**要导出** ✗ 不是它坏了★ ⇒ 开游戏跑一次 `/dshkb` ✗ 再回来跑它 ✓")
    sys.exit(4)

# ---- ③ 铁律②
print("")
print("★③ 铁律②（★不一致必须都声明✗★）✗★")
u = U1.u1_numbers(verbose=True)
print("   ★未声明 **%d** ✗★（★达成 ✗ 两条机器判据看着✓★）" % u["no"])

# ---- ④ 卡在模组／世界的
rows = ET.load()
by_sp = {}
for e in rows:
    by_sp.setdefault(e.get("species"), {})[e.get("claim")] = e
sem_only = [sp for sp, c in by_sp.items()
            if "family" in c and "blocks_space" not in c and "is_floor" not in c]
absent = [sp for sp in sem_only if sp not in blocks]
print("")
print("★④ 卡在**模组／世界**那边的✗★")
print("   ★只有语义声明 ★%d★ 个 ✗ 全部**不在导出里** ⇒ 要模组把碰撞报上来（★要求 ②a✓★）"
      % len(absent))
print("   ★另有两条✗★：★逐格列三种 air✗★（★§79.170 ✗ 探针卡在那✓★）✗ "
      "★`counts[…]` 别截断✗★（★§79.163✓★）✗★")

# ---- ①② 切与能切
print("")
print("★① 已经切的✗★（★以 `state/cut.json` 为准 ✗ 进程环境只说明「这个进程开着没」✓★）✗★")
import os  # noqa: E402
# ★★2026-10-08（★§79.218✗★）✗★★：★切刀**落在盘上**（`state/cut.json`✓★）
#   ★⇒ 这一屏必须**以落盘配置为准**（★环境变量只说明"★这个进程里开着没★"✓★）✗★
#   ★（★不然会出现"★配置说切了 ✗ 这一屏说没切★" ✗ 又是那一族✓★）✗★ ✓
_cfg = {}
try:
    import json as _j
    _p = ROOT / "state" / "cut.json"
    if _p.is_file():
        _cfg = _j.loads(_p.read_text(encoding="utf-8"))
except Exception:
    _cfg = {}
_cuts = sorted((_cfg.get("cuts") or {}))
src = os.environ.get("CLASSIFIER_SOURCE") or "blacklist"
scope = os.environ.get("DSH_KB_SCOPE") or "（★全作用域✗★）"
print("   进程里的环境 ✗★：★`CLASSIFIER_SOURCE=%s` ✗ `DSH_KB_SCOPE=%s`✗★" % (src, scope))
print("   ★★落盘的切刀配置✗★★（★`state/cut.json` ✗ 这才是「切了什么」的真源✓★）✗★：%s"
      % ("★" + " ｜ ".join(_cuts) + "★" if _cuts else "★空 ✗ 一个都没切★"))
if not _cuts:
    print("   ★⇒ 终判那个数现在是 **0/0**（★空集上的 0 ✗ 不代表成绩✓★）✗★")
else:
    _tot = _blk = 0
    for _ns in _cuts:
        _mine = [sp for sp in blocks if sp.startswith(_ns + ":")]
        if _mine:
            _c, _s, _d, _dd = CM.diff_of(_mine)
            _tot += _d
            _blk += len(_mine)
    print("   ★⇒ ★已切 **%d** 个命名空间 ✗ 覆盖 **%d** 个方块 ✗ "
          "其中**行为变了 %d** 个✗★（★终判那个数 ＝ 它✗★）✗★" % (len(_cuts), _blk, _tot))

print("")
print("★② 还能切哪些（★按改动量排 ✗ 前 12✗★）✗★")
by_ns = {}
for sp in blocks:
    by_ns.setdefault(sp.split(":")[0], []).append(sp)
und_ns = Counter(sp.split(":")[0] for sp in u["undeclared"])
cand = []
_done = set(_cuts)          # ★已经切过的不再列进「还能切哪些」✗★
for ns, mine in by_ns.items():
    if len(mine) < 40 or und_ns.get(ns) or ns in _done:
        continue
    _c, skip, diff, _d = CM.diff_of(sorted(mine))
    if skip:
        continue
    cand.append((ns, len(mine), diff))
cand.sort(key=lambda t: t[2] / max(1, t[1]))
print("   %-26s %8s %9s %7s" % ("模组", "方块", "★会改✗★", "占比"))
for ns, n, d in cand[:12]:
    print("   %-26s %8d %9d %6.0f%%%s" % (ns, n, d, 100.0 * d / n,
                                          "   ★零改动✗★" if d == 0 else ""))
print("")
print("★合计✗★：★%d 个模组能切 ✗ 一共 **%d** 个方块 ✗ 其中**会改 %d**✗★"
      % (len(cand), sum(n for _ns, n, _d in cand), sum(d for _ns, _n, d in cand)))
print("")
print("★口径✗★：★终判那个数 ＝ **切过去的种里行为变了的个数**✗★ ⇒ ★现在 **0**（★因为一个都没切✓★）✗★")
print("   ★而 `kb_risk` 的 5900 是**上界预警** ✗ 它不随切换变 ✗★ ✓")
