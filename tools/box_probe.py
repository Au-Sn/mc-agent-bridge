#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""box_probe.py -- ★★"我改的世界动了没有"✗★★ 的标准做法（2026-10-03 ✓ 欠账 ① 的沉淀 ✓）

★为什么要有它✗★：★① 那一串跑了**六次**✗ ✗ 每一次栽的都是**同一个形状**✗★：
  ★"我看见的"与"我以为我看见的" ✗ 中间隔着**一层**✗★ ✓
  ⇒ ★把正确做法**写死在这里** ✗ 下次谁都不用再踩一遍✗★ ✓

★三条口径（★都是从世界里换来的 ✗ 见 §79.48✓★）★
  ① ★字段分层✗★：★`counts[…]`／`solid=`／`air=`／`kinds=` 是**模组裸回执**就有的✗★
     ★而 `cells[…]` **只在给了 `match=` 时**才列内容✗★（★裸命令回
     `cells[pass a match= to list cells]`✓★）
  ② ★"安静"＝**解析后排序**的 `counts` 多重集一致✗★（★不是整段文本 ✗ 排列顺序是噪声✓★）
  ③ ★判据按**增量**✗★（★基线在**动手之前**取 ✓ 不许用绝对值 ✓ 盒里本来有别的什么都不管✓★）
★而且 ✗ 读不到就**说读不到**✗★ —— ★不许把"读失败"当"盒里是空的"✗★ ✓
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

FIELD_HELP = ("★裸 `dshscan` 就有✗：counts[…] / solid= / air= / kinds= / matched= / shown= "
              "｜★`cells[…]` 要**给了 match=** 才列内容✗（★否则回 'pass a match= to list cells'✓★）")


def parse_scan(text: str) -> Optional[Tuple[int, int, int, Tuple[str, ...]]]:
    """★把一份 `dshscan` 回执解析成 `(solid, air, kinds, counts)`✗★

    ★★读不到 ⇒ 回 `None`✗★★（★**不**回 `(0,0,0,())` ✗ 那会让"读失败"冒充"盒里是空的"✗★）
    """
    if not text or "dshscan" not in text:
        return None
    def num(k):
        m = re.search(k + r"=(\d+)", text)
        return int(m.group(1)) if m else None
    m = re.search(r"counts\[([^\]]*)\]", text)
    if m is None:
        return None
    counts = tuple(sorted(p.strip() for p in m.group(1).split(",") if p.strip()))
    s, a, k = num("solid"), num("air"), num("kinds")
    if s is None or a is None or k is None:
        return None
    return s, a, k, counts


def fingerprint(text: str):
    """★"安静世界"的指纹 ＝ **解析后排序**的 `counts` 多重集✗★（★读不到 ⇒ None✓★）"""
    p = parse_scan(text)
    return None if p is None else p[3]


def is_quiet(t1: str, t2: str) -> Optional[bool]:
    """★同一个盒连读两次 ✗ 多重集一致才算安静✗★（★读不到 ⇒ None ✗ 不许当成"安静"✓★）"""
    a, b = fingerprint(t1), fingerprint(t2)
    if a is None or b is None:
        return None
    return a == b


def verdict(before: str, after_place: str, after_dig: str, short: str):
    """★四条判据的**纯函数**版✗★（★可离线判 ✓ 与 ① 那一跑用的完全一样✓★）

    ★回 `(ok, 明细字典)`✗★ ✓ 明细里每条都写**它凭什么**（★原始数字 ✓★）
    """
    b, ap, ad = parse_scan(before), parse_scan(after_place), parse_scan(after_dig)
    d = {}
    if b is None or ap is None or ad is None:
        d["读得到吗"] = "★读不到✗★（★不判 ✗ 也不冒充通过✓★）"
        return False, d
    d["solid"] = "%d ⇒ %d ⇒ %d" % (b[0], ap[0], ad[0])
    d["含 %s 的项" % short] = "%d ⇒ %d ⇒ %d" % (
        sum(1 for x in b[3] if short in x), sum(1 for x in ap[3] if short in x),
        sum(1 for x in ad[3] if short in x))
    d["counts 项数"] = "%d ⇒ %d ⇒ %d" % (len(b[3]), len(ap[3]), len(ad[3]))
    c1 = ap[0] == b[0] + 1                      # ★放上去 ⇒ solid +1✗★
    c2 = len(ap[3]) == len(b[3]) + 1            # ★多重集也 +1✗★
    c3 = ad[0] == b[0] and ad[3] == b[3]        # ★挖掉 ⇒ **逐项**回基线✗★
    d["M8a solid+1"] = c1
    d["M8b 多重集+1"] = c2
    d["M8d 逐项回基线"] = c3
    return bool(c1 and c2 and c3), d


def full_cube_below(text: str, words=("grass_block", "dirt", "cobblestone", "stone", "planks",
                                      "sand", "gravel", "deepslate", "andesite", "granite",
                                      "diorite", "log", "obsidian", "terracotta", "glass",
                                      "bricks", "clay", "snow_block", "bedrock")):
    """★"脚下是不是**整方块**"✗★（★§79.48 的关键那一改 ✗ 按名字认 ✓ 不猜几何✓★）"""
    p = parse_scan(text)
    if p is None or p[0] != 1:
        return False
    return any(w in text for w in words)


if __name__ == "__main__":
    import sys
    # ★★会印 ✓/✗ 的脚本必须 **pin 住 stdout**✗★★（★P151/P160 ✓ 被 `stdio_guard` 当场点名✓★）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("★box_probe 自检（★不连世界✗★）★")
    print("  " + FIELD_HELP)
    ok, d = verdict(
        "dshscan vol=27 solid=5 air=22 kinds=5 counts[a:2,b:1,c:1,d:1]",
        "dshscan vol=27 solid=6 air=21 kinds=6 counts[a:2,b:1,c:1,d:1,e:1]",
        "dshscan vol=27 solid=5 air=22 kinds=5 counts[a:2,b:1,c:1,d:1]",
        "e")
    print("  三份好回执 ⇒", ok, d)
    print("  读不到 ⇒", verdict("", "", "", "e"))
