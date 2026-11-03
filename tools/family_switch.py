#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""family_switch.py -- ★物理切到碰撞表的**按族声明**✗★（§79.349 ✗ 用户裁决 2026-10-24）

★★用户原话✗★★：★"★不需要完全声明每一项改动 ✗ 这个超大量的改动可以考虑
  仅说明改动了哪几个族的几项★"✗★ ✓
★★⇒ ★本工具把"★切到碰撞表★"的影响面 ✗ **按碰撞族**汇总成一份**声明**✗★★ ✓
  ★声明形状✗★：★每个**族** ⇒ `is_floor` 怎么变 ＋ `blocks_space` 怎么变 ＋ **几条**✗★ ✓
★`--write`：★现算一遍 ✗ 落 `state/family_switch_declaration.json`✗★ ✓
★`--check`：★现算 ✗ 与声明**逐族比条数** ✗ 并且**任何会变的族都必须出现在声明里**
  （★这就是**铁律②**在**族粒度**上的形态✗★）✗★ ✓
★口径✗★：★名字老路 ＝ `mapread.is_floor`／`blocks_space`（**方块名**✗★）✗
  碰撞表 ＝ 导出的 `family` ⇒ 经 **`FAM2SHAPE`** 映射 ⇒ `blockkb.is_floor_fam`／`blocks_space_fam`✗★ ✓
"""
from __future__ import annotations

import argparse
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

OUT = ROOT / "state" / "family_switch_declaration.json"

# ★导出族 ⇒ mapread shape（★按物理含义 ✗ 不是按名字像：fence_15→fence ✗ snow_layer→pass✗★）✗★
FAM2SHAPE = {"full": "full", "slab": "slab", "fence_15": "fence",
             "snow_layer": "pass", "none": "pass", "liquid": "liquid", "other": "other"}
FAM_WHY = {
    "full": "★max_height ≥0.999 ⇒ 整块 ✗ 能站能挡✗★",
    "slab": "★0.45–0.999 ⇒ 半砖 ✗ 能站能挡✗★",
    "fence_15": "★1.5 ⇒ 栅栏 ✗ 挡人但**站不上去**（★顶面高于脚✗★）✗★",
    "snow_layer": "★≤0.45 ⇒ 薄层 ✗ 不挡不站（★真值契约：1 层给 0 高度✗★）✗★",
    "none": "★没有碰撞 ✗ 不挡不站✗★",
    "liquid": "★液体 ✗ 不挡不站✗★",
    "other": "★其它 ✗ 只有 1 块✗★",
}


def compute():
    """★逐块比 ✗ 不许拿族里第一个块的读数当全族（§79.349 修的）✗★"""
    import kb_export as KX
    import mapread as MR
    import blockkb as KB
    blocks = json.loads(pathlib.Path(KX.find_export("")).read_text(encoding="utf-8")).get("blocks") or {}
    per = {}
    for sp, b in blocks.items():
        fam = (b or {}).get("family") or "?"
        if fam not in FAM2SHAPE:
            continue
        sh = FAM2SHAPE[fam]
        e = per.setdefault(fam, {"family": fam, "blocks": 0, "shape": sh,
                                 "is_floor_to": int(bool(KB.is_floor_fam(sh))),
                                 "blocks_space_to": int(bool(KB.blocks_space_fam(sh))),
                                 "is_floor_changed": 0, "blocks_space_changed": 0,
                                 "floor_true_before": 0, "space_true_before": 0})
        e["blocks"] += 1
        f_old = bool(MR.is_floor(sp))
        b_old = bool(MR.blocks_space(sp))
        e["floor_true_before"] += int(f_old)
        e["space_true_before"] += int(b_old)
        if int(f_old) != e["is_floor_to"]:
            e["is_floor_changed"] += 1
        if int(b_old) != e["blocks_space_to"]:
            e["blocks_space_changed"] += 1
    return blocks, per


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    blocks, per = compute()
    tot_f = sum(e["is_floor_changed"] for e in per.values())
    tot_b = sum(e["blocks_space_changed"] for e in per.values())
    print("== family_switch：★切到碰撞表 ✗ 按族汇总✗★ ==")
    print("   导出 **%d** 块 ｜ 族 %d 个" % (len(blocks), len(per)))
    print("")
    print("   %-11s %7s %9s %13s  %s" % ("碰撞族", "块数", "is_floor", "blocks_space", "方向"))
    for fam in sorted(per, key=lambda f: -per[f]["is_floor_changed"] - per[f]["blocks_space_changed"]):
        e = per[fam]
        arrows = []
        if e["is_floor_changed"]:
            arrows.append("★floor→%d ✗ %d 条✗★" % (e["is_floor_to"], e["is_floor_changed"]))
        if e["blocks_space_changed"]:
            arrows.append("★space→%d ✗ %d 条✗★" % (e["blocks_space_to"], e["blocks_space_changed"]))
        print("   %-11s %7d %9s %13s  %s"
              % (fam, e["blocks"],
                 ("→%d" % e["is_floor_to"]) if e["is_floor_changed"] else "—",
                 ("→%d" % e["blocks_space_to"]) if e["blocks_space_changed"] else "—",
                 "；".join(arrows) or "★不变✓★"))
    print("")
    print("   ★合计✗★：★is_floor 变 **%d** ✗ blocks_space 变 **%d** ✗ 共 **%d** 条✗★"
          % (tot_f, tot_b, tot_f + tot_b))
    changed = {f: e for f, e in per.items() if e["is_floor_changed"] or e["blocks_space_changed"]}
    payload = {
        "schema": "family_switch_declaration@1",
        "decided_by": "用户 2026-10-24：★不需要完全声明每一项改动 ✗ 仅说明改动了哪几个族的几项★",
        "meaning": ("★切到碰撞表时 ✗ 物理答案会按**族**整片变化 ✗ 本文件**按族**声明："
                    "每个族怎么变（0→1／1→0）＋ 影响几条 ✗ 不逐项列✗★"),
        "principle": "★物理只听碰撞 ✗ 名字只在名字层；变化按铁律②**在族粒度上声明**✗★",
        "families": per,
        "totals": {"is_floor_changed": tot_f, "blocks_space_changed": tot_b,
                   "all_changed": tot_f + tot_b,
                   "changed_families": sorted(changed)},
    }
    ok = [True]

    def check(tag, cond, note):
        ok[0] &= bool(cond)
        print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))

    if a.write:
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print("   ★已写 `state/family_switch_declaration.json`（★%d 个族 ✗ 共 %d 条✗★）"
              % (len(per), tot_f + tot_b))
    if a.check:
        old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
        of = old.get("families") or {}
        check("S1", bool(of), "★声明文件必须在✗★")
        missing = [f for f in changed if f not in of]
        check("S2", not missing, "★任何会变的族都必须在声明里✗★（★缺：%s✗★）" % (missing or "（没有 ✓）"))
        bad = []
        for f, e in changed.items():
            o = of.get(f) or {}
            if (o.get("is_floor_changed") != e["is_floor_changed"]
                    or o.get("blocks_space_changed") != e["blocks_space_changed"]):
                bad.append("%s 声明 %s/%s ✗ 现算 %s/%s"
                           % (f, o.get("is_floor_changed"), o.get("blocks_space_changed"),
                              e["is_floor_changed"], e["blocks_space_changed"]))
        check("S3", not bad, "★每族的条数必须与现算一致✗★（★不一致：%s✗★）" % (bad or "（没有 ✓）"))
        ot = old.get("totals") or {}
        check("S4", ot.get("all_changed") == tot_f + tot_b,
              "★总数必须一致✗★：声明 **%s** ✗ 现算 **%d**" % (ot.get("all_changed"), tot_f + tot_b))
        check("S5", len(per) >= 7, "★计数器✗★：比过 **%d** 个族（★≥7 ✗ 不许空转✗★）" % len(per))
        print("")
        print("=> family_switch %s" % ("PASS ✓" if ok[0] else "FAIL"))
        print("FAMILYSWITCH ok=%d families=%d changed=%d floor=%d space=%d"
              % (1 if ok[0] else 0, len(per), tot_f + tot_b, tot_f, tot_b))
        return 0 if ok[0] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
