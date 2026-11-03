#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""declare_collision_test.py -- ★物理裁决器的离线判据★（D1~D6 ✓ 全离线 ✓ 2026-10-03）

★为什么它要紧✗★：★这个工具是**唯一**会被授权"★用碰撞数据改写物理判定★"的东西✗★ ⇒
  ★它一松 ✗ 就等于"★随便拿点数据就把判定改了★"✗★ ✓

★判据（先写死）★
  D1 ★真的翻了的 ⇒ 声明进**碰撞槽** ✗ 等级 `collision`✗★
  D2 ★导出**支持**黑名单 ⇒ **不声明** ✗ 但要**计数**（★"★已经对了★"也是证据✓★）
  D3 ★导出**没覆盖**的物种 ⇒ **绝不**退化成名字兜底 ✗ 计入"★没覆盖★"✗★
  D4 ★导出说 `canopy` ⇒ **拒**✗★（★树冠是语义 ✗ 碰撞看不出✓★）
  D5 ★★全程**不动语义槽**✗★★（★两槽拆分的意思 ✗ 也是铁律 1✓★）
  D6 ★导出不在 ⇒ **抛**✗★（★不许"★那就没得判★"地滑过去✓★）
"""
from __future__ import annotations

import importlib
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ["CLASSIFIER_SOURCE"] = "table"
import blockkb as KB  # noqa: E402
import declare_collision as DC  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def fresh():
    KB.TABLE.clear()
    KB.PHYS.clear()
    KB.REFUSED.clear()
    return KB


DEC = "★★决策级✗★★ ★挡人 False⇒True✗★"
SEM = "★语义级（★两族在「挡人／能站」上一样 ✗ 只是名字不同✓★）"

print("== declare_collision_test：D1~D6 ==")

# ---- 合成的一批行（★真物种名 ✗ 假碰撞数据 ✓ 明确是合成✓★）
ROWS = [
    ("absentbydesign:slab_moss", "pass", "slab", DEC),      # ★黑名单说能穿 ✗ 导出一会儿说它挡人✗★
    ("minecraft:oak_planks", "full", "full", DEC),          # ★导出**支持**黑名单✗★
    ("some:not_in_export", "pass", "slab", DEC),            # ★导出没覆盖✗★
    ("x:canopy_case", "pass", "canopy", DEC),               # ★导出说 canopy ⇒ 拒✗★
    ("x:sem_only", "full", "machine", SEM),                 # ★语义级 ✗ 本工具**不该**碰✗★
]
EXPORT = {"schema": "dshbridge/registry_blocks@1", "count": 4, "errors": 0,
          "blocks": {"absentbydesign:slab_moss": {"family": "slab", "max_height": 0.5},
                     "minecraft:oak_planks": {"family": "full", "max_height": 1.0},
                     "x:canopy_case": {"family": "canopy", "max_height": 1.0}}}

kb = fresh()
# ★先塞一条**语义**条目 ✗ 看它会不会被动✗★
kb.put("x:sem_only", "machine", "registry", "★标签 `crates`（★语义级✓★）")
r = DC.adjudicate(ROWS, EXPORT, kb)
check("D1a", r["declared"] >= 1, "★真的翻了的 ⇒ 要声明✗★ ⇒ declared=%s" % r["declared"])
check("D1b", (kb.PHYS.get("absentbydesign:slab_moss") or {}).get("level") == "collision",
      "★声明进的是**碰撞槽** ✗ 等级 `collision`✗★ ⇒ %s"
      % (kb.PHYS.get("absentbydesign:slab_moss") or {}).get("level"))
check("D1c", kb.classify("absentbydesign:slab_moss", phys=True)["fam"] == "slab",
      "★物理那一侧要看得到 `slab`✗★ ⇒ %s"
      % kb.classify("absentbydesign:slab_moss", phys=True)["fam"])
check("D2", r["agreed"] == 1,
      "★导出支持黑名单 ⇒ **不声明** ✗ 但要计数✗★ ⇒ agreed=%s declared=%s"
      % (r["agreed"], r["declared"]))
check("D3a", r["not_covered"] == 1, "★没覆盖的要**计数**✗★ ⇒ %s" % r["not_covered"])
check("D3b", "some:not_in_export" not in kb.PHYS,
      "★★没覆盖**绝不**退化成名字兜底✗★★")
check("D4a", r["refused"] == 1, "★`canopy` ⇒ 拒✗★ ⇒ refused=%s" % r["refused"])
check("D4b", "x:canopy_case" not in kb.PHYS, "★而它**不许**进碰撞槽✗★")
check("D5", (kb.get("x:sem_only") or {}).get("fam") == "machine",
      "★★全程**不动语义槽**✗★★ ⇒ %s" % (kb.get("x:sem_only") or {}).get("fam"))
check("D5b", kb.classify("x:sem_only", phys=False)["fam"] == "machine",
      "★语义侧照旧看得到 `machine`（★铁律 1 ✓★）✗★")

# ---- D6 导出不在 ⇒ 抛
try:
    DC.read_export(pathlib.Path(tempfile.mkdtemp()) / "nope.json")
    threw = False
except RuntimeError:
    threw = True
check("D6", threw, "★导出不在 ⇒ **抛** ✗ 不许当空✗★")

os.environ.pop("CLASSIFIER_SOURCE", None)
print("=> declare_collision %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
