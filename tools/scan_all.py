#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_all.py -- ★把 `dshscan` 扫**全**★（§79.345 ✗ 2026-10-24）

★★今天实测清楚的一件旧误会✗★★（★E3 那条"★`dshscan` 只回 40 格★"✗★）✗★：
  · ★`dshscan` 的**真语法是位置参数**✗★：`dshscan x0 y0 z0 x1 y1 z1 ["match"] [limit] [page]`✗★
    （★`box=…` 那种写法会回中文错 ✗ 过通道变 `????`✗★）✗★ ✓
  · ★**默认 limit ＝ 64** ✗ 而且它**分页**（★`shown=64 page=1/2`✗★）✗★ ✓
  · ★传大 `limit` ⇒ **全给**（★`shown=122 page=1/1`✗★）✗ 而且 `counts[…]` **本来就没截断**
    （★整行 5096 字 ✗ 结尾是完整的方块状态✗★）✗★ ✓
★★⇒ ★★"★只回 40 格★"**不是**模组限制 ✗ 是**调用方没传 limit**✗★★ ⇒ ★本工具：★传大 limit ＋
  ★按 `page=1/N` **翻页** ✗ 把所有格拼起来✗★ ✓
★（★唯一**仍需改模组**的是"★逐格列三种 air★" ✗ 因为 `counts` 里**没有** `minecraft:air`✗★）✗★ ✓
"""
from __future__ import annotations

import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def scan(x0, y0, z0, x1, y1, z1, match=":", limit=2000, max_pages=8, dsh=None):
    """★返回 (head, cells, pages) ✗ cells 是**所有页**拼起来的正文格✗★"""
    if dsh is None:
        sys.path.insert(0, "tools")
        import mcp_core as C
        dsh = C.dsh
    head, cells, page, npages = "", [], 1, 1
    while page <= min(npages, max_pages):
        cmd = 'dshscan %d %d %d %d %d %d "%s" %d %d' % (
            x0, y0, z0, x1, y1, z1, match, limit, page)
        txt = dsh(cmd, 60.0) or ""
        if not txt or "dshscan box=" not in txt:
            return head, cells, page - 1
        head = txt.splitlines()[0]
        m = re.search(r"page=(\d+)/(\d+)", head)
        if m:
            page, npages = int(m.group(1)), int(m.group(2))
        body = [l for l in txt.splitlines()[1:] if l.strip()]
        cells.extend(body)
        page += 1
    return head, cells, npages


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("box", help="x0 y0 z0 x1 y1 z1（★顺序与 dshscan 一致✗★）")
    ap.add_argument("--match", default=":")
    ap.add_argument("--limit", type=int, default=2000)   # ★模块上限就是 2000 ✗ 超了回中文错✗★
    a = ap.parse_args(argv)
    v = [int(s) for s in a.box.replace(",", " ").split()]
    if len(v) != 6:
        print("SCANALL ok=0 reason=bad_box")
        return 2
    head, cells, pages = scan(*v, match=a.match, limit=a.limit)
    print("  ★头✗★：%s" % head[:160])
    print("  ★共翻 %d 页 ✗ 格数 **%d**★" % (pages, len(cells)))
    for c in cells[:6]:
        print("    %s" % c[:130])
    print("SCANALL ok=%d cells=%d pages=%d" % (1 if cells else 0, len(cells), pages))
    return 0 if cells else 4


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
