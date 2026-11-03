#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixtures.py -- ★★测试件：清单 ＋ 快照 ＋ 复原 ＋ 复核✗★★（欠账 ⑦ 第 2 层 ✓ 2026-10-02 ✓）

WHY ✓（★方案文档第 2 层✗★）：★"分离"的第一目标不是"有个干净世界" ✗
而是★"**任何测试造成的改变 ✗ 都能被复述、被复原、被复核**"✗★ ✓
★三条实证逼出来的✗★：★`/fill` 把火把冲成圆石（对不上 ✓）／soak 放块撞进扫描窗口（假结论 ✓）／
持续性实验把假人跑死（**不可逆** ✓）★

口径 ✓（★先写死✗★）
  F-A ★清单✗★：`state/test_fixtures.json` 里每件记 `id` ✓ `box` ✓ `purse` ✓ `created_by` ✓
  F-B ★快照✗★：★只记**非空气**的格子✗★（★空气是默认 ✗ 记满会淹掉真信息 ✓★）
  F-C ★复原✗★：★只动**和快照不一致**的格子✗★（★最小改动 ✗ 不推平整个世界✓★）
  F-D ★★异动必须可见✗★★：★要"挖掉"的那一格 ✗ 如果**不在快照里**（★当时就是空气 ⇒ 有东西是**后来**来的✓★）
       ⇒ ★标 `foreign=true` ✗ 并**报出来** ✗ 不许静默铲掉别人的东西✗★
  F-E ★复核✗★：`verify()` 必须**只认世界真值**✗（★重新扫一遍 ✗ 与快照逐格比 ✓★）
  ★所有读数都从**注入的 `scan`** 来✗ ⇒ ★判据可离线跑 ✗ 不碰世界✓★
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "state" / "test_fixtures.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def key(x, y, z):
    return "%d,%d,%d" % (int(x), int(y), int(z))


def cells_of(box):
    """★把 `{x0,x1,y0,y1,z0,z1}` 铺成格子表✗★"""
    for x in range(box["x0"], box["x1"] + 1):
        for y in range(box["y0"], box["y1"] + 1):
            for z in range(box["z0"], box["z1"] + 1):
                yield (x, y, z)


def snapshot(scan, box):
    """★扫一遍 ✗ 记**全部**格子（★含空气✗★）★

    ★★为什么必须含空气✗★★（2026-10-02 被 `fixtures_test` 的 F3 抓出来 ✓）：
      ★第一版"只记非空气"看着省地方 ✗ ⇒ ★可"该挖哪一格"就**永远推不出来**✗★ ——
      ★因为"该是空气"这件事**没被记下来** ✗ 于是要挖的格子只能被算成"异动"✗★ ✓
      ⇒ ★口径✗★：★快照 ＝ **那一刻世界的样子**✗（★不是"我放了什么"✗ ✓）★
    """
    snap = {}
    for (x, y, z) in cells_of(box):
        snap[key(x, y, z)] = scan(x, y, z) or "air"
    return snap


def plan_restore(snap, scan, box):
    """★算出"要放什么／要挖什么"✗★ ⇒ `(ops, foreign)`

    ★★两条安全规则✗★★：① ★只动 box 里的格子✗★
      ② ★★"异动"必须**标出来**✗★★：★快照里那格是空气 ✗ 现在有东西 ⇒
         这一格的变化**不是夹具本身**（★是后来的✗★）⇒ ★op 上带 `foreign: true`✗✗
         让调用者**在计划里就看见** ✗ 而不是悄悄铲掉✓★
    """
    ops, foreign = [], []
    for (x, y, z) in cells_of(box):
        k = key(x, y, z)
        want = snap.get(k, "air")
        now = scan(x, y, z) or "air"
        if want == now:
            continue
        was_air = (k in snap and snap[k] == "air")
        if want == "air":
            op = {"op": "dig", "at": k, "was": now}
            if was_air:
                op["foreign"] = True
                foreign.append({"at": k, "now": now,
                                "why": "★快照里这格是空气 ✗ 现在有东西 ⇒ 是**后来的**✗★"})
            ops.append(op)
        else:
            ops.append({"op": "place", "at": k, "block": want, "was": now})
    return ops, foreign


def verify(snap, scan, box):
    """★复核✗★ ⇒ 不一致清单（★空 ⇒ 复原成功 ✓★）"""
    bad = []
    for (x, y, z) in cells_of(box):
        k = key(x, y, z)
        want = snap.get(k, "air")
        now = scan(x, y, z) or "air"
        if want != now:
            bad.append({"at": k, "want": want, "now": now})
    return bad


# ── 清单 ─────────────────────────────────────────────────────────────────────
def load_manifest(path: Path = MANIFEST):
    if not path.is_file():
        return {"fixtures": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError("★清单坏了 ✗ 不静默当成空✗★：%s" % e)


def add_fixture(fid, box, purpose, created_by, path: Path = MANIFEST):
    m = load_manifest(path)
    for f in m["fixtures"]:
        if f.get("id") == fid:
            raise RuntimeError("★清单里已经有 `%s`✗★（★要么改名 ✗ 要么先删✓★）" % fid)
    m["fixtures"].append({"id": fid, "box": box, "purpose": purpose, "created_by": created_by})
    path.parent.mkdir(parents=True, exist_ok=True)
    # ★★2026-10-03 记一次**我自己的误判**✗★★（★不是代码的错 ✗ 留在这里当路标✓★）：
    #   ★我在 PowerShell 里用 `Get-Content` 看这个清单 ✗ 看到 `purpose` 是 `鈽呮牎…` 乱码 ✗
    #   差点"修"这里 —— ★可是**这里本来就钉了** `encoding="utf-8"`✗★ ✓
    #   ★真因✗★：★`Get-Content` 按平台默认（cp936）去读一个 UTF-8 文件✗★ ✓
    #     （★用 Python 按 utf-8 读 ⇒ 中文**完全正确**✓★）
    #   ⇒ ★口径✗★：★看到乱码先查**读法** ✗ 别先改**写法**✗★ ✓
    path.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return m


def list_fixtures(path: Path = MANIFEST):
    return load_manifest(path)["fixtures"]


if __name__ == "__main__":
    print("★fixtures 自检✗★（★注入假 scan ✗ 不碰世界✓★）")
    world = {key(1, 1, 1): "minecraft:cobblestone", key(2, 1, 1): "minecraft:torch"}
    box = {"x0": 1, "x1": 3, "y0": 1, "y1": 1, "z0": 1, "z1": 1}

    def scan(x, y, z):
        return world.get(key(x, y, z), "air")

    s = snapshot(scan, box)
    print("  快照（★只记非空气✗★）：%s" % s)
    world[key(2, 1, 1)] = "air"
    world[key(3, 1, 1)] = "minecraft:dirt"          # ★后来有人放的✗★
    ops, foreign = plan_restore(s, scan, box)
    print("  复原计划：%s" % ops)
    print("  ★异动（不许静默铲）✗★：%s" % foreign)
