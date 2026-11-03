"""respawn_bot.py -- 把假人拉回来（可重复跑 ✓）

为什么单独写一个 ✗：假人死了以后，**桥还是通的** ✓（dshver 照样回话 ✓）
  ⇒ 所以"读不到 Bot 的状态"很容易被我当成"桥断了"✗ —— 实测 2026-09-23 就是这样 ✗
  ⇒ 这个脚本把"假人不在"这条前提**当场说清** ✓ 并且按 runbook 拉回来 ✓
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ch = Channel("cmd0", verbose=False)


def raw(t: str, tmo: float = 40.0) -> str:
    try:
        return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
    except Exception as e:
        return "ERR:%s" % type(e).__name__


def alive() -> bool:
    d = raw("execute as Bot at Bot run dshdigest 1", 30.0)
    return bool(re.search(r"name=Bot", d))


def main() -> int:
    if alive():
        print("Bot 活着 ✓ 不用拉（dshdigest 有 name=Bot ✓）")
        return 0
    print("Bot **不在** ✗ ⇒ 按 runbook 拉：player Bot spawn ＋ gamemode survival Bot")
    print("  spawn ->", raw("player Bot spawn", 40.0)[:160] or "(无回执)")
    time.sleep(2.0)
    print("  mode  ->", raw("gamemode survival Bot", 40.0)[:160] or "(无回执)")
    time.sleep(1.5)
    if alive():
        d = raw("execute as Bot at Bot run dshdigest 2", 30.0)
        m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", d)
        print("=> 拉回来了 ✓ 位置 %s" % (m.group(0) if m else "?"))
        return 0
    print("=> ★没拉回来★ ✗（再试一次或看游戏日志 ✓ 不许假装成功 ✓）")
    return 1


raise SystemExit(main())
