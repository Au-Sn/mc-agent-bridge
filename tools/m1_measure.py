"""m1_measure.py -- 地图读取的成本预算（先量再设计 ✓ 纪律①）

要量三件事 ✓：
  A. 一次 1x1 方块读取（`dshscan x y z x y z`）的**往返时间**（20 次采样 ✓ 中位数/最大 ✓）
  B. `dshscan` 带 `match` 时**到底给不给坐标** ✓（给的话，找方块就不用逐格探 ✓）
  C. 整块区域一次扫描（大盒子 ✓）要不要钱 ✓（毫秒级吗？✓）
判据（事先写死 ✓）：
  · 若 A 中位数 > 0.8s ⇒ 逐格探测法只适合 ≤9x9 的小图 ✓ 大图必须靠模组侧 /dshmap ✓
  · B 必须给坐标 ✓ 否则"找最近的 X"就没法做 ✓
"""
from __future__ import annotations

import re
import statistics
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


def ab(t: str, tmo: float = 60.0) -> str:
    return (ch.cmd("execute as Bot at Bot run " + t, timeout=tmo, allow_str=True).text() or "").strip()


def main() -> int:
    # 先读 bot 的位置（拿真实坐标来探 ✓）
    d = ab("dshdigest 1")
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", d)
    if not m:
        print("NO POS:", d[:200])
        return 1
    bx, by, bz = (int(float(m.group(1))), int(float(m.group(2))), int(float(m.group(3))))
    print("bot at %d,%d,%d" % (bx, by, bz))

    # ── A. 1x1 往返成本
    xs = []
    for i in range(20):
        t0 = time.time()
        ab("dshscan %d %d %d %d %d %d" % (bx, by - 1 - (i % 5), bz, bx, by - 1 - (i % 5), bz))
        xs.append(time.time() - t0)
    print("A) 1x1 读取: n=%d 中位=%.3fs 最小=%.3fs 最大=%.3fs  <- 每格成本"
          % (len(xs), statistics.median(xs), min(xs), max(xs)))

    # ── C. 大盒子一次扫
    t0 = time.time()
    big = ab("dshscan %d %d %d %d %d %d" % (bx - 20, by - 10, bz - 20, bx + 20, by + 10, bz + 20))
    print("C) 41x21x41 大盒子: %.3fs  <- 一次调用" % (time.time() - t0))
    print("   回执:", big.splitlines()[0][:220])

    # ── B. 带 match 给不给坐标
    t0 = time.time()
    mm = ab('dshscan %d %d %d %d %d %d "chest" 4 1' % (bx - 30, by - 15, bz - 30, bx + 30, by + 15, bz + 30))
    print("B) match=chest: %.3fs" % (time.time() - t0))
    for line in mm.splitlines():
        print("   |", line.strip()[:260])
    return 0


raise SystemExit(main())
