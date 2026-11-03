#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_risk.py -- ★迁移风险图：模型 vs 碰撞 ✗ 逐种 ✗ 覆盖**全部**注册方块✗★（2026-10-04）

★它回答阶段 4 的那个问题✗★：★"★如果把分类源换成碰撞表 ✗ 哪些方块**会改变决策**★"✗★ ✓

★比什么✗★
  · ★模型✗★：`mapread.shape`（★名字那条老路✓★）
  · ★碰撞✗★：`/dshkb` 导出的几何族（★物理真值✓★）
★判"一致"的口径✗★：★**按两条物理判定比**（★挡人／能站✓★）✗ **不按族名字面比**✗★ ——
  ★因为 `full` 与 `machine` 名字不同 ✗ 但两条判定一样 ⇒ ★换过去**不改变决策**✗★ ✓
  （★这正是 `divergence.decision_delta` 那条老口径 ✗ 一份实现✓★）

★为什么不用读世界✗★：★两边都是**数据** ✗ 而世界扫描受**回执上限**（★一次只能看几十种✓★）
  ✗ 这个图能覆盖**全部 24779**✗★ ✓
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def risk_map(export: dict, shape_fn) -> dict:
    """★纯函数✗★（★`shape_fn` 注入 ✗ 好离线判✓★）⇒ 见模块注释

    ★★它量的是**哪一件事**✗★★（★§79.188 写清 ✗ 因为与 `cut_verify` 的数不一样✓★）✗★：
      ★"★**名字模型**（★`shape_fn` 从名字推族✗★）" ↔ "★**导出**（★注册表给的族✗★）"✗★ ✓
      ★★这是**预测性**的一比 ✗ 与运行时开关无关✗★★ ✓
    ★★它**不是**"★切了开关会不会改★"✗★★ —— 那件事由 `cut_verify_test` 量✗
      （★它比的是**关／开开关**时三条保护签名各自的答案✓★）✗★ ✓
      ★两者数不同 ✗ 因为"★名字模型★" ≠ "★老路黑名单★"（★后者窄得多✓★）✗★ ✓
    """
    import blockkb as KB
    blocks = (export or {}).get("blocks") or {}
    out = {"total": 0, "agree": 0, "disagree": 0, "no_family": 0,
           "by_ns": {}, "worst": []}
    for sp, ent in blocks.items():
        fam, _why = KB.family_from_export(ent if isinstance(ent, dict) else {})
        ns = sp.split(":", 1)[0]
        d = out["by_ns"].setdefault(ns, {"n": 0, "agree": 0, "disagree": 0, "no_family": 0})
        out["total"] += 1
        d["n"] += 1
        if not fam:
            out["no_family"] += 1
            d["no_family"] += 1
            continue
        model = shape_fn(sp)
        if (KB.blocks_space_fam(model) == KB.blocks_space_fam(fam)
                and KB.is_floor_fam(model) == KB.is_floor_fam(fam)):
            out["agree"] += 1
            d["agree"] += 1
        else:
            out["disagree"] += 1
            d["disagree"] += 1
            out["worst"].append(sp)
    out["worst"].sort()
    return out


def snapshot(path, worst) -> int:
    """★把"★会改决策★"的名单**存下来**✗★（★一行一个物种 ✗ 排序✓★）

    ★为什么✗★：★任务书阶段 5 要的是"★分类族错题**新增率** → 0★"✗★ ⇒
      ★而"★分类族错题★"在这里有**精确定义**：★模型（名字那条老路）与碰撞真值
      **不一致**的方块✗★ ✓ ⇒ ★存下今天的名单 ✗ 以后每次重跑一对比 ✗
      "★新增了几个★／★修掉了几个★"就是那个率✗★ ✓
    """
    import pathlib as _pl
    p = _pl.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(sorted(worst)) + "\n", encoding="utf-8")
    return len(worst)


def compare(path, worst) -> dict:
    """★与快照逐条对比✗★ ⇒ `{"new": [...], "fixed": [...], "same": n}`✗★

    ★口径（★写死✗★）✗★：★`new` ＝ 今天有而快照里没有（★**新增错题** ✗ 要盯的就是它✓★）✗
      `fixed` ＝ 快照里有而今天没有（★修好的✓★）✗★ ✓
    """
    import pathlib as _pl
    p = _pl.Path(path)
    old = set()
    if p.is_file():
        old = {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()}
    now = set(worst)
    return {"new": sorted(now - old), "fixed": sorted(old - now),
            "same": len(now & old), "old_total": len(old), "now_total": len(now)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--snapshot", default="", help="★把会改决策的名单存下来✗★")
    ap.add_argument("--compare", default="", help="★与快照逐条对比✗★")
    a = ap.parse_args(argv)

    import kb_export as KX
    import mapread as MR
    p = KX.find_export(a.export)
    if not p.is_file():
        # ★★B1（★§79.224✗★）✗★★：★缺输入 ⇒ **硬红 ＋ 一句人话**✗★
        #   ★不是 INCONCLUSIVE ✗ 那个留给"要世界"（★没法测✓★）✗★ ✓
        import export_guard as _EG
        print("★FAIL★（缺输入）%s" % _EG.SENTENCE)
        return 1
    try:
        export = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print("INCONCLUSIVE: ★读不动✗★ %s: %s" % (type(e).__name__, e))
        return 4
    r = risk_map(export, MR.shape)
    tot = max(1, r["total"])
    print("== 迁移风险图 ✗ 导出 %d 个方块（★%s✗★）==" % (r["total"], p.name))
    print("  ★两条判定一致✗★（★换过去不改变决策✓★）  %6d  %5.1f%%"
          % (r["agree"], 100.0 * r["agree"] / tot))
    print("  ★★会改变决策✗★★（★迁移的**风险**✓★）      %6d  %5.1f%%"
          % (r["disagree"], 100.0 * r["disagree"] / tot))
    print("  ★族名不合用（★`canopy` 等 ✗ 交语义层✓★）  %6d" % r["no_family"])
    print("")
    # ★按"★风险条数★"排模组 ✗ 而不是按比例 ⇒ ★先修影响面最大的✗★ ✓
    big = [(n, d) for n, d in r["by_ns"].items() if d["n"] >= 40]
    print("  == 按**风险条数**排（★≥40 个方块的模组✗★）==")
    print("     %-26s %7s %9s %9s" % ("模组", "方块", "会改决策", "风险占比"))
    for n, d in sorted(big, key=lambda kv: -kv[1]["disagree"])[:a.top]:
        print("     %-26s %7d %9d %8.0f%%"
              % (n, d["n"], d["disagree"], 100.0 * d["disagree"] / max(1, d["n"])))
    print("")
    print("  == 风险最高的模组（★按占比 ✗ ≥40 个✗★）==")
    for n, d in sorted(big, key=lambda kv: -kv[1]["disagree"] / max(1, kv[1]["n"]))[:a.top]:
        print("     %-26s %7d %9d %8.0f%%"
              % (n, d["n"], d["disagree"], 100.0 * d["disagree"] / max(1, d["n"])))
    print("")
    if a.snapshot:
        n = snapshot(a.snapshot, r["worst"])
        print("  ★快照已存✗★ %s（★%d 条✓★）" % (a.snapshot, n))
    if a.compare:
        c = compare(a.compare, r["worst"])
        print("  ★★与快照对比✗★★：★新增 %d✗★ ｜ ★修掉 %d✗★ ｜ 仍然 %d"
              % (len(c["new"]), len(c["fixed"]), c["same"]))
        for sp in c["new"][:8]:
            print("     ★新增✗★ %s" % sp)
    print("  == 逐条（★前 8 ✗ 全名单 %d 条✗★）==" % len(r["worst"]))
    for sp in r["worst"][:8]:
        print("     %s" % sp)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
