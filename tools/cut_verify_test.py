#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut_verify_test.py -- ★「先切」那些模组：逐签名比对✗★（V1~V4 ✗ 离线 ✓ 2026-10-05）

★★它把 §79.186 那次**手工**比对变成**每次都能查**的判据✗★★ ✓
★★判据（★先写死✗★）✗★★
  ★对参比的命名空间 ✗ 拿**它的每一个方块**比三条**保护签名**✗★：
    ★mapread.is_floor ✗ mapread.blocks_space ✗ mapread.cat✗★ ✓
  ★老路（CLASSIFIER_SOURCE=blacklist）↔ 新路（table）✗★ ✓
  ★★V1 是**计数器**✗★★：★比过的数 ＋ 跳过的数 必须等于方块总数✗★ ⇒
    ★★「全跳光」**不许**看起来像「全一致」（§79.186 那个假 0 的教训）✗★★ ✓
  ★V2 ✗ 一个都不许**静默**跳过✗★ ✓
★★它验的是**哪一层**✗★★：★导出 ＋ 三条签名✗★ ⇒ ★**没有**验世界侧 ✗ 也没有验 table 下的规划✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import blockkb as KB  # noqa: E402
import kb_export as KX  # noqa: E402
import mapread as MR  # noqa: E402
import cut_measure as CM  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== cut_verify：V1~V4（★逐签名比对 ✗ 离线✗★）==")
print("   ★它量的是✗★：★**关／开开关**时三条保护签名（★is_floor／blocks_space／cat✗★）各自的答案 ✗ **变不变**✗★ ✓")
print("   ★它**不是**✗★：★「名字模型 vs 导出」那一比 ✗ 那件事由 `kb_risk` 量（★预测性 ✗ 与开关无关✓★）✗★ ✓")

# ★★B1（★§79.224✗★）✗★★：★缺输入 ⇒ **硬红 ＋ 一句人话**✗★
#   （★原来直接抛 FileNotFoundError ✗ 记成裸 FAIL ✗ 与 kb_risk 的 INCONCLUSIVE 两种口径✓★）
import export_guard as _EG
try:
    _exp_p = _EG.require("cut_verify_test")
except _EG.MissingExport as _e:
    # ★缺输入 ⇒ 硬红 ✗ 但**不打 traceback**✗★（B1 口径：红着说人话）
    print("★FAIL★（缺输入）%s" % _e)
    sys.exit(1)
exp = json.loads(_exp_p.read_text(encoding="utf-8"))
blocks = exp.get("blocks") or {}
FIELDS = [("is_floor", MR.is_floor), ("blocks_space", MR.blocks_space), ("cat", MR.cat)]

by_ns = {}
for sp in blocks:
    by_ns.setdefault(sp.split(":")[0], []).append(sp)
rows = sorted([(ns, v) for ns, v in by_ns.items() if len(v) >= 40],
              key=lambda kv: -len(kv[1]))
print("  ★参比的命名空间✗★：%d 个（★≥40 个方块✗★）✗ 共 %d 个方块"
      % (len(rows), sum(len(v) for _n, v in rows)))

# ★★2026-10-05（★§79.191✗★）✗★★：★比法**只留一份** ✗ 用 `cut_measure.diff_of`✗★ ✓
#   ★（★免得 `cut_verify` 与 `cut_ready` 各算一套又打脸 ✗ §79.188✓★）✗★ ✓
tot_blocks = tot_compared = tot_skip = 0
diff_by_ns = []
for ns, mine in rows:
    cmp_n, skip_n, diff_n, _d = CM.diff_of(mine)
    tot_blocks += len(mine)
    tot_compared += cmp_n
    tot_skip += skip_n
    if diff_n:
        diff_by_ns.append((ns, len(mine), diff_n))

check("V1", (tot_compared + tot_skip) == tot_blocks and tot_compared > 0,
      "★★比过 %d ＋ 跳过 %d ＝ %d ✗ 必须等于参比方块总数 %d✗★★"
      % (tot_compared, tot_skip, tot_compared + tot_skip, tot_blocks))

check("V2", tot_skip == 0,
      "★跳过 **%d** 个 ✗ 必须 0（★有异常要说出来 ✗ 不许咽✓★）" % tot_skip)

_top = sorted(diff_by_ns, key=lambda t: -t[2])[:8]
check("V3", True,
      "★有差异的命名空间 **%d** 个 ✗ 前 8（★模组 ✗ 方块 ✗ 差异✗★）：%s"
      % (len(diff_by_ns), _top or "（★没有 ✗ 一处不差✓★）"))

_worst = sorted(diff_by_ns, key=lambda t: -(t[2] / max(1, t[1])))[:3]
_ratios = ["%s %d/%d=%.0f%%" % (n, d, b, 100.0 * d / max(1, b)) for n, b, d in _worst]
check("V4", True, "★差异占比最高的三个✗★：%s" % (" ｜ ".join(_ratios) or "（★没有✗★）"))

print("=> cut_verify %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
print("   ★说明✗★：本节验的是**导出 ＋ 三条签名** ✗ **没有**验世界侧 ✗ "
      "也没有验 table 模式下的规划（★那两样要游戏✓★）")
sys.exit(0 if ok[0] else 1)
