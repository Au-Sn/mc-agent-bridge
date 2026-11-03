#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_surface.py —— ★把 `mc_mcp.py` 暴露的**工具面**导出来，用来做"重构前后接口不变"的对账✗★

WHY（为什么非它不可 ✗）：
  拆 god file（`tools/mc_mcp.py` ✓ 约 2800 行 ✓ P91 被毁过一次 ✓）最容易出的事**不是报错** ✗
  而是★**接口悄悄变了**✗★：少一件工具 ✓ 丢一个参数 ✓ 描述改了字 ✓ ——
  这些**都不会让 py_compile 报错** ✗ 也**不会让任何现有判据变红** ✗
  而工具名与说明**就是大脑直接读的那些字** ✗（P91 的教训正是"必须一字不改" ✓）
  ⇒ ★所以要有"逐字节对账"✗★：改之前导一份，改之后导一份，**必须完全一样** ✓

★为什么它能当离线判据✗★：`initialize` 与 `tools/list` **根本不碰世界** ✓
  （只有 `tools/call` 才会去发 `dsh*` 指令 ✓）⇒ **不需要游戏** ✓ 秒级 ✓

判据（跑之前先写 ✓）：
  S1 能握手：`initialize` 回来 ✓ 且 `serverInfo.name == "mc-bridge"`
  S2 工具面**稳定**：同一份代码连导两次 ⇒ **逐字节相同** ✓（不稳定 ⇒ 后面所有对账都没意义 ✗）
  S3 `tools/list` 条目数 **>= 41** ✓（防"导了个空壳"✗ —— 空洞绿正是本项目最恨的 ✓）

用法 ✓：
  py tools/mcp_surface.py --dump tmp/surface.json    # 导一份基线
  py tools/mcp_surface.py --diff tmp/surface.json    # ★与基线比 ⇒ 必须逐字节相同✗★
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MC = ROOT / "tools" / "mc_mcp.py"


def say(s=""):
    print(s, flush=True)


def surface() -> str:
    """起一个 `mc_mcp.py`，走一遍 initialize + tools/list，返回**规范化**后的文本 ✓"""
    p = subprocess.Popen([sys.executable, str(MC)], cwd=str(ROOT),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL,
                         text=True, encoding="utf-8", errors="replace")
    try:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        p.stdin.write(json.dumps(init) + "\n")
        p.stdin.flush()
        line1 = p.stdout.readline()
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
        p.stdin.flush()
        line2 = p.stdout.readline()
    finally:
        try:
            p.kill()
        except Exception:
            pass
    if not line1 or not line2:
        raise RuntimeError("no reply from mc_mcp (line1=%r line2=%r)" % (line1[:80], line2[:80]))
    r1 = json.loads(line1).get("result", {})
    r2 = json.loads(line2).get("result", {})
    tools = sorted(r2.get("tools", []), key=lambda t: t.get("name", ""))
    # ★规范化✗★：键排序 ＋ 固定缩进 ⇒ 两次导出可比 ✓（不依赖 dict 顺序 ✓）
    canon = {
        "protocolVersion": r1.get("protocolVersion"),
        "serverInfo": r1.get("serverInfo"),
        "count": len(tools),
        "tools": tools,
    }
    return json.dumps(canon, ensure_ascii=False, sort_keys=True, indent=1)


def crit() -> int:
    """S1/S2/S3 ✓"""
    ok = True
    a = surface()
    j = json.loads(a)
    s1 = (j.get("serverInfo") or {}).get("name") == "mc-bridge"
    say("S1 握手：serverInfo=%s => %s" % (j.get("serverInfo"), s1))
    b = surface()
    s2 = (a == b)
    say("S2 稳定：连导两次逐字节相同 = %s => %s" % (s2, s2))
    n = int(j.get("count") or 0)
    s3 = n >= 41
    say("S3 条目数：%d（要求 >= 41）=> %s" % (n, s3))
    ok = s1 and s2 and s3
    say("---- S1=%s S2=%s S3=%s ----" % (s1, s2, s3))
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv) -> int:
    if "--dump" in argv:
        out = Path(argv[argv.index("--dump") + 1])
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        txt = surface()
        out.write_text(txt, encoding="utf-8", newline="\n")
        say("dumped %d bytes -> %s" % (len(txt.encode("utf-8")), out))
        say("tools = %d" % json.loads(txt)["count"])
        return 0
    if "--diff" in argv:
        base = Path(argv[argv.index("--diff") + 1])
        if not base.is_absolute():
            base = ROOT / base
        if not base.is_file():
            say("no baseline: %s（先 --dump 一份 ✓）" % base)
            return 2
        old = base.read_text(encoding="utf-8")
        new = surface()
        if old == new:
            say("S4 对账：与基线**逐字节相同** ✓ => PASS（tools = %d）"
                % json.loads(new)["count"])
            return 0
        ol, nl = old.splitlines(), new.splitlines()
        say("S4 对账：★与基线不同✗★  old=%d 行  new=%d 行" % (len(ol), len(nl)))
        shown = 0
        for i in range(max(len(ol), len(nl))):
            a = ol[i] if i < len(ol) else "<缺>"
            b = nl[i] if i < len(nl) else "<缺>"
            if a != b:
                say("  第一处不同（第 %d 行）：" % (i + 1))
                say("     old: %s" % a[:200])
                say("     new: %s" % b[:200])
                shown += 1
                break
        # 再给一份"工具名集合"的差
        try:
            on = {t["name"] for t in json.loads(old)["tools"]}
            nn = {t["name"] for t in json.loads(new)["tools"]}
            if on != nn:
                say("  工具名差：少了 %s ｜ 多了 %s" % (sorted(on - nn), sorted(nn - on)))
        except Exception as e:      # ★★§79.403✗★★ 判据里**读坏就跳过比较** ⇒ **假绿**✗★
            say("  ★工具名对账**读坏了** ✗ 不能当作没差：%r" % (e,))
            ok[0] = False           # ★判据：读坏 ⇒ **红** ✗ 不是"跳过"✗★ ✓
        return 1
    return crit()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
