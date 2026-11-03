#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_export.py -- ★导出文件的**验收器**✗★（规格 §5 的第二条 ✓ 2026-10-03）

★它查什么✗★（★判据先写死✗★）
  V1 ★四样版本／标识字段齐✗★：`schema` ／ `exported_at` ／ `mod_version` ／ `count`✗★ ✓
  V2 ★`count` **必须等于** `len(blocks)`✗★（★不许"★说两万 ✗ 给三千★"✓★）
  V3 ★族名在**闭集**里✗★（★用户拍板：★`full`／`slab`／`snow_layer`／`fence_15`／
     `canopy`／`none`／`other`／`liquid`✗★）✗★ ✓
  V4 ★`other` **必须**带 `max_height`✗★（★用户原话：★消费者不许为 `other` 写特例✓★）
  V5 ★`max_height` 与 `empty` 不许自相矛盾✗★（★空碰撞却说高度 > 0 ⇒ 假✗★）
  V6 ★`errors=N` 非零 ⇒ **必须报出来**✗★（★不许静默吞✗★）

★为什么要有它✗★：★导出是**唯一**能改写物理判定的输入 ✗ 它一歪 ✗ 后面全歪✗★ ⇒
  ★"★落地前先验它★"这一步**不许**省✗★ ✓
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import paths as PA  # noqa: E402  ★解绑：实例路径只从 paths 来✗不写死✗★

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EXPORT = ROOT / "logs" / "blockkb.json"
# ★★游戏把它写在**实例目录**里✗★★（2026-10-04 实测 ✓ 不是仓库 ✓）
#   ★为什么✗★：★模组写的是**相对路径** `logs/blockkb.json` ✗ 而游戏进程的工作目录
#     是 **PCL2 的实例目录**✗★（★`/dshkb` 回执里 `path=logs\blockkb.json` 就是这个意思✓★）✓
#   ★⇒ 找它要按顺序试✗★：★`--export` ⇒ 环境变量 ⇒ 仓库 ⇒ **实例**（★下面这条✓★）✗★ ✓
INSTANCE_EXPORT = PA.BLOCKKB_EXPORT


def find_export(given: str = "") -> pathlib.Path:
    """★按顺序找导出✗★ ⇒ ★找不到就回"★仓库那条★"（★让调用方如实报"不在"✗★）✓"""
    import os as _os
    # ★★2026-10-13（★用户裁决 B1 ✗ §79.224✗★）✗★★：
    #   ★快照插在"★仓库 logs★"**之前**✗★ —— ★它是**特意存下来**的 ✗ 比临时文件可信✗★ ✓
    #   ★（★不 import `kb_snapshot` ✗ 免得循环 ✗ 直接 glob 一下✓★）✗★ ✓
    #   ★★2026-10-13 修（★§79.224 ✗ 我自己造的回归✗★）✗★★：
    #     ★现象✗★：★`glob("*.json")` 把 **`manifest.json`** 也算成候选 ✗★ ——
    #       ★而它是个**数组**（★快照清单✓★）⇒ ★消费者拿它当导出读 ⇒ 全崩成
    #       `AttributeError: 'list' object has no attribute 'get'`**✗★ ✓
    #     ★★这正是 B1 要消灭的那种"★看不懂的红★" ✗ 我十分钟前刚消灭 ✗ 又自己造了一个✗★★ ✓
    #     ★修法✗★：★只认**命名格式**（`<版本>__<schema>__<日期>.json`✗★）✗★ ✓
    _snapdir = ROOT / "state" / "export_snapshots"
    _snaps = sorted(p for p in _snapdir.glob("*__*__*.json")
                    if "__" in p.name) if _snapdir.is_dir() else []
    _newest = str(_snaps[-1]) if _snaps else ""
    for c in (given, _os.environ.get("DSH_BLOCKKB", ""), _newest, str(EXPORT),
              str(INSTANCE_EXPORT)):
        if c and pathlib.Path(c).is_file():
            return pathlib.Path(c)
    return pathlib.Path(given) if given else EXPORT
SCHEMA = "dshbridge/registry_blocks@1"
# ★族名闭集（★用户 2026-10-03 拍板 ✗ 七类 ＋ `liquid`✓★）
FAMILIES = ("full", "slab", "snow_layer", "fence_15", "canopy", "none", "other", "liquid")


def validate(export: dict) -> tuple:
    """★返回 `(ok, problems)`✗★ —— ★问题逐条写清 ✗ 不许只说"★不合法★"✗★"""
    p = []
    if not isinstance(export, dict):
        return False, ["★根本不是对象✗★"]
    for k in ("schema", "exported_at", "mod_version", "count"):
        if not export.get(k):
            p.append("★V1 缺字段✗★：%s" % k)
    if export.get("schema") and export["schema"] != SCHEMA:
        p.append("★V1 schema 不是 %s ✗ 而是 %r✗★" % (SCHEMA, export["schema"]))
    blocks = export.get("blocks")
    if not isinstance(blocks, dict):
        p.append("★V2 没有 `blocks` ✗ 或不是对象✗★")
        return False, p
    if export.get("count") != len(blocks):
        p.append("★V2 `count`=%s 但实际 %d 条 ⇒ 说谎✗★" % (export.get("count"), len(blocks)))
    bad_fam, other_noh, contra = {}, {}, 0
    for sp, ent in blocks.items():
        if not isinstance(ent, dict):
            p.append("★V3 %s 不是对象✗★" % sp)
            continue
        fam = ent.get("family")
        if fam not in FAMILIES:
            bad_fam[fam] = bad_fam.get(fam, 0) + 1
        if fam == "other" and ent.get("max_height") is None:
            other_noh["★other 缺高度✗★"] = other_noh.get("★other 缺高度✗★", 0) + 1
        h = ent.get("max_height")
        if ent.get("empty") is True and isinstance(h, (int, float)) and h > 0:
            contra += 1
    if bad_fam:
        p.append("★V3 族不在闭集里✗★：%s" % {k: v for k, v in list(bad_fam.items())[:5]})
    if other_noh:
        p.append("★V4 `other` 缺 `max_height`✗★：%d 条" % sum(other_noh.values()))
    if contra:
        p.append("★V5 `empty=true` 却有高度 > 0✗★：%d 条" % contra)
    if export.get("errors"):
        p.append("★V6 ★导出自己报了错★ ✗ `errors=%s` ⇒ 必须先看那几条✗★" % export.get("errors"))
    return (not p), p


def reconcile(export: dict, verbose: bool = False) -> dict:
    """★与普查的"★标签宇宙★"**逐条对账**✗★（★规格 §5 第三条✓★）

    ★它报什么✗★：★导出里有而宇宙里没有的（★"★标签侧不知道它★"✓★）✗
      ★宇宙里有而导出里没有的（★"★注册表里没有它★" ✗ 那多半是**空壳标签**✗★）✗★ ✓
    ★注意✗★：★两边都**不该**期待完全一致 ✗ 差异**要能解释**才是合格✗★ ✓
    """
    import tag_census as TC
    jars, vanilla, roots = TC.sources_of(None)
    src, _u, _s = TC.scan(jars, roots, want_universe=False)
    vsrc, _v, _vs = TC.scan(vanilla, [], want_universe=False)
    full = TC.closure(*TC.build(src + vsrc))
    uni = set(TC.invert(full))
    exp = set((export.get("blocks") or {}))
    only_exp = sorted(exp - uni)
    only_uni = sorted(uni - exp)
    if verbose:
        for sp in only_exp[:6]:
            print("     ★只在导出里✗★ %s" % sp)
        for sp in only_uni[:6]:
            print("     ★只在宇宙里✗★ %s" % sp)
    return {"export": len(exp), "universe": len(uni), "only_export": only_exp,
            "only_universe": only_uni}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="")
    ap.add_argument("--reconcile", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    p = find_export(a.export)
    if not p.is_file():
        print("INCONCLUSIVE: ★导出不在✗★：%s（★先 `/dshkb` 跑一次✓★）" % p)
        return 4
    try:
        export = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print("INCONCLUSIVE: ★读不动✗★：%s: %s" % (type(e).__name__, e))
        return 4
    ok, problems = validate(export)
    print("== kb_export ✗ %s（★%d 条 ✗ schema=%s ✗ mod=%s✗★）=="
          % (p.name, len(export.get("blocks") or {}), export.get("schema"),
             export.get("mod_version")))
    if ok:
        print("=> ★导出合规 ✓（★V1~V6 全过✗★）")
    else:
        print("=> ★导出**不合规**✗★：")
        for x in problems:
            print("   %s" % x)
    if a.reconcile:
        r = reconcile(export, verbose=a.verbose)
        print("   对账：★导出 %d ✗ 宇宙 %d ✗ 只在导出 %d ✗ 只在宇宙 %d✗★"
              % (r["export"], r["universe"], len(r["only_export"]), len(r["only_universe"])))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
