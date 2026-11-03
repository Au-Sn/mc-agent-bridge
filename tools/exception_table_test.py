#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exception_table_test.py -- ★例外表的离线判据★（X1~X7 ✓ 全离线 ✓ 秒级 ✓ 2026-10-03）

★为什么要有它✗★：★例外表是阶段 3 的**落点** ✗ 它一松 ✗ "★分歧★"就会变成
  "★一张更大的名字表★"✗★ ⇐ ★那正是这条路线**最怕**的退路✗★ ✓
  ⇒ ★所以"★拒收什么★"必须比"★收什么★"写得更死✗★ ✓

★判据（先写死）★
  X1 ★缺字段 ⇒ 拒✗★（★物种／主张／结论／证据／出处／声明人✗★）
  X2 ★★★标签证据**不许**支撑**物理**结论✗★★★（★铁律 1 ✗ 这是**核心**那条✓★）
      ★而标签证据**可以**支撑**语义**结论✗★（★"★这是半砖★"这种✓★）
  X3 ★物理结论必须是布尔 ✗ 家族结论必须在闭集里✗★
  X4 ★`name_fallback` ⇒ 必须 TEMPORARY ＋ 复核触发✗★（★登记册第 4 条✓★）
  X5 ★升级语义✗★：★更硬的覆盖更软的 ✓ 反方向**拒收**✗★
  X6 ★坏文件／形状不对 ⇒ **抛** ✗ 不许当成空表✗★（★"★空表★"会让"★没声明★"看着像"★没事★"✓★）
  X7 ★生成物里每条都要看得见**证据与出处**✗★（★不许只有结论✓★）
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import exception_table as ET  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def ent(**kw):
    base = {"species": "x:a", "claim": "blocks_space", "verdict": True,
            "evidence": "collision", "source": "dshshape 导出 2026-10-03 读 x:a 的碰撞箱",
            "by": "测试"}
    base.update(kw)
    return base


print("== exception_table_test：X1~X7 ==")
tmp = pathlib.Path(tempfile.mkdtemp()) / "exceptions.json"

# ---- X1 缺字段 ----
miss = [(k, ET.validate(ent(**{k: ""}))) for k in
        ("species", "claim", "verdict", "evidence", "source", "by")]
_ok_all = all(not o for _k, (o, _w) in miss)
# ★★2026-10-04 修判据✗★★：★`verdict=""` 的拒绝理由现在是 **R4**（★必须是布尔✓★）✗
#   而**不是** R1 —— ★因为 `verdict` 单独判"★在不在★" ✗ 免得把 `False` 当没写✗★ ✓
_r1_ok = all(("R1" in w) for k, (o, w) in miss if k != "verdict")
check("X1", _ok_all and _r1_ok,
      "★六样缺任何一个都要拒 ✗ 五个字符串字段报 R1 ✗ verdict 报 R4✗★（%s）"
      % "／".join("%s:%s" % (k, ("缺→拒" if not o else "★收了✗★")) for k, (o, _w) in miss))

# ---- X2 ★核心：标签证据不许支撑物理结论 ----
v1 = ET.validate(ent(evidence="registry", source="minecraft:slabs 标签里有它（2026-10-03 普查）"))
check("X2a", (not v1[0]) and ("R3" in v1[1]),
      "★★标签证据 ⇒ **物理**结论必须拒收✗★★ ⇒ %s" % v1[1][:60])
v2 = ET.validate(ent(claim="family", verdict="slab", evidence="registry",
                     source="minecraft:slabs 标签里有它（2026-10-03 普查）"))
check("X2b", v2[0], "★标签证据 ⇒ **语义**结论**可以**收✗★（★铁律 1 的另一半✓★）")
v3 = ET.validate(ent(claim="is_floor", evidence="registry",
                     source="minecraft:slabs 标签（2026-10-03 普查）"))
check("X2c", not v3[0], "★`is_floor` 也是物理主张 ⇒ 同样拒✗★")

# ---- X3 结论形状 ----
check("X3a", not ET.validate(ent(verdict="yes"))[0], "★物理结论必须是布尔✗★")
check("X3b", not ET.validate(ent(claim="family", verdict="半砖"))[0],
      "★家族结论必须在闭集里✗★（%s）" % "／".join(ET.FAMILIES[:4]))

# ---- X4 name_fallback 强制条款 ----
check("X4a", not ET.validate(ent(evidence="name_fallback",
                                 source="名字表 PASS_SUB 命中它（2026-10-03 读源码）"))[0],
      "★`name_fallback` 缺 TEMPORARY／触发 ⇒ 拒✗★")
# ★★X4b 改主张（★A4 ✗ §79.241✗★）✗★★：
#   ★这条**原来断言的是旧模型**✗★ —— 它拿**物理主张** ＋ `name_fallback` 当合法（★只要带 TEMPORARY✓★）✗★ ✓
#   ★而 A4 之后`name_fallback` **不在物理梯上**✗（★物理梯只有 collision／experiment✓★）⇒
#     ★它被 **R7** 拒（★"★名字不许进物理★" ✗ 那正是 §11 要堵的✓★）✗★ ✓
#   ⇒ ★改成断言**语义那一侧**的合法用法 ✗ 并**补一条**反向的（★物理 ＋ 名字 ⇒ 拒✓★）✗★ ✓
check("X4b", ET.validate(ent(claim="family", verdict="full", evidence="name_fallback",
                             temporary=True, trigger="阶段 4 完成",
                             source="名字表 PASS_SUB 命中它（2026-10-03 读源码）"))[0],
      "★`name_fallback` ＋ TEMPORARY＋触发 ⇒ **语义**那一侧收✗★"
      "（★A4 起名字只在语义梯上✓★）")
check("X4c", not ET.validate(ent(evidence="name_fallback", temporary=True,
                                 trigger="阶段 4 完成",
                                 source="名字表 PASS_SUB 命中它（2026-10-03 读源码）"))[0],
      "★物理主张 ＋ `name_fallback` ⇒ **拒**✗★（★「名字不许进物理」 ✗ R7✓★）")
check("X5a", ET.add(ent(evidence="experiment", source="世界实验：地图字母说这一层被占（2026-10-03）"),
                    tmp)[0], "★先放一条 `experiment`✗★")
_r5b = ET.add(ent(evidence="registry", claim="family", verdict="full",
                  source="minecraft:planks 标签（2026-10-03 普查）"), tmp)
check("X5b", _r5b[0],
      "★同一物种**不同主张** ⇒ 不算覆盖 ✗ 这条是 family ⇒ 应当能收✗★ ⇒ %s" % _r5b[1][:70])
_r = ET.add(ent(evidence="name_fallback", temporary=True, trigger="t",
                source="名字表命中它（2026-10-03 读源码）"), tmp)
check("X5c", not _r[0], "★软的**不许**覆盖硬的✗★ ⇒ %s" % _r[1][:50])
check("X5d", ET.add(ent(evidence="collision", source="dshshape 导出 2026-10-03 读碰撞箱"),
                    tmp)[0], "★硬的**可以**覆盖软的✗★")

# ---- X6 坏文件 ⇒ 抛 ----
bad = pathlib.Path(tempfile.mkdtemp()) / "bad.json"
bad.write_text("{ 这不是 json", encoding="utf-8")
try:
    ET.load(bad)
    threw = False
except RuntimeError:
    threw = True
check("X6", threw, "★坏文件 ⇒ **抛** ✗ 不许静默当空表✗★")

# ---- X7 生成物 ----
doc = pathlib.Path(tempfile.mkdtemp()) / "例外表.md"
ET.render(ET.load(tmp), doc)
txt = doc.read_text(encoding="utf-8")
check("X7", ("证据" in txt) and ("出处" in txt) and ("collision" in txt),
      "★生成物里每条都要看得见证据与出处✗★")

# ---- Y1~Y3 接进 blockkb（★铁律 1 的机械形态：物理级只收碰撞／实验 ✗ 语义级只收标签✓★）----
import os  # noqa: E402
import importlib  # noqa: E402

os.environ["CLASSIFIER_SOURCE"] = "table"
import blockkb as KB  # noqa: E402
importlib.reload(KB)

_src = "dshshape 导出 2026-10-03 读 x:slab 的碰撞箱（max_height=0.5）"
_ok, _why = ET.add(ent(species="x:slab1", claim="blocks_space", verdict=True,
                       evidence="collision", source=_src), tmp)
check("Y1a", _ok, "★先放进一条物理（★碰撞证据✓★）✗★ ⇒ %s" % _why[:50])
ET.add(ent(species="x:sem1", claim="family", verdict="slab", evidence="registry",
           source="minecraft:slabs 标签里有它（2026-10-03 普查）"), tmp)
KB.TABLE.clear()
KB.REFUSED.clear()
_r = ET.to_blockkb(ET.load(tmp), KB)
check("Y1b", (_r["put"] >= 2), "★两条都该进 `blockkb`✗★ ⇒ put=%s refused=%s"
      % (_r["put"], _r["refused"]))
check("Y2", (KB.classify("x:slab1", phys=True) or {}).get("level") == "collision",
      "★物理主张用碰撞证据 ⇒ 进**碰撞槽**✗★ ⇒ %s"
      % (KB.classify("x:slab1", phys=True) or {}).get("level"))
# ★★2026-10-03 补✗★★：★它**不许**顺带把语义槽也写成 collision✗★（★两槽拆分的意思✓★）
check("Y2b", (KB.get("x:slab1") or {}).get("level") != "collision",
      "★★碰撞证据**不许**污染语义槽✗★★ ⇒ 语义槽是 %s"
      % (KB.get("x:slab1") or {}).get("level"))
check("Y3", (KB.get("x:sem1") or {}).get("level") == "registry",
      "★语义主张用标签证据 ⇒ 进 `registry` 级 ✗ **不许**落物理级✗★ ⇒ %s"
      % (KB.get("x:sem1") or {}).get("level"))
# ★★关键否定例✗★★：★物理主张 ＋ 名字兜底 ⇒ **不许**进（★表本身也会拒 ✗ 这里再兜一层✓★）
KB.TABLE.clear()
KB.REFUSED.clear()
_r2 = ET.to_blockkb([ent(species="x:bad1", claim="blocks_space", verdict=True,
                        evidence="name_fallback", temporary=True, trigger="t",
                        source="名字表命中它（2026-10-03 读源码）")], KB)
check("Y4", (_r2["put"] == 0) and KB.TABLE == {},
      "★★物理主张不许靠名字兜底✗★★ ⇒ put=%s（★表里 %d 条✓★）" % (_r2["put"], len(KB.TABLE)))
os.environ.pop("CLASSIFIER_SOURCE", None)

# ---- Z1~Z4 自动声明：**只许语义级**（★决策级一条都不许碰✗★）----
_rows = [
    ("x:dec", "pass", "slab", "★★决策级✗★★ ★挡人 False⇒True✗★"),
    ("x:conf", "full", None, "★★决策级✗★★ ★标签自相冲突 ✗ 必须先解决★"),
    ("x:none", "full", None, "★没法比（★有一边没族名✓★）"),
    ("x:sem", "full", "machine", "★语义级（★两族在「挡人／能站」上一样 ✗ 只是名字不同✓★）"),
    ("x:same", "full", "full", "★语义级（★两族在「挡人／能站」上一样 ✗ 只是名字不同✓★）"),
]
_keep, _drop = ET.pick_semantic(_rows, cap=10)
_sp = [e["species"] for e in _keep]
check("Z1", "x:dec" not in _sp, "★★决策级**一条都不许**自动声明✗★★ ⇒ 入选 %s" % _sp)
check("Z2", ("x:conf" not in _sp) and ("x:none" not in _sp),
      "★冲突与表中无都不收✗★ ⇒ 入选 %s" % _sp)
check("Z3", _sp == ["x:sem"], "★只收**真分歧的语义级**✗★ ⇒ 入选 %s" % _sp)
_z3 = [e for e in _keep if e["species"] == "x:sem"][0]
check("Z4", (_z3["evidence"] == "registry") and (_z3["claim"] == "family")
      and ET.validate(_z3)[0],
      "★自动生成的条目**必须**过表自己的校验（★证据 registry ✓ 主张 family✓★）✗★ ⇒ %s"
      % (ET.validate(_z3)[1][:50]))

# ---- X1b/X1c ★`False` 是**合法结论** ✗ 不许被当成「没写」✗★（★2026-10-04 修的真错✓★）----
check("X1b", ET.validate(ent(verdict=False))[0],
      "★物理结论 `False` ⇒ 必须收 ✗ 它与 `True` 一样是结论✗★")
check("X1c", not ET.validate({k: v for k, v in ent().items() if k != "verdict"})[0],
      "★而**真的没写** `verdict` ⇒ 仍要拒✗★")

print("=> exception_table %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
