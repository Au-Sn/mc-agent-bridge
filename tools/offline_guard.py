#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""offline_guard.py -- ★"★没有世界★"的统一约定✗★（2026-10-05 ✗ §79.179）

★闸门**既有**的三种结论（★不是我这轮发明的✓★）✗★：
  ★`=> PASS`✗ ★`=> FAIL`✗ ★`INCONCLUSIVE` ＋ 非零退出（★"★测不了★" ✗
  ★不是通过 ✗ 也不是坏 ✗ 换个位置／条件再测✓★）✗★ ✓
★为什么需要它✗★：★有些测试被登记成"★离线★" ✗ 其实**要世界**（★真格子上的瞄准／放置✓★）✗★
★游戏一关它们**红** ✗ 而那条红会被**误读**成"★谁改坏了东西★"✗★ ✓
★用法（★三行✗★）✗★：`import offline_guard as OG` ⇒ `OG.require_world("手势")`✗★ ✓
"""
from __future__ import annotations

import re
import sys

# ★★pin 住 stdout✗★★（★§79.180 ✗ `stdio_guard_test` 的 S3 抓到的：
#   ★本模块会印 `✓`／`✗` ✗ 不 pin 就会在别的编码下炸✓★）✗★
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def world_up(timeout: float = 3.0) -> bool:
    """★世界在不在✗★ —— 用**最便宜**的一问 ✗ **失败不抛**（★只是 `False`✓★）✗★ ✓

    ★★2026-10-05 修紧（§79.180✗★）✗★★：★原来写的是 `return bool(st)`✗★ ⇒
      ★而"★没有回执 ✗ 模组在不在？★"这种**错误提示**也是**非空字符串**✗★ ⇒
      ★★于是它把"★没有世界★"判成"★有世界★" ✗ 那条保护**永远不触发**✗★★ ✓
    ★⇒ 现在要求**正记号**✗★：★回执里**必须**有 `pos=`（★`t_bot_state` 的真格式✓★）✗★ ✓
      ★或 `dshver` 能报出模组版本（★备选 ✓ 但只认一种就够 ✗ 少一层耦合✓★）✗★ ✓
    """
    try:
        import mcp_percept as P
        st, _bad = P.t_bot_state()
        if st and re.search(r"pos\s*=", str(st)):
            return True
    except Exception:
        pass
    return False


def require_world(tag: str, code: int = 3):
    """★没有世界 ⇒ 按闸门既有约定报"★测不了★"并退出✗★ ✓"""
    if world_up():
        return True
    print("=> INCONCLUSIVE: %s 要世界（★游戏关着／链接不通✗★）"
          " —— ★不是通过（★不是通过 ✗ 也不是坏 ✗ 开游戏再测✓★）" % tag)
    sys.exit(code)
