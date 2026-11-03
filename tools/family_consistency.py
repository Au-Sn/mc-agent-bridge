#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""family_consistency.py -- ★家族标签集的"成员物理一致率"（任务书 ④补 ✗ ㊲ 第 ⑤ 项）★

★判据（★用户 2026-10-03 的 ④补 ✗ 先写死✗★）★
  一致率(F) ＝ ★这一族的**成员**里 ✗ 物理读数与**多数派**一致的比例✗★
  物理读数 ✗ 现在唯一**独立**可得的是：★模组的 `solid=` 读数✗★（★它读真的 `BlockState` ✗
  不是我们的名字分类器 ✓ 所以不循环 ✓ 见铁律 3✓★）

★它能干什么 ✗ 不能干什么✗★（★分工写死 ✗ 免得被当成分类器✓★）
  ✔ 能：★滤掉"成员在物理上**混杂**"的**语义标签**✗★ —— ★例如某个"挂绳子上"的标签里既有
     灯笼又有牌子又有植物 ⇒ 一致率低 ⇒ **不该当形状家族**✗★ ✓
        （★这正是"★有 10 个标签却没有一族★"那种种 ✗ 靠**数**滤掉 ✗ 不靠记忆✓★）
  ✘ 不能：★替你决定"★该归哪一族★"✗★ —— ★那是**碰撞形状**（★登记册第 4 条更高级的来源✓★）
       的事 ✓ 一致率只回答"★这一串成员**齐不齐**★"✓
  ✘ 不能：★一致率高**不等于**该族正确✗★ —— ★一整族"整方块"的东西一致率也是 1.0✗★ ✓
        （★这条不许含糊 ✗ 否则就会有人拿它当"正确性证明"✓★）

★阈值✗★：★**先报数后定**（P98 ✗ 用户明说）✗ 本工具**只报数** ✗ 不带阈值 ✗ 不判红✗★ ✓
★纪律✗★：★只读世界 ✗ 不改任何东西 ✗ 探针结果落 `tmp/` ✗ 不碰真数据✗★ ✓
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import tag_census as TC  # noqa: E402  ★复用它的标签解析（一份实现✓★）


def majority_rate(vals) -> float:
    """★多数派比例✗★ —— ★只数"有读数"的那些 ✗ 读不到的**不算** ✗ 也不许当 False✗★"""
    got = [bool(v) for v in vals if v is not None]
    if not got:
        return -1.0
    return max(sum(got), len(got) - sum(got)) / float(len(got))


def _cell_of(species: str, box):
    """★找一个这种方块的格子✗★（★用中间层的 `t_scan(match=…)` ⇒ 引号它自己加✓★）"""
    try:
        import mc_mcp as M
        out, _bad = M.t_scan(*box, match=species, max_=2)
    except Exception as e:
        return None, "★扫描炸了✗★ %s" % type(e).__name__
    txt = str(out or "")
    # ★回执形如：`dshscan box=… matched=88 shown=4 page=1/22 us=445` ✗ 后面跟逐格行✓★
    m = re.search(r"matched=(\d+)", txt)
    if not m or int(m.group(1)) == 0:
        return None, "★这个盒子里没有它✗★（matched=0）"
    cells = re.findall(r"\((-?\d+),(-?\d+),(-?\d+)\)", txt)
    if not cells:
        # ★有的回执写 `x,y,z` 不写括号 ✗ 都认✓★
        cells = re.findall(r"(?<!\d)(-?\d+),(-?\d+),(-?\d+)", txt)
    if not cells:
        return None, "★回执里没看到坐标✗★"
    return tuple(int(v) for v in cells[0]), ""


def _solid_of(x: int, y: int, z: int):
    """★这一格实心吗✗★ —— ★模组读真方块 ⇒ **独立**读数✓★（★读不到 ⇒ None ✗ 不许当 False✓★）"""
    try:
        import mc_mcp as M
        txt = str(M.dsh("dshscan %d %d %d %d %d %d" % (x, y, z, x, y, z), 60.0) or "")
    except Exception:
        return None
    m = re.search(r"solid=(\d+)", txt)
    if not m:
        return None
    return bool(int(m.group(1)))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", default="叶子,原木,木板,半砖,楼梯,栅栏,墙,门")
    ap.add_argument("--per-family", type=int, default=8)
    ap.add_argument("--box", default="4107,63,-6,4135,77,22")
    ap.add_argument("--cache", default="tmp/species_solid.json")
    ap.add_argument("--species-file", default="tmp/species_world.txt")
    a = ap.parse_args(argv)

    box = tuple(int(v) for v in a.box.split(","))
    wanted = [s.strip() for s in a.families.split(",") if s.strip()]

    # ---- 标签侧：复用普查工具（★扫 jar ✗ 只读✗★）----
    jars, vanilla, roots = TC.sources_of(a)
    src, uni, st = TC.scan(jars, roots, want_universe=False)
    vsrc, _vu, _vst = TC.scan(vanilla, [], want_universe=False)
    mem, ref = TC.build(src + vsrc)
    full = TC.closure(mem, ref)
    ft = TC.family_tags(full)
    print("== family_consistency（★只报数 ✗ 阈值留空 ✓ 见文件头的判据✓★）==")
    print("  标签 %d 个 ｜ 家族模式命中 %d 个：%s"
          % (len(full), len(ft), "／".join(ft.keys())))

    cache_p = ROOT / a.cache
    cache = {}
    if cache_p.is_file():
        try:
            cache = json.loads(cache_p.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    rows = []
    for fam in wanted:
        tags = ft.get(fam) or []
        if not tags:
            rows.append((fam, 0, 0, -1.0, "★这一族在本包里没有标签✗★"))
            continue
        members = sorted(TC.family_union(full, tags))
        # ★★2026-10-03 现场纠错✗★★：★原来按"名字最短"取样 ✗ 挑出来的全是**模组物种**
        #   （`fig_crop`／`cut_tuff_slab`／`brass_door` …）⇒ ★扫描盒里 `matched=0` ✗
        #   ⇒ 8 个取样 0 个有读数 ✗ **一点用都没有**✗★ ✓
        #   ★正确取样✗★：★和"★这个盒子里**真有的**物种★"求交✗★（★那一份是**世界真值**
        #     一份宽盒扫描换来的 ✗ 不是我的记忆✓★）⇒ ★交出来的每一个都**必定找得到格子**✗★ ✓
        in_box = set()
        if (ROOT / a.species_file).is_file():
            in_box = {s.strip() for s in
                      (ROOT / a.species_file).read_text(encoding="utf-8").splitlines()
                      if s.strip()}
        cand = [s for s in members if (not in_box) or (s in in_box)]
        pick = cand[:a.per_family]
        if not pick:
            rows.append((fam, 0, 0, -1.0,
                         "★这一族在**扫描盒里**没有成员（★所以**测不了** ✗ 不是 0✓★）"))
            continue
        vals, notes = [], []
        for sp in pick:
            if sp in cache:
                vals.append(cache[sp].get("solid"))
                continue
            cell, why = _cell_of(sp, box)
            if cell is None:
                notes.append("%s：%s" % (sp.split(":")[-1], why))
                vals.append(None)
                continue
            sv = _solid_of(*cell)
            cache[sp] = {"cell": list(cell), "solid": sv}
            vals.append(sv)
        got = [v for v in vals if v is not None]
        rate = majority_rate(vals)
        rows.append((fam, len(pick), len(got), rate,
                     "／".join(notes[:2]) if notes else ""))

    cache_p.parent.mkdir(parents=True, exist_ok=True)
    cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    print("")
    print("  %-8s %8s %8s %9s  %s" % ("家族", "取样", "有读数", "一致率", "备注"))
    for fam, n, got, rate, note in rows:
        print("  %-8s %8d %8d %9s  %s"
              % (fam, n, got, ("%.2f" % rate) if rate >= 0 else "  -  ", note[:60]))
    print("")
    print("★覆盖诚实✗★：★上面「取样」只是这一族成员里的一小撮 ✗ 而且必须在**扫描盒里真的出现**"
          "才能读到物理量✗★ ⇒ ★一致率只对「有读数」的那几格负责 ✗ 别当全族结论✗★ ✓")
    print("★阈值✗★：★★本工具**故意不带阈值**✗★（★先报数后定 ✗ P98 ✗ 用户明说✓★）✗ 也不判红 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
