#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tag_census.py -- ★方块标签普查（任务书·阶段 0）★ 纯离线 · 只读 · 零游戏改动

三种模式（★同一个工具 ✗ 一份实现✓★）：
  species   ：给定物种清单 ⇒ 逐个报"带几个标签／命中哪些家族／零命中"
  universe  ：★全量✗★ —— 把**物种宇宙**从三份**离线代理**拼出来再算覆盖率：
                · `assets/<ns>/blockstates/<name>.json`（★最接近"有这个方块"✓★）
                · `data/<ns>/loot_tables/blocks/<name>.json`
                · 标签成员本身（★分子那部分 ✓ 不能只算它✗★）
              ⚠ ★这是**代理** ✗ 不是游戏注册表本身✗★ —— 真注册表要一次**只读导出**
                （★模组侧一条命令 ✗ 零判定逻辑改动✓★）。报告里会明写这一点 ✓
  families  ：★家族表反推✗★ —— 从全部标签里按**名字模式**找出"天然对应形状家族"的标签
              （★跨命名空间 ✗ `forge:`／`c:`／模组自己的也算✓★），并报各自的覆盖面 ✓

★做法✗★：标签是**数据**（datapack JSON ✓ 游戏认的就是这份 ✓）⇒
  读 `data/<ns>/tags/blocks/*.json` 与 `tags/block/*.json`（★两种拼法都认✓★），
  把 `#引用` 做**传递闭包**（★环也安全✓★），得到 标签→物种 与 物种→标签 ✓

★诚实边界（★不许把测不到说成没有✗★）★
  ① 若某模组在**代码里**动态加标签 ⇒ 本方法看不见 ✓
  ② ★原版来源（vanilla jar）找不到时会**大声说** ✗ 否则 `minecraft:` 家族会假性为 0✗★
  ③ ★零命中 ≠ 一定没标签 ✗ 也可能是物种名拼错 ✗ 所以额外报"这个名字有没有在任何标签里出现过"✗★
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys, paths as PA
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PACK = PA.MC_HOME

# ★家族标签：物理/语义上"这一族该怎么判"最要紧的那些✗★（★确信存在的才写 ✗ 写错只显示 0✗★）
FAMILY = (
    ("叶子", "minecraft:leaves"), ("原木", "minecraft:logs"), ("木板", "minecraft:planks"),
    ("半砖", "minecraft:slabs"), ("楼梯", "minecraft:stairs"), ("栅栏", "minecraft:fences"),
    ("墙", "minecraft:walls"), ("栅栏门", "minecraft:fence_gates"), ("门", "minecraft:doors"),
    ("活板门", "minecraft:trapdoors"), ("花", "minecraft:flowers"),
    ("小花", "minecraft:small_flowers"), ("树苗", "minecraft:saplings"),
    ("庄稼", "minecraft:crops"), ("能爬", "minecraft:climbable"),
    ("可替换", "minecraft:replaceable"), ("剑快挖", "minecraft:sword_efficient"),
    ("镐可挖", "minecraft:mineable/pickaxe"), ("斧可挖", "minecraft:mineable/axe"),
    ("锹可挖", "minecraft:mineable/shovel"), ("锄可挖", "minecraft:mineable/hoe"),
    ("要石具", "minecraft:needs_stone_tool"), ("要铁具", "minecraft:needs_iron_tool"),
    ("要钻具", "minecraft:needs_diamond_tool"), ("按钮", "minecraft:buttons"),
    ("压力板", "minecraft:pressure_plates"), ("牌子", "minecraft:signs"),
    ("旗", "minecraft:banners"), ("铁轨", "minecraft:rails"), ("蜡烛", "minecraft:candles"),
    ("灯笼", "minecraft:lanterns"), ("土", "minecraft:dirt"), ("沙", "minecraft:sand"),
    ("石基", "minecraft:base_stone_overworld"), ("通用矿", "c:ores"), ("forge矿", "forge:ores"),
    ("花盆", "minecraft:flower_pots"), ("珊瑚", "minecraft:corals"),
    # ★★2026-10-13 补（★用户裁决 C5 ✗ §79.221✗★）✗★★：
    #   ★为什么用它✗★：★只靠碰撞**分不开**"能游的水"与"会死的岩浆"✗★
    #     （★两个都是 `liquid` ✗ §79.175 记过✓★）⇒ ★危险必须由**语义**补上✗★ ✓
    #   ★凭什么选这几个 id✗★：★先报数再选（★§79.221✗★）✗★ ——
    #     `minecraft:fire` 3 个 ✗ `farmersdelight:heat_sources` 10 ✗
    #     `amendments:cauldron_heat_source` 29 ✗ `create:passive_boiler_heaters` 17 ✗
    #     `minecraft:strider_warm_blocks` 1 ✗★ ✓
    #   ★★而 `minecraft:replaceable` **故意不收**✗★★：★连 `minecraft:water` 都命中它✗
    #     ⇒ 收了就会把水也当岩浆 ✗★ ✓
    #   ★抽查✗★：★`torch`／`glowstone` 一个都不命中 ⇒ "亮"没被吞✗★ ✓
    ("火", "minecraft:fire"),
    ("岩浆", "farmersdelight:heat_sources"),
    ("岩浆", "amendments:cauldron_heat_source"),
    ("岩浆", "create:passive_boiler_heaters"),
    ("岩浆", "minecraft:strider_warm_blocks"),
)

# ★家族表**反推**用的名字模式（★跨命名空间 ✗ 只看标签路径那一段✓★）
FAMILY_PATTERNS = (
    ("叶子", r"(^|/)leaves(_|$)"),
    ("原木", r"(^|/)logs?(_that_burn|_that_dont_burn)?$"),
    ("木板", r"(^|/)planks$"),
    ("半砖", r"(^|/)slabs?$"),
    ("楼梯", r"(^|/)stairs$"),
    ("栅栏", r"(^|/)fences$"),
    ("墙", r"(^|/)walls$"),
    ("门", r"(^|/)doors$"),
    ("活板门", r"(^|/)trapdoors$"),
    ("花", r"(^|/)flowers?$|(^|/)small_flowers$"),
    ("树苗", r"(^|/)saplings$"),
    ("庄稼", r"(^|/)crops$"),
    ("能爬", r"(^|/)climbable$"),
    ("可替换", r"(^|/)replaceable"),
    ("按钮", r"(^|/)buttons$"),
    ("压力板", r"(^|/)pressure_plates$"),
    ("牌子", r"(^|/)signs$"),
    ("旗", r"(^|/)banners$"),
    ("铁轨", r"(^|/)rails$"),
    ("蜡烛", r"(^|/)candles$"),
    # ★2026-10-03✗★：`lanterns?$` 会把 `chipped:jack_o_lantern`（★南瓜灯 ✗ 整方块✓★）
    #   误收进"灯笼族" ⇒ ★本包**没有**灯笼族 ✗ 如实留空 ✗ 别用正则凑一个✗★ ✓
    ("灯笼", r"(^|/)lanterns$"),
    ("可挖", r"(^|/)mineable/"),
    ("要工具", r"(^|/)needs_[a-z]+_tool$"),
    ("剑快挖", r"(^|/)sword_efficient$"),
    ("玻璃", r"(^|[_/])glass(_panes|_blocks)?$"),
    ("羊毛", r"(^|[_/])wool$"),
    ("地毯", r"(^|[_/])carpets?$|wool_carpets$"),
    # ★★2026-10-03 第二轮：**带前缀**的也算✗★★
    #   ★又一个我自己踩过的同一类漏✗★：★`wool_carpets` 因为前面是**下划线**被漏掉 ✗
    #     而 `minecraft:wooden_slabs`（★195 个成员✓★）／`wooden_stairs`（195）／
    #     `wooden_fences`（255）／`wall_signs`（192）**同样是带前缀的**✗★ ✓
    #   ⇒ ★口径✗★：★族名前后都允许 `_` ✗ 但**只限已经认下的那些族词**✗★ ——
    #     ★不新增没认过的词 ✗ 因为"★见到就收★"正是 §79.91 那条教训✗★ ✓
    #   （★而"★到底该不该收★"的**正式判据**仍是 ④补 的"★成员碰撞判定一致率★" ✗ 那个还在等导出✓★）
    ("半砖", r"(^|[_/])slabs?$"), ("楼梯", r"(^|[_/])stairs$"),
    ("栅栏", r"(^|[_/])fences$"), ("墙", r"(^|[_/])walls$"),
    ("门", r"(^|[_/])doors$"), ("活板门", r"(^|[_/])trapdoors$"),
    ("按钮", r"(^|[_/])buttons$"), ("压力板", r"(^|[_/])pressure_plates$"),
    ("牌子", r"(^|[_/])signs$"), ("旗", r"(^|[_/])banners$"),
    ("铁轨", r"(^|[_/])rails$"), ("蜡烛", r"(^|[_/])candles$"),
    ("叶子", r"(^|[_/])leaves$"), ("原木", r"(^|[_/])logs?(_that_burn)?$"),
    ("木板", r"(^|[_/])planks$"),
    ("矿石", r"(^|/)ores?$|(^|/)ore_bearing"),
    ("箱子类", r"(^|/)(chests?|barrels?|shulkers?)$"),
    # ★★2026-10-03 补：**精确名**那几个也成族✗★★（★现场抓到的缺口✗★）
    #   ★现象✗★：★`minecraft:dirt` 与 `minecraft:cobblestone` 落在"★表中无★"✗★ ——
    #     ★可它们**明明**在 `minecraft:dirt` ／ `minecraft:base_stone_overworld` 里✗★ ✓
    #   ★真因✗★：★上面那些正则只认"★复数／派生名★" ✗ 而这几族的标签名是**单数精确名**✗★ ✓
    #   ⇒ ★口径✗★：★精确名也**算候选** ✗ 但仍要过 §4 那条"★按成员数排序复核✗★" ✗ 不许见了就收✗★ ✓
    ("土", r"(^|/)dirt$"), ("沙", r"(^|/)sand$"),
    ("石基", r"(^|/)base_stone_[a-z_]+$"),
    ("花盆", r"(^|/)flower_pots?$"), ("珊瑚", r"(^|/)corals?$"),
)

# ★★**故意不做形状家族**的那些（★要写理由 ✗ 不许默默没有✗★）✗★★
#   ★为什么需要这张表✗★：★判据 D4 要**双向**查（★模式 ⊆ 映射 ✗ 映射 ⊆ 模式✓★）✗
#   而下面这几个**确实**没有映射 ✗ 若不明写 ✗ 判据就分不清"★忘了★"与"★故意★"✗★ ✓
#   （★口径✗★：★不一致可以有 ✗ 但一条都不许没声明✓★ —— 这张表就是那条口径的落点✓★）
NOT_SHAPE_FAMILY = {
    "可挖": "★工具归属（能不能挖 / 用什么挖）✗ 不是形状 ✗ 铁律 1 说标签只管语义✓★",
    "要工具": "★同上（★`needs_*_tool` 说的是工具门槛✓★）",
    "剑快挖": "★同上（★`sword_efficient` 是工具效率✓★）",
    "灯笼": "★这一族**在本包里没有标签**（★只有 `chipped:jack_o_lantern` ✗ 那是南瓜灯✓★）"
            "⇒ 见了就收会**误收整方块** ✗ 见 §79.91 ✓",
    # ★★2026-10-03 第三轮：`可替换` 移出形状家族✗★★（★有**证据** ✗ 不是感觉✓★）
    #   ★证据✗★：★367 条"★标签自相冲突★"**全部**是同一组 `canopy／pass`✗★ ——
    #     ★物种同时落在 `minecraft:leaves`（★canopy✓★）与 `minecraft:replaceable_by_trees`✗★ ✓
    #   ★判别✗★：★`replaceable_by_trees` 说的是"★世界生成时树能不能把它盖掉★"✗
    #     ★那是**放置属性** ✗ 不是"★它是什么形状的方块★"✗★ ⇒ ★它不是形状族✗★ ✓
    #   ⇒ ★修它属于"★成因 A：我自己的映射错了★" ✗ 我自己就能修 ✗ 不用等世界判断✗★ ✓
    "可替换": "★放置属性（★`replaceable_by_trees` 等✓★）✗ 不是形状 ✗ 留着会与 `叶子` **自相冲突**"
            "（★实测 367 条 ✗ 全是 `canopy／pass` 这一组✓★）",
    # ★★2026-10-13（★用户裁决 C5✗★）✗★★：这两个是**政策**类别 ✗ 不是形状族 ✗★ ✓
    #   ★理由✗★：★成员几何**五花八门**✗★ —— ★`minecraft:lava`＝`liquid` ✗
    #     `minecraft:magma_block`＝`full` ✗ `minecraft:campfire`＝`full`✗★ ⇒
    #   ★★硬给它们一个几何期望 ✗ 会**凭空造出新分歧** ✗ 把"未声明 0"打烂✗★★ ✓
    #   ★它们要回答的是另一件事✗★：★"★进去会不会死★" ✗ 而那是**政策**栏（★§11 phys／sem 那一族✓★）✗★ ✓
    "岩浆": "★政策类别（★危险✗★）✗ 成员几何五花八门（★岩浆=`liquid` ✗ 岩浆块／篝火=`full`✓★）"
            "⇒ 给不出单一几何期望 ✗ 给了会凭空造分歧 ✗ 它答的是「进去会不会死」不是「什么形状」",
    "火": "★政策类别（★危险✗★）✗ 同上：`minecraft:fire` 只 3 个成员（★火／灵魂火／ars 一个✓★）"
          "✗ 几何上是可穿过的（★`pass`✓★）✗ 但它答的是「会不会烧死」",
}


def tag_id(name: str):
    """★`data/<ns>/tags/blocks/<p>.json` ⇒ `<ns>:<p>`✗★（★两种目录拼法都认✓★）"""
    if not name.endswith(".json"):
        return None
    parts = name.split("/")
    if len(parts) < 5 or parts[0] != "data" or parts[2] != "tags":
        return None
    if parts[3] not in ("blocks", "block"):
        return None
    return "%s:%s" % (parts[1], "/".join(parts[4:])[:-5])


def species_of_asset(name: str):
    """★`assets/<ns>/blockstates/<p>.json` ⇒ `<ns>:<p>`✗★"""
    if not name.endswith(".json"):
        return None
    parts = name.split("/")
    if len(parts) < 4 or parts[0] != "assets" or parts[2] != "blockstates":
        return None
    return "%s:%s" % (parts[1], "/".join(parts[3:])[:-5])


def species_of_loot(name: str):
    """★`data/<ns>/loot_tables/blocks/<p>.json` ⇒ `<ns>:<p>`✗★"""
    if not name.endswith(".json"):
        return None
    parts = name.split("/")
    if len(parts) < 5 or parts[0] != "data" or parts[2] != "loot_tables" or parts[3] != "blocks":
        return None
    return "%s:%s" % (parts[1], "/".join(parts[4:])[:-5])


def _norm(name: str) -> str:
    """★把**裸名**补成 `minecraft:`✗★（★2026-10-04 修的真瑕疵✗★）

    ★现象✗★：★分歧清单里有 **19** 条"★导出没覆盖★" ✗ 长得像 `bamboo_planks` ✗
      `black_carpet`（★**没有命名空间**✓★）✗ 而 `kb_export --reconcile` 里
      "★只在宇宙里★"那批（★`acacia_door` ✗ `acacia_leaves`✓★）**同一个毛病**✗★ ✓
    ★真因✗★：★1.20 的标签格式**允许裸名** ✗ 它的意思就是 `minecraft:<裸名>`✗★ ⇒
      ★我原来**原样收下** ✗ 于是它既**对不上**导出（★那边是 `minecraft:black_carpet`✓★）✗
      又在宇宙里多出一批**不存在的物种**✗★ ✓
    ★⇒ 口径✗★：★从标签里读到的名字 ✗ **要么**带命名空间 ✗ **要么**补 `minecraft:`✗★ ✓
    """
    n = str(name or "").strip()
    if not n:
        return n
    return n if ":" in n else ("minecraft:" + n)


def _members(d):
    out = []
    for v in (d.get("values") or []):
        if isinstance(v, str) and not v.startswith("#"):
            out.append(_norm(v))
        elif isinstance(v, dict) and v.get("id") and not str(v["id"]).startswith("#"):
            out.append(_norm(str(v["id"])))
    return out


def _refs(d):
    out = []
    for v in (d.get("values") or []):
        if isinstance(v, str) and v.startswith("#"):
            out.append(_norm(v[1:]))
        elif isinstance(v, dict) and str(v.get("id") or "").startswith("#"):
            out.append(_norm(str(v["id"])[1:]))
    return out


def scan(jars, roots, want_universe=True):
    """★一趟扫完✗★：返回 (标签来源, 宇宙集合, 统计)"""
    src, uni = [], set()
    stats = {"tags": 0, "bad": 0, "jars": 0, "jars_bad": 0, "spellings": {},
             "blockstates": 0, "loot": 0, "dirs": 0}
    for p in jars:
        try:
            with zipfile.ZipFile(p) as z:
                stats["jars"] += 1
                for n in z.namelist():
                    tid = tag_id(n)
                    if tid:
                        stats["tags"] += 1
                        stats["spellings"][n.split("/")[3]] = \
                            stats["spellings"].get(n.split("/")[3], 0) + 1
                        try:
                            src.append((p.name, n, z.read(n)))
                        except Exception:
                            stats["bad"] += 1
                        continue
                    if not want_universe:
                        continue
                    s = species_of_asset(n)
                    if s:
                        uni.add(s)
                        stats["blockstates"] += 1
                        continue
                    s = species_of_loot(n)
                    if s:
                        uni.add(s)
                        stats["loot"] += 1
        except Exception:
            stats["jars_bad"] += 1
    for r in roots:
        if not r.is_dir():
            continue
        stats["dirs"] += 1
        for p in r.rglob("*.json"):
            rel = str(p).replace("\\", "/")
            i = rel.find("/data/")
            j = rel.find("/assets/")
            if i >= 0:
                n = rel[i + 1:]
                tid = tag_id(n)
                if tid:
                    stats["tags"] += 1
                    src.append((str(r), n, p.read_bytes()))
                    continue
                if want_universe:
                    s = species_of_loot(n)
                    if s:
                        uni.add(s)
            elif j >= 0 and want_universe:
                s = species_of_asset(rel[j + 1:])
                if s:
                    uni.add(s)
    return src, uni, stats


def build(src):
    mem, ref = {}, {}
    for _label, name, data in src:
        tid = tag_id(name)
        if not tid:
            continue
        try:
            d = json.loads(data.decode("utf-8", "replace"))
        except Exception as e:
            # 记录：一份标签文件读不了 ⇒ 普查静默少一族（分类依据跟着少）——§79.401 那一族
            print("[记录] 标签文件读不了 %s（%s）⇒ 普查少一份"
                  % (name, type(e).__name__), file=sys.stderr)
            continue
        if not isinstance(d, dict):
            continue
        mem.setdefault(tid, set()).update(_members(d))
        ref.setdefault(tid, set()).update(_refs(d))
    return mem, ref


def closure(mem, ref):
    """★标签成员的传递闭包✗★ —— ★用**不动点** ✗ 不用 DFS＋memo✗★

    ★★2026-10-03 判据抓到的真 bug（✗ 我自己的）✗★★：
      第一版是 DFS ＋ memo ✓ 而**环里**的标签会把「★在环里没展开完的★」结果**记进 memo** ✗
      ⇒ 之后谁再来问它 ✗ 拿到的是**残缺集合** ✓
      现象 ✓：`tag_census_test` 的 **C4b/C5** 时红时绿 —— ★因为遍历顺序取决于 `set` 的
      **哈希顺序** ✗ 而 Python 的字符串哈希**每个进程都随机**✗★ ✓
      ⇒ ★这是个**顺序相关的真缺陷** ✗ 而真实数据里模组标签确实互相引用✓★
    ★不动点✗★：反复把"引用的那些标签的成员"并进来 ✗ 直到某一轮没有变化 ✓
      ⇒ ★与顺序**无关** ✗ 环自然收敛✓★（★标签数 1833 ✗ 轮数很少 ✓ 代价可接受✓★）
    """
    cur = {t: set(mem.get(t) or ()) for t in (set(mem) | set(ref))}
    changed = True
    while changed:
        changed = False
        for t, rs in ref.items():
            add = set()
            for r in rs:
                add |= cur.get(r) or set()
            if not add <= cur[t]:
                cur[t] |= add
                changed = True
    return cur


def invert(full):
    out = {}
    for t, members in full.items():
        for s in members:
            out.setdefault(s, set()).add(t)
    return out


def family_tags(full, patterns=FAMILY_PATTERNS, explicit=None):
    """按名字模式把「天然对应形状家族」的标签挑出来 —— 返回 {家族: [标签id,…]}

    2026-10-13 改（用户裁决 A1 / §79.221）：
      现象：我把 火/岩浆 的**显式标签 id** 加进上面那张 FAMILY，重生成后
        state/tags_category.json 里**还是没有**这两个类别。
      真因：这个函数**只吃 patterns**，上面那张显式表**根本没被调用** ——
        这正是裁决 A1 说的「五张表并存，没接线」在咬人。
      改法：**显式 id 先收**（它是更硬的证据），正则再并进来。
      注意：同一族常有多个命名空间各一份（minecraft/forge/模组自己的），取并集。
      （原注：我那张 FAMILY 是凭记忆列的，实测记错了两个 —— minecraft:lanterns 与
        minecraft:carpets 这套包里根本没有 => 所以要从数据里挑，不只信记忆。）
    """
    out = {}
    # 显式 id 先收（更硬的证据）
    for fam, tid in (FAMILY if explicit is None else explicit):
        if tid in full:
            lst = out.setdefault(fam, [])
            if tid not in lst:
                lst.append(tid)
    # 正则再并进来（不覆盖显式收的）
    for fam, pat in patterns:
        rx = re.compile(pat)
        hits = sorted(t for t in full if rx.search(t.split(":", 1)[-1]))
        if hits:
            lst = out.setdefault(fam, [])
            for h in hits:
                if h not in lst:
                    lst.append(h)
    for fam in list(out):
        out[fam] = sorted(out[fam])
    return out


def family_union(full, fam_ids):
    """★一个家族（可能好几个标签）覆盖的物种并集✗★"""
    cov = set()
    for t in fam_ids:
        cov |= full.get(t) or set()
    return cov


def sources_of(args):
    mods = PACK / "mods"
    jars = sorted(mods.glob("*.jar")) if mods.is_dir() else []
    # ★★2026-10-03 现场抓到的**污染**（修）✗★★
    #   原来这里写的是 `versions/*/*.jar` ⇒ 把 **别的整合包**（`1.21.11`／`ATM10SKY`／
    #   `BeLoong …`）的标签也读了进来 ✗ ⇒ 标签宇宙被**放大** ✗ 而且那 `tags/block`
    #   拼法根本是**别的版本**的习惯 ✗（★本包只扫出 `blocks` 一种 ✗ 2683 个✓★）
    #   ⇒ ★只收**本包自己的**版本 jar✗★；★并把每个候选**逐个报出来**✗ 好审计 ✓
    own = sorted(PACK.glob("*.jar"))
    vanilla = own
    roots = [PACK / "kubejs" / "data", PACK / "config" / "openloader" / "data"]
    return jars, vanilla, roots


def has_tag(jar, want="minecraft:leaves"):
    """★这个 jar 里到底有没有那条标签✗★（★用来判"原版来源在不在" ✗ 逐 jar 可审计✓★）"""
    try:
        with zipfile.ZipFile(jar) as z:
            return any(tag_id(n) == want for n in z.namelist())
    except Exception:
        return False


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="species",
                    choices=("species", "universe", "families", "tags", "cross"))
    ap.add_argument("--species", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--ns-top", type=int, default=25)
    ap.add_argument("--min-cov", type=int, default=20,
                    help="★`tags` 模式：只列成员数 >= 这个的标签✗★")
    a = ap.parse_args(argv)

    jars, vanilla, roots = sources_of(a)
    print("== 来源 ==")
    print("  模组 jar %d 个 ｜ ★本包版本 jar 候选 %d 个（★只收本包 ✗ 别的整合包一律不收✓★）"
          % (len(jars), len(vanilla)))
    for v in vanilla:
        print("     %s ⇒ 有 `minecraft:leaves` 吗＝%s" % (v.name, has_tag(v)))
    print("  数据目录：%s" % [str(r) for r in roots if r.is_dir()])
    src, uni, st = scan(jars, roots)
    have_vanilla = False
    if vanilla:
        vsrc, vuni, vst = scan(vanilla, [], want_universe=(a.mode in ("universe", "cross")))
        have_vanilla = any(tag_id(n) == "minecraft:leaves" for (_l, n, _d) in vsrc)
        src += vsrc
        uni |= vuni
    print("  读到标签文件 %d（坏 %d）｜ 拼法 %s" % (st["tags"], st["bad"], st["spellings"]))
    print("  ★原版来源 %s✗★" % ("在 ✓ `minecraft:` 家族可信"
                                if have_vanilla else "**没找到** ✗ 家族会假性为 0 ✗ 别当没有"))

    mem, ref = build(src)
    full = closure(mem, ref)
    from_tag = invert(full)
    print("  标签 %d 个 ｜ 标签里出现过的物种 %d 个" % (len(full), len(from_tag)))

    if a.mode == "species":
        sp = [s.strip() for s in a.species.split(",") if s.strip()]
        if a.file and pathlib.Path(a.file).is_file():
            sp += [s.strip() for s in pathlib.Path(a.file).read_text(
                encoding="utf-8").splitlines() if s.strip()]
        sp = list(dict.fromkeys(sp))
        if not sp:
            print("★没有物种清单 ⇒ 什么都不做✗★")
            return 2
        print("")
        print("== 逐个物种（共 %d）==" % len(sp))
        n_any = n_fam = 0
        for s in sp:
            tags = from_tag.get(s) or set()
            fam = [nm for (nm, t) in FAMILY if t in tags]
            n_any += bool(tags)
            n_fam += bool(fam)
            v = ("★零命中 ✗ 出现在别的标签里吗＝%s★" % (s in from_tag)) if not tags \
                else ("家族：%s" % ("／".join(fam) if fam else "（★没有家族命中★）"))
            print("  %-46s 标签 %-3d %s" % (s, len(tags), v))
            if tags:
                print("        %s" % "  ".join(sorted(tags)[:a.top]))
        print("")
        print("== 覆盖率（抽样）==")
        print("  带任意标签：%d/%d = %.0f%%" % (n_any, len(sp), 100.0 * n_any / max(1, len(sp))))
        print("  带家族标签：%d/%d = %.0f%%" % (n_fam, len(sp), 100.0 * n_fam / max(1, len(sp))))
        return 0

    if a.mode == "universe":
        uni |= set(from_tag)
        tagged = {s for s in uni if s in from_tag}
        fam_tagged = {s for s in uni
                      if any(t in (from_tag.get(s) or set()) for (_n, t) in FAMILY)}
        print("")
        print("== 全量覆盖率（★宇宙＝三份离线代理的并集 ✗ 不是注册表本身✗★）==")
        print("  宇宙大小 %d ｜ 带任意标签 %d = %.0f%% ｜ 带家族标签 %d = %.0f%%"
              % (len(uni), len(tagged), 100.0 * len(tagged) / max(1, len(uni)),
                 len(fam_tagged), 100.0 * len(fam_tagged) / max(1, len(uni))))
        print("  组成：blockstates %d ｜ loot_tables %d ｜ 标签成员 %d"
              % (st["blockstates"], st["loot"], len(from_tag)))
        by_ns = {}
        for s in uni:
            ns = s.split(":")[0]
            d = by_ns.setdefault(ns, [0, 0])
            d[0] += 1
            if s in from_tag:
                d[1] += 1
        rows = sorted(by_ns.items(), key=lambda kv: -kv[1][0])[:a.ns_top]
        print("")
        print("== 按命名空间的覆盖率（★前 %d ✗ 这就是「哪个模组没登记标签」的答案✓★）==" % a.ns_top)
        print("  %-34s %8s %8s %s" % ("命名空间", "物种", "带标签", "占比"))
        for ns, (tot, tag) in rows:
            print("  %-34s %8d %8d %5.0f%%" % (ns, tot, tag, 100.0 * tag / max(1, tot)))
        zero_ns = [(ns, v[0]) for ns, v in by_ns.items() if v[1] == 0]
        zero_ns.sort(key=lambda kv: -kv[1])
        print("")
        print("★零标签的命名空间 %d 个 ✗ 前 12✗★：%s"
              % (len(zero_ns), "  ".join("%s(%d)" % (n, c) for n, c in zero_ns[:12])))
        return 0

    if a.mode == "tags":
        # ★★按成员数列出全部标签✗★★（2026-10-03 ㊲ 第 ② 项）
        #   为什么 ✗：上一轮的"家族反推"只挑**我写下的模式** ✗ 于是真名（★`wool_carpets`
        #   这种我记错/记不全的✓★）**永远不会冒出来** ✗ ⇒ 改成把标签**按大小全列** ✗
        #   ★人（或下一轮的我）从这张表里挑家族 ✗ 而不是靠记忆✗★ ✓
        rows = sorted(full.items(), key=lambda kv: -len(kv[1]))
        print("")
        print("== 标签按成员数排序（★成员数 >= %d ✗ 共 %d 个标签✓★）=="
              % (a.min_cov, len(rows)))
        fam_of = {}
        for fam, ids in family_tags(full).items():
            for t in ids:
                fam_of.setdefault(t, []).append(fam)
        print("  %-46s %8s  %s" % ("标签", "成员数", "家族模式命中"))
        shown = 0
        for t, members in rows:
            if len(members) < a.min_cov:
                break
            print("  %-46s %8d  %s" % (t, len(members), "／".join(fam_of.get(t, [])) or ""))
            shown += 1
        print("  （★共列出 %d 个 ✗ 阈值 %d ✗ 想全看就把 --min-cov 调小✓★）"
              % (shown, a.min_cov))
        return 0

    if a.mode == "cross":
        # ★★家族 × 命名空间交叉表✗★★（2026-10-03 ㊲ 第 ③ 项）
        #   为什么 ✗：★"有标签" ≠ "有**这一族**的标签"✗★ ——
        #     ★`mcwfences` 100% 带标签 ✗ 可它的墙不在 `minecraft:walls` 里 ✗
        #     也没有自己的 `*:walls`✗★ ⇒ ★光看总覆盖率会把这种**藏住**✗★ ✓
        #   ★★第一版这里写错了✗★★：我把「★**标签**的命名空间★」和「★**物种**的命名空间★」
        #     混成了一个 ✗ ⇒ 分子（★`minecraft:logs` 里装着 `productivetrees:` 的方块✓★）
        #     冲出了分母 ✗ ⇒ 打出 `chipped 104%` ／ `minecraft 2291%` 这种**荒唐数**✗★ ✓
        #   ★正确口径✗★：★按**物种**的命名空间分组 ✗ 分母是**宇宙**的大小✗（★不是"标签成员"✓★）✗
        #     每一族先算"★这一族覆盖的物种全体★" ✗ 再和某个物种命名空间求交✓★
        ft = family_tags(full)
        fams = list(ft.keys())
        fam_cov = {f: family_union(full, ft[f]) for f in fams}
        species = set(uni) | set(from_tag)
        by_ns = {}
        for s in species:
            by_ns.setdefault(s.split(":", 1)[0], set()).add(s)
        top = sorted(by_ns.items(), key=lambda kv: -len(kv[1]))[:a.ns_top]
        fam_show = fams[:8]
        print("")
        print("== 家族 × 命名空间（★按**物种**命名空间 ✗ 前 %d 大 ✓★）==" % a.ns_top)
        print("  分母＝该命名空间的物种数（★宇宙 ∪ 标签成员✓★）｜ ★`-` ＝ 这一族一个都没有✗★")
        print("  %-24s %6s %7s  %s" % ("命名空间", "物种", "带任意", "  ".join(fam_show)))
        for ns, mem in top:
            tot = len(mem)
            any_cov = len([s for s in mem if s in from_tag])
            cells = []
            for f in fam_show:
                c = len(fam_cov[f] & mem)
                cells.append(("%3.0f%%" % (100.0 * c / tot)) if c else "  - ")
            print("  %-24s %6d %6.0f%%  %s"
                  % (ns, tot, 100.0 * any_cov / max(1, tot), "  ".join(cells)))
        print("")
        print("★藏起来的那些（★带任意标签 >=50%% ✗ 而某一族**一点没有** ✗ 且这一族在别处存在✓★）★")
        n_hidden = 0
        for ns, mem in top:
            tot = len(mem)
            any_cov = 100.0 * len([s for s in mem if s in from_tag]) / max(1, tot)
            if any_cov < 50:
                continue
            missing = [f for f in fams if not (fam_cov[f] & mem)]
            if missing:
                n_hidden += 1
                print("  %-24s 物种 %-5d 带任意 %3.0f%%  ｜ 没有的族：%s"
                      % (ns, tot, any_cov, "／".join(missing[:10])))
        if not n_hidden:
            print("  （★没有 ✗ 前 %d 大命名空间里每一族都有人认领✓★）" % a.ns_top)
        return 0
    # families
    print("")
    print("== 家族表反推（★按名字模式 ✗ 跨命名空间✓★）==")
    print("  %-10s %6s %10s  %s" % ("家族", "标签数", "覆盖物种", "命中标签样例"))
    for fam, pat in FAMILY_PATTERNS:
        rx = re.compile(pat)
        hits = [t for t in full if rx.search(t.split(":", 1)[-1])]
        cov = set()
        for t in hits:
            cov |= full[t]
        print("  %-10s %6d %10d  %s"
              % (fam, len(hits), len(cov), "  ".join(sorted(hits)[:a.top])))
    print("")
    print("★怎么用✗★：★上面哪一族「标签数>0 而覆盖物种很大」 ✗ 那一族就该进家族表✗★；"
          "★我原来那张 `FAMILY` 是**凭记忆**列的 ✗ 这张是从数据里反推的✗★")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
