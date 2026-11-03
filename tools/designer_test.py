#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""designer_test.py -- 模块 L5 设计官的离线判据（★不需要游戏 ✗ 注入合成配方数据✗★）

规格 §13.1／§13.2／§14.1：L5 只读 · 离线设计 · 每一步可判。
判据口径（★都是"能机器判"的✗★）：
  D1  ★确定性★：同输入 ⇒ 同输出（两次序列化逐字相等）
  D2  元件清单来自配方图：角色/数量与合成配方逐项对上（机器/容器/料块分行）
  D3  ★覆盖完整对账★：配方树每个节点都有去处（placed/materials/intermediates/tags），
      格子数 == 可放置元件的实例数（计数对账）
  D4  ★可被 port.py 消费★：port.plan 算账通过（无悬空）＋ port.order 一致 ＋
      port.execute（假原语）能把整张图放完
  D5  边界拒绝：bounds 放不下 ⇒ refuse reason=out_of_bounds（★不硬排✗★）
  D6  无配方拒绝：no_recipe（★不许凭空编元件✗★）
  D7  配方数据缺失/坏形状 ⇒ no_recipe_data／bad_recipe_data（诚实分开）
  D8  预算拒绝：元件数超 max_cells ⇒ too_many_cells
  D9  无可放置元件 ⇒ no_placeable_components
  D10 参数错抛 DesignError（target 空／need<1／bounds 坏）
  D11 ★放置顺序★：自下而上＋与 port.order 一致；所有格 dy>=0 且无悬空
  D12 理由与置信度：每格从属某个元件 ＋ rationale/assumptions 有 why/confidence/evidence
  D13 ★不按名字猜方块★：同一 id 被注入分类器判成 item 时**不再是机器**（角色随分类走）
  D14 ★不写死本包数字★：源码里没有 24779/20764 这类本包计数；换合成数据仍成立
  D15 真实数据冒烟：默认 build/recipes.json 上一个有机器元件的目标能设计出布局
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

import designer as D          # noqa: E402
import port as PORT           # noqa: E402

# ── 合成配方数据（★换整合包/换数据源都能跑：判据不依赖本包真实内容✗★）──
RECIPES = {
    "test:gear": [{"type": "minecraft:crafting_shaped", "count": 1,
                   "ingredients": [
                       {"id": "test:smelter", "count": 2},
                       {"id": "test:chest_machine", "count": 1},
                       {"id": "test:frame_block", "count": 3},
                       {"tag": "forge:ingots/iron", "count": 4},
                       {"id": "test:raw_ore", "count": 2},
                   ]}],
}
CLASSIFY = {
    "test:smelter": {"placeable": True, "role": "machine", "confidence": 0.9,
                     "evidence": {"kind": "fake-classification", "ref": "cls:smelter"}},
    "test:chest_machine": {"placeable": True, "role": "container", "confidence": 0.85,
                           "evidence": {"kind": "fake-classification",
                                        "ref": "cls:chest_machine"}},
    "test:frame_block": {"placeable": True, "role": "block", "confidence": 0.7,
                         "evidence": {"kind": "fake-classification",
                                      "ref": "cls:frame_block"}},
    "test:raw_ore": {"placeable": False, "role": "item", "confidence": 0.2,
                     "evidence": {"kind": "fake-classification", "ref": "cls:raw_ore"}},
}


def classify(bid: str) -> dict:
    return CLASSIFY.get(bid, {"placeable": False, "role": "item", "confidence": 0.1,
                              "evidence": {"kind": "fake-classification",
                                           "ref": "cls:unknown"}})


class FakePrims:
    """给 port.execute 用的假原语：只记录，不碰世界"""

    def __init__(self):
        self.placed = []

    def place(self, pos, item, mission=""):
        self.placed.append({"pos": list(pos), "block": item})
        return {"ok": True, "kind": "place", "why": "place_verified"}


def _design_ok(**kw):
    return D.design("test:gear", recipes=RECIPES, classify=classify, **kw)


def main() -> int:
    checks = []

    # ── D1 确定性 ──
    p1 = _design_ok(need=1)
    p2 = _design_ok(need=1)
    checks.append(("D1 ★确定性：同输入 ⇒ 同输出★",
                   p1.get("ok") and json.dumps(p1, ensure_ascii=False, sort_keys=True)
                   == json.dumps(p2, ensure_ascii=False, sort_keys=True),
                   "ok=%s cells=%d" % (p1.get("ok"), len(p1.get("cells") or []))))

    # ── D2 元件清单来自配方图（角色/数量对账）──
    comp = {c["item"]: c for c in (p1.get("components") or [])}
    cells_role = {}
    for c in p1.get("cells") or []:
        cells_role[c["role"]] = cells_role.get(c["role"], 0) + 1
    checks.append(("D2 元件清单来自配方图：机器 2 ／ 容器 1 ／ 料块 3 格",
                   comp.get("test:smelter", {}).get("need") == 2
                   and comp.get("test:chest_machine", {}).get("role") == "container"
                   and comp.get("test:frame_block", {}).get("role") == "block"
                   and cells_role == {"machine": 2, "container": 1, "block": 3},
                   "roles=%s" % (cells_role,)))

    # ── D3 覆盖对账 ＋ 计数对账 ──
    audit = p1.get("audit") or {}
    mats = {m["item"]: m["need"] for m in (p1.get("materials") or [])}
    checks.append(("D3 ★覆盖完整对账★（每个节点有去处 ✗ 格数=元件实例数）",
                   audit.get("coverage_ok") is True and audit.get("counts_ok") is True
                   and audit.get("nodes") == 5 and audit.get("cells") == 6
                   and mats.get("test:raw_ore") == 2
                   and any(t["key"] == "forge:ingots/iron" for t in p1.get("tags") or []),
                   "audit=%s mats=%s" % (audit.get("buckets"), mats)))

    # ── D4 可被 port.py 消费 ──
    pl = PORT.plan(p1["cells"], (0, 0, 0), {})
    fake = FakePrims()
    ex = PORT.execute(pl, fake, live={})
    checks.append(("D4 ★可被 port.py 消费★（算账过＋顺序一致＋假原语放完）",
                   pl["need_n"] == 6 and pl["floating"] == []
                   and ex["placed_n"] == 6 and len(fake.placed) == 6
                   and p1["placement_order"] == [{"dx": c["dx"], "dy": c["dy"],
                                                  "dz": c["dz"], "block": c["block"]}
                                                 for c in PORT.order(p1["cells"], {}, (0, 0, 0))],
                   "need=%d placed=%d floating=%d"
                   % (pl["need_n"], ex["placed_n"], len(pl["floating"]))))

    # ── D5 边界拒绝 ──
    r5 = _design_ok(bounds={"x": 2, "y": 1, "z": 1})       # 3 行塞进 1 行 ⇒ 放不下
    checks.append(("D5 边界拒绝：放不下 ⇒ out_of_bounds（不硬排）",
                   r5.get("ok") is False and r5.get("refused") is True
                   and r5.get("reason") == "out_of_bounds", str(r5.get("reason"))))

    # ── D6 无配方拒绝 ──
    r6 = D.design("test:no_such_recipe", recipes=RECIPES, classify=classify)
    checks.append(("D6 无配方 ⇒ no_recipe（不凭空编元件）",
                   r6.get("ok") is False and r6.get("reason") == "no_recipe",
                   str(r6.get("reason"))))

    # ── D7 数据缺失／坏形状分开报 ──
    r7a = D.design("test:gear", recipes={}, classify=classify)
    r7b = D.design("test:gear", recipes={"test:gear": {"not": "a-list"}},
                   classify=classify)
    r7c = D.design("test:gear", recipes={"test:gear": ["not-a-dict"]}, classify=classify)
    checks.append(("D7 数据缺失⇒no_recipe_data ／ 坏形状⇒bad_recipe_data",
                   r7a.get("reason") == "no_recipe_data"
                   and r7b.get("reason") == "bad_recipe_data"
                   and r7c.get("reason") == "bad_recipe_data",
                   "%s/%s/%s" % (r7a.get("reason"), r7b.get("reason"), r7c.get("reason"))))

    # ── D8 预算拒绝 ──
    r8 = _design_ok(max_cells=2)
    checks.append(("D8 元件数超预算 ⇒ too_many_cells",
                   r8.get("ok") is False and r8.get("reason") == "too_many_cells",
                   str(r8.get("reason"))))

    # ── D9 无可放置元件 ──
    r9 = D.design("test:tagonly", recipes={
        "test:tagonly": [{"type": "x", "count": 1,
                          "ingredients": [{"tag": "forge:ingots/iron", "count": 2}]}],
    }, classify=classify)
    checks.append(("D9 无可放置元件 ⇒ no_placeable_components",
                   r9.get("ok") is False and r9.get("reason") == "no_placeable_components",
                   str(r9.get("reason"))))

    # ── D10 参数错抛 DesignError ──
    bad10 = []
    for name, fn in [
        ("target 空", lambda: D.design("", recipes=RECIPES, classify=classify)),
        ("need=0", lambda: D.design("test:gear", need=0, recipes=RECIPES,
                                    classify=classify)),
        ("bounds 坏", lambda: D.design("test:gear", bounds=(1, 2), recipes=RECIPES,
                                       classify=classify)),
        ("recipes 不是 dict", lambda: D.design("test:gear", recipes=[], classify=classify)),
    ]:
        try:
            fn()
            bad10.append((name, "没抛"))
        except D.DesignError as exc:
            print("  （D10 预期拒绝：%s ⇒ DesignError ✓）" % name)
        except Exception as exc:
            bad10.append((name, "抛了 %s" % type(exc).__name__))
    # bounds 坏会走 refuse（不是抛）——单独核对
    rb = D.design("test:gear", bounds={"x": 0, "y": 1, "z": 1}, recipes=RECIPES,
                  classify=classify)
    checks.append(("D10 参数错 ⇒ DesignError／坏 bounds ⇒ bad_bounds",
                   not bad10 and rb.get("reason") == "bad_bounds",
                   str(bad10[:2]) if bad10 else "4/4 正确"))

    # ── D11 放置顺序：自下而上、与 port.order 一致、无负层 ──
    order = p1.get("placement_order") or []
    want_order = [{"dx": c["dx"], "dy": c["dy"], "dz": c["dz"], "block": c["block"]}
                  for c in PORT.order(p1["cells"], {}, (0, 0, 0))]
    checks.append(("D11 放置顺序：与 port.order 一致 ＋ 所有格 dy>=0",
                   len(order) == 6 and order == want_order
                   and all(int(c["dy"]) >= 0 for c in order),
                   "order=%s" % ([(c["dx"], c["dy"], c["dz"]) for c in order[:6]],)))

    # ── D12 理由/置信度 ──
    bad12 = []
    if not (0.0 <= float(p1.get("confidence") or -1) <= 1.0):
        bad12.append("总置信度越界")
    for c in p1.get("cells") or []:
        if not c.get("component") or not c.get("why"):
            bad12.append("格子缺理由/从属")
            break
    for r in (p1.get("rationale") or []):
        if not r.get("why") or not ("confidence" in r) or not r.get("evidence"):
            bad12.append("rationale 不齐")
            break
    for a in (p1.get("assumptions") or []):
        if not a.get("why") or not ("confidence" in a):
            bad12.append("assumption 不齐")
            break
    checks.append(("D12 理由/置信度：每格有从属＋why，rationale/assumptions 齐",
                   not bad12, str(bad12[:2]) if bad12 else
                   "conf=%.2f reasons=%d" % (p1.get("confidence"),
                                             len(p1.get("rationale") or []))))

    # ── D13 ★不按名字猜方块：角色随分类走★ ──
    def classify_as_item(bid):
        r = classify(bid)
        if bid == "test:smelter":            # 同一个 id，分类器说它不是可放方块
            return {"placeable": False, "role": "item", "confidence": 0.1,
                    "evidence": {"kind": "fake-classification", "ref": "forced-item"}}
        return r
    r13 = D.design("test:gear", recipes=RECIPES, classify=classify_as_item)
    roles13 = {c["item"]: c["role"] for c in (r13.get("components") or [])}
    checks.append(("D13 ★角色随分类走，不按名字猜★（smelter 被判 item ⇒ 不再是机器）",
                   r13.get("ok") is True and "test:smelter" not in roles13
                   and roles13.get("test:chest_machine") == "container"
                   and len(r13.get("cells") or []) == 4,
                   "components=%s cells=%d" % (sorted(roles13), len(r13.get("cells") or []))))

    # ── D14 ★不写死本包数字★ ──
    src = (ROOT / "tools" / "designer.py").read_text(encoding="utf-8", errors="replace")
    hard = [n for n in ("24779", "20764", "13046872") if n in src]
    checks.append(("D14 ★不写死本包数字★（换数据源仍成立）",
                   not hard, "命中=%s" % (hard or "无")))

    # ── D15 真实数据冒烟（默认 build/recipes.json）──
    try:
        real = D.design("advanced_ae:pick_craft_card", need=1)
        roles15 = {}
        for c in real.get("cells") or []:
            roles15[c["role"]] = roles15.get(c["role"], 0) + 1
        ok15 = (real.get("ok") is True and real.get("source") == "self_designed"
                and len(real.get("cells") or []) >= 1
                and roles15.get("machine", 0) >= 1
                and (real.get("data") or {}).get("recipes", "").endswith("recipes.json"))
        detail15 = "cells=%d roles=%s" % (len(real.get("cells") or []), roles15)
    except Exception as exc:                  # ★不许静默✗★
        ok15, detail15 = False, "异常 %r" % (exc,)
    checks.append(("D15 真实数据冒烟：默认配方库里有机器元件的目标能出布局", ok15, detail15))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:130]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => designer 有红（%d 项不对）" % bad)
        print("DESIGNER ok=0 bad=%d" % bad)
        return 1
    print("  => designer 全绿（确定性／覆盖对账／port 可消费／拒绝路径／不按名字猜）")
    print("DESIGNER ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
