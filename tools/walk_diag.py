#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""walk_diag.py -- ★走不到就**当场问它为什么**✗★（2026-09-30 ✓ 电池 8 红全是这一族 ✓）

## 为什么要这一份 ✗
  全量电池 **29/37** ✗ ⇒ 8 个红项**全在"走路/路线"这一族** ✗
  ⇒ 而"走不到"这件事，本项目**早就有判据**了（P104/P116/P117/P120/P124 ✓）：
    工具层会打印 **`★为什么没到★`** 与 **`★为什么停★`** ✗ —— ★我就不许再靠猜✗★
  ⇒ 这份脚本干三件事 ✓：
    ① 读实况（`dshdigest` ✓ 世界真值 ✗）
    ② 拿**一个具体目标**去走（默认取电池里真红过的那条 ✓ 也可以用 `--to x,y,z` ✓）
    ③ 把**完整回执**（含 why 行 ✓）原样打出来 ＋ 事后用**世界真值**判到没到 ✓

## 判据（★先写✗★）
  D1 起点真值 ：走之前 `pos=` 拿得到 ✓
  D2 回执有因 ：★"没到"⇒ 回执里**必须有** `★为什么没到★` 或 `★为什么停★`✗★（没有 ⇒ 判据本身漏了 ✓）
  D3 世界对账 ：★最终位置**由 `dshdigest` 判**✗★（不听工具自述 ✓）—— 同格同层才算到 ✓
  D4 归类     ：把原因归到四类之一 ✓（安全规则拦住 ✗／路上不通 ✗／走一半停 ✗／其实到了 ✓）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))

from channel import Channel        # noqa: E402


def say(s):
    print(s, flush=True)


def main(argv) -> int:
    to = None
    for i, a in enumerate(argv):
        if a == "--to" and i + 1 < len(argv):
            to = argv[i + 1]
    ch = Channel("cmd0", verbose=False)

    def cmd(t, tmo=120.0):
        r = ch.cmd("execute as Bot at Bot run %s" % t, timeout=tmo, allow_str=True)
        s = (r.text() or "").strip()
        return s

    d0 = cmd("dshdigest 6")
    say("D1 起点真值：%s" % d0[:150])
    m = re.search(r"pos=([-\d.]+),([-\d.]+),([-\d.]+)", d0)
    if not m:
        say("★读不到 pos ⇒ 停下 ✗（先说清楚，不许把 SKIP 当 PASS ✓）★")
        return 1
    x0, y0, z0 = (float(g) for g in m.groups())

    if not to:
        # ★默认目标：电池里真红过的那条（r8_guard G1：从 (4124,71,5) 去 (4136,71,7) ✓）
        to = "%d,%d,%d" % (int(x0) + 12, int(y0) - 1, int(z0) + 2)
    say("目标：%s（从 %.1f,%.1f,%.1f 出发 ✓）" % (to, x0, y0, z0))

    reply = cmd("dshwalk %s" % to, 240.0)
    # ★★回执必须落到**UTF-8 文件**再读✗★★（GBK 控制台打不了中文 ✓ 见 P39 ✓
    #   ★刚才就吃了这个亏✗★：中文全变 `??????` ⇒ 我根本看不出它为什么拒绝 ✓）
    out = ROOT / "logs" / "walk_diag.txt"
    out.write_text("目标 %s（从 %.2f,%.2f,%.2f 出发）\n%s\n---- 起点 ----\n%s\n"
                   % (to, x0, y0, z0, reply, d0), encoding="utf-8")
    say("---- 回执（原样 ✓ 一个字都不改 ✗）—— ★控制台是 GBK ✗ 中文看下面这个文件✗★ ----")
    say("     %s" % out)
    for ln in reply.splitlines():
        say("  " + ln)

    why = [ln for ln in reply.splitlines()
           if ("为什么没到" in ln) or ("为什么停" in ln)]
    d2 = bool(why) or ("arrived=true" in reply.lower())
    say("D2 回执有因：why 行 %d 条 ｜ 自述到了=%s => %s"
        % (len(why), "arrived=true" in reply.lower(), d2))

    d1 = cmd("dshdigest 6")
    m1 = re.search(r"pos=([-\d.]+),([-\d.]+),([-\d.]+)", d1)
    x1, y1, z1 = (float(g) for g in m1.groups()) if m1 else (x0, y0, z0)
    tx, ty, tz = (int(g) for g in to.split(","))
    ok_cell = (int(x1 // 1) == tx) and (int(z1 // 1) == tz)
    same_lv = abs(y1 - ty) < 1.01
    d3 = ok_cell and same_lv
    say("D3 世界对账：终点 %.2f,%.2f,%.2f ｜ 目标 %d,%d,%d ｜ 同格=%s 同层=%s ｜ 走了 %.2f 格 => %s"
        % (x1, y1, z1, tx, ty, tz, ok_cell, same_lv,
           ((x1 - x0) ** 2 + (z1 - z0) ** 2) ** 0.5, d3))

    txt = reply
    kind = ("其实到了 ✓" if d3 else
            "★安全规则**拦住**了 ✗（回执里有 边/虚空/回不来/单向 之类 ✓）"
            if any(k in txt for k in ("虚空", "边走", "回不来", "单向", "出不来", "不肯")) else
            "★路上不通 ✗（找不到路 / 堵住 ✓）" if any(k in txt for k in ("找不到", "无路", "堵", "不通"))
            else "★走一半停了 ✗（超时／被卡 ✓）" if any(k in txt for k in ("超时", "卡", "停"))
            else "★说不清 ✗（回执里没有能归类的理由 ✓ ⇒ 这条要补判据 ✓）")
    say("D4 归类：%s" % kind)
    say("=> %s" % ("到了 ✓" if d3 else "没到 ✗（上面那行就是原因 ✓ 下一步照它修 ✓）"))
    return 0 if d3 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
