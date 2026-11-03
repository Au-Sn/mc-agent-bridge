#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mapread.py —— ★地图读取（中间层）★ ✓ 用**已有的** dshscan 就把图建出来 ✓

## 为什么这么写 ✗（先量再设计 ✓ 纪律① ✓ 实测 2026-09-23 ✓）

| 量的事 | 实测 | 结论 |
|---|---|---|
| 一次 1x1 方块读取 | 中位 **0.617 s** | 逐格探测 = 一格 0.6 秒 ✗ 29x29 要 8 分钟 ✗ |
| 一次 41x21x41 大盒子扫描 | **1.42 s**（模组内部 `us=560` ✓） | 贵的是**往返** ✗ 不是扫描 ✓ |
| `dshscan ... "kind" 1000 1` | `matched=248 shown=248` **一次给全** ✓ | ★按方块种类批量取坐标★ ✓ |
| 翻页 `page=2/3` | 坐标确实不同 ✓ | 收不完可以翻页 ✓ |
| `#tag` 查询（`#minecraft:mineable/shovel`） | `matched=1023 shown=1000` ✓ | 一次能拿 1000 个坐标 ✓ |

⇒ 于是**建图不用逐格** ✓：**先拿这一片的方块种类清单**（不带 match 的那次回执里就有 `counts[...]` ✓）
  ⇒ **每种一次调用**（拿回它所有坐标 ✓）⇒ 每个 (x,z) 柱子里**最高的那个**就是地表 ✓

实测成本 ✓：29x29x15 那片 61 种 ⇒ 查 top-N 种 ⇒ **二十几次调用 ≈ 20 秒** ✓
（对比逐格 504 秒 ✓ ⇒ 快两个数量级 ✓）并且**结果落盘缓存** ✓ 第二次读同一片 ≈ 0 ✓

## 诚实的边界 ✗（必须写出来 ✓ 免得以后自己骗自己 ✓）
  · `counts[...]` 只列 **top-40** 种 ✓ ⇒ 更稀有的种类**可能漏** ✗ ⇒
    所以 `Map.unknown` 会记"这一柱子里一个已知方块都没有"的格子 ✓ 并且 `verify()` 可以抽查复核 ✓
  · 只读**已加载的区块** ✓（没加载的地方扫出来是空气 ✓ 不是"真的没有"✗）
  · 这是一张**快照** ✓ 建图之后世界会变 ✓ ⇒ 每次带 `max_age` 用 ✓ 过期就重建 ✓
"""
from __future__ import annotations

import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

CACHE = ROOT / "logs" / "map_cache"
KV = re.compile(r"(\w+)=(\S+)")
CJK = re.compile(r"[^\x00-\x7f]")

# ★什么是"地板"★ ✗（2026-09-23 实测撞出来的大坑 ✓）
#   第一版把"柱子里最高的方块"一律当地板 ✓ ⇒ 小麦/草/火把/树叶/栅栏全被当成地板 ✗
#   表现 ✗：规划出的航点落在**庄稼顶上** ✓ ⇒ 模组走过去站不住 ⇒ 一步 0.3 格地挣扎 ✗
#     （实测：12 格的一段路走了 **37 条腿 / 211 秒** ✗）
#   ⇒ 所以"能站"必须要求：**最高的那个是真正能踩的实心方块** ✓
#   ★用黑名单★ ✓（不能白名单：ATM9 有几百种模组方块 ✓ 白名单会把正常地板也挡掉 ✗）
NON_FLOOR_EXACT = {
    "minecraft:air", "minecraft:cave_air", "minecraft:void_air",
    "minecraft:grass", "minecraft:tall_grass", "minecraft:fern", "minecraft:large_fern",
    "minecraft:dead_bush", "minecraft:water", "minecraft:lava", "minecraft:fire",
    "minecraft:snow", "minecraft:vine", "minecraft:scaffolding",
}
NON_FLOOR_SUB = (
    "_plant", "sapling", "flower", "petal", "torch", "lantern", "candle", "crop",
    "wheat", "carrot", "potato", "beetroot", "melon_stem", "pumpkin_stem", "stem",
    "_leaves", "fence", "_wall", "door", "trapdoor", "carpet", "button", "lever",
    "rail", "sign", "banner", "kelp", "seagrass", "lily_pad", "mushroom", "bush",
    "berry", "azalea", "chain", "ladder", "cake", "composter", "hopper",
    "pressure_plate", "tripwire", "cobweb", "sugar_cane", "bamboo", "cactus",
    "water", "lava", "bubble", "_air", "snow_layer", "dripstone", "amethyst_cluster",
)



# ★★§79.452✗★★：★**通用判据 —— 导出优先**✗★
#   ★为什么✗★：★下面的 `NON_FLOOR_*`／`BLOCKING_SUB` 是**黑名单**✗★
#     ★没列出的模组植物／花／毯就会被当成"★地板★"✗ ⇒ ★**换包就要重来**✗★ ✓
#   ★现在✗★：★**导出里有它**（★24779 条 ✗ 覆盖所有模组✗★）⇒ ★**只看碰撞高**✗★
#     能踩 ✗ `0.45 ≤ h ≤ 1.05`（★整块 ＋ 半砖 ✓ 花 0 ✗ 雪层 0.125 ✗ 栅栏 1.5 全排除✗★）
#     挡人 ✗ `h ≥ 0.45`（★有实体碰撞就挡 ✗ 花 0 不挡✓★）
#   ★导出里没有**（★未知名字 ★地图字母之类✗★）⇒ ★**才**走老名单 ✗ 并计数（★可观测✗★）✗★ ✓
_FALLBACK_USED = {"floor": 0, "space": 0}


def _export_h(block: str):
    """★从导出查碰撞高 ✗ 没有 ⇒ None（★不猜✗★）✗★

    ★★§79.452✗★★：★**只在 `SOURCE == "export"` 时启用**✗★
      ★`blacklist` 档必须"★与老路逐字相同★"（★`kb_switch_test` S1 守的就是这条✗★）✗★
      ★`table`／`table+fallback` 走知识表 ✗ **不看导出**（★那是另一条路✗★）✗★ ✓
    """
    try:
        import blockkb as _KB
        if getattr(_KB, "SOURCE", "blacklist") != "export":
            return None                 # ★其它档 ⇒ 不走导出（★开关语义不变✗★）✗★
    except Exception as e:              # ★不许静默✗★
        print("★mapread 读 SOURCE 失败：%r✗★" % (e,), file=sys.stderr)
        return None
    try:
        import world3d as _W3
        _W3._load_h3d()
        mp = _W3._H3D.get("map") or {}
        v = mp.get((block or "").lower())
        return None if v is None else float(v)
    except Exception as e:              # ★不许静默✗★
        print("★mapread 查导出失败：%r✗★" % (e,), file=sys.stderr)
        return None


def _has_be(block: str) -> bool:
    """★这个方块**有没有方块实体**✗★（★机器/箱子/熔炉… 的硬信号 ✗ 不看名字✓★）

    ★数据来源✗★：★导出快照的 `has_block_entity`（★§79.486 ✗ 4570/24779 = 18.4%✗★）✗
    ★读不到 ⇒ 回 False**（★保守 ✗ 不许凭空说"是机器"✗★）✗★
    """
    try:
        import blockkb as _KB
        if getattr(_KB, "SOURCE", "blacklist") != "export":
            return False          # ★其它档不看导出（★开关语义不变✗★）✗★
        import world3d as _W3
        _W3._load_h3d()
        return bool((_W3._H3D.get("has_be") or {}).get((block or "").lower()))
    except Exception as e:        # ★不许静默✗★
        print("★mapread 查 has_block_entity 失败：%r✗★" % (e,), file=sys.stderr)
        return False


def machine_family(block: str) -> str:
    """★语义族「机器」✗★ —— ★有方块实体 ⇒ "机器" ✗ 否则回空串✗★

    ★为什么必须先有这个✗★：★大脑要能**问**"★这是不是机器✗ 能不能右键✗★"✗
      ★在此之前 ✗ 4570 个机器**一个都问不出来**（★只能靠名字猜 ✗ 违反普适性✗★）✗★ ✓
    """
    return "机器" if _has_be(block) else ""


def is_floor(block: str) -> bool:
    """这个方块能不能**踩**（真正站上去）✓ —— 不是"最高的那个"就算 ✓

    ★★§79.452✗★★：★**导出优先**（★碰撞高判 ✗ 不看名字✗★）✗ 导出里没有 ⇒ 老名单兜底✗★ ✓
    """
    b = (block or "").lower()
    if not b:
        return False
    _h = _export_h(b)
    if _h is not None:
        # ★半砖(0.5) 能踩 ✗ 整块(1.0) 能踩 ✗ 花(0)／雪层(0.125)／栅栏(1.5) 不能✗★
        return 0.45 <= _h <= 1.05
    _FALLBACK_USED["floor"] += 1
    if b in NON_FLOOR_EXACT:
        return False
    for k in NON_FLOOR_SUB:
        if k in b:
            return False
    return True


# ★"占不占地方"★ ✗（与 is_floor 分开 ✓ 2026-09-23 ✓）
#   为什么必须分开 ✗：模组判"站得下吗"用的是**碰撞箱** ✓（`standable` ✓）
#     · 小麦/草/火把/花：**没有碰撞箱** ⇒ 站在那一格里是**可以的** ✓
#     · 树叶/栅栏/墙/门/玻璃：**有碰撞箱** ⇒ 那一格站不了 ✓
#   我第一版把"凡不是地板"都当"占地方" ✗ ⇒ 假人站在**麦田里**时 ⇒ 它的格子被判成"站不住"✗
#     ⇒ 表现：连通区域**算出来是空的** ✗（而验收脚本还"通过"了 ✗ 见 M4a 的空集陷阱 ✓）
#   ⇒ 近似（地图里只有方块名 ✓ 没有形状 ✗）：**会挡人的那些**用名字认出来 ✓
BLOCKING_SUB = ("_leaves", "fence", "_wall", "door", "trapdoor", "glass", "pane",
                "_slab", "stairs", "iron_bars", "scaffolding", "cactus", "chest",
                "barrel", "furnace", "hopper", "log", "wood", "planks", "stone",
                "dirt", "sand", "gravel", "obsidian", "_ore", "bricks", "concrete")


# ══ ★★知识表接线（★2026-10-04✗★）✗★ ═════════════════════════════════════════════
#   ★为什么✗★：★`CLASSIFIER_SOURCE` 三态开关原来**没有任何真实判定路径在用**✗★ ——
#     ★实测：`import blockkb` 的九处**全是我新写的工具** ✗ `mapread` 一次都没查表✗★ ⇒
#     ★"★按种切换★"是**空的** ✗ 打开开关也什么都不变✗★ ✓
#   ★口径（★写死 ✗ 违反即退回✗★）✗★
#     · ★`blacklist`（★出厂✓★）⇒ **一个字节都不变**✗★（★连表都不看✓★）
#     · ★`table`／`table+fallback` ⇒ ★**碰撞槽有它** 就用**碰撞**结果✗★
#       ✗ 没有 ⇒ ★按档回落 ✗ 而回落**已经在 `declared` 里写明**✗★ ✓
#     · ★★只看**碰撞槽**✗★★：★语义槽（★标签✓★）**永不许**影响物理 ✗ 铁律 1✗★ ✓
def _kb_phys(block: str):
    """★问知识表的**碰撞槽**✗★ ⇒ 三态字符串✗★

    ★★返回三态（★这是"★三档分清★"的关键✗★）✗★★
      · ★`(fam, "collision")`✗★   ：★表里有 ✗ 就听它的✗★
      · ★`(None, "fallback")`✗★  ：★`table+fallback` 档 ＋ 表里没有 ⇒ 走老路✗★
      · ★`(None, "unknown")`✗★   ：★`table` 档 ＋ 表里没有 ⇒ **不许回落**✗★
    ★★"★未知时取哪一侧★"是**安全策略** ✗ 写死在调用点✗★★
      · `blocks_space` 未知 ⇒ **True**（★别往不认识的方块里走✓★）
      · `is_floor`    未知 ⇒ **False**（★别站在不认识的方块上✓★）
    """
    try:
        import blockkb as _KB
    except Exception:
        return None, "unknown"
    # sec 79.457: `export` must behave exactly like `blacklist` here. The export only
    #   supplies the PHYSICAL collision height (mapread asks it separately); the
    #   semantic/tag side keeps using the old tables. Without this, export fell through
    #   to (None, "unknown"), which makes is_floor() return False early.
    if _KB.SOURCE in ("blacklist", "export"):
        return None, "blacklist"        # ★出厂档／导出档 ⇒ 语义侧不介入✗★
    r = _KB.classify(block, phys=True)
    lv = r.get("level")
    if lv == "collision" and r.get("fam"):
        return r["fam"], "collision"
    if _KB.SOURCE == "table+fallback":
        return None, "fallback"         # ★这一档**允许**回落（★已声明✓★）
    return None, "unknown"              # ★`table` 档 ⇒ **不许**回落✗★



def _kb_canopy(block: str) -> bool:
    """★"★它是树冠★" —— 问**标签类别**（★`叶子`✓★）✗ 读不到就按**不是**✗★（★保守✗★）

    ★为什么不吞异常当"★是★"✗★：★读不到 ⇒ 按**不是树冠** ⇒ `is_landing` 退回 `is_floor`✗★
      ⇒ ★行为与今天一致**而不是**凭空拦人 ✗ 这是**安全的那一侧**✗★ ✓
    """
    try:
        import blockkb as _KB
        return bool(_KB.is_canopy(block))
    except Exception:
        return False


def is_landing(block: str) -> bool:
    """★能不能把它当**落脚点**（★**规划**问的那个问题✗★）✗★

    ★＝`is_floor`（★物理：能不能站✓★）**且** 不是**树冠**（★政策：该不该去✓★）✗★ ✓
    ★用户裁定 (a)✗★：★"★`is_floor` 说真话 ＋ 规划层另立规则「不把树冠当落脚点」★"✗★ ✓
    ★而"★它是树冠★"只从**标签类别**（★`叶子`✓★）来 ✗ 不从几何来✗★ ✓
    """
    return is_floor(block) and not _kb_canopy(block)


def blocks_space(block: str) -> bool:
    """这一格的方块**会不会把人挡住** ✓ —— 由**形状家族**推出 ✓（不再按名字穷举 ✗）

    ★用户点的方向★ ✓（2026-09-23 ✓ 原话：**"除栅栏一类非完整方块和正常方块，以此建立障碍情况"**✓
      "无需要标明所有方块位置"✓）：
      以前我列了两张名字表（`is_floor` ✓ `NON_FLOOR_SUB` ✗）⇒ 每遇到一个模组方块就要补名字 ✗
        ⇒ 实测被 `mcwfences:…_wall` 冤枉过 ✓（它其实挡人 ✓ 但我把它当"能穿过"✗）
      ⇒ 现在改成**先按家族归形状** ✓ 再按形状定"踩/挡/穿" ✓：
        · `full`（正常完整方块 ✓）· `slab`（台阶/半砖/雪层/耕地…：**能踩、也挡** ✓）
        · `fence`（栅栏/墙/栏杆/玻璃板/锁链…：**挡人** ✓ 不是好地板 ✓）
        · `machine`（箱子/桶/熔炉…：**挡人、能踩** ✓）· `canopy`（树叶：挡人 ✓ 不当路 ✓）
        · `pass`（草/花/火把/庄稼/铁轨/地毯…：**不挡** ✓ 能穿过去 ✓）
        · `air` / `liquid` / `other`（认不出的归 other ⇒ **当挡**✓ 保守 ✓ 并在日志里留名 ✗）
    """
    _f, _how = _kb_phys(block)
    # ★★§79.452✗★★：★blocks_space 走导出**（★有实体碰撞就挡人 ✗ 不看名字✗★）✗★
    _h2 = _export_h(block)
    if _h2 is not None:
        return _h2 >= 0.45          # 花 0 ✗ 雪层 0.125 ⇒ 不挡 ✗ 半砖 0.5 ✗ 整块 ⇒ 挡
    # ★★§79.486 修正✗★★：★**识别（是不是机器）与挡人（有没有碰撞）是两件事**✗★
    #   ★数据实测✗★：★882 个带方块实体但 `max_height=0` 的方块 ✗
    #     ★例如 `ae2:cable_bus`（线缆总线）／`amendments:ceiling_banner_*`（天花板旗帜）✗
    #     导出里它们是 **`"empty": true`**（★真的没有碰撞箱✗★）⇒ ★**必须能穿过去**✗★ ✓
    #   ★所以这里**只信物理** ✗ 机器身份由 `machine_family()` 单独回答 ✓
    #   （★大脑同时拿到"★是机器★"和"★没碰撞★" ⇒ 知道"★能穿过去 ✗ 但能右键★"✗★）✓
    _FALLBACK_USED["space"] += 1
    if _f:
        import blockkb as _KB
        return _KB.blocks_space_fam(_f)
    if _how == "unknown":
        return True                  # ★未知 ⇒ 保守：当作挡住（★别往不认识的方块里走✓★）
    return shape(block) in ("full", "slab", "fence", "machine", "canopy", "other")


# ── ★形状家族分类（用户点的方向 ✓ 一份实现 ✓）★ ─────────────────────────────
CANOPY_SUB = ("_leaves",)
FENCE_SUB = ("fence", "_wall", "wall_", "pane", "iron_bars", "chain", "ladder",
             "scaffolding", "cobweb", "bars", "trapdoor", "door")
SLAB_SUB = ("_slab", "stairs", "snow", "carpet", "path", "farmland", "soul_sand",
            "dirt_path", "pressure_plate", "composter", "cauldron")
MACHINE_SUB = ("chest", "barrel", "furnace", "smoker", "hopper", "anvil", "crafting_table",
               "sieve", "crucible", "machine", "tank", "generator", "crusher", "press",
               "computer", "monitor", "modem", "drive", "printer", "turtle", "vault",
               "reactor", "cable", "pipe", "duct")
PASS_SUB = ("_plant", "sapling", "flower", "petal", "torch", "lantern", "candle", "crop",
            "wheat", "carrot", "potato", "beetroot", "_stem", "rail", "lever", "button",
            "sign", "banner", "kelp", "seagrass", "lily_pad", "mushroom", "bush", "berry",
            "azalea", "vine", "tripwire", "sugar_cane", "bamboo", "air", "water", "lava",
            "bubble", "dripstone", "amethyst_cluster", "moss", "roots", "sprouts", "dust",
            "redstone_wire", "fire", "soul_fire", "light", "string",
            # ★★2026-10-03 检修补✗★★（欠账 ㉜）：★"认不出的当挡"是**保守** ✗ 但会**冤枉装饰类**✗★
            #   ★实测✗★：`supplementaries:book_pile_horizontal`（★一摞书✓★）被归 `other`
            #     ⇒ 地图打 `#` ✗ 而世界明明能站（★脚下是它 ✗ 头层是空气✓★）
            #     ⇒ `route_verify_test` 的 X1 当场抓住这个不一致 ✓
            #   ★口径✗★：★家族词按**形状**补 ✗ 不按模组名穷举✗★ ✓（★一摞／一层／一张 这类
            #     薄片装饰 ✓ 归 `pass`：**不挡人**✓★）
            "_pile", "pile", "_sheets", "sheet", "_layers", "_envelope", "envelope",
            "_present", "_stack", "_books", "_paper", "_post", "_plaque")
LIQUID_SUB = ("water", "lava")


# ★"同名不同命"的那几个必须**整名判**★ ✗（2026-09-23 ✓）
#   坑 ✓：`minecraft:grass`（草 ✓ 植物 ✓ 能穿过 ✓）与 `minecraft:grass_block`（草方块 ✓ 完整方块 ✓）
#     差一个 `_block` ✗ ⇒ 只按子串 "grass" 判 ⇒ 两个会被归成同一族 ✗（实测被判错过 ✓）
EXACT_PASS = {"minecraft:grass", "minecraft:tall_grass", "minecraft:fern",
              "minecraft:large_fern", "minecraft:dead_bush", "minecraft:sugar_cane",
              "minecraft:nether_sprouts", "minecraft:sea_pickle"}


# ★★"学来的形状"：从**碰撞箱**学，不从名字猜★★ ✗（2026-09-28 第 21 轮 ✓ 治 §38.5 ✓）
#   为什么必须有 ✗（实测 ✓）：`shape()` 是**按名字**的子串匹配 ✗ ⇒ 不认识的模组方块
#     一律落到最后那句 `return "full"` ✗ ⇒ **两种假话都会出** ✓：
#       · `ars_elemental:spore_blossom_up`（装饰植物 ✓）⇒ 被当**实心** ✗ ⇒ **假障碍** ✗
#       · `mcwfurnitures:mangrove_stool_chair`（家具 ✓）⇒ 被当**不当地板** ✗ ⇒ **假"没地板"** ✗
#   真值在哪 ✗：**模组按碰撞箱判的那两样** ✓ —— 而它们**正在我的回执里** ✓ 白拿 ✓：
#     · `/dshmap` 的**字母格** ⇒ 模组说"这一层的**地板**是它" ✓ ⇒ 学成**能踩** ✓
#     · `/dshmap` 的 **`b<z>|` 行** ⇒ 模组说"**你这一层被它占着**" ✓ ⇒ 学成**实心/挡人** ✓
#   ⇒ 学来的表**优先于**名字猜测 ✓（它是碰撞箱 ✓ 名字只是猜 ✗）
LEARNED_FILE = ROOT / "logs" / "block_shapes.json"
LEARNED: dict = {}
_LEARN_DIRTY = [0]

# ★★"验过的框"要**跨地图**记住★★ ✗（2026-09-29 第 26 轮 ✓ 实测白扫过一次 ✗）
#   现象 ✗：同一目标连问两次 ⇒ `#1 verify-calls=1 ｜ #2 verify-calls=1` ✗
#     ⇒ "同一个框不重复扫"**只在同一张地图对象里有效**✗
#     而两次调用之间假人一动 ⇒ 图框变 ⇒ **地图被重建** ⇒ 新图的 `meta` **不记得**验过哪些框 ✗
#   为什么要 TTL ✗：世界会变（挖了/放了/别的人动了 ✓）⇒ 永久信 = 拿旧真值当新真值 ✗
#     ⇒ 只信 **`VERIFIED_TTL` 秒内**验过的框 ✓（默认 300 秒 ✓ 与地图缓存同量级 ✓）
VERIFIED_FILE = ROOT / "logs" / "verified_boxes.json"
VERIFIED_TTL = 300.0
_VERIFIED: list = []          # [["x0,y0,z0,x1,y1,z1", epoch], ...] ✓


def _vb_load() -> None:
    try:
        if VERIFIED_FILE.is_file():
            rec = json.loads(VERIFIED_FILE.read_text(encoding="utf-8"))
            for it in (rec.get("boxes") or []):
                if isinstance(it, list) and len(it) == 2:
                    _VERIFIED.append([str(it[0]), float(it[1])])
    except Exception as e:
        # 记录（§79.401 那一族）：数据表读坏了不许静默当成"空表"
        print("[记录] 已验证框表读不到（当作空表，会多扫）：%s: %s"
              % (type(e).__name__, str(e)[:80]), file=sys.stderr)


def vb_note(box, when: float | None = None) -> None:
    """记下"这个框验过了" ✓（**跨地图** ✓ 带时间 ✓ 供 TTL 用 ✓）"""
    key = "%d,%d,%d,%d,%d,%d" % tuple(int(v) for v in box)
    now = float(when if when is not None else time.time())
    _VERIFIED.append([key, now])
    del _VERIFIED[:-64]                    # 只留最近 64 条 ✓（别把文件撑大 ✗）
    try:
        VERIFIED_FILE.parent.mkdir(parents=True, exist_ok=True)
        VERIFIED_FILE.write_text(json.dumps({"boxes": _VERIFIED}, ensure_ascii=False),
                                 encoding="utf-8")
    except Exception:
        pass


def vb_covered(box, ttl: float = VERIFIED_TTL) -> bool:
    """★这个框是不是**最近验过**的★ ✓（跨地图 ✓ 有时间窗 ✓）

    ★必须按"**包含**"判 ✗（与 `Map.box_verified` 同一条理由 ✓）：
      有重叠就算 ⇒ 新框边缘仍是推的 ✗ ⇒ "一半真一半假" ✗ 最难查 ✓
    """
    x0, y0, z0, x1, y1, z1 = (int(v) for v in box)
    now = time.time()
    for (key, when) in _VERIFIED:
        if (now - float(when)) > float(ttl):
            continue
        try:
            a, b, c, d, e, f = (int(v) for v in key.split(","))
        except Exception:
            continue
        if a <= x0 and b <= y0 and c <= z0 and x1 <= d and y1 <= e and z1 <= f:
            return True
    return False


_vb_load()


def _learn_load() -> None:
    try:
        if LEARNED_FILE.is_file():
            rec = json.loads(LEARNED_FILE.read_text(encoding="utf-8"))
            for k, v in (rec.get("shapes") or {}).items():
                if isinstance(v, dict) and v.get("fam"):
                    LEARNED[k] = v
    except Exception as e:
        # 记录（§79.401 那一族）：学到的形状表读坏了 ⇒ 悄悄退回名字猜（判据会假绿）
        print("[记录] 学到的形状表读不到（退回名字猜）：%s: %s"
              % (type(e).__name__, str(e)[:80]), file=sys.stderr)


def learn_shape(block: str, fam: str, src: str) -> bool:
    """★把一条"模组说的事实"记下来★ ✓ 返回 True ⇒ **这条改变了判断**（值得落盘 ✓）

    只在**真的改变了结论**时才写 ✗（不然每建一次图都刷一遍盘 ✗ 而且日志会脏 ✓）
    """
    b = (block or "").lower()
    if not b or b in ("minecraft:air", "") or b.endswith(":?"):
        return False
    old = LEARNED.get(b, {}).get("fam")
    guess = _shape_by_name(b)
    if old == fam:
        return False
    LEARNED[b] = {"fam": fam, "src": src, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _LEARN_DIRTY[0] += 1
    # ★"改了结论"= 要么以前没记过、要么这次的真值与**名字猜的**不一样 ✓
    return (old is None and guess != fam) or (old is not None and old != fam)


def learn_save(force: bool = False) -> int:
    """落盘 ✓（`force=False` 时只在有改动时写 ✓）"""
    if not force and not _LEARN_DIRTY[0]:
        return 0
    try:
        LEARNED_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEARNED_FILE.write_text(json.dumps(
            {"note": "★从模组碰撞箱学来的方块形状 ★（不按名字猜 ✗）；每条的 src 写明出处 ✓",
             "shapes": LEARNED}, ensure_ascii=False, indent=1), encoding="utf-8")
        n = _LEARN_DIRTY[0]
        _LEARN_DIRTY[0] = 0
        return n
    except Exception:
        return 0


def _tok_match(b: str, k: str) -> bool:
    """★短关键词必须**按词**匹配★ ✗（2026-09-28 第 21 轮 ✓ 实测抓到的同类坑 ✓）

    现场 ✗：`mcwfurnitures:mangrove_stool_chair`（家具 ✓）被判成 **`pass`**（能穿过去 ✗）
      真因 ✓：`PASS_SUB` 里有 `"air"` ✗ 而 **`ch|air|` 含 `air`** ✗ ⇒ 子串一撞就中 ✗
      ★与 `wheat` vs `wheat_seeds` **同一族**✓（P105 ✓）：**短词做子串匹配必然误伤**✗
    口径 ✓：**≥6 字**的照样按子串（`furnace` ✓ `crafting_table` ✓ 够长不会误伤 ✓）；
            **≤5 字**的按"**下划线分词后的整词**"匹配 ✓（`cave_air` ⇒ 词 `air` ✓ 命中 ✓；
              `chair` ⇒ 词 `chair` ✓ **不命中** ✓）
    """
    # ⚠ 关键词**先去掉两头的下划线**✗（`"_slab"` / `"_leaves"` / `"wall_"` ✓）
    #   不然"按词匹配"会把它们全部 miss 掉 ✗ —— 我第一版就栽在这 ✓（`oak_slab` 被判 full ✗）
    k2 = k.strip("_")
    if not k2:
        return False
    if len(k2) >= 6:
        return k2 in b
    # ★短词：先"整词"，再"**词前缀**"★ ✗（2026-09-28 第 21 轮 ✓）
    #   为什么要前缀 ✓：`pink_petals` 的词是 `petals` ✗ 而关键词是 `petal` ✗ ⇒ 整词比会 miss ✗
    #   ★为什么不会退回误伤★ ✓：`chair` 是**整词** ✗ ⇒ `"chair".startswith("air")` = False ✓
    #     （误伤的根源是"**任意位置子串**"✓ 只看词首就安全了 ✓）
    toks = b.split(":")[-1].split("_")
    return (k2 in toks) or any(t.startswith(k2) for t in toks)


def is_known(block: str) -> bool:
    """★这个名字我到底认不认识★ ✗（U3 ✓）：学来的 ✓ 或者名字表命中 ✓ ⇒ True
    ★不认识的 ⇒ 调用方要知道自己是在**猜** ✗（保守方向 ✓：宁可当实心 ✓）"""
    b = (block or "").lower()
    if not b:
        return True
    if b in LEARNED:
        return True
    if b in EXACT_PASS or b in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
        return True
    for tbl in (LIQUID_SUB, PASS_SUB, CANOPY_SUB, MACHINE_SUB, SLAB_SUB, FENCE_SUB):
        for k in tbl:
            if _tok_match(b, k):
                return True
    return False


def shape(block: str) -> str:
    """★给一个方块名 → 它的**形状家族**★ ✓（用户点的方向 ✓ 只有这几种 ✓ 不再穷举方块 ✗）

    顺序要紧 ✗：
      ⓪ **学来的**（★模组碰撞箱给的 ✓ 比名字可信 ✓★ 2026-09-28 第 21 轮加的 ✓）
      ① **整名特判**（`EXACT_PASS` ✓ 处理 `grass` vs `grass_block` 这类同名不同命 ✓）
      ② air ⇒ ③ 液体 ⇒ ④ 能穿过 ⇒ ⑤ 树叶 ⇒ ⑥ 机器 ⇒ ⑦ 半砖 ⇒ ⑧ 栅栏 ⇒ 其余 `full`
    """
    b = (block or "").lower()
    if not b:
        return "air"
    if b in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
        return "air"
    got = LEARNED.get(b)                       # ⓪ ★学来的优先★ ✗
    if got and got.get("fam"):
        return str(got["fam"])
    return _shape_by_name(b)


def _shape_by_name(block: str) -> str:
    """★纯按名字猜★ ✗（没有学来的记录时才走这条 ✓ 所以它必须**保守** ✓）"""
    b = (block or "").lower()
    if not b:
        return "air"
    if b in EXACT_PASS:
        return "pass"
    if b in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
        return "air"
    for k in LIQUID_SUB:
        if _tok_match(b, k):
            return "liquid"
    # ★★2026-10-03 检修（欠账 ㉟）顺序修正✗★★：★树冠要**排在"能穿过"前面**✗★
    #   现场：`minecraft:flowering_azalea_leaves`（★树叶 ✓ 会挡人✓★）被判 `pass` ✗
    #     ⇒ 真因：`PASS_SUB` 里有 `azalea` ✗ 而它**排在树冠检查前面**✗ ⇒ 先撞上就返回了 ✓
    #   ⇒ ★口径✗★：★"叶子"比"灌木"更**具体** ✗ 具体的先判✗★ ✓
    #     （★`azalea`（★没有 `_leaves`✗★）仍然落回 `pass` ✗ 那是对的✓★）
    for k in CANOPY_SUB:
        if _tok_match(b, k):
            return "canopy"
    for k in PASS_SUB:
        if _tok_match(b, k):
            return "pass"
    for k in MACHINE_SUB:
        if _tok_match(b, k):
            return "machine"
    for k in SLAB_SUB:
        if _tok_match(b, k):
            return "slab"
    for k in FENCE_SUB:
        if _tok_match(b, k):
            return "fence"
    return "full"


_learn_load()


def is_floor(block: str) -> bool:
    """能不能**踩**（站上去）✓ —— `full` ✓ `slab` ✓ `machine` ✓ 三种可以 ✓ 其余不行 ✗

    ★2026-10-04✗★：★先问知识表的**碰撞槽** ✗ 它给了族就以它为准✗★（★物理听碰撞✓★）✗
      出厂档 `blacklist` ⇒ `_kb_phys` 直接回 `None` ⇒ **一个字节都不变**✗★ ✓
    """
    # ★★§79.452✗★★：★is_floor 走导出**（★碰撞高判 ✗ 不看任何名字✗★）✗★
    #   ★导出里有它（24779 条 ✗ 覆盖所有模组）⇒ 只看碰撞高✗★：
    #   ★能踩 = 0.45 ≤ h ≤ 1.05（整块 1.0 ✓ 半砖 0.5 ✓ 花 0 ✗ 雪层 0.125 ✗ 栅栏 1.5 排除）✗★
    _h = _export_h(block)
    if _h is not None:
        return 0.45 <= _h <= 1.05
    _FALLBACK_USED["floor"] += 1
    _f, _how = _kb_phys(block)
    if _f:
        import blockkb as _KB
        return _KB.is_floor_fam(_f)
    if _how == "unknown":
        return False                 # ★未知 ⇒ 保守：不当作地板（★别站在不认识的方块上✓★）
    return shape(block) in ("full", "slab", "machine")


# 方块名 -> 类别（渲染成 ASCII 字符用 ✓；不认识的归 '?' ✓ 不装作认识 ✗）
CATS = [
    (("water",), "~"), (("lava",), "!"),
    (("grass_block", "dirt_path"), "G"), (("dirt", "coarse_dirt", "rooted_dirt"), "D"),
    (("farmland",), "F"), (("sand", "gravel", "sandstone"), "S"),
    (("stone", "cobble", "deepslate", "calcite", "brick", "andesite", "diorite", "granite"), "#"),
    (("log", "wood", "planks", "fence", "slab", "stairs", "door", "trapdoor"), "W"),
    (("leaves",), "L"), (("glass",), "o"),
    (("chest", "barrel", "furnace", "sieve", "crucible", "hopper", "crafting_table", "anvil",
      "smoker", "blast_furnace", "campfire", "composter"), "M"),
    (("torch", "lantern", "candle"), "*"),
    (("wheat", "carrot", "potato", "beetroot", "melon", "pumpkin"), "c"),
    (("flower", "petal", "sapling", "grass", "fern", "bush", "vine", "moss", "azalea", "lily"), "v"),
    (("_ore",), "O"),
    (("slime_block", "honey", "wool", "carpet"), "="),
]


# ★★"名字不知道"的**唯一**哨兵值★★ ✗（2026-09-29 第 30 轮 ✓ 一处定义 ✓ P106 ✓）
#   它什么时候出现 ✗：模组对"**能站的层正好是你自己那一层**"的柱子只印 `@` ✗
#     ⇒ **那一柱的地板方块名模组没发** ✗（`mapCmd` 里 `sb.append('@'); continue;` ✓）
#     ⇒ 只能老实记"有地板、名字不知道" ✓ **绝不许猜一个名字** ✗
#   ★它有多大影响★ ✗（实测 ✓）：假人站在**平坦大平台**上时（脚层 = 地面 ✓）
#     **一大片**格子都是同层 ⇒ 实测 750 格里 **418 格（56%）** 是哨兵 ✗
#     ⇒ 俯视图那些格子原来渲染成 `?`（= "我什么都不知道"✗ —— **与"不知道名字"混成一个字符**✗ P106 同族 ✓）
#   ⇒ 两条一起治 ✓：
#     ① 渲染**分开**（`x` = 已知有地板、名字不知道 ✓ 见 `cat` ✓）——
#        形状看得见了 ✓ 不再假装"整片不知道"✗
#     ② 名字**照着补**：`absorb_true` 实扫一灌 ⇒ 真名就进来了 ✓
#        （根治在模组 v2.17 ✓：同层格也把地板字母印出来 ✓ 靠 `y<z>|` 的 `0` 表"同层"✓
#          解析器那边**老模组也照样能读** ✓ ⇒ 两边都不用改口径 ✓）
UNKNOWN_NAME = "minecraft:?"


def cat(block: str) -> str:
    b = (block or "").lower()
    if b == UNKNOWN_NAME:
        return "x"                    # ★"这一格**有地板**，只是模组没发名字"★ ✗（≠ 什么都不知道 ✓）
    for keys, ch in CATS:
        for k in keys:
            if k in b:
                return ch
    if b.endswith("air") or b == "air":
        return " "
    return "?"


class Map:
    """一片区域的**快照** ✓（柱子里有哪些方块 ＋ 每个柱子最高的那个 ✓）"""

    def __init__(self, x0, y0, z0, x1, y1, z1):
        self.box = (int(x0), int(y0), int(z0), int(x1), int(y1), int(z1))
        self.cols: dict = {}        # (x,z) -> {y: block}
        self.meta: dict = {"calls": 0, "sec": 0.0, "kinds": [], "matched": {}, "built": ""}
        # ★★版本号 ✗★（2026-09-30 第 40 轮 ✓ ⇒ P148 ✓）
        #   ★为什么要它✗★：`pathplan.Planner.region()`（连通区洪泛 ✓）实测 **0.79 秒** ✗
        #     而 `walk_route` **每一跳都新建 Planner** ✗ ⇒ 同一张图被反复洪泛 ✗
        #   ⇒ 想缓存就必须能判断"**图变没变**" ✗ —— 而★"逐个改动点去失效缓存"是错的路子✗★
        #     （漏一个 ⇒ **静默用旧连通区** ✗ ⇒ 又造出"假 unreachable" ✗ ★正是本项目最恨的那种✗★）
        #   ⇒ 口径 ✓：**Map 自带版本号 ✗ 任何改动就 +1** ✓ ⇒ 缓存键带上它 ⇒ 自动失效 ✓
        #   ★本轮的实测确认✗★：`absorb_true()` 是**唯一**改 `cols`／`meta` 的地方 ✓
        #     （`self.meta[...] =` 与 `del self.cols[...]` 全在它里面 ✓ 555/565/588/592/593 ✓）
        #   ⚠ ★将来若有人在**别处**改 `cols`／`meta` ✗ ⇒ **必须同时调 `bump()`**✗★
        #     （漏了 ⇒ 缓存读到旧图 ✓ 而且**不会报错**✗ 只会偶尔规划错 ✗ —— 最难查的那种 ✓）
        self.rev: int = 0
        self._regions: dict = {}    # 连通区缓存 ✓（键里含 `rev` ✓）

    def bump(self) -> int:
        """★"这张图变了"✗★ —— 改过 `cols`／`meta` 之后**必须**调它 ✓（P148 ✓）"""
        self.rev += 1
        self._regions.clear()
        return self.rev

    # ── 查询 ──────────────────────────────────────────────────────────────
    def surface(self, x, z, below=None, floor_only=True):
        """柱子**最高**的那个方块 ✓ 或"不高于 `below` 的最高那个" ✓

        ⚠ 为什么要 `below` ✗（实测 2026-09-23 ✓）：直接取最高 ⇒ 树冠（`oak_leaves@74` ✓）
          会被当地表 ✗ ⇒ 寻路会规划到**树顶**上去 ✗
          所以"走到某一层"的图必须问：**这一层下面最高的实心是什么** ✓（`below=层+1` ✓）

        ⚠ 为什么要 `floor_only` ✗（同上 ✓ 更狠的一课 ✓）：小麦/草/火把/树叶/栅栏
          **不是地板** ✗ ⇒ 不然航点会落在庄稼顶上 ✓ 走过去站不住 ⇒ 一步 0.3 格地挣扎 ✗
        """
        c = self.cols.get((int(x), int(z)))
        if not c:
            return None
        ys = [y for y in c if (below is None or y < int(below))]
        if floor_only:
            # ★规划问的是**落脚点**（★不是「能站」✗★）✗ 见 §79.147✗★
            ys = [y for y in ys if is_landing(c[y])]
        if not ys:
            return None
        y = max(ys)
        return (y, c[y])

    def solid_ys(self, x, z):
        return sorted(self.cols.get((int(x), int(z)), {}))

    def blocked_at(self, x, z, below=None):
        """这一格在「脚层 = `below-1`」上被什么占着 ✓（没被占 / 不知道 ⇒ `None` ✓）

        ⚠ 只在 `below - 1 == meta.blevel` 时有意义 ✗ —— 这份障碍信息是**建图那一刻**
          按假人当时所在的那一层读回来的 ✓（模组的 `b<z>|` 行 ✓ 碰撞箱判定 ✓）
          别的层我**没有**这份数据 ✗ ⇒ 老实返回 `None` ✓ **不装作知道** ✗
        """
        bc = self.meta.get("blocked_cells")
        bl = self.meta.get("blevel")
        if not bc or bl is None or below is None:
            return None
        if int(below) - 1 != int(bl):
            return None
        return bc.get("%d,%d" % (int(x), int(z)))

    def no_layer_set(self) -> set:
        """模组**明确说过**"这一格附近 (±6) 没有能站的层"的格子 ✓（懒解析 ＋ 缓存 ✓）

        为什么要缓存 ✗：渲染一张图会**逐格**问 `cell_kind` ✓
        每次都重新拆一个几万字符的字符串 ⇒ 慢到不能用 ✗（渲染几百格 × 解析 = 自杀 ✗）
        """
        s = getattr(self, "_nls", None)
        if s is None:
            s = set()
            for part in (self.meta.get("no_layer") or "").split(";"):
                if "," in part:
                    a, _, b = part.partition(",")
                    try:
                        s.add((int(a), int(b)))
                    except Exception as e:
                        # 记录：模组明确说过的一格解析不了 ⇒ 会被当成"正常格"（偏乐观）
                        print("[记录] no_layer 一格解析不了（%r）：%s"
                              % (part, type(e).__name__), file=sys.stderr)
            self._nls = s
        return s

    # ── ★把"实地扫到的真值"灌进图里★ ✓（2026-09-28 ✓ 治 P99 那个"高度是推的"✗）──
    def absorb_true(self, scan: dict, y_lo: int, y_hi: int) -> dict:
        """先**清掉**这一段里的旧数据 ✗ 再写真值 ✓

        ★为什么"必须先清"★ ✗（2026-09-28 ✓）：只增不减 ⇒ 旧模组那条**假地板**
        会原样留在图上 ✗ ⇒ 图变成"又准又不准"✗ ⇒ **比不改更坏** ✗
        （"图上同时存在真值和假值"这种状态最难查 ✗ —— 与本项目 `no_layer` 那条同族 ✓）
        """
        # ★改图 ⇒ **先加版本号**✗★（2026-09-30 第 40 轮 ✓ ⇒ P148 ✓）
        #   ★放在**最前面**✗★：万一后面抛异常 ⇒ 版本号也已经变了 ✓
        #     ⇒ 缓存失效 ✓（★"宁可多算一次 ✗ 也不许用旧图"✗★）
        self.bump()
        bx = scan["box"]
        y_lo, y_hi = int(y_lo), int(y_hi)
        # ★★扫描**被截断**时：只加不清★★ ✗（2026-09-29 第 22 轮 ✓ 这是"数据销毁"级的坑 ✓）
        #   为什么 ✗：清段是按**整个框**清 ✓ 而写真值只写**扫到的那些** ✓
        #     截断（分页没取完 / 中途读失败 ✓）⇒ **扫到的没写回、没扫到的被清掉** ✗
        #     ⇒ 柱子变空 ⇒ 连通区**塌成 0** ✗（实测撞到过：`plan_verify` 报"连通区 0 格"✗
        #       而十几秒后再量是 **876** ✓ ⇒ 图被我自己弄坏又自己修好了 ✓）
        #   ⇒ 口径 ✓：**宁可有旧值（可能不准）✗ 也不许把已知的抹掉** ✓
        #     截断时只**补充**扫到的真值 ✓ 不删任何东西 ✓（并且照样**大声报**截断 ✓）
        truncated = bool(scan.get("truncated"))
        cleared = 0
        inserted = 0
        cols = set()
        for x in range(bx[0], bx[3] + 1):
            for z in range(bx[2], bx[5] + 1):
                cols.add((x, z))
        # ★★先"学一条真值"：**模组说这一层站得住 ⇒ 这一层里的方块不挡人**★★ ✗
        #   （2026-09-29 第 30 轮 ✓ 治"假障碍"✓ 这是 `plan_verify` Z1 那个假失败的真因 ✓）
        #   事实链 ✓（每一环都是可复算的 ✓）：
        #     ① 快图每柱子的字母 = 模组 `standable(lv, f)` 为真的那一层 ✓（按**碰撞箱**判 ✓）
        #     ② 字母对应的名字 = 那一层**下面**那块（地板 ✓）
        #     ③ 我把这一带的地面**实地扫**回来 ⇒ 知道那一层里**真有什么** ✓
        #     ④ ⇒ 若那一层里有方块 B ✗ 而模组还说"站得住" ✓
        #          ⇒ **B 不挡人** ✓（否则模组自己就判 false 了 ✗）
        #   ⇒ 把 B 学成 `pass` ✓ —— 这正是"**碰撞箱说了算，名字只是猜**"的同一族 ✓
        #   ⚠ 三条护栏 ✗：① 只信**真高度**图（`has_offsets` ✗ 旧模组那 y 是推的 ✓）
        #                  ② 只信**没截断**的扫描（没扫到的格子不是"空的"✗）
        #                  ③ 只改**名字猜不准**的方块（`is_known` 为真的不碰 ✓ 别推翻已知表 ✓）
        #                     并且要求**世界真值**确认它下面那块是地板 ✓（防串行/错位 ✓）
        #   实测（第 30 轮 ✓）：`ars_elemental:spore_blossom_up` 长在草方块上方 1 格 ✓
        #     名字猜判它 `full`（"挡死"✗）而模组的碰撞箱说这一层能站 ✓ ⇒ 学成 `pass` ✓
        #     ⇒ 地图不再自造障碍 ✓ 规划/判据/视图三处**同口径** ✓（P106 ✓）
        learned = []
        if (not truncated) and bool(self.meta.get("has_offsets")) \
                and self.meta.get("blevel") is not None:
            lvl = int(self.meta["blevel"])
            truth = {}
            for (x, y, z, name) in scan["cells"]:
                truth[(int(x), int(y), int(z))] = name
            for key in cols:
                col = self.cols.get(key) or {}
                ys = [y for y in col if y <= lvl and is_landing(col[y])]
                if not ys:
                    continue
                fy = max(ys)                        # 模组找到的那一层的地板 ✓
                b_feet = truth.get((key[0], fy + 1, key[1]))
                b_floor = truth.get((key[0], fy, key[1]))
                if not b_feet or not blocks_space(b_feet):
                    continue
                if is_known(b_feet):                # ★只改"猜的"✗ 已知表不推翻 ✓
                    continue
                if not b_floor or not is_landing(b_floor):
                    continue                        # ★世界真值必须确认脚下是地板★ ✓
                if learn_shape(b_feet, "pass", "dshmap-feet"):
                    learned.append(b_feet)
            # ★学到了就**立刻落盘**★ ✗（第 30 轮 ✓）：这条结论会改变**后面每一次**判"能不能走"✓
            #   只放内存 ⇒ 进程一退（或换一个工具调用进来 ✓）就白学了 ✗ ⇒ 同一格反复假障碍 ✗
            if learned:
                learn_save()
        # ★★模组那条"能站"的结论也要**允许被新事实推翻**★★ ✗（第 30 轮 ✓ 新鲜度 ✓）
        #   为什么 ✗：那条结论是**建图那一刻**测的 ✓ 而世界会变（有人放了块方块 ✓）
        #     ⇒ 实扫回来的**新真值**若在**同一层**里发现一个**名录里认得**的挡人方块 ✓
        #       （栅栏/树叶/机器那种**不是猜的** ✓）⇒ 那条旧结论就该**作废** ✗
        #   ⚠ 只在"**认得的**"方块上作废 ✗：认不出的（`is_known=False` ✓）恰恰是名字猜不可信的 ✓
        #     ⇒ 那种情况按上面那条学习办 ✓（学成 pass ✓）不许拿名字猜去推翻实测 ✓
        dropped = []
        if not truncated:
            tmap = {}
            for (x, y, z, name) in scan["cells"]:
                tmap[(int(x), int(y), int(z))] = name
            ms_all = self.meta.get("mod_standable") or {}
            for key, fy in list(ms_all.items()):
                try:
                    kx, _, kz = key.partition(",")
                    kx, kz, fy2 = int(kx), int(kz), int(fy)
                except Exception as e:
                    # 记录：这条旧结论解析不了 ⇒ 它不会被新真值推翻（地图偏乐观）
                    print("[记录] mod_standable 一条旧结论解析不了（不推翻）：%r（%s）"
                          % (key, type(e).__name__), file=sys.stderr)
                    continue
                b = tmap.get((kx, fy2, kz))
                if b and is_known(b) and blocks_space(b):
                    del ms_all[key]
                    dropped.append(((kx, kz), fy2, b))
            if dropped:
                self.meta["mod_standable"] = ms_all
        if not truncated:
            for key in cols:
                c = self.cols.get(key)
                if not c:
                    continue
                for y in [y for y in list(c) if y_lo <= y <= y_hi]:
                    del c[y]
                    cleared += 1
                if not c:
                    del self.cols[key]
        for (x, y, z, name) in scan["cells"]:
            if y_lo <= y <= y_hi:
                self.cols.setdefault((x, z), {})[y] = name
                inserted += 1
        # ★"这一段里什么都没有"是**事实** ✓ 不是"没看到"✗ ⇒ 记进 `no_layer` ✓
        #   ⚠ 但**截断时不许记** ✗（第 22 轮 ✓）：没扫到的柱子会被误标成"没地板"✗
        nf = []
        if not truncated:
            for (x, z) in cols:
                c = self.cols.get((x, z)) or {}
                if any(y_lo <= y <= y_hi and is_landing(c[y]) for y in c):
                    continue
                # ★★"没地板"这句结论也要**问过模组**★★ ✗（第 30 轮 ✓ P106 ✓）：
                #   墙头那种柱子 ✓ 名字算不出地板 ✗ 而**模组说它那一层能站** ✓
                #   ⇒ 标成"没地板"就是**假话** ✗（`cell_kind` 会把它画成坑 ✗）
                _ms = self.mod_stand_y(x, z)
                if _ms is not None and y_lo <= _ms <= y_hi \
                        and c.get(_ms - 1) not in (None, "minecraft:air"):
                    continue
                nf.append("%d,%d" % (x, z))
            have = set(p for p in (self.meta.get("no_layer") or "").split(";") if p)
            have.update(nf)
            self.meta["no_layer"] = ";".join(sorted(have))
            self._nls = None                               # 缓存失效 ✓
            vb = list(self.meta.get("verified_boxes") or [])
            vb.append("%d,%d,%d,%d,%d,%d" % (bx[0], y_lo, bx[2], bx[3], y_hi, bx[5]))
            self.meta["verified_boxes"] = vb[-8:]          # 只留最近 8 个框 ✓（别把 meta 撑爆 ✗）
            self.meta["verified_cells"] = int(self.meta.get("verified_cells") or 0) + len(cols)
            # ★同时记进**跨地图**的账 ✓（第 26 轮 ✓ 否则地图一重建就白扫 ✓）
            vb_note((bx[0], y_lo, bx[2], bx[3], y_hi, bx[5]))
        else:
            # ★截断时**不许**把"这个框验过了"记下来★ ✗（第 22 轮 ✓ 这条最要命 ✓）：
            #   记了 ⇒ `box_verified` 之后**永远跳过重扫**✗ ⇒ 那块地就**一直半真半假**✗
            #   ⇒ 宁可下次多花一两次调用 ✓ 也不许留下"我有真值"的假象 ✗
            pass
        return {"cleared": cleared, "inserted": inserted, "cols": len(cols),
                "no_floor": len(nf), "y": (y_lo, y_hi), "truncated": truncated,
                "learned": learned, "verdict_dropped": dropped}

    def names_missing(self):
        """★这一张图上"有地板但不知道名字"的格子有多少★ ✗（第 30 轮 ✓ 零调用 ✓ 本地算 ✓）

        为什么要有它 ✗：模组对"**能站的层正好是你自己那一层**"的柱子只印 `@` ✗
          ⇒ 站到**平坦大平台**上时 **一大片**格子都是这样 ✗（实测 **425/458 = 93%** ✓）
          ⇒ 图上那些格子**是什么方块**不知道 ✓ 俯视图只能画个 `x` ✗
        ★这是个**可查的缺口** ✗ ⇒ 要能数出来 ✓ 并且**补得上**（`mc_mcp._fill_names` ✓）
          返回 ✓：`(总数, {地板 y: 该层缺多少})`
        """
        n = 0
        per: dict = {}
        for col in self.cols.values():
            ys = [y for y in col if is_landing(col[y])]
            if not ys:
                continue
            y = max(ys)
            if col[y] == UNKNOWN_NAME:
                n += 1
                per[y] = per.get(y, 0) + 1
        return n, per

    def mod_stand_y(self, x, z):
        """★模组**自己**（按碰撞箱 ✓）说"这一柱能站的那一层"是哪一层★ ✗（第 30 轮 ✓）

        来源 ✓：`/dshmap` 每柱那个字母 ⇒ **模组只在 `standable()` 为真时才印字母** ✓
          ＋ `y<z>|` 那行给的偏移 ⇒ 反推出"脚占的那一格" = `blevel + off` ✓
        ★为什么要有它★ ✗（实测 ✓ 这一轮的真教训 ✓）：
          模组说"这一柱 71 层能站"✓ 而我的图**只记地板那一格**✗ ⇒ 71 层里**站着什么**我不知道 ✗
          ⇒ 名字猜（认不出的方块一律当"挡死"✗）就会把它判成**站不住** ✗
          ⇒ **我自己的图否掉了模组的实测结论** ✗（`plan_verify` Z1 那个假失败就是这个 ✓）
          ⇒ 修法有两条 ✓：① 实扫回真值 ⇒ 学"这方块不挡人"✓（只覆盖**扫过**的地方 ✗）
                          ② ★★这一条★★：**把模组的结论本身记下来**✓ ⇒ 全图都生效 ✓ 不必扫 ✓
        ★口径★ ✗：**按碰撞箱判出来的站立结论 > 我的名字猜** ✓（本项目一贯那条 ✓）
        ⚠ 两个护栏 ✗：① 只在**真高度**图上收（`has_offsets` ✗ 旧模组那 y 是推的 ✓）
                     ② 查询的脚层**正好等于**模组说的那一层才用它 ✓（不越权推广到别的层 ✓）
        """
        ms = self.meta.get("mod_standable") or {}
        if not ms or not self.meta.get("has_offsets"):
            return None
        v = ms.get("%d,%d" % (int(x), int(z)))
        return int(v) if v is not None else None

    def mod_stand_conflicts(self) -> list:
        """★"名字猜说挡死、可模组说这一层能站"的格子★ ✗（第 30 轮 ✓ 供判据与报账 ✓ 零调用 ✓）"""
        out = []
        for k, fy in (self.meta.get("mod_standable") or {}).items():
            try:
                x, _, z = k.partition(",")
                x, z, fy = int(x), int(z), int(fy)
            except Exception:
                continue
            col = self.cols.get((x, z)) or {}
            b = col.get(fy)
            if b and blocks_space(b):
                out.append(((x, z), fy, b))
        return out

    def is_verified(self, x, z, level: int) -> bool:
        """这一格的结论是不是"**实地扫过**"的 ✓（不是从快图推的 ✗）—— 用于出处透明 ✓"""
        x, z, L = int(x), int(z), int(level)
        for part in (self.meta.get("verified_boxes") or []):
            try:
                a, b, c, d, e, f = (int(v) for v in str(part).split(","))
            except Exception:
                continue
            if a <= x <= d and c <= z <= f and b <= L <= e:
                return True
        return False

    def box_verified(self, x0, y0, z0, x1, y1, z1) -> bool:
        """★这个框**整个**都已经验过了吗★ ✓（⇒ 同一件事不必再扫一遍 ✗ 省通道 ✓）

        ★必须按"**包含**"判 ✗（2026-09-28 ✓）：只要**有重叠**就算验过 ⇒ 会出现
        "新框比旧框大 ✗ 却跳过 ⇒ 新框边缘仍是推的"✗ ⇒ **图一半真一半假**✗
        —— 那种状态最难查 ✓（P102 的"清段没覆盖"是同族 ✓）
        """
        for part in (self.meta.get("verified_boxes") or []):
            try:
                a, b, c, d, e, f = (int(v) for v in str(part).split(","))
            except Exception:
                continue
            if a <= int(x0) and b <= int(y0) and c <= int(z0) \
                    and int(x1) <= d and int(y1) <= e and int(z1) <= f:
                return True
        return False

    def standable(self, x, z, below=None):
        """能不能站在 (x,z)：该层下面最高的**地板** ✓ 且它上面两格**没有挡人的方块** ✓

        ⚠ 注意是"没有**挡人**的"✗ 不是"没有方块" ✓ —— 麦子/草/火把**不挡人** ✓（见 `blocks_space` ✓）

        ★v2.16：先看"**你这一层被什么占着**"★ ✗（2026-09-28 实测抓到的真 bug ✓）：
          现象 ✗：栅栏站在你的脚层 ⇒ 模组 `standable(那格)` = false ✓ ⇒ 它跳过这层
                 去找**下面**那层 ⇒ 回一个字母 ✗ ⇒ 我按"同层"近似收下 ✗
                 ⇒ **图说能走、走过去被挡** ✗（一整片 979 格全变 `*` ✗）
          ⇒ 模组 v2.16 多回一类 `b<z>|` 行（你的脚层/头层被什么占着 ✓ 碰撞箱判定 ✓）
          ⇒ 这里先查它 ✓ 被占 ⇒ **直接判不能站** ✗（不管底下那层多好站 ✓）
          ⚠ 只对"**建图时假人所在的那一层**"有效 ✓（`meta.blevel` ✓）——
            别的层没有这份障碍信息 ✗ ⇒ 不越权替它们下结论 ✓

        ★★为什么仓库里**还有**一套 `world3d.World3D.standable`（★§79.438 ✗ task-8 ✗ 不合并✗★）✗★★：
          ★这一层是 **2.5D 快图**✗★：★`dshmap` 一柱一个字母 ＋ 模组按碰撞箱的 `standable()` 结论
            ＋ 名字猜兜底（`blocks_space`）✗ ⇒ ★数据是**建图那一刻**的 ✗ 便宜✗★ ✓
          ★`world3d.World3D.standable` 是 **3D 体素**✗★：★`dshscan` 逐格读 ✗ 导出碰撞高
            ＋ 实时 `open=` 状态 ✗ ⇒ ★能答**任意一格** ✗ 数据是**现读的**✗★ ✓
          ★⇒ ★同一个问题 ✗ **两种数据层** ✗ 谁也不是谁的重复实现✗★ ✓
          ★⇒ 分界线✗★：★要**快**／只有 `dshmap` ⇒ 用**这里** ✗
            要**准**／要任意 y／要实时方块状态 ⇒ 用 `world3d.World3D.standable`✗★ ✓
        """
        # ★★优先级**写清楚**★★ ✗（第 30 轮 ✓ 两次都栽在同一件事上 ✓）：
        #   ① `b<z>|` 行 = "**你这一层这一格**被什么占着"（**逐格实测** ✓ 碰撞箱 ✓）
        #   ② 字母＋偏移 = "这一柱**能站的那一层**是第几层"（**逐柱的搜索结果** ✓）
        #   ⇒ **① > ②** ✗：逐格的观测比逐柱的结论**更具体** ✓
        #   （真实的模组里两者不会打架 ✓ —— 那一层真被占 ⇒ `standable()` 为假 ⇒ 它会往下找 ✓
        #     但**解析器不该依赖"上游不会自相矛盾"**✗ ⇒ 顺序写死在这里 ✓
        #     —— 合成回执的 W1c/W1d 就是靠这条把矛盾照出来 ✓）
        blk = self.blocked_at(int(x), int(z), below)
        if blk:
            return False
        # ★★然后才问"模组说这一柱哪一层能站"★★ ✗（第 30 轮 ✓ 碰撞箱说了算的落地 ✓）
        #   为什么它要排在**按名字的几何推断**前面 ✗：下面那两条全是猜的（`blocks_space` ✓）
        #     而模组是**按碰撞箱**实测的 ✓ ⇒ 同一个问题两种证据 ⇒ **实测的赢** ✓（P106 ✓）
        #   实测现场 ✓：草方块上方长着 `ars_elemental:spore_blossom_up` ✓
        #     模组说"71 层能站"（字母就是这么来的 ✓）✗ 而名字猜说它"挡死" ✗
        #     ⇒ 旧代码把我自己的实测结论**否掉**✗ ⇒ 规划器挑中的目的地被判"站不住"✗
        #       （`plan_verify` Z1 那一红 ✓ 真因就在这 ✓）
        #   ⚠ 只在"问的脚层**正好是**模组说的那一层"时生效 ✓ ⇒ 不越权推广到别的层 ✓
        ms = self.mod_stand_y(x, z)
        if below is not None and ms is not None and int(below) - 1 == ms \
                and (self.cols.get((int(x), int(z))) or {}).get(ms - 1) is not None:
            # ⚠ 护栏 ✓：**那一层下面那一格得有方块**（模组说 f 能站 ⇒ 它判过 f 下面那块实心 ✓）
            #   —— 而且**不能是空气** ✓（实扫说"那儿的方块被挖了" ⇒ 这条旧结论自动作废 ✓）
            #   ★★为什么护栏**不能**用 `is_floor` / `surface()`★★ ✗（第 30 轮实测抓到的真 bug ✓）：
            #     模组说"**72 层能站**"✓ 而 71 层是**树叶** ✓ ⇒ `is_floor(树叶)` = False ✗
            #       （项目**故意**不把树冠当"地板" ✓ 免得路画到树顶上 ✗）
            #     ⇒ 拿它当护栏 ⇒ 这 **16 柱**（N6 实测 ✓）全被我否掉 ✗
            #       而**模组按碰撞箱**说那儿站得住 ✓ —— 树叶确实是实心的 ✓ ⇒ **该信模组** ✓
            #   ⇒ 口径 ✓：**下面那格有方块 ＋ 模组说能站** ⇒ 就能站 ✓
            #     （地板被挖掉 ⇒ 实扫会把它清掉 ⇒ 这里就没有方块 ⇒ 结论自动作废 ✓ 不会拿旧事实当新的 ✓）
            return True
        s = self.surface(x, z, below)
        if not s:
            return False
        y = s[0]
        c = self.cols[(int(x), int(z))]
        for dy in (1, 2):
            b = c.get(y + dy)
            if b is not None and blocks_space(b):
                return False
        return True

    def reachable_floor(self, x, z, level, up=1, down=3, allow_auto_step=False):
        """★"走在 `level` 这一层的人，这一柱给他哪一层地板"★ ✗（第 31 轮 ✓ **一处口径** ✓）

        ★为什么必须有它★ ✗（第 31 轮实测抓到的**假 unreachable 真因之一** ✓）：
          33 轮里 `Planner.ok()` 问的一直是"**我这一层**这一格能不能站"✗
          （`standable(x, z, below=self.level + 1)` ✓）—— 可它同时**允许抬一级/降三级**✗
          ⇒ 那两种格子必然被否掉 ✗：
            · **抬一级**（地板在 `level` ✓ 脚在 `level+1` ✓）：
              那一格在**我这一层**里站着的是**台阶本身**（或墙头 ✓）
              ⇒ `standable(我这一层)` = False ✗ ⇒ **图说"不在连通区"** ✗
            · **降下去**（地板在 `level-2` ✓ 脚在 `level-1` ✓）：我这一层是空气/虚空 ✗ ⇒ 同样被否 ✗
          ⇒ 表现 ✓：**只要路要上下台阶，规划就报"不通"**✗ ——
            ★用户长期抱怨的"假 unreachable"★ ✓ 而平台是平的 ⇒ 一直没暴露 ✗

        ★★一个柱子可能给**不止一层**地板 ⇒ 必须挑"真的站得住"的那个★★ ✗（第 31 轮第二次实测 ✓）：
          现场 ✓：墙那一柱 —— 名字算得出草方块在 70（脚 71 ✗ 那一层站着**墙** ✓）
            而**模组说 72 能站**（站墙头 ✓）
          ⇒ 原来只挑"名字算出的最高地板" ✗ ⇒ 挑到脚=71 ⇒ 被墙挡 ⇒ **整柱判不通** ✗
          ⇒ 现在 ✓：把两个候选都列出来（名字算的 ＋ 模组结论的 ✓）
            先挑**真站得住**的 ✓ 都站得住就挑**离我这一层最近**的 ✓（平地优先 ✓）
        ⚠ 校验口径 ✓：地板 `f` ⇒ 脚占 `f+1` ⇒ 问 `standable(below=f+2)` ✓（`below` = 脚层+1 ✓ 一处换算 ✓）
        返回 ✓：地板 y ✓ 或 `None` ✓
        """
        lv = int(level)
        cands = []
        s = self.surface(x, z, below=lv + 1)
        if s:
            # ★★半步 ⇒ 多给一级★★ ✗（第 34 轮 ✓ 物理：顶面 +0.5 ≤ 自动上台阶 0.6 ✓）
            #   ⚠ **默认不启用** ✗ —— 见 `pathplan.Planner.max_rise` 的长注释 ✓：
            #     "半步能上"这条**没被实测证明过**✗（世界里那几格半步都在够不到的地方 ✗）
            #     ⇒ 拿它换覆盖率 ⇒ 电池 4 项当场红 ✗ ⇒ **默认关** ✓ 只留给判据开 ✓
            #   ⇒ 打开时必须问**白名单** ✓（`is_auto_step` ✓ 顶面 ≤0.6 才算 ✓
            #     不是 `shape=='slab'` ✗：耕地/楼梯/堆肥桶也是 slab ✗ 可顶面 >0.6 ⇒ 得跳 ✗）
            up_ok = int(up)
            if up_ok < 1 and bool(allow_auto_step):
                try:
                    import pathplan as _PP
                    if _PP.is_auto_step(s[1]):
                        up_ok = 1
                except Exception:
                    pass
            if (lv - int(down)) <= s[0] + 1 <= (lv + up_ok):
                cands.append(s[0])
        ms = self.mod_stand_y(x, z)
        if ms is not None and (lv - int(down)) <= ms <= (lv + int(up)) \
                and (self.cols.get((int(x), int(z))) or {}).get(ms - 1) \
                not in (None, "minecraft:air"):
            cands.append(ms - 1)
        cands = list(dict.fromkeys(cands))
        if not cands:
            return None
        good = [f for f in cands if self.standable(x, z, below=f + 2)]
        pick = good or cands
        return min(pick, key=lambda f: (abs(f + 1 - lv), -f))

    def mod_floor_y(self, x, z, below=None):
        """★"这一柱的地板在哪一层"★ ✓ —— **一处口径**（P106 ✓）

        ① 先按名字算（`surface` ✓ 正常情况 ✓）
        ② 算不出来（那一柱的地板在我的名录里"不是地板" ✗ 例如**树叶** ✓）
           ⇒ 就问**模组自己**那条结论：它说 `below-1` 这一层能站 ✓ ⇒ 地板就在 `below-1 - 1` ✓
           （模组的 `standable()` 判过"下面那块是实心的" ✓ 这不叫猜 ✓）
        ★为什么必须有它★ ✗（第 30 轮 ✓ 否则**规划器与判据会各说一套**✗ P106 ✓）：
          `standable()` 认了模组的结论 ✓ 而 `Planner.y()` 还按 `surface()` 算 ⇒ 回 `None` ✗
          ⇒ `ok()` 说"能站" ✓ `y()` 说"没地板" ✗ ⇒ 规划器要么开洞 ✓ 要么 `None + 1` **崩** ✗
        """
        s = self.surface(x, z, below=below)
        if s:
            return s[0]
        ms = self.mod_stand_y(x, z)
        if below is not None and ms is not None and int(below) - 1 == ms \
                and (self.cols.get((int(x), int(z))) or {}).get(ms - 1) not in (None, "minecraft:air"):
            return ms - 1          # ★墙头/树叶这种"名字不是地板、但确实站得住"的 ✓（空气不行 ✗）
        return None

    def walk_level(self, x, z, below=None):
        """站在这一柱子上时，脚底下那块实心的 y ✓（= surface 的 y ✓ 便于写清楚 ✓）"""
        s = self.surface(x, z, below)
        return s[0] if s else None

    def stand_cell(self, x, z, below=None):
        """★把 (x,z) 变成"人站的那一格坐标"★ ✓（返回 (x, y, z) 或 None ✓）

        ⚠ 为什么必须有它 ✗（实测 2026-09-23 ✓ 又栽一次同一族 ✗）：
          实体的 `pos.y` **不是**"脚站的那一格" ✗ ——
          · 站在**耕地**上 ⇒ 耕地的碰撞面在 70.9375 ✓ ⇒ `pos.y = 70.94` ✓
            而**那一格**（能站人的空气格）是 **71** ✓
          · 台阶/雪层/半砖同理 ✓
          ⇒ 我拿 `int(pos.y)` 当目标 y 传给模组 ✗ ⇒ 模组被要求"站在耕地**里面**"✗
            ⇒ 表现：**永远"没到"** ✓ 而且只差 1~2 格 ✓ 看起来像"寻路不行"✗
            实测：R2 2/3 ✗ R3 1/3 且慢 15 倍 ✗（全都是这一个 y 造成的 ✗）
          ⇒ 纪律：★**"人在哪"与"站哪一格"是两件事**★ ✗ —— 一律用地图问 ✓ 不许 int(pos.y) ✗
        """
        s = self.surface(x, z, below)
        if not s:
            return None
        return (int(x), s[0] + 1, int(z))

    @property
    def unknown(self):
        return [(x, z) for (x, z) in self.cells() if not self.cols.get((x, z))]

    def cells(self):
        x0, _, z0, x1, _, z1 = self.box
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                yield (x, z)

    def coverage(self) -> float:
        n = total = 0
        for (x, z) in self.cells():
            total += 1
            if self.cols.get((x, z)):
                n += 1
        return (n / total) if total else 0.0

    # ── 渲染 ──────────────────────────────────────────────────────────────
    def ascii(self, mark=None, below=None, with_y=False) -> str:
        """俯视图 ✓ 北在上（-Z 在上 ✓ 与本项目其它地图一致 ✓）；`mark` = 用 @ 标的坐标 ✓

        `below` 给了 ⇒ 只画**这一层下面**的地表 ✓（寻路要的就是这张图 ✓ 不是树冠图 ✓）
        """
        x0, _, z0, x1, _, z1 = self.box
        lines = []
        for z in range(z0, z1 + 1):
            row = []
            for x in range(x0, x1 + 1):
                if mark and (int(mark[0]), int(mark[1])) == (x, z):
                    row.append("@")
                    continue
                s = self.surface(x, z, below)
                row.append(cat(s[1]) if s else ".")
            lines.append("%+5d %s" % (z, "".join(row)))
        head = "      " + "".join(str(abs(x) % 10) for x in range(x0, x1 + 1))
        return "\n".join([head] + lines)

    def height_ascii(self, below=None) -> str:
        """高度图 ✓（用 0-9A-Z 表示"地表高度 - 基准" ✓ 一眼看出高差 ✓）"""
        x0, y0, z0, x1, _, z1 = self.box
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        lines = []
        for z in range(z0, z1 + 1):
            row = []
            for x in range(x0, x1 + 1):
                s = self.surface(x, z, below)
                if not s:
                    row.append(".")
                else:
                    d = s[0] - y0
                    row.append(chars[d] if 0 <= d < len(chars) else "?")
            lines.append("%+5d %s" % (z, "".join(row)))
        return "      " + "".join(str(abs(x) % 10) for x in range(x0, x1 + 1)) + "\n" + "\n".join(lines)

    def legend(self) -> str:
        return ("legend: G=grass D=dirt F=farmland S=sand/gravel #=stone W=wood/plank L=leaves "
                "c=crop v=plant M=machine *=light O=ore ~=water !=lava o=glass = =soft ?=other "
                "x=有地板但模组没发名字(同层格 ✅ 实扫一次就有真名) .=nothing-known @=you")

    # ── ★"道的剖面"★ ✓：把这条路展开成**能看的图** ✓（2026-09-28 ✓ 用户点的方向 ✓）────
    #   用户的原话 ✓：「寻路的重点是**识别道中的障碍物**，不一定说一定要快……
    #                  怎么做到让你能识别到地图的完整情况」
    #   ⇒ 地图（`/dshmap` ✓）解决"看得见"✓；**这一层解决"看得懂"**✓ ——
    #     光有整片俯视图 ✗ 我还是得自己在脑子里把路走一遍 ✗
    #     ⇒ 把**规划出的那条路**单独渲染出来 ✓ 走不通的格一眼就是 `X` ✓
    def cell_kind(self, x, z, level: int):
        """走在 `level` 层（= **脚占的那一格** ✓ 见 `_stand_level` ✓）的人，看这一格是什么 ✓

        返回 `(char, name, why)` ✓ —— ★字符口径**写死在这里**★ ✗（与 `is_floor`/`blocks_space`
        同一个道理 ✓：口径散在各处 ⇒ 必然出现"同一个格子在两处结论不同"✗）

          `*` 能走 ✓（地面正好在下面一格 ＋ 脚/头两格没挡人的方块 ✓）
          `+` 矮障 ✓（半砖/机器这类"矮一截"的 ⇒ 模组**能自动上一步** ✓ 不必绕 ✓）
          `#` 挡死 ✓（整方块/栅栏/树冠这类 ⇒ **要绕或要挖** ✓）
          `~` 液体 ✓（水/岩浆 ⇒ 不能走 ✓）
          `^` 抬一格 ✓（地面就在 `level` 这一格 ⇒ 跳一下能上 ✓）
          `v` 降下去 ✓（地面在 `level-1`~`level-3` ⇒ 走得下去 ✓）
          `.` 没地板 ✓（这一柱已知 ✓ 但**这一层附近没有地板** ⇒ 坑/虚空 ✗）
          `?` 未知 ✓（这一柱**一个已知方块都没有** ✗ ⇒ 多半是虚空 ⇒ **不能走** ✓）

        ★为什么 `?` 必须与 `#` 分开报★ ✗：
          `?` 是"**我没看到**"✗ `#` 是"**我看到了、它挡着**"✓ ——
          混在一起 ⇒ 我分不清该"去探一探"还是该"绕开" ✗
          （"没看到 ≠ 没有"这一条在本项目栽过多次 ✗ ⇒ 在字符上就分开 ✓）
        """
        c = self.cols.get((int(x), int(z)))
        L = int(level)
        # ★优先级（与 `standable` 写死同一套 ✓ P106 ✓）：
        #   ① `b<z>|` 行 = **这一格**被什么占着（逐格实测 ✓）⇒ 最高 ✓
        #   ② 字母＋偏移 = **这一柱**能站的是哪一层（逐柱结论 ✓）⇒ 其次 ✓
        #   ③ 地面几何 ＋ 名字猜 ⇒ 最后 ✓
        blk = self.blocked_at(x, z, L + 1)
        if blk:
            sh = shape(blk)
            if sh == "liquid":
                return ("~", blk, "液体 ⇒ 不能走 ✓")
            if sh == "slab":
                return ("+", blk, "半砖高 ⇒ 能自动上一步 ✓")
            return ("#", blk, "★你这一层被它占着★（碰撞箱判定 ✓）⇒ 要绕或要挖 ✓")
        # ★★"模组实测说这一层能站" ⇒ **视图也必须这么说**★★ ✗（第 30 轮 ✓ P106 ✓）
        #   为什么 ✗：`standable()` 已经采信模组的碰撞箱结论 ✓ ⇒ 要是 `cell_kind` 还按名字猜画 `#` ✗
        #     ⇒ **同一格在"规划判据"里能走、在"视图"里是墙** ✗ —— 那正是本项目最恨的**两个口径** ✗
        ms = self.mod_stand_y(x, z)
        if ms is not None and ms == L:
            s0 = self.surface(x, z, below=L + 1)
            if s0 is not None:      # ★脚下真有地板才这么画 ✗（与 `standable` 同一条护栏 ✓）
                return ("*", s0[1],
                        "★模组按碰撞箱说这一层**能站**★（字母就是这么来的 ✓）"
                        "⇒ 就算这里记着方块也**不挡人** ✓（名字猜不算数 ✓）")
        if (int(x), int(z)) in self.no_layer_set():
            # 模组**明确**在 ±6 层内找不到能站的层 ⇒ 那是"坑/虚空"✓ **不是**"我没看到"✗
            return (".", None, "模组在你这一层附近（±6）找不到能站的层 ⇒ 坑/虚空 ✗")
        if not c:
            return ("?", None, "地图没这一柱 ⇒ **没看到 ≠ 没有** ✓")
        # ★顺序很要紧★ ✗（2026-09-28 写错过一次 ✓）：
        #   **先算"地面在哪" ⇒ 得到"站上去脚占哪一格" ⇒ 再看那两格有没有挡人的** ✓
        #   反过来（先查 `level` 这一格有没有方块 ✗）会把"**地面高一格、抬腿就能上**"
        #   判成**挡死** ✗ —— 而那正是规划器认为**能走**的格 ✓ ⇒ 视图凭空造出**假障碍** ✗
        s = self.surface(x, z, below=L + 1)
        if not s:
            return (".", None, "这一层附近没有地板 ⇒ 坑/虚空 ✗")
        fy = s[0]
        feet = fy + 1                       # ★站上去以后，脚占的那一格★ ✓（与 `stand_cell` 同一个算法 ✓）
        for dy in (0, 1):                   # 脚/头两格
            b = c.get(feet + dy)
            if b is None or not blocks_space(b):
                continue
            sh = shape(b)
            if sh == "liquid":
                return ("~", b, "液体 ⇒ 不能走 ✓")
            if sh == "slab":
                return ("+", b, "半砖高 ⇒ 能自动上一步 ✓")
            return ("#", b, "挡死 ⇒ 要绕或要挖 ✓")
        if feet == L:
            return ("*", s[1], "能走 ✓")
        if feet > L:
            # 高一格以上 ⇒ 抬腿；半砖那类**能自动上** ✓ 整方块/机器要**跳一下** ✓
            #   ★只给 slab 记 `+`★ ✗（2026-09-28 收窄 ✓）：机器那类整方块高 1 格 ✗
            #   说它"能自动上一步"是错的 ✗（自动上台阶只到 0.6 格 ✗）
            if shape(s[1]) == "slab":
                return ("+", s[1], "半砖高 ⇒ 能自动上一步 ✓")
            if feet - L == 1:
                return ("^", s[1], "要抬 1 格 ⇒ 跳一下 ✓")
            # ★抬 2 格以上 ⇒ **上不去** ✗★（2026-09-28 第 19 轮 ✓ 实测被"假干净"抓到 ✓）：
            #   原来一律给 `^`（在"能走"集合里 ✗）⇒ 明明跳不上去 ✗ 却被当成路 ✓
            return (".", s[1], "地板在脚下**上面 %d 格** ⇒ **上不去** ✗" % (feet - L))
        d = L - feet
        if d <= 3:
            return ("v", s[1], "要降 %d 格 ⇒ 走得下去 ✓" % d)
        # ★降 4 格以上 ⇒ **下不去** ✗★（同上 ✓）：落差上限就是 3 ✓（`pathplan.MAX_DOWN` ✓）
        return (".", s[1], "地板在脚下 **%d 格** ⇒ **下不去** ✗（最多 3 ✓）" % d)

    ROUTE_OK = ("*", "^", "v", "+")     # 路线格上出现这些 ⇒ 这条路**走得通** ✓

    ROUTE_LEGEND = ("legend（★本视图自己的口径 ✓ 与俯视图的 legend 不是一套 ✗）："
                    "*=路线格且走得通 ✓ X=★路线格但走不通★ ✗ +=矮障(能上) ✓ #=挡死(要绕/要挖) ✓ "
                    "~=液体 ✓ ^=要抬一格 ✓ v=要降下去 ✓ .=没地板(坑) ✗ ?=未知(没看到 ≠ 没有) ✓")

    def route_ascii(self, pts, level: int, margin: int = 1, max_cells: int = 1200):
        """★把这条路画出来★ ✓ 路线格 `*`（走不通 ⇒ **`X`** ✓）

        返回 `(图, 格数)` ✓；格子数超 `max_cells` ⇒ **图给 None**（但不撒谎 ✓
        调用方要如实说"太大了画不下"✗ 不许画半张 ✗）
        """
        cells = [(int(p[0]), int(p[2])) for p in pts]
        if not cells:
            return None, 0
        xs = [c[0] for c in cells]
        zs = [c[1] for c in cells]
        x0, x1 = min(xs) - int(margin), max(xs) + int(margin)
        z0, z1 = min(zs) - int(margin), max(zs) + int(margin)
        n = (x1 - x0 + 1) * (z1 - z0 + 1)
        if n > int(max_cells):
            return None, n
        route = set(cells)
        lines = []
        for z in range(z0, z1 + 1):
            row = []
            for x in range(x0, x1 + 1):
                ch, _name, _why = self.cell_kind(x, z, level)
                if (x, z) in route:
                    row.append("*" if ch in self.ROUTE_OK else "X")
                else:
                    row.append(ch)
            lines.append("%+5d %s" % (z, "".join(row)))
        head = "      " + "".join(str(abs(x) % 10) for x in range(x0, x1 + 1))
        # ★★2026-10-24（★§79.339 ✗ 用户说"那就改"✗★）✗★★：★把自己**实际画的框**记下来✗★ ——
        #   ★`route_view_test` 之前拿**自己那条路**的包围盒来要求这张图 ✗ 而这张图画的是
        #   **这边重规划出来的另一条路** ✗ 两条路的 x 跨度**本来就不一样**✗★ ⇒ ★宽度当然不等✗★ ✓
        self.last_art_box = (x0, x1, z0, z1)
        return "\n".join([head] + lines), n

    def to_json(self) -> dict:
        return {"box": self.box, "meta": self.meta,
                "cols": {"%d,%d" % k: {str(y): b for y, b in v.items()} for k, v in self.cols.items()}}


# ── 与游戏说话（这一层只依赖 channel ✓ 便于单测时换掉 ✓）────────────────────
def _mk_chan():
    from channel import Channel
    return Channel("cmd0", verbose=False)


class Reader:
    # ★进程内地图记忆★ ✓（实测 2026-09-23 ✗：走路时假人一动 ⇒ 图框就变 ⇒ **缓存全 miss** ✗
    #   ⇒ 每走一步都重建一张图（40+ 次调用 ≈ 30 秒 ✗）⇒ 三段路走了 413 秒 ✗✗
    #   ⇒ 所以：**同一个进程里，框一样就直接复用** ✓ 而且**对齐过的框**（见 mc_mcp._route_map ✓）
    #     在假人小幅移动时保持不变 ✓）
    _MEM: dict = {}

    def __init__(self, chan=None, cache_dir: Path = CACHE, verbose: bool = False):
        self.ch = chan or _mk_chan()
        self.cache = Path(cache_dir)
        self.verbose = verbose
        self.calls = 0

    def ab(self, cmd: str, tmo: float = 60.0) -> str:
        self.calls += 1
        r = self.ch.cmd("execute as Bot at Bot run %s" % cmd, timeout=tmo, allow_str=True)
        return (r.text() or "").strip()

    # ── 基本读 ───────────────────────────────────────────────────────────
    def block(self, x, y, z) -> str:
        """读**一格** ✓（0.6 秒 ✓ 只在抽查/补漏时用 ✓ 别拿它建图 ✗）

        返回方块名 ✓；**空气返回 "minecraft:air"** ✓（不是空串 ✗ —— 空串会被误当成"读失败"✗）
        """
        out = self.ab("dshscan %d %d %d %d %d %d" % (x, y, z, x, y, z))
        m = re.search(r"counts\[([^\]]*)\]", out)
        if m and m.group(1):
            # ★必须 rpartition★ ✗：条目是 `minecraft:oak_planks:645` ✓
            #   用 partition 会切成 "minecraft" ✗ —— 我第一版就这么错的 ✓
            #   表现是"地图没错、验收脚本报 14/14 全不一致"✗（差点去改没错的地方 ✗）
            name, _, _cnt = m.group(1).rpartition(":")
            return name
        if re.search(r"kinds=0\b", out) or re.search(r"\bair=1\b", out):
            return "minecraft:air"
        return ""          # 真空串 = 读失败 ✓（调用方要区别对待 ✓）

    def pos(self):
        out = self.ab("dshdigest 1")
        m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", out)
        return tuple(float(g) for g in m.groups()) if m else None

    def scan(self, box, match=None, max_=1000, page=1):
        x0, y0, z0, x1, y1, z1 = box
        cmd = "dshscan %d %d %d %d %d %d" % (x0, y0, z0, x1, y1, z1)
        if match:
            cmd += ' "%s" %d %d' % (match, int(max_), int(page))
        out = self.ab(cmd)
        head = out.split("counts[")[0]
        kv = dict(KV.findall(head))
        tail = out.split("counts[", 1)[1] if "counts[" in out else ""
        coords = [tuple(int(g) for g in t) for t in re.findall(r"(-?\d+),(-?\d+),(-?\d+)", tail)]
        return kv, coords

    def kinds(self, box):
        """这一片的**种类清单** ✓（回执头部的 counts[...] 就是 ✓ top-40 ✓ 按数量降序 ✓）"""
        kv, _ = self.scan(box)
        out = self.ab("dshscan %d %d %d %d %d %d" % box)     # 拿 counts 原文 ✓
        m = re.search(r"counts\[([^\]]*)\]", out)
        items = []
        for part in (m.group(1) if m else "").split(","):
            name, _, cnt = part.rpartition(":")
            if name and cnt.isdigit():
                items.append((name, int(cnt)))
        return kv, items

    # ── 建图 ─────────────────────────────────────────────────────────────
    def build(self, box, max_kinds: int = 40, max_calls: int = 400, max_age: float = 600.0) -> Map:
        """建一片图 ✓

        ★两个"实测撞出来"的规矩（2026-09-23 ✓）★：
        ① **长的名字先认领** ✗：`dshscan ... "grass"` 是**子串匹配** ✓
           ⇒ 它把 `grass_block` 的坐标也一起给回来 ✗ ⇒ 要是先按 `grass` 记 ⇒
           那格就被标成 `minecraft:grass`（草 ✓ 植物）而真身是 `grass_block` ✗
           （验收脚本当场抓出来：3/14 不一致 ✓）
           ⇒ 解：按**名字长度降序**处理 ✓ 已被认领的格子不覆盖 ✓
           —— `grass_block` ⊆ `grass` ✓ 所以先认长的正好对 ✓
        ② 每个格子（x,y,z）**只属于一个方块** ✓ ⇒ 认领表按 (x,y,z) 记 ✓
        """
        x0, y0, z0, x1, y1, z1 = (int(v) for v in box)
        m = Map(x0, y0, z0, x1, y1, z1)
        t0 = time.time()
        c0 = self.calls
        kv, items = self.kinds((x0, y0, z0, x1, y1, z1))
        m.meta["kinds"] = [k for k, _ in items]
        claimed: set = set()
        for name, cnt in sorted(items[:max_kinds], key=lambda kv2: -len(kv2[0])):
            if self.calls - c0 > max_calls:
                m.meta["truncated"] = True
                break
            page = 1
            while True:
                kv2, coords = self.scan((x0, y0, z0, x1, y1, z1), match=name, max_=1000, page=page)
                for (x, y, z) in coords:
                    if x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1:
                        if (x, y, z) in claimed:
                            continue
                        claimed.add((x, y, z))
                        m.cols.setdefault((x, z), {})[y] = name
                m.meta["matched"][name] = int(kv2.get("matched") or 0)
                pg = kv2.get("page") or "1/1"
                try:
                    cur, tot = (int(v) for v in pg.split("/"))
                except Exception:
                    break
                if cur >= tot or not coords:
                    break
                page += 1
        m.meta["calls"] = self.calls - c0
        m.meta["sec"] = round(time.time() - t0, 2)
        m.meta["built"] = time.strftime("%Y-%m-%d %H:%M:%S")
        m.meta["coverage"] = round(m.coverage(), 3)
        self.save(m, max_age)
        return m

    # ── 缓存 ─────────────────────────────────────────────────────────────
    def path_of(self, box) -> Path:
        self.cache.mkdir(parents=True, exist_ok=True)
        return self.cache / ("map_%d_%d_%d_%d_%d_%d.json" % tuple(int(v) for v in box))

    def build_dshmap(self, radius: int = 16, max_age: float = 300.0) -> "Map | None":
        """★用模组 `/dshmap` **一次**拿一整片★ ✓（v2.15 起 ✓ 这是"地图完整性"的正解 ✓）

        为什么它比"按种类扫描"强 ✗（实测 2026-09-25 ✓）：
          · 扫描法：**42 次调用 / 36 秒** ✓ 而且 `counts[...]` **只列 top-40** ✗
            ⇒ 稀有方块（`computercraft:computer_command` 那类 ✓）**根本进不了图** ✗
          · `/dshmap`：**1 次调用** ✓ 逐格问服务器"这一格站得住吗、地板是什么" ✓
            ⇒ 覆盖率和**稀有方块**都不再是问题 ✓（模组那边读的是**碰撞箱** ✓ 世界真值 ✓）
        回执形状 ✓（见模组 `mapCmd` ✓）：
          `dshmap box=x0,z0..x1,z1 from=x,y,z standable=N legend=A:name,B:name…`
          然后每行 `z|字符…` ✓；`@` = **与假人同层**（＝这一格现在就能站 ✓）✓ `.` = 站不住 ✓
        本函数只把 **`@` 那些格子**写进图 ✓（＝**能站** ✓ 地板名也记下 ✓）
          其余的（`.` 与别的字母）**记进 meta 备查** ✓ 但不画成"能站" ✗ —— 宁可少说 ✓ 不假装 ✓
        返回 ✓：`Map` 或 `None`（模组不支持 ⇒ 调用方回落老办法 ✓）
        """
        out = self.ab("dshmap %d" % max(1, min(int(radius), 32)), 90.0)
        if not out or "dshmap" not in out.splitlines()[0]:
            return None
        lines = out.splitlines()
        head = lines[0]
        m2 = re.search(r"box=(-?\d+),(-?\d+)\.\.(-?\d+),(-?\d+)", head)
        f2 = re.search(r"from=(-?\d+),(-?\d+),(-?\d+)", head)
        st = re.search(r"standable=(\d+)", head)
        # ★★`legend=` 与 `ylegend=` 互为子串 ⇒ 必须按**字段边界**取★★ ✗（2026-09-29 第 30 轮 ✓）
        #   坑（实测 ✓ 一整个电池两处假失败都从这里长出来 ✓）✗：
        #     `re.search(r"legend=([^ ]*)", head)` 会在 `ylegend=0:same,A:+1,…` 里**先命中**✗
        #     （`ylegend=` 里含 `legend=` ✓ 而 `re.search` 取**最左**那个 ✓）
        #     ⇒ 拿到的"图例"其实是**偏移**表 ✓ ⇒ `legend.get('E')` ⇒ None ✓
        #     ⇒ **每个柱子的地板名退化成它自己那个字母** ✗（`m.cols[(x,z)] = {70: 'E'}` ✓）
        #   连锁（都是实测 ✓）✗：
        #     · ASCII 俯视图**整张 `?`** ✗（`cat('E')` 不认识 ✓ 用户要的"看得懂"直接没了 ✗）
        #     · `is_floor('E')` 落到 `full` ⇒ **碰巧为真** ✓ ⇒ 高度/连通判据全看不出来 ✗
        #       （所以它躲过了整整五轮电池 ✗ —— 判据一直在问 y ✓ 从没问过**名字** ✓）
        #     · `blocked_cells` 存的是字母（`M`/`V` ✗）⇒ `shape('M')` = `full` ✗ ⇒ 障碍真假不明 ✗
        #   口径 ✓：字段前面**必须是行首或空白** ✓ ⇒ `(?:^|\s)` ✓
        #     ＋ 只收**带命名空间**的值 ✓（偏移表的值是 `same`/`+1` ✗ ⇒ 再兜一层 ✓）
        lg = re.search(r"(?:^|\s)legend=([^ ]*)", head)
        if not (m2 and f2):
            return None
        x0, z0, x1, z1 = (int(m2.group(i)) for i in (1, 2, 3, 4))
        bx, by, bz = (int(f2.group(i)) for i in (1, 2, 3))
        legend = {}
        legend_dropped = 0
        if lg and lg.group(1) != "-":
            for part in lg.group(1).split(","):
                if ":" in part:
                    ch, _, name = part.partition(":")
                    if ":" in name:          # ★只收命名空间 id★ ✗（`0:same` 这种一律不要 ✓）
                        legend[ch] = name
                    else:
                        legend_dropped += 1
        # ★v2.16：模组多回了两类行★ ✓（见模组 `mapCmd` 的注释 ✓ 那里有这次的真 bug ✓）
        #   `y<z>|` 那一层相对**你的脚**高多少 ✓（0/A/B/a..f ✓）
        #   `b<z>|` **你的脚层/头层**上占着什么方块 ✓（碰撞箱判定 ✓ `.` = 空的 ✓）
        #   旧模组没有这两样 ✗ ⇒ `has_offsets=False` ✓ 走"同层近似"✓ 但**标记出来** ✗
        #   （不许静默降级 ✗：调用方要能看出"这张图的高度是推的"✓）
        blm = re.search(r"blevel=(-?\d+)", head)
        bl = int(blm.group(1)) if blm else by
        has_off = "ylegend=" in head
        OFF_NUM = {}
        yleg = re.search(r"ylegend=([^ ]*)", head)
        if yleg:
            for part in yleg.group(1).split(","):
                ch, _, val = part.partition(":")
                if not ch:
                    continue
                if val == "same":
                    OFF_NUM[ch] = 0
                else:
                    try:
                        OFF_NUM[ch] = int(val)
                    except Exception:
                        pass          # `none`（`.` ✓）之类 ⇒ 不收 ✓ 那就是"不知道"✓
        kind_rows, yrows, brows = [], {}, {}
        for line in lines[1:]:
            if "|" not in line:
                continue
            tag, _, row = line.partition("|")
            tag = tag.strip()
            kind = "k"
            if tag[:1] in ("y", "b"):
                kind = tag[:1]
                tag = tag[1:]
            try:
                z = int(tag)
            except Exception as e:
                # 记录：dshmap 的一整行解析不了 ⇒ 这一行不进地图（静默少数据）—— §79.401 那一族
                print("[记录] dshmap 一行解析不了（少一整行）：%r（%s）"
                      % (tag, type(e).__name__), file=sys.stderr)
                continue
            if kind == "y":
                yrows[z] = row
            elif kind == "b":
                brows[z] = row
            else:
                kind_rows.append((z, row))
        m = Map(x0, by - 8, z0, x1, by + 6, z1)
        other = {}
        blocked = {}
        mod_stand = {}
        no_layer = []
        standable_cells = 0
        learned_n = 0                     # ★这一趟从碰撞箱学到几条真值★ ✓（第 21 轮 ✓）
        _declared_gaps = []   # ★㉜：占用不一致**必须声明**（★不许静默✗★）
        assumed = 0
        exact = 0
        for (z, row) in kind_rows:
            yrow = yrows.get(z, "")
            brow = brows.get(z, "")
            for i, ch in enumerate(row):
                x = x0 + i
                key = "%d,%d" % (x, z)
                # ★★先把"模组说这一柱哪一层能站"记下来★★ ✗（第 30 轮 ✓）
                #   字母 = 模组**按碰撞箱**判 `standable()` 为真 ✓ ⇒ 那是**实测结论** ✓
                #   ＋ `y<z>|` 的偏移 ⇒ 脚占的那一格 = `blevel + off` ✓
                #   ⇒ 存进 `meta["mod_standable"]` ✓ ⇒ `Map.standable` 直接采信它 ✓
                #     （不然我那些**按名字**的判断会反过来否掉模组的实测 ✗ 见那里的长注释 ✓）
                _off = OFF_NUM.get(yrow[i]) if i < len(yrow) else None
                if ch != "." and _off is not None:
                    mod_stand[key] = by + int(_off)
                # ★"你这一层被占"先收★ ✓ —— 与"底层能站"**无关** ✗（栅栏站在你层上时
                #   模组会跳过这层去找下面 ✓ ⇒ 只看字母就会把它当"能走" ✗ 这正是那个 bug ✓）
                if i < len(brow) and brow[i] != ".":
                    blocked[key] = legend.get(brow[i], brow[i])
                    # ★★2026-10-03 检修（欠账 ㉜）：这里**原来**会学一条 "full" ✗★★
                    #   原意 ★"模组按**碰撞箱**说'你这一层被它占着' ⇒ 以模组为准"✓★ ——
                    #   但那个字母（`brow[i]`）**本身就是地图按名字分类出来的**✗
                    #   ⇒ ★从"地图自己的判断"学"事实" = **循环** ✗ 错的猜测会被固化✗★ ✓
                    #   实测 ✗：`supplementaries:book_pile_horizontal`（一摞书）被学成 full ✗
                    #     从此**盖住**名字表（名字表说它是 `pass` ✓）⇒ 地图一直打 `#`
                    #     而世界明明能站 ⇒ `route_verify_test` 的 X1 当场抓住 ✗
                    #   ⇒ ★口径✗★：★只有**真的碰撞箱探测**（`src` 不是地图自己）才配改名字判断✗★
                    #     （★名字表该补就补家族词 ✓ 见 `PASS_SUB` 里那串装饰类✓★）
                    _bn = blocked[key]
                    # ★★2026-10-03 检修（欠账 ㉜）✗★★：★不学 ✗ 但**必须声明**✗★ ✓
                    #   停用「从地图自己的字母学」之后，这类不一致会**一直存在** ✗
                    #   ⇒ ★不能让它静默 ✗ 地图要自己把它们**列出来**✗★ ✓
                    #   （★判据 U1 就是按这个字段查的：★不一致可以有 ✗ 但一条都不许**没声明**✓★）
                    if _bn and not blocks_space(_bn):
                        # ★key 本来就是 "x,z" 字符串（★不是元组 ✗ 我第一版当元组用了✓★）
                        _declared_gaps.append("%s=%s" % (key, _bn))
                if ch == ".":
                    # ★模组明确说了"这一格在你这一层附近 (±6) 找不到能站的层"★ ✓
                    #   这与"我没看到"**不是一回事** ✗ ⇒ 单独记 ✓（别混成一个 `?` ✗）
                    no_layer.append(key)
                    continue
                name = legend.get(ch, UNKNOWN_NAME if ch == "@" else ch)
                if ch != "@" and not is_floor(name):
                    # ★★字母 = 模组**按碰撞箱**说"这一层站得住、地板是它"★★ ✗（第 21 轮的设计 ✓
                    #   第 30 轮才真正生效 ✓）：这么说的意思是"**能踩**"✓ 哪怕**名字猜**说它不能 ✗
                    #   （`mcwfurnitures:…_stool_chair` 那类家具 ✓）
                    #   ⇒ ① 先**学**（`is_floor` 立刻变真 ✓ 而且 `surface()` 之后也认它 ✓）
                    #     ② 学不动（真液体/树叶那种 ✓ 或者纯字母没图例 ✓）才降级进 `other` ✗
                    #   ⚠ **顺序**很要紧 ✗：原来这条学习写在下面 `else` 里 ✗ ⇒ 上面 `continue` 先跑了 ✗
                    #     ⇒ 学不到 ＋ 这一格**从图上消失** ✗ ⇒ 图上凭空多一个洞 ✗（假 unreachable 同族 ✓）
                    #   ★★但只学"**不知道的**"，绝不推翻"**知道的**"★★ ✗（第 30 轮 ✓ 写清楚 ✓）：
                    #     名录里已经认出来的非地板（树叶/水/玻璃 ✗）⇒ **不学** ✗ ⇒ 照旧不收 ✓
                    #     理由 ✓：项目**故意**不把树冠当路走 ✓；而"不知道的模组方块"才是真该学的 ✓
                    #     （口径与 `absorb_true` 那条学习一致 ✓：**只覆盖无知，不覆盖已知** ✓）
                    if name and (not is_known(name)) \
                            and learn_shape(name, "full", "dshmap-letter"):
                        learned_n += 1
                    if not is_floor(name):
                        # ★★"名字说它不是地板"**不等于**"这一格要丢掉"★★ ✗（第 30 轮 N6 实测 ✓）
                        #   现场 ✓：`mcwfences:sandstone_grass_topped_wall` 是一堵**墙** ✓
                        #     模组说"**72 层能站**"（墙的碰撞箱高 1.5 ✓ 站在墙头是**可以的** ✓）
                        #     而 `is_floor(墙)` = False ✗ ⇒ 原来这里 `continue` ⇒ **整柱被丢掉** ✗
                        #     ⇒ 那一片在图上是个**洞** ✗（实测 15~16 柱 ✓ 全是墙头 ✓）
                        #       ⇒ 需要沿墙头走一格的时候 ⇒ **假 unreachable** ✗（用户长期抱怨那条 ✓）
                        #   ⇒ 口径 ✓：**照旧记进 `other` 备查** ✓ **但格子照存** ✓
                        #     · "不是地板"只影响 `surface()`（不把墙当平地 ✓ 树冠同理 ✓）
                        #     · 而"**能不能站上去**"由**模组那条结论**说了算 ✓（`mod_stand_y` ✓）
                        other[key] = name
                off = OFF_NUM.get(yrow[i]) if i < len(yrow) else None
                if off is None:
                    # ★★旧模组的"同层近似"★★ ✗ —— 保留（不然图直接没了 ✗）但**记数** ✓
                    #   代价说清楚 ✓：落差看不见 ✗ 一层上站着什么也看不见 ✗
                    m.cols.setdefault((x, z), {})[by - 1] = name
                    assumed += 1
                else:
                    # ★真高度★ ✓：`found` 是**脚占的那一格** ⇒ 地板在它下面一格 ✓
                    m.cols.setdefault((x, z), {})[by + off - 1] = name
                    exact += 1
                if ch == "@":
                    standable_cells += 1
        # ★"图上的名字到底是不是名字"要**记账**★ ✗（第 30 轮 ✓）
        #   这一整族 bug 能躲过五轮电池 ✓ 就是因为**判据从没问过名字** ✗（只问 y/连通/能走 ✓）
        #   ⇒ 现在把它写进 `meta` ✓ ⇒ 调用方可以据此**大声报警** ✓ 而不是静默退化成 `?` ✗
        letters_kept = 0
        for _col in m.cols.values():
            for _n in _col.values():
                if _n and ":" not in str(_n):
                    letters_kept += 1
        m.meta.update({"from": "dshmap", "source": "dshmap", "calls": self.calls,
                       "cached": False, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "dshmap_standable": int(st.group(1)) if st else standable_cells,
                       "cells_at_level": standable_cells, "legend": legend,
                       "legend_ok": bool(legend), "legend_dropped": legend_dropped,
                       "letters_kept": letters_kept,
                       "other_cells": len(other),
                       "coverage": round(m.coverage() * 100, 1),
                       "blevel": bl, "has_offsets": bool(has_off and OFF_NUM),
                       "y_exact": exact, "y_assumed": assumed,
                       "blocked": len(blocked), "blocked_cells": blocked,
                       "mod_standable": mod_stand,
                       "no_layer": ";".join(no_layer),
                       "learned": learned_n, "blocked_disagreements": _declared_gaps})
        learn_save()                      # ★学到就落盘★ ✓（`logs/block_shapes.json` ✓）
        self.save(m, max_age)
        return m

    def probe_cell(self, x, y, z) -> str:
        """独立读一格 ✓（`minecraft:air` = 空的 ✓ **空串 = 读失败** ✗ 调用方必须分清 ✓）"""
        return self.block(x, y, z)

    def scan_route(self, m: "Map", pts, level: int, budget: int = 12, pace: float = 0.25,
                   known: set | None = None) -> dict:
        """★把"这条路"上的格子挨个独立探一遍★ ✓ —— 这就是"**识别道中的障碍物**"✓

        为什么要有它 ✗（用户点的方向 ✓ 2026-09-23 ✓）：
          地图是**按方块种类**建的 ✓ 而模组回执的 `counts[...]` **只列 top-40** ✗
          ⇒ **稀有方块根本不在图里** ✗（实测撞到：`computercraft:computer_command` ✓ 地图完全不知道 ✓）
          ⇒ 光靠"看地图"**识别不出道中的障碍物** ✗ ⇒ 必须在**走之前实地探一遍** ✓

        ★两条"别把桥压死"的规矩★ ✗（2026-09-23 实测 ✓）：
          ① **每一探之间歇一下**（`pace` 秒 ✓）—— 通道是**一台 CC 电脑一次只吃一条**✗
             实测：一口气发三十多条 ⇒ 网关**队列堆到 16** ✗ ⇒ 后面全超时 ✗
          ② **读失败就立刻停**（返回 `aborted=True` ✓）—— "没回执"是**通道有问题**的强信号 ✗
             继续硬发只会把队列堆得更高 ✗（这正是那次的放大机制 ✓）

        返回 ✓：{cells, probed, found:[(x,z,方块)], left, sec, aborted} ✓
          `left>0` ⇒ **没探完** ✓ 要如实说 ✗；`aborted` ⇒ 通道出问题了 ✓ 停下来别硬发 ✓
        """
        import time as _t
        t0 = _t.time()
        ded, seen = [], set()
        for p in pts:
            c = (int(p[0]), int(p[2]))
            if c not in seen:
                seen.add(c)
                ded.append(c)
        found = []
        probed = 0
        left = 0
        aborted = False
        skipped_known = 0
        for (px, pz) in ded:
            # ★已经知道的障碍：**不必再探一遍**★ ✗（2026-09-28 ✓ 障碍记忆 ✓）
            #   这才是"探路"该有的价格 ✓：**第一次**去某个地方才全探 ✓
            #   同一个障碍已经在 `known` 里 ⇒ 跳过 ✓（省一次 ≈0.6 秒 ✓ 也省一次通道占用 ✓）
            if known and (px, pz) in known:
                skipped_known += 1
                continue
            if probed + 1 >= budget:
                left = len(ded) - probed
                break
            for dy in (0, 1):
                if probed:
                    _t.sleep(pace)               # ★别连着轰★ ✗
                name = self.probe_cell(px, level + dy, pz)
                probed += 1
                if not name:
                    aborted = True               # ★读失败（空串）⇒ 通道有问题 ⇒ 立刻收手★ ✗
                    left = len(ded) - probed
                    break
                if name.endswith("air"):
                    continue
                m.cols.setdefault((px, pz), {})[level + dy] = name
                if blocks_space(name):
                    found.append((px, pz, name))
                    break
            if aborted:
                break
        return {"cells": len(ded), "probed": probed, "found": found, "left": left,
                "sec": round(_t.time() - t0, 1), "aborted": aborted,
                "skipped_known": skipped_known}

    # ── ★"把真值灌进图里"★ ✓（2026-09-28 ✓ 让**旧模组**也能交出准图 ✓）────────
    def scan_truth(self, box, max_: int = 600, max_pages: int = 6,
                   pace: float = 0.0) -> dict:
        """★一次调用拿一片地里**全部非空气方块的真实坐标**★ ✓

        ★这招怎么来的★ ✗（值得记住 ✓）：`dshscan` 规定"**给了 match 才回逐格坐标**"✗
        而 `match` 是"方块 id 的**子串**"✓ ⇒ 传 **`:`** —— 每个 id 里都有冒号 ✓
        ⇒ 于是 = "**所有非空气方块**"✓ 实测：100 格的小片 ⇒ `matched=62 page=1/1`
        ⇒ **一次调用** ✓（模组侧 39 微秒 ✓）

        为什么要它 ✗：旧模组的快图**只给一个字母**✗ ⇒ 高度是推的 ✗（错题本 **P99** ✓）
        ⇒ 想让图**今天**就准 ✗ 就得自己把地面读回来 ✓
        （新模组 v2.16 有 `y` 行 ⇒ 不必 ✓ `t_route_view` 会自动跳过 ✓ 省调用 ✓）

        返回 ✓：`{box, cells:[(x,y,z,name)], calls, pages, truncated, sec}`
          `truncated=True` ⇒ **没扫完** ✗ ⇒ 调用方必须如实说 ✗ 不许当成"扫过了"✗
        """
        import time as _t
        t0 = _t.time()
        x0, y0, z0, x1, y1, z1 = (int(v) for v in box)
        cells, page, pages, calls = [], 1, 1, 0
        truncated = False
        while page <= pages:
            if page > int(max_pages):
                truncated = True
                break
            if calls and pace:
                _t.sleep(pace)
            out = self.ab('dshscan %d %d %d %d %d %d ":" %d %d'
                          % (x0, y0, z0, x1, y1, z1, int(max_), page), 90.0)
            calls += 1
            if not out or "cells[" not in out:
                # ★读失败/没有 cells ⇒ 立刻收手★ ✗（接着发只会把单通道压死 ✗ P97 ✓）
                truncated = True
                break
            mm = re.search(r"page=(\d+)/(\d+)", out)
            if mm:
                page, pages = int(mm.group(1)), int(mm.group(2))
            tail = out.split("cells[", 1)[1].split("]", 1)[0]
            # 条目形如 `4118,70,6:minecraft:grass_block,snowy=false` ✓
            #   ⇒ 名字取到**第一个逗号**为止 ✓（状态后缀是逗号分隔的 ✓ 见模组 `stateSuffix` ✓）
            for t in re.finditer(r"(-?\d+),(-?\d+),(-?\d+):([^,\s\]]+)", tail):
                cells.append((int(t.group(1)), int(t.group(2)), int(t.group(3)),
                              t.group(4).strip()))
            if page >= pages:
                break
            page += 1
        return {"box": (x0, y0, z0, x1, y1, z1), "cells": cells, "calls": calls,
                "pages": pages, "truncated": truncated,
                "sec": round(_t.time() - t0, 2)}

    def save(self, m: Map, max_age: float = 600.0) -> None:
        d = m.to_json()
        d["meta"]["max_age"] = max_age
        self.path_of(m.box).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def load(self, box, max_age: float = 600.0):
        p = self.path_of(box)
        if not p.is_file():
            return None
        if time.time() - p.stat().st_mtime > max_age:
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        m = Map(*d["box"])
        m.meta = d.get("meta", {})
        for k, v in (d.get("cols") or {}).items():
            x, z = (int(t) for t in k.split(","))
            m.cols[(x, z)] = {int(y): b for y, b in v.items()}
        return m

    def get(self, box, max_age: float = 600.0, force: bool = False) -> Map:
        key = tuple(int(v) for v in box)
        if not force:
            hit = Reader._MEM.get(key)
            if hit is not None and (time.time() - hit[1]) <= max_age:
                m = hit[0]
                m.meta["from_cache"] = "mem"
                return m
            m = self.load(box, max_age)
            if m is not None:
                m.meta["from_cache"] = "disk"
                Reader._MEM[key] = (m, time.time())
                return m
        m = self.build(box, max_age=max_age)
        m.meta["from_cache"] = False
        Reader._MEM[key] = (m, time.time())
        return m


def ascii_only(txt: str) -> str:
    return CJK.sub("?", txt or "")


def main(argv) -> int:
    box = None
    if "--around" in argv:
        r = Reader()
        p = r.pos()
        if not p:
            print("NO BOT POS")
            return 1
        rad = int(argv[argv.index("--around") + 1]) if len(argv) > argv.index("--around") + 1 else 12
        box = (int(p[0]) - rad, int(p[1]) - 8, int(p[2]) - rad,
               int(p[0]) + rad, int(p[1]) + 6, int(p[2]) + rad)
    elif "--box" in argv:
        i = argv.index("--box")
        box = tuple(int(v) for v in argv[i + 1:i + 7])
    if not box:
        print("usage: py tools/mapread.py --around 12 | --box x0 y0 z0 x1 y1 z1")
        return 2
    r = Reader()
    m = r.get(box)
    print("box=%s calls=%s sec=%s coverage=%s from_cache=%s"
          % (box, m.meta.get("calls"), m.meta.get("sec"),
             m.meta.get("coverage"), m.meta.get("from_cache")))
    print(ascii_only(m.ascii()))
    print(m.legend())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
