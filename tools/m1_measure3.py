"""m1_measure3.py -- shown 上限与翻页（决定"建一张图要几次调用"✓）

判据（事先写死 ✓）：
  · 若 `max=500` 时 `shown` 明显变大（>48 ✓）⇒ 每次调用能拿回更多坐标 ⇒ 建图调用数大降 ✓
  · 翻页 page=2 必须给出**不同**的坐标 ✓ 否则分页是假的 ✗（那就得靠 max ✓）
"""
from __future__ import annotations

import re
import sys
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


def coords(out: str):
    head, _, rest = out.partition("counts[")
    return re.findall(r"(-?\d+),(-?\d+),(-?\d+)", rest or out)


def main() -> int:
    d = ab("dshdigest 1")
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", d)
    bx, by, bz = (int(float(m.group(1))), int(float(m.group(2))), int(float(m.group(3))))
    box = "%d %d %d %d %d %d" % (bx - 14, by - 8, bz - 14, bx + 14, by + 6, bz + 14)
    for mx in (6, 48, 200, 1000):
        out = ab('dshscan %s "grass_block" %d 1' % (box, mx))
        head = out.split("counts[")[0]
        kv = dict(re.findall(r"(\w+)=(\S+)", head))
        got = len(coords(out))
        print("max=%-5d -> matched=%s shown=%s page=%s 实收坐标=%d"
              % (mx, kv.get("matched"), kv.get("shown"), kv.get("page"), got))
    a = coords(ab('dshscan %s "grass_block" 6 1' % box))
    b = coords(ab('dshscan %s "grass_block" 6 2' % box))
    c = coords(ab('dshscan %s "grass_block" 6 3' % box))
    print("page1=%s" % (a[:3],))
    print("page2=%s" % (b[:3],))
    print("page3=%s" % (c[:3],))
    print("=> 翻页有效 =", (a != b and b != c))

    # 顺带量：整盒"所有方块的位置"能不能一次拿到（用一个宽 tag 试 ✓）
    out = ab('dshscan %s "#minecraft:mineable/shovel" 1000 1' % box)
    kv = dict(re.findall(r"(\w+)=(\S+)", out.split("counts[")[0]))
    print("tag 查询: matched=%s shown=%s page=%s 实收=%d"
          % (kv.get("matched"), kv.get("shown"), kv.get("page"), len(coords(out))))
    return 0


raise SystemExit(main())
