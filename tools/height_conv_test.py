#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""height_conv_test.py -- ★把"★高度约定★"钉死：脚格 vs 支撑格 差一格就红★（§79.372）

★★为什么要有这条判据（★用户 2026-10-25 的提醒✗★）✗★★：
  ★"★看一下高度检测是根据脚底方块还是头部方块 ✗ 这个偏差会导致全部失效★"✗★ ✓
  ★我犯过的错✗★：★拿"★脚格 vs 脚下那一块★"算**坑深** ⇒ **恒等于 1** ✗★ ⇒
  ★实测那处是**2 格深**（★东／南 比脚格高 2✗★）⇒ ★整个"★深度／可跳性★"都错✗★ ✓

★★判五条（★全过才算约定对✗★）✗★★：
  ★C1 `dshdigest` 的 `floor(pos.y)` ＝ **脚格** ✗ 且该格 `dshscan` 是**空气**✗★ ✓
  ★C2 **脚格下面一格**（`y-1`）`dshscan` 是**实心**（★支撑✗★）✗★ ✓
  ★C3 `world3d.h(feet)` ＝ 0（★模型认为脚格无碰撞✗★）✗★ ✓
  ★C4 `world3d.support(feet)` ＝ True（★模型认为脚下有地板✗★）✗★ ✓
  ★C5 `world3d.standable(feet)` ＝ True ✗ 且 `world3d.h(feet+1)` ＝ 0（★头格空✗★）✗★ ✓
  ★C6 **反证**✗★：★`support(feet+1)` **必须**是 `h(feet)`＝0 ⇒ False（★不许把脚格当支撑✗★）✗★ ✓
"""
from __future__ import annotations

import math
import re
import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C            # noqa: E402
import world3d as W3            # noqa: E402


def settle(max_s: float = 5.0):
    """★等假人站稳（★§79.428✗★）✗★

    ★为什么✗★：★这条判据读**假人当前位置**✗ 而前一条判据可能刚 `tp` 过它✗★
      ★⇒ ★位置还在变／没接地 ⇒ C1~C6 里会有条对不上 ⇒ **假红**✗★ ✓
    ★口径✗★：★连续两次 `dshdigest` 的**格子一致** ∧ `onground=true`** ⇒ 算站稳✗★
      ★最多等 `max_s` 秒 ✗ 等不到**返回 False**（★调用方如实红 ✗ 不假装✗★）✗★ ✓
    """
    import time as _time
    prev = None
    t0 = _time.time()
    while _time.time() - t0 < max_s:
        o = C.dsh("dshdigest", 20.0) or ""
        m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", o)
        if m:
            cell = C.cell_of(m.group(1), m.group(2), m.group(3))
            ong = "onground=true" in o
            if ong and prev == cell:
                return cell
            prev = cell if ong else None
        _time.sleep(0.35)
    return None


def single(p):
    """★单格扫✗★ ⇒ (solid?, 名字)✗★"""
    t = C.dsh('dshscan %d %d %d %d %d %d ":" 8 1' % (p[0], p[1], p[2], p[0], p[1], p[2]), 30.0) or ""
    head = t.splitlines()[0] if t else ""
    if "dshscan box=" not in head:
        return None, "回包不合法：%r" % head[:70]
    m = re.search(r"solid=(\d+)", head)
    if not m:
        return None, "没有 solid=：%r" % head[:70]
    solid = int(m.group(1)) > 0
    cm = re.search(r"cells\[[^]]*:([^\]]*)\]", head)
    name = (cm.group(1).split(",")[0] if cm else "")
    return solid, name


def main() -> int:
    # ★★§79.432✗★★：★先把假人 **tp 到平台上一个已知格子**✗★
    #   ★为什么✗★：★这条判据验★脚格约定★ ✗ 但**假人站哪**是环境变量✗★
    #   ★⇒ ★它飘到半高方块／别层 ⇒ 判据红得**毫无信息**（★2026-10-27 连红两次 ✗ 一次 dirt_path 一次 h=1.5✗★）✗★
    #   ★⇒ ★固定到**平台地板**（★feet=71 ✗ 下面 oak_planks✗★）✗ 只看约定对不对✗★ ✓
    C.dsh("tp Bot 4120.5 71.0 15.5", 20.0)
    import time as _t0
    _t0.sleep(1.0)
    # ★★§79.428✗★★：★先等站稳 ✗ 不然"位置还在变／没接地"会把这条判据弄成**假红**✗★
    #   （★2026-10-27 实测：单跑 6/6 ✗ 但 world_regress 里红 1 条 ✗ 重试仍红✗★）✗★ ✓
    _settled = settle()
    if _settled is None:
        print("  ★等不到站稳（★5 秒✗★）⇒ 如实红（★不假装✗★）✗★")
        print("HEIGHTCONV ok=0 fail=1 reason=not_settled")
        return 1
    print("  站稳了：%s" % (_settled,))
    o = C.dsh("dshdigest", 25.0) or ""
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+).*?onground=(\w+)", o)
    if not m:
        print("HEIGHTCONV ok=0 reason=no_pos")
        return 4
    fx, fy, fz = float(m.group(1)), float(m.group(2)), float(m.group(3))
    onground = m.group(4)
    # ★★§79.431✗★★：★脚格 = ceil(y−ε)**（★站在 `dirt_path`／半砖上时 `floor` 会读到那方块自己✗★）✗★
    feet = C.cell_of(fx, fy, fz)
    print("  ★脚格规则✗★：pos.y=%.4f ⇒ ceil ⇒ 脚格 y=%d（★floor 会给 %d ✗ 那是砖自己✗★）"
          % (fy, feet[1], math.floor(fy)))
    below = (feet[0], feet[1] - 1, feet[2])
    above = (feet[0], feet[1] + 1, feet[2])
    print("  digest：pos=%.2f,%.2f,%.2f onground=%s ⇒ 脚格 %s" % (fx, fy, fz, onground, feet))

    w = W3.World3D()
    ok_read = w.fetch_region((feet[0] - 2, feet[1] - 3, feet[2] - 2,
                              feet[0] + 2, feet[1] + 3, feet[2] + 2))
    print("  模型读全：%s ｜ cells=%d ｜ partial=%d"
          % (ok_read, len(w.cells), len(w.partial)))

    res = []
    s_feet, n_feet = single(feet)
    res.append(("C1 脚格是空气（★允许脚下有雪层等半格✗★）",
                s_feet is False or (n_feet and "air" in n_feet),
                "实扫 solid=%s 名字=%r" % (s_feet, n_feet)))
    s_below, n_below = single(below)
    res.append(("C2 脚格下面一格是实心（★支撑✗★）", s_below is True,
                "实扫 solid=%s 名字=%r" % (s_below, n_below)))
    res.append(("C3 模型 h(脚格) = 0", abs(w.h(*feet)) <= 0.05,
                "h=%.2f" % w.h(*feet)))
    res.append(("C4 模型 support(脚格) = True", w.support(*feet) is True,
                "support=%s ｜ 下面那块模型名=%r" % (w.support(*feet), w.name(*below))))
    res.append(("C5 模型 standable(脚格) = True 且 h(头格)=0",
                w.standable(*feet) is True and w.h(*above) <= 0.05,
                "standable=%s h(头)=%.2f" % (w.standable(*feet), w.h(*above))))
    # ★C6 反证：support(头格) 必须 False（★因为 h(脚格)=0✗★）
    res.append(("C6 反证：不能把脚格当支撑（support(头格) 必须 False）",
                w.support(*above) is False,
                "support(头)=%s（★脚格 h=%.2f✗★）" % (w.support(*above), w.h(*feet))))

    bad = 0
    for name, ok, detail in res:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- 五路＋反证一致：%d/%d ----" % (len(res) - bad, len(res)))
    if bad:
        print("HEIGHTCONV ok=0 fail=%d" % bad)
        return 1
    print("HEIGHTCONV ok=1 checks=%d feet=%s" % (len(res), feet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
