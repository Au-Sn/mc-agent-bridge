#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""u1_declared.py -- ★铁律②的那个数✗★：★「不一致」里**有多少条没声明**（2026-10-05）

★★铁律②的原话✗★★：★「★不一致可以有 ✗ **一条都不许没声明**★」✗★ ✓
★⇒ 所以这个工具只回答一件事✗★：★
  ★**决策级不一致**（★挡人／能站**真的会翻**✓★）里 ✗ **哪些在例外表里有名字** ✗ **哪些没有**✗★ ✓
★★口径（★照 `divergence` 走 ✗ 不另造一套✗★）✗★★
  ★同样的管线 ✗ 同样的分档 ✗ 只多一问"★这一条在 `state/exceptions.json` 里吗★"✗★ ✓
★★第一版只**报数** ✗ 不判红✗★★（★与任务书阶段 3 同一条口径✓★）✗★ ✓

★★2026-10-18（★复核 P1-6 ✗ §79.274✗★）✗★★：
  ★真身✗★：★`main()` 原来**自己算一套**（★而且**读了导出** ‹passable›✓★）✗
    ★`u1_numbers()` 又算**另一套**（★不读导出 ✗ `passable=None`✓★）✗★ ⇒
    ★★合成导出实测 **2163 vs 2165** ✗★★ ⇒ ★导出回来的第一天就会"两个工具各说一套"✗★ ✓
  ★治本✗★：★**只有一处管线**（`_scan`）✗ `main` 与 `u1_numbers` **都调它**✗★ ✓
  ★而 `u1_numbers` 原来定义在 `if __name__` **之后** ✗ ⇒ ★`main` 一调它就是 `NameError`✗★
    （★§79.269 那个坑的**第二例** —— 定义在使用之后✓★）⇒ ★本文按"★先定义 ✗ 后入口★"重排✗★ ✓
"""
from __future__ import annotations

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


def _read_export_blocks() -> dict:
    """★把导出读进来 ✗ 读不到就**空**（★`passable=None` ⇒ 仍判冲突✗★）（★§79.200✓★）"""
    try:
        import json as _json2
        import kb_export as _KX2
        return (_json2.loads(_KX2.find_export("").read_text(encoding="utf-8")).get("blocks")
                or {})
    except Exception:
        return {}


def _scan(blocks=None):
    """★★**唯一**的管线✗★（★`main` 与 `u1_numbers` 都走这里 ✗ 不许再各写一套✗★）
    ★返回✗★：★`(inc, dec, declared_sp, entries)`✗★ ✓
    """
    if blocks is None:
        blocks = _read_export_blocks()
    jars, vanilla, roots = TC.sources_of([])
    src, _uni, _st = TC.scan(jars, roots, want_universe=False)
    vsrc, _v, _s = TC.scan(vanilla, [], want_universe=False)
    mem, ref = TC.build(src + vsrc)
    full = TC.closure(mem, ref)
    from_tag = TC.invert(full)
    ft = TC.family_tags(full)

    inc, dec = [], []
    for sp in sorted(from_tag):
        fams = [f for f, ids in ft.items() if any(t in ids for t in (from_tag.get(sp) or ()))]
        # ★★"★能通过★"要**真读到**导出才敢下结论✗★（★§79.200✗★）✗★ ✓
        _e3 = blocks.get(sp) or {}
        _fam3 = _e3.get("family")
        exp, _why, conflict = DV.expected_from_tags(
            fams, passable=None if _fam3 is None else (_fam3 in ("none", "pass", "liquid")))
        black = MR.shape(sp)
        if DV.bucket(black, exp, conflict) != "★不一致✗★":
            continue
        inc.append(sp)
        if conflict or DV.decision_delta(black, exp).startswith("★★决策级"):
            dec.append(sp)

    entries = ET.load()
    declared_sp = set()
    for e in entries:
        sp = e.get("block") or e.get("species") or e.get("id")
        if sp:
            declared_sp.add(sp)
    return inc, dec, declared_sp, entries


def u1_numbers(verbose: bool = False) -> dict:
    """★把「★决策级里多少条没声明★」算出来**给别人用**✗★（★§79.190 ✗ 两边共用一套口径✗★）✓
    ★★为什么抽出来✗★★：★不然 `cut_ready` 自己再算一套 ✗ 两个工具又要打脸✗★ ✓
    """
    inc, dec, declared_sp, _entries = _scan()
    dec_no = [sp for sp in dec if sp not in declared_sp]
    dec_yes = [sp for sp in dec if sp in declared_sp]
    if verbose:
        print("   ★决策级 %d ✗ 已声明 %d ✗ 未声明 %d★" % (len(dec), len(dec_yes), len(dec_no)))
    return {"inc": len(inc), "dec": len(dec), "yes": len(dec_yes), "no": len(dec_no),
            "undeclared": dec_no, "declared": dec_yes}


def main(argv):
    top = 15
    # ★★只走**一条**管线✗★（★P1-6 的治本 ✗ 见文件头✓★）✗★ ✓
    inc, dec, declared_sp, entries = _scan()
    dec_yes = [sp for sp in dec if sp in declared_sp]
    dec_no = [sp for sp in dec if sp not in declared_sp]

    print("== 铁律②的账 ✗ 不一致 %d 条 ✗ 其中决策级 %d 条 ==" % (len(inc), len(dec)))
    print("   ★例外表里现成 %d 条声明✗★" % len(entries))
    print("")
    print("   ★★决策级里✗★★：")
    print("      ★已声明✗★    %5d   （%.0f%%）"
          % (len(dec_yes), 100.0 * len(dec_yes) / max(1, len(dec))))
    print("      ★★未声明✗★★  %5d   （%.0f%%）"
          % (len(dec_no), 100.0 * len(dec_no) / max(1, len(dec))))
    print("")
    print("   ★未声明的按模组排（★前 %d✗★）✗★：" % top)
    by_ns = {}
    for sp in dec_no:
        by_ns.setdefault(sp.split(":")[0], []).append(sp)
    for ns, v in sorted(by_ns.items(), key=lambda kv: -len(kv[1]))[:top]:
        print("      %-26s %5d" % (ns, len(v)))
    print("")
    print("   ★未声明的头 6 个（★长这样✗★）✗★：")
    for sp in dec_no[:6]:
        print("      %s" % sp)
    print("")
    print("★口径✗★：★第一版**只报数** ✗ 不判红✗★ ✓（★要判红得先定"
          "「★哪些必须声明 ✗ 哪些允许只报数★」✗ 那是你的裁定✗★）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
