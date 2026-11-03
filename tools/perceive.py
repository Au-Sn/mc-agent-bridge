#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""perceive.py -- 模块 B 感知层：一次调用给出一份结构化世界快照

用户规格（docs/方案-拟人化模块.md §2.2 / §19）：
  * 「世界的执行和获取都应该**实时**获得世界信息」⇒ 这是"获取"那一半
  * 方块性质**一律问分类**（★严禁写名字表 ✗ 普适性✗★）
  * 延迟硬约束：★chat 0 次往返 ✗ query ≤1 次往返★ ⇒ 所以有**缓存**这条快路

往返预算：
  snapshot()   = 1（digest）＋ 1（scan）＋ ≤caps 次（dshcaps）  => 默认 ≤4
  read_cache() = **0 次往返**（只读本地文件）                  => 给前台对话官用
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CACHE = ROOT / "state" / "perceive_cache.json"
DEFAULT_CACHE_MAX_MS = 1500


def _core():
    import mcp_core as C
    return C


def _mapread():
    import mapread as MR
    return MR


RE_POS = re.compile(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)")


def _parse_digest(txt: str) -> dict:
    """从 `dshdigest` 回执里取字段（每个字段用精确模式，不贪吃到下一个逗号）"""

    def one(pat, cast=str, default=None):
        m = re.search(pat, txt)
        if not m:
            return default
        try:
            return cast(m.group(1))
        except Exception:
            return default

    m = RE_POS.search(txt)
    if not m:
        return {}
    x, y, z = (float(m.group(i)) for i in (1, 2, 3))
    return {
        "pos": (x, y, z), "x": x, "y": y, "z": z,
        "feet": max(1, math.ceil(y - 1e-9)),
        "onground": one(r"onground=(true|false)", str, "?") == "true",
        "hp": one(r"hp=([\d.]+)", float),
        "food": one(r"food=(\d+)", int),
        "items": one(r"items=(\d+)", int),
        "held": one(r"held=([\w:./-]+)"),
        "mode": one(r"mode=(\w+)"),
        "time": one(r"\btime=(\d+)", int),
        "day": one(r"\bday=(\d+)", int),
    }


# ★字符类必须含 = ✗ 否则 ctive=false 会被截成 ctive ⇒ 属性全丢（§79.489 实测）✗
CELL_RE = re.compile(r"(-?\d+),(-?\d+),(-?\d+):([a-z0-9_.:/=,\-]+)")


def _parse_cells(txt: str):
    """`dshscan` 的格列表：`x,y,z:name,prop=val,...`（属性自带 —— §79.488 的意外收获）"""
    out = []
    for a, b, c, rest in CELL_RE.findall(txt):
        parts = rest.split(",")
        name = parts[0]
        props = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                props[k] = v
        out.append({"pos": (int(a), int(b), int(c)), "id": name, "props": props})
    return out


def snapshot(radius: int = 6, caps: int = 2, timeout: float = 45.0) -> dict:
    """做一次完整快照（要花几次往返 ⇒ 给"预取/后台"用；前台请用 read_cache）"""
    C = _core()
    MR = _mapread()
    t0 = time.time()
    trips = 0

    d = (C.dsh("dshdigest", timeout) or "").strip()
    trips += 1
    bot = _parse_digest(d)
    if not bot:
        return {"ts": time.time(), "error": "no_bot", "raw": d[:200], "round_trips": trips}

    bx, fy, bz = int(bot["x"]), int(bot["feet"]), int(bot["z"])
    lo = (bx - radius, fy - 3, bz - radius)
    hi = (bx + radius, fy + 4, bz + radius)
    scan = (C.dsh('dshscan %d %d %d %d %d %d ":" 1900 1' % (lo + hi), timeout) or "")
    trips += 1
    cells = _parse_cells(scan)
    if not cells:
        # ★空扫描 = 命令失败（★例如 max 超出 1..2000 的校验✗★）⇒ **必须报**✗ 不许静默 ✓
        return {"ts": time.time(), "error": "scan_empty", "raw": scan[:220],
                "bot": bot, "round_trips": trips}

    nearby = {}
    for c in cells:
        e = nearby.setdefault(c["id"], {"count": 0, "phys_family": "",
                                        "is_floor": None, "blocks_space": None,
                                        "machine": ""})
        e["count"] += 1
    for name, e in nearby.items():
        try:
            e["is_floor"] = bool(MR.is_floor(name))
            e["blocks_space"] = bool(MR.blocks_space(name))
            e["machine"] = MR.machine_family(name)
            fam, _how = MR._kb_phys(name)
            e["phys_family"] = fam or ""
        except Exception as exc:          # 不许静默
            print("perceive 分类失败 %r: %r" % (name, exc), file=sys.stderr)

    machines = []
    for c in cells:
        if not nearby.get(c["id"], {}).get("machine"):
            continue
        facing = (c["props"].get("facing")
                  or c["props"].get("horizontal_facing")
                  or c["props"].get("axis")
                  or c["props"].get("rotation"))
        machines.append({"pos": c["pos"], "id": c["id"], "facing": facing,
                         "props": c["props"], "caps": None})

    for m in machines[:caps]:
        cp = (C.dsh("dshcaps %d %d %d" % m["pos"], timeout) or "").strip()
        trips += 1
        m["caps"] = cp

    hazards = []
    for c in cells:
        if any(k in c["id"] for k in ("lava", "fire", "magma", "cactus", "sweet_berry")):
            hazards.append({"pos": c["pos"], "id": c["id"], "why": "dangerous_block"})

    return {"ts": time.time(), "stale_ms": 0, "bot": bot,
            "time": {"time": bot.get("time"), "day": bot.get("day")},
            "machines": machines, "hazards": hazards, "nearby": nearby,
            "box": {"lo": lo, "hi": hi}, "round_trips": trips,
            "build_ms": int((time.time() - t0) * 1000)}


def write_cache(snap=None, **kw) -> dict:
    snap = snap or snapshot(**kw)
    snap["cached_at"] = time.time()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return snap


def read_cache(max_ms: int = DEFAULT_CACHE_MAX_MS):
    """0 次往返（只读本地文件）⇒ 前台对话官用它；过期回 None（由调用方决定要不要刷新）"""
    if not CACHE.is_file():
        return None
    try:
        snap = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception as exc:              # 不许静默
        print("perceive 读缓存失败：%r" % (exc,), file=sys.stderr)
        return None
    age = (time.time() - float(snap.get("cached_at") or 0)) * 1000.0
    snap["stale_ms"] = int(age)
    if age > max_ms:
        return None
    return snap


def main(argv) -> int:
    if "--cache" in argv:
        snap = write_cache()
        print("PERCEIVE cached ok=%d machines=%d kinds=%d trips=%d build_ms=%d"
              % (0 if snap.get("error") else 1, len(snap.get("machines") or []),
                 len(snap.get("nearby") or {}), snap.get("round_trips", 0),
                 snap.get("build_ms", 0)))
        return 0 if not snap.get("error") else 1
    if "--show-cache" in argv:
        snap = read_cache(max_ms=10 ** 9)
        print(json.dumps(snap, ensure_ascii=False, indent=1)[:3000] if snap else "（没有缓存）")
        return 0
    snap = snapshot()
    print(json.dumps(snap, ensure_ascii=False, indent=1)[:4000])
    return 0 if not snap.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
