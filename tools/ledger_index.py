#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_index.py -- 台账索引：由脚本生成（§79.248 用户裁决 D2）

用户原话：交接文档分卷 ＋ **脚本生成索引** ＋ 入口文档状态行配判据
（★§77 已记过一次「入口当天就过期」✗★）。
这一版先做**索引**那一半（★分卷要动 1.3 万行的主文档 ✗ 风险大 ✗ 留作独立一步✓★）。
★口径✗★：
  · ★索引里的每个条目都**指回台账的真实标题**✗★（★不许手抄 ✗ 一抄就会飘✗★）
  · ★顺带把「★有号无标题★」与「★被代码引用却没落进台账★」两类**当场列出来**✗★
    （★后者就是审计 M0 抓到的「§79.230／§79.235 引用悬空」✓★）
  · ★内容没变就不写✗★（★走 `docwrite` ✗ D4✓★）
"""
from __future__ import annotations

import pathlib
import re
import sys

# ★★2026-10-13（★stdio_guard 抓的✗★）✗★★：★会印 ✓／✗ 的脚本**必须 pin 住 stdout**✗★ ✓
#   ★（★本文件印「✗」= U+2717 ✗ 在 Windows 控制台默认代码页下会炸 ✗ 而它是**静默**炸✗★）✗★ ✓
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
# ★★2026-10-18（★§79.323 ✗ D2 分卷✗★）✗★★：★台账**分了卷** ✗ 再只读一个文件
#   就会**看不见**卷一里的 175 节 ✗ 索引缺一大半 ✗ 悬空检测也会误报✗★ ⇒
#   ★★扫**所有卷**✗★★ ✓
LEDGER = ROOT / "docs" / "当前阶段-状态与交接.md"      # ★主文件（★§79.14＋状态行＋§79.190 起✗★）✗★
LEDGERS = [LEDGER] + sorted((ROOT / "docs").glob("交接-卷*.md"))
OUT = ROOT / "docs" / "台账-索引.md"


def scan():
    """★扫台账标题 ✗ 返回 (编号, 标题, 行号)✗★"""
    rows = []
    for _f in LEDGERS:
      if not _f.is_file():
        continue
      for i, line in enumerate(_f.read_text(encoding="utf-8", errors="replace").splitlines()):
        # ★★2026-10-13 修（★§79.248 续✗★）✗★★：★两块都改 ✗ 因为第一版**误报了 9 个悬空**✗★ ✓
        #   ① ★合并标题要**认全**✗★：★台账里有「### 79.233／79.234 …」这种写法 ✗
        #      第一版只取到 `79.233` ⇒ ★`79.234` 被当成"没有这个号"✗★ ✓
        #   ② ★只认**台账命名空间**（`79.x`）✗★：★`§5.1／§6.1／§7.2` 那些是
        #      **任务书**的节号 ✗ 不是台账的 ✗ 拿它们查台账当然查不到✗★ ✓
        #   ★（★同一族第 6 次 ✗ 先量再写 —— 这次是**生成器**里的判据写歪了✗★）✗★ ✓
        m = re.match(r"^#{2,3}\s*(.*)$", line.strip())
        if not m:
            continue
        nums = re.findall(r"(79\.[0-9]+)", m.group(1))
        if nums:
            rows.append((nums[0], m.group(1).strip(), i + 1, _f.name))
            for extra in nums[1:]:
                rows.append((extra, "（★与 §%s 同一节 ✗ 合并标题✗★）" % nums[0], i + 1, _f.name))
    return rows


def cited():
    """★工具脚本里引用过的 § 号（★引用悬空就靠它发现✗★）✗★"""
    refs = {}
    for p in sorted((ROOT / "tools").glob("*.py")):
        txt = p.read_text(encoding="utf-8", errors="replace")
        # ★只收台账命名空间（★`§79.x`✗★）✗ 任务书那些节号不归它管✗★ ✓
        for m in re.finditer(r"§(79\.[0-9]+)", txt):
            refs.setdefault(m.group(1), set()).add(p.name)
    return refs


def render():
    rows = scan()
    refs = cited()
    have = {n for n, _t, _l, _f in rows}
    dangling = sorted(k for k in refs if k not in have)
    # ★★2026-10-18（★§79.323✗★）✗★★：★**分了卷**之后"★第 N 行★"跨文件有歧义✗★ ⇒
    #   ★索引行**必须带卷名**（★主文件照旧 ✗ 卷一标出来✗★）✗★ ✓
    _vols = [f.name for f in LEDGERS if f.is_file()]
    body = ["# 台账索引（由 `tools/ledger_index.py` 生成，别手改）", "",
            "★台账共 **%d** 节 ✗ 扫 **%d** 个文件：%s✗★" % (len(rows), len(_vols), "／".join("`%s`" % v for v in _vols)), ""]
    for n, t, ln, fn in rows:
        _where = "" if fn == LEDGER.name else "（★%s✗★）" % fn
        body.append("* §%s %s（第 %d 行%s）" % (n, t[:90], ln, _where))
    body += ["", "★被工具脚本引用、但台账里**没有**这个号的✗★（★引用悬空 ✗ 要补 ✗ 别让它烂着✓★）："]
    if dangling:
        for k in dangling:
            body.append("* §%s —— 被 %s 引用" % (k, "／".join(sorted(refs[k])[:4])))
    else:
        body.append("* （没有 ✓）")
    body.append("")
    return chr(10).join(body), len(rows), dangling


def main(argv=None) -> int:
    import docwrite as DW
    text, n, dangling = render()
    wrote = DW.write_if_changed(OUT, text)
    print("台账 %d 节 ✗ 索引%s ✗ 引用悬空 %d 个%s"
          % (n, "已重写" if wrote else "没变（不写）", len(dangling),
             ("：" + "／".join(dangling[:6])) if dangling else ""))
    # ★★2026-10-18（★复核 P2-10 ✗ §79.278✗★）✗★★：★"★引用悬空 0 个★"**只对 `tools/*.py` 成立**✗★ ——
    #   ★文档（★任务书／决策单／审计／跑单✓★）里的 `§79.x` **不在扫描范围**✗★ ⇒
    #   ★★这个 0 **不能**当"★全部引用都在★"读✗★★ ⇒ ★输出**自己说清** ✗ 别让人误读✗★ ✓
    #   ★（★"★数字对 ✗ 但被误读★"是这一族的老毛病 ✗ 治法是**让输出自己带口径**✗★）✗★ ✓
    print("   （★扫描范围★：★只扫 `tools/*.py` ✗ **不含 docs/ 里的引用** ✓ "
          "★所以这个 0 只说明**代码里**的节号都在✓★）")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    raise SystemExit(main())
