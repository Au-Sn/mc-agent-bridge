#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exec_task_test.py -- ★多目标执行器的离线判据（★不需要游戏✗★）（§79.423）

★做法✗★：★把 `exec3d.execute` **打桩**（monkeypatch）✗★：
　★假 `execute` 只**记录自己被调用了几次 ✗ 拿到什么 goal** ✗ 并**按剧本返回 ok／失败**✗★
★验五件✗★：
　★① `parse_goals`：★好格式解析对 ✗ 坏格式**抛错**（★不猜✗★）✗ 空串 ⇒ 空表✗★
　★② **每段都重新读位置**（★`bot_cell` 被调 N 次 ✗ 不是只调 1 次✗★）✗★
　★③ **两段全成** ⇒ `pass=2 fail=0 total=2`** ✗ 且两段都跑了✗★
　★④ **第 1 段失败 ⇒ 如实停**（★第 2 段**不许**跑 ✗ `total=1`✗★）✗★
　★⑤ ★`dry` 时**不 sleeping／不提交**（★打桩里看出 dry=True 被透传✗★）✗★ ✓
"""
from __future__ import annotations

import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import exec_task as ET          # noqa: E402
import exec3d as E3             # noqa: E402

checks = []


def main() -> int:
    # ── ① parse_goals ──
    # ★★§79.447✗★★：★`parse_goals` 现在返回「任务步」**（★不是裸坐标✗★）✗★
    g = ET.parse_goals("1,2,3;4,5,6")
    want_walk = [("walk", (1, 2, 3), None, 0), ("walk", (4, 5, 6), None, 0)]
    checks.append(("parse_goals 旧格式 ⇒ walk 步", g == want_walk, "%s" % (g,)))
    # ★容器步✗★
    g2 = ET.parse_goals("take:10,71,5:iron_ingot:8;store:10,71,5:dirt")
    checks.append(("parse_goals take 步（★带数量✗★）",
                   set(g2[0][:2]) == {"take"} or (g2[0][0] == "take" and g2[0][1] == (10, 71, 5)
                                                 and g2[0][2] == "iron_ingot" and g2[0][3] == 8),
                   "%s" % (g2[0],)))
    checks.append(("parse_goals store 步（★默认数量 1✗★）",
                   g2[1][0] == "store" and g2[1][1] == (10, 71, 5) and g2[1][2] == "dirt"
                   and g2[1][3] == 1,
                   "%s" % (g2[1],)))
    # ★坏格式当场报✗★
    bad_ok = False
    try:
        ET.parse_goals("take:10,71,5")          # ★缺 item✗★
    except ValueError:
        bad_ok = True
    checks.append(("take 步缺 item ⇒ 抛 ValueError", bad_ok, "raised=%s" % bad_ok))
    g2 = ET.parse_goals("")
    checks.append(("parse_goals 空串 ⇒ 空表", g2 == [], "%s" % (g2,)))
    raised = False
    try:
        ET.parse_goals("1,2")
    except ValueError:
        raised = True
    checks.append(("parse_goals 坏格式 ⇒ 抛 ValueError", raised, "raised=%s" % raised))

    # ── ②③④⑤ 打桩 `exec3d.execute` 和 `bot_cell` ──
    real_exec, real_bot = E3.execute, E3.bot_cell
    calls = {"bot": 0, "exec": 0, "dry_flags": [], "goals": []}

    def fake_bot():
        calls["bot"] += 1
        return (10 + calls["bot"], 71, 10)      # ★每调一次位置**不一样** ✗ 好验"重读了"✗★

    def fake_exec(goal, dry=False, max_steps=400, restore=False, pause=0.0):
        calls["exec"] += 1
        calls["dry_flags"].append(bool(dry))
        calls["goals"].append(tuple(goal))
        script = SCRIPT[calls["exec"] - 1] if calls["exec"] - 1 < len(SCRIPT) else True
        ok = bool(script)
        return ok, {"reason": None if ok else "fake_fail", "arrived": ok,
                    "end": tuple(goal), "attempts": [{"try": 1, "ok": ok}]}

    SCRIPT = [True, True]                        # ★先测"两段全成"✗★
    try:
        E3.execute, E3.bot_cell = fake_exec, fake_bot
        ok, rep = ET.run_goals([(1, 1, 1), (2, 2, 2)], dry=False)
    finally:
        E3.execute, E3.bot_cell = real_exec, real_bot
    checks.append(("两段全成 ⇒ ok=True", ok is True, "ok=%s" % (ok,)))
    checks.append(("两段全成 ⇒ pass=2 fail=0 total=2",
                   rep["pass"] == 2 and rep["fail"] == 0 and rep["total"] == 2,
                   "pass=%d fail=%d total=%d" % (rep["pass"], rep["fail"], rep["total"])))
    checks.append(("每段都重新读位置（★bot_cell 调 ≥ 段数✗★）",
                   calls["bot"] >= 2, "bot_cell 调用 %d 次" % calls["bot"]))
    checks.append(("两段的 goal 都透传对了（★顺序也对✗★）",
                   calls["goals"] == [(1, 1, 1), (2, 2, 2)], "%s" % (calls["goals"],)))

    # ── ④ 第一段失败 ⇒ 如实停 ✗ 第二段不许跑 ──
    calls.update({"bot": 0, "exec": 0, "dry_flags": [], "goals": []})
    SCRIPT[:] = [False, True]
    try:
        E3.execute, E3.bot_cell = fake_exec, fake_bot
        ok2, rep2 = ET.run_goals([(1, 1, 1), (2, 2, 2)], dry=False)
    finally:
        E3.execute, E3.bot_cell = real_exec, real_bot
    checks.append(("第 1 段失败 ⇒ **如实停**（★只跑了 1 段✗★）",
                   rep2["total"] == 1 and calls["exec"] == 1,
                   "total=%d exec 调用 %d 次" % (rep2["total"], calls["exec"])))
    checks.append(("第 1 段失败 ⇒ ok=False", ok2 is False, "ok=%s" % (ok2,)))

    # ── ⑤ dry 透传 ──
    calls.update({"bot": 0, "exec": 0, "dry_flags": [], "goals": []})
    SCRIPT[:] = [True, True]
    try:
        E3.execute, E3.bot_cell = fake_exec, fake_bot
        _ok3, _rep3 = ET.run_goals([(1, 1, 1)], dry=True)
    finally:
        E3.execute, E3.bot_cell = real_exec, real_bot
    checks.append(("dry=True 被透传给 execute", calls["dry_flags"] == [True],
                   "%s" % (calls["dry_flags"],)))

    bad = 0
    for name, ok4, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok4 else "★✗★", detail))
        if not ok4:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => exec_task ★FAIL★（%d 项不对）" % bad)
        print("EXECTASK ok=0 bad=%d" % bad)
        return 1
    print("  => exec_task PASS ✓（★每段重读位置 ✗ 失败如实停 ✗ dry 透传 ✓✗★）")
    print("EXECTASK ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
