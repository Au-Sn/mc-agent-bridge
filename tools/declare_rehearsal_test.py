#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""declare_rehearsal_test.py -- 预演"导出回来"那条链（R1~R5 离线 2026-10-13 §79.267）

★为什么有它✗★：★真导出到的那一次是**一次性窗口** ✗ 别在那儿才发现工具有问题✗★ ✓
★它拿一份**合成导出**（★放在 tmp/ ✗ 不叫 blockkb.json✗★）去撞 `declare_collision.py`✗★ ✓
★口径✗★：
  · ★只走 `--dry`✗★ ⇒ ★**不许动真例外表**✗★（★哈希前后比 ✗ R4 就是这条✓★）✗★ ✓
  · ★三条纪律要**在输出里被点名**✗★：★canopy ⇒ 拒 ✗ 导出没覆盖 ⇒ 不猜 ✗ 只写碰撞槽✗★ ✓
  · ★计划要有**四个数**✗★（★已声明／一致／没覆盖／拒✗★）✗ 否则"★先看计划★"是空话✗★ ✓
"""
from __future__ import annotations

import hashlib
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

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.is_file() else "?"


print("== declare_rehearsal: R1~R5 ==")
STORE = ROOT / "state" / "exceptions.json"
h0 = sha(STORE)

# ★拿**真的**未声明名单（★不是我编的物种✗★）✗ 造一份合成导出✗★
import u1_declared as U1
und = (U1.u1_numbers().get("undeclared") or [])[:40]
check("R1", len(und) >= 10, "拿真名单来预演：%d 条未声明里取前 %d 条" % (len(und), len(und)))

FAM = {"full": 1.0, "slab": 0.5, "snow_layer": 0.125, "none": 0.0, "other": 0.9375}
blocks = {}
for i, sp in enumerate(und):
    fam = ("full", "slab", "snow_layer")[i % 3]
    blocks[sp] = {"family": fam, "max_height": FAM[fam], "empty": False}
if len(und) >= 2:
    blocks[und[1]] = {"family": "canopy", "max_height": 1.0}      # ★必须被拒✗★
if len(und) >= 3:
    blocks.pop(und[2], None)                                      # ★必须"不猜"✗★
SYN = ROOT / "tmp" / "rehearsal_export.json"
SYN.write_text(json.dumps({"schema": "dshbridge/registry_blocks@1", "count": len(blocks),
                            "errors": 0, "blocks": blocks}, ensure_ascii=False),
                encoding="utf-8")

r = subprocess.run([sys.executable, "-B", "-X", "utf8",
                    str(ROOT / "tools" / "declare_collision.py"),
                    "--dry", "--export", str(SYN)], cwd=str(ROOT), capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=600)
out = (r.stdout or "") + (r.stderr or "")

check("R2", ("已声明" in out) and ("没覆盖" in out) and ("拒" in out),
      "计划要有四个数（★已声明／一致／没覆盖／拒✗★）⇒ %s"
      % next((l.strip()[:70] for l in out.splitlines() if "已声明" in l and "拒" in l), "★没有✗★"))
check("R3", ("canopy" in out) and ("没覆盖" in out),
      "三条纪律要**在输出里被点名**（★canopy ⇒ 拒 ✗ 没覆盖 ⇒ 不猜✗★）")
check("R4", sha(STORE) == h0,
      "★`--dry` **不许动真例外表**✗★ ⇒ %s ⇒ %s" % (h0, sha(STORE)))
check("R5", r.returncode == 0, "它自己能跑完（★rc=%s✗★）" % r.returncode)

# ★★2026-10-18（★§79.285✗★）✗★★：★`未声明` **已经是 0**✗★ ⇒ ★这条预演**没有对象**✗★ ⇒
#   ★"★没对象可预演★" ＝ **INCONCLUSIVE ＋ rc=4**（★不是通过 ✗ 也不是坏✗★）✗★ ✓
#   ★它会**自动复活**✗★：★未声明哪天又 > 0 ✗ 它就重新真预演✗★ ✓
if len(und) < 10:
    print("INCONCLUSIVE: ★没有对象可预演★ —— `未声明` 只有 **%d** 条"
          "（★铁律②成立后为 0 ✓★）⇒ 这条预演**无事可做** ✗ 不是坏✗★" % len(und))
    sys.exit(4)
print("=> declare_rehearsal %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
