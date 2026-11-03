#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""switch_plan.py -- ★按模组的**切换计划**✗★（阶段 4 的执行件 ✓ 2026-10-04）

★它把两张表**并起来**✗★
  · ★`迁移准备度`（★`divergence --by-namespace`✓★）✗：★今天标签侧说清了、与黑名单一致的占比✗★
  · ★`迁移风险图`（★`kb_risk`✓★）✗：★切过去**会改变决策**的方块数✗★
★⇒ ★每个模组一行✗★：★"★能切多少★"与"★切了会改多少★"并排 ✗ 再给一句**建议**✗★ ✓

★建议的口径（★写死✗★）✗★
  · ★`先切`✗★：★准备度 ≥ 70% 且风险占比 ≤ 25%✗★（★两头都不差✓★）
  · ★`先看清`✗★：★风险占比 > 50%✗★（★像 `mcwdoors` 那种 ⇒ ★逐条看明白再动 ✓ 见 §79.122✓★）
  · ★`等导出覆盖`✗★：★"★表中无★"占比 > 50%✗★（★标签侧没话说 ✗ 切了也没依据✓★）
  · ★其余 ⇒ `可切`✗★ ✓
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def advise(n, agree, disagree, no_family) -> str:
    """★纯函数✗★（★好离线判✓★）⇒ 见模块注释的口径"""
    tot = max(1, n)
    if no_family / tot > 0.5:
        return "★等导出覆盖✗★"
    if disagree / tot > 0.5:
        return "★先看清✗★"
    if disagree / tot <= 0.25:
        return "★先切✗★"
    return "可切"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=40)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--out", default="docs/切换计划.md")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)

    import json
    import blockkb as KB
    import kb_export as KX
    import kb_risk as KR
    import mapread as MR
    import tag_census as TC
    import divergence as DV

    exp = json.loads(KX.find_export("").read_text(encoding="utf-8"))
    risk = KR.risk_map(exp, MR.shape)
    # ★★"★标签准备度★"的口径（★2026-10-05 ✗ 定 **(乙)**✗★）✗★★
    #   · ★判据✗★：★`类别 ⇒ 族` 映射里**声明过**的那个族 ✗ 与**碰撞真值**是否一致✗★ ✓
    #   · ★★分母写清✗★★：★**能判的物种数**（★有类别 **且** 该类已声明✓★）✗
    #     ★而"★无类别★"与"★类别未声明★"**分列** ✗ 绝不混成一个假的百分比✗★ ✓
    #   ★旧版为什么是**假的 0%**✗★：★它拿**英文几何族**去比**中文类别**✗ ⇒ 全不匹配✗★ ✓
    #     （★§79.143 实测 33 类 vs 8 族 ✗ 两套词表✗★）
    KB.load_categories()
    read = {}
    for sp, ent in (exp.get("blocks") or {}).items():
        ns = sp.split(":", 1)[0]
        d = read.setdefault(ns, {"judgeable": 0, "match": 0, "no_cat": 0,
                                 "undeclared": 0, "policy": 0})
        _cat = KB.category_of(sp)
        if not _cat:
            d["no_cat"] += 1
            continue
        # ★★只有**几何类**声明才拿去和碰撞核验✗★★（★政策类如 `叶子`⇒`canopy`
        #   声称的不是几何 ✗ 比了必然"★对不上★" ✗ 那是**假的不合格**✗★ ✓）
        _want = KB.GEOMETRIC_CATEGORY.get(_cat)
        if not _want:
            if _cat in KB.POLICY_CATEGORY:
                d["policy"] = d.get("policy", 0) + 1
            else:
                d["undeclared"] += 1
            continue
        d["judgeable"] += 1
        if (ent or {}).get("family") == _want:
            d["match"] += 1
    rows = []
    for ns, r in risk["by_ns"].items():
        if r["n"] < a.min:
            continue
        rd = read.get(ns) or {"judgeable": 0, "match": 0, "no_cat": 0, "undeclared": 0}
        rows.append({"ns": ns, "n": r["n"], "agree": r["agree"], "disagree": r["disagree"],
                     "no_family": r["no_family"], "rd": rd,
                     "rate": (rd["match"] / rd["judgeable"]) if rd["judgeable"] else None,
                     "advise": advise(r["n"], r["agree"], r["disagree"], r["no_family"])})
    print("== 切换计划 ✗ 导出 %d 个方块 ✗ 覆盖 %d 个模组（≥%d）=="
          % (risk["total"], len(rows), a.min))
    print("  %-22s %6s %7s %7s  %-24s %s"
          % ("模组", "方块", "不改变", "会改", "★几何可判/对上✗★", "建议"))
    for r in sorted(rows, key=lambda x: -x["agree"])[:a.top]:
        rd = r["rd"]
        rate = ("★不可判✗★" if r["rate"] is None else "%.0f%%" % (100 * r["rate"]))
        print("  %-22s %6d %7d %7d  %3d/%-3d %-5s 政策%-4d 未声明%-5d 无类别%-5d %s"
              % (r["ns"], r["n"], r["agree"], r["disagree"], rd["match"],
                 rd["judgeable"], rate, rd.get("policy", 0), rd["undeclared"],
                 rd["no_cat"], r["advise"]))
    if a.dry:
        return 0
    lines = ["# 切换计划（★生成物 ✗ 别手改 ✗ 重跑 `switch_plan.py`✓★）", "",
             "> ★来源✗★：`迁移准备度`（★标签侧说清多少✓★）＋ `迁移风险图`（★切过去会改多少✓★）",
             "> ★★两个轴别混✗★★：★**风险**（★切过去会改多少决策 ✗ 物理✓★）与",
             "> ★**标签准备度**（★标签侧说清多少 ✓ **语义**✓★）是**两件事**✗★ ⇒",
             "> ★物理切换看**风险** ✗ 标签准备度低**不**阻止物理切换（★碰撞自己就是依据✓★）✗★",
             "> ★建议口径✗★：★先切 ＝ 风险≤25% ✗ 先看清 ＝ 风险>50% ✗",
             "> 等导出覆盖 ＝ 表中无>50% ✗ 其余 ＝ 可切✗★", "",
             "| 模组 | 方块 | 不改变决策 | 会改决策 | 准备度 | ★建议✗★ |",
             "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: -x["agree"]):
        _rd = r["rd"]
        lines.append("| `%s` | %d | %d | %d | %d/%d（%s） | %d | %d | %s |"
                     % (r["ns"], r["n"], r["agree"], r["disagree"], _rd["match"],
                        _rd["judgeable"],
                        "★不可判✗★" if r["rate"] is None else "%.0f%%" % (100 * r["rate"]),
                        _rd["undeclared"], _rd["no_cat"], r["advise"]))
    lines += ["", "★怎么用✗★：★挑一个 `先切` 的 ✗ 按 `docs/按种切换-操作手册.md` 四步走✗**",
              "★`先看清` 的（★像 `mcwdoors` 99%✓★）**必须逐条看明白**再动 ✗ 不许跳✗★ ✓"]
    (ROOT / a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("")
    print("  已写 %s ✓" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
