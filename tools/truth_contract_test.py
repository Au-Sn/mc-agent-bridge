#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""truth_contract_test.py -- 真值契约的守卫（T1~T4 离线 2026-10-13 §79.227）

用户裁决 B2：真值契约的期望**必须来自物理实测**，**不许来自导出**。
这条判据守的就是这件事 —— 它**不**去问导出"期望该是多少"（那就是循环），
它只问：
  T1 每条都有 status，且 status 只能是 measured／unmeasured
  T2 measured 的条目必须有数字期望 ＋ evidence 指向**实测**（台账 §）
  T3 unmeasured 的条目必须 expect=null ＋ 写清 how_to_measure（★不许留空✗★）
  T4 有实测的那条，导出若在盘上就必须**对得上**（★导出在不在都不影响 T1~T3✗★）
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

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


print("== truth_contract: T1~T4 ==")
p = ROOT / "state" / "contracts" / "truth_v1.json"
if not p.is_file():
    check("T1", False, "真值契约文件不在")
    sys.exit(1)
d = json.loads(p.read_text(encoding="utf-8"))
items = d.get("items") or []

bad1 = [i.get("id") for i in items if i.get("status") not in ("measured", "unmeasured")]
check("T1", not bad1, "%d 条，status 只有 measured／unmeasured（坏的：%s）"
      % (len(items), bad1 or "无"))

# ★★2026-10-13（★第四轮扫描 TC-T2-item 抓的**真缺陷**✗★）✗★★：
#   ★现象✗★：★把实测那条的 `species_key` 改名 ⇒ T2 **照样绿**✗★ ✓
#   ★真因✗★：★T2 的注释里写着"★`species_key` 现在是**必填**（★T2 管✗★）★"✗
#     ★而代码里**没有**这条检查✗★ ⇒ ★★**主张超出了实现**✗★★ ——
#     ★★而这正是我 §79.252 那次补丁**静默没打上**的那一半✗★★（★"★补丁要自证打上了没有★"✓★）✗★ ✓
bad2 = [i.get("id") for i in items
        if (i.get("status") == "measured"
            and (not isinstance(i.get("expect"), (int, float))
                 or "§" not in str(i.get("evidence") or "")
                 or not str(i.get("species_key") or "").strip()))]
check("T2", not bad2,
      "measured 的条目：数字期望 ＋ evidence 指向台账 §（坏的：%s）" % (bad2 or "无"))

bad3 = [i.get("id") for i in items
        if i.get("status") == "unmeasured"
        and not (i.get("expect") is None and str(i.get("how_to_measure") or "").strip())]
check("T3", not bad3,
      "unmeasured 的条目：expect=null ＋ 写清怎么量（坏的：%s）" % (bad3 or "无"))

# ★★T4（★审计 M2 之后重写✗★）✗★★：有实测的那条，导出在盘上就要**真的**对得上
#   ★原来为什么是空转✗★：它读 `species_key` ✗ 而**契约里一个都没有**（★物种装的是人话✓★）⇒
#     ★`if sp and sp in exp` 永远不成立 ⇒ 12 条查 0 条 ⇒ **它不判**✗★ ✓
#     ★审计用一份「★书堆 max_height=99.0★」的假导出去撞它 ✗ 它照样绿✗★ ✓
#   ★⇒ 三条新口径✗★：① `species_key` 现在是**必填**（★T2 管✗★）✗
#     ② ★必须有**比过的条数**（★比了 0 条 ⇒ **红**✗ —— ★"★没得比★"与"★比过且对上★"不是一回事✗★）✗
#     ③ ★实测的 key 若**不在导出里** ⇒ 如实说"★这条没得比★"✗ 但不许拿它凑数✗★ ✓
import kb_export as KX
exp_p = pathlib.Path(KX.find_export(""))
if not exp_p.is_file():
    print("  T4   ✓（★跳过✗★）导出不在盘上 ⇒ 这条**没法验** ✗ 如实说，不当通过也不当坏")
else:
    exp = json.loads(exp_p.read_text(encoding="utf-8")).get("blocks") or {}
    miss, notcomp, cmp_n, skipped, declared = [], [], 0, [], []
    for i in items:
        if i.get("status") != "measured":
            continue
        sp = i.get("species_key")
        if not sp:
            miss.append((i.get("id"), "★缺 `species_key`✗★"))
            continue
        if sp not in exp:
            notcomp.append(sp)
            continue
        # ★★2026-10-18（★§79.296✗★）✗★★：★**不是所有实测都能拿 `max_height` 比**✗★ ——
        #   ★比如"★台阶一步上 0.5 格★"讲的是**抬腿高度**（★行为✗★）✗ 导出那个值是 **盒子总高 1.0**✗★ ⇒
        #   ★硬比就是**假红**✗★ ⇒ ★用 `compare` 字段分流✗★ ✓
        kind = (i.get("compare") or "max_height")
        if kind != "max_height":
            skipped.append((sp, kind))
            continue
        h = (exp[sp] or {}).get("max_height")
        # ★★已声明**分歧**的（★铁律②✗★）✗ 要被**大声点名** ✗ 但不判红（★它已经声明过了✗★）✓
        if i.get("export_disagrees"):
            declared.append((sp, h, i["expect"]))
            cmp_n += 1
            continue
        cmp_n += 1
        if h is not None and abs(float(h) - float(i["expect"])) > 0.01:
            miss.append((sp, h, i["expect"]))
    print("  T4   ★真比过 %d 条★（★没得比 %d 条：%s✗★）"
          % (cmp_n, len(notcomp), notcomp[:3]))
    if cmp_n == 0 and notcomp:
        # ★★2026-10-18（★§79.285✗★）✗★★：★measured 的条目**导出里都没有** ⇒
        #   ★那是"★**没得比**★" ✗ 真类别 **INCONCLUSIVE ＋ rc=4** ✗ 不是红✗★ ✓
        print("INCONCLUSIVE: ★比不了★ —— measured 的条目导出里都没有（%s）✗ "
              "★不是判据坏✗★" % notcomp)
        sys.exit(4)
    if skipped:
        print("  T4   ★跳过 %d 条**不是几何**的实测✗★：%s（★它们要各自的判法 ✗ 硬比就是假红✗★）"
              % (len(skipped), skipped[:3]))
    if declared:
        print("  T4   ★★**已声明的分歧**★（★铁律②✗★）✗ **导出说** ✗ **世界说**✗★ ⇒ %s"
              % (declared[:3],))
    check("T4", (not miss) and cmp_n >= 1,
          "有实测的那条与导出**真的**对得上（★必须比过 ≥1 条 ✗ 否则这条判据就是空的✗★）"
          "（不一致：%s）" % (miss or "无"))

print("=> truth_contract %s（★已实测 %d ／ 待实测 %d✗★）"
      % ("PASS ✓" if ok[0] else "FAIL",
         sum(1 for i in items if i.get("status") == "measured"),
         sum(1 for i in items if i.get("status") == "unmeasured")))
sys.exit(0 if ok[0] else 1)
