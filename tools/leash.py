#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""leash.py -- ★★"持续输入"实验的**安全壳**✗★★（P177 的系统解 ✓ 2026-10-02 ✓）

WHY ✓（★代价：2026-10-02 我用 `sprint` ＋ `move forward` 判 `jump_run` ✗
把假人**冲下平台** ✗ 而 Lua 注释早就写着"天空岛一步踏空＝掉进虚空"✗★）：
  ★同族错还有✗★：★脚本**崩在读取那一步** ✗ 于是**没人发 stop** ✗★
  ⇒ ★这个壳把三件事变成**默认**✗★（★不是"记得做" ✓ 而是"不这么做就跑不起来"✓★）：
  ① ★**时长上限**✗★（到点无条件停 ✓）② ★**围栏**✗★（水平位移超过 `max_drift` 立刻停 ✓）
  ③ ★**`finally` 无条件停**✗★（★哪怕 body 抛异常 ✗ 哪怕采样读不到 ✗ 也停 ✓★）
  ＋ ④ ★**采样读不到也算"必须停"的信号**✗★（★这正是今天翻车的那一步✓★）
  ＋ ⑤ ★回执里必须写**为什么停**✗（`why=` ✓ 不许只说"停了"✓★）
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass
class LeashReport:
    ok: bool = False
    why: str = ""
    moved: float = 0.0
    peak_y: Optional[float] = None
    samples: int = 0
    read_fail: int = 0
    stops: list = field(default_factory=list)

    def line(self):
        return ("leash why=%s moved=%.2f samples=%d read_fail=%d stops=%d"
                % (self.why, self.moved, self.samples, self.read_fail, len(self.stops)))


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def arm_mod_leash(send, max_drift=1.5, seconds=3):
    """★★把围栏**交给模组**✗★★（欠账 ⑰ ✓ 2026-10-03 ✓ 中间层这一侧的接线 ✓）

    ★为什么要有它✗★：★§79.27 实测 ✗ 中间层**一次采样 ≈ 1 秒**✗ 这期间 `move forward`
      能走 **5~7 格** ⇒ ★它只能**事后拦**✗★ ⇒ ★围栏下沉到模组（★每 tick✓★）✗
      中间层这一侧就只剩两件✗★：★① **发约束**✗ ② **读结果**✗★ ✓

    ★判据（★不许静默✓★）★：★回执里**必须**出现 `dshleash armed`✗★ ——
      ★没有就当作"**没装上**"✗（★而不是"大概装上了" ✓ P164 家族✓★）
    """
    cmd = "dshleash %.2f %d" % (float(max_drift), int(seconds))
    try:
        out = str(send(cmd) or "")
    except Exception as e:
        return False, "ERR:%s: %s" % (type(e).__name__, e)
    return ("dshleash armed" in out), out.strip()


def mod_leash_status(send):
    """★读模组侧的约束状态✗★（★`on/max_drift/left_ms/moved/ticks/stops`✓★）"""
    try:
        return str(send("dshleash status") or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def run_leashed(send: Callable[[str], object],
                sample: Callable[[], Optional[tuple]],
                start: Callable[[], object],
                stop_cmds=("stop",),
                duration_s: float = 3.0,
                max_drift: float = 3.0,
                tick: float = 0.12,
                max_read_fail: int = 3,
                sleep: Callable[[float], None] = time.sleep) -> LeashReport:
    """★跑一段"持续输入" ✗ 但**永远**在时长/围栏/读不到/异常这四种情况下停✗★

    ★口径✗★：★`stop` 在 `finally` 里发 ✗ 且**每一条** stop 都记进 `stops`✗★
      （★"我发过 stop"要**有据可查** ✗ 参见 P164/P172 ✓★）
    """
    rep = LeashReport()
    p0 = None
    try:
        p0 = sample()
    except Exception:
        p0 = None
    if p0 is None:
        rep.why = "★start-unreadable✗★（★一开始就读不到位置 ⇒ **一个输入都不发**✗ ✓）"
        for c in stop_cmds:
            try:
                send(c)
                rep.stops.append(c)
            except Exception as e:
                # 记录：停机命令没发出去 ⇒ 安全壳的"必停"承诺没兑现（不许静默）
                print("[记录] 停机命令没发出去 %s（%s）⇒ 假人可能还在动"
                      % (c, type(e).__name__), file=sys.stderr)
        return rep

    rep.peak_y = p0[1]
    t0 = time.time()
    try:
        start()
        while True:
            sleep(tick)
            if time.time() - t0 >= duration_s:
                rep.why = "duration"
                rep.ok = True
                break
            try:
                s = sample()
            except Exception:
                s = None
            if s is None:
                rep.read_fail += 1
                if rep.read_fail >= max_read_fail:
                    rep.why = "★read-fail✗★（★连续 %d 次读不到 ⇒ 停✗ —— 今天就是栽在这一步✓★）" % rep.read_fail
                    break
                continue
            rep.samples += 1
            if s[1] > (rep.peak_y or s[1]):
                rep.peak_y = s[1]
            d = _dist(p0, s)
            if d > rep.moved:
                rep.moved = d
            if d > max_drift:
                rep.why = "★fence✗★（★位移 %.2f > 围栏 %.2f ⇒ 停✗★）" % (d, max_drift)
                break
    except Exception as e:
        rep.why = "★body-raised✗★（%s: %s ⇒ ★仍然会 stop✗★）" % (type(e).__name__, e)
    finally:
        for c in stop_cmds:
            try:
                send(c)
                rep.stops.append(c)
            except Exception as e:
                # 记录：停机命令没发出去 ⇒ 安全壳的"必停"承诺没兑现（不许静默）
                print("[记录] 停机命令没发出去 %s（%s）⇒ 假人可能还在动"
                      % (c, type(e).__name__), file=sys.stderr)
    if not rep.why:
        rep.why = "ended"
    return rep


if __name__ == "__main__":
    print("★leash 自检✗★（★用**假** send/sample ✗ 不碰世界✓★）")
    sent = []

    def fake_send(c):
        sent.append(c)

    box = {"x": 0.0}

    def drift_sample():
        box["x"] += 1.0                      # ★每 tick 漂 1 格 ⇒ 应在第 4 次撞围栏✓★
        return (box["x"], 71.0, 0.0)

    r = run_leashed(fake_send, drift_sample, lambda: None, duration_s=10.0, max_drift=3.0,
                    sleep=lambda s: None)
    print("  ① 围栏：%s" % r.line())
    print("     stops=%s" % (sent,))
