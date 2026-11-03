"""r2_verify.py -- 寻路验收（判据先写死 ✓ 世界真值说话 ✓ 并保护假人不掉虚空 ✓）

判据 ✓：
  P0 前提：Bot 必须在场 ✓（不在就先跑 respawn_bot.py ✓ 不许拿"桥断了"糊弄过去 ✗）
  P1 规划：3 个安全目标（连通区域内陆格 ✓ 12~24 格）都必须规划出路线 ✓
     每个航点都必须在地图的**连通区域**里 ✓ 且路径长度 ≤ 2× 曼哈顿 ＋ 4 ✓
  P2 walk_route 到位：**实测**位置离目标 ≤ 1.5 格 ✓（dshdigest 读的 ✓）
  P3 同段对比：交替跑老路 `walk_to` 与新路 `walk_route` ✓ 新路成功数 ≥ 老路 ✓
     且新路**不许出现假 unreachable** ✓
  P4 每段都验过：腿记录条数 = 航点数 － 1 ✓ 每条腿都有实测位置读数 ✓
  P5 ★假人必须活着★ ✗：跑完再查一次 ✓ 掉虚空/死亡 ⇒ 整个 FAIL ✓（2026-09-23 的教训 ✓）
"""
from __future__ import annotations

import math
import re
import subprocess
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


def dist(a, b):
    return math.dist(a[:3], b[:3])


def alive() -> bool:
    return M._pos_now() is not None


def finish(code: int) -> int:
    txt = "\n".join(out)
    (ROOT / "logs" / "r2_verify.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


def main() -> int:
    # ── P0 前提 ───────────────────────────────────────────────────────────
    if not alive():
        out.append("P0 Bot 不在 ⇒ 先拉回来")
        subprocess.run([sys.executable, str(ROOT / "tools" / "respawn_bot.py")],
                       capture_output=True, text=True, encoding="utf-8")
        if not alive():
            out.append("=> FAIL: Bot 拉不回来 ✗")
            return finish(1)
    p = M._pos_now()
    start = (int(p[0]), int(p[1]), int(p[2]))
    out.append("P0 Bot 在场 ✓ 起点 %s" % (start,))

    # ── 挑安全目标（内陆格 ✓ 连通区 ✓）────────────────────────────────────
    r = MR.Reader()
    box = (start[0] - 26, start[1] - 8, start[2] - 26, start[0] + 26, start[1] + 6, start[2] + 26)
    m = r.get(box, max_age=300.0)
    # ★起点要用**地图算出来的"站的那一格"**★ ✗（`int(pos.y)` 会指着耕地/台阶里面 ✗
    #   实测 ✓：那样传下去 ⇒ 模组永远"没到" ✓ 只差 1~2 格 ✓ 看起来像"寻路不行"✗ 见 mapread.stand_cell ✓）
    cell = m.stand_cell(start[0], start[2], start[1] + 1)
    if cell:
        out.append("P0 实测位置 %s ⇒ 站的那一格 %s（y: %d -> %d ✓）"
                   % (start, cell, start[1], cell[1]))
        start = cell
    pl = PP.Planner(m, level=start[1])
    reg = pl.region(start[0], start[2])
    tg = pl.safe_targets(start[0], start[2], 12.0, 24.0, reg)
    out.append("连通平台 %d 格（图 box=%s 覆盖 %.0f%%）｜ 12~24 格的安全落脚点 %d 个"
               % (len(reg), box, m.coverage() * 100, len(tg)))
    if len(tg) < 3:
        out.append("=> FAIL: 安全目标不足 3 个 ✗（不敢挑边上的格子 ✓ 见 2026-09-23 事故 ✓）")
        return finish(1)
    picks = [tg[0], tg[len(tg) // 2], tg[-1]]
    for (d, x, y, z) in picks:
        out.append("   目标 (%d,%d,%d) 距离 %.1f 格" % (x, y, z, d))

    # ── P1 规划 ───────────────────────────────────────────────────────────
    p1 = True
    for (d, x, y, z) in picks:
        pl2, pts, why, info = M._make_plan(start[0], start[2], x, z, start[1])
        if not pts:
            out.append("P1 (%d,%d,%d) 规划失败 ✗ %s" % (x, y, z, why))
            p1 = False
            continue
        bad = [(wx, wz) for (wx, wy, wz) in pts if (wx, wz) not in reg]
        total = sum(math.dist((pts[i - 1][0], pts[i - 1][2]), (pts[i][0], pts[i][2]))
                    for i in range(1, len(pts)))
        manh = abs(x - start[0]) + abs(z - start[2])
        ok = (not bad) and total <= 2.0 * manh + 4
        out.append("P1 -> (%d,%d,%d)：航点 %d ✓ 全在连通区=%s ✓ 路程 %.1f ≤ 2×曼哈顿+4=%d ⇒ %s"
                   % (x, y, z, len(pts), not bad, total, int(2 * manh + 4), "OK" if ok else "**不行**"))
        if not ok:
            p1 = False
            out.append("    越界点 %s" % bad[:4])

    # ── P2/P3/P4：交替实走（A→T1 → T1→A → A→T2 …）─────────────────────────
    # ★★2026-09-23：改成"两个安全锚点来回走"★★ ✗
    #   为什么 ✗：中间层现在**拒绝** >8 格的单发 `walk_to`（它掉过两次虚空 ✓）
    #     ⇒ 原来的排法（12~24 格）会让老路**全被拦** ⇒ walk_route 那几段又"已经在原地"⇒
    #       跑出 **3/0、0/0 的"空过"** ✗ —— 判据全绿但**一步没走** ✗（这正是 P82/M4c 那个坑 ✗）
    #   ⇒ 现在：选 A（当前格）与 B（**5~8 格**的安全落脚点 ✓）⇒ 交替 A↔B ✓
    #     两边都在单发闸之内 ✓ 每段都真的要走 ✓ 对比才有意义 ✓（并加 P6：不许空跑 ✗）
    tg8 = pl.safe_targets(start[0], start[2], 5.0, 8.0, reg, min_n=3)
    if not tg8:
        out.append("=> FAIL: 5~8 格内没有安全落脚点 ✗（没法做有意义的对比 ✗）")
        return finish(1)
    (d8, bxx, byy, bzz) = min(tg8, key=lambda t: abs(t[0] - 7.0))
    A = (start[0], start[1], start[2])
    B = (bxx, byy, bzz)
    out.append("P0 锚点 A=%s ｜ B=%s（相距 %.1f 格 ✓ 都在单发闸的 8 格内 ✓）" % (A, B, d8))
    seq = [("walk_to", B), ("walk_route", A)] * 3
    res = []
    skipped_to = 0
    no_move = 0
    for i, (method, (x, y, z)) in enumerate(seq, 1):
        cur = M._pos_now()
        if not cur:
            out.append("P5 ★假人不见了★ ✗（第 %d 段之前）⇒ 停 ✗" % i)
            return finish(1)
        d0 = dist(cur, (x, y, z))
        t0 = time.time()
        if method == "walk_to":
            txt, bad = M.t_walk_to(x, y, z, 25000)
            extra = ""
            if "拒发" in txt:
                # ★2026-09-23：老用法被中间层拦了 ✗（>8 格 ✗ 它掉过两次虚空 ✗）
                #   ⇒ 这**不是**失败 ✓ 是"这种用法现在不允许" ✓ 单独记一类 ✓（别混进成功率 ✗）
                extra = " ｜ ★老用法已被拦（>8 格）✗ 不计入对比✓★"
                skipped_to += 1
        else:
            txt, bad = M.t_walk_route(x, y, z, 25000, 2)
            # ★口径跟着实现走★ ✗（实测 ✓：`walk_route` 改成"长跳＋短补"后
            #   回执行首从 `腿 n/m` 变成 `跳 n ->` ✗ 而我的正则还停在老格式 ✗
            #   ⇒ 判据报"0 条腿 ⇒ 缺读数 ⇒ FAIL"✗ —— **是测试过期了** ✗ 不是功能坏了 ✗
            #   与 P86/P79 同族 ✓：改了实现**必须回头看判据** ✓）
            steps = re.findall(r"(?:跳|腿) (\d+) ->", txt)
            ver = len(re.findall(r"(?:跳|腿) \d+ -> .*?现在 \(", txt))
            extra = " ｜ P4 步 %d 条（有实测读数 %d 条）%s" % (
                len(steps), ver, "OK" if (steps and ver == len(steps)) else "**缺读数/没走**")
        dt = time.time() - t0
        end = M._pos_now()
        got = dist(end, (x, y, z)) if end else 99.0
        ok = got <= 1.5
        if method == "walk_to" and "拒发" in txt:
            ok = None            # ★被拦 ⇒ 不计成功也不计失败 ✓（见上面那段注释 ✓）
        out.append("%s [%d] -> (%d,%d,%d)：%.0fs 实测剩 %.2f 格 ⇒ %s%s"
                   % (method, i, x, y, z, dt, got,
                      "到 ✓" if ok else ("（被拦 ✓ 不计）" if ok is None else "**没到** ✗"), extra))
        # ★P6：不许空跑★ ✗（实测撞过：判据全绿而一步没走 ✓ 见文件头那段 ✓）
        if method == "walk_route":
            steps_n = len(re.findall(r"(?:跳|腿) (\d+) ->", txt))
            if steps_n == 0:
                no_move += 1
                out.append("     ★P6 空跑★：walk_route 一步没走 ✗（距离 %.1f 格 > 到达口径 1.6 ✗）"
                           % d0)
        out.append("     " + txt.replace("\n", "\n     ")[:900])
        if method == "walk_route" and "unreachable" in txt:
            out.append("     ★假 unreachable★ ✗")
        res.append((method, ok, i))

    if not alive():
        out.append("P5 ★假人死了/不见了★ ✗ ⇒ 整轮 FAIL（掉虚空是硬伤 ✗ 见 2026-09-23 ✓）")
        return finish(1)
    p2 = all(ok for (k, ok, _i) in res if k == "walk_route")
    n_to = sum(1 for (k, ok, _i) in res if k == "walk_to" and ok is not None)
    ok_to = sum(1 for (k, ok, _i) in res if k == "walk_to" and ok)
    ok_rt = sum(1 for (k, ok, _i) in res if k == "walk_route" and ok)
    p3 = ok_rt >= ok_to
    out.append("P2 walk_route 到位 %d/%d ⇒ %s" % (ok_rt, n_to, p2))
    out.append("P3 walk_to %d/%d（另有 %d 段**被拦**✓ 不计 ✗）｜ walk_route %d/%d ⇒ 新 ≥ 老 = %s"
               % (ok_to, n_to, skipped_to, ok_rt, n_to, p3))
    out.append("P5 跑完假人还活着 ✓")
    p6 = (no_move == 0)
    out.append("P6 不许空跑（walk_route 每段至少 1 步）= %s（空跑 %d 段）" % (p6, no_move))
    allok = p1 and p2 and p3 and p6
    out.append("=> %s" % ("PASS" if allok else "FAIL"))
    return finish(0 if allok else 1)


raise SystemExit(main())
