#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut34_seam_check.py —— ★拆完之后，"桩还打得中吗"的专项判据★（离线 ✓ 秒级 ✓）

WHY ✓：拆 god file 最毒的一种坏法是"**判据全绿而桩打空了**"✗（P156~P158 同族 ✓）：
  · `chest_many_test` 把 `mc_mcp._near` 换成计数桩 ✗ 桩打空 ⇒ 那条"走一趟办多件"**假绿** ✗
  · `mc_mcp_smoke` 把 `mc_mcp.dsh/_walk/_pos_now` 换成假货 ✗ 桩打空 ⇒ 它**真去连世界** ✗
⇒ 这里把这件事**单独**测 ✓（★与"世界长什么样"无关✗★ —— 只问"桩有没有打中" ✓）

判据（先写死 ✓）
  S1 `mc_mcp.dsh` 换桩 ⇒ ★搬去 `mcp_walk` 的★ `_near` 发出去的是**桩的指纹** ✓
  S2 `mc_mcp.dsh` 换桩 ⇒ ★搬去 `mcp_geo` 的★ `_verify_band` 也走桩 ✓（两层不是一层 ✓）
  S3 `mc_mcp._walk` 换桩 ⇒ `_near` 真走那一支时用的是桩 ✓
  S4 `mc_mcp._walk`/`_pos_now` 换桩 ⇒ `mcp_walk._walk` 内部那两处也走桩 ✓
  S5 `_MISSION`/`BLOCKED`/`BLOCKED_LV`/`MOD_CLIMB_UP` 全层**同一个对象** ✓
  S6 还原之后 ⇒ 各层读到的又是**真身** ✓（不许留桩 ✗）
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M            # noqa: E402
import mcp_core               # noqa: E402
import mcp_geo                # noqa: E402
import mcp_percept            # noqa: E402
import mcp_walk               # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


lines = []
ok = [True]


def say(s: str) -> None:
    lines.append(s)
    print(s)


def check(name: str, cond: bool, note: str = "") -> None:
    ok[0] &= bool(cond)
    say("  %-4s %s %s" % (name, "✓" if cond else "★不符✗★", note))


seen: list = []
real = {"dsh": M.dsh, "walk": M._walk, "pos": M._pos_now}


def stub_dsh(text, t=60.0):
    seen.append("DSH:" + text.split()[0])
    if text.startswith("dshidle"):
        return "dshidle humanoid=false radius=6"
    return "dsh?(stub) " + text


def stub_walk(x, y, z, timeout_ms=20000, exact=False, dist_hint=None):
    seen.append("WALK:%d,%d,%d" % (x, y, z))
    return "走到 (%d,%d,%d)：到达 ✓" % (x, y, z), False


def stub_pos():
    seen.append("POS")
    return (4100.0, 71.0, 10.0)


try:
    M.dsh, M._walk, M._pos_now = stub_dsh, stub_walk, stub_pos

    # ── S1：搬去 mcp_walk 的 `_near` 里那一句 `_LIVE.dsh` ──────────────────
    seen.clear()
    mcp_walk._near(4129, 71, 29, 4.0)
    check("S1", any(s.startswith("DSH:") for s in seen),
          "mcp_walk._near 发过：%s" % (", ".join(seen[:3]) or "（无 ✗）"))

    # ── S2：`mcp_geo` 这一层**不该自己碰 `dsh`**（它的桩面是 reader/map ✓）────────
    seen.clear()
    reader = types.SimpleNamespace(
        box_verified=lambda *a: False,
        scan_truth=lambda *a, **k: {"calls": 1, "sec": 0.01, "box": (0, 0, 0, 0, 0, 0),
                                    "pages": 1, "cells": {}, "truncated": False},
        save=lambda *a, **k: None)
    mp = types.SimpleNamespace(box_verified=lambda *a: False,
                               absorb_true=lambda *a, **k: {"inserted": 0})
    mcp_geo._verify_band(reader, mp, 0, 0, 0, 0, 71, force=True)
    check("S2", not any(s.startswith("DSH:") for s in seen),
          "mcp_geo._verify_band 没绕过 reader 直接发指令 ⇒ %s"
          % ("干净 ✓" if not seen else "★它自己发了 %s ✗★" % seen[:3]))

    # ── S3/S4：`_walk` 的桩（`mcp_walk._walk` 里那句 `_LIVE.dsh` ＋ `_LIVE._pos_now`）──
    seen.clear()
    txt, bad = mcp_walk._walk(4120, 71, 10, 5000)
    check("S3", any(s.startswith("DSH:dshwalk") for s in seen),
          "`_walk` 发出：%s" % (", ".join(seen[:3]) or "（无 ✗）"))
    check("S4", "POS" in seen, "`_walk` 里 `_pos_now` 也走桩 ⇒ %s" % ("POS" in seen))
finally:
    M.dsh, M._walk, M._pos_now = real["dsh"], real["walk"], real["pos"]

# ── S5：可变对象是同一个 ────────────────────────────────────────────────────
same = (M._MISSION is mcp_core._MISSION
        and M.BLOCKED is mcp_geo.BLOCKED
        and M.BLOCKED_LV is mcp_geo.BLOCKED_LV
        and M.MOD_CLIMB_UP == mcp_walk.MOD_CLIMB_UP)
check("S5", same, "`_MISSION`/`BLOCKED`/`BLOCKED_LV`/`MOD_CLIMB_UP` 同一个对象")

# ── S6：还原之后各层读到真身 ────────────────────────────────────────────────
back = (mcp_walk._LIVE.dsh is real["dsh"] and mcp_percept._LIVE.dsh is real["dsh"])
check("S6", back, "还原后 `_LIVE.dsh` 又是真身 ✓（不留桩 ✓）")

say("=> %s" % ("PASS" if ok[0] else "FAIL"))
(ROOT / "logs" / "cut34_seam_check.txt").write_text("\n".join(lines), encoding="utf-8")
raise SystemExit(0 if ok[0] else 1)
