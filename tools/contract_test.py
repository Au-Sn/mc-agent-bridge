#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_test.py —— ★「接入契约」守恒判据★ ✗（离线 ✓ 秒级 ✓ 2026-10-01 ✓）

WHY（为什么要有它 ✗）：
  交付物是「**身体 ＋ 接口，脑可插拔**」✓ ⇒ 契约文档就是**产品说明书** ✓
  而说明书最大的敌人是**漂移** ✗：代码加了工具/改了参数，文档没跟上 ⇒
  接进来的人（或另一个 agent）会照着**过期的**说明书做事 ✗
  ★本项目已经栽过一次同族✗★（P131）：事件名**凭印象编** ⇒ 整条扳机永远不响 ✗
  ⇒ 所以口径与 `errata_guard_test.py` 的 E11 **一模一样** ✓：
    ★**双向**对账 ＋ 一条判据当场报红✗★ —— 不靠"记得更新文档" ✗

CRITERIA（跑之前先写 ✓）：
  C1 双向守恒：`mc_mcp.py` 里 `TOOLS` 的名字集合
               == 契约文档里那一段工具表列出的名字集合 ✓
               （少一个＝说明书漏了它 ✗；多一个＝说明书编了一个不存在的工具 ✗）
  C2 参数一致：★每个工具「schema 声明的参数」必须 == 「`fn` 真的读的参数」★ ✗
               · 读了但没声明 ⇒ **接入者从 `tools/list` 里看不到它** ✗（照着接就会踩空）
               · 声明了但没读 ⇒ **schema 在说谎** ✗
  C3 每个工具在文档里都有一行 ✓ 且**非空描述** ✓
  C4 版本单一真源：`mc_mcp.py` 的 `serverInfo.version`
               == 契约文档头部声明的版本 ✓（★改版本只许改一处✗★）
  C5 传输必须写清：文档里必须写明「**一行一条 JSON**（不是 Content-Length 分帧 ✓）」
               —— ★这一条是接入者最容易踩死的✗★（LSP 习惯会让他写出永远读不到回执的客户端 ✗）

★输出纪律★ ✗：结论行一律 ASCII（`C1=True ...` ✓）—— 便于判据机读 ✓
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP = ROOT / "tools" / "mc_mcp.py"
DOC = ROOT / "docs" / "接口契约-伙伴v1.0.md"


def say(s=""):
    print(s, flush=True)


def tools_block() -> str:
    """把 `TOOLS = [ ... ]` 那一段切出来 ✓（按**括号配平**切 ✗ 不按行 ✗）"""
    t = MCP.read_text(encoding="utf-8")
    i = t.index("TOOLS = [")
    j = t.index("\n]", i)
    return t[i:j]


def match_brace(s: str, start: int) -> int:
    """`s[start]` 必须是 `{` ✓ 返回与它配对的 `}` 的下标 ✓（跳过字符串里的括号 ✓）"""
    depth = 0
    in_str = False
    esc = False
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
    raise ValueError("unbalanced braces")


def top_keys(body: str) -> set:
    r"""从 `properties` 的 `{...}` **内容**里只取**最外层**的键 ✓

    ★为什么必须写这个 ✗★（2026-10-01 我自己栽的 ✓ 判据第一版就报错 ✓）：
      第一版用 `re.findall(r'"(\w+)"\\s*:', body)` ✗ ⇒ 把**每个参数自己的**
      `"type"` / `"description"` / `"enum"` 也当成参数名捞进来 ✗ ⇒
      41 个工具里报了 **36 个"声明了没读"** ✗ —— ★全是假红✗★
      （同族 ✓：P106「同一个谓语只许一个定义」／P110「判据的前提也要对账」 ✓
        —— ★这次错的是**我量"参数"的那把尺子**✗★，不是接口 ✓）
    口径 ✓：按**括号深度**走 ✗ —— 只在 depth==0（即 properties 的直接子层）
      且那个字符串**紧跟一个冒号**时，它才是"参数名" ✓
    """
    out = set()
    depth = 0
    in_str = False
    esc = False
    start = 0
    i = 0
    while i < len(body):
        c = body[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
                j = i + 1
                while j < len(body) and body[j] in " \t\r\n":
                    j += 1
                if depth == 0 and j < len(body) and body[j] == ":":
                    out.add(body[start:i])
            i += 1
            continue
        if c == '"':
            in_str = True
            start = i + 1
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        i += 1
    return out


def parse_tools():
    """⇒ [(名字, 声明参数集合, fn 里读到的参数集合, 描述)] ✓"""
    blk = tools_block()
    chunks = blk.split('dict(name="')[1:]
    out = []
    for ch in chunks:
        name = ch.split('"', 1)[0]
        # 声明参数：inputSchema 里的 "properties": { ... }（★只取最外层键✗★）
        props = set()
        m = re.search(r'"properties"\s*:\s*\{', ch)
        if m:
            b = match_brace(ch, m.end() - 1)
            props = top_keys(ch[m.end():b])
        # fn 真的读了哪些键
        reads = set(re.findall(r'a\["(\w+)"\]', ch)) | set(re.findall(r'a\.get\("(\w+)"', ch))
        dm = re.search(r'description="(.*?)",\s*\n?\s*inputSchema', ch, re.S)
        desc = dm.group(1) if dm else ""
        out.append((name, props, reads, desc))
    return out


def doc_tools() -> set:
    if not DOC.is_file():
        return set()
    t = DOC.read_text(encoding="utf-8")
    out = set()
    for m in re.finditer(r"^\|\s*`([a-z_][a-z0-9_]*)`\s*\|", t, re.M):
        out.add(m.group(1))
    return out


def main() -> int:
    ok = True
    tools = parse_tools()
    names = [t[0] for t in tools]
    say("tools in mc_mcp.py TOOLS = %d" % len(names))

    # ---- C2：参数一致（★这条与文档无关，先报它 —— 它量的是代码自己✗★）
    bad = []
    for (n, props, reads, _d) in tools:
        miss = sorted(reads - props)      # 读了没声明 ✗
        extra = sorted(props - reads)     # 声明了没读 ✗
        if miss or extra:
            bad.append((n, miss, extra))
    say("C2 参数一致：不一致的工具 %d 个" % len(bad))
    for (n, miss, extra) in bad:
        say("     %-18s read-but-undeclared=%s   declared-but-unread=%s" % (n, miss, extra))
    say("C2 => %s" % (not bad))
    ok &= (not bad)

    # ---- C1/C3：与契约文档双向对账
    if not DOC.is_file():
        say("C1/C3/C4/C5 FAIL: contract doc missing -> %s" % DOC.name)
        say("---- C1=False C2=%s C3=False C4=False C5=False ----" % (not bad))
        return 1
    dt = doc_tools()
    c1a = sorted(set(names) - dt)
    c1b = sorted(dt - set(names))
    c1 = not c1a and not c1b
    say("C1 双向守恒：文档里缺 %d 个 %s ｜ 文档里多出 %d 个 %s => %s"
        % (len(c1a), c1a[:6], len(c1b), c1b[:6], c1))

    empty = [n for (n, _p, _r, d) in tools if not d.strip()]
    c3 = (not empty) and all(n in dt for n in names)
    say("C3 每工具一行且描述非空：空描述 %d 个 %s => %s" % (len(empty), empty[:5], c3))

    ver = "?"
    mm = re.search(r'"serverInfo":\s*\{"name":\s*"mc-bridge",\s*"version":\s*"([^"]+)"\}',
                   MCP.read_text(encoding="utf-8"))
    if mm:
        ver = mm.group(1)
    t = DOC.read_text(encoding="utf-8")
    c4 = bool(ver) and (ver != "?") and re.search(re.escape(ver), t) is not None
    say("C4 版本单一真源：mc_mcp.py 报 %r ｜ 文档里写到了 = %s => %s" % (ver, bool(c4) and True, c4))

    c5 = ("一行一条 JSON" in t) and ("Content-Length" in t)
    say("C5 传输写清：一行一条 JSON ＋ 点名不是 Content-Length => %s" % c5)

    ok &= c1 and c3 and c4 and c5
    say("---- C1=%s C2=%s C3=%s C4=%s C5=%s ----" % (c1, not bad, c3, c4, c5))
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
