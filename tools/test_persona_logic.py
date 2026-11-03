#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单元自测：人设输入口 ＋ 指令判定 ✓（不进游戏 ✓ 不起 harness ✓ 纯逻辑 ✓）

为什么要有这一层 ✗（P45 的教训 ✓）：判定逻辑**必须写成代码来验** ✗
别用眼睛看两条例子就说"应该行" ✓
"""
from __future__ import annotations

import tempfile

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))

import talk  # noqa: E402

CASES_PERSONA = [
    ("!人设 你是个话很少的老矿工，只说短句。", "你是个话很少的老矿工，只说短句。"),
    ("!设定：你叫铁蛋，脾气爆。", "你叫铁蛋，脾气爆。"),
    ("bot,你的设定是：你是这座岛上的管家，说话客气。", "你是这座岛上的管家，说话客气。"),
    ("记住你是只猫，只会喵。", "只猫，只会喵。"),
    ("人设：沉默寡言的伐木工", "沉默寡言的伐木工"),
    ("你在干嘛？", None),
    ("bot，说一下你包里有什么", None),
    ("帮我搞点沙砾", None),
]

CASES_IMPERATIVE = [
    ("bot,搞点沙砾", True),
    ("帮我砍那棵树", True),
    ("过来我这边", True),
    ("把这个方块挖了", True),
    ("你去筛一下", True),
    ("你在干嘛？", False),
    ("你手里是什么？", False),
    ("你去过下界吗", False),
    ("在吗", False),
    ("你会筛矿吗", False),
    ("今天天气不错", False),
    ("能不能帮我搞点沙砾吗", True),
    ("你会走路吗", False),
    ("帮我看看筛子里有啥", True),
]

fails = []
lines = []
for msg, want in CASES_PERSONA:
    got = talk.parse_persona_set(msg)
    ok = (got == want) if want is not None else (got is None)
    lines.append("%s  parse_persona_set(%r) = %r  (want %r)" % ("ok  " if ok else "FAIL", msg, got, want))
    if not ok:
        fails.append(msg)

for msg, want in CASES_IMPERATIVE:
    got = talk.looks_imperative(msg)
    ok = (got == want)
    lines.append("%s  looks_imperative(%r) = %s  (want %s)" % ("ok  " if ok else "FAIL", msg, got, want))
    if not ok:
        fails.append(msg)

lines.append("")
# ── ★诚实兜底 ＋ 硬前缀★ ✓（2026-09-20 新增 ✓）─────────────────────────────
cases_hr = [
    ("我去弄好了", True, 0, "（我还没真动手 ✗）我去弄好了"),
    ("", True, 0, "（我还没真动手 ✗）没做成。"),
    ("到了", True, 3, "到了"),
    ("在呢", False, 0, "在呢"),
]
for text, force, tools, want in cases_hr:
    got = talk.honest_reply(text, force, tools)
    ok = (got == want)
    lines.append("%s  honest_reply(%r, %s, %s) = %r  (want %r)"
                 % ("ok  " if ok else "FAIL", text, force, tools, got, want))
    if not ok:
        fails.append("honest_reply:%s" % text)

cases_hp = [
    ("!do 走过去", ("走过去", True)),
    ("!执行 挖矿", ("挖矿", True)),
    ("! go now", ("now", True)),
    ("bot,过来", ("bot,过来", False)),
    ("", ("", False)),
]
for msg, want in cases_hp:
    got = talk.strip_hard_prefix(msg)
    ok = (got == want)
    lines.append("%s  strip_hard_prefix(%r) = %r  (want %r)" % ("ok  " if ok else "FAIL", msg, got, want))
    if not ok:
        fails.append("strip_hard_prefix:%s" % msg)

lines.append("")
lines.append("FAILS=%d" % len(fails))
Path(tempfile.gettempdir()) / "unit_out.txt".write_text("\n".join(lines), encoding="utf-8")
# ★控制台只打 ASCII★ ✗（P39/P47 ✓ 别让一行 print 毁掉退出码 ✓）
print("unit tests: %d cases, %d FAIL"
      % (len(CASES_PERSONA) + len(CASES_IMPERATIVE) + len(cases_hr) + len(cases_hp), len(fails)))
raise SystemExit(1 if fails else 0)
