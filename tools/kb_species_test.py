#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_species_test.py -- ★单种可回退的判据★（T1~T4 ✓ 全离线 ✓ 用临时文件 ✓ 2026-10-04）

★它守什么✗★：★"★可回退★"如果**没有痕迹** ✗ 那它和"★悄悄改掉★"没法区分✗★ ✓
  · ★T1 ✗★：★`show` 要把**三处**（★模型／碰撞槽／语义槽✓★）与**三档**都摆出来✗★
  · ★T2 ✗★：★`drop` 从表里摘掉**那一条** ✗ 并**留痕**✗★
  · ★T3 ✗★：★`drop` 一个**不在表里**的 ⇒ 明说"★什么都没退★"✗★（★不许假装成功✓★）
  · ★T4 ✗★：★★`drop` **不许**动导出文件✗★★（★导出是**观测** ✗ 观测不许被"★退掉★"✓★）
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import exception_table as ET  # noqa: E402
import kb_species as KS  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


tmp = pathlib.Path(tempfile.mkdtemp())
STORE = tmp / "exceptions.json"
LOG = tmp / "kb_rollback.log"
KS.LOG = LOG
ET.STORE = STORE
STORE.write_text(json.dumps({
    "schema": "dshbridge/exceptions@1",
    "entries": [
        {"species": "a:door", "claim": "blocks_space", "verdict": True, "evidence": "collision",
         "source": "★`/dshkb` 导出 ✗ 族 full ⇒ 物理真值★", "by": "测试", "at": "2026-10-04"},
        {"species": "a:keep", "claim": "family", "verdict": "full", "evidence": "registry",
         "source": "★标签普查 ✗ 2026-10-04 离线读出★", "by": "测试", "at": "2026-10-04"},
    ]}, ensure_ascii=False, indent=1), encoding="utf-8")

print("== kb_species_test：T1~T4 ==")

# ---- T1 show 要摆出三处与三档
os.environ["CLASSIFIER_SOURCE"] = "blacklist"
buf = io.StringIO()
with redirect_stdout(buf):
    rc = KS.show("minecraft:oak_planks")
out = buf.getvalue()
check("T1", (rc == 0) and ("模型" in out) and ("碰撞槽" in out) and ("语义槽" in out)
      and ("blacklist" in out) and ("table+fallback" in out),
      "★`show` 要摆**三处**与**三档**✗★ ⇒ rc=%s（%d 字符）" % (rc, len(out)))

# ---- T4（★先量导出文件的指纹 ✗ 因为 drop 之后要它不变✗★）
import kb_export as KX  # noqa: E402
_exp = KX.find_export("")
_fp0 = (_exp.stat().st_mtime_ns, _exp.stat().st_size) if _exp.is_file() else None

# ---- T2 drop 要摘掉那一条 ＋ 留痕
buf = io.StringIO()
with redirect_stdout(buf):
    rc = KS.drop("a:door", claim="blocks_space", why="★测试：单种回退✗★",
                 store=STORE, log=LOG)
out = buf.getvalue()
left = [e["species"] for e in ET.load(STORE)]
check("T2a", (rc == 0) and ("a:door" not in left) and ("a:keep" in left),
      "★只摘掉**那一条** ✗ 别的照旧✗★ ⇒ rc=%s 剩 %s" % (rc, left))
check("T2b", LOG.is_file() and ("a:door" in LOG.read_text(encoding="utf-8")),
      "★★回退**必须留痕**✗★★ ⇒ %s" % (LOG.name if LOG.is_file() else "★没写日志✗★"))

# ---- T3 不在表里 ⇒ 明说
buf = io.StringIO()
with redirect_stdout(buf):
    rc = KS.drop("a:nothing", why="★测试✗★", store=STORE, log=LOG)
out = buf.getvalue()
check("T3", (rc == 2) and ("什么都没退" in out),
      "★不在表里 ⇒ 明说「什么都没退」 ✗ 不许假装成功✗★ ⇒ rc=%s" % rc)

# ---- T4 导出文件必须**原封不动**
_fp1 = (_exp.stat().st_mtime_ns, _exp.stat().st_size) if _exp.is_file() else None
check("T4", _fp0 == _fp1,
      "★★`drop` **不许**动导出（★观测不许被退掉✗★）⇒ %s ⇒ %s✗★★" % (_fp0, _fp1))

print("=> kb_species %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
