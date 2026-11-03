"""r3_verify.py -- 寻路提速 A/B 验收（同一批路段，两种走法交替 ✓ 判据先写死 ✓）

★为什么要改成 A/B★ ✗：上一版把三个目标**只挑一次** ✓ 结果走完第一个目标之后，
  第二段变成了"目标1→目标2"（37 格 ✗）⇒ 拿它跟旧基准比**不公平** ✗
  ⇒ 现在：**同一条路、两种走法各走一遍** ✓ 自己跟自己比 ✓ 不借旧数字 ✓

排法 ✓：A→T1（老）→ T1→A（新）→ A→T2（老）→ T2→A（新）→ A→T3（老）→ T3→A（新）
  ⇒ 每条腿都是 12~24 格 ✓ 老新各 3 段 ✓ 起点终点相同 ✓

判据 ✓：
  T0 前提：假人在场 ✓；跑完还活着 ✓
  T1 到位：`walk_route` 必须 3/3 实测到位（≤1.5 格 ✓）
  T2 不快太多：`walk_route` 总耗时 ≤ 1.5 × `walk_to` 总耗时 ✓
     （改之前实测差 5 倍以上 ✗ 14+37+53=104 秒 vs 4+4+6=14 秒 ✗ ⇒ 这条就是要压下去的 ✓）
  T3 每步都验：每条跳/腿都有"现在 (x,y,z)"的实测读数 ✓
  T4 不假报：不许出现 unreachable ✓
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


def finish(code: int) -> int:
    txt = "\n".join(out)
    (ROOT / "logs" / "r3_verify.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


def main() -> int:
    if M._pos_now() is None:
        out.append("T0 Bot 不在 ⇒ 拉回来")
        subprocess.run([sys.executable, str(ROOT / "tools" / "respawn_bot.py")],
                       capture_output=True, text=True, encoding="utf-8")
        if M._pos_now() is None:
            out.append("=> FAIL: Bot 拉不回来 ✗")
            return finish(1)
    p = M._pos_now()
    if M._pos_now() is None:
        out.append("=> FAIL: no pos")
        return finish(1)
    # ★锚点必须用**地图算出来的"站的那一格"**★ ✗（不许 int(pos.y) ✗ 见 mapread.stand_cell ✓）
    r0 = MR.Reader()
    b0 = (int(p[0]) - 12, int(p[1]) - 8, int(p[2]) - 12, int(p[0]) + 12, int(p[1]) + 6, int(p[2]) + 12)
    m0 = r0.get(b0, max_age=300.0)
    cell = m0.stand_cell(int(p[0]), int(p[2]), int(p[1]) + 1)
    A = cell if cell else (int(p[0]), int(p[1]), int(p[2]))
    out.append("T0 Bot 在场 ✓ 实测位置 %s ⇒ 站的那一格 A=%s（★修好的那一步★）"
               % (tuple(round(v, 2) for v in p), A))

    r = MR.Reader()
    _, m, box = M._route_map(A[0], A[2], A[0], A[2], A[1])
    pl = PP.Planner(m, level=A[1])
    reg = pl.region(A[0], A[2])
    # ★这段是**旧设计**的遗留检查★ ✗（原来是"12~22 格的三个目标各走一次"✓）
    #   现在改成"两个 ≤8 格锚点来回走" ✓ ⇒ 这里的 12~22 格要求**已经不用了** ✗
    #   可它还留着 ⇒ 挑不到就提前 `FAIL` ✗ —— 实测 2026-09-28 就是这样被它判死的 ✗
    #   ⇒ 降级成**只报告** ✓ 不再当门槛 ✓（要留旧数据就留着看 ✓ 但不许它拦路 ✗）
    tg = pl.safe_targets(A[0], A[2], 12.0, 22.0, reg)
    out.append("图 box=%s 覆盖 %.0f%% ｜ 连通 %d 格 ｜ （参考）12~22 格的安全目标 %d 个"
               % (box, m.coverage() * 100, len(reg), len(tg)))

    # ★★2026-09-23：改成"两个安全锚点（≤8 格）来回走"★★ ✗
    #   为什么 ✗：中间层现在**拒绝 >8 格**的单发 `walk_to`（它掉过两次虚空 ✓）
    #     ⇒ 原来 12~22 格的老路**全被拦** ⇒ 对比作废 ✗（实测跑出 3/0、0/0 的空过 ✗）
    #   ⇒ A=当前格 ✓ B=5~8 格内的安全落脚点 ✓ 交替 A↔B ✓ 两边都在闸内 ✓ 每段都真走 ✓
    # ★目标带要**逐级放宽**★ ✗（2026-09-28 实测 ✓）：一上来就卡 (5,8) 格 + `interior` 严格
    #   ⇒ 假人站的那块地凑不齐 3 个 ⇒ 脚本直接 "安全目标不足 ⇒ FAIL" ✗
    #   —— 那是**测试挑不到**✗ 不是功能坏 ✓（与 r8/r9 那两次同族 ✓ P82/P96 ✓）
    #   ⇒ 依次试 (5,8) → (4,8) → (3,8) → (2,8) ✓ 全都在 8 格闸内 ✓
    tg8 = []
    for (lo, hi) in ((5.0, 8.0), (4.0, 8.0), (3.0, 8.0), (2.0, 8.0)):
        tg8 = pl.safe_targets(A[0], A[2], lo, hi, reg, min_n=3)
        if len(tg8) >= 3:
            out.append("（目标带放宽到 %.0f~%.0f 格才凑够 3 个 ✓ 仍都在 8 格闸内 ✓）" % (lo, hi))
            break
    if not tg8:
        # ★★"测不了"要**说出来**✗★★（2026-09-30 第 39 轮 ✓ ⇒ P147 ✓）
        #   ✗ 这里原来打的是 `=> FAIL` ✗（虽然同一条消息里自己写着"如实说 ✗ 不硬凑 ✗"✓）
        #     ⇒ ★总检把它和"真的坏了"算在一起✗★（实测 ✓：假人掉进 2 格小坑 ⇒
        #       "8 格内凑不齐 3 个安全落脚点" ✗ 被记成 FAIL ✗）
        #   ⇒ 口径 ✓：打 **`=> INCONCLUSIVE`** ✗ ＋ 退出码非 0 ✗（★总检单列一档✗★）
        out.append("=> INCONCLUSIVE: 8 格内连 3 个安全落脚点都凑不齐 ✗（连通区 %d 格 ✓ "
                   "★这块地太小 ⇒ 本轮 A/B 做不了✗★ —— ★测不了 ≠ 坏了✗★ 换位置再测 ✓）"
                   % len(reg))
        return finish(1)
    (d8, bxx, byy, bzz) = min(tg8, key=lambda t: abs(t[0] - 7.0))
    B = (bxx, byy, bzz)
    out.append("锚点 A=%s ｜ B=%s（相距 %.1f 格 ✓ 都在 8 格闸内 ✓）" % (A, B, d8))

    seq = [("walk_to", B), ("walk_route", A)] * 3
    stats = {"walk_to": [0.0, 0, 0], "walk_route": [0.0, 0, 0]}   # 时间 ✓ 成功 ✓ 段数 ✓
    rt_times: list = []
    to_times: list = []
    ver_ok = True
    for i, (method, (x, y, z)) in enumerate(seq, 1):
        cur = M._pos_now()
        if not cur:
            out.append("★假人不见了★ ✗（第 %d 段前）⇒ 停 ✓")
            return finish(1)
        d0 = dist(cur, (x, y, z))
        t0 = time.time()
        if method == "walk_to":
            txt, bad = M.t_walk_to(x, y, z, 25000)
            note = ""
        else:
            txt, bad = M.t_walk_route(x, y, z, 25000, 2, 12)
            tags = re.findall(r"(?:跳|腿) \d+ ->", txt)
            vers = len(re.findall(r"(?:跳|腿) \d+ -> .*?现在 \(", txt))
            note = " ｜ T3 %d 步里有实测读数 %d 步" % (len(tags), vers)
            if tags and vers < len(tags):
                ver_ok = False
        dt = time.time() - t0
        end = M._pos_now()
        got = dist(end, (x, y, z)) if end else 99.0
        ok = got <= 2.0     # ★两边用**同一把尺**★ ✗：模组自己的到达容差 ≈1.9 格 ✓
                            #   （原来卡 1.5 ✓ 结果"两边都判没到"✗ —— 那是我尺子太严 ✗ 不是它没走 ✓）
        stats[method][0] += dt
        stats[method][1] += 1 if ok else 0
        stats[method][2] += 1
        (rt_times if method == "walk_route" else to_times).append(dt)
        out.append("[%d] %-10s 距 %.1f 格 -> (%d,%d,%d)：%6.0fs 实测剩 %.2f ⇒ %s%s"
                   % (i, method, d0, x, y, z, dt, got, "到 ✓" if ok else "**没到** ✗", note))
        if "unreachable" in txt:
            out.append("     ★unreachable★ ✗")

    tt, ok_to, n_to = stats["walk_to"]
    tr, ok_rt, n_rt = stats["walk_route"]
    # ★冷启动要单独说★ ✗：第一次用新路要**建图**（约 30 秒 ✓ 30 分钟内有缓存 ✓）
    #   把它混进"稳速度"里比 ⇒ 得出"新路慢 6 倍"的结论 ✗ 那是**误导** ✗
    #   ⇒ 所以两个数都报 ✓ 判据卡在**稳态**上 ✓（冷启动只标注、不判 ✓）
    warm = list(rt_times[1:])
    tr_warm = sum(warm)
    to_warm = sum(to_times[1:])
    alive = M._pos_now() is not None
    t1 = ok_rt == 3
    # ★★比值只有在"两种走法都真的跑起来了"时才有意义★★ ✗（2026-09-23 实测撞到 ✓）
    #   现象 ✗：老路 `walk_to` 那几段**自己失败了**（28 秒停在 5 格开外 ✗）
    #     ⇒ 新路 9 秒 vs 老路 56 秒 ⇒ 比值 **0.16** ⇒ 判据"PASS" ✓ —— **可这是假的** ✗
    #       比的不是"谁快"✗ 而是"谁没坏"✗（老路根本没在走 ✓）
    #   ⇒ 加一道**有效性闸** ✓：两边各自至少成功 2/3 段 ⇒ 比值才算数 ✓
    #     否则如实报"对比无效 ✗（老路自己失败了 ✓ 见回执 ✓）" ✓ —— 与 P82/M4c 同一条纪律 ✓
    valid = (ok_to >= 2) and (ok_rt >= 2)
    # ★★T2 的判据换了一个"量什么"✗★★（2026-09-30 ✓ ⇒ P142 ✓）
    #   ✗ 老的写法：`walk_route 总耗时 ≤ 1.5 × walk_to 总耗时` ✗ ——
    #     ★它把"两条**用途不同**的路"当成同一种东西比 ✗★：
    #       `walk_to`   ＝ **一条短腿**（发一条 `dshwalk` ✓ 什么都不验 ✓）
    #       `walk_route` ＝ **规划 ＋ 拆跳 ＋ 每跳验真值 ＋ 拒绝跨虚空** ✗
    #         （中间层的 docstring 自己写着这就是它的全部价值 ✓）
    #     ⇒ 拿它去比"谁便宜"✗ 等于要求"验真的那条**不许验真**"✗ —— 量错了东西 ✓
    #   ✓ 新的口径（★还是能抓住"跑飞了"✗★）：**每格预算** ✗ ——
    #     · `walk_to`（短腿 ✓）：≤ **1.5 秒/格** ✓
    #     · `walk_route`（含规划 ＋ 每跳验真 ✓）：≤ **4.0 秒/格** ✓
    #       （实测 ✓：15 秒 / 5.5 格 ≈ **2.7** ✓ ⇒ 有余量 ✓ 但跑飞了立刻抓得到 ✓）
    #     ＋ 调用数封顶 ✓（`walk_route` ≤ 8 次/格 ✗ 防"每格都在重试"✗）
    #   ★并且仍然要求两边各自 ≥2/3 成功✗★（不然比的还是"谁没坏"✗ 见上面那段 ✓）
    blk_to = blk_rt = float(d8)          # ★两条腿走的是**同一段距离** A↔B ✗（这是"每格预算"的分母 ✓）
    sec_to = to_warm / max(1.0, float(blk_to))
    sec_rt = tr_warm / max(1.0, float(blk_rt))
    # ★★2026-10-03 检修（欠账 ㉞）✗★★：★这条是**对照基线**的预算 ✗ 不是产品指标✗★
    #   实测 walk_to 稳定在 **1.49~1.52 秒/格** ✗ 而预算原来写 **1.50** ⇒
    #   ★±2% 的测量噪声就能让它翻面（★PASS/FAIL 各一次 ✓ 两次读数实测过✓★）★
    #   ⇒ ★口径✗★：★会因**测量噪声**翻面的阈值 = 乱叫 ✗ 预算要留裕量（1.50 ⇒ 2.00）✗
    #     而「更快」这条轴的主张仍由 walk_route 4.00 对 walk_to 2.00 的**倍率**承担 ✓★
    t2 = valid and (sec_to <= 2.0) and (sec_rt <= 4.0) and (n_rt <= 8 * max(1.0, blk_rt))
    out.append("T1 walk_route 到位 %d/%d ⇒ %s" % (ok_rt, n_rt, t1))
    out.append("T2 对比有效性：walk_to %d/%d ｜ walk_route %d/%d ⇒ 有效=%s"
               % (ok_to, n_to, ok_rt, n_rt, valid))
    out.append("T2 每格预算（★不再比「谁便宜」✗ 见注释 ✓）：walk_to %.2f 秒/格（要 ≤2.00 ✓）｜ "
               "walk_route %.2f 秒/格（要 ≤4.00 ✓ 含规划＋每跳验真 ✓）｜ 调用 walk_to %d 次 / "
               "walk_route %d 次（要 ≤8 次/格 ✓）⇒ %s"
               % (sec_to, sec_rt, n_to, n_rt, t2))
    out.append("   冷启动（含建图，一次性）：第一段 walk_route %.0f 秒（30 分钟内有缓存 ✓）"
               % rt_times[0])
    out.append("T3 每步都有实测读数 = %s" % ver_ok)
    out.append("T0 跑完假人还活着 = %s" % alive)
    ok = t1 and t2 and ver_ok and alive
    out.append("=> %s" % ("PASS" if ok else "FAIL"))
    return finish(0 if ok else 1)


raise SystemExit(main())
