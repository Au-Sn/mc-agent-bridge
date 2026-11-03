#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_guard_test.py -- 缺输入必须硬红, 快照必须能被找到（X1~X5 离线 2026-10-13 §79.224）

用户裁决 B1 三招：
  ① 版本化快照（带 mod_version+schema，进库）
  ② 缺文件硬红（缺输入≠测不了；统一两种口径）
  ③ mod_contract 接上导出（下一节）
这一条守 ①②。口径：
  · 用**临时合成导出**（明确标 synthetic）验机制 ✗ 不往 state/ 里塞假数据 ✗
  · 验完**必清**（快照目录里那个合成文件要删掉）
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import os as _os
# ★★2026-10-13（★§79.246✗★）✗★★：★判据的结论**不许取决于环境变量**✗★ ——
#   ★实测✗★：★外面设了 `DSH_BLOCKKB` ⇒ `find_export` 把**给定路径**排在快照前面 ⇒
#     ★X3（★"★必须优先快照★"✗★）就红 ✗ 而那是**环境**造成的 ✗ 不是判据坏✗★ ✓
#   ★⇒ 本判据**自己**把它清掉✗★（★与 §79.239"★结论不许取决于用哪个 Python★"同一族✓★）✗★ ✓
_os.environ.pop("DSH_BLOCKKB", None)
import export_guard as EG
import kb_export as KX
import kb_snapshot as KS

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


print("== export_guard: X1~X5 ==")

# ---- X1 缺输入时 require 必须红, 而且带一句人话
_real_missing = not pathlib.Path(KX.find_export("")).is_file()
if _real_missing:
    try:
        EG.require("X1")
        check("X1", False, "缺输入却没红")
    except EG.MissingExport as e:
        check("X1", ("缺输入" in str(e)) and ("怎么补" in str(e)),
              "缺输入 ⇒ MissingExport, 且带人话（%d 字）" % len(str(e)))
else:
    check("X1", True, "（导出在盘上 ⇒ 这条跳过验证 ✗ 如实说）")

# ---- X2 soft() 不红, 只如实报
p, why = EG.soft("X2")
check("X2", (p is not None and not why) or (p is None and "缺输入" in why),
      "soft() 不抛异常 ⇒ %s" % ("在盘上" if p else "如实报缺"))

# ---- X3 快照必须能被 find_export 找到（用临时合成导出验机制）
SYN = {"schema": KX.SCHEMA, "exported_at": "2026-10-13T00:00:00Z",
       "mod_version": "synthetic-0.0.0", "count": 1, "errors": [],
       "blocks": {"minecraft:stone": {"family": "full", "max_height": 1.0}}}
tmp = ROOT / "tmp" / "_syn_export.json"
tmp.write_text(json.dumps(SYN, ensure_ascii=False), encoding="utf-8")
made = None
try:
    dst = KS.save(tmp)
    made = dst
    got = pathlib.Path(KX.find_export(""))
    check("X3", got.name == dst.name,
          "find_export 找到的是**快照**（%s）而不是仓库那条" % got.name)
    # ---- X4 快照名字带 mod_version 与 schema
    check("X4", ("synthetic-0.0.0" in dst.name) and ("registry_blocks" in dst.name),
          "快照名带版本与 schema ⇒ %s" % dst.name)
    # ---- X5 内容没变 ⇒ 不重写（D4 口径）
    before = dst.stat().st_mtime_ns
    KS.save(tmp)
    check("X5", dst.stat().st_mtime_ns == before,
          "同样的内容再存一次 ⇒ **没有重写**（mtime 不变）")
finally:
    # ★★验完必清✗★★：合成快照要删掉 ✗ 别留在 state/ 里当"真数据"
    for f in ((ROOT / "state" / "export_snapshots").glob("synthetic*")):
        f.unlink()
    man = ROOT / "state" / "export_snapshots" / "manifest.json"
    if man.is_file():
        try:
            rows = [r for r in json.loads(man.read_text(encoding="utf-8"))
                    if "synthetic" not in str(r.get("file"))]
            man.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as exc:
            # ★不静默✗★：manifest 里会留着 synthetic* 行 ✗ 而快照文件刚被删掉 ✗★
            #   ⇒ 下一次 `find_export` 会读到「指向不存在文件的清单」⇒ X3/X4 可能假绿✗★
            #   ⇒ ★失败必须喊出来 ✗ 不许 pass（★判定语义一律不动 ✗ 只加记录✗★）
            print("   ★警告✗★：manifest 清理失败（★合成快照行可能残留 ✗ 下次跑会假绿✗★）："
                  "%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
    tmp.unlink(missing_ok=True)
    print("   （★已清✗★：合成快照与临时文件都删了）")

print("=> export_guard %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
