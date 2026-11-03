#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""runbook_after_restart.py —— ★重启后一条命令跑完全套★（判据写死 ✓ 全 ASCII 输出 ✗）

顺序（每一步都有前提检查 ✓ 不过就停并说明 ✗）：
  0 版本必须是 2.13.x ✓（不是就停 ✓ 不白跑 ✓）
  1 把假人拉回来 ✓（spawn ＋ gamemode survival ✓）
  2 **不敲 /dskskin** ✓ —— 先看**自愈**能不能自己把皮肤长回来 ✓
    （config/dshbridge/skins_state.json 里已经预置 {"Bot":"deepseek"} ✓）
  3 读 logs/skin_http.log ✓ ⇒ ★客户端到底有没有来下载★ ⇒ 三种情况直接定因 ✓
  4 跑 D1..D4（/dshdrop 含 in_water ✓ ／ 水下那格 walk ⇒ reached ✓ ／ go_to_drop 捡它 ✓ ／ 陆地回归 ✓）
  5 汇总 ＋ 落档 logs/runbook.txt ✓
"""
from __future__ import annotations

import re
import sys, paths as PA
import time
from pathlib import Path

ROOT = PA.ROOT
GAME = PA.MC_HOME
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))
from channel import Channel  # noqa: E402

ch = Channel("cmd0", verbose=False)
out: list[str] = []
WATER = (4134, 70, 13)
LAND = (4128, 70, 21)


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
    out.append("STEP0 version -> %s" % ver[:90])
    if "2.13." not in ver:
        out.append("=> STOP: not 2.13.x (restart pending; nothing else run)")
        (ROOT / "logs" / "runbook.txt").write_text("\n".join(out), encoding="utf-8")
        print("RUNBOOK: STOP - not 2.13.x yet")
        return 2

    if "name=Bot" not in ab("dshdigest 4"):
        out.append("STEP1 spawn bot")
        raw("player Bot spawn", 45.0)
        time.sleep(2.5)
        raw("gamemode survival Bot", 45.0)
        time.sleep(1.0)
    dig = ab("dshdigest 4")
    out.append("STEP1 bot -> %s" % dig[:170])
    if "name=Bot" not in dig:
        out.append("=> STOP: no bot")
        (ROOT / "logs" / "runbook.txt").write_text("\n".join(out), encoding="utf-8")
        print("RUNBOOK: STOP - no bot")
        return 2

    # STEP2 自愈：**故意不敲 /dskskin** ✓
    out.append("")
    out.append("STEP2 自愈检查（★不敲 /dskskin★ ✓ 只看它自己有没有长回来 ✓）")
    ev = ab("dshevents", 45.0)
    healed = "skin_heal" in ev
    out.append("STEP2 事件流里有 skin_heal = %s" % healed)
    if not healed:
        time.sleep(12.0)                      # 自愈每 100 tick 一次 ⇒ 等一等 ✓
        ev = ab("dshevents", 45.0)
        healed = "skin_heal" in ev
        out.append("STEP2 再等 12 秒后 = %s" % healed)
    out.append("STEP2 => %s" % ("PASS" if healed else "FAIL（自愈没发生 ✗ 要查 skins_state.json ✓）"))

    # STEP3 皮肤 HTTP 访问日志 ⇒ 客户端到底有没有来 ✓
    out.append("")
    hp = GAME / "logs" / "skin_http.log"
    if hp.is_file():
        lines = hp.read_text(encoding="utf-8", errors="replace").splitlines()
        out.append("STEP3 skin_http.log 行数=%d" % len(lines))
        for l in lines[-6:]:
            out.append("   " + l.strip()[:170])
        ok3 = any("found=true" in l for l in lines)
        out.append("STEP3 => %s" % ("客户端来下载过 ✓（若画面仍不变 ⇒ 是渲染/缓存那一层 ✗）"
                                    if ok3 else "★客户端一次都没来 ✗ ⇒ 它不信这个档案（签名之类）★"))
    else:
        out.append("STEP3 skin_http.log 不存在 ⇒ 客户端一次都没请求 ✗（或模组没生效 ✗ 但版本已过 ✓）")

    # STEP4 D1..D4
    out.append("")
    raw('summon item %d.5 %d.5 %d.5 {Item:{id:"minecraft:dirt",Count:1b},PickupDelay:0s}'
        % (WATER[0], WATER[1], WATER[2]))
    time.sleep(2.0)
    dl = ab("dshdrop 24", 60.0)
    d1 = ("in_water=true" in dl) and ("minecraft:dirt" in dl)
    out.append("D1 dshdrop -> %s" % dl[:300])
    out.append("D1 => %s" % ("PASS" if d1 else "FAIL"))

    out.append("D2 start -> %s" % ab("dshwalk %d %d %d 40000" % WATER, 60.0)[:150])
    st2 = wait_walk(70.0)
    out.append("D2 status -> %s" % st2[:280])
    d2 = "result=reached" in st2
    out.append("D2 => %s" % ("PASS" if d2 else "FAIL"))

    import mc_mcp  # noqa: E402
    txt, bad = mc_mcp.t_go_to_drop("minecraft:dirt", 24, 20000)
    out.append("D3 -> %s" % txt[:320])
    out.append("D3 => %s" % ("FAIL" if bad else "PASS"))

    out.append("D4 start -> %s" % ab("dshwalk %d %d %d 40000" % LAND, 60.0)[:150])
    st4 = wait_walk(70.0)
    out.append("D4 status -> %s" % st4[:280])
    d4 = "result=reached" in st4
    out.append("D4 => %s" % ("PASS" if d4 else "FAIL"))

    out.append("")
    out.append("SUMMARY heal=%s D1=%s D2=%s D3=%s D4=%s" % (healed, d1, d2, not bad, d4))
    (ROOT / "logs" / "runbook.txt").write_text("\n".join(out), encoding="utf-8")
    print("RUNBOOK: heal=%s D1=%s D2=%s D3=%s D4=%s" % (healed, d1, d2, not bad, d4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
