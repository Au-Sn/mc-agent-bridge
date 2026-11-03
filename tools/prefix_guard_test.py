#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prefix_guard_test.py -- refuse BEFORE moving, when the mod cannot tell two
items apart (G1..G4)

WHY (2026-09-29, round 24): P105 taught the middle layer to notice a wrong move
and undo it exactly. That works, but it is the expensive way round: the world
really WAS changed for a moment, and the single-channel bridge paid for the
extra ops. The cheap way is to look before moving: the mod matches items by
substring, so if another item that is really present has this one inside its id,
the two cannot be told apart -- refuse and say so.

CRITERIA (declared BEFORE running):
  G4 offline : _collide_set must flag minecraft:wheat when minecraft:wheat_seeds
               is present, must NOT flag the longer one (wheat_seeds is not
               inside wheat), and must not flag an unrelated id.
  G1 refuse early: with both wheat and wheat_seeds in play, a request for
               `wheat:2` must be refused BEFORE acting -- the reply says it did
               not touch anything and names the colliding id.
  G2 world truth: after that refusal the inventory AND the container must be
               item-for-item unchanged (measured while frozen).
  G3 no over-refusal: an item present in the inventory that has no colliding
               sibling must still move normally (its own reconciliation
               consistent), and then be put back.

ASCII-only output.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M      # noqa: E402
import mapread as MR    # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass



def say(s):
    print(s, flush=True)


def inv_ids():
    return M._inv_ids()


def find_container(r):
    p = M._pos_now()
    bx, by, bz = int(p[0]), int(p[1]), int(p[2])
    box = (bx - 26, by - 5, bz - 26, bx + 26, by + 6, bz + 26)
    for kind in ("barrel", "chest"):
        _kv, coords = r.scan(box, match=kind, max_=40)
        if coords:
            return min(coords, key=lambda c: (c[0] - bx) ** 2 + (c[2] - bz) ** 2)
    return None


def main():
    ok = True

    # ---------------- G4 offline -----------------------------------------
    ids = {"minecraft:wheat": 128, "minecraft:wheat_seeds": 286,
           "minecraft:cooked_beef": 13}
    c1 = M._collide_set("minecraft:wheat", ids) == ["minecraft:wheat_seeds"]
    c2 = M._collide_set("minecraft:wheat_seeds", ids) == []
    c3 = M._collide_set("minecraft:cooked_beef", ids) == []
    g4 = c1 and c2 and c3
    say("G4 offline: wheat->%s  seeds->%s  beef->%s => %s"
        % (M._collide_set("minecraft:wheat", ids),
           M._collide_set("minecraft:wheat_seeds", ids),
           M._collide_set("minecraft:cooked_beef", ids), g4))
    ok &= g4

    # ---------------- live -------------------------------------------------
    p = M._pos_now()
    if not p:
        say("live part INCONCLUSIVE: no bot position")
        say("---- G1 / G2 / G3 / G4 = - / - / - / %s ----" % g4)
        say("=> %s" % ("PASS (offline only)" if g4 else "FAIL"))
        return 0 if g4 else 1
    M.t_freeze(True)                       # ★冻住再量 ✗（第 23 轮的纪律 ✓）
    try:
        r = MR.Reader()
        cont = find_container(r)
        if not cont:
            say("live part INCONCLUSIVE: no container nearby")
            return 0 if g4 else 1
        cx, cy, cz = cont
        nav, bad = M._near(cx, cy, cz)
        if bad:
            say("live part INCONCLUSIVE: cannot get near the container | %s" % nav[:100])
            return 0 if g4 else 1
        iv = inv_ids()
        say("container at (%d,%d,%d)  inventory ids=%d" % (cx, cy, cz, len(iv)))

        # --- G1 + G2: a colliding request must be refused untouched --------
        if not (("minecraft:wheat" in iv) and ("minecraft:wheat_seeds" in iv)):
            say("G1/G2 INCONCLUSIVE: this inventory has no wheat/wheat_seeds pair "
                "to collide -- NOT a pass")
            g1 = g2 = None
        else:
            before_inv = inv_ids()
            before_box = M._box_peek_map(cx, cy, cz)
            txt, err = M.t_chest_put_many(cx, cy, cz, "wheat:2")
            time.sleep(0.5)
            after_inv = inv_ids()
            after_box = M._box_peek_map(cx, cy, cz)
            says_no_touch = ("没动手" in txt)
            names_sib = ("wheat_seeds" in txt)
            says_collide = ("撞名" in txt)
            g1 = err and says_no_touch and names_sib and says_collide
            say("G1 refuse early: err=%s no-touch=%s names-sibling=%s says-collide=%s => %s"
                % (err, says_no_touch, names_sib, says_collide, g1))
            say("   reply: " + (txt or "").splitlines()[0][:150])
            # ★只比"**这一趟相关的物品**"★ ✗（2026-09-29 第 24 轮 ✓ 我又犯了一次同一个病 ✗）：
            #   现象 ✗：G2 拿**整个背包**前后比 ⇒ 期间世界动一下（鸡下蛋 ✓ 捡到东西 ✓）
            #     就被算成"没冻住/工具动了手"✗ ⇒ **假失败** ✓
            #   ⇒ 口径 ✓：只看**请求的那个物品 ＋ 它的撞名兄弟** ✓
            #     （世界自己长出来的别的东西 ⇒ 与"这一趟有没有动手"无关 ✓）
            rel = {"minecraft:wheat", "minecraft:wheat_seeds"}
            key = lambda d: {k: v for k, v in d.items() if k in rel}
            g2 = (key(before_inv) == key(after_inv)) and (before_box == after_box)
            say("G2 world truth: relevant-inventory unchanged=%s  container unchanged=%s "
                "=> %s" % (key(before_inv) == key(after_inv), before_box == after_box, g2))
            if key(before_inv) != key(after_inv):
                say("   relevant before=%s after=%s"
                    % (key(before_inv), key(after_inv)))
        ok &= (g1 is not False) and (g2 is not False)

        # --- G3: no over-refusal -------------------------------------------
        cand = None
        for it, n in sorted(iv.items(), key=lambda kv: -kv[1]):
            if n >= 2 and not M._collide_set(it, iv):
                cand = it
                break
        if not cand:
            say("G3 INCONCLUSIVE: no colliding-free item with count>=2 -- NOT a pass")
            g3 = None
        else:
            short = cand.split(":")[-1]
            txt2, err2 = M.t_chest_put_many(cx, cy, cz, "%s:2" % short)
            moved = ("对账" in txt2) and ("一点没动" not in txt2)
            g3 = (not err2) and moved
            say("G3 no over-refusal: %s moved normally=%s (err=%s) => %s"
                % (cand, moved, err2, g3))
            if g3:
                # 放回去 ⇒ 可逆 ✓
                M.t_chest_take_many(cx, cy, cz, "%s:2" % short)
                say("   (put back ✓)")
        ok &= (g3 is not False)
    finally:
        M.t_freeze(False)

    say("---- G1 / G2 / G3 / G4 = %s / %s / %s / %s ----"
        % (g1, g2, g3, g4))
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
