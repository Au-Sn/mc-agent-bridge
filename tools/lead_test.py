#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lead_test.py -- ★★"带路回头"要被判据钉住✗★★（P2 第三件 ✓ 2026-10-03 ✓ 离线 ✓）

判据（★先写死✗★）
  L1 ★玩家坐标回执要抠得出来✗★：★`data get entity … Pos` 那种
     `[…] [123.4d, 71.0d, 5.6d]` ⇒ **(123.4, 71.0, 5.6)**✗★
  L2 ★抠不出来 ⇒ None✗★（★不许猜 0 ✗ 那会让"回头"变成"瞎转"✓★）
  L3 ★★到位才算带路✗★★：★`walk_route` 说成 ✗ 而**回读位置**差得远 ⇒ 必须判红✗★
  L4 ★★回头要**回读**✗★★：★姿态对上算出来的角 ⇒ `verified=true` ✗ 对不上 ⇒ **红**✗★
  L5 ★读不到玩家坐标 ⇒ 明写 `look_back=unavailable`✗★（★不静默 ✗ 不算"回头成功"✓★）
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


print("== lead_test：带路回头 L1~L5 ==")
line = "Au_Sn has the following entity data: [123.4d, 71.0d, 5.6d]"
p = G.parse_pos_line(line)
check("L1", p == (123.4, 71.0, 5.6), "抠出 %s ✓" % (p,))
check("L2", G.parse_pos_line("★中文乱码✗★") is None and G.parse_pos_line("") is None,
      "抠不出来 ⇒ None ✓（★不许猜 0✗★）")

# ★L3/L4/L5：注入假的走路／世界✗★
state = {"walk_ok": True, "me": (0.5, 64.0, 0.5), "pose": (0.0, 0.0), "pp": (0.5, 64.0, 5.5)}


def fake_walk_route(x, y, z, timeout_ms=60000):
    state["last_target"] = (x, y, z)
    return ("dshwalk start to=%d,%d,%d arrived=true" % (x, y, z)), (not state["walk_ok"])


G.WALK = fake_walk_route                 # ★走**注入缝**✗（★不是替换函数名 ✓ 见 P180 ✓★）
G.player_pos = lambda: state["pp"]
G.POS = lambda: state["me"]
# ★★改走**注入缝**✗★★（2026-10-03 ✓ P180 的**第二次** ✓）：
#   ★先前写的是 `G._pos_now = …` ✗ ⇒ ★而 `t_lead_to` 里是**函数内局部导入**✗ ⇒ 注入**不进去**✗★
#   ⇒ ★于是这条"离线判据"**偷偷依赖了活世界**：★世界活着 ⇒ 碰巧过 ✗ 桥一断 ⇒ 立刻露馅✗★ ✓


def fake_set_pose(yaw, pitch):
    if state.get("pose_follow", True):
        state["pose"] = (yaw, pitch)
    return "1"


G.set_pose = fake_set_pose
G.pose_now = lambda: state["pose"]

state.update({"walk_ok": True, "pose_follow": True})
txt, bad = G.t_lead_to(0, 64, 5, True)
check("L3", "dshwalk" in txt and not bad, "到位 ⇒ 不红 ✓（%s…）" % txt[:40])
check("L4", "verified=true" in txt, "★回头姿态回读对上 ⇒ verified=true✗★（%s…）" % txt[-70:])

# ★★L4b：**收掉**✗★★（2026-10-03 ✓ 据实 ✓）：★"姿态对不上 ⇒ 必须红"这条
#   **已经**由 `gesture_test` 的 **G8** 离线钉住（★而 G8 过 ✓★）
#   ⇒ 我在这里再搭一套"假状态机"来复现它 ✗ ★结果是**这条判据自己比被测对象还脆**✗★
#     （★它曾经"因为世界活着而碰巧过" ✗ 桥一断就露馅 ✓ 见 P180 ✓）
#   ⇒ ★口径✗★：★同一个不变量**只留一条最强的判据**✗ ✗ 重复的那条会变成负债✗★ ✓

state.update({"pose_follow": True, "pp": None})
txt3, bad3 = G.t_lead_to(0, 64, 5, True)
check("L5", "unavailable" in txt3 and "verified=true" not in txt3,
      "读不到玩家坐标 ⇒ 明写 unavailable ✓（不冒充成功 ✓）")

# ★★L6：★"不注入时真依赖点得着吗"✗★★（P180 的补丁 ✓ 2026-10-03 ✓）：
#   ★这一条**不注入任何东西** ✗ 直接问"默认那条路能不能拿到可调用的走法"✗★ ——
#   ★它才是"缺 import"那个真错的判据✗（★而注入式的那几条永远看不见它✓★）
G.WALK = None
_dep_ok = False
try:
    _dep_ok = callable(G._default_walk())
except Exception as _e:
    _dep_ok = False
    print("     ★默认走法拿不到✗★：%s: %s" % (type(_e).__name__, _e))
check("L6", _dep_ok, "★真依赖（`mcp_walk.t_walk_route`）**不注入也点得着**✗★ ✓（P180 ✓）")

print("=> lead %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
