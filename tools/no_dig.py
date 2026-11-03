#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""no_dig.py -- 模块 I 施工许可层：**不可挖区域**黑名单（用户口径：申明哪些地方不能挖）

用户规格（docs/方案-拟人化模块.md §6.3 / §10.1）：
  * 「破坏性行为 —— 一般而言是**申明哪些地方不能挖**」⇒ **黑名单**，不是白名单限区
  * 默认五类：**家 / 屋 / 箱子周围 3 格 / 产线区 / 农田（已种地）**
  * 每条带**理由** ＋ **可随时删**

接口（其他模块只走这三条）：
    allowed(pos)        -> (bool, zone_or_None)      # ★动手前必问★
    forbid(...)         -> 加一条区域（带理由）
    release(name)       -> 删一条
    list_zones()        -> 全部区域

★为什么必须集中一处：**同一个判断只许一处实现**（§79.471 的教训）——
  挖／放／用 三条路径都要问它，绝不允许各自写一份。
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STATE = ROOT / "state" / "no_dig.json"

DEFAULT_ZONES = [
    # name, box(lo xyz, hi xyz), why   —— ★家／屋 用工程的真实 bbox★
    ("家", (4115, 71, 19, 4129, 79, 32), "这是家 ✗ 挖了就没地方住"),
    ("屋", (4115, 71, 19, 4129, 79, 32), "室内空间 ✗ 不许破坏"),
    # ★箱子周围 3 格：位置未登记 ⇒ 空列表，等感知层发现箱子后自动补★
    # ★产线区：还没开始搭 ⇒ 空★
    # ★农田／已种地：还没种 ⇒ 空（一旦种上就 forbid 进来）★
]


def _load() -> dict:
    if not STATE.is_file():
        d = {"schema": "dshbridge/no_dig@1", "zones": [
            {"name": n, "box": list(b), "why": w, "created": "2026-11-01"}
            for (n, b, w) in DEFAULT_ZONES
        ]}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return d
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception as exc:              # ★不许静默✗★
        print("no_dig 读 %s 失败：%r ⇒ 按「全部禁止」处理（保守）" % (STATE, exc), file=sys.stderr)
        return {"schema": "dshbridge/no_dig@1", "zones": [], "_broken": True}
    if not isinstance(d, dict) or "zones" not in d:
        print("no_dig 状态文件形状不对 ⇒ 按空处理", file=sys.stderr)
        return {"schema": "dshbridge/no_dig@1", "zones": [], "_broken": True}
    return d


def _save(d: dict) -> None:
    d.pop("_broken", None)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _in(box, pos) -> bool:
    x, y, z = pos
    return (box[0] <= x <= box[3] and box[1] <= y <= box[4] and box[2] <= z <= box[5])


def allowed(pos) -> tuple:
    """★这一格能不能动手✗★ ⇒ `(True, None)` 或 `(False, zone_dict)`

    ★状态文件坏了 ⇒ **一律禁止**（★宁可不动手 ✗ 不许瞎挖✗★）✗★
    """
    d = _load()
    if d.get("_broken"):
        return False, {"name": "★状态坏了★", "why": "no_dig.json 读不出来 ⇒ 保守全禁"}
    for z in d.get("zones") or []:
        box = z.get("box")
        if not box or len(box) != 6:
            continue
        if _in(box, pos):
            return False, z
    return True, None


def forbid(name: str, box, why: str) -> dict:
    """加一条区域（★同名的覆盖 ✗ 不重复堆✗★）"""
    box = list(box)
    if len(box) != 6:
        raise ValueError("box 必须是 6 个数（lo xyz ＋ hi xyz）")
    d = _load()
    zones = [z for z in (d.get("zones") or []) if z.get("name") != name]
    zones.append({"name": name, "box": box, "why": why,
                  "created": time.strftime("%Y-%m-%d %H:%M")})
    d["zones"] = zones
    _save(d)
    return zones[-1]


def release(name: str) -> bool:
    """删一条（★用户随时可撤✗★）"""
    d = _load()
    before = len(d.get("zones") or [])
    d["zones"] = [z for z in (d.get("zones") or []) if z.get("name") != name]
    _save(d)
    return len(d["zones"]) < before


def list_zones() -> list:
    return list(_load().get("zones") or [])


def main(argv) -> int:
    if "--list" in argv:
        for z in list_zones():
            print("  %-10s box=%s  why=%s"
                  % (z.get("name"), z.get("box"), (z.get("why") or "")[:48]))
        return 0
    if "--check" in argv:
        i = argv.index("--check")
        x, y, z = (int(v) for v in argv[i + 1].split(","))
        ok, zone = allowed((x, y, z))
        print("NODIG pos=%d,%d,%d allowed=%s zone=%s why=%s"
              % (x, y, z, "true" if ok else "false",
                 (zone or {}).get("name", "-"), (zone or {}).get("why", "-")))
        return 0 if ok else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
