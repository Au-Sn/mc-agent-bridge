#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""environment.py -- ★问世界的**有名查询**✗★（★借鉴④ ✗ 2026-10-05✗★）

★★它解决什么✗★★：★让**每条判定可审计 ✗ 每个 bug 可归族**✗★ ✓
★（★用户原话：★"★对着 `NavigationEnvironment.java` 抄骨架 ✗ 7 个方法的接口✓★"✗★）✗★ ✓
★★★三栏（★我提的那条反对落成的 ✗ 用户的草稿把两栏混了✗★）✗★★
  ★**真值族**（★`truth`✗★）✗★：★只听**碰撞／已声明的标签**✗ ✗ 与执行者无关✗★ ✓
    ★`standable(pos)`✗ ★`is_liquid(pos)`✗★
  ★**执行族**（★`exec`✗★）✗★：★"★**我们**能不能用它★" ✗ 系数来自**校准场**✗★
    ★每条**必须**标 `measured` 还是 `theoretical`✗★ ✓
    ★`swimmable(pos)`✗ ★`climbable(pos)`✗ ★`parkourable(frm,to)`✗ ★`ascendable(frm,to)`✗★ ✓
  ★**政策族**（★`policy`✗★）✗★：★"★**该不该**去★" ✗ **绝不参与物理**✗★ ✓
    ★`canopy(pos)`✗ ★`safe(pos)`✗★ ✓
★★★两条铁规矩✗★★
  ★① **答不了就 `None`**✗★（★`UNKNOWN` 一等公民 ✗ **永不**静默当"★安全／可走★"✓★）✗★ ✓
  ★② ★政策族**动了物理**就是 bug✗★ ⇒ ★判据 `E6` 机械查它（★§79.182 同一条口径✓★）✗★ ✓
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★★三栏（★每个查询**必须**在表里 ✗ 判据据此查"★有没有漏声明的★"✗★）✗★
QUERIES = {
    # ★真值族✗★
    "standable_physical": {"family": "truth", "why": "★纯物理：脚下那格是 `is_floor` ＋ 本格／头上能穿过（★只看碰撞 ✗ 不问政策✓★）✗★"},
    "standable":   {"family": "policy",  "why": "mapread.is_landing（★碰撞 ＋ 政策『树冠不落』✗★）"},
    "is_liquid":   {"family": "truth",  "why": "blockkb 碰撞族 == liquid"},
    # ★执行族✗★
    "swimmable":   {"family": "exec",   "measured": False,
                    "why": "★执行者会不会游 ✗ **没在校准场测过**✗★"},
    "climbable":   {"family": "exec",   "measured": False,
                    "why": "★标签 `能爬`（★8 个物种✗★）✗ 但**执行者能不能爬 ✗ 没测过**✗★"},
    "parkourable": {"family": "exec",   "measured": True,  "why": "★同层平走 ✗ 走手实测✗★"},
    "ascendable":  {"family": "exec",   "measured": True,  "why": "★上 1 格 ✗ 走手实测只上 1 格✗★"},
    # ★政策族✗★
    "canopy":      {"family": "policy", "why": "★标签类别 `叶子`（★声明过✓★）✗★"},
    # ★★2026-10-13（★裁决 C5 ✗ §79.222✗★）✗★★：★来源**有了**✗★ ——
    #   ★`岩浆`／`火` 两个标签类别落地（★显式标签 id ✗ §79.221✓★）⇒
    #   ★政策默认"**回避进入**"（★保守默认 ✗ 不需要执行者状态✓★）✗★ ✓
    "safe":        {"family": "policy", "why": "★危险 ✗ 来源＝标签类别 岩浆／火（★§79.221 落地✓★）✗ 默认**回避进入**（★保守 ✗ 不需执行者状态✓★）✗★"},
}


def family_of(query: str):
    q = QUERIES.get(query)
    return q.get("family") if q else None


# ##########################################################################
# ★真值族✗★
# ##########################################################################
def standable_physical(pos):
    """★**纯物理**：这一格能不能站（★只看碰撞 ✗ 不看政策✗★）✗★ ✓

    ★★2026-10-13（★用户裁决 C3✗★）✗★★：★原话✗★ ——
      ★"★拆 `environment.standable`（★现在标 truth 家族却掺『树冠不落』政策✗★）："
      "`standable_physical`（★纯碰撞✗★）＋ `is_landing`（★物理＋政策✗★）★"✗★ ✓
    ★为什么必须拆✗★：★"★政策污染真值栏★"的教科书例子 ——
      一个查询标着"★真值★" ✗ 而它的答案里**混了政策** ⇒ ★以后没人分得清"★物理说不行★"
      还是"★政策说别去★"✗★ ✓
    ★这一条**只问碰撞**✗★：★脚下那格是不是 `is_floor` ✗ 本格与头上能不能穿过✗★ ✓
    ★（★树叶：★**在当前档位**物理上**站不住**（★名字档与 table 档都是 False✗★）✗ ★而 table 档 ＋ 导出说 `full` 时才是能站✗★ —— ★§79.231 认定树叶能站这条前提**在当前档位不成立**✗★ ✗ 而政策上**不落脚** —— 两条现在各答各的✓★）✗★ ✓
    """
    import mapread as MR
    x, y, z = int(pos[0]), int(pos[1]), int(pos[2])
    below = _species_at((x, y - 1, z))
    if below is None:
        return None
    import blockkb as KB
    for p in ((x, y, z), (x, y + 1, z)):
        sp2 = _species_at(p)
        if sp2 is None:
            return None
        try:
            if KB.blocks_space(sp2):
                return False
        except Exception:
            return None
    try:
        return bool(MR.is_floor(below))       # ★纯碰撞 ✗ 不问政策✗★ ✓
    except Exception:
        return None


def standable(pos):
    """★**物理＋政策**：去那儿落脚合不合适✗★ —— ★碰撞 ＋ 政策『树冠不落』✗★ ✓

    ★★2026-10-13（★用户裁决 C3✗★）✗★★：★这一条现在**明确**是复合的✗★ ——
      ★它＝ `standable_physical` ＋ `canopy` 政策✗★ ⇒ ★它的**栏是政策**✗ 不是真值✗★ ✓
      ★（★原来它标着"★真值★" ✗ 而答案里掺了政策 ⇒ 这就是 C3 要修的那件事✓★）✗★ ✓
    ★要**纯物理**那一问 ⇒ 用 `standable_physical`✗★ ✓

    ★★2026-10-05 修语义（★§79.183 ✗ `E2` 抓到的✗★）✗★★：★"★能不能站★"问的是
      **脚下那一格**是什么 ✗ **不是** `pos` 自己✗★ ✓
      ★（★原来写成问 `pos` 自己 ✗ 于是"★石头上面的空气★"被判成**站不住**✗★ ✓）
    ★还要求 `pos` 与头上**能穿过**（★不然站不进去✓★）✗★ ✓
    """
    import mapread as MR
    x, y, z = int(pos[0]), int(pos[1]), int(pos[2])
    # ★① 脚下那格要是**落脚点**（★读不到 ⇒ `None` ✗ 不许猜✓★）
    below = _species_at((x, y - 1, z))
    if below is None:
        return None
    # ★② 本格与头上要能穿（★"★空气★"或"★能穿过★"✗★）
    import blockkb as KB
    for p in ((x, y, z), (x, y + 1, z)):
        sp2 = _species_at(p)
        if sp2 is None:
            return None             # ★读不到 ⇒ 不许当空✗★ ✓
        try:
            if KB.blocks_space(sp2):
                return False        # ★挡人 ⇒ 站不进去✗★ ✓
        except Exception:
            return None
    try:
        return bool(MR.is_landing(below))
    except Exception:
        return None


def is_liquid(pos):
    """★这一格是不是**液体**✗★ —— ★纯真值（★碰撞族✗★）✗★ ✓"""
    import blockkb as KB
    sp = _species_at(pos)
    if sp is None:
        return None
    try:
        return KB.classify(sp, phys=True).get("fam") == "liquid"
    except Exception:
        return None


# ##########################################################################
# ★执行族✗★（★每条**必须**带 measured 标记✗★）
# ##########################################################################
def swimmable(pos):
    """★**我们**能不能从这格游过去✗★ —— ★执行族 ✗ 而**没测过** ⇒ `None`✗★ ✓

    ★★注意✗★★：★"★这格是水★"是真值（★`is_liquid`✓★）✗
    ★而"★我们能不能游★"是**执行** ✗ 两者**不是**一回事✗★ ✓（★§79.176 那条反对✓★）
    """
    if QUERIES["swimmable"].get("measured") is not True:
        return None                     # ★没测过 ⇒ 只许 `None`✗★ ✓
    return is_liquid(pos)               # ★测过之后才接执行者系数✗★ ✓


def climbable(pos):
    """★**我们**能不能爬这格✗★ —— ★执行族 ✗ 系数**没测过** ⇒ `None`✗★ ✓

    ★标签 `能爬` 只说明"★它是可爬的东西★" ✗ **不说明**我们爬得上去✗★ ✓
    """
    if QUERIES["climbable"].get("measured") is not True:
        return None
    import blockkb as KB
    sp = _species_at(pos)
    return None if sp is None else (KB.category_of(sp) == "能爬")


def parkourable(frm, to):
    """★从 `frm` 平走到 `to` 行不行✗★ —— ★执行族 ✗ **measured**✗★ ✓"""
    if abs(to[1] - frm[1]) != 0:
        return False
    return standable(to) is True


def ascendable(frm, to):
    """★从 `frm` 上到 `to` 行不行✗★ —— ★执行族 ✗ **只上 1 格**（★measured✗★）✗★ ✓"""
    if to[1] - frm[1] != 1:
        return False
    return standable(to) is True


# ##########################################################################
# ★政策族✗★（★**绝不**参与物理✗★）
# ##########################################################################
def canopy(pos):
    """★它是不是树冠✗★ —— ★政策 ✗ 用来"★回避落脚★"✗★ ✓"""
    import blockkb as KB
    sp = _species_at(pos)
    return None if sp is None else bool(KB.is_canopy(sp))


def safe(pos):
    """★去那儿**安不安全**✗★ —— ★政策栏✗★ ⇒ ★三态✗★ ✓

    ★★2026-10-13（★用户裁决 C5 ✗ §79.222✗★）✗★★：★来源**有了**✗★ ⇒ 接上✗★：
      · ★这一格的类别是 `DANGER`（★标签类别 `岩浆`／`火`✗★）⇒ **`False`**✗★ ✓
      · ★这一格读得到 ✗ 且不是 `DANGER` ⇒ **`True`**✗★ ✓
      · ★读不到 ✗ 或类别层答不出 ⇒ **`None`**✗★ ✓（★永不假装安全✓★）
    ★★为什么原来回 `None`✗★★：★那时类别表 27 个里**没有** `岩浆`／`火`✗★ ⇒
      ★按 ㉜ 口径**不许**从名字猜"★岩浆危险★"✗★ ⇒ ★只能诚实地说"★不知道★"✗★ ✓
      ★（★那句话今天**过期**了 ✗ 因为来源已经落地 ✗ 见 §79.221✓★）✗★ ✓
    ★★口径✗★★：★这**只影响"★要不要进去★"的政策** ✗ ★**绝不**动 `blocks_space`✗★ ✓
      （★物理只听碰撞 ✗ 政策不许越界 —— `environment_test` E6 与 `danger_test` D4 守着✓★）
    """
    import passclass as PC
    sp = _species_at(pos)
    if sp is None:
        return None                       # ★读不到 ⇒ 不许假装安全✗★ ✓
    try:
        cls = PC.class_of(sp)[0]
    except Exception:
        return None                       # ★类别层读不了 ⇒ 同上✗★ ✓
    if cls == "UNKNOWN":
        return None
    return cls != "DANGER"


# ##########################################################################
# ★★一格视图✗★★（★探针读完之后 `bind(cells)` ✗ **没绑定就一律回 `None`**✗★）✗★ ✓
#   ★为什么显式✗★：★"★从哪读这一格★"必须是**给进来的** ✗ 不许猜（★§79.171 的口径✓★）✗★ ✓
_BOUND = {"cells": None, "src": None}


def bind(cells, src="probe"):
    """★把一盒"★坐标 ⇒ 物种★"交给这层✗★ —— ★没绑就回 `None`✗★ ✓"""
    _BOUND["cells"] = cells or None
    _BOUND["src"] = src


def unbound():
    return _BOUND["cells"] is None


def _species_at(pos):
    """★这一格是什么物种✗★ —— ★没绑定／读不到 ⇒ `None`✗★ ✓"""
    cells = _BOUND["cells"]
    if not cells:
        return None
    return cells.get(tuple(int(v) for v in pos[:3]))


if __name__ == "__main__":
    print("★三栏✗★：")
    for q, v in sorted(QUERIES.items(), key=lambda kv: (kv[1]["family"], kv[0])):
        m = v.get("measured")
        print("   %-12s %-7s %s%s" % (q, v["family"],
                                      ("measured=%s " % m) if m is not None else "", v["why"][:52]))
