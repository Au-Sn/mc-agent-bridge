#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docwrite.py -- 生成物写盘：内容没变就不写（§79.238 用户裁决 D4）

用户原话：生成物内容没变就不写（先哈希比对），免得每次跑闸门都脏工作区、
并让 generated_docs_test 的对比失真。
★为什么要有它（而不是各写各的）✗★：这句话只许有**一份**定义 ——
不然就是又一次「两个工具各算一套」（§79.188 那一族）。
★而"哈希比对"要真管用 ✗ 还得**内容本身稳定**✗★：
如果文档里写了「生成时间 %H:%M:%S」⇒ 每秒都变 ⇒ 比对永远不相等 ⇒
★那句时间戳**才是**脏工作区的真因✗★（本次就抓到了这个）。
口径：
  · 返回 True ＝ 真的写了；False ＝ 内容一样 ⇒ 一个字节都没动（连 mtime 都不变）
  · 只有**内容**一样才跳过；mtime 一样但内容不同 ⇒ 照写
"""
from __future__ import annotations

import hashlib
import pathlib


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_if_changed(path, text: str) -> bool:
    p = pathlib.Path(path)
    old = None
    if p.is_file():
        try:
            old = p.read_text(encoding="utf-8")
        except Exception:
            old = None
    if old is not None and _sha(old) == _sha(text):
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return True
