#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recipe_graph.py -- 模块 K 的配方图：★"要做 X 需要哪些料"✗★

为什么必须有它（规格 §10.2 / §13.2）：
  「产线蓝图**应该是可以搜索的**」＋「若没有就让 dsh **自己设计**」
  ⇒ 自己设计的第一步是 ★**功能需求 → 元件清单**★ ⇒ 元件清单要靠**配方图**算出来 ✓

数据源：`build/recipes.json`（★12.4 MB ✗ 20764 个产物 ✗ 每个产物可有多个配方✗★）
  一条配方形如：
    {"type":"minecraft:crafting_shaped", "count":1,
     "ingredients":[{"id":"thermal:iron_gear"}, {"tag":"forge:ingots/iron"}...], ...}

接口：
    producers(item)        -> [recipe, ...]
    ingredients(recipe)    -> [{"kind":"id"|"tag", "key":..., "count":n}, ...]（★同名合并✗★）
    shopping(item, need)   -> {key: qty}   ★只到底料（没有配方的那些）✗★
    tree(item, depth)      -> 嵌套结构（★人看得懂 ✗ 也给 K 用✗★）
★环保护✗★：★A 要 B 要 A ⇒ **在环上停下并标出来 ✗ 不许无限递归**✗★ ✓
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

DEFAULT = ROOT / "build" / "recipes.json"
_CACHE = {}


def load(path=None) -> dict:
    p = pathlib.Path(path) if path else DEFAULT
    key = str(p)
    if key in _CACHE:
        return _CACHE[key]
    if not p.is_file():
        print("recipe_graph: ★找不到 %s✗★" % p, file=sys.stderr)
        _CACHE[key] = {}
        return {}
    d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    _CACHE[key] = d if isinstance(d, dict) else {}
    return _CACHE[key]


def producers(item: str, recipes=None) -> list:
    r = recipes if recipes is not None else load()
    return list(r.get(item) or [])


def _best(recipes_list) -> dict:
    """★优先"产物数最多"的那个配方**（★能一次做更多✗★）✗ 其次按 type 稳定排序 ✓"""
    if not recipes_list:
        return {}
    return sorted(recipes_list,
                  key=lambda x: (-int(x.get("count") or 0), str(x.get("type") or "")))[0]


def ingredients(recipe: dict) -> list:
    """★把一条配方的原料摊平并**按 (kind,key) 合并计数**✗★"""
    agg = {}
    for ing in (recipe.get("ingredients") or []):
        if not isinstance(ing, dict):
            continue
        if ing.get("id"):
            key, kind = str(ing["id"]), "id"
        elif ing.get("tag"):
            key, kind = str(ing["tag"]), "tag"
        else:
            continue
        cnt = int(ing.get("count") or 1)
        k = (kind, key)
        agg[k] = agg.get(k, 0) + cnt
    return [{"kind": k[0], "key": k[1], "count": v} for k, v in sorted(agg.items())]


def _yield(recipe: dict) -> int:
    return max(1, int(recipe.get("count") or 1))


def tree(item: str, depth: int = 3, need: int = 1, seen=(), recipes=None):
    """★嵌套展开✗★ ⇒ (node, notes)；★环/深度到顶会标出来✗★"""
    notes = []
    rs = producers(item, recipes)
    node = {"item": item, "need": need, "recipe": None, "children": [], "why": ""}
    if item in seen:
        node["why"] = "★环✗★（%s 已经在上层）" % item
        notes.append(node["why"])
        return node, notes
    if not rs:
        node["why"] = "★底料（没有配方）✗★"
        return node, notes
    r = _best(rs)
    node["recipe"] = {"type": r.get("type"), "count": _yield(r)}
    batches = max(1, -(-need // _yield(r)))       # ceil
    if depth <= 0:
        node["why"] = "★深度到顶✗★（还要 %d 个）" % need
        notes.append(node["why"])
        node["batches"] = batches
        return node, notes
    node["batches"] = batches
    for ing in ingredients(r):
        cnt = ing["count"] * batches
        if ing["kind"] == "tag":
            node["children"].append({"item": "tag:" + ing["key"], "need": cnt,
                                     "why": "★标签 ✗ 运行时要查真实物品✗★", "children": []})
            continue
        child, n2 = tree(ing["key"], depth - 1, cnt, tuple(seen) + (item,), recipes)
        node["children"].append(child)
        notes.extend(n2)
    return node, notes


def shopping(item: str, need: int = 1, max_depth: int = 6, recipes=None) -> dict:
    """★摊成购物清单✗★：只保留**没有配方**的底料 ＋ 所有**标签**（★要运行时解析✗★）"""
    out = {}

    def walk(cur, cnt, depth, seen):
        if depth <= 0:
            out[cur] = out.get(cur, 0) + cnt
            return
        if cur in seen:                 # ★环：按底料算 ✗ 不许无限✗★
            out[cur] = out.get(cur, 0) + cnt
            return
        rs = producers(cur, recipes)
        if not rs:
            out[cur] = out.get(cur, 0) + cnt
            return
        r = _best(rs)
        batches = max(1, -(-cnt // _yield(r)))
        for ing in ingredients(r):
            total = ing["count"] * batches
            if ing["kind"] == "tag":
                out["tag:" + ing["key"]] = out.get("tag:" + ing["key"], 0) + total
            else:
                walk(ing["key"], total, depth - 1, tuple(seen) + (cur,))

    walk(item, max(1, need), max_depth, ())
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def main(argv) -> int:
    r = load()
    if argv and argv[0] == "--shopping":
        item = argv[1]
        need = int(argv[2]) if len(argv) > 2 else 1
        print("★%s × %d 的底料清单✗★" % (item, need))
        for k, v in shopping(item, need).items():
            print("  %-44s ×%d" % (k, v))
        return 0
    if argv and argv[0] == "--tree":
        node, notes = tree(argv[1], depth=int(argv[2]) if len(argv) > 2 else 3)
        print(json.dumps(node, ensure_ascii=False, indent=1)[:3000])
        if notes:
            print("★注意✗★：", notes[:6])
        return 0
    if argv and argv[0] == "--producers":
        item = argv[1]
        rs = producers(item)
        print("★%s✗★ ⇒ %d 个配方" % (item, len(rs)))
        for x in rs[:4]:
            print("  type=%-32s count=%s ｜ 原料 %s"
                  % (x.get("type"), x.get("count"), ingredients(x)))
        return 0
    print("配方图：%d 个产物 ｜ 用法 --producers <item> / --tree <item> [depth] / --shopping <item> [need]"
          % len(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
