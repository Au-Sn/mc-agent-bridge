#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验"人设文件被换掉后，正在跑的 talk.py 会不会重新读" ✓（确定性的 ✓ 不靠等 ✓）"""
from __future__ import annotations

import sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))

import talk  # noqa: E402

cur = talk.PERSONA_DIR / "current.md"
bak = cur.read_text(encoding="utf-8") if cur.is_file() else None
lines = []
try:
    t = talk.Talk({"persona": "current"})
    lines.append("初始人设开头 = %r" % t.persona[:16])
    # 从"外面"（模拟命令行）换掉文件 ✓
    cur.write_text("你是测试用的临时人设：只会说「嗯」。\n", encoding="utf-8", newline="\n")
    t.reload_persona_if_changed()
    changed = t.persona.startswith("你是测试用的临时人设")
    lines.append("换掉之后 reload_persona_if_changed() ⇒ 变成新人设 = %s" % changed)
    lines.append("现在开头 = %r" % t.persona[:16])
    lines.append("结论 = %s" % ("✓ 当轮生效（不用重启）" if changed else "✗ 还是旧的（要重启）"))
finally:
    if bak is not None:
        cur.write_text(bak, encoding="utf-8", newline="\n")
        lines.append("已还原原人设 ✓（%d 字）" % len(bak.strip()))
Path(tempfile.gettempdir()) / "reload_out.txt".write_text("\n".join(lines), encoding="utf-8")
print("reload test done, see reload_out.txt")
