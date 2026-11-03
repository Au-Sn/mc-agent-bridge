#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""damage_policy_test.py -- 伤害来源 → 对策 的判据（★用户口径✗★）

用户原话：「N7 应该**明确伤害来源**，根据伤害来源给到**不同对策**，
比如**有怪就打或跑**，**窒息就上浮**，**卡墙就传送出来**，**饿掉血就找食物**」

CHECKS
  D1 有怪 ⇒ fight_or_flee（★打或跑★）
  D2 窒息 ⇒ surface（★上浮★）
  D3 卡墙 ⇒ unstick（★挪出去★）
  D4 饿 ⇒ eat（★找食物★）
  D5 岩浆/火 ⇒ escape_hazard
  D6 摔 ⇒ step_back
  D7 ★未知来源不许静默★ ⇒ known=False ＋ 保守回安全点
  D8 ★不同来源给不同对策★（抽查：四种关键来源的对策两两不同）
  D9 别名/大小写/空格归一（"In Wall" ⇒ in_wall）
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

import damage_policy as DP          # noqa: E402


def main() -> int:
    checks = []

    a = DP.advise("mob")
    checks.append(("D1 有怪 ⇒ 打或跑", a["action"] == "fight_or_flee" and a["known"],
                   a["action"]))
    a = DP.advise("drown")
    checks.append(("D2 窒息 ⇒ 上浮", a["action"] == "surface" and a["known"],
                   a["action"]))
    a = DP.advise("in_wall")
    checks.append(("D3 卡墙 ⇒ 挪出去", a["action"] == "unstick" and a["known"],
                   a["action"]))
    a = DP.advise("starve")
    checks.append(("D4 饿 ⇒ 找食物", a["action"] == "eat" and a["known"],
                   a["action"]))
    a, b = DP.advise("lava"), DP.advise("fire")
    checks.append(("D5 岩浆/火 ⇒ escape_hazard",
                   a["action"] == b["action"] == "escape_hazard", a["action"]))
    a = DP.advise("fall")
    checks.append(("D6 摔 ⇒ step_back", a["action"] == "step_back", a["action"]))

    unk = DP.advise("some_weird_new_source")
    checks.append(("D7 未知来源不静默（known=False ＋ 保守）",
                   unk["known"] is False and unk["action"] == "retreat_safe",
                   "known=%s action=%s" % (unk["known"], unk["action"])))

    four = [DP.advise(s)["action"] for s in ("mob", "drown", "in_wall", "starve")]
    checks.append(("D8 不同来源给不同对策（四种两两不同）",
                   len(set(four)) == 4, str(four)))

    alias = DP.advise("In Wall")
    checks.append(("D9 别名归一（In Wall ⇒ in_wall）",
                   alias["src"] == "in_wall" and alias["action"] == "unstick",
                   "%s ⇒ %s" % (alias["src"], alias["action"])))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:100]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => damage_policy FAIL (%d)" % bad)
        print("DAMAGEPOL ok=0 bad=%d" % bad)
        return 1
    print("  => damage_policy PASS (source -> distinct countermeasure; unknown is never silent)")
    print("DAMAGEPOL ok=1 checks=%d sources=%d" % (len(checks), len(DP.POLICY)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
