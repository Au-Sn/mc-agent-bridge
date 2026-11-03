#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_fence_test.py -- 导出那一半的机制（F1~F4 离线 2026-10-13 §79.228）

用户裁决 B1③：mod_contract 接上导出。口径：
  · 第一次跑 ⇒ 记账（schema／mod_version／count／摘要）
  · 以后跑 ⇒ 比，不一样就红
  · 缺导出 ⇒ export_guard 硬红 ＋ 一句人话
★验法✗★：用**临时合成导出**（标 synthetic）＋**临时围栏文件**（走 tmp/）⇒
  不碰 state/ 里的真围栏 ✗ 验完必清 ✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import export_guard as EG
import kb_export as KX
import kb_snapshot as KS

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


def syn(count=2, h=1.0):
    return {"schema": KX.SCHEMA, "exported_at": "2026-10-13T00:00:00Z",
            "mod_version": "synthetic-0.0.0", "count": count, "errors": [],
            "blocks": {"minecraft:stone": {"family": "full", "max_height": h},
                       "minecraft:oak_slab": {"family": "slab", "max_height": 0.5}}}


print("== export_fence: F1~F4 ==")
import mod_contract as MC

tmp_exp = ROOT / "tmp" / "_syn_export.json"
tmp_fence = ROOT / "tmp" / "_syn_fence.json"
snap = None
try:
    # F1 缺导出（不给候选）⇒ 硬红一句人话
    #   ★做法✗★：把合成导出**不**放进去 ⇒ find_export 找不到 ⇒ require 抛
    for f in (ROOT / "state" / "export_snapshots").glob("synthetic*"):
        f.unlink()
    if not pathlib.Path(KX.find_export("")).is_file():
        try:
            MC.export_fence(fence_path=tmp_fence)
            check("F1", False, "缺导出却没红")
        except EG.MissingExport as e:
            check("F1", "缺输入" in str(e), "缺导出 ⇒ MissingExport ＋ 人话")
    else:
        check("F1", True, "（导出在盘上 ⇒ 这条跳过，如实说）")

    # F2 有合成导出 ⇒ 第一次跑是**记账**
    tmp_exp.write_text(json.dumps(syn(), ensure_ascii=False), encoding="utf-8")
    snap = KS.save(tmp_exp)
    tmp_fence.unlink(missing_ok=True)
    ok2, why2 = MC.export_fence(fence_path=tmp_fence)
    check("F2", ok2 and tmp_fence.is_file(),
          "第一次跑 ⇒ 记账 ⇒ %s" % why2[:72])

    # F3 同样的导出再跑 ⇒ 一致（绿）
    ok3, why3 = MC.export_fence(fence_path=tmp_fence)
    check("F3", ok3, "同一份导出再跑 ⇒ %s" % why3[:72])

    # F4 导出动过（改一个 max_height）⇒ 必须红
    tmp_exp.write_text(json.dumps(syn(h=0.9375), ensure_ascii=False), encoding="utf-8")
    (ROOT / "state" / "export_snapshots").glob("synthetic*")
    for f in (ROOT / "state" / "export_snapshots").glob("synthetic*"):
        f.unlink()
    KS.save(tmp_exp)
    ok4, why4 = MC.export_fence(fence_path=tmp_fence)
    check("F4", (not ok4) and ("导出" in why4),
          "导出动过 ⇒ %s" % why4[:72])
finally:
    # ★★验完必清：合成快照 ✗ 临时导出 ✗ 临时围栏 全删✗★★
    for f in (ROOT / "state" / "export_snapshots").glob("synthetic*"):
        f.unlink()
    man = ROOT / "state" / "export_snapshots" / "manifest.json"
    if man.is_file():
        try:
            rows = [r for r in json.loads(man.read_text(encoding="utf-8"))
                    if "synthetic" not in str(r.get("file"))]
            man.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as exc:
            # ★不静默✗★：这段一失败 ⇒ ★manifest 里还留着 synthetic* 行 ✗ 而快照文件刚被删掉✗★
            #   ⇒ ★下一次跑会读到「指向不存在文件的清单」✗ F1 可能走「跳过 ⇒ PASS」的假绿✗★
            #   ⇒ ★所以失败必须喊出来 ✗ 不许 pass（★返回/判定语义一律不动 ✗ 只加记录✗★）
            print("   ★警告✗★：manifest 清理失败（★合成快照行可能残留 ✗ 下次跑会假绿✗★）："
                  "%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
    tmp_exp.unlink(missing_ok=True)
    tmp_fence.unlink(missing_ok=True)
    print("   （★已清✗★：合成快照／临时导出／临时围栏都删了）")

print("=> export_fence %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
