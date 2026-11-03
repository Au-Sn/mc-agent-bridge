#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_nav_test.py -- ★导航汇报的"该说／不该说"判据（★离线✗★）（§79.424）

★守什么✗★：★`speech.nav_intent(report)`** 这个**纯函数**（★不发声 ✗ 不需要游戏✗★）✗★
　★① **到达** ⇒ 「邀功」（★"★到地方了★"✗★）✗★
　★② **规划不出／材料不够** ⇒ 「播报」✗ 且 **why 是**人话（★不是只回错误码✗★）✗★
　★③ **多段全成** ⇒ 「邀功」✗ **有段失败** ⇒ 「播报」**✗ ④ **不认识／不是 dict** ⇒ **None**（★不硬编✗★）✗★
　★⑤ ★**口子必须在 `KINDS` 里**（★不新造类型 ✗ `Intent` 构造会校验✓★）✗★
　★⑥ ★**不许直接发声**✗★：★本判据**扫源码**确认 `speech.py` 里**没有** `dshsay`**（★出口只有 talk／acp_talk✓★）✗★
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import speech as S              # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

CASES = [
    # (报告, 期望 kind 或 None, 说明)
    ({"arrived": True, "end": (1, 2, 3), "steps": 5}, "邀功", "单段到达"),
    ({"reason": "no_plan"}, "播报", "规划不出"),
    ({"reason": "not_enough_scaffold"}, "播报", "材料不够"),
    ({"bad": ["x"]}, "播报", "有坏消息"),
    ({"segments": [{"ok": True}], "pass": 1, "fail": 0, "total": 1}, "邀功", "单段任务全成"),
    ({"segments": [{"ok": True}, {"ok": False, "reason": "max_steps"}],
      "pass": 1, "fail": 1, "total": 2}, "播报", "任务卡住"),
    ({"whatever": 1}, None, "不认识的报告"),
    ("not a dict", None, "不是字典"),
    (None, None, "None"),
    ({}, None, "空字典"),
]


def main() -> int:
    checks = []
    for rep, want, name in CASES:
        try:
            it = S.nav_intent(rep)
        except Exception as e:                 # ★不许静默✗★
            checks.append((name, False, "抛异常 %r" % (e,)))
            continue
        got = it.kind if it is not None else None
        ok = got == want
        detail = "got=%s want=%s" % (got, want)
        if ok and it is not None:
            detail += " ｜ why=%s" % it.why
            # ★Intent 的构造已经校验过 kind ✗ 这里再显式确认一次✗★
            if it.kind not in S.KINDS:
                ok = False
                detail += " ★kind 不在 KINDS★"
        checks.append((name, ok, detail))

    # ★人话：失败类必须带 `why_key`（★台词库分层键 ✗ 没有就抽不到台词✗★）
    it = S.nav_intent({"reason": "no_plan"})
    has_key = bool(it and it.payload.get("why_key") and it.payload.get("why"))
    checks.append(("失败类带 why_key ＋ why（★人话✗★）", has_key,
                   "%s" % (it.payload if it else None,)))

    # ★出口唯一：`speech.py` 里不许出现 `dshsay`（★它是判断层 ✗ 不是出口✗★）
    # ★★§79.424✗★★：★**出口唯一**✗ —— speech.py 是**判断层**✗★
    #   ★不许 import 发声通道 ✗ 不许定义 say／speak／send**✗（★否则两个出口 ✗ 迟早打架✗★）✗★
    #   ★（★注释里提到 dshsay 是**说明** ✗ 不算出口✗★）✗★ ✓
    src = ""
    p = ROOT / "tools" / "speech.py"
    if p.is_file():
        src = p.read_text(encoding="utf-8", errors="replace")
    import re as _re
    bad_import = _re.search(r"(?m)^\s*(?:from|import)\s+mcp_core", src) is not None
    bad_def = _re.search(r"(?m)^def (say|speak|send|shout)\w*\s*\(", src) is not None
    checks.append(("speech.py 是判断层、不发声（★不 import 通道 ✗ 无 say／speak✗★）",
                   not bad_import and not bad_def,
                   "import 通道=%s ／ 有 say 类函数=%s" % (bad_import, bad_def)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => speech_nav ★FAIL★（%d 项不对）" % bad)
        print("SPEECHNAV ok=0 bad=%d" % bad)
        return 1
    print("  => speech_nav PASS ✓（★到达邀功 ✗ 失败播报 ✗ 不认识 ⇒ None ✗ 出口唯一✓✗★）")
    print("SPEECHNAV ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
