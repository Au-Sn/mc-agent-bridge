#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""families.py -- 四族词汇：phys／sem／exec／policy（§79.245 用户裁决 C1）

用户原话：§11 的 L1-L4 文档速记退役（与仓库 L0-L6 运行时栈撞名），
统一为一套：真值族={phys, sem}／执行族={exec}／政策族={policy}。
为什么要登记处而不是各写各的：「这个东西属于哪一族」是同一个问题，
散在几十个文件的注释里 ⇒ 问三次会得到三个答案（§79.188 那一族）。
四族的判据：
  · phys：只问碰撞形状；答不出就是 unknown，但永远不受标签影响
  · sem：只问标签／注册表；答不出就是「未知归属」
  · exec：问「执行者做得到吗」（台阶／跳跃／下落／绕路）
  · policy：我们选择怎么对待它（树冠不当路／岩浆要躲）
而「物理上答不出」（UNKNOWN）属于 phys —— 它是物理层的一等公民，
不是「不属于任何族」（用户裁决 C2）。
"""
from __future__ import annotations

FAMILIES = ("phys", "sem", "exec", "policy")

MEANING = {
    "phys": "只问碰撞形状；答不出＝unknown；永远不受标签影响",
    "sem": "只问标签／注册表；答不出＝未知归属",
    "exec": "问执行者做得到吗（台阶／跳跃／下落／绕路）",
    "policy": "我们选择怎么对待它（树冠不当路／岩浆要躲）",
}

# ---- 符号 ⇒ 族（一个符号只许有一个族）
SYMBOLS = {
    "mapread.is_floor": ("phys", "碰撞形状里「挡不挡人」"),
    "mapread.blocks_space": ("phys", "碰撞形状里「占不占位」"),
    "mapread.shape": ("phys", "碰撞形状的粗分类（走的是名字侧，仍是物理问题）"),
    "passclass.class_of": ("phys", "物理类；它把 UNKNOWN 也归 phys"),
    "environment.standable_physical": ("phys", "纯碰撞：脚下是地板且头上空"),
    "mapread.is_landing": ("policy", "is_floor 且 非树冠 —— 减号那一半是政策"),
    "environment.standable": ("policy", "物理 ＋ 树冠政策"),
    "environment.safe": ("policy", "危险品的处置是我们选的，不是物理"),
    "blockkb.category_of": ("sem", "物种 ⇒ 标签类别"),
    "blockkb.GEOMETRIC_CATEGORY": ("sem", "类别 ⇒ 导出族（家族真源）"),
    "divergence.expected_from_tags": ("sem", "类别 ⇒ 几何期望"),
    "passclass.POLICY_TAG": ("policy", "叶子⇒CANOPY、岩浆⇒DANGER"),
    "pathplan.is_auto_step": ("exec", "执行者能不能自动上这一格"),
    "pathplan.is_climbable": ("exec", "执行者能不能跳上去"),
    "reach_probe.reach_probe": ("exec", "执行者到不到得了（按原语表）"),
    "pathplan.A_STAR": ("exec", "怎么走，是执行侧的事"),
}

# ---- 退役的旧词汇（只许登记，不许再用）
RETIRED = {
    "L1": "§11 的文档速记第一层，与仓库 L0~L6 运行时栈撞名 ⇒ 该说的是 phys（只问碰撞形状）",
    "L2": "§11 的文档速记第二层，撞名 ⇒ 该说的是 sem（只问标签／注册表）",
    "L3": "§11 的文档速记第三层，撞名 ⇒ 该说的是 exec（执行者做得到吗）",
    "L4": "§11 的文档速记第四层，撞名 ⇒ 该说的是 policy（我们选择怎么对待它）",
}
# ★★判据只认"★退役那种★"的形式✗★★：★`L1`~`L4` 挨着「层／族／§11」才算旧词汇✗★；
# ★而判据自检编号（★`probe_limit` 的 L1~L5 ✗ `speech` 的 L1~L9✓★）**是合法的**✗★ ✓
# ★（★这一条是量出来的✗★：★裸出现 91 次 ✗ 而挨着"层／族"的只有 %d 次✓★）✗★ ✓
RETIRED_NEAR = ("层", "族", "§11")
# ★真值是 **0**✗★：★除了 `families.py` 与 `family_vocab_test.py`
#   （★它们是**定义**退役清单的地方 ✗ 当然要提旧名✓★）之外 ✗
#   ★全仓 `tools/*.py` 里挨着「层／族／§11」的 `L1`~`L4` **一次都不许有**✗★ ✓
RETIRED_NEAR_COUNT = 0
