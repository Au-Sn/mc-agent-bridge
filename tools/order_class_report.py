#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""order_class_report.py -- 阶段 5 后半句「顺序类错题结构性消失」的**报告器**（§79.257）

★为什么它**只报数 ✗ 不判红**★：
  任务书那句「顺序类错题**结构性消失**」**没有机械定义**；
  §79.125 给了一个**可操作读法**，并明确标成「**待用户确认 ✗ 不擅自当成判据写死**」。
  原话口径：「**写死一条错定义比不写更坏**」⇒ 这一版**照那个读法报数**，但**不宣布「消失了」**。

★它报三样★：
  ① **五个世界侧几何检查**（`route_verify` 道剖面 ✗ `area_verify` map_area ✗
     `slab_ramp` 半步边界 ✗ `verdict_levels` 分层与越权 ✗ `step_route` 上下台阶）
     最近一次跑出来什么（读 `logs/check_*.log`；**没跑过就如实说「没跑过」✗ 不当绿**）
  ② `kb_audit` 的「矛盾」一栏（它**要导出** ⇒ 没导出就如实说「要导出」）
  ③ **结构性**那一问：造成这一类错题的**成因**还在不在 ——
     今天的诚实答案是「**还在**」（名字判据仍是默认档，`AUTO_STEP_BY_HEIGHT` 默认关，见 §79.232）

★输出★：机器行（`logs/order_class.txt` 首行）纯 ASCII（D3）；退出码三分类（与闸门同口径）：
  0 ＝ 三条都拿到了；4 ＝ **有东西没拿到**（**不是通过 ✗ 也不是坏**）
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# §79.125 那五个世界侧几何检查（名字照抄，不改）
GEOM = ("route_verify_test.py", "area_verify_test.py", "slab_ramp_test.py",
        "verdict_levels_test.py", "step_route_test.py")


def last_log(name: str):
    """最近一次跑的结论（读日志，不跑它）"""
    p = ROOT / "logs" / ("check_" + name.replace(".py", "") + ".log")
    if not p.is_file():
        return None, "没有日志（★没跑过 ✗ 不是绿★）"
    txt = p.read_text(encoding="utf-8", errors="replace")
    if "不符合" in txt or "FAIL" in txt:
        why = [l.strip() for l in txt.splitlines() if "不符合" in l or "FAIL" in l]
        return "red", (why[0][:80] if why else "有 FAIL")
    if "INCONCLUSIVE" in txt or "测不了" in txt:
        return "inconclusive", "测不了"
    return "green", "绿"


def main() -> int:
    lines, missing = [], []
    print("== order_class：阶段 5 后半句（★只报数 ✗ 不判红★）==")
    print("")
    print("① 五个世界侧几何检查（最近一次）：")
    n_red = 0
    for name in GEOM:
        st, why = last_log(name)
        if st is None:
            missing.append(name)
        if st == "red":
            n_red += 1
        print("   %-26s %-12s %s" % (name, st or "★没跑过✗★", why[:60]))
    lines.append("geom_red=%d" % n_red)
    lines.append("geom_missing=%d" % len(missing))

    print("")
    print("② `kb_audit` 的「矛盾」一栏：")
    rep = ROOT / "logs" / "kb_audit.txt"
    con = None
    if rep.is_file():
        m = re.search(r"矛盾[^0-9]{0,6}(\d+)", rep.read_text(encoding="utf-8", errors="replace"))
        con = int(m.group(1)) if m else None
        print("   %s ⇒ %s" % (rep.name, ("矛盾 %d" % con) if con is not None else "★读不出那个数★"))
    else:
        print("   ★没跑过 ✗ 它**要导出** ⇒ 如实说「要导出」★")
        missing.append("kb_audit.txt")
    lines.append("kb_conflicts=%s" % ("?" if con is None else con))

    print("")
    print("③ **结构性**那一问（成因还在不在）：")
    pp = (ROOT / "tools" / "pathplan.py").read_text(encoding="utf-8", errors="replace")
    # ★它读**环境** ✗ 不是赋值（★第一版按赋值找 ✗ 打出 `?`✓★）
    byh = re.search(r"AUTO_STEP_BY_HEIGHT[^\n]{0,80}", pp)
    _sw = re.search(r"(BY_HEIGHT\s*=\s*[^\n]{0,80})", pp)
    _val = (_sw.group(1) if _sw else (byh.group(0) if byh else "?"))
    print("   成因：「名字判据」仍是默认档 ⇒ **结构上还没消失**")
    print("   （`AUTO_STEP_BY_HEIGHT` ＝ %s ✗ 默认关 ⇒ 要等它转正 ＋ A/B 绿 ✗ 见 §79.232）"
          % (_val.strip()[:64],))
    lines.append("cause_present=1")

    print("")
    print("★这一条**不能**证明什么（写清 ✗ 免得被读成「消失了」）★：")
    print("   · 证明不了「顺序类错题已结构性消失」—— 成因今天**还在**")
    print("   · 它也不是判据：因为「顺序类错题」的定义**仍待用户确认**（§79.125）")
    print("   · 五个几何检查里只要**没跑过**，这一格就**不是绿**，是「没拿到」")

    head = ("ORDERCLASS red=%d missing=%d cause_present=1 %s"
            % (n_red, len(missing), " ".join(lines)))
    out = ROOT / "logs" / "order_class.txt"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(head + chr(10), encoding="utf-8")
        print("")
        print("机器行（纯 ASCII）⇒ %s" % head[:120])
    except Exception as e:
        print("★写日志失败 ★：%s" % type(e).__name__)
    return 0 if not missing else 4


if __name__ == "__main__":
    raise SystemExit(main())
