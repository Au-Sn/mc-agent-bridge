#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v29_verify.py —— ★一次跑完：恢复假人 ＋ v2.9 走路的复测★（判据先说死 ✗）

判据（写在这里 ✓ 免得事后改口 ✗）：
  1. `/dshver` 必须是 **2.9.0** ✓ 否则一切免谈 ✗（说明 jar 没真加载 ✓）
  2. 上次失败那条：去 `(4150,71,25)` ⇒ 开工回执里**必须**有 `reachable=false` ＋ `nearest=…` ✓
     绝不许再出现"走一半 blocked 且说不清为什么" ✗
  3. 岛内跨 3 层高差那条：去 `(4129,71,29)` ⇒ 期望 `result=reached` ✓ 且 `path=` 有值 ✓
  4. 全程 `path=/replans=/next=` 可见 ✓
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ch = Channel("cmd0", verbose=False)
out: list[str] = []


def log(s: str) -> None:
    out.append(s)


def raw(t: str, tmo: float = 60.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR %s: %s" % (type(e).__name__, str(e)[:120])


def asbot(t: str, tmo: float = 60.0) -> str:
    return raw("execute as Bot at Bot run %s" % t, tmo)


def wait_walk(limit: float = 75.0) -> str:
    """轮询 `/dshwalk` 状态直到 done ✓（返回最后那行 ✓ 里面就有我判据要的字段 ✓）"""
    t0 = time.time()
    last = ""
    while time.time() - t0 < limit:
        time.sleep(0.6)
        s = asbot("dshwalk", 30.0)
        if s:
            last = s
        if "status=done" in s:
            return s
    return last or "(没拿到状态 ✗)"


log("======== ① 模组版本 ========")
log("dshver -> %s" % raw("dshver"))
if "2.9.0" not in raw("dshver"):
    log("!! 不是 2.9.0 ⇒ **停在这里** ✓（jar 没真加载 ⇒ 后面测了也没意义 ✗）")
    (ROOT / "logs" / "v29_verify.txt").write_text("\n".join(out), encoding="utf-8")
    print("VERIFY: version mismatch, stopped")
    raise SystemExit(1)

log("")
log("======== ② 把假人弄回来 ========")
log("spawn 前 data get: %s" % raw("data get entity Bot Pos", 30.0)[:120])
log("player Bot spawn -> %s" % raw("player Bot spawn", 40.0)[:120])
time.sleep(2.5)
log("gamemode survival -> %s" % raw("gamemode survival Bot", 40.0)[:120])
time.sleep(1.0)
log("digest -> %s" % asbot("dshdigest 6", 40.0)[:260])
log("dshver(再确认一次) -> %s" % raw("dshver"))

log("")
log("======== ③ 测 A：目标在岛外（上次失败那条）========")
log("start -> %s" % asbot("dshwalk 4150 71 25 20000", 60.0)[:400])
log("status（终态）-> %s" % wait_walk(75.0)[:500])

log("")
log("======== ④ 测 B：岛内跨高差（去岛南那口箱子）========")
log("start -> %s" % asbot("dshwalk 4129 71 29 40000", 60.0)[:400])
log("status（终态）-> %s" % wait_walk(90.0)[:500])

dest = ROOT / "logs" / "v29_verify.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("VERIFY written %s (%d lines)" % (dest, len(out)))
