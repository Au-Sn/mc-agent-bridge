#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_tables_test.py -- 闸门四张表的关系一条都不许没声明（G1~G6 离线 2026-10-13 §79.237）

用户裁决 B3：闸门四张表生成化（一张源表＋标签派生四张，包含关系由生成保证）。
这一步先做「可查的那半」（全量生成是下一步，但那一步要先有个安全网）：
  · 该成立的关系 ⇒ 判据守着
  · 不成立的关系 ⇒ 必须声明 ＋ 写理由（与 NOT_SHAPE_FAMILY 同一个模式）
为什么「不成立」也能是正常的：四张表量的不是同一件事 ——
  QUICK＝快而低风险／WALK＝要走路／OFFLINE＝不要游戏／FAST＝几秒钟
  ⇒「QUICK ⊆ OFFLINE」从一开始就不该成立（QUICK 里本来就有一批要游戏的）
项数由脚本产出：本判据顺手把 docs/闸门-项数.md 生成出来（内容没变就不写，D4 口径）。
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import check_all as CA

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


TAB = {"QUICK": CA.QUICK, "WALK": CA.WALK, "OFFLINE": CA.OFFLINE, "FAST": CA.FAST}
S = {k: [x[0] for x in v] for k, v in TAB.items()}

# ---- 必须成立的四条
check("G1", all(len(n) == len(set(n)) for n in S.values()),
      "每张表内部不许重名 ⇒ %s" % {k: len(v) - len(set(v)) for k, v in S.items()})
miss = {k: [n for n in v if not (ROOT / "tools" / n).is_file()] for k, v in S.items()}
# ★★2026-10-13（★§79.256✗★）✗★★：★`GATE` 每行必须是**三元组**✗★ ——
#   ★我插 `world_touch_test.py` 时**漏了标签** ⇒ `for s, d, t in GATE` 解包失败 ⇒
#     ★闸门**整个崩掉**（★连 SUMMARY 都没有✗★）✗★ ⇒ ★加这条 ✗ 让"★漏标签★"当场红✗★ ✓
_arity = sorted({len(x) for x in CA.GATE}) if hasattr(CA, "GATE") else []
check("G1b", _arity == [3] or not _arity,
      "`GATE` 每行必须是（★脚本 ✗ 说明 ✗ 标签✗★）三元组 ⇒ 实测元数集合 %s" % (_arity,))
check("G2", not any(miss.values()),
      "表里点的脚本都得在盘上 ⇒ %s" % ({k: v for k, v in miss.items() if v} or "全在 ✓"))
check("G3", not (set(S["FAST"]) - set(S["QUICK"])),
      "FAST ⊆ QUICK（快到能进 FAST 的必然也在 QUICK）⇒ 只在 FAST 里的 %d 个"
      % len(set(S["FAST"]) - set(S["QUICK"])))
check("G4", not (set(S["OFFLINE"]) & set(S["WALK"])),
      "OFFLINE ∩ WALK ＝ 空集（要游戏与要走路不该同时算）⇒ 两边都在的 %d 个"
      % len(set(S["OFFLINE"]) & set(S["WALK"])))

# ---- 不成立的必须声明 ＋ 写理由
# ★★2026-10-13（★审计缺陷①的后果 ✗ §79.252✗★）✗★★：★12 个有序对里**全部**
#   不成立的都写上理由✗★ —— ★原来是 3 个键 ✗ 而 `for` 也只遍历那 3 对 ⇒ G5 恒绿✗★ ✓
#   ★现在 `for` 遍历 12 对 ✗ 缺一个理由就红✗★ ✓
DECLARED = {
    ("FAST", "OFFLINE"): "两张表量的不是同一件事",
    ("FAST", "WALK"): "FAST 是「几秒钟」✗ WALK 要走路 ⇒ 慢",
    ("OFFLINE", "FAST"): "OFFLINE 不含那 4 个要游戏的 ✗ 而 FAST 只管「几秒钟」✗ 与离不离线无关",
    ("OFFLINE", "WALK"): "OFFLINE 是「不要游戏」✗ WALK 是「要走路」⇒ 两者互斥（★交集为空✓★）",
    ("QUICK", "FAST"): "QUICK 比 FAST 宽（★FAST 是它的子集 ✗ 反过来不成立是设计✓★）",
    ("QUICK", "OFFLINE"): "两张表量的不是同一件事",
    ("QUICK", "WALK"): "QUICK 是「快而低风险」✗ WALK 是「要走路」⇒ 两张表量的不是同一件事",
    ("WALK", "FAST"): "两张表量的不是同一件事",
    ("WALK", "OFFLINE"): "WALK 要走路 ⇒ 必然要游戏 ✗ 与 OFFLINE 互斥",
    ("WALK", "QUICK"): "WALK 三条要走路 ✗ 慢 ⇒ 不进 QUICK 那一档",
}
# ★★2026-10-13 修（★审计缺陷① ✗ §79.252✗★）✗★★：★原来这一条**不可能失败**✗★ ——
#   ★它 `for` 遍历的三对 ✗ **就是** `DECLARED` 的三个键 ✗★ ⇒
#   ★`(a, b) not in DECLARED` **恒假** ✗ 于是 `bad` 恒空 ✗ 判词却写着
#   "★四张表的关系一条都不许没声明★"（★审计用 AST 取证 ✗ 并造出「QUICK ⊄ FAST」
#   未声明关系 ⇒ 它照样绿 ✗ 而同一次 G3 红了✗★）✗★ ✓
#   ★⇒ 口径✗★：★遍历**全部 12 个有序对**✗ 每对**要么关系成立** ✗
#     **要么在 `DECLARED` 里写了理由**✗ 并**报出对数**（★计数器✗★）✗★ ✓
_bad, _pairs = [], 0
for _a in ("QUICK", "WALK", "OFFLINE", "FAST"):
    for _b in ("QUICK", "WALK", "OFFLINE", "FAST"):
        if _a == _b:
            continue
        _pairs += 1
        _only = sorted(set(S[_a]) - set(S[_b]))
        if _only and (_a, _b) not in DECLARED:
            _bad.append((_a, _b, len(_only)))
# ★★2026-10-18（★复核 P2-9 ✗ §79.274✗★）✗★★：★G5 原来只查「有没有声明」✗
#   **不查声明里的数**✗★ ⇒ ★于是「★实测 69 个只在 FAST 里★」这种话
#     **漂了也没人管**✗★ ⇒ ★复核实测：文档/判词里 69／76／98 ✗ 现算 72／79／101✗★ ✓
#   ★口径✗★：★声明里写了数 ⇒ 那个数**必须等于现算**✗★ ✓
import re as _re2
# ★★2026-10-18（★§79.282✗★）✗★★：★上面的数**一加判据就漂**✗★（★我加一条新判据 ✗
#   72／79／101 就变 73／80／102 ✗ 判据当场红✗★）⇒ ★★口径反过来✗★★：
#   ★**理由里不许写死数** ✗ 真数由 G5 **每次现算打印**✓★（★写死了就一定会漂 ✗ 然后就得手改✗★）✗★ ✓
_why_with_num = [(a, b, m.group(0)) for (a, b), _w in DECLARED.items()
                 for m in _re2.finditer(r"实测\s*\d+\s*个", _w)]
check("G5c", not _why_with_num,
      "★理由里**不许写死数**✗（★会漂 ✗ 真数看 G5 每次现算的那行✓★）⇒ 还在：%s"
      % (_why_with_num or "（没有 ✓）"))
_num_bad = []
for (_a2, _b2), _why2 in DECLARED.items():
    _m2 = _re2.search(r"实测\s*(\d+)\s*个", _why2)
    if not _m2:
        continue
    _act2 = len(set(S[_a2]) - set(S[_b2]))
    if int(_m2.group(1)) != _act2:
        _num_bad.append((_a2, _b2, int(_m2.group(1)), _act2))
check("G5b", not _num_bad,
      "★声明里的数必须**等于现算**✗★ ⇒ 漂了的（对 ✗ 写的 ✗ 现算）：%s"
      % (_num_bad or "（没有 ✓）"))
check("G5", (not _bad) and _pairs == 12,
      "★12 个有序对逐对看★（★%d 对✗★）：关系不成立又**没声明**的：%s"
      % (_pairs, _bad or "（没有 ✓）"))
for (a, b), why in DECLARED.items():
    only = sorted(set(S[a]) - set(S[b]))
    print("      声明过：%-6s ⊄ %-8s（%2d 个）—— %s" % (a, b, len(only), why[:56]))

# ---- 项数由脚本产出（D4：内容没变就不写）
NOTES = {
    "QUICK": "快而低风险（它里面有要游戏的，所以它不是离线表）",
    "WALK": "要走路（慢，所以不在 FAST 里）",
    "OFFLINE": "不要游戏（闸门发货前那一关）",
    "FAST": "几秒钟（快，与离不离线无关）",
}
lines = ["# 闸门四张表 ✗ 项数（由 tools/gate_tables_test.py 生成，别手改）", "",
         "这四张表量的不是同一件事：", ""]
for k in ("QUICK", "WALK", "OFFLINE", "FAST"):
    lines.append("* `%s`：**%d** 项 —— %s" % (k, len(S[k]), NOTES[k]))
lines += ["", "去重后共 **%d** 个不同脚本" % len(set(sum(S.values(), []))), "",
          "不成立的关系（已声明）："]
for (a, b), why in DECLARED.items():
    lines.append("* `%s ⊄ %s`：%s" % (a, b, why))
lines.append("")
blob = chr(10).join(lines)
P = ROOT / "docs" / "闸门-项数.md"
# ★★2026-10-13（★审计实验 GT-G6-unwritable 抓的✗★）✗★★：★写不动时要**红 ＋ 说人话**✗★ ——
#   ★那次实验把文档目录弄成只读 ✗ 于是本判据**直接抛异常**✗★ ⇒
#   ★报告里它显示"★G6＝缺行✗★"（★脚本在跑到它之前就崩了 ✗ 连"★红★"都算不上✗★）✗★ ✓
#   ★⇒ 口径（★与"★不许静默吞 ✗ 但要说人话★"同族✗★）✗★：
#     ★写不进去 ⇒ `G6` **红** ✗ 并把"★为什么写不进去★"打出来✗★ ✓
_g6_err = ""
try:
    old = P.read_text(encoding="utf-8") if P.is_file() else ""
    if hashlib.sha256(old.encode("utf-8")).hexdigest() != hashlib.sha256(blob.encode("utf-8")).hexdigest():
        P.write_text(blob, encoding="utf-8")
        print("      项数文档已重写（内容变了）")
    else:
        print("      项数文档没变 ⇒ 不写（D4 口径）")
except Exception as _e:
    _g6_err = "%s: %s" % (type(_e).__name__, str(_e)[:80])
check("G6", P.is_file() and not _g6_err,
      "项数文档在：%s（%d 字节）✗ ★写不进去要说清★：%s"
      % (P.name, (P.stat().st_size if P.is_file() else 0), _g6_err or "（能写 ✓）"))

print("=> gate_tables %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
