#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
act.py — 直接给某台机器下发**桥接动作**（crosshair / jade / self_update / reboot / 海龟指令…）

与 raw.py 的分工：
    raw.py  发**游戏指令**（/setblock、/data get …）→ 永远走 cmd0
    act.py  发**桥接动作**（Lua 里的 A.xxx）→ 可以指定 who / 海龟 target

为什么要绕过技能层：
    技能层（skills.py）会**按 schema 过滤参数** ✗ —— 排查问题时最怕参数在进入通道前
    就被默默丢掉 ✗（本项目真实踩过：海龟的 x/y/z 在技能层被过滤掉 ✓ → 现场表现
    却是"海龟说需要坐标" ✗）。这个工具**不过滤、不裁剪** ✓ 只把动作与完整回传摆出来 ✓。

用法：
    py tools/act.py crosshair raw=True
    py tools/act.py --who cc0 status
    py tools/act.py --who cc0 reboot                        # 重启一台机器（等它自己起来）
    py tools/act.py --target 1 equip slot=4 side=right      # 转发给海龟 1
    py tools/act.py --who cc0 --wait 2 crosshair

⚠ 也是**能改世界**的通道（dig/place/reboot…）✓ 自己确认动作安全 ✓。

★★ 2026-09-19 标记：`--target`（转发给海龟 / cc0）是**遗留能力** ★★
    用户定的方向 ✓：「**cc0 老是出问题就慢慢用模组去替代掉 CC 电脑的作用**」✓
    ⇒ 现在**主线已经不需要它了** ✗（见 docs/模组-容器存取与假人手.md §8 ✓）：
        · 对着方块用物品（筛矿 ✗）⇒ 模组 `/dshuse` ✓
        · 合成                      ⇒ 模组 `/dshcraft` ✓
        · 容器存取                  ⇒ 模组 `/dshbox` `/dshslot` ✓
        · 整理背包                  ⇒ 模组 `/dshinv` ✓
        · 精确走位                  ⇒ `path_goto exact=true` ✓
        · 说话 / 自报状态            ⇒ 模组 `/dshsay` `/dshstats` ✓
        · 读方块 / 扫地形 / 准星     ⇒ 桥接动作（跑在 **cmd0** 上）✓
    ⇒ 所以 `--target` 现在只用于"**保留海龟那条路**"✗ 与"**排查旧账**"✓
      **新流程不要再依赖它** ✗（cc0 每次世界重启都会把自己搞成 0 字节 ✗ 见错题本 P18 ✓）
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel, BridgeError  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def coerce(v: str):
    low = v.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("none", "null", "nil"):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    who, target, wait = "cmd0", None, 0.0
    who_set = False
    while argv and argv[0].startswith("--"):
        if argv[0] == "--who":
            who, who_set, argv = argv[1], True, argv[2:]
        elif argv[0] == "--target":
            target, argv = int(argv[1]), argv[2:]
        elif argv[0] == "--wait":
            wait, argv = float(argv[1]), argv[2:]
        else:
            print("[X] 未知选项 %s" % argv[0])
            return 2
    if not argv:
        print(__doc__)
        return 2
    # ⚠ 转发给海龟**必须经由带 modem 的那台机器** ✗
    #   （真实踩过：发给 cmd0 ✓ 它没有 modem ✓ 于是回 "rednet 发送失败" ✗
    #     而这条错误看起来像"海龟没反应" ✓ 极易误判 ✗ → 有 --target 时默认走 cc0 ✓）
    if target is not None and not who_set:
        who = "cc0"
    cmd = argv[0]
    args = {}
    for kv in argv[1:]:
        if "=" in kv:
            k, v = kv.split("=", 1)
            args[k] = coerce(v)
    if target is not None:
        args["target"] = target

    ch = Channel(who=who)
    print("== %s ← %s %s" % (who, cmd, json.dumps(args, ensure_ascii=False)))
    try:
        cid = ch.send(cmd, args)
        r = ch.wait(cid, timeout=90.0, cmd=cmd)
    except BridgeError as e:
        print("[X] %s" % e)
        return 1
    # ⚠ 失败时 result 是**字符串**（错误信息）✗ → as_dict() 会抛异常 ✓
    #   而排查问题时最需要看到的恰恰是那句话 ✗ → 所以这里自己吞掉异常、把原文摆出来 ✓
    if isinstance(r.result, str):
        print(json.dumps({"ok": r.ok, "result": r.result}, ensure_ascii=False, indent=1))
    else:
        try:
            d = r.as_dict()
        except BridgeError:
            d = {"ok": r.ok, "result": r.result}
        payload = d.get("result")
        if not isinstance(payload, dict):
            payload = d.get("result", d)
        print(json.dumps({"ok": d.get("ok"), "result": payload}, ensure_ascii=False, indent=1)[:4000])
    if wait:
        print("…等 %.1f 秒" % wait)
        time.sleep(wait)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
