#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pathplan.py —— ★在"看得见的地图"上规划路线（中间层）★ ✓

## 为什么要有它 ✗（实测 2026-09-23 ✓ 都是真事 ✓）
  · `walk_to` 常报 **unreachable** ✗ —— 其中一部分是**目标格本身站不住** ✓
    （小数坐标取整 ⇒ 落到半砖/庄稼/箱子那一格 ✗ ⇒ 到达判定永远不成立 ✗）
  · 长距离只发**一条**指令 ⇒ 中途被挡就只能整体失败 ✗（回执里 `blocked` ✓ 而人已经走了一半 ✗）
  · 走 5 格却 `step_downs=19` ✓（绕路 ✓）⇒ 因为它只在局部看 ✓ 没有全局图 ✓
⇒ 中间层的办法 ✓：**用地图做全局规划 ⇒ 拆成几段 ⇒ 一段一段走 ⇒ 每段验世界真值 ⇒ 偏了就重规划** ✓

## 规矩（写死在代码里 ✓ 不靠"记得"✗）
  · **未知 = 不能走** ✓（柱子里一个已知方块都没有 ⇒ 那多半是虚空/空气 ⇒ 不是地板 ✓）
  · **不切角** ✗：斜着走要求**两侧正交格**都能站 ✓（不然会贴着边缘掉下去 ✓）
  · **落差**：往上最多 1 格 ✓（跳一下 ✓）往下最多 3 格 ✓（摔得动 ✓）；再多算断路 ✓
  · **目标站不住 ⇒ 就近找落脚点** ✓（半径 2 内最近的能站格 ✓）—— 这一条专治上面那个假 unreachable ✓
  · **不假装有路** ✗：规划不出就返回 `None` ＋ **具体原因** ✓（目标未知/被围住/超出图 ✓）
"""
from __future__ import annotations

import heapq
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
MAX_UP = 1
MAX_DOWN = 3
# ★"贴边"那一笔代价★ ✗（2026-09-29 第 25 轮 ✓）：**必须比"绕一格"小**（1.0 ✓）
#   这样"有平路就绕开边"✓ 而"只有边路"时仍然照走 ✓（不会把路判死 ✗）
EDGE_PENALTY = 0.8


# ★★"自动上得去"的方块**白名单**★★ ✗（第 34 轮 ✓ 实测：写宽了会**假可达** ✗）
#   依据 ✓：Minecraft 自动上台阶上限 **0.6 格** ⇒ 只有**顶面 ≤0.6** 的才算"不用跳" ✓
#     ✅ 算：`*_slab`（下半砖 0.5 ✓）／`carpet` 地毯 ✓／`snow` 雪层 ✓／`pressure_plate` ✓／`_button` ✓
#     ❌ 不算（★它们 `shape()` **也是** `slab` ✗ 可**顶面 >0.6** ✗ 得跳 ✗）：
#          `farmland`／`dirt_path`（0.9375 ✗）／`stairs` 楼梯（高的那侧 1.0 ✗ 而且朝向不明 ✗）／
#          `composter`／`cauldron`（≈1.0 ✗）／`soul_sand` ✓ 等
#   ★为什么必须写窄★ ✗：写宽了 ⇒ 规划**以为**能上去 ✓ 而模组上不去 ✗ ⇒ 又回到"假可达"✗
#     （★实测教训★ ✓：第 34 轮第一版拿 `shape=='slab'` 当判据 ✗ ⇒ 电池里 **4 项**当场红 ✗）
AUTO_STEP_SUB = ("_slab", "carpet", "snow", "pressure_plate", "_button", "flower_pot")
AUTO_STEP_NOT = ("farmland", "dirt_path", "stairs", "composter", "cauldron", "soul_sand",
                 "dirt path", "_path", "step")


def is_auto_step(block: str) -> bool:
    """★这个方块是不是"抬腿就能上"的（顶面 ≤0.6 ✓）★ ✗（第 34 轮 ✓ 白名单 ✓ 一处口径 ✓）"""
    if BY_HEIGHT:
        # ★★A3✗★★：★只问碰撞顶高 ✗ ≤0.6 才算"抬腿就能上"✗★ ✓
        #   ★拿不到高度 ⇒ False（★保守 ✗ 绝不静默回落名字✓★）✗★ ✓
        h = height_of(block)
        return h is not None and h <= STEP_MAX
    b = (block or "").lower()
    if not b:
        return False
    for k in AUTO_STEP_NOT:
        if k in b:
            return False
    for k in AUTO_STEP_SUB:
        if k in b:
            return True
    return False


def is_climbable(block: str) -> bool:
    """★"跳一下上得去吗"★ ✗（第 34 轮修正 ✓ 用户指出 ✓ 源码为准 ✓）

    ★★我上一轮的结论**错了**★★ ✗：我说"**模组不会跳**"✗ ——
      真因 ✓：我当时**只拿墙（`mcwfences:*_wall`）当试验对象** ✗
        而**墙高 1.5 格** ✗ ⇒ 跳也上不去（跳跃上限 ≈ **1.25** ✓ **真人也不行** ✓）
        ⇒ 我把"**墙跳不上去**"错推成了"**模组不会跳**" ✗（★过度概括 ✗★）
    源码证据 ✓（`DshBridgeMod.java` 3687/3725 行 ✓）：
      `boolean wantJump = blocked && headroom && p.onGround() && detourTicks == 0;`
      `p.setDeltaMovement(..., 0.42, ...)` ⇒ 起跳初速 0.42 ⇒ **能上约 1.25 格** ✓
      ★同处 v2.7 的注释还写着★："墙高 1.5 格 ⇒ **跳不过去** ✗（真人也不行 ✓）⇒ 真人会**绕**"
      ⇒ 模组照做 ✓：跳不上去时走**绕障**（`detour` ✓）✓ —— ★它一直在按真人的方式做事 ✓★
    ⇒ 口径 ✓：**按"这一级要抬多高"判** ✗：
      · 整方块／半砖／机器（≈1.0 及以下 ✓）⇒ **跳得上** ✓
      · 栅栏／墙（≈1.5 ✗）／树冠（高度不明 ✗）⇒ **不指望** ✗（老实绕 ✓）
    """
    if BY_HEIGHT:
        # ★★A3✗★★：★只问碰撞顶高 ✗ ≤1.25 才算"跳得上去"✗★ ✓
        #   ★（★栅栏／墙 1.5 ⇒ False ⇒ 老实绕 ✗ 与源码注释一致✓★）✗★ ✓
        h = height_of(block)
        return h is not None and h <= JUMP_MAX
    try:
        import mapread as _MR
        sh = _MR.shape(block)
        return sh in ("full", "slab", "machine")
    except Exception:
        return False


class Planner:
    """在 `mapread.Map` 上做 A* ✓（地图是快照 ✓ 规划完立刻就走 ⇒ 窗口很短 ✓）"""

    def __init__(self, m, level: int | None = None, allow_unknown: bool = False,
                 blocked: set | None = None, avoid_edge: bool = True,
                 same_level_only: bool = False, max_up: int = MAX_UP,
                 auto_step_on: bool = False):
        self.m = m
        # ★★`y()` 的记忆化（第 37 轮 ✓ ⇒ P144 ✓）★★：
        #   实测 ✓ `region()` 在 641 格上要 **2.38 秒** ✗ —— 因为同一格被问 ~24 次 ✗
        #   ★缓存挂在 **Planner** 上✗ 不挂在 Map 上★：
        #     Planner 每次调用新建 ✓ ⇒ 活不过一次规划 ✓；地图在一次规划期间不变 ✓
        #     ⇒ ★读不到过期值✗★；而挂 Map 就得**逐个改动点失效缓存**✗ ⇒ 漏一个就静默用旧值 ✗
        self._rf: dict = {}
        self.level = level if level is not None else (m.box[1] + 8)
        self.allow_unknown = allow_unknown
        # ★★半步（半砖/楼梯）开关：**默认关**★★ ✗（第 34 轮 ✓ 见 `max_rise` 的长注释 ✓）
        self.auto_step_on = bool(auto_step_on)
        # ★★`max_up`：**执行者真能抬几级**★★ ✗（第 33 轮 ✓ 用实测换来的 ✓）
        #   实测 ✓（第 32 轮 ✓ 两次真走 ＋ 独立读 ✓）：`dshwalk` 去"抬一级"的格子 ⇒
        #     停在 **0.8~1.7 格**外 ✗ ⇒ ★**它爬不上去**★ ✗（而它自己还把这当成"到了"✗）
        #   ⇒ 口径 ✗：**"几何上能站" ≠ "模组走得到"** ✗ ——
        #     地图/判据该用 `MAX_UP=1`（人真能站上去 ✓）✓
        #     ★而**要执行的那条路**必须按模组的真实能力算★ ✗（`max_up=0` ✓）
        #   为什么这件事很要紧 ✗：不按能力算 ⇒ 规划交出一条"最后一段要爬"的路 ✗
        #     ⇒ 规划说"通"✓ 模组停在旁边 ✗ ⇒ ★正是用户那句"走完还差 1 格"★ ✗
        #   等模组 v2.17 会跳一级 ⇒ 把这个数改成 1 即可 ✓（一处开关 ✓）
        self.max_up = int(max_up)
        # ★★`same_level_only`★ ✗（第 31 轮 ✓）：★"**我的平台**／**我的边**"是**同层**概念★ ✗
        #   为什么要单独开这个口径 ✗：`ok()` 修好之后 ✓ 它按 `MAX_UP/MAX_DOWN` 允许抬一级/降三级 ✓
        #     ⇒ 那对**规划**是对的 ✓（人真能上台阶 ✓）
        #     可"**我脚下这块平台有多大、边在哪**"问的**不是**这个 ✗ ——
        #       它问的是"**我现在这一层**上连着多大一片"✓（踩空是**同层**的事 ✓）
        #     ⇒ 混在一起 ⇒ `platform` 会把**墙头**（`+1` 层 ✓）也算进我的平台 ✗
        #       ⇒ 实测撞到 ✓：`platform_test` 的 P1 拿**同层**去独立探那些"边格"✗
        #          ⇒ 世界说"那格站不住"✗ ⇒ **判据红** ✗（可工具其实说的是**另一层** ✓）
        #   ⇒ 口径 ✓：**两个问题，两个开关，都写在名字上** ✗（不许再有"碰巧合在一起"的口径 ✗）
        self.same_level_only = bool(same_level_only)
        # ★★避边：宁可绕一点，也别**贴着边磨**★★ ✗（2026-09-29 第 25 轮 ✓）
        #   为什么要它 ✗：2026-09-23 那次掉虚空 ✓ 不是"目标选在边上"✗（那条早就修了 ✓）
        #     而是**路本身沿着边磨**✗ —— 空岛的边就是虚空边 ✓ 磨着磨着就下去了 ✓
        #   怎么做 ✓：给"**不是内陆格**"的位置加一笔**有限**代价（`EDGE_PENALTY` ✓）
        #     · 有平路 ⇒ 自然走中间 ✓（Q1 ✓）
        #     · **只有边路可走** ⇒ 照走 ✓（代价有限 ✓ ⇒ **绝不会**因为避边就报"不通" ✗ Q2 ✓）
        self.avoid_edge = bool(avoid_edge)
        # ★"已知挡路"的格子★ ✗（2026-09-23 ✓ 用户点的方向 ✓）
        #   来源是**实地探到的障碍**（独立读出来的 ✓ 不是按名字猜的 ✗）
        #   用途 ✓：探路探到真障碍 ⇒ 记进来 ⇒ **重规划时绕开** ✓（这才是"识别道中障碍物"✓）
        # ★★第 31 轮：障碍记忆**带层**★★ ✗（实测抓到的漏子 ✓ 详见 `mc_mcp.BLOCKED_LV` ✓）
        #   两种送法都收 ✓：
        #     · **集合** `{(x,z)}` ⇒ 老口径 ✓ "这一柱**任何层**都别走"✗
        #     · **字典** `{(x,z): 探到它的那一层}` ⇒ 新口径 ✓ "**那一层**走不过去"✗
        #       别的层（比如**墙头**那层 ✓）该走还得走 ✓ —— 否则"抬一级"的目标会被自己锁死 ✗
        if isinstance(blocked, dict):
            self.blocked = set(blocked.keys())
            self.blocked_lv = {k: int(v) for k, v in blocked.items() if v is not None}
        else:
            self.blocked = set(blocked or ())
            self.blocked_lv = {}
        self.nodes = 0

    def auto_step(self, x, z, fy) -> bool:
        """★这一柱的地板是"**抬腿就能上**"的吗★ ✗（第 34 轮 ✓ 按**物理**算 ✓ 不是放宽 ✗）

        为什么必须有它 ✗：Minecraft 的**自动上台阶**上限是 **0.6 格** ✓
          ⇒ **半砖**（顶面 +0.5 ✓）**不用跳**就能走上去 ✓✓
          ⇒ 而**整方块**（+1.0 ✗）必须跳 ✗ —— 模组**不会跳**（第 32 轮实测 ✓）
        口径 ✓：本项目把"地板在 `level`"记成 `feet = level + 1` ✗
          ⇒ 半砖那种其实只抬 **0.5** ✓ 却被当成"抬一级要跳"✗ ⇒ **规划把它拒了** ✗
          ⇒ **地板形状是 `slab` ⇒ 这一级是自动的** ✓（与 `cell_kind` 的 `+` 矮障同一条 ✓ P106 ✓）
        ★这不是放宽 ✗ 是**把物理写进模型** ✓★（半砖铺的坡道真能走 ✓ 整方块真不能走 ✗）
        """
        try:
            nm = (self.m.cols.get((int(x), int(z))) or {}).get(int(fy))
            return is_auto_step(nm)          # ★白名单 ✓（顶面 ≤0.6 才算 ✓ 不是"shape==slab"✗）
        except Exception:
            return False

    def max_rise(self, x, z, fy) -> int:
        """★这一柱允许抬几级★ ✗ = `max_up` ✓，**再按"这一级抬多高"修正** ✓

        ★★第 34 轮修正（用户指出 ✓ 源码为准 ✓ 见 `is_climbable` 的长注释 ✓）★★：
          · 地板是**整方块/机器**（抬 **1.0** ✓）⇒ 跳得上 ✓（模组真的会跳 ✓）
          · 地板是**栅栏/墙**（抬 **1.5** ✗）⇒ ★跳不上，真人也不行★ ✗ ⇒ 不算 ✓
          · 地板是**半砖**（抬 **0.5** ✓）⇒ **自动上** ✓（`auto_step_on` 打开时才算 ✓）
        """
        up = int(self.max_up)
        if up >= 1:
            nm = (self.m.cols.get((int(x), int(z))) or {}).get(int(fy))
            if nm is None or not is_climbable(nm):
                up = 0                      # ★1.5 的墙 / 高度不明的方块 ⇒ 不指望跳 ✓
        if getattr(self, "auto_step_on", False) and up < 1 and self.auto_step(x, z, fy):
            up = 1                          # 半步 ⇒ 自动上 ✓（没验过 ⇒ 默认关 ✓ 见 `auto_step_on` ✓）
        return up

    def blocked_here(self, x, z, feet) -> bool:
        """★这一格在**脚占 `feet` 那一层**上被记为障碍了吗★ ✗（第 31 轮 ✓ 一处口径 ✓）"""
        k = (int(x), int(z))
        if k not in self.blocked:
            return False
        lv = self.blocked_lv.get(k)
        if lv is None:
            return True                  # 没记层（老数据 ✓）⇒ 保守：照旧挡 ✓
        return int(feet) == int(lv)      # 只有**同层**才算被挡 ✓

    def edge_extra(self, x, z) -> float:
        """★"贴边"要加多少代价★ ✓（纯函数式 ✓ 好离线单测 ✗）

        `interior()` = 四邻都能站 ✓ ⇒ 它的**补集**就是"边上一圈"✓
        ★有限值★ ✗：0.8 比"绕一格"（1.0 + 抬腿 0.6 ✓）小 ✓
          ⇒ 绕得动就绕 ✓；绕不动（只有一条边路 ✓）也照走 ✓
        """
        if not self.avoid_edge:
            return 0.0
        return EDGE_PENALTY if not self.interior(int(x), int(z)) else 0.0

    # ── 地图问答 ──────────────────────────────────────────────────────────
    def y(self, x, z):
        """★这一柱**地板**在哪一层★ ✗（第 30／31 轮 ✓ 口径统一到 `Map.reachable_floor` ✓）

        ⚠ 第 30 轮改过一次 ✗（按名字算不出时问模组那条结论 ✓）；
          第 31 轮**再改一次** ✗（实测 ✓）：原来固定按 `below = self.level + 1` 问 ✗
          ⇒ 只会回"**我这一层**脚下那块"✗ ⇒ 抬一级/降下去的地板**根本问不出来** ✗
            ⇒ 那些格子 `y()` 回 `None` ⇒ `ok()` False ⇒ **规划说"不通"** ✗（假 unreachable ✓）
          ⇒ 现在交给 `reachable_floor`（它按 `MAX_UP/MAX_DOWN` 的窗口找 ✓ **一处口径** ✓）
        """
        ck = (int(x), int(z))
        if ck in self._rf:
            return self._rf[ck]
        rf = getattr(self.m, "reachable_floor", None)
        if self.same_level_only:
            # ★"我的平台"/"我的边"要的是**同层**那块地板 ✗（第 31 轮 ✓ 见 `__init__` 的注释 ✓）
            mf = getattr(self.m, "mod_floor_y", None)
            if mf is not None:
                self._rf[ck] = mf(x, z, below=self.level + 1)
                return self._rf[ck]
            # ★C3（§79.230）：这里要的是**落脚面**（物理＋政策『树冠不落』）✗★
            #   ⇒ 把意图写明 ✗ 别再「悄悄用默认值」✗★（`floor_only=True` 就是 `is_landing`）✗★
            s2 = self.m.surface(x, z, below=self.level + 1, floor_only=True)
            self._rf[ck] = (s2[0] if s2 else None)
            return self._rf[ck]
        if rf is not None:
            self._rf[ck] = rf(x, z, self.level, up=self.max_rise(x, z, self.level - 1),
                              down=MAX_DOWN, allow_auto_step=self.auto_step_on)
            return self._rf[ck]
        # ★C3（§79.230）：这里要的是**落脚面**（物理＋政策『树冠不落』）✗★
        #   ⇒ 把意图写明 ✗ 别再「悄悄用默认值」✗★（`floor_only=True` 就是 `is_landing`）✗★
        s = self.m.surface(x, z, below=self.level + 1, floor_only=True)
        self._rf[ck] = (s[0] if s else None)
        return self._rf[ck]

    def ok(self, x, z) -> bool:
        """★"走在 `self.level` 这一层的人，能站到这一格吗"★ ✗

        ★2026-09-28 第 19 轮收紧了**高度**★ ✗（**实测被假干净抓到** ✓）：
          现象 ✗：地图里有"**地板在脚下 6 格**"的柱子（验真之后地图存的都是**真高度** ✓）
            ⇒ 老版 `ok()` **只看"下面有没有地板"**✗ ⇒ 判"能站" ✓
            ⇒ 可人**根本下不去** ✗（`MAX_DOWN=3` ✓）⇒ 连通区/落脚点/我的判据全被它骗 ✗
            ⇒ 表现就是判据里的 **false clean**（5/6 ✗）
          ⇒ 现在要求 ✓：**地板落在 `level-3 .. level+1` 之间** ✓
            （= 和 A* 扩张时的落差规则**同一口径** ✓：往下最多 3 ✓ 往上最多 1 ✓）
          ⚠ 这是**安全方向**的严格 ✗：宁可少算几格能走的 ✓ 不许把下不去的当能走 ✗
        """
        fy = self.y(x, z)                     # ★这是**地板**那一格 ✓
        if fy is None:
            return False
        feet = fy + 1                         # ★人站上去，**脚**占的是地板上面那一格★ ✗
        if self.same_level_only and feet != self.level:
            return False                      # ★同层口径：抬一级/降下去都**不算我的平台** ✗（第 31 轮 ✓）
        # ★抬的那一级按 `max_rise` 算 ✓（半砖地板 ⇒ 多给一级"自动上" ✓ 第 34 轮 ✓）
        if not (self.level - MAX_DOWN <= feet <= self.level + self.max_rise(x, z, fy)):
            return False                      # ★落差太大 ⇒ 过不去 ✗（见上面的注释 ✓）
        # ★按**我真正会站上去的那一层**判"这格是不是被记为障碍"★ ✗（第 31 轮 ✓）
        #   ⚠ 顺序很要紧 ✗：先算 `feet` ✓ 再判障碍 ✓ ——
        #     反过来（按 `self.level` 判 ✗）会把"**抬一级的墙头**"整柱否掉 ✗
        #     （探路是在**假人那一层**探的 ✓ 记的也是那一层 ✓ ⇒ 不该管到上面那层 ✓）
        if self.blocked_here(x, z, feet):
            return False                      # ★实地探到障碍的格子 ⇒ 不许走★ ✗
        # ★★问的必须是"**我真正会站上去的那一层**"★★ ✗（第 31 轮 ✓ 实测抓到的真 bug ✓）
        #   原来写的是 `below=self.level + 1` ✗ ⇒ 那是在问"**我这一层**这一格能不能站" ✗
        #   ⇒ 抬一级（地板在 `level` ✓ 台阶/墙头就在我这一层 ✓）与降下去（我这一层是空气 ✗）
        #     的格子**一律被否** ✗ ⇒ **要上下台阶的路全报"不通"** ✗（假 unreachable ✓）
        #   ⇒ 现在按 `feet` 问 ✓ —— 与我实际的落脚处**同一件事** ✓（P106 ✓）
        return self.m.standable(x, z, below=feet + 1)

    def interior(self, x, z) -> bool:
        """★是不是"内陆"格★ ✓ —— 自己和**上下左右四格**都能站 ✓

        ⚠ 为什么要它 ✗（★2026-09-23 血的教训★ ✓）：目标选在平台边上 ✓
          旧的 `walk_to` 走过去时一脚踩空 ⇒ **假人掉进虚空** ✓
          丢掉：钻石 x2 ✓ 钻石斧 ✓ 漏斗 ✓ 煤 x8 ✓ 铁锭 ✓ 锤子 ✓ 麦子/种子 ✓
          ⇒ 纪律：**在空岛上，"能站"不等于"安全"** ✗ —— 边上那一圈要用四邻判 ✓
        """
        if not self.ok(x, z):
            return False
        for (dx, dz) in DIRS:
            if not self.ok(x + dx, z + dz):
                return False
        return True

    def region(self, sx, sz, limit: int = 20000) -> set:
        """★与 (sx,sz) 连通的那一整块能站的区域★ ✓（BFS ✓ 走同样的邻居规则 ✓）

        用途 ✓：**只在这块区域里挑目标和路** ✓ ——
          隔着虚空的另一块"孤岛"即使有地板 ✓ 也**不许**当目标 ✗（中间是空的，走不过去 ✓）
        """
        if not self.ok(sx, sz):
            # ★★起点自己"不 ok"时不许直接回空集★★ ✗（第 31 轮 ✓ 实测撞到 ✓）
            #   现场 ✗：假人**站在墙头**（`y=72` ✓）而那一柱在**7 1 层**被记成了障碍 ✓
            #     ⇒ 老代码 `return set()` ✗ ⇒ 连通区 **0 格** ✗
            #       ⇒ `platform`/`whereami`/规划全都会报"这片区域是空的"✗（**假**的 ✓）
            #   ⇒ 口径 ✓：与 `plan()` 一致 —— **就近找落脚点**（半径 3 ✓）✓
            #     找不到 ⇒ 才是真的空 ✓
            near = self.nearest_standable(sx, sz, 3)
            if not near:
                return set()
            sx, sz = near
        # ★★连通区缓存 ✗★（2026-09-30 第 40 轮 ✓ ⇒ P148 ✓）
        #   ★为什么✗★：实测这一函式 **0.79 秒** ✗ 而 `walk_route` 每跳都新建 Planner ✗
        #     ⇒ 同一张图被反复洪泛（一腿 4 跳 ⇒ 约 3 秒×4 ✗）
        #   ★为什么键里必须有 `rev`✗★：图会被 `absorb_true()` 改 ✓（验真纠正 ✓）
        #     ⇒ ★没有版本号就会读到**旧连通区**✗★ ⇒ 又造出"假 unreachable" ✗
        #   ★配置也要进键✗★：洪泛用的是 `neighbors()` ✓ 它取决于
        #     `level`／`max_up`／`auto_step_on`／`avoid_edge`／`blocked` ✓
        #     （`blocked` 用**规模**当版本 ✓ —— ★实测确认它只增不减✗★：全仓没有
        #       `BLOCKED.pop`／`del`／`clear` ✓ ⇒ 规模单调 ✓ ⇒ 可以当版本 ✓
        #       ⚠ 将来若有人加了删除 ⇒ **这条缓存要跟着改** ✗）
        key = (getattr(self.m, "rev", 0), int(sx), int(sz), int(self.level),
               bool(self.same_level_only), int(self.max_up), bool(self.auto_step_on),
               bool(self.avoid_edge), len(self.blocked or ()))
        cache = getattr(self.m, "_regions", None)
        if cache is not None and key in cache:
            return cache[key]
        seen = {(int(sx), int(sz))}
        stack = [(int(sx), int(sz))]
        while stack and len(seen) < limit:
            cx, cz = stack.pop()
            for (nx, nz, _c) in self.neighbors(cx, cz):
                if (nx, nz) not in seen:
                    seen.add((nx, nz))
                    stack.append((nx, nz))
        if cache is not None:
            cache[key] = seen
        return seen

    def in_box(self, x, z) -> bool:
        x0, _, z0, x1, _, z1 = self.m.box
        return x0 <= x <= x1 and z0 <= z <= z1

    # ── 目标处理（★专治假 unreachable★ ✓）────────────────────────────────
    def nearest_standable(self, x, z, rad: int = 2):
        """目标格站不住 ⇒ 在半径 `rad` 里找**最近的**能站格 ✓（返回 (x,z) 或 None ✓）"""
        if self.ok(x, z):
            return (x, z)
        best = None
        for dx in range(-rad, rad + 1):
            for dz in range(-rad, rad + 1):
                cx, cz = x + dx, z + dz
                if self.ok(cx, cz):
                    d = dx * dx + dz * dz
                    if best is None or d < best[0]:
                        best = (d, cx, cz)
        return (best[1], best[2]) if best else None

    # ── A* ────────────────────────────────────────────────────────────────
    def neighbors(self, x, z, nodes=None):
        y0 = self.y(x, z)
        if y0 is None:
            return []
        out = []
        for (dx, dz) in DIRS:
            nx, nz = x + dx, z + dz
            if nodes is not None and (nx, nz) not in nodes:
                continue
            if not self.in_box(nx, nz) or not self.ok(nx, nz):
                continue
            ny = self.y(nx, nz)
            dy = ny - y0
            # ★抬的那一级也按 `max_rise` ✓（半砖 ⇒ 自动上 ✓ 第 34 轮 ✓）
            if dy > self.max_rise(nx, nz, ny) or dy < -MAX_DOWN:
                continue
            cost = (1.0 + (0.6 if dy > 0 else 0.0) + (0.25 * abs(dy) if dy < 0 else 0.0)
                    + self.edge_extra(nx, nz))          # ★贴边加价★ ✗（第 25 轮 ✓）
            out.append((nx, nz, cost))
        for (dx, dz) in DIAGS:                      # ★不许切角★ ✗（两侧正交都要能站 ✓）
            nx, nz = x + dx, z + dz
            if nodes is not None and ((nx, nz) not in nodes):
                continue
            if not (self.ok(x + dx, z) and self.ok(x, z + dz)):
                continue
            if not self.in_box(nx, nz) or not self.ok(nx, nz):
                continue
            ny = self.y(nx, nz)
            dy = ny - y0
            if dy > self.max_rise(nx, nz, ny) or dy < -MAX_DOWN:   # ★半砖=自动上 ✓ 第 34 轮 ✓
                continue
            out.append((nx, nz, 1.4142 + (0.6 if dy > 0 else 0.0)
                        + (0.25 * abs(dy) if dy < 0 else 0.0)
                        + self.edge_extra(nx, nz)))     # ★贴边加价（斜着也算 ✓）★ ✗
        return out

    def plan(self, sx, sz, gx, gz, max_nodes: int = 20000, region: set | None = None,
             nodes: set | None = None):
        """返回 (路径 ✓ 原因 ✓)；路径是 [(x,y,z), …] ✓ 含起点与终点 ✓

        `region` 给了 ⇒ **目标必须在同一块连通区域里** ✓ 否则**坚决不去** ✗ 并说清为什么 ✓
        `nodes` 给了 ⇒ 只允许走这个格子集合 ✓（★"全程内陆"的安全走廊就是这么算的 ✓）
        """
        sx, sz, gx, gz = int(sx), int(sz), int(gx), int(gz)
        if not self.in_box(sx, sz):
            return None, "起点 (%d,%d) 不在地图里（图 box=%s）" % (sx, sz, self.m.box)
        if not self.ok(sx, sz):
            near = self.nearest_standable(sx, sz, 3)
            if not near:
                return None, "起点 (%d,%d) 站不住，附近也找不到落脚点" % (sx, sz)
            sx, sz = near
        if region is None:
            region = self.region(sx, sz)
        if (gx, gz) not in region:
            near = None
            if self.ok(gx, gz):
                near = min(region, key=lambda c: (c[0] - gx) ** 2 + (c[1] - gz) ** 2) if region else None
            if near and (near[0], near[1]) != (gx, gz):
                d = math.hypot(near[0] - gx, near[1] - gz)
                if d <= 3.0:
                    return None, ("目标 (%d,%d) 能站，但**和你不在同一块连通的平台上** ✗"
                                  "（走过去要跨虚空 ✓ 最近的自家落脚点 (%d,%d) 离它 %.1f 格）"
                                  % (gx, gz, near[0], near[1], d))
            return None, ("目标 (%d,%d) **不在你脚下这块连通区域里** ✗ ⇒ 中间隔着虚空 ✓ ⇒ "
                          "**不去** ✗（空岛上「看着能站」不等于「走得过去」✗）" % (gx, gz))
        tgt = self.nearest_standable(gx, gz, 2)
        if not tgt:
            if not self.in_box(gx, gz):
                return None, "目标 (%d,%d) 不在地图里（图 box=%s）" % (gx, gz, self.m.box)
            # ★C3（§79.230）：这里要的是**落脚面**（物理＋政策『树冠不落』）✗★
            #   ⇒ 把意图写明 ✗ 别再「悄悄用默认值」✗★（`floor_only=True` 就是 `is_landing`）✗★
            s = self.m.surface(gx, gz, below=self.level + 1, floor_only=True)
            if not s:
                return None, "目标 (%d,%d) 这一柱子**没有已知地板** ⇒ 未知 ⇒ 不走（不是「走不到」✓ 是「不知道」✗）" % (gx, gz)
            return None, "目标 (%d,%d) 上方被 %s 占着 ⇒ 站不住；半径 2 内也没有落脚点" % (gx, gz, s[1])
        adjusted = (tgt != (gx, gz))
        if (sx, sz) == tgt:
            return [(sx, self.y(sx, sz) + 1, sz)], "起点就是目标（或目标的落脚点）"

        openq = [(0.0, (sx, sz))]
        came: dict = {}
        g = {(sx, sz): 0.0}
        seen = 0
        while openq:
            _, cur = heapq.heappop(openq)
            if cur == tgt:
                break
            seen += 1
            if seen > max_nodes:
                return None, "搜索节点超过 %d ⇒ 放弃（图太大或目标太绕）" % max_nodes
            for (nx, nz, cost) in self.neighbors(*cur, nodes=nodes):
                ng = g[cur] + cost
                if ng < g.get((nx, nz), 1e18):
                    g[(nx, nz)] = ng
                    came[(nx, nz)] = cur
                    h = math.hypot(nx - tgt[0], nz - tgt[1])
                    heapq.heappush(openq, (ng + h, (nx, nz)))
        if tgt not in came and tgt != (sx, sz):
            return None, "图上**真的不通** ✗（起点 (%d,%d) 与目标 (%d,%d) 之间没有落脚的路 ✓ 搜索了 %d 个格子）" % (sx, sz, tgt[0], tgt[1], seen)
        path = [tgt]
        while path[-1] != (sx, sz):
            path.append(came[path[-1]])
        path.reverse()
        pts = [(x, self.y(x, z) + 1, z) for (x, z) in path]     # 脚站的那一格 y ✓
        why = "距离 %.1f 格 ｜ 搜索 %d 格" % (g[tgt], seen)
        if adjusted:
            why += " ｜ ★目标原来站不住 ⇒ 改走它旁边 (%d,%d)★" % tgt
        return pts, why

    @staticmethod
    def simplify(pts):
        """★把直线上多余的点去掉★ ✓（点越少 ⇒ 发的指令越少 ⇒ 越快越稳 ✓）

        只保留**方向变化**的点 ＋ 终点 ✓（同一条直线上的中间点没意义 ✓）
        """
        if len(pts) <= 2:
            return list(pts)
        out = [pts[0]]
        for i in range(1, len(pts) - 1):
            ax, az = out[-1][0], out[-1][2]
            bx, bz = pts[i][0], pts[i][2]
            cx, cz = pts[i + 1][0], pts[i + 1][2]
            d1 = (bx - ax, bz - az)
            d2 = (cx - bx, cz - bz)
            if (d1[0] * d2[1] - d1[1] * d2[0]) != 0:      # 叉积 != 0 ⇒ 拐弯 ✓
                out.append(pts[i])
        out.append(pts[-1])
        return out

    def safe_targets(self, sx, sz, dmin: float = 6.0, dmax: float = 24.0, region=None,
                     corridor: bool = True, min_n: int = 0):
        """★可以放心去的目标★ ✓ —— **同一块连通区域里** ＋ **内陆格**（四邻都能站 ✓）

        ⚠ 这就是那次事故的修法 ✗（2026-09-23 ✓ 我自己的验收脚本把假人送进虚空 ✓）：
          原来的挑法只要求"这一格能站" ✓ ⇒ 平台**边上一格**也算 ✓
          而空岛的平台边上一格 = 一步踩空 = 掉虚空 ✗
          ⇒ 现在挑目标只从**内陆格**里挑 ✓（离边至少一格 ✓）

        `corridor=True` ✓：不光终点内陆 ✓ **整条走廊**都在内陆子图里 ✓

        `min_n>0` ✓（★2026-09-23 加的★）：**安全目标不够就先放宽** ✓ 但**必须自己承认**✗ ——
          实测 ✓：假人站在某些位置时，安全走廊只剩 0~2 个目标 ✗
          ⇒ 验收脚本直接"挑不够 3 个 ⇒ FAIL"✗ —— 而那不是"功能坏了"✗ 是"这块地方就是这么小"✓
          放宽的规则 ✓：补上"终点内陆但走廊贴边"的格子 ✓ 并把 `last_relaxed=True` 记下来 ✓
          ⇒ 调用方**看得见"这几个是放宽挑的"** ✓ 而不是以为它们一样安全 ✗
        """
        if region is None:
            region = self.region(sx, sz)
        self.last_relaxed = False
        root = (sx, sz) if self.ok(sx, sz) else None
        out = []
        if corridor:
            # ★安全走廊★ ✓：只在**内陆格**这张子图上找路 ✓
            inter = {c for c in region if self.interior(*c)}
            if root is not None and root not in inter:
                inter = inter | {root}       # 起点站在边上 ⇒ 允许它自己"上船" ✓
            cands = sorted((c for c in inter if c != root),
                           key=lambda c: (c[0] - sx) ** 2 + (c[1] - sz) ** 2)
            for (x, z) in cands:
                d = math.hypot(x - sx, z - sz)
                if d < dmin:
                    continue
                if d > dmax:
                    break
                pts, _why = self.plan(sx, sz, x, z, region=region, nodes=inter)
                if not pts:
                    continue
                out.append((round(d, 2), x, self.y(x, z) + 1, z))
                if len(out) >= 24:
                    break
            out.sort()
            if len(out) < int(min_n or 0):
                # ★放宽：补"终点内陆、但走廊可能贴边"的格子 ✓ 并且**明确标记**✗
                self.last_relaxed = True
                have = {(t[1], t[3]) for t in out}
                for (x, z) in sorted(region, key=lambda c: (c[0] - sx) ** 2 + (c[1] - sz) ** 2):
                    if (x, z) in have or not self.interior(x, z):
                        continue
                    d = math.hypot(x - sx, z - sz)
                    if not (dmin <= d <= dmax):
                        continue
                    pts, _why = self.plan(sx, sz, x, z, region=region)
                    if not pts:
                        continue
                    out.append((round(d, 2), x, self.y(x, z) + 1, z))
                    if len(out) >= max(24, int(min_n or 0)):
                        break
                out.sort()
            return out
        for (x, z) in region:
            if not self.interior(x, z):
                continue
            d = math.hypot(x - sx, z - sz)
            if dmin <= d <= dmax:
                out.append((round(d, 2), x, self.y(x, z) + 1, z))
        out.sort()
        return out

# ##########################################################################
# ★★A3：按**碰撞顶高**判（★`AUTO_STEP_BY_HEIGHT` A/B 开关 ✗ 默认**关**✗★）
#   ★用户裁决 A3✗★：★"★寻路层接 `max_height`：先加 `AUTO_STEP_BY_HEIGHT` 开关 A/B 并行跑 ✗
#     ★绿了再换默认★"✗★ ✓
#   ★为什么两个阈值**不是我编的**✗★：★它们就写在上面那两段注释里（★都是实测口径✗★）✗★ ——
#     · ★自动上台阶上限 **0.6 格**✗★（★第 34 轮：写宽了会**假可达**✓★）✗★ ✓
#     · ★跳跃上限 ≈ **1.25 格**✗★（★模组源码 `0.42` 初速 ⇒ 能上约 1.25✓★）✗★ ✓
#   ★口径✗★：
#     · ★开关**关** ⇒ 与今天**逐字相同**✗★（★名字白名单／`shape()`✓★）✗★ ✓
#     · ★开关**开** ⇒ 只问导出的 `max_height` ✗★ ✓
#     · ★拿不到高度 ⇒ `False`（★"★上不去★"✗ 保守 ✗ 与白名单同一个方向：★宁可不指望 ✗ 也不假可达★✓★）✗
#       ★**绝不**静默回落到名字✗★（★那就等于开关没生效而人还以为生效了✓★）✗★ ✓
# ##########################################################################
BY_HEIGHT = (__import__("os").environ.get("AUTO_STEP_BY_HEIGHT", "").strip().lower()
             in ("1", "true", "yes", "on"))
STEP_MAX = 0.6          # ★自动上台阶上限（★第 34 轮实测口径✗★）
JUMP_MAX = 1.25         # ★跳跃上限（★模组 `0.42` 初速实测口径✗★）

_HEIGHTS = None         # ★惰性读一次 ✗ 不许每格读 3.6 MB✗★
_HEIGHTS_OK = None


def _heights():
    """★导出的 `max_height` 表✗★（★读一次 ✗ 缓存✗★）⇒ `(表, 读到了没有)`"""
    global _HEIGHTS, _HEIGHTS_OK
    if _HEIGHTS is None:
        try:
            import json as _j
            import kb_export as _KX
            p = _KX.find_export("")
            if pathlib.Path(p).is_file():
                _d = _j.loads(pathlib.Path(p).read_text(encoding="utf-8"))
                _HEIGHTS = {k: (v or {}).get("max_height")
                            for k, v in (_d.get("blocks") or {}).items()}
                _HEIGHTS_OK = True
            else:
                _HEIGHTS, _HEIGHTS_OK = {}, False
        except Exception:
            _HEIGHTS, _HEIGHTS_OK = {}, False
    return _HEIGHTS, bool(_HEIGHTS_OK)


def height_of(block: str):
    """★这一格的碰撞顶高✗★ ⇒ ★拿不到回 `None` ✗ 不许猜✗★ ✓"""
    if not block:
        return None
    h = _heights()[0].get(block)
    try:
        return None if h is None else float(h)
    except Exception:
        return None

