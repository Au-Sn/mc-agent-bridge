#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mapnames_test.py -- does the fast map hold REAL block names? (N1..N4, live)

WHY (2026-09-29, round 30): the battery's plan_verify Z1 failed on one target out
of six, and platform P3' failed on geometry. Chasing the first one exposed a
five-battery-old defect in the /dshmap parser:

  the reply's first line carries BOTH `ylegend=0:same,A:+1,...` (height offsets)
  and `legend=A:minecraft:oak_planks,...` (block names). `ylegend=` CONTAINS the
  substring `legend=`, and the parser used `re.search(r"legend=([^ ]*)", head)`,
  which takes the LEFTMOST match -- so it read the OFFSET table as if it were the
  block-name table. Every column then stored a bare LETTER as its floor "name"
  (`m.cols[(4120,6)] == {70: 'E'}`), and:
    * the ascii view rendered 100% '?'  (the user's "can I actually SEE the map")
    * `is_floor('E')` fell through to "full" and was accidentally TRUE, so every
      height/connectivity/walkability criterion stayed green -- which is why ten
      offline checks and five live batteries never noticed
    * `blocked_cells` held letters too ('M', 'V'), so "what is blocking me" was
      unanswerable.

CRITERIA (declared BEFORE running):
  N1 names real : on a FRESH /dshmap, every sampled known column's stored floor
                  name must be a namespaced id (contain ':') and the parser's own
                  counter `meta.letters_kept` must be 0.
  N2 names true : every REAL name the map states must EQUAL the block the world
                  holds at that same y, read independently with `dshscan ":"`.
                  ---- RESTATED in round 30, AFTER a real battery failure ----
                  The first version also demanded "named >= half of comparable",
                  which is wrong for the most ordinary situation there is: when
                  the bot stands on a flat platform, the mod prints '@' for every
                  column whose standable layer IS the bot's layer, so 22 of 25
                  comparable columns legitimately hold the sentinel and the
                  half-rule failed a map that was telling the truth.
                  What is actually checkable, always:
                    (a) no real name contradicts the world (the anti-fabrication
                        claim) -- needs >= 3 named columns, else INCONCLUSIVE;
                    (b) the sentinel appears ONLY where the mod printed '@', i.e.
                        exactly at floor y == blevel - 1. A sentinel anywhere else
                        means we invented an excuse for a cell we should know.
                  and the sentinel share is PRINTED, because it is a real gap
                  (measured: 418 of 750 view cells on the platform), not a pass.
  N3 readable   : (i) for every column the map knows, `cell_kind` must NOT come
                  out '?' (that is the rendered "I know nothing" char);
                  (ii) the TOP-DOWN view must not render a known column as '?' --
                  a known floor with an unknown name renders as 'x' ('there is a
                  floor here, the mod did not send its name'), which is a
                  different fact from "I know nothing" and must not share a char
                  (that conflation is why the view looked empty for half the map).
  N4 no fake    : (a) ZERO-call invariant, always checkable: for every column the
                  mod's collision-based b-row calls EMPTY that also has a floor
                  right under the bot's feet, the map must say standable -- a map
                  that refuses there has invented an obstacle, which is exactly
                  the round-30 bug.
                  (b) best effort, reported: if the mod's own map says a layer is
                  standable while a NAME-GUESSED-INTO-BLOCKING block sits in that
                  layer, then after `absorb_true` the map must call that column
                  standable and hold the block as `pass`; the ledger entry is
                  forgotten in-process first so this is re-derived live. If the
                  7x7 holds no such column it is INCONCLUSIVE (the deterministic
                  guard for that rule is the offline W3a..W3f in
                  dshmap_parse_test.py).
  N6 verdict    : ZERO-call invariant: the mod states, for EVERY column, which layer
                  it found standable (its letter plus the y-offset row). The map
                  must therefore call every one of those cells standable -- the
                  learning from a truth scan only ever covered the scanned area,
                  so before this the map could still contradict the mod elsewhere.
                  Only exception: the per-cell `b<z>|` row saying the bot's layer is
                  occupied (a per-cell observation outranks a per-column finding).
                  The number of cells where a name-guessed-blocking block sits in
                  the verdict layer is printed: that is the size of the hole fixed.
  N5 fill       : the gap must actually be CLOSABLE, cheaply: after                  `mc_mcp._fill_names` (ONE thin scan of the missing floor layer)
                  the number of "has a floor, name unknown" cells must drop to ~0
                  (<=5%), the top-down view must contain NO 'x' left and at least
                  one REAL category char (>=1, not >=2: a platform made of one
                  material is the normal case -- I first wrote >=2 and it failed a
                  perfectly good fill), and 3 of the filled names must equal an
                  independent per-cell read.

Bridge calls per run: two /dshmap, three single-cell reads, two truth scans. ASCII-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mapread as MR     # noqa: E402
import mc_mcp as M       # noqa: E402


def say(s):
    print(s, flush=True)


# The one name the parser is allowed to state without knowing it: for a column
# whose standable layer IS the bot's own layer the mod prints '@' and never sends
# that floor block's name. Anything else must be a real, world-true name.
SENTINEL = "minecraft:?"


def top_floor(col, hi=None):
    """The highest y in this column that the project's own rules call a floor."""
    ys = [y for y in (col or {}) if MR.is_floor(col[y]) and (hi is None or y <= hi)]
    return max(ys) if ys else None


def main():
    ok = True
    n2 = n4 = n5v = None
    p = M._pos_now()
    if not p:
        say("INCONCLUSIVE: no bot position")
        return 0
    sx, sy, sz = int(p[0]), int(round(float(p[1]))), int(p[2])
    say("bot at (%d,%s,%d)  feet cell L=%d" % (sx, p[1], sz, sy))

    r = MR.Reader()
    m = r.build_dshmap(radius=12)
    if m is None:
        say("INCONCLUSIVE: /dshmap unsupported (old mod) -> the fast path is not in use")
        return 0
    say("map box=%s cols=%d coverage=%.0f%% legend_ok=%s letters_kept=%s"
        % (m.box, len(m.cols), m.coverage() * 100, m.meta.get("legend_ok"),
           m.meta.get("letters_kept")))
    say("legend=%s" % (m.meta.get("legend"),))

    # ---------------- N1: names are real ------------------------------------
    # ★口径（第 30 轮第二次改 ✓ 第一次太窄 ✗）：**图上存的每一个名字**都得是真名字 ✓
    #   原来的写法只看"最高的那块**地板**"✗ ⇒ 站在**墙头/树叶**那种柱子（名字不是地板 ✗
    #   但模组说站得住 ✓）会被判成"没名字" ✗ ⇒ 假失败 ✓
    #   ⇒ 现在 ✓：**格子里存的每个名字**都要带命名空间 ✓ 且至少存了一个 ✓
    known = sorted(k for k, c in m.cols.items() if c)
    step = max(1, len(known) // 12)
    samp = known[::step][:12]
    noname = []
    for k in samp:
        names = [str(v) for v in m.cols[k].values()]
        if (not names) or any(":" not in v for v in names):
            noname.append((k, names))
    n1 = (not noname) and (int(m.meta.get("letters_kept") or 0) == 0) and (len(samp) >= 5)
    say("N1 names: sampled=%d  columns holding a non-namespaced name=%s  letters_kept=%s => %s"
        % (len(samp), noname[:4], m.meta.get("letters_kept"), n1))
    ok &= n1
    say("   e.g. %s" % [(k, m.cols[k]) for k in samp[:3]])

    # ---------------- N3: the view is readable ------------------------------
    chars = {}
    q_known = []
    for k in known:
        c = m.cell_kind(k[0], k[1], sy)[0]
        chars[c] = chars.get(c, 0) + 1
        if c == "?":
            q_known.append(k)
    # (ii) 俯视图：**已知的格子不许渲染成 `?`**（`x` = 有地板、名字模组没发 ✓ 那是**另一件事** ✓）
    view = m.ascii()
    import re as _re
    view_bad = []
    for line in view.splitlines()[1:]:
        mm = _re.match(r"\s*(-?\d+) (.*)$", line)
        if not mm:
            continue
        z = int(mm.group(1))
        row = mm.group(2)
        for i, ch in enumerate(row):
            x = m.box[0] + i
            if ch == "?" and m.cols.get((x, z)):
                view_bad.append((x, z))
    view_chars = {}
    for line in view.splitlines()[1:]:
        mm = _re.match(r"\s*(-?\d+) (.*)$", line)
        if mm:
            for ch in mm.group(2):
                view_chars[ch] = view_chars.get(ch, 0) + 1
    x_cells = view_chars.get("x", 0)
    n3 = (len(q_known) == 0) and (len(view_bad) == 0)
    say("N3 readable: cell_kind '?' on known columns = %d (want 0) | top-down view '?' on "
        "known columns = %d (want 0) %s => %s"
        % (len(q_known), len(view_bad), view_bad[:3], n3))
    say("   view histogram=%s  | 'x' (= has a floor, mod sent no name) = %d cells"
        % (sorted(view_chars.items(), key=lambda kv: -kv[1])[:8], x_cells))
    say("   cell_kind histogram=%s" % (sorted(chars.items(), key=lambda kv: -kv[1])[:8],))
    ok &= n3

    # ---------------- N2: real names must equal the world --------------------
    # ★口径（第 30 轮第二次改 ✓ 第一次的"抽样"太依赖站位 ✗）★：
    #   第一版在**7x7 邻域**里对账 ✗ ⇒ 假人一站到**平坦大平台**上 ✓
    #     几乎每根柱子的"能站层"就是它自己那一层 ⇒ 全是 `@`（哨兵 ✗）
    #     ⇒ 能对账的实名只剩 **1** 条 ⇒ INCONCLUSIVE ✗（判据几乎什么都没证明 ✗）
    #   ⇒ 现在 ✓：**从整张图里挑实名柱**（按位置排序取跨度的 5 根 ✓）**逐格独立读**（1 格 1 次 ✓）
    #     ＋ 哨兵**只许**出现在"模组印了 '@'"的位置（`地板 y == blevel-1` ✓ 纯本地 ✓ 零调用 ✓）
    #     ＋ 哨兵占比**如实打印**（那是个真缺口 ✓ 不是通过 ✓）
    named_cols = []
    for k in known:
        col = m.cols[k]
        fy = top_floor(col, hi=(int(m.meta["blevel"]) if m.meta.get("blevel") is not None else None))
        if fy is None:
            continue
        nm = col[fy]
        if nm and nm != SENTINEL and ":" in str(nm):
            named_cols.append((k, fy, nm))
    named_cols.sort()
    step = max(1, len(named_cols) // 5)
    pick = named_cols[::step][:5]
    misses = []
    for (k, fy, nm) in pick:
        t = r.probe_cell(k[0], fy, k[1])
        if not t:
            say("N2 ABORT: world read failed at %s" % ((k[0], fy, k[1]),))
            return 1
        if t != nm:
            misses.append(((k[0], k[1]), fy, nm, t))
    sentinel_cols = []
    sentinel_bad = []
    bl = m.meta.get("blevel")
    for k in known:
        fy = top_floor(m.cols[k])
        if fy is None or m.cols[k][fy] != SENTINEL:
            continue
        sentinel_cols.append(k)
        # ★哨兵只许出现在"模组印了 '@'"的位置★ ✗ —— 那一层就是假人自己那一层 ✓
        #   即 `地板 y == blevel - 1` ✓（`mapCmd` 里 `found.getY() == c.getY()` 那条 ✓）
        if bl is None or fy != int(bl) - 1:
            sentinel_bad.append((k, fy, bl))
    if sentinel_bad:
        n2 = False
        say("N2 names true: sentinel used where the mod did NOT print '@' (floor y != "
            "blevel-1) => %s => False" % sentinel_bad[:3])
    elif len(pick) < 3:
        say("N2 names true: only %d named columns in the whole map "
            "=> INCONCLUSIVE (not a pass)" % len(pick))
    else:
        n2 = (not misses)
        share = 100.0 * len(sentinel_cols) / max(1, len(known))
        say("N2 names true: %d named columns read one by one, named-but-wrong=%s => %s"
            % (len(pick), misses[:3], n2))
        say("   sentinel columns: %d/%d (%.0f%%) -- all of them at floor y == blevel-1 "
            "(the mod prints '@' there and sends no name) | bl=%s"
            % (len(sentinel_cols), len(known), share, bl))
        say("   examples: named=%s | sentinel=%s"
            % ([(k, m.cols[k]) for (k, _f, _n) in pick[:2]],
               [(k, m.cols[k]) for k in sentinel_cols[:2]]))
    if n2 is not None:
        ok &= n2

    # ---------------- N4a: the map must not invent obstacles ----------------
    # ★★这一条**零调用**且**永远可判**★★ ✗（第 30 轮 ✓）：
    #   模组的 `b<z>|` 行是**按碰撞箱**说的"你这一层被谁占着"✓ 而 `.` = **那两格都是空的** ✓
    #   ⇒ 凡是"模组说空 ✓ 而这柱子有地板 ✓ 而且地板就在你脚下一格"的位置 ✓
    #     地图**必须**说"站得住"✓ —— 地图说站不住 ⇒ **它自己造了一个障碍** ✗（正是这轮的元凶 ✓）
    #   口径写死 ✓：`standable(x, z, below=blevel+1)` 必须为 True ✓
    n4a = None
    bad_obs = []
    bc = m.meta.get("blocked_cells") or {}
    if bl is not None:
        for k in known:
            col = m.cols[k]
            fy = top_floor(col, hi=int(bl))
            if fy is None or fy != int(bl) - 1:
                continue
            if ("%d,%d" % k) in bc:
                continue                     # 模组说这一层被占 ⇒ 另一条路（N4a 只管"说空的"）
            if not m.standable(k[0], k[1], below=int(bl) + 1):
                bad_obs.append((k, fy, col.get(fy)))
        n4a = (not bad_obs)
        say("N4a no invented obstacle: columns the mod's b-row says are EMPTY, with a floor "
            "right under my feet, that the map still refuses = %d %s => %s"
            % (len(bad_obs), bad_obs[:3], n4a))
        ok &= n4a
    else:
        say("N4a INCONCLUSIVE: no blevel in this map")

    # ---------------- N6: 模组自己的"能站"结论必须全图生效 ------------------
    # ★为什么★★ ✗（第 30 轮 ✓ 这一条把"藏在扫过的地方才生效"的漏洞堵死 ✓）：
    #   模组对**每一柱**都给了"能站的是哪一层"✓（字母 ＋ 偏移 ⇒ `meta.mod_standable` ✓）
    #   而"实扫 ⇒ 学成 pass"那条只在**扫过的地方**生效 ✗
    #   ⇒ 判据 ✓：**凡是有结论的柱子 ✓ 地图就必须说站得住** ✓（零调用 ✓ 永远可判 ✓）
    #     例外**只有一种** ✓：`b<z>|` 那一行说"这一格被你占着"✓（逐格观测 > 逐柱结论 ✓）
    #   ＋ 顺便数出"结论与名字猜打架"的格子 ✓ —— 那就是这条修好的洞有多大 ✓
    n6 = None
    if bl is not None:
        ms = m.meta.get("mod_standable") or {}
        bc2 = m.meta.get("blocked_cells") or {}
        bad_v = []
        conflicts = 0
        for key, fy in ms.items():
            try:
                kx, _, kz = key.partition(",")
                kx, kz, fy = int(kx), int(kz), int(fy)
            except Exception as e:
                # 记录：模组给了结论却解析不了这一柱 ⇒ N6 "凡有结论的柱子"少查一根（可能假绿）
                say("  ★记录✗★ N6 少查一柱（键解析不了 ⇒ 可能假绿）：%r（%s）"
                    % (key, type(e).__name__))
                continue
            if ("%d,%d" % (kx, kz)) in bc2 and fy == int(bl):
                continue                     # 逐格观测说被占 ⇒ 那条路归 N4a/N5b 管 ✓
            nm = (m.cols.get((kx, kz)) or {}).get(fy)
            if nm and MR.blocks_space(nm):
                conflicts += 1
            if not m.standable(kx, kz, below=fy + 1):
                bad_v.append(((kx, kz), fy, nm))
        n6 = (len(ms) > 0) and (not bad_v)
        say("N6 the mod's verdict is in force: verdicts=%d | cells where a name-guessed "
            "blocking block sits in that layer=%d | map disagrees=%d %s => %s"
            % (len(ms), conflicts, len(bad_v), bad_v[:3], n6))
        ok &= n6
    else:
        say("N6 INCONCLUSIVE: no blevel in this map")

    # ---------------- N4b: the live learning (best effort, reported) --------
    R = 3
    box = (sx - R, sy - 6, sz - R, sx + R, sy + 2, sz + R)
    scan = r.scan_truth(box, max_=600, max_pages=2)
    say("N4b truth scan box=%s calls=%d pages=%d truncated=%s cells=%d"
        % (scan["box"], scan["calls"], scan["pages"], scan["truncated"], len(scan["cells"])))
    truth = {}
    for (x, y, z, nm) in scan["cells"]:
        truth[(int(x), int(y), int(z))] = nm
    # 候选口径用**名字猜**判（不看账本 ✗）：这样"账本已经学会了"之后这条判据**依然有效** ✓
    cand = []
    if not scan["truncated"]:
        for (x, z) in sorted(m.cols.keys()):
            if not (sx - R <= x <= sx + R and sz - R <= z <= sz + R):
                continue
            col = m.cols[(x, z)]
            fy = top_floor(col, hi=sy)
            if fy is None:
                continue
            b = truth.get((x, fy + 1, z))          # the mod's standable layer is fy + 1
            if not b or ":" not in b:
                continue
            below = truth.get((x, fy, z))
            if not below or not MR.is_floor(below):
                continue                           # the same guard absorb_true applies
            if MR._shape_by_name(b) != "pass":     # NAME GUESS says it blocks
                cand.append(((x, z), fy + 1, b))
    if not cand:
        say("N4b live learning: no name-guessed-into-blocking block sits in a standable "
            "layer in this %dx%d => INCONCLUSIVE (the deterministic guard is the offline "
            "W3a..W3f; this one is best effort)" % (2 * R + 1, 2 * R + 1))
    else:
        # ★先用**名字猜**看它此刻会不会造出假障碍★ ✗（把账本里那条**暂时忘掉** ✓ 只在本进程 ✓）
        for (_c, _f, b) in cand:
            MR.LEARNED.pop(b, None)
        pre = [(c, f, b, MR.shape(b), MR.blocks_space(b)) for (c, f, b) in cand]
        info = m.absorb_true(scan, sy - 6, sy + 2)
        rows = [(c, f, b, MR.shape(b), m.standable(c[0], c[1], below=sy + 1))
                for (c, f, b) in cand]
        n4b = all((sh == "pass") and (st is True) for (_c, _f, _b, sh, st) in rows)
        say("N4b live learning: with the ledger entry forgotten, the name guess called "
            "these blocking: %s" % [(c, f, b, bc2) for (c, f, b, sh, bc2) in pre])
        say("   learned-now=%s | after absorbing truth (cell, y, block, shape, "
            "map-says-standable):" % (info.get("learned"),))
        for row in rows:
            say("     %s" % (row,))
        say("   the mod's own map says those layers ARE standable (that is where the "
            "letters came from) => the map must agree => %s" % n4b)
        ok &= n4b
        n4 = n4b
        say("   ledger: %s" % {b: MR.LEARNED.get(b) for (_c, _f, b, _s, _t) in rows})

    # ---------------- N5: the missing names can actually be filled ----------
    # ★为什么必须有★ ✗（第 30 轮 ✓ 这一条才是**用户看得见的那一半** ✓）：
    #   "图上有名字" ≠ "图**看得懂**" ✗ —— 实测假人站在**平坦大平台**上时 93% 的格子
    #   "有地板但名字不知道" ✗ ⇒ 俯视图只能画 `x` ✗
    #   ⇒ `map_area` 现在会**补一层**（`mc_mcp._fill_names` ✓ 只扫那一层 ✓ 世界真值 ✓）
    #   判据 ✓：① 补完哨兵必须**基本清零**（≤5% ✓ 没扫完要如实说 ✗）
    #          ② 俯视图必须出现**真的类别字符**（不再是 `x` 一片 ✓）
    #          ③ 抽 3 格**逐格独立读** ⇒ 名字必须**等于世界** ✓（补进来的也得是真的 ✓）
    m2 = r.build_dshmap(radius=8)
    if m2 is None:
        say("N5 INCONCLUSIVE: second map build failed")
    else:
        miss0, per0 = m2.names_missing()
        say("N5 fill: fresh map cols=%d, cells with a floor but no name = %d (layers=%s)"
            % (len(m2.cols), miss0, per0))
        finfo = M._fill_names(r, m2, sy)
        miss1, _per1 = m2.names_missing()
        view2 = m2.ascii()
        cats = {}
        for line in view2.splitlines()[1:]:
            mm = _re.match(r"\s*(-?\d+) (.*)$", line)
            if mm:
                for ch in mm.group(2):
                    cats[ch] = cats.get(ch, 0) + 1
        real_cats = {c: n for c, n in cats.items() if c not in (".", " ", "x", "?")}
        picked = []
        for k in sorted(m2.cols):
            for y in sorted(m2.cols[k]):
                if m2.cols[k][y] != SENTINEL and MR.is_floor(m2.cols[k][y]) \
                        and ":" in m2.cols[k][y]:
                    picked.append((k, y, m2.cols[k][y]))
                    break
            if len(picked) >= 3:
                break
        wrong = []
        for (k, y, nm) in picked:
            t = r.probe_cell(k[0], y, k[1])
            if not t:
                say("N5 ABORT: world read failed at %s" % ((k[0], y, k[1]),))
                return 1
            if t != nm:
                wrong.append(((k[0], k[1]), y, nm, t))
        # ★★口径（第 34 轮第二次修正 ✓）："视图里要有真的类别字符"这条**依赖站位** ✗
        #   实测 ✓：假人跑到**农田/墙边**那一带时 ⇒ 图框里几乎全是未知/虚空 ✗
        #     ⇒ `view categories=[]` ✗ ⇒ **判据红** ✗ —— 可补名字这件事**做得好好的** ✓
        #   ⇒ 改成 ✓：**"凡是图上知道名字的格子，视图里必须给出真类别（不能是 `x`/`?`）"** ✓
        #     一个都没有 ⇒ **INCONCLUSIVE**✗（如实 ✓ 不当通过 ✓）
        named_in_view = 0
        for line in view2.splitlines()[1:]:
            mm = _re.match(r"\s*(-?\d+) (.*)$", line)
            if not mm:
                continue
            z = int(mm.group(1))
            row = mm.group(2)
            for i, ch in enumerate(row):
                x = m2.box[0] + i
                nm2 = (m2.cols.get((x, z)) or {})
                if any((v and ":" in str(v) and v != SENTINEL) for v in nm2.values()):
                    named_in_view += 1
                    if ch in ("?", "x"):
                        real_cats = {}          # ★已知名字却画成 x/? ⇒ 不达标 ✓
        cleared = (miss0 == 0) or (miss1 <= max(1, int(0.05 * len(m2.cols))))
        if named_in_view == 0:
            n5 = None
            say("N5 INCONCLUSIVE (not a pass): no named cell inside the view to judge "
                "(before=%d after=%d, fill=%s)" % (miss0, miss1, finfo))
        else:
            n5 = cleared and (cats.get("x", 0) == 0) and (len(picked) >= 3) and (not wrong)
        say("N5 fill: before=%d after=%d (want ~0) | fill=%s" % (miss0, miss1, finfo))
        say("   named cells inside the view=%d (each must render a real category, not x/?) | "
            "view categories=%s | 'x' left=%d | 3 filled names from the world: wrong=%s => %s"
            % (named_in_view, sorted(real_cats.items(), key=lambda kv: -kv[1])[:6],
               cats.get("x", 0), wrong, n5))
        if n5 is not None:
            ok &= n5
        n5v = n5

    # ★★2026-10-03 检修补（欠账 ㉜）：装饰类不许被冤枉成障碍★★
    #   真事：`supplementaries:book_pile_horizontal`（一摞书）认不出 ⇒ 归 `other` ⇒ 地图打 `#`，
    #   而世界明明能站（脚下是它、头层是空气）⇒ `route_verify_test` 的 X1 抓住过这个不一致。
    #   口径：家族词按**形状**补（薄片装饰 ⇒ `pass`：不挡人），不按模组名穷举。
    import mapread as _MR592
    # ★★2026-10-05：一摞书的期望**按档写**✗★★（★用户裁定② ＋ 物理证据已齐✓★）
    #   ★★证据链✗★★（★§79.139／§79.140 ✗ 2026-10-05 实测✗★）✗★
    #     ★导出✗★：`family=slab` ｜ `max_height=`**0.625**✗★
    #     ★世界✗★：★走到它**顶上那格**（★`(4117,72,8)`✓★）⇒ 停在
    #       **`(4117.41, 71.63, 8.70)`** ｜ ★期望 `方块 y ＋ h` ＝ **71.625** ✗
    #       **差 0.00**✗★ ｜ `onground=true` ⇒ ★**能站**✗★ ✓
    #     ★走到它**自身那格**（★`(4117,71,8)`✓★）⇒ ★它**真的试过**（★位移 1.24✓★）
    #       而走手报 ★"★没到（**unreachable**）｜ 原因=**target**★" ⇒ ★**占不进去** ⇒ **挡人**✗★ ✓
    #   ★★旧期望为什么**是猜错的**✗★★：★名字时代**认不出**这个种 ⇒ 归 `other` ⇒
    #     判"★不挡人★"✗★ ⇒ ★它把"★**能站**★"（★`route_verify` X1 那次观察✓★）
    #     **当成了**"★**不挡人**★"✗★ ⇒ ★两条判定**都错** ✗ 碰撞真值是 **True**✗★ ✓
    #   ★★而出厂档必须继续绿✗★★：★`blacklist` 下老路**确实**判 `False`✗★ ⇒
    #     ★两个档**各写各的** ✗ 写死一个会让另一个说谎✗★ ✓
    # ★★2026-10-05：改问"★碰撞槽有没有真的回答这个物种★"✗★★（§79.153 实测：
    #   ★`DSH_KB_SCOPE` 能把它排除在外 ⇒ "★开关开没开★"**不等于**"★表回答了它★"✓★）
    try:
        import blockkb as _KB592
        _pile_src = _KB592.classify("supplementaries:book_pile_horizontal",
                                    phys=True).get("level")
    except Exception:
        _pile_src = None
    for _b, _want in (('supplementaries:book_pile_horizontal',
                       True if _pile_src == "collision" else False),
                      ('minecraft:torch', False),
                      ('minecraft:grass_block', True),
                      ('minecraft:stone', True),
                      ('mcwfences:sandstone_grass_topped_wall', True)):
        _got = _MR592.blocks_space(_b)
        say('N-pile %-46s 挡人=%s（应当 %s）' % (_b, _got, _want))
        ok &= (_got is _want)
    say("---- N1=%s N2=%s N3=%s N4a=%s N4b=%s N5=%s ----" % (n1, n2, n3, n4a, n4, n5v))
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
