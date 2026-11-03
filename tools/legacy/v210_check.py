#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v210_check.py —— 验 v2.10 的扫描（判据写死 ✓）＋ 顺手补文档

判据（★写在这里 ＝ 事后不许改口★ ✗）：
  C1 `/dshver` 必须 2.10.0 ✓
  C2 `#minecraft:dirt` ⇒ **matched > 1000** ✓（v2.9 时它是 0 ✗ 这就是 bug 证据 ✓）
     —— 用这个标签是因为它**原版就有** ✓ 而且岛上草方块 794 ＋ 泥土 2443 ✓ ⇒ 必 > 1000 ✓
  C3 不带 match 的 `counts[...]` **必须按数量降序** ✓（我用代码检查"非递增" ✓）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)
BOX = "4096 55 -16 4160 96 48"
res: list[str] = []


def raw(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR %s: %s" % (type(e).__name__, str(e)[:100])


def kv(t: str) -> dict:
    d = {}
    for tok in t.replace("|", " ").split():
        if "=" in tok:
            k, _, v = tok.partition("=")
            d[k] = v
    return d


ver = raw("dshver")
res.append("C1 dshver -> %s" % ver)
ok1 = "2.10.0" in ver
res.append("C1 结果 -> %s" % ("PASS" if ok1 else "FAIL (还没重启 ⇒ 后面两项不算数 ✗)"))

if ok1:
    r2 = raw('dshscan %s "#minecraft:dirt" 5 1' % BOX)
    k2 = kv(r2)
    m = int(k2.get("matched", "-1") or -1)
    ok2 = m > 1000
    res.append("")
    res.append("C2 #minecraft:dirt -> %s" % r2[:300])
    res.append("C2 matched=%s ⇒ %s" % (m, "PASS" if ok2 else "FAIL"))

    r3 = raw("dshscan %s" % BOX)
    res.append("")
    res.append("C3 counts 原始 -> %s" % r3[:700])
    blob = ""
    if "counts[" in r3:
        blob = r3.split("counts[", 1)[1].split("]", 1)[0]
    pairs = []
    for tok in blob.split(","):
        if tok.startswith("more_kinds"):
            continue
        name, _, num = tok.rpartition(":")
        if num.isdigit():
            pairs.append(int(num))
    nonincreasing = all(pairs[i] >= pairs[i + 1] for i in range(len(pairs) - 1))
    ok3 = len(pairs) >= 10 and nonincreasing
    res.append("C3 解析到 %d 种 ✓ 非递增=%s ⇒ %s" % (len(pairs), nonincreasing, "PASS" if ok3 else "FAIL"))
    res.append("")
    res.append("小结：C1=%s C2=%s C3=%s" % (ok1, ok2, ok3))
else:
    res.append("（游戏还没重启到 2.10.0 ⇒ C2/C3 跳过 ✓ 等重启后再跑 ✓）")

(ROOT / "logs" / "v210_check.txt").write_text("\n".join(res), encoding="utf-8")
print("V210: %s" % " ".join(x for x in res if x.startswith("小结") or x.startswith("C1 结果")))
