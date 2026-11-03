#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""idle_test.py -- ★★"挂机小动作"的判据✗★★（I1~I5 ✓ 离线 ✓ 2026-10-03 ✓）

★口径（★先写死 ✗ 三条硬约束都是从世界里学来的✓★）★
  ★I1 忙 ⇒ **不做** ✗ 而且**说清因为忙**✗★（★走路时身体朝向归移动 ✗ §79.55✓★）
  ★I2 幅度**有上限**✗★（★给 999 也只走 45°✗★）
  ★I3 ★★必须转回原位✗★★（★回读对不上 ⇒ 判红 ✗ 不许"看一眼就跑了"✓★）
  ★I4 ★**冷却**内再来 ⇒ 拒 ✗ 且要说明**还要等几秒**✗★
  ★I5 ★读不到自己的朝向 ⇒ **不做**✗★（★不猜 0,0 ✗ 不冒充成功✓★）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_gesture as G  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== idle_test：挂机小动作 I1~I5 ==")
state = {"t": 1000.0, "pose": (10.0, 0.0), "aims": [], "back_ok": True}
G.pose_now = lambda: state["pose"]


def fake_aim(yaw, pitch, tol=12, wait=0.25, tries=2):
    # ★★注入缝要跟**真签名**对齐✗★★（2026-10-03 ✓ 当场被 `TypeError` 抓住✓★）
    #   ★而且"哪一次是**转回来**"不能靠 yaw 比 ✗ 因为看一眼之后**姿态已经变了**✗★
    #   ⇒ ★按**第几次调用**判 ✗（★第 2 次＝回原位✓★）★
    state["n"] = state.get("n", 0) + 1
    state["aims"].append((round(yaw, 1), round(pitch, 1)))
    if state["n"] % 2 == 0:                          # ★偶数次 ＝ 转回来✓★
        state["pose"] = (yaw, pitch)
        return state["back_ok"], "回看", 1
    state["aims"].append((round(yaw, 1), round(pitch, 1)))
    if abs(yaw - state["pose"][0]) < 0.01:          # ★"转回来"那一次✓★
        return state["back_ok"], "回看", 1
    state["pose"] = (yaw, pitch)
    return True, "看向别处", 1


G.aim_and_verify = fake_aim
G._last_idle[0] = 0.0

# ★I1：忙 ⇒ 不做
txt, bad = G.t_idle_beat(busy=lambda: (True, "它在动（0.5 秒挪了 0.30 格）"), now=lambda: 1000.0)
check("I1", bad and "不做" in txt and "它在动" in txt and not state["aims"],
      "★忙 ⇒ 不做 ✗ 且说清因为忙 ✗ 且**一次都没转头**✗★ ✓")

# ★I2：幅度被夹到 45°
state["aims"].clear()
state["pose"] = (10.0, 0.0)
G._last_idle[0] = 0.0
G.t_idle_beat(amplitude=999.0, hold=0.0, busy=lambda: (False, "闲着"), now=lambda: 2000.0)
first = state["aims"][0] if state["aims"] else None
check("I2", first is not None and abs(first[0] - 10.0) <= 45.01,
      "★幅度给 999 ⇒ 实际只走 %s✗★ ✓" % (first,))

# ★I3：转不回来 ⇒ 判红
state["aims"].clear()
state["pose"] = (10.0, 0.0)
state["back_ok"] = False
G._last_idle[0] = 0.0
txt3, bad3 = G.t_idle_beat(hold=0.0, busy=lambda: (False, "闲着"), now=lambda: 3000.0)
check("I3", bad3 and "转回来了=false" in txt3,
      "★回不到原位 ⇒ 判红 ✗（★不许「看一眼就跑了」✓★）")

# ★I4：冷却
state["back_ok"] = True
txt4, bad4 = G.t_idle_beat(hold=0.0, busy=lambda: (False, "闲着"), now=lambda: 3001.0)
check("I4", bad4 and "还要等" in txt4, "★冷却内再来 ⇒ 拒 ✗ 且说明还要等几秒✗★ ✓（%s）" % txt4[-40:])

# ★I5：读不到朝向 ⇒ 不做
G.pose_now = lambda: (None, None)
G._last_idle[0] = 0.0
txt5, bad5 = G.t_idle_beat(hold=0.0, busy=lambda: (False, "闲着"), now=lambda: 9000.0)
check("I5", bad5 and "读不到自己朝向" in txt5, "★读不到朝向 ⇒ 不做 ✗（★不猜 0,0✓★）")

print("=> idle %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
