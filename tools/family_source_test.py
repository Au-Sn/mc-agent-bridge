#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""family_source_test.py -- 五张家族表：**真源一条路**（F1~F5 离线 2026-10-13 §79.242）

用户裁决 A1：家族真源收敛到 GEOMETRIC_CATEGORY（唯一锚定碰撞的），
其余四张降级为生成物＋各配「该含什么」断言（扩 generated_docs_test，不新写）。
★量出来的真相不是"五张并列"✗★ —— ★是**三层 ＋ 两套词汇**✗★：
  ⑤ `FAMILY_PATTERNS`（标签名 ⇒ 类别，引导）
  ① 类别（语义）
  ② `GEOMETRIC_CATEGORY`（类别 ⇒ **导出族**）  ← ★**真源**✗★
  ③ `EXPORT_FAMILY`（导出族 ⇒ **判定族**，翻译层）
  ④ `TAG_FAMILY`（类别 ⇒ 判定族）  ← ★它**绕过真源** ✗ 这就是要收敛的那条✗★
★推导路✗★：★类别 ⇒ `GEOMETRIC_CATEGORY` ⇒ 导出族 ⇒ `EXPORT_FAMILY` ⇒ 判定族✗★
★F3 就是那条路的机械形态✗★ —— ★它**抓到了 3 条**（§79.242 现场✗★）✗★ ✓
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import blockkb as KB
import divergence as DV
import kb_export as KX
import tag_census as TC

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


# ★★角色声明（★不许有第二张自称真源的✗★）✗★★
ROLES = {
    "tag_census.FAMILY_PATTERNS": ("引导", "★标签名 ⇒ 类别（正则）✗ 它是**入口** ✗ 不是真源✗★"),
    "blockkb.GEOMETRIC_CATEGORY": ("真源", "★★类别 ⇒ 导出族 ✗ **唯一锚定碰撞**的（★用户裁决 A1✓★）✗★★"),
    "kb_export.FAMILIES": ("导出闭集", "★模组那边**导出**的族名闭集 ✗ 不是我们的判定族✗★"),
    "blockkb.EXPORT_FAMILY": ("翻译", "★导出族 ⇒ **判定族** ✗ 两套词汇之间的桥✗★"),
    "divergence.TAG_FAMILY": ("生成物（★待收敛✗★）",
                              "★类别 ⇒ 判定族 ✗ 现在**手写** ✗ 目标是**由真源推**✗★"),
}

print("== family_source: F1~F5 ==")
# ★★2026-10-13 修（★审计缺陷③ ✗ §79.252✗★）✗★★：★原来这一条**空转**✗★ ——
#   ★它判的对象是**它自己文件里的字面 `ROLES`** ✗ 与 `TC／KB／DV／KX` **零接触**✗★ ⇒
#   ★审计往 `tag_census.py` 加一张"★本表才是唯一真源★"的门面 ⇒ 它照样绿✗★ ✓
#   ★⇒ 现在改读**真东西**✗★：★`families.SYMBOLS`（★族登记处✗★）里**恰好一个** `sem`
#     符号被点名当真源 ✗ 而按那个名字 `getattr` **真拿到对象** ✗ 且它**非空**✗★ ✓
#   ★★本判据**不**做什么（★写清 ✗ 不许过度主张✗★）✗★★：★它**不扫**别的文件里
#     有没有人自称真源 ✗ ★那件事由 **F3**（★推导路必须一致✗★）兜✗★ ✓
import families as _FAM
_sem = [k for k, v in _FAM.SYMBOLS.items() if v[0] == "sem"]
_src = [k for k in _sem if "GEOMETRIC_CATEGORY" in k]
_obj = None
try:
    _obj = KB.GEOMETRIC_CATEGORY
except Exception:
    _obj = None
check("F1", (_src == ["blockkb.GEOMETRIC_CATEGORY"]) and bool(_obj),
      "★登记处里**恰好一个** `sem` 符号被点名当真源 ✗ 而且**真拿得到对象**✗★ ⇒ %s"
      "（★登记处共 %d 个符号 ✗ 其中 sem %d 个✗★；★本判据不扫别处的自称 ✗ 那由 F3 兜✗★）"
      % (_src, len(_FAM.SYMBOLS), len(_sem)))
for k, (role, why) in ROLES.items():
    print("       %-30s %-12s %s" % (k, role, why[:52]))

# ★★F2：五张表都在且非空✗★★
_missing = []
for name, obj in (("FAMILY_PATTERNS", TC.FAMILY_PATTERNS),
                  ("GEOMETRIC_CATEGORY", KB.GEOMETRIC_CATEGORY),
                  ("FAMILIES", KX.FAMILIES),
                  ("EXPORT_FAMILY", KB.EXPORT_FAMILY),
                  ("TAG_FAMILY", DV.TAG_FAMILY)):
    if not obj:
        _missing.append(name)
check("F2", not _missing, "五张表都在且非空 ⇒ 缺的：%s" % (_missing or "（没有 ✓）"))

# ★★F3：★推导路必须一致★（★这条抓到过 3 条✗★）✗★★
G, E, TF = KB.GEOMETRIC_CATEGORY, KB.EXPORT_FAMILY, DV.TAG_FAMILY
_both = sorted(set(G) & set(TF))
_bad = [(c, TF[c], E.get(G[c])) for c in _both if TF[c] != E.get(G[c])]
check("F3", not _bad,
      "★类别 ⇒ 真源 ⇒ 导出族 ⇒ 翻译 ⇒ 判定族★ 必须一致 ⇒ 两边都有的 **%d** 个类别里"
      "不一致的：%s" % (len(_both), _bad or "（没有 ✓）"))

# ★★F4：★真源还没覆盖的那些 ⇒ 必须声明 ＋ 替换触发✗★
NOT_YET = {
    "压力板", "叶子", "土", "墙", "庄稼", "按钮", "旗", "树苗", "楼梯", "沙",
    "牌子", "石基", "矿石", "箱子类", "能爬", "蜡烛", "铁轨", "门",
}
_only_t = set(TF) - set(G)
check("F4", _only_t <= NOT_YET,
      "★只在 `TAG_FAMILY` 里（★真源没覆盖✗★）的必须落在这张声明表里★"
      "（★替换触发：真源补到这些类别时 ⇒ 删掉这条声明 ✗ 改由真源推✓★）⇒ 没声明的：%s"
      % (sorted(_only_t - NOT_YET) or "（没有 ✓）"))

# ★★F5：翻译层的定义域 ✗ 与"两套词汇"都声明清楚✗★
check("F5", set(E) <= set(KX.FAMILIES),
      "`EXPORT_FAMILY` 的定义域 ⊆ 导出闭集（★%d ⊆ %d✓★）✗ 而判定族那一侧"
      "（★`fence`／`machine`／`pass`✓★）**不在**导出闭集里 —— ★那是两套词汇 ✗ 不是错✗★"
      % (len(E), len(KX.FAMILIES)))

print("=> family_source %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
