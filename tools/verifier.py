#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verifier.py -- 模块 L4 独立校验官：**只信世界真值，不信执行者自述**

规格（§14.1 / §14.4）核心原则：
  「**写世界的只有一个 ✗ 验世界的独立于它 ✗ 设计的在动手之前**」
  判据 L-g：★执行官写的每个动作都被校验官独立核过（覆盖率 100%）★
  判据 L-h：★校验官红过之后 ⇒ 执行官不许继续★

本模块的**唯一数据来源**是重新读世界（`dshscan`/`dshdigest`），
★任何接受"执行者说它成了"的参数都是设计错误**✗★
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★校验路径的**事件记录口**（模块 H 接线）✗★：
#   ★默认 None ⇒ 没有任何副作用**（既有判据/单测一个字节都不变✓★）✗★；
#   ★主流程（`primitives.Primitives(log=True)`）注册记录器 ⇒ 每次校验都留事件✗★。
#   ★记录器由**调用方**给 ✗ 校验官自己不许决定"记到哪"✗★。
_RECORDER = None


def set_recorder(fn) -> None:
    """注册校验事件记录器：`fn(kind, verdict, pos)`；`fn=None` ⇒ 关掉（★无副作用✗★）"""
    global _RECORDER
    _RECORDER = fn if callable(fn) else None


def _rec(kind: str, verdict: dict, pos=None) -> None:
    if _RECORDER is None:
        return
    try:
        _RECORDER(kind, dict(verdict), pos)
    except Exception as exc:                  # ★不许静默✗★（也不许把校验带崩）
        print("verifier: 事件记录失败 %r" % (exc,), file=sys.stderr)


def _truth_cell(pos, timeout=40.0) -> str:
    """★重新读世界真值✗★ ⇒ 该格的 `name[props]`，空气回 ""✗★"""
    import mcp_core as C
    x, y, z = (int(v) for v in pos)
    txt = (C.dsh('dshscan %d %d %d %d %d %d ":" 8 1' % (x, y, z, x, y, z), timeout) or "")
    m = re.search(r"cells\[([^\]]*)\]", txt)
    inner = (m.group(1).strip() if m else "")
    if not inner:
        if "solid=0" in txt:
            return ""
        return "★读不到★"
    # `x,y,z:name,props`
    after = inner.split(":", 1)[1] if ":" in inner else inner
    return after


def _truth_bot() -> dict:
    import mcp_core as C
    d = (C.dsh("dshdigest", 30.0) or "").strip()
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", d)
    if not m:
        return {}
    import math
    y = float(m.group(2))
    return {"pos": (float(m.group(1)), y, float(m.group(3))),
            "feet": max(1, math.ceil(y - 1e-9))}


def verify_dig(pos, expect_air=True, read=None) -> dict:
    """★校验"挖"：世界真值现在必须是空气✗★"""
    read = read or _truth_cell
    now = read(pos)
    if now == "★读不到★":
        verdict = {"ok": False, "why": "verify_unreadable", "now": now, "pos": list(pos)}
        _rec("verify_dig", verdict, pos)
        return verdict
    is_air = (now == "" or now.lower().startswith("minecraft:air"))
    ok = (is_air == bool(expect_air))
    verdict = {"ok": ok, "why": "dig_verified" if ok else "dig_not_done",
               "now": now[:60], "pos": list(pos)}
    _rec("verify_dig", verdict, pos)
    return verdict


def verify_place(pos, expect_id: str, read=None) -> dict:
    """★校验"放"：世界真值现在必须是那个方块✗★"""
    read = read or _truth_cell
    now = read(pos)
    if now == "★读不到★":
        verdict = {"ok": False, "why": "verify_unreadable", "now": now, "pos": list(pos)}
        _rec("verify_place", verdict, pos)
        return verdict
    ok = now.split(",", 1)[0].strip() == (expect_id or "").strip()
    verdict = {"ok": ok, "why": "place_verified" if ok else "place_mismatch",
               "now": now[:60], "want": expect_id, "pos": list(pos)}
    _rec("verify_place", verdict, pos)
    return verdict


def verify_arrived(goal, tol=0.9, bot=None) -> dict:
    """★校验"到达"：脚格必须就是目标格（★"★近★"不等于"★到★"✗★）✗★"""
    b = bot or _truth_bot()
    if not b:
        verdict = {"ok": False, "why": "no_bot"}
        _rec("verify_arrived", verdict, goal)
        return verdict
    feet = (int(round(b["pos"][0])), int(b["feet"]), int(round(b["pos"][2])))
    # 用脚格判定（★不是浮点距离✗★）
    ok = tuple(int(v) for v in goal) == feet
    verdict = {"ok": ok, "why": "arrived" if ok else "not_at_goal",
               "feet": list(feet), "goal": [int(v) for v in goal],
               "pos": [round(v, 2) for v in b["pos"]]}
    _rec("verify_arrived", verdict, goal)
    return verdict


def verify(action: str, **kw) -> dict:
    """统一入口：`action` ∈ {dig, place, arrived}"""
    a = (action or "").strip().lower()
    if a == "dig":
        return verify_dig(kw.get("pos"), expect_air=kw.get("expect_air", True),
                          read=kw.get("read"))
    if a == "place":
        return verify_place(kw.get("pos"), kw.get("expect_id", ""), read=kw.get("read"))
    if a == "arrived":
        return verify_arrived(kw.get("goal"), tol=kw.get("tol", 0.9), bot=kw.get("bot"))
    return {"ok": False, "why": "unknown_action", "action": action}


def main(argv) -> int:
    if argv and argv[0] == "dig":
        pos = tuple(int(v) for v in argv[1].split(","))
        print(verify_dig(pos))
        return 0
    if argv and argv[0] == "place":
        pos = tuple(int(v) for v in argv[1].split(","))
        print(verify_place(pos, argv[2] if len(argv) > 2 else ""))
        return 0
    if argv and argv[0] == "arrived":
        goal = tuple(int(v) for v in argv[1].split(","))
        print(verify_arrived(goal))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
