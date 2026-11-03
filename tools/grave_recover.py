#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""grave_recover.py -- 把墓碑里的东西捡回来（可重复跑 ✓ 2026-09-29 第 31 轮 ✓）

WHY (第 31 轮的真事故 ✓)：
  18:56:26 游戏日志 `Bot掉出了这个世界` ✗ —— 假人掉虚空死了一次 ✓
  好在 `tombstone` 把东西存成了墓碑 ✓（日志：`The player Bot has successfully been saved` ✓）
  ⇒ 现在的目标很具体 ✓：**找到墓碑 ⇒ 走过去 ⇒ 右键打开 ⇒ 用世界真值确认背包真的多了** ✓

CRITERIA（跑之前先写 ✓）：
  G1 找得到   ：靠 `/dshmap` 的一次图把 `tombstone:grave*` 的坐标**报出来** ✓
                （图里没有 ⇒ 如实说"半径 32 内没墓碑"✗ 不许编 ✓）
  G2 站得到   ：走到墓碑**旁边那一格**（墓碑那格本身站着块块 ✗ 站不进去 ✓）——
                落脚点必须是**图上站得住**的格子 ✓（本地挑 ✓ 不猜 ✓）
  G3 真的到手 ：右键墓碑**之后**独立读一次 `dshdigest` ✓
                ⇒ **件数必须真的变多** ✓（★不看工具自己说成没成★ ✗）
  G4 诚实     ：当面说不出"东西到手"就**如实报**（换了几个面 ✓ 试了几次 ✓ 剩下什么 ✓）

用法 ✓：`py tools/grave_recover.py [--max 2] [--dry]`（`--dry` 只找不走 ✓）
ASCII-only 输出（坐标/方块名都是 ASCII ✓ 中文只在注释与说明里 ✓）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mapread as MR      # noqa: E402
import mc_mcp as M        # noqa: E402
import pathplan as PP     # noqa: E402


def say(s):
    print(s, flush=True)


def inv_now():
    """(kinds, items, free, held) —— 独立读一次（世界真值 ✓ 秒级稳定 ✓ 见 §49.3 ✓）"""
    raw = M.dsh("dshdigest 8", 30.0) or ""
    k = re.search(r"kinds=(\d+),items=(\d+),free=(\d+)", raw)
    held = re.search(r"held=(\S+)", raw)
    if not k:
        return None
    return (int(k.group(1)), int(k.group(2)), int(k.group(3)),
            held.group(1) if held else "?")


def find_graves(radius=32):
    """G1：找到墓碑（坐标 ＋ 它下面/周围哪个格子站得住 ✓）"""
    r = MR.Reader()
    m = r.build_dshmap(radius=radius)
    if m is None:
        return None, None, None
    out = []
    for (x, z), col in m.cols.items():
        for y, nm in col.items():
            if "grave" in str(nm).lower() or "tombstone" in str(nm).lower():
                out.append((int(x), int(y), int(z), str(nm)))
    # 去重（图＋blocked 行可能各报一次 ✓）
    seen = set()
    uniq = []
    for t in out:
        if t[:3] in seen:
            continue
        seen.add(t[:3])
        uniq.append(t)
    return m, r, sorted(uniq)


def pick_stand_next_to(m, level, gx, gz, from_xz=None):
    """G2：墓碑旁边**图上站得住**的那几格 —— 按"离假人近"排序**全部**返回 ✓

    ⚠ 为什么返回**全部** ✗（第 31 轮实测 ✓）：只挑最近的那一格 ⇒
      那一边的路被挡住（实测：差 **5.67 格**停住 ✓ 工具的"为什么没到"说**水平被挡**✓）
      ⇒ 就白跑一趟 ✗ —— **换一个方向绕过去**往往就够得着了 ✓
    """
    pl = PP.Planner(m, level=level, blocked=M.BLOCKED_LV)
    out = []
    for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        c = (gx + dx, gz + dz)
        if not pl.ok(*c):
            continue
        d = 0 if from_xz is None else ((c[0] - from_xz[0]) ** 2 + (c[1] - from_xz[1]) ** 2)
        out.append((d, c))
    return [c for (_d, c) in sorted(out)]


def face_from(gx, gz, bx, bz):
    """从墓碑看向假人 ⇒ 要右键的是墓碑的**那一面** ✓（`dshuse` 的面 = 被点的那一面 ✓）"""
    if bx < gx:
        return "west"
    if bx > gx:
        return "east"
    if bz < gz:
        return "north"
    if bz > gz:
        return "south"
    return "up"


def main(argv) -> int:
    dry = "--dry" in argv
    maxn = 2
    if "--max" in argv:
        try:
            maxn = int(argv[argv.index("--max") + 1])
        except Exception:
            pass
    p = M._pos_now()
    if not p:
        say("INCONCLUSIVE: no bot position (bot alive? -> py tools/respawn_bot.py)")
        return 0
    sx, sy, sz = int(p[0]), int(round(float(p[1]))), int(p[2])
    say("bot at (%d,%s,%d) feet L=%d" % (sx, p[1], sz, sy))

    before = inv_now()
    say("G3 baseline inventory: kinds/items/free/held = %s" % (before,))
    if before is None:
        say("INCONCLUSIVE: cannot read the inventory")
        return 0

    m, r, graves = find_graves()
    if m is None:
        say("INCONCLUSIVE: /dshmap unavailable")
        return 0
    say("G1 graves found in radius 32: %d %s" % (len(graves), graves[:6]))
    if not graves:
        say("=> 半径 32 内**没有墓碑** ✗（换半径再找 ✓ 或者它不在这个高度上 ✓）")
        return 0
    if dry:
        say("--dry: stopping here (found only)")
        return 0

    got_any = False
    for (gx, gy, gz, gname) in graves[:maxn]:
        say("--- grave %s at (%d,%d,%d) ---" % (gname, gx, gy, gz))
        cells = pick_stand_next_to(m, sy, gx, gz, from_xz=(sx, sz))
        if not cells:
            say("G2 cannot find a standable cell next to it (map) => skip honestly")
            continue
        say("G2 stand cells (nearest first) = %s" % (cells,))
        reached = None
        for cell in cells:
            txt, err = M.t_walk_route(cell[0], sy, cell[1], 45000, 1)
            for ln in txt.splitlines():
                if ("到位" in ln) or ("没到" in ln) or ("为什么" in ln):
                    say("   %s" % ln.strip()[:190])
            q = M._pos_now()
            if not q:
                say("   read failed after the walk => stop")
                break
            dist = ((q[0] - gx) ** 2 + (q[2] - gz) ** 2) ** 0.5
            say("   after walk to %s: (%.2f,%.2f) => %.2f blocks from the grave"
                % (cell, q[0], q[2], dist))
            if dist <= 4.0:
                reached = (cell, q)
                break
            say("   too far for `dshuse` from this side => try the NEXT side ✓")
        if not reached:
            say("G4 no approach worked (tried %d side(s)) -- reported honestly" % len(cells))
            continue
        bx, bz = int(reached[1][0] // 1), int(reached[1][2] // 1)
        tried = []
        for f in (face_from(gx, gz, bx, bz), "up", "north", "south", "east", "west"):
            if f in tried:
                continue
            tried.append(f)
            utxt, uerr = M.t_use_block(gx, gy, gz, f, 0.5)
            line = (utxt or "").strip().splitlines()
            say("   dshuse face=%-5s -> %s" % (f, (line[0][:150] if line else "(no reply)")))
            now = inv_now()
            if now and now[1] > before[1]:
                say("G3 ★INVENTORY REALLY GREW★ %s -> %s (+%d items) => recovered ✓"
                    % (before, now, now[1] - before[1]))
                got_any = True
                before = now
                break
            if now and now[0] > before[0]:
                say("G3 kinds grew %s -> %s => recovered ✓" % (before, now))
                got_any = True
                before = now
                break
        else:
            say("G4 nothing gained from this grave (tried faces: %s) -- reported honestly"
                % ",".join(tried))
    now = inv_now()
    say("final inventory: %s (started at %s)" % (now, before))
    say("=> %s" % ("RECOVERED ✓" if got_any else
                   "★没拿到东西★ ✗（按 G4 如实报：可能墓碑是空的 / 够不到 / 面不对 ✓）"))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
