#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conflict_rule_test.py -- ★"★多族冲突必须被碰撞裁决掉★"的判据✗★（C1~C4 ✗ 离线 ✓ 2026-10-05）

★★它守的是 §79.200 那条裁定✗★★：★多族冲突时**问碰撞**✗★ ⇒
★能通过 ⇒ `pass` ✗ 挡人 ⇒ 非 pass 那个 ✗ **读不到 ⇒ 才许报冲突**✗★ ✓
★★为什么要有它✗★★：★不然这条规则只活在"★我那次跑了一遍★"里 ✗
★下次谁改了 `expected_from_tags` ✗ **没人知道**✗★ ✓（★§79.162 那条纪律的同一形态✓★）✗★ ✓
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

import divergence as DV  # noqa: E402
import kb_export as KX
import export_guard as _EG  # B1：缺输入硬红＋一句人话  # noqa: E402
import mapread as MR  # noqa: E402
import tag_census as TC  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== conflict_rule：C1~C4（★裁定：多族冲突交给碰撞裁决✗★）==")
blocks = json.loads(_EG.require("conflict_rule_test.py").read_text(encoding="utf-8")).get("blocks") or {}
jars, vanilla, roots = TC.sources_of([])
src, _a, _b = TC.scan(jars, roots, want_universe=False)
vsrc, _c, _d = TC.scan(vanilla, [], want_universe=False)
mem, ref = TC.build(src + vsrc)
full = TC.closure(mem, ref)
from_tag = TC.invert(full)
ft = TC.family_tags(full)

n_total = n_multi = n_arb = n_unread = n_left = n_skip = 0
left = []
for sp in sorted(from_tag):
    fams = [f for f, ids in ft.items() if any(t in ids for t in (from_tag.get(sp) or ()))]
    got = {DV.TAG_FAMILY[f] for f in fams if f in DV.TAG_FAMILY}
    if len(got) <= 1:
        continue                         # ★不是多族 ✗ 本判据不管✗★ ✓
    n_total += 1
    n_multi += 1
    e = blocks.get(sp) or {}
    fx = e.get("family")
    if fx is None:
        n_unread += 1                    # ★导出里没有 ⇒ 碰撞读不到 ⇒ **允许**冲突✗★ ✓
        continue
    exp, _why, conf = DV.expected_from_tags(
        fams, passable=(fx in ("none", "pass", "liquid")))
    if conf:
        n_left += 1
        if len(left) < 6:
            left.append((sp, fx, "／".join(sorted(got))))
    else:
        n_arb += 1

check("C1", n_left == 0,
      "★★★多族冲突里 ✗ **读得到碰撞却仍判冲突**的：**%d** 条✗★★★%s"
      % (n_left, ("  例：" + str(left[:3])) if left else "（★一条都没有 ✓★）"))
check("C2", (n_arb + n_unread + n_left) == n_multi,
      "★计数器✗★：已裁决 %d ＋ 碰撞读不到 %d ＋ 仍冲突 %d ＝ %d ✗ 必须等于多族总数 %d"
      % (n_arb, n_unread, n_left, n_arb + n_unread + n_left, n_multi))
check("C3", n_arb > 0,
      "★真的有**裁决过**的 ✗ 不然这条判据是空的✗★ ⇒ 已裁决 **%d** 条" % n_arb)

# ★C4 ✗ 裁决**不许**动物理（★与 P4／E6 同一口径✗★）
_sp = "minecraft:cherry_leaves"
_before = MR.blocks_space(_sp)
DV.expected_from_tags(["叶子", "花", "可替换"], passable=False)
_after = MR.blocks_space(_sp)
check("C4", _before == _after,
      "★★裁决**只管语义** ✗ `blocks_space` 必须不变✗★★ ⇒ %s ⇒ %s" % (_before, _after))

# ★C5 ✗ 裁决函数里**不许**出现名字侧的东西（★它只许看 `passable`✗★）
_src = (ROOT / "tools" / "divergence.py").read_text(encoding="utf-8")
_body = _src[_src.find("def expected_from_tags"):]
_body = _body[:_body.find("\ndef ", 10)]
check("C5", ("MR." not in _body) and ("shape(" not in _body),
      "★★裁决函数**只许看 `passable`** ✗ 不许碰名字侧（★`MR.`／`shape(`✓★）✗★★")

print("=> conflict_rule %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
print("   ★多族物种 %d ✗ 已裁决 %d ✗ 碰撞读不到 %d ✗ 仍冲突 %d★"
      % (n_multi, n_arb, n_unread, n_left))
sys.exit(0 if ok[0] else 1)
