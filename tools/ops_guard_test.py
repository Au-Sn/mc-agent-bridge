#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ops_guard_test.py -- ★「改世界必须够得着 ✗ 或显式声明是运维」★（O1~O4 ✓ 离线 ✓ 2026-10-03）

★为什么有它✗★（欠账 ㊱）：`raw` 通道能直接发 `/setblock` 这类**改世界**的指令，
  而代码里**没有一处**会因为「够不着却改了世界」而报错 —— 那条「我不做」只是**人的判断**。
  来历：㉘ 那颗洞我**能**隔空补 ✗ 但那样会把「**类玩家行为**」这条底线变假 ⇒ 于是要一道守卫。

★判据（先写死）★
  O1 ★分类✗★：`setblock`／`fill` ⇒ **改世界** ；`data get` ⇒ 不是 ；★`/dsh…` 一律**不是**★
     （★模组动作走的是 reach ✓ 那正是"玩家行为"那条路✓★）
  O2 ★没声明 ⇒ **一个字都不许发出去**✗★（★用假通道数它到底发了几条 ✓ 并且退出码 3✓★）
  O3 ★声明了 ⇒ 发 ✓ 而且**留痕**✗★（★运维日志里必须有那一行 ✓ 日志指到**临时目录** ✓
     ★探针不许动真数据✓★）
  O4 ★拒绝话要说清两条正路✗★（★不是光说"不行" ✓ 见 P-family：拒了要能说出为什么✓★）
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import raw as R  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


class FakeCh:
    """★假通道✗★：只记下"到底发了什么" ✓ 不碰世界 ✓"""

    who = "fake0"

    def __init__(self):
        self.sent = []

    def cmd(self, text, **kw):
        self.sent.append(text)
        raise RuntimeError("★探针不该真的发出去✗★")     # ★真发了就炸 ✗ 这样才能证明没发✓★


print("== ops_guard_test：O1~O4 ==")

# ---- O1 分类 ----
_cases = (("setblock 1 2 3 stone", True), ("fill 1 2 3 4 5 6 air", True),
          ("data get entity Bot Pos", False), ("dshscan 1 2 3 1 2 3", False),
          ("dshplace 1 2 3 minecraft:dirt", False), ("clone 1 2 3 4 5 6 7 8 9", True),
          ("tp Bot 1 2 3", True))
_bad = [(s, R.is_world_change(s), w) for (s, w) in _cases if R.is_world_change(s) != w]
check("O1", not _bad, "★分类✗★：%s" % (_bad or "全部对 ✓（★`/dsh…` 一律放行 ✓ 因为 reach 由模组判✓★）"))

# ---- O2 没声明 ⇒ 一个字都不发 ----
_tmp = pathlib.Path(tempfile.mkdtemp())
_orig_log = R.ROOT_LOG
R.ROOT_LOG = _tmp                                  # ★日志指到临时目录（★不许动真数据✓★）
ch1 = FakeCh()
rc1 = R.run_one(ch1, "setblock 4103 69 20 minecraft:dirt", ops=False)
check("O2a", rc1 == 3, "★没声明 ⇒ 退出码应该是 3✗★（实得 %s）" % rc1)
check("O2b", ch1.sent == [], "★★一个字都没发出去✗★★（发了：%s）" % (ch1.sent or "（没有 ✓）"))
check("O2c", not (R.ROOT_LOG / "ops_world.log").exists(),
      "★没声明就**不该**留运维痕 ✗（★没发哪来的痕✓★）")

# ---- O3 声明了 ⇒ 发 ＋ 留痕 ----
ch2 = FakeCh()
try:
    R.run_one(ch2, "setblock 4103 69 20 minecraft:dirt", ops=True)
except RuntimeError:
    pass                                            # ★假通道会炸 ✗ 那正好说明"它发出去了"✓★
_log = R.ROOT_LOG / "ops_world.log"
check("O3a", ch2.sent == ["setblock 4103 69 20 minecraft:dirt"],
      "★声明了就该发✗★（发了：%s）" % (ch2.sent or "（没发 ✗）"))
check("O3b", _log.is_file() and "setblock" in _log.read_text(encoding="utf-8"),
      "★发了就留痕✗★（%s）" % (_log if _log.is_file() else "（没有日志 ✗）"))

# ---- O4 拒绝话要说清两条正路 ----
import io  # noqa: E402
import contextlib  # noqa: E402
_buf = io.StringIO()
ch3 = FakeCh()
with contextlib.redirect_stdout(_buf):
    R.run_one(ch3, "fill 1 2 3 4 5 6 air", ops=False)
_txt = _buf.getvalue()
check("O4", ("/dsh" in _txt) and ("--ops" in _txt) and ("没" in _txt or "没有" in _txt),
      "★拒绝话要给出两条正路（模组动作 ／ 显式 --ops）✗★（%d 字）" % len(_txt))

R.ROOT_LOG = _orig_log
print("=> ops_guard %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
