#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""leash_test.py -- ★"安全壳"自己要被判据钉住✗★（P177 ✓ 2026-10-02 ✓）

判据（★先写死✗★）
  L1 ★撞围栏就停✗★：位移超过 `max_drift` ⇒ `why` 里必须是 `fence` ✓ 且**停过**✓
  L2 ★到点就停✗★：时长到 ⇒ `why=duration` ✓ 且**停过**✓
  L3 ★★读不到就停✗★★：连续 `max_read_fail` 次采样返回 None ⇒ 必须停
     （★今天翻车**就是这一步**：读不到 ⇒ 假人继续跑 ⇒ 冲下平台 ✓★）
  L4 ★★body 抛异常也要停✗★★：★这是**最要紧**的一条 ✗ 因为今天正是"脚本崩了没人 stop"✗★
  L5 ★一开始就读不到 ⇒ **一个输入都不发**✗★（★连 start 都不调✓★）
  L6 ★回执必须写**为什么停**✗★（★`why` 不许空 ✗ 不许只写"停了"✓★）
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

import leash as L  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def mk(samples, sleep_raises=False):
    sent = []

    def send(c):
        sent.append(c)

    def sleep(_s):
        if sleep_raises:
            raise RuntimeError("boom")
    it = iter(samples)

    def sample():
        try:
            v = next(it)
        except StopIteration:
            return None
        if v == "RAISE":
            raise RuntimeError("sample boom")
        return v

    return sent, send, sample, sleep


print("== leash_test：安全壳 L1~L6 ==")
sent, send, sample, sleep = mk([(1, 71, 0), (2, 71, 0), (5, 71, 0), (9, 71, 0)])
r = L.run_leashed(send, sample, lambda: None, duration_s=10, max_drift=3, sleep=sleep)
check("L1", "fence" in r.why and sent, "撞围栏 ⇒ why 含 fence ✓ 且停过（stops=%d ✓）" % len(sent))

# ★L2 的坑✗★：★第一版给 `sleep=lambda s: None`（空睡 ✗）⇒ ★40 次采样在微秒内跑完 ✗
#   `time.time()` 那一步**永远追不上** ⇒ 判词变成 `read-fail` ✗（★是**我的装置**错了 ✗ 不是壳错了✓★）
# ⇒ ★改成真睡一点点 ✗ 时长才可能触发✓★
sent, send, sample, sleep = mk([(0, 71, 0)] * 40)
r = L.run_leashed(send, sample, lambda: None, duration_s=0.05, max_drift=99,
                  tick=0.01, sleep=__import__("time").sleep)
check("L2", r.why == "duration" and sent, "到点 ⇒ why=duration ✓ 且停过 ✓（%s）" % r.line())

sent, send, sample, sleep = mk([(0, 71, 0), None, None, None, None])
r = L.run_leashed(send, sample, lambda: None, duration_s=10, max_drift=99,
                  tick=0.01, max_read_fail=3, sleep=lambda s: None)
check("L3", "read-fail" in r.why and sent, "★读不到 ⇒ 停✗★（why=%s…）" % r.why[:34])

sent, send, sample, sleep = mk([(0, 71, 0), (1, 71, 0), (2, 71, 0), (3, 71, 0)], sleep_raises=True)
r = L.run_leashed(send, sample, lambda: None, duration_s=10, max_drift=99, sleep=sleep)
check("L4", sent and "body-raised" in r.why, "★body 抛异常 ⇒ 仍然 stop✗★（stops=%d ✓ why=%s…）"
      % (len(sent), r.why[:30]))

sent, send, sample, sleep = mk([])
called = {"start": 0}
r = L.run_leashed(send, sample, lambda: called.__setitem__("start", 1), duration_s=5,
                  max_drift=9, sleep=lambda s: None)
check("L5", called["start"] == 0 and sent and "start-unreadable" in r.why,
      "★一开始读不到 ⇒ **一个输入都不发**✗★（start 调了 %d 次 ✓ 且仍发了 stop ✓）" % called["start"])

check("L6", all(r.why for r in [L.LeashReport()]) is False and "why=" in L.LeashReport(why="x").line(),
      "回执里必有 `why=` ✓（%s ✓）" % L.LeashReport(why="duration", moved=1.2).line())

# ★★L7/L8：★把围栏**交给模组**✗★（欠账 ⑰ ✓ 2026-10-03 ✓ 离线 ✓）：
#   ★口径✗★：★回执里**没有** `dshleash armed` ⇒ 就算**没装上**✗（★不许"大概装上了"✓★）
_sent = []


def _fake_send(cmd):
    _sent.append(cmd)
    return ("dshleash armed max_drift=1.50 seconds=3 from=4118.50,9.40 "
            "(it stops inputs IN-TICK on breach)")


_ok7, _out7 = L.arm_mod_leash(_fake_send, 1.5, 3)
check("L7", _ok7 and _sent and _sent[0] == "dshleash 1.50 3",
      "★发的是 `%s` ✗ 且回执含 `armed` ⇒ 算装上✗★ ✓" % (_sent[0] if _sent else "-"))

_ok8, _out8 = L.arm_mod_leash(lambda c: "0", 1.5, 3)
check("L8", (not _ok8) and "0" in _out8,
      "★回执里没有 `armed` ⇒ 判**没装上**✗★（★不静默 ✗ 不冒充✓★）")

print("=> leash %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
