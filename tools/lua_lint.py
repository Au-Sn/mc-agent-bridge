#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lua_lint.py — 轻量 Lua 5.1 词法检查器（无依赖）

用途：在没有 lua/luac 的环境下，先卡住最常见的语法错误与跨语言笔误：
  1. 圆括号/方括号/花括号不平衡
  2. 字符串未闭合（含 [[ ]] 长字符串）
  3. 长注释未闭合
  4. 块关键字粗略配平（function/if/for/while/do ... end）—— 仅作 WARNING
  5. **跨语言习惯规则**（硬错误）：`"x" * 5`、`!=`、`&&`、`None`、`+=`、行首 `#` 等
     —— 这一组来自真实事故：`print("=" * 52)` 在 Lua 里是
     `attempt to perform arithmetic on a string value`，词法检查抓不到，
     结果在游戏里第一次运行就崩（见 docs/lessons-learned.md B14）
  6. Python/JS 方法名等可疑写法（WARNING，需人工确认）

它不做真正的语法树解析，因此**不能替代 luac -p**。能过这关说明"不太可能一眼就崩"，
上线前仍建议在游戏里跑一次。

用法：
    python tools/lua_lint.py cc-tweaked/agent_bridge.lua
    python tools/lua_lint.py cc-tweaked/*.lua
"""

from __future__ import annotations

import re
import sys

# Windows 控制台常是 GBK，强制 UTF-8 避免中文/符号报 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def mask_code(src: str) -> str:
    """把注释与字符串【内容】替换成空格（保留引号、换行与总长度）。

    这样对"代码本体"做正则匹配时，不会误报注释/文案里的字眼；
    同时字符串字面量本身仍然可见（引号保留），所以
    `"..." * 5` 这类"把字符串写进表达式"的错法依然能抓到。
    """
    out = list(src)
    n = len(src)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    while i < n:
        if src.startswith("--[[", i):
            end = src.find("]]", i + 4)
            end = n if end < 0 else end + 2
            blank(i, end)
            i = end
            continue
        if src.startswith("--", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if src.startswith("[[", i):
            end = src.find("]]", i + 2)
            end = n if end < 0 else end + 2
            blank(i, end)
            i = end
            continue
        c = src[i]
        if c == '"' or c == "'":
            j = i + 1
            closed = False
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "\n":
                    break
                if src[j] == c:
                    closed = True
                    break
                j += 1
            if closed:
                blank(i + 1, j)      # 保留两端的引号
                i = j + 1
            else:
                i += 1
            continue
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# 语义 / 跨语言习惯规则（真实事故驱动）
#
# 起因：agent_bridge.lua 里写了 print("=" * 52)。
#   Lua **没有** "字符串 × 数字" 这种重复语法（那是 Python / PowerShell 的习惯），
#   运行到该行直接抛 "attempt to perform arithmetic on a string value"，
#   而当时的 lua_lint 只做词法检查（括号/字符串/注释平衡），完全抓不到。
# 本机没有 lua/luac 可执行文件 → **无法真正执行验证**，所以必须靠规则兜住这类写法。
# ---------------------------------------------------------------------------
IDIOM_RULES = [
    (r'"\s*\*\s*\d',
     "ERROR",
     'Lua 没有「字符串 × 数字」的重复语法，请用 string.rep("x", n)；'
     '否则运行时抛 attempt to perform arithmetic on a string value'),
    (r'"\s*\+\s*[%w_("]',
     "ERROR",
     "Lua 字符串拼接用 .. 而不是 +"),
    (r'!=',
     "ERROR",
     "Lua 的「不等于」写作 ~= ，不是 !="),
    (r'&&|\|\|',
     "ERROR",
     "Lua 没有 && / ||，请用 and / or"),
    (r'\b(None|True|False|null|NULL|undefined|NaN)\b',
     "ERROR",
     "Lua 没有这个字面量：应使用 nil / true / false"),
    (r'\+=' r'|-=' r'|\*=' r'|/=' r'|\+\+',
     "ERROR",
     "Lua 不支持复合赋值（+= 等）与自增运算符"),
    (r'^\s*#',
     "ERROR",
     "Lua 的注释是 -- ；# 是取长度运算符，不能当注释用"),
    (r'\b(len|str|int|float|range|dict|list|tuple|repr|enumerate|zip|type_)\s*\(',
     "WARN",
     "疑似 Python 内建函数，Lua 里没有（除非你自己定义了同名函数）"),
    (r'\b(os\.path|time\.sleep|sys\.|re\.|json\.loads)',
     "WARN",
     "疑似 Python 模块，Lua 里不存在"),
    (r'(?<!table)\.(append|strip|lstrip|rstrip|split|startswith|endswith|items|keys|values|sort|push|length|size)\(',
     "WARN",
     "疑似 Python/JS 方法；Lua 的字符串方法只有 :sub :gsub :find :match :rep :format :upper :lower :len 等"
     "（注意 table.sort/table.insert 是正牌 Lua，已排除）"),
    (r'\b(switch|case|default|try|catch|finally|throw|extends|implements|public|private|void|static)\b',
     "WARN",
     "疑似其它语言的关键字"),
    # ⚠ 最值钱的一条（真实事故）：把 Lua **保留字**当成字段名 ✗
    #    `args.local` → `<name> expected near 'local'`，解析器直接拒绝整个文件 ✗
    #    这类错误词法完全合法、只在编译时才暴露，本机没有 Lua 解释器时极难发现。
    # 注意：必须是同一行内匹配（用 [ \t]* 而不是 \s*），否则会把"注释行末的 . +
    #      下一行开头的 local"误判成字段访问 ✗（真实误报过）。
    # 注意：goto 在 Lua 5.1 / CC 的 Cobalt 里**不是**保留字（`ACT.goto` 能正常加载 ✓），
    #      所以只给 WARN，避免噪音。
    (r'\.[ \t]*(and|break|do|else|elseif|end|false|for|function|if|in|local|nil|not|or|repeat|return|then|true|until|while)\b',
     "ERROR",
     "Lua 保留字不能用作字段名（点号后必须是名字）：`x.local` ✗ 会报 "
     "<name> expected near 'local'；请改成 x[\"local\"] 或换个参数名（如 localname）"),
    (r'\.[ \t]*goto\b',
     "WARN",
     "`goto` 在 Lua 5.2+ 是保留字（Lua 5.1 / CC 的 Cobalt 里不是）。"
     "若将来换到 5.2+ 环境，`x.goto` 会变成语法错误 ✗"),
    # ⚠ 犯过两次的错（真实事故）：pcall 吞掉多返回值 ✗
    #    commands.exec 返回 (成功标志, 输出表, 结果码) 三个值；
    #    写成 `local ok, out = pcall(commands.exec, cmd)` 只接住第一个返回值，
    #    out 其实是布尔 `true`，于是：
    #      · A.cmd   → 三条完全不同的指令都回传 "true"（输出被吞掉）
    #      · A.bot_inv → 背包永远解析出 0 件物品（"手上没工具"，退化成徒手砍树）
    #    两次都是靠"回传结果明显不合理"才发现的，代价是好几轮往返。
    #    正确写法：用 packReturns(...) 接全，再按下标取值。
    #    ⚠ 只针对 commands.exec：它返回 3 个值。
    #      commands.getBlockInfo 只返回 1 个（表），用两个变量接是**正确**的写法，
    #      所以规则用 \b 卡住 exec 这个词尾（不会误伤 execAsync / getBlockInfo）。
    #      加规则时先自测命中、再看真实文件有没有误报——这次就是靠这一步发现的误报。
    (r'local\s+\w+\s*,\s*\w+\s*=\s*pcall\(\s*commands\.exec\b',
     "ERROR",
     "pcall 只声明两个变量会丢掉多余返回值：commands.exec 返回 "
     "(成功标志, 输出表, 结果码)。请用 packReturns(pcall(commands.exec, ...)) 接全，"
     "再取 p[2] / p[3]"),
    # ⚠ 最惨的一次事故：`{...}[k]` —— Lua **不允许对表构造式直接取下标** ✗
    #    报错原文：`unexpected symbol near '['` / `Unexpected '['. Expected a statement.`
    #    危害特别大：这是**解析级**错误 → 整个程序一行都没跑 →
    #    开机脚本回退到旧副本 → 机器停在 shell → 外部看到的是"指令成功、世界毫无变化"，
    #    极容易误判成"作业卡住"或"回传丢失"（我为此浪费了好几轮 ✗）。
    #    正确写法：用括号包起来 —— `({...})[k]`
    (r'\}[ \t]*\[',
     "ERROR",
     "Lua 不允许对表构造式直接取下标：`{...}[k]` 会报 unexpected symbol near '['。"
     "请写成 `({...})[k]`（变量或函数返回值取下标则没问题）"),
]


def check_idioms(src: str):
    """返回 [(行号, 级别, 说明, 片段)]，按行号排序。"""
    masked = mask_code(src)
    found = []
    for pat, level, msg in IDIOM_RULES:
        for m in re.finditer(pat, masked):
            ln = masked.count("\n", 0, m.start()) + 1
            found.append((ln, level, msg, m.group(0).strip()))
    found.sort(key=lambda x: (x[0], x[1]))
    return found


def check(path: str) -> int:
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()

    i, n = 0, len(src)
    line = 1
    stack = []            # (char, line)
    problems = []
    kw_open = 0           # 块开启计数（启发式）
    kw_end = 0

    pairs = {")": "(", "]": "[", "}": "{"}

    def err(msg, ln):
        problems.append((ln, msg))

    while i < n:
        c = src[i]

        if c == "\n":
            line += 1
            i += 1
            continue

        # 长注释 / 长字符串  --[[ ... ]]  [[ ... ]]
        if src.startswith("--[[", i) or src.startswith("[[", i):
            start = i + (4 if src.startswith("--[[", i) else 2)
            startln = line
            end = src.find("]]", start)
            if end < 0:
                err("长注释/长字符串未闭合（缺少 ]]）", startln)
                break
            line += src.count("\n", i, end + 2)
            i = end + 2
            continue

        # 行注释
        if src.startswith("--", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue

        # 普通字符串
        if c == '"' or c == "'":
            startln = line
            j = i + 1
            closed = False
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "\n":
                    break
                if src[j] == c:
                    closed = True
                    break
                j += 1
            if not closed:
                err("字符串未闭合（行末仍在 %s 内）" % c, startln)
                break
            i = j + 1
            continue

        # 括号
        if c in "([{":
            stack.append((c, line))
            i += 1
            continue
        if c in ")]}":
            if not stack:
                err("多余的闭合符号 %s" % c, line)
            else:
                op, oln = stack.pop()
                if op != pairs[c]:
                    err("括号不匹配：第 %d 行 %s 与第 %d 行 %s" % (oln, op, line, c), line)
            i += 1
            continue

        # 块关键字（粗略）
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            # 计数规则：function / if / repeat 直接算一个开启；
            # **独立 `do ... end` 块** 由 `do` 计入 ✓，而 for / while 各自已经带一个 `do`，
            # 所以**不单独计 for/while**（否则重复计数 ✗）。
            # 之前漏掉独立 do 块，导致"多一个 end"的假警报（真实踩过）。
            if word in ("function", "if", "repeat", "do"):
                kw_open += 1
            elif word == "end":
                kw_end += 1
            elif word == "until":
                kw_end += 1
            i = j
            continue

        i += 1

    for op, oln in stack:
        err("未闭合的 %s（第 %d 行打开）" % (op, oln), oln)

    print("=" * 60)
    print("检查：%s" % path)
    if problems:
        for ln, msg in problems:
            print("  [X] 第 %d 行：%s" % (ln, msg))
    else:
        print("  [OK] 定界符/字符串/注释：全部平衡")

    diff = kw_open - kw_end
    if diff != 0:
        print("  [!] 块关键字启发式：open=%d end/until=%d（差 %+d）"
              "—— 仅提示，可能是 function 简写或 elseif 造成的统计偏差"
              % (kw_open, kw_end, diff))
    else:
        print("  [OK] 块关键字启发式：平衡（function/if/for/while/do/repeat = end/until）")

    # ---- 语义 / 跨语言习惯（真实事故驱动，见 IDIOM_RULES 上方注释）----
    idioms = check_idioms(src)
    errs = [x for x in idioms if x[1] == "ERROR"]
    warns = [x for x in idioms if x[1] == "WARN"]
    if errs:
        print("  [X] 跨语言习惯检查：%d 处【会直接运行期失败】" % len(errs))
        for ln, _lv, msg, snip in errs:
            print("        第 %d 行  【%s】\n            %s" % (ln, snip, msg))
    else:
        print("  [OK] 跨语言习惯检查：未发现必崩写法（字符串×数字 / != / && / None / += 等）")
    if warns:
        print("  [!] 可疑写法 %d 处（人工确认，不一定是错）：" % len(warns))
        for ln, _lv, msg, snip in warns[:12]:
            print("        第 %d 行  【%s】  %s" % (ln, snip, msg))
        if len(warns) > 12:
            print("        …还有 %d 处" % (len(warns) - 12))

    return 1 if (problems or errs) else 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    rc = 0
    for p in argv:
        rc |= check(p)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
