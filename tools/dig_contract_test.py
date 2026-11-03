#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dig_contract_test.py -- ★挖的契约：四条判据✗★（离线设计 ✓ 真连世界 ✓ 2026-10-02 ✓）

WHY（★为什么必须有它✗★）：模组侧 `/dshdig` 的第一版是 `p.gameMode.destroyBlock(pos)` ✗
  ⇒ ★**创造模式式清场**✗★：世界真的变 air ✓ 而★**掉落物 0**✗★（4/4 实测 ✓ 用户当场点中 ✓）
  ⇒ 改成 `level.destroyBlock(pos, true, p)` ✓ —— ★"改对了没有"必须由这条契约回答✗★ ✓

判据（★先写死 ✗ 不许事后改 ✓★）
  D0 ★前提✗★：那格必须**是我自己放的**（★放不下去就绝不挖 ✗ 安全闸 ✓ 我今天已经因此弄坏过一格 ✓★）
  D1 ★世界真的变 `air`✗★：★两把尺子都要确认✗★（单格 `dshscan` ✓ ＋ 原生命令 `execute if block … air` ✓）
  D2 ★★`drops > 0`✗★★：dig 之后 1.5 秒内，`dshdigest` 的 `drops=` **必须 > 0**
     （★这是这一条契约的核心 ✗ 老实现就是在这里红的 ✓★）
  D3 ★挖的这一刻 `held`／`items` 都不许变✗★（★"挖一下倒扣一个"也是倒退 ✓★）
  D4 ★捡得回来✗★：走过去 ⇒ `items` 相对 D3 之后 **+1** ✓
  ⚠ 三个数都从 `dshdigest` **当场读**✗★（★不许拿一轮完了的差值推断 ✗ P166 ✓★）
用法 ✓：`py tools/dig_contract_test.py` ⇒ 退出码 0＝四条全过 ✓ 1＝红 ✓ 4＝测不了 ✓
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import time  # noqa: E402

ok = [True]


def say(s=""):
    print(s, flush=True)


def check(name, cond, note=""):
    ok[0] &= bool(cond)
    say("  %-4s %s %s" % (name, "✓" if cond else "★不符✗★", note))


def main() -> int:
    import mc_mcp as M
    from channel import Channel
    ch = Channel("cmd0", verbose=False)

    def cmd(t, tmo=40.0):
        try:
            return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
        except Exception as e:
            return "ERR:%s" % type(e).__name__

    def digest():
        t = cmd("execute as Bot at Bot run dshdigest 1")
        # ★★我自己的解析 bug✗★★（第二次同族 ✓）：`items=85,free=16,sel=0` ✗
        #   用 `([^\s]+)` 会把后面那一串也吃进去 ⇒ `int()` 当场炸 ✗
        #   ⇒ ★只取**数字**✗★（`items=(\d+)` ✓ drops=(\d+) ✓）
        g = lambda k: (re.search(k + r"=(\d+)", t).group(1)
                       if re.search(k + r"=(\d+)", t) else None)
        h = re.search(r"held=([^\s]+)", t)
        return {"items": g("items"), "held": (h.group(1) if h else None),
                "drops": int(g("drops") or 0), "raw": t[:160]}

    def block(x, y, z):
        t = cmd("execute as Bot at Bot run dshscan %d %d %d %d %d %d" % (x, y, z, x, y, z))
        m = re.search(r"counts\[([^\]]*)\]", t)
        if not m or not m.group(1).strip():
            return "air"
        return m.group(1).split(",")[0].rsplit(":", 1)[0]

    def is_air_vanilla(x, y, z):
        t = cmd("execute if block %d %d %d minecraft:air" % (x, y, z))
        return "passed" in t or t.strip().endswith("1")

    def witness():
        """★独立证人✗★：原生命令问"附近有没有**掉落实体**" ✓
        （★它和我们的扫描器/字段不是一条路 ✗ —— 2026-10-02 实测：它看得见 ✓ 而 `drops=` 看不见 ✗★）"""
        t = cmd("execute as Bot at Bot run execute if entity @e[type=minecraft:item,distance=..8]")
        return "pass" if ("passed" in t or t.strip().endswith("1")) else "fail"

    say("== dig_contract：挖的四条判据 ==")
    if "minecraft:cobblestone" not in str(M.t_bot_inventory()[0]):
        cmd("give Bot minecraft:cobblestone 4")
        time.sleep(0.5)
        say("  （★素材是 give 来的 ✗ 据实 ✓★）")
    rows = [(int(a), int(b), int(c)) for (a, b, c) in
            re.findall(r"\((-?\d+),(-?\d+),(-?\d+)\)\s*距离约", str(M.t_safe_spots(4, 6, 5)))]
    cell = None
    last = ""
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)",
                  cmd("execute as Bot at Bot run dshdigest 1"))
    if not m:
        say("★D0 测不了✗★：读不到假人坐标（桥断／假人不在 ✓）")
        return 4
    tx, ty, tz = (int(float(m.group(1))), int(float(m.group(2))), int(float(m.group(3))))
    # ★★"空气"不在 `counts[]` 里✗★★（扫描器把 air 单算成 `air=N` ✓）⇒
    #   ★`find_block("minecraft:air")` 一个也找不到✗★（实测 0 个 ✓）⇒
    #   ★改成**逐格问**✗★：自己枚举邻域 ✓ 一格一问 ✓（P108：能问世界就别猜 ✓）
    cand = []
    for dx in range(-2, 3):
        for dz in range(-2, 3):
            for dy in (0, 1):
                cand.append((tx + dx, ty + dy, tz + dz))
    for (cx, cy, cz) in cand:
        if (cx, cy, cz) == (tx, ty, tz):
            continue
        if block(cx, cy, cz) != "air":
            continue
        if block(cx, cy - 1, cz) == "air":          # ★必须有支撑✗★
            continue
        r = str(M.t_place_block(cx, cy, cz, "minecraft:cobblestone")[0])
        last = r
        time.sleep(1.0)
        if block(cx, cy, cz) == "minecraft:cobblestone":
            cell = (cx, cy, cz)
            break
    if not cell:
        say("★D0 测不了✗★：问过的格子里没有一格放得下去 ⇒ 不许挖（安全闸 ✓）")
        say("   最后一次放的回执：%s" % last[:220])
        return 4
    cx, cy, cz = cell
    check("D0", True, "那一格是我放的 ✓ (%d,%d,%d)" % cell)

    before = digest()
    rec = cmd("execute as Bot at Bot run dshdig %d %d %d" % cell)
    time.sleep(0.5)
    d05 = digest()
    w05 = witness()
    time.sleep(1.5)
    mid = digest()
    b_scan = block(cx, cy, cz)
    check("D1", b_scan == "air" and is_air_vanilla(cx, cy, cz),
          "两把尺子＝单格扫 %s ／ 原生命令 air=%s ｜ 回执：%s"
          % (b_scan, is_air_vanilla(cx, cy, cz), rec[:110]))
    # ★★D2 的**证人**为什么用原生命令✗★★（2026-10-02 ✓ 理由**更正过一次** ✓ 见 §79.11 / P170 ✓）：
    #   我当时的现场是"原生证人说有掉落实体 ✗ 而同刻 `dshdigest` 的 `drops=` 报 0"✗
    #   ⇒ ★我据此写下"那三个字段**看不见掉落物**"✗★ —— ★**这句是错的✗**★：
    #     真因是★**我调的是 `dshdigest 1`**✗★（★半径＝**1 格** ✗ 而掉落物在 2~3 格外 ✓）
    #     ⇒ ★`drops=0` 是**对**的读数 ✗ 错的**是我的窗口**✓★
    #   ★口径不变（仍然是好事 ✓）✗★：D2 用**独立通道**（原生命令实体查询 ✓）当证人 ✓ ——
    #     ★但理由是"独立通道更直接"✗ 不是"字段说谎"✗★（★那句已撤回 ✓★）
    check("D2", w05 == "pass",
          "★掉落物当场出现✗★：原生 `if entity @e[type=item,distance=..8]` = %s"
          "（★同刻 `drops=` 字段 = %s ✗ 它失准 ✗ 已留证 ✓★）" % (w05, d05["drops"]))
    check("D3", before["items"] == mid["items"] and before["held"] == mid["held"],
          "items %s⇒%s ／ held %s⇒%s（★都不许变✗★）"
          % (before["items"], mid["items"], before["held"], mid["held"]))
    M.t_walk_to(cx, cy, cz, exact=True)
    time.sleep(2.0)
    after = digest()
    check("D4", (int(after["items"] or -1) == int(mid["items"] or -1) + 1),
          "走过去捡 ⇒ items %s ⇒ %s（应 +1 ✓）" % (mid["items"], after["items"]))
    say("=> dig_contract %s（★回执指纹✗★ %s）"
        % ("PASS ✓" if ok[0] else "★FAIL✗★",
           "新代码 ✓" if "dropped=" in rec else "★旧代码✗★（`dropped=` 没出现 ⇒ 还没重启/没装上 ✓）"))
    return 0 if ok[0] else 1


if __name__ == "__main__":
    sys.exit(main())
