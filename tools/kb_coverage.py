#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_coverage.py -- EXACT coverage denominator from the game's own block registry (debt ㊲ ①)

WHY: the coverage numbers (93% any tag / 81% family tag) were computed over a union of
three offline proxies (25719 names), not over the game's real block registry. With mod
2.44.0 there is `/dshkbexport [page]`, a read-only dump of BuiltInRegistries.BLOCK. That
gives the exact denominator, so the percentage stops being an estimate.

WHAT IT REPORTS
  * registry total  (exact N from /dshkbexport)
  * how many registry blocks have a physical verdict in the exported collision data
  * how many have a semantic/classification entry reachable from tools/blockkb.py
  * the gap lists (so the next batch of work is data-driven, not guessed)

USAGE
  py tools/kb_coverage.py            # live: asks the game (needs gateway + bot)
  py tools/kb_coverage.py --offline  # uses only files on disk (no game)
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PER = 700


def registry_ids(offline: bool):
    """All block ids from the game registry (`/dshkbexport`), or None when offline."""
    if offline:
        return None
    try:
        import mcp_core as C
    except Exception as e:
        print("  (cannot import mcp_core: %r)" % (e,))
        return None
    ids, total, page, npages = [], None, 1, 1
    while page <= npages and page <= 40:
        out = (C.dsh("dshkbexport %d" % page, 40.0) or "").strip()
        m = re.search(r"total=(\d+) page=(\d+)/(\d+) ids=(\S+)", out)
        if not m:
            print("  ★dshkbexport 回执看不懂✗★:", repr(out[:160]))
            return None
        total = int(m.group(1))
        npages = int(m.group(3))
        ids.extend(x for x in m.group(4).split(",") if x)
        page += 1
    print("  registry total=%s ｜ collected=%d ｜ pages=%d" % (total, len(ids), npages))
    return set(ids)


def export_ids():
    """Block names that have a physical verdict in the exported collision data."""
    # ★真导出在 state/export_snapshots/（★3.5MB ✗ 24779 个方块✗★）✗ 不是 logs 那个 710B 的测试件 ✓
    cand = sorted((ROOT / "state" / "export_snapshots").glob("*.json"), reverse=True)[:3]
    cand += [ROOT / "logs" / "block_shapes.json", ROOT / "tmp" / "block_shapes.json"]
    cand += list((ROOT / "logs").glob("*shapes*.json"))
    for p in cand:
        if not p.is_file():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        keys = set()
        if isinstance(d, dict):
            # 可能是 {name: entry} 或 {name: [..]}
            keys = set(k for k in d.keys() if isinstance(k, str) and ":" in k)
            if not keys:
                for v in d.values():
                    if isinstance(v, dict):
                        keys |= set(k for k in v.keys() if isinstance(k, str) and ":" in k)
        elif isinstance(d, list):
            for it in d:
                if isinstance(it, str) and ":" in it:
                    keys.add(it)
                elif isinstance(it, dict):
                    for f in ("name", "id", "block", "species"):
                        v = it.get(f)
                        if isinstance(v, str) and ":" in v:
                            keys.add(v)
                            break
        if keys:
            print("  物理导出: %s ⇒ %d 个方块" % (p.name, len(keys)))
            return keys
    print("  ★找不到物理导出（block_shapes.json）✗★")
    return set()


def semantic_ids():
    """★语义覆盖的来源✗★ = state/tags_category.json 的 categories（★21k 条 ✗ 每条带 cat/tag/all✓★）

    ★原来我去枚举 lockkb 的字典 ✗ 那是**运行期 put/get** ✗ 没有可枚举的容器 ✗ 所以永远是 0 ✓
    """
    import json as _json
    p = ROOT / "state" / "tags_category.json"
    if not p.is_file():
        print("  ★找不到 state/tags_category.json✗★")
        return set(), set()
    d = _json.loads(p.read_text(encoding="utf-8", errors="replace"))
    cats = d.get("categories") if isinstance(d, dict) else None
    if not isinstance(cats, dict):
        print("  ★tags_category 形状变了✗★")
        return set(), set()
    fam_kw = ("叶子", "原木", "木板", "半砖", "楼梯", "栅栏", "墙", "门", "活板门",
              "牌子", "地毯", "羊毛", "玻璃", "玻璃板", "栅栏门", "按钮", "压力板",
              "花", "树苗", "庄稼", "能爬", "可替换")
    any_tag, fam_tag = set(), set()
    for name, v in cats.items():
        if not isinstance(name, str) or ":" not in name:
            continue
        alls = (v or {}).get("all") or []
        if alls:
            any_tag.add(name)
        if any(a in fam_kw for a in alls):
            fam_tag.add(name)
    print("  语义侧: 有任意标签 %d 个 ｜ 有家族标签 %d 个" % (len(any_tag), len(fam_tag)))
    return any_tag, fam_tag

def main(argv) -> int:
    offline = "--offline" in argv
    reg = registry_ids(offline)
    phys = export_ids()
    sem_any, sem_fam = semantic_ids()

    print()
    if reg:
        print("== 精确覆盖率（真的分母）==")
        print("  注册表方块总数        : %d" % len(reg))
        p = reg & phys
        print("  其中**有物理结论**    : %d  （%.1f%%）" % (len(p), 100.0 * len(p) / max(1, len(reg))))
        sa, sf = reg & sem_any, reg & sem_fam
        print("  其中**有任意标签**    : %d  （%.1f%%）" % (len(sa), 100.0 * len(sa) / max(1, len(reg))))
        print("  其中**有家族标签**    : %d  （%.1f%%）" % (len(sf), 100.0 * len(sf) / max(1, len(reg))))
        gap = sorted(reg - phys)
        print("  ★没有物理结论的缺口✗★ : %d 个（前 10：%s）" % (len(gap), ", ".join(gap[:10])))
        if len(gap) > 10:
            out = ROOT / "logs" / "kb_coverage_gap.txt"
            out.write_text("\n".join(gap) + "\n", encoding="utf-8")
            print("  完整缺口清单 ⇒ %s" % out.relative_to(ROOT))
    else:
        print("== 离线模式：只有文件数据 ==")
        print("  物理导出: %d ｜ 有任意标签: %d ｜ 有家族标签: %d" % (len(phys), len(sem_any), len(sem_fam)))
        if phys and sem:
            print("  物理 ∩ 任意标签: %d ｜ 物理 ∩ 家族: %d" % (len(phys & sem_any), len(phys & sem_fam)))
    print()
    print("KBCOV ok=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
