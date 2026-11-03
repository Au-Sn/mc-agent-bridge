#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_snapshot.py -- 把导出落成**版本化快照**进库（§79.224 用户裁决 B1 第 ① 招）

为什么有它：
  导出是阶段 3/4 **全部数字**的唯一输入，却（i）被 .gitignore 排除（ii）只能在游戏里生成
  （iii）2026-10-13 实测**不在盘上**了 ⇒ 那批数字在这棵树上复现不出来。
口径：
  · 快照路径 state/export_snapshots/<mod_version>__<schema>__<YYYY-MM-DD>.json
  · 快照**带出处**：mod_version ＋ schema ＋ 生成时间 ＋ 字节数 ＋ sha256 前 12 位
  · find_export 的候选顺序里插在"仓库 logs"**之前**（快照是**特意存下来的**，比临时文件可信）
  · 内容没变就不写新文件（D4 的口径）
用法：
  py tools\\kb_snapshot.py save [--from 路径]   把当前导出存成快照
  py tools\\kb_snapshot.py list                 列出所有快照
  py tools\\kb_snapshot.py newest               打印最新快照路径（没有就空）
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DIR = ROOT / "state" / "export_snapshots"


def newest():
    if not DIR.is_dir():
        return None
    # ★★2026-10-18（★复核 P2-12c ✗ §79.279✗★）✗★★：★`manifest.json` **不是快照** ✗
    #   它是**目录**✗★ ⇒ ★原来 `sorted(glob('*.json'))[-1]` 会把它当成"★最新快照★"✗★ ✓
    fs = sorted(p for p in DIR.glob("*.json") if p.name != "manifest.json")
    return fs[-1] if fs else None


def save(src: pathlib.Path = None) -> pathlib.Path:
    import kb_export as KX
    src = pathlib.Path(src) if src else KX.find_export("")
    if not src.is_file():
        import export_guard as EG
        raise EG.MissingExport(EG.SENTENCE)
    blob = src.read_text(encoding="utf-8", errors="replace")
    d = json.loads(blob)
    mv = str(d.get("mod_version") or "unknown")
    sc = str(d.get("schema") or "unknown").replace("/", "_")
    name = "%s__%s__%s.json" % (mv, sc, datetime.now().strftime("%Y-%m-%d"))
    DIR.mkdir(parents=True, exist_ok=True)
    dst = DIR / name
    if dst.is_file() and dst.read_text(encoding="utf-8", errors="replace") == blob:
        print("★内容没变 ⇒ 不写★（D4 口径）：%s" % dst.name)
        return dst
    dst.write_text(blob, encoding="utf-8")
    man = DIR / "manifest.json"
    rows = []
    if man.is_file():
        try:
            rows = json.loads(man.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    rows = [r for r in rows if r.get("file") != name]
    rows.append({"file": name, "mod_version": mv, "schema": d.get("schema"),
                 "count": d.get("count"), "bytes": len(blob.encode("utf-8")),
                 "sha256_12": hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12],
                 "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    man.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("★快照已存✗★：%s（%d 个方块 ✗ %d 字节）" % (dst.name, d.get("count") or -1,
                                                len(blob.encode("utf-8"))))
    return dst


def main(argv):
    if not argv or argv[0] == "list":
        if not DIR.is_dir():
            print("（还没有快照目录）")
            return 0
        for f in sorted(DIR.glob("*.json")):
            print("  %-56s %8d KB" % (f.name, f.stat().st_size // 1024))
        return 0
    if argv[0] == "newest":
        n = newest()
        print(n if n else "")
        return 0
    if argv[0] == "save":
        src = None
        if "--from" in argv:
            i = argv.index("--from")
            src = argv[i + 1] if len(argv) > i + 1 else None
        try:
            save(pathlib.Path(src) if src else None)
        except Exception as e:
            print("★存不了✗★：%s" % e)
            # ★★2026-10-18（★复核 P2-12d ✗ §79.279✗★）✗★★：★本项目三分类✗★：
            #   ★0 ＝ 做完 ✗ 1 ＝ 坏 ✗ **4 ＝ 有东西没拿到**✗★ ⇒ ★缺输入是 4 ✗ 不是 2✗★ ✓
            return 4
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
