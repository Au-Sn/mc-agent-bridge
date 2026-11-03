#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_ladder_test.py -- 两条不相交的梯子（L1~L6 离线 2026-10-13 §79.241）

用户裁决 A4：物理梯 collision > 物理实验；语义梯 registry > 实验 > 名字兜底。
★注册表在语义上是权威 ✗ **在物理上永远不许压过"亲手摸过"**✗★ ——
原代码一条混合梯 `collision>registry>experiment>name_fallback` 是把两条轴混成一条，
那正是 §11 想堵的侧门。
★这条判据守的就是那句「不许压过」✗★：★它是**机械**的 ——
★`registry` **根本不在物理梯上**✗★ ✓
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import exception_table as ET

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


def ent(claim, ev, verdict=True, **kw):
    d = {"species": "a:b", "claim": claim, "verdict": verdict, "evidence": ev,
         "source": "★判据自测：在 tmp 里跑，不写盘✗★", "by": "evidence_ladder_test"}
    d.update(kw)
    return d


print("== evidence_ladder: L1~L6 ==")

# L1 物理 ＋ collision ⇒ 收
_o1, w1 = ET.validate(ent("blocks_space", "collision"))
check("L1", _o1, "物理 ＋ `collision` ⇒ 收（%s）" % str(w1)[:40])

# L2 物理 ＋ registry ⇒ 拒（R3）
_o2, w2 = ET.validate(ent("blocks_space", "registry"))
check("L2", (not _o2) and ("R3" in w2), "物理 ＋ `registry` ⇒ 拒（R3）")

# L3 语义 ＋ registry ⇒ 收
_o3, w3 = ET.validate(ent("family", "registry", verdict="full"))
check("L3", _o3, "语义 ＋ `registry` ⇒ 收（%s）" % str(w3)[:40])

# L4 语义 ＋ collision ⇒ 拒（R7）
_o4, w4 = ET.validate(ent("family", "collision", verdict="full"))
check("L4", (not _o4) and ("R7" in w4),
      "语义 ＋ `collision` ⇒ 拒（R7 ✗ 两条梯不相交）⇒ %s" % str(w4)[:60])

# L5 ★关键那条★：registry **不在**物理梯上 ＋ 两条梯的**头**不一样
check("L5",
      ("registry" not in ET.EVIDENCE_PHYS)
      and (ET.EVIDENCE_PHYS[0] == "collision")
      and (ET.EVIDENCE_SEM[0] == "registry")
      and (ET.EVIDENCE_PHYS != ET.EVIDENCE_SEM),
      "★`registry` 不在物理梯上★（★这就是「不许压过」的机械形态✗★）✗ "
      "物理梯 %s ／ 语义梯 %s" % ("／".join(ET.EVIDENCE_PHYS), "／".join(ET.EVIDENCE_SEM)))

# L6 ★旧账不许被新规打翻✗★：现有表**每一条**仍要合规
rows = ET.load()
_bad = []
for e in rows:
    okk, why = ET.validate(e)
    if not okk:
        _bad.append((e.get("species"), e.get("claim"), why[:40]))
check("L6", not _bad,
      "现有 **%d** 条仍全部合规（★R7 不许把旧账打翻✗★）⇒ 不合规的 %d 条：%s"
      % (len(rows), len(_bad), _bad[:3] or "（没有 ✓）"))

# ★★2026-10-18（★复核 P1-5 ✗ §79.277✗★）✗★★：★两套口径必须**合一** ✗
#   而且"★物理主张 ＋ experiment 证据★"必须真的进**碰撞槽** ✗ 不许静默落进语义槽✗★ ✓
import blockkb as _KB  # noqa: E402
check("L7", tuple(_KB.PHYS_LEVELS) == tuple(ET.EVIDENCE_PHYS),
      "★`blockkb.PHYS_LEVELS` 必须**等于** `ET.EVIDENCE_PHYS`★（★两套口径就是一个病✓★）⇒ %s vs %s"
      % (tuple(_KB.PHYS_LEVELS), tuple(ET.EVIDENCE_PHYS)))
_r_amb = _KB.put("ladder_probe:amb", "full", "experiment", "★判据自测✗★")
_why_amb = _KB.REFUSED[-1]["why"] if _KB.REFUSED else ""
check("L7b", _r_amb is False and ("两条梯子" in _why_amb or "phys" in _why_amb),
      "★`experiment` 两条梯子共有 ⇒ **不给主张必须拒收并说清**★ ⇒ %s" % _why_amb[:64])
_r_p = _KB.put("ladder_probe:p", "full", "experiment", "★判据自测✗★", phys=True)
check("L7c", _r_p and ("ladder_probe:p" in _KB.PHYS) and ("ladder_probe:p" not in _KB.TABLE),
      "★给 `phys=True` ⇒ 必须进**碰撞槽** ✗ 不许落进语义槽★ ⇒ put=%s／PHYS=%s／TABLE=%s"
      % (_r_p, "ladder_probe:p" in _KB.PHYS, "ladder_probe:p" in _KB.TABLE))
_r_s = _KB.put("ladder_probe:s", "full", "experiment", "★判据自测✗★", phys=False)
check("L7d", _r_s and ("ladder_probe:s" in _KB.TABLE) and ("ladder_probe:s" not in _KB.PHYS),
      "★给 `phys=False` ⇒ 必须进**语义槽**★ ⇒ put=%s" % _r_s)

print("=> evidence_ladder %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
