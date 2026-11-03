#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""safe_edit.py -- ★★"改文档"的安全帮手：唯一锚 ＋ 自动看 diff 行数✗★★（2026-10-02 ✓ 欠账 ⑧ ✓）

WHY ✓（★把 **P175** 从"我记得"变成"工具不让我错"✗★）：
  ★2026-10-02 我用"行首 `| ② |`"当锚 ✗ 一次误伤 **11** 行历史小节✗★（★P175 ✓★）
  ★另一次我按整份文档找圈号 ✗ 解析吞了 **53** 行✗★（★同族 ✓★）
  ⇒ ★两次都是同一个形状✗★：★**在长文档里用不唯一的锚去改东西**✗★
  ⇒ ★这个帮手把三件事变成**默认**✗★：① 唯一命中断言（≠1 ⇒ **一行都不改** ✗ 并报出来 ✓）
     ② 改完**自动**比对 `git diff --numstat` ✗ 行数对不上 ⇒ **抛异常**✗ ③ 只碰你说要碰的文件 ✓

★口径✗★：★它不是"文本替换库" ✗ 它是"**不许悄悄改多**"的护栏✗★
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# ★★stdout 必须 pin✗★★（★这是本仓既有守卫 `stdio_guard_test.py` 的要求 ✗
#   ★我第一版**漏了它** ⇒ 闸门当场红 ✗ 而我**还是提交了**✗★ —— ★两条教训 ✗ 都记在 P176 ✓★）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent


class UnsafeEdit(Exception):
    """★锚不唯一／diff 行数不符 ⇒ 一律抛这个 ✗ 不许静默继续✓★"""


def _numstat(path: Path):
    r = subprocess.run(["git", "diff", "--numstat", "--", str(path)], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "").strip()
    if not out:
        return (0, 0)
    parts = out.split("\t")
    try:
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return (0, 0)


def replace_unique(path, old: str, new: str, expect_diff=None):
    """★文本级替换 ✗ 必须**恰好命中一次**✗★

    ★★`expect_diff` 是**增量**✗ 不是累计✗★★（2026-10-02 当场吃到 ✓）：
      ★第一版拿"当前 `git diff` 的总数"去比 ✗ ⇒ ★同一次运行里**先追加了一节**（23 行）
      再改一行 ⇒ 实测 (24,1) ✗ 而我只期望 (1,1) ⇒ **护栏误报** ✗★
      ⇒ ★口径✗★：★先在写之前量一次 ✗ 写完再量一次 ✗ 比的是**这两次之差**✗★ ✓
    """
    p = Path(path)
    t = p.read_text(encoding="utf-8")
    n = t.count(old)
    if n != 1:
        raise UnsafeEdit("★锚命中 %d 次 ✗ 要求 1 ⇒ **一字未改**✗★\n  锚前 60 字：%r"
                         % (n, old[:60]))
    before = _numstat(p)
    orig = p.read_bytes()                      # ★★2026-10-03 检修：留一份原文，好回滚★★
    p.write_bytes(t.replace(old, new, 1).encode("utf-8"))
    try:
        return check_delta(p, before, expect_diff)
    except UnsafeEdit as e:
        # ★★`expect_diff` 不符 ⇒ 回滚★★（2026-10-03 检修）
        #   原来它先写后检 ⇒ 不符时只喊一声，而改动已经落在盘上。
        #   实测代价：一天里六次喊停（㉖ ㉔ ㉚ ㉜ ㉛ ㉙）全都留下了坏行 ——
        #   每行内格变 4 个 ⇒ 状态读到旧尾巴 ⇒ 正文写着已销、账面还算未销。
        #   口径：一个工具如果叫 safe，就必须要么不改、要么改了就一致。
        p.write_bytes(orig)
        raise UnsafeEdit(str(e) + "\n★已**回滚**★（文件回到写之前，这才是「拦住」）")


def check_delta(path, before, expect=None):
    """★比的是**这次写的增量**✗★（★写之前/之后各量一次 ✗ 两者之差✓★）"""
    after = _numstat(Path(path))
    delta = (after[0] - before[0], after[1] - before[1])
    if expect is not None and tuple(expect) != delta:
        raise UnsafeEdit("★本次改动量不符✗★：期望 %s ✗ 实测 (加,删)=%s ⇒ ★这次改动**比你想的大** ✗ "
                         "立刻用 `git diff` 看清楚 ✓★" % (tuple(expect), delta))
    return delta


def patch_line(path, prefix: str, new_line: str, expect_diff=None):
    """★行级替换（★按**行首**匹配 ✗ 这正是 P175 那次翻车的地方✓★）⇒ 仍然要求唯一 ✓"""
    p = Path(path)
    lines = p.read_text(encoding="utf-8").split("\n")
    hits = [i for i, ln in enumerate(lines) if ln.startswith(prefix)]
    if len(hits) != 1:
        raise UnsafeEdit("★行首锚 `%s…` 命中 %d 行 ✗ 要求 1 ⇒ **一字未改**✗★"
                         % (prefix[:40], len(hits)))
    before = _numstat(p)
    lines[hits[0]] = new_line
    p.write_bytes("\n".join(lines).encode("utf-8"))
    return check_delta(p, before, expect_diff)


def insert_after(path, prefix: str, new_lines, expect_diff=None):
    """★在某行**之后**插入几行 ✗ 锚仍须唯一✓★"""
    p = Path(path)
    lines = p.read_text(encoding="utf-8").split("\n")
    hits = [i for i, ln in enumerate(lines) if ln.startswith(prefix)]
    if len(hits) != 1:
        raise UnsafeEdit("★插入锚 `%s…` 命中 %d 行 ✗ 要求 1 ⇒ **一字未改**✗★"
                         % (prefix[:40], len(hits)))
    before = _numstat(p)
    lines[hits[0] + 1:hits[0] + 1] = list(new_lines)
    p.write_bytes("\n".join(lines).encode("utf-8"))
    return check_delta(p, before, expect_diff)


def check_diff(path, expect=None):
    """★把"改完要看 diff 行数"变成**函数**✗★（★P175 的另一半 ✓★）"""
    got = _numstat(Path(path))
    if expect is not None and tuple(expect) != got:
        raise UnsafeEdit("★diff 行数不符✗★：期望 %s ✗ 实测 (加,删)=%s ⇒ ★这次改动**比你想的大** ✗ "
                         "立刻用 `git diff` 看清楚 ✓★" % (tuple(expect), got))
    return got


if __name__ == "__main__":
    print("★safe_edit 自检✗★（在一个临时文件上 ✓ 不碰 docs ✓）")
    tmp = ROOT / "tmp" / "_safe_edit_probe.txt"
    tmp.write_bytes("甲\n乙\n甲\n".encode("utf-8"))
    try:
        replace_unique(tmp, "甲", "丙")
        print("  ★不该到这里✗★：锚命中 2 次却没抛 ✓")
    except UnsafeEdit as e:
        print("  ① ✓ 命中 2 次 ⇒ 抛了：%s" % str(e).splitlines()[0][:70])
    replace_unique(tmp, "乙", "丁")
    print("  ② ✓ 命中 1 次 ⇒ 改了（现在：%r）" % tmp.read_text(encoding="utf-8").strip())
    try:
        patch_line(tmp, "甲", "戊")
        print("  ★不该到这里✗★：行首锚 2 行却没抛 ✓")
    except UnsafeEdit as e:
        print("  ③ ✓ 行首锚 2 行 ⇒ 抛了：%s" % str(e).splitlines()[0][:70])
    tmp.unlink()
    print("  ✓ 临时文件已删 ✓")
