#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_guard.py -- 缺导出**硬红**，而且带一句人话（§79.224 用户裁决 B1）

为什么有它（用户裁决 B1 第 ② 招）：
  同一个"导出不在盘上"，仓库里有**两种**处置：
    · cut_verify_test 直接抛 FileNotFoundError ⇒ 记成 FAIL（裸 traceback）
    · kb_risk 报 INCONCLUSIVE ⇒ 看起来像"没法测"
  裁决：★缺输入 ≠ 测不了★ ⇒ 一律**硬红**，而且**必须**给一句人能读的话。
口径：
  · INCONCLUSIVE 留给"要世界／要游戏"（那是**没法测**）
  · 缺输入是**环境坏了** ⇒ 红 ✗ 而且要说清"缺什么、去哪弄、怎么补"
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

SENTENCE = ("★缺输入（硬红，不是测不了）★：导出不在盘上 ⇒ "
            "找过：`--export`／`$DSH_BLOCKKB`／`state/export_snapshots/`／`logs/blockkb.json`／"
            "PCL2 实例。怎么补：开游戏跑 `/dshkb` 重新生成，然后 `py tools\\kb_snapshot.py save` "
            "把它落成**版本化快照**（带 mod_version+schema）进库。")


class MissingExport(RuntimeError):
    """★导出不在盘上✗★ —— 硬红，不是"没法测" """


def require(tag: str = "") -> pathlib.Path:
    """★要导出 ✗ 没有就**红着报一句人话**✗★"""
    import kb_export as KX
    p = KX.find_export("")
    if not pathlib.Path(p).is_file():
        raise MissingExport(("【%s】" % tag if tag else "") + SENTENCE)
    return pathlib.Path(p)


def soft(tag: str = ""):
    """★有的调用方只想知道"在不在"✗ 不想红✗★ ⇒ 返回 (path|None, 理由)"""
    import kb_export as KX
    p = KX.find_export("")
    if not pathlib.Path(p).is_file():
        return None, ("【%s】" % tag if tag else "") + SENTENCE
    return pathlib.Path(p), ""
