"""r2_guard_test.py -- 虚空守卫的**确定性**自测（手工造图 ✓ 与游戏无关 ✓）

为什么必须手工造图 ✗：上一版我用真地图跑 ✓ 结果那张图里**恰好没有孤岛** ✗
  ⇒ "拒绝孤岛"那条根本没被测到 ✓ 却打印了 True ✓（这叫**假通过** ✗ 比失败更坏 ✗）
  ⇒ 纪律：**守卫的测试必须自己造出"该被拒的场景"** ✓ 不能指望现实刚好给你 ✗

判据（事先写死）：
  G1 手工图：3x3 平台 ＋ 隔 2 格虚空的一块孤岛 ⇒ 连通区域必须**不含**孤岛 ✓
  G2 规划到孤岛 ⇒ **必须被拒** ✓ 且原因里含"连通"或"虚空" ✓
  G3 interior()：平台正中为 True ✓ 平台边上为 False ✓
  G4 safe_targets()：只返回内陆格 ✓ 且数量 > 0 ✓
  G5 真图抽查：假人脚下这块区域里，内陆格数量 > 20 ✓（有没有地方可去 ✓）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import mapread as MR   # noqa: E402
import pathplan as PP  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

out: list[str] = []


def synth(size: int = 3) -> MR.Map:
    """`size`x`size` 平台在 (0..size-1, 0..size-1) ✓；孤岛一格在 (size+3, size+3) ✓
    中间全是虚空（= 图里没有方块 ✓）
    """
    m = MR.Map(0, 60, 0, size + 5, 70, size + 5)
    for x in range(0, size):
        for z in range(0, size):
            m.cols[(x, z)] = {64: "minecraft:stone"}
    m.cols[(size + 3, size + 3)] = {64: "minecraft:stone"}
    return m


def main() -> int:
    m = synth()
    pl = PP.Planner(m, level=65)
    reg = pl.region(1, 1)
    out.append("手工图：能站 %d 格 ｜ 与 (1,1) 连通 %d 格" % (len(m.cols), len(reg)))
    out.append("连通区 = %s" % sorted(reg))
    G1 = ((6, 6) not in reg) and ((1, 1) in reg) and len(reg) == 9
    p, why = pl.plan(1, 1, 6, 6)
    out.append("规划到孤岛 (6,6) -> %s" % ("★有路?! 守卫没拦住★" if p else why))
    G2 = (p is None) and (("连通" in why) or ("虚空" in why))
    G3 = pl.interior(1, 1) and (not pl.interior(0, 0)) and (not pl.interior(1, 2))
    # ★G4 换了口径★ ✗：加了"安全走廊"之后，3x3 平台里**没有再往里一格**的落脚点 ✓
    #   ⇒ 用 5x5 平台测：内陆格 9 个（正中 3x3 ✓）⇒ 出发点自己不算 ⇒ 应该正好 8 个 ✓
    m5 = synth(5)
    pl5 = PP.Planner(m5, level=65)
    reg5 = pl5.region(2, 2)
    tg5 = pl5.safe_targets(2, 2, 0.0, 9.0, reg5)
    G4 = (len(tg5) == 8) and all(pl5.interior(t[1], t[3]) for t in tg5)
    # 顺带：走廊模式下 3x3 应该**给不出**目标 ✓（因为无处可退 ✓ 少给总比给错的强 ✓）
    tg3 = pl.safe_targets(1, 1, 0.0, 9.0, reg)
    out.append("G4-corridor：5x5 平台给出 %d 个安全落脚点 ✓ 3x3 平台给出 %d 个（应为 0 ✓）"
               % (len(tg5), len(tg3)))
    G4 = G4 and (len(tg3) == 0)
    out.append("G1 连通不含孤岛 = %s" % G1)
    out.append("G2 拒绝孤岛 = %s" % G2)
    out.append("G3 interior 判得对 = %s（正中 %s ｜ 角 %s ｜ 边 %s）"
               % (G3, pl.interior(1, 1), pl.interior(0, 0), pl.interior(1, 2)))
    out.append("G4 safe_targets = %s（%s）" % (G4, tg5))

    # ── G5 真图抽查 ───────────────────────────────────────────────────────
    cs = sorted((ROOT / "logs" / "map_cache").glob("map_*.json"), key=lambda q: q.stat().st_mtime)
    G5 = False
    if cs:
        d = json.loads(cs[-1].read_text(encoding="utf-8"))
        m2 = MR.Map(*d["box"])
        m2.meta = d.get("meta", {})
        for k, v in d["cols"].items():
            x, z = (int(t) for t in k.split(","))
            m2.cols[(x, z)] = {int(y): b for y, b in v.items()}
        lvl = 71
        pl2 = PP.Planner(m2, level=lvl)
        stand = [c for c in m2.cells() if pl2.ok(*c)]
        if stand:
            s = min(stand, key=lambda c: (c[0] - 4119) ** 2 + (c[1] - 9) ** 2)
            reg2 = pl2.region(*s)
            intr = [c for c in reg2 if pl2.interior(*c)]
            G5 = len(intr) > 20
            out.append("G5 真图：box=%s 起点 %s 连通 %d 格 ｜ 内陆 %d 格 ⇒ %s"
                       % (m2.box, s, len(reg2), len(intr), G5))
            out.append("   真图 safe_targets(6~24 格) = %d 个" % len(pl2.safe_targets(s[0], s[1], 6, 24, reg2)))
    ok = G1 and G2 and G3 and G4 and G5
    out.append("=> %s" % ("PASS" if ok else "FAIL"))
    txt = "\n".join(out)
    (ROOT / "logs" / "r2_guard_test.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return 0 if ok else 1


raise SystemExit(main())
