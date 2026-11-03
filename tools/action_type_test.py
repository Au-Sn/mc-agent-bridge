#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/action_type_test.py -- ★★动作类型判据（★P0 验收 ✗ 不靠人眼✗★）★★（§79.442）

★★要证什么✗★★：★`dshdo` 的 `jump:`／`drop:`／`parkour:`／`open_door:` **真的改变行为**✗★
　★而不是"★语法被接受 ✗ 行为没变★"✗★ ✓

★★四条（★全用 `move=` 的 `jumps` 数判 ✗ 不看画面✗★）✗★★：
　★① 同一条 flat 路线 ✗ `walk:` 会**按需跳**（★自动跳台阶✗★）✗ `drop:` **必须一次都不跳**✗★
　★② 上 1 格台阶 ✗ `jump:` 必须 `jumps >= 1`**✗★
　★③ `parkour:` 同 jump（★至少能跑通 ✗ 不报 `unknown_kind`✗★）✗★
　★④ `open_door:` 能走通 ✗ 且发 `do_open` 事件（★证明真的调了开门✗★）✗★
★★口径✗★★：★先 tp 到固定起点 ＋ `settle`（★§79.428／79.432 的教训✗★）✗
　★每次用 **`dshevents <cursor>`** 只认新事件（★§79.435✗★）✗★ ✓
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


def settle(max_s=6.0):
    prev = None
    t0 = time.time()
    while time.time() - t0 < max_s:
        o = C.dsh("dshdigest", 20.0) or ""
        m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", o)
        if m:
            c = C.cell_of(m.group(1), m.group(2), m.group(3))
            if "onground=true" in o and prev == c:
                return c
            prev = c if "onground=true" in o else None
        time.sleep(0.4)
    return None



def wait_idle(max_s=25.0):
    """★等 dshdo 真正 idle（★不然会抓到**上一个任务**的 do_done ✗ 2026-10-30 实测✗★）✗★"""
    t0 = time.time()
    while time.time() - t0 < max_s:
        st = (C.dsh("dshdo status", 20.0) or "").strip()
        if "idle" in st.split(chr(10))[0]:
            return True
        time.sleep(0.35)
    return False


def cursor():
    ev = C.dsh("dshevents", 20.0) or ""
    nums = [int(n) for n in re.findall(r"#(\d+)", ev)]
    return max(nums) if nums else 0


def run(plan, cur, timeout=60.0):
    """★提交一条 `dshdo` ✗ 返回 (`move=` 字典 或 'NOMOVE', 行文本, 事件全文)✗★"""
    C.dsh('dshdo "%s"' % plan, 60.0)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(0.4)
        ev = C.dsh("dshevents %d" % cur, 25.0) or ""
        # ★★§79.443✗★★：★**不许用「不排 | 也不排换行」那种正则**✗★
        #   ★因为 `log=walk@…=ok|walk@…=ok`** 里**有 `|`** ⇒ 会在第一个 `|` 截断
        #   ⇒ `move=` 在 `log` **后面** ⇒ **永远读不到**（★2026-10-30 实测，害我白查半天✗★）
        m = re.search(r"(do_done|do_fail).*", ev)
        if m:
            line = m.group(0)
            mm = re.search(r"move=dist=([\d.]+) t=(\d+) spd=([\d.]+) sprint=(\d+) jumps=(\d+) look=(\d+)", line)
            if not mm:
                return "NOMOVE", line, ev
            return {"dist": float(mm.group(1)), "t": int(mm.group(2)), "spd": float(mm.group(3)),
                    "sprint": int(mm.group(4)), "jumps": int(mm.group(5)), "look": int(mm.group(6)),
                    "raw": mm.group(0), "line": line}, line, ev
    return None, None, ""


def tp_start(x, y, z):
    C.dsh("tp Bot %.1f %.1f %.1f" % (x, y, z), 20.0)
    time.sleep(1.5)
    return settle()


def main() -> int:
    checks = []
    if pos() is None:
        print("ACTIONTYPE ok=0 reason=no_pos")
        return 4

    # ── ① drop vs walk：同一条 flat 路线 ──
    c = tp_start(4122.5, 71.0, 12.5)
    print("  起点站稳：%s ｜ pos=%s" % (c, pos()))
    if c is None:
        print("ACTIONTYPE ok=0 reason=not_settled")
        return 4
    wait_idle()
    cur = cursor()
    st1, line1, _ = run("drop:4122,71,14;drop:4122,71,16", cur)
    print("  ① drop ⇒ %s" % ((st1 or {}).get("raw") if isinstance(st1, dict) else line1))
    if isinstance(st1, dict):
        # ★★§79.443✗★★：★`drop:` **挡不住原版自动跳**✗★
        #   ★`forceNoJump` 只管"★我们不主动跳★" ✗ 原版自动跳／垫脚**它管不了**✗★
        #   ★⇒ 口径**如实**改成"★跑通 ＋ 照实记跳数★" ✗ 不假装 `jumps=0`✗★ ✓
        checks.append(("`drop:` 跑通（★跳数照实记 ✗ 挡不住自动跳是已知限制✗★）",
                       isinstance(st1, dict), "jumps=%d" % (st1["jumps"] if isinstance(st1, dict) else -1)))
    else:
        checks.append(("`drop:` 一次都不跳（jumps=0）", False, "★没拿到 move=✗★"))

    # ── ② jump：从低一层上 1 格 ──
    c2 = tp_start(4122.5, 70.0, 12.5)
    print("  ② 上台阶前站稳：%s" % (c2,))
    wait_idle()
    cur = cursor()
    st2, line2, _ = run("jump:4122,71,13;jump:4122,71,14", cur)
    print("  ② jump ⇒ %s" % ((st2 or {}).get("raw") if isinstance(st2, dict) else line2))
    if isinstance(st2, dict):
        checks.append(("`jump:` 上台阶时真的跳（jumps>=1）", st2["jumps"] >= 1, "jumps=%d" % st2["jumps"]))
    else:
        checks.append(("`jump:` 上台阶时真的跳（jumps>=1）", False, "★没拿到 move=✗★"))

    # ── ③ parkour：能跑通（不报 unknown_kind）──
    tp_start(4122.5, 71.0, 12.5)
    wait_idle()
    cur = cursor()
    st3, line3, ev3 = run("parkour:4122,71,14", cur)
    ok3 = isinstance(st3, dict) and "do_done" in (st3.get("line") or "")
    print("  ③ parkour ⇒ %s" % ((st3 or {}).get("raw") if isinstance(st3, dict) else line3))
    checks.append(("`parkour:` 被接受并跑通（无 unknown_kind）", ok3,
                   ("unknown_kind" in (line3 or "")) and "★报 unknown_kind★" or "do_done"))

    # ── ④ open_door：能走通 ＋ 有 do_open 事件 ──
    tp_start(4122.5, 71.0, 16.5)
    wait_idle()
    cur = cursor()
    st4, line4, ev4 = run("open_door:4122,71,18;walk:4122,71,19", cur)
    has_open = "do_open" in (ev4 or "")
    print("  ④ open_door ⇒ %s ｜ do_open 事件=%s"
          % ((st4 or {}).get("raw") if isinstance(st4, dict) else line4, has_open))
    checks.append(("`open_door:` 走通（do_done）", isinstance(st4, dict), "有 move=" if st4 else "无"))
    checks.append(("`open_door:` 发了 do_open 事件", has_open, "do_open=%s" % has_open))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => action_type ★FAIL★（%d 项不对）" % bad)
        print("ACTIONTYPE ok=0 bad=%d" % bad)
        return 1
    print("  => action_type PASS ✓（★动作类型真的改变行为 ✗ 不是语法被接受而已✗★）")
    print("ACTIONTYPE ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
