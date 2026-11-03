#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sandbox_test.py -- ★★"沙盒档"要被判据钉住✗★★（欠账 ⑦ 第 1 层 ✓ 2026-10-02 ✓）

判据（★先写死✗★）
  A1 ★测试件必须落在沙盒框里✗★：★已知测试件（§79.8 的校准网格 ＋ 那块木板✓）的坐标
     必须被 `SANDBOX_BOUNDS` 包含✗★ —— ★否则沙盒会把**我们要测的东西**挡在外面✗ ✓
  A2 ★框外必须被拒✗★：`mcp_policy.check` 对框外坐标必须回 **False ＋ `out_of_bounds`**✓
  A3 ★框内必须放行✗★（★不然测试跑不动 ✗ 会被当成"闸门太严"✗ ✓）
  A4 ★`off` 必须能还原✗★：★切 on 再 off ✗ 策略文件要回到**切换前**的样子（或不存在✓★）
  A5 ★不许静默✗★：`on` 的输出里必须**明写**"跑完要 off"✗ ✓
  ★全部在**临时策略文件**上做 ✗ 不碰真的 `tools/bridge_policy.json`✓（★A4 也用它 ✓）
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_policy as P  # noqa: E402
import sandbox as SB  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def inside(b, x, y, z):
    """★框形状是 `x0/x1/y0/y1/z0/z1`✗★（★第一版我按 `{"x":[lo,hi]}` 判 ✗ 于是**永远为真**✗ ✓）"""
    return (b["x0"] <= x <= b["x1"] and b["y0"] <= y <= b["y1"] and b["z0"] <= z <= b["z1"])


print("== sandbox_test：沙盒档 A1~A5 ==")
b = SB.SANDBOX_BOUNDS
fixtures = [(4124, 71, -1, "校准网格（§79.8 ✓）"), (4124, 72, -1, "那块木板 ✓"),
            (4115, 71, 11, "假人常驻点（§78 那一带 ✓）")]
missing = [f for f in fixtures if not inside(b, f[0], f[1], f[2])]
check("A1", not missing,
      "测试件都在框里 ✓（★缺 %s✗★）" % ([f[3] for f in missing] or "无 ✓"))

# ★A2/A3 用**临时**策略文件 ✗ 不碰真的那份✓★
#   ★注✗★：★第一版我只写了 `bounds` ✗ 于是 `dig_block` 先撞上**权限交集**（缺 blocks/navigation ✗）
#   ⇒ ★判词变成 `capability_not_granted` ✗ 而我要验的是**边界**✗★ ⇒ ★把 `grant` 也写进去✗★ ✓
tmp = ROOT / "tmp" / "_sandbox_probe.json"
tmp.write_text(json.dumps({"enabled": True, "allow": None, "bounds": b,
                           "grant": ["blocks", "navigation", "observation", "inventory",
                                     "containers"]}), encoding="utf-8")
P.POLICY = tmp
P._state["loaded"] = False
P.load(force=True)
in_ok = P.check("dig_block", {"x": 4124, "y": 71, "z": -1, "purpose": "测试"})
out_bad = P.check("dig_block", {"x": 4000, "y": 71, "z": -1, "purpose": "测试"})
check("A2", out_bad[0] is False and "out_of_bounds" in out_bad[1],
      "框外 ⇒ 拒 ✓（%s…）" % out_bad[1][:40])
check("A3", in_ok[0] is True, "框内 ⇒ 放行 ✓")
tmp.unlink()
P.POLICY = ROOT / "tools" / "bridge_policy.json"
P._state["loaded"] = False
P.load(force=True)

# ★A4：切 on ／ off 必须回到原样（★也在临时路径上做✓★）
probe = ROOT / "tmp" / "_sandbox_state.json"
probe.write_text(json.dumps({"enabled": True, "allow": ["bot_state"]}), encoding="utf-8")
orig = probe.read_text(encoding="utf-8")
SB.POLICY = probe
SB.BACKUP = ROOT / "tmp" / "_sandbox_state.before.json"
if SB.BACKUP.exists():
    SB.BACKUP.unlink()
SB.on()
after_on = probe.read_text(encoding="utf-8")
SB.off()
check("A4", after_on != orig and probe.read_text(encoding="utf-8") == orig,
      "`on` 改了 ✓ `off` **还原**成原样 ✓")
SB.BACKUP.unlink(missing_ok=True)
probe.unlink(missing_ok=True)
SB.POLICY = ROOT / "tools" / "bridge_policy.json"
SB.BACKUP = ROOT / "tools" / "bridge_policy.before_sandbox.json"

import io  # noqa: E402
import contextlib  # noqa: E402
buf = io.StringIO()
SB.POLICY = ROOT / "tmp" / "_sandbox_out.json"
SB.BACKUP = ROOT / "tmp" / "_sandbox_out.before.json"
with contextlib.redirect_stdout(buf):
    SB.on()
txt = buf.getvalue()
check("A5", "off" in txt and "务必" in txt, "`on` 明写「跑完务必 off」 ✓（%s…）" % txt.strip()[:40])
SB.POLICY.unlink(missing_ok=True)
SB.BACKUP.unlink(missing_ok=True)
SB.POLICY = ROOT / "tools" / "bridge_policy.json"
SB.BACKUP = ROOT / "tools" / "bridge_policy.before_sandbox.json"
print("=> sandbox %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
