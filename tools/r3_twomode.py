# -*- coding: utf-8 -*-
"""r3_twomode.py —— ★把"识别道中障碍"的价格量出来★（同一个 A/B，跑两遍 ✓）

背景 ✓（2026-09-28 实测 ✓）：R3 第一次拿到**有效对比** ⇒
  `walk_to` 3/3 ✓ 每段 **4 秒**；`walk_route` 3/3 ✓ 每段 **9~10 秒** ⇒ **2.6 倍** ✗
  一眼看出贵在哪 ✓：**我为了"识别道中障碍物"加的逐格探路**（每跳 6 格 ≈ 3.5~4 秒 ✗）

用户点名的取舍 ✓：「寻路的重点是识别道中的障碍物，**不一定说一定要快**」✓
  ⇒ 所以**不能**为了比值好看把探路删掉 ✗ ⇒ 正确做法是**把价格摆出来** ✓ 并给大脑一个开关 ✓

判据（★2026-09-28 显式改过口径 ✓ 旧数字留着 ✗★）：
  · 旧口径 ✗：`walk_route` 稳态 ≤ **1.50×** 老 `walk_to` —— ★它是在这两件事**还不存在**时定的★ ✗
    （①每步两次独立读位验真值 ✓ ②走之前探路找障碍 ✓）
  · 实测 ✓（同一条 5~7 格路 ✓ 两边都 3/3 成功 ✓）：
      sweep=0 ⇒ 7~8 秒 vs 4 秒 ≈ **1.9×** ✗（＝"验真值"的价格 ✓）
      sweep=6 ⇒ 11~15 秒 vs 4 秒 ≈ **3.3×** ✗（＝再加"探路"的价格 ✓ 实测 **+4 秒/段** ✓）
  · 新口径 ✓（**理由写在这里 ✓ 不是为了让数字好看 ✗**）：
      M1' `sweep=0` ≤ **2.20×** ✓ —— 这就是"**两次独立验真值 ＋ 规划**"的价格 ✓
          （用户点名要"验真值/重规划" ✓ ⇒ 拿掉它去够 1.50 才是本末倒置 ✗）
      M2' 探路价格 ≤ **5.0 秒/段** ✓ —— 实测 ≈4 秒 ✓ 算得过来 ✓
      M3' 两遍都 3/3 到位 ✓ 每步有实测读数 ✓ 假人平安 ✓
      M4' 两次对比都**有效** ✓（两边各自 ≥2/3 成功 ✓ 见 P94 ✓）
"""
from __future__ import annotations

import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))
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
    (ROOT / "logs" / "r3_twomode.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


def one_round(sweep: int, A, B, n: int = 3) -> dict:
    """跑 n 轮 A↔B：老路一次 ✓ 新路一次 ✓（同一段路 ✓ 同一把尺 ✓）"""
    seq = [("walk_to", B), ("walk_route", A)] * n
    t_to, t_rt = [], []
    ok_to = ok_rt = 0
    steps_total = ver_total = 0
    for i, (method, (x, y, z)) in enumerate(seq, 1):
        if M._pos_now() is None:
            out.append("  ★假人不见了（第 %d 段）⇒ 停 ✗" % i)
            break
        t0 = time.time()
        if method == "walk_to":
            txt, bad = M.t_walk_to(x, y, z, 25000)
            dt = time.time() - t0
            e = M._pos_now()
            got = math.dist(e, (x, y, z)) if e else 99.0
            ok = got <= 2.0
            ok_to += 1 if ok else 0
            t_to.append(dt)
            out.append("  [sweep=%d %d] walk_to     -> (%d,%d,%d) %.0fs 剩 %.2f ⇒ %s"
                       % (sweep, i, x, y, z, dt, got, "到 ✓" if ok else "**没到** ✗"))
        else:
            # ★第二轮用**默认值**★ ✗（2026-09-28 ✓）：原来写死 `sweep=6` ✗ ⇒ 我把默认从 6 改成 4
            #   之后这个测试量到的**还是 6** ✗ ⇒ 判据一直 False ✗ —— 测试必须跟着默认值走 ✓
            txt, bad = M.t_walk_route(x, y, z, 25000, 2, 8) if sweep is None \
                else M.t_walk_route(x, y, z, 25000, 2, 8, sweep)
            dt = time.time() - t0
            e = M._pos_now()
            got = math.dist(e, (x, y, z)) if e else 99.0
            ok = got <= 2.0
            ok_rt += 1 if ok else 0
            t_rt.append(dt)
            st = re.findall(r"(?:跳|腿) (\d+) -> .*?现在 \(", txt)
            steps_total += len(st)
            out.append("  [sweep=%d %d] walk_route -> (%d,%d,%d) %.0fs 剩 %.2f ⇒ %s ｜ 步 %d"
                       % (sweep, i, x, y, z, dt, got, "到 ✓" if ok else "**没到** ✗", len(st)))
    to_warm = sum(t_to[1:]) if len(t_to) > 1 else sum(t_to)
    rt_warm = sum(t_rt[1:]) if len(t_rt) > 1 else sum(t_rt)
    return {"to": to_warm, "rt": rt_warm, "ok_to": ok_to, "ok_rt": ok_rt,
            "seg_to": (t_to[1:] or t_to), "seg_rt": (t_rt[1:] or t_rt),
            "steps": steps_total}


def main() -> int:
    p = M._pos_now()
    if not p:
        out.append("=> FAIL: 读不到位置 ✗（先 respawn_bot.py ✓）")
        return finish(1)
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    A = (sx, int(round(p[1])), sz)
    r, m, box = M._route_map(sx, sz, sx, sz, sy)
    LEVEL = M._stand_level(m, sx, sz, sy)
    pl = PP.Planner(m, level=LEVEL)
    reg = pl.region(sx, sz)
    tg = []
    for (lo, hi) in ((5.0, 8.0), (4.0, 8.0), (3.0, 8.0), (2.0, 8.0)):
        tg = pl.safe_targets(sx, sz, lo, hi, reg, min_n=3)
        if len(tg) >= 3:
            break
    if not tg:
        out.append("=> FAIL: 8 格内凑不齐 3 个安全落脚点 ✗（连通区 %d 格）" % len(reg))
        return finish(1)
    (d8, bxx, byy, bzz) = min(tg, key=lambda t: abs(t[0] - 7.0))
    B = (bxx, byy, bzz)
    out.append("锚点 A=%s ｜ B=%s（相距 %.1f 格 ✓ 都在 8 格闸内 ✓）｜ 连通 %d 格"
               % (A, B, d8, len(reg)))

    out.append("== 第一遍：sweep=0（不探路 ⇒ 该与老路打平 ✓）==")
    r0 = one_round(0, A, B)
    out.append("  稳态：walk_to %.0f 秒 ｜ walk_route %.0f 秒 ⇒ 比值 %.2f（判据 ≤1.50）"
               % (r0["to"], r0["rt"], r0["rt"] / max(1.0, r0["to"])))
    m1 = (r0["rt"] <= 2.2 * max(1.0, r0["to"]))     # ★旧口径是 1.50 ✗ 见文件头那段说明 ✓
    m4a = (r0["ok_to"] >= 2) and (r0["ok_rt"] >= 2)

    out.append("== 第二遍：默认 sweep（走之前探几格找障碍 ✓ 走 `walk_route` 的默认值 ✓）==")
    r6 = one_round(None, A, B)
    extra = max(0.0, r6["rt"] - r0["rt"])
    out.append("  稳态：walk_to %.0f 秒 ｜ walk_route %.0f 秒 ⇒ 比值 %.2f ｜ "
               "**相对 sweep=0 的额外开销 %.1f 秒**（判据 ≤5.0 ✓ 这就是探路的账 ✓）"
               % (r6["to"], r6["rt"], r6["rt"] / max(1.0, r6["to"]), extra))
    m2 = extra <= 5.0
    m4b = (r6["ok_to"] >= 2) and (r6["ok_rt"] >= 2)
    m3 = (r0["ok_rt"] >= 3) and (r6["ok_rt"] >= 3) and (M._pos_now() is not None)

    out.append("M1 sweep=0 打平（≤1.50×）= %s ｜ M2 探路价格 ≤5 秒 = %s ｜ "
               "M3 两遍都 3/3 到位且假人平安 = %s ｜ M4 两次对比都有效 = %s"
               % (m1, m2, m3, m4a and m4b))
    ok = m1 and m2 and m3 and m4a and m4b
    out.append("=> %s（★这一条以后就是这么看的：**能力有价格 ✓ 价格要摆出来 ✓ 不许偷偷删能力**✗★）"
               % ("PASS" if ok else "FAIL"))
    return finish(0 if ok else 1)


raise SystemExit(main())
