#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""move_slot_test.py -- ★★"槽位移动"要被判据钉住✗★★（欠账 ⑳ ✓ 2026-10-03 ✓ 离线 ✓）

判据（★先写死✗★）
  N1 ★越界**发都不发**✗★（★99 ⇒ 拒 ✓ 且**一次 `dsh` 都没调**✓★）
  N2 ★`from` 槽是空的 ⇒ 没动✗★（★不许发命令 ✗ 并如实说✓★）
  N3 ★★回读才算成✗★★：★注入假的 `dshinv list`**和**假的命令回执 ✗
     ★`to` 槽真变成那件东西 ⇒ `verified=true`✗ ✗ 没变 ⇒ **判红**✗★
  N4 ★读不到背包 ⇒ `verified=false`✗★（★不静默 ✗ 不冒充成功✓★）
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

import mcp_percept as P  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== move_slot_test：槽位移动 N1~N4 ==")
calls = {"dsh": 0, "inv": None, "reply": "dshinv move 21 -> 0 ok"}


def fake_dsh(cmd, t=60.0):
    if cmd.startswith("dshinv list"):
        calls["dsh"] += 1
        if calls["inv"] is None:
            return ""
        return "dshinv list selected=0 => " + " ".join(
            "%d:%s" % (k, v) for k, v in sorted(calls["inv"].items()))
    calls["dsh"] += 1
    return calls["reply"]


P.dsh = fake_dsh                     # ★注入缝：替换模块里的 `dsh`✓★

calls.update({"dsh": 0, "inv": {}})
txt, bad = P.t_move_slot(99, 3)
check("N1", bad and calls["dsh"] == 0, "★越界 ⇒ 拒 且**一次都没发**✗★（dsh 调用 %d 次 ✓）"
      % calls["dsh"])

calls.update({"dsh": 0, "inv": {5: "minecraft:torchx1"}})
txt, bad = P.t_move_slot(30, 4)
check("N2", bad and calls["dsh"] <= 1, "★`from` 空 ⇒ 没发移动命令✗★（dsh %d 次 ✓ ｜ %s）"
      % (calls["dsh"], txt[:44]))

calls.update({"dsh": 0, "inv": {21: "minecraft:iron_pickaxex1"}, "reply": "ok"})
_seq = {"n": 0}


def moving_dsh(cmd, t=60.0):
    if cmd.startswith("dshinv list"):
        _seq["n"] += 1
        if _seq["n"] >= 2:                  # ★第二次读 ⇒ 镐**已经挪到 0**✗★
            return "dshinv list selected=0 => 0:minecraft:iron_pickaxex1"
        return "dshinv list selected=0 => 21:minecraft:iron_pickaxex1"
    return "ok"


P.dsh = moving_dsh
txt, bad = P.t_move_slot(21, 0)
check("N3", (not bad) and "verified=true" in txt,
      "★`to` 槽回读**真变了** ⇒ verified=true✗★（%s…）" % txt[:60])


def stuck_dsh(cmd, t=60.0):
    if cmd.startswith("dshinv list"):
        return "dshinv list selected=0 => 21:minecraft:iron_pickaxex1"
    return "ok"


P.dsh = stuck_dsh
txt, bad = P.t_move_slot(21, 0)
check("N3b", bad and "verified=false" in txt, "★`to` 槽**没变** ⇒ 判红✗★（%s…）" % txt[:56])

P.dsh = lambda cmd, t=60.0: ""          # ★读不到背包✗★
txt, bad = P.t_move_slot(21, 0)
check("N4", bad and "verified=false" in txt and "没发命令" in txt,
      "★读不到背包 ⇒ verified=false 且**不发命令**✗★（%s…）" % txt[:50])
print("=> move_slot %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
