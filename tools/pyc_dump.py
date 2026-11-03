"""pyc_dump.py -- 从"损坏前编译好的" .pyc 里把**真字符串与结构**掏出来（救文件 ✓）

为什么能救 ✗：`tools/__pycache__/mc_mcp.cpython-314.pyc` 的时间戳（19:57:32）**早于**我把它弄坏的
  19:59:40 ✓ ⇒ 那份字节码是**好源码**编出来的 ✓（代码对象的常量表里存着**原样的字符串** ✓）
用途 ✓：把 31 件工具的名字 ✓ 说明 ✓ schema ✓ 和函数名顺序原样还原 ⇒ 重写文件时**不丢信息** ✓
"""
from __future__ import annotations

import dis
import importlib.util
import marshal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYC = ROOT / "tools" / "__pycache__" / "mc_mcp.cpython-314.pyc"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def code_from_pyc(p: Path):
    data = p.read_bytes()
    # 3.7+ 头部 16 字节（magic4 + flags4 + mtime4 + size4）
    return marshal.loads(data[16:])


def walk(co, depth=0, out=None):
    out = out if out is not None else []
    out.append((depth, co.co_name, co))
    for c in co.co_consts:
        if hasattr(c, "co_name"):
            walk(c, depth + 1, out)
    return out


def main() -> int:
    if not PYC.is_file():
        print("no pyc")
        return 2
    co = code_from_pyc(PYC)
    items = walk(co)
    print("== 顶层代码对象里的函数/类顺序（%d 项）==" % len(items))
    for depth, name, c in items:
        if depth <= 1:
            print("  " * depth + name)
    print()
    print("== 顶层字符串常量（前 60）==")
    for s in co.co_consts:
        if isinstance(s, str) and len(s) > 8:
            print("  " + s[:150].replace("\n", " "))
    print()
    # 把 TOOLS 那段（列表常量）单独找出来：它是个 tuple of dicts ✗（不可 marshal 重建 ✓ 但常量在）
    for depth, name, c in items:
        consts = [x for x in c.co_consts if isinstance(x, str) and len(x) > 20]
        if name.startswith("t_") or name == "<module>":
            if consts:
                print("== %s（%d 条长字符串）==" % (name, len(consts)))
                for s in consts[:40]:
                    print("   |" + s[:160].replace("\n", " "))
    return 0


raise SystemExit(main())
