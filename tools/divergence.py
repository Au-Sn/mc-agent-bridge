#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""divergence.py -- ★分歧清单（任务书阶段 3 ✗ 大半机械✓★）★

★它回答什么✗★：★把**现黑名单**（`mapread.shape()` 那条路）和**标签**（数据侧的家族标签）
  逐个物种比一遍 ✗ 分三栏✗★ ✓

| 栏 | 含义 | 处置（★任务书 §4✗★） |
|---|---|---|
| ★一致✗★ | 两边说同一族 | ★无事✗★ |
| ★不一致✗★ | 两边说法不同 | ★逐条送校准场／世界物理验证 ⇒ 按 **U1 口径显式声明**✗★（★book_pile／azalea 那族全在这栏 ✗ **历史错题的沉淀机械地变成新系统的例外表** ✗ 不许人工重翻✓★） |
| ★表中无✗★ | 标签里没有它 | ★黑名单继续兜底 ⇒ 登记"待覆盖"✗★ |

★三处纪律✗★
  ① ★标签只给**语义**（★族名✗★）✗ 物理仍听碰撞形状 ✗ 这里**不判**"谁对" ✗ 只**列出分歧**✗★ ✓
  ② ★`TAG_FAMILY` 是**显式数据**（★不是正则 ✗ 不是猜 ✗ 见 §79.94 那条教训✓★）✗
     要改就改这张表 ✗ 而它是**给人审**的✗★ ✓
  ③ ★一个物种同时落在**两个互相冲突**的家族标签里 ⇒ 这**本身**就是一条"★不一致★" ✗
     要**显式声明** ✗ 不许挑一个了事✗★ ✓（★登记册第 2 条✓★）

★诚实边界✗★：★宇宙 ＝ 标签里出现过的物种（★今天 23918 个✗★）✗
  ★不是**注册表全集**（★那要导出 ✗ 见 `docs/方案-注册表只读导出.md`✓★）⇒
  ★"★表中无★"这一栏里混着"★真没标签★"和"★没进宇宙★" ✗ 输出里会**分开数**✗★ ✓
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import blockkb as BK  # noqa: E402  ★"族 ⇒ 布尔"那两条判定由它拥有（★一份实现✓★）
import mapread as MR  # noqa: E402  ★现黑名单那条路（★被比的一方✗★）
import tag_census as TC  # noqa: E402  ★标签那条路（★一份实现✓★）

# ★★两条判定**照抄** `mapread`（★不许我自己猜哪几族算"能站"✗★）✗★
#   ★2026-10-03 搬家✗★：★它们原来**长在这个文件里** ✗ 可它们是"★族 ⇒ 布尔★"的**知识层**事实 ✗
#   ★而 `exception_table`／`declare_collision` 也要用 ⇒ ★改由 `blockkb` **拥有** ✗
#   这里只**引用** ✗ 一份实现✗★ ✓（★引用之后再导出同名符号 ✗ 免得动到别的调用点✓★）
FAM_BS = BK.FAM_BS
FAM_FLOOR = BK.FAM_FLOOR
blocks_space_fam = BK.blocks_space_fam
is_floor_fam = BK.is_floor_fam


def decision_delta(black_fam, tag_fam) -> str:
    """★这条分歧**会不会真的改变运行时判定**✗★ ⇒ 三档（★纯函数 ✗ 好离线判✓★）

    ★为什么要分档✗★：★1843 条里有一大批是"★`full` 与 `machine` 之争★"✗★ ——
      ★两个族**都挡人 ✗ 都能站** ⇒ **决策上没差** ✗ 只是名字不同 ✓
      而 `pass` ↔ `slab` 是**真的会翻**：★规划会**以为能从它身上穿过去**✗★ ✓
    ★★纪律✗★★：★分档只用来**排优先** ✗ **不许**据此说"★语义级就不算不一致★"✗★ ——
      ★登记册第 2 条要求**每一条**都声明 ✗ 分档只是先做要紧的✓★ ✓
    """
    if not black_fam or not tag_fam:
        return "★没法比（★有一边没族名✓★）"
    d = []
    if blocks_space_fam(black_fam) != blocks_space_fam(tag_fam):
        d.append("★挡人 %s⇒%s✗★" % (blocks_space_fam(black_fam), blocks_space_fam(tag_fam)))
    if is_floor_fam(black_fam) != is_floor_fam(tag_fam):
        d.append("★能站 %s⇒%s✗★" % (is_floor_fam(black_fam), is_floor_fam(tag_fam)))
    if d:
        return "★★决策级✗★★ " + " ／ ".join(d)
    return "★语义级（★两族在「挡人／能站」上一样 ✗ 只是名字不同✓★）"


# ★★标签家族 ⇒ 现分类器的家族名（★显式数据 ✗ 给人审 ✗ 不是正则✗★★）
TAG_FAMILY = {
    "叶子": "canopy", "原木": "full", "木板": "full",
    "半砖": "slab", "楼梯": "slab",
    # ★★2026-10-13（★用户裁决 A1 ✗ §79.242✗★）✗★★：★这三条**按真源改正**✗★ ✓
    #   ★真源那条路✗★：★类别 ⇒ `GEOMETRIC_CATEGORY` ⇒ 导出族 ⇒ `EXPORT_FAMILY` ⇒ 判定族✗★ ✓
    #     · ★活板门 ⇒ `snow_layer` ⇒ **`pass`**✗★（★3/16 的薄板 ✗ 本来就该走过去✓★）
    #     · ★珊瑚   ⇒ `none`        ⇒ **`pass`**✗★（★§79.199 已按碰撞声明过✓★）
    #     · ★花盆   ⇒ `snow_layer` ⇒ **`pass`**✗★（★6/16 ✗ 同上✓★）
    #   ★而手写那张表**还停在旧的 `fence`／`full`**✗★ ⇒ ★这就是"★五张表各说各的★"✗★ ✓
    #   ★★改它的依据是**真源** ✗ 不是我挑一个★✗★★（★A1 说真源是 `GEOMETRIC_CATEGORY`✓★）✗★ ✓
    "栅栏": "fence", "墙": "fence", "门": "fence", "活板门": "pass",
    "花": "pass", "树苗": "pass", "庄稼": "pass", "能爬": "pass",
    "按钮": "pass", "压力板": "pass", "牌子": "pass", "旗": "pass", "铁轨": "pass",
    "蜡烛": "pass", "地毯": "pass",
    "玻璃": "full", "羊毛": "full", "矿石": "full", "箱子类": "machine",
    # ★★2026-10-03 补漏✗★★：★我加了**模式**（`tag_census.FAMILY_PATTERNS`）却忘了加这里的**映射**
    #   ⇒ ★症状✗★：★`minecraft:dirt` 命中 `可挖／土` ✗ 而期望算出来是 `-` ⇒ 落"★表中无★"✗★ ✓
    #   ⇒ ★真因✗★：★`expected_from_tags` 只认 `TAG_FAMILY` 里有的族 ✗ 缺映射的族被**静默丢掉**✗★ ✓
    #   ⇒ ★口径✗★：★判据 D4 必须**双向**查（★映射 ⊆ 模式 ✗ 模式 ⊆ 映射✓★）✗
    #     这一条是补上**反方向**之后才不漏的✓★ ✓
    "土": "full", "沙": "full", "石基": "full", "花盆": "pass", "珊瑚": "pass",
}


def expected_from_tags(fams, passable=None) -> tuple:
    """★标签那边说它是哪一族✗★ ⇒ `(family | None, why, conflict)`

    ★冲突要**说出来** ✗ 而且**要标出来**✗★（★登记册第 2 条：★不一致可以有 ✗
    但一条都不许没声明 ✓★）✗ 因为"★冲突★"与"★没有★"是**两件事** ✗ 见 `bucket` 的注释 ✓★
    """
    got = sorted({TAG_FAMILY[f] for f in (fams or ()) if f in TAG_FAMILY})
    if not got:
        return None, "★没有一条家族标签对得上✗★", False
    if len(got) == 1:
        return got[0], "★标签：%s✗★" % "／".join(sorted(f for f in fams if f in TAG_FAMILY)), False
    # ★★2026-10-05（★§79.200 ✗ 用户裁定✗★）✗★★：★多族冲突时**问碰撞**✗★
    #   ★用户原话✗★：★"★可以搜索一下它的碰撞箱和是否允许通过吗？
    #   ★如果是允许通过的那就当花处理★"✗★ ✓
    #   ★能通过 ⇒ `pass`（★当花✗★）✗ 挡人 ⇒ 非 pass 那个（★`canopy` ✗ 当叶子✓★）✗
    #   ★读不到 ⇒ **仍报冲突**（★不许猜✓★）✗★ ✓
    if passable is True and "pass" in got:
        return "pass", ("★多族冲突（★%s✗★）⇒ ★碰撞说能穿过 ⇒ 当 `pass`（★花✗★）✗★"
                        % "／".join(got)), False
    if passable is False and len([g for g in got if g != "pass"]) == 1:
        pick = [g for g in got if g != "pass"][0]
        return pick, ("★多族冲突（★%s✗★）⇒ ★碰撞说挡人 ⇒ 取 `%s`✗★"
                      % ("／".join(got), pick)), False
    return None, "★标签自相冲突✗★：%s（★碰撞裁决不了✗★）" % "／".join(got), True


def bucket(black_fam, expected, conflict: bool = False) -> str:
    """★三栏之一✗★（★纯函数 ✗ 好离线判✓★）

    ★★2026-10-03 判据 D2 逼出来的一个口径问题✗★★：★"★多族冲突★"原来和"★表里没有★"
      落进同一栏 ✗ ⇒ ★可它们是**两件事**✗★ ✓
      · ★表里没有✗★ ＝ ★标签侧**没话说** ⇒ 黑名单继续兜底 ✗ 登记"待覆盖"✗★
      · ★多族冲突✗★ ＝ ★标签侧**说了两句矛盾的话** ⇒ 这是**真分歧** ✗ 必须进"不一致"栏 ✗
        而且理由里写明冲突 ✗★ ✓（★登记册第 2 条：★不一致可以有 ✗ 但一条都不许没声明✓★）
    """
    if conflict:
        return "★不一致✗★"
    if expected is None:
        return "★表中无✗★"
    if black_fam == expected:
        return "一致"
    return "★不一致✗★"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--out", default="docs/分歧清单.md")
    ap.add_argument("--by-namespace", action="store_true",
                    help="★按模组看「迁移准备度」✗ 阶段 4 的排序依据✗★")
    ap.add_argument("--dry", action="store_true", help="★只打印 ✗ 不写文档✗★")
    a = ap.parse_args(argv)

    jars, vanilla, roots = TC.sources_of(a)
    src, _uni, st = TC.scan(jars, roots, want_universe=False)
    vsrc, _v, _s = TC.scan(vanilla, [], want_universe=False)
    mem, ref = TC.build(src + vsrc)
    full = TC.closure(mem, ref)
    from_tag = TC.invert(full)
    ft = TC.family_tags(full)
    print("== 分歧清单（★标签 %d 个 ✗ 家族模式命中 %d ✗ 宇宙（标签侧）%d 个物种✓★）=="
          % (len(full), len(ft), len(from_tag)))

    # ★§79.200：循环里要问「这一格能不能穿过」⇒ 先把导出读一次 ✗ 不是每物种读一遍✗★
    try:
        import json as _json
        import kb_export as _KX
        _blocks = (_json.loads(_KX.find_export("").read_text(encoding="utf-8"))
                   .get("blocks") or {})
    except Exception:
        _blocks = {}

    rows = {"一致": [], "★不一致✗★": [], "★表中无✗★": []}
    lvl_of = {}                     # ★物种 ⇒ 决策级／语义级（★只用来排优先 ✗ 不许当"可以不管"✗★）
    for sp in sorted(from_tag):
        fams = [f for f, ids in ft.items() if any(t in ids for t in (from_tag.get(sp) or ()))]
        _e2 = _blocks.get(sp) or {}
        _fam2 = _e2.get("family")
        exp, why, conflict = expected_from_tags(
            fams, passable=None if _fam2 is None else (_fam2 in ("none", "pass", "liquid")))
        black = MR.shape(sp)
        b = bucket(black, exp, conflict)
        rows[b].append((sp, black, exp, why))
        lvl_of[sp] = ("★★决策级✗★★ ★标签自相冲突 ✗ 必须先解决★" if conflict
                      else decision_delta(black, exp))

    total = max(1, len(from_tag))
    print("")
    print("  %-12s %8s %7s" % ("栏", "物种", "占比"))
    for k in ("一致", "★不一致✗★", "★表中无✗★"):
        print("  %-12s %8d %6.0f%%" % (k, len(rows[k]), 100.0 * len(rows[k]) / total))
    print("")
    # ★★按"★会不会真的改变运行时判定★"再切一刀✗★★（2026-10-03）
    #   ★为什么✗★：★1843 条里一大半是"★`full` 与 `machine` 之争★" ✗ 两边**都挡人都能站** ⇒
    #     **决策上没差** ✗ 只是名字不同 ✓ 而 `pass` ↔ `slab` 是**真的会翻**✗★ ✓
    #   ★★纪律✗★★：★这只是**排优先** ✗ **不许**据此说"★语义级就不算不一致★"✗★ ✓
    # ★★2026-10-03 修我自己的一个计数错✗★★：★第一版把**所有**物种都算进这两个数
    #   ⇒ "★语义级 6062★" 里混进了 **6018 个"一致"**（★它们的 delta 当然是"语义级"✓★）✗
    #   ⇒ ★现象✗★：★"决策级 ＋ 语义级 ≠ 不一致总数"✗ ✗ 一眼就该看出来★ ✓
    #   ★口径✗★：★只在**不一致**那一栏里分档 ✗ 并**断言**两边加起来等于它✗★ ✓
    _inc = {sp for (sp, _b, _e, _w) in rows["★不一致✗★"]}
    dec = sorted(sp for sp in _inc if lvl_of.get(sp, "").startswith("★★决策级"))
    sem = sorted(sp for sp in _inc if lvl_of.get(sp, "").startswith("★语义级"))
    if len(dec) + len(sem) != len(_inc):
        print("  ★★自检不过✗★★：决策级 %d ＋ 语义级 %d ≠ 不一致 %d ⇒ ★分档漏了东西✗★"
              % (len(dec), len(sem), len(_inc)))
    assert len(dec) + len(sem) == len(_inc), "★分档之和必须等于不一致总数✗★"
    print("  == 不一致里，按「会不会改判定」分 ==")
    print("     ★★决策级✗★★（★挡人／能站 真的翻了✓★）  %d" % len(dec))
    print("     ★语义级✗★（★两族在这两条上一样 ✗ 只是名字不同✓★）%d" % len(sem))
    by_delta = {}
    for sp in dec:
        k = lvl_of[sp].replace("★★决策级✗★★ ", "")[:28]
        by_delta[k] = by_delta.get(k, 0) + 1
    for k, v in sorted(by_delta.items(), key=lambda kv: -kv[1])[:6]:
        print("        %-30s %d" % (k, v))
    print("")
    for k in ("★不一致✗★", "★表中无✗★"):
        print("  == %s ✗ 前 %d 条 ==" % (k, a.top))
        for (sp, black, exp, why) in rows[k][:a.top]:
            print("     %-46s 黑名单 %-8s 标签 %-8s %s"
                  % (sp, black, exp or "-", why[:40]))
    # ★按标签家族再切一刀 ✗ 看"★哪一族的不一致最多★"✗★（★那就是阶段 3 的优先队列✓★）
    by_fam = {}
    for (sp, black, exp, why) in rows["★不一致✗★"]:
        by_fam.setdefault(why.split("：")[-1][:24], 0)
        by_fam[why.split("：")[-1][:24]] += 1
    print("")
    print("  == 不一致按标签族分堆（前 %d）==" % a.top)
    for k, v in sorted(by_fam.items(), key=lambda kv: -kv[1])[:a.top]:
        print("     %-40s %d" % (k, v))

    # ★★按模组看"★迁移准备度★"✗★★（2026-10-04 ✗ 阶段 4 的**排序依据**✓★）
    #   ★它回答✗★：★哪个模组的物种**今天就能切**（★标签侧说清 ＋ 与黑名单一致✓★）✗
    #     ★哪个要**等导出** ✗★ ⇒ ★先切准备度高的 ✗ 风险小 ✗ 见效快 ✗
    #     而且**可回退**（★`CLASSIFIER_SOURCE` 一拨就回去✓★）✓
    if a.by_namespace:
        ns = {}
        _buckets = {}
        for k in rows:
            _buckets[k] = {r[0] for r in rows[k]}
        for sp in sorted(from_tag):
            n = sp.split(":", 1)[0]
            d = ns.setdefault(n, {"total": 0, "一致": 0, "不一致": 0, "表中无": 0, "决策": 0})
            d["total"] += 1
            if sp in _buckets.get("一致", ()):
                d["一致"] += 1
            elif sp in _buckets.get("★不一致✗★", ()):
                d["不一致"] += 1
                if lvl_of.get(sp, "").startswith("★★决策级"):
                    d["决策"] += 1
            else:
                d["表中无"] += 1
        print("")
        print("  == 按模组看迁移准备度（★准备度越高越先切✗★）==")
        print("     %-26s %7s %7s %7s %8s %8s"
              % ("模组", "物种", "一致", "不一致", "表中无", "准备度"))
        big = [kv for kv in ns.items() if kv[1]["total"] >= 40]
        for n, d in sorted(big, key=lambda kv: -kv[1]["一致"] / max(1, kv[1]["total"]))[:a.top]:
            print("     %-26s %7d %7d %7d %8d %7.0f%%"
                  % (n, d["total"], d["一致"], d["不一致"], d["表中无"],
                     100.0 * d["一致"] / max(1, d["total"])))
        # ★★第二张表：★按"★能切的**物种数**"排✗★★ ⇒ ★准备度 × 体量 ✗ 才是先切谁的真依据✗★ ✓
        #   （★准备度 85% 但只有 12 个物种 ✗ 不如 72% 但 2691 个✓★）
        print("")
        print("  == 同上 ✗ 但按「能切的物种数」排（★先切这张的头部✗★）==")
        print("     %-26s %7s %9s %8s" % ("模组", "物种", "可切", "可切占比"))
        for n, d in sorted(big, key=lambda kv: -kv[1]["一致"])[:a.top]:
            print("     %-26s %7d %9d %7.0f%%"
                  % (n, d["total"], d["一致"], 100.0 * d["一致"] / max(1, d["total"])))
        if not a.dry:
            _out = ROOT / "docs" / "迁移准备度.md"
            _L = ["# 迁移准备度（★生成物 ✗ 别手改 ✗ 重跑 `divergence.py --by-namespace`✓★）", "",
                  "> ★阶段 4 的**排序依据**：★先切「★准备度高★」的（★风险小 ✗ 可回退✓★）✗",
                  "> 再切「★能切的物种多★」的（★见效快✓★）✗★ ｜ ★`CLASSIFIER_SOURCE` 一拨就回滚✗★", "",
                  "## ★按准备度✗★（★一致 ÷ 物种 ✗ 只列 ≥40 个物种的模组✓★）", "",
                  "| 模组 | 物种 | 一致 | 不一致 | 表中无 | 准备度 |", "|---|---|---|---|---|---|"]
            for n, d in sorted(big, key=lambda kv: -kv[1]["一致"]
                               / max(1, kv[1]["total"]))[:40]:
                _L.append("| `%s` | %d | %d | %d | %d | %.0f%% |"
                          % (n, d["total"], d["一致"], d["不一致"], d["表中无"],
                             100.0 * d["一致"] / max(1, d["total"])))
            _L += ["", "## ★按能切的物种数✗★（★先切这张的头部✓★）", "",
                   "| 模组 | 物种 | 可切 | 可切占比 |", "|---|---|---|---|"]
            for n, d in sorted(big, key=lambda kv: -kv[1]["一致"])[:40]:
                _L.append("| `%s` | %d | %d | %.0f%% |"
                          % (n, d["total"], d["一致"], 100.0 * d["一致"] / max(1, d["total"])))
            _L += ["", "★怎么用✗★：★切一个模组 ⇒ 跑 `check_all` ＋ `kb_audit` ⇒ "
                   "★不一致的那几条**逐条**进例外表（★按 U1 口径声明✓★）✗ "
                   "★回退就是把 `CLASSIFIER_SOURCE` 拨回 `blacklist`✗★ ✓"]
            _out.write_text("\n".join(_L) + "\n", encoding="utf-8")
            print("")
            print("  已写 %s ✓" % _out.name)

    if a.dry:
        return 0
    out = ROOT / a.out
    lines = ["# 分歧清单（★生成物 ✗ 别手改 ✗ 改 `TAG_FAMILY` 或重跑✓★）", "",
             "> 生成时间 %s ｜ 工具 `tools/divergence.py`（★标签侧 %d 个物种✗★）"
             % (time.strftime("%Y-%m-%d %H:%M:%S"), len(from_tag)),
             "> ★宇宙是**标签侧**的 ✗ 不是注册表全集 ✗ 真全集要导出（★见 方案-注册表只读导出✗★）✓", "",
             "| 栏 | 物种 | 占比 |", "|---|---|---|"]
    for k in ("一致", "★不一致✗★", "★表中无✗★"):
        lines.append("| %s | %d | %.0f%% |" % (k, len(rows[k]), 100.0 * len(rows[k]) / total))
    lines += ["", "## ★不一致✗★（★按 U1 口径逐条声明 ✗ 优先队列＝先**决策级**再按标签族✓★）", "",
              "★先说怎么读✗★：★`级别`只用来**排优先** ✗ **不许**据此说「语义级不用管」✗★（★登记册第 2 条要求**每一条**都声明✓★）",
              "", "| 物种 | 黑名单说 | 标签说 | 级别 | 依据 | 处置 |", "|---|---|---|---|---|---|"]
    for (sp, black, exp, why) in (sorted(rows["★不一致✗★"],
                                         key=lambda r: (0 if lvl_of.get(r[0], "").startswith("★★")
                                                        else 1, r[0]))[:120]):
        lines.append("| `%s` | %s | %s | %s | %s | ★待声明✗★ |"
                     % (sp, black, exp or "-", lvl_of.get(sp, "-"), why))
    lines += ["", "## ★表中无✗★（★黑名单继续兜底 ✗ 登记待覆盖✓★）", "",
              "| 物种 | 黑名单说 | 依据 |", "|---|---|---|"]
    for (sp, black, exp, why) in rows["★表中无✗★"][:40]:
        lines.append("| `%s` | %s | %s |" % (sp, black, why))
    lines += ["", "★口径✗★：★这一栏**不判谁对** ✗ 只列出分歧 ✗ 物理仍只听碰撞形状✗★ ✓"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("")
    print("  已写 %s ✓" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
