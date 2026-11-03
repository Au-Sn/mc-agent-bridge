#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skills.py — 技能层：把"底层动作"包装成"像玩家一样的行为"，并强制治理规则

分层理由：
  底层动作（walk_to / dshdig / place_adjacent / sift …）是机器语言，
  大模型直接调它俩问题：既要记住参数名，又容易漏掉验证。
  技能层的职责：
    1. 给出语义清晰、参数很少的动作（goto / dig / place / chop / sift / attack / craft …）
    2. **每个技能自带验收**：动作干完必须用世界状态复核，绝不拿自述当结果
    3. **治理**：脚手架类技能（/give）默认在代码层禁用；
       危险技能（可能掉虚空、可能砸到自己）标记出来给大脑看
    4. 每次调用都写进行动日志，供复盘与错题本使用

自测：
    py agent/skills.py                 # 列出全部技能与参数
    py agent/skills.py scan radius=5   # 跑一个只读技能
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channel import Channel, BridgeError          # noqa: E402
from memory import Journal                        # noqa: E402
from world import World                           # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


# --------------------------------------------------------------------------- #
# 技能声明表：名字 / 说明 / 参数 / 治理标记
# 参数写法：名字 -> (类型, 说明, 是否必填, 默认值)
# --------------------------------------------------------------------------- #

SPEC: dict[str, dict] = {
    "scan": dict(desc="扫描周边方块，返回分类计数（只读，先看清再动手）",
                 params={"radius": ("integer", "扫描半径（格，建议 4~8）", False, 6)}),
    "verify": dict(desc="查一个方块的权威状态（任何‘我放下了/挖掉了’都必须用它复核）",
                   params={"x": ("integer", "x", True), "y": ("integer", "y", True),
                           "z": ("integer", "z", True)}),
    "look_block": dict(desc=("准星感知（Jade）：读出假人**此刻正对着**的那块方块 —— "
                             "名称/坐标/距离/入射面/所需工具（读方块标签得到，不是猜）/方块状态。"
                             "只读。动手（挖/放/建）之前先问一句，能省掉一整轮试错 ✗。"),
                       params={"reach": ("number", "视距（默认 5 = 玩家交互距离）", False, 5.0),
                               "nbt": ("boolean", "是否附带方块实体数据（箱子/机器才有）", False, False),
                               "raw": ("boolean", "附带上游原始方块信息（排查用）", False, False)}),
    "goto": dict(desc="走到指定坐标附近（**反应式直线走** ✓ 快 ✓ 但不绕障：遇到 U 形障碍会卡在局部极值 ✗）。"
                      "远距离 / 要绕障请改用 `path_goto` ✓",
                 params={"x": ("integer", "x", True), "y": ("integer", "y", True),
                         "z": ("integer", "z", True),
                         "range": ("number", "到达判定半径（默认 0.4）", False, 0.4),
                         "clear": ("boolean", "挡路时是否挖开（默认否）", False, False)},
                 long=True),
    # ── 真正的寻路（A* + 逐格执行 ✓ 2026-09-20 上桥 ✓）────────────────────────
    # 与 `goto` 的分工（文档 §1/§5 ✓）：
    #   * `goto`      = 反应式直线走 ✓ 看目标、move forward ✓ 带防坠崖 ✓
    #                   ⇒ 遇到 U 形障碍**必卡在局部极值** ✗（那正是它做不到的部分 ✗）
    #   * `path_goto` = **先想清楚再走** ✓ 批量读地图 → A* → 逐格走 ✓（学 mineflayer 的
    #                   Movements 代价模型 ✓）＋ 学车万女仆的**分层退化**（走不通才回传 ✓）
    # ⚠ 但必须如实报告"这次是回传的、不是走过去的" ✗（`warped` ✓ 文档明确写了这条纪律 ✓）
    "path_goto": dict(desc=("★真正的寻路★：A* 规划 + 逐格执行 ✓ 能绕障 ✓ 能上台阶 ✓ 会防坠崖 ✓ "
                            "卡住自动重规划 ✓ 只有万不得已才回传 ✓ —— 而且**回传会如实标 warped=true** ✗ "
                            "绝不假装走过去了 ✓。远距离/要绕障请用它 ✓。"
                            "⚠ 代价：它**先扫一片区域**（实测约 67ms / 4³ 块 ✓ ⇒ 半径 6 约 3~8 秒 ✓）"),
                       params={"x": ("integer", "x", True), "y": ("integer", "y", True),
                               "z": ("integer", "z", True),
                               "timeout": ("number", "整段总时长上限（秒，默认 90）", False, 90),
                               "radius": ("integer", "扫描包围盒半径（省略=6；越大越慢 ✗）", False, None),
                               "plan_timeout": ("number", "单次搜索预算（秒，默认 8）", False, None),
                               "scan_timeout": ("number", "单次扫描预算（秒，默认同 plan_timeout）", False, None),
                               "dig": ("boolean", "允许挖穿挡路的方块（默认否 ✗ 保守）", False, None),
                               "place": ("boolean", "允许搭桥（默认否 ✗）", False, None),
                               "warp": ("boolean", "走不通时允许传送兜底（默认是 ✓ 返回会标 warped）", False, None),
                               "exact": ("boolean", "★钉死那一格★（GoalBlock ✓ 默认否=GoalNear 允许 ±1 格）", False, None)},
                       long=True,
                       danger="dig/place 会改变世界 ✗；warp 是**传送**兜底 ⇒ warped=true 时**不算走过去** ✗"),
    "dig": dict(desc="挖掉一个方块（自动换合适的工具）",
                params={"x": ("integer", "x", True), "y": ("integer", "y", True),
                        "z": ("integer", "z", True)},
                danger="若目标在脚下，挖掉后可能会掉下去"),
    "place": dict(desc="紧贴一个已确认实心的方块放置物品；会自动报告真正落点的格子",
                  params={"x": ("integer", "参照方块 x", True), "y": ("integer", "参照方块 y", True),
                          "z": ("integer", "参照方块 z", True),
                          "item": ("string", "要放的物品（可省略=用主手）", False, None)}),
    "sneak_place": dict(desc="潜行贴边放置（平台外扩专用）：会逐步验证地板，不会走空",
                        params={"pieces": ("integer", "最多放几块", False, 1)}, long=True,
                        danger="外扩到虚空边缘有坠落风险，已内置逐步地板校验"),
    "chop": dict(desc="砍最近的树（原木+树叶），掉落物会自动拾取",
                 params={"max_logs": ("integer", "最多砍多少原木", False, 64)}, long=True),
    # ★★ 作业（`agent/jobs.py` ✓ 用户明确要求："把收割→补种做成**一条作业**"✓）★★
    #   一条指令 = 一整件事 ✓ 自带前置检查（背包守卫 ✓）＋ 自带自证（重扫世界＋数背包 ✓）
    "harvest": dict(desc=("★作业：收割 → 补种★（**一条指令干完一整件事** ✓）。"
                          "先过背包守卫 ✓ 再只收成熟的小麦（`age>=7` ✓ 青苗只掉种子 ✗）✓ "
                          "**逐株走到跟前**收（收与捡必须同位置 ✗ 否则收成够不着、5 分钟消失 ✗）✓ "
                          "收完在同一处补种 ✓ 顺手把**本来就空着**的耕地也种上 ✓ "
                          "最后**重扫世界 ＋ 数背包**自证 ✗（不听动作自述 ✗）"),
                 params={"x0": ("integer", "区域 x 最小", True), "y0": ("integer", "y 最小", True),
                         "z0": ("integer", "z 最小", True), "x1": ("integer", "x 最大", True),
                         "y1": ("integer", "y 最大", True), "z1": ("integer", "z 最大", True),
                         "replant": ("boolean", "是否补种（默认是 ✓ 少种就是把田收秃 ✗）",
                                     False, True)}, long=True),
    "sift_at": dict(desc=("★作业：筛矿★（**一条指令干完一整件事** ✓ 模组 `/dshuse` 那条路 ✓）。"
                          "先过背包守卫 ✓ → 读筛子真值（是不是筛子 ✓ **装没装网** ✓）→ 有无沙砾 ✗ "
                          "→ **用脚走到够得着** ✓ → 拿着沙砾 ✓ → ★一下一下筛，**每一下都显式指名 `up` 面**★ ✗ "
                          "→ 每一下都用**世界真值**判（沙砾有没有被吃掉 ✓ 碎块有没有进背包 ✓）→ "
                          "连续 3 下没吃料就**停手并大声说明** ✗。"
                          "★为什么这条是 P16 的正解★ ✓：打**侧面**时 `use` 每下都回 `success:true` ✓ "
                          "而筛子 NBT **一字不变** ✗✗ —— 靠准星的旧路全看站位 ✗；"
                          "这里把面**钉死成参数** ✓ ⇒ 不可能再打错 ✓"),
                 params={"x": ("integer", "筛子 x", True), "y": ("integer", "筛子 y", True),
                         "z": ("integer", "筛子 z", True),
                         "uses": ("integer", "最多筛几下（默认 16）", False, 16),
                         "item": ("string", "筛什么（默认 gravel ✓ 泥土也能筛 ✓ 泥土才出石砾 ✓）",
                                  False, "minecraft:gravel")}, long=True),
    # ⚠ 上面那条是**作业**（推荐 ✓ 模组路 ✓）；下面这条是**旧的 Lua 路** ✗（靠准星 ✓ 见 P16 ✗）
    "sift": dict(desc="用手里的筛子和网连续筛矿（**旧 Lua 路** ✗ 靠准星命中 `up` 面 ✓ ⇒ 全看站位 ✗，"
                      "建议改用 `sift_at` ✓）。**必须给出筛子坐标**（不给就等于对着空气右键 ✗，"
                      "会把手里物品放到地上 ✗）；技能层会先做距离预检 ✓，"
                      "并在**开筛前用准星硬检查**是否命中筛子的 `up` 面 ✓（P16 的解药之一 ✓）",
                 params={"x": ("integer", "筛子 x", True), "y": ("integer", "筛子 y", True),
                         "z": ("integer", "筛子 z", True),
                         "item": ("string", "筛的原料（默认 gravel）", False, "minecraft:gravel"),
                         "count": ("integer", "最多用多少原料", False, 16),
                         "seconds": ("number", "连续筛多少秒", False, 12),
                         "reach": ("number", "允许的最大距离（默认 4 格）", False, 4.0)}, long=True),
    "equip": dict(desc="把背包里的物品拿到主手",
                  params={"item": ("string", "物品 id 或名字", True)}),
    "install_mesh": dict(desc="给面前的筛子装网",
                         params={"x": ("integer", "筛子 x", True), "y": ("integer", "筛子 y", True),
                                 "z": ("integer", "筛子 z", True)}),
    "look": dict(desc="转头看向某个坐标",
                 params={"x": ("number", "x", True), "y": ("number", "y", True),
                         "z": ("number", "z", True)}),
    "locate": dict(desc="问 GPS 自己在哪（需要 4 个不共面的基站；基站没搭好会失败）",
                   params={"timeout": ("number", "等多久（秒）", False, 2)}),
    "attack": dict(desc="还击最近的敌对生物（先看它、再连续攻击，直到它死或超时）",
                   params={"radius": ("integer", "搜索半径", False, 12),
                           "seconds": ("number", "最长打多久", False, 10)}, long=True),
    "flee": dict(desc="后退脱离危险",
                 params={"seconds": ("number", "后退多少秒", False, 3)}),
    "eat": dict(desc="吃东西回血（需要主手拿着食物）",
                params={"item": ("string", "食物（可省略=用主手）", False, None)}),
    "find_block": dict(desc="找某种方块在哪（只查这一类，所以能搜大范围；可指定扫描中心 ✓"
                            "—— Lua 把半径钳到 12 ✓ 所以搜索更大范围的办法是**换中心多扫几次** ✓）",
                       params={"name": ("string", "方块名（可只写后半段，如 crafting_table）", True),
                               "radius": ("integer", "搜索半径（默认 16，Lua 会钳到 12）", False, 12),
                               "x": ("integer", "扫描中心 x（省略=用假人当前位置）", False, None),
                               "y": ("integer", "扫描中心 y", False, None),
                               "z": ("integer", "扫描中心 z", False, None)}, long=True),
    # ── 容器存取三件套（dshbridge 模组 ✓ 2026-09-20 上桥 ✓）─────────────────────
    # 为什么非得写模组 ✗（三条路都实测封死过 ✓ 见 docs/模组-容器存取与假人手.md）：
    #   · 原版 `/item replace block … container.N` 只走原版 `Container` 接口 ✗
    #     ⇒ 对 `sophisticatedstorage:netherite_barrel` 这类**模组容器**直接报"不是容器"✗
    #   · KubeJS 的 `block.inventory` 只对原版容器稳 ✗ 且语义是"脚本替它搬"✗（不是它自己拿 ✗）
    #   · 漏斗喂料**只能存不能取** ✗ 还要占一个漏斗 ✗
    # ⇒ 缺的那块 = "以**假人身份**、按 **Forge 能力接口**、跟任何容器打交道" ✓ 正是本模组 ✓
    "box_peek": dict(desc=("看一个容器里有什么（只读 ✓）。走 dshbridge 模组的 `IItemHandler` 能力 ✓ "
                           "⇒ 原版箱子/木桶/熔炉 ✓ 与**模组容器**通吃 ✓（原版 `/item` 对模组容器无效 ✗）"),
                     params={"x": ("integer", "容器 x", True), "y": ("integer", "容器 y", True),
                             "z": ("integer", "容器 z", True)}),
    "box_take": dict(desc=("把容器里的东西搬进**假人自己的背包**。模组纪律：先确认放得下 ✓ "
                           "放不下的**原样退回** ✓ 绝不静默吞物品 ✗（KubeJS 版就吃过这个亏 ✗）。"
                           "item 只写名字的一部分也行（如 gravel ✓）"),
                     params={"x": ("integer", "容器 x", True), "y": ("integer", "容器 y", True),
                             "z": ("integer", "容器 z", True),
                             "item": ("string", "只要这一种（省略=能拿的都拿）", False, None),
                             "count": ("integer", "最多拿几个（省略=不限量）", False, None)}, long=True),
    "box_put": dict(desc=("把假人背包里的东西放进容器。容器满时**如实报还剩多少** ✓ 不假装成功 ✗"),
                    params={"x": ("integer", "容器 x", True), "y": ("integer", "容器 y", True),
                            "z": ("integer", "容器 z", True),
                            "item": ("string", "只放这一种（省略=能放的就放）", False, None),
                            "count": ("integer", "最多放几个（省略=不限量）", False, None)}, long=True),
    # ── 模组 v2.0 四件套（★把"真人能干、假人干不了"的事补上★ ✓）──────────────
    # 为什么要有它们 ✗：假人与真人的**结构性差距只有一个 —— 它没有客户端** ✗
    #   ⇒ 一切"要靠客户端按键 / 界面 / 瞄准"的事它都干不了 ✗
    #   ⇒ 这四条就是把这些事**搬回服务端**做一遍 ✓（语义与真人一致 ✓ 不白送东西 ✗）
    "use_face": dict(desc=("★对着方块的**指定面**右键★（真人最日常的动作 ✗ 假人原来做不到 ✓）。"
                           "`dshuse` 走的是**真人那条服务端路径** ✓ ⇒ 拉杆/按钮/门 ✓ 播种/骨粉/锄地 ✓ "
                           "水桶/空桶 ✓ 床 ✓ 蛋糕 ✓ **筛子** ✓ 以及**一切模组方块**通吃 ✓。"
                           "aimy 是瞄准点在方块内的高度比例（0~1 ✓ 默认 0.5）——"
                           "★筛子必须从上方射进碗里（face=up）★ ✗ 打侧面时它**完全不动、而且一声不响** ✗"
                           "（错题本 P16 ✓）"),
                     params={"x": ("integer", "x", True), "y": ("integer", "y", True),
                             "z": ("integer", "z", True),
                             "face": ("string", "up/down/north/south/east/west（默认 up）", False, "up"),
                             "aimy": ("number", "瞄准点在方块内的高度比例 0~1（默认 0.5；筛子用 0.15）", False, 0.5)},
                     danger="会真的右键那个方块 ⇒ 可能改变世界（放置/消耗/点燃…）；模组会做触及距离检查 ✓"),
    "make": dict(desc=("★工作台合成（不开界面 ✓ 按**服务端配方表**真扣料真出货）★。"
                       "① 先 `op=can` 干跑（够不够料 ✓ 放不放得下 ✓）② 再 `op=do` 真做 ✓。"
                       "只接**真人在 3×3 工作台上做得出来**的配方 ✓ ⇒ 熔炼/粉碎之类机器配方**一律拒绝** ✗"
                       "（否则「合成」就变成凭空造物 ✗）。通吃模组配方 ✓（比 KubeJS 工单通用得多 ✓）"),
                 params={"op": ("string", "do/can/recipes（默认 do）", False, "do"),
                         "item": ("string", "产物 id 或配方 id（如 minecraft:cobblestone / oak_planks）", True),
                         "times": ("integer", "做几份（默认 1）", False, 1)}, long=True),
    "inv": dict(desc=("★整理背包★（真人拖背包 ✗ 假人做不到 ✓ 这里补上）。"
                      "op=list 列出槽位 ✓；op=move a=源 b=目标 count=几个 ✓；"
                      "**op=drop a=槽位** ⇒ 从**那个槽位**丢出去 ✓（这是历史卡点的正解 ✗："
                      "假人的 `drop` 只能丢**手持** ✗ 主背包里的东西**交不出来** ✗ 错题本 I4 ✓）；"
                      "op=equip a=槽位 ⇒ 自动装到护甲/副手 ✓；op=hotbar a=槽位 ⇒ 换进选中的快捷栏 ✓"),
              params={"op": ("string", "list/move/drop/equip/hotbar", True),
                      "a": ("integer", "源槽位（list 不用）", False, None),
                      "b": ("integer", "目标槽位（move 用）", False, None),
                      "count": ("integer", "数量（省略=尽量多）", False, None)}, long=True),
    "ent_use": dict(desc=("★右键实体★（喂食 ✓ 繁殖 ✓ 挤奶 ✓ 剪毛 ✓ —— 真人对动物做的事）。"
                          "target 是**选择器**（如 @e[type=cow,limit=1,sort=nearest] ✓ 或玩家名）"),
                    params={"target": ("string", "实体选择器", True)}, long=True),
    # ── 模组 v2.1 三件套（继续往"像真人"补 ✓）────────────────────────────────
    # ══ ★★模组 v2.6：把"看"和"走"变成原生行为★★（2026-09-19 晚 ✓）════════════
    #   动机（**有实测数字** ✓ 见 docs/模组-容器存取与假人手.md §10 ✓）：
    #     · 原来看世界走 Lua 的 4³ 分块 ✗ ⇒ 2268 格 3.5 s ✗ 7696 格**直接超时** ✗
    #     · 原来走路是"一格一次指令脉冲"✗ ⇒ 杂物区 4.5 s/途经点 ＋ 放弃 ✗
    #   ⇒ 这一版把"一次问一大片""一条指令走一整段"做成**服务端原生** ✓
    "digest": dict(desc=("★一条指令一份态势★（模组 v2.6 ✓）—— 位置/朝向/血/饿/经验/模式/手持 ＋ "
                         "背包（种类·件数·**空位**）＋ 附近实体（含**敌对计数**）＋ "
                         "**地上的掉落物**（带「还剩多少 tick 消失」✗ —— 纪律⑤的哨兵 ✓）＋ 准星命中 ✓。"
                         "★取代「一次决策要问 4~6 条指令」✗★（每次决策先跑它 ✓）"),
                   params={"radius": ("number", "实体/掉落物统计半径（默认 8）", False, 8.0)}),
    "scan_box": dict(desc=("★原生区域扫描★（模组 v2.6 ✓ **毫秒级** ✓）—— 聚合返回各方块名计数 ✓ "
                           "给了 match= 才逐格列 cells（**带方块状态** ✓ 如 `age=7` ✓ 决定「该不该收」✓）✓ "
                           "★取代 Lua 的 4³ 分块扫描★ ✗（2268 格要 3.5 s ✗ 7696 格**超时** ✗ ⇒ "
                           "寻路/农田/矿脉查询从此不再怕大范围 ✓）"),
                     params={"x0": ("integer", "x 最小", True), "y0": ("integer", "y 最小", True),
                             "z0": ("integer", "z 最小", True), "x1": ("integer", "x 最大", True),
                             "y1": ("integer", "y 最大", True), "z1": ("integer", "z 最大", True),
                             "match": ("string", "只看名字含这个子串的方块（给了才列 cells）", False, None),
                             "max": ("integer", "cells 一页最多几格（默认 64）", False, 64),
                             "page": ("integer", "cells 第几页（默认 1）", False, 1)}, long=True),
    "look_hit": dict(desc=("★准星射线 ＋ **可达性**★（模组 v2.6 ✓）—— 读出正对着的方块/实体的"
                           "**面** ✓ 距离 ✓ 以及 **reachable**（真人触及 4.5 格 ✓）✗。"
                           "★把 P16 那类「打得中、却一声不响、完全无效」✗ 变成**调用点就能问**★ ✓"
                           "（筛矿/播种/放置之前先问一句 ✓ 省掉一整轮试错 ✓）"),
                     params={"reach": ("number", "射线长度（默认 4.5 ＝ 真人触及距离）", False, 4.5)}),
    "walk_to": dict(desc=("★走一条腿★（模组 v2.6 ✓ **原生逐 tick 推进** ＝ 像真人按住 W ✓）—— "
                          "**一条指令走一整段** ✓ 带**空岛防坠**（前方没有落脚点就停手 ✓ 宁可不动也不掉虚空 ✓）"
                          "与**卡住诊断**（为什么走不动：前方挡？头顶低？没支撑？✓ P21 缺的就是这句 ✗）✓ "
                          "本技能会**等到走完**并如实回 reached/why ✗（走不到就说走不到 ✓ 不假装到了 ✓ "
                          "也**绝不偷偷传送** ✗）"),
                    params={"x": ("integer", "目标 x", True), "y": ("integer", "目标 y", True),
                            "z": ("integer", "目标 z", True),
                            "ms": ("integer", "预算毫秒（默认 10000）", False, 10000),
                            "exact": ("boolean", "是否钉死那一格（默认否＝允许 1 格内）", False, False)},
                    long=True),
    "events": dict(desc=("★增量事件流★（模组 v2.6 ✓）—— 受伤 ✓ 吃东西 ✓ 背包增减 ✓ **模式变化**"
                         "（★创造模式警报 ✗ P17 那种「自给证据失真」当场就能看见 ✓）✓ "
                         "**位置瞬移**（有人 `tp` 它 ✗ ⇒ 给「主线不走 tp」这条纪律当哨兵 ✓）✓ "
                         "**地上掉落物 / 快消失的掉落物**（★P20 丢 25 个绿宝石那次的警报 ✓★）✓ "
                         "走路的起止与结果 ✓。传 since=cursor 只取新的 ✓（从「我轮询」变「它告诉我」✓）"),
                   params={"since": ("integer", "只要这个序号之后的事件（省略＝取全部）", False, None)}),
    "auto": dict(desc=("自动行为开关（模组 v2.6 ✓）："
                       "`eat` = 饿了就**走真人那条路**吃 ✓（`ItemStack.use` ⇒ 原版有 **1.6 秒咀嚼** ✓ "
                       "不是瞬间白送 ✗）；`idle` = 空闲时四处看（★默认关 ✗★ —— 它会把准星转走 ✗ "
                       "而长作业（筛矿 `use interval`）中途不发指令 ✗ ⇒ 会变成 P16 那类**静默无效** ✗）；"
                       "`status` = 看现在开着什么 ✓"),
                 params={"what": ("string", "eat / idle / status", True),
                         "on": ("boolean", "开/关（status 不用给）", False, None),
                         "minfood": ("integer", "eat 的触发阈值（默认 14）", False, 14)}),
    "place_at": dict(desc=("★显式放方块 ＋ **落点校验**★（模组 v2.7 ✓）。"
                           "走的是真人那条 `useItemOn` ✓ 而且和 `dshuse` 的区别是它**会说清为什么** ✗："
                           "物品在不在背包里 ✓ 目标格是不是空气 ✓ 六邻有没有支撑面 ✓ "
                           "★放完**读世界真值复核**并报出**实际放下的方块名**★ ✗（不听自述 ✓）。"
                           "★解决的是错题本 P30★ ✗：同一条 `dshuse … up` 一次 FAIL 一次 CONSUME ✗ "
                           "而 FAIL 什么原因都不说 ✗ ⇒ 现在**可判读** ✓"),
                     params={"x": ("integer", "目标格 x（要放成方块的那一格）", True),
                             "y": ("integer", "目标格 y", True),
                             "z": ("integer", "目标格 z", True),
                             "item": ("string", "放什么（如 minecraft:cobblestone）", True)}, long=True),
    "box_slot": dict(desc=("★按**槽位**精确读写容器★（v2.1 ✓）。"
                           "v2.0 只能按「物品名子串」匹配 ✗ ⇒ 同一种物品占多格时分不清是哪一格 ✗；"
                           "自动化经常要「就动第 0 格」✓（机器输入槽 ✓ 燃料槽 ✗）⇒ 用这个 ✓。"
                           "op=get 看某一格 ✓；op=take 从那一格搬进背包 ✓；"
                           "op=put 把**主手**的东西放进那一格 ✓（放不下会如实报 ✗ 绝不吞 ✓）"),
                     params={"op": ("string", "get/take/put", True),
                             "x": ("integer", "容器 x", True), "y": ("integer", "容器 y", True),
                             "z": ("integer", "容器 z", True),
                             "slot": ("integer", "槽位号（0 起算 ✓ 与 inv list 一致）", True),
                             "count": ("integer", "数量（省略=尽量多）", False, None)}, long=True),
    "entbox": dict(desc=("★实体容器★（箱子矿车 ✓ 漏斗矿车 ✓ 以及一切实现了 Container 的实体 ✓）。"
                         "op=peek 看内容（可给 page 翻页 ✓ 大容器一次看不全 ✗）；"
                         "op=take 搬进背包 ✓；op=put 从背包放进去 ✓。语义与 box_* 完全一致 ✓"),
                   params={"op": ("string", "peek/take/put", True),
                           "target": ("string", "实体选择器", True),
                           "item": ("string", "只动这一种（可省）", False, None),
                           "count": ("integer", "数量（省略=尽量多）", False, None),
                           "page": ("integer", "peek 翻页（默认 1 ✓ 每页 24 格）", False, 1)}, long=True),
    "trade": dict(desc=("★跟村民交易★（真人点交易界面 ✗ 假人打不开 ✓ 这里补上）。"
                        "走的是原版那条路 ✓（`interactOn` 开商人菜单 ⇒ `setSelectionHint`＋`tryMoveItems` ✓ "
                        "与服务端处理「选交易」包时**同一套调用** ✓）。"
                        "op=list 列报价；op=do index=N times=M 真交易 ✓。"
                        "⚠ 成没成**以报价的 uses 计数与背包实增为准** ✗ —— 那个方法**不返回值** ✗"),
                  params={"op": ("string", "list/do", True),
                          "target": ("string", "村民选择器", True),
                          "index": ("integer", "第几条报价（list 看 ✓ 0 起算）", False, 0),
                          "times": ("integer", "交易几笔（默认 1）", False, 1)}, long=True),
    "turtle": dict(desc=("给海龟下发原生命令（透传）。可用动作：forward/back/up/down/turn_left/"
                         "turn_right/dig/dig_up/dig_down/place/place_up/place_down/attack/drop/"
                         "suck/select/refuel/inspect/select_item/inv_list/inv_count/locate/status/"
                         "equip/unequip/craft/gather/dig_up_while/chop_log/place_row/tunnel/"
                         "mine_column/goto/calibrate_auto"),
                   params={"cmd": ("string", "海龟动作名", True),
                           "who": ("string", "在哪台机器执行：turtle(默认)/cc0/cmd0", False, None),
                           "op": ("string", "子操作（如 inv_man 的 list）", False, None),
                           "slot": ("integer", "槽位（select/equip 用，1..16）", False, None),
                           "n": ("integer", "次数（refuel 用）", False, None),
                           "limit": ("integer", "合成次数（craft 用）", False, None),
                           "name": ("string", "方块/物品名（inspect/select_item/equip 用）", False, None),
                           "side": ("string", "left 或 right（equip/unequip 用）", False, None),
                           "count": ("integer", "数量", False, None),
                           "target": ("integer", "海龟的 rednet id（可省略，默认广播）", False, None),
                           "x": ("integer", "坐标 x（goto/dshdig/chop_log 等用）", False, None),
                           "y": ("integer", "坐标 y", False, None),
                           "z": ("integer", "坐标 z", False, None),
                           "max_steps": ("integer", "goto 的步数预算", False, None),
                           "dir": ("string", "方向（tunnel/place_row 用）", False, None),
                           "rows": ("integer", "行数（place_row 等用）", False, None),
                           "depth": ("integer", "深度（mine_column 用）", False, None),
                           "length": ("integer", "长度（tunnel 用）", False, None),
                           "dx": ("integer", "相对移动 dx", False, None),
                           "dy": ("integer", "相对移动 dy", False, None),
                           "dz": ("integer", "相对移动 dz", False, None),
                           "aim": ("number", "瞄准高度比例", False, None),
                           "walk_closer": ("boolean", "是否先走近", False, None),
                           "max": ("integer", "上限（chop_log 等用）", False, None),
                           "budget": ("integer", "预算（extend_platform 用）", False, None),
                           "wait": ("number", "等回包秒数", False, 8)},
                   long=True, passthrough=True),
    "craft": dict(desc=("让海龟合成。注意 CC 的 turtle.craft **不接受「合成什么」** —— "
                        "它合成背包里当前可合成的配方，所以正确用法是先把原料给它（例如原木→木板）。"
                        "前置条件：海龟必须装备工作台（Crafty 升级），否则会明确报错。"),
                  params={"limit": ("integer", "合成次数", False, 1)}),
    "say": dict(desc="在聊天框说话（其他玩家能看到）",
                params={"text": ("string", "内容", True)}),
    "remember": dict(desc="把一条【已核实】的事实写进长期记忆",
                     params={"key": ("string", "键", True), "value": ("string", "值", True),
                             "source": ("string", "来源（怎么核实的）", True)}),
    "done": dict(desc="目标已完成，结束本次行动",
                 params={"summary": ("string", "总结：做了什么、证据是什么", True)}),
    # ---- 脚手架：默认禁用，只有显式开启才可用（用户要求最终必须自给） ----
    "give_item": dict(desc="【脚手架】直接发物品给假人 —— 默认禁用",
                      params={"slot": ("integer", "快捷栏槽位 1~9", True),
                              "item": ("string", "物品 id", True),
                              "count": ("integer", "数量", False, 1)},
                      scaffold=True),
}

SCAFFOLD_NOTE = ("\n[已禁用] give_item 属于脚手架：用户的最终要求是假人必须自己从零获取材料。"
                 "只有显式开启 --allow-scaffold 才能用，并且用了必须登记到 docs/自给清单.md。")


def _tool_schema(name: str, spec: dict) -> dict:
    props, required = {}, []
    for pname, p in (spec.get("params") or {}).items():
        typ, desc, req = p[0], p[1], p[2]
        default = p[3] if len(p) > 3 else None
        entry = {"type": typ, "description": desc}
        if default is not None:
            entry["default"] = default
        props[pname] = entry
        if req:
            required.append(pname)
    desc = spec["desc"]
    if spec.get("danger"):
        desc += "  ⚠ 风险：%s" % spec["danger"]
    if spec.get("long"):
        desc += "  （耗时较长，调用后要耐心等回传）"
    if spec.get("scaffold"):
        desc += "  【脚手架，默认禁用】"
    return {"type": "function",
            "function": {"name": name, "description": desc,
                         "parameters": {"type": "object", "properties": props,
                                        "required": required}}}


# ★★2026-10-03：中间层的"按方块名挑工具"**整块删掉**✗★★（欠账 ② 收尾 ✓ 用户拍板 ✓）
#   ★为什么删✗★：★模组侧 `/dshdig` 现在按**游戏自己的破坏速度**挑✗★
#     （★`ItemStack#getDestroySpeed(state)`✗ —— ★那是原版自己的判断 ✗ 比这张名字表更准✓★）
#   ★为什么必须删而不是留着✗★：★留着就是**第二条口径**✗（P106 ✓）⇒
#     ★"哪件工具更快"会同时有两个答案 ✗ 而且名字表这份**必然会过期**✗（新方块进游戏就漏 ✓）
#   ★表本身仍留在文档里备查 ✗ 只是**不再参与决策**✗★（见本提交留言 ＋ §79.24 ✓）


class Skills:
    def __init__(self, ch: Channel, world: World, allow_scaffold: bool = False,
                 bot: str = "Bot", verbose: bool = True):
        self.ch = ch
        self.w = world
        self.bot = bot
        self.allow_scaffold = allow_scaffold
        self.verbose = verbose
        self.journal = Journal("actions")
        self.calls = 0

    # -- 对外接口 ------------------------------------------------------------ #

    def tools(self, exclude: tuple[str, ...] = ()) -> list[dict]:
        out = []
        for name, spec in SPEC.items():
            if name in exclude:
                continue
            if spec.get("scaffold") and not self.allow_scaffold:
                continue
            out.append(_tool_schema(name, spec))
        return out

    def help_text(self) -> str:
        lines = []
        for name, spec in SPEC.items():
            if spec.get("scaffold") and not self.allow_scaffold:
                continue
            ps = ", ".join("%s:%s" % (k, v[0]) for k, v in (spec.get("params") or {}).items())
            lines.append("  %-13s %s   (%s)" % (name, spec["desc"], ps or "无参数"))
        return "\n".join(lines)

    def run(self, name: str, args: dict | None = None, timeout: float = 180.0) -> dict:
        args = dict(args or {})
        spec = SPEC.get(name)
        if spec is None:
            return {"ok": False, "error": "没有这个技能：%s" % name}
        if spec.get("scaffold") and not self.allow_scaffold:
            return {"ok": False, "error": "技能 %s 是脚手架，已被禁用。" % name + SCAFFOLD_NOTE}
        # 补默认值
        for pname, p in (spec.get("params") or {}).items():
            if pname not in args and len(p) > 3 and p[3] is not None:
                args[pname] = p[3]
        fn = getattr(self, "s_" + name, None)
        if fn is None:
            return {"ok": False, "error": "技能 %s 已声明但没有实现（代码缺口）" % name}
        self.calls += 1
        t0 = time.time()
        # 透传型技能：**不按 SPEC 过滤参数** ✓
        # 真实事故（同一类病的第二层 ✗）：`turtle` 是把动作转发给海龟的技能 ✓
        #   而海龟的动作表有几十个、参数各不相同 ✓ → SPEC 里**永远列不全** ✗
        #   我先前只列了少数几个 ✓ → `x/y/z` 在**进入技能之前**就被丢掉了 ✗
        #   表现：海龟回报"需要 x y z 三个坐标" ✓ 而我实际发出的 payload 只剩 {wait,target} ✗
        if spec.get("passthrough"):
            call_args = dict(args)
        else:
            call_args = {k: args[k] for k in args if k in (spec.get("params") or {})}
        try:
            out = fn(**call_args)
        except BridgeError as e:
            out = {"ok": False, "error": "通道错误：%s" % e}
        except TypeError as e:
            out = {"ok": False, "error": "参数不对：%s" % e}
        except Exception as e:                     # 技能不该把异常抛给大脑
            out = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        out.setdefault("skill", name)
        out["elapsed"] = round(time.time() - t0, 2)
        self.journal.write("skill", skill=name, args=args, ok=out.get("ok"),
                           summary=out.get("evidence") or out.get("error"))
        if self.verbose:
            tag = "OK " if out.get("ok") else "FAIL"
            print("[技能 %s] %s (%ss) %s" % (tag, name, out["elapsed"],
                                             out.get("evidence") or out.get("error") or ""))
        return out

    @staticmethod
    def _r(ok: bool, evidence: str = "", **extra) -> dict:
        d = {"ok": bool(ok), "evidence": evidence}
        d.update(extra)
        return d

    # ══ ★背包守卫：任何"会接东西"的技能，入口先过它★ ═══════════════════════════
    #  用户明确要求 ✓：「把 inv_guard 接到**收割/筛矿等所有会接东西的流程**前」✗
    #  （错题本 **P19.1** ✓ 那次是用户当场指出来的 ✗ 我把"捡不起来"错解释成"站得远"✗
    #    真因是背包 36/36 全满 ✗ —— 而"满不满"**一条命令就能查到** ✓）
    #
    #  为什么**必须焊在技能入口**（而不是"调用者记得先跑一下"✗）：
    #    "记得做"在本项目的历史战绩是 **0 次生效 ✗**（绿宝石 64 个 ✗ 麦子 ✗ 砂砾两次 ✗）
    #    ⇒ 纪律要能被**机械执行**才有意义 ✓ ⇒ 写在代码里 ✓ 不写在文档里 ✗
    #
    #  ⚠ 判据分级（别把守卫自己变成新的单点故障 ✗）：
    #    · 读得到背包 ＋ 空位不够 ⇒ ★**拒绝开工**★ ✗（这就是它存在的意义 ✓）
    #    · **读不到**背包（模组没加载/假人掉线）⇒ 也**拒绝** ✗ 但**说清是"读不到"**✓
    #      —— 因为"读不到"同样意味着"接不住掉落物"✗；宁可停 ✗ 也别边干边丢 ✗（纪律⑤ ✓）
    #    · 真要绕过去：调用方传 `guard=False` ✓（显式 ✓ 有记录 ✓ 不是静默 ✓）
    def _guard(self, need: int = 2, guard: bool = True) -> dict | None:
        """放行 → None ✓ ｜ 拒绝 → 直接可返回的结果 dict ✗（调用方 `return` 它即可 ✓）"""
        if not guard:
            return None
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
            from inv_guard import ensure_free          # noqa: PLC0415
        except Exception as e:                         # 守卫缺失也要**大声** ✗ 不许静默 ✗
            return self._r(False, "拒绝开工 ✗ 背包守卫加载不了（%s: %s）"
                                  "—— 装不上守卫就不许执行「会接东西」的动作 ✓（纪律⑤ ✓）"
                           % (type(e).__name__, e))
        try:
            r = ensure_free(self.ch, bot=self.bot, need=int(need), auto=True,
                            verbose=bool(self.verbose))
        except Exception as e:
            return self._r(False, "拒绝开工 ✗ 背包守卫自己出错了（%s: %s）"
                                  "—— 宁可停 ✓ 也不在「不知道满没满」的情况下往下走 ✗"
                           % (type(e).__name__, e))
        if not r.get("ok"):
            return self._r(False, "拒绝开工 ✗ 背包守卫：%s" % (r.get("why") or "空位不足"),
                           free=r.get("free"), guard=r)
        return None

    # -- 只读技能 ------------------------------------------------------------ #

    def s_scan(self, radius: int = 6) -> dict:
        snap = self.w.survey(int(radius))
        by = snap.get("by_name") or snap.get("counts") or {}
        if not by:
            return self._r(False, "扫描没有返回方块清单（动作名/参数可能和 schema 不符）", raw=snap)
        top = sorted(((k, v) for k, v in by.items() if isinstance(v, int) and v > 0),
                     key=lambda kv: -kv[1])[:15]
        return self._r(True, "半径 %d 内主要方块：%s" % (radius, "，".join("%s×%d" % t for t in top)),
                       counts=dict(top))

    def s_verify(self, x: int, y: int, z: int) -> dict:
        d = self.ch.verify_block(int(x), int(y), int(z))
        name = d.get("name") or d.get("block") or json.dumps(d, ensure_ascii=False)
        return self._r(bool(d), "(%s,%s,%s) = %s" % (x, y, z, name), state=d)

    def s_look_block(self, reach: float = 5.0, nbt: bool = False, raw: bool = False) -> dict:
        """准星感知：假人正对着什么（= 玩家装了 Jade 之后看到的那一行）。

        ⚠ 为什么必须有它：假人没有客户端 ✗ 它**看不见**任何东西 ✗。
          过去的做法是"人先报坐标、它再去读" ✓ —— 于是"我面前是什么"这个最基本的问题
          反而答不上来 ✗（真实后果：以为面前是木板、其实是泥土 ✗；少带一把工具就走过去 ✗）。
        这条走的是服务端**真值** ✓：Pos + Rotation → 体素射线 → 第一块非空气方块 ✓。
        """
        r = self.ch.call("crosshair", {"reach": float(reach), "nbt": bool(nbt), "raw": bool(raw)},
                         timeout=30.0, allow_str=True)
        d = r.as_dict()
        hit = d.get("hit") or {}
        if not hit:
            return self._r(True, "准星 %.1f 格内没有方块（%s）" % (reach, d.get("looking_at") or "空"),
                           target=None, rotation=d.get("rotation"))
        ev = "%s @ (%s,%s,%s) 距离 %s 面 %s 工具=%s(%s)" % (
            hit.get("name"), hit.get("x"), hit.get("y"), hit.get("z"),
            hit.get("dist"), hit.get("face"), hit.get("tool") or "无",
            hit.get("tool_from") or "-")
        return self._r(True, ev, target=hit, rotation=d.get("rotation"),
                       tool=hit.get("tool"), tier=hit.get("tier"))

    # -- 移动与地形 ---------------------------------------------------------- #

    def s_goto(self, x: int, y: int, z: int, range: float = 0.4, clear: bool = False) -> dict:
        known = self.ch.action_args("walk_to") or {}
        args = {}
        for k, v in (("x", x), ("y", y), ("z", z), ("range", range), ("clear", clear)):
            if k in known:
                args[k] = v
        if not args:
            return self._r(False, "schema 里没有 walk_to 的参数信息，拒绝盲发")
        r = self.ch.call("walk_to", args, timeout=150.0, allow_str=True)
        p = self.w.pos()
        if p is None:
            return self._r(False, "走完了但查不到位置，无法验收", action=r.summary(200))
        import math
        dist = math.dist(p, (x + 0.5, y, z + 0.5))
        return self._r(dist <= 2.0, "目标 (%s,%s,%s)，实际停在 (%.1f,%.1f,%.1f)，偏差 %.2f 格"
                       % (x, y, z, p[0], p[1], p[2], dist), action=r.summary(200))

    def s_path_goto(self, x: int, y: int, z: int, timeout: float = 90.0,
                    radius: int | None = None, plan_timeout: float | None = None,
                    scan_timeout: float | None = None, dig: bool | None = None,
                    place: bool | None = None, warp: bool | None = None,
                    exact: bool | None = None) -> dict:
        """真正的寻路：A* 规划 + 逐格执行（自证 ✓ 卡住重规划 ✓ 兜底回传会如实标记 ✓）。

        `exact=true` = **GoalBlock 语义**（必须站到**那一格那一层** ✓）
          为什么要有它 ✗（真实教训 ✓ 2026-09-20 两次）：
            GoalNear 的 ±1 容差会把"**隔壁一格、低一层**"也判成已到达 ✗
            ⇒ 人要站 (4128,71,12) ✓ 实际停在 (4127,70,12) ✗ 而规划器认为"本来就在"✗
              （`steps:1, cost:0, waypoints:0` ✓ 一步不走 ✓ 外部却以为成功了 ✗）
            这类需求很常见 ✓：**站到那一格才能打到顶面**（筛矿 ✗ P16 ✓）、
              站到那一格才能放方块 ✓、站到那一格才够得着容器 ✓

        ⚠ 验收的三条纪律（都来自本项目踩过的坑 ✓）：
          1. **看世界真值** ✗：位置现读 `w.pos()` ✓ 不看动作自述 ✗
          2. **`warped=true` 不算成功** ✗ —— 那是**传送过去**的 ✓
             文档明写："**必须如实报告这次是回传的、不是走过去的** ✗"
             ⇒ 所以本技能对 warped 一律判 **ok=false** ✓
          3. `reached=false` 时把 `why`/`trace` **原文摆出来** ✗ 别只说"失败" ✓
        """
        args: dict = {"x": int(x), "y": int(y), "z": int(z), "timeout": float(timeout)}
        for k, v in (("radius", radius), ("plan_timeout", plan_timeout), ("scan_timeout", scan_timeout),
                     ("dig", dig), ("place", place), ("warp", warp), ("exact", exact)):
            if v is None:
                continue
            if k == "radius":
                args[k] = int(v)
            elif k in ("plan_timeout", "scan_timeout"):
                args[k] = float(v)
            else:
                args[k] = bool(v)
        # 客户端要等得比 Lua 的预算**久一点** ✓
        # （Lua 的 `timeout` 是**整段**预算 ✓ 之外还有规划/重规划 ✓ 兜底 tp 也要时间 ✓）
        r = self.ch.call("path_follow", args, timeout=float(timeout) + 60.0, allow_str=True)
        d = r.result if isinstance(r.result, dict) else {}
        if not d:
            return self._r(False, "path_follow 没有返回表（多半是 Lua 侧报错）：%s" % r.summary(300))
        reached = bool(d.get("reached"))
        warped = bool(d.get("warped"))
        why = d.get("why") or ""
        p = self.w.pos()
        # ⚠ 收尾判据**与请求口径一致** ✗（真实教训 P10 ✓）：
        #   exact ⇒ 容差 0（那一格那一层 ✓）；否则 GoalNear 容差 1 ✓
        tol = 0 if exact else 1
        if p:
            dx, dz = p[0] - (x + 0.5), p[2] - (z + 0.5)
            dist = (dx * dx + dz * dz) ** 0.5
            cells_off = max(abs(math.floor(p[0]) - int(x)), abs(math.floor(p[2]) - int(z)))
            dy_off = abs(math.floor(p[1]) - int(y))
        else:
            dist, cells_off, dy_off = 999.0, 99, 99
        # ★ 判据：**到了 ✓ 不是传送过去的 ✓ 真的在目标格附近 ✓（含 y ✓）**（三条都要 ✓）
        ok = reached and (not warped) and cells_off <= tol and dy_off <= tol
        ev = "寻路→(%s,%s,%s%s)：reached=%s warped=%s 途经点=%s 重规划=%s 用时=%ss" % (
            x, y, z, " exact" if exact else "", reached, warped,
            d.get("waypoints"), d.get("replans"), d.get("seconds"))
        if p:
            ev += " ｜ 实际停在 (%.1f,%.1f,%.1f) 水平偏差 %.2f 格（格差 %d / y差 %d）" % (
                p[0], p[1], p[2], dist, cells_off, dy_off)
        if warped:
            ev = ("⚠ **这是传送过去的，不是走过去的** ✗（兜底生效 ✓ 但不算寻路能力 ✗）" + ev)
        if (not reached) and why:
            ev += " ｜ 原因：%s" % why
        at = d.get("at") or ({"x": p[0], "y": p[1], "z": p[2]} if p else None)
        return self._r(ok, ev, at=at, reached=reached, warped=warped, why=why,
                       waypoints=d.get("waypoints"), replans=d.get("replans"),
                       trace=d.get("trace"))

    def s_look(self, x: float, y: float, z: float) -> dict:
        ok = self.ch.verify_command_ok("player %s look at %s %s %s" % (self.bot, x, y, z))
        return self._r(ok, "已转向 (%s,%s,%s)" % (x, y, z))

    def s_locate(self, timeout: float = 2) -> dict:
        known = self.ch.action_args("locate") or {}
        args = {"timeout": timeout} if "timeout" in known else {}
        r = self.ch.call("locate", args, timeout=40.0, allow_str=True)
        d = r.result
        shown = json.dumps(d, ensure_ascii=False)[:200] if not isinstance(d, str) else d[:200]
        return self._r(bool(r.ok), "GPS 定位：%s" % shown)

    # -- 挖掘与放置 ---------------------------------------------------------- #

    def s_dig(self, x: int, y: int, z: int) -> dict:
        before = self.ch.verify_block(int(x), int(y), int(z))
        bname = str(before.get("name", "?"))
        # ★★2026-10-03 改走**模组侧**✗★★（欠账 ② 收尾 ✓ 用户拍板：往模组侧并 ✗ Lua `dig_at` 冻结 ✓）
        #   ★★"按方块名挑工具"**删掉**✗★★：★模组侧已经按**游戏自己的破坏速度**挑✗★
        #     （★`ItemStack#getDestroySpeed(state)` ✗ 比名字匹配更准 ✓ 也不怕别的模组加工具✓★）
        #   ★判"成没成"**照旧只看世界真值**✗★（★下面 `verify_block` 前后各读一次 ✓ 不听自述 ✓ P164✓★）
        try:
            _rt = self.ch.cmd("execute as %s at %s run dshdig %d %d %d"
                              % (self.bot, self.bot, int(x), int(y), int(z)),
                              timeout=120.0, allow_str=True)
            _txt = str(_rt.text() or "")
        except Exception as _e:
            _txt = "ERR:%s" % type(_e).__name__
        after = self.ch.verify_block(int(x), int(y), int(z))
        aname = after.get("name", "?")
        gone = aname in ("air", "minecraft:air", "cave_air", "void_air")
        return self._r(gone, "(%s,%s,%s)：%s → %s（模组回执 %s）"
                       % (x, y, z, bname, aname, _txt.strip()[:80]),
                       before=bname, after=aname)

    def s_place(self, x: int, y: int, z: int, item: str | None = None) -> dict:
        if item:
            e = self.s_equip(item)
            if not e.get("ok"):
                return e
        known = self.ch.action_args("place_adjacent") or {}
        args = {k: v for k, v in (("x", int(x)), ("y", int(y)), ("z", int(z))) if k in known}
        if not args:
            return self._r(False, "schema 里没有 place_adjacent 的参数信息，拒绝盲发")
        r = self.ch.call("place_adjacent", args, timeout=90.0, allow_str=True)
        d = {}
        try:
            d = r.as_dict()
        except BridgeError:
            pass
        landed = d.get("landed") or d.get("pos") or d.get("placed")
        # 真正的验收：动作报告落点后，还要去查那个格子到底有没有东西
        if isinstance(landed, dict) and {"x", "y", "z"} <= set(landed):
            st = self.ch.verify_block(int(landed["x"]), int(landed["y"]), int(landed["z"]))
            nm = st.get("name", "?")
            return self._r(nm not in ("air", "minecraft:air"),
                           "落点 (%s,%s,%s) = %s" % (landed.get("x"), landed.get("y"),
                                                     landed.get("z"), nm), state=st)
        return self._r(bool(d.get("ok", r.ok)),
                       "动作自述落点=%s（未拿到坐标，无法独立复核）" % json.dumps(landed, ensure_ascii=False),
                       action=r.summary(250))

    def s_sneak_place(self, pieces: int = 1) -> dict:
        known = self.ch.action_args("sneak_place") or {}
        args = {k: v for k, v in (("pieces", int(pieces)), ("count", int(pieces))) if k in known}
        r = self.ch.call("sneak_place", args, timeout=180.0, allow_str=True)
        p = self.w.pos()
        return self._r(r.ok, "贴边放置结束，现在在 %s（动作自述：%s）"
                       % (("(%.1f,%.1f,%.1f)" % p) if p else "未知位置", r.summary(200)))

    # -- 采集与加工 ---------------------------------------------------------- #

    def s_harvest(self, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int,
                  replant: bool = True) -> dict:
        """★作业：收割 → 补种★（实现在 `agent/jobs.py` ✓ 这里只是把它接进技能层 ✓）

        为什么要单独一个作业 ✗（而不是"让大脑自己拼 chop 式的小动作"✗）：
          "收 + 补种 + 自证 + 背包守卫"这四件事**必须一起发生** ✗
          —— 少任何一件都会留下一个**看不见的坏结果** ✗：
            少守卫 ⇒ 满包时收成掉地上 5 分钟消失 ✗（P19.1 / M4 ✓ 丢过 30 株 ✗）
            少"走到跟前" ⇒ 收成够不着 ✗
            少补种 ⇒ 把田收秃 ✗（不可持续 ✗）
            少自证 ⇒ 不知道到底收了几株 ✗（"完成"两个字不算证据 ✗）
          ⇒ 打包成**一条作业** ✓ 让"忘记"这件事**不可能发生** ✓✓
        """
        from jobs import harvest_and_replant           # noqa: PLC0415（作业层 ✓）
        box = {"x0": int(x0), "y0": int(y0), "z0": int(z0),
               "x1": int(x1), "y1": int(y1), "z1": int(z1)}
        r = harvest_and_replant(self.ch, box, bot=self.bot, replant=bool(replant),
                                verbose=bool(self.verbose))
        ev = ("作业 harvest：%s" % r.get("why", ""))
        if r.get("failed"):
            ev += " ｜ 失败 %d 处 ✗（前 3：%s）" % (
                len(r["failed"]), json.dumps(r["failed"][:3], ensure_ascii=False)[:200])
        return self._r(bool(r.get("ok")), ev, job=r)

    def s_chop(self, max_logs: int = 64) -> dict:
        # ★ 砍树会往背包里塞**一堆原木** ✗ ⇒ 入口先过背包守卫 ✓（见 _guard 注释 ✓ P19.1 ✓）
        g = self._guard(need=2)
        if g is not None:
            return g
        known = self.ch.action_args("chop_tree") or {}
        args = {k: v for k, v in (("max_logs", int(max_logs)), ("max", int(max_logs))) if k in known}
        before = self.w.counts()
        r = self.ch.call("chop_tree", args, timeout=240.0, allow_str=True)
        after = self.w.counts()
        gained = {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after)}
        gained = {k: v for k, v in gained.items() if v > 0}
        wood = {k: v for k, v in gained.items() if "_log" in k or "planks" in k}
        return self._r(bool(wood), "砍树后新增：%s（动作自述 %s）"
                       % (json.dumps(gained, ensure_ascii=False) or "无",
                          "成功" if r.ok else "失败"), gained=gained)

    def s_sift_at(self, x: int, y: int, z: int, uses: int = 16,
                  item: str = "minecraft:gravel") -> dict:
        """★作业：筛矿★（实现在 `agent/jobs.py` 的 `sift_job` ✓）

        为什么单独一个作业 ✗：筛矿要"守卫 ✓ 前置检查 ✓ 走位 ✓ 指名面 ✓ 逐下判真值 ✓"**一起发生** ✗
        —— 少任何一件都会留下**看不见的坏结果** ✗（尤其"打侧面时静默无效"✗ P16 ✓）

        ⚠ `item` 必须能改 ✗（我第一版写死 gravel ✗ 一查配方就错了 ✓）：
          Ex Deorum 里**泥土也能筛** ✓ 而且**只有泥土**出 `stone_pebble`
          （4 个 → **原石** ✓ 原石被锤子砸 → **沙砾** ✓ 沙砾再筛 → **矿物碎块** ✓）
        """
        from jobs import sift_job                        # noqa: PLC0415
        r = sift_job(self.ch, int(x), int(y), int(z), uses=int(uses), bot=self.bot,
                     item=str(item), verbose=bool(self.verbose))
        ev = "作业 sift_at：%s" % r.get("why", "")
        if r.get("failed"):
            ev += " ｜ 失败 %d 处 ✗（前 2：%s）" % (
                len(r["failed"]), json.dumps(r["failed"][:2], ensure_ascii=False)[:180])
        return self._r(bool(r.get("ok")), ev, job=r)

    def s_sift(self, x: int, y: int, z: int, item: str = "minecraft:gravel",
               count: int = 16, seconds: float = 12, reach: float = 4.0) -> dict:
        """筛矿。**动手前先在客户端侧算一次距离** ✓

        为什么要有客户端侧的检查（真实事故 ✓）：
          假人离筛子 5~7 格时就调了 sift ✗ → 右键打在地面上 ✓
          → 把整组砂砾放到地上 ✗ 还堆成 2 格高把假人自己埋住 ✗（后来手工清理 ✓）
          Lua 侧现在也会拒绝 ✓ 但"能不发就不发"更省一次往返 ✓ 失败原因也更好解释 ✓
        """
        # ★ 筛矿**出碎块** ⇒ 入口先过背包守卫 ✓（P19.1 ✓ 用户明确要求 ✓）
        #   ⚠ 顺序讲究：**先看守卫、再看站位** ✗ ——
        #     背包满时"站得再对"也没用 ✗（产出接不住 ✓ 那才是真正的失败点 ✓）
        g = self._guard(need=2)
        if g is not None:
            return g
        p = self.w.pos()
        if p:
            import math
            dist = math.dist(p, (x + 0.5, y + 0.5, z + 0.5))
            if dist > reach:
                return self._r(False,
                               "拒绝执行：假人在 (%.1f,%.1f,%.1f)，离筛子 (%d,%d,%d) 有 %.2f 格 ✗"
                               "（上限 %.1f）→ 先走到它旁边再筛；离得远时右键会打在地面上、"
                               "把手里物品放到地上 ✗"
                               % (p[0], p[1], p[2], x, y, z, dist, reach), dist=dist)
        # ══════════════════════════════════════════════════════════════════════
        # ★ 开筛前的硬检查：**射线必须命中筛子的 `up` 面** ✗（2026-09-20 新增 ✓）
        #
        # 真实事故（错题本 **P16** ✓ 最贵的那一类 ✗）：
        #   站在**同层或更低**的位置打筛子的**侧面**时 ⇒ `use` **每一步都回 success:true** ✓
        #   而筛子 NBT **一个字节都不变** ✗（`progress` / `contents` 原样 ✓）
        #   ⇒ 只看指令回显会得出"筛了但没掉落"✗ 这个完全错误的结论 ✗
        #   实测对照 ✓：命中 `面 up` ⇒ `progress 0.8 → 0.0` ＋ `contents` 消失 ＋ 出碎块 ✓
        #
        # ⚠ 为什么要在这里拦 ✗：光做"距离检查"是**不够的** ✗
        #   （原来的 reach 检查只保证"离得近"✓ 保证不了"打得到顶面"✗ —— 本轮就被它放过去了 ✗）
        # ⚠ 也让"失败大声"✓：宁可**明确拒绝**并告诉调用方怎么站位 ✓
        #   也不要发出一串"成功但什么都没发生"的右键 ✗
        # ══════════════════════════════════════════════════════════════════════
        try:
            pre = self.ch.call("crosshair", {}, timeout=30.0, allow_str=True)
            pd = pre.as_dict() if isinstance(pre.result, dict) else {}
        except BridgeError:
            pd = {}
        hit = pd.get("hit") or {}
        hname = str(hit.get("name") or "")
        hface = str(hit.get("face") or "")
        if pd:                      # 拿得到准星信息才检查 ✓（拿不到就不拦 ✗ 别把功能卡死 ✗）
            if ("sieve" not in hname) or (hface != "up"):
                return self._r(
                    False,
                    "拒绝开筛 ✗ 准星现在打在 **%s** @ 面 **%s** ✗（距离 %s）"
                    "—— 必须命中筛子的 **up** 面 ✓"
                    "（打侧面时筛子**完全不动、而且一声不响** ✗ 见错题本 P16 ✓）"
                    "⇒ 站到**比筛子高**的位置，从上方把射线射进碗里 ✓"
                    "（本轮的可行站位：站到东侧台阶上，脚在 y+0.5，瞄 筛子中心 y+0.15 ✓）"
                    % (hname or "（空气）", hface or "?", pd.get("looking_at") or "?"),
                    looking_at=pd.get("looking_at"), hit=hit)
        known = self.ch.action_args("sift") or {}
        args = {"x": int(x), "y": int(y), "z": int(z), "item": item, "count": int(count)}
        if "seconds" in known:
            args["seconds"] = float(seconds)
        if "reach" in known:
            args["reach"] = float(reach)
        if known:
            args = {k: v for k, v in args.items() if k in known}
        before = self.w.counts()
        r = self.ch.call("sift", args, timeout=float(seconds) + 150.0, allow_str=True)
        after = self.w.counts()
        gained = {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after)}
        gained = {k: v for k, v in gained.items() if v > 0}
        return self._r(bool(gained), "筛矿 %ss 后新增：%s" % (seconds, json.dumps(gained, ensure_ascii=False)),
                       gained=gained)

    def s_equip(self, item: str) -> dict:
        known = self.ch.action_args("hold_item") or {}
        args = {}
        if "item" in known:
            args["item"] = item
        if "bot" in known:
            args["bot"] = self.bot
        r = self.ch.call("hold_item", args, timeout=60.0, allow_str=True)
        held = self.w.held()
        want = item.split(":")[-1]
        ok = bool(held) and (want in held)
        return self._r(ok, "主手现在是 %s（想拿的是 %s）" % (held, item), held=held)

    def s_install_mesh(self, x: int, y: int, z: int) -> dict:
        r = self.ch.call("install_mesh", {"x": int(x), "y": int(y), "z": int(z)},
                         timeout=60.0, allow_str=True)
        st = self.ch.verify_block(int(x), int(y), int(z))
        txt = json.dumps(st, ensure_ascii=False)
        return self._r("mesh" in txt.lower(), "筛子 (%s,%s,%s) 状态含 mesh：%s"
                       % (x, y, z, "是" if "mesh" in txt.lower() else "否"), state=st)

    # -- 战斗与生存 ---------------------------------------------------------- #

    def s_attack(self, radius: int = 12, seconds: float = 10) -> dict:
        ents = self.w.entities(radius=int(radius))
        foes = [e for e in ents if e.get("hostile")]
        if not foes:
            return self._r(True, "半径 %d 内没有敌对生物（附近实体：%s）"
                           % (radius, [e["id"] for e in ents] or "无"))
        target = foes[0]
        if target.get("pos"):
            self.s_look(target["pos"][0], target["pos"][1] + 1.0, target["pos"][2])
        # Carpet: attack continuous 会持续攻击；用 stop 结束
        self.ch.cmd_async("player %s attack continuous" % self.bot)
        t0 = time.time()
        killed = False
        while time.time() - t0 < float(seconds):
            time.sleep(1.5)
            now = [e for e in self.w.entities(radius=int(radius)) if e.get("hostile")]
            if not now:
                killed = True
                break
            v = self.w.vitals()
            if v.get("health") is not None and v["health"] <= 6:
                break
        self.ch.cmd_async("player %s stop" % self.bot)
        v = self.w.vitals()
        return self._r(killed, "目标 %s：%s；自身生命 %s"
                       % (target["id"], "已消灭" if killed else "未消灭（已停手）", v.get("health")))

    def s_flee(self, seconds: float = 3) -> dict:
        p0 = self.w.pos()
        self.ch.cmd_async("player %s move backward continuous" % self.bot)
        time.sleep(float(seconds))
        self.ch.cmd_async("player %s stopMovement" % self.bot)
        p1 = self.w.pos()
        moved = None
        if p0 and p1:
            import math
            moved = round(math.dist(p0, p1), 2)
        return self._r(bool(moved and moved > 1.0), "后退了 %s 格" % moved)

    def s_eat(self, item: str | None = None) -> dict:
        if item:
            e = self.s_equip(item)
            if not e.get("ok"):
                return e
        before = self.w.vitals()
        # 吃东西 = 主手拿食物 + 长按右键。假人没有客户端界面，靠 use 持续触发。
        self.ch.cmd_async("player %s use continuous" % self.bot)
        time.sleep(2.5)
        self.ch.cmd_async("player %s stop" % self.bot)
        after = self.w.vitals()
        f0, f1 = before.get("food"), after.get("food")
        ok = bool(f0 is not None and f1 is not None and f1 > f0)
        return self._r(ok, "饥饿 %s → %s（若没变，多半是主手没拿食物：假人点不开背包界面）" % (f0, f1))

    # -- 协作与交流 ---------------------------------------------------------- #

    def s_craft_legacy_unused(self, item: str, count: int = 1) -> dict:
        """合成必须借海龟：Carpet 的 /player 没有 craft，假人也没有合成界面。"""
        for cand in ("turtle_craft", "craft_item", "remote_craft"):
            known = self.ch.action_args(cand)
            if known is not None:
                args = {}
                if "item" in known:
                    args["item"] = item
                if "count" in known:
                    args["count"] = int(count)
                r = self.ch.call(cand, args, timeout=120.0, allow_str=True)
                after = self.w.counts()
                got = after.get(item, after.get("minecraft:" + item, 0))
                return self._r(got > 0, "合成 %s×%d：背包里现有 %d（动作自述 %s）"
                               % (item, count, got, "成功" if r.ok else "失败"),
                               action=r.summary(250))
        return self._r(False, "还没有接通海龟合成：schema 里找不到 turtle_craft/craft_item。"
                              "需要在 cc0 上加一个把合成请求转发给海龟的动作（见 docs/当前阶段-状态与交接.md）")

    def s_find_block(self, name: str, radius: int = 12,
                     x: int | None = None, y: int | None = None, z: int | None = None) -> dict:
        """找方块在哪。只筛一类方块，所以可以用大半径（否则全量统计会很慢）。

        `x/y/z` 可选：指定**扫描中心** ✓ —— 因为 Lua 把半径钳到 12 ✗
        想搜更大范围就只能**换中心多扫几次** ✓（例如沿岛扫一圈找工作台 ✓）
        """
        center = (x, y, z) if None not in (x, y, z) else None
        snap = self.w.survey(int(radius), only=name, center=center)
        if not snap:
            return self._r(False, "扫描没有返回结果（动作名/参数可能和 schema 不符）")
        by = snap.get("by_name") or snap.get("counts") or {}
        hits = {k: v for k, v in by.items() if isinstance(v, int) and v > 0}
        # 有些实现会把坐标清单也带回来，有就一并交出去，别浪费
        spots = snap.get("list") or snap.get("blocks") or snap.get("positions") or []
        where = ("中心 (%s,%s,%s) " % center) if center else ""
        if not hits and not spots:
            return self._r(True, "%s半径 %d 内没有 %s" % (where, radius, name), raw=snap)
        shown = json.dumps(spots[:8], ensure_ascii=False) if spots else "（该动作只回数量、不回坐标）"
        return self._r(True, "%s半径 %d 内 %s：%s；位置：%s"
                       % (where, radius, name, json.dumps(hits, ensure_ascii=False), shown),
                       counts=hits, spots=spots[:50] if isinstance(spots, list) else [],
                       raw_keys=sorted(snap.keys()))

    # ══ 【遗留】海龟技能（2026-09-19 标记 ✗）═══════════════════════════════════
    # 用户定的方向 ✓：「**cc0 老是出问题就慢慢用模组去替代掉 CC 电脑的作用**」✓
    # ★ **主线已经不需要它了** ✗ —— 它的每一件活儿模组都能干了 ✓（详见
    #   `docs/模组-容器存取与假人手.md` §8 的对照表 ✓）：
    #     对着方块用物品（筛矿 ✗）⇒ `/dshuse` ✓ ｜ 合成 ⇒ `/dshcraft` ✓
    #     容器 / 背包 ⇒ `/dshbox` `/dshslot` `/dshinv` ✓ ｜ 精确走位 ⇒ `path_goto exact` ✓
    #     说话 / 状态 ⇒ `/dshsay` `/dshstats` ✓ ｜ 读方块 / 扫地形 ⇒ cmd0 的桥接动作 ✓
    # ⚠ 而且这条路本身**不可靠** ✗：cc0 每经历一次世界重启都会把自己搞成 0 字节 ✗（错题本 P18 ✓）
    # ⇒ 新流程**不要再依赖它** ✗；保留它只为"旧账排查"与"用户想看海龟"✓
    def s_turtle(self, cmd: str, who: str | None = None, **kw) -> dict:
        """在指定计算机上执行原生命令（默认转发给海龟）。

        为什么透传而不是给每个动作写一个技能：海龟的动作表有 39 个，
        逐个包装既没必要也会很快过期；透传 + 一个"动作名"参数就够了。
        参数名按 schema 过滤，所以拼错了会被拦住（不会静默变成"没传参数"）。

        who=cc0/cmd0 时直接在该计算机上执行（例如 cc0 的 inv_man 能替假人看箱子 ——
        假人自己点不开容器界面）。
        """
        target = who or "turtle"
        payload = {k: v for k, v in kw.items() if v is not None}
        if target in ("cc0", "cmd0"):
            ch = self._channel_for(target)
            if ch.action_args(cmd) is None:
                return self._r(False, "计算机 %s 上没有动作 %s" % (target, cmd))
            payload = {k: v for k, v in payload.items() if k in (ch.action_args(cmd) or {})}
            r = ch.call(cmd, payload, timeout=120.0, allow_str=True)
            d = {}
            try:
                d = r.as_dict()
            except BridgeError:
                d = {"raw": r.result}
            return self._r(bool(r.ok), "%s.%s → %s" % (target, cmd, json.dumps(d, ensure_ascii=False)[:500]),
                           raw=d)

        # 转给海龟：**不要走 `broadcast_cmd`** ✗（这是我改过的一处真 bug ✓）
        #   病根：`broadcast_cmd` 的 schema 只有 cmd/target/wait ✓
        #        我却拿它去过滤参数 ✗ → `x`/`y`/`z`/`max_steps` 这类**静默消失** ✗✓
        #        （结果就是"指令发成功了、海龟却没按坐标动" ✗ 极难查 ✓）
        #   正解：用 cc0 的**通用路由** —— `args.target` 会让 cc0 先把整条指令转发给海龟 ✓
        #        而 `goto` 这类动作**本来就不在 cc0 的动作表里** ✓ 所以这里必须**跳过动作表检查**
        #        并且**不做 schema 过滤**（schema 属于目标机器 ✓ 不属于中转机 ✓）
        router = self._channel_for("cc0")
        tid = payload.pop("turtle", None) or payload.pop("id", None) or 1
        payload["target"] = tid
        wait = float(kw.get("wait") or 60)
        with router._lock:                       # 与其它调用互斥 ✓ 同一台中转机串行 ✓
            cid = router.send(cmd, payload, note="turtle-forward")
            try:
                r = router.wait(cid, timeout=wait + 120.0, cmd=cmd)
            except BridgeTimeout as e:
                return self._r(False, "海龟未在期限内回报：%s（它多半正在跑长作业 ✓ "
                                      "用 py tools/cc_logs.py 1 看它的磁盘日志更可靠 ✓）" % e)
        d = {}
        try:
            d = r.as_dict()
        except BridgeError:
            d = {"raw": r.result}
        text = json.dumps(d, ensure_ascii=False)
        if isinstance(d.get("raw"), str):
            # 中转层的错误信息（例如"海龟无响应"/"未知指令"）→ 原样暴露 ✓ 不要吞 ✓
            return self._r(False, "海龟 %s 未执行：%s" % (cmd, d["raw"][:300]), raw=d)
        # ⚠ 升级槽是"挖得动什么"的**唯一决定因素** ✓（2026-09-18 血的教训 ✓）：
        #   CC:Tweaked 的海龟用**升级槽里的工具**挖 ✗ 不是背包里的 ✗
        #   （`turtle.dig` → `TurtleToolCommand` → 取 left/right 升级 ✓；官方文档：
        #     dig "requires a turtle tool capable of breaking the block" ✓）
        #   而 worker 里读升级槽用的 `turtle.getEquippedLeft/Right` 是 **1.116+** 才有的 API ✗
        #   → ATM9 这台没有 → status 里两项为空 ✓ **静默** ✓（这正是当初查不出根因的原因 ✓）
        #   ⇒ 改用**世界真值**：海龟的方块 NBT 里就有 LeftUpgrade / RightUpgrade ✓
        #     位置取它自己回报的 pos ✓ 再去问 cmd0 要 NBT ✓（"世界才是证据"的又一例 ✓）
        # ⚠ 回传"信封"形状不止一种 ✗（同一类坑今天踩了两次 ✓）：
        #   这里 `d` **就是** 结果表本身（channel.Result.as_dict() 已经把 result 剥出来了 ✓）
        #   而不是 {"result": {...}} ✗ —— 所以判据是 `d.get("pos")` ✓ 不是 `d["raw"]["pos"]` ✗
        if cmd == "status" and isinstance(d, dict) and d.get("pos"):
            up = self._turtle_upgrades(d.get("pos"))
            if up:
                d.update(up)
                text = json.dumps(d, ensure_ascii=False)
        return self._r(bool(r.ok), "海龟 %s → %s" % (cmd, text[:400]), raw=d)

    def _turtle_upgrades(self, pos) -> dict:
        """用方块 NBT 读海龟的升级槽（不在世界里就返回空表 ✓ 静默不报错 ✓）。"""
        import re
        if not isinstance(pos, dict) or pos.get("x") is None:
            return {}
        try:
            r = self._channel_for("cmd0").cmd(
                "data get block %d %d %d" % (int(pos["x"]), int(pos["y"]), int(pos["z"])),
                allow_str=True, timeout=20.0)
        except BridgeError:
            return {}
        txt = " ".join(r.lines())
        out = {}
        for key, nbtkey in (("left_upgrade", "LeftUpgrade"), ("right_upgrade", "RightUpgrade")):
            m = re.search(nbtkey + r':\s*"([^"]+)"', txt)
            if m:
                out[key] = m.group(1)
        out.setdefault("left_upgrade", None)
        out.setdefault("right_upgrade", None)
        m = re.search(r"Fuel:\s*(\d+)", txt)
        if m:
            out["fuel"] = int(m.group(1))
        # 挖得动什么的**一句话结论**（比让人自己看两个 id 有用得多 ✓）
        tools = [x for x in (out.get("left_upgrade"), out.get("right_upgrade"))
                 if x and ("pickaxe" in x or "axe" in x or "shovel" in x or "sword" in x)]
        out["dig_tools"] = tools
        out["can_dig"] = bool(tools)
        return out

    def s_craft(self, limit: int = 1) -> dict:
        return self.s_turtle("craft", limit=int(limit))

    def _channel_for(self, who: str) -> Channel:
        if who == self.ch.who:
            return self.ch
        if getattr(self, "_chans", None) is None:
            self._chans = {}
        if who not in self._chans:
            self._chans[who] = Channel(who, verbose=self.verbose)
        return self._chans[who]

    def s_say(self, text: str) -> dict:
        """说话。

        坑：Lua 的 say 动作依赖 **Chat Box 外设**，而它只挂在 cc0 上（cmd0 没有）✓
        所以先说 → 失败了就换 cc0 说 → 再失败才退回 tellraw 指令。
        """
        text = str(text)
        for ch in ([self.ch] + ([self._cc0_channel()] if self.ch.who != "cc0" else [])):
            if ch.action_args("say") is None:
                continue
            try:
                r = ch.call("say", {"text": text}, timeout=45.0, allow_str=True)
                if r.ok:
                    return self._r(True, "说了（经 %s）：%s" % (ch.who, text))
            except BridgeError:
                pass
        payload = json.dumps([{"text": "<%s> " % self.bot, "color": "aqua"},
                              {"text": text}], ensure_ascii=False)
        ok = self.ch.verify_command_ok("tellraw @a %s" % payload)
        if not ok:
            ok = self.ch.verify_command_ok("say [%s] %s" % (self.bot, text))
        return self._r(ok, "说了（经 tellraw 兜底）：%s" % text)

    def _cc0_channel(self) -> Channel:
        if getattr(self, "_cc0", None) is None:
            self._cc0 = Channel("cc0", verbose=self.verbose)
        return self._cc0

    def s_remember(self, key: str, value: str, source: str) -> dict:
        from memory import Facts
        Facts().add(key, value, source)
        return self._r(True, "已记住 %s = %s" % (key, value))

    def s_done(self, summary: str) -> dict:
        return self._r(True, "目标完成：%s" % summary, finished=True)

    # -- 容器存取（dshbridge 模组 ✓ 走 Forge 的 IItemHandler 能力 ✓）---------- #
    #
    # ★ 一个必须记住的细节 ✗（先读代码再写包裹 ✓ 否则第一次调用必炸 ✗）：
    #   `/dshbox` 的三个子命令都作用在**执行者自己**身上 ✓
    #   —— 模组里 `take` / `put` 用的是 `src.getPlayerOrException()` ✓
    #   ⇒ 直接由 cmd0 发 `/dshbox take …` ⇒ 命令源**不是玩家** ✗
    #     那一句会抛 `CommandSyntaxException` ✗ 而回传只有一句看不懂的错 ✗
    #   ⇒ 必须套一层 `execute as Bot at Bot run …` ✓✓
    #     （`as` 换执行者 ✓ `at` 把位置也带过去 ✓ 本来 `pos` 参数是绝对的 ✓ 但保持一致更难出错 ✓）
    BOX = "execute as {bot} at {bot} run dshbox {op}"

    # ⚠⚠ 判据**只能用 ASCII** ✗（2026-09-20 实测 ✓ 这是本轮踩到的新坑 ✓）
    #   现象 ✓：`/dshbox` 的中文回执走 CC 命令通道回来时**全变成 `?`** ✗
    #     例：`dshbox peek 4122, 71, 3 ? 132 ?? ? 0 ? / 0 ?`
    #     （对应原文 "…共 132 格：⇒ 0 种 / 0 个" ✓ 数字与 ASCII 全在 ✓ 中文全丢 ✗）
    #   这是错题本 **A6**（CC 终端显示不了中文 ✗）的**第二次**发作 ✓
    #     —— 上一次的结论是"每个分支都写 console.info"✓ 这次要补一条更硬的规矩 ✓：
    #   ⇒ **凡是"要被程序解析"的回执，一律只用 ASCII** ✗
    #   于是这里改成认**ASCII 前缀**：
    #     * 成功 = `dshbox peek/take/put …` ✓
    #     * 失败 = `dshbox: …`（带冒号 ✓ 不带动作名 ✓）
    #   ⚠ 我第一版写的是 `"✗" not in txt` ✗ —— 那个字符**永远不会出现** ✗
    #     于是"失败"会被判成"成功" ✓ 典型的**静默假阳性** ✗（最贵的一类 ✗）
    BOX_FAIL = "dshbox:"

    @staticmethod
    def _box_ok(txt: str, op: str) -> bool:
        """模组那条回执是不是"成功"那一支（只认 ASCII ✓ 见上面的注释 ✓）"""
        s = (txt or "").strip()
        return s.startswith("dshbox " + op)

    def _dshbox(self, op: str, x, y, z, item=None, count=None) -> Result:
        text = "%d %d %d" % (int(x), int(y), int(z))
        if item:
            # ★ 物品名**必须加引号** ✗（2026-09-20 实测 ✓ 第一版就栽在这里 ✗）
            #   模组用的是 Brigadier 的 `StringArgumentType.string()` ✓
            #   而它的"不带引号"分支只允许 `[0-9A-Za-z_.+-]` ✗ —— **冒号不在其中** ✗
            #   ⇒ `minecraft:flint` 会直接被判"参数不对"✗
            #     回执长这样 ✓：`... minecraft:flint 3<--[??]`（箭头指着那个参数 ✓）
            #   注意：**回执是中文的 ⇒ 会变成 `?`** ✗（见上面 ASCII 那段注释 ✓）
            #   ⇒ 光看回执**根本看不出**是"冒号"的问题 ✗ —— 必须自己知道 Brigadier 这条规矩 ✓
            text += ' "%s"' % str(item)
            # ⚠ 数量只跟在**物品名之后** ✓（模组的参数顺序就是 pos → item → count ✓）
            if count is not None:
                text += " %d" % int(count)
        elif count is not None:
            # 只给数量不给物品 = 模组那边没有这个位置参数 ✗ ⇒ 明说，别静默丢掉 ✗
            return self.ch.cmd("say dshbox: count needs item too", allow_str=True)
        return self.ch.cmd(self.BOX.format(bot=self.bot, op=op) + " " + text,
                           timeout=60.0, allow_str=True)

    def s_box_peek(self, x: int, y: int, z: int) -> dict:
        r = self._dshbox("peek", x, y, z)
        txt = (r.text() or r.summary(300)).strip()
        ok = self._box_ok(txt, "peek")
        # 顺手把 `[槽位]物品x数量` 抠出来 ✓（全 ASCII ✓ 中文丢了也不影响 ✓）
        items = [{"slot": int(m.group(1)), "item": m.group(2), "count": int(m.group(3))}
                 for m in re.finditer(r"\[(\d+)\]([A-Za-z0-9_:.\-]+)x(\d+)", txt)]
        ev = txt[:400] if txt else "（没有任何回执 ✗ 模组没加载？还是坐标不是容器？）"
        if not ok and self.BOX_FAIL in txt:
            ev = "容器读取失败：" + txt[:400]
        return self._r(ok, ev, items=items, reply=txt)

    def s_box_take(self, x: int, y: int, z: int, item: str | None = None,
                   count: int | None = None) -> dict:
        # ★ 取物**就是"接东西"** ✗ ⇒ 入口先过背包守卫 ✓（P19.1 ✓）
        #   真因记录 ✓：满包时拾取**根本不会发生** ✗ ⇒ 模组会如实回"放不下、已原样退回"✓
        #   ⇒ 与其让它退回来（白跑一趟 ✗）不如**先把格子腾出来** ✓
        g = self._guard(need=1)
        if g is not None:
            return g
        before = self.w.counts()
        r = self._dshbox("take", x, y, z, item, count)
        txt = (r.text() or r.summary(300)).strip()
        after = self.w.counts()
        # ★ 验收要**看背包真的有变化** ✓ 不能只听它说"搬了 N 个"✗（回传会说谎 ✓ 背包不会 ✓）
        gained = {k: after.get(k, 0) - before.get(k, 0)
                  for k in set(list(before) + list(after))
                  if after.get(k, 0) - before.get(k, 0) > 0}
        failed = self.BOX_FAIL in txt            # 模组抱怨了（多半是"背包放不下 ✗ 已原样退回"✓）
        # ⚠ 判"成没成"**以背包为准** ✓ 不以那句话为准 ✗ ——但"只搬了一部分"要如实标出来 ✓
        ok = bool(gained)
        ev = "取物回执：%s" % (txt[:220] or "（无回执 ✗）")
        ev += " ｜ 背包实增：%s" % ("，".join("%s×%d" % t for t in gained.items()) if gained else "（没有变化 ✗）")
        if failed and gained:
            ev += " ｜ ⚠ 模组报了不满 ⇒ **只搬了一部分** ✓（余量已按设计退回容器 ✓）"
        return self._r(ok, ev, gained=gained, partial=failed, reply=txt)

    def s_box_put(self, x: int, y: int, z: int, item: str | None = None,
                  count: int | None = None) -> dict:
        before = self.w.counts()
        r = self._dshbox("put", x, y, z, item, count)
        txt = (r.text() or r.summary(300)).strip()
        after = self.w.counts()
        lost = {k: before[k] - after.get(k, 0) for k in before if before[k] > after.get(k, 0)}
        failed = self.BOX_FAIL in txt
        # 再用一次 peek 读**容器真值** ✓（"放完了"必须由容器自己证明 ✓ 不由命令回显证明 ✗）
        pk = self._dshbox("peek", x, y, z)
        ptxt = (pk.text() or "").strip()
        ok = bool(lost)
        ev = "放物回执：%s" % (txt[:200] or "（无回执 ✗）")
        ev += " ｜ 背包实减：%s" % ("，".join("%s×%d" % t for t in lost.items()) if lost else "（没有变化 ✗）")
        ev += " ｜ 容器现在：%s" % ptxt[:200]
        if failed and lost:
            ev += " ｜ ⚠ 模组报了「放不下」⇒ **只放进去一部分** ✓ 余额仍在背包 ✓"
        return self._r(ok, ev, removed=lost, partial=failed, container=ptxt, reply=txt)

    # ══ 模组 v2.0：把"真人能干、假人干不了"的事补上 ✓ ═════════════════════════
    # 统一纪律（都是本项目最贵的教训 ✓）：
    #   * 回执**只认 ASCII** ✗（P13 ✓）：中文过 CC 命令通道会变成 `?` ✗
    #     模组 v2.0 起**所有回执都是 ASCII** ✓ ⇒ 成功 = `dshxxx <op> …` ✓
    #     失败 = `dshxxx: …`（带冒号 ✓）⇒ 用 startswith 就能判 ✓ 不依赖任何中文 ✓
    #   * 判成败**看世界/背包真值** ✗ 不看指令回显 ✗（C5 / N1 ✓）
    #   * 模组**自己会做触及距离检查** ✓（4.5 格 ✓ 真人约束 ✓ 不是能力膨胀 ✗）

    @staticmethod
    def _dsh_ok(txt: str, cmd: str) -> bool:
        s = (txt or "").strip()
        return s.startswith(cmd + " ")

    def _dsh_call(self, text: str, timeout: float = 60.0):
        """★必须 `execute as Bot at Bot`★★ ✗
        模组里所有动作都作用在**执行者自己**身上 ✓（`src.getPlayerOrException()` ✗）
        ⇒ 直接由 cmd0 发 ⇒ 命令源不是玩家 ⇒ 那一句会抛异常 ✗（P14/18.3 ✓）
        """
        return self.ch.cmd("execute as %s at %s run %s" % (self.bot, self.bot, text),
                           timeout=timeout, allow_str=True)

    def s_use_face(self, x: int, y: int, z: int, face: str = "up", aimy: float = 0.5) -> dict:
        before = self.ch.verify_block(int(x), int(y), int(z))
        bname = str(before.get("name", "?"))
        r = self._dsh_call("dshuse %d %d %d %s %.3f" % (int(x), int(y), int(z), str(face), float(aimy)),
                           timeout=90.0)
        txt = (r.text() or r.summary(300)).strip()
        after = self.ch.verify_block(int(x), int(y), int(z))
        aname = str(after.get("name", "?"))
        ok = self._dsh_ok(txt, "dshuse")
        ev = "对 (%s,%s,%s) 的 %s 面右键：%s → %s ｜ %s" % (x, y, z, face, bname, aname, txt[:240])
        if ok and bname == aname:
            ev += " ｜ ⚠ 方块没变 ✓ 但**这不一定等于没发生** ✗（可能只是消耗了手持物/推进了内部进度 ✓" \
                  " 也可能**真的什么都没发生** ✗）⇒ 要判效果请看**瞄准的那个方块的 NBT/进度** ✗（P16 ✓）"
        return self._r(ok, ev, before=bname, after=aname, reply=txt)

    def s_make(self, op: str = "do", item: str = "", times: int = 1) -> dict:
        op = str(op or "do").lower()
        if op not in ("do", "can", "recipes"):
            return self._r(False, "op 只能是 do / can / recipes ✗（收到 %r）" % op)
        # ★ 合成**会往背包里塞产物** ✗ ⇒ 入口先过背包守卫 ✓
        #   ⚠ 这条是**血的教训** ✓（错题本 **L1** ✓）：
        #     背包满时 `player.give` **静默失败** ✗ ⇒ 现象是"**扣了料、没给货**"✗
        #     —— 看起来像"配方不对"✗ 其实是没地方放 ✗（`can` 是干跑 ✓ 不用守卫 ✓）
        if op == "do":
            g = self._guard(need=1)
            if g is not None:
                return g
        before = self.w.counts()
        # ⚠ `recipes` 子命令**只接 item**（没有 times ✗）——
        #   实测踩过：多传一个数字 ⇒ Brigadier 直接回"参数不对"✗
        #   而回执是中文的 ⇒ 变成 `?` ✗ 光看回执根本看不出是"多传了一个参数"✗（P13/P14 同族 ✓）
        cmd = 'dshcraft %s "%s"' % (op, str(item))
        if op != "recipes":
            cmd += " %d" % int(times)
        r = self._dsh_call(cmd, timeout=120.0)
        txt = (r.text() or r.summary(300)).strip()
        after = self.w.counts()
        gained = {k: after.get(k, 0) - before.get(k, 0)
                  for k in set(list(before) + list(after))
                  if after.get(k, 0) - before.get(k, 0) > 0}
        lost = {k: before[k] - after.get(k, 0) for k in before if before[k] > after.get(k, 0)}
        if op == "do":
            # ★ 判据看**背包真的变了** ✗ 不看那句回执 ✓（回执会说谎 ✓ 背包不会 ✓）
            ok = self._dsh_ok(txt, "dshcraft") and bool(gained)
            ev = "合成 %s ×%d：%s" % (item, times, txt[:220])
            ev += " ｜ 实增：%s ｜ 实耗：%s" % (
                "，".join("%s×%d" % t for t in gained.items()) or "（没有变化 ✗）",
                "，".join("%s×%d" % t for t in lost.items()) or "（没有消耗 ✗）")
        else:
            ok = self._dsh_ok(txt, "dshcraft")
            ev = "合成预检(%s) %s ×%d：%s" % (op, item, times, txt[:260])
        return self._r(ok, ev, gained=gained, consumed=lost, reply=txt)

    def s_inv(self, op: str, a: int | None = None, b: int | None = None,
              count: int | None = None) -> dict:
        op = str(op or "").lower()
        if op == "list":
            cmd = "dshinv list"
        elif op == "move":
            if a is None or b is None:
                return self._r(False, "move 需要 a=源槽位 b=目标槽位 ✗")
            cmd = "dshinv move %d %d" % (int(a), int(b)) + ("" if count is None else " %d" % int(count))
        elif op == "drop":
            if a is None:
                return self._r(False, "drop 需要 a=槽位 ✗")
            cmd = "dshinv drop %d" % int(a) + ("" if count is None else " %d" % int(count))
        elif op == "equip":
            if a is None:
                return self._r(False, "equip 需要 a=槽位 ✗")
            cmd = "dshinv equip %d" % int(a)
        elif op == "hotbar":
            if a is None:
                return self._r(False, "hotbar 需要 a=槽位 ✗")
            cmd = "dshinv hotbar %d" % int(a)
        else:
            return self._r(False, "op 只能是 list/move/drop/equip/hotbar ✗（收到 %r）" % op)

        before = self.w.counts()
        r = self._dsh_call(cmd, timeout=90.0)
        txt = (r.text() or r.summary(300)).strip()
        after = self.w.counts()
        ok = self._dsh_ok(txt, "dshinv")
        ev = "背包 %s：%s" % (op, txt[:260])
        if op in ("drop", "move"):
            # drop 会让"背包总数减少"✓ move 不改变总数 ✓ ⇒ 分别报 ✓
            ev += " ｜ 背包总数 %d → %d" % (sum(before.values()), sum(after.values()))
        return self._r(ok, ev, reply=txt, total_before=sum(before.values()),
                       total_after=sum(after.values()))

    # ══ ★★模组 v2.6：感知与行走★★（都是"模组原生" ✓ 一条指令 = 一整件事 ✓）══════
    #
    # 统一纪律（与容器那批一致 ✓）：
    #   * 回执只认 **ASCII 前缀** ✗（`dshdigest …` ✓ / `dshdigest: …` 失败 ✓ 见 P13 ✓）
    #   * 判据用**世界/背包真值** ✗ 不听自述 ✗
    #   * **失败大声** ✓：走不到就说走不到 ✓ 而且带上**为什么** ✓
    @staticmethod
    def _kv(txt: str) -> dict:
        """把 `k=v` 一行拆成 dict ✓（模组回执全 ASCII ✓ 好拆 ✓）"""
        out: dict = {}
        for tok in (txt or "").replace("|", " ").split():
            if "=" in tok:
                k, _, v = tok.partition("=")
                out[k] = v
        return out

    def s_digest(self, radius: float = 8.0) -> dict:
        """★一条指令一份态势★ —— 每次决策**先跑它** ✓（取代 4~6 条零散查询 ✗）"""
        r = self._dsh_call("dshdigest %.1f" % float(radius), timeout=60.0)
        txt = (r.text() or r.summary(400)).strip()
        ok = self._dsh_ok(txt, "dshdigest")
        kv = self._kv(txt)
        ev = "态势：%s" % (txt[:400] or "（没有回执 ✗ 模组没加载？还是版本低于 v2.6？）")
        return self._r(ok, ev, raw=txt, pos=kv.get("pos"), free=kv.get("inv[x]kinds"),
                       food=kv.get("food"), hp=kv.get("hp"), mode=kv.get("mode"),
                       drops=kv.get("drops"), look=kv.get("look"), fields=kv)

    def s_scan_box(self, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int,
                   match: str | None = None, max: int = 64, page: int = 1) -> dict:
        """★原生区域扫描★ —— 2268 格 3.5 s ✗ ⇒ 毫秒级 ✓（寻路扫描不再超时 ✓）"""
        cmd = "dshscan %d %d %d %d %d %d" % (int(x0), int(y0), int(z0), int(x1), int(y1), int(z1))
        if match:
            # ⚠ 物品/方块名带冒号 ⇒ **必须加引号** ✗（Brigadier 的 string() 不吃裸冒号 ✓ P14 ✓）
            cmd += ' "%s" %d %d' % (str(match), int(max), int(page))
        r = self._dsh_call(cmd, timeout=60.0)
        txt = (r.text() or r.summary(400)).strip()
        ok = self._dsh_ok(txt, "dshscan")
        kv = self._kv(txt)
        cells = []
        if "cells[" in txt:
            blob = txt.split("cells[", 1)[1].rstrip("]")
            for tok in blob.split():
                if ":" in tok and "," in tok:
                    xyz, _, rest = tok.partition(":")
                    parts = xyz.split(",")
                    if len(parts) == 3 and all(p.lstrip("-").isdigit() for p in parts):
                        name, _, state = rest.partition(",")
                        cells.append({"x": int(parts[0]), "y": int(parts[1]), "z": int(parts[2]),
                                      "n": name, "state": state})
        ev = ("区域扫描：%s（solid=%s kinds=%s matched=%s 用时 %s us ✓）"
              % (" ".join("%s=%s" % (k, kv[k]) for k in ("vol", "solid", "kinds", "matched", "us") if k in kv),
                 kv.get("solid"), kv.get("kinds"), kv.get("matched"), kv.get("us")))
        return self._r(ok, ev, raw=txt[:600], cells=cells, matched=kv.get("matched"), us=kv.get("us"))

    def s_look_hit(self, reach: float = 4.5) -> dict:
        """★准星射线 ＋ 可达性★ —— 动手前先问"我到底打得到什么面" ✓（P16 的解药 ✓）"""
        r = self._dsh_call("dshlook %.2f" % float(reach), timeout=60.0)
        txt = (r.text() or r.summary(300)).strip()
        kv = self._kv(txt)
        ok = self._dsh_ok(txt, "dshlook")
        reachable = kv.get("reachable")
        ev = "准星：%s" % (txt[:300] or "（没有回执 ✗）")
        if reachable is not None and str(reachable).lower() == "false":
            ev += " ｜ ⚠ **够不着** ✗（真人触及 4.5 格 ✓）—— 先走近再动手 ✓"
        return self._r(ok, ev, raw=txt, block=kv.get("block"), entity=kv.get("entity"),
                       face=kv.get("face"), dist=kv.get("dist"), reachable=reachable)

    def s_walk_to(self, x: int, y: int, z: int, ms: int = 10000, exact: bool = False) -> dict:
        """★走一条腿★ —— 一条指令一整段 ✓（不再"一格一条指令"✗ 也不再 `tp` ✗）

        为什么这里**必须等**（而不是发完就走）✗：
          "发了指令"和"走到了"是两件事 ✗ —— 本项目最贵的教训就是**别把发出当成功** ✗
          ⇒ 所以本技能循环问 `/dshwalk` 状态 ✓ 直到 `done` ✓ 再按 `result` 如实判 ✓
          （`reached` ✓ / `edge`（前面没落脚点 ✓ 空岛防坠 ✓）/ `blocked`（附**为什么**✓）/
            `timeout`（预算用完 ✓）✓ —— **绝不假装到了** ✗）
        """
        cmd = "dshwalk %d %d %d %d%s" % (int(x), int(y), int(z), int(ms),
                                         " exact" if exact else "")
        r0 = self._dsh_call(cmd, timeout=60.0)
        t0 = (r0.text() or "").strip()
        if not self._dsh_ok(t0, "dshwalk"):
            return self._r(False, "开走失败 ✗：%s" % (t0[:200] or "（没有回执 ✗ 模组版本低于 v2.6？）"))
        deadline = time.time() + max(3.0, float(ms) / 1000.0 + 3.0)
        last = ""
        while time.time() < deadline:
            time.sleep(0.4)
            rs = self._dsh_call("dshwalk", timeout=30.0)
            st = (rs.text() or "").strip()
            if st:
                last = st
            kv = self._kv(st)
            if kv.get("status") == "done":
                res = kv.get("result", "?")
                ok = (res == "reached")
                ev = ("走去 (%d,%d,%d)：%s ✓ 停在 %s 偏差 %s 格 ｜ 驱动=%s ｜ 绕障=%s ｜ 下台阶=%s ｜ 原因：%s"
                      % (x, y, z, "到达" if ok else "**没到** ✗", kv.get("at"), kv.get("dist"),
                         kv.get("mode"), kv.get("detours", "0"), kv.get("step_downs", "0"),
                         kv.get("why", "none")))
                return self._r(ok, ev, raw=st, result=res, at=kv.get("at"),
                               dist=kv.get("dist"), mode=kv.get("mode"), why=kv.get("why"),
                               detours=kv.get("detours"), step_downs=kv.get("step_downs"),
                               ticks=kv.get("ticks"), sprint=kv.get("sprint"))
        self._dsh_call("dshwalk stop", timeout=30.0)
        return self._r(False, "走去 (%d,%d,%d)：**超时** ✗（本技能等不下去了 ⇒ 已发 stop ✓）最后状态：%s"
                       % (x, y, z, last[:200]))

    def s_events(self, since: int | None = None) -> dict:
        """★增量事件流★ —— "它告诉我"而不是"我轮询" ✓"""
        cmd = "dshevents" if since is None else "dshevents %d" % int(since)
        r = self._dsh_call(cmd, timeout=60.0)
        txt = (r.text() or r.summary(400)).strip()
        ok = self._dsh_ok(txt, "dshevents")
        kv = self._kv(txt)
        items = [seg.strip() for seg in txt.split("|")[1:]] if "|" in txt else []
        ev = "事件：new=%s cursor=%s ｜ %s" % (kv.get("new"), kv.get("cursor"),
                                              " ／ ".join(items[-6:]) or "（没有新事件 ✓）")
        return self._r(ok, ev, raw=txt[:800], events=items, cursor=kv.get("cursor"),
                       new=kv.get("new"))

    def s_auto(self, what: str, on: bool | None = None, minfood: int = 14) -> dict:
        """自动行为开关 ✓（eat ✓ idle ✓ status ✓）"""
        w = str(what or "").lower()
        if w == "status":
            cmd = "dshauto"
        elif w == "eat":
            cmd = "dshauto eat %s" % ("on" if on else "off") if on is not None else "dshauto"
            if w == "eat" and on:
                cmd = "dshauto eat %d" % int(minfood)
        elif w == "idle":
            cmd = "dshauto idle %s" % ("on" if on else "off")
        else:
            return self._r(False, "what 只能是 eat / idle / status ✗（收到 %r）" % what)
        r = self._dsh_call(cmd, timeout=40.0)
        txt = (r.text() or r.summary(200)).strip()
        return self._r(self._dsh_ok(txt, "dshauto"), "自动行为：%s" % (txt[:200] or "（没有回执 ✗）"),
                       raw=txt)

    def s_place_at(self, x: int, y: int, z: int, item: str) -> dict:
        """★显式放方块★（模组 v2.7 ✓ 带落点校验 ✓ 可判读的失败原因 ✓）

        ⚠ 与旧技能 `place` 的分工 ✗：
          * `place`   = **旧 Lua 路** ✗（靠 `place_adjacent` ✓ 对**可交互方块**要先潜行 ✗ 见 L4 ✓
                        而且失败只说"四周没出现新方块"✗ 什么都问不出来 ✗）
          * `place_at`= **模组路** ✓（说清"物品不在身上/目标不是空气/没有支撑面"✗ ＋ 世界真值复核 ✓）
        ⇒ 新流程用这条 ✓（旧那条留作排查 ✓）
        """
        r = self._dsh_call('dshplace %d %d %d "%s"' % (int(x), int(y), int(z), str(item)), timeout=90.0)
        txt = (r.text() or r.summary(300)).strip()
        ok = self._dsh_ok(txt, "dshplace")
        # ★复核**必须以世界真值为准**✗（模组已经复核过一次 ✓ 我这边再独立读一次 ✓ 两边对账 ✓）
        st = self.ch.verify_block(int(x), int(y), int(z))
        now = str(json.dumps(st, ensure_ascii=False))
        placed_name = ""
        m = re.search(r'"name"\s*:\s*"([^"]+)"', now)
        if m:
            placed_name = m.group(1)
        really = ("air" not in placed_name) and ok
        ev = "放方块 %s←%s：%s" % ((x, y, z), item, txt[:240] or "（没有回执 ✗ 模组版本低于 v2.7？）")
        ev += " ｜ 世界真值该格 = %s" % (placed_name or "?")
        if not really:
            ev += " ｜ ⚠ **没放成** ✗（以世界真值为准 ✗ —— 别拿那句话当结论 ✓）"
        return self._r(really, ev, raw=txt, block=placed_name)

    def s_ent_use(self, target: str) -> dict:        # ★ 右键实体**可能给东西**（挤奶 ✗ 剪毛 ✗ 繁殖掉的蛋 ✗）⇒ 先过守卫 ✓
        g = self._guard(need=1)
        if g is not None:
            return g
        r = self._dsh_call('dshent use %s' % str(target), timeout=90.0)
        txt = (r.text() or r.summary(300)).strip()
        ok = self._dsh_ok(txt, "dshent")
        return self._r(ok, "右键实体 %s：%s" % (target, txt[:260]), reply=txt)

    # ── v2.1：按槽位 ✓ 实体容器 ✓ 村民交易 ✓ ───────────────────────────────
    def s_box_slot(self, op: str, x: int, y: int, z: int, slot: int,
                   count: int | None = None) -> dict:
        op = str(op or "").lower()
        if op not in ("get", "take", "put"):
            return self._r(False, "op 只能是 get / take / put ✗（收到 %r）" % op)
        if op == "take":                       # ★ 按槽位取物也是"接东西" ✗ ⇒ 先过守卫 ✓
            g = self._guard(need=1)
            if g is not None:
                return g
        cmd = "dshslot %s %d %d %d %d" % (op, int(x), int(y), int(z), int(slot))
        if count is not None and op in ("take", "put"):
            cmd += " %d" % int(count)
        before = self.w.counts()
        r = self._dsh_call(cmd, timeout=90.0)
        txt = (r.text() or r.summary(300)).strip()
        after = self.w.counts()
        gained = {k: after.get(k, 0) - before.get(k, 0)
                  for k in set(list(before) + list(after))
                  if after.get(k, 0) - before.get(k, 0) > 0}
        lost = {k: before[k] - after.get(k, 0) for k in before if before[k] > after.get(k, 0)}
        ok = self._dsh_ok(txt, "dshslot")
        ev = "容器槽位 %s (%s,%s,%s)[%d]：%s" % (op, x, y, z, slot, txt[:240])
        if op != "get":
            ev += " ｜ 背包实增 %s ｜ 实减 %s" % (
                "，".join("%s×%d" % t for t in gained.items()) or "（无）",
                "，".join("%s×%d" % t for t in lost.items()) or "（无）")
        return self._r(ok, ev, gained=gained, lost=lost, reply=txt)

    def s_entbox(self, op: str, target: str, item: str | None = None,
                 count: int | None = None, page: int = 1) -> dict:
        op = str(op or "").lower()
        if op == "peek":
            cmd = "dshentbox peek %s %d" % (str(target), int(page))
        elif op in ("take", "put"):
            cmd = "dshentbox %s %s" % (op, str(target))
            if item:
                cmd += ' "%s"' % str(item)          # ⚠ 带冒号必须加引号 ✗（P14 ✓）
                if count is not None:
                    cmd += " %d" % int(count)
        else:
            return self._r(False, "op 只能是 peek / take / put ✗（收到 %r）" % op)
        if op == "take":                       # ★ 实体容器取物也是"接东西" ✗ ⇒ 先过守卫 ✓
            g = self._guard(need=1)
            if g is not None:
                return g
        before = self.w.counts()
        r = self._dsh_call(cmd, timeout=90.0)
        txt = (r.text() or r.summary(300)).strip()
        after = self.w.counts()
        gained = {k: after.get(k, 0) - before.get(k, 0)
                  for k in set(list(before) + list(after))
                  if after.get(k, 0) - before.get(k, 0) > 0}
        lost = {k: before[k] - after.get(k, 0) for k in before if before[k] > after.get(k, 0)}
        ok = self._dsh_ok(txt, "dshentbox")
        ev = "实体容器 %s %s：%s" % (op, target, txt[:240])
        if op != "peek":
            ev += " ｜ 背包实增 %s ｜ 实减 %s" % (
                "，".join("%s×%d" % t for t in gained.items()) or "（无）",
                "，".join("%s×%d" % t for t in lost.items()) or "（无）")
        return self._r(ok, ev, gained=gained, lost=lost, reply=txt)

    def s_trade(self, op: str, target: str, index: int = 0, times: int = 1) -> dict:
        op = str(op or "").lower()
        if op == "list":
            cmd = "dshtrade list %s" % str(target)
        elif op == "do":
            # ══════════════════════════════════════════════════════════════════════
            # ★★ 已知缺陷（2026-09-19 晚**实测** ✓ 证据 tools/trade_probe.py ✓）★★
            #   ① `times>1` **一次也不多** ✗ —— 两次独立实测都是 `trades=1` ✗
            #      （verify_trade 的 `do 0 2` ✓ 与探针 C 的 `do 0 2` ✓ 都是 1 笔 ✗）
            #   ② **余款会掉在地上** ✗ —— 探针 C 那一次，**28 个绿宝石从背包消失** ✗
            #      地上当场查到 `minecraft:emerald Count:25` ✗
            #      ★当时背包正好 36/36 全满 ✗ ⇒ **捡不起来** ✗ ⇒ 差 5 分钟就全没了 ✗★
            #      （我用 inv_guard 腾出 4 格才抢回来 ✓ 现在 `19:minecraft:emeraldx25` ✓）
            #   ③ 产物**不并堆** ✗ —— 一次一笔就**占掉一个新槽** ✗（实测出现 9 格各 1 双铁靴 ✗）
            #      ⇒ 连续交易**必然把背包塞满** ✗ ⇒ 与②叠加 = **必丢钱** ✗✗
            #   ⇒ 在 v2.5 修好之前 ✗ **技能层直接拒绝 times>1** ✓
            #     宁可只做一笔（慢 ✓ 但账目清楚 ✓）也绝不让它悄悄丢钱 ✗（纪律⑤ ✓）
            # ══════════════════════════════════════════════════════════════════════
            if int(times) > 1:
                return self._r(False,
                               "拒绝执行 ✗ `dshtrade do … times=%d` —— 实测 **times>1 一次也不多** ✗"
                               "（两次实测都只成 1 笔 ✓）而且余款会掉地上 ✗"
                               "（实测一次掉 25 个绿宝石 ✗ 当时满包 ⇒ 捡不起来 ✗）"
                               "⇒ 请改成**一笔一条**逐笔来 ✓（v2.5 修好之前技能层不冒这个险 ✓ "
                               "复现：py tools/trade_probe.py ✓）" % int(times))
            # 产物 1 格 ＋ 余款回手 1 格 ✓ —— 少一格就可能把余款丢在地上 ✗
            g = self._guard(need=2)
            if g is not None:
                return g
            cmd = "dshtrade do %s %d %d" % (str(target), int(index), int(times))
        else:
            return self._r(False, "op 只能是 list / do ✗（收到 %r）" % op)
        before = self.w.counts()
        r = self._dsh_call(cmd, timeout=120.0)
        txt = (r.text() or r.summary(300)).strip()
        after = self.w.counts()
        gained = {k: after.get(k, 0) - before.get(k, 0)
                  for k in set(list(before) + list(after))
                  if after.get(k, 0) - before.get(k, 0) > 0}
        ok = self._dsh_ok(txt, "dshtrade")
        ev = "村民交易 %s：%s" % (op, txt[:300])
        dropped = ""
        if op == "do":
            # ★ 成没成**看背包实增** ✗ 不看那句话 ✓（那个方法不返回值 ✓ 只信真值 ✓）
            ev += " ｜ 背包实增：%s" % ("，".join("%s×%d" % t for t in gained.items()) or "（没有变化 ✗）")
            ok = ok and bool(gained)
            # ★ **地面哨兵** ✗（2026-09-19 晚新增 ✓ 因为**真的**掉过东西 ✗）：
            #   模组交易那条路会把**余款**和**产物**落到地上 ✗（见上面那段证据 ✓）
            #   ⇒ 交易后**立刻问一句"地上有没有掉落物"** ✓
            #   —— 有 ⇒ 大声报出来 ✓ 让人立刻腾格子捡回来 ✓（5 分钟就消失 ✗ 绝不静默 ✗）
            try:
                gr = self.ch.cmd("execute as %s at %s run data get entity "
                                 "@e[type=item,limit=1,sort=nearest,distance=..6] Item.id"
                                 % (self.bot, self.bot), timeout=30.0, allow_str=True)
                gl = (gr.text() or "").strip().splitlines()
                dropped = gl[0] if gl else ""
            except BridgeError:
                dropped = ""
            if "minecraft:" in dropped:
                ev += (" ｜ ⚠★**地上有掉落物**★✗：%s ⇒ 立刻查空位 ✓ 并捡回来 ✓"
                       "（满包时**捡不起来** ✗ 5 分钟消失 ✗ 实测丢过 25 个绿宝石 ✗）" % dropped[:80])
        return self._r(ok, ev, gained=gained, reply=txt, dropped_on_ground=dropped)

    # -- 脚手架（默认禁用） -------------------------------------------------- #

    def s_give_item(self, slot: int, item: str, count: int = 1) -> dict:
        r = self.ch.call("give_slot", {"bot": self.bot, "slot": int(slot) - 1,
                                       "item": item, "count": int(count)},
                         timeout=60.0, allow_str=True)
        inv = self.w.counts()
        got = inv.get(item, inv.get("minecraft:" + item, 0))
        return self._r(got >= int(count), "【脚手架】发放 %s×%d，背包现有 %d" % (item, count, got))


def main(argv: list[str]) -> int:
    ch = Channel("cmd0")
    w = World(ch)
    sk = Skills(ch, w, allow_scaffold="--allow-scaffold" in argv)
    if not argv or argv[0] in ("-h", "--help", "list"):
        print("=" * 74)
        print("可用技能（脚手架技能 %s）" % ("已启用" if sk.allow_scaffold else "已禁用"))
        print("-" * 74)
        print(sk.help_text())
        print("=" * 74)
        print("用法：py agent/skills.py scan radius=5")
        return 0
    name = argv[0]
    args = {}
    for a in argv[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            if v.lower() in ("true", "false"):
                args[k] = v.lower() == "true"
            else:
                try:
                    args[k] = int(v)
                except ValueError:
                    try:
                        args[k] = float(v)
                    except ValueError:
                        args[k] = v
    out = sk.run(name, args)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
