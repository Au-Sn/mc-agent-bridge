#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""family_selection.py -- ★A2 落地：45 个**家族标签类**的 ≥99% 判定（§79.331）

★用户裁决（★2026-10-18 ✗ 原话✗★）✗★：★"★阈值 ≥99% ✗ **20 族入选** ✗ 其余 **25 族**登记为
「语义标签 ✗ 形状由导出裁决」★"✗★ ✓
★★"★族★"到底指什么 —— **数据上确认了**✗★★：
  ★＝ ★`tag_census.family_tags()` 找出来的 **45 个家族标签类**（★`family_consistency` 第一行
    打的就是"★家族模式命中 45 个★"✗★）✗★ ✓
  ★一致率 ＝ ★该类底下**经标签闭包**得到的**物种** ✗ 在**导出**里的**碰撞族**（`family` 字段）的
    **多数派占比**（★只数导出里有的 ✗ 没有的如实计数✗★）✗★ ✓
★★两个数**都对上**✗★★：★≥99% ⇒ **20**（★用户说 20✗★）✗ 其余 ⇒ **25**（★用户说 25✗★）✗★ ✓

★用法✗★：`--write` 落 `state/family_selection.json` ✗ `--check` 重算比对（★闸门项✗★）✗
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import types
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

THRESHOLD = 0.99
OUT = ROOT / "state" / "family_selection.json"
N_SEL, N_SEM = 20, 25          # ★用户给的两个数 ✗ 只用来**对账** ✗ 不用来凑✗★


def compute():
    """★返回 (rows, sel, sem, none, multinfo) ✗ 全部**现算**✗★"""
    import tag_census as TC
    import kb_export as KX
    a = types.SimpleNamespace()
    for k, v in (("jars", ""), ("roots", ""), ("vanilla", ""), ("families", ""),
                 ("box", "0,0,0"), ("cache", "tmp/fc_cache.json"), ("per_family", 6),
                 ("species_file", "tmp/species.txt")):
        setattr(a, k, v)
    jars, vanilla, roots = TC.sources_of(a)
    src, _u, _s = TC.scan(jars, roots, want_universe=False)
    vsrc, _vu, _vst = TC.scan(vanilla, [], want_universe=False)
    mem, ref = TC.build(src + vsrc)
    full = TC.closure(mem, ref)
    ft = TC.family_tags(full)
    exp_p = pathlib.Path(KX.find_export(""))
    blocks = json.loads(exp_p.read_text(encoding="utf-8")).get("blocks") or {}
    cover = Counter()
    for tags in ft.values():
        for sp in TC.family_union(full, tags):
            cover[sp] += 1
    multi = sum(1 for sp, k in cover.items() if k >= 2)
    rows = []
    for fam in sorted(ft):
        sps = TC.family_union(full, ft[fam])
        inexp = [s for s in sps if s in blocks]
        fams = [((blocks[s] or {}).get("family") or "?") for s in inexp]
        if not fams:
            rows.append({"family": fam, "species": len(sps), "in_export": 0,
                         "rate": -1.0, "mode": "?", "class": "none"})
            continue
        c = Counter(fams)
        mode, cnt = c.most_common(1)[0]
        rate = cnt / len(fams)
        rows.append({"family": fam, "species": len(sps), "in_export": len(inexp),
                     "rate": round(rate, 4), "mode": mode,
                     "class": "geometric" if rate >= THRESHOLD else "semantic"})
    sel = [r["family"] for r in rows if r["class"] == "geometric"]
    sem = [r["family"] for r in rows if r["class"] == "semantic"]
    none_ = [r["family"] for r in rows if r["class"] == "none"]
    return rows, sel, sem, none_, {"multi_species": multi, "species_total": len(cover),
                                   "blocks_total": len(blocks), "export": exp_p.name}


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="落 state/family_selection.json")
    ap.add_argument("--check", action="store_true", help="重算并比对（闸门用）")
    a = ap.parse_args(argv)
    rows, sel, sem, none_, mi = compute()
    n_classes = len(rows)
    print("== family_selection：★A2 的 ≥99% 判定✗★ ==")
    print("   ★家族标签类✗★ = **%d** 个 ｜ 阈值 ≥99%% ｜ 导出 %s（★%d 块✗★）"
          % (n_classes, mi["export"], mi["blocks_total"]))
    ok = [True]

    def check(tag, cond, note):
        ok[0] &= bool(cond)
        print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))

    if not a.check:
        for r in sorted(rows, key=lambda r: -r["rate"]):
            print("   %-14s 物种 %5d 在导出 %5d 一致率 %6.3f 多数派 %-11s %s"
                  % (r["family"], r["species"], r["in_export"], r["rate"], r["mode"],
                     "★入选✓★" if r["class"] == "geometric"
                     else ("★语义✗★" if r["class"] == "semantic" else "★没成员✗★")))
    print("")
    payload = {
        "schema": "family_selection@2",
        "decided_by": "用户 2026-10-18：阈值 ≥99%，20 族入选；其余 25 族为「语义标签，形状由导出裁决」",
        "interpretation_verified": {
            "族": "tag_census.family_tags() 的 45 个**家族标签类**（family_consistency 打的「家族模式命中 45 个」）",
            "命中": "经**标签闭包**得到的物种 × 导出里的**碰撞族**（family 字段）",
            "一致率": "多数派占比（只数导出里有的成员）",
            "为什么这么定": "★两个独立数字都对上★：≥99% ⇒ 20（用户说 20）／其余 ⇒ 25（用户说 25）",
        },
        "threshold": THRESHOLD,
        "n_classes": n_classes,
        "selected": sel,
        "semantic_only": sem + none_,
        "no_members": none_,
        "multi_covered": mi,
        "rows": rows,
        "order_class": {"note": "★「同时命中 ≥2 族规则」的 1260 仍未对上（本篇不算它）✗ 见 §79.309✗★"},
    }
    if a.write:
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print("   ★已写 `state/family_selection.json` ✓（★入选 %d ✗ 语义 %d✗★）"
              % (len(sel), len(payload["semantic_only"])))
    if a.check:
        old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
        check("S1", old.get("n_classes") == n_classes,
              "★类数必须与现算一致✗★：写 %s ／ 现算 %d" % (old.get("n_classes"), n_classes))
        check("S2", sorted(old.get("selected") or []) == sorted(sel),
              "★`selected` 必须与现算一致✗★（★写 %d ✗ 现算 %d✗★）"
              % (len(old.get("selected") or []), len(sel)))
        check("S3", sorted(old.get("semantic_only") or []) == sorted(sem + none_),
              "★`semantic_only` 必须与现算一致✗★（★写 %d ✗ 现算 %d✗★）"
              % (len(old.get("semantic_only") or []), len(sem + none_)))
        check("S4", len(sel) == N_SEL and len(sem + none_) == N_SEM,
              "★两个数必须对得上用户给的✗★：入选 **%d**（★应 %d✗★）✗ 语义 **%d**（★应 %d✗★）"
              % (len(sel), N_SEL, len(sem + none_), N_SEM))
        check("S5", len(sel) + len(sem + none_) == n_classes,
              "★计数器✗★：入选 %d ＋ 语义 %d ＝ **%d**（★应等于类数 %d ✗ 不许漏类✗★）"
              % (len(sel), len(sem + none_), len(sel) + len(sem + none_), n_classes))
        print("")
        print("=> family_selection %s" % ("PASS ✓" if ok[0] else "FAIL"))
        print("FAMILYSELECT ok=%d classes=%d selected=%d semantic=%d"
              % (1 if ok[0] else 0, n_classes, len(sel), len(sem + none_)))
        return 0 if ok[0] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
