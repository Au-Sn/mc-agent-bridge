#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
raw.py — 把游戏指令原样发给命令计算机，并打印**服务端完整回传**（不裁剪、不判断）

为什么需要它：
    调试时最常问的是"这条指令到底成功了吗？它回了什么？"
    而技能层会把回传裁成 summary（好看 ✗ 但看不到细节 ✗）；
    加上 CC 终端渲染不了 CJK（中文变 '?'）⇒ 光看回传极易误判 ✗。
    本工具**只摆事实** ✓：success / 每一行输出 / 完整 JSON ✓。

⚠ 引号纪律（真实踩过）：
    PowerShell 5.1 把带内嵌双引号的参数交给原生程序时会**吃掉反斜杠** ✗
    （实测：`{text:"{\\"a\\":1}"}` 到达进程时已经变成 `{text:{"a":1}}` ✓ —— 指令因此解析失败 ✗）
    ⇒ 凡是指令里带引号/花括号（NBT、JSON），**一律写进文件**用 `--file` ✓ 不要手拼命令行 ✗。

用法：
    py tools/raw.py "data get entity @e[tag=dsh_jade,limit=1] Pos"
    py tools/raw.py --file cmds.txt          # 一行一条指令（# 开头为注释）；**带引号就用这个**
    py tools/raw.py --who cc0 "id"           # 换一台计算机（默认 cmd0）

⚠ 这是**能改世界**的通道（它就是 /指令）：默认不拦 ✗，请自己确认指令安全 ✓。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel, BridgeError  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


# ★★2026-10-03 检修（欠账 ㊱）✗★★ ─────────────────────────────────────────────
#   ★缺的是什么✗★：`raw` 通道能直接发 `/setblock` 这类**改世界**的游戏指令 ✗
#     而代码里**没有一处**会因为"★够不着却改了世界★"而报错 ⇒ ★那条"我不做"只是我的判断✗★ ✓
#     （★来历✗★：㉘ 那颗洞我**能**隔空补 ✗ 但那样会把「**类玩家行为**」这条底线变假 ✓）
#   ★口径✗★：
#     · ★`/dsh…` 一律**放行**✗★ —— 它们是**模组里的动作** ✗ 模组自己按**够不够得着**判 ✓
#       （★那正是"玩家行为"那条路 ✓★）
#     · ★别的一律要**显式声明** `ops=True`✗★ —— 声明了才发 ✗ 而**发了就留痕**✗★
#       （★`logs/ops_world.log` ✗ 不许静默✓★）
#   ★它拦得住谁✗★：★拦的是"**我自己顺手抄近路**" ✗ 不是"别人绕不过去"✗★ ✓
#     （★包里/别处仍能直接 `Channel.cmd` ✗ 这一点必须说清 ✗ 不装成沙盒✓★）
WORLD_CMDS = ("setblock", "fill", "clone", "summon", "kill", "give", "effect", "enchant",
              "item", "loot", "tp", "teleport", "gamemode", "weather", "time ",
              "difficulty", "scoreboard", "data merge", "data modify", "forceload")


def is_world_change(text: str) -> bool:
    """★这条指令会不会**改世界**✗★（★`/dsh…` 是模组动作 ⇒ 不算"运维改世界" ✓★）"""
    s = (text or "").strip().lstrip("/")
    if s.startswith("dsh"):
        return False                      # ★模组动作：reach 由模组自己判 ✓
    low = s.lower()
    return any(low.startswith(c) for c in WORLD_CMDS)


def _ops_log(text: str, who: str) -> str:
    """★发了就留痕✗★（★返回日志路径 ✓ 失败也不吞 ✗ 打到 stderr✓★）"""
    import time as _t
    p = ROOT_LOG / "ops_world.log"
    line = "%s  who=%s  cmd=/%s\n" % (_t.strftime("%Y-%m-%d %H:%M:%S"), who, text)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as e:
        sys.stderr.write("★运维日志写不进去 ✗ %s: %s\n" % (type(e).__name__, e))
    return str(p)


ROOT_LOG = Path(__file__).resolve().parent.parent / "logs"


def run_one(ch: Channel, text: str, ops: bool = False) -> int:
    # ★★㊱ 的守卫✗★★：★改世界的指令要么走模组（够得着）✗ 要么**显式声明** ops=True✗★
    if is_world_change(text):
        if not ops:
            print("★拒绝✗★：/%s" % text)
            print("   ★它**改世界** ✗ 而 `raw` 通道**不知道你够不够得着**✗★")
            print("   ★两条正路✗★：① 走**模组动作**（`/dsh…` ✓ 它自己按 reach 判 ✓）")
            print("              ② 确实是**运维**（★不是玩家行为✗★）⇒ 显式 `--ops` 声明 ✓")
            print("   ★★一个字都没有发出去✗★★（★这才是「拦住」✓★）")
            return 3
        print("★运维声明已收到 ✗ 这一条会留痕✗★：%s" % _ops_log(text, ch.who))
    print("== 执行: /%s" % text)
    try:
        r = ch.cmd(text, allow_str=True, timeout=60.0)
    except BridgeError as e:
        print("[X] 通道错误：%s" % e)
        return 1
    d = r.as_dict()
    # ⚠ 回传的"信封"形状**不止一种** ✗（实测）：
    #   有的动作把结果包在 `result` 里 ✓ 而 `cmd` 直接就是 {success,lines,ret_types,...} ✓。
    #   只认一种形状 ⇒ 另一种会被当成"没有回传" ✗ → 误判成"指令没执行" ✗✗
    payload = d.get("result")
    if not isinstance(payload, dict):
        payload = d if ("lines" in d or "success" in d) else None
    res = payload
    if isinstance(res, dict):
        print("   ok=%s success=%s ret_types=%s" % (d.get("ok"), res.get("success"),
                                                    res.get("ret_types")))
        for i, line in enumerate(res.get("lines") or []):
            print("   [%d] %s" % (i, line))
        if not (res.get("lines") or []):
            print("   （无输出行）")
    elif res is None:
        # 关键：**不要**把"没有 result"当成"没有回传" ✗ —— 把整包原样打出来 ✓
        print("   [!] 回传里没有 result 字段，原始包：")
        print("   " + json.dumps(d, ensure_ascii=False)[:2000])
    else:
        print("   result=%s" % json.dumps(res, ensure_ascii=False)[:2000])
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    ops = "--ops" in argv          # ★㊱：运维声明（★显式才发 ✗ 发了留痕✓★）
    argv = [a for a in argv if a != "--ops"]
    who = "cmd0"
    if argv[0] == "--who":
        who, argv = argv[1], argv[2:]
    ch = Channel(who=who)
    if argv and argv[0] == "--file":
        p = Path(argv[1])
        if not p.is_file():
            print("[X] 找不到指令文件：%s" % p)
            return 1
        n = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            print("-" * 58)
            run_one(ch, line)
            n += 1
        print("-" * 58)
        print("共执行 %d 条" % n)
        return 0
    if not argv:
        print(__doc__)
        return 2
    return run_one(ch, " ".join(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
