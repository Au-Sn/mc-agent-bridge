#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""errata_costs.py -- ★错题代价分档：离线拦的 vs 世界里换的✗★（欠账 ⑧ 的另一半 ✓ 2026-10-02 ✓）

WHY ✓（用户 2026-10-02 的原话要点 ✓）：
  ★"P172 条里离线拦的 vs 世界里换的 ✗ 构成比要开始有数✗★ ——
   ★这是「**免疫系统在长** 还是 只有病历在厚」的**唯一判据**✗"★

★方法（★先说清楚 ✗ 因为它是**启发式**✓★）
  ① 逐条读归档（`### P<n>` ✓）
  ② 按**文本证据**分档 ✓：
     ★离线拦✗★：条目里出现**闸门/判据**的痕迹（`check_all` ✓ `*_test.py` ✓ `离线` ✓
        `判据` ✓ `闸门` ✓ `不许` ＋ 具体测试名 ✓）
     ★世界里换✗★：出现**实地测量**的痕迹（`实测` ✓ `世界里` ✓ `回读` ✓ `采样` ✓
        `witness` ✓ `digest` ✓ `世界真值` ✓ `掉` ✓ `挖` ✓ `走` ✓）
     ★两样都有✗★ ⇒ 记 `both`（★这恰恰是**最好**的一档：世界里抓到 ✗ 然后**固化成闸门**✓★）
     ★都没有✗ ⇒ `unknown`（★据实报 ✗ 不许猜✓★）
  ③ ★按 P 号**分段**给构成比✗★（P 号≈时间序 ✓）⇒ ★看比值**随时间是升还是平**✗★
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "docs" / "错题本-归档-2026-09-30.md"
OUT = ROOT / "docs" / "错题代价分档.md"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GATE = ("check_all", "_test.py", "离线", "判据", "闸门", "守卫", "跑一遍闸门", "总检",
        "闸门里", "白名单")
WORLD = ("实测", "世界里", "回读", "采样", "witness", "digest", "世界真值", "真的升",
         "掉下", "挖掉", "走过去", "跑了", "两次", "当场", "现场")

text = ARCH.read_text(encoding="utf-8", errors="replace")
blocks = re.split(r"^### (P\d+)", text, flags=re.M)
entries = []
for i in range(1, len(blocks), 2):
    tag, body = blocks[i], blocks[i + 1]
    n = int(re.sub(r"\D", "", tag) or 0)
    g = [k for k in GATE if k in body]
    w = [k for k in WORLD if k in body]
    kind = "both" if (g and w) else ("gate" if g else ("world" if w else "unknown"))
    entries.append((n, tag, kind, g[:3], w[:3]))
entries.sort()
print("★解析到错题 %d 条✗★（P%d ~ P%d ✓）" % (len(entries), entries[0][0], entries[-1][0]))

kinds = {}
for e in entries:
    kinds[e[2]] = kinds.get(e[2], 0) + 1
print("★总构成✗★：" + " ｜ ".join("%s=%d" % (k, kinds.get(k, 0))
                                 for k in ("gate", "world", "both", "unknown")))

# ★分段看趋势✗★（每 40 条一段 ✓ P 号≈时间序 ✓）
SEG = 40
segs = []
for s in range(0, len(entries), SEG):
    chunk = entries[s:s + SEG]
    c = {}
    for e in chunk:
        c[e[2]] = c.get(e[2], 0) + 1
    segs.append((chunk[0][1], chunk[-1][1], len(chunk), c))

print()
print("★分段趋势✗★（★每段 40 条✗★）：")
for (a, b, cnt, c) in segs:
    gate_like = c.get("gate", 0) + c.get("both", 0)
    print("  %s~%s（%d 条）⇒ ★离线沾边 %d ✗ 纯世界里 %d ✗ 两样都有 %d✗★ ⇒ 闸门化率 %.0f%%"
          % (a, b, cnt, c.get("gate", 0), c.get("world", 0), c.get("both", 0),
             100.0 * gate_like / max(1, cnt)))

doc = ["# 错题代价分档（★离线拦的 vs 世界里换的✗★）", "",
       "> 生成：**2026-10-02** ✓ 由 `py tools/errata_costs.py` 机器生成 ✗ 方法见脚本头 ✓",
       "> ★这是用户 2026-10-02 点名的**唯一判据**✗★：★「免疫系统在长」 ⇒ 后面的错题应当**越来越多**"
       "先被闸门拦住 ✗ 而不是靠世界里撞✗ ✗ 也不是靠我好记性 ✓★", "",
       "## 一、总构成", "",
       "| 档 | 条数 | 含义 |", "|---|---|---|",
       "| ★离线拦（gate）✗★ | **%d** | ★文本里出现闸门/判据的痕迹✗★ |" % kinds.get("gate", 0),
       "| ★世界里换（world）✗★ | **%d** | ★文本里出现实地测量的痕迹✗★ |" % kinds.get("world", 0),
       "| ★两样都有（both）✗★ | **%d** | ★世界里抓到 ✗ **然后固化成闸门**✗ —— 这是**最好**的一档✓★"
       % kinds.get("both", 0),
       "| 认不出（unknown） | **%d** | ★据实报 ✗ 不许猜✓★ |" % kinds.get("unknown", 0), "",
       "## 二、★分段趋势✗★（每 40 条 ✗ P 号≈时间序 ✓）", "",
       "| 段 | 条数 | gate | world | both | ★闸门化率✗★ |", "|---|---|---|---|---|---|"]
for (a, b, cnt, c) in segs:
    doc.append("| %s~%s | %d | %d | %d | %d | **%.0f%%** |"
               % (a, b, cnt, c.get("gate", 0), c.get("world", 0), c.get("both", 0),
                  100.0 * (c.get("gate", 0) + c.get("both", 0)) / max(1, cnt)))
doc += ["", "★怎么读这张表✗★：", "",
        "- ★闸门化率**往上走**✗ ⇒ ★免疫系统在长✗★（★新的教训越来越多变成**会自己红的判据**✓★）",
        "- ★闸门化率**平或往下**✗ ⇒ ★只有病历在厚✗★（★写完就躺着 ✗ 下次照样犯 ✓★）",
        "- ★`both` 那一档最值钱✗★：★世界里抓到一条 ✗ 同一轮就把它**变成闸门**✗★ ✓",
        "- ★方法局限（据实✗）★：★分档是**按关键词**的启发式 ✗ ⇒ 它给的是**趋势** ✗",
        "  ★不是逐条的精确裁定 ✗ 要精确裁定得人工过一遍 ✓★", ""]
OUT.write_bytes("\n".join(doc).encode("utf-8"))
print()
print("★已写✗★ docs/%s ✓" % OUT.name)
