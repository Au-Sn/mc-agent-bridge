#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""structures_test.py -- 模块 K 第 1 级（结构检索）的判据（★离线 ✗ 读真包✗★）

用户口径（§10.2）：「产线蓝图**应该是可以搜索的**」
⇒ 本判据证明：★真的能在包里**找到**结构 ✗ 真的能**读成坐标表** ✗ 而且**方块名都在注册表里**★

CHECKS
  S1 find() 能检索到结构（>100 个）
  S2 read() 读一个**真实**结构：size/palette/blocks 都非空
  S3 palette 里都是**带命名空间**的方块 id
  S4 ★属性也读到了★（farmland 的 moisture 之类）
  S5 to_cells() 输出**现有蓝图 `cells` 格式**（dx/dy/dz/block）
  S6 ★蓝图里每个方块 id 都在**注册表**里★（★用导出快照核对 ✗ 防"凭空方块"✗★）
  S7 读不存在的结构 ⇒ **明确报错**（不返回空壳）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import structures as S          # noqa: E402

JAR = "create-1.20.1-6.0.4.jar"
PATH = "data/create/structures/gametest/contraptions/crop_farming.nbt"


def _registry_ids():
    snap = ROOT / "state" / "export_snapshots"
    for p in sorted(snap.glob("*.json")):
        if p.name == "manifest.json":
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            b = d.get("blocks") if isinstance(d, dict) else None
            if isinstance(b, dict) and len(b) > 10000:
                return set(b.keys())
        except Exception as exc:      # ★不许静默✗★
            print("structures_test: 读 %s 失败 %r" % (p.name, exc), file=sys.stderr)
    return set()


def main() -> int:
    checks = []

    rows = S.find("", limit=400)
    checks.append(("S1 find() 能检索到结构（>100）", len(rows) > 100, "%d 条" % len(rows)))

    bp = S.read(JAR, PATH)
    checks.append(("S2 read() 真实结构：size/palette/blocks 非空",
                   all(bp.get(k) for k in ("size", "palette", "blocks")),
                   "size=%s palette=%d blocks=%d"
                   % (bp["size"], len(bp["palette"]), len(bp["blocks"]))))

    bad3 = [e["id"] for e in bp["palette"] if ":" not in (e["id"] or "")]
    checks.append(("S3 palette 全是带命名空间的 id", not bad3, str(bad3[:3])))

    props = [e for e in bp["palette"] if e.get("props")]
    checks.append(("S4 ★属性也读到了★", bool(props),
                   "%d/%d 有属性 ｜ 例：%s"
                   % (len(props), len(bp["palette"]),
                      (props[0]["id"] + str(props[0]["props"])[:30]) if props else "-")))

    cells = S.to_cells(bp)
    ok5 = bool(cells) and all({"dx", "dy", "dz", "block"} <= set(c) for c in cells[:5])
    checks.append(("S5 to_cells() 输出蓝图 cells 格式", ok5,
                   "%d 格 ｜ 例：%s" % (len(cells), str(cells[0])[:60] if cells else "-")))

    reg = _registry_ids()
    miss = sorted(i for i in S.ids(bp) if reg and i not in reg and ":" in i)
    checks.append(("S6 ★蓝图方块都在注册表里★",
                   bool(reg) and not miss,
                   "注册表 %d 个 ｜ 缺 %s" % (len(reg), miss[:4])))

    try:
        S.read(JAR, "data/does/not/exist.nbt")
        ok7 = False
    except Exception:
        ok7 = True
    checks.append(("S7 读不存在的结构 ⇒ 明确报错", ok7, "KeyError" if ok7 else "没报错"))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:115]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => structures FAIL (%d)" % bad)
        print("STRUCTURES ok=0 bad=%d" % bad)
        return 1
    print("  => structures PASS (real pack structures readable, ids match the registry)")
    print("STRUCTURES ok=1 checks=%d found=%d" % (len(checks), len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
