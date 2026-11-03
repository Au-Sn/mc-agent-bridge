#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""model_fetch_guard_test.py -- the world model must fail fast, and never fetch while planning

BUG THIS GUARDS (sec 79.472, measured):
  World3D.get() -> _ensure() -> fetch_region() for EVERY unknown cell, with a 150 s
  timeout each. With a dead link, plan() looked hung: no return in 600 s and
  faulthandler never fired (blocked in I/O). The model also mutated DURING planning,
  so results depended on fetch order.

CHECKS (offline, a fake dsh that always fails):
  M1 fetch_region reports failure and increments the breaker counter
  M2 after max_fail consecutive failures, _ensure stops calling dsh at all (no more 150 s waits)
  M3 freeze() makes get() return UNKNOWN without any fetch
  M4 a successful fetch resets the breaker
  M5 plan() on a dead world RETURNS (no path) quickly instead of hanging
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import plan3d as P3           # noqa: E402
import world3d as W3          # noqa: E402


class DeadLink:
    """dsh replacement: always fails, counts calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self, cmd, timeout=None):
        self.calls += 1
        return ""


class GoodLink:
    """dsh replacement: one valid single-cell answer, counts calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self, cmd, timeout=None):
        self.calls += 1
        # minimal valid dshscan reply: one page, one solid cell
        return ("dshscan box=0,0,0..0,0,0 tick=1 hash=1 vol=1 solid=1 air=0 kinds=1 "
                "matched=1 shown=1 page=1/1 us=1 counts[x:1] cells[0,0,0:x]")


def main() -> int:
    checks = []

    # M1 + M2: dead link -> failures counted, then breaker stops fetching
    d = DeadLink()
    w = W3.World3D(dsh=d)
    r = w.fetch_region((0, 0, 0, 1, 2, 1))
    checks.append(("M1 失败被抓到并计数", (r is False) and w.fetch_fail >= 1,
                   "ret=%s fail=%d" % (r, w.fetch_fail)))
    for _ in range(6):
        w.get(999, 70, 999)
    checks.append(("M2 熔断后不再发起抓取", w.fetch_fail >= w.max_fail,
                   "fail=%d max=%d calls=%d" % (w.fetch_fail, w.max_fail, d.calls)))
    before = d.calls
    w.get(12345, 70, 12345)
    checks.append(("M2b 熔断后 get 不再调 dsh", d.calls == before,
                   "calls %d -> %d" % (before, d.calls)))

    # M3: freeze
    d2 = DeadLink()
    w2 = W3.World3D(dsh=d2)
    w2.freeze()
    v = w2.get(7, 70, 7)
    checks.append(("M3 冻结时 get 直接回未知且不抓",
                   (v is W3.UNKNOWN or v is None) and d2.calls == 0,
                   "v=%r calls=%d" % (v, d2.calls)))

    # M4: success resets
    d3 = GoodLink()
    w3 = W3.World3D(dsh=d3)
    w3.fetch_fail = 2
    w3.fetch_region((0, 0, 0, 0, 0, 0))
    checks.append(("M4 成功一次就清零熔断", w3.fetch_fail == 0, "fail=%d" % w3.fetch_fail))

    # M5: plan on a dead world must return quickly
    d4 = DeadLink()
    w4 = W3.World3D(dsh=d4)
    t0 = time.time()
    try:
        path, acts, cost = P3.plan(w4, (0, 70, 0), (5, 70, 5), scaffold=0)
        dt = time.time() - t0
        ok5 = (not path) and dt < 20.0
        detail = "steps=%s %.1fs dsh_calls=%d" % (len(path) if path else None, dt, d4.calls)
    except Exception as e:
        dt = time.time() - t0
        ok5 = dt < 20.0
        detail = "raised %r after %.1fs" % (e, dt)
    checks.append(("M5 掉线时 plan 快速返回（不卡死）", ok5, detail))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => model_fetch_guard FAIL (%d)" % bad)
        print("MODELGUARD ok=0 bad=%d" % bad)
        return 1
    print("  => model_fetch_guard PASS (fail fast, breaker, freeze all hold)")
    print("MODELGUARD ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
