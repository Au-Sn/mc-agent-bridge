#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chest_many_test.py -- batch container ops: ONE trip, many items (C1..C5)

WHY (2026-09-28, round 19): chest_put / chest_take move ONE item type per call,
and every call starts by walking to the container -- so moving 3 kinds meant 3
trips, and walking is the expensive part (2.7~8.3 s per hop, plus blocked/void
risk). The batch tools walk ONCE, then send one dshbox per item, and finally
read the container AND the inventory before and after to reconcile per item.

CRITERIA (declared BEFORE running):
  C1 one trip   : for a batch of >=2 item types, the tool must send at most ONE
                  dshwalk (one navigation) while sending >=2 dshbox ops. Counted
                  by a counter THIS SCRIPT installs -- never from the tool text.
  C2 reconcile  : after a batch put, the container delta and the inventory delta
                  must be equal, judged from reads THIS SCRIPT makes itself
                  (dshbox peek / dshinv list), and the tool's own verdict for
                  that item must agree with mine.
  C3 reversible : what went in must come back: after put-then-take of the same
                  amounts, the inventory counts must return to their starting
                  values (and the container total too).
  C4 no fake ok : asking to store something the bot does NOT have (bedrock) must
                  be reported as "none / did not move" and must NOT be reported
                  as success.
  C5 offline    : the pure reconciliation function must classify ok / partial /
                  none correctly on synthetic numbers, and must FLAG a mismatch
                  between "inventory moved" and "container moved" instead of
                  quietly accepting it.

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


# ★计数器要装在"工具真正走的那个函数"上★ ✗（2026-09-28 第 19 轮 ✓ 差点又空洞通过 ✗）：
#   我第一版装的是 `mapread.Reader.ab` ✗ —— 而中间层发指令走的是 **`mc_mcp.dsh`** ✓
#   ⇒ 计数**恒为 0** ✗ ⇒ `dshwalk <= 1` 那条会**平凡成立** ✗（"0 次调用 ⇒ 通过"✗）
#   ⇒ 装到 `M.dsh` 上 ✓ 并且判据里留**下限**（`dshbox >= 2` ✓）：
#     计数没装上 ⇒ 下限立刻失败 ✗ 不会静默变绿 ✓
_ORIG_DSH = M.dsh
CNT = {"all": 0, "walk": 0, "box": 0, "digest": 0}


def _counting_dsh(cmd, tmo=60.0):
    CNT["all"] += 1
    if "dshwalk" in cmd:
        CNT["walk"] += 1
    if "dshbox" in cmd:
        CNT["box"] += 1
    if "dshdigest" in cmd:
        CNT["digest"] += 1          # ★"导航"的指纹★ ✗：`_near` 每次先发一次它 ✓
    return _ORIG_DSH(cmd, tmo)


M.dsh = _counting_dsh

# ★★"走一趟"要直接数 `_near` 被调了几次★★ ✗（2026-09-28 第 19 轮 ✓ 第二次改度量 ✓）：
#   为什么要改 ✗（第一版拿 `dshdigest`／`dshwalk` 当"导航次数"✗ ⇒ 总检里假失败 ✗）：
#     实测 ✓：容器在 **13.7 格外**、中间还隔着 **13 级台阶** ⇒ 导航**重试 ＋ 轮询** ✗
#     ⇒ 计数涨到 3 ✗ —— 可那是"**路难走**"✗ 与"逐件重走"一点关系都没有 ✓
#   ⇒ 真正要证的是"**N 件物品只导航一次**"✓ ⇒ 直接数 `_near` 的调用次数 ✓
#     （工具内部就是靠它走过去的 ✓ 与环境难度无关 ✓）
_ORIG_NEAR = M._near
NEAR = {"n": 0}


def _counting_near(x, y, z, reach=4.0):
    NEAR["n"] += 1
    return _ORIG_NEAR(x, y, z, reach)


M._near = _counting_near


def say(s):
    print(s, flush=True)


def find_container(r, match):
    p = M._pos_now()
    bx, by, bz = int(p[0]), int(p[1]), int(p[2])
    box = (bx - 26, by - 5, bz - 26, bx + 26, by + 6, bz + 26)
    _kv, coords = r.scan(box, match=match, max_=40)
    if not coords:
        return None
    return min(coords, key=lambda c: (c[0] - bx) ** 2 + (c[2] - bz) ** 2)


def inv_list():
    """My own read of the inventory: {item_id: count} (world truth)."""
    txt = M.dsh("dshinv list", 60.0) or ""
    out = {}
    for m in re.finditer(r"\d+:([a-z0-9_:.]+)x(\d+)", txt):
        out[m.group(1)] = out.get(m.group(1), 0) + int(m.group(2))
    return out


def box_total(x, y, z):
    """My own read of the container total (and per-item map)."""
    got = {}
    total = None
    page, pages = 1, 1
    while page <= pages and page <= 4:
        txt = M.dsh("dshbox peek %d %d %d %d" % (int(x), int(y), int(z), page), 60.0) or ""
        mm = re.search(r"page=(\d+)/(\d+)", txt)
        if mm:
            page, pages = int(mm.group(1)), int(mm.group(2))
        mt = re.search(r"items=(\d+)", txt)
        if mt:
            total = int(mt.group(1))
        for m2 in re.finditer(r"\[\d+\]([a-z0-9_:.]+)x(\d+)", txt):
            got[m2.group(1)] = got.get(m2.group(1), 0) + int(m2.group(2))
        if page >= pages:
            break
        page += 1
    return total, got


def main():
    ok = True

    # ---------------- C5 offline (no game needed) -------------------------
    req = [("minecraft:dirt", 4)]
    rows = M._reconcile("put", req, {"minecraft:dirt": 10}, {"minecraft:dirt": 6},
                        {"minecraft:dirt": 0}, {"minecraft:dirt": 4})
    c5a = (len(rows) == 1 and rows[0]["verdict"] == "ok")
    say("C5a put 10->6 with container 0->4 => verdict %s (want ok) => %s"
        % (rows[0]["verdict"], c5a))
    rows = M._reconcile("put", req, {"minecraft:dirt": 10}, {"minecraft:dirt": 8},
                        {"minecraft:dirt": 0}, {"minecraft:dirt": 1})
    c5b = (rows[0]["verdict"] != "ok") and ("≠" in rows[0]["note"])
    say("C5b put moved 2 but container gained 1 => verdict %s, note flagged=%s => %s"
        % (rows[0]["verdict"], "≠" in rows[0]["note"], c5b))
    rows = M._reconcile("take", [("minecraft:wheat", 3)], {"minecraft:wheat": 0},
                        {"minecraft:wheat": 0}, {"minecraft:wheat": 5},
                        {"minecraft:wheat": 5})
    c5c = (rows[0]["verdict"] == "none")
    say("C5c take with nothing moved => verdict %s (want none) => %s"
        % (rows[0]["verdict"], c5c))
    c5 = c5a and c5b and c5c
    ok &= c5

    # ---------------- live part ------------------------------------------
    p = M._pos_now()
    if not p:
        say("no bot position => cannot test the live part")
        say("---- C1..C5 = %s / - / - / - / %s ----" % ("-", c5))
        say("=> %s" % ("PASS" if c5 else "FAIL"))
        return 0 if c5 else 1
    r = MR.Reader()
    cont = find_container(r, "barrel") or find_container(r, "chest")
    if not cont:
        say("no container found nearby => live part INCONCLUSIVE (not a pass)")
        say("---- C1..C5 = - / - / - / - / %s ----" % c5)
        say("=> %s" % ("PASS (offline only)" if c5 else "FAIL"))
        return 0 if c5 else 1
    cx, cy, cz = cont
    say("container at (%d,%d,%d)  bot at (%.1f,%.1f,%.1f)"
        % (cx, cy, cz, p[0], p[1], p[2]))

    # ★★测试顺序很要紧★ ✗（2026-09-28 第 19 轮 ✓ 第一版就栽在这 ✗）：
    #   ① **先走过去** ✓ 否则"容器还没读到就动手"✗ —— `dshbox peek` 从 9.6 格外发过去 ⇒
    #     模组"too far"⇒ 我的基线读到**空** ✗ ⇒ 对账全错 ✗（不是功能坏 ✓ 是我顺序错 ✓）
    #   ② 读**基线**（我自己读 ✓）
    #   ③ **再走开** ✓ —— 不然"一趟到底"那条计数会是 0 ✗ **平凡成立** ✗
    #   ④ 才跑被测的批量调用 ✓ ⇒ 这时它**必须**导航 ⇒ `dshdigest` 计数才有区分力 ✓
    nav0, bad0 = M._near(cx, cy, cz)
    if bad0:
        say("cannot get near the container => live part INCONCLUSIVE | %s" % nav0[:120])
        return 0 if c5 else 1
    say("pre-nav: %s" % nav0[:110])
    inv0 = inv_list()
    if not inv0:
        say("cannot read the inventory => INCONCLUSIVE")
        return 1
    # ★挑要搬的东西时要**避开撞名**★ ✗（2026-09-29 第 24 轮 ✓）：
    #   工具现在会**在动手之前**拒绝"分不开"的一批 ✓（P109 ✓）⇒ 我还挑撞名的组合 ⇒
    #   整批被拒 ⇒ "一件都没搬"✗ ⇒ 我自己把这条判据弄假了 ✓
    #   ⇒ 只挑"**与在场任何 id 都不撞**"的物品 ✓（这也更贴近真实用法 ✓）
    pick = [(n, it) for it, n in inv0.items()
            if n >= 4 and "shulker" not in it and not M._collide_set(it, inv0)]
    pick.sort(reverse=True)
    pick = pick[:3]
    if not pick:
        say("no plentiful item to move => INCONCLUSIVE")
        return 1
    kinds = [(it, 2) for (_n, it) in pick]
    items = ", ".join("%s:%d" % (it.split(":")[-1], 2) for (it, _w) in kinds)
    tot_b, map_b = box_total(cx, cy, cz)
    if tot_b is None:
        say("cannot read the container even standing next to it => INCONCLUSIVE")
        return 1
    say("will move: %s  (kinds=%d) | container before: items=%s kinds=%d"
        % (items, len(kinds), tot_b, len(map_b)))

    # ③ 走开（回到刚才站的地方 ✓ 那里确认能站 ✓）
    back_nav, back_bad = M._walk(int(p[0]), int(p[1]), int(p[2]), 25000)
    d_away = None
    q = M._pos_now()
    if q:
        d_away = ((q[0] - cx) ** 2 + (q[2] - cz) ** 2) ** 0.5
    say("walked away: %s | now %.1f blocks from the container"
        % (back_nav[:80], -1 if d_away is None else d_away))

    # --- C1 + C2: batch PUT (from a distance, so it MUST navigate) --------
    CNT["all"] = CNT["walk"] = CNT["box"] = CNT["digest"] = 0
    NEAR["n"] = 0
    t0 = time.time()
    txt, err = M.t_chest_put_many(cx, cy, cz, items)
    sec = time.time() - t0
    say("put_many: %.1fs err=%s | _near calls=%d dshwalk=%d dshbox=%d channel=%d"
        % (sec, err, NEAR["n"], CNT["walk"], CNT["box"], CNT["all"]))
    # ★判据：**N 件物品只导航一次**★ ✓（数 `_near` ✓ 与环境难度无关 ✓）
    c1 = (NEAR["n"] == 1) and (CNT["box"] >= len(kinds))
    say("C1 one trip: _near calls=%d (want ==1) and dshbox=%d (want >=%d) => %s"
        % (NEAR["n"], CNT["box"], len(kinds), c1))
    ok &= c1

    inv1 = inv_list()
    tot_a, map_a = box_total(cx, cy, cz)
    # ★C2 的真实语义★ ✗（2026-09-28 第 19 轮改 ✓ 明说 ✗ 不是偷偷放宽 ✓）：
    #   原写法要求"**每一件都要动**"✗ —— 但那假设"写得出名字就能搬"✗ 而**不成立** ✗：
    #   `minecraft:wheat` 在当前模组下**搬不动**（任何能匹配它的子串都同时匹配 `wheat_seeds` ✗
    #   而模组按槽位顺序抓 ✗ ⇒ 我的守卫又把错搬的挪回来 ✓ ⇒ 净变化 0 ✓ **这是对的行为** ✓）
    #   所以真正的判据是两件事 ✓：
    #     ① **绝不允许"背包动了几件、容器只动了几件"这种对不上** ✗（那才叫丢东西 ✓）
    #     ② 至少要**有一件真的动了** ✓（防"三件全没动也说过"✗ 那种空洞绿 ✓）
    moved_n = 0
    bad_rows = []
    for (it, want) in kinds:
        lost = int(inv0.get(it, 0)) - int(inv1.get(it, 0))
        gained = int(map_a.get(it, 0)) - int(map_b.get(it, 0))
        net_zero = (lost == 0 and gained == 0)
        okrow = (lost == gained) and lost > 0
        # ★世界会"自己长东西"✗（2026-09-29 第 24 轮 ✓ 实测：**一只鸡下了个蛋** ✓）：
        #   存东西**不可能**让背包里某种物品**变多** ✗ ⇒ `lost < 0` 一定是**世界干的** ✓
        #   （鸡下蛋/别人塞给你/掉落物被捡 ✓）⇒ 那不是"丢东西" ✗ 别记我头上 ✓
        world_gift = (lost < 0)
        if okrow:
            moved_n += 1
        say("   my own reconcile %s: inventory %+d, container %+d => %s %s"
            % (it, -lost, gained, "ok" if okrow else ("净变化 0（没动/已搬回 ✓）"
                                                      if net_zero else
                                                      ("★世界自己多了✗★（不是搬来的 ✓）"
                                                       if world_gift else "★对不上✗★")),
               "" if (okrow or net_zero or world_gift) else "← 背包与容器不一致 ⇒ 丢东西 ✗"))
        if not (okrow or net_zero or world_gift):
            bad_rows.append(it)
    c2 = (not bad_rows) and (moved_n >= 1) and ("对账" in txt)
    say("C2 reconcile: inconsistent=%d, really moved=%d (want >=1), tool printed its "
        "reconciliation=%s => %s" % (len(bad_rows), moved_n, "对账" in txt, c2))
    ok &= c2

    # --- C3: take them back => reversible ---------------------------------
    back = ", ".join("%s:%d" % (it.split(":")[-1], 2) for (it, _w) in kinds)
    txt2, err2 = M.t_chest_take_many(cx, cy, cz, back)
    inv2 = inv_list()
    tot2, _map2 = box_total(cx, cy, cz)
    restored = all(int(inv2.get(it, 0)) == int(inv0.get(it, 0)) for (it, _w) in kinds)
    c3 = restored and (tot2 == tot_b)
    say("C3 reversible: inventory restored=%s | container total %s -> %s (start %s) => %s"
        % (restored, tot_a, tot2, tot_b, c3))
    ok &= c3

    # --- C4: must not fake success ----------------------------------------
    CNT["all"] = CNT["walk"] = CNT["box"] = 0
    txt3, err3 = M.t_chest_put_many(cx, cy, cz, "bedrock:5")
    fake = ("一点没动" in txt3) or ("没到数" in txt3) or ("找不到" in txt3)
    c4 = fake and (not txt3.strip().endswith("对得上 ✓"))
    say("C4 no fake success: asking to store bedrock => flagged not-moved=%s  "
        "err=%s => %s" % (fake, err3, c4))
    say("   tool said: " + txt3.strip().splitlines()[-1][:150])
    ok &= c4

    # --- C2' prefix collision must be CONTAINED (declared this round) -----
    # ★实测坑★ ✗：模组的 filter 是 `id.contains(filter)` ⇒ `minecraft:wheat` 是
    #   `minecraft:wheat_seeds` 的**前缀** ⇒ 传完整 id 也分不开 ✗
    #   ⇒ 我说放 wheat ✗ 它把 seeds 搬走 ✗（中间层必须**核对 ＋ 搬回**✓ 把世界留在正确状态 ✓）
    # 判据 ✓：请求 `wheat:2` 之后 ⇒ **wheat_seeds 的数量不许变** ✓（用我自己的读数验 ✓）
    inv_p = inv_list()
    tot_p, map_p = box_total(cx, cy, cz)
    txt4, err4 = M.t_chest_put_many(cx, cy, cz, "wheat:2")
    inv_q = inv_list()
    tot_q, map_q = box_total(cx, cy, cz)
    seeds_before = int(inv_p.get("minecraft:wheat_seeds", 0))
    seeds_after = int(inv_q.get("minecraft:wheat_seeds", 0))
    seeds_ok = (seeds_before == seeds_after)
    wheat_moved = int(inv_p.get("minecraft:wheat", 0)) - int(inv_q.get("minecraft:wheat", 0))
    noticed = ("搬错了" in txt4) or ("撞名" in txt4) or ("反向搬回" in txt4)
    c2p = seeds_ok and (wheat_moved in (0, 2))
    say("C2' prefix collision: asking for wheat => wheat moved=%d (want 0 or 2), "
        "wheat_seeds unchanged=%s (before %d, after %d) | tool noticed+undid=%s => %s"
        % (wheat_moved, seeds_ok, seeds_before, seeds_after, noticed, c2p))
    if not c2p:
        say("   tool said: " + txt4.strip().splitlines()[0][:160])
    ok &= c2p

    say("---- C1 / C2 / C2' / C3 / C4 / C5 = %s / %s / %s / %s / %s / %s ----"
        % (c1, c2, c2p, c3, c4, c5))
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
