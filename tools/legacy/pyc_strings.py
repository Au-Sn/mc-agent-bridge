"""pyc_strings.py -- 把 .pyc 里**每件工具的名字/说明/schema 文本**掏出来写成 JSON（重写文件的依据 ✓）

说明 ✓：`tools/mc_mcp.py` 被我自己的编码往返弄坏了 ✗（注释与非 ASCII 文本花了 ✓ 代码结构还在但**没法解析** ✗）
  ⇒ 唯一"没有失真"的副本是 `tools/__pycache__/mc_mcp.cpython-314.pyc`（19:57:32 ✓ 早于事故 19:59:40 ✓）
  ⇒ 这个脚本把它里面的**字符串常量**全倒出来 ✓ 重写文件时逐字对齐 ✓
"""
from __future__ import annotations

import json
import marshal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
PYC = ROOT / "tools" / "__pycache__" / "mc_mcp.cpython-314.pyc"
OUT = ROOT / "logs" / "mc_mcp_pyc_strings.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def walk(co, depth=0, acc=None):
    acc = acc if acc is not None else []
    strs = [c for c in co.co_consts if isinstance(c, str)]
    acc.append({"depth": depth, "name": co.co_name,
                "consts": [c for c in co.co_consts if isinstance(c, str)],
                "nested": [x.co_name for x in co.co_consts if hasattr(x, "co_name")]})
    for c in co.co_consts:
        if hasattr(c, "co_name"):
            walk(c, depth + 1, acc)
    return acc


def main() -> int:
    co = marshal.loads(PYC.read_bytes()[16:])
    acc = walk(co)
    OUT.write_text(json.dumps(acc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("倒出 %d 个代码对象 ⇒ %s" % (len(acc), OUT.name))
    # 顶层：把工具名字/说明按出现顺序列出来（TOOLS 表用的都是模块级常量 ✓）
    mod = acc[0]
    names = [c for c in mod["consts"] if c.startswith(("bot_", "walk_", "come_", "look", "dig_",
                                                       "place_", "use_", "equip", "scan",
                                                       "harvest", "sift", "say", "stop", "idle",
                                                       "go_to_", "chest_", "map_", "find_",
                                                       "plan_", "safe_", "survey", "remember",
                                                       "job_")) and len(c) < 24 and " " not in c]
    print("模块级疑似工具名 %d 个：" % len(names))
    print("  " + ", ".join(names))
    print("模块级长字符串 %d 条（前 8 条预览）：" % len([c for c in mod["consts"] if len(c) > 40]))
    for c in [c for c in mod["consts"] if len(c) > 40][:8]:
        print("   |" + c[:110].replace("\n", " "))
    return 0


raise SystemExit(main())
