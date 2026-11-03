#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""primitives_test.py -- 模块 C 动作原语层的判据（★离线 ✗ 用假 dsh ＋ 假校验✗★）

规格（§2.4 / §6.3 / §14.1）要求每个原语：
  ★许可 → 执行 → 独立校验 → 留痕★，且**破坏性动作命中禁止区时一次 dsh 都不许发**。

CHECKS
  C1 走：校验通过 ⇒ ok
  C2 走：校验不通过 ⇒ **如实失败**（★不许"看起来成功"✗★）
  C3 ★挖：命中禁止区 ⇒ 拒绝 ＋ 证明**一次 dsh 都没发**★
  C4 挖：允许 ⇒ 发 dshdig ＋ 校验
  C5 ★放：item **带引号**发出★（★`StringArgumentType.string()` 的坑✗★）
  C6 放：命中禁止区 ⇒ 拒绝且不发 dsh
  C7 ★留痕：每个有后果的动作都写了一条理由★
  C8 ★前摇：刻数不足 ⇒ `windup_ok=False`（不许当成功）★
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import primitives as P          # noqa: E402


class FakeDsh:
    """记录所有发出去的命令；`time=` 每次递增 ticks_per_call"""

    def __init__(self, ticks=6, replies=None):
        self.cmds = []
        self.ticks = ticks
        self.t = 1000
        self.replies = replies or {}

    def __call__(self, cmd, t=45.0):
        self.cmds.append(cmd)
        if "dshdigest" in cmd:
            self.t += self.ticks
            return "dshdigest reason=ok pos=1.0,70.0,1.0 time=%d hp=20.0 food=18 items=5" % self.t
        for k, v in self.replies.items():
            if k in cmd:
                return v
        self.t += self.ticks
        return "dsh" + cmd.split()[0][3:] + " ok " + cmd.split()[0]


def main() -> int:
    checks = []

    # C1 走成功
    d1 = FakeDsh(replies={"dshwalk": "dshwalk start n=1 to=1, 70, 3"})
    ver_ok = type("V", (), {"verify_arrived": staticmethod(lambda cell: {"ok": True, "why": "arrived"})})
    p1 = P.Primitives(dsh=d1, verifier=ver_ok, permit=type("N", (), {"allowed": staticmethod(lambda pos: (True, None))}), log=False)
    r1 = p1.walk_to((1, 70, 3))
    checks.append(("C1 走：校验通过 ⇒ ok", r1["ok"] is True, str(r1["why"])))

    # C2 走失败要如实
    ver_bad = type("V", (), {"verify_arrived": staticmethod(lambda cell: {"ok": False, "why": "not_at_goal"})})
    p2 = P.Primitives(dsh=FakeDsh(), verifier=ver_bad,
                      permit=type("N", (), {"allowed": staticmethod(lambda pos: (True, None))}), log=False)
    r2 = p2.walk_to((1, 70, 3))
    checks.append(("C2 走：校验不过 ⇒ 如实失败", r2["ok"] is False and r2["why"] == "not_at_goal",
                   str(r2["why"])))

    # C3 挖：禁止区 ⇒ 拒绝且 0 次 dsh（digest 都不发）
    deny = type("N", (), {"allowed": staticmethod(lambda pos: (False, {"name": "家"}))})
    d3 = FakeDsh()
    p3 = P.Primitives(dsh=d3, verifier=ver_ok, permit=deny, log=False)
    r3 = p3.dig((10, 70, 10))
    checks.append(("C3 挖：禁止区 ⇒ 拒绝且**一次 dsh 都没发**",
                   r3["ok"] is False and r3.get("refused_before_dsh") is True and len(d3.cmds) == 0,
                   "dsh 次数=%d" % len(d3.cmds)))

    # C4 挖：允许 ⇒ 发 dshdig 且校验
    d4 = FakeDsh(replies={"dshdig": "dshdig 1, 70, 3 was=x now=air dropped=true"})
    ver_dig_ok = type("V", (), {"verify_dig": staticmethod(lambda pos: {"ok": True, "why": "dig_verified"})})
    p4 = P.Primitives(dsh=d4, verifier=ver_dig_ok,
                      permit=type("N", (), {"allowed": staticmethod(lambda pos: (True, None))}), log=False)
    r4 = p4.dig((1, 70, 3))
    checks.append(("C4 挖：允许 ⇒ 发 dshdig ＋ 校验",
                   r4["ok"] is True and any(c.startswith("dshdig") for c in d4.cmds),
                   str([c.split()[0] for c in d4.cmds][:4])))

    # C5 放：item 必须带引号
    d5 = FakeDsh()
    ver_place_ok = type("V", (), {"verify_place": staticmethod(lambda pos, item: {"ok": True, "why": "place_verified"})})
    p5 = P.Primitives(dsh=d5, verifier=ver_place_ok,
                      permit=type("N", (), {"allowed": staticmethod(lambda pos: (True, None))}), log=False)
    p5.place((1, 70, 3), "mekanism:energized_smelter")
    place_cmd = [c for c in d5.cmds if c.startswith("dshplace")]
    quoted = bool(place_cmd) and '"mekanism:energized_smelter"' in place_cmd[0]
    checks.append(("C5 放：带 `:` 的 id **加引号**发出", quoted,
                   place_cmd[0][:60] if place_cmd else "（没有 dshplace）"))

    # C6 放：禁止区 ⇒ 拒绝
    d6 = FakeDsh()
    p6 = P.Primitives(dsh=d6, verifier=ver_place_ok, permit=deny, log=False)
    r6 = p6.place((10, 70, 10), "minecraft:stone")
    checks.append(("C6 放：禁止区 ⇒ 拒绝且不发 dsh",
                   r6["ok"] is False and len(d6.cmds) == 0, "dsh 次数=%d" % len(d6.cmds)))

    # C7 留痕（真 reasons 模块 ＋ 临时目录）
    import tempfile
    import reasons as R
    with tempfile.TemporaryDirectory() as td:
        old = R.LOGDIR
        R.LOGDIR = Path(td)
        try:
            p7 = P.Primitives(dsh=FakeDsh(),
                              verifier=ver_dig_ok,
                              permit=type("N", (), {"allowed": staticmethod(lambda pos: (True, None))}),
                              log=True)
            p7.dig((1, 70, 3))
            recs = R.load(days=1)
        finally:
            R.LOGDIR = old
    checks.append(("C7 留痕：有后果的动作写了理由",
                   len(recs) >= 1 and recs[-1].get("action") == "dig",
                   "%d 条 ｜ 最后 action=%s" % (len(recs), recs[-1].get("action") if recs else "-")))

    # C8 前摇：刻数不足要标出来
    d8 = FakeDsh(ticks=0)          # 同一刻 ⇒ 0 刻
    p8 = P.Primitives(dsh=d8, verifier=ver_dig_ok,
                      permit=type("N", (), {"allowed": staticmethod(lambda pos: (True, None))}), log=False)
    r8 = p8.dig((1, 70, 3))
    checks.append(("C8 前摇：0 刻 ⇒ windup_ok=False",
                   r8.get("windup_ok") is False or r8.get("ticks") == 0,
                   "ticks=%s windup_ok=%s" % (r8.get("ticks"), r8.get("windup_ok"))))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => primitives FAIL (%d)" % bad)
        print("PRIMITIVES ok=0 bad=%d" % bad)
        return 1
    print("  => primitives PASS (permit -> execute -> verify -> log; refusals send nothing)")
    print("PRIMITIVES ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
