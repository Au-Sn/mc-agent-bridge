#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recipe_index.py — 从整合包文件里建"配方索引"

为什么这么做（而不是去问 JEI）：
  JEI 是客户端模组；它的服务端配置只有三项作弊模式权限（enableCheatModeForOp /
  ForCreative / ForGive），**不对外提供任何配方数据**。假人没有客户端，既打不开它的
  界面，也读不到它的内容。
  但 JEI 显示的东西来自服务端 RecipeManager，而 RecipeManager 是加载期由
  mods/*.jar 里的 data/<mod>/recipes/*.json（以及 KubeJS 脚本增删）构建出来的。
  所以"扫描 JEI"的正确实现 = 读这些源头文件，自己建索引 —— 数据相同、而且可离线查。

用法：
    py tools/recipe_index.py --build                      # 建索引并缓存
    py tools/recipe_index.py --find minecraft:oak_planks  # 查某产物（自动按需建索引）
    py tools/recipe_index.py --find "planks" --limit 20   # 子串匹配
    py tools/recipe_index.py --stats
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys, paths as PA
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE = str(PA.MC_HOME)
MODS = str(PA.MODS_DIR)
CACHE = str(PA.RECIPES_FILE)
KUBEJS = str(PA.MC_HOME / "kubejs")


def norm_ing(v):
    """把一个 ingredient 对象压成 {item|tag, count} 的紧凑形式。"""
    if isinstance(v, str):
        return {"id": v, "count": 1}
    if isinstance(v, list):                      # 多选一（tag 或列表）
        out = [norm_ing(x) for x in v]
        return {"any": out}
    if isinstance(v, dict):
        if "item" in v:
            return {"id": v["item"], "count": int(v.get("count", 1))}
        if "tag" in v:
            return {"tag": v["tag"], "count": int(v.get("count", 1))}
        if "items" in v:
            return {"any": [norm_ing(x) for x in v["items"]]}
        return {"raw": {k: v[k] for k in list(v)[:4]}}
    return {"raw": str(v)}


def result_of(rec):
    """取产物与数量。

    不同模组的字段差异很大，这里踩过两个坑：
      1. result 可能是字符串（Ex Deorum 筛矿 / KubeJS custom 都是字符串）✗ 按对象取会全空；
      2. 数量与概率在 result_amount 里，形如 {type:'minecraft:binomial', n:1, p:0.01}
         —— 「出 1 个、概率 1%」。把 n 当数量、p 当概率记录下来，
         才能真正回答"筛 100 个砾石能得到几个钻石"。
    """
    amount, chance = 1, None
    ra = rec.get("result_amount")
    if isinstance(ra, dict):
        amount = int(ra.get("n", ra.get("count", 1)) or 1)
        chance = ra.get("p")
    elif isinstance(ra, (int, float)):
        amount = int(ra)
    for key in ("result", "results", "output", "outputs"):
        r = rec.get(key)
        if isinstance(r, str):
            return r, amount, chance
        if isinstance(r, dict):
            if "item" in r and isinstance(r["item"], str):
                return r["item"], int(r.get("count", amount)), chance
            if "id" in r and isinstance(r["id"], str):
                return r["id"], int(r.get("count", amount)), chance
            if "items" in r and r["items"]:
                x = norm_ing(r["items"][0])
                if isinstance(x.get("id"), str):
                    return x["id"], int(r.get("count", amount)), chance
        if isinstance(r, list) and r and isinstance(r[0], dict):
            x = r[0]
            rid = x.get("item") or x.get("id")
            if isinstance(rid, str):
                return rid, int(x.get("count", amount)), chance
    return None, 0, None


def ingredients_of(rec):
    """取原料。

    ⚠ 关键修正（真实踩坑）：Ex Deorum 与 KubeJS 写的筛矿配方用的是 **ingredient（单数）**，
      而不是 ingredients/key/inputs。少了这一条，索引里所有筛矿配方的"原料"都是空的，
      于是"砾石+铁筛网能出什么"这种最要紧的问题根本答不出来。
    """
    out = []
    for key in ("ingredients", "ingredient", "key", "inputs", "input"):
        v = rec.get(key)
        if isinstance(v, list):
            out += [norm_ing(x) for x in v]
        elif isinstance(v, dict):
            # shaped 的 key: {"X": {...}} —— 键都是单个字符
            if v and all(isinstance(k, str) and len(k) <= 2 for k in v.keys()):
                out += [norm_ing(x) for x in v.values()]
            else:
                out.append(norm_ing(v))
    return out


def build():
    idx = {}
    jars = sorted(glob.glob(os.path.join(MODS, "*.jar")))
    n_rec = 0
    for j in jars:
        try:
            z = zipfile.ZipFile(j)
        except Exception as e:
            # ★不静默✗★：整个 jar 打不开 ⇒ ★它里面的**所有配方**都不在索引里**✗★
            #   ★下面"单条配方读不到"都会喊 ✗ 这一层更粗 ✗ 更该喊✗★ ✓
            #   （★静默少一整个模组 ⇒ "查不到这个配方"会变成**假结论**✗★ ✓）
            print("[记录] jar 打不开（★该模组配方**全部缺席**✗★）：%s: %s"
                  % (os.path.basename(j), type(e).__name__), file=sys.stderr)
            continue
        for n in z.namelist():
            if not (n.startswith("data/") and "/recipes/" in n and n.endswith(".json")):
                continue
            try:
                rec = json.loads(z.read(n).decode("utf-8", "replace"))
            except Exception as e:
                # 记录：一条配方读不了 ⇒ 索引里静默少一条（"不会做"可能是假的）
                print("[记录] 配方读不到（索引少一条）：%s: %s"
                      % (n, type(e).__name__), file=sys.stderr)
                continue
            if not isinstance(rec, dict):
                continue
            rid, cnt, chance = result_of(rec)
            # 有些模组的 result 字段本身是对象（{item:{...}} 之类），必须压成字符串，
            # 否则会以"不可哈希的 dict"直接崩在 setdefault 上——真实踩到过。
            if isinstance(rid, dict):
                rid = rid.get("id") or rid.get("item") or None
            if not isinstance(rid, str) or not rid:
                continue
            n_rec += 1
            idx.setdefault(rid, []).append({
                "type": rec.get("type", "?"),
                "count": cnt,
                "chance": chance,
                # mesh 是 Ex Deorum 筛矿的必填字段：筛网等级决定能不能筛、出什么
                "mesh": rec.get("mesh"),
                "from": os.path.basename(j),
                "path": n,
                "ingredients": ingredients_of(rec),
                "pattern": rec.get("pattern"),
            })
    # KubeJS：包作者常在这里增删配方，一并记录脚本位置（内容不做 JS 解释，只登记文件）
    kj = []
    for p in glob.glob(os.path.join(KUBEJS, "**", "*.js"), recursive=True):
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except Exception as e:
            # 记录：KubeJS 脚本读不了 ⇒ 配方来源清单静默少一个文件
            print("[记录] KubeJS 脚本读不到（来源清单少一个）：%s: %s"
                  % (os.path.basename(p), type(e).__name__), file=sys.stderr)
            continue
        if "recipe" in txt.lower() and ("add" in txt.lower() or "remove" in txt.lower()):
            kj.append(os.path.relpath(p, BASE))
    idx["__kubejs_scripts"] = kj
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False)
    print("索引已建立：%d 个 jar，%d 条配方，%d 个产物" % (len(jars), n_rec, len(idx) - 1))
    print("KubeJS 中涉及配方增删的脚本：%d 个" % len(kj))
    print("缓存：%s" % CACHE)
    return idx


def load():
    if not os.path.isfile(CACHE):
        return build()
    with open(CACHE, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--find")
    ap.add_argument("--type", help="按配方类型筛选（子串，如 exdeorum:sieve）")
    ap.add_argument("--input", help="按原料 id 子串筛选（如 minecraft:gravel）")
    ap.add_argument("--mesh", help="按筛网筛选（如 iron_mesh）")
    ap.add_argument("--raw", action="store_true", help="配合 --type/--find：打印原始 JSON")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args(argv)

    if args.build:
        build()
        return 0
    idx = load()
    if args.stats:
        outs = {k: v for k, v in idx.items() if k != "__kubejs_scripts" and v}
        print("产物数：%d" % len(outs))
        types = {}
        for v in outs.values():
            for r in v:
                types[r["type"]] = types.get(r["type"], 0) + 1
        print("配方类型 Top 15：")
        for t, c in sorted(types.items(), key=lambda x: -x[1])[:15]:
            print("   %-52s %d" % (t, c))
        return 0
    def hits_filters(r):
        if args.input:
            ids = [str(i.get("id") or i.get("tag") or "") for i in r["ingredients"]]
            if not any(args.input.lower() in x.lower() for x in ids):
                return False
        if args.mesh:
            if not r.get("mesh") or args.mesh.lower() not in str(r["mesh"]).lower():
                return False
        return True

    if args.type or args.input or args.mesh:
        want = (args.type or "").lower()
        shown = 0
        for out, recs in idx.items():
            if out == "__kubejs_scripts":
                continue
            for r in recs:
                if want and want not in r["type"].lower():
                    continue
                if not hits_filters(r):
                    continue
                ing = ", ".join(
                    (i.get("id") or i.get("tag") or json.dumps(i, ensure_ascii=False))
                    for i in r["ingredients"][:4]
                ) or "(无)"
                extra = ""
                if r.get("mesh"):
                    extra += "  mesh=%s" % r["mesh"]
                if r.get("chance") is not None:
                    extra += "  p=%s" % r["chance"]
                print("  %-30s <- %-26s [%s] x%d%s" % (
                    out, ing, r["type"], r["count"], extra))
                if args.raw:
                    print("      raw: " + json.dumps(r, ensure_ascii=False)[:900])
                shown += 1
                if shown >= args.limit:
                    print("  …（--limit 调整）")
                    return 0
        if shown == 0:
            print("没有匹配的配方（type=%r input=%r mesh=%r）" % (args.type, args.input, args.mesh))
        return 0
    if args.find:
        key = args.find
        exact = idx.get(key) or []
        sub = []
        if not exact:
            for k, v in idx.items():
                if k != "__kubejs_scripts" and key in k:
                    sub.append((k, v))
        if exact:
            print("产物 %s 共 %d 条配方：" % (key, len(exact)))
            for r in exact[: args.limit]:
                print("  [%s] x%d  from %s" % (r["type"], r["count"], r["from"]))
                if r.get("pattern"):
                    for line in r["pattern"]:
                        print("        | %s" % line)
                for ing in r["ingredients"][:9]:
                    print("        需 %s" % json.dumps(ing, ensure_ascii=False))
        elif sub:
            print("没有精确匹配 %r，子串匹配 %d 个产物（列前 %d）：" % (key, len(sub), args.limit))
            for k, v in sub[: args.limit]:
                print("  %-56s %d 条" % (k, len(v)))
        else:
            print("没找到 %r 的配方" % key)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
