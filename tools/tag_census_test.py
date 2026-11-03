#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tag_census_test.py -- ★标签普查工具的离线判据★（C1~C6 ✓ 全离线 ✓ 秒级 ✓ 2026-10-03）

★为什么要有它✗★：`tools/tag_census.py` 是阶段 0 的**证据来源** ✗ 而它自己**不能被真 jar 当判据**
  （★真 jar 会变 ✗ 那是"与世界耦合"的老毛病 ✓ 见 ㉖✓★）⇒ 用**合成 fixture** 钉住它的解析与闭包 ✓

★判据（先写死）★
  C1 标签路径：`tags/blocks` 与 `tags/block` **都认** ✗ 别的目录**不认**✗★
  C2 宇宙路径：`assets/<ns>/blockstates/…` 与 `data/<ns>/loot_tables/blocks/…` 认 ✗ 别的不认✓★
  C3 值的三种形态：裸字符串 ／ `#引用` ／ `{"id":…, "required":false}` ✗ 都要读对✗★
  C4 ★传递闭包✗★：`#A` 里的物种要能传到引用 A 的标签里 ✗ **环也不能死**✗★
  C5 反查：物种 → 它到底在哪些标签里 ✓
  C6 ★一趟扫✗★：合成一个 **zip 假 jar** ＋ 一个目录 ✗ 两者都要被抓到✗★
     （★zip 里的 `assets/` 与 `data/` 名字也要进宇宙 ✓★）
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import tag_census as TC  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== tag_census_test：C1~C6 ==")

# ---- C1 标签路径 ----
_c1 = (("data/x/tags/blocks/a.json", "x:a"), ("data/x/tags/block/a.json", "x:a"),
       ("data/x/tags/items/a.json", None), ("data/x/tags/blocks/a/b.json", "x:a/b"),
       ("data/x/tags/blocks/a.txt", None), ("assets/x/blockstates/a.json", None))
_bad = [(n, TC.tag_id(n)) for (n, w) in _c1 if TC.tag_id(n) != w]
check("C1", not _bad, "★标签路径✗★ %s" % (_bad or "全对 ✓（★两种拼法都认 ✓ items 不认✓★）"))

# ---- C2 宇宙路径 ----
_c2 = (("assets/x/blockstates/a.json", "x:a"), ("data/x/loot_tables/blocks/a.json", "x:a"),
       ("assets/x/models/block/a.json", None), ("data/x/loot_tables/entities/a.json", None))
_bad2 = []
for n, w in _c2:
    got = TC.species_of_asset(n)
    if got is None:
        got = TC.species_of_loot(n)
    if got != w:
        _bad2.append((n, got, w))
check("C2", not _bad2, "★宇宙路径✗★ %s" % (_bad2 or "全对 ✓"))

# ---- C3 值的三种形态 ----
_d = {"values": ["minecraft:stone", "#minecraft:base", {"id": "x:y", "required": False},
                 {"id": "#x:z"}]}
check("C3a", TC._members(_d) == ["minecraft:stone", "x:y"],
      "★裸串与 dict 都要读✗★ ⇒ %s" % TC._members(_d))
check("C3b", TC._refs(_d) == ["minecraft:base", "x:z"],
      "★`#引用`（含 dict 里的）都要认✗★ ⇒ %s" % TC._refs(_d))

# ---- C4 传递闭包（含环）----
_mem = {"a:leaf0": {"x:p"}, "a:leaf1": {"x:q"}, "a:leaf2": {"x:r"}}
_ref = {"a:top": {"a:mid"}, "a:mid": {"a:leaf0", "a:leaf1"}, "a:loop1": {"a:loop2"},
        "a:loop2": {"a:loop1", "a:leaf2"}}
_full = TC.closure(_mem, _ref)
check("C4a", _full["a:top"] == {"x:p", "x:q"},
      "★引用要传递✗★ ⇒ %s" % sorted(_full["a:top"]))
check("C4b", _full["a:loop1"] == {"x:r"},
      "★环不能死 ✗ 而且环里的成员要拿到✗★ ⇒ %s" % sorted(_full["a:loop1"]))
check("C4c", _full.get("a:missing") is None or _full["a:missing"] == set(),
      "★引用不存在的标签 ⇒ 空 ✗ 不许抛✗★")

# ---- C5 反查 ----
_inv = TC.invert(_full)
check("C5", _inv["x:r"] == {"a:leaf2", "a:loop1", "a:loop2"},
      "★物种 → 标签✗★ ⇒ %s" % sorted(_inv["x:r"]))

# ---- C6 一趟扫：假 zip ＋ 目录 ----
tmp = pathlib.Path(tempfile.mkdtemp())
jar = tmp / "fake_mod.jar"
with zipfile.ZipFile(jar, "w") as z:
    z.writestr("data/fx/tags/blocks/leafy.json",
               json.dumps({"values": ["fx:leafy_block", {"id": "fx:other", "required": False}]}))
    z.writestr("data/fx/tags/block/old_style.json", json.dumps({"values": ["fx:old_block"]}))
    z.writestr("assets/fx/blockstates/leafy_block.json", "{}")
    z.writestr("data/fx/loot_tables/blocks/other.json", "{}")
    z.writestr("assets/fx/blockstates/nested/two.json", "{}")
d = tmp / "kubejs" / "data" / "fx2" / "tags" / "blocks"
d.mkdir(parents=True)
(d / "packmade.json").write_text(json.dumps({"values": ["#fx:leafy"]}), encoding="utf-8")
src, uni, st = TC.scan([jar], [tmp / "kubejs" / "data"])
m2, r2 = TC.build(src)
f2 = TC.closure(m2, r2)
check("C6a", st["tags"] == 3, "★zip 两个 ＋ 目录一个 ＝ 3✗★ ⇒ %s" % st["tags"])
check("C6b", {"fx:leafy_block", "fx:nested/two"} <= uni,
      "★宇宙要收 blockstates ✗ 含嵌套路径✗★ ⇒ %s" % sorted(uni))
# ★分工✗★：`scan()` 只收 assets/loot ★标签成员由调用方并进去★（`main` 里 `uni |= from_tag`）
#   ⇒ ★判据按**同一条并集**断言 ✗ 否则测的是"我说的话"而不是"工具的话"✗★
_uni_all = uni | set(TC.invert(f2))
check("C6b2", "fx:old_block" in _uni_all,
      "★只在标签里出现过的种 ✗ 并进宇宙后必须在✗★ ⇒ %s" % sorted(_uni_all))
check("C6c", "fx:other" in uni, "★宇宙也要收 loot_tables ✗ 哪怕没有 blockstate✗★")
check("C6d", f2["fx2:packmade"] == {"fx:leafy_block", "fx:other"},
      "★目录里的包标签引用 zip 里的标签 ⇒ 要跨界解析✗★ ⇒ %s" % sorted(f2["fx2:packmade"]))

# ---- C7 ★裸名要补 `minecraft:`✗★（★2026-10-04 修的真瑕疵 ✓ 见 §79.120✓★）----
check("C7a", TC._norm("bamboo_planks") == "minecraft:bamboo_planks",
      "★裸名 ⇒ 补 `minecraft:`✗★")
check("C7b", TC._norm("minecraft:oak_planks") == "minecraft:oak_planks",
      "★已经带命名空间的 ⇒ 一字不动✗★")
_m = TC._members({"values": ["black_carpet", "#minecraft:planks", {"id": "oak_door"}]})
check("C7c", _m == ["minecraft:black_carpet", "minecraft:oak_door"],
      "★`_members` 只收**非引用**的 ✗ 且裸名要补全✗★ ⇒ %s" % _m)

print("=> tag_census %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
