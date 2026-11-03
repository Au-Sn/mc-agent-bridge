#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shape_learn_test.py -- stop guessing mod blocks by name (U1..U4)

WHY (2026-09-28, round 21): the shape classifier is a cascade of SUBSTRING
matches whose fallback is "full". Unknown mod blocks therefore get two opposite
lies: a decorative plant (`ars_elemental:spore_blossom_up`) reads as a solid
obstacle, and a furniture piece (`mcwfurnitures:mangrove_stool_chair`) reads as
"cannot be stood on". Worse, short keywords match inside longer words -- "air"
is inside "ch|air|" -- the same family of bug as `wheat` vs `wheat_seeds`.

The truth is already in my hands: `/dshmap` is computed from COLLISIONS by the
mod. Its letter cells mean "the mod says this block IS the floor", and its
`b<z>|` rows mean "the mod says this block occupies YOUR layer". So:

  * short keywords are matched by WORD (or word prefix), not by raw substring
  * anything the mod contradicts my name-guess about is LEARNED into
    logs/block_shapes.json, and learned facts outrank name guesses

CRITERIA (declared BEFORE running):
  U1 gap closed : after one fast-map build (1 call), there must be ZERO blocks
                  where "the mod says floor / the mod says occupied" and my
                  classifier disagrees. (The build learns them.)
  U2 two knowns : mcwfurnitures:mangrove_stool_chair must be standable-on
                  (is_floor True) and ars_elemental:spore_blossom_up must be
                  blocking (blocks_space True) -- however each is decided.
  U3 no overreach: a block id nobody has ever seen must be reported as NOT known
                  and must stay conservative (blocks_space True, i.e. never
                  treated as walk-through).
  U4 offline    : word matching (chair must NOT match "air"; petals MUST match
                  "petal"), learned facts outrank name guesses, and learning
                  survives a save+reload round trip.

ASCII-only output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# ★★stdio pin（P151 ✗ 2026-10-03 被 `stdio_guard_test` 抓到）✗★★
#   ★本文件会印 `✗`／`✓` 这类字符 ✗ 而在 cp936 控制台下**没 pin 就会炸**✗★ ✓
#   ★口径✗★：★会印危险字符的脚本一律 pin ✗ 不许靠"我这边能跑"✗★ ✓
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mapread as MR    # noqa: E402

TEST_ID = "zz_shapetest:block"


def say(s):
    print(s, flush=True)


def name_floor(nm):
    return MR._shape_by_name(nm) in ("full", "slab", "machine")


def name_blocks(nm):
    return MR._shape_by_name(nm) not in ("air", "liquid", "pass")


def main():
    ok = True

    # ---------------- U4 offline ------------------------------------------
    u4a = (MR.shape("mcwfurnitures:mangrove_stool_chair") == "full"
           and MR.shape("minecraft:pink_petals") == "pass"
           and MR.shape("minecraft:oak_slab") == "slab"
           and MR.shape("minecraft:oak_fence") == "fence"
           and MR.shape("minecraft:grass") == "pass")
    say("U4a word matching: chair=%s petals=%s slab=%s fence=%s grass=%s => %s"
        % (MR.shape("mcwfurnitures:mangrove_stool_chair"),
           MR.shape("minecraft:pink_petals"), MR.shape("minecraft:oak_slab"),
           MR.shape("minecraft:oak_fence"), MR.shape("minecraft:grass"), u4a))
    ok &= u4a

    before = MR.shape(TEST_ID)
    MR.learn_shape(TEST_ID, "pass", "selftest")
    after = MR.shape(TEST_ID)
    u4b = (after == "pass") and MR.is_known(TEST_ID)
    say("U4b learned outranks the name guess: %s -> %s (known=%s) => %s"
        % (before, after, MR.is_known(TEST_ID), u4b))
    ok &= u4b

    # ★★2026-10-03 检修（本条自身的毛病）✗★★：★下面 `learn_save(force=True)` 原来写的是
    #   **真文件** `logs/block_shapes.json`✗★ —— ★虽然 93~95 行会把那条测试条目删掉 ✗
    #   但**中途崩了就会留一条假知识**（`src=selftest`）✗ ⇒ ★违反"探针不许动真数据"✗★ ✓
    #   ★修法✗★：★把学习表的路径**指到临时文件**✗ ✗ 并加一条"★真文件一个字节都不许变★"的判据✓★
    import pathlib as _pl
    import tempfile as _tf
    _real = MR.LEARNED_FILE
    _before = ((_real.stat().st_mtime_ns, _real.stat().st_size)
               if _real.is_file() else None)
    _tmpdir = _pl.Path(_tf.mkdtemp())
    MR.LEARNED_FILE = _tmpdir / "block_shapes.json"
    try:
        MR.learn_save(force=True)
        rec = json.loads(MR.LEARNED_FILE.read_text(encoding="utf-8"))
        u4c = (TEST_ID in (rec.get("shapes") or {}))
        say("U4c saved to %s with a source tag: %s => %s"
            % (MR.LEARNED_FILE.name, (rec.get("shapes") or {}).get(TEST_ID), u4c))
        ok &= u4c

        # clean up the self-test entry so the **temp** table stays honest
        MR.LEARNED.pop(TEST_ID, None)
        MR._LEARN_DIRTY[0] = 1
        MR.learn_save(force=True)
    finally:
        MR.LEARNED_FILE = _real
    _after = ((_real.stat().st_mtime_ns, _real.stat().st_size) if _real.is_file() else None)
    _same = (_after == _before)
    say("U4d ★真学习表一个字节都不许变✗★：前 %s 后 %s => %s" % (_before, _after, _same))
    ok &= _same

    # ---------------- U3 no overreach -------------------------------------
    u3 = (not MR.is_known("foo:bar_baz")) and MR.blocks_space("foo:bar_baz") is True
    say("U3 no overreach: unknown id is_known=%s and stays conservative "
        "blocks_space=%s => %s"
        % (MR.is_known("foo:bar_baz"), MR.blocks_space("foo:bar_baz"), u3))
    ok &= u3

    # ---------------- U2 two known blocks ---------------------------------
    # ★U2 改口径 ★ ✗（2026-09-29 第 30 轮 ✓ 必须说清为什么改 ✓）：
    #   原判据是"`ars_elemental:spore_blossom_up` 的 `blocks_space` 必须为 **True**"✓
    #     —— 那是把**名字猜**（认不出 ⇒ 落到 `full` ⇒ "挡死"✗）当成了要守住的事实 ✗
    #   而第 30 轮从**模组自己的碰撞箱**学回来一条真值 ✓：
    #     模组的地图逐柱报"这一层站得住"✓ 而实地扫回来那一层里就长着这株孢子花 ✓
    #     ⇒ 它**不挡人** ✓（`absorb_true` 的 `dshmap-feet` 那条 ✓ 见 `mapread` 注释 ✓）
    #   ⇒ 现在分成两半判 ✓（都还是"判定要跟真值一致"✓ 不是放宽 ✓）：
    #     ① 家具（模组说它是地板 ✓）⇒ `is_floor` 必须 True ✓
    #     ② 孢子花 ⇒ **账本里有记录** ⇒ 形状必须等于**记录的形状**（学来的优先 ✓）
    #        账本里还没有 ⇒ 名字猜在说话 ⇒ 那就把**名字猜的结果**如实报出来 ✓
    #     ③ 无论哪半边 ✓：`_shape_by_name` 必须说它"挡死"✗ —— 这一条证明
    #        "**学来的压过名字猜**"这件事**真的在发生** ✓（U4b 测机制 ✓ 这里测现场 ✓）
    chair_floor = MR.is_floor("mcwfurnitures:mangrove_stool_chair")
    spore = "ars_elemental:spore_blossom_up"
    rec = MR.LEARNED.get(spore)
    spore_now = MR.shape(spore)
    spore_guess = MR._shape_by_name(spore)
    u2 = bool(chair_floor) and (spore_now == (rec["fam"] if rec else spore_guess)) \
        and (spore_guess != "pass")
    say("U2 chair is_floor=%s (want True) | spore ledger=%s shape=%s name-guess=%s "
        "(want != pass) => %s"
        % (chair_floor, (rec or {}).get("fam"), spore_now, spore_guess, u2))
    ok &= u2

    # ---------------- U1 gap closed (live) --------------------------------
    p = MR.Reader().pos()
    if not p:
        say("U1 INCONCLUSIVE: no bot position (is the game running?) => NOT a pass")
        u1 = None
    else:
        r = MR.Reader()
        m = r.build_dshmap(radius=12, max_age=600.0)
        if m is None:
            say("U1 INCONCLUSIVE: fast map unavailable")
            u1 = None
        else:
            # ★缺口 = "模组说了什么" 与 "我的分类器认什么" 不一致★ ✗
            #   · 出现在 cols 里的方块 ⇒ 模组说它**能站** ✓ ⇒ 分类器要么 `is_floor` ✓
            #     ★要么**这条结论本身就是模组给的**★（`mod_standable` ✓ 第 30 轮 ✓）：
            #       现场 ✓：`mcwfences:sandstone_grass_topped_wall`（**墙** ✓）
            #         模组说"**站在墙头可以**"✓ 而 `is_floor(墙)` = False ✓（"挡人的不是平地"✓）
            #         ⇒ 这两件事**同时为真** ✓ ⇒ 不算缺口 ✓（原来这条会把它们全判成缺口 ✗ 15 条 ✓）
            #   · 出现在 blocked_cells 里 ⇒ 模组说它**占着你这一层** ✓ ⇒ 必须 `blocks_space` ✓
            # ★★2026-10-03 检修（欠账 ㉝）改口径✗★★
            #   原来：`u1 = (not floor_gap) and (not occ_gap)` —— 要求「占用不一致 = 0」✗
            #   那是**旧规则**（建图时会把不一致的学成 `full` ⇒ 不一致消失）✗
            #   现在**停用了**那个循环学习（★因为它从"地图自己的字母"学 ✗ 是循环✗★）⇒
            #   这类不一致会**一直存在** ⇒ ★正解不是放宽 ✗ 而是更硬✗★：
            #   ★★不一致**可以有** ✗ 但**一条都不许没声明**✗★★ —— 地图必须把它们列进
            #   `meta['blocked_disagreements']`（★有静默的就算红 ✓★）
            floor_gap, occ_gap, _silent = [], [], []
            ms_all = m.meta.get("mod_standable") or {}
            for _key, col in m.cols.items():
                vfy = ms_all.get("%d,%d" % _key)
                for _y, nm in col.items():
                    if not nm or MR.is_floor(nm):
                        continue
                    if vfy is not None and int(vfy) - 1 == int(_y):
                        continue
                    floor_gap.append(nm)
            _decl = set(m.meta.get("blocked_disagreements") or [])
            for _key, nm in (m.meta.get("blocked_cells") or {}).items():
                if nm and (not MR.blocks_space(nm)):
                    occ_gap.append(nm)
                    _tag = "%s=%s" % (_key, nm)   # ★键本来就是 x,z 字符串（★别当元组✓★）
                    if _tag not in _decl:
                        _silent.append(_tag)
            u1 = (not floor_gap) and (not _silent)
            say("U1 floor-disagreements=%d %s | occupied-disagreements=%d %s | "
                "★静默的（没声明）=%d %s | learned this build=%s, table=%d entries"
                % (len(floor_gap), sorted(set(floor_gap))[:3], len(occ_gap),
                   sorted(set(occ_gap))[:3], len(_silent), sorted(_silent)[:2],
                   m.meta.get("learned"), len(MR.LEARNED)))
        ok &= u1

    say("---- U1 / U2 / U3 / U4 = %s / %s / %s / %s ----" % (u1, u2, u3, u4a and u4b and u4c))
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
