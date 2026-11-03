#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_risk_test.py -- ★迁移风险图的判据★（R1~R4 ✓ 全离线 ✓ 注入 shape_fn ✓ 2026-10-04）"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import kb_risk as KR  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def exp(blocks):
    return {"schema": "dshbridge/registry_blocks@1", "blocks": blocks}


print("== kb_risk_test：R1~R4 ==")

# ★★R1：★"★族名不同但两条判定一样★" ⇒ 必须算**一致**✗★★
#   （★`full` vs `machine` 就是这种 ✗ 迁移**不改变决策** ✓ 若这条错了 ✗ 风险图会吓人✓★）
# ★★注意✗★★：★导出族必须是**闭集里**的（★full／slab／snow_layer／fence_15／canopy／
#   none／other／liquid✓★）✗ 而 `machine` 是**判定族** ✗ 拿它当导出族会被 `family_from_export` 拒✗★ ✓
#   ★要验的是"★族名不同但两条判定一样★"✗ 所以用 **`full`（导出）vs `machine`（模型）**✗★ ✓
r = KR.risk_map(exp({"a:x": {"family": "full", "max_height": 1.0}}), lambda sp: "machine")
check("R1", (r["agree"] == 1) and (r["disagree"] == 0),
      "★`full`（碰撞）vs `machine`（模型）⇒ 都挡人都能站 ⇒ 算**一致**✗★ ⇒ %s" % r)

# ★R2：★真的翻了 ⇒ 必须算**不一致**✗★（★`pass` vs `slab`✓★）
r = KR.risk_map(exp({"a:y": {"family": "slab", "max_height": 0.5}}), lambda sp: "pass")
check("R2", (r["disagree"] == 1) and (r["worst"] == ["a:y"]),
      "★`slab` vs `pass` ⇒ 挡人真的翻了 ⇒ 算**不一致** ✗ 并进名单✗★ ⇒ %s" % r)

# ★R3：★`canopy`（★碰撞看不出的语义族✓★）⇒ 计入 `no_family` ✗ **不算**风险✗★
r = KR.risk_map(exp({"a:z": {"family": "canopy", "max_height": 1.0}}), lambda sp: "canopy")
check("R3", (r["no_family"] == 1) and (r["disagree"] == 0) and (r["agree"] == 0),
      "★`canopy` 交语义层 ⇒ 既不算一致也不算风险✗★ ⇒ %s" % r)

# ★R4：★按模组分组要能算（★风险条数 ✗ 这就是"★先修谁★"的依据✓★）
r = KR.risk_map(exp({"m:a": {"family": "slab", "max_height": 0.5},
                     "m:b": {"family": "full", "max_height": 1.0},
                     "n:c": {"family": "slab", "max_height": 0.5}}),
                lambda sp: "pass" if sp.endswith(":a") else "full")
check("R4", (r["by_ns"]["m"]["disagree"] == 1) and (r["by_ns"]["m"]["agree"] == 1)
      and (r["by_ns"]["n"]["agree"] == 1),
      "★分组：m 一险一对 ✗ n 一对（★`full` vs `slab` 两条判定一样 ⇒ 一致✗★）✗★ ⇒ %s"
      % {k: v for k, v in r["by_ns"].items()})

print("=> kb_risk %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
