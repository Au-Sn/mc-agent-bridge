"""ob_unit_test.py -- "识别道中障碍物"的**离线**确定性测试（不需要游戏 ✓ 不需要桥 ✓）

为什么要离线版 ✗：2026-09-23 深夜游戏被关掉 ⇒ 桥断了 ✗ ⇒ 不能拿"世界"当唯一验证手段 ✗
  ⇒ 这条能力（探路找障碍 ✓ 绕开 ✓ 预算诚实 ✓）本质是**纯逻辑** ✓ ⇒ 用**打桩的通道**就能验 ✓
判据（先写死 ✓）：
  O1 探得出：打桩通道在某一格"脚层"返回一个挡人的方块 ⇒ `scan_route` 必须**报出来** ✓ 并写进图 ✓
  O2 绕得开：把那一格放进 `blocked` ⇒ 规划出来的路线**不许再包含它** ✓
  O3 预算诚实：格子数 > 预算 ⇒ 必须 `left>0` ✓（不许把"没探"说成"干净"✗）
  O4 通道坏了就收手：探到一半**读失败**（空串 ✓）⇒ 必须 `aborted=True` ✓ 且**立刻停** ✓
     （★这一条是那次"队列堆到 16"的教训 ✗ 硬发只会更糟 ✓）
  O5 有节流：每次探测之间有 `pace` 秒 ✓（不许连着轰 ✗）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import mapread as MR  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

out: list[str] = []


class StubReader(MR.Reader):
    """★打桩的 Reader★ ✓：不连游戏 ✓ 由脚本决定每一格"读到什么"✓"""

    def __init__(self, world: dict, fail_after: int | None = None):
        self.world = world              # {(x,y,z): 方块名}
        self.calls = []
        self.fail_after = fail_after
        self.cache = ROOT / "logs" / "map_cache"

    def probe_cell(self, x, y, z) -> str:
        self.calls.append((x, y, z))
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            return ""                   # ← 空串 = **读失败** ✓（通道出问题的信号 ✓）
        return self.world.get((x, y, z), "minecraft:air")


def main() -> int:
    LEVEL = 71
    # 造一条 6 格的"路" ✓ 其中第 4 格脚层被一个**挡人的方块**占着 ✓（地图不该预先知道它 ✓）
    route = [(4100 + i, LEVEL, 10) for i in range(6)]
    world = {route[3]: "computercraft:computer_command"}
    m = MR.Map(4095, LEVEL - 6, 5, 4110, LEVEL + 5, 15)
    r = StubReader(world)

    # ── O1 探得出 ＋ O5 节流 ──────────────────────────────────────────────
    t0 = time.time()
    sw = r.scan_route(m, route, LEVEL, budget=20, pace=0.05)
    dt = time.time() - t0
    hit = [(x, z, n) for (x, z, n) in sw["found"]]
    o1 = (len(hit) == 1) and (hit[0][2] == "computercraft:computer_command")
    inmap = m.cols.get((route[3][0], route[3][2]), {}).get(LEVEL) == "computercraft:computer_command"
    o5 = dt >= 0.05 * max(0, sw["probed"] - 1)          # 有节流 ⇒ 耗时至少 ≈ pace×次数 ✓
    out.append("O1 探到障碍 = %s ｜ 报出 %s ｜ 写进图 = %s ⇒ %s"
               % (len(hit) == 1, hit, inmap, o1 and inmap))
    out.append("O5 节流：探 %d 次用了 %.2f 秒（pace=0.05 ✓ 至少 %.2f）⇒ %s"
               % (sw["probed"], dt, 0.05 * max(0, sw["probed"] - 1), o5))
    o1 = o1 and inmap

    # ── O2 绕得开 ─────────────────────────────────────────────────────────
    import pathplan as PP
    blocked = {(route[3][0], route[3][2])}
    # 给整条路铺上地板 ✓ 否则"站不住"会把规划挡掉 ✓（那样测的就不是"绕障碍"了 ✗）
    for (x, y, z) in route:
        for dx in (-2, -1, 0, 1, 2):
            for dz in (-2, -1, 0, 1, 2):
                m.cols.setdefault((x + dx, z + dz), {})[LEVEL - 1] = "minecraft:stone"
    pl = PP.Planner(m, level=LEVEL, blocked=blocked)
    reg = pl.region(route[0][0], route[0][2])
    pts, why = pl.plan(route[0][0], route[0][2], route[-1][0], route[-1][2], region=reg)
    onroute = bool(pts) and any((int(px), int(pz)) in blocked for (px, _py, pz) in pts)
    o2 = bool(pts) and (not onroute)
    out.append("O2 绕开障碍：规划 %d 航点（%s）｜ 路线里含障碍格=%s ⇒ %s"
               % (len(pts) if pts else 0, why[:60], onroute, o2))

    # ── O3 预算诚实 ───────────────────────────────────────────────────────
    r2 = StubReader({})
    sw2 = r2.scan_route(m, [(4200 + i, LEVEL, 10) for i in range(30)], LEVEL, budget=6, pace=0.0)
    o3 = (sw2["left"] > 0) and (sw2["probed"] <= 6)
    out.append("O3 预算：探 %d 次（≤6 ✓）｜ 没探的 %d 格 ⇒ 报出来了 ⇒ %s"
               % (sw2["probed"], sw2["left"], o3))

    # ── O4 通道坏了就收手 ─────────────────────────────────────────────────
    r3 = StubReader({}, fail_after=2)
    sw3 = r3.scan_route(m, [(4300 + i, LEVEL, 10) for i in range(20)], LEVEL, budget=20, pace=0.0)
    o4 = bool(sw3.get("aborted")) and (len(r3.calls) <= 4)   # 第 3 次就该停 ✓ 不许继续轰 ✗
    out.append("O4 读失败即收手：aborted=%s ｜ 实际发了 %d 次探测 ⇒ %s"
               % (sw3.get("aborted"), len(r3.calls), o4))

    ok = o1 and o2 and o3 and o4 and o5
    out.append("O1 %s ｜ O2 %s ｜ O3 %s ｜ O4 %s ｜ O5 %s" % (o1, o2, o3, o4, o5))
    out.append("=> %s" % ("PASS" if ok else "FAIL"))
    txt = "\n".join(out)
    (ROOT / "logs" / "ob_unit_test.txt").write_text(txt, encoding="utf-8")
    print(MR.ascii_only(txt))
    return 0 if ok else 1


raise SystemExit(main())
