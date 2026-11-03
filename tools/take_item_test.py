#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/take_item_test.py -- ★★"去箱子把东西拿来"判据（★净零 ✗ 不动用户世界✗★）★★（§79.444／79.445）

★★铁律✗★★：★**必须还原**（★用户的规矩✗★）⇒ 本判据**用完就放回去** ✗ 并**核对总数没变**✗★
★★做法✗★★（★用世界里**已有的**箱子 ✗ 不 `setblock`（★那个通道跑不了✗★）✗★）✗★：
　★① 先用一个**不存在的名字**探一次（★`no_match` 会列出**里面有什么** ✗ 零改动✗★）✗★
　★② ★`dshtake` 取 **8 个** wheat_seeds** ⇒ ★`got=8`**✗★
　★③ ★**背包里真的有**（★`dshinv list` 查 ✗ 不信回执✗★）✗★
　★④ ★**反向**：★取不存在的 `diamond`** ⇒ ★`why=no_match`**✗★
　★⑤ ★**反向**：★对空气取** ⇒ ★`why=no_block_entity`**✗★
　★⑥ ★**`dshstore` 把 8 个放回去** ⇒ ★`put=8`**✗★
　★⑦ ★**再探一次** ⇒ ★内容与①**完全一致**（★净零 ✗ 世界没变✗★）✗★ ✓
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C            # noqa: E402

CHEST = (4105, 71, 18)          # ★已知有 wheat_seeds 的箱子✗★
ITEM = "wheat_seeds"
N = 8


def cmd(s, t=30.0):
    return (C.dsh(s, t) or "").strip()


def probe():
    """★探内容（★取不存在的名字 ✗ 零改动✗★）✗★"""
    r = cmd('dshtake %d %d %d __probe__' % CHEST)
    m = re.search(r"have\[(.*?)\]", r)
    return (m.group(1) if m else None), r


def inv_count(item):
    o = cmd("dshinv list")
    total = 0
    for m in re.finditer(r"(\d+):([a-z0-9_:.]+)x(\d+)", o):
        if item in m.group(2):
            total += int(m.group(3))
    return total, o[:160]


def main() -> int:
    checks = []
    print("  箱子：%s ｜ 目标物品：%s ｜ 取 %d 个" % (CHEST, ITEM, N))

    # ① 探内容
    before, raw0 = probe()
    print("  ① 取前内容：%s" % (str(before)[:170],))
    checks.append(("能探到箱子内容（no_match 列出 have[]）", before is not None, str(before)[:100]))
    if before is None:
        print("TAKEITEM ok=0 reason=cannot_probe")
        return 4

    inv0, _ = inv_count(ITEM)
    print("     取前背包 %s：%d" % (ITEM, inv0))

    # ② 取 8 个
    r2 = cmd('dshtake %d %d %d %s %d' % (CHEST[0], CHEST[1], CHEST[2], ITEM, N))
    print("  ② dshtake：%r" % r2[:180])
    checks.append(("`dshtake` 拿到 %d 个（got=%d）" % (N, N), ("got=%d" % N) in r2, r2[:120]))
    checks.append(("回执带 left=（剩余数量）", "left=" in r2, "有" if "left=" in r2 else "没有"))

    # ③ 背包真查
    inv1, snap = inv_count(ITEM)
    print("     取后背包 %s：%d（★应 +%d✗★）" % (ITEM, inv1, N))
    checks.append(("背包真的多了 %d 个（不信回执，查背包）" % N, inv1 >= inv0 + N,
                   "%d → %d" % (inv0, inv1)))

    # ④ 反向：取不存在
    r4 = cmd('dshtake %d %d %d diamond' % CHEST)
    print("  ④ 取 diamond：%r" % r4[:150])
    checks.append(("取不存在的 ⇒ why=no_match（不静默 0）", "no_match" in r4, r4[:110]))

    # ⑤ 反向：对空气
    r5 = cmd('dshtake %d %d %d %s' % (CHEST[0], CHEST[1], CHEST[2] + 6, ITEM))
    print("  ⑤ 对空气取：%r" % r5[:150])
    checks.append(("对空气取 ⇒ why=no_block_entity", "no_block_entity" in r5, r5[:110]))

    # ⑥ 放回去
    r6 = cmd('dshstore %d %d %d %s %d' % (CHEST[0], CHEST[1], CHEST[2], ITEM, N))
    print("  ⑥ dshstore：%r" % r6[:180])
    checks.append(("`dshstore` 放回 %d 个（put=%d）" % (N, N), ("put=%d" % N) in r6, r6[:120]))

    # ⑦ 净零核对
    after, raw7 = probe()
    print("  ⑦ 取后内容：%s" % (str(after)[:170],))
    same = (before == after)
    checks.append(("★世界净零（内容与取前完全一致）", same, "一致" if same else "★变了★"))
    inv2, _ = inv_count(ITEM)
    checks.append(("背包也回到取前（%d → %d）" % (inv0, inv2), inv2 == inv0, "%d → %d" % (inv0, inv2)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => take_item ★FAIL★（%d 项不对）" % bad)
        print("TAKEITEM ok=0 bad=%d" % bad)
        return 1
    print("  => take_item PASS ✓（★真的取到 ✗ 拿不到说实话 ✗ **用完放回 ✗ 世界净零**✗★）")
    print("TAKEITEM ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
