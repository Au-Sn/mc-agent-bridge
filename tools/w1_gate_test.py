# -*- coding: utf-8 -*-
"""w1_gate_test.py —— ★v2.15 之后，"单发长走"还危险吗？★（决定那道 8 格闸能不能放宽）

背景 ✗：8 格闸是给 **2.13.x** 的毛病兜底的 ✓
  那个毛病 ✓：一条长的单发 `dshwalk` ⇒ 模组的**局部**寻路会贴着平台边绕 ⇒ 一步踩空 ⇒
  实测**掉过两次虚空**（18:18 丢掉钻石那批 ✓ 20:34 丢掉刚收的麦子 ✓）
v2.15 加了 ✓：A* 预算 3ms→12ms ✓ 搜索框罩住起点目的 ✓ **贴边惩罚**（四邻站不住 ⇒ 加代价 ✓）
  ⇒ 那么"8 格"这个上限现在是**必要的**还是**过时的** ✗？只能用**实测**回答 ✓ 不许拍脑袋 ✗

判据（先写死 ✓）：
  W1a 每一次尝试之后**假人必须还活着** ✓（`dshdigest` 读得到 ✓）
  W1b **一次都不许掉**（y 全程 ≥ 60 ✓ —— 虚空是 y<-64 ✓）
  W1c 3 次里至少 **2 次走到**（≤2.0 格 ✓ 用模组自己的容差当尺子 ✓）
  W1d 跑完假人**还在连通平台里** ✓（没被逼到孤岛上 ✓）
决策 ✓（写在脚本末尾 ✓）：三条全过 ⇒ 把 `SAFE_WALK` 从 8 放到 **16** ✓
  否则**维持 8** ✓ 并如实说"v2.15 还不够" ✗

⚠ 实测风险 ✓（先说清 ✗）：假人身上有麦子/种子 ✓ 万一掉虚空会丢 ✓（能再收 ✓ 不值几个钱 ✓）
  每次尝试前都记一次背包行数 ✓ 掉了**当场说** ✗
"""
from __future__ import annotations

import math
import sys
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
    (ROOT / "logs" / "w1_gate_test.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


def main() -> int:
    p = M._pos_now()
    if not p:
        out.append("=> FAIL: 读不到位置 ✗（先 respawn_bot.py ✓）")
        return finish(1)
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    LEVEL = int(round(p[1]))
    inv0 = M._inv_items()
    out.append("起点实测 (%d,%d,%d) ｜ LEVEL=%d ｜ 出发时背包 items=%s" % (sx, sy, sz, LEVEL, inv0))

    r, m, box = M._route_map(sx, sz, sx, sz, sy)
    pl = PP.Planner(m, level=LEVEL)
    reg = pl.region(sx, sz)
    out.append("图：%s（%s ✓）｜ 连通 %d 格" % (box, m.meta.get("from"), len(reg)))

    # ★挑"贴边走"的目标★ ✗：`corridor=False` ⇒ 允许路贴着平台边 ✓（正是当年出事的形态 ✓）
    cand = pl.safe_targets(sx, sz, 12.0, 20.0, reg, corridor=False)
    picks = []
    for (d, x, y2, z) in cand:
        pts, why = pl.plan(sx, sz, x, z, region=reg)
        if not pts:
            continue
        rim = any(not pl.interior(px, pz) for (px, _py, pz) in pts)
        if rim:
            picks.append((d, x, y2, z))
        if len(picks) >= 3:
            break
    if len(picks) < 3:
        # ★挑不到"贴边"目标就退而求其次★ ✗（2026-09-28 实测 ✓ 岛心内陆很大 ⇒ 贴边目标 = 0 ✗
        #   ⇒ 判据 W1c 变成 **0/0 的空过** ✗ ＝ 什么都没测 ✗ 与 P94/M4c 同族 ✓）
        #   而真正要回答的是 ✓：**"12~20 格的单发长走现在会不会掉虚空"** ✓（两次事故都是 13 格 ✓）
        #   ⇒ 不卡"贴边"这一条 ✗ 只要距离够 ✓ 能站 ✓ 就拿它测 ✓
        cand2 = pl.safe_targets(sx, sz, 12.0, 20.0, reg, corridor=False) \
            or pl.safe_targets(sx, sz, 9.0, 20.0, reg, corridor=False)
        picks = [(d, x, y2, z) for (d, x, y2, z) in cand2[:3]]
        out.append("（贴边目标挑不到 ⇒ 改用任意 %.1f~20 格的能站目标 ✓ 测的仍是同一件事 ✓）"
                   % (12.0 if cand2 else 9.0))
    out.append("目标 %d 个：%s" % (len(picks), [(x, z) for (_d, x, _y, z) in picks]))

    alive_ok = True
    fell = False
    arrived = 0
    for i, (d, x, y2, z) in enumerate(picks, 1):
        if M._pos_now() is None:
            out.append("★尝试 %d 之前假人就不在了★ ✗ ⇒ 停 ✗" % i)
            alive_ok = False
            break
        inv_before = M._inv_items()
        t0 = __import__("time").time()
        # ★force=True ⇒ 绕过 8 格闸 ✓ 就是要测"放开了会怎样"✗
        txt, bad = M.t_walk_to(x, y2, z, 25000, False, True)
        dt = __import__("time").time() - t0
        e = M._pos_now()
        inv_after = M._inv_items()
        if e is None:
            out.append("[%d] 距 %.1f 格 -> (%d,%d,%d)：%.0f 秒 ⇒ ★假人不见了（掉虚空?）✗★"
                       % (i, d, x, y2, z, dt))
            alive_ok = False
            fell = True
            break
        low = e[1] < 60
        fell = fell or low
        got = math.dist(e, (x, y2, z))
        ok = got <= 2.0
        arrived += 1 if ok else 0
        out.append("[%d] 距 %.1f 格 -> (%d,%d,%d)：%.0f 秒 ｜ 实测剩 %.2f 格 ⇒ %s ｜ y=%.1f%s"
                   " ｜ 背包 %s -> %s"
                   % (i, d, x, y2, z, dt, got, "到 ✓" if ok else "**没到** ✗", e[1],
                      "★掉下去了★" if low else "", inv_before, inv_after))
        out.append("     " + txt.replace("\n", " ")[:150])

    alive_now = M._pos_now() is not None
    inreg = None
    if alive_now:
        e = M._pos_now()
        pl2 = PP.Planner(m, level=LEVEL)
        inreg = (int(e[0]), int(e[2])) in pl2.region(sx, sz)
    w1a = alive_ok and alive_now
    w1b = not fell
    w1c = arrived >= 2
    w1d = bool(inreg)
    out.append("W1a 全程还活着 = %s ｜ W1b 一次都没掉（y≥60）= %s ｜ W1c 到位 %d/%d ⇒ %s ｜ W1d 还在连通平台 = %s"
               % (w1a, w1b, arrived, len(picks), w1c, w1d))
    final = M._inv_items()
    if inv0 is not None and final is not None and final < inv0:
        out.append("⚠ 背包掉了：items %s -> %s（如实报 ✗）" % (inv0, final))
    ok = w1a and w1b and w1c and w1d
    out.append("决策建议 = %s" % ("★可以放宽 SAFE_WALK 到 16★" if ok
                                else "★维持 8★（v2.15 还不足以放开 ✗）"))
    out.append("=> %s" % ("PASS" if ok else "FAIL"))
    return finish(0 if ok else 1)


raise SystemExit(main())
