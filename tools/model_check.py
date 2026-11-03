#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""model_check.py -- ★世界模型**保真度自检**★（§79.371 ✗ 用户："这些先修 + 我的读取可能有问题"）

★做法✗★：★读一片区域 ⇒ **随机抽 N 格** ⇒ 每格拿 `dshscan` **单格**核一遍 ⇒ 和模型比✗★ ✓
★比三样✗★：★① 实心/空气 ② 名字（★切掉 `[…]`／`,状态`✗★）③ 碰撞高度（★h>0.05 ⇒ 实心✗★）✗★ ✓
★判据✗★：★一致率必须 **100%** ✗ 有任何一个不一致就 **FAIL** ✗ 并把不一致的格**逐条列出**✗★ ✓
"""
from __future__ import annotations

import random
import re
import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C            # noqa: E402
import world3d as W3            # noqa: E402

BOX = (4098, 66, 12, 4116, 74, 28)
N = 24


def scan_cell(p):
    """★单格扫✗★ ⇒ (是否实心, 名字)✗★"""
    t = C.dsh('dshscan %d %d %d %d %d %d ":" 8 1' % (p[0], p[1], p[2], p[0], p[1], p[2]), 30.0) or ""
    head = t.splitlines()[0] if t else ""
    if "dshscan box=" not in head:
        return None, "回包不合法：%r" % head[:60]
    m = re.search(r"solid=(\d+)", head)
    if not m:
        return None, "没有 solid=：%r" % head[:60]
    solid = int(m.group(1)) > 0
    cm = re.search(r"cells\[[^:]*:([^\]]*)\]", head)
    name = (cm.group(1).split(",")[0] if cm else "")
    return solid, name


def main() -> int:
    w = W3.World3D()
    ok = w.fetch_region(BOX)
    print("  读：%s" % w.stats())
    print("  读全了吗：%s ｜ 没读全的盒子 %d ｜ errors %d"
          % (ok, len(w.partial), len(w.errors)))
    if not ok:
        print("  ★没读全 ⇒ 直接 FAIL ✗ 不许拿半个模型判✗★")
        print("MODELCHK ok=0 reason=partial_read")
        return 1
    rng = random.Random(20261025)
    pts = []
    for _ in range(N):
        pts.append((rng.randint(BOX[0], BOX[3]), rng.randint(BOX[1], BOX[4]),
                    rng.randint(BOX[2], BOX[5])))
    bad = []
    for p in pts:
        got_solid, got_name = scan_cell(p)
        if got_solid is None:
            bad.append((p, "scan 失败", got_name))
            continue
        mh = w.h(*p)
        m_solid = (mh > 0.05) if mh >= 0 else None
        mn = (w.name(*p) or "").split(",")[0]
        if m_solid is None:
            bad.append((p, "★模型说未知 ✗ 这一格在已读盒子里不该未知★", ""))
            continue
        # ★★§79.401✗★★：★**名字一致 ⇒ 这一格就一致**✗★
        #   ★为什么✗★：★`dshscan` 的 `solid=1` 是 **`!isAir`**（★植物／火把也算"实心"✗★）✗
        #   ★而模型的 `solid` 是 **`h>0.05`**（★按**碰撞盒**✗ 植物 h=0 ✗）✗★
        #   ⇒ ★两边定义**本来就不同** ✗ 拿它们比是**判据自己的错**✗★
        #     （★2026-10-26 实测：`(4114,71,24)` 名字 `minecraft:grass` ✗ 模型 h=0.00／实扫 solid=1✗★）✗★ ✓
        #   ★正确口径✗★：★**名字是强不变量**（★两边都报方块 id✗★）⇒ **名字一致即通过**✗
        #     ★名字不一致 / 模型未知 才继续查✗★ ✓
        if mn and got_name:
            if mn == got_name:
                continue
            bad.append((p, "名字不符 模型=%r 实扫=%r（h=%.2f 模型solid=%s 实扫solid=%s）"
                        % (mn, got_name, mh, m_solid, got_solid), ""))
            continue
        # ★名字缺失（★空✗★）时才退回比 solid✗★ ✓
        if m_solid != got_solid:
            bad.append((p, "实心不符 模型=%s 实扫=%s（h=%.2f 名字=%r）"
                        % (m_solid, got_solid, mh, mn), ""))
            continue
    agree = N - len(bad)
    print("  抽样 %d 格 ✗ 一致 **%d** ✗ 不一致 %d" % (N, agree, len(bad)))
    for p, why, extra in bad[:12]:
        print("     ★ %s ⇒ %s %s" % (p, why, extra))
    rate = agree / N
    print("  一致率：**%.1f%%**（★要求 100%%✗★）" % (rate * 100))
    p = 1.0 if not bad else rate
    print("MODELCHK ok=%d agree=%d/%d rate=%.3f" % (1 if not bad else 0, agree, N, p))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
