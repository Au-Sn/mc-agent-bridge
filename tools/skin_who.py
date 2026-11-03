# -*- coding: utf-8 -*-
"""skin_who.py —— 分清"客户端来取"还是"我自己 curl"（判官 = 游戏目录 logs/skin_http.log ✓）

判据 ✓（先写死 ✓）：
  S1 我先不动 URL（不发任何 HTTP 请求 ✗）⇒ 只看日志行数会不会变 ✓
  S2 发 `/dskskin off` ＋ `/dskskin deepseek`（模组自己会去问客户端 ✓）⇒ 8 秒内若**多出新行**
     ⇒ **客户端来取了** ✓（那一行就是它 ✓）；8 秒没有新行 ⇒ **客户端没来** ✗
  S3 不管哪种结果 ✓ 都**如实报**✗ —— 不猜、不说"应该会好"✗
说明 ✓：模组的访问日志写在 **游戏目录** 的 `logs/skin_http.log` ✓
  （我先前在**仓库**里找它 ✗ ⇒ 找不到就说"客户端没取" ✗ —— 那是错的 ✓ 这里改正 ✓）
"""
from __future__ import annotations

import sys, paths as PA
import time
from pathlib import Path

ROOT = PA.ROOT
GAME = PA.MC_HOME
LOGF = GAME / "logs" / "skin_http.log"
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def lines() -> list:
    if not LOGF.is_file():
        return []
    return LOGF.read_text(encoding="utf-8", errors="replace").splitlines()


def main() -> int:
    ch = Channel("cmd0", verbose=False)

    def ab(c: str, t: float = 60.0) -> str:
        try:
            return (ch.cmd("execute as Bot at Bot run " + c, timeout=t,
                           allow_str=True).text() or "").strip()
        except Exception as e:
            return "ERR:%s" % type(e).__name__

    n0 = len(lines())
    print("S1 起始日志行数 = %d（我**不**发任何 HTTP 请求 ✓）" % n0)
    r1 = ab("dskskin off")
    time.sleep(1.0)
    r2 = ab("dskskin deepseek")
    print("   dskskin off      -> %s" % (r1.splitlines()[0][:120] if r1 else "(空)"))
    print("   dskskin deepseek -> %s" % (r2.splitlines()[0][:160] if r2 else "(空)"))
    print("S2 等 10 秒，看客户端自己来不来取 ……")
    time.sleep(10.0)
    L = lines()
    new = L[n0:]
    print("   现在行数 = %d（新增 %d 行）" % (len(L), len(new)))
    for ln in new:
        print("   NEW  " + ln[:150])
    if new:
        print("=> ★客户端来取了★ ✓（这条就是它 ✓）⇒ 若外观还没变 ⇒ 问题在**渲染/缓存** ✗")
        print("   ⇒ 下一步按文档 §6.2 bug #4：/dskskin off ⇒ **重启游戏** ⇒ /dskskin deepseek ✓")
    else:
        print("=> ★客户端没来取★ ✗ ⇒ 属性没送到它手上 ⇒ 同样走：重启游戏后立刻 /dskskin deepseek ✓")
    return 0


raise SystemExit(main())
