"""find_graves.py -- 找墓碑（ATM9 里有 tombstone 模组 ✓ 日志露了 [tombstone/] ✓）

为什么找 ✗：假人掉虚空两次（18:18 ✓ 20:34 ✓）✓ 损失过一批东西 ✓
  若死亡点有墓碑 ⇒ 东西**可能还在** ✓（这是用户会关心的实事 ✓ 不能只报"丢了"✗）
判据 ✓：找到就报坐标＋离假人多远 ✓；找不到就**明说找不到** ✗（不猜 ✓）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import mapread as MR  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

r = MR.Reader()
p = r.pos()
print("bot pos =", p)
if not p:
    print("=> 读不到假人位置 ✗（先 respawn_bot.py ✓）")
    raise SystemExit(1)
bx, by, bz = int(p[0]), int(p[1]), int(p[2])
# 墓碑模组的方块名可能是 tombstone:* / gravestone:* ✓ 用子串一次扫多种 ✓
box = (bx - 80, 30, bz - 80, bx + 80, 200, bz + 80)
found = {}
for pat in ("tombstone", "grave", "corpse", "death"):
    kv, coords = r.scan(box, match=pat, max_=60, page=1)
    n = int(kv.get("matched") or 0)
    print("  match=%-10s matched=%d  page=%s" % (pat, n, kv.get("page") or "?"))
    if n:
        found[pat] = coords
if not found:
    print("=> 这片范围里**没找到**墓碑 ✗（也可能名字不含这几个词 ✓ 或不在这个 y 范围 ✓）")
else:
    import math
    for pat, coords in found.items():
        for (x, y, z) in sorted(coords, key=lambda c: math.dist((c[0], c[1], c[2]), (bx, by, bz)))[:6]:
            print("   %s @ (%d,%d,%d)  离假人 %.1f 格" % (pat, x, y, z,
                                                       math.dist((x, y, z), (bx, by, bz))))
