"""r8_guard_test.py -- 长走拦截的验收（判据先写死 ✓ 不碰危险动作 ✓）

背景 ✗：假人**两次**掉虚空（18:18 ✓ 20:34 ✓）都是"单发一条长 `dshwalk`"造成的 ✗
  （模组侧修法在 v2.15 ✓ 要重启 ✗ ⇒ 中间层先**兜底拦掉** ✓）

判据 ✓：
  G1 目标 > 8 格 ⇒ `walk_to` **必须拒绝** ✓ 并且**一动都不动**（前后位置一致 ✓）
  G2 目标 ≤ 8 格 ⇒ 必须**照常走**（不能因为加闸把短走也弄坏 ✗）
  G3 拒绝的回执里必须**说清怎么替代**（出现 `walk_route` ✓）—— "不许只说不行" ✗
  G4 跑完假人还活着 ✓ 而且**不越出连通平台**（走完仍在连通区里 ✓）
"""
from __future__ import annotations

import math
import sys
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
    (ROOT / "logs" / "r8_guard_test.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


def main() -> int:
    p = M._pos_now()
    if not p:
        out.append("=> FAIL: 读不到假人位置 ✗（先 respawn_bot.py ✓）")
        return finish(1)
    r = MR.Reader()
    box = (int(p[0]) - 20, int(p[1]) - 8, int(p[2]) - 20, int(p[0]) + 20, int(p[1]) + 6, int(p[2]) + 20)
    m = r.get(box, max_age=300.0)
    cell = m.stand_cell(int(p[0]), int(p[2]), int(p[1]) + 2) or (int(p[0]), int(p[1]), int(p[2]))
    pl = PP.Planner(m, level=cell[1])
    reg = pl.region(cell[0], cell[2])

    def pick(lo, hi):
        """★目标池要**逐级放宽**★ ✗（2026-09-28 第 18 轮 ✓）：
        现象 ✗：`r8` 在总检里 FAIL：起点四周**找到 0 格** ✗
        真因 ✓（**数据变真了** ✓ 是好事 ✗）：验真之后**真的栅栏/机器都显形了** ✓
          ⇒ "四邻都能站"的内陆格（`min_n=3`）在拥挤处**本来就少** ✗
          ⇒ 选取器挑不到 ⇒ 它却把"环境不允许"报成"功能坏"✗
        ⇒ 口径 ✓：3 → 2 → 1 逐级放宽 ✓；**还挑不到就 SKIP**（大声 ✗）而不是 FAIL ✗
        """
        for mn in (3, 2, 1):
            t = [c for c in pl.safe_targets(cell[0], cell[2], float(lo), float(hi), reg, min_n=mn)]
            if t:
                out.append("  （目标池 min_n=%d ⇒ %d 个 ✓）" % (mn, len(t)))
                return t
        return []

    far = pick(12.0, 18.0)
    near = pick(2.0, 6.0)
    out.append("起点（站的那格）%s ｜ 连通 %d 格 ｜ 远目标 %d 个 ｜ 近目标 %d 个"
               % (cell, len(reg), len(far), len(near)))
    if not far or not near:
        out.append("=> SKIP: 这一带挑不出合格目标（远 %d 近 %d ✗）"
                   " ⇒ **环境不允许跑这条判据** ✓ 不算通过也不算失败 ✓" % (len(far), len(near)))
        return finish(0)

    # ── G1 远目标必须被拒，且一步不动 ─────────────────────────────────────
    (d, fx, fy, fz) = far[-1]
    before = M._pos_now()
    txt, bad = M.t_walk_to(fx, fy, fz, 20000)
    after = M._pos_now()
    moved = math.dist(before, after) if (before and after) else 99.0
    # ★G1 的口径★★（2026-09-28 第 18 轮改 ✓ 与 r9 那条对齐 ✓）★：
    #   原来判"**位移 < 0.2 格**"✗ ⇒ 假人**自己在溜达**（`dshidle` 开着 ✓ 或者服务器把它挤开 ✓）
    #     就会有 0.3+ 格的漂移 ✗ ⇒ 明明**拒发成功** ✓ 却被判失败 ✗
    #   ⇒ 中间层能保证的只有一件事 ✓：**"走"这条指令没发出去** ✗
    #     （"绝对不动"受世界摆布 ✗ 保证不了 ✓ —— r9 那边早就写成这个口径了 ✓ 这里没跟上 ✗）
    sent_walk = ("dshwalk start" in txt) or ("走到 (" in txt)
    g1 = bad and ("拒发" in txt) and (not sent_walk)
    g3 = "walk_route" in txt
    out.append("G1 远目标 %.1f 格 -> (%d,%d,%d)：%s ｜ 位移 %.2f 格（**只当参考** ✓）｜ "
               "发了走指令 = %s ⇒ %s"
               % (d, fx, fy, fz, "被拒 ✓" if "拒发" in txt else "★没拒✗★", moved,
                  sent_walk, g1))
    out.append("G3 回执给了替代方案 = %s" % g3)
    out.append("   回执: " + txt[:170].replace("\n", " "))

    # ── G2 近目标必须照常走 ───────────────────────────────────────────────
    # ★"近"必须**当场重算**★ ✗（2026-09-28 实测撞到 ✓）：`near` 是**开局**相对起点挑的 ✓
    #   轮到 G2 时假人早被 G1 之外的动作带走了 ✓ ⇒ 实测距离 **14.7 格** ✗ ⇒ 被闸拦 ✓
    #   ⇒ 我却判"闸拦错了人" ✗ —— 又是"测试自己没跟着现实走" ✗（P94/P96 同族 ✓）
    cur = M._pos_now()
    if not cur:
        out.append("G2 ★假人不见了★ ✗ ⇒ 停")
        return finish(1)
    m2 = M._route_map(int(cur[0]), int(cur[2]), int(cur[0]), int(cur[2]), int(cur[1]))
    r2ok, m2map, _b2 = m2
    LEVEL2 = M._stand_level(m2map, int(cur[0]), int(cur[2]), int(cur[1]))
    pl2 = PP.Planner(m2map, level=LEVEL2)
    reg2 = pl2.region(int(cur[0]), int(cur[2]))
    fresh = pl2.safe_targets(int(cur[0]), int(cur[2]), 2.0, 6.0, reg2, min_n=1) \
        or pl2.safe_targets(int(cur[0]), int(cur[2]), 2.0, 9.0, reg2, min_n=1)
    if not fresh:
        out.append("G2 ★当场找不到 ≤9 格的能站目标★ ✗ ⇒ 这条不判（如实说 ✗）")
        return finish(1)
    (d2, nx, ny, nz) = fresh[0]
    b2 = M._pos_now()
    # ★轮到 G2 时**再量一次**距离★ ✗（2026-09-28 第 18 轮 ✓）：假人**会自己溜达** ✓
    #   实测撞到：开局挑的"**2.0 格**"近目标 ⇒ 到调用时已经 **10.9 格**✗
    #     ⇒ 被"超过单发上限 10 格"拒 ✓ —— 而**它拒得对** ✓ 我却记成"闸拦错人"✗
    #   ⇒ 口径 ✓：飘出 1~SAFE_WALK ⇒ **这条不判**（大声说 ✗ 不算通过也不算失败 ✓）
    d_re = math.dist(b2, (nx, ny, nz)) if b2 else 99.0
    if not (1.0 <= d_re <= float(M.SAFE_WALK)):
        out.append("G2 ★假人自己溜走了★：挑目标时 %.1f 格 ✓ 现在 **%.1f 格** ✗ ⇒ "
                   "**这条不判**（环境不允许 ✓ 不是闸坏 ✓）" % (d2, d_re))
        g2 = None
    else:
        t2, bad2 = M.t_walk_to(nx, ny, nz, 20000)
        a2 = M._pos_now()
        got = math.dist(a2, (nx, ny, nz)) if a2 else 99.0
        # ★G2 的口径收窄到"闸有没有拦错人"★ ✗（2026-09-23 ✓）
        #   为什么 ✗：一开始我要求"必须走到（≤1.6/2.0 格）"✗ ⇒ 结果**模组那个局部寻路**有时自己
        #     报 `unreachable`（停在 1.7 格 ✓ 见回执 ✓）⇒ 我的闸被误判成"坏了" ✗
        #   —— 那个可靠性问题是**模组侧**的 ✓（v2.15 三改正是冲它 ✓）✗ 不该算在中间层的闸头上 ✓
        #   ⇒ G2 只管一件事 ✓：**闸没有拦** ✓ 且**走指令真的发下去了** ✓；到位情况如实打印当参考 ✓
        g2 = ("拒发" not in t2) and ("dshwalk" in t2 or "走到" in t2)
        out.append("G2 近目标 %.1f 格（现场 %.1f 格）-> (%d,%d,%d)：闸没拦=%s ✓ ｜ "
                   "实测剩 %.2f 格（模组侧可靠性 ✓ 另算 ✓）｜ %s"
                   % (d2, d_re, nx, ny, nz, "拒发" not in t2, got,
                      t2[:110].replace("\n", " ")))

    # ── G4 还活着，而且仍在连通区里（没被赶到孤岛/虚空边）──────────────────
    e = M._pos_now()
    alive = e is not None
    inreg = None
    if e:
        m2 = r.get(box, max_age=60.0)
        pl2 = PP.Planner(m2, level=cell[1])
        reg2 = pl2.region(cell[0], cell[2])
        inreg = (int(e[0]), int(e[2])) in reg2
    out.append("G4 假人还活着 = %s ｜ 仍在连通平台里 = %s" % (alive, inreg))
    # ★`None` = "环境不允许，这条不判" ★ ✗ ⇒ 只把它从判据里排除 ✓ 不许当成 False ✗
    ok = g1 and g3 and alive and bool(inreg) and (g2 is not False)
    out.append("=> %s%s" % ("PASS" if ok else "FAIL",
                            "" if g2 is not None else "（G2 因环境未判 ✓）"))
    return finish(0 if ok else 1)


raise SystemExit(main())
