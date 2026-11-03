#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchlist_test.py -- ★第五种状态的离线判据★（C1~C5 ✓ 全离线 ✓ 秒级 ✓ 2026-10-03）

★为什么它比别的判据更较真✗★：★`contradicted` 是**最容易烂掉**的一种状态✗★ ——
  ★它既可以悄悄变成"★不知道★"（★责任消失✗★）✗ 也可以悄悄变成"★挑一个★"（★禁止✗★）✗★ ✓
  ⇒ ★所以"★怎么写才算数★"必须钉死✗★ ✓

★判据（先写死）★
  C1 ★必须写明**两条通道各说什么**✗★（★"★有冲突★"这种话**不算**✓★）
  C2 ★必须有**隔离理由**与**重读条件**✗★（★没有重读条件 ⇒ 它会烂在表里✗★）
  C3 ★坏文件必须**抛**✗★（★不许当成空名单 ✗ 否则"★未裁决★"看起来像"★没有★"✓★）
  C4 ★机械生成：★生成的条目**必须**过自己的判据 ✗ 没过就**抛**✗★（★不许静默丢✓★）
  C5 ★名单上的人**不许**被自动声明✗★（★与 `pick_semantic` 联动验一次✓★）
"""
from __future__ import annotations

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
import watchlist as WL  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def ent(**kw):
    base = {"species": "x:a", "state": "contradicted",
            "channels": {"model": "full", "tags": ["叶子", "庄稼"]},
            "why_isolated": "★两条通道都有结论而不同 ✓ 今天没有裁决证据✗★",
            "recheck": "★导出到来 ⇒ 读碰撞形状重判✗★", "since": "2026-10-03"}
    base.update(kw)
    return base


print("== watchlist_test：C1~C5 ==")

# ---- C1 两条通道都要写 ----
check("C1a", not WL.validate(ent(channels={"model": "full"}))[0],
      "★只写模型一侧 ⇒ 拒✗★")
check("C1b", not WL.validate(ent(channels={"tags": ["叶子"]}))[0],
      "★只写标签一侧 ⇒ 拒✗★")
check("C1c", not WL.validate(ent(state="unknown"))[0],
      "★状态必须写死 `contradicted`✗★（★不许拿它跟 `unknown` 混✓★）")

# ---- C2 隔离理由与重读条件 ----
check("C2a", not WL.validate(ent(why_isolated=""))[0], "★缺隔离理由 ⇒ 拒✗★")
check("C2b", not WL.validate(ent(recheck=""))[0],
      "★缺重读条件 ⇒ 拒✗★（★没有它 ⇒ 这条会烂在表里✓★）")
check("C2c", WL.validate(ent())[0], "★四样齐 ⇒ 收✗★")

# ---- C3 坏文件必须抛 ----
bad = pathlib.Path(tempfile.mkdtemp()) / "bad.json"
bad.write_text("{ 这不是 json", encoding="utf-8")
try:
    WL.load(bad)
    threw = False
except RuntimeError:
    threw = True
check("C3", threw, "★坏文件 ⇒ **抛** ✗ 不许当空名单✗★")

# ---- C4 机械生成不许静默丢 ----
_rows = [("x:ok", "full", ["叶子", "庄稼"], "★标签侧自相冲突✗★")]
made = WL.build(_rows)
check("C4a", len(made) == 1 and made[0]["species"] == "x:ok",
      "★机械生成的条目要**留下**✗★ ⇒ %d 条" % len(made))
try:
    WL.build([("x:bad", "", [], "★故意缺模型侧✗★")])
    threw2 = False
except RuntimeError:
    threw2 = True
check("C4b", threw2, "★生成的条目没过判据 ⇒ **抛** ✗ 不许静默丢✗★")

# ---- C5 名单上的人不许被自动声明 ----
_w = pathlib.Path(tempfile.mkdtemp()) / "watch.json"
WL.save(WL.build(_rows), _w)
check("C5a", WL.is_watched("x:ok", _w), "★名单查询可用✗★")
_keep, _drop = ET.pick_semantic(
    [("x:ok", "full", None, "★★决策级✗★★ ★标签自相冲突 ✗ 必须先解决★")], cap=10)
check("C5b", not _keep,
      "★冲突行**不许**被自动声明（★`pick_semantic` 本来就不收 ✓ 这里联动验一次✓★）✗★")

print("=> watchlist %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
