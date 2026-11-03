#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut_diff.py -- ★把"★切了会改哪几条 ✗ 改成了什么★"摊开✗★（★§79.192 ✗ 离线✗★）

★★为什么✗★★：★`cut_ready` 只给"★会改几个★"✗★ ⇒ ★而挑第一刀要知道**改的性质**✗★：
  ★老路说 A ✗ 导出说 B ✗★ ⇒ ★★那是"★老路漏了（★导出更真✗★）" 还是 "★导出更松（★要小心✗★）"✗★★ ✓
★★三栏✗★★（★每次比对都标出来 ✗ 便于一眼分类✗★）
  · ★`改挡人`✗★：★`blocks_space` 变了 ✗ 记 `True→False`（★变松 ✗ 能穿过去了✓★）／`False→True`（★变紧✓★）✗★
  · ★`改能站`✗★：★`is_floor` 变了 ✗ 同上✗★
  · ★`改字母`✗★：★`cat` 变了 ✗ 只是**地图上画的字**变 ✗ 不影响物理✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import blockkb as KB  # noqa: E402
import kb_export as KX  # noqa: E402
import mapread as MR  # noqa: E402

FIELDS = [("blocks_space", MR.blocks_space), ("is_floor", MR.is_floor), ("cat", MR.cat)]


LOOSE_ONLY = False


def main(argv):
    global LOOSE_ONLY
    if argv and argv[0] in ("--loose", "-l"):
        LOOSE_ONLY = True
        argv = argv[1:]
    ns = argv[0] if argv else "luminax"
    top = int(argv[1]) if len(argv) > 1 else 12
    exp = json.loads(KX.find_export("").read_text(encoding="utf-8"))
    blocks = exp.get("blocks") or {}
    mine = sorted(sp for sp in blocks if sp.startswith(ns + ":"))
    print("== `%s` ✗ %d 个方块 ✗ 逐条摊开 ==" % (ns, len(mine)))

    kinds = {}
    shown = 0
    skip = 0
    for sp in mine:
        KB.SOURCE = "blacklist"
        try:
            old = {f: fn(sp) for f, fn in FIELDS}
        except Exception:
            skip += 1
            continue
        KB.SOURCE = "table"
        try:
            new = {f: fn(sp) for f, fn in FIELDS}
        except Exception:
            skip += 1
            continue
        if old == new:
            continue
        # ★给这次变更**起个名字**✗★
        tags = []
        if old["blocks_space"] != new["blocks_space"]:
            tags.append("改挡人 %s→%s" % (old["blocks_space"], new["blocks_space"]))
        if old["is_floor"] != new["is_floor"]:
            tags.append("改能站 %s→%s" % (old["is_floor"], new["is_floor"]))
        if old["cat"] != new["cat"]:
            tags.append("改字母 %s→%s" % (old["cat"], new["cat"]))
        key = " ＋ ".join(tags)
        kinds[key] = kinds.get(key, 0) + 1
        # ★★`--loose`：★只印"★变松★"那几条✗★★（★§79.195 ✗ 丙档要看的就是它们✗★）✗★
        _loose_here = any(s.startswith("改挡人 True→False") or s.startswith("改能站 True→False")
                          for s in tags)
        if LOOSE_ONLY and not _loose_here:
            continue
        if shown < top:
            # ★★每条带上**导出的凭什么**✗★★（★§79.194✗★）✗★：
            #   ★族名 ＋ 碰撞高度 ＋ 出处 ✗ 这样"★纠正★"才有**可审**的依据✗★ ✓
            #   ★（★"★判据是导出★"**不等于**"★导出一定对★" ✗ 所以要看证据✓★）
            _e = blocks.get(sp) or {}
            _ev = "族=%s h=%s src=%s" % (_e.get("family", "?"),
                                         _e.get("max_height", "?"),
                                         str(_e.get("src", ""))[:14])
            print("   %-44s %-34s %s" % (sp, key, _ev))
            shown += 1
    KB.SOURCE = "blacklist"
    print("")
    print("★比过 %d ✗ 跳过 %d✗★" % (len(mine) - skip, skip))
    print("★变更按**性质**归类✗★：")
    for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print("   %-42s %5d" % (k, n))
    if not kinds:
        print("   ★一条都没有 ✗ 切过去一模一样✗★")
    return 0


def survey(min_blocks: int = 40, top: int = 60):
    """★把每个命名空间**按改动方向分档**✗★（★§79.193 ✗ 挑刀用✗★）

    ★★三档✗★★
      ★甲✗★：★零改动✗★ ⇒ ★随时可切✗★ ✓
      ★乙✗★：★改动**全为** `False→True`（★老路漏了 ✗ 导出补上✗★）✗★ ⇒ ★纠正✗★ ✓
      ★丙✗★：★含 `True→False`（★变松✗★）✗★ ⇒ ★必须先逐条看清✗★ ✓
    """
    exp = json.loads(KX.find_export("").read_text(encoding="utf-8"))
    blocks = exp.get("blocks") or {}
    by_ns = {}
    for sp in blocks:
        by_ns.setdefault(sp.split(":")[0], []).append(sp)

    out = {"甲": [], "乙": [], "丙": [], "丁": []}
    for ns, mine in sorted(by_ns.items(), key=lambda kv: -len(kv[1])):
        if len(mine) < min_blocks:
            continue
        loose = 0          # ★True→False（★变松✗★）
        tight = 0          # ★False→True（★变紧／补上✗★）
        chg = 0
        skip = 0
        for sp in sorted(mine):
            KB.SOURCE = "blacklist"
            try:
                old = {f: fn(sp) for f, fn in FIELDS}
            except Exception:
                skip += 1
                continue
            KB.SOURCE = "table"
            try:
                new = {f: fn(sp) for f, fn in FIELDS}
            except Exception:
                skip += 1
                continue
            if old == new:
                continue
            chg += 1
            for f in ("blocks_space", "is_floor"):
                if old[f] is True and new[f] is False:
                    loose += 1
                elif old[f] is False and new[f] is True:
                    tight += 1
        KB.SOURCE = "blacklist"
        row = (ns, len(mine), chg, loose, tight, skip)
        if skip:
            out["丁"].append(row)          # ★有跳过 ⇒ **不许**分进甲／乙／丙✗★
        elif chg == 0:
            out["甲"].append(row)
        elif loose == 0:
            out["乙"].append(row)
        else:
            out["丙"].append(row)

    print("== 挑刀表 ✗ 按改动方向分档（★≥%d 个方块✗★）==" % min_blocks)
    print("   ★甲 零改动 ✗ %d 个模组✗★" % len(out["甲"]))
    for ns, n, c, l, ti, s in out["甲"][:top]:
        print("      %-26s %5d 个方块 ✗ 一处不改✗★" % (ns, n))
    print("")
    print("   ★乙 改动全为「★补上★」（★False→True ✗ 纠正✓★）✗ %d 个✗★" % len(out["乙"]))
    print("      %-26s %6s %7s %7s" % ("模组", "方块", "改动", "补上"))
    for ns, n, c, l, ti, s in out["乙"][:top]:
        print("      %-26s %6d %7d %7d" % (ns, n, c, ti))
    print("")
    print("   ★★丙 含「★变松★」（★True→False ✗ 危险✓★）✗ %d 个✗★★" % len(out["丙"]))
    print("      %-26s %6s %7s %7s" % ("模组", "方块", "改动", "★变松✗★"))
    for ns, n, c, l, ti, s in sorted(out["丙"], key=lambda r: -r[3])[:top]:
        print("      %-26s %6d %7d %7d" % (ns, n, c, l))
    if out["丁"]:
        print("")
        print("   ★丁 有跳过的（★不许分档 ✗ 要先查为什么跳✗★）✗ %d 个✗★" % len(out["丁"]))
        for ns, n, c, l, ti, s in out["丁"][:8]:
            print("      %-26s 跳过 %d" % (ns, s))
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--all", "-a"):
        survey()
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))

# ★★2026-10-18（★复核 P2-12g ✗ §79.279✗★）✗★★：★这里原来**有第二份** `survey`✗★
#   ★（★CLI 走第一份 ✗ `import cut_diff` 会拿到这份✗★）⇒ ★两个工具各说一套✗★ ✓
#   ★★已删 ✗ 而且**没有任何工具 import 它**（★grep 过 ✗ 一个都没有✓★）✗★ ✓
