#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pathplan_height_test.py -- 寻路层接 max_height 的 A/B（H1~H5 离线 2026-10-13 §79.232）

用户裁决 A3：寻路层接 `max_height`，先加 `AUTO_STEP_BY_HEIGHT` 开关 A/B 并行跑。
两个阈值**不是我编的**，就写在 pathplan 的注释里（都是实测口径）：
  · 自动上台阶上限 **0.6**（第 34 轮：写宽了会假可达）
  · 跳跃上限 ≈ **1.25**（模组 0.42 初速）
★验法✗★：开关是**读环境**的 ⇒ 必须在**子进程**里带 env 跑（真路径）✗;
  而高度**注入**进去（`_HEIGHTS`）⇒ 不用等导出 ✗ 规则本身完全可离线验✗★ ✓
"""
from __future__ import annotations

import json
import os
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


def sub(env, code):
    e = dict(os.environ)
    e.pop("AUTO_STEP_BY_HEIGHT", None)
    e.update(env)
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], cwd=str(ROOT), env=e,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode or not (r.stdout or "").strip():
        return None, (r.stderr or "").strip()[-200:]
    return json.loads(r.stdout.strip().splitlines()[-1]), ""


INJECT = ("import json,sys;sys.path.insert(0,r'" + str(ROOT / "tools") + "');"
          "import pathplan as PP;"
          "PP._HEIGHTS={'a:slab':0.5,'a:farm':0.9375,'a:fence':1.5,'a:full':1.0,'a:snow':0.1875};"
          "PP._HEIGHTS_OK=True;"
          "print(json.dumps({'by':PP.BY_HEIGHT,'step_max':PP.STEP_MAX,'jump_max':PP.JUMP_MAX,"
          "'slab':PP.is_auto_step('a:slab'),'farm':PP.is_auto_step('a:farm'),"
          "'snow':PP.is_auto_step('a:snow'),"
          "'climb_fence':PP.is_climbable('a:fence'),'climb_full':PP.is_climbable('a:full'),"
          "'h_full':PP.height_of('a:full'),'h_missing':PP.height_of('a:zzz')}))")

# H1 开关**关**着 ⇒ 名字版（与今天逐字相同）
d1, err1 = sub({}, INJECT)
check("H1", bool(d1) and d1.get("by") is False,
      "开关关着 ⇒ `BY_HEIGHT=False`（★走名字白名单／shape ✗ 与今天逐字相同✓★）%s" % (err1 or ""))

# H2 开关**开**着 ⇒ 自动上台阶按高度（≤0.6）
d2, err2 = sub({"AUTO_STEP_BY_HEIGHT": "1"}, INJECT)
check("H2", bool(d2) and d2.get("slab") is True and d2.get("farm") is False
      and d2.get("snow") is True,
      "开关开着 ⇒ 半砖(0.5)能上 ✗ 农田(0.9375)**不能** ✗ 雪层(0.1875)能 ⇒ %s"
      % ({k: d2.get(k) for k in ("slab", "farm", "snow")} if d2 else err2))

# H3 跳跃阈值（≤1.25）：栅栏 1.5 不行 ✗ 整方块 1.0 行
check("H3", bool(d2) and d2.get("climb_fence") is False and d2.get("climb_full") is True,
      "跳跃：整块(1.0)行 ✗ 栅栏(1.5)不行（★老实绕✓★）⇒ %s"
      % ({k: d2.get(k) for k in ("climb_fence", "climb_full")} if d2 else err2))

# H4 ★拿不到高度 ⇒ False ✗ **绝不静默回落名字**✗★
d4, err4 = sub({"AUTO_STEP_BY_HEIGHT": "1"},
               ("import json,sys;sys.path.insert(0,r'" + str(ROOT / "tools") + "');"
                "import pathplan as PP;PP._HEIGHTS={};PP._HEIGHTS_OK=False;"
                "print(json.dumps({'slab_by_h':PP.is_auto_step('minecraft:oak_slab'),"
                "'slab_by_name':(PP.BY_HEIGHT and None)}))"))
d4b, err4b = sub({}, ("import json,sys;sys.path.insert(0,r'" + str(ROOT / "tools") + "');"
                      "import pathplan as PP;"
                      "print(json.dumps({'slab_by_name':PP.is_auto_step('minecraft:oak_slab')}))"))
check("H4",
      bool(d4) and bool(d4b) and d4.get("slab_by_h") is False
      and d4b.get("slab_by_name") is True,
      "开关开着但**没有高度** ⇒ `False`（保守）✗ 而名字版说 `True`"
      " ⇒ ★两边不同 ✗ 证明**没有静默回落**✗★ ⇒ %s ／ %s"
      % (d4.get("slab_by_h") if d4 else err4, d4b.get("slab_by_name") if d4b else err4b))

# H5 阈值与注释里的实测口径一致
check("H5", bool(d2) and abs(float(d2.get("step_max", 0)) - 0.6) < 1e-9
      and abs(float(d2.get("jump_max", 0)) - 1.25) < 1e-9,
      "阈值＝实测口径：`STEP_MAX=0.6`（★第 34 轮✓★）✗ `JUMP_MAX=1.25`（★0.42 初速✓★）⇒ %s／%s"
      % (d2.get("step_max") if d2 else "?", d2.get("jump_max") if d2 else "?"))

print("=> pathplan_height %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
