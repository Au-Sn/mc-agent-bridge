#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feet_cell_test.py -- ★★"脚格"换算钉死（★§79.431✗★）★★

★★这是什么✗★★：★`pos.y` ＝ **脚底** ✗ 而"★脚格★"（★人站的那一格 ✗ 必须是空气 ✗ 模型能站✗★）
　★**不是** `floor(y)`** ✗★
★★为什么✗★★：★站在**不满一格高**的方块上时 `pos.y` 是**小数**✗★
　★`dirt_path`（★0.9375✗★）⇒ `pos.y = 70.94` ⇒ ★`floor` 给 **70** ⇒ ★那是**砖自己**那格（★实心✗★）✗★
　★半砖（★0.5✗★）⇒ `pos.y = 70.5` ⇒ ★`floor` 给 70 ⇒ 同上**错**✗★
　★⇒ ★2026-10-27 实测：★`height_conv` **4 条全红**（★C1 脚格是空气 ✗ C3 h=0 ✗ C5 standable ✗ C6 反证✗★）✗★
　★⇒ ★而**规划起点**也走同一套换算 ⇒ **起点错 ⇒ 整条路错**✗★ ✓
★★正确规则✗★★：★`cell_y = ceil(feet_y − 1e-9)`**✗★
　★整数（★71.0✗★）⇒ **71** ✓ ／ `dirt_path`（★70.9375✗★）⇒ **71** ✓ ／ 半砖（★70.5✗★）⇒ **71** ✓★
★★本判据✗★★：★直接测 `mcp_core.cell_of`**（★纯函数 ✗ 不需要游戏✗★）✗ ＋ **查全仓没人再手写 `int(float(y))`**✗★ ✓
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_core as C            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ★(fx, fy, fz) ⇒ 期望的脚格✗★
CASES = [
    ((4122.36, 71.00, 13.77), (4122, 71, 13), "整数台阶（★最常见✗★）"),
    ((4122.36, 70.9375, 13.77), (4122, 71, 13), "★`dirt_path`（★0.9375 ✗ §79.431 的元凶✗★）"),
    ((4122.50, 70.50, 13.50), (4122, 71, 13), "半砖（★0.5✗★）"),
    ((4122.50, 70.0625, 13.50), (4122, 71, 13), "雪层／薄片（★0.0625✗★）"),
    ((4122.99, 71.00, 13.99), (4122, 71, 13), "★`.99` 不许进位到下一格（★x／z 用 floor✗★）"),
    ((4122.00, 71.00, 13.00), (4122, 71, 13), "正好整数（★边界✗★）"),
    ((-1.50, 70.9375, -1.50), (-2, 71, -2), "负坐标（★`floor`/`ceil` 的边界✗★）"),
]


def main() -> int:
    checks = []

    # ── ① 纯函数：逐例对 ──
    for inp, want, why in CASES:
        got = C.cell_of(*inp)
        checks.append(("%s ⇒ %s" % (why, want), got == want, "got=%s" % (got,)))

    # ── ② `cell_from_pos`：从 dshdigest 回包取（★坏回包 ⇒ None ✗ 不静默给 0✗★）──
    o = "dshdigest name=Bot pos=4122.36,70.94,13.77 hp=20.0 onground=true"
    checks.append(("cell_from_pos 正常回包", C.cell_from_pos(o) == (4122, 71, 13),
                   "%s" % (C.cell_from_pos(o),)))
    checks.append(("cell_from_pos 坏回包 ⇒ None", C.cell_from_pos("") is None,
                   "%r" % (C.cell_from_pos(""),)))

    # ── ③ 全仓不许再手写脚格换算（★`int(float(y))` 那种✗★）──
    bad = []
    for rel in ("tools/exec3d.py", "tools/house_nav_test.py", "tools/height_conv_test.py",
                "tools/m1_measure.py"):
        p = ROOT / rel
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        # ★只抓**三个一组**的坐标转换（那种就是脚格换算✗★）
        for m in re.finditer(r"int\(float\(([^)]*)\)\)\s*\n?\s*,?\s*int\(float\(", t):
            bad.append("%s:%d" % (rel, t[:m.start()].count("\n") + 1))
    checks.append(("全仓没有残留的手写脚格换算", not bad, "%s" % (bad[:4] or "0 处",)))

    bad_n = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "★✗★", detail))
        if not ok:
            bad_n += 1
    print("  ---- %d/%d ----" % (len(checks) - bad_n, len(checks)))
    if bad_n:
        print("  => feet_cell ★FAIL★（%d 项不对 ✗ **脚格错 ⇒ 规划起点错 ⇒ 整条路错**）" % bad_n)
        print("FEETCELL ok=0 bad=%d" % bad_n)
        return 1
    print("  => feet_cell PASS ✓（★`ceil(y−ε)` ✗ 半高方块上也读到「人站的那一格」✗★）")
    print("FEETCELL ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
