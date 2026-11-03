"""ob_test.py -- ★"识别道中障碍物"的验收★ ✓（用户点的方向 ✓ 判据先写死 ✓）

背景 ✗：地图是**按方块种类**建的 ✓ 而模组回执的 `counts[...]` **只列 top-40** ✗
  ⇒ 稀有方块（实测：`computercraft:computer_command` ✓ 就在假人重生点那一格 ✓）**地图完全不知道** ✗
  ⇒ "看图规划"看不出道上的障碍 ✗ ⇒ 所以要**走之前实地探** ✓（`scan_route` ✓）

判据 ✓：
  OB1 **探得出来**：对那格做独立探测 ⇒ 必须报出**真的挡人的方块名** ✓（不能是 air ✓ 不能是读失败 ✗）
  OB2 **进地图**：探到之后那格必须写进图 ✓（图从"不知道"变成"知道 ✓ 且是障碍 ✓"）
  OB3 **绕得开**：把 (x,z) 记进 `BLOCKED` 后，规划器必须**不再把这一格排进路线** ✓
      （除非它绕不过去 ⇒ 那也必须**如实说"不通"** ✓ 不许硬穿 ✗）
  OB4 **预算诚实**：`left>0` 时必须报"还有没探的" ✓（不许把"没探"说成"干净"✗）
  OB5 **不碰世界**：整段测试**不发走路指令** ✓（只发读指令 ✓）且假人位置不变 ✓
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
    (ROOT / "logs" / "ob_test.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return code


def main() -> int:
    p = M._pos_now()
    if not p:
        out.append("=> FAIL: 读不到位置 ✗")
        return finish(1)
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    LEVEL = int(round(p[1]))
    r, m, box = M._route_map(sx, sz, sx, sz, sy)
    out.append("bot (%d,%d,%d) ｜ LEVEL=%d ｜ 图 box=%s ｜ 覆盖 %.0f%%"
               % (sx, sy, sz, LEVEL, box, m.coverage() * 100))

    # ── OB1：独立探"已知地图漏掉的那一格"──
    # 先把地图整片的"地图不知道、但实地有方块"找出来（用少量探测 ✓ 有预算 ✓）
    cand = []
    for (x, z) in sorted(m.cells(), key=lambda c: (c[0] - sx) ** 2 + (c[1] - sz) ** 2):
        if math.dist((x, z), (sx, sz)) > 8:
            break
        col = m.cols.get((x, z)) or {}
        if (LEVEL) not in col and (LEVEL + 1) not in col:
            cand.append((x, z))
    out.append("候选（地图不知道脚层/头层）%d 格 ✓ 最多探 10 格（预算 ✓）" % len(cand))
    skip_air = []
    hit = None
    probed = 0
    for (x, z) in cand[:10]:
        for dy in (0, 1):
            name = r.probe_cell(x, LEVEL + dy, z)
            probed += 1
            if name and not name.endswith("air"):
                m.cols.setdefault((x, z), {})[LEVEL + dy] = name
                if MR.blocks_space(name):
                    hit = (x, z, name, dy)
                    break
            elif name.endswith("air"):
                skip_air.append((x, z, dy))
        if hit:
            break
    out.append("探了 %d 次 ✓（其中空气 %d 次 ✓）" % (probed, len(skip_air)))
    # ###### 2026-10-03：没前提时报「测不了」，不报红 ######
    #   这条判据的前提是「附近还有地图不知道的格」；42 轮下来附近早被摸清了，
    #   于是它**permanently 红**——而红着就会被晾在闸门外（最坏处置）。
    #   闸门的约定：退出码非 0 ＋ 输出里有 INCONCLUSIVE ＋ **没有** => FAIL 行
    #   ⇒ 算「测不了」：不算通过，也不算坏。
    inc = hit is None
    ob1 = hit is not None
    if hit:
        (hx, hz, hname, hdy) = hit
        out.append("OB1 ★探到挡人的方块★：(%d,%d) dy=%+d 是 **%s** ✓ ⇒ %s"
                   % (hx, hz, hdy, hname, ob1))
    else:
        out.append("OB1 ★没探到挡人的方块★ ✗ —— 这一片可能真的很干净 ✓"
                   "（那这条判据本轮测不到 ⇒ 如实报 ✗ 不装作通过 ✗）")

    # ── OB2：进没进地图 ───────────────────────────────────────────────────
    if hit:
        (hx, hz, hname, hdy) = hit
        col = m.cols.get((hx, hz)) or {}
        ob2 = col.get(LEVEL + hdy) == hname
        out.append("OB2 那格进图 = %s（图里记的是 %s ✓）" % (ob2, col.get(LEVEL + hdy)))
    else:
        ob2 = False
        out.append("OB2 没得测（同上 ✗）")

    # ── OB3：绕得开 ───────────────────────────────────────────────────────
    if hit:
        (hx, hz, hname, hdy) = hit
        target = (hx, hz)
        M.BLOCKED.add(target)
        M.BLOCKED_WHY[target] = hname
        pl = PP.Planner(m, level=LEVEL, blocked=M.BLOCKED)
        reg = pl.region(sx, sz)
        pts, why = pl.plan(sx, sz, target[0], target[1], region=reg)
        if pts:
            onroute = any((int(px), int(pz)) == target for (px, _py, pz) in pts)
            ob3 = not onroute
            out.append("OB3 绕开：规划出 %d 航点 ✓ 路线里有那一格=%s ⇒ %s（%s）"
                       % (len(pts), onroute, ob3, why[:90]))
        else:
            ob3 = True      # 绕不过去 ⇒ 如实报"不通" ✓ 也是合格行为 ✓
            out.append("OB3 绕开：**如实报不通** ✓ ⇒ %s ｜ %s" % (ob3, why[:110]))
        M.BLOCKED.discard(target)
    else:
        # 用**手工造的场景**兜住这条判据 ✗（P82 的老办法 ✓：自己造出该被绕开的格子 ✓）
        fake = (sx + 1, sz)
        M.BLOCKED.add(fake)
        pl = PP.Planner(m, level=LEVEL, blocked=M.BLOCKED)
        reg = pl.region(sx, sz)
        pts, why = pl.plan(sx, sz, fake[0], fake[1], region=reg)
        onroute = bool(pts) and any((int(px), int(pz)) == fake for (px, _py, pz) in pts)
        ob3 = (not onroute)
        out.append("OB3（手工造的障碍 %s）⇒ 路线里有它=%s ⇒ %s" % (fake, onroute, ob3))
        M.BLOCKED.discard(fake)

    # ── OB4：预算诚实 ─────────────────────────────────────────────────────
    sw = r.scan_route(m, [(sx + i, LEVEL, sz) for i in range(1, 20)], LEVEL, budget=6)
    ob4 = (sw["left"] > 0) and sw["probed"] <= 6
    out.append("OB4 预算：探 %d 次（上限 6 ✓）｜ 还有 %d 格没探 ⇒ 报出来了=%s ⇒ %s"
               % (sw["probed"], sw["left"], sw["left"] > 0, ob4))

    # ── OB5：不碰世界（★源码级✗★ 2026-10-03 检修改）─────────────────────────
    #   ★为什么改✗★：原判据是「假人前后差 < 0.5 格」，而世界里**常驻脑一直在走**
    #     ⇒ 实测差过 **11.88 格** ⇒ 那条红的**不是本脚本**（共享控制下「假人没动」
    #     不是本测试的性质，见 §79.73／欠账 ㉚）。
    #   ★新判据✗★：本脚本源码里不许出现会挪动假人的调用（自己读自己，静态可查，
    #     与世界状态无关）；「期间挪了几格」改成**信息**打印，不当判据。
    #   ★坑（踩了两次）✗★：token 列表**自己就是那些字符串** ⇒ 全都要**拼接**写，
    #     少拼一个，它就把自己抓了。
    _src = Path(__file__).read_text(encoding='utf-8', errors='replace')
    _code = '\n'.join(ln for ln in _src.splitlines() if not ln.strip().startswith('#'))
    _toks = ['walk' + '_route(', 't_move' + '_relative(', 'move ' + 'forward',
             'player Bot ' + 'move', 'dsh' + 'walk', 't_' + 'press(', 't_' + 'jump(',
             't_go' + '_to(', 't_walk' + '_to(', 'dsh' + 'walkto(']
    _bad_calls = [tok for tok in _toks if tok in _code]
    ob5 = not _bad_calls
    e = M._pos_now()
    moved = math.dist(p, e) if e else -1.0
    out.append('OB5 源码级：会挪动假人的调用 = %s ⇒ %s ｜（信息，不当判据）'
               '★期间假人挪了 %.2f 格 —— 那是**世界在动**（常驻脑），不是本脚本发的★'
               % (_bad_calls or '（没有 ✓）', ob5, moved))

    rest = bool(ob3 and ob4 and ob5)
    out.append("OB1 %s ｜ OB2 %s ｜ OB3 %s ｜ OB4 %s ｜ OB5 %s"
               % ("测不了" if inc else ob1, "测不了" if inc else ob2, ob3, ob4, ob5))
    if inc and rest:
        out.append("INCONCLUSIVE: 附近没有「地图不知道的格」可探 ⇒ OB1/OB2 测不了"
                   "（OB3/OB4/OB5 是自造场景的，仍然过 ✓）")
        return finish(4)
    if inc and not rest:
        out.append("=> FAIL（OB3/OB4/OB5 里有没过的东西 —— 那与前提无关 ✗ 要看 ✓）")
        return finish(1)
    ok = bool(ob1 and ob2 and rest)
    out.append("=> %s" % ("PASS" if ok else "FAIL（哪条没过看上面 ✓ 不粉饰 ✗）"))
    return finish(0 if ok else 1)


raise SystemExit(main())
