#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory.py -- 模块 L6 记忆官：★地标 ＋ 选择性保留✗★

规格（§2.8 / §21）：
  * 地标：`home` ／ `chest:<name>` ／ `crafting:<name>` ／ `bed` ／ `last_pos`
  * ★持久化 ✗ 重启后逐字读回✗★
  * ★**选择性保留**✗★（★用户原话："不能让日志一直累计"✗★）⇒ 每类封顶 ✗ 超了丢**最旧**的✗★
  * ★**地标用什么认**✗★：★问**方块分类**（★有没有方块实体✗★）✗ 不许写名字表✗★ ✓

存储：`state/landmarks.json`
  {"schema":"dshbridge/landmarks@1","kinds":{"chest":[{name,pos,at,meta},...]}, ...}
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

STATE = ROOT / "state" / "landmarks.json"
KINDS = ("home", "chest", "crafting", "bed", "last_pos", "mine", "farm")
CAP = {"home": 3, "chest": 60, "crafting": 20, "bed": 5, "last_pos": 20,
       "mine": 30, "farm": 20}


def _load(path=None) -> dict:
    p = pathlib.Path(path) if path else STATE
    if not p.is_file():
        return {"schema": "dshbridge/landmarks@1", "kinds": {}, "saved_at": None}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:              # ★不许静默✗★
        print("memory: 读 %s 失败 %r ⇒ 从空开始" % (p, exc), file=sys.stderr)
        return {"schema": "dshbridge/landmarks@1", "kinds": {}, "saved_at": None}
    d.setdefault("kinds", {})
    return d


def _save(d: dict, path=None) -> None:
    p = pathlib.Path(path) if path else STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    d["saved_at"] = time.time()
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def put(kind: str, name: str, pos, meta=None, path=None) -> dict:
    """★记一个地标 ✗ 同名覆盖✗★（★位置更新到最新✗★）"""
    if kind not in KINDS:
        raise ValueError("unknown landmark kind: %r (允许 %s)" % (kind, ",".join(KINDS)))
    d = _load(path)
    arr = d["kinds"].setdefault(kind, [])
    rec = {"name": str(name)[:40], "pos": [int(v) for v in pos],
           "at": time.time(), "meta": meta or {}}
    arr[:] = [x for x in arr if x.get("name") != rec["name"]]
    arr.append(rec)
    # ★选择性保留✗★：★只留最新的 cap 个（★丢最旧✗★）
    cap = CAP.get(kind, 20)
    if len(arr) > cap:
        arr.sort(key=lambda x: float(x.get("at") or 0))
        del arr[: len(arr) - cap]
    _save(d, path)
    return rec


def get(kind: str, name: str = None, path=None):
    d = _load(path)
    arr = d["kinds"].get(kind) or []
    if name is None:
        return arr[-1] if arr else None
    for x in arr:
        if x.get("name") == name:
            return x
    return None


def all_of(kind: str, path=None) -> list:
    return list((_load(path)["kinds"].get(kind) or []))


def near(kind: str, pos, radius: float = 8.0, path=None) -> list:
    """★按距离找地标✗★（★切比雪夫距离 ✗ 与方块格口径一致✗★）"""
    x, y, z = (int(v) for v in pos)
    out = []
    for rec in all_of(kind, path):
        px, py, pz = rec["pos"]
        d = max(abs(px - x), abs(py - y), abs(pz - z))
        if d <= radius:
            out.append({**rec, "dist": d})
    out.sort(key=lambda r: r["dist"])
    return out


def forget(kind: str, name: str, path=None) -> bool:
    d = _load(path)
    arr = d["kinds"].get(kind) or []
    before = len(arr)
    d["kinds"][kind] = [x for x in arr if x.get("name") != name]
    _save(d, path)
    return len(d["kinds"][kind]) < before


def landmark_kind(block_id: str) -> str:
    """★这块方块能不能当地标 ✗ 用什么类别✗★

    ★口径✗★：★问**方块分类**（★有方块实体 ⇒ 可交互 ⇒ 地标候选✗★）✗ **不认名字**✗★ ✓
    返回：`interactable` ／ `""`（★不是地标✗★）
    """
    try:
        import mapread as MR
        return "interactable" if MR.machine_family(block_id) else ""
    except Exception as exc:              # ★不许静默✗★
        print("memory: 问分类失败 %r" % (exc,), file=sys.stderr)
        return ""


def dump(path=None) -> dict:
    d = _load(path)
    return {k: len(v or []) for k, v in (d.get("kinds") or {}).items()}


def main(argv) -> int:
    if argv and argv[0] == "--dump":
        print("地标：" + json.dumps(dump(), ensure_ascii=False))
        return 0
    if argv and argv[0] == "--kind":
        print("landmark_kind(%s) = %r" % (argv[1], landmark_kind(argv[1])))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
