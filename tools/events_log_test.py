#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""events_log_test.py -- ★★"死亡保险的证据链"要被判据钉住✗★★（欠账 ⑬ ✓ 2026-10-02 ✓）

判据（★先写死✗★）
  E1 ★ASCII 事件要**捞得到**✗★（`bot_died phase=stashed who=Bot kept_items=81` ✓）
  E2 ★★含非 ASCII 的整行**必须丢**✗★★（★不许把 `?` 存进账本 ✗ P13/P38✓★）
  E3 ★★落盘必须是**纯 ASCII**✗★★（★写的时候 `encoding="ascii"` ＋ `errors="strict"` ✗
     非 ASCII 会**抛**而不是静默替换 ✓★）
  E4 ★去重✗★：同一行连喂两次 ⇒ 第二次**不写** ✓（★轮询会把同一事件看很多遍✗★）
  E5 ★★凭证要**够用**✗★★：`bot_died` 那一行里必须有 `who=` ✓ 和 `kept_items=` ✓
     —— ★因为欠账 ⑬ 要回答的正是"**保险到底还了多少**"✗★
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

import events_log as E  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== events_log_test：证据链 E1~E5 ==")
sample = ("garbage 前面有中文 ✗\n"
          "bot_died phase=stashed who=Bot kept_items=81\n"
          "★中文事件★\n"
          "bot_revived phase=done who=Bot back_items=81\n"
          "walk_refuse kind=edge why=step_down=2_at_4121_71_0\n"
          "??\n")
found, dropped = E.extract_ascii(sample)
check("E1", found == ["bot_died phase=stashed who=Bot kept_items=81",
                      "bot_revived phase=done who=Bot back_items=81",
                      "walk_refuse kind=edge why=step_down=2_at_4121_71_0"],
      "捞到 %d 条 ✓（★三缺一都不对 ✓★）" % len(found))
check("E2", dropped == 3 and all(E.HEXOK.match(x) for x in found),
      "丢掉 %d 行（★含中文/问号的一律丢✗★）" % dropped)

probe = ROOT / "tmp" / "_events_probe.log"
if probe.exists():
    probe.unlink()
seen = set()
w1, s1 = E.append(found, probe, seen)
w2, s2 = E.append(found, probe, seen)
raw = probe.read_bytes()
check("E3", all(b < 128 for b in raw) and raw.count(b"\n") == len(found),
      "落盘 %d 字节 ⇒ ★全是 ASCII✗★ ✓ 行数 = %d ✓" % (len(raw), raw.count(b"\n")))
check("E4", w1 == 3 and w2 == 0 and s2 == 3, "第一次写 %d ✓ 第二次写 %d（★去重生效✗★）✓" % (w1, w2))
died = [x for x in found if x.startswith("bot_died")][0]
check("E5", "who=" in died and "kept_items=" in died,
      "`bot_died` 凭证含 who= 与 kept_items= ✓（★这正是 ⑬ 要回答的✗★）")

# ★★E6：★轮询命令**必须**是 `dshevents`（不带参数）✗★★（欠账 ㉑ ✓ 2026-10-03 ✓）
#   ★为什么值得一条判据✗★：★我先前写成 `dshevents tail`✗ ⇒ 原生报"参数不对"✗
#     ⇒ ★过 CC 变 `????` ⇒ 于是"读不到"被误读成"**没有事件**"✗★ ✓
#   ⇒ ★这条守着"别再加尾巴"✗★ ✓
import inspect as _insp  # noqa: E402
_src = _insp.getsource(E.poll_once)
# ★★口径✗★★（2026-10-03 当场吃到 ✓）：★第一版把**文档字符串里**那句
#   "★我先前写的是 `dshevents tail`✗"也当成了"代码里加了 tail"✗ ⇒ **假红**✗★
#   ⇒ ★只查**调用那一行**✗（★`dsh("dshevents tail"` 这种✗）✓ 不查说明文字✓★
check("E6", 'dsh("dshevents",' in _src and 'dsh("dshevents tail"' not in _src,
      "★轮询的**调用**是 `dshevents`（不带参数）✗★ ✓（★调用里加 `tail` 才会红✗★）")

# ★★E7~E9：★⑬ 的解锁器 `death_evidence`✗★★（2026-10-03 ✓ 离线 ✓ 判据先写死 ✓）
#   ★口径✗★：★只有死没复活 ⇒ 明写"**还缺复活**"✗（★不许说"没事"✓★）
#     ★还的少于扣的 ⇒ 明写差额✗ ／ ★凭证缺字段 ⇒ 判"读不到"✗（★不许判"还了"✓★）
import tempfile as _tf  # noqa: E402
import pathlib as _pl  # noqa: E402  ★2026-10-03 补：新块用了它而上面只 import 过 `sys`✗★
_td = _pl.Path(_tf.mkdtemp())


def _mk(name, lines):
    f = _td / name
    f.write_text("\n".join(lines) + "\n", encoding="ascii")
    return str(f)


D_ONLY = _mk("d1.log", ["2026-10-03T00:00:00\tbot_died phase=done who=Bot kept_items=42"])
D_PAIR = _mk("d2.log", ["2026-10-03T00:00:00\tbot_died phase=done who=Bot kept_items=42",
                        "2026-10-03T00:01:00\tbot_revived phase=done who=Bot back_items=42"])
D_SHORT = _mk("d3.log", ["2026-10-03T00:00:00\tbot_died phase=done who=Bot kept_items=42",
                         "2026-10-03T00:01:00\tbot_revived phase=done who=Bot back_items=7"])
D_NONE = _mk("d4.log", ["2026-10-03T00:00:00\twalk_done result=reached at=1,2,3 want=1,2,3"])

r1 = E.death_evidence(D_NONE)
check("E7", r1["state"] == "none" and "还没发生过真死" in r1["note"],
      "★没死过 ⇒ 老实说「还没发生」✗★（★不是红 ✗ 也不许说没事✓★）")

r2 = E.death_evidence(D_ONLY)
check("E8", r2["state"] == "died-no-revive" and "还缺复活" in r2["note"],
      "★只有死没复活 ⇒ 明写「**还缺复活**」✗★（★不许说没事✓★）")

r3 = E.death_evidence(D_SHORT)
r4 = E.death_evidence(D_PAIR)
check("E9", r3["state"] == "short" and "差 **35**" in r3["note"]
      and r4["state"] == "ok" and "还 **42** 件" in r4["note"],
      "★还少了 ⇒ 明写差额（★差 35✓★）✗ ／ 成对 ⇒ 报「扣 42 还 42」✗★ ✓")

probe.unlink()
print("=> events_log %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
