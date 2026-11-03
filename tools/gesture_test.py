#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gesture_test.py -- ★★"动作即语言"要被判据钉住✗★★（P2 ✓ 2026-10-02 ✓ 离线 ✓ 不碰世界 ✓）

判据（★先写死✗★）
  G1 ★朝向数学✗★：★`bearing_to` 朝 +Z ⇒ yaw≈0✗；朝 **+X** ⇒ yaw≈**-90**（★MC 的 yaw 是顺时针✗★）；
     朝 **-Z** ⇒ yaw≈**180**✓★
  G2 ★点头序列✗★：★低头→抬头→回中✗ ⇒ 三步 ✗ 且**回到原值**✗★
  G3 ★摇头序列✗★：★左→右→回中✗ ⇒ 三步 ✗ 且**回到原值**✗★
  G4 ★`wrap180`✗★：★179.5 ⇒ -179.5✗（★跨 ±180 那一步不许算成 359 度差✓★）
  G5 ★★做完必须**回读**✗★★：★注入假 send／假 pose ✗ ⇒ 姿态对得上 ⇒ `verified=true`✓★
  G6 ★★对不上必须报红✗★★：★注入"姿态永远不动"的假 send ✗ ⇒ 必须 `verified=false`✗★
     （★这条是 G5 的**反面** ✗ 少了它 ✗ "回读"这件事**等于没验**✗ ✓）
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


print("== gesture_test：动作即语言 G1~G6 ==")
# ★★G1 的第一版我写错了期望✗★★：★`bearing_to` 瞄的是**方块中心**（`+0.5` ✓）✗
#   而我站在 (0,64,0) 去瞄 (0,64,5) ⇒ 中心是 (0.5,64.5,5.5) ⇒ yaw≈-5.2° ✗ 不是 0 ✗★
#   ⇒ ★把**自己的站位**放到格中心 (0.5,64,0.5)**✗ 期望才是整数值✓★
y1, p1 = G.bearing_to(0.5, 64, 0.5, 0, 64, 5)      # ★朝 +Z✗★
y2, _ = G.bearing_to(0.5, 64, 0.5, 5, 64, 0)       # ★朝 +X✗★
y3, _ = G.bearing_to(0.5, 64, 0.5, 0, 64, -5)      # ★朝 -Z✗★
check("G1", abs(y1) < 1 and abs(y2 + 90) < 1 and abs(abs(y3) - 180) < 1,
      "yaw: +Z⇒%.0f ✓ +X⇒%.0f ✓ -Z⇒%.0f ✓" % (y1, y2, y3))
check("G2", G.nod_seq(10.0, 1) == [28.0, -8.0, 10.0], "点头＝低头→抬头→回中 ✓（%s ✓）"
      % G.nod_seq(10.0, 1))
check("G3", G.shake_seq(0.0, 1) == [-22.0, 22.0, 0.0], "摇头＝左→右→回中 ✓（%s ✓）"
      % G.shake_seq(0.0, 1))
# ★G4 的第二版我又写错了期望✗★：★`wrap180` 的口径是**映射到 (-180, 180]**✗ ⇒
#   ★179.5 **本来就在区间里** ✗ 不该翻成 -179.5✗★（★翻过去反而差 359°✗★）
#   ⇒ ★真正要验的是"**超出区间才折**"✗：181 ⇒ -179 ✗ -181 ⇒ 179 ✓★
check("G4", abs(G.wrap180(179.5) - 179.5) < 1e-6 and abs(G.wrap180(-179.5) - (-179.5)) < 1e-6
      and abs(G.wrap180(181.0) - (-179.0)) < 1e-6 and abs(G.wrap180(-181.0) - 179.0) < 1e-6,
      "区间内不动 ✓ 超出才折（181⇒-179 ✗ -181⇒179 ✓）✓")

# ★G5/G6：注入假的 send／pose✗★
state = {"yaw": 0.0, "pitch": 0.0, "mode": "follow"}


def fake_send(text):
    if state["mode"] == "follow":
        import re
        m = re.search(r"~ ~ ~ (-?[\d.]+) (-?[\d.]+)", text)
        if m:
            state["yaw"], state["pitch"] = float(m.group(1)), float(m.group(2))
    return "1"


G._send = fake_send
G.pose_now = lambda: (state["yaw"], state["pitch"])

state.update({"yaw": 0.0, "pitch": 0.0, "mode": "follow"})
txt5, bad5 = G.t_gesture("nod", 1)
check("G5", "verified=true" in txt5 and not bad5, "回读对上 ⇒ verified=true ✓（%s…）" % txt5[:44])

state.update({"yaw": 0.0, "pitch": 0.0, "mode": "freeze"})   # ★姿态永远不动✗★
txt6, bad6 = G.t_gesture("nod", 1)
check("G6", "verified=false" in txt6 and bad6, "★姿态不动 ⇒ verified=false 且判红✗★（%s…）"
      % txt6[:52])
# ★★G7/G8：★"发一次没对上 ⇒ **重发**"✗★★（欠账 ⑲ ✓ 2026-10-03 ✓）
#   ★场景✗★：★假人是**共享**的 ⇒ ★第一次设的姿态可能被别人的动作覆盖✗★
#     ⇒ ★`aim_and_verify` 必须**再发一次** ✗ 并且**如实写出"发了几次"**✗★
_seq2 = {"n": 0, "pose": (0.0, 0.0)}


def _flakey_set(yaw, pitch):
    _seq2["n"] += 1
    if _seq2["n"] >= 2:                 # ★第一次**没生效** ✗ 第二次才生效✓★
        _seq2["pose"] = (yaw, pitch)
    return "1"


G.set_pose = _flakey_set
G.pose_now = lambda: _seq2["pose"]
_seq2.update({"n": 0, "pose": (0.0, 0.0)})
ok7, got7, used7 = G.aim_and_verify(90.0, 10.0)
check("G7", ok7 and used7 == 2, "★第一次没对上 ⇒ 重发一次 ⇒ 对上✗★（★used=%d✗★ ✓）" % used7)

_seq2.update({"n": 0, "pose": (0.0, 0.0)})


def _never_set(yaw, pitch):
    _seq2["n"] += 1
    return "1"                          # ★全都不生效✗★


G.set_pose = _never_set
ok8, got8, used8 = G.aim_and_verify(90.0, 10.0, tries=2)
check("G8", (not ok8) and used8 == 2, "★两次都没对上 ⇒ 必须判 false✗★（★不许报成真✓★）")

# ★★G9/G10：★"跟着你的视线看"✗★（2026-10-03 ✓ 观感那一轴 ✓ 离线 ✓）
#   ★口径✗★：★读不到玩家的朝向 ⇒ **明写 unavailable**✗（★不猜 0,0 ✓★）
#     ★而读得到 ⇒ 发出去的 yaw **就是玩家那个**（★照抄 ✗ 不加自己的加工✓★）
_sent = []


def _fake_aim(yaw, pitch, tol=12, wait=0.25):
    _sent.append((round(yaw, 1), round(pitch, 1)))
    return True, "ok", 1


G.aim_and_verify = _fake_aim
G._player_rot = lambda name: (137.5, -22.0)
_ok9, _bad9 = G.t_follow_gaze("Au_Sn")
check("G9", (not _bad9) and "verified=true" in _ok9 and _sent and _sent[0] == (137.5, -22.0),
      "★读到玩家 (137.5,-22.0) ⇒ 发出去的就是它✗★ ✓（★同一路 `aim_and_verify`✓★）")

G._player_rot = lambda name: None
_ok10, _bad10 = G.t_follow_gaze("Nobody")
check("G10", _bad10 and "unavailable" in _ok10,
      "★读不到朝向 ⇒ 明写 `unavailable`✗★（★不猜 0,0 ✗ 不冒充成功✓★）")

# ★★G11/G12：★"先看再放"✗★（欠账 ㉕ ✓ 2026-10-03 ✓ 离线 ✓）
#   ★口径✗★：★放置之前**必须**先把视线对准那一格 ✗ 而且"没对上"要**写在回执里**✗★ ✓
#     （★世界实测：★不看就放 ⇒ `useItemOn=FAIL` ✗ 哪怕下面**是实心的**✓★）
import offline_guard as OG  # noqa: E402
OG.require_world("手势（★G11／G12 要在真格子上瞄准／放置✗★）")
import mc_mcp as M2  # noqa: E402

_seen = []


def _fake_aim(x, y, z):
    _seen.append((round(x, 1), round(y, 1), round(z, 1)))
    return "★指路✗★ 回读 verified=true", False


M2.AIM = _fake_aim
_txt11, _bad11 = M2.t_place_block(4121, 70, 9, "minecraft:crafting_table")
check("G11", _seen and _seen[0] == (4121.5, 70.2, 9.5) and "dshplace" in _txt11
      and "先看" in _txt11,
      "★放之前先对准了格子中心✗★ " + str(_seen[0] if _seen else "-")
      + " ✓（★回执里也带「先看」✓★）")


def _bad_aim(x, y, z):
    return "★指路✗★ 读不到自己的坐标", True


M2.AIM = _bad_aim
_txt12, _bad12 = M2.t_place_block(4121, 70, 9, "minecraft:crafting_table")
check("G12", "没对上" in _txt12 and "dshplace" in _txt12,
      "★对准没成 ⇒ 回执**明写「没对上」**✗ ✗ 而放置本身照样报出来（★不静默跳过✓★）")
M2.AIM = None

print("=> gesture %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
