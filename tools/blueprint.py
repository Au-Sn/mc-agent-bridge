#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blueprint.py — 蓝图工具链（仿 Create 的「蓝图 + 蓝图大炮」）

为什么做这个（用户的明确要求 ✓）：
    假人搭平台一直靠"一格一格探、一格一格试"✗ —— 慢，且容易在虚空上方把自己摔下去 ✗。
    Create 的蓝图大炮把这件事拆成了清楚的两半 ✓：
        ① **蓝图**：结构化数据（哪些相对位置、放什么方块）✓
        ② **一门会飞过去逐块放的炮** ✓ 带**缺料清单** ✓ 带**跳过已符合的格子** ✓ 可中断续做 ✓
    本工具就是①③（读图 / 算账 / 生成蓝图），炮本身在桥接里（`A.blueprint_build` ✓）。

子命令：
    capture  把世界里一片区域读成蓝图（仿「蓝图与笔」✓）
    new      直接生成一张标准蓝图（手写常用图样 ✓ 例如石台 pad）
    plan     对着现场算账：哪些已符合 ✓ 哪些要放 ✗ 缺什么料 ✗（仿炮的 checklist ✓）
    build    开炮：让假人飞过去逐块放，可分批 ✓ 可重跑 ✓（幂等 ✓）

用法：
    py tools/blueprint.py capture --name deck --x0 4125 --y0 71 --z0 12 --x1 4127 --y1 71 --z1 14
    py tools/blueprint.py new --name pad --kind pad
    py tools/blueprint.py plan  --name pad --x 4150 --y 78 --z 20
    py tools/blueprint.py build --name pad --x 4150 --y 78 --z 20 --max 24

蓝图形状（与桥接约定 ✓）：
    { "name": "...", "kind": "...", "size": {"x":n,"y":n,"z":n},
      "cells": [ {"dx":0,"dy":0,"dz":0,"block":"minecraft:oak_planks"}, ... ] }
    —— dx/dy/dz 是**相对锚点**的偏移 ✓ 锚点由 build/plan 的 --x/--y/--z 给 ✓
"""

from __future__ import annotations

import json
import sys, paths as PA
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "agent"))

from channel import Channel, BridgeError  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BP_DIR = ROOT / "cc-tweaked" / "blueprints"
# ⚠ 交给假人（游戏内 CC 计算机）的地址**必须是绝对的** ✗
#   桥接里的 httpGet 不会自己拼 BASE ✓（真实踩过：相对路径直接 404/失败 ✗）
#   网关监听在 paths.GATEWAY_PORT ✓ 而 CC 计算机跑在同一台机器上 ✓ ⇒ 用回环地址即可 ✓
#   网关 /files/ 的根就是 cc-tweaked ✓（启动参数 --root，默认值 ✓）
GW = PA.gateway_url()
URL_PREFIX = GW + "/files/blueprints/"


def call(ch: Channel, cmd: str, args: dict, timeout: float = 180.0) -> dict:
    cid = ch.send(cmd, args)
    r = ch.wait(cid, timeout=timeout, cmd=cmd)
    d = r.as_dict()
    # ⚠ 两种回传形状都要兜 ✓（真实踩过：只写一种就崩 ✓ 见 docs/错题本.md J5）
    payload = d.get("result")
    if not isinstance(payload, dict):
        payload = d if isinstance(d, dict) else None
    if not isinstance(payload, dict):
        raise BridgeError("%s 回传异常：%s" % (cmd, payload))
    return payload


def load_bp(name: str) -> dict:
    p = BP_DIR / ("%s.json" % name)
    if not p.is_file():
        raise SystemExit("[X] 找不到蓝图 %s" % p)
    return json.loads(p.read_text(encoding="utf-8"))


def save_bp(bp: dict) -> Path:
    BP_DIR.mkdir(parents=True, exist_ok=True)
    p = BP_DIR / ("%s.json" % bp["name"])
    p.write_text(json.dumps(bp, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def cmd_capture(ch: Channel, a: dict) -> int:
    box = {k: int(a[k]) for k in ("x0", "y0", "z0", "x1", "y1", "z1")}
    snap = call(ch, "snapshot", box)
    x0, y0, z0 = snap["box"]["x0"], snap["box"]["y0"], snap["box"]["z0"]
    cells = []
    for c in snap["cells"]:
        cells.append({"dx": c["x"] - x0, "dy": c["y"] - y0, "dz": c["z"] - z0, "block": c["n"]})
    bp = {
        "name": a["name"], "kind": "captured",
        "size": {"x": snap["box"]["nx"], "y": snap["box"]["ny"], "z": snap["box"]["nz"]},
        "source": snap["box"],
        "cells": cells,
    }
    p = save_bp(bp)
    print("[OK] 蓝图已存：%s（%d 格 ✓ 空气 %d 格已略去 ✓）" % (p, len(cells), snap["air_n"]))
    for k, v in sorted(snap["counts"].items(), key=lambda kv: -kv[1]):
        print("      %-36s ×%d" % (k, v))
    return 0


def cmd_new(ch: Channel, a: dict) -> int:
    """手写常用图样。pad = 一块平台（默认 4×3 木板）+ 可选三件套。"""
    kind = a.get("kind", "pad")
    if kind != "pad":
        print("[X] 目前只有 --kind pad")
        return 2
    nx = int(a.get("nx", 4))
    nz = int(a.get("nz", 3))
    mat = a.get("material", "minecraft:oak_planks")
    cells = []
    for dx in range(nx):
        for dz in range(nz):
            cells.append({"dx": dx, "dy": 0, "dz": dz, "block": mat})
    bp = {"name": a["name"], "kind": "pad", "size": {"x": nx, "y": 1, "z": nz}, "cells": cells}
    p = save_bp(bp)
    print("[OK] 生成蓝图：%s（%d×%d 的 %s ✓ 共 %d 格）" % (p, nx, nz, mat, len(cells)))
    return 0


def cmd_plan(ch: Channel, a: dict) -> int:
    bp = load_bp(a["name"])
    ax, ay, az = int(a["x"]), int(a["y"]), int(a["z"])
    xs = [ax + c["dx"] for c in bp["cells"]]
    ys = [ay + c["dy"] for c in bp["cells"]]
    zs = [az + c["dz"] for c in bp["cells"]]
    snap = call(ch, "snapshot", {"x0": min(xs), "y0": min(ys), "z0": min(zs),
                                 "x1": max(xs), "y1": max(ys), "z1": max(zs), "maxcells": 1200})
    live = {(c["x"], c["y"], c["z"]): c["n"] for c in snap["cells"]}
    need, ok_n = {}, 0
    for c in bp["cells"]:
        k = (ax + c["dx"], ay + c["dy"], az + c["dz"])
        if live.get(k) == c["block"]:
            ok_n += 1
        else:
            need[c["block"]] = need.get(c["block"], 0) + 1

    inv = call(ch, "bot_inv", {"bot": a.get("bot", "Bot")})
    have = {}
    for it in inv.get("items") or []:
        have[it["id"]] = have.get(it["id"], 0) + int(it.get("count", 1))

    print("== 蓝图 %s @ (%d,%d,%d) ==" % (bp.get("name"), ax, ay, az))
    print("   总格数 %d ✓ 已符合 %d ✓ 待放 %d ✗" % (len(bp["cells"]), ok_n, len(bp["cells"]) - ok_n))
    print("   ── 缺料清单（仿蓝图大炮的 checklist ✓）──")
    short = 0
    for blk, n in sorted(need.items(), key=lambda kv: -kv[1]):
        h = have.get(blk, 0)
        flag = "OK " if h >= n else "缺 "
        if h < n:
            short += 1
        print("   %s %-34s 需要 %3d ｜ 背包 %3d" % (flag, blk, n, h))
    print("   ⇒ %s" % ("材料齐了 ✓ 可以开炮" if short == 0 else "有 %d 种料不够 ✗ 先补料" % short))
    return 0


def cmd_build(ch: Channel, a: dict) -> int:
    bp = load_bp(a["name"])
    url = URL_PREFIX + a["name"] + ".json"
    res = call(ch, "blueprint_build", {
        "bot": a.get("bot", "Bot"), "url": url,
        "x": int(a["x"]), "y": int(a["y"]), "z": int(a["z"]),
        "max": int(a.get("max", 48)), "fly": a.get("fly", True),
    }, timeout=float(a.get("timeout", 600)))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    sub, rest = argv[0], argv[1:]
    a: dict = {}
    i = 0
    while i < len(rest):
        k = rest[i].lstrip("-")
        if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
            a[k] = rest[i + 1]
            i += 2
        else:
            a[k] = True
            i += 1
    for key in ("x0", "y0", "z0", "x1", "y1", "z1", "x", "y", "z", "max", "nx", "nz", "timeout"):
        if key in a and a[key] is not True:
            a[key] = int(a[key])
    ch = Channel(who=a.get("who", "cmd0"))
    fn = {"capture": cmd_capture, "new": cmd_new, "plan": cmd_plan, "build": cmd_build}.get(sub)
    if fn is None:
        print("[X] 未知子命令 %s" % sub)
        return 2
    if sub in ("capture", "new") and not a.get("name"):
        print("[X] 需要 --name")
        return 2
    try:
        return fn(ch, a)
    except BridgeError as e:
        print("[X] %s" % e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
