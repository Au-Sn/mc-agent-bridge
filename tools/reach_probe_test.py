#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reach_probe_test.py -- ★可达性探针的契约判据✗★（R1~R12 ✓ 全离线 ✓ 2026-10-05）

★第 0 步的契约（★`docs/方案-可达性探针.md`✓★）＋ 第 1 步的四步流水线✗★ ✓
★★判据**不碰游戏**✗★★：★世界读取走 `scan_fn` **注入**（★假扫描✗★）✗★ ✓
★★而"★没验过的能力不许换覆盖率★"落成 **R6**✗★★：
  ★只有**真命中**才许 `yes` ✗ 只有**分析过 frontier** 才许 `no` ✗ 其余一律 `unknown`✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import reach_probe as RP  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


AIR = "minecraft:air"
STONE = "minecraft:stone"
FENCE = "minecraft:oak_fence"          # ★`fence_15` ⇒ 1.5 不可跳✗★
LEAF = "minecraft:oak_leaves"


def flat(y=64, x0=0, x1=10, z=0, gap=None):
    """★一条平地走廊✗★（★`gap` 给的 x 范围**没有地板**✗★）

    ★★2026-10-05（§79.174✗★）✗★★：★这里要模拟的是"★**一次完整的读**★"✗★ ⇒
      ★**脚那层与头上那层**都要填 `AIR`✗★ ✓ ——
      ★因为原语化之后 ✗ `stand()` 要求"★本格与头上空★"✗ 而**没列出的格算 `missing`**
      ✗★ ★而 `missing` **不许**当空气（★`UNKNOWN` 一等公民 ✗ 用户借鉴②✓★）✗★ ✓
      ★（★真读**做不到**这种完整 ✗ 那个缺口在探针文档 **6.1**✓★）✗★ ✓
    """
    c = {}
    for x in range(x0 - 2, x1 + 3):
        for zz in range(z - 2, z + 3):
            c[(x, y, zz)] = AIR          # ★脚那层✗★
            c[(x, y + 1, zz)] = AIR      # ★头上那层✗★
            if gap and gap[0] <= x <= gap[1]:
                continue
            c[(x, y - 1, zz)] = STONE
    return c


def main(argv):
    print("== reach_probe_test：R1~R12 ==")

    # ---- R1~R3 形状（★契约✗★）
    _r = RP.reach_probe((0, 64, 0), (10, 64, 0), scan_fn=lambda b: flat())
    check("R1", set(_r) == {"reachable", "layers", "evidence", "why_not"},
          "★四个键都在✗★ ⇒ %s" % sorted(_r))
    check("R2", _r["reachable"] in RP.REACHABLE and "unknown" in RP.REACHABLE,
          "★三值 ✗ `unknown` 合法✗★ ⇒ %s" % _r["reachable"])
    check("R3", _r["why_not"] is None or _r["why_not"] in RP.WHY_NOT,
          "★`why_not` 在闭集内✗★ ⇒ %s" % _r["why_not"])

    # ---- R4 骨架期的硬闸：★没有**生产**模块 import 它✗★
    #   ★2026-10-13 修（★§79.223✗★）✗★：★这条的**主张**是"★没有**生产**模块 import 它★"✗★
    #     而实现原来只排除了 `reach_probe.py` 与 `reach_probe_test.py` 两个**名字**✗★ ⇒
    #     ★新加的**判据** `danger_test.py` 被当成了"生产模块"⇒ 误报✗★ ✓
    #   ★修的是**分类** ✗ **规则不动**✗★：★判据（`*_test.py`）**本来就该** import 它✗
    #     （★那正是探针被验的方式✓★）⇒ 排除**一整类**而不是两个名字✗★ ✓
    _prod = []
    for f in sorted((ROOT / "tools").glob("*.py")):
        if f.name == "reach_probe.py" or f.name.endswith("_test.py"):
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(import|from)\s+reach_probe\b", t, re.M):
            _prod.append(f.name)
    # ★★2026-10-13（★§79.252✗★）✗★★：★`e1_window.py` 是**实机窗口跑单器**✗★ ——
    #   ★它**故意**要在窗口里跑探针 ✗ 所以它会 import `reach_probe`✗★ ⇒
    #   ★这是**声明的例外**（★不是放过 ✗ 是写清理由 ＋ 替换触发✓★）✗★：
    #   ★替换触发✗★：★阶段 4 结束、`reach_probe` 转正之后 ⇒ 删掉这条例外✗★ ✓
    #   ★（★补丁第一次插错缩进 ✗ 把外层块提前闭合了 ⇒ `IndentationError` ✗ 已按块内缩进重排✓★）
    _ALLOW_PROD = ("e1_window.py",)
    _prod = [x for x in _prod if x not in _ALLOW_PROD]
    check("R4", not _prod,
          "★★**没有任何生产模块** import `reach_probe`✗★★（★生产＝不含 `*_test.py` 判据✗★）（★违反者：%s✗★）"
          % (_prod or "（没有 ✓）"))

    # ---- R5 用例库
    _d = json.loads((ROOT / "state" / "probe_cases.json").read_text(encoding="utf-8"))
    _cs = _d.get("cases") or []
    _bad = [c.get("id") for c in _cs
            if not all(k in c for k in ("id", "name", "kind", "truth_source", "status"))]
    # ★★2026-10-05 升（§79.161✗★）✗★★：★从"★正好 7 条★"改成
    #   ★"★≥7 ✗ 四要素齐 ✗ 且**有真值的必须带出处**★"✗★ ——
    #   ★因为"★真值从哪来★"比"★有几条★"要紧得多（★没出处的真值就是编的✓★）✗★ ✓
    _no_prov = [c.get("id") for c in _cs
                if (c.get("truth") or c.get("expect")) and not c.get("provenance")]
    check("R5", (len(_cs) >= 7) and (not _bad) and (not _no_prov) and (_cs[0].get("id") == 1),
          "★用例库 ≥7 条 ✗ 四要素齐 ✗ **有真值必有出处** ✗ 一号是 ㉘✗★"
          " ⇒ %d 条 ｜ 坏的 %s ｜ 真值没出处 %s"
          % (len(_cs), _bad or "无", _no_prov or "无"))

    # ---- R6 ★★没验过就不许下结论✗★★（★读不到 ⇒ `unknown`✗★）
    _r6 = RP.reach_probe((0, 64, 0), (10, 64, 0),
                         scan_fn=lambda b: (_ for _ in ()).throw(RuntimeError("no scan")))
    check("R6", _r6["reachable"] == "unknown" and _r6["why_not"] == "unknown_region",
          "★★读不到世界 ⇒ **只许** `unknown`＋`unknown_region`✗★★ ⇒ %s／%s"
          % (_r6["reachable"], _r6["why_not"]))

    # ---- R7 平地 → 平地：★基线 ⇒ yes ／ 0 层✗★（用例 2）
    _r7 = RP.reach_probe((0, 64, 0), (8, 64, 0), scan_fn=lambda b: flat())
    check("R7", _r7["reachable"] == "yes",
          "★用例 2（★平地→平地 ✗ 基线✓★）⇒ yes ｜ layers=%s" % _r7["layers"])

    # ---- R8 1.5 墙后 ⇒ no ／ `wall_too_high`（用例 6）
    def _wall(b):
        c = flat()
        for zz in range(-2, 3):
            c[(5, 64, zz)] = FENCE
            c[(5, 65, zz)] = FENCE
        return c
    _r8 = RP.reach_probe((0, 64, 0), (10, 64, 0), scan_fn=_wall)
    check("R8", (_r8["reachable"] == "no") and (_r8["why_not"] == "wall_too_high"),
          "★用例 6（★1.5 墙后✗★）⇒ %s／%s" % (_r8["reachable"], _r8["why_not"]))

    # ---- R9a ★**连续的 2 格高墙**✗★ ⇒ no（★§79.159 改：原来那个用例是"★连续小台阶★"✗
    #          ★而**真人爬得上去** ⇒ `yes` 本来就是对 ✗ 是**用例错**了✗★）
    def _wall2(b):
        c = flat()
        for zz in range(-2, 3):
            c[(5, 64, zz)] = STONE
            c[(5, 65, zz)] = STONE         # ★两面摞起来 ⇒ 净高 2 ✗ 一步上不去✗★
        return c
    _r9a = RP.reach_probe((0, 64, 0), (9, 64, 0), scan_fn=_wall2)
    check("R9a", _r9a["reachable"] == "no",
          "★连续 2 格高墙 ⇒ no✗★ ⇒ %s／%s" % (_r9a["reachable"], _r9a["why_not"]))

    # ---- R9b ★**连续小台阶**✗★ ⇒ **yes**（★每步只上 1 层 ✗ 走手会上✗★）
    def _stairs(b):
        # ★★2026-10-05 修✗★★：★上一版把台阶放在了**地板层**（★`(x,63)`✗★）⇒
        #   ★`x=4` 那格**没有石头** ✗ 而**目标 `(9,68)` 落在实心块里** ✗★ ⇒
        #   ★假人当然到不了 ✗ 判 `no`／`sealed` 是**对的** ✗ 是**用例错**✗★ ✓
        #   ★现在✗★：★从 x=4 起 ✗ 每格把**脚下垫高 1 层**（★`(x, 64+i-1)` 放石✗★）✗
        #     ★并保证**上面是空气** ✗ 目标落在**最后一格的顶上**（★空气里✓★）✗★ ✓
        c = flat()
        for i, x in enumerate(range(4, 10)):
            for zz in range(-2, 3):
                for k in range(i + 1):
                    c[(x, 63 + k, zz)] = STONE          # ★地板层往上垫✗★
                for k in range(i + 1, i + 5):
                    c[(x, 63 + k, zz)] = AIR            # ★★上面**填空气**✗★★（§79.174：
                    #   ★原来只是 `pop` 掉 ✗ 而"★没列出★"算 `missing` ✗ 前置"★头上有空★"就失败✓★）
        return c
    _r9b = RP.reach_probe((0, 64, 0), (9, 69, 0), scan_fn=_stairs)
    check("R9b", (_r9b["reachable"] == "yes") and (_r9b["layers"] == 5),
          "★连续小台阶（★每步 1 层✗★）⇒ %s ｜ ★层数=%s✗★（★契约要的「跨几层」✓★）"
          % (_r9b["reachable"], _r9b["layers"]))

    # ---- R10 断档 ⇒ no ／ `gap`
    _r10 = RP.reach_probe((0, 64, 0), (9, 64, 0), scan_fn=lambda b: flat(gap=(4, 5)))
    check("R10", (_r10["reachable"] == "no") and (_r10["why_not"] in ("gap", "sealed")),
          "★断档（★x=4..5 没有地板✗★）⇒ %s／%s" % (_r10["reachable"], _r10["why_not"]))

    # ---- R11 ★树冠不是落脚点✗★（★政策层 ✗ 用真实物种名 ✗ 走 `blockkb`✗★）
    def _canopy(b):
        # ★★2026-10-05 修✗★★：★原来树叶只铺 `x=3..6` ✗ 而平地一直铺到 `x=12`✗★
        #   ⇒ ★假人**从旁边绕过去了** ⇒ 判据回 `yes` 是**对的** ✗ 是**用例不对**✗★ ✓
        #   ★改成：树叶**横跨整条走廊**（★z=-2..2 全铺 ✗ 而且把平地也铺满那一段✗★）
        c = flat()
        for x in range(3, 7):
            for zz in range(-2, 3):
                c[(x, 63, zz)] = STONE        # ★底下是石头✗★
                c[(x, 64, zz)] = LEAF         # ★上面一层全是树叶✗★
                c[(x, 65, zz)] = AIR
        return c
    _r11 = RP.reach_probe((0, 64, 0), (9, 65, 0), scan_fn=_canopy)
    check("R11", _r11["reachable"] != "yes",
          "★★树叶**不算落脚点**✗★★（★政策层 ✗ `is_landing`✓★）⇒ %s／%s"
          % (_r11["reachable"], _r11["why_not"]))

    # ---- R12 成本红线：★盒子超上限 ⇒ `outside_box`✗★
    _r12 = RP.reach_probe((0, 64, 0), (200, 64, 0), scan_fn=lambda b: {})
    check("R12", (_r12["reachable"] == "unknown") and (_r12["why_not"] == "outside_box"),
          "★盒子超 **64×32×64** ⇒ outside_box✗★ ⇒ %s／%s" % (_r12["reachable"], _r12["why_not"]))

    
    # ---- R13 用例 4 ★**洞穴里**✗★（★头顶有盖 ✗ 但**水平方向通**⇒ 应当 yes✗★）
    #   ★这一条考的是✗★：★"★有天花板★" **不等于** "★走不到★"✗★ ✓
    def _cave(b):
        c = flat()
        for x in range(-2, 13):
            for zz in range(-2, 3):
                c[(x, 66, zz)] = STONE          # ★盖子在头顶 2 格 ✗ 人站得下✗★
        return c
    _r13 = RP.reach_probe((0, 64, 0), (9, 64, 0), scan_fn=_cave)
    check("R13", _r13["reachable"] == "yes",
          "★用例 4 洞穴里（★有盖 ✗ 水平通✗★）⇒ %s ｜ layers=%s"
          % (_r13["reachable"], _r13["layers"]))

    # ---- R14 用例 5 ★**屋顶上**✗★（★高 3 层 ✗ 没有台阶 ⇒ 上不去✗★）
    def _roof(b):
        c = flat()
        for x in range(-2, 13):
            for zz in range(-2, 3):
                for k in range(3):
                    c[(x, 64 + k, zz)] = STONE  # ★一整块抬 3 格 ✗ 一面 3 格高的墙✗★
        return c
    _r14 = RP.reach_probe((0, 64, 0), (9, 67, 0), scan_fn=_roof)
    check("R14", _r14["reachable"] == "no",
          "★用例 5 屋顶上（★高 3 层 ✗ 无台阶✗★）⇒ %s ／ %s"
          % (_r14["reachable"], _r14["why_not"]))

    # ---- R15a／R15b 用例 7 ★**竖直井**✗★（★下 3 层内 ⇒ yes ✗ 下 6 层 ⇒ no✗★）
    def _shaft(depth):
        def f(b):
            c = flat()
            for x in range(3, 7):
                for zz in range(-2, 3):
                    for k in range(depth):
                        c[(x, 63 - k, zz)] = AIR      # ★挖一口井✗★
                    c[(x, 63 - depth, zz)] = STONE    # ★井底✗★
            return c
        return f
    _r15a = RP.reach_probe((0, 64, 0), (5, 61, 0), scan_fn=_shaft(3))
    _r15b = RP.reach_probe((0, 64, 0), (5, 58, 0), scan_fn=_shaft(6))
    # ★★2026-10-05 收紧（§79.182✗★）✗★★：★原来这两条写的是 `in ("yes","unknown")`
    #   ✗★ ⇒ ★★它们**怎么都不可能红** ✗ 于是"★层差对不对★"根本没查✗★★ ✓
    #   ★（★`layers` 按甲 ＝ **层差累计** ✗ 下 3 层 ⇒ **−3**✓★）✗★ ✓
    check("R15a", (_r15a["reachable"] == "yes") and (_r15a["layers"] == -3),
          "★竖直井（★下 3 层 ✗ 在 down_max=3 内✗★）⇒ ★必须 yes 且 layers = **−3**✗★"
          " ⇒ %s ｜ layers=%s" % (_r15a["reachable"], _r15a["layers"]))
    check("R15b", (_r15b["reachable"] == "no") and (_r15b["why_not"] in ("gap", "sealed")),
          "★竖直井（★下 6 层 ✗ 超 down_max✗★）⇒ ★必须 no ✗ 且理由实质✗★"
          " ⇒ %s ／ %s" % (_r15b["reachable"], _r15b["why_not"]))


    # ---- ★★R16a~R16c：真世界的形状（★`dshscan` 只列非空气✗★）＋「甲」的高度图★★
    #   ★这三条**照真世界造** ✗ 不填空气 ✗★ ⇒ ★它们才碰得到「甲」那条路径✗★ ✓
    def _bare(box, y=64, x0=0, x1=10, z=0):
        """★只列**非空气**的扫描（★真世界就是这样✗★）✗★

        ★★2026-10-05 修签名✗★★：★原来写的是 `_bare(y=64, …)`✗★ ⇒
          ★而它被当成 `scan_fn(box)` 调用✗★ ⇒ ★**元组落进了 `y`** ✗ `y-1` 抛异常✗★ ⇒
          ★★而探针**兜住了**扫描的异常 ⇒ 报 `unknown_region`**✗★★ ⇒
          ★判据看到的是"★读不到★" ✗ 不是"★甲没用上★"✗★ ✓（★判据的锅★）
        """
        c = {}
        for x in range(x0 - 2, x1 + 3):
            for zz in range(z - 2, z + 3):
                c[(x, y - 1, zz)] = STONE          # ★只有地板 ✗ 空气**一个都不列**✗★
        return c

    def _cols_flat(x, z):
        return 63                                     # ★列顶 63 ⇒ 64 与 65 都在它之上✗★

    _r16a = RP.reach_probe((0, 64, 0), (8, 64, 0), scan_fn=_bare, col_fn=_cols_flat)
    check("R16a", _r16a["reachable"] == "yes",
          "★扫描不列空气 ＋ 列顶说在它之上 ⇒ 应当走通✗★ ⇒ %s ｜ layers=%s"
          % (_r16a["reachable"], _r16a["layers"]))

    def _cols_void(x, z):
        return None                                   # ★空列 ⇒ 虚空✗★

    _r16b = RP.reach_probe((0, 64, 0), (8, 64, 0), scan_fn=_bare, col_fn=_cols_void)
    check("R16b", _r16b["reachable"] == "no",
          "★★空列（虚空）⇒ **不许**走通✗★★ ⇒ %s ／ %s"
          % (_r16b["reachable"], _r16b["why_not"]))

    def _cols_boom(x, z):
        raise RuntimeError("read failed")

    _r16c = RP.reach_probe((0, 64, 0), (8, 64, 0), scan_fn=_bare, col_fn=_cols_boom)
    check("R16c", _r16c["reachable"] == "no",
          "★★列顶读不到 ⇒ **不许**当空气✗★★ ⇒ %s ／ %s"
          % (_r16c["reachable"], _r16c["why_not"]))

    print("=> reach_probe %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
    return 0 if ok[0] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
