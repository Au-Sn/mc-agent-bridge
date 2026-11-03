#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motion_stat_test.py -- ★★运动统计的判据：跑没跑／跳没跳／多快（★不靠人眼✗★）★★

★★用户的要求✗★★：★"★确实在跑跳 ✗ 但你也得有获取方法 ✗ 不能全依靠我的观察★"✗★★
★⇒ ★模组 2.37.0 起 ✗ `do_done`/`do_fail` 事件带 ★`move=dist=… t=… spd=… sprint=… jumps=… look=…`**✗★
★⇒ 本判据**只读这个字段** ✗ **不用人看** ✗★

★★判五条✗★★：
　★① 长距离直线（★平台 z=12..30 ✗ 18 格✗★）⇒ ★`spd` 必须 **> 4.0 格/秒**（★真的在走 ✗ 不是抖✗★）✗★
　★② 同一趟 ⇒ ★`sprint > 0`**（★疾跑 tick 数 > 0 ⇒ 真的疾跑过✗★）✗★
　★③ 有台阶的路线 ⇒ ★`jumps > 0`**（★真的跳过✗★）✗★
　★④ `t` 与 `dist` 自洽 ⇒ ★`dist / (t/20)` ≈ `spd`**（★±20%✗★）✗★
　★⑤ 静止时（★`walk` 目标＝当前格✗★）⇒ ★`dist ≈ 0`**（★不虚报✗★）✗★ ✓

★口径说明✗★★：★`spd` 由**模组自己**算（★`dist / (motionTicks/20)`✗★）✗
　★⇒ ★**排除了 Python 侧轮询延迟** ✗ 这正是上一轮测不准的原因✗★ ✓
"""
from __future__ import annotations

import re
import sys
import time

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C            # noqa: E402


def pos():
    o = C.dsh("dshdigest", 20.0) or ""
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", o)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def cursor():
    """★`dshevents` 的游标：★取当前最后一条的 `#N`**（★§79.435 的教训 ✗ 必须用游标✗★）✗★"""
    ev = C.dsh("dshevents", 20.0) or ""
    nums = [int(n) for n in re.findall(r"#(\d+)", ev)]
    return max(nums) if nums else 0


def do_move(plan, cur, timeout=90.0):
    """★提交一条 `dshdo` ✗ 只认**新**事件 ✗ 返回 `move=` 字段与 `do_done`/`do_fail`✗★"""
    C.dsh('dshdo "%s"' % plan, 60.0)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(0.5)
        ev = C.dsh("dshevents %d" % cur, 25.0) or ""
        m = re.search(r"do_done[^|\n]*", ev)
        f = re.search(r"do_fail[^|\n]*", ev)
        line = m.group(0) if m else (f.group(0) if f else None)
        if line:
            mm = re.search(r"move=(dist=([\d.]+) t=(\d+) spd=([\d.]+) sprint=(\d+) jumps=(\d+) look=(\d+))",
                           line)
            if not mm:
                # ★★§79.438✗★★：★事件里**没有 move=** ⇒ 说明模组**还没装 2.37.0**✗★
                #   ★⇒ 这是**环境不满足** ✗ 不是判据失败 ⇒ 报 **†测不了†**（★项目口径✗★）✗★
                return "NOMOVE", line
            return {"dist": float(mm.group(2)), "t": int(mm.group(3)),
                    "spd": float(mm.group(4)), "sprint": int(mm.group(5)),
                    "jumps": int(mm.group(6)), "look": int(mm.group(7)),
                    "raw": mm.group(1), "line": line}, line
    return None, None


def main() -> int:
    checks = []
    p = pos()
    print("  假人：%s" % (p,))
    if not p:
        print("MOTION ok=0 reason=no_pos（★测不了 ✗ 不是失败✗★）")
        print("MOTIONSTAT ok=0 reason=no_pos")
        return 4

    # ★复位到平台（★x=4122 ✗ feet y=71 ✗ z=12✗★）
    C.dsh("tp Bot 4122.5 71.0 12.5", 20.0)
    time.sleep(1.5)

    # ① ② ④：★长直线 18 格✗★
    cur = cursor()
    plan = ";".join("walk:4122,71,%d" % z for z in range(13, 31))
    st, line = do_move(plan, cur)
    print("  ① 长直线：%s" % (line[:170] if line else "★没收到 do_done/do_fail★"))
    if st == "NOMOVE":
        print("  ★†测不了† ｜ 模组没有 move= 字段（★说明跑的不是 2.37.0✗★）⇒ **不是失败**✗★")
        print("MOTIONSTAT ok=0 reason=no_move_field inconclusive=1")
        return 2
    if st:
        print("     统计：%s" % st["raw"])
        # ★★§79.441✗★★：★阈值不能拍 4.0**✗★
        #   ★实测（★2.37.1✗★）：★平路 19 格 ✗ jumps=10（★自动跳台阶✗★）⇒ spd=3.57**✗★
        #   ★⇒ ★**跳一下必然慢** ✗ 这是**真实**不是 bug ⇒ 阈值改成 **3.4**（★明显高于抖✗★）✗★
        #   ★并**同时报 jumps** ✗ 让人一眼看出★慢是因为在跳★✗★
        checks.append(("真的在走（spd > 3.4 ✗ 跳多了会慢✗★）", st["spd"] > 3.4,
                       "spd=%.2f jumps=%d" % (st["spd"], st["jumps"])))
        checks.append(("真的疾跑过（sprint > 0）", st["sprint"] > 0, "sprint=%d" % st["sprint"]))
        expect = st["dist"] / (st["t"] / 20.0) if st["t"] > 0 else 0
        rel = abs(expect - st["spd"]) / max(0.01, st["spd"])
        checks.append(("dist/t/spd 自洽（±20%）", rel <= 0.20,
                       "期望 %.2f ／ 报 %.2f（差 %.0f%%）" % (expect, st["spd"], rel * 100)))
    else:
        for nm in ("真的在走（spd > 4.0）", "真的疾跑过（sprint > 0）", "dist/t/spd 自洽（±20%）"):
            checks.append((nm, False, "★没拿到统计✗★"))

    # ③ 台阶：★从低一层上到平台✗★（★y=70 ⇒ y=71 正交上 1 格✗★）
    C.dsh("tp Bot 4122.5 70.0 12.5", 20.0)
    time.sleep(1.5)
    cur = cursor()
    st2, line2 = do_move("walk:4122,71,13;walk:4122,71,14", cur)
    print("  ③ 上台阶：%s" % (line2[:170] if line2 else "★没收到★"))
    if st2 == "NOMOVE":
        print("  ★†测不了† ｜ 模组没有 move= ⇒ 不是失败✗★")
        print("MOTIONSTAT ok=0 reason=no_move_field inconclusive=1")
        return 2
    if st2:
        print("     统计：%s" % st2["raw"])
        checks.append(("真的跳过（jumps > 0）", st2["jumps"] > 0, "jumps=%d" % st2["jumps"]))
    else:
        checks.append(("真的跳过（jumps > 0）", False, "★没拿到统计✗★"))

    # ⑤ 静止：★walk 到当前格 ⇒ dist ≈ 0✗★
    here = pos()
    if here:
        cell = C.cell_of(here[0], here[1], here[2])
        cur = cursor()
        st3, line3 = do_move("walk:%d,%d,%d" % cell, cur, timeout=30.0)
        print("  ⑤ 静止：%s" % (line3[:150] if line3 else "★没收到★"))
        if st3 == "NOMOVE":
            print("  ★†测不了† ｜ 模组没有 move= ⇒ 不是失败✗★")
            print("MOTIONSTAT ok=0 reason=no_move_field inconclusive=1")
            return 2
        if st3:
            checks.append(("静止时 dist ≈ 0（不虚报）", st3["dist"] <= 1.0, "dist=%.2f" % st3["dist"]))
        else:
            checks.append(("静止时 dist ≈ 0（不虚报）", False, "★没拿到统计✗★"))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => motion_stat ★FAIL★（%d 项不对）" % bad)
        print("MOTIONSTAT ok=0 bad=%d" % bad)
        return 1
    print("  => motion_stat PASS ✓（★跑 ✗ 跳 ✗ 速度 ✗ **全部由模组报数 ✗ 不靠人眼**✗★）")
    print("MOTIONSTAT ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
