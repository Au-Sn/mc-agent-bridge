#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_kb_test.py -- ★★"能垫脚"必须**引用方块分类**（★不许名字子串✗★）★★（§79.450）

★★用户的指令✗★★：★"★在本项目的规划里面**引用方块分类的结果** ✗ 不要出现单纯的写哪些拿来垫脚★"✗★★
★★曾经的错（★A2 ✗ 已实测✗★）✗★★：★`is_placeable` 用 `PLACEABLE_KW` 名字子串** ✗★
　★⇒ ★`tombstone:grave_dust`（★**不是方块** ✗ 纯物品✗★）被判"★能垫★" ✗ 于是
　　★`placeable_count` **虚高**（★实测 106 ✗ 实际远少✗★）⇒ ★规划**以为**材料够 ✗ 其实不够✗★ ✓
★★正确来源✗★★：★**导出的碰撞高度**（★§79.401 物理真值层 ✗ 24779 条✗★）✗★
　★**在导出里** ⇒ 是方块 ；★**h ≈ 1.0** ⇒ 整块（★才配当垫脚✗★）
★判据（★离线 ✗ 导出是本地文件✗★）✗★：
　★① ★**整块**（★grass_block ✗ dirt ✗ stone ✗ oak_planks ✗ gravel ✗ sand✗★）⇒ **能垫**✗★
　★② ★**纯物品**（★`tombstone:grave_dust` ✗ `tombstone:gift`✗★）⇒ **不能**（★不在导出里✗★）✗★
　★③ ★**非整块方块**（★fence 1.5 ✗ slab 0.5 ✗ water ✗ torch ✗ chest✗★）⇒ **不能**✗★
　★④ ★**源码纪律**：★`is_placeable` 里**不许**再出现 `PLACEABLE_KW` 之类名字匹配✗★
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import plan3d as P3            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ★(名字, 期望能垫?, 说明)✗★
CASES = [
    ("minecraft:grass_block", True, "整块（★土类✗★）"),
    ("minecraft:dirt", True, "整块"),
    ("minecraft:stone", True, "整块"),
    ("minecraft:cobblestone", True, "整块"),
    ("minecraft:oak_planks", True, "整块（★木板✗★）"),
    ("minecraft:gravel", True, "整块"),
    ("minecraft:sand", True, "整块"),
    ("tombstone:grave_dust", False, "★纯物品 ✗ 不是方块（★曾经的误判✗★）"),
    ("tombstone:gift", False, "★纯物品 ✗ 不是方块（★曾经的误判✗★）"),
    ("minecraft:oak_fence", False, "★h=1.5 ✗ 非整块"),
    ("minecraft:oak_slab", False, "★h=0.5 ✗ 非整块"),
    ("minecraft:water", False, "★液体 ✗ 不能垫"),
    ("minecraft:torch", False, "★h=0 ✗ 不能垫"),
    ("minecraft:chest", False, "★容器 ✗ 不能垫"),
]


def main() -> int:
    checks = []
    bad_n = 0
    for nm, want, why in CASES:
        try:
            got = bool(P3.is_placeable(nm))
        except Exception as e:              # ★不许静默✗★
            got = "ERR:%r" % (e,)
        ok = got == want
        if not ok:
            bad_n += 1
        print("  %-30s 期望=%-5s 实得=%-5s %s ｜ %s"
              % (nm, want, got, "✓" if ok else "★✗★", why))
    checks.append(("逐例判定（%d 例）" % len(CASES), bad_n == 0, "★%d 例错★" % bad_n if bad_n else "全对"))

    # ★④ 源码纪律：is_placeable 不许再用名字匹配✗★
    src = (ROOT / "tools" / "plan3d.py").read_text(encoding="utf-8", errors="replace")
    i = src.find("def is_placeable(")
    j = src.find("\ndef ", i + 10)
    body = src[i:j] if i >= 0 and j > i else ""
    uses_kw = bool(re.search(r"PLACEABLE_KW|\bin\s+low\b|endswith\(", body))
    checks.append(("源码纪律：is_placeable 不用名字匹配", not uses_kw,
                   "★还在用★" if uses_kw else "只看分类"))
    # ★⑤ 必须真的读了分类／导出✗★
    reads_kb = ("_kb_h" in body) or ("_H3D" in body) or ("world3d" in body)
    checks.append(("源码纪律：判定走**分类／导出**", reads_kb,
                   "走导出 ✓" if reads_kb else "★没读分类★"))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => scaffold_kb ★FAIL★（%d 项不对）" % bad)
        print("SCAFFOLDKB ok=0 bad=%d" % bad)
        return 1
    print("  => scaffold_kb PASS ✓（★能垫脚**引用方块分类** ✗ 名单式写法已退役✗★）")
    print("SCAFFOLDKB ok=1 checks=%d cases=%d" % (len(checks), len(CASES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
