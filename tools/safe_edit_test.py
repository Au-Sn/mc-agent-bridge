#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""safe_edit_test.py -- ★"唯一锚 ＋ 看 diff"这条护栏**自己**要被判据钉住✗★（欠账 ⑧ ✓ 2026-10-02 ✓）

判据（★先写死✗★）
  S1 ★锚命中 2 次 ⇒ **必须抛** ✗ 且**一字未改**✗★
  S2 ★锚命中 1 次 ⇒ 改 ✓ 且替换**只发生一次** ✓
  S3 ★行首锚命中 2 行 ⇒ **必须抛**✗（★这正是 P175 翻车的形状 ✓★）
  S4 ★`insert_after` 命中 1 行 ⇒ 只插**一处** ✓
  S5 ★`check_diff` 期望对不上 ⇒ **必须抛**✗（★"改完看 diff"的机器版 ✓★）
  S6 ★★端到端✗★★：以上全部在**临时文件**上做 ✗ **绝不碰 `docs/`**✗（★护栏自己不许有副作用✓★）
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

import safe_edit as S  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== safe_edit_test：护栏的护栏 S1~S6 ==")
probe = ROOT / "tmp" / "_safe_edit_test_probe.txt"
probe.write_bytes("甲\n乙\n甲\n".encode("utf-8"))
before = probe.read_text(encoding="utf-8")

try:
    S.replace_unique(probe, "甲", "丙")
    check("S1", False, "★命中 2 次却没抛✗★")
except S.UnsafeEdit as e:
    check("S1", probe.read_text(encoding="utf-8") == before,
          "命中 2 次 ⇒ 抛了 ✓ 且**一字未改** ✓（%s…）" % str(e).splitlines()[0][:40])

S.replace_unique(probe, "乙", "丁")
after = probe.read_text(encoding="utf-8")
check("S2", after == "甲\n丁\n甲\n" and after.count("丁") == 1,
      "命中 1 次 ⇒ 只改一处 ✓（%r ✓）" % after.strip())

try:
    S.patch_line(probe, "甲", "戊")
    check("S3", False, "★行首锚 2 行却没抛✗★")
except S.UnsafeEdit as e:
    check("S3", True, "行首锚 2 行 ⇒ 抛了 ✓（★P175 那个形状被挡住✓★）")

probe.write_bytes("甲\n乙\n丙\n".encode("utf-8"))
S.insert_after(probe, "乙", ["插1", "插2"])
txt = probe.read_text(encoding="utf-8")
check("S4", txt == "甲\n乙\n插1\n插2\n丙\n", "只插一处 ✓（%r ✓）" % txt.replace("\n", "|"))

try:
    S.check_diff(probe, expect=(999, 999))
    check("S5", False, "★期望对不上却没抛✗★")
except S.UnsafeEdit as e:
    check("S5", True, "期望对不上 ⇒ 抛了 ✓（%s…）" % str(e).splitlines()[0][:44])

probe.unlink()
check("S6", not probe.exists(), "临时文件已清 ✓ 全程没碰 `docs/` ✓")


# ###### S7：增量不符 ⇒ **回滚**（文件一个字节都不许变）######
#   2026-10-03 检修抓到：`replace_unique` 原来**先写后检** ⇒ 不符时只喊一声，
#   而改动已经落在盘上 ⇒ 一天里六次喊停全都留下了坏行。
#   => 判据：期望不符时，文件内容必须与写之前**逐字节相同**。
_tmp7 = ROOT / "tmp" / "_s7_probe.md"
_tmp7.parent.mkdir(parents=True, exist_ok=True)
_tmp7.write_text("甲\n乙\n", encoding="utf-8")
_before7 = _tmp7.read_bytes()
try:
    S.replace_unique(_tmp7, "甲", "丙丁", expect_diff=(1, 1))       # ★实际 diff 会是 (1,1) ✗ 期望故意写错
except S.UnsafeEdit:
    pass                     # ★只吞"预期的那种"✗★：别的异常（改名/TypeError/…）必须炸出来 ✗
                             #   原来写的是 `except Exception: pass` ＋ `SE.`（没这个名字）
                             #   ⇒ 那句 NameError 被吞 ⇒ S7 一直是"什么都没测就绿" ✗（§79.401 同族）
check("S7", _tmp7.read_bytes() == _before7,
      "★期望不符 ⇒ 文件必须**没变**✗★（★回滚 ✓★）")
_tmp7.unlink(missing_ok=True)

print("=> safe_edit %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
