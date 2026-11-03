#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cfg_check.py —— ★把 `dsh --dump-config` 的组成树**认真解析**一遍★

为什么要有它 ✗（刚踩的坑 ✓）：
  我第一次是拿 PowerShell 的字符串匹配去查"某个 id 后面有没有 disabled"✗
  ⇒ 得出**反的结论**（"禁用没生效"✗）而 dump 里明明写着 `patched by …` ✓
  ⇒ 纪律：**判定要写成代码，别用眼睛** ✗（本项目错题本里那一类"我的测试有瑕疵" ✓）

用法：
    py tools/cfg_check.py <dump 文件>                 # 列出「被本层补丁动过」的条目 + disabled 状态
    py tools/cfg_check.py <dump 文件> tool-pwsh look  # 只看这几个 id
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROW = re.compile(r"^- id: (\S+)\s*$")
SEC = re.compile(r"^# == (.*)$")


def read_any(path: str) -> tuple[str, str]:
    """★按字节读，再逐个试编码★ ✗ —— 实测环境事实（2026-09-20 ✓）：

    PowerShell 的 `>` 重定向写出来的是 **UTF-16LE ＋ BOM**（`\\xff\\xfe` ✓）
    而不是 UTF-8 ✗ ⇒ 拿 `read_text(encoding='utf-8')` 去读 ⇒ **一行都匹配不上** ✗
    而且它**不报错**（errors='replace' 会把 NUL 塞进字符串 ✓）⇒ 表现成"0 个条目"✗
    ⇒ 这类"沉默的错"最贵 ✗（本项目的纪律：失败要大声 ✓）
    """
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16", "utf-8", "gbk"):
        try:
            text = raw.decode(enc)
        except Exception:
            continue
        if "- id:" in text or "# ==" in text:
            return text, enc
    return raw.decode("utf-8", "replace"), "utf-8(replace)"


def parse(path: str) -> tuple[dict, list, str]:
    rows: dict = {}
    order: list = []
    sec = "(root)"
    cur = None
    text, enc = read_any(path)
    for line in text.splitlines():
        m = SEC.match(line)
        if m:
            sec = m.group(1)
            continue
        m = ROW.match(line)
        if m:
            cur = m.group(1)
            if cur not in rows:
                order.append(cur)
            rows.setdefault(cur, {"sec": sec, "disabled": None, "name": None})
            rows[cur].update({"sec": sec})
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("disabled:"):
            rows[cur]["disabled"] = s.split(":", 1)[1].strip()
        elif s.startswith("name:"):
            rows[cur]["name"] = s.split(":", 1)[1].strip()
    return rows, order, enc


def main(argv: list[str]) -> int:
    if not argv:
        print("用法: py tools/cfg_check.py <dump 文件> [id...]")
        return 2
    rows, order, enc = parse(argv[0])
    want = argv[1:]
    out: list[str] = []
    out.append("dump 文件编码 = %s（PowerShell 的 `>` 写出的是 UTF-16LE ✗ 见 read_any 注释 ✓）" % enc)
    out.append("条目总数 %d" % len(order))
    patched = [i for i in order if "patched by" in rows[i]["sec"]]
    out.append("被本层补丁动过的条目：%d 个" % len(patched))
    for i in patched:
        out.append("    %-24s disabled=%-28s ← %s" % (i, rows[i]["disabled"], rows[i]["sec"][:70]))
    if want:
        out.append("")
        out.append("── 指定 id 的最终状态 ──")
        for i in want:
            r = rows.get(i)
            if r is None:
                out.append("    %-24s ★不存在★（补丁里写了它 ⇒ 会打 'not found' 诊断 ✗）" % i)
            else:
                out.append("    %-24s disabled=%-28s name=%s" % (i, r["disabled"], r["name"]))
    txt = "\n".join(out)
    dest = Path(argv[0]).with_suffix(".parsed.txt")
    dest.write_text(txt, encoding="utf-8")
    print("[cfg_check] wrote %s" % dest)
    print(txt.encode("ascii", "replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
