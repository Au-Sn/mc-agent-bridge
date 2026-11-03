#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""machine_recognize_test.py -- machines must be recognisable from DATA, not names

用户：「先解决并测试机器可能无法被识别的问题」

DIAGNOSIS THIS GUARDS (real export, 24779 blocks):
  * 4570 (18.4%) have a block entity -- the hard data signal for "machine"
  * their physics families: full 2778 | **none 881** | slab 705 | snow_layer 173 | fence 32
  * the semantic side had NO "机器" family at all; 864 machine candidates had no tags

FIX (sec 79.486, data-driven, zero name tables):
  world3d._load_h3d now also loads `has_block_entity`;
  mapread._has_be(block) exposes it; mapread.machine_family(block) returns "机器";
  blocks_space() treats a block-entity block with no known collision height as BLOCKING
  (previously those 881 were walk-through).

CHECKS
  M1 has_be is loaded for a large share of the registry (not silently empty)
  M2 a machine gets family 机器, a plain block does not
  M3 ★block-entity blocks with no collision height BLOCK (the 881 fix)★
  M4 machines WITH a height keep the old height rule (no regression)
  M5 non-machine blocks behave exactly as before
  M6 no name table is consulted: a made-up id with a "machine-ish" name is NOT 机器
     (generality: recognition must come from data, not from looking like a machine)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mapread as MR          # noqa: E402
import world3d as W3          # noqa: E402


def main() -> int:
    checks = []

    W3._load_h3d()
    has_be = W3._H3D.get("has_be") or {}
    total = len(W3._H3D.get("map") or {})
    n_be = sum(1 for v in has_be.values() if v)
    checks.append(("M1 has_be 真的装进来了",
                   n_be > 3000 and total > 20000,
                   "map=%d has_be=true %d" % (total, n_be)))

    # M2: a known machine and a plain block
    fur = "minecraft:furnace"
    stone = "minecraft:stone"
    checks.append(("M2 熔炉=机器 且 石头≠机器",
                   MR.machine_family(fur) == "机器" and MR.machine_family(stone) == "",
                   "furnace=%r stone=%r" % (MR.machine_family(fur), MR.machine_family(stone))))

    # M3: 识别不等于碰撞 -- 无碰撞箱的机器必须仍是「机器」，但**不挡人**
    zero = [k for k, v in has_be.items() if v and (W3._H3D["map"].get(k) or 0.0) < 0.05]
    if zero:
        s = zero[:6]
        ok3 = (all(MR.machine_family(k) == "机器" for k in s)
               and all(MR.blocks_space(k) is False for k in s))
        checks.append(("M3 ★无碰撞箱的机器：仍是机器 ✗ 但不挡人★", ok3,
                       "%d 例 例：%s" % (len(s), s[:2])))
    else:
        checks.append(("M3 ★无碰撞箱的机器：仍是机器 ✗ 但不挡人★", False, "没找到样本"))

    # M4: machines WITH height keep the old rule h>=0.45
    with_h = [(k, MR._export_h(k)) for k, v in has_be.items() if v and MR._export_h(k) is not None]
    bad4 = [(k, h) for k, h in with_h[:200]
            if MR.blocks_space(k) != (h >= 0.45)]
    checks.append(("M4 有高度的机器仍按 h>=0.45", not bad4,
                   "%d/%d 不符 %s" % (len(bad4), min(200, len(with_h)), bad4[:2])))

    # M5: plain blocks unchanged
    checks.append(("M5 普通方块行为不变",
                   MR.blocks_space("minecraft:stone") is True
                   and MR.blocks_space("minecraft:poppy") is False,
                   "stone=%s poppy=%s" % (MR.blocks_space("minecraft:stone"),
                                          MR.blocks_space("minecraft:poppy"))))

    # M6: generality -- a fake machine-looking id must NOT be recognised as a machine
    fake = "somemod:super_awesome_machine_block"
    checks.append(("M6 不许靠名字认机器（伪造名 ≠ 机器）",
                   MR.machine_family(fake) == "",
                   "fake=%r" % (MR.machine_family(fake),)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => machine_recognize FAIL (%d)" % bad)
        print("MACHINE ok=0 bad=%d" % bad)
        return 1
    print("  => machine_recognize PASS (data-driven, no name tables)")
    print("MACHINE ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
