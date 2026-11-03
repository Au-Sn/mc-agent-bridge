#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blockkb_test.py -- ★方块知识表的离线判据★（K1~K7 ✓ 全离线 ✓ 秒级 ✓ 2026-10-03）

★为什么要有它✗★：`blockkb.py` 是阶段 2 的**开关＋来源分级**那一层 ✗
  ★它一出错 ✗ 上层看到的"家族"会**静默变样**✗★ ⇒ 判据必须钉住三件事 ✓
    ① ★默认（`blacklist`）与**今天逐字相同**✗★ —— 这是"翻开关即回滚"的前提 ✓
    ② ★升级语义✗★ —— ★高级到达能覆盖低级 ✗ 低级**永远不许**覆盖高级✗★
    ③ ★`name_fallback` 的强制条款 ✗ 与"回落必须被声明"✗★（登记册第 2／4 条）

★判据（先写死）★
  K1 ★默认不动✗★：`SOURCE=blacklist` ⇒ 抽样一批名字 ✗ `classify(...)["fam"]` 必须**等于**
     `mapread.shape(...)`✗★（★逐字相同 ✗ 这条一红就说明"回滚"承诺破了✓★）
  K2 ★等级合法✗★：不在册的等级 ⇒ **拒收** ✗ 并记进 `REFUSED`✗★
  K3 ★来源必须能说✗★：`src` 空 ⇒ 拒收 ✓
  K4 ★`name_fallback` 强制条款✗★：没有 TEMPORARY 或没有复核触发 ⇒ **拒收** ✓
  K5 ★升级语义✗★：`registry` 放进去之后 ✗ `name_fallback` **不许**覆盖它 ✓
     而 `collision` 到达 ⇒ **覆盖** `name_fallback` 与 `registry` ✓
  K6 ★物理只听碰撞形状✗★：`phys=True` 时 ✗ `registry` 级的条目**不许**说话 ✓
  K7 ★回落必须声明✗★：`table+fallback` 下查不到 ⇒ 家族来自名字兜底 ✓
     而返回值里的 `declared` **必须**写明"回落到名字兜底" ＋ 它是 TEMPORARY ✓
"""
from __future__ import annotations

import importlib
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def fresh(source: str):
    """★换个开关值重新加载✗★（★模块自带默认值 ✓ 不给它别的入口✗★）"""
    os.environ["CLASSIFIER_SOURCE"] = source
    import blockkb
    importlib.reload(blockkb)
    blockkb.TABLE.clear()
    blockkb.REFUSED.clear()
    return blockkb


print("== blockkb_test：K1~K7 ==")

SAMPLE = ("minecraft:oak_leaves", "minecraft:oak_slab", "minecraft:oak_fence",
          "minecraft:grass_block", "minecraft:torch", "minecraft:stone",
          "supplementaries:book_pile_horizontal", "chipped:flat_andesite_tiles",
          "mcwfences:sandstone_grass_topped_wall", "minecraft:lantern")

# ---- K1 默认不动 ----
kb = fresh("blacklist")
bad = [(n, kb.classify(n)["fam"], kb.MR.shape(n)) for n in SAMPLE
       if kb.classify(n)["fam"] != kb.MR.shape(n)]
check("K1", not bad, "★默认必须与今天逐字相同✗★ %s" % (bad or
      "✓（%d 个名字全对 ✗ 这就是「翻开关即回滚」的前提✓★）" % len(SAMPLE)))

# ---- K2 等级不在册 ⇒ 拒收 ----
kb = fresh("blacklist")
_r = kb.put("x:a", "pass", "guess", "somewhere")
check("K2", (_r is False) and len(kb.REFUSED) == 1,
      "★不在册的等级 ⇒ 拒收 ＋ 记进 REFUSED✗★（%s）" % (kb.REFUSED[0]["why"] if kb.REFUSED else "★没记✗★"))

# ---- K3 来源必须能说 ----
kb = fresh("blacklist")
_r = kb.put("x:a", "pass", "registry", "   ")
check("K3", (_r is False) and kb.REFUSED, "★`src` 空 ⇒ 拒收✗★")

# ---- K4 name_fallback 强制条款 ----
kb = fresh("blacklist")
_r1 = kb.put("x:a", "pass", "name_fallback", "名字表")
_r2 = kb.put("x:b", "pass", "name_fallback", "名字表", trigger="阶段 4 完成")
_r3 = kb.put("x:c", "pass", "name_fallback", "名字表", temporary=True)
check("K4", (_r1 is False) and (_r2 is False) and (_r3 is False) and len(kb.REFUSED) == 3,
      "★缺 TEMPORARY 或 缺复核触发 ⇒ 都拒收✗★（拒了 %d 条）" % len(kb.REFUSED))
_r4 = kb.put("x:d", "pass", "name_fallback", "名字表", temporary=True, trigger="阶段 4 完成")
check("K4b", _r4 is True, "★两条都齐 ⇒ 收✗★")

# ---- K5 升级语义 ----
kb = fresh("table")
kb.put("x:a", "pass", "name_fallback", "名字表", temporary=True, trigger="t")
kb.put("x:a", "full", "registry", "minecraft:minecraft")
check("K5a", kb.get("x:a")["level"] == "registry",
      "★registry 覆盖 name_fallback✗★ ⇒ %s" % kb.get("x:a")["level"])
kb.put("x:a", "canopy", "name_fallback", "名字表", temporary=True, trigger="t")
check("K5b", kb.get("x:a")["level"] == "registry",
      "★name_fallback **不许**覆盖 registry✗★ ⇒ 仍是 %s" % kb.get("x:a")["level"])
kb.put("x:a", "slab", "collision", "dshshape")
# ★★2026-10-03 改过✗★★：★原来这条断言"★collision 到达 ⇒ 覆盖**一切**★"✗★ ——
#   ★而两槽拆分之后它**只覆盖物理那一侧**✗★（★语义仍是 registry 的 `full` ✗ 因为标签说了算✓★）
check("K5c", (kb.classify("x:a", phys=True)["level"] == "collision")
      and (kb.classify("x:a", phys=True)["fam"] == "slab"),
      "★collision 到达 ⇒ **物理**那一侧覆盖✗★ ⇒ %s／%s"
      % (kb.classify("x:a", phys=True)["level"], kb.classify("x:a", phys=True)["fam"]))
check("K5d", (kb.get("x:a")["level"] == "registry") and (kb.get("x:a")["fam"] == "full"),
      "★★而**语义**那一侧**不许**被碰撞改掉✗★★ ⇒ %s／%s"
      % (kb.get("x:a")["level"], kb.get("x:a")["fam"]))

# ---- K6 物理只听碰撞形状 ----
kb = fresh("table")
kb.put("x:a", "pass", "registry", "minecraft:leaves")
check("K6a", kb.classify("x:a", phys=True)["level"] == "unknown",
      "★phys=True 时 registry **不许**说话✗★ ⇒ %s" % kb.classify("x:a", phys=True)["level"])
kb.put("x:a", "full", "collision", "dshshape")
check("K6b", kb.classify("x:a", phys=True)["fam"] == "full",
      "★collision 说了算✗★ ⇒ %s" % kb.classify("x:a", phys=True)["fam"])

# ---- K10 ★铁律 1 的**端到端**守卫（★2026-10-03 加 ✗ 因为 K6a 只查了 `classify`✓★）----
#   ★规划真正调的是 `blocks_space` ／ `is_floor` ✗ 而它们会不会**顺手**去查表 ✗ 之前没人验过✗★ ✓
kb = fresh("table")
_before = (kb.blocks_space("x:z"), kb.is_floor("x:z"))
kb.put("x:z", "machine", "registry", "★标签 `crates` 里有它（★语义级✓★）")
_after = (kb.blocks_space("x:z"), kb.is_floor("x:z"))
check("K10a", _before == _after,
      "★★语义（registry）条目**绝不许**动物理结果✗★★ ⇒ %s ⇒ %s" % (_before, _after))
# ★★防空转✗★★：★必须**同时**证明那条条目**确实生效了**（★否则"前后一样"可能是它根本没进去✓★）
check("K10b", kb.classify("x:z")["fam"] == "machine",
      "★语义上它必须**确实**生效 ✗ 否则 K10a 是空判据✗★ ⇒ %s" % kb.classify("x:z")["fam"])

# ---- K7 回落必须声明 ----
kb = fresh("table+fallback")
_r = kb.classify("minecraft:oak_leaves")
check("K7a", _r["level"] == "name_fallback",
      "★查不到 ⇒ 回落到名字兜底✗★ ⇒ %s" % _r["level"])
check("K7b", any("回落" in d for d in _r["declared"]),
      "★回落**必须**在 `declared` 里写明✗★ ⇒ %s" % (_r["declared"] or "★没声明✗★"))
check("K7c", any("TEMPORARY" in d for d in _r["declared"]),
      "★并且要标出它是 TEMPORARY✗★")
kb2 = fresh("table")
_r2 = kb2.classify("minecraft:oak_leaves")
check("K7d", (_r2["level"] == "unknown") and ("不许回落" in _r2["why"]),
      "★`table` 模式**不许**回落 ✗ 而且要明说✗★ ⇒ %s" % _r2["level"])

# ---- K11 ★导出的**几何**族 ⇒ 判定族（★2026-10-03 用户拍板✗★）----
#   ★为什么单列一条✗★：★用户拍板的族名是**几何**的 ✗ 与 `mapread` 现有族名不同 ✗
#     ⇒ ★"★上层零改动★"就落在 `family_from_export` 这张映射上 ✗ 它错了 ⇒ 全盘错✗★ ✓
_cases = [({"family": "full", "max_height": 1.0}, "full"),
          ({"family": "slab", "max_height": 0.5}, "slab"),
          ({"family": "fence_15", "max_height": 1.5}, "fence"),
          ({"family": "snow_layer", "max_height": 0.125}, "pass"),
          ({"family": "none", "max_height": 0.0}, "pass"),
          ({"family": "liquid", "max_height": 0.0}, "liquid"),
          ({"family": "other", "max_height": 0.9375}, "other")]
_bad = [(e, w) for (e, w) in _cases if kb.family_from_export(e)[0] != w]
check("K11a", not _bad, "★七类几何族都要映对✗★ ⇒ %s" % (_bad or "全对 ✓"))
check("K11b", kb.family_from_export({"family": "canopy", "max_height": 1.0})[0] is None,
      "★`canopy` **不许**由导出给（★它是语义 ✗ 碰撞看不出树冠✓★）✗★")
check("K11c", kb.family_from_export({"family": "other"})[0] is None,
      "★★`other` 缺 `max_height` ⇒ **拒**✗★★（★用户：★消费者不许为 `other` 写特例✓★）")
check("K11d", kb.family_from_export({"family": "月亮", "max_height": 1.0})[0] is None,
      "★不在册的族 ⇒ 拒✗★")

# ---- K8/K9 接老的"学来的"表（★等级一律查表 ✗ 禁止来源永久拒收✓★）----
import json  # noqa: E402
import tempfile  # noqa: E402

kb = fresh("table")
_tmp = pathlib.Path(tempfile.mkdtemp()) / "block_shapes.json"
_tmp.write_text(json.dumps({
    "minecraft:flowering_azalea_leaves": {"fam": "full", "src": "dshmap-blocked"},
    "x:feet_one": {"fam": "pass", "src": "dshmap-feet"},
    "x:letter_one": {"fam": "full", "src": "dshmap-letter"},
    "x:test_one": {"fam": "pass", "src": "selftest"},
    "x:weird_one": {"fam": "pass", "src": "i_made_this_up"},
    "x:no_src": {"fam": "pass"},
}, ensure_ascii=False), encoding="utf-8")
_r = kb.ingest_learned(str(_tmp), verbose=False)
check("K8a", (_r["accepted"] == 2) and (_r["refused"] == 4),
      "★只收在册来源（★2 收 4 拒 ✗ 实得 %s/%s✓★）" % (_r["accepted"], _r["refused"]))
# ★★2026-10-18（★P1-5 连带 ✗ §79.277✗★）✗★★：★`dshmap-feet` 是**物理实验**证据✗★ ⇒
#   ★修完之后它进的是**碰撞槽**（★`phys=True`✓★）✗ 而不是语义槽✗★ ⇒
#   ★断言要查 `PHYS` ✗ 查 `get()`（★语义口✗★）当然拿到 None✗★ ✓
#   ★（★"★物理事实住在物理槽★"这件事 ✗ 现在**有断言管**了✗★）✗★ ✓
check("K8b", (kb.PHYS.get("x:feet_one") or {}).get("level") == "experiment",
      "★`dshmap-feet` ⇒ **物理实验**级 ✗ 且必须住在**碰撞槽**✗★ ⇒ %s"
      % (kb.PHYS.get("x:feet_one") or {}).get("level"))
check("K8c", kb.get("minecraft:flowering_azalea_leaves") is None,
      "★`dshmap-blocked`（★循环✗★）⇒ **永久拒收** ✗ 一条都不许进表✗★")
check("K8d", any("永久禁止" in k for k in _r["why"]),
      "★拒收理由要按来源归类 ✗ 且写明「永久禁止」✗★ ⇒ %s" % list(_r["why"].keys())[:3])
check("K8e", kb.get("x:weird_one") is None,
      "★不在册的来源 ⇒ 拒（★铁律 3 ✗ 学来的必须来自更硬的东西✓★）")

# ---- K9 ★迁移之后再升级 ⇒ ★但**不许**跨槽覆盖✗★ ----
#   ★★2026-10-03 改过这条判据✗★★：★原来它要求"★collision 到达 ⇒ 语义槽也被改成 collision★"✗★
#   ⇒ ★而两槽拆分之后**那正是错的**✗★（★铁律 1：★物理听碰撞 ✗ 语义听标签 ⇒ 各听各的✗★）✓
# ★★2026-10-18（★P1-5 连带 ✗ §79.277✗★）✗★★：★这条判据的**前提**过时了✗★ ——
#   ★它原来指望 `dshmap-feet`（★**物理实验**级✗★）住在**语义槽**✗★ ⇒
#   ★而按**两条梯子**（A4）✗ `experiment` 是**物理**证据✗ 它现在住在**碰撞槽**✗★ ✓
#   ★⇒ 这条判据要测的**真规则**是"★**两槽互不影响**✗★"✗★ ⇒
#   ★★★要**先各放一条**✗ 再看碰撞到达时语义那条**还在不在**✗★★ ✓
kb.put("x:feet_one", "machine", "registry", "★判据自测：语义级✗★")
kb.put("x:feet_one", "full", "collision", "dshshape")
check("K9a", (kb.get("x:feet_one") or {}).get("level") == "registry",
      "★★碰撞到达**不许**抹掉语义槽✗★★（★语义那条是 `registry` ✗ 碰撞是物理✗★）⇒ %s"
      % (kb.get("x:feet_one") or {}).get("level"))
check("K9b", kb.classify("x:feet_one", phys=True)["level"] == "collision",
      "★而**物理**那一侧必须看到 `collision`✗★ ⇒ %s"
      % kb.classify("x:feet_one", phys=True)["level"])
check("K9c", kb.classify("x:feet_one", phys=False)["level"] == "registry",
      "★语义那一侧看到的仍是**语义级** `registry`（★不是碰撞✓★）✗★ ⇒ %s"
      % kb.classify("x:feet_one", phys=False)["level"])

# ---- K12 ★`/dshkb` 导出的装载器（★等级写死 collision ✗ 只写碰撞槽✓★）----
_exp = {"schema": "dshbridge/registry_blocks@1", "errors": 0,
        "blocks": {"x:exp_full": {"family": "full", "max_height": 1.0},
                   "x:exp_snow": {"family": "snow_layer", "max_height": 0.125},
                   "x:exp_other_bad": {"family": "other"},
                   "x:exp_canopy": {"family": "canopy", "max_height": 1.0},
                   "x:exp_badfam": {"family": "月亮", "max_height": 1.0}}}
kb = fresh("table")
_r12 = kb.load_export(_exp)
check("K12a", _r12["put"] == 2,
      "★只收过得了 `family_from_export` 的两条✗★ ⇒ put=%s（拒 %s）"
      % (_r12["put"], _r12["refused"]))
check("K12b", _r12["refused"] == 3,
      "★其余三条（★`other` 缺高度 ✗ `canopy` ✗ 族不在册✓★）都要**计入拒收**✗★ ⇒ %s"
      % _r12["refused"])
check("K12c", kb.classify("x:exp_snow", phys=True)["fam"] == "pass",
      "★`snow_layer` ⇒ 物理族 `pass`（★薄板／雪层不是一整格地板 ✗ v2.17✓★）✗★ ⇒ %s"
      % kb.classify("x:exp_snow", phys=True)["fam"])
check("K12d", kb.classify("x:exp_full", phys=True)["level"] == "collision",
      "★收进来的信源等级就是 `collision`✗★ ⇒ %s"
      % kb.classify("x:exp_full", phys=True)["level"])
check("K12e", kb.load_export({"nope": 1})["put"] == 0,
      "★形状不对（★没有 `blocks`✓★）⇒ 一条都不收 ✗ 并**说明**✗★")

os.environ.pop("CLASSIFIER_SOURCE", None)
print("=> blockkb %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
