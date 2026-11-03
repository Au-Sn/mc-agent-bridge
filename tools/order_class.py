#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/order_class.py -- 按 B 重定"顺序类"并算**新基线**（§79.335 ✗ 用户 2026-10-24 选 B ✗ 工具化）

★用户选 B✗★：★"★按 B 继续★" ⇒ ★**作废 1260 ✗ 按碰撞优先原则重新定义 ✗ 新基线由新定义算出**✗★ ✓

★★新定义（★比 1260 那版更硬 ✗ 因为要两条都成立✗★）✗★★：
  ★★"★顺序类候选★" ＝ 一个方块 ✗
    ★① **名字**同时命中 **≥2 个族关键词组**（★⇒ 它的名字结论**依赖先查哪条**✗★）✗★
    ★② **名字判出来的形状 ≠ 导出碰撞族判出来的形状**（★⇒ 名字**确实错了**✗★）✗★★ ✓
★⇒ ★这是"★顺序错了就**真的会错**★"的那批 ✗ 不是"★只是多匹配 ✗ 碰巧都对★"✗★ ✓
★判据仍是✗★：★**该集合的基数必须 0**✗★ ⇒ ★但**先不加**（★你的原话✗★）✗ 今天只**报基线**✗★ ✓
★口径✗★：★**碰撞优先** ⇒ 名字结论只用 `mapread.shape`（★纯名字那一份 ✗ 不是查表那一份✗★）✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mapread as MR
import kb_export as KX

# ★族关键词组（★与 §79.332 的 ⑥ 同一套 ✗ 从 45 个族里挑**名字能看出来**的那些✗★）
KW = {
    "半砖": ["_slab"], "楼梯": ["stairs", "_step"], "栅栏": ["fence"], "墙": ["wall"],
    "门": ["_door"], "活板门": ["trapdoor"], "按钮": ["button"], "压力板": ["pressure_plate"],
    "地毯": ["carpet"], "叶子": ["leaves", "_leaf"], "原木": ["_log", "log_"], "木板": ["planks"],
    "花盆": ["flower_pot"], "珊瑚": ["coral"], "铁轨": ["rail"], "蜡烛": ["candle"],
    "箱子类": ["chest", "barrel"], "牌子": ["sign"], "旗": ["banner"],
}
# ★导出碰撞族 ⇒ mapread 的名字形状词汇✗★（★碰撞优先：以碰撞为准 ✗ 名字要跟上它✗★）
FAM2SHAPE = {"full": "full", "slab": "slab", "fence_15": "fence", "snow_layer": "snow_layer",
             "none": "none", "liquid": "liquid", "other": "other"}


def main() -> int:
    blocks = json.loads(pathlib.Path(KX.find_export("")).read_text(encoding="utf-8")).get("blocks") or {}
    print("== order_class_b：★新定义 ⇒ 新基线✗★ ==")
    print("   导出 %d 块 ｜ 关键词组 %d 个" % (len(blocks), len(KW)))

    multi = []
    for sp in sorted(blocks):
        nm = sp.split(":", 1)[-1].lower()
        hits = [f for f, kws in KW.items() if any(k in nm for k in kws)]
        if len(hits) >= 2:
            multi.append((sp, hits))
    print("   ① 名字命中最 ≥2 个族关键词组 ⇒ **%d** 块" % len(multi))

    cand, samples = [], []
    for sp, hits in multi:
        nm = sp.split(":", 1)[-1]
        try:
            name_shape = MR.shape(sp)          # ★纯名字形状（★不是查表那一份✗★）
        except Exception:
            name_shape = "?"
        coll = (blocks[sp] or {}).get("family") or "?"
        coll_shape = FAM2SHAPE.get(coll, coll)
        if name_shape != coll_shape and name_shape != "?" and coll_shape != "?":
            cand.append((sp, hits, name_shape, coll_shape))
            if len(samples) < 12:
                samples.append((sp, hits, name_shape, coll_shape))
    print("   ② 其中**名字形状 ≠ 碰撞形状** ⇒ ★★**%d** 块**✗★ ⇒ ★这就是**新基线**✗★"
          % len(cand))
    print("   比例：%d / %d ＝ %.2f%%" % (len(cand), len(blocks),
                                         100.0 * len(cand) / max(1, len(blocks))))
    print("")
    print("   样例（★名字多匹配 ＋ 名字说错✗★）✗★：")
    for sp, hits, ns, cs in samples:
        print("     %-46s 命中 %-16s 名字说 %-10s 碰撞说 %s"
              % (sp[:46], "／".join(hits)[:16], ns, cs))
    out = {
        "schema": "order_class@2",
        "decided_by": "用户 2026-10-24 选 B：作废 1260，按碰撞优先原则重新定义顺序类，新基线由新定义算出",
        "definition": ("★顺序类候选★ ＝ 一个方块 ✗ ① 名字同时命中 ≥2 个族关键词组（顺序敏感）✗ "
                       "② 名字判出来的形状 ≠ 导出碰撞族判出来的形状（名字确实错了）"),
        "criterion": "该集合的基数必须为 0（★先不加 ✗ 用户原话✗★）",
        "principle": "★碰撞优先✗★：名字形状只用 `mapread.shape`（纯名字）；碰撞族以导出为准",
        "baseline": {"count": len(cand), "total": len(blocks),
                     "ratio": round(len(cand) / max(1, len(blocks)), 4),
                     "multi_hit_blocks": len(multi)},
        "samples": [{"species": s, "hits": h, "name_shape": n, "collision_shape": c}
                    for s, h, n, c in samples],
        "⚠": "★这是**新定义**下的基线 ✗ 与用户 2026-10-18 给的 1260 **不是同一件事**（那个数已作废）✗★",
    }
    (ROOT / "state" / "order_class.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("")
    print("   ★已写 state/order_class.json ✗ 新基线 ＝ **%d**✗★" % len(cand))
    print("ORDERCLASS_B baseline=%d multi=%d total=%d" % (len(cand), len(multi), len(blocks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
