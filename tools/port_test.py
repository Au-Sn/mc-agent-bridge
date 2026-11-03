#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""port_test.py -- 模块 K 第 2 级（移植）的判据（★离线 ✗ 假现场 ＋ 假原语✗★）

规格 §10.2 / §13.1：
  ★① **幂等**：已经对的格子**不放**（★省料 ✗ 不多余动作✗★）✗
  ★② **支撑优先**：自下而上 ✗ 悬空格**不硬放** ⇒ 标 `floating`✗
  ★③ **只信真值**：每格放完由 L4 校验✗★

CHECKS
  P1 算账：已对的进 ok ✗ 缺的进 need ✗ 缺料按种类计数正确
  P2 ★顺序：自下而上（dy 不增）＋ 底下没支撑的排后✗★
  P3 ★悬空格被标出 ✗ 且**不会被尝试放**★
  P4 ★幂等：已对的格子**一次都不放**（假原语计数为 0）★
  P5 放完重算 ⇒ `need_n == 0`
  P6 放失败要带 `why`（★不许静默✗★）
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

import port as P          # noqa: E402


class FakePrims:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = set(fail_at or [])

    def place(self, pos, item, mission=""):
        self.calls.append((tuple(pos), item))
        if tuple(pos) in self.fail_at:
            return {"ok": False, "why": "place_unperformable"}
        return {"ok": True, "why": None}


def main() -> int:
    checks = []
    # 一张 2×2 的板 ＋ 上面一格（悬空）＋ 一格已存在的
    cells = [
        {"dx": 0, "dy": 0, "dz": 0, "block": "minecraft:stone"},
        {"dx": 1, "dy": 0, "dz": 0, "block": "minecraft:stone"},
        {"dx": 0, "dy": 0, "dz": 1, "block": "minecraft:stone"},
        {"dx": 0, "dy": 1, "dz": 0, "block": "minecraft:glass"},
    ]
    origin = (100, 70, 100)
    live = {
        (100, 70, 100): "minecraft:stone",      # 已对
        (101, 70, 100): "minecraft:dirt",       # 要换
        (100, 70, 101): "minecraft:air",        # 要放
        # (100, 71, 100) 上面有石头 ⇒ glass 站得住
    }
    live[(100, 71, 100)] = "minecraft:air"

    pl = P.plan(cells, origin, live)
    checks.append(("P1 算账：ok=1 need=3 ✗ 缺料 stone×2",
                   pl["ok_n"] == 1 and pl["need_n"] == 3
                   and pl["missing"].get("minecraft:stone") == 2,
                   "ok=%d need=%d missing=%s"
                   % (pl["ok_n"], pl["need_n"], pl["missing"])))

    # P2 顺序
    ord2 = P.order(pl["need"], live, origin)
    dys = [int(c["dy"]) for c in ord2]
    checks.append(("P2 ★顺序自下而上★（dy 不增）",
                   dys == sorted(dys), str(dys)))

    # P3 悬空：造一个真正悬空的（四周和下面都是空气）
    cells3 = [{"dx": 0, "dy": 5, "dz": 0, "block": "minecraft:glass"}]
    pl3 = P.plan(cells3, (0, 100, 0), {})
    fp = FakePrims()
    P.execute(pl3, fp, origin=(0, 100, 0), live={})
    checks.append(("P3 ★悬空格被标出 ✗ 且不尝试放★",
                   len(pl3["floating"]) == 1 and fp.calls == [],
                   "floating=%d 放了几次=%d" % (len(pl3["floating"]), len(fp.calls))))

    # P4 幂等：已对的格子不放
    fp4 = FakePrims()
    r4 = P.execute(pl, fp4, origin=origin, live=live)
    tried_pos = [c[0] for c in fp4.calls]
    checks.append(("P4 ★幂等：已对的格一次都不放★",
                   (100, 70, 100) not in tried_pos,
                   "放了 %d 次 ｜ 位置 %s" % (len(tried_pos), tried_pos[:4])))

    # P5 放完重算为 0
    live5 = dict(live)
    for row in r4["placed"]:
        live5[tuple(row["pos"])] = row["block"]
    pl5 = P.plan(cells, origin, live5)
    checks.append(("P5 放完重算 ⇒ need_n == 0", pl5["need_n"] == 0,
                   "need=%d" % pl5["need_n"]))

    # P6 失败带 why
    fp6 = FakePrims(fail_at=[(101, 70, 100)])
    r6 = P.execute(pl, fp6, origin=origin, live=live)
    checks.append(("P6 放失败带 why",
                   r6["failed_n"] >= 1 and r6["failed"][0].get("why") == "place_unperformable",
                   "%s" % (r6["failed"][:1],)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => port FAIL (%d)" % bad)
        print("PORT ok=0 bad=%d" % bad)
        return 1
    print("  => port PASS (idempotent, bottom-up, floating cells never attempted)")
    print("PORT ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
