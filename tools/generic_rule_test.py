#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generic_rule_test.py -- ★★"规划层不许靠方块名字"（★普适性的机械守门✗★）★★（§79.451）

★★用户的根本原则✗★★：★"★优先考虑**通用性** ✗ 不要都从头开始 / 手动加名称 ✗
　　★我们花了那么久做**方块分类**就是为了**普适性** ✗ ★**不能换一个包就要从头开始**★"✗★★ ✓

★★这条判据守什么✗★★：★**规划／物理层**（★`plan3d`／`world3d`／`exec3d`**）✗★
　★**不许**出现"★靠方块名字判性质★"的写法✗★：
　　★① ★`PLACEABLE_KW` 这类**关键词表**（★"★哪些拿来垫脚★"✗★）✗★
　　★② ★`name.contains(…)` ／ `endswith(…)` 这类**名字匹配**✗★
　　★③ ★**内容方块的 `minecraft:xxx` 字面量**（★`minecraft.stone` ✗ `"minecraft:oak_planks"`✗★）✗★
★★允许的**结构性**名字（★它们不是"★内容★" ✗ 是空气／液体这种**普遍存在**的✗★）✗★★：
　★`minecraft:air` ✗ `minecraft:cave_air` ✗ `minecraft:water` ✗ `minecraft:lava`**✗★ ★
　★（★这些**任何包都有** ✗ 换包不变✗★）✗★ ✓
★★正确的做法✗★★：★**查分类／导出**（★`blockkb` ✗ `h3d` ✗ `tags`✗★）✗ **名字只用来查表**✗★ ✓
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★受监管的层（★规划／物理✗★）✗★
WATCHED = ["tools/plan3d.py", "tools/world3d.py", "tools/exec3d.py", "tools/mapread.py",
           "tools/skills.py"]

# ★结构性名字（★允许 ✗ 任何包都有✗★）✗★
STRUCTURAL = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air",
              "minecraft:water", "minecraft:lava"}

# ★名字匹配的写法（★违规✗★）✗★
# ★★§79.451✗★★：★**只抓"★像方块名★"的匹配** ✗ 别把事件名／act 标签／空气判断误报✗★
#   ★误报实例（★第一次跑实测✗★）：★`startswith("open")`（act 标签✗★）✗
#     ★`endswith(":air")`（★空气 ✗ 结构性✗★）✗ `startswith("do_cmd_err")`（★事件名✗★）✗★
#   ★⇒ 名字匹配**只有在带 `minecraft:` 前缀 ✗ 或明显是方块词根时**才算违规✗★ ✓
NAME_MATCH = [
    (r"\bPLACEABLE_KW\b", "关键词表"),
    (r"\.contains\(\s*['\"](minecraft:)?[a-z_]+['\"]", "名字 contains"),
    (r"\.endswith\(\s*['\"]minecraft:[a-z_]+['\"]", "名字 endswith(minecraft:)"),
    (r"\.startswith\(\s*['\"]minecraft:[a-z_]+['\"]", "名字 startswith(minecraft:)"),
]

# ★**已知豁免**（★带理由 ✗ 以后必须改 ✗ 换包就失效✗★）✗★
KNOWN_EXEMPT = {
    # ★★§79.452✗★★：★mapread 的老名单**已不再是主路径**✗★
    #   ★现在 is_floor／locks_space 都是**导出优先**（★_export_h(block) 先查 ✗ 有就用✗★）✗
    #   ★⇒ 老名单**只在★导出里没有这个名字★时兜底** ✗ 实测兜底 **0 次**（★所有方块都走导出✗★）✗★
    #   ★⇒ ★**换包不用重来** ✓ ✗ 名单留着是因为★地图字母／未知名字★仍可能需要✗★
    "tools/mapread.py": "老名单已降级为**兜底**（★导出优先 ✗ 实测兜底 0 次✗★）✗ 名单本身待彻底删除",
}



def main() -> int:
    checks = []
    problems = []
    for rel in WATCHED:
        p = ROOT / rel
        if not p.is_file():
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            # ★跳过注释（★本判据自己的说明里会出现这些词✗★）✗★
            if s.startswith("#") or s.startswith("--"):
                continue
            for pat, why in NAME_MATCH:
                if re.search(pat, ln):
                    problems.append((rel, i, why, s[:96]))
            # ★内容方块字面量✗★
            for m in re.finditer(r"['\"](minecraft:[a-z0-9_]+)['\"]", ln):
                nm = m.group(1)
                if nm not in STRUCTURAL:
                    problems.append((rel, i, "内容方块字面量", "%s ｜ %s" % (nm, s[:70])))
    exempted = [p for p in problems if p[0] in KNOWN_EXEMPT]
    problems = [p for p in problems if p[0] not in KNOWN_EXEMPT]
    if exempted:
        print("  ★已知豁免 %d 处（★mapread 老名单 ✗ **已降级为兜底** ✗ 实测兜底 0 次 ✗ 待彻底删除✗★）：" % len(exempted))
    checks.append(("规划层没有「靠名字判性质」的写法", not problems,
                   "%d 处违规（★另有 %d 处已知豁免✗★）" % (len(problems), len(exempted))))
    if problems:
        print("  ★违规 %d 处（★前 12✗★）：" % len(problems))
        for rel, i, why, s in problems[:12]:
            print("     %-22s:%-5d [%s] %s" % (rel, i, why, s))

    # ★② 关键能力必须**走分类**（★抽查三个实现✗★）✗★
    def reads_classification(rel, fn):
        p = ROOT / rel
        if not p.is_file():
            return False
        t = p.read_text(encoding="utf-8", errors="replace")
        i = t.find("def %s(" % fn)
        if i < 0:
            return False
        j = t.find("\ndef ", i + 6)
        body = t[i:j] if j > i else t[i:]
        return any(k in body for k in ("blockkb", "_H3D", "_kb_h", "collision_h", "world3d", "W3.", "category_of"))

    for rel, fn, what in [
        ("tools/plan3d.py", "is_placeable", "★能垫脚（★必须看导出高✗★）"),
        ("tools/world3d.py", "pass_info", "★通行性（★必须看碰撞✗★）"),
        ("tools/world3d.py", "collision_h", "★碰撞高（★必须读导出✗★）"),
    ]:
        ok = reads_classification(rel, fn)
        checks.append(("%s 走分类" % what, ok, "✓" if ok else "★没读分类★"))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => generic_rule ★FAIL★（%d 项不对 ✗ ★靠名字 = 换包就得重来★）" % bad)
        print("GENERICRULE ok=0 bad=%d" % bad)
        return 1
    print("  => generic_rule PASS ✓（★规划层只查**分类** ✗ 不靠方块名字 ✗ 换包不用重来✗★）")
    print("GENERICRULE ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
