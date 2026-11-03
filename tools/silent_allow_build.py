#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""silent_allow_build.py -- ★从两份审计报告生成**机器可读白名单**（§79.403）

★输入✗★：★`tmp/audit_kb.md`（★gate-auditor✗★）✗ `tmp/audit_tools.md`（★ledger-proofreader✗★）
★输出✗★：★`state/silent_allow.json`** ✗
  ★格式✗★：★{"<相对路径>": {"lines": [..], "why": "..."}, …}✗★ ✓
★★只收"★判定明确是**假阳性**★"的（★"★不确定★"一律**不收** ✗ 宁可让它继续报出来✗★）✗★★ ✓
★★健壮性✗★★：★万一某行因为改代码**移位** ✗ 条目**匹配不上** ⇒ ★判据会**重新报出来**（★安全方向✗★）
  ★不会"★白名单把新问题也盖住★"✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPORTS = ("tmp/audit_kb.md", "tmp/audit_tools.md")
OUT = ROOT / "state" / "silent_allow.json"

# ★表格行：`| path:line | ... |`✗★
ROW = re.compile(r"^\|\s*`?([A-Za-z0-9_./\\-]+\.(?:py|java)):(\d+)`?\s*\|(.*)$")
# ★"假阳性" 的写法✗★：★`假阳性` 或 `★假阳性★`✗★
FP = re.compile(r"(★假阳性★|假阳性[:：]|\|\s*假阳性\s*\|)")
# ★"不确定" ⇒ **不收**✗★
UNCERTAIN = re.compile(r"(★不确定|不确定[:：]|待定|看 ACP 语义|要世界才知道)")


def main() -> int:
    allow = {}
    stats = {"rows": 0, "fp": 0, "uncertain": 0, "other": 0}
    for rel in REPORTS:
        p = ROOT / rel
        if not p.is_file():
            print("  ★%s 不在 ✗ 跳过★" % rel)
            continue
        print("  读 %s" % rel)
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = ROW.match(ln)
            if not m:
                continue
            stats["rows"] += 1
            path, line, rest = m.group(1), int(m.group(2)), m.group(3)
            if UNCERTAIN.search(rest):
                stats["uncertain"] += 1
                continue
            if not FP.search(rest):
                stats["other"] += 1
                continue
            stats["fp"] += 1
            # ★理由✗★：★取判定那一列的文字（截 120 字✗★）
            cols = [c.strip() for c in rest.split("|") if c.strip()]
            why = ""
            for c in cols:
                if "假阳性" in c:
                    why = c[:120]
                    break
            e = allow.setdefault(path.replace("\\", "/"), {"lines": [], "why": []})
            if line not in e["lines"]:
                e["lines"].append(line)
            if why and why not in e["why"] and len(e["why"]) < 3:
                e["why"].append(why)
    # ★★§79.404✗★★：★**合并** ✗ 不覆盖✗★ —— ★既有条目（★手工补的 ✗ 含修过的✗★）必须保留✗★
    #   ★教训✗★：★2026-10-26 我跑了一次本脚本 ⇒ **把手加的 9 条冲掉了** ⇒ 判据立刻报 9 处 A ✗★ ✓
    OUT.parent.mkdir(parents=True, exist_ok=True)
    old = {}
    if OUT.is_file():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception as e:                  # ★读坏要吵✗★
            print("  ★旧白名单读坏：%r ✗ 按空处理（★会丢手工条目 ✗ 注意✗★）" % (e,))
    for k, v in old.items():
        e = allow.setdefault(k, {"lines": [], "why": []})
        for ln in (v.get("lines") or []):
            if ln not in e["lines"]:
                e["lines"].append(ln)
        for w in (v.get("why") or []):
            if w not in e["why"] and len(e["why"]) < 6:
                e["why"].append(w)
        e["lines"].sort()
    OUT.write_text(json.dumps(allow, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    n = sum(len(v["lines"]) for v in allow.values())
    print("  表格行 %d ✗ 判假阳性 **%d** ✗ 不确定 %d（★不收✗★）✗ 其他 %d"
          % (stats["rows"], stats["fp"], stats["uncertain"], stats["other"]))
    print("  ★写进 %s✗★：**%d** 个文件 ✗ 共 **%d** 条（★每条都带理由✓★）"
          % (OUT.relative_to(ROOT), len(allow), n))
    for k in sorted(allow)[:6]:
        print("     %-42s %s" % (k, allow[k]["lines"]))
    print("SILENTALLOW ok=1 files=%d lines=%d" % (len(allow), n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
