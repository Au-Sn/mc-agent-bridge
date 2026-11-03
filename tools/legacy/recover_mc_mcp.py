"""recover_mc_mcp.py -- 把被 PowerShell 编码往返弄坏的文件"逆变换"回来

事故（我自己造的 ✗ 2026-09-23 ✓）：
  我用 `Get-Content -Raw`（**没带 -Encoding** ✓）读 `tools/mc_mcp.py` ✓
  ⇒ PowerShell 5.1 按**本机 ANSI（cp936）**解码 UTF-8 字节 ✗
  ⇒ 再用 `Set-Content -Encoding utf8` 写回 ⇒ **所有非 ASCII 文本全花** ✗
  （这正是本项目 P39/P47 反复记的那一条 ✗ —— 我又犯了 ✓）

逆变换 ✓：`坏文件按 UTF-8 读` → `按 cp936 编码回字节` → `按 UTF-8 解码` = 原文 ✓
  只有在"某个字节对不上 cp936"时才会丢 ✓ 所以要**逐行检查可疑字符**（U+FFFD 与 '?' ✓）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
SRC = ROOT / "tools" / "mc_mcp.py"
DST = ROOT / "tools" / "mc_mcp.recovered.py"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> int:
    bad_text = SRC.read_text(encoding="utf-8", errors="replace")
    try:
        raw = bad_text.encode("cp936", errors="strict")
        mode = "strict"
    except Exception as e:
        print("strict 失败（%s）⇒ 用 replace 试" % type(e).__name__)
        raw = bad_text.encode("cp936", errors="replace")
        mode = "replace"
    try:
        good = raw.decode("utf-8", errors="strict")
        umode = "strict"
    except Exception as e:
        print("utf-8 解码 strict 失败（%s）⇒ 用 replace" % type(e).__name__)
        good = raw.decode("utf-8", errors="replace")
        umode = "replace"
    DST.write_text(good, encoding="utf-8", newline="\n")
    n_bad = good.count("\ufffd")
    print("编码方式 cp936/%s → utf-8/%s" % (mode, umode))
    print("还原后长度 %d（坏文件 %d）" % (len(good), len(bad_text)))
    print("替换字符 U+FFFD 个数 = %d ⇒ %s" % (n_bad, "可能无损 ✓" if n_bad == 0 else "★有损 ✗★"))
    # 抽几行看看中文对不对
    for i, ln in enumerate(good.splitlines(), 1):
        if i in (1, 2, 3, 76, 100):
            print("  L%-4d %s" % (i, ln[:100]))
    return 0 if n_bad == 0 else 1


raise SystemExit(main())
