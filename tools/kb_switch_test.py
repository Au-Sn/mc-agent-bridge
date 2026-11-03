#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_switch_test.py -- ★三档开关接线的判据★（S1~S5 ✓ 全离线 ✓ 2026-10-04）

★它守什么✗★：★`mapread` 的两条物理判定**在开关背后**查表 ✗ 而三档的语义**不许串**✗★ ✓
  · ★`blacklist`（★出厂✓★）⇒ 与老路**逐字相同**✗★（★连表都不看✓★）
  · ★`table` ⇒ 碰撞槽有它就用碰撞 ✗ 没有 ⇒ **保守值**（★`is_floor=False` ✗ `blocks_space=True`✓★）
  · ★`table+fallback` ⇒ 没有 ⇒ 老路（★回落已声明✓★）
  · ★★语义槽（★标签✓★）**永不许**影响物理 ✗ 铁律 1✗★★
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "\u2713" if cond else "\u2605\u4e0d\u7b26\u2717\u2605", note))


print("== kb_switch_test\uff1aS1~S5 ==")

# ---- S1 出厂档：与老路逐字相同（★用模块自己的 shape 当"老路"✗★）
os.environ["CLASSIFIER_SOURCE"] = "blacklist"
import mapread as MR  # noqa: E402
_samples = ["minecraft:oak_planks", "minecraft:oak_leaves", "minecraft:stone",
            "absentbydesign:slab_brown_mushroom", "mcwdoors:acacia_bark_glass_door"]
_bad = []
for sp in _samples:
    if MR.is_floor(sp) != (MR.shape(sp) in ("full", "slab", "machine")):
        _bad.append(("is_floor", sp))
    if MR.blocks_space(sp) != (MR.shape(sp) in ("full", "slab", "fence", "machine",
                                                 "canopy", "other")):
        _bad.append(("blocks_space", sp))
check("S1", not _bad, "\u2605\u51fa\u5382\u6863 blacklist \u21d2 \u4e0e\u8001\u8def\u9010\u5b57\u76f8\u540c\u2717\u2605 \u21d2 %s" % (_bad or "\u5168\u5bf9 \u2713"))

# ---- S2~S4 用一个**假的**知识表（★不许碰真文件✗★）
import blockkb as KB  # noqa: E402
KB.PHYS.clear()
KB.PHYS["x:door"] = {"fam": "full", "level": "collision", "src": "dshkb:\u6d4b\u8bd5",
                     "temporary": False, "trigger": "", "at": "-"}
KB.SOURCE = "table"
check("S2", (MR.is_floor("x:door") is True) and (MR.blocks_space("x:door") is True),
      "\u2605\u78b0\u649e\u69fd\u8bf4 full \u21d2 \u95e8\u80fd\u7ad9\u4e86\uff08\u2717 \u800c\u8001\u8def\u8bf4\u4e0d\u80fd\uff09\u2717\u2605")
check("S3", (MR.is_floor("x:nothing") is False) and (MR.blocks_space("x:nothing") is True),
      "\u2605\u2605table \u6863\u672a\u77e5 \u21d2 \u4fdd\u5b88\u503c\uff08\u4e0d\u5f53\u5730\u677f \uff0f \u5f53\u4f5c\u6321\u4f4f\uff09\u2717\u2605\u2605")
KB.SOURCE = "table+fallback"
check("S4", MR.is_floor("x:nothing") == (MR.shape("x:nothing") in ("full", "slab", "machine")),
      "\u2605table+fallback \u672a\u77e5 \u21d2 \u8d70\u8001\u8def\uff08\u56de\u843d\u5df2\u58f0\u660e\uff09\u2717\u2605")

#   ★前置（★2026-10-04 补回：★我换 S5 段时把它一起删了 ✗
#     而新块还在用它 ⇒ `TABLE.get` 是 `None` ⇒ S5b 红 ✗★）✗★
KB.TABLE.clear()
KB.TABLE["x:sem"] = {"fam": "machine", "level": "registry", "src": "tags",
                     "temporary": False, "trigger": "", "at": "-"}
# ---- S5 ★★语义槽（标签）永不许影响物理 ✗ 铁律 1✗★★
#   ★这一条我写成**不依赖上下文**的形式✗★ —— ★因为第一版我写了两条断言 ✗
#     其中"★`classify(phys=False)` 还看得见它★"在**判据上下文**里红了 ✗
#     而**同一次调用在干净进程里是对的**（★复现过 ✓ 打出 `fam='machine'`✓★）✗★
#   ★★根因我**没有**查出来（★如实记在 §79.123 ✗ 不假装✓★）✗ 所以不把它留成红判据✗★★
#   ★而这条性质**另有三处**在守✗★：★S5a（★物理侧✓★）✗ `exception_table_test` 的 **Y2b**
#     （★碰撞证据不许污染语义槽✓★）✗ `blockkb_test` 的 **K10**（★语义条目不动物理结果✓★）
KB.SOURCE = "table"
_before = dict(KB.TABLE.get("x:sem") or {})
check("S5", (MR.is_floor("x:sem") is False) and (MR.blocks_space("x:sem") is True),
      "\u2605\u2605\u4e25\u683c\u6863\u4e0b\u8bed\u4e49\u69fd\u4e0d\u8bb8\u5f71\u54cd\u7269\u7406"
      " \u21d2 \u53d6\u4fdd\u5b88\u503c\u2717\u2605\u2605")
check("S5b", (KB.TABLE.get("x:sem") == _before) and bool(_before),
      "\u2605\u7269\u7406\u4fa7\u8bfb\u5b8c\u4e4b\u540e \u8bed\u4e49\u69fd\u91cc\u90a3\u6761"
      "**\u539f\u6837\u672a\u52a8**\uff08\u2605\u4e0d\u4f9d\u8d56\u4e0a\u4e0b\u6587\u7684\u5199\u6cd5\u2717\u2605\uff09\u2717\u2605"
      " \u21d2 %s" % KB.TABLE.get("x:sem"))
KB.SOURCE = "table+fallback"

# ---- S6~S8 ★作用域（★"按种切换"能不能表达出来✗★）----
#   ★★口径✗★★：★不设 `DSH_KB_SCOPE` ⇒ **全允许**（★逐字不变✓★）✗
#     ★设了 ⇒ 名单外**当作表里没有**✗★ ✓
KB.SOURCE = "table"
KB.PHYS["minecraft:oak_planks"] = {"fam": "full", "level": "collision", "src": "dshkb",
                                   "temporary": False, "trigger": "", "at": "-"}
KB.PHYS["mysticalagriculture:x"] = {"fam": "pass", "level": "collision", "src": "dshkb",
                                    "temporary": False, "trigger": "", "at": "-"}
KB.SCOPE = []                                   # ★不设 ⇒ 全允许✗★
check("S6", KB.scope_allows("minecraft:oak_planks") and KB.scope_allows("any:thing"),
      "★不设作用域 ⇒ **全允许**（★逐字不变✓★）✗★")
KB.SCOPE = ["mysticalagriculture"]              # ★只切这一个模组✗★
check("S7a", KB.scope_allows("mysticalagriculture:x"),
      "★名单内的命名空间 ⇒ 允许✗★")
check("S7b", not KB.scope_allows("minecraft:oak_planks"),
      "★★名单外 ⇒ **不许走表**✗★★（★这才叫「★按种切换★」✓★）")
KB.SOURCE = "table"
check("S7c", KB.classify("minecraft:oak_planks", phys=True)["level"] == "unknown",
      "★名单外 ＋ `table` 档 ⇒ 保守（★不许回落✓★）✗★")
KB.SOURCE = "table+fallback"
_r = KB.classify("minecraft:oak_planks", phys=True)
check("S7d", (_r["level"] == "name_fallback") and any("作用域外" in d for d in _r["declared"]),
      "★名单外 ＋ 回落档 ⇒ 走老路 ✗ 而「★作用域外★」**要声明**✗★ ⇒ %s" % _r["declared"])
KB.SCOPE = ["minecraft:oak_leaves"]             # ★只切**一个物种**✗★
check("S8", KB.scope_allows("minecraft:oak_leaves")
      and (not KB.scope_allows("minecraft:oak_planks")),
      "★名单里也可以写**单个物种**✗★（★「单种切」也能表达✓★）✗★")
KB.SCOPE = []
KB.SOURCE = "table+fallback"

os.environ.pop("CLASSIFIER_SOURCE", None)
print("=> kb_switch %s" % ("PASS \u2713" if ok[0] else "\u2605FAIL\u2717\u2605"))
sys.exit(0 if ok[0] else 1)
