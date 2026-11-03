#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_contract.py —— 把 `mc_mcp.py` 里的 `TOOLS` **生成**成契约文档里的工具表 ✓

WHY（为什么不让手写 ✗）：
  · 41 个工具、每个都有参数与默认值 ⇒ 手抄必然抄漏 ✓（★P132 就是"白名单手抄一份"栽的✗★）
  · 而契约文档是**接入者要照着他做事的** ✗ ⇒ 抄错一个参数名 = 让接入者踩空 ✓
  ⇒ 口径与 `errata_archive.py` **一样** ✓：**代码是唯一真源 ✗，文档是它的投影 ✗**
    （★这与 P129 同族：同一种格式只许**一把尺子**✗★）

用法 ✓：`py tools/gen_contract.py`（幂等 ✓ 只重写两个标记之间的那一段 ✓ 其余一个字不动 ✓）
判据 ✓：`py tools/contract_test.py` 每次跑都双向对账（C1~C5 ✓）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP = ROOT / "tools" / "mc_mcp.py"
DOC = ROOT / "docs" / "接口契约-伙伴v1.0.md"
BEGIN = "<!-- TOOLS-TABLE-BEGIN -->"
END = "<!-- TOOLS-TABLE-END -->"


def match_brace(s: str, start: int) -> int:
    depth, in_str, esc = 0, False, False
    for k in range(start, len(s)):
        c = s[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return k
    raise ValueError("unbalanced")


def rows():
    t = MCP.read_text(encoding="utf-8")
    i = t.index("TOOLS = [")
    blk = t[i:t.index("\n]", i)]
    out = []
    for ch in blk.split('dict(name="')[1:]:
        name = ch.split('"', 1)[0]
        dm = re.search(r'description="(.*?)",\s*\n?\s*inputSchema', ch, re.S)
        desc = (dm.group(1) if dm else "").replace("|", "/").replace("\n", " ")
        desc = re.sub(r"\s+", " ", desc).strip()
        # 一句话：第一个句号/分号前
        short = re.split(r"[。；;]", desc)[0][:110]
        # 参数（★只取最外层键✗★ —— 与 contract_test 同一口径 ✓）
        props, req = [], []
        m = re.search(r'"properties"\s*:\s*\{', ch)
        if m:
            b = match_brace(ch, m.end() - 1)
            body = ch[m.end():b]
            depth, in_str, esc, start = 0, False, False, 0
            k = 0
            while k < len(body):
                c = body[k]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                        j = k + 1
                        while j < len(body) and body[j] in " \t\r\n":
                            j += 1
                        if depth == 0 and j < len(body) and body[j] == ":":
                            props.append(body[start:k])
                    k += 1
                    continue
                if c == '"':
                    in_str, start = True, k + 1
                elif c in "{[":
                    depth += 1
                elif c in "}]":
                    depth -= 1
                k += 1
        rm = re.search(r'"required"\s*:\s*\[([^\]]*)\]', ch)
        if rm:
            req = re.findall(r'"(\w+)"', rm.group(1))
        defaults = dict(re.findall(r'a\.get\("(\w+)",\s*([^)]+)\)', ch))
        bits = []
        for p in props:
            if p in req:
                bits.append("`%s`★必填★" % p)
            elif p in defaults:
                bits.append("`%s`=%s" % (p, defaults[p].strip()))
            else:
                bits.append("`%s`" % p)
        out.append((name, " ｜ ".join(bits) if bits else "—", short))
    return out


def main() -> int:
    if not DOC.is_file():
        print("no doc: %s" % DOC.name)
        return 2
    t = DOC.read_text(encoding="utf-8")
    if BEGIN not in t or END not in t:
        print("doc is missing the %s / %s markers" % (BEGIN, END))
        return 2
    R = rows()
    lines = ["| 工具 | 参数（★必填★ ／ 可选=默认） | 它自己怎么说（首句 ✓ 原文摘自代码 ✗） |",
             "| --- | --- | --- |"]
    for (n, params, short) in R:
        lines.append("| `%s` | %s | %s |" % (n, params, short))
    table = "\n".join(lines)
    head, rest = t.split(BEGIN, 1)
    _mid, tail = rest.split(END, 1)
    DOC.write_text(head + BEGIN + "\n\n" + table + "\n\n" + END + tail, encoding="utf-8")
    print("wrote %d tool rows into %s" % (len(R), DOC.name))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
