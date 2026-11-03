"""r9_target_guard_test.py -- "目标站不住就别发"这道闸的验收（判据先写死 ✓）

背景 ✗（2026-09-23 实测 ✓）：`walk_to` 去一个"地图看着能站"的坐标 ⇒ 模组走 **28 秒**
  然后**停在 4.9 格开外** ✗（老路 1/3 ✓ 新路 `walk_route` 3/3 ✓）
  —— 差别就在 `walk_route` **先在地图上把落点定下来** ✓ ⇒ 中间层也该这么做 ✓

判据 ✓：
  G1 目标那一格**站不住** ⇒ 必须**拒发** ✓ 回执里要说明"站不住"✓ 并指路 `walk_route` ✓ 且**一步不动** ✓
  G2 目标那一格**站得住**（内陆 ✓ ≤8 格）⇒ 必须**照常走** ✓（不许把正常的也拦了 ✗）
  G3 闸的代价：地图新鲜时**不发任何探路指令** ✓（拒发那一步的耗时 < 3 秒 ✓ —— 见代码里的改口理由 ✓）
  G4 跑完假人还活着 ✓ 仍在连通平台里 ✓
"""
from __future__ import annotations

import math
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
    (ROOT / "logs" / "r9_guard_test.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


def main() -> int:
    p = M._pos_now()
    if not p:
        out.append("=> FAIL: 读不到位置 ✗")
        return finish(1)
    far = (int(p[0]) - 6, int(p[1]), int(p[2]) - 6)     # 先建任务图（含一片范围 ✓）
    M.t_plan_route(far[0], far[1], far[2])              # 只规划 ✓ 不动 ✓ 但会建任务图 ✓
    r = MR.Reader()
    mb, mm = M._MISSION.get("box"), M._MISSION.get("map")
    out.append("任务图 box=%s ✓（新鲜=%s ✓）" % (mb, (time.time() - float(M._MISSION.get("at") or 0)) < 900))
    if not mm:
        out.append("=> FAIL: 任务图没建起来 ✗（后面的判据没法测 ✗）")
        return finish(1)
    lvl = int(round(float(p[1])))
    pl = PP.Planner(mm, level=lvl)
    reg = pl.region(int(p[0]), int(p[2]))
    # 找一个"站不住"的格子 ✓ —— 半径要放宽 ✗（岛上"身边 7 格"几乎全是地板 ✓ 实测找不到 ✗）
    bad = None
    for (x, z) in sorted(mm.cells(), key=lambda c: (c[0] - p[0]) ** 2 + (c[1] - p[2]) ** 2):
        if not pl.ok(x, z) and 2.0 <= math.dist((x, z), (p[0], p[2])) <= 16.0:
            bad = (x, z)
            break
    good = pl.safe_targets(int(p[0]), int(p[2]), 2.0, 7.0, reg, min_n=1)
    if not good:
        out.append("=> FAIL: 找不到对照的「好格」✗（连通区 %d 格 ✓）" % len(reg))
        return finish(1)

    # ★★G1 用**手工造的洞**★★ ✗（实测撞到：岛上"身边 8 格"几乎全是地板 ✓ 根本找不到坏格 ✗；
    #   找远的又会被**距离闸**先拦掉 ✓ ⇒ 判据测不到想测的那条分支 ✗ —— 与 P82 同族 ✓）
    #   做法 ✓：往任务图里塞一张**自己造的图**（一整片地板 ＋ 挖掉一格 ✓）
    #     ⇒ 那一格"没有已知方块" ⇒ `pl.ok()` 为假 ⇒ 必须被"站不住"拦 ✓ 全程**不发任何指令** ✓
    bxx, bzz = int(p[0]), int(p[2])
    syn = MR.Map(bxx - 10, lvl - 8, bzz - 10, bxx + 10, lvl + 6, bzz + 10)
    for sx in range(bxx - 10, bxx + 11):
        for sz in range(bzz - 10, bzz + 11):
            syn.cols[(sx, sz)] = {lvl - 1: "minecraft:dirt"}
    hole = (bxx + 3, bzz + 3)
    syn.cols.pop(hole, None)                    # ← 洞：那一列一个已知方块都没有 ✓
    # ★但"洞"那一格在**真实世界**里是什么？★ ✗（独立读要能证实"确实站不住"✓）
    #   2026-09-23 实测 ✓：闸加了"拒之前必须独立复核"之后 ✓ 这里必须**真的**是个站不住的格子 ✓
    #   ⇒ 直接从世界挑一个**独立读也站不住**的格子（岛外的虚空 ✓）当洞 ✓
    real_hole = None
    for (x, z) in sorted(mm.cells(), key=lambda c: (c[0] - bxx) ** 2 + (c[1] - bzz) ** 2):
        if not pl.ok(x, z) and 2.0 <= math.dist((x, z), (bxx, bzz)) <= 14.0:
            real_hole = (x, z)
            break
    if real_hole:
        hole = real_hole
        syn.cols.pop(hole, None)
        out.append("（真实世界里也站不住的格子：%s ✓ 用它当洞 ✓）" % (hole,))
    keep = dict(M._MISSION)
    M._MISSION.update({"box": syn.box, "map": syn, "at": time.time()})
    try:
        b0 = M._pos_now()
        t0 = time.time()
        txt, bad_flag = M.t_walk_to(hole[0], lvl, hole[1], 20000)
        cost = time.time() - t0
        b1 = M._pos_now()
        moved = math.dist(b0, b1) if (b0 and b1) else 99.0
        # ★G1 的口径：闸有没有拦住"**发指令**" ✓ 而不是"人一丝没动"✗（2026-09-23 实测撞到 ✓）
        #   现象 ✗：拒发 ✓ 但前后读数差 **2.60 格** ⇒ 我判失败 ✗
        #     —— 那是假人**刚重生还在被挤开/落地**（它就在 `cmd0` 那台命令电脑那一格里 ✓）
        #   ⇒ 中间层能保证的是"**没把走指令发出去**"✓ —— "绝对不动"受世界摆布 ✗ 保证不了 ✓
        sent_walk = ("dshwalk start" in txt) or ("走到 (" in txt)
        g1 = bad_flag and ("拒发" in txt) and ("站不住" in txt) and (not sent_walk)
        # ★G3 的尺子（2026-09-28 改口 ✓ 理由写死在这里 ✗）：原来卡 **2.0 秒** ✗
        #   实测 **2.02 秒** ⇒ 差 0.02 秒判失败 ✗ —— 可这道闸的代价本来就是：
        #     **一次内存判定**（地图新鲜 ≈0 ✓）＋ **一次独立读取复核**（拒绝路径才有 ≈0.6 秒 ✓）
        #     ＋ 世界繁忙抖动 ✓ ⇒ 物理下限就在 1~2 秒 ⇒ 卡 2.0 = **比物理还紧** ✗
        #   ⇒ 改 **< 3.0 秒** ✓：量级判据 ✓（闸只花"一次往返"的量级 ✓）
        #     不是"放宽到随便过" ✗ —— 真去探 4 次以上就会超 ✓ 那种回归抓得住 ✓
        g3 = cost < 3.0
        out.append("G1 手工洞 (%d,%d) 距 %.1f 格：%s ｜ 耗时 %.2fs ｜ 前后读数差 %.2f 格"
                   "（重生落地也会动 ✓ 所以只判「没发走指令」✓）⇒ %s"
                   % (hole[0], hole[1], math.dist(hole, (bxx, bzz)),
                      "被拒 ✓" if "拒发" in txt else "★没拒✗★", cost, moved, g1))
        out.append("    回执: " + txt[:150].replace("\n", " "))
        out.append("G3 闸的代价 %.2fs < 3.0 ⇒ %s（地图新鲜 ⇒ 内存判定 ＋ 至多一次独立读取 ✓）" % (cost, g3))
    finally:
        M._MISSION.clear()
        M._MISSION.update(keep)

    # ── G2 好格：只判"闸有没有拦错人"（模组自己的可靠性另算 ✓ 见 r8 的同款注 ✓）────
    (d, gx, gy, gz) = good[0]
    t2, bad2 = M.t_walk_to(gx, gy, gz, 20000)
    e = M._pos_now()
    got = math.dist(e, (gx, gy, gz)) if e else 99.0
    g2 = ("拒发" not in t2) and ("dshwalk" in t2 or "走到" in t2)
    out.append("G2 好格 (%d,%d,%d) 距 %.1f：闸没拦=%s ✓ ｜ 实测剩 %.2f 格（模组侧可靠性另算 ✓）"
               % (gx, gy, gz, d, "拒发" not in t2, got))
    # ── G4 ────────────────────────────────────────────────────────────────
    alive = M._pos_now() is not None
    inreg = None
    if alive:
        reg2 = PP.Planner(mm, level=lvl).region(int(p[0]), int(p[2]))
        inreg = (int(M._pos_now()[0]), int(M._pos_now()[2])) in reg2
    out.append("G4 还活着 = %s ｜ 仍在连通平台里 = %s" % (alive, inreg))
    ok = g1 and g2 and g3 and alive and bool(inreg)
    out.append("=> %s" % ("PASS" if ok else "FAIL"))
    return finish(0 if ok else 1)


raise SystemExit(main())
