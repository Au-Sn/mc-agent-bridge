#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""persona.py —— ★"输入人设"的地方★（用户要求 ✓）

用户原话 ✓：「现在需要给一个输入人设的地方，好让 bot 获得这样的人设」

⇒ 一共给了**三个**入口 ✓ 都写同一个文件 ✓（所以随便从哪儿进都算数 ✓）：

| 入口 | 怎么用 | 适合 |
|---|---|---|
| **① 游戏里说一句**（最顺手 ✓） | 聊天里打 `!人设 你是个话很少的老矿工…` | 你正在玩的时候 ✓ 立刻生效 ✓ |
| ② 命令行 | `py tools/persona.py set --file 我的人设.txt` | 长文本 / 从别处粘贴 ✓ |
| ③ 直接改文件 | 编辑 `personas/current.md` | 想手改 ✓ |

★人设存在哪★ ✓：`personas/current.md`（就是"当前生效的那一个" ✓ UTF-8 ✓ 无 BOM ✓）
`talk.py` 默认就读它 ✓（没有它才退回 `personas/bot.md` ✓）
⇒ 所以"换人设"**不用重启**正在盯着聊天的 talk.py 吗 ✗ ——
   ⚠ 严格说：`talk.py` 每轮**重新读一次文件** ✓（见 `Talk.set_persona` 与 `round()` ✓）
   所以游戏里说完**当轮就生效** ✓ 不用重启 ✓

★留痕★ ✓：每次改动都往 `personas/current.meta.jsonl` 追加一条 ✓（谁改的/什么时候/多少字 ✓）
—— 本项目纪律 ✓：**改了东西要留痕** ✗ 免得以后不知道人设是怎么来的 ✓
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PDIR = ROOT / "personas"
CURRENT = PDIR / "current.md"
FALLBACK = PDIR / "bot.md"
META = PDIR / "current.meta.jsonl"
MAXLEN = 6000

# ★控制台输出必须重配成 UTF-8★ ✗ —— 实测（2026-09-20 ✓ 今天第 4 次踩 ✓）：
#   不重配 ⇒ 打中文/`✓` 到 GBK 控制台 ⇒ `UnicodeEncodeError` ⇒ **退出码变 1** ✗
#   ⇒ 看起来像"工具失败" ✗ 其实功能全对 ✓（P39/P47 一家 ✓）
try:
    sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
except Exception:
    pass


def _clean(text: str) -> str:
    """★去掉 BOM★ ✗ —— 血的教训 ✓：

    PowerShell 的 `Set-Content -Encoding UTF8` 会**加 BOM**（`\\ufeff`）✗
    ⇒ 那个 BOM 会变成**人设正文的第一个字符** ✗ 一路送到模型眼前 ✗
    ⇒ 所以：**读进来的时候就去掉** ✓（写出去的时候也顺手去掉 ✓）
    （本项目纪律 ✓：**要写文件就用 Python** ✗ 别用 PowerShell ✓ —— 我这次自己又犯了 ✗）
    """
    return (text or "").replace("\ufeff", "").strip()


def _write(text: str, source: str) -> int:
    text = _clean(text)
    if not text:
        raise SystemExit("人设是空的 ✗ ⇒ 不写（免得把现有的人设清掉 ✗）")
    if len(text) > MAXLEN:
        raise SystemExit("人设太长（%d 字 ✗ 上限 %d ✓）" % (len(text), MAXLEN))
    PDIR.mkdir(parents=True, exist_ok=True)
    CURRENT.write_text(text + "\n", encoding="utf-8", newline="\n")
    try:
        with META.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "source": source, "chars": len(text),
                                "head": text[:60]}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return len(text)


def show() -> int:
    if CURRENT.is_file():
        t = _clean(CURRENT.read_text(encoding="utf-8"))
        print("[persona] 当前人设 ← %s（%d 字）" % (CURRENT, len(t.strip())))
        print("-" * 70)
        print(t.rstrip())
        return 0
    print("[persona] ★还没有 current.md★ ✗ ⇒ talk.py 会退回 %s" % FALLBACK)
    if FALLBACK.is_file():
        print("-" * 70)
        print(FALLBACK.read_text(encoding="utf-8").rstrip())
        return 1
    return 2


def main(argv: list[str]) -> int:
    a: dict = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            a[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            a[argv[i].lstrip("-")] = True
            i += 1

    op = "show"
    for k in ("show", "set", "list", "use", "clear"):
        if a.get(k):
            op = k

    # ★位置参数补一手★ ✗（实测漏洞 ✓）：`py tools/persona.py use bot` ⇒
    #   我的参数解析器把 `use` 和 `bot` **都当成开关**了 ✗ ⇒ `a["use"] is True` ✗
    #   ⇒ 报"用法"而什么都没干 ✗（**沉默地失败** ✓ 正是本项目最恨的 ✓ 见 P45 ✓）
    #   ⇒ 补：`use <名字>` / `set <文本…>` 这种位置写法也认 ✓
    if op in ("use", "set") and not isinstance(a.get(op), str):
        rest = [x for x in argv[1:] if not x.startswith("--")]
        if rest:
            a[op] = rest[0] if op == "use" else " ".join(rest)

    if op == "list":
        PDIR.mkdir(parents=True, exist_ok=True)
        print("[persona] 目录 %s" % PDIR)
        for p in sorted(PDIR.glob("*.md")):
            mark = "★当前★" if p.name == CURRENT.name else "      "
            print("  %s %-20s %5d 字" % (mark, p.stem,
                                          len(_clean(p.read_text(encoding="utf-8")))))
        return 0

    if op == "show":
        return show()

    if op == "clear":
        if CURRENT.is_file():
            CURRENT.unlink()
            print("[persona] 已删掉 current.md ✓ ⇒ 下一轮起退回 %s" % FALLBACK.name)
        return 0

    if op == "use":
        name = a.get("use")
        if not isinstance(name, str):
            print("用法: py tools/persona.py use <名字>   （见 list ✓）")
            return 2
        src = PDIR / (name + ".md")
        if not src.is_file():
            print("[X] 没有 %s ✗" % src)
            return 2
        n = _write(src.read_text(encoding="utf-8"), "use:%s" % name)
        print("[persona] 已把 %s 设成当前人设 ✓（%d 字）" % (name, n))
        return 0

    # op == "set"
    if a.get("file"):
        p = Path(str(a["file"]))
        if not p.is_file():
            print("[X] 没有这个文件 ✗：%s" % p)
            return 2
        n = _write(p.read_text(encoding="utf-8"), "file:%s" % p.name)
        print("[persona] 已从 %s 设好 ✓（%d 字 ✓ 下一轮生效 ✓）" % (p, n))
        return 0
    if a.get("text"):
        n = _write(str(a["text"]), "text")
        print("[persona] 已设好 ✓（%d 字）" % n)
        return 0
    print("用法（三个入口挑一个 ✓）：")
    print("  py tools/persona.py show                    # 看当前人设 ✓")
    print("  py tools/persona.py list                    # 列出现成的 ✓")
    print("  py tools/persona.py use menghulu            # 用现成的某个 ✓")
    print("  py tools/persona.py set --file 我的人设.txt   # 从文件设 ✓")
    print("  py tools/persona.py set --text \"你是个…\"      # 直接给文本 ✓")
    print("  py tools/persona.py clear                   # 清掉 ⇒ 退回 bot.md ✓")
    print("★或者最顺手的那个★ ✓：游戏聊天里打  !人设 <你想要的设定>  ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
