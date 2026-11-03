#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reasons.py -- 模块 G 的留痕通道：**有后果的事件必须可解释**（★且不许无限累计✗★）

用户口径：
  * 「做无意义的事**不需要**理由；但是**在做事件的时候**至少一些地方要**申明理由**，
    **可以放在后台日志**」⇒ N8'：mut／inv delta／damage 都要能在同一时间窗找到理由
  * 「这个在做记忆系统时要记得**选择性保留内容** ✗ **毕竟不能让日志一直累计**」⇒ **保留策略**

保留策略（★选择性保留 ✗ 不是全留也不是全删✗★）：
  1. **按天分文件**：`logs/reasons-YYYYMMDD.jsonl`（★今天的写在当天文件里✗★）
  2. **单文件上限** MAX_LINES（默认 4000）✗ 超了就 `prune()` ⇒ **只保留**：
       · 最后 KEEP_TAIL 条（默认 800）
       · 以及**重要理由**（带 `important=True` 或 action ∈ IMPORTANT_ACTIONS）
  3. **跨天汇总**：`logs/reasons_index.json` 记每天的行数/首末时间（★记忆层以后读它✗★）
  4. **旧天文件**保留最近 KEEP_DAYS 天（默认 14）✗ 更早的**只留 index ✗ 内容删掉**✗★
"""
from __future__ import annotations

import datetime as _dt
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

LOGDIR = ROOT / "logs"
INDEX = LOGDIR / "reasons_index.json"
MAX_LINES = 4000
KEEP_TAIL = 800
KEEP_DAYS = 14
IMPORTANT_ACTIONS = ("dig", "place", "no_dig_zone", "abort", "fail", "damage", "eat")


def _day(ts=None) -> str:
    return _dt.datetime.fromtimestamp(ts if ts is not None else time.time()).strftime("%Y%m%d")


def log_path(ts=None) -> pathlib.Path:
    return LOGDIR / ("reasons-%s.jsonl" % _day(ts))


def _important(rec: dict) -> bool:
    if rec.get("important"):
        return True
    return str(rec.get("action") or "") in IMPORTANT_ACTIONS


def because(reason: str, mission: str = "", pos=None, action: str = "",
            important: bool = False, **extra) -> dict:
    """记一条理由（★改了世界就一定要有它✗★）✗ 写完顺手按策略裁剪"""
    rec = {"ts": time.time(), "day": _day(),
           "reason": str(reason)[:120], "mission": str(mission)[:120],
           "action": str(action)[:24], "pos": list(pos) if pos else None}
    if important:
        rec["important"] = True
    for k, v in extra.items():
        rec[str(k)] = v
    p = log_path(rec["ts"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    prune(p); _rec_event_important(rec, p)    # ★H 接线：重要理由同时进事件账本✗★
    return rec


def prune(path=None) -> dict:
    """★选择性保留✗★ ⇒ 单文件超上限时：留最后 KEEP_TAIL ＋ 全部重要记录"""
    p = pathlib.Path(path) if path else log_path()
    if not p.is_file():
        return {"path": str(p), "lines": 0, "kept": 0, "dropped": 0}
    lines = [l for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    n = len(lines)
    if n <= MAX_LINES:
        return {"path": str(p), "lines": n, "kept": n, "dropped": 0}
    keep = []
    seen_keep = set()
    tail = lines[-KEEP_TAIL:]
    for l in tail:
        if l not in seen_keep:
            keep.append(l)
            seen_keep.add(l)
    for l in lines[:-KEEP_TAIL]:
        try:
            rec = json.loads(l)
        except Exception:
            continue
        if _important(rec) and l not in seen_keep:
            keep.append(l)
            seen_keep.add(l)
    p.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return {"path": str(p), "lines": n, "kept": len(keep), "dropped": n - len(keep)}


def rotate(days: int = KEEP_DAYS) -> dict:
    """★旧天文件：只留最近 days 天 ✗ 更早的删掉（★但 index 里留一行统计✗★）"""
    idx = _load_index()
    cut = time.time() - days * 86400
    dropped = []
    for p in sorted(LOGDIR.glob("reasons-*.jsonl")):
        try:
            day = p.stem.split("-", 1)[1]
            ts = _dt.datetime.strptime(day, "%Y%m%d").timestamp()
        except Exception:
            continue
        if ts < cut:
            idx.setdefault("days", {}).setdefault(day, {})["dropped_at"] = time.strftime("%Y-%m-%d %H:%M")
            dropped.append(p.name)
            p.unlink()
    _save_index(idx)
    return {"dropped": dropped, "kept_days": days}


def _load_index() -> dict:
    if not INDEX.is_file():
        return {"schema": "dshbridge/reasons_index@1", "days": {}}
    try:
        d = json.loads(INDEX.read_text(encoding="utf-8"))
        d.setdefault("days", {})
        return d
    except Exception as exc:              # ★不许静默✗★
        print("reasons index 坏了：%r ⇒ 重建" % (exc,), file=sys.stderr)
        return {"schema": "dshbridge/reasons_index@1", "days": {}}


def _save_index(d: dict) -> None:
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def update_index() -> dict:
    idx = _load_index()
    for p in sorted(LOGDIR.glob("reasons-*.jsonl")):
        day = p.stem.split("-", 1)[1]
        recs = load(p)
        idx["days"][day] = {"lines": len(recs),
                            "first": recs[0].get("ts") if recs else None,
                            "last": recs[-1].get("ts") if recs else None}
    _save_index(idx)
    return idx


def load(path=None, days: int = 3) -> list:
    """读最近 days 天的记录（★记忆层只该读窗口内的 ✗ 不是全历史✗★）"""
    if path is not None:
        p = pathlib.Path(path)
        return _read(p)
    out = []
    cut = time.time() - days * 86400
    for p in sorted(LOGDIR.glob("reasons-*.jsonl")):
        try:
            day = p.stem.split("-", 1)[1]
            ts = _dt.datetime.strptime(day, "%Y%m%d").timestamp()
        except Exception:
            continue
        if ts >= cut:
            out.extend(_read(p))
    out.sort(key=lambda r: float(r.get("ts") or 0))
    return out


def _read(p: pathlib.Path) -> list:
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception as exc:            # ★坏行要报 ✗ 不许静默吃掉✗★
            print("reasons 坏行 %s：%r（%r）" % (p.name, line[:60], exc), file=sys.stderr)
    return out


def main(argv) -> int:
    if "--prune" in argv:
        print(prune())
        return 0
    if "--rotate" in argv:
        print(rotate())
        return 0
    if "--index" in argv:
        print(json.dumps(update_index(), ensure_ascii=False)[:600])
        return 0
    recs = load(days=2)
    print("REASONS %d 条 ｜ 今天文件 %s ｜ 上限 %d 行 / 留 %d 行 / 保 %d 天"
          % (len(recs), log_path().name, MAX_LINES, KEEP_TAIL, KEEP_DAYS))
    for r in recs[-8:]:
        print("  day=%s mission=%s action=%s reason=%s"
              % (r.get("day"), r.get("mission"), r.get("action"), r.get("reason")))
    return 0


# ── H 接线：重要理由 → 事件账本（★默认关 ⇒ 既有行为零变化✗★）──────────────
#   ★注册方：`primitives.Primitives(log=True)`；只有**重要理由**才转发✗★
_EVENT_RECORDER = None


def set_event_recorder(fn) -> None:
    """注册"重要理由 → 事件账本"的记录器：`fn(rec)`；`fn=None` ⇒ 关掉✗★"""
    global _EVENT_RECORDER
    _EVENT_RECORDER = fn if callable(fn) else None


def _rec_event_important(rec: dict, path) -> None:
    """`because()` 的尾巴调它：★只有重要理由同时进事件账本✗★（best-effort 不抛）"""
    if _EVENT_RECORDER is None or not _important(rec):
        return
    try:
        _EVENT_RECORDER(dict(rec, log_file=pathlib.Path(path).name))
    except Exception as exc:                  # ★不许静默✗★（也不许把留痕带崩）
        print("reasons: 事件记录失败 %r" % (exc,), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
