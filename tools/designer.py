#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""designer.py -- 模块 L5 设计官：★配方图 → 元件清单 → 可被 port.py 消费的布局计划✗★

规格（§13.1／§13.2／§14.1）：
  * 用户：「若没有就让 dsh **自己设计**」⇒ 模块 K 第 3 级
  * L5 的权限是**只读**：★设计必须在**离线**完成 ✗ 不能边设计边施工✗★
  * 每一步都可判：① 功能需求→元件清单 ② 布局约束 ③ 坐标表（带**来源标记**）
    ④ 离线仿真/预算校验 ⑤（执行是 port.py 的事）⑥（真值逐格核对是 K/L4 的事）

本模块只做 **①②③④ 的离线那一半**：
  输入：`target`（目标产物 id，如 `minecraft:iron_ingot`）＋ 现场约束（`bounds` 可用空间、
        `stand` 站立点、`existing` 已有资产）＋ 数据源（默认 `build/recipes.json`；
        可注入 ` recipes=` 换整合包/换合成数据）
  输出：`{ok, source:"self_designed", target, size, cells, placement_order, components,
          materials, missing, assumptions, rationale, confidence, audit}`

★★诚实边界（★这些不是"做完了"✗★）：
  * **布局是元件铺位图**（机器/容器/料块按角色分行），**不是产线拓扑**：
    不做管道连接、不做机器朝向的真实求解（朝向只作为**假设**给出来 ＋ 低置信度）；
  * `.nbt` 结构导出**未实现**（JSON 计划已能被 `port.py` 直接消费；
    写 NBT 要新的二进制序列化器 → 明确留作未实现，不假装）；
  * 分类**一律问 `blockkb`/`mapread` 的导出分类**，★不写方块名表✗★；
    分类查不到就如实降级（role=unknown / item），**不猜**。

★★拒绝（refuse）比假装成功好✗★★：数据缺失／坏配方／放不下／超预算 ⇒
  `{ok:False, refused:True, reason:"<ASCII 码>", detail:...}`，码表见 `REFUSE_CODES`。

★确定性✗★：同输入 ⇒ 同输出（排序全靠显式 key ✗ 不靠 dict/hash 顺序）。
★来源标记（K-a）✗★：本模块产出一律 `source="self_designed"`（★不许把"抄的"说成"设计的"✗★）。
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mapread as MR                 # noqa: E402
import recipe_graph as RG            # noqa: E402
import port as PORT                  # noqa: E402  ★复用"可被 port.py 消费"的既有口径✗不另造✗★

DEFAULT_RECIPES = ROOT / "build" / "recipes.json"

SCHEMA = "dshbridge/design@1"
SOURCE_SELF = "self_designed"
ROLE_ORDER = {"machine": 0, "container": 1, "block": 2, "unknown": 3}
ROLE_LABEL = {"machine": "机器", "container": "容器", "block": "料块", "unknown": "未知"}
REFUSE_CODES = (
    "no_recipe",             # 目标没有配方（且没有可放置元件可借）
    "no_recipe_data",        # 配方数据缺失/空
    "recipes_unreadable",    # 配方数据读不出来
    "bad_recipe_data",       # 配方数据形状坏（不是 dict/list）
    "no_placeable_components",  # 元件清单里没有"可放置方块"（全是纯物品/标签）
    "too_many_cells",        # 元件数超预算（max_cells）
    "out_of_bounds",         # 布局放不进给定 bounds
    "bad_bounds",            # bounds 参数坏
)
# ★角色 → 置信度（★这是"我们对这条判断有多确定" ✗ 不是精确概率✗★）
ROLE_CONF = {"machine": 0.9, "container": 0.85, "block": 0.7, "unknown": 0.3}


class DesignError(ValueError):
    """参数/数据形状错误（★调用方参数错就抛 ✗ 数据缺失就 refuse✗★）。"""


def _refuse(reason: str, target="", detail="", **extra) -> dict:
    if reason not in REFUSE_CODES:
        raise DesignError("未知拒绝码 %r（允许 %s）" % (reason, ",".join(REFUSE_CODES)))
    out = {"schema": SCHEMA, "ok": False, "refused": True, "source": SOURCE_SELF,
           "reason": reason, "target": target, "detail": str(detail)[:240]}
    out.update(extra)
    return out


# ── 数据源 ────────────────────────────────────────────────────────────────
def _load_recipes(recipes=None):
    """返回 `(recipes_dict, source_desc)`；**空/坏数据不冒充**（抛 DesignError 给上层转 refuse）。"""
    if recipes is not None:
        if not isinstance(recipes, dict):
            raise DesignError("recipes 必须是 dict（物品 → 配方列表）：%r"
                              % (type(recipes).__name__,))
        return recipes, "injected"
    try:
        d = RG.load(DEFAULT_RECIPES)
    except Exception as exc:                  # ★不许静默✗★
        raise DesignError("读配方数据失败：%r" % (exc,)) from exc
    if not d:
        raise DesignError("配方数据为空/不存在：%s" % DEFAULT_RECIPES)
    return d, str(DEFAULT_RECIPES.relative_to(ROOT))


def _producers(target: str, recipes: dict) -> list:
    """★目标 ⇒ 配方列表✗★（★过滤掉形状坏的元素 ✗ 不许拿 str 当配方✗★）"""
    arr = recipes.get(target)
    if arr is None:
        return []
    if not isinstance(arr, (list, tuple)):
        raise DesignError("配方数据形状坏：%r → %r" % (target, type(arr).__name__))
    good = [x for x in arr if isinstance(x, dict)]
    if arr and not good:
        raise DesignError("配方数据形状坏：%r 的配方列表里没有 dict" % (target,))
    return good


# ── 分类（★一律问导出分类 ✗ 不写方块名表✗★）──────────────────────────────
def classify_default(block_id: str) -> dict:
    """默认分类：`mapread` 的**导出碰撞高**证明"这是方块"；`machine_family` 证明"有方块实体"。

    返回 `{placeable, role, confidence, evidence}` —— ★查不到就 role=unknown/item ✗ 不猜✗★。
    """
    bid = str(block_id or "").strip()
    if not bid:
        return {"placeable": False, "role": "item", "confidence": 0.0,
                "evidence": {"kind": "classification", "ref": "empty-id"}}
    try:
        h = MR._export_h(bid)                 # ★导出里没有 ⇒ 不是"可放置方块"✗★
    except Exception as exc:                  # ★不许静默✗★
        print("designer: 查导出分类失败 %r（%r）" % (bid, exc), file=sys.stderr)
        h = None
    if h is None:
        return {"placeable": False, "role": "item", "confidence": 0.2,
                "evidence": {"kind": "classification", "ref": "not-a-block:%s" % bid}}
    try:
        fam = MR.machine_family(bid) or ""
    except Exception as exc:                  # ★不许静默✗★
        print("designer: 查 machine_family 失败 %r（%r）" % (bid, exc), file=sys.stderr)
        fam = ""
    try:
        cat = ""                              # ★语义类别（标签层）✗ 只用来分"容器"✗★
        import blockkb as KB
        cat = KB.category_of(bid) or ""
    except Exception as exc:                  # ★不许静默✗★
        print("designer: 查方块类别失败 %r（%r）" % (bid, exc), file=sys.stderr)
        cat = ""
    if "箱" in cat:
        role = "container"
    elif fam:
        role = "machine"
    else:
        role = "block"
    return {"placeable": True, "role": role, "confidence": ROLE_CONF[role],
            "evidence": {"kind": "classification",
                         "ref": "export_h=%s machine=%r category=%r" % (h, fam, cat)}}


def _norm_classify(r) -> dict:
    if not isinstance(r, dict):
        raise DesignError("classify() 必须返回 dict：%r" % (type(r).__name__,))
    placeable = bool(r.get("placeable"))
    role = str(r.get("role") or ("block" if placeable else "item"))
    if placeable and role not in ("machine", "container", "block"):
        role = "unknown"
    conf = r.get("confidence")
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = ROLE_CONF.get(role, 0.3)
    return {"placeable": placeable,
            "role": role if placeable else "item",
            "confidence": max(0.0, min(1.0, conf)),
            "evidence": r.get("evidence") or {"kind": "classifier", "ref": "injected"}}


# ── 元件清单（来自配方图）───────────────────────────────────────────────
def _flatten_tree(node: dict, out: list, depth: int = 0) -> None:
    for ch in (node.get("children") or []):
        out.append({"node": ch, "depth": depth + 1})
        _flatten_tree(ch, out, depth + 1)


def _components_from_tree(target: str, need: int, recipes: dict, include_depth: int,
                          classifier) -> dict:
    """★配方图 ⇒ 元件清单✗★：每个节点进**且只进一个桶**（★覆盖对账✗★）。"""
    try:
        node, notes = RG.tree(target, depth=max(1, int(include_depth)), need=int(need),
                              recipes=recipes)
    except Exception as exc:                  # ★坏配方数据 ⇒ 交给上层 refuse✗★
        raise DesignError("配方树展开失败：%r" % (exc,)) from exc
    nodes = []
    _flatten_tree(node, nodes)
    placed, materials, intermediates, tags = [], [], [], []
    for row in nodes:
        n = row["node"]
        item = str(n.get("item") or "")
        cnt = int(n.get("need") or 1)
        if not item:
            raise DesignError("配方树节点缺 item：%r" % (n,))
        if item.startswith("tag:"):
            tags.append({"key": item[4:], "need": cnt, "why": "标签（运行时要查真实物品）"})
            continue
        cls = _norm_classify(classifier(item))
        rec = {"item": item, "need": cnt, "depth": row["depth"],
               "role": cls["role"], "placeable": cls["placeable"],
               "confidence": cls["confidence"], "evidence": cls["evidence"]}
        if cls["placeable"]:
            placed.append(rec)
        elif not (n.get("children") or []):
            materials.append(rec)              # ★叶子且不可放 ⇒ 底料✗★
        else:
            intermediates.append(rec)          # ★中间产物：由上游工位产出 ✗ 不进布局✗★
    return {"nodes": len(nodes), "placed": placed, "materials": materials,
            "intermediates": intermediates, "tags": tags, "notes": notes}


# ── 布局求解（网格铺位）＋ 预算校验 ──────────────────────────────────────
def _norm_bounds(bounds) -> dict | None:
    if bounds is None:
        return None
    if isinstance(bounds, dict):
        try:
            b = {"x": int(bounds["x"]), "y": int(bounds["y"]), "z": int(bounds["z"])}
        except (KeyError, TypeError, ValueError):
            raise DesignError("bounds 必须含整数 x/y/z：%r" % (bounds,)) from None
    elif isinstance(bounds, (tuple, list)) and len(bounds) == 3:
        try:
            b = {"x": int(bounds[0]), "y": int(bounds[1]), "z": int(bounds[2])}
        except (TypeError, ValueError):
            raise DesignError("bounds 三个分量必须是整数：%r" % (bounds,)) from None
    else:
        raise DesignError("bounds 只收 {x,y,z} 或 (x,y,z)：%r" % (bounds,))
    if min(b.values()) < 1:
        raise DesignError("bounds 每一维都必须 >=1：%r" % (b,))
    return b


def _layout(placed_components: list, bounds, max_cells: int) -> dict:
    """★把可放置元件铺到网格✗★：按角色分行（机器／容器／料块）✗ 每行连续填格✗★"""
    instances = []
    for comp in sorted(placed_components, key=lambda c: (ROLE_ORDER.get(c["role"], 9),
                                                         -int(c["need"]), c["item"])):
        for _k in range(max(1, int(comp["need"]))):
            instances.append(comp)
    if len(instances) > int(max_cells):
        return {"refused": "too_many_cells", "need": len(instances), "max": int(max_cells)}
    # ★角色分行：机器在前 ✗ 容器其次 ✗ 料块最后✗★（行号来自角色，不是实例顺序）
    bands = []
    for role in ("machine", "container", "block", "unknown"):
        arr = [c for c in instances if c["role"] == role]
        if arr:
            bands.append((role, arr))
    width = max((len(arr) for _r, arr in bands), default=0)
    if width == 0:
        return {"refused": "no_placeable_components", "need": 0}
    if bounds is None:
        b = {"x": width, "y": 1, "z": len(bands)}
    else:
        b = bounds
    if b["y"] < 1 or b["x"] < width or b["z"] < len(bands):
        return {"refused": "out_of_bounds", "need_size": {"x": width, "y": 1, "z": len(bands)},
                "bounds": b}
    cells = []
    for dz, (role, arr) in enumerate(bands):
        for dx, comp in enumerate(arr):
            cells.append({"dx": dx, "dy": 0, "dz": dz, "block": comp["item"],
                          "role": role, "component": comp["item"],
                          "confidence": comp["confidence"],
                          "why": "元件清单里 %r 是%s（分类证据：%s）"
                                 % (comp["item"], ROLE_LABEL.get(role, role),
                                    (comp.get("evidence") or {}).get("ref", ""))})
    return {"cells": cells, "size": {"x": max(b["x"], width), "y": b["y"],
                                     "z": max(b["z"], len(bands))}}


def _placement_order(cells: list) -> list:
    """★放置顺序✗★：直接借 `port.order`（自下而上／有支撑优先）⇒ 保证 port.py 能消费。"""
    ordered = PORT.order(cells, {}, (0, 0, 0))
    return [{"dx": c["dx"], "dy": c["dy"], "dz": c["dz"], "block": c["block"]}
            for c in ordered]


def _missing_ledger(target: str, need: int, recipes: dict, existing: dict | None) -> dict:
    """★缺料清单✗★：`recipe_graph.shopping` 的全量底料 − 已有资产（★只减不减出负✗★）"""
    try:
        shopping = RG.shopping(target, int(need), recipes=recipes)
    except Exception as exc:                  # ★坏配方 ⇒ 交给上层 refuse✗★
        raise DesignError("算料失败：%r" % (exc,)) from exc
    have = {}
    for k, v in (existing or {}).items():
        try:
            have[str(k)] = max(0, int(v))
        except (TypeError, ValueError):
            raise DesignError("existing 的计数必须是整数：%r=%r" % (k, v)) from None
    raw = []
    missing = {}
    for key in sorted(shopping):
        qty = int(shopping[key])
        h = have.get(key, 0)
        short = max(0, qty - h)
        raw.append({"key": key, "need": qty, "have": h, "short": short})
        if short > 0:
            missing[key] = short
    return {"shopping": raw, "missing": dict(sorted(missing.items())),
            "missing_n": len(missing)}


def _audit(comp: dict, cells: list, materials_meta: dict) -> dict:
    """★覆盖对账✗★：配方树的每个节点**必须**落在 placed／materials／intermediates／tags 之一。"""
    bucket = {"placed": len(comp["placed"]), "materials": len(comp["materials"]),
              "intermediates": len(comp["intermediates"]), "tags": len(comp["tags"])}
    accounted = sum(bucket.values())
    placed_instances = len(cells)
    needed_instances = sum(max(1, int(c["need"])) for c in comp["placed"])
    return {"nodes": comp["nodes"], "buckets": bucket, "accounted": accounted,
            "coverage_ok": accounted == comp["nodes"] and comp["nodes"] > 0,
            "cells": placed_instances, "placed_needed": needed_instances,
            "counts_ok": placed_instances == needed_instances,
            "materials": materials_meta}


def design(target: str, need: int = 1, bounds=None, stand=None, existing=None,
           recipes=None, classify=None, max_cells: int = 64,
           include_depth: int = 2) -> dict:
    """★自己设计一张"元件布局图"✗★（离线只读；★拒绝比假装好✗★）

    参数：
      target   目标产物 id（没有配方就 refuse `no_recipe`）
      need     要多少份（影响元件数与算料）
      bounds   可用空间 `{x,y,z}`（自动 = 刚好排下；放不进 ⇒ refuse `out_of_bounds`）
      stand    站立点（**只记录为约束**：布局不占站立格；本轮不做可达性求解）
      existing 已有资产 `{item_id: count}`（从缺料清单里扣）
      recipes  注入配方数据（默认 `build/recipes.json`）
      classify 注入分类函数 `id -> {placeable, role, confidence, evidence}`
               （默认问 `mapread`/`blockkb` 的导出分类；★判据用它证"不靠名字表"✗★）
      max_cells 元件格数预算（超 ⇒ refuse `too_many_cells`）
      include_depth 配方树展开深度（>=1）
    """
    if not isinstance(target, str) or not target.strip():
        raise DesignError("target 不能为空（要物品 id，如 minecraft:iron_ingot）")
    target = target.strip()
    if isinstance(need, bool) or not isinstance(need, int) or need < 1:
        raise DesignError("need 必须是 >=1 的整数：%r" % (need,))
    if isinstance(max_cells, bool) or not isinstance(max_cells, int) or max_cells < 0:
        raise DesignError("max_cells 必须是 >=0 的整数：%r" % (max_cells,))
    classifier = classify or classify_default
    if not callable(classifier):
        raise DesignError("classify 必须可调用：%r" % (classifier,))
    # ★参数形状错 ⇒ 抛（调用方 bug 不许被当成"数据缺失"✗★）；数值不合理 ⇒ refuse bad_bounds
    b = None
    if bounds is not None:
        if isinstance(bounds, dict):
            if not all(k in bounds for k in ("x", "y", "z")):
                raise DesignError("bounds 必须含 x/y/z：%r" % (bounds,))
        elif not (isinstance(bounds, (tuple, list)) and len(bounds) == 3):
            raise DesignError("bounds 只收 {x,y,z} 或 (x,y,z)：%r" % (bounds,))
        try:
            b = _norm_bounds(bounds)
        except DesignError as exc:
            return _refuse("bad_bounds", target, str(exc))
    # ★recipes 类型错 ⇒ 抛；读不出来/为空 ⇒ refuse（数据问题 ✗ 不是调用方 bug✗★）
    if recipes is not None and not isinstance(recipes, dict):
        raise DesignError("recipes 必须是 dict（物品 → 配方列表）：%r"
                          % (type(recipes).__name__,))

    # ① 配方数据
    try:
        recipes_d, recipes_src = _load_recipes(recipes)
    except DesignError as exc:
        return _refuse("no_recipe_data" if not str(exc).startswith("读") else
                       "recipes_unreadable", target, str(exc))
    if not recipes_d:
        return _refuse("no_recipe_data", target,
                       "配方数据 %r 是空的（★空数据不许冒充「有配方」✗★）" % (recipes_src,))
    try:
        prods = _producers(target, recipes_d)
    except DesignError as exc:
        return _refuse("bad_recipe_data", target, str(exc))
    if not prods:
        return _refuse("no_recipe", target,
                       "目标 %r 在配方数据 %r 里没有配方（★不许凭空编元件✗★）"
                       % (target, recipes_src))

    # ② 元件清单（来自配方图）
    try:
        comp = _components_from_tree(target, need, recipes_d, include_depth, classifier)
    except DesignError as exc:
        return _refuse("bad_recipe_data", target, str(exc))
    if not comp["placed"]:
        return _refuse("no_placeable_components", target,
                       "配方树里 %d 个节点没有一个「可放置方块」（全是物品/标签）"
                       % comp["nodes"])

    # ③ 布局 ＋ ④ 预算/边界校验
    lay = _layout(comp["placed"], b, max_cells)
    if lay.get("refused"):
        return _refuse(lay["refused"], target,
                       "元件 %s 格 ／ 预算 %s ／ 边界 %s"
                       % (lay.get("need"), lay.get("max"), lay.get("bounds")),
                       need_cells=lay.get("need"), max_cells=max_cells)
    cells = lay["cells"]

    # 站立点约束：布局只铺 dy=0 层；站立点若落在布局格上 ⇒ 明确报冲突（不硬排）
    assumptions = [{"why": "地面 dy=0 层由现场承重（★执行前由 port.plan 对现场算账复核✗★）",
                    "confidence": 0.8},
                   {"why": "机器/容器的**朝向与接口**未求解：布局只给铺位（不做管道/朝向）",
                    "confidence": 0.5},
                   {"why": "可达性未求解：站立点只记录为约束（不保证每台机器都走得到）",
                    "confidence": 0.5}]
    if stand is not None:
        try:
            st = [int(v) for v in stand]
            if len(st) != 3:
                raise ValueError("stand 要 3 个数")
        except (TypeError, ValueError):
            raise DesignError("stand 必须是 (x,y,z)：%r" % (stand,)) from None
        # ★锚点由执行时选 ✗ 这里不假造"冲突"✗★：只把站立点登记成**执行期约束**
        assumptions.append({"why": "站立点 %s 是执行期约束（锚点须避开它 ✗ 本轮不求解可达性）"
                                  % (st,), "confidence": 0.5})

    # 缺料清单（全量底料 − 已有）
    try:
        ledger = _missing_ledger(target, need, recipes_d, existing)
    except DesignError as exc:
        return _refuse("bad_recipe_data", target, str(exc))

    order = _placement_order(cells)
    rationale = []
    for role in ("machine", "container", "block", "unknown"):
        arr = [c for c in comp["placed"] if c["role"] == role]
        if not arr:
            continue
        rationale.append({
            "why": "把 %d 种%s排成一行（共 %d 格）：机器先落位、容器挨着、料块靠后"
                   % (len(arr), ROLE_LABEL.get(role, role),
                      sum(max(1, int(x["need"])) for x in arr)),
            "confidence": round(sum(x["confidence"] for x in arr) / len(arr), 3),
            "evidence": [x["evidence"] for x in arr[:4]]})
    confs = ([c["confidence"] for c in comp["placed"]]
             + ([0.5] if stand is not None else []))
    overall = round(sum(confs) / len(confs), 3) if confs else 0.0
    audit = _audit(comp, cells, {"leaf_kinds": len(comp["materials"]),
                                 "tags": len(comp["tags"]),
                                 "intermediates": len(comp["intermediates"])})
    plan = {
        "schema": SCHEMA, "ok": True, "refused": False, "source": SOURCE_SELF,
        "reason": "self_designed", "target": target, "need": need,
        "origin": [0, 0, 0], "size": lay["size"],
        "cells": cells, "placement_order": order,
        "components": comp["placed"],
        "intermediates": comp["intermediates"],
        "materials": comp["materials"],
        "tags": comp["tags"],
        "missing": ledger["missing"], "material_ledger": ledger["shopping"],
        "missing_n": ledger["missing_n"],
        "rationale": rationale, "assumptions": assumptions,
        "confidence": overall,
        "audit": audit,
        "data": {"recipes": recipes_src, "classifier":
                 "injected" if classify else "mapread-export+blockkb-category"},
        "why": "从配方图算元件清单 → 按角色分行铺位 → 缺料清单；来源=self_designed",
    }
    # ④ 离线仿真自检：port.py 的算账口径必须能消费（★不能消费就不许说设计好了✗★）
    check = PORT.plan(cells, (0, 0, 0), {})
    if check["need_n"] != len(cells) or check["floating"]:
        return _refuse("out_of_bounds", target,
                       "port.plan 预检不过：need=%d/%d floating=%d"
                       % (check["need_n"], len(cells), len(check["floating"])),
                       cells=len(cells))
    plan["port_check"] = {"need_n": check["need_n"], "floating": len(check["floating"]),
                          "ok": True}
    return plan


# ── 给人看的小结（★只转述计划里有的东西✗★）────────────────────────────
def summary(plan: dict) -> str:
    if not plan.get("ok"):
        return "设计被拒：reason=%s ｜ %s" % (plan.get("reason"), plan.get("detail", ""))
    cells = plan.get("cells") or []
    by_role = {}
    for c in cells:
        by_role[c.get("role", "?")] = by_role.get(c.get("role", "?"), 0) + 1
    return ("设计 %s ×%d：[%s] ｜ %d 格 ｜ 缺料 %d 种 ｜ 置信度 %.2f ｜ 来源=%s"
            % (plan.get("target"), plan.get("need"),
               " ".join("%s=%d" % (ROLE_LABEL.get(k, k), v)
                        for k, v in sorted(by_role.items())),
               len(cells), int(plan.get("missing_n") or 0),
               float(plan.get("confidence") or 0), plan.get("source")))


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="L5 设计官：目标产物 → 可被 port.py 消费的布局计划")
    ap.add_argument("--target", required=True)
    ap.add_argument("--need", type=int, default=1)
    ap.add_argument("--bounds", default="", help="x,y,z（省略=自动）")
    ap.add_argument("--stand", default="", help="x,y,z")
    ap.add_argument("--existing", default="", help='JSON：{"item":count}')
    ap.add_argument("--max-cells", type=int, default=64)
    ap.add_argument("--json", action="store_true", help="打完整计划 JSON")
    ns = ap.parse_args(argv)
    bounds = None
    if ns.bounds.strip():
        try:
            bounds = tuple(int(v) for v in ns.bounds.split(","))
        except ValueError:
            print("DESIGNER error: --bounds 要 x,y,z")
            return 2
    stand = None
    if ns.stand.strip():
        try:
            stand = tuple(int(v) for v in ns.stand.split(","))
        except ValueError:
            print("DESIGNER error: --stand 要 x,y,z")
            return 2
    existing = {}
    if ns.existing.strip():
        try:
            existing = json.loads(ns.existing)
        except Exception as exc:              # ★不许静默✗★
            print("DESIGNER error: --existing 不是 JSON：%r" % (exc,))
            return 2
    try:
        plan = design(ns.target, need=ns.need, bounds=bounds, stand=stand,
                      existing=existing, max_cells=ns.max_cells)
    except DesignError as exc:                # ★参数错明确报✗★
        print("DESIGNER error: %r" % (exc,))
        return 2
    if ns.json:
        print(json.dumps(plan, ensure_ascii=False, indent=1))
    else:
        print(summary(plan))
        for c in (plan.get("cells") or [])[:12]:
            print("  (%d,%d,%d) %-36s %s" % (c["dx"], c["dy"], c["dz"],
                                             c["block"], c.get("role")))
    return 0 if plan.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
