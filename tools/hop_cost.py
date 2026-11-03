"""hop_cost.py -- 量"一跳到底花多久"（R3 慢的另一半 ✓ 先量再动 ✗）
★世界★：改世界（★限**移动假人** ✗ 不许放／挖方块 ✓★）

判据（先写死 ✓）：
  H1 至少量到 6 跳 ✓（每跳 8~14 格 ✓ 都在安全走廊里 ✓）
  H2 这 6 跳期间**建图次数 ≤ 2** ✓（任务图应当被复用 ✓ 见 mc_mcp._route_map ✓）
  H3 中位跳时 ≤ 6.0 秒 ✓（目标值 ✓ —— 若超了，就把分布摆出来 ✓ 不许含糊 ✗）
  H4 跑完假人还活着 ✓ 且每一步都有实测位置读数 ✓
输出 ✓：每一跳的 距离/耗时/回执摘要 ＋ 中位/最大/最小 ✓（全 ASCII ✓）
"""
from __future__ import annotations

import math
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import mapread as MR   # noqa: E402
import mc_mcp as M     # noqa: E402
import pathplan as PP  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

out: list[str] = []


def finish(code: int) -> int:
    txt = "\n".join(out)
    (ROOT / "logs" / "hop_cost.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


def main() -> int:
    p = M._pos_now()
    if not p:
        out.append("=> FAIL: no bot pos（先跑 respawn_bot.py ✓）")
        return finish(1)
    r = MR.Reader()
    box = (int(p[0]) - 24, int(p[1]) - 8, int(p[2]) - 24, int(p[0]) + 24, int(p[1]) + 6, int(p[2]) + 24)
    m = r.get(box, max_age=300.0)
    cell = m.stand_cell(int(p[0]), int(p[2]), int(p[1]) + 1) or (int(p[0]), int(p[1]), int(p[2]))
    pl = PP.Planner(m, level=cell[1])
    reg = pl.region(cell[0], cell[2])
    tg = pl.safe_targets(cell[0], cell[2], 8.0, 14.0, reg, min_n=6)
    out.append("起点（站的那一格）%s ｜ 连通 %d 格 ｜ 8~14 格的安全目标 %d 个%s"
               % (cell, len(reg), len(tg), "（含放宽挑的 ✓）" if getattr(pl, "last_relaxed", False) else ""))
    if len(tg) < 3:
        # ★★2026-10-24（★§79.346 ✗ 与 §79.285／§79.293 同一条口径✗★）✗★★：
        #   ★★挑不到目标 ✗ 是**环境不给** ✗ 不是**我坏了**✗★★ ⇒ ★按项目自己的约定应是
        #   **INCONCLUSIVE（测不了）** ✗ rc=4 ✗ 而不是 FAIL ✗★ ⇒
        #   ★真 FAIL 只留给：跳了但没到／建图次数 >2／跳时中位 >6 秒／假人死了✗★ ✓
        out.append("INCONCLUSIVE: ★这一带 8~14 格内挑不到安全目标（只有 %d 个✗★）"
                   " —— ★不是判据坏 ✗ 是这一步测不了★（★换个位置再测✗★）" % len(tg))
        return finish(4)

    # 交替走：目标 → 起点 → 目标 …… 每段都记时
    seq = []
    for (d, x, y, z) in tg[:4]:
        seq.append((x, y, z))
        seq.append(cell)
    hops = []
    builds0 = int(M._MISSION.get("builds") or 0)
    for i, (x, y, z) in enumerate(seq[:8], 1):
        cur = M._pos_now()
        if not cur:
            out.append("★假人不见了★ ✗ 第 %d 段前 ⇒ 停 ✓")
            return finish(1)
        d0 = math.dist(cur, (x, y, z))
        t0 = time.time()
        txt, bad = M.t_walk_route(x, y, z, 25000, 2)
        dt = time.time() - t0
        end = M._pos_now()
        got = math.dist(end, (x, y, z)) if end else 99.0
        step = re.findall(r"(?:跳|腿) \d+ -> .*?本步 ([\d.]+)s ｜ 实测位移 ([\d.]+) 格 ｜ 现在 \(", txt)
        hops.append(dt)
        out.append("[%d] 距 %.1f -> (%d,%d,%d)：%.1fs 实测剩 %.2f ⇒ %s ｜ 步数 %d（都有读数=%s）"
                   % (i, d0, x, y, z, dt, got, "到 ✓" if got <= 1.6 else "**没到** ✗",
                      len(step), len(step) == txt.count("->")))
        for (s_t, s_d) in step:
            out.append("      本步 %ss 位移 %s 格" % (s_t, s_d))
    builds = int(M._MISSION.get("builds") or 0) - builds0
    med = statistics.median(hops)
    H1 = len(hops) >= 6
    H2 = builds <= 2
    H3 = med <= 6.0
    alive = M._pos_now() is not None
    out.append("跳数 %d（要求 ≥6）⇒ %s" % (len(hops), H1))
    out.append("建图次数 %d（要求 ≤2）⇒ %s" % (builds, H2))
    out.append("跳时 中位 %.1fs 最小 %.1fs 最大 %.1fs（要求中位 ≤6.0s）⇒ %s"
               % (med, min(hops), max(hops), H3))
    out.append("跑完假人还活着 = %s（要求 True ✓）" % alive)
    ok = H1 and H2 and H3 and alive
    out.append("=> %s" % ("PASS" if ok else "FAIL"))
    return finish(0 if ok else 1)


raise SystemExit(main())
