"""m1_verify.py -- 地图读取的验收（判据先写死 ✓ 用**独立读取**复核 ✓ 不听自己 ✗）

判据 ✓：
  M1 抽查 14 格：图的"层内最高方块"必须与**另一次 1x1 独立读取**逐格一致（要求 14/14 ✓）
     ＋ 抽查它上面第一格：图说"空"就必须真空 ✓（图说"被占"就必须真被占 ✓）
  M2 成本：第一次建图 ≤ 60 次调用 且 ≤ 70 秒 ✓；缓存命中 ≤ 3 秒 ✓
  M3 渲染：ASCII 图非空 ✓ 且**全部是 ASCII** ✓（本项目铁律 ✓）
  M4 覆盖：★口径改过★（2026-09-23 ✓ 见下 ✗）——
     原来写"coverage ≥0.75" ✗ ⇒ 这条**取决于假人站在哪** ✗：
       站在岛心 ⇒ 0.88 ✓ 通过 ✓；站在岛东边 ⇒ 0.72 ✗ 失败 ✗
       —— 而"读数质量"根本没变 ✗ ⇒ ★这是我的判据设计错了 ✗ 不是地图错了 ✗
     现在改成**与位置无关的不变量** ✓：
       M4a 连通区域里的每一格**都必须已知** ✓（不许"我能走但图上没有"✗）
       M4b 未知的格子**都不许判成能站** ✓（不许"图上看不见却说走得过去"✗）
     覆盖率只**报告** ✓ 不再当判据 ✓
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import mapread as MR  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

out: list[str] = []


def main() -> int:
    r = MR.Reader()
    p = r.pos()
    out.append("bot pos = %s" % (p,))
    if not p:
        out.append("=> FAIL: cannot read bot pos")
        return finish(1)
    bx, by, bz = int(p[0]), int(p[1]), int(p[2])
    box = (bx - 12, by - 8, bz - 12, bx + 12, by + 6, bz + 12)
    out.append("box = %s (level=%d)" % (box, by))

    # ── M2a 冷建 ──────────────────────────────────────────────────────────
    r.get(box, force=True)          # 先强制重建一次（不管缓存 ✓）
    m = r.build(box)
    cold_calls, cold_sec = m.meta.get("calls"), float(m.meta.get("sec") or 0)
    out.append("M2a 冷建: calls=%s sec=%.1f" % (cold_calls, cold_sec))

    # ── M2b 缓存 ──────────────────────────────────────────────────────────
    t0 = time.time()
    def walk(m):
        n = 0
        for (x, z) in m.cells():
            if m.standable(x, z, below=by + 1):
                n += 1
        return n
    stands = walk(m)
    sec_walk = time.time() - t0
    t0 = time.time()
    m2 = r.get(box)
    sec_cache = time.time() - t0
    out.append("M2b 缓存命中: %.2fs (from_cache=%s) ｜ 纯遍历 %d 格 = %.3fs ｜ 可站 %d 格"
               % (sec_cache, m2.meta.get("from_cache"), sum(1 for _ in m.cells()), sec_walk, stands))

    # ── M1 抽查 ───────────────────────────────────────────────────────────
    cand = [(x, z) for (x, z) in m.cells() if m.surface(x, z, by + 1)]
    step = max(1, len(cand) // 14)
    picks = cand[::step][:14]
    ok = bad = 0
    for (x, z) in picks:
        y, name = m.surface(x, z, by + 1)
        real = r.block(x, y, z)
        above = r.block(x, y + 1, z)
        # ★"上面空不空"只在**地图声称知道那一格**时才比★ ✗（2026-09-23 实测撞到 ✓）
        #   现象 ✗：假人旁边是 `computercraft:computer_command`（**稀有方块** ✓ 不在 counts 的 top-40 ✓）
        #     ⇒ 地图**根本不知道**它 ✓ ⇒ 按地图自己的语义（未知＝不挡人 ✓ 设计如此 ✓）
        #     ⇒ 我拿它跟"真实上面有方块"比 ⇒ 判"不一致" ✗ —— **判据比地图的口径更严** ✗
        #   ⇒ 规矩 ✓：地图**没声称知道**的格子 ⇒ M1 **不作断言** ✓ 只统计 ✓（并在报告里说清 ✓）
        knows_above = (y + 1) in m.cols.get((x, z), {})
        real_free = above in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air")
        good = (real == name) and ((not knows_above) or (knows_above == (not real_free)))
        ok += 1 if good else 0
        bad += 0 if good else 1
        if not good:
            out.append("   MISMATCH (%d,%d) map=%s@%d knows_above=%s | real=%s above=%s free=%s"
                       % (x, z, name, y, knows_above, real, above, real_free))
    out.append("M1 抽查: %d/%d 一致" % (ok, ok + bad))

    # ── M3 渲染 ───────────────────────────────────────────────────────────
    art = m.ascii(mark=(bx, bz), below=by + 1)
    hgt = m.height_ascii(below=by + 1)
    ascii_ok = all(ord(c) < 128 for c in (art + hgt))
    out.append("M3 渲染: 图 %d 行 ✓ 高差图 %d 行 ✓ 全 ASCII=%s" % (len(art.splitlines()),
                                                                 len(hgt.splitlines()), ascii_ok))

    # ── M4 覆盖（★口径改过 ✓ 与位置无关的不变量 ✓ 见文件头 ✗）────────────────
    cov = m.coverage()
    import pathplan as PP
    pl = PP.Planner(m, level=by + 1)
    reg = pl.region(bx, bz)
    unknown_in_region = [c for c in reg if not m.cols.get(c)]
    unknown_standable = [c for c in m.cells() if (not m.cols.get(c)) and m.standable(c[0], c[1], by + 1)]
    M4a = len(unknown_in_region) == 0
    M4b = len(unknown_standable) == 0
    # ★M4c：防"空集通过"★ ✗（实测 2026-09-23 ✓：连通区算成 **0 格** ⇒ M4a 照样 True ✗）
    #   —— 与 P82（守卫要自己造出"该被拒的场景"）是同一条 ✓：**判据也要防止"没什么可判"**✗
    M4c = len(reg) >= 20
    M4 = M4a and M4b and M4c
    out.append("M4a 连通区 %d 格里未知的 %d 格 ⇒ %s" % (len(reg), len(unknown_in_region), M4a))
    out.append("M4b 未知但被判能站的 %d 格 ⇒ %s" % (len(unknown_standable), M4b))
    out.append("M4c 连通区非空（>=20 格 ✓ 防「空集通过」✗）%d ⇒ %s" % (len(reg), M4c))

    out.append("M4 覆盖（**仅供参考** ✓）: %.3f（unknown=%d 格 ✓ 大多是岛外的虚空 ✓）"
               % (cov, len(m.unknown)))

    out.append("---- 层内图（below=%d）----" % (by + 1))
    out.append(art)
    out.append(m.legend())
    out.append("---- 高差图 ----")
    out.append(hgt)

    M1 = (ok == ok + bad) and len(picks) >= 10
    M2 = (cold_calls or 999) <= 60 and cold_sec <= 70 and sec_cache <= 3.0
    M3 = ascii_ok and len(art.splitlines()) > 3
    out.append("M1 抽查一致 = %s" % M1)
    out.append("M2 成本 = %s（冷 %s 次/%.1fs ✓ 热 %.2fs）" % (M2, cold_calls, cold_sec, sec_cache))
    out.append("M3 渲染 = %s" % M3)
    out.append("M4 覆盖不变量 = %s（M4a %s ｜ M4b %s ｜ M4c %s）" % (M4, M4a, M4b, M4c))
    allok = M1 and M2 and M3 and M4
    out.append("=> %s" % ("PASS" if allok else "FAIL"))
    return finish(0 if allok else 1)


def finish(code: int) -> int:
    txt = "\n".join(out)
    (ROOT / "logs" / "m1_verify.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


raise SystemExit(main())
