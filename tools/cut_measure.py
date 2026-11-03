#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut_measure.py -- ★"★切了到底改多少★"的**唯一一份**实现✗★（★§79.191 ✗ 2026-10-05✗★）

★★为什么单独一件✗★★：★`cut_verify_test` 与 `cut_ready` **都要**这个数✗★ ⇒
★★只留一份定义 ✗ 免得两个工具各算一套又打脸（★§79.188 的教训✓★）✗★★ ✓
★★它量的是✗★★：★**关／开开关**时三条**保护签名**（★`mapread.is_floor`／`blocks_space`／`cat`✗★）
★各自的答案 ✗ **变不变**✗★ ✓
★★它**不是**✗★★：★"★名字模型 vs 导出★"那一比（★那是 `kb_risk` ✗ 预测性✗★）✗★ ✓
★它**也不**保证铁律②（★那是 `u1_declared` ✗ 未声明数✗★）✗★ ✓
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

import blockkb as KB  # noqa: E402
import mapread as MR  # noqa: E402

FIELDS = [("is_floor", MR.is_floor), ("blocks_space", MR.blocks_space), ("cat", MR.cat)]


def diff_of(blocks_iter):
    """★逐方块比三条签名 ✗ 回 `(比过 ✗ 跳过 ✗ 差异 ✗ 差异清单✗★)`✗★ ✓

    ★★计数器是**必须**的✗★★：★"★全跳光★"不许看起来像"★全一致★"✗★ ✓（★§79.186✗★）
    """
    cmp_n = skip_n = diff_n = 0
    diffs = []
    for sp in blocks_iter:
        KB.SOURCE = "blacklist"
        try:
            old = tuple(fn(sp) for _f, fn in FIELDS)
        except Exception:
            skip_n += 1
            continue
        KB.SOURCE = "table"
        try:
            new = tuple(fn(sp) for _f, fn in FIELDS)
        except Exception:
            skip_n += 1
            continue
        cmp_n += 1
        if old != new:
            diff_n += 1
            diffs.append(sp)
    KB.SOURCE = "blacklist"
    return cmp_n, skip_n, diff_n, diffs


def per_ns_diff(blocks: dict, min_blocks: int = 1) -> dict:
    """★按命名空间分组算 ✗ 回 `{ns: (方块数 ✗ 比过 ✗ 跳过 ✗ 差异✗★)}`✗★ ✓"""
    by_ns = {}
    for sp in blocks:
        by_ns.setdefault(sp.split(":")[0], []).append(sp)
    out = {}
    for ns, v in by_ns.items():
        if len(v) < min_blocks:
            continue
        cmp_n, skip_n, diff_n, _d = diff_of(sorted(v))
        out[ns] = (len(v), cmp_n, skip_n, diff_n)
    return out


if __name__ == "__main__":
    import json
    import kb_export as KX
    exp = json.loads(KX.find_export("").read_text(encoding="utf-8"))
    r = per_ns_diff(exp.get("blocks") or {}, min_blocks=40)
    print("★按模组（★≥40 个方块✗★）✗ 共 %d 个✗★" % len(r))
    for ns, (n, c, s, d) in sorted(r.items(), key=lambda kv: -kv[1][3])[:16]:
        print("   %-26s ★差异 %5d★ / %5d  （★比过 %d ✗ 跳过 %d✗★）"
              % (ns, d, n, c, s))
