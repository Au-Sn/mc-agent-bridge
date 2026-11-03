#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dshmap_parse_test.py -- OFFLINE tests for the /dshmap parser (W1, W2)

WHY: the fast map silently flattened the world. The mod searched downward for
the first standable layer and printed only a LETTER -- the layer's height was
thrown away, and a cell whose own layer was occupied (fence/machine) made the
mod look at a LOWER layer instead, so the obstacle never appeared at all.
Result: 979 cells, all "walkable", while world truth had a 1-block drop and a
block sitting at feet level.

The mod (v2.16) now also returns `y<z>|` (height offset) and `b<z>|` (what
occupies YOUR feet/head layer) rows. This test feeds SYNTHETIC payloads to the
parser -- no game, no bridge -- and checks the resulting map.

CRITERIA (declared before running):
  W1 (new payload, 3x3, bot feet at (1,72,1)) :
     W1a has_offsets == True
     W1b floors: offset 'a' (-1) cell stores floor at by-2; offset 'A' (+1)
         cell stores floor at by; '@' cell stores floor at by-1
     W1c cell_kind => '@' '*', step-down 'v', step-up '^', occupied '#'
     W1d a fence at my feet layer makes standable() False and the planner
         refuses that cell (ok() == False), while clean cells stay usable
     W1e a cell rendered '.' by the mod but carrying a blocker in the b-row
         still reads '#' (the obstacle layer wins over "no layer found")
     W1f a cell with no standable layer and no blocker reads '.' (known pit),
         NOT '?' (unknown) -- "the mod told me there is nothing" is not the
         same as "I did not look"
  W2 (old payload, no y/b rows) :
     W2a has_offsets == False and y_assumed > 0 (the guess is COUNTED)
     W2b blocked_at() == None (no obstacle layer => never invent one)
     W2c letter cells are still accepted as walkable (map not empty)
     W2d meta blocked == 0 and no_layer empty
  ---- added in round 30 (declared before that run) ----
  W1g names      : the map must store the LEGEND's block names -- floor(1,1) and
                   floor(2,2) == minecraft:grass_block, blocked(2,2) ==
                   mwfences:oak_wall, meta legend_ok is True, meta letters_kept
                   == 0, and the ascii view really contains 'G'.
                   WHY: W1a..W2d only ever asked about y / walkability / obstacles
                   and NEVER about the block name, so a parser that read the
                   offset legend (`ylegend=` contains the substring `legend=`)
                   stored a bare LETTER per column for five whole batteries --
                   the ascii view was 100% '?' and `is_floor(letter)` was
                   accidentally True, which is exactly why nothing noticed.
  W3 learned     : when the mod's own (collision-based) map says a layer is
                   standable, a block sitting IN that layer does not block --
                   `absorb_true` must learn it as `pass` so the map stops
                   inventing obstacles. Checked on a SYNTHETIC block name
                   (testmod:fake_bush_up) plus four negative controls that must
                   learn NOTHING: no offsets (old mod), truncated scan, an
                   already-known block (a fence), and a cell whose world truth
                   shows no floor underneath. The ledger is snapshotted and
                   restored, so this test can never write into the real one.

The test never touches the real map cache: save() is stubbed out, so a fake
payload can never poison the on-disk cache.

ASCII-only output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mapread as MR    # noqa: E402
import pathplan as PP   # noqa: E402

BY = 72                 # the bot's feet cell in the payloads
LEG = "G:minecraft:grass_block,W:mcwfences:oak_wall"
YLEG = "0:same,A:+1,B:+2,a:-1,b:-2,c:-3,d:-4,e:-5,f:-6,.:none"


def say(s):
    print(s, flush=True)


def fake_reader(payload):
    """A Reader whose only channel is our synthetic payload; save() is disabled."""
    r = MR.Reader.__new__(MR.Reader)
    r.calls = 1
    r.verbose = False
    r.ab = lambda cmd, tmo=60.0: payload
    r.save = lambda m, max_age=600.0: None
    return r


def new_payload():
    """3x3 grid, z=0..2 / x=0..2, bot feet at (1,72,1).

      x:      0    1    2
      z=0:    @    G    .        (2,0) no standable layer, nothing blocking  -> '.'
      z=1:    @    G    G        (1,1) offset a (-1) -> floor by-2 -> 'v'
                                 (2,1) offset A (+1) -> floor by   -> '^'
      z=2:    @    .    G        (1,2) '.' but a fence at MY feet layer -> '#'
                                 (2,2) letter + fence at my feet layer   -> '#'
    """
    head = ("dshmap box=0,0..2,2 from=1,%d,1 standable=3 blocked=2 blevel=%d "
            "ylegend=%s legend=%s" % (BY, BY, YLEG, LEG))
    rows = ["0|@G.", "1|@GG", "2|@.G"]
    yrows = ["y0|00.", "y1|0aA", "y2|0.0"]
    brows = ["b0|...", "b1|...", "b2|.WW"]
    return "\n".join([head] + rows + yrows + brows)


def old_payload():
    """The same grid the way the OLD mod answered: kind rows only."""
    head = "dshmap box=0,0..2,2 from=1,%d,1 standable=9 legend=%s" % (BY, LEG)
    rows = ["0|@GG", "1|@GG", "2|@GG"]
    return "\n".join([head] + rows)


def _purge_test_artifacts():
    """sec 79.456: remove leftovers from an interrupted previous run.

    The ledger is only restored at the END of the batteries, so a Ctrl-C leaks fake
    entries. Purging at START makes the test independent of how the last run ended.
    """
    import json as _json
    p = ROOT / "logs" / "block_shapes.json"
    if not p.is_file():
        return 0
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:      # not silent: say why we could not clean
        print("note: could not read %s to purge test artifacts: %r" % (p, e))
        return 0
    shapes = d.get("shapes") or {}
    bad = [k for k in shapes
           if "testmod" in str(k).lower() or "fake" in str(k).lower()]
    for k in bad:
        del shapes[k]
    if bad:
        d["shapes"] = shapes
        p.write_text(_json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("purged %d test artifact(s): %s" % (len(bad), bad))
    return len(bad)


def main():
    _purge_test_artifacts()
    ok = True

    # ---------------- W1 ----------------
    m = fake_reader(new_payload()).build_dshmap(radius=1, max_age=1.0)
    if m is None:
        say("W1 FAIL: parser returned None on the new payload")
        return 1
    say("W1 parsed: cells=%d has_offsets=%s y_exact=%s y_assumed=%s blocked=%s "
        "blevel=%s no_layer=%s"
        % (len(m.cols), m.meta.get("has_offsets"), m.meta.get("y_exact"),
           m.meta.get("y_assumed"), m.meta.get("blocked"), m.meta.get("blevel"),
           len(m.no_layer_set())))

    say("W1a has_offsets == True => %s" % (m.meta.get("has_offsets") is True))
    ok &= (m.meta.get("has_offsets") is True)

    def floor_y(x, z):
        c = m.cols.get((x, z)) or {}
        ys = sorted(y for y in c if MR.is_floor(c[y]))
        return ys[-1] if ys else None

    w1b = (floor_y(1, 1) == BY - 2) and (floor_y(2, 1) == BY) and (floor_y(0, 0) == BY - 1)
    say("W1b floors: (1,1) off 'a' floor=%s want %d | (2,1) off 'A' floor=%s want %d | "
        "(0,0) '@' floor=%s want %d => %s"
        % (floor_y(1, 1), BY - 2, floor_y(2, 1), BY, floor_y(0, 0), BY - 1, w1b))
    ok &= w1b

    cells = [(0, 0), (1, 1), (2, 1), (2, 2), (1, 2), (1, 0), (2, 0)]
    k = {c: m.cell_kind(c[0], c[1], BY) for c in cells}
    say("W1c cell_kind: " + "  ".join("%s=%s" % (c, k[c][0]) for c in cells))
    w1c = (k[(0, 0)][0] == "*" and k[(1, 1)][0] == "v" and k[(2, 1)][0] == "^"
           and k[(2, 2)][0] == "#" and k[(1, 2)][0] == "#" and k[(1, 0)][0] == "*")
    say("W1c expected * v ^ # # * for the first six => %s" % w1c)
    ok &= w1c

    st = [m.standable(x, z, below=BY + 1) for (x, z) in [(0, 0), (1, 1), (2, 2)]]
    pl = PP.Planner(m, level=BY)
    oks = [pl.ok(x, z) for (x, z) in [(0, 0), (1, 1), (2, 2)]]
    say("W1d standable(0,0 / 1,1 / 2,2)=%s | planner ok=%s" % (st, oks))
    w1d = (st[0] is True) and (st[2] is False) and (oks[2] is False) and (oks[0] is True)
    say("W1d occupied cell refused by the planner, clean cells usable => %s" % w1d)
    ok &= w1d

    w1e = (k[(1, 2)][0] == "#")
    say("W1e '.' cell with a blocker at my layer still reads '#' => %s" % w1e)
    ok &= w1e

    w1f = (k[(2, 0)][0] == ".") and (m.blocked_at(2, 0, BY + 1) is None)
    say("W1f known-pit cell reads '.' (not '?') and has no blocker => %s" % w1f)
    ok &= w1f

    # ---------------- W2 ----------------
    m2 = fake_reader(old_payload()).build_dshmap(radius=1, max_age=1.0)
    if m2 is None:
        say("W2 FAIL: parser returned None on the OLD payload")
        return 1
    say("W2 old payload: cells=%d has_offsets=%s y_assumed=%s blocked=%s no_layer=%s"
        % (len(m2.cols), m2.meta.get("has_offsets"), m2.meta.get("y_assumed"),
           m2.meta.get("blocked"), len(m2.no_layer_set())))
    w2a = (m2.meta.get("has_offsets") is False) and (int(m2.meta.get("y_assumed") or 0) > 0)
    say("W2a has_offsets False and y_assumed > 0 => %s" % w2a)
    ok &= w2a
    w2b = (m2.blocked_at(1, 1, BY + 1) is None)
    say("W2b blocked_at() is None (never invent an obstacle) => %s" % w2b)
    ok &= w2b
    w2c = (m2.cell_kind(1, 1, BY)[0] == "*") and len(m2.cols) >= 8
    say("W2c letter cells still walkable (map not empty, cells=%d) => %s"
        % (len(m2.cols), w2c))
    ok &= w2c
    w2d = (int(m2.meta.get("blocked") or 0) == 0) and (len(m2.no_layer_set()) == 0)
    say("W2d blocked == 0 and no_layer empty => %s" % w2d)
    ok &= w2d

    # ---------------- W1g: the map's NAMES must be real block names ----------
    # ★这一条为什么必须有★ ✗（2026-09-29 第 30 轮 ✓）：
    #   上面 W1a..W1f、W2a..W2d 一共十条判据 ✓ 问的全是 **y / 能不能走 / 有没有障碍** ✗
    #   **一条都没问过"这格的地板叫什么"** ✗
    #   ⇒ 于是下面这个 bug 躲过了整整五轮电池 ✓（实测 ✓）：
    #     `/dshmap` 的头一行同时有 `ylegend=…` 和 `legend=…` ✗ 而前者**包含后者**✗
    #     ⇒ 解析永远读到**偏移表** ✗ ⇒ 每个柱子的地板名退化成**一个字母** ✓
    #     ⇒ 连锁 ✓：ASCII 俯视图**整张 `?`**✗（`cat('E')` 不认识 ✓ 用户要的"看得懂"没了 ✗）
    #        ／`blocked_cells` 也存字母 ✗（`M`/`V` ✓ 真假不明 ✗）
    #     ⇒ 而 `is_floor(字母)` 落进 `full` ⇒ **碰巧为真** ✗ ⇒ 高度/连通判据全绿 ✗
    #   ⇒ 口径（判据先写 ✓）：**图里的名字必须是图例给的名字** ✓
    #     ＋ `letters_kept == 0`（"还剩几个字母冒充名字" ✓ 由解析器自己记账 ✓）
    #     ＋ 俯视图里必须出现真字符（`G` ✓ 而不是整张 `?` ✓）
    nm1 = (m.cols.get((1, 1)) or {}).get(BY - 2)
    nm2 = (m.cols.get((2, 2)) or {}).get(BY - 1)
    blk1 = m.blocked_at(2, 2, BY + 1)
    ascii_view = m.ascii()
    w1g = (nm1 == "minecraft:grass_block") and (nm2 == "minecraft:grass_block") \
        and (blk1 == "mcwfences:oak_wall") and (m.meta.get("legend_ok") is True) \
        and (int(m.meta.get("letters_kept") or 0) == 0) and ("G" in ascii_view)
    say("W1g names are real: floor(1,1)=%r floor(2,2)=%r blocked(2,2)=%r "
        "legend_ok=%s letters_kept=%s | ascii has 'G'=%s => %s"
        % (nm1, nm2, blk1, m.meta.get("legend_ok"), m.meta.get("letters_kept"),
           "G" in ascii_view, w1g))
    ok &= w1g

    # ---------------- W3: learn "the mod can stand here => that block is pass" --
    # ★为什么★★ ✗（第 30 轮 ✓ 这是 `plan_verify` Z1 那个假失败的真因 ✓）：
    #   快图的字母 = 模组**按碰撞箱**判"这一层站得住"✓ 而我把这一带**实地扫**回来 ✓
    #   ⇒ 若那一层里**有方块** ✓ 而模组还说站得住 ✓ ⇒ 那个方块**不挡人** ✓（事实链见
    #     `mapread.absorb_true` 的注释 ✓）⇒ 学成 `pass` ✓ 地图不再自造障碍 ✓
    #   实测现场 ✓：草方块 (4120,70,6) 上方长着 `ars_elemental:spore_blossom_up` ✓
    #     名字猜判它"挡死"✗ ⇒ 规划器挑中的目的地在判据眼里"站不住"✗ ⇒ 假失败 ✗
    #   ⚠ 这里用**合成方块名**（不依赖真实账本 ✓）：真账本里那条由**实机验收**管 ✓
    SNAP = dict(MR.LEARNED)
    DIRTY0 = MR._LEARN_DIRTY[0]
    #   ⚠ 名字要挑得**名字猜一定判它挡人** ✗（`..._bush_up` 不行 ✗：`bush` 在 `PASS_SUB` 里 ✓
    #     那样"本来就判能穿" ⇒ 这条判据会**假通过** ✗ —— 我第一版就栽在这里 ✓）
    FAKE = "testmod:zzz_decor_up"          # 名字表里哪个词都不沾 ⇒ 名字猜 = full（挡死 ✗）
    FENCE = "minecraft:oak_fence"          # 名字表里有 ⇒ 已知 ⇒ 不许被改 ✓

    def mk_map(has_offsets=True, feet_block=FAKE, floor_block="minecraft:grass_block"):
        mm = MR.Map(0, BY - 8, 0, 0, BY + 6, 0)
        mm.meta.update({"has_offsets": has_offsets, "blevel": BY, "blocked_cells": {}})
        mm.cols[(0, 0)] = {BY - 1: "minecraft:grass_block"}
        cells = [(0, BY - 1, 0, floor_block)]
        if feet_block:
            cells.append((0, BY, 0, feet_block))
        return mm, {"box": (0, BY - 6, 0, 0, BY + 2, 0),
                    "cells": cells, "truncated": False}

    before = MR.blocks_space(FAKE)
    mm, sc = mk_map()
    info = mm.absorb_true(sc, BY - 6, BY + 2)
    w3a = before and (MR.shape(FAKE) == "pass") and (not MR.blocks_space(FAKE)) \
        and (FAKE in (info.get("learned") or [])) and (mm.standable(0, 0, below=BY + 1) is True)
    say("W3a learn from the mod's own standability: guess-full=%s -> shape=%s "
        "blocks_space=%s learned=%s standable=%s => %s"
        % (before, MR.shape(FAKE), MR.blocks_space(FAKE), info.get("learned"),
           mm.standable(0, 0, below=BY + 1), w3a))
    ok &= w3a

    # 反向对照（★每条都要能"不动"★ ✗）：旧模组的图 / 截断的扫描 / 已知方块 /
    #   脚下没地板 ⇒ 四种情况**一条都不许学** ✓（不然就是"拿推的当真值"✗）
    MR.LEARNED.pop(FAKE, None)
    mm_b, sc_b = mk_map(has_offsets=False)
    mm_b.absorb_true(sc_b, BY - 6, BY + 2)
    w3b = MR.blocks_space(FAKE)
    say("W3b no offsets (old mod) => nothing learned, still blocking=%s => %s"
        % (MR.blocks_space(FAKE), w3b))
    ok &= w3b

    MR.LEARNED.pop(FAKE, None)
    mm_c, sc_c = mk_map()
    sc_c["truncated"] = True
    mm_c.absorb_true(sc_c, BY - 6, BY + 2)
    w3c = MR.blocks_space(FAKE)
    say("W3c truncated scan => nothing learned, still blocking=%s => %s"
        % (MR.blocks_space(FAKE), w3c))
    ok &= w3c

    MR.LEARNED.pop(FAKE, None)
    mm_d, sc_d = mk_map(feet_block=FENCE)
    mm_d.absorb_true(sc_d, BY - 6, BY + 2)
    w3d = (MR.shape(FENCE) != "pass") and (FENCE not in MR.LEARNED)
    say("W3d known block (a fence) is never overridden: shape=%s learned=%s => %s"
        % (MR.shape(FENCE), FENCE in MR.LEARNED, w3d))
    ok &= w3d

    MR.LEARNED.pop(FAKE, None)
    mm_e, sc_e = mk_map(floor_block="minecraft:air")   # 世界真值说脚下不是地板
    mm_e.absorb_true(sc_e, BY - 6, BY + 2)
    w3e = MR.blocks_space(FAKE)
    say("W3e world truth shows no floor under the cell => nothing learned, "
        "still blocking=%s => %s" % (MR.blocks_space(FAKE), w3e))
    ok &= w3e

    # ★把账本恢复原样★ ✗：这个测试**不许**往真账本里写自己造的方块 ✓
    #   ⚠ 只恢复**内存**不够 ✗（第 30 轮实测 ✓）：`absorb_true` 学到东西时会**立刻落盘** ✓
    #     （那一手是给实机加的 ✓ 免得进程一退就白学 ✗）⇒ 合成方块已经被写进
    #     `logs/block_shapes.json` 了 ✗ ⇒ 必须**再把文件按恢复后的内存重写一遍** ✓
    MR.LEARNED.clear()
    MR.LEARNED.update(SNAP)
    MR._LEARN_DIRTY[0] = DIRTY0
    wrote = MR.learn_save(force=True)
    still = MR.LEARNED.get(FAKE)
    fake_in_file = FAKE in (json.loads(MR.LEARNED_FILE.read_text(encoding="utf-8"))
                            .get("shapes") or {})
    say("W3f ledger restored: in-memory fake=%s | in-file fake=%s (want None/False) "
        "| save-wrote=%d => %s" % (still, fake_in_file, wrote,
                                   (still is None) and (not fake_in_file)))
    ok &= (still is None) and (not fake_in_file)

    # ---------------- W5: 模组自己的"能站"结论（碰撞箱）说了算 ---------------
    # ★为什么★★ ✗（第 30 轮 ✓）：模组对每一柱都给了"**能站的是哪一层**"✓（字母 ＋ 偏移 ✓）
    #   那是**按碰撞箱**实测的 ✓ 而我的判定链里有两条是**按名字猜**的 ✗
    #   ⇒ 猜的**不许**否掉实测的 ✗（`plan_verify` Z1 那一红的真因 ✓）
    #   合成现场 ✓：草方块上方长着 `ars_elemental:spore_blossom_up` ✓
    #     模组说 72 层能站 ✓ 而名字猜说"挡死" ✗（认不出的方块一律当挡 ✗）
    #   判据（先写 ✓）：
    #     W5a 逐柱结论 > 名字猜 ✓：那一层里就算记着一个"名字猜=挡死"的方块 ⇒ 仍然站得住 ✓
    #     W5b 逐格观测 > 逐柱结论 ✓：`b<z>|` 说这一格被占 ⇒ 站不住 ✓（更具体的证据赢 ✓）
    #     W5c 脚下没地板就不认那条结论 ✓（拿旧结论当新事实是本项目的忌讳 ✓）
    #     W5d 新真值能推翻旧结论 ✓：实扫发现那一层里是**名录里认得的**挡人方块 ⇒ 结论作废 ✓
    #         （认不出的**不许**作废 ✓ 那是名字猜的地盘 ✓ 走 W3 那条学习 ✓）

    def w5_payload(brow):
        h = ("dshmap box=0,0..1,0 from=0,%d,0 standable=2 blocked=0 blevel=%d "
             "ylegend=%s legend=%s" % (BY, BY, YLEG, LEG))
        return "\n".join([h, "0|GG", "y0|00", "b0|" + brow])

    FAKE2 = "testmod:zzz_decor_up"
    m5 = fake_reader(w5_payload("..")).build_dshmap(radius=1, max_age=1.0)
    # 把"名字猜=挡死"的方块**塞进模组说的那一层**（模拟实扫写过真值之后的状态 ✓）
    m5.cols.setdefault((0, 0), {})[BY] = FAKE2
    a = (m5.mod_stand_y(0, 0) == BY)
    st_a = m5.standable(0, 0, below=BY + 1)
    k_a = m5.cell_kind(0, 0, BY)[0]
    w5a = a and (MR._shape_by_name(FAKE2) == "full") and (st_a is True) and (k_a == "*")
    say("W5a the mod's own (collision) verdict wins: verdict_y=%s | name-guess=%s | "
        "standable=%s | view=%s => %s"
        % (m5.mod_stand_y(0, 0), MR._shape_by_name(FAKE2), st_a, k_a, w5a))
    ok &= w5a

    m5b = fake_reader(w5_payload("W.")).build_dshmap(radius=1, max_age=1.0)
    m5b.cols.setdefault((0, 0), {})[BY] = FAKE2
    st_b = m5b.standable(0, 0, below=BY + 1)
    k_b = m5b.cell_kind(0, 0, BY)[0]
    w5b = (st_b is False) and (k_b == "#")
    say("W5b the per-CELL collision row beats the per-COLUMN verdict: b-row says the layer "
        "is occupied by a wall | standable=%s | view=%s => %s" % (st_b, k_b, w5b))
    ok &= w5b

    m5c = fake_reader(w5_payload("..")).build_dshmap(radius=1, max_age=1.0)
    m5c.cols.pop((0, 0), None)                 # 地板被清掉（实扫会这样 ✓）
    st_c = m5c.standable(0, 0, below=BY + 1)
    w5c = (st_c is False)
    say("W5c a verdict without a floor under it is NOT trusted: standable=%s => %s"
        % (st_c, w5c))
    ok &= w5c

    m5d = fake_reader(w5_payload("..")).build_dshmap(radius=1, max_age=1.0)
    m5d.cols.setdefault((0, 0), {})[BY] = FAKE2
    pre_d = m5d.standable(0, 0, below=BY + 1)
    sc_d = {"box": (0, BY - 6, 0, 0, BY + 2, 0),
            "cells": [(0, BY - 1, 0, "minecraft:grass_block"),
                      (0, BY, 0, "minecraft:oak_fence")], "truncated": False}
    inf_d = m5d.absorb_true(sc_d, BY - 6, BY + 2)
    post_d = m5d.standable(0, 0, below=BY + 1)
    w5d = (pre_d is True) and (post_d is False) and bool(inf_d.get("verdict_dropped"))
    say("W5d a fresh truth scan can retire a stale verdict: before=%s after=%s "
        "dropped=%s => %s" % (pre_d, post_d, inf_d.get("verdict_dropped"), w5d))
    ok &= w5d
    # ★W5 也碰过账本（`absorb_true` 那条学习会落盘 ✓）⇒ 照样按恢复后的内存重写文件 ✓
    MR.LEARNED.clear()
    MR.LEARNED.update(SNAP)
    MR._LEARN_DIRTY[0] = DIRTY0
    MR.learn_save(force=True)

    say("---- W1a..W1g / W2a..W2d / W3a..W3f / W5a..W5d = %s ----" % ok)
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
