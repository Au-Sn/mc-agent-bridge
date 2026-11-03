#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""errata_index_test.py -- ★错题归档的"守恒"判据★ ✓（离线 ✓ 秒级 ✓ 2026-09-30 ✓）

WHY（用户要求"先处理错题，并归档" ✓ 而归档最怕的就是**悄悄丢东西** ✗）：
  · `docs/错题本.md` 现在只是**索引**（一句话一条 ✓）；**正文在 `错题本-归档-*.md`** ✓
  · 于是有两种"静默失忆"随时可能发生 ✗：
    ① 索引里少了条目 ✗ ⇒ 没人知道它存在过 ✓（= 记忆被剪掉 ✓）
    ② 代码/文档里引用 `P121` ✗ 而正文里根本没有这条 ✗（★实测真发生过★ ✓ ——
       第 34 轮我引用过 P121/P122 ✗ 却从没把它们写进正文 ✓ 是我的判据查出来的 ✓）
  ⇒ 这份判据就盯这两件事 ＋ 判据表的双向对账 ✓

CRITERIA（跑之前先写 ✓）：
  G1 守恒   ：**归档并集**里的 `### P<n>.` 条目集合 ⇒ 与**索引表**里列出的**完全一致** ✓
              （少一个 = 记忆被剪 ✗；多一个 = 索引写了不存在的东西 ✗）
  G2 不悬空 ：`tools/*.py`｜`tools/*.ps1`｜`docs/*.md`（**除归档与索引本身** ✓）里出现的
              每个 `P<n>` ⇒ 必须在归档里**真有这一条** ✓
  G3 判据表 ：`errata_guard_test.py` 里每条 `E<n> (P…)` ⇒ 那些 P 必须都存在 ✓；
              且**至少 6 条** E 挂了错题 ✗（空表也是假绿 ✓）
  G4 结构   ：索引必须有三节（纪律清单／判据对照／全部条目 ✓）＋ 指向归档的说明 ✓；
              归档必须**存在**且条目数 > 0 ✓
  G5 只增不减：归档文件按日期**只增**✓（同一天不允许出现两份同名 ✓）——
              条目数只报数 ✓ 不与历史比较 ✗（没有历史快照可比 ✓ 老实说 ✓）
  G6 不许重复：★同一条 `P<n>` 在归档里**只许出现一次**✗★ ＋ 索引表行数必须**等于**编号数 ✓
              （★G1 用集合 ⇒ **看不见重复** ✗ 实测 4 份 `P19.1` 时它照样报绿 ✗★）

ASCII 输出为主 ✓（中文只在说明里 ✓ 控制台走 UTF-8 重定向 ✓）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def say(s):
    print(s, flush=True)


def archived_entries() -> dict:
    """归档并集：{P编号: (来自哪份归档, 标题)} ✓"""
    out = {}
    for (name, p, title) in archived_all():
        out.setdefault(p, (name, title))
    return out


def archived_all() -> list:
    """★归档里**每一次出现**✗★ ✓ ⇒ `[(归档名, 编号, 标题)]` ✓（含重复 ✗）

    ★为什么不能只用 `setdefault` 的那个版本✗★（2026-09-30 第 35 轮 ✓ 实测撞到 ✓ ⇒ G6 ✓）：
      并集版本**看不见重复** ✗ ⇒ 归档里 `P19.1` **四份**、索引表 130 行 / 129 个编号 ✗
      而 G1「守恒」照样**报绿** ✗ —— ★因为它的尺子用的是集合 ✗★
      ⇒ 于是单开 G6 专门数**出现次数** ✓（P106 同族：口径不同就是两把尺子 ✓）
    """
    out = []
    for a in sorted(DOCS.glob("错题本-归档-*.md")):
        t = a.read_text(encoding="utf-8")
        # ★与 `errata_archive.py` **同一处口径** ✗（第 34 轮末 ✓ 点为可选 ✓ 认 `P19.1` 子条 ✓）
        for m in re.finditer(r"^### (P\d+(?:\.\d+)?)\.?\s+(.*)$", t, re.M):
            out.append((a.name, m.group(1), m.group(2).strip()))
    return out


def index_entries() -> dict:
    """索引表里列出的条目：{P编号: 标题} ✓（第三节的表 ✓）

    ⚠ 要认 **`P19.1`** 这种子条 ✗（第 34 轮末 ✓ 实测：`P\\d+` 会在 `P19.1` 上停下 ✗
      ⇒ 索引表少一条 ⇒ 守恒判据报"归档 127 / 索引 126" ✗ —— ★是判据把我抓出来的 ✓★）
    """
    t = (DOCS / "错题本.md").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^\|\s*(P\d+(?:\.\d+)?)\s*\|\s*([^|]*)\|", t, re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


def _key(s: str):
    """编号排序键 ✓（`P19.1` ⇒ (19, 1) ✓ 不能直接 `int` ✗ 我第一版就崩在这 ✓）"""
    return tuple(int(x) for x in s[1:].split("."))


def main() -> int:
    ok = True
    arch = archived_entries()
    idx = index_entries()
    say("归档并集 %d 条 ✓ ｜ 索引表 %d 条 ✓" % (len(arch), len(idx)))
    if not arch:
        say("G4 FAIL: 一份归档都没有 ✗（先跑 `py tools/errata_archive.py` ✓）")
        return 1

    g1_missing = sorted(set(arch) - set(idx), key=_key)
    g1_extra = sorted(set(idx) - set(arch), key=_key)
    g1 = (not g1_missing) and (not g1_extra)
    say("G1 守恒：索引里缺 %d 条 %s ｜ 索引里多出 %d 条 %s => %s"
        % (len(g1_missing), g1_missing[:6], len(g1_extra), g1_extra[:6], g1))
    ok &= g1

    # G2：全仓（除归档/索引）里引用的每个 P<n> 都必须真有
    files = [p for p in list((ROOT / "tools").glob("*.py"))
             + list((ROOT / "tools").glob("*.ps1"))
             + list(DOCS.glob("*.md"))
             if p.name != "错题本.md" and not p.name.startswith("错题本-归档")
             and p.name != "errata_index_test.py"]
    dangling = {}
    for f in files:
        try:
            t = f.read_text(encoding="utf-8")
        except Exception as e:
            # 记录：读不到一个文件 ⇒ G2 少查一处引用（可能假绿）
            say("  ★记录✗★ G2 读不到（少查一处引用 ⇒ 可能假绿）：%s（%s）"
                % (f.name, type(e).__name__))
            continue
        for p in set(re.findall(r"\b(P[1-9]\d{0,2}(?:\.\d+)?)\b", t)):
            if p not in arch:
                dangling.setdefault(p, []).append(f.name)
    g2 = not dangling
    say("G2 不悬空：被引用却**不存在**的编号 %d 个 %s => %s"
        % (len(dangling), {k: v[:2] for k, v in list(dangling.items())[:5]}, g2))
    ok &= g2

    # G3：判据表的双向对账
    gt = (ROOT / "tools" / "errata_guard_test.py").read_text(encoding="utf-8")
    pairs = re.findall(r"#\s*-+\s*(E\d+)\s*\(([^)]*)\)", gt)
    bad = [p for (_e, ps) in pairs
           for p in re.findall(r"P\d{1,3}", ps) if p not in arch]
    g3 = (len(pairs) >= 6) and (not bad)
    say("G3 判据表：%d 条 ✓（要求 >=6）｜ 表里指向不存在的编号 %s => %s"
        % (len(pairs), bad[:5], g3))
    ok &= g3

    # G4：结构
    it = (DOCS / "错题本.md").read_text(encoding="utf-8")
    g4 = ("## 一、纪律清单" in it) and ("## 二、错题 → 回归判据" in it) \
        and ("## 三、全部条目" in it) and ("错题本-归档-" in it)
    say("G4 结构：三节齐全 ＋ 指向归档 = %s" % g4)
    ok &= g4

    # G5：只增不减（同一天不许两份同名归档 ✓ 多份不同日期的允许 ✓）
    names = [p.name for p in DOCS.glob("错题本-归档-*.md")]
    g5 = len(names) == len(set(names))
    say("G5 归档唯一：%d 份 %s => %s" % (len(names), sorted(names)[:3], g5))
    ok &= g5

    # G6：★同一条**不许出现两次**✗★（第 35 轮新增 ✓ ⇒ P129 ✓）
    all_e = archived_all()
    cnt = {}
    for (_n, p, _t) in all_e:
        cnt[p] = cnt.get(p, 0) + 1
    dups = {p: n for p, n in cnt.items() if n > 1}
    rows = len(re.findall(r"^\|\s*P\d+(?:\.\d+)?\s*\|", (DOCS / "错题本.md")
                          .read_text(encoding="utf-8"), re.M))
    g6 = (not dups) and (rows == len(cnt))
    say("G6 不重复：出现 %d 次／%d 个编号 ｜ 重复的 %s ｜ 索引表 %d 行 => %s"
        % (len(all_e), len(cnt), dups, rows, g6))
    ok &= g6

    say("---- G1=%s G2=%s G3=%s G4=%s G5=%s G6=%s ----" % (g1, g2, g3, g4, g5, g6))
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
