#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_repair.py — 自测网关的 repair_cc_text（CC 上报乱码还原）

背景见 agent_gateway.py 里 repair_cc_text 的注释：
CC:Tweaked 的 textutils.serializeJSON 会把 0x7F-0xFF 的每个字节转义成 \\u00XX，
导致 UTF-8 中文在上报时变成 Latin-1 双重编码。

用法：
    py tools/test_repair.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
GW = os.path.join(os.path.dirname(HERE), "gateway", "agent_gateway.py")

spec = importlib.util.spec_from_file_location("gw_mod", GW)
mod = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
spec.loader.exec_module(mod)                          # type: ignore[union-attr]
repair = mod.repair_cc_text

CN = "我是外部 Agent"
# 模拟 CC 的 serializeJSON：每个 UTF-8 字节 -> \u00XX
mojibake_json = json.dumps(CN, ensure_ascii=True)
escaped = "".join("\\u%04X" % b for b in CN.encode("utf-8"))
cc_payload = json.loads('"%s"' % escaped)

cases = [
    ("CC 上报的双重编码中文", cc_payload, CN),
    ("上层嵌套 dict/list", {"result": {"said": cc_payload}, "list": [cc_payload]}, None),
    ("纯 ASCII 必须原样", "hello world", "hello world"),
    ("正常 Unicode 中文必须原样", CN, CN),
    ("Latin-1 文本必须原样", "café", "café"),
    ("空串", "", ""),
]

fails = 0
print("=" * 60)
print("repair_cc_text 自测")
print("=" * 60)
print("模拟输入（CC 逐字节转义后）：", escaped)
print("Python 解出来是：", repr(cc_payload))
print("还原后：", repair(cc_payload))
print("-" * 60)

for name, value, expect in cases:
    got = repair(value)
    if expect is None:
        # 嵌套用例：只检查里面的字符串被还原
        inner = got["result"]["said"] if isinstance(got, dict) else None
        ok = inner == CN and got["list"][0] == CN
    else:
        ok = got == expect
    print("  [%s] %s -> %r" % ("OK" if ok else "FAIL", name, got))
    if not ok:
        fails += 1

print("-" * 60)
print("结论：%s" % ("全部通过 ✓" if fails == 0 else "%d 项失败 ✗" % fails))
raise SystemExit(1 if fails else 0)
