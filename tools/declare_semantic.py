#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""declare_semantic.py -- ★把"现在就能合法声明"的语义级分歧**声明掉**✗★（§79.108）

★为什么只做语义级✗★（★这一段是全部理由✗★）
  · ★决策级（★"挡人／能站"真的翻了✓★）✗★ ⇒ ★必须 `collision` ／ `experiment` 证据 ✗
    而今天**两种都拿不到**（★§79.103 实测：`solid` 只是"★这一格不是空气★"✓★）✗★ ✓
  · ★语义级（★两条物理判定**都没翻**✓★）✗★ ⇒ ★`registry` 标签**就是语义的权威**✗
    （★铁律 1：★标签只管语义 ✗ 那在这件事上它说了算✓★）⇒ ★**今天就能合法声明**✗★ ✓

★它做什么✗★：★跑一遍分歧分类 ⇒ 用 `exception_table.pick_semantic` 挑 ⇒ 逐条 `add` ⇒
  （可选）`--apply` 推进 `blockkb` ⇒ 重生成 `docs/例外表.md`✗★ ✓
★它不做什么✗★：★不碰决策级 ✗ 不碰冲突 ✗ 不碰"表中无" ✗ 也不改任何**判定代码**✗★ ✓
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import divergence as DV  # noqa: E402
import exception_table as ET  # noqa: E402
import mapread as MR  # noqa: E402
import tag_census as TC  # noqa: E402


def rows_all():
    """★跑一遍分歧分类 ✗ 产出 `[(物种, 黑名单族, 标签族, 级别), …]`✗★"""
    jars, vanilla, roots = TC.sources_of(None)
    src, _u, _s = TC.scan(jars, roots, want_universe=False)
    vsrc, _v, _vs = TC.scan(vanilla, [], want_universe=False)
    mem, ref = TC.build(src + vsrc)
    full = TC.closure(mem, ref)
    from_tag = TC.invert(full)
    ft = TC.family_tags(full)
    rows = []
    for sp in sorted(from_tag):
        fams = [f for f, ids in ft.items() if any(t in ids for t in (from_tag.get(sp) or ()))]
        exp, _why, conflict = DV.expected_from_tags(fams)
        black = MR.shape(sp)
        if conflict:
            lvl = "★★决策级✗★★ ★标签自相冲突 ✗ 必须先解决★"
        else:
            lvl = DV.decision_delta(black, exp)
        if black != exp and exp:          # ★只关心**分歧**（★一致的不进表✓★）
            rows.append((sp, black, exp, lvl))
    return rows


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="★顺手推进 blockkb✗★")
    ap.add_argument("--cap", type=int, default=60)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)

    rows = rows_all()
    keep, drop = ET.pick_semantic(rows, cap=a.cap)
    print("== declare_semantic ✗ 分歧 %d 条 ⇒ 可声明的语义级 **%d** 条（★上限 %d✓★）=="
          % (len(rows), len(keep), a.cap))
    for k, v in sorted(drop.items(), key=lambda kv: -kv[1]):
        print("   ★落选✗★ %-52s %d" % (k, v))
    if a.dry:
        for e in keep[:8]:
            print("   ★将声明✗★ %-44s family=%s（★证据 registry✓★）"
                  % (e["species"], e["verdict"]))
        return 0

    ok = 0
    for e in keep:
        good, why = ET.add(e)
        if good:
            ok += 1
        else:
            print("   ★被拒✗★ %-40s %s" % (e["species"], why[:60]))
    print("")
    print("  已进表 **%d** 条（★拒 %d✗★）｜ 表里现在 %d 条"
          % (ok, len(keep) - ok, len(ET.load())))
    doc = ET.render()
    print("  已重生成 %s ✓" % doc.name)
    if a.apply:
        import blockkb as KB
        r = ET.to_blockkb(ET.load(), KB)
        print("  推进 blockkb：put=%s ｜ refused=%d" % (r["put"], len(r["refused"])))
        for x in r["refused"][:5]:
            print("     ★refused✗★ %s %s" % (x[0], str(x[2])[:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
