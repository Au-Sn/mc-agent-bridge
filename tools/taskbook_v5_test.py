#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taskbook_v5_test.py -- 任务书 v5 的**主张**必须与代码一致（V1~V5 离线 2026-10-13 §79.255）

★为什么有它✗★：★用户裁决说"★修订点**并入**任务书 v5★"✗★ ⇒ ★我把四条修订写进了
`docs/任务书-v5-标签方向.md`✗★ ⇒ ★★但"★写进文档★"和"★代码真的那样★"是两件事✗★★ ✓
★（★这一路的病史就是"★主张 vs 实现★" ✗ 例 M2 那个"★不判的判据★"✓★）✗★ ✓
★判法✗★：★文档里**四条修订**各自点名了代码里的东西 ✗ 逐条去代码里撞✗★ ✓
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


DOC = ROOT / "docs" / "任务书-v5-标签方向.md"
print("== taskbook_v5: V1~V5 ==")
if not DOC.is_file():
    check("V1", False, "任务书 v5 不在：%s" % DOC.name)
    sys.exit(1)
doc = DOC.read_text(encoding="utf-8", errors="replace")

# ★V1 ★四条修订**都**在文档里点名了（★并入不是"★提一句★"✗★）
_need = ("A4", "C1", "C4", "E3")
_miss = [k for k in _need if k not in doc]
check("V1", not _miss, "四条修订都写进了 v5（★A4／C1／C4／E3✗★）⇒ 缺的：%s" % (_miss or "（没有 ✓）"))

# ★V2 §9 的两条梯子：文档说"★registry 不在物理梯上★" ✗ 代码里真的是那样吗
import exception_table as ET
_phys = tuple(ET.EVIDENCE_PHYS)
_sem = tuple(ET.EVIDENCE_SEM)
check("V2", ("registry" not in _phys) and (_phys[:2] == ("collision", "experiment"))
      and (_sem[:2] == ("registry", "experiment")),
      "§9 说「物理梯 collision⇒experiment ✗ registry 不在」★ ⇒ 代码里物理梯 %s ✗ 语义梯 %s"
      % ("／".join(_phys), "／".join(_sem)))

# ★V3 §8 的四族：文档点名 `tools/families.py` ✗ 代码里真的是那四个吗
import families as FAM
check("V3", tuple(FAM.FAMILIES) == ("phys", "sem", "exec", "policy"),
      "§8 说四族是 phys／sem／exec／policy ⇒ 代码里 %s" % ("／".join(FAM.FAMILIES),))

# ★V4 §7 的 TEMPORARY：文档说"★机器可读表 ＋ 8 样字段 ＋ 替换触发★" ✗ 表在不在
import json
TJ = ROOT / "state" / "temporary.json"
_rows = []
if TJ.is_file():
    _rows = (json.loads(TJ.read_text(encoding="utf-8")) or {}).get("entries") or []
_keys = ("id", "what", "where", "why_temporary", "today_state", "since",
         "replace_trigger", "watched_by")
_bad = [r.get("id") for r in _rows if any(not str(r.get(k) or "").strip() for k in _keys)]
check("V4", bool(_rows) and not _bad,
      "§7 说临时的东西都进 `state/temporary.json` 且带**替换触发** ⇒ 表里 %d 条 ✗ 缺字段的：%s"
      % (len(_rows), _bad or "（没有 ✓）"))

# ★V5 §6 的范围例外：文档说"★只读增强允许 ✗ 判定逻辑仍冻结★" ✗ 而代码里
#   ★只有**只读**的东西被加过 ✗ 判定逻辑一个字没动✗★ —— 拿"★导出围栏★"那条当抓手
_fence = (ROOT / "tools" / "mod_contract.py").read_text(encoding="utf-8", errors="replace")
check("V5", ("export_fence" in _fence) and ("missing" in _fence.lower()
      or "缺输入" in _fence or "MissingExport" in _fence or "require(" in _fence),
      "§6 说的是「只读导出/扫描增强允许」 ⇒ 代码里那条**只读**的导出围栏在（`mod_contract.export_fence`）")

# ★★2026-10-18（★复核 P0-2 ✗ §79.274✗★）✗★★：★V1~V5 一条数都不重算✗★ ⇒
#   ★§3 写「★1699／1699／0★」而真数是 **2165／1541／624** ✗ 它**照绿**✗★ ✓
#   ★口径✗★：★§3 的现状数必须**等于** `u1_declared.u1_numbers()` 现算✗★ ＋
#     ★旧的假数**不许再出现**✗★ ✓
import u1_declared as _U1
_nums = _U1.u1_numbers()
_doc_txt = DOC.read_text(encoding="utf-8", errors="replace") if DOC.is_file() else ""
# ★★2026-10-18（★§79.285✗★）✗★★：★V6 原来要求"★§3 的数**恰好**等于现算★"✗★ ⇒
#   ★每改一次数据 ✗ 任务书就得跟着改 ✗ 而它**已经漂过两次**（★1699 → 2165 → 2162✗★）✗★ ⇒
#   ★★根子是"★文档里**写死**数★"✗★★ ⇒ ★口径反过来（★与 `gate_tables` 的 `G5c` 同一课✗★）✗★：
#     ★★§3 **不许**写死现状数 ✗ 必须**引用** `state/u1_account.json`✗★★ ✓
_hard = [s for s in ("决策级 2162", "决策级 2165", "决策级 1699", "已声明 2162",
                     "未声明 0", "未声明 624", "已声明 1541") if s in _doc_txt]
_ref = ("u1_account.json" in _doc_txt) or ("u1_declared" in _doc_txt)
check("V6", (not _hard) and _ref,
      "★§3 **不许写死**现状数（★会漂 ✗ 已漂过两次✗★）✗ 必须**引用** `state/u1_account.json`★"
      " ⇒ 写死的：%s ／ 有引用：%s" % (_hard or "（没有 ✓）", _ref))
check("V6b", True, "★（★旧的两条已并进 V6 ✗ 不再要字面数✗★）★")

print("=> taskbook_v5 %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
