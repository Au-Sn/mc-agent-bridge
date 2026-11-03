#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""house_nav_test.py -- ★进屋回归判据（★世界侧 ✗ 手动跑✗★）（§79.398）

★★它守什么✗★★（★一条链三处要害✗★）✗★：
  ★① **规划**：★从 `(4114,71,10)` 到屋内 `(4120,71,27)` ✗ 计划里必须有 **`open@`**
     ✗ 且**不许**对门 `(4122,71,18)`／`(4122,72,18)` 发 **`dig@`**（★§79.397 的回归✗★）✗★ ✓
  ★② **执行**：★`exec3d` 真跑 ✗ 必须 `arrived=True` 且 `bad=[]`**✗★ ✓
  ★③ **结果**：★脚格在**房间集合**里（★限 bbox ✗ 从门内洪水✗★）✗ 且门**还活着**（★没被挖✗★）✗★ ✓
★用法✗★：★`py tools/house_nav_test.py [--no-exec]`✗★（★`--no-exec` 只验规划 ✗ 不动人✗★）✗★ ✓
"""
from __future__ import annotations

import argparse
import sys
from collections import deque

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C            # noqa: E402
import plan3d as P3             # noqa: E402
import world3d as W3            # noqa: E402

START = (4114, 71, 10)
GOAL = (4120, 71, 27)
DOOR = [(4122, 71, 18), (4122, 72, 18)]
ROOM_BOX = (4113, 68, 16, 4131, 82, 34)
SEED = (4122, 71, 21)


def close_door():
    """★把门关上（★`dshuse` 是**切换** ✗ 关着就变开✗★）⇒ 先读状态再决定✗★

    ★★§79.398 修✗★★：★`dshuse` 有 **4.5 格**上限 ✗ 而假人可能在 10 格外✗★
      ⇒ 实测 `too far 10.66 > 4.5` **静默失败**✗★ ⇒ ★先 `tp` 到门前 1.5 格✗★ ✓
    """
    import re as _re
    import time as _time
    C.dsh("tp Bot 4122.5 71.0 16.5", 20.0)     # ★门北侧 1.5 格 ✗ 在 4.5 内✗★
    _time.sleep(1.0)
    for p in DOOR:
        t = C.dsh('dshscan %d %d %d %d %d %d "door" 8 1' % (p[0], p[1], p[2], p[0], p[1], p[2]), 25.0) or ""
        m = _re.search(r"open=(true|false)", t)
        if m and m.group(1) == "false":
            continue                       # ★已经关着 ✗ 别动（★切一下就开了✗★）✗★
        for face in ("south", "north", "east", "west"):
            C.dsh("dshuse %d %d %d %s" % (p[0], p[1], p[2], face), 40.0)
            import time
            time.sleep(0.4)
            t2 = C.dsh('dshscan %d %d %d %d %d %d "door" 8 1' % (p[0], p[1], p[2], p[0], p[1], p[2]), 25.0) or ""
            m2 = _re.search(r"open=(true|false)", t2)
            if m2 and m2.group(1) == "false":
                break
    st = {}
    for p in DOOR:
        t3 = C.dsh('dshscan %d %d %d %d %d %d "door" 8 1' % (p[0], p[1], p[2], p[0], p[1], p[2]), 25.0) or ""
        m3 = _re.search(r"open=(true|false)", t3)
        st[p] = m3.group(1) if m3 else "?"
    return st


def bot_cell():
    o = C.dsh("dshdigest", 20.0) or ""
    import re
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", o)
    # ★★§79.431✗★ 统一走 `mcp_core.cell_of`**（★半高方块上不会再读错格✗★）✗★
    return C.cell_of(m.group(1), m.group(2), m.group(3)) if m else None


def room_cells(w):
    """★房间集合✗★：★从门内格洪水 ✗ 限 bbox✗★"""
    if not P3.stand_at(w, *SEED)[0]:
        return set()
    seen = {SEED}
    q = deque([SEED])
    while q:
        x, y, z = q.popleft()
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            n = (x + dx, y + dy, z + dz)
            if n in seen:
                continue
            if not (ROOM_BOX[0] <= n[0] <= ROOM_BOX[3] and ROOM_BOX[1] <= n[1] <= ROOM_BOX[4]
                    and ROOM_BOX[2] <= n[2] <= ROOM_BOX[5]):
                continue
            if P3.stand_at(w, *n)[0]:
                seen.add(n)
                q.append(n)
    return seen


def door_alive():
    """★门还在吗（★没被挖✗★）✗★"""
    out = {}
    for p in DOOR:
        t = C.dsh('dshscan %d %d %d %d %d %d "door" 8 1' % (p[0], p[1], p[2], p[0], p[1], p[2]), 25.0) or ""
        h = t.splitlines()[0] if t else ""
        m = __import__("re").search(r"solid=(\d+)", h)
        out[p] = (m.group(1) != "0") if m else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-exec", action="store_true")
    ns = ap.parse_args()
    checks = []

    # ★先把门关上（★否则计划里没有 `open@` ✗ 判据会误红✗★）✗★
    #   ★`--no-exec` 也关 ✗ 关门不动人 ✗ 安全 ✓（★§79.398 收口✗★）✗★
    st_doors = close_door()
    print("  ★关完门✗★：%s" % (st_doors,))
    # ★把起点摆好（★关完门再摆 ✗ 顺序不能反✗★）✗★
    if not ns.no_exec:
        C.dsh("tp Bot %.1f %d.0 %.1f" % (START[0] + 0.5, START[1], START[2] + 0.5), 20.0)
        import time
        time.sleep(1.0)
    b = bot_cell()
    print("  起点（★当前✗★）：%s ｜ 目标（★屋内✗★）：%s" % (b, GOAL))

    w = W3.World3D()
    w.fetch_region((4108, 62, 8, 4136, 84, 36))
    print("  模型 %s ｜ partial=%d" % (w.stats(), len(w.partial)))
    checks.append(("模型读全", len(w.partial) == 0, "partial=%d" % len(w.partial)))

    start = b or START
    path, acts, cost = P3.plan(w, start, GOAL)
    print("  ★计划✗★：%s 步 ✗ 代价 %s ✗ %s"
          % (len(path or []), round(cost, 1) if cost else "-", P3.summarize(acts or {})))
    checks.append(("规划有路", bool(path), "%s 步" % (len(path or []),)))
    opens = [a for a in (acts or []) if a.startswith("open@")]
    digs = [a for a in (acts or []) if a.startswith("dig@")]
    checks.append(("计划**开门**（★open@✗★）", bool(opens), "%s" % (opens,)))
    door_dig = [d for d in digs if any(d == "dig@%d,%d,%d" % p for p in DOOR)]
    checks.append(("**不许挖门**", not door_dig, "门上的 dig=%s" % (door_dig,)))

    if not ns.no_exec and path:
        import exec3d as E
        ok, rep = E.execute(GOAL, dry=False, max_steps=400, restore=False, pause=0.9)
        print("  ★执行✗★：ok=%s arrived=%s bad=%s end=%s"
              % (ok, rep.get("arrived"), rep.get("bad"), rep.get("end")))
        checks.append(("执行到达", bool(ok) and bool(rep.get("arrived")), "arrived=%s" % rep.get("arrived")))
        # ★★§79.399✗★★：★split_to_* 是**恢复手段**（★dshgoto 被拒后折半✗★）✗
        #   ★不是错误✗★ ⇒ 从坏消息里滤掉 ✗ 只留**真错误**✗★ ✓
        real_bad = [b for b in (rep.get("bad") or []) if not b.startswith("split_to_")]
        if len(real_bad) != len(rep.get("bad") or []):
            print("     （★折半恢复 %d 次 ✗ 不算错误✗★）" % (len(rep.get("bad") or []) - len(real_bad),))
        checks.append(("执行无真错误", not real_bad, "%s" % (real_bad,)))

    # ★③ 结果核验✗★
    w2 = W3.World3D()
    w2.fetch_region((4108, 62, 8, 4136, 84, 36))
    room = room_cells(w2)
    p = bot_cell()
    # ★★§79.398✗★★：★"在屋里"用**屋子内部 bbox** 判 ✗ 不用洪水集合✗★
    #   ★洪水集合太松✗★：★模型把**关着的门**当可过（★INTERACT ✗ 开门就能走✗★）
    #   ⇒ ★洪水会穿门到屋外 ⇒ 站在屋外也"★在屋里★"✗★（★实测到过✗★）✗★ ✓
    in_room = bool(p) and (4115 <= p[0] <= 4129) and (71 <= p[1] <= 79) and (19 <= p[2] <= 32)
    print("  ★屋内 bbox✗★：x4115..4129 y71..79 z19..32 ｜ 假人 %s ｜ ★在屋里=%s"
          % (p, in_room))
    print("     （★参考✗★：洪水集合 %d 格 ✗ 太松 ✗ 只作参考✗★）" % (len(room),))
    if ns.no_exec:
        print("     （★--no-exec：★没执行 ✗ 不要求人在屋里✗★）")
    else:
        checks.append(("假人在屋里", in_room, "pos=%s" % (p,)))
    alive = door_alive()
    checks.append(("门没被挖", all(v is True for v in alive.values()), "%s" % (alive,)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => house_nav ★FAIL★（%d 项不对）" % bad)
        print("HOUSENAV ok=0 bad=%d" % bad)
        return 1
    print("  => house_nav PASS ✓（★规划开门 ✗ 执行到达 ✗ 人在屋内 ✗ 门还在✗★）")
    print("HOUSENAV ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
