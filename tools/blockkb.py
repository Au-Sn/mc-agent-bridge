#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blockkb.py -- ★方块知识表（任务书·阶段 2 的骨架）★ 纯离线 · 不碰世界 · 不落盘

★这个模块的**一句职责**✗★：★给"★这个名字是地板吗／挡人吗／属于哪族★"提供一个**带来源等级**的
  查询口 ✗ 并且**默认什么都不改**✗★（★`CLASSIFIER_SOURCE=blacklist` ⇒ 与今天**逐字相同**✓★）

── ★模块出生门（任务书 §7.2 ✗ 本项目第一次走这道门✗★）────────────────────────
按登记册要求 ✗ 逐个写出**与作用域匹配的那几条**的关系 ✓：

| 登记册 | 关系 |
|---|---|
| ★第 1 条✗★（分类要读标签／注册表 ✗ 不维护名字表✗★） | ★**本模块就是为它而生的**✗★ ⇒ 遵守 ✓（名字表只作为 `name_fallback` 级 ✗ 且**强制**标出来 ✓） |
| ★第 2 条✗★（不一致可以有 ✗ 但一条都不许没声明✗★） | ★遵守✗★ ⇒ `classify()` 的每一次返回都带 `level` ＋ `why` ✗ 而"回落到黑名单"这件事**显式写在返回里**✗★（不许静默回落 ✓） |
| ★第 3 条✗★（学来的必须来自比名字更硬的东西✗★） | ★遵守✗★ ⇒ `put()` 只接受登记在册的等级 ✗ 而且**升级语义**：高级到达就覆盖低级 ✓ |
| ★第 4 条✗★（来源分级 ＋ 升级语义 ✗ `name_fallback` 强制 TEMPORARY＋复核触发✓★） | ★**本模块是它的第一案**✗★ ⇒ 见 `put()` 的拒收规则 ✓ |

── ★三铁律怎么落在这个骨架里✗★ ─────────────────────────────────────────────
  ① ★物理只听碰撞形状✗★：★`blocks_space()`／`is_floor()` 在 `table` 模式下**只认
     `collision` 级** ✗ 标签级（`registry`）**永远不许**参与物理判定✗★ ✓
  ② ★不一致可以有 ✗ 但一条都不许没声明✗★：★返回值里 `declared` 字段列出**所有**回落／分歧 ✓
  ③ ★学来的必须来自更硬的东西✗★：★`put()` 不接受未登记的等级 ✗ 也不接受空 `src`✗★ ✓
"""
from __future__ import annotations

import os
import json
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mapread as MR  # noqa: E402  ★名字兜底那一路只用它的**纯函数**✓★

# ★★来源等级（登记册第 4 条 ✗ 从硬到软 ✗ 写死✗★★）
#   ① collision   ：★模组读碰撞形状 ⇒ **物理真值** ✗ 铁律 1 的唯一依据✗★
#   ② registry    ：★注册表/标签 ⇒ **只管语义** ✗ 永不影响物理✗★
#   ③ experiment  ：★物理实验（真实方块名 ＋ 几何结论）✗ 合格但弱✓★
#   ④ name_fallback：★名字兜底 ⇒ **必须**带 TEMPORARY ＋ 复核触发✗★
RANK = {"collision": 1, "registry": 2, "experiment": 3, "name_fallback": 4}
# ★物理判定只许这些等级说话✗★（★登记册第 4 条 ＋ 铁律 1 ✓★）
# ★★2026-10-18（★复核 P1-5 ✗ §79.277✗★）✗★★：★物理梯（★A4：collision > **物理实验**✗★）✗
#   ★原来这里是 `("collision",)` ✗ 而 `exception_table.EVIDENCE_PHYS` 是
#     `("collision","experiment")`✗★ ⇒ ★★**两套口径**✗★★ ⇒
#   ★一条合法的「物理主张 ＋ experiment 证据」落进表里 ✗ 而 `classify(phys=True)`
#     **读不到它**✗★ ⇒ ★物理结论**静默失效**✗★ ✓
PHYS_LEVELS = ("collision", "experiment")
# ★语义（家族/归属）可以用的等级✗★
SEM_LEVELS = ("registry", "collision", "experiment", "name_fallback")

SOURCE = (__import__("os").environ.get("CLASSIFIER_SOURCE", "export") or "export").strip()   # sec 79.457: DEFAULT IS export (general path)
#   Physical rules read the exported collision heights (all mods); tags/danger still
#   come from the tables (_kb_phys treats export like blacklist). Rollback:
#   CLASSIFIER_SOURCE=blacklist.
#   export is in VALID_SOURCES, mapread reads exported heights first, and
#   floor_test/temporary_test are adapted. Remaining before flipping the default:
#   dshmap_parse_test bot-cell mark + a few fixtures. Tracked in sec 79.455.
#   Physical rules read the exported collision heights (24779 entries, all mods);
#   tags/danger still come from the existing tables, so danger semantics are kept.
#   Rollback: CLASSIFIER_SOURCE=blacklist.
#   ★export 档**已就绪**（★mapread 的导出优先只在它下面生效✗★）✗ 切默认要迁移 7 条判据 ✗ 独立回合✗★
#   ★`blacklist` 仍是"★一个字节都不变★"（★想关就设 CLASSIFIER_SOURCE=blacklist✗★）✗★
# sec 79.455: add the export source. Behavior inside classify() is identical to
#   blacklist (tags/danger still come from the existing tables), but mapread's
#   physical rules (is_floor / blocks_space) read the exported collision heights
#   first. This is what makes the general path the default without losing danger.
VALID_SOURCES = ("blacklist", "table", "table+fallback", "export")

# ★知识表（★骨架期只在内存 ✗ 不落盘 ✗ 不碰任何真数据✓★）
TABLE: dict = {}
# ★★碰撞槽（★2026-10-03 拆出来 ✗ 因为**铁律 1 要求物理与语义各听各的**✗★）✗★★
#   ★为什么非拆不可✗★：★原来一个物种只有一个 `fam` ✗ 于是"★把 `/dshkb` 导出装进来★"
#     会把那 **91** 条**语义**族**抹掉**✗★ ⇒ ★而铁律 1 明说：★物理听碰撞 ✗ 语义听标签✗★ ✓
#   ★拆完之后**不可能**互相覆盖 ✗ 因为它们是两个字典✗★（★这比"★靠顺序小心★"结实✓★）
#   ★对外**不改签名**✗★：★`classify(phys=True)` 查这里 ✗ `classify(phys=False)` 查 `TABLE`✗★ ✓
PHYS: dict = {}
REFUSED: list = []          # ★被拒收的记录（★不许静默丢 ✗ 留着给人看✓★）

# ★★"★族 ⇒ 挡人／能站★"这两条判定（★**照抄** `mapread` ✗ 不许自己猜✗★）✗★★
#   ★出处（★grep 出来的 ✓ 不是记忆✓★）★：
#     · `mapread.py:105`  `blocks_space = shape in ("full","slab","fence","machine","canopy","other")`
#     · `mapread.py:361`  `is_floor    = shape in ("full","slab","machine")`
#   ★为什么放在**这一层**✗★：★它两条是"★族 ⇒ 布尔★"的**知识层**事实 ✗
#     而 `divergence` 要判"★这条分歧会不会改判定★" ✗ 也要用它 ⇒ ★一份实现 ✗ 由这里拥有✓★ ✓
FAM_BS = ("full", "slab", "fence", "machine", "canopy", "other")
FAM_FLOOR = ("full", "slab", "machine")


def blocks_space_fam(fam) -> bool:
    """★这一族**挡不挡人**✗★（★照抄 `mapread.py:105`✓★）"""
    return fam in FAM_BS


def is_floor_fam(fam) -> bool:
    """★这一族**算不算地板**✗★（★照抄 `mapread.py:361`✓★）"""
    return fam in FAM_FLOOR


def put(species: str, fam: str, level: str, src: str,
        trigger: str = "", temporary: bool = False, phys=None) -> bool:
    """★写一条知识✗★ —— ★升级语义 ＋ `name_fallback` 强制条款✗★（登记册第 4 条）

    ★拒收规则（★拒了就进 `REFUSED` ✗ 不许静默✗★）★
      · 等级不在册 ⇒ 拒（★第 3 条：学来的必须来自更硬的东西✗★）
      · `src` 空 ⇒ 拒（★说不出来源 ＝ 猜✗★）
      · ★`name_fallback` 级没有 TEMPORARY 或没有复核触发 ⇒ 拒✗★（★第 4 条强制条款✓★）
      · ★低级别**不许**覆盖高级别✗★（★不是先到先得 ✓ 是"谁硬谁说话"✓★）
    ★返回✗★：True ＝ 真的写进去了（★值得落盘的改变✓★）
    """
    why = None
    if level not in RANK:
        why = "★等级不在册✗★：%s" % level
    elif not (src or "").strip():
        why = "★说不出来源 ✗ 那就是猜✗★"
    elif level == "name_fallback" and not (temporary and (trigger or "").strip()):
        why = "★`name_fallback` 必须带 TEMPORARY ＋ 复核触发✗★（登记册第 4 条）"
    if why:
        REFUSED.append({"species": species, "fam": fam, "level": level, "why": why})
        return False
    # ★★按**等级**分槽✗★★：★`collision` ⇒ 碰撞槽（★物理✗★）✗ 其余 ⇒ 语义槽✗★ ✓
    #   ★两边各自跑同一套升级语义 ✗ 互不干扰✗★（★这就是铁律 1 的机械形态✓★）
    # ★★2026-10-18（★复核 P1-5 ✗ §79.277✗★）✗★★：★`experiment` 是**两条梯子唯一共有**
    #   的那一级 ✗★ ⇒ ★★"★按等级分槽★"**必然**错✗★★（★物理主张＋experiment 会落进语义槽✓★）⇒
    #   ★口径✗★：★`phys=True/False` **显式给** ⇒ 按它分槽 ＋ 查等级**在那条梯上**✗★；
    #   ★没给 ⇒ 只有 `collision` 能自己挑槽** ✗ 其余**拒收**（★"★不许猜✗ ★"）✗★ ✓
    if phys is True:
        if level not in PHYS_LEVELS:
            why = "★`phys=True` 而等级 `%s` 不在物理梯上（★%s✗★）✗ 拒✗★" % (
                level, "／".join(PHYS_LEVELS))
        slot = PHYS
    elif phys is False:
        if level not in SEM_LEVELS:
            why = "★`phys=False` 而等级 `%s` 不在语义梯上（★%s✗★）✗ 拒✗★" % (
                level, "／".join(SEM_LEVELS))
        slot = TABLE
    elif level == "collision":
        slot = PHYS                       # ★物理梯**独有** ⇒ 可以自己挑槽✗★ ✓
    elif level in ("registry", "name_fallback"):
        slot = TABLE                      # ★语义梯**独有** ⇒ 同上✗★ ✓
    else:
        # ★只有 `experiment` 会走到这里 ✗ 它**两条梯子都有**✗★ ⇒ ★不许猜✗★ ✓
        slot = None
        why = ("★`%s` 这条证据**两条梯子都有**（★物理梯 %s ✗ 语义梯 %s✗★）✗"
               "★不许由等级猜槽位 ✗ 调用方必须给 `phys=True/False`（★§79.277✓★）✗★"
               % (level, "／".join(PHYS_LEVELS), "／".join(SEM_LEVELS)))
    if why:
        REFUSED.append({"species": species, "fam": fam, "level": level, "why": why})
        return False
    old = slot.get(species)
    if old and RANK[old["level"]] <= RANK[level]:
        # ★旧的不比新的软 ⇒ 新的**不许**覆盖✗★（同级也不覆盖 ✗ 先到的算✓★）
        REFUSED.append({"species": species, "fam": fam, "level": level,
                        "why": "★升级语义：现有的 %s 级不比它软 ⇒ 不覆盖✗★" % old["level"]})
        return False
    slot[species] = {"fam": fam, "level": level, "src": src,
                     "temporary": bool(temporary or level == "name_fallback"),
                     "trigger": trigger or "", "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    return True


def get(species: str):
    return TABLE.get(species)


# ★★来源名字 ⇒ 等级（★登记册第 4 条 ✗ 只有写在这里的才收✗★★）★
#   ★这张表的用处✗★：★把"★已经有来源名字★"的老数据（`logs/block_shapes.json` 那 4 条✓★）
#   接进来时 ✗ **不许**由调用方随便报等级 ✗ 一律查这张表 ✓
SRC_LEVEL = {
    # ★真碰撞箱探测（★还没人产出 ✗ 但名字先占位 ✓ 将来只有它能覆盖一切✓★）
    "dshshape": "collision", "collision": "collision",
    # ★★2026-10-03：用户拍板的导出命令 ✗ 它就是**碰撞真值**的家✗★★
    "dshkb": "collision", "registry_blocks@1": "collision",
    # ★物理实验级✗★：★真实方块名 ＋ 几何结论（★"这一层站得住 ⇒ 脚下那块不挡人"✓★）
    #   ★2026-10-03 用户拍板✗★：★老的 `logs/block_shapes.json`（★`learn_shape` 的污染学习库存✓★）
    #   **降级**为"★物理实验级证据输入★" ⇒ ★它就是这一级 ✗ 不升不降✗★ ✓
    "dshmap-feet": "experiment", "dshmap-letter": "experiment",
    "learned:block_shapes": "experiment",
}

# ★★导出族（★`/dshkb` 的**几何**族 ✗ 七类 ＋ `liquid`✓★）⇒ 判定族（★`mapread` 现有族名✗★）✗★★
#   ★为什么要这张表✗★：★用户拍板的族名是**几何**的（★`full`／`slab`／`snow_layer`／
#     `fence_15`／`canopy`／`none`／`other`／`liquid`✓★）✗ 而 `is_floor`／`blocks_space`
#     用的是**现有**族名 ✗ ⇒ ★"★上层零改动★"这条要求**就落在这一张映射上**✗★ ✓
#   ★★映射的依据是几何 ✗ 不是名字✗★★（★由导出的 `empty` 与 `max_height` 决定✓★）
#     · `full`(1.0)        ⇒ `full`   —— ★挡人 ✓ 能站✗★
#     · `slab`(0.5)        ⇒ `slab`   —— ★挡人 ✓ 能站 ✓ 与 `floorOk` 那条 **0.5** 界同源✓★
#     · `snow_layer`(<0.45)⇒ `pass`   —— ★**不挡人** ✗ **不算地板** ✗
#         ★正是 v2.17 那条实测：★"★薄板／地毯／雪层**不是**一整格地板★"✓★
#     · `fence_15`(1.5)    ⇒ `fence`  —— ★挡人 ✓ 能站✗★
#     · `none`(空)         ⇒ `pass`   —— ★不挡人 ✗ 不算地板✗★
#     · `liquid`           ⇒ `liquid` —— ★不挡人 ✗ 不算地板 ✗ 物理上是"游"不是"走"✓★
#     · `other`            ⇒ `other`  —— ★挡人 ✓ 能站 ✗ 而**站多高**必须看 `max_height`✗★
#         （★用户原话：★"★`other` 必须永远带 `max_height` ✗ 消费者就不许为 `other` 写特例★"✓★）
#     · `canopy`           ⇒ ★**不在导出里**✗★ —— ★树叶的碰撞箱就是**整方块** ✗
#         碰撞**看不出**它是树冠 ⇒ ★它是**语义**（★标签 `leaves`✓★）✗ 由标签层给✗★ ✓
EXPORT_FAMILY = {
    "full": "full", "slab": "slab", "snow_layer": "pass", "fence_15": "fence",
    "none": "pass", "liquid": "liquid", "other": "other",
}


def family_from_export(entry: dict) -> tuple:
    """★一条导出记录 ⇒ `(判定族, why)`✗★ —— ★依据是几何 ✗ 不是名字✗★

    ★★两条纪律✗★★
      · ★`other` **必须**有 `max_height`✗★ ⇒ ★没有就**拒**（★不许猜一个✗★）
        —— ★这正是用户那句"★消费者就不许为 `other` 写特例★"的机械形态✗★ ✓
      · ★`canopy` 不由这里出✗★（★它要看标签 ✓ 混进来就破了"★物理只听碰撞★"✓★）
    """
    fam = str(entry.get("family") or "")
    if fam == "canopy":
        return None, "★`canopy` 是**语义** ✗ 碰撞看不出树冠 ⇒ 不许由导出给✗★"
    if fam not in EXPORT_FAMILY:
        return None, "★导出族不在册✗★：%r（★在册：%s✓★）" % (fam, "／".join(EXPORT_FAMILY))
    if fam == "other" and entry.get("max_height") is None:
        return None, "★`other` **必须**带 `max_height`✗★（★用户拍板 ✗ 不许让消费者写特例✓★）"
    return EXPORT_FAMILY[fam], "★几何：%s（★max_height=%s✓★）" % (fam, entry.get("max_height"))
# ★★永久禁止的来源✗★★（★铁律 3 ✗ 登记册第 3 条✗★）
#   `dshmap-blocked` ＝ ★从**地图自己的分类字母**学 ⇒ **循环**✗★（★㉜ 那次清出 14 条✓★）
#   `selftest`       ＝ ★测试自己造的 ✗ 不是世界给的✗★
SRC_FORBIDDEN = {
    "dshmap-blocked": "★循环：从地图自己的**分类字母**学 ✗ 铁律 3 永久禁止✗★",
    "selftest": "★测试自己造的来源 ✗ 不是世界给的✗★",
}


def ingest_learned(path: str = "", verbose: bool = False) -> dict:
    """★把老的"学来的"表接进知识表✗★ —— ★等级一律**查表** ✗ 禁止的来源**永久拒收**✗★

    ★老表长什么样✗★（`mapread.learn_save` 写的）：`{物种: {fam, src, at}}` ✓
    ★为什么要接✗★：★那 4 条是**已经**在影响判定的知识 ✗ 换数据源时如果不管它们 ✗
      它们会**绕过等级**继续说话✗★ ✓（★"★没迁移的旧知识★"是最容易漏的一类✓★）
    ★返回✗★：`{"accepted": n, "refused": n, "why": {...}}`（★拒收理由按来源归类 ✗ 好读✓★）
    """
    import json as _json
    import pathlib as _pl
    p = _pl.Path(path) if path else (_pl.Path(ROOT) / "logs" / "block_shapes.json")
    out = {"path": str(p), "accepted": 0, "refused": 0, "why": {}}
    if not p.is_file():
        out["why"]["★文件不在★"] = "★没有老表 ✗ 什么都不用接✗★"
        return out
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        # ★读不动就说读不动 ✗ 不许当"没有"✗★
        out["why"]["★读不动★"] = "%s: %s" % (type(e).__name__, e)
        return out
    table = d.get("shapes") if isinstance(d, dict) and "shapes" in d else d
    if not isinstance(table, dict):
        out["why"]["★形状不对★"] = "★不是 {物种: …} 这种表✗★"
        return out
    for species, ent in table.items():
        src = (ent or {}).get("src") if isinstance(ent, dict) else None
        fam = (ent or {}).get("fam") if isinstance(ent, dict) else None
        if not src:
            out["refused"] += 1
            out["why"].setdefault("★没有来源名字★", 0)
            out["why"]["★没有来源名字★"] += 1
            continue
        if src in SRC_FORBIDDEN:
            out["refused"] += 1
            k = "★永久禁止★ %s" % src
            out["why"].setdefault(k, 0)
            out["why"][k] += 1
            REFUSED.append({"species": species, "fam": fam, "level": "-",
                            "why": SRC_FORBIDDEN[src]})
            continue
        lvl = SRC_LEVEL.get(src)
        if not lvl:
            out["refused"] += 1
            k = "★来源不在册★ %s" % src
            out["why"].setdefault(k, 0)
            out["why"][k] += 1
            continue
        # ★★2026-10-18（★P1-5 连带 ✗ §79.277✗★）✗★★：★这张老表（★`mapread.learn_save` 写的
        #   `block_shapes.json`✗★）装的是**形状**✗★ ⇒ ★它是**物理**证据✗★ ⇒
        #   ★必须显式 `phys=True`✗★ —— ★不然 `experiment` 级（★`dshmap-feet`✓★）会被
        #     "★两条梯子共有 ⇒ 不许猜槽位★"那条新规矩拒掉（★而它本来该进**碰撞槽**✓★）✗★ ✓
        if put(species, fam or "?", lvl, "learned:%s" % src, phys=True):
            out["accepted"] += 1
            if verbose:
                print("   收 %-44s %-8s %s" % (species, fam, lvl))
        else:
            out["refused"] += 1
            out["why"].setdefault("★被 put 拒（升级语义／等级条款）★", 0)
            out["why"]["★被 put 拒（升级语义／等级条款）★"] += 1
    return out


def load_export(export: dict, verbose: bool = False) -> dict:
    """★把 `/dshkb` 的导出接进**碰撞槽**✗★（★等级**写死** `collision`✗★）

    ★它是**物理真值**那一级✗★ ⇒ ★只收"★过得了 `family_from_export` 的★"条目✗★ ✓
    ★拒收也要**计数并说明**✗★（★`canopy` ✗ `other` 缺 `max_height` ✗ 族不在册 ✗ 形状不对✓★）✗
    ★★它**只写碰撞槽**✗★★ ⇒ ★绝不会动那 91 条语义族✗★（★2026-10-03 拆两槽的理由✓★）✓
    """
    out = {"schema": None, "put": 0, "refused": 0, "why": {}}

    def rej(k):
        out["refused"] += 1
        out["why"][k] = out["why"].get(k, 0) + 1

    if not isinstance(export, dict):
        rej("★形状不对：不是对象★")
        return out
    out["schema"] = export.get("schema")
    blocks = export.get("blocks")
    if not isinstance(blocks, dict):
        rej("★形状不对：没有 `blocks`★")
        return out
    # ★错误计数也要**如实带出来** ✗ 不许静默✗★（★模组侧承诺 `errors=`✓★）
    if export.get("errors"):
        out["why"]["★导出自己报了错★ errors=%s" % export.get("errors")] = 1
    for species, ent in blocks.items():
        fam, why = family_from_export(ent if isinstance(ent, dict) else {})
        if not fam:
            rej("★拒：%s★" % why)
            continue
        if put(species, fam, "collision", "dshkb:%s" % (out["schema"] or "?")):
            out["put"] += 1
            if verbose:
                print("   收 %-46s %-10s %s" % (species, fam, why))
        else:
            rej("★被 put 拒（升级语义）★")
    return out


def load_all(exceptions: bool = True, export: bool = True, verbose: bool = False) -> dict:
    """★把一个进程的**知识表装齐**✗★（★例外表 ＋ 碰撞导出✗★）—— ★2026-10-04 补✗★

    ★为什么非有它不可✗★：★`TABLE`／`PHYS` 都是**内存字典** ✗ 而每个工具都是**新进程**✗★ ⇒
      ★不装的话 ✗ `kb_audit` 那样的消费者永远看到"★空表 ✗ 覆盖率 0%★"✗★ ✓
      （★这正是 2026-10-04 实测出来的：★导出已落地 ✗ 而审计还说"★不知道 16/16★"✗★）✓
    ★顺序✗★：★先例外表（★语义 ＋ 物理都有✓★）⇒ 再导出（★它只写碰撞槽 ✗ 而且**更硬** ✓
      但同级不覆盖 ⇒ 例外表里已有的 collision **照样在**✓★）✗★ ✓
    """
    out = {"exceptions": 0, "refused": 0, "export_put": 0, "export_refused": 0, "export": ""}
    if exceptions:
        try:
            import exception_table as ET
            r = ET.to_blockkb(ET.load(), sys.modules[__name__])
            out["exceptions"] = r["put"]
            out["refused"] = len(r["refused"])
            for (sp, claim, why) in r["refused"][:3]:
                if verbose:
                    print("   ★例外表拒✗★ %s %s ⇒ %s" % (sp, claim, str(why)[:60]))
        except Exception as e:
            out["refused"] = "★例外表装不动✗★ %s: %s" % (type(e).__name__, e)
    if export:
        try:
            import kb_export as KX
            p = KX.find_export("")
            if p.is_file():
                r = load_export(json.loads(p.read_text(encoding="utf-8")), verbose=False)
                out["export_put"] = r["put"]
                out["export_refused"] = r["refused"]
                out["export"] = str(p)
        except Exception as e:
            out["export"] = "★导出装不动✗★ %s: %s" % (type(e).__name__, e)
    return out


def _blacklist_fam(species: str) -> str:
    """★今天那条路（名字兜底）✗★ —— ★只做**查询** ✗ 不改它✗★"""
    return MR.shape(species)


# ★★作用域（★2026-10-04✗★）✗★★
#   ★为什么✗★：★开关是**全局**的 ✗ 而表里装着**全部**物种✗★ ⇒ ★没有作用域就**说不出来**
#     "★我只想先切某一个模组★" ✗ 一开就是全表生效✗★ ✓
#   ★口径✗★：★不设 ⇒ **全部生效**（★与今天逐字相同✓★）✗ 设了 ⇒ ★只让名单里的走表✗
#     ★名单项可以是一个命名空间（★`mysticalagriculture`✓★）✗ 也可以是一个物种
#     （★`minecraft:oak_leaves`✓★）✗★ ✓
SCOPE = [x.strip() for x in (os.environ.get("DSH_KB_SCOPE") or "").split(",") if x.strip()]


def scope_allows(species: str) -> bool:
    """★这个物种**许不许**走表✗★（★名单空 ＝ 全允许 ✓ 与今天逐字相同✓★）"""
    if not SCOPE:
        return True
    ns = species.split(":", 1)[0]
    return (species in SCOPE) or (ns in SCOPE)


_ENSURED = [False]
# ★★2026-10-18（★复核 P1-7 ✗ §79.275✗★）✗★★：★装表失败**不许静默吞**✗★ ——
#   ★真身✗★：★原来是 `except Exception: pass` ✗ 而**同一行的注释**写着
#     "★装不动不许吞成「没有」✗ 留给调用方看 `SOURCE` 与空表★"✗★ ⇒
#     ★★**注释与实现相反**✗★★ ⇒ ★`table` 档下导出一坏 ⇒ `classify()` 会把
#     "★输入坏了★"答成"★表里没有★"✗★ ✓
#   ★口径✗★：★把错误**记下来** ＋ **当场印一行醒目警告**（★一次一进程 ✗ 不刷屏✓★）✗★ ✓
LOAD_ERROR = ""


def _ensure_loaded():
    """★开关打开时**自动装一次**表✗★（2026-10-04 ✓）

    ★为什么✗★：★每个工具／测试都是**新进程** ✗ 而 `TABLE`／`PHYS` 是内存字典✗★ ⇒
      ★不自动装 ✗ 那么"★打开了开关★"的子进程里**表还是空的** ✗ 开关就是**空的**✗★ ✓
      （★这正是 2026-10-04 实测出来的第二个坑：★接线之后才发现的✓★）
    ★只在开关 != `blacklist` 时装✗★ ⇒ ★出厂档**连装都不装** ⇒ 逐字不变✗★ ✓
    ★★装表失败时（★§79.275✗★）✗★★：★把错误写进 `LOAD_ERROR` ＋ **印出来**✗★ ⇒
      ★不再"★安安静静当成表里没有★"✗★ ✓
    """
    global LOAD_ERROR
    if _ENSURED[0] or SOURCE == "blacklist":
        return
    _ENSURED[0] = True
    try:
        load_all()
    except Exception as _e:
        LOAD_ERROR = "%s: %s" % (type(_e).__name__, str(_e)[:200])
        print("★装表失败✗★（★CLASSIFIER_SOURCE=%s✗★）：%s" % (SOURCE, LOAD_ERROR))
        print("   ⇒ ★之后的 `classify()` **不可信**✗★"
              "（★`table` 档会把「输入坏了」答成「表里没有」✓★）—— 先修输入再问 ✗★")


def classify(species: str, phys: bool = False) -> dict:
    """★核心查询口✗★ —— ★每次返回都带 `level` ＋ `why` ＋ `declared`✗★（登记册第 2 条）

    ★三态开关（★`CLASSIFIER_SOURCE`✗★）★
      · `blacklist`      ：★只走名字兜底 ⇒ 与**今天逐字相同**✗★（★默认 ✓ 回滚就是它✓★）
      · `table`          ：★只查表 ⇒ 查不到就"未知归属" ✗ **不许**回落✗★（★测"表够不够"用✓★）
      · `table+fallback` ：★先查表 ⇒ 查不到回落黑名单 ✗ **并且显式声明回落了**✗★（★不静默✓★）
    ★`phys=True`✗★（★问物理✗★）：★只有 `collision` 级能说话 ✗ 标签级一律**不许**影响它✗★
    """
    _ensure_loaded()
    allowed = PHYS_LEVELS if phys else SEM_LEVELS
    if SOURCE not in VALID_SOURCES:
        return {"fam": None, "level": "unknown", "why": "★开关值不在册✗★：%s" % SOURCE,
                "declared": ["★开关值非法 ✗ 不敢猜✗★"]}
    # ★★作用域：名单外的物种**当作表里没有**✗★★（★于是 `table` 档给保守值 ✗
    #   `table+fallback` 档走老路 ✗ 回落照样声明✓★）✗★
    if not scope_allows(species):
        if SOURCE == "table":
            return {"fam": None, "level": "unknown",
                    "why": "★不在作用域内 ✗ 而开关是 `table` ⇒ 不许回落✗★",
                    "declared": ["★作用域外（★明说没回落✓★）★"]}
        fam0 = _blacklist_fam(species)
        return {"fam": fam0, "level": "name_fallback",
                "why": "★不在作用域内 ⇒ 走老路★ ⇒ %s" % fam0,
                "declared": ["★作用域外 ✗ 回落到**名字兜底**（★TEMPORARY✓★）★"]}
    # ★★物理查**碰撞槽** ✗ 语义查**语义槽**✗★★（★两个字典 ✗ **不可能**互相覆盖✓★）
    slot = PHYS if phys else TABLE
    ent = slot.get(species)
    if SOURCE in ("table", "table+fallback") and ent and ent["level"] in allowed:
        return {"fam": ent["fam"], "level": ent["level"],
                "why": "★表里★ %s（%s）" % (ent["level"], ent["src"]),
                "declared": (["★TEMPORARY ✗ 复核触发：%s★" % ent["trigger"]]
                             if ent.get("temporary") else [])}
    if SOURCE == "table":
        return {"fam": None, "level": "unknown",
                "why": "★表里没有 ✗ 而开关是 `table` ⇒ 不许回落✗★",
                "declared": ["★未知归属（★明说没回落 ✓ 铁律 1 所以物理不受影响✓★）★"]}
    # blacklist 或 table+fallback 的回落那一段
    fam = _blacklist_fam(species)
    decl = ["★回落到**名字兜底** ✗ 这一级是 TEMPORARY✗★"
            "（★复核触发：★阶段 4 按种切换完成 ✗ 见 ㊲✓★）"]
    return {"fam": fam, "level": "name_fallback",
            "why": "★名字兜底★ ⇒ %s（★不是注册表 ✗ 也不是碰撞形状✓★）" % fam,
            "declared": decl}


def is_floor(species: str, legacy=MR.is_floor) -> bool:
    """★与 `mapread.is_floor` **同签名**✗★（★上层零改动的那条要求✓★）

    ★注意✗★：`is_floor` 是**物理/几何**问题 ⇒ ★默认走"碰撞形状"那条 ✗ 而今天还没有碰撞数据
      ⇒ ★在拿到之前它**只能**等于老路 ✗ 这件事**写在 `declared` 里**✗ 不许假装已经换了✗★ ✓
    """
    return bool(legacy(species))


def blocks_space(species: str, legacy=MR.blocks_space) -> bool:
    """★与 `mapread.blocks_space` 同签名✗★（★同上：★今天只能等于老路 ✗ 且如实声明✓★）"""
    return bool(legacy(species))


def report(limit: int = 8) -> str:
    """★给人看的一页✗★（★开关 ✗ 表里几条 ✗ 被拒收几条 ✗ 为什么✓★）"""
    lines = ["★blockkb 现状✗★：开关 `CLASSIFIER_SOURCE=%s` ｜ 表里 %d 条 ｜ 拒收 %d 条"
             % (SOURCE, len(TABLE), len(REFUSED))]
    for s, e in list(TABLE.items())[:limit]:
        lines.append("   %-44s %-8s %-14s %s" % (s, e["fam"], e["level"], e["src"]))
    for r in REFUSED[:limit]:
        lines.append("   ★拒收✗★ %-38s %s" % (r["species"], r["why"]))
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())


# ══ ★★政策层（★2026-10-05 ✗ 用户裁定 (a)✗★）✗★★ ═════════════════════════════════════
#   ★用户原话（★按原意记✓★）✗★：★"(a): is_floor 说真话（树叶物理可站）＋
#     规划层另立规则「不把树冠当落脚点」"✗★ ✓
#   ★★为什么非要分两层✗★★：★铁律 1 说"★物理只听碰撞形状★"✗ ★⇒ `is_floor(树叶)`
#     在切换档下**必须**是 **True**✗（★碰撞真值说顶面实心 ✓ 世界实测也站得住✓★）✗★
#     ★可**规划**不该往树冠上走✗★ ⇒ ★不是矛盾 ✗ 是**两个问题**✗★：
#     ★"★能不能站★"（★物理✗★）／"★该不该去★"（★政策✗★）✗★ ✓
#   ★为什么只读**语义槽**✗★：★"★它是树冠★"是**归属语义** ✗ 标签说了算✗★ ⇒
#     ★物理那条一个字不改 ✗ 政策只读 TABLE（★语义✓★）⇒ ★两条铁律都不破✗★ ✓
CATEGORY = {}
_CAT_LOADED = [False]

# ★★语义类别 ⇒ 几何族：**只声明有裁定的那几行**✗★★（★2026-10-05✗★）
#   ★为什么只一行✗★：★§79.143 实测——标签侧的 **33 个类别**（★`叶子`／`门`／`半砖`…✓★）
#     与导出侧的 **8 个几何族**（★`full`／`slab`…✓★）**不是一种话**✗★ ⇒
#     ★把它们"★顺理成章★"地对应起来 ✗ 正是"★假的 0%★"那类事的来源✗★ ✓
#   ★⇒ 只声明**有出处 ＋ 有裁定**的那些 ✗ 其余**一律未声明**✗★ ⇒
#     ★未声明 ⇒ **不影响物理／规划**✗（★铁律 1：★缺失一律未知归属 ✗ 永不影响物理✓★）✗★ ✓
# ★★政策类声明✗★★：★语义**专属** ✗ 它**不声称几何**✗★ ⇒ ★永不拿去和碰撞族比✗★ ✓
POLICY_CATEGORY = {
    # ★用户裁定 (a)✗★：★"★不把树冠当落脚点★"✗ ⇒ ★`叶子` 这一类在**政策层**算树冠✗★
    "叶子": "canopy",
}

# ★★几何类声明✗★★：★它**声称**一个几何族 ✗ 于是**可以**和碰撞真值核验✗★ ✓
#   ★只声明**无歧义**的（★"★半砖★"这个标签名声称的就是 slab 形状 ✓★）✗
#   ★拿不准的**一律不写**✗（★写了才叫声明 ✗ 猜的就叫猜✗★）✓
GEOMETRIC_CATEGORY = {
    # ★★每条都是**实测单一族 100%**✗★★（★`tmp/measure_cat_fam.py` 全量数出来的 ✓
    #   计数就写在行尾 ✗ 就是证据 ✗ 见 §79.146✓★）✗★
    # ★**不**声明的（★实测不到 100%✗★）✗★：`门` 96% ✗ `楼梯` 93% ✗ `墙` 68% ✗
    #   `可挖` 83% ✗ `压力板` 98% ✗ `按钮` 99% ✗ —— ★差一个百分点就是**假声明**✗★ ✓
    "原木": "full",          # ★971/971 全中（★实测✓★）★
    "活板门": "snow_layer",         # ★632/632 全中（★实测✓★）★
    "半砖": "slab",          # ★581/581 全中（★实测✓★）★
    "栅栏": "fence_15",          # ★342/342 全中（★实测✓★）★
    "玻璃": "full",          # ★336/336 全中（★实测✓★）★
    "花盆": "snow_layer",          # ★106/106 全中（★实测✓★）★
    "地毯": "snow_layer",          # ★33/33 全中（★实测✓★）★
    "珊瑚": "none",          # ★30/30 全中（★实测✓★）★
    "花": "none",           # ★24/24 全中（★实测✓★）★
    "可替换": "liquid",         # ★22/22 全中（★实测✓★）★
    "羊毛": "full",          # ★16/16 全中（★实测✓★）★
    "木板": "full",          # ★6/6 全中（★实测✓★）★
}

# ★兼容旧名（★§79.144 的 J6 用它 ✗ 保留免得判据红在一个改名上✗★）
CATEGORY_TO_FAMILY = POLICY_CATEGORY


def load_categories():
    """★把"★物种 ⇒ 标签类别★"缓存读进来✗★（★**与开关无关** ✗ 它是语义层✓★）"""
    import json as _json
    if _CAT_LOADED[0]:
        return CATEGORY
    _CAT_LOADED[0] = True
    import pathlib as _pl
    p = _pl.Path(__file__).resolve().parent.parent / "state" / "tags_category.json"
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return CATEGORY
    for sp, v in (d.get("categories") or {}).items():
        if isinstance(v, dict):
            CATEGORY[sp] = v
    return CATEGORY


def category_of(species: str):
    """★它的**标签类别**✗★（★"★它属于哪一类归属★"✗ ✗ 不是几何族✓★）✗★"""
    load_categories()
    v = CATEGORY.get(species)
    return v.get("cat") if isinstance(v, dict) else None


def category_evidence(species: str) -> str:
    """★这个类别的**出处标签 id**✗★（★审计用 ✓ 没出处就空串✓★）"""
    load_categories()
    v = CATEGORY.get(species)
    return (v.get("tag") or "") if isinstance(v, dict) else ""


def is_canopy(species: str) -> bool:
    """★它是不是**树冠**✗★ —— ★问的是**标签类别**（★`叶子`✓★）✗ **不是**几何族✗★ ✓"""
    return category_of(species) == "叶子"


def is_landing_spot(species: str) -> bool:
    """★能不能把它当**落脚点**✗★（★＝物理上能站 **且** 政策上不去✗★）✗★

    ★这是**规划层**该问的那个问题✗★（★`is_floor_fam` 是物理层的问题 ✓ 两者都要存在✓★）✗★
    ★物理那一半走**碰撞槽**（★`classify(phys=True)`✓★）✗ 政策那一半走**语义槽**✗★ ✓
    """
    r = classify(species, phys=True)
    fam = r.get("fam")
    if not fam:
        return False
    return is_floor_fam(fam) and not is_canopy(species)
