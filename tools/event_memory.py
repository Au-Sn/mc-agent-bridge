#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""event_memory.py -- 模块 H 事件记忆：★事件层 → 事实层 → 检索层✗★

规格（docs/方案-拟人化模块.md §2.8 / §21 / §16 M6）：
  * 用户：「**记不住"发生过什么"**」⇒ 事件记忆（挖了多少／被炸过／箱子整理过／哪个任务失败）
  * 用户：「这个在做记忆系统时要记得 **选择性保留内容** ✗ **毕竟不能让日志一直累计**」
    ⇒ 三条保留规则（与 `tools/reasons.py` 同口径，但这里落**单文件状态** ✗ 不是日志流）：
      ① **按天**：非重要事件只留最近 KEEP_DAYS 天；跨天统计一直在 `days` 里（★index✗★）
      ② **上限**：全局 MAX_EVENTS ＋ 每天非重要事件 MAX_PER_DAY
      ③ **重要不丢**：`IMPORTANT_KINDS`（改世界／花资源／受伤／失败…）与显式 `important=True`
         在任何裁剪里**一条都不删**
  * 事件必须挂**证据指针**（事件 → 哪条回执 / 哪个 job）⇒ 检索结果带得回来
  * 落盘 `state/event_memory.json`：schema ＋ **原子写**（同目录 tmp ＋ `os.replace`）
  * ★坏文件必须抛 `EventMemoryError`✗★（不许静默从空开始 —— 那会把"记忆丢了"冒充
    "没发生过"，正是 P-family 的病）

三层（每层职责单一 ✗ 不许越层编造）：
  ① **事件层**：`append(kind, what, evidence, when, where, objects, important, ...)`
     —— 只追加事实（带证据指针），不写"我觉得"
  ② **事实层**：`facts(day)` / `derive_facts(events)` —— 由事件**推导**的聚合（计数／最后位置／
     重要项），不手写、不覆盖事件；没事件就返回空事实（★不冒充✗★）
  ③ **检索层**：`query(kind/time_window/place/importance)` / `recent(n)` / `since(ts)` /
     `summarize(day)` —— 只读，返回带 `evidence` 指针的副本

用法：
    import event_memory as EM
    EM.append("dig", "挖了 3 个铁矿石", evidence={"kind": "receipt", "ref": "dshdig ..."},
              where=(4120, 71, 16), objects=["iron_ore"])
    EM.query(kind="dig", time_window=(t0, t1), place=(4120, 71, 16), radius=2)
    EM.recent(10) / EM.since(t0) / EM.summarize("20261102") / EM.facts()

CLI（离线可跑；`--state` 换文件）：
    py tools/event_memory.py --stats
    py tools/event_memory.py --append '{"kind":"dig","what":"...","evidence":{"kind":"job","id":"j1"}}'
    py tools/event_memory.py --query '{"kind":"dig"}' ／ --recent 10 ／ --summarize 20261102
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCHEMA = "dshbridge/event_memory@1"
STATE = ROOT / "state" / "event_memory.json"

# ★保留策略（★与 reasons.py 同口径 ✗ 但这里是状态文件不是日志流✗★）
MAX_EVENTS = 2000          # 全局上限（重要事件不计入裁剪目标，但计入真实条数）
MAX_PER_DAY = 500          # 每天非重要事件上限
KEEP_DAYS = 14             # 非重要事件最多留多少天（更早的只留 days 统计）

# ★重要 = 改世界／花资源／受伤／失败类（★reasons.py 的 IMPORTANT_ACTIONS ＋ A 任务层事件✗★）
try:
    import reasons as _R
    _BASE_IMPORTANT = tuple(_R.IMPORTANT_ACTIONS)
except Exception as _exc:                    # ★不许静默✗★
    print("event_memory: 读 reasons.IMPORTANT_ACTIONS 失败 %r ⇒ 用内置表" % (_exc,),
          file=sys.stderr)
    _BASE_IMPORTANT = ("dig", "place", "no_dig_zone", "abort", "fail", "damage", "eat")
IMPORTANT_KINDS = tuple(dict.fromkeys(
    _BASE_IMPORTANT + ("interrupt", "cancel", "task", "death", "trade", "consume")))

ZERO_DAY = {"n": 0, "first": None, "last": None, "kept": 0}


class EventMemoryError(RuntimeError):
    """事件记忆文件坏了／数据形状不对（★必须抛 ✗ 不许静默从空开始✗★）。"""


# ── 小工具 ────────────────────────────────────────────────────────────────
def _now() -> float:
    return time.time()


def day_of(ts=None) -> str:
    """★时间 ⇒ 天键 `YYYYMMDD`✗★（与 reasons.py 的按天分文件同口径）"""
    t = _now() if ts is None else float(ts)
    return _dt.datetime.fromtimestamp(t).strftime("%Y%m%d")


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))


def _fresh() -> dict:
    return {"schema": SCHEMA, "seq": 0, "days": {}, "events": [], "saved_at": None,
            "retention": {"max_events": MAX_EVENTS, "max_per_day": MAX_PER_DAY,
                          "keep_days": KEEP_DAYS}}


def _path(path=None) -> pathlib.Path:
    return pathlib.Path(path) if path else STATE


# ── 事件层：校验 ＋ 追加 ──────────────────────────────────────────────────
def _norm_where(where):
    if where is None:
        return None
    try:
        vals = list(where)
    except TypeError:
        raise ValueError("where 必须是 (x,y,z)：%r" % (where,)) from None
    if len(vals) != 3:
        raise ValueError("where 必须有 3 个数（x,y,z）：%r" % (where,))
    try:
        return [int(v) for v in vals]
    except (TypeError, ValueError):
        raise ValueError("where 必须是整数坐标：%r" % (where,)) from None


def _norm_objects(objects):
    if objects is None:
        return []
    if isinstance(objects, str):
        raise ValueError("objects 必须是列表（不是裸字符串）：%r" % (objects,))
    out = []
    for o in objects:
        if isinstance(o, str):
            s = o.strip()
            if not s:
                raise ValueError("objects 里有空串 ⇒ 不记（★空数据不冒充✗★）")
            out.append({"id": s[:120]})
        elif isinstance(o, dict):
            oid = str(o.get("id") or o.get("name") or "").strip()
            if not oid:
                raise ValueError("objects 里的 dict 必须有 id/name：%r" % (o,))
            rec = {"id": oid[:120]}
            for k in ("count", "pos", "state", "meta"):
                if k in o:
                    rec[k] = o[k]
            out.append(rec)
        else:
            raise ValueError("objects 元素只收 str/dict：%r" % (o,))
    return out


def _norm_evidence(evidence):
    """★证据指针✗★：事件 → 哪条回执／哪个 job（检索时原样带回来）

    收：`"REF"` ／ `{"kind":"receipt"|"job"|"file"|"event"|"fake", "ref"/"id"/"job"/...}`。
    空指针 ⇒ **抛**（没有证据就不许记成事实）。
    """
    if evidence is None:
        return None
    if isinstance(evidence, str):
        s = evidence.strip()
        if not s:
            raise ValueError("evidence 空串 ⇒ 不许（没有证据就不算事实）")
        return {"kind": "text", "ref": s[:400]}
    if not isinstance(evidence, dict):
        raise ValueError("evidence 只收 str/dict：%r" % (evidence,))
    ref = None
    for k in ("ref", "id", "job", "receipt", "path", "reply"):
        v = evidence.get(k)
        if v not in (None, ""):
            ref = str(v)
            break
    if ref is None:
        raise ValueError("evidence 缺指针（要 ref/id/job/receipt/path 之一）：%r" % (evidence,))
    out = {"kind": str(evidence.get("kind") or "receipt")[:24], "ref": ref[:400]}
    for k in ("mission", "at", "meta", "why"):
        if k in evidence:
            out[k] = evidence[k]
    return out


def _norm_importance(importance, important):
    if importance is None:
        return "high" if important else "normal"
    s = str(importance).strip().lower()
    if s in ("high", "important", "2", "true"):
        return "high"
    if s in ("normal", "low", "0", "1", "false"):
        return "normal"
    raise ValueError("importance 只收 normal/high：%r" % (importance,))


def _norm_when(when):
    if when is None:
        return _now()
    if isinstance(when, bool) or not isinstance(when, (int, float)):
        raise ValueError("when 必须是 epoch 秒（数字）：%r" % (when,))
    t = float(when)
    if not (t > 0 and t < 1e12):
        raise ValueError("when 不像 epoch 秒：%r" % (when,))
    return t


def _make_event(ledger: dict, kind, what="", evidence=None, when=None, where=None,
                objects=None, importance=None, important=False, facts=None) -> dict:
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("kind 不能为空（★空数据不冒充✗★）")
    kind = kind.strip()
    if len(kind) > 40:
        raise ValueError("kind 太长（>40）：%r" % (kind,))
    imp = _norm_importance(importance, important)
    imp = "high" if (imp == "high" or kind in IMPORTANT_KINDS) else "normal"
    ev = _norm_evidence(evidence)
    if imp == "high" and ev is None:
        # ★N8'：「有后果的事件必须可解释」✗ 记忆层的第一道闸
        raise ValueError("★重要事件 %r 必须带证据指针★（有后果的事件必须能解释）" % (kind,))
    ts = _norm_when(when)
    rec = {"id": "evt-%06d" % (int(ledger.get("seq") or 0) + 1),
           "ts": round(ts, 3), "day": day_of(ts), "kind": kind,
           "what": str(what or "")[:400], "where": _norm_where(where),
           "objects": _norm_objects(objects), "evidence": ev,
           "important": imp == "high", "importance": imp,
           "recorded_at": round(_now(), 3)}
    if facts is not None:
        if not isinstance(facts, dict):
            raise ValueError("facts 必须是 dict：%r" % (facts,))
        rec["facts"] = facts
    return rec


def append(kind, what="", evidence=None, when=None, where=None, objects=None,
           importance=None, important=False, facts=None, path=None) -> dict:
    """★记一条事件（带证据指针）✗ 追加后**顺手按策略裁剪**✗★"""
    ledger = load(path)
    rec = _make_event(ledger, kind, what=what, evidence=evidence, when=when,
                      where=where, objects=objects, importance=importance,
                      important=important, facts=facts)
    ledger["events"].append(rec)
    ledger["seq"] = int(ledger.get("seq") or 0) + 1
    _bump_day(ledger, rec)
    prune(ledger)
    _atomic_save(ledger, path)
    return rec


def _bump_day(ledger: dict, rec: dict) -> None:
    d = ledger["days"].setdefault(rec["day"], dict(ZERO_DAY))
    d["n"] = int(d.get("n") or 0) + 1
    if d.get("first") is None:
        d["first"] = rec["ts"]
    d["last"] = rec["ts"]
    d["kept"] = int(d.get("kept") or 0) + 1


def append_many(events, path=None) -> list:
    """批量追加（★一次读写 ✗ 给导入/回放用✗★）—— 每条事件走同一套校验。"""
    if not isinstance(events, (list, tuple)):
        raise ValueError("append_many 要一个事件列表")
    ledger = load(path)
    out = []
    for e in events:
        if not isinstance(e, dict):
            raise ValueError("append_many 的元素必须是 dict：%r" % (e,))
        kw = dict(e)
        kind = kw.pop("kind", None)
        rec = _make_event(ledger, kind, **kw)
        ledger["events"].append(rec)
        ledger["seq"] = int(ledger.get("seq") or 0) + 1
        _bump_day(ledger, rec)
        out.append(rec)
    prune(ledger)
    _atomic_save(ledger, path)
    return out


# ── 选择性保留（★核心判据在这里 ✗ 纯函数好造红✗★）──────────────────────────
def prune(ledger: dict, now=None, max_events=None, max_per_day=None,
          keep_days=None) -> dict:
    """★选择性保留✗★：按天 ⇒ 每天上限 ⇒ 全局上限；**重要事件一条不删**。

    返回统计：`{before, after, dropped, important_kept, by_rule:{age, per_day, global}}`。
    ★口径✗★：重要事件不计入"要删的目标"；若重要事件本身超过上限 ⇒ **宁可超上限也不丢**。
    """
    now = _now() if now is None else float(now)
    max_events = MAX_EVENTS if max_events is None else int(max_events)
    max_per_day = MAX_PER_DAY if max_per_day is None else int(max_per_day)
    keep_days = KEEP_DAYS if keep_days is None else int(keep_days)
    if max_events < 0 or max_per_day < 0 or keep_days < 0:
        raise ValueError("保留上限不许为负")
    events = ledger.get("events")
    if not isinstance(events, list):
        raise EventMemoryError("ledger['events'] 不是列表 ⇒ 账本形状坏了")
    before = len(events)
    cutoff = now - keep_days * 86400
    stats = {"age": 0, "per_day": 0, "global": 0}

    # ① 按天：非重要且早于 cutoff ⇒ 删（跨天统计留在 days 里）
    kept = []
    for e in events:
        if e.get("important"):
            kept.append(e)
            continue
        if keep_days > 0 and float(e.get("ts") or 0) < cutoff:
            stats["age"] += 1
            continue
        kept.append(e)
    # ② 每天上限：同一天的非重要事件只留最新 max_per_day 条
    if max_per_day > 0:
        by_day = {}
        for e in kept:
            if not e.get("important"):
                by_day.setdefault(e.get("day"), []).append(e)
        drop_ids = set()
        for _day, arr in by_day.items():
            if len(arr) > max_per_day:
                for e in arr[: len(arr) - max_per_day]:
                    drop_ids.add(e.get("id"))
        if drop_ids:
            stats["per_day"] = sum(1 for e in kept
                                   if not e.get("important") and e.get("id") in drop_ids)
            kept = [e for e in kept if e.get("important") or e.get("id") not in drop_ids]
    # ③ 全局上限：超了从最旧的非重要开始丢
    if max_events >= 0 and len(kept) > max_events:
        excess = len(kept) - max_events
        out = []
        for e in kept:
            if excess > 0 and not e.get("important"):
                excess -= 1
                stats["global"] += 1
                continue
            out.append(e)
        kept = out
    ledger["events"] = kept
    # ★days 统计不因裁剪消失（★这就是「按天 index」✗★）
    for day, d in (ledger.get("days") or {}).items():
        if not isinstance(d, dict):
            raise EventMemoryError("ledger['days'][%r] 不是 dict" % (day,))
        d["kept"] = sum(1 for e in kept if e.get("day") == day)
    return {"before": before, "after": len(kept), "dropped": before - len(kept),
            "important_kept": sum(1 for e in kept if e.get("important")),
            "by_rule": stats}


# ── 事实层（由事件推导 ✗ 不手写✗★）────────────────────────────────────────
def derive_facts(events) -> list:
    """★事件 ⇒ 事实✗★：计数／最后位置／重要项／最近一条（纯函数 ✗ 可直接造红）"""
    evs = [e for e in (events or []) if isinstance(e, dict)]
    if not evs:
        return []                     # ★没事件就没事实 ✗ 不编造✗★
    facts = []
    by = {}
    for e in evs:
        key = (e.get("day"), e.get("kind"))
        by.setdefault(key, []).append(e)
    for (day, kind) in sorted(by, key=lambda k: (str(k[0]), str(k[1]))):
        arr = by[(day, kind)]
        facts.append({"fact": "count", "day": day, "kind": kind, "n": len(arr),
                      "evidence": [arr[0].get("id"), arr[-1].get("id")]})
    last_where = {}
    for e in evs:
        if e.get("where") is not None:
            last_where[e.get("kind")] = e
    for kind in sorted(last_where, key=str):
        e = last_where[kind]
        facts.append({"fact": "last_where", "kind": kind, "where": e.get("where"),
                      "ts": e.get("ts"), "evidence": [e.get("id")]})
    imp = [e for e in evs if e.get("important")]
    if imp:
        days = sorted({str(e.get("day")) for e in imp})
        for d in days:
            arr = [e for e in imp if str(e.get("day")) == d]
            facts.append({"fact": "important_count", "day": d, "n": len(arr),
                          "evidence": [e.get("id") for e in arr[-3:]]})
    tail = evs[-1]
    facts.append({"fact": "last_event", "kind": tail.get("kind"),
                  "ts": tail.get("ts"), "evidence": [tail.get("id")]})
    return facts


def facts(day=None, path=None) -> dict:
    """事实层入口：某天（默认今天）的事实表；没数据 ⇒ 空表 ＋ `has_data=False`。"""
    ledger = load(path)
    d = str(day or day_of())
    evs = [e for e in ledger["events"] if e.get("day") == d]
    return {"day": d, "has_data": bool(evs), "events": len(evs),
            "facts": derive_facts(evs)}


# ── 检索层 ────────────────────────────────────────────────────────────────
def _copies(arr) -> list:
    return [json.loads(json.dumps(e, ensure_ascii=False)) for e in arr]


def query(kind=None, time_window=None, since=None, until=None, place=None,
          radius=None, importance=None, important=None, limit=None, path=None) -> list:
    """★检索✗★：kind／时间窗／地点（含半径）／重要度；结果按 ts 升序、带证据指针。"""
    ledger = load(path)
    evs = list(ledger["events"])

    kinds = None
    if kind is not None:
        if isinstance(kind, str):
            if not kind.strip():
                raise ValueError("kind 不能是空串")
            kinds = {kind.strip()}
        elif isinstance(kind, (list, tuple, set)):
            kinds = {str(k).strip() for k in kind if str(k).strip()}
            if not kinds:
                raise ValueError("kind 列表为空")
        else:
            raise ValueError("kind 只收 str/列表：%r" % (kind,))

    t0 = t1 = None
    if time_window is not None:
        if isinstance(time_window, dict):
            t0 = time_window.get("since", time_window.get("start"))
            t1 = time_window.get("until", time_window.get("end"))
        else:
            try:
                t0, t1 = list(time_window)[:2]
            except (TypeError, ValueError):
                raise ValueError("time_window 只收 (start,end) 或 {'since','until'}") from None
    if since is not None:
        t0 = since
    if until is not None:
        t1 = until
    for name, v in (("since", t0), ("until", t1)):
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            raise ValueError("%s 必须是 epoch 秒：%r" % (name, v))
    if t0 is not None and t1 is not None and float(t0) > float(t1):
        raise ValueError("时间窗倒置（since > until）：%r > %r" % (t0, t1))   # ★不猜✗★

    cell = _norm_where(place) if place is not None else None
    r = 0 if radius is None else int(radius)
    if cell is not None and r < 0:
        raise ValueError("radius 不许为负：%r" % (r,))

    imp_filter = None
    if important is not None:
        if not isinstance(important, bool):
            raise ValueError("important 只收 bool：%r" % (important,))
        imp_filter = important
    if importance is not None:
        s = str(importance).strip().lower()
        if s in ("high", "important", "only_important"):
            imp_filter = True
        elif s in ("normal", "not_important", "low"):
            imp_filter = False
        else:
            raise ValueError("importance 只收 high/normal：%r" % (importance,))

    out = []
    for e in evs:
        if kinds is not None and e.get("kind") not in kinds:
            continue
        ts = float(e.get("ts") or 0)
        if t0 is not None and ts < float(t0):
            continue
        if t1 is not None and ts > float(t1):
            continue
        if cell is not None:
            w = e.get("where")
            if w is None:
                continue
            d = max(abs(int(w[0]) - cell[0]), abs(int(w[1]) - cell[1]),
                    abs(int(w[2]) - cell[2]))
            if d > r:
                continue
        if imp_filter is not None and bool(e.get("important")) is not imp_filter:
            continue
        out.append(e)
    out.sort(key=lambda e: float(e.get("ts") or 0))
    if limit is not None:
        n = int(limit)
        if n < 0:
            raise ValueError("limit 不许为负")
        out = out[-n:] if n else []
    return _copies(out)


def recent(n=20, path=None) -> list:
    """★最近 n 条✗★（n=0 ⇒ 空表 ✗ 不返回"全部"✗★）"""
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("recent(n) 的 n 必须是整数：%r" % (n,))
    if n < 0:
        raise ValueError("recent(n) 不许为负")
    if n == 0:
        return []
    ledger = load(path)
    return _copies(ledger["events"][-n:])


def since(ts, path=None) -> list:
    """★ts 之后（含）✗★的事件，按时间升序"""
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        raise ValueError("since(ts) 的 ts 必须是 epoch 秒：%r" % (ts,))
    return query(since=float(ts), path=path)


def summarize(day=None, path=None) -> dict:
    """★某天小结✗★：条数／分类计数／重要项／事实／首末时间；**没数据就空表**（不编造）。"""
    ledger = load(path)
    d = str(day or day_of())
    idx = (ledger.get("days") or {}).get(d)
    evs = [e for e in ledger["events"] if e.get("day") == d]
    by_kind = {}
    for e in evs:
        by_kind[e.get("kind")] = by_kind.get(e.get("kind"), 0) + 1
    return {"day": d, "known_day": idx is not None,
            "events": len(evs),
            "appended": int((idx or {}).get("n") or 0),
            "by_kind": dict(sorted(by_kind.items())),
            "important": [{"id": e.get("id"), "kind": e.get("kind"),
                           "what": e.get("what"), "evidence": e.get("evidence")}
                          for e in evs if e.get("important")],
            "facts": derive_facts(evs),
            "first_ts": evs[0].get("ts") if evs else None,
            "last_ts": evs[-1].get("ts") if evs else None}


def stats(path=None) -> dict:
    ledger = load(path)
    evs = ledger["events"]
    return {"events": len(evs),
            "important": sum(1 for e in evs if e.get("important")),
            "days": len(ledger.get("days") or {}),
            "seq": int(ledger.get("seq") or 0),
            "path": str(_path(path)),
            "retention": {"max_events": MAX_EVENTS, "max_per_day": MAX_PER_DAY,
                          "keep_days": KEEP_DAYS,
                          "important_kinds": len(IMPORTANT_KINDS)}}


def forget(path=None) -> None:
    """★清空记忆文件✗★（测试/用户显式要清才用；**不在正常路径里自动调**）"""
    p = _path(path)
    if p.is_file():
        p.unlink()


# ── 主流程接线入口（★原语／校验／理由都用它 ✗ 不做第二套✗★）─────────────
EVENT_PATH_ENV = "DSH_EVENT_MEMORY"


def wired_path(path=None):
    """接线时用的落盘路径（★判据运行不污染真实记忆账本✗★——测试世界/真实世界分离）：

    显式 `path` > 环境变量 `DSH_EVENT_MEMORY` > 判据运行 ⇒ **不写** >
    默认 `state/event_memory.json`（真实运行）。

    "判据运行"两档：① `check_all` 子的 `DSH_GATE_STARTED`；② ★进程入口是 `*_test.py`✗★
    （既有人工单跑判据时会构造 `Primitives(log=True)` ✗ 不许把假动作写进真实记忆✗★）。
    ★要判接线就**显式给 path 或 DSH_EVENT_MEMORY**（集成判据就是这么做的✓★）。
    """
    if path is not None:
        return pathlib.Path(path)
    envp = os.environ.get(EVENT_PATH_ENV)
    if envp:
        return pathlib.Path(envp)
    if os.environ.get("DSH_GATE_STARTED"):
        return None
    try:
        argv0 = os.path.basename(str(sys.argv[0] or ""))
    except Exception:                         # ★不许静默✗★
        argv0 = ""
    if argv0.endswith("_test.py") or argv0.startswith("test_"):
        return None
    return STATE


def record(kind, what="", evidence=None, when=None, where=None, objects=None,
           importance=None, important=False, facts=None, path=None):
    """★接线用的 best-effort 记事件✗★：失败只报 stderr（★动作不能因为记账失败而崩✗★）。

    ★只该记"有后果"的事件✗★（dig／place／container／到达失败／校验红／重要理由）；
    无意义动作按用户口径**不需要**理由（也不记）。
    """
    p = wired_path(path)
    if p is None:
        return None
    try:
        return append(kind, what=what, evidence=evidence, when=when, where=where,
                      objects=objects, importance=importance, important=important,
                      facts=facts, path=p)
    except Exception as exc:                  # ★不许静默✗★ 但也不许把主流程带崩
        print("event_memory.record: 记 %r 失败 %r（path=%s）" % (kind, exc, p),
              file=sys.stderr)
        return None


# ── 读 / 原子写（★坏文件必须抛✗★）──────────────────────────────────────
def _validate_event(e, i) -> None:
    if not isinstance(e, dict):
        raise EventMemoryError("events[%d] 不是 dict ⇒ 文件坏了" % i)
    for key in ("id", "ts", "day", "kind"):
        if key not in e:
            raise EventMemoryError("events[%d] 缺 %r ⇒ 文件坏了" % (i, key))
    if not isinstance(e["id"], str) or not e["id"]:
        raise EventMemoryError("events[%d].id 不是非空字符串" % i)
    if isinstance(e["ts"], bool) or not isinstance(e["ts"], (int, float)):
        raise EventMemoryError("events[%d].ts 不是数字" % i)
    if not isinstance(e["kind"], str) or not e["kind"]:
        raise EventMemoryError("events[%d].kind 不是非空字符串" % i)


def load(path=None) -> dict:
    """★读记忆文件✗★：不存在 ⇒ 新账本；**存在但坏了 ⇒ 抛**（不静默重置）。"""
    p = _path(path)
    if not p.is_file():
        return _fresh()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:                  # ★不许静默✗★
        raise EventMemoryError("读 %s 失败：%r（★坏文件必须抛 ✗ 不许当没有✗★）"
                               % (p, exc)) from exc
    if not isinstance(d, dict):
        raise EventMemoryError("%s 顶层不是 dict（%r）" % (p, type(d).__name__))
    if d.get("schema") != SCHEMA:
        raise EventMemoryError("%s schema=%r（要 %r）⇒ 不是本模块的账本，拒绝猜"
                               % (p, d.get("schema"), SCHEMA))
    if not isinstance(d.get("events"), list):
        raise EventMemoryError("%s 的 events 不是列表 ⇒ 文件坏了" % (p,))
    if not isinstance(d.get("days"), dict):
        raise EventMemoryError("%s 的 days 不是 dict ⇒ 文件坏了" % (p,))
    for i, e in enumerate(d["events"]):
        _validate_event(e, i)
    d.setdefault("seq", len(d["events"]))
    if isinstance(d["seq"], bool) or not isinstance(d["seq"], int):
        raise EventMemoryError("%s 的 seq 不是整数" % (p,))
    return d


def _atomic_save(ledger: dict, path=None) -> pathlib.Path:
    """★原子写✗★：同目录 tmp ＋ `os.replace`（★中途死掉不会留下半个 JSON✗★）"""
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ledger["saved_at"] = round(_now(), 3)
    ledger["retention"] = {"max_events": MAX_EVENTS, "max_per_day": MAX_PER_DAY,
                           "keep_days": KEEP_DAYS}
    data = json.dumps(ledger, ensure_ascii=False, indent=1)
    tmp = p.with_name(p.name + ".tmp")
    try:
        tmp.write_text(data, encoding="utf-8", newline="\n")
        os.replace(str(tmp), str(p))
    finally:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError as exc:                # ★不许静默✗★
            print("event_memory: 清临时文件失败 %r" % (exc,), file=sys.stderr)
    return p


# ── CLI ───────────────────────────────────────────────────────────────────
def _arg(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 >= len(argv):
            raise SystemExit("参数 %s 缺值" % flag)
        return argv[i + 1]
    return default


def main(argv) -> int:
    path = _arg(argv, "--state")
    try:
        if "--append" in argv:
            spec = json.loads(_arg(argv, "--append") or "{}")
            kw = dict(spec)
            kind = kw.pop("kind", None)
            rec = append(kind, path=path, **kw)
            print(json.dumps(rec, ensure_ascii=False))
            return 0
        if "--query" in argv:
            spec = json.loads(_arg(argv, "--query") or "{}")
            rows = query(path=path, **spec)
            print(json.dumps(rows, ensure_ascii=False))
            return 0
        if "--recent" in argv:
            print(json.dumps(recent(int(_arg(argv, "--recent", "10")), path=path),
                             ensure_ascii=False))
            return 0
        if "--since" in argv:
            print(json.dumps(since(float(_arg(argv, "--since", "0")), path=path),
                             ensure_ascii=False))
            return 0
        if "--summarize" in argv:
            day = _arg(argv, "--summarize", "")
            print(json.dumps(summarize(day or None, path=path), ensure_ascii=False))
            return 0
        if "--facts" in argv:
            day = _arg(argv, "--facts", "")
            print(json.dumps(facts(day or None, path=path), ensure_ascii=False))
            return 0
        if "--stats" in argv or not argv:
            print(json.dumps(stats(path), ensure_ascii=False))
            return 0
    except (EventMemoryError, ValueError) as exc:   # ★明确报错 ✗ 不吞✗★
        print("EVENTMEMORY error: %r" % (exc,))
        return 2
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
