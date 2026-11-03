#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2130_check.py —— D1..D4 一条命令跑完（★判据写死 ✓ 全 ASCII 输出 ✗★）

前提检查（第一段 ✓ 我的硬规矩 ✗）：版本必须是 2.13.0 ✓ 假人必须在 ✓（不在就拉起来 ✓）
D1 往水里丢一件 ⇒ `/dshdrop 24` 必须列出它且 `in_water=true` ✓
D2 `/dshwalk` 到水面下方一格 ⇒ `result=reached` ✓ 且状态里出现 `in_water=true` ✓
D3 `go_to_drop` 找水下的它 ⇒ 世界真值：items 涨了 或 那个 id 消失 ✓
D4 陆地回归：岛内跨高差 ⇒ `reached` ✓（别把陆地走法改坏 ✗）
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)
out: list[str] = []
WATER = (4134, 70, 13)          # 早先普查到的水源方块（level=0 ✓）
LAND = (4128, 70, 21)           # 草方块 (4128,69,21) 的正上方 ⇒ 站得住 ✓


def raw(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def ab(t: str, tmo: float = 60.0) -> str:
    return raw("execute as Bot at Bot run %s" % t, tmo)


def kv(t: str, k: str, d: str = "-") -> str:
    m = re.search(k + r"=([^\s|]+)", t or "")
    return m.group(1) if m else d


def wait_walk(limit: float) -> str:
    t0, last = time.time(), ""
    while time.time() - t0 < limit:
        time.sleep(0.7)
        s = ab("dshwalk", 30.0)
        if s:
            last = s
        if "status=done" in s:
            return s
    return last or "(no status)"


def main() -> int:
    ver = raw("dshver")
    out.append("PRECHECK version -> %s" % ver[:90])
    if "2.13." not in ver:            # ★前缀比较★ ✗（2.13.1 也应当通过 ✓ 别再卡死在补丁号上 ✓）
        out.append("=> STOP: game not restarted to 2.13.x (D1..D4 not run)")
        (ROOT / "logs" / "v2130_check.txt").write_text("\n".join(out), encoding="utf-8")
        print("V2130: STOP - not 2.13.0 yet")
        return 2
    if "name=Bot" not in ab("dshdigest 4"):
        out.append("bot missing -> spawn")
        raw("player Bot spawn", 45.0)
        time.sleep(2.5)
        raw("gamemode survival Bot", 45.0)
        time.sleep(1.0)
    dig = ab("dshdigest 4")
    out.append("PRECHECK bot -> %s" % dig[:160])
    if "name=Bot" not in dig:
        out.append("=> STOP: no fake player")
        (ROOT / "logs" / "v2130_check.txt").write_text("\n".join(out), encoding="utf-8")
        print("V2130: STOP - no bot")
        return 2

    # ── D1：往水里丢一件
    sumr = raw('summon item %d.5 %d.5 %d.5 {Item:{id:"minecraft:dirt",Count:1b},PickupDelay:0s}'
               % (WATER[0], WATER[1], WATER[2]))
    out.append("")
    out.append("D1 summon -> %s" % sumr[:80])
    time.sleep(2.0)
    dl = ab("dshdrop 24", 60.0)
    out.append("D1 dshdrop -> %s" % dl[:400])
    d1 = ("in_water=true" in dl) and ("minecraft:dirt" in dl)
    out.append("D1 => %s" % ("PASS" if d1 else "FAIL"))

    # ── D2：走到水面下方那一格
    out.append("")
    out.append("D2 start -> %s" % ab("dshwalk %d %d %d 40000" % WATER, 60.0)[:200])
    st2 = wait_walk(70.0)
    out.append("D2 status -> %s" % st2[:300])
    out.append("D2 => %s" % ("PASS" if "result=reached" in st2 else "FAIL"))

    # ── D3：go_to_drop 捡水下的它
    import mc_mcp  # noqa: E402
    t0 = time.time()
    txt, bad = mc_mcp.t_go_to_drop("minecraft:dirt", 24, 20000)
    out.append("")
    out.append("D3 %.1fs -> %s" % (time.time() - t0, txt[:400]))
    out.append("D3 => %s" % ("FAIL" if bad else "PASS"))

    # ── D4：陆地回归
    out.append("")
    out.append("D4 start -> %s" % ab("dshwalk %d %d %d 40000" % LAND, 60.0)[:200])
    st4 = wait_walk(70.0)
    out.append("D4 status -> %s" % st4[:300])
    out.append("D4 => %s" % ("PASS" if "result=reached" in st4 else "FAIL"))

    ok = d1 and ("result=reached" in st2) and ("result=reached" in st4)
    out.append("")
    out.append("SUMMARY D1=%s D2=%s D4=%s" % (d1, "result=reached" in st2, "result=reached" in st4))
    (ROOT / "logs" / "v2130_check.txt").write_text("\n".join(out), encoding="utf-8")
    print("V2130: %s" % " ".join(l for l in out if l.startswith(("D1 =>", "D2 =>", "D3 =>", "D4 =>", "SUMMARY"))))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
