#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""errata_archive.py -- 把错题本**归档并重建索引** ✓（2026-09-29 用户要求 ✓ 可重复跑 ✓）

WHY（用户原话 ✓）：「先处理错题，并归档」
  ★现状问题 ✗：`docs/错题本.md` 已经 **2817 行 / 125 条** ✓
    ⇒ 每轮"要读"的那几条纪律 ✗ 被埋在 2800 行里 ✗ ⇒ **读过 ≠ 防住** ✗
  ★这份工具做三件事★ ✓：
    ① **全文快照**到 `docs/错题本-归档-<日期>.md` ✓（★逐字保留 ✗ 一条都不删 ✓★）
    ② 把 `docs/错题本.md` 改写成**索引版** ✓：纪律清单（一句话一条 ✓）＋
       **错题→回归判据**对照表 ✓＋ 全部条目一行一条 ✓
    ③ **校验**：条目数守恒 ✓（归档里有多少条 ⇒ 索引里必须都列出来 ✓）
  ★纪律★ ✗：**归档不是删除** ✓ —— 索引里丢了标题 ⇒ 就是"记忆被悄悄剪掉" ✗（本项目最忌讳 ✓）
    所以脚本末尾**自己报数** ✓ 并让 `tools/errata_index_test.py` 每次跑都复查 ✓

用法 ✓：`py tools/errata_archive.py`（重建 ✓ 幂等 ✓ 归档按日期命名 ⇒ 同一天重复跑就覆盖 ✓）
"""
from __future__ import annotations

import io
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "错题本.md"

# ★★入口标题**只有这一把尺子**★★ ✗（2026-09-30 第 35 轮修 ✓ ⇒ P129 ✓）
#   ✗ 原来 `parse()` 写 `\.?`（宽容 ✓ 认 `### P19.1 ★…` ✓）
#     而"查重"那一段写 `\.`（严格 ✗）⇒ **同一条被反复追加** ✗
#     （实测 ✓：归档里 4 份一模一样的 `### P19.1` ✗ 索引表里也出现两行 ✗）
#   ⇒ 现在**两处都用这一个常量** ✓（P106：一个 predicate 只能有一个定义 ✓）
HEAD_RE = re.compile(r"^### (P\d+(?:\.\d+)?)\.?\s+(.*)$", re.M)


def canonical_text() -> tuple:
    """★正文的**唯一真源**是归档 ✗（不是索引版！）★ ✓（第 34 轮末修 ✓ 实测撞到 ✓）

    ✗ 第一版从 `docs/错题本.md`（索引版）里找 `### P<n>.` ✗
      ⇒ 索引建好之后**再跑一次就找不到条目** ✗ ⇒ 直接中止 ✓（★幸好它中止了而不是把索引清空 ✗★）
    口径 ✓：**归档（全部 `错题本-归档-*.md` 并起来）才是正文** ✗；索引**只是它的摘要** ✓
      没有归档时（第一次跑 ✓）才退回读索引版 ✓
    返回 ✓：`(文本, 来源说明)` ✓
    """
    archs = sorted((ROOT / "docs").glob("错题本-归档-*.md"))
    if archs:
        parts = [a.read_text(encoding="utf-8") for a in archs]
        return "\n\n".join(parts), "归档 %d 份（%s）" % (
            len(archs), ", ".join(a.name for a in archs))
    return SRC.read_text(encoding="utf-8"), "索引版（还没有归档 ✓ 第一次跑 ✓）"


def parse(txt: str):
    """切成 [(编号, 标题, 正文)] ✓ —— 只认 `### P<n>.` 这种标题 ✗"""
    lines = txt.splitlines()
    heads = []
    for i, ln in enumerate(lines):
        # ★标题两种写法都要认 ✗（第 34 轮末 ✓ 实测：`### P19.1 ★★更正…` **没有**末尾那个点 ✗）
        #   `\.?` ⇒ 点为可选 ✓（★我第一版要求必须有点 ⇒ 子条被并进上一条 ✗ 判据当场报出来 ✓★）
        m = HEAD_RE.match(ln)
        if m:
            heads.append((i, m.group(1), m.group(2).strip()))
    out = []
    for k, (i, p, title) in enumerate(heads):
        j = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        out.append((p, title, "\n".join(lines[i:j]).rstrip()))
    return out, lines[:heads[0][0]] if heads else lines


def status_of(p: str, guard: str, others: dict) -> str:
    if re.search(r"\b%s\b" % p, guard):
        return "★有回归判据★ ✓"
    n = len(others.get(p) or ())
    if n:
        return "被 %d 处引用 ✓" % n
    return "仅归档 ✓"


def _body_span(lines: list, i: int, j: int) -> tuple:
    """块里**正文**的范围 ✓：从标题行起 ✗ 到**最后一个真内容行**为止 ✗

    ★为什么要这一步✗★（实测 ✓ 第一版只删掉 2 块、还剩 3 块 ✗）：
      `### P19.1` 的四份**正文一字不差** ✓ 但**尾巴上挂的东西不一样** ✗
      （有的后面是 `---` ＋ 一个空的 `# P 系列…` 小节标题 ✓ 有的只剩空行 ✓）
      ⇒ 拿"整段"比较 ⇒ **认不出它们是重复的** ✗
    口径 ✓：尾部的 **空行｜`---`｜`<!-- … -->` 注释｜`#`／`##` 小节标题** ⇒ **都不算正文** ✗
    """
    k = j
    while k - 1 > i:
        s = lines[k - 1].strip()
        if (not s) or s == "---" or s.startswith("<!--") or re.match(r"^#{1,2} ", s):
            k -= 1
            continue
        break
    return i, k


def dedupe_identical(path: Path) -> tuple:
    """★把**逐字一模一样**的重复块删掉 ✗★（★不一样的一个字都不动 ✗★）

    WHY（2026-09-30 第 35 轮 ✓ 实测撞到 ✓ ⇒ P129 ✓）：
      `### P19.1` 这种**子条**标题**没有末尾那个点** ✗ ⇒ 老代码里"查重"用的尺子比
      `parse()` 严一格 ✗ ⇒ **同一段被每次跑都追加一遍** ✗
      （实测 ✓：归档里 **4 份**一模一样的 `P19.1` ✗ ＋ 索引表里 130 行 / 129 个编号 ✗）
    ★口径★ ✗：**只删"正文逐字相同"的**（行尾空白不算 ✓；尾部空行／`---`／注释／小节标题不算 ✓）
      ⇒ 正文真的不一样的 ⇒ **留着 ＋ 大声报出来** ✗ ——
        ★宁可留两份让人看见，也不许"顺手删掉我不认识的东西" ✗★
    返回 ✓：`(删掉的块数, [(编号, 出现次数)])` ✓
    """
    txt = path.read_text(encoding="utf-8")
    lines = txt.splitlines(keepends=True)
    heads = [i for i, ln in enumerate(lines) if HEAD_RE.match(ln)]
    if not heads:
        return 0, []
    blocks = []                                  # [(编号, 起, 止)]
    for k, i in enumerate(heads):
        j = heads[k + 1] if k + 1 < len(heads) else len(lines)
        blocks.append((HEAD_RE.match(lines[i]).group(1), i, j))
    seen = {}                                    # 编号 -> 规范化正文
    drop = []
    dup = {}
    for (p, i, j) in blocks:
        a, b = _body_span(lines, i, j)
        body = tuple(ln.rstrip() for ln in lines[a:b])
        if p not in seen:
            seen[p] = body
            continue
        dup[p] = dup.get(p, 1) + 1
        if body == seen[p]:
            drop.append((a, b))
    if drop:
        skip = set()
        for (a, b) in drop:
            skip.update(range(a, b))
        path.write_text("".join(ln for k, ln in enumerate(lines) if k not in skip),
                        encoding="utf-8")
    return len(drop), sorted(dup.items())


def main() -> int:
    # ★第一步就"清掉逐字重复的块"✗★（不然它会一路带进索引 ✗ ⇒ P129 ✓）
    arch0 = ROOT / "docs" / ("错题本-归档-%s.md" % time.strftime("%Y-%m-%d"))
    if arch0.is_file():
        n_drop, dups = dedupe_identical(arch0)
        if dups:
            print("查重 ✓ %s：重复编号 %s ｜ **逐字相同 ⇒ 删掉 %d 块** ✓ %s"
                  % (arch0.name, dups, n_drop,
                     "（★不一样的那些我一个都没动 ✗★）" if n_drop != sum(n - 1 for _, n in dups)
                     else ""))
    txt, whence = canonical_text()
    entries, preamble = parse(txt)
    if not entries:
        print("找不到任何 `### P<n>.` 条目 ✗ ⇒ 停下来 ✓ 不动任何文件 ✓（正文来源：%s）" % whence)
        return 1
    print("正文来源 ✓ %s ⇒ %d 条 ✓" % (whence, len(entries)))
    # ① 归档：★★**只追加**★★ ✗（第 34 轮末修 ✓ 实测教训 ✓）
    #   为什么 ✗：我第一版是"按日期命名 ⇒ 同一天重复跑就**覆盖**"✗
    #     ⇒ 而我先补记了 P121/P122 到归档里 ✗ 再跑一次脚本 ⇒ **补记被抹掉** ✗✗
    #       （★"归档"最忌讳的就是这个 ✗ —— 它必须是**只增不减**的 ✓）
    #   口径 ✓：文件已存在 ⇒ **把还缺的条目追加进去** ✗ 别的**一个字都不改** ✓
    day = time.strftime("%Y-%m-%d")
    arch = ROOT / "docs" / ("错题本-归档-%s.md" % day)
    banner = ("<!-- 错题本**全文归档** ✓ %s ✓\n"
              "     ★这不是备份而是**正文**✗★：索引版（docs/错题本.md）只放一句话摘要 ✓\n"
              "     要细节 ⇒ 来这里按 `### P<n>.` 搜 ✓（tools/errata_archive.py 生成 ✓ **只追加** ✓）-->\n\n"
              % time.strftime("%Y-%m-%d %H:%M"))
    if not arch.is_file():
        arch.write_text(banner + txt, encoding="utf-8")
        added = len(entries)
    else:
        have = set(m.group(1) for m in HEAD_RE.finditer(arch.read_text(encoding="utf-8")))
        add = [e for e in entries if e[0] not in have]
        if add:
            with arch.open("a", encoding="utf-8") as f:
                f.write("\n\n<!-- 追加于 %s ✓ 只增不减 ✓ -->\n\n"
                        % time.strftime("%Y-%m-%d %H:%M"))
                f.write("\n\n".join(b for (_p, _t, b) in add) + "\n")
        added = len(add)
    # ② 收集"被引用"与"有判据"的账
    guard = (ROOT / "tools" / "errata_guard_test.py").read_text(encoding="utf-8")
    others: dict = {}
    for f in sorted((ROOT / "tools").glob("*.py")) + sorted((ROOT / "docs").glob("*.md")) + \
            sorted((ROOT / "tools").glob("*.ps1")):
        if f.name in ("错题本.md",) or f.name.startswith("错题本-归档"):
            continue
        try:
            t = f.read_text(encoding="utf-8")
        except Exception as e:
            # 记录：读不到一个文件 ⇒ "被引用"集合少一份（可能把还有引用的条目当成没人引用）
            print("[记录] 引用扫描读不到 %s（%s）⇒ 引用账偏少"
                  % (f.name, type(e).__name__), file=sys.stderr)
            continue
        for p in set(re.findall(r"\b(P[1-9]\d{0,2}(?:\.\d+)?)\b", t)):
            others.setdefault(p, set()).add(f.name)
    # ③ 纪律清单：只收"**以`纪律`开头**"的那种行 ✓（第 34 轮末修 ✓）
    #   ✗ 第一版收"含'纪律'二字 且 以 -/*/★ 开头"⇒ 收进来一堆**句子碎片** ✗
    #     （实测 ✓：104 条里一半是半句话 ✓ ⇒ 这种清单**没人会读** ✗ = 白做 ✓）
    #   ⇒ 口径 ✓：剥掉 bullet/星号后**必须以"纪律"二字开头** ✓ ＋ 去重 ✓ ＋ 只留最近 40 条 ✓
    seen = set()
    rules = []
    for (p, _title, body) in reversed(entries):        # 从最近的往前收 ✓
        for ln in body.splitlines():
            s = re.sub(r"^[\s\-*★>]+", "", ln.strip())
            s = re.sub(r"\*+", "", s)
            if not s.startswith("纪律"):
                continue
            one = re.sub(r"^纪律[：:\s]*", "", s)
            one = re.sub(r"[★✗✓]", "", one).strip(" ：:（(")
            if len(one) < 6 or one in seen:
                continue
            seen.add(one)
            rules.append((p, one[:120]))
            break
    rules = rules[:40]
    # ④ 写索引版
    L = []
    L.append("# 错题本（**索引版** ✓ %s ✓）" % day)
    L.append("")
    L.append("> ★**正文在归档**✗★：`%s`（%d 条 ✓ 逐字保留 ✓）"
             % (arch.name, len(entries)))
    L.append("> ★**怎么用**✗★：① 每轮开工先扫一眼下面**纪律清单**（一句话一条 ✓）"
             "② 动过行为 ⇒ 跑 `py tools\\check_all.py --offline`（含 `errata_guard_test.py` ✓ 秒级 ✓）"
             "③ 要细节 ⇒ 去归档里按 `### P<n>.` 搜 ✓")
    L.append("> ★**不许删条目**✗★：条目数守恒由 `tools/errata_index_test.py` 每次复查 ✓"
             "（新增错题 ⇒ 跑一次 `py tools/errata_archive.py` 重建 ✓）")
    L.append("")
    L.append("## 一、纪律清单（活跃 ✓ 一句话一条 ✓）")
    L.append("")
    for p, one in rules:
        L.append("- **%s** %s" % (p, one))
    L.append("")
    L.append("## 二、错题 → 回归判据（`errata_guard_test.py`）")
    L.append("")
    L.append("| 判据 | 钉住的错题 |")
    L.append("| --- | --- |")
    for m in re.finditer(r"#\s*-+\s*(E\d+)\s*\(([^)]*)\)", guard):
        L.append("| **%s** | %s |" % (m.group(1), m.group(2)))
    L.append("")
    L.append("## 三、全部条目（%d 条 ✓ 一行一条 ✓ 细节在归档 ✓）" % len(entries))
    L.append("")
    L.append("| # | 标题 | 状态 |")
    L.append("| --- | --- | --- |")
    for (p, title, _b) in entries:
        t = re.sub(r"[|]", "/", title)
        L.append("| %s | %s | %s |" % (p, t[:96], status_of(p, guard, others)))
    SRC.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("归档 ✓ %s（%d 条 ✓ 逐字 ✓）" % (arch.name, len(entries)))
    print("索引 ✓ docs/错题本.md：纪律 %d 条 ✓ 全部条目 %d 条 ✓ 判据表 %d 行 ✓"
          % (len(rules), len(entries), len(re.findall(r"\| \*\*E\d+\*\* \|", "\n".join(L)))))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
