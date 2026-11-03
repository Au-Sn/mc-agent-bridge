#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reporter.py -- 模块 L7 汇报官：★把"做过什么"讲成人话 ✗ 只引用证据✗★

规格（§10.3／§14.1／§14.4）：
  * 发言口径：★只报开始/结束 ✗ 中间静默✗★ ⇒ 汇报 = 从**账本/事件/校验/理由**里取事实，
    ★不编数字 ✗ 不编"完成"✗★
  * L7 权限是**无**：只读三处（`jobs_store` 账本、`event_memory` 事件、
    `verifier` 判定／`reasons` 理由），不写世界、不改账本
  * ★空账本/坏账本要如实说"没有记录"✗★（★不许用"完成 0 件"这种假热闹✗★）

输入（都能注入 ✗ 判据用合成账本）：
    report(period=..., level=..., jobs_dir=None, events_path=None,
           verdicts=None, reasons_records=None, max_items=200, now=None)

period：`"today"`（默认）／`"all"`／`int` 最近 N 天／`"job:<job_id>"`／`"events:<n>"`（最近 n 条事件）
level ：`"one"` 一句话（短回执，可落 say 码）／`"para"` 一段／`"full"` 全文（带证据指针）

★★三条纪律（判据会拒）✗★★：
  ① ★没有证据不出现"完成"**：账本标 `done` 但挖不出任何证据指针 ⇒ 记异常
     `done_no_evidence`，汇报里写"未验证"✗★；
  ② ★数字只来自入参✗★：counts 全由 jobs/events/verdicts/reasons 现算，不写死；
  ③ ★异常必报✗★：坏账本、坏事件文件、红判定、无证据完成 都进 `anomalies`。

输出：
    {ok, period, level, counts, items, anomalies, next_steps, text, say_code, evidence_ok}
"""
from __future__ import annotations

import datetime as _dt
import json
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

import jobs_store as JS            # noqa: E402  ★账本口径/默认目录复用✗不另造✗★

SCHEMA = "dshbridge/report@1"
LEVELS = ("one", "para", "full")
MAX_ONE_CHARS = 160


# ── 读三处事实（★坏数据必须进 anomalies ✗ 不许静默少报✗★）────────────────
def _jobs_dir(jobs_dir=None) -> pathlib.Path:
    return pathlib.Path(jobs_dir) if jobs_dir else JS.JOBS


def _parse_ts(s):
    """账本时间串 ⇒ epoch；认不出来 ⇒ None（★不猜✗★）"""
    if s is None:
        return None
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    txt = str(s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        dt = None
        try:
            dt = _dt.datetime.strptime(txt, fmt)
        except ValueError:
            dt = None
        if dt is not None:
            return dt.timestamp()
    return None


def _read_jobs(jobs_dir, anomalies) -> list:
    d = _jobs_dir(jobs_dir)
    if not d.is_dir():
        return []                            # ★目录都没有 ⇒ 没记录 ✗ 不是错误✗★
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:              # ★坏账本如实报 ✗ 不许静默少一件✗★
            anomalies.append({"kind": "bad_job_ledger", "file": p.name,
                              "why": "%s: %s" % (type(exc).__name__, str(exc)[:80])})
            continue
        if not isinstance(job, dict) or not job.get("id"):
            anomalies.append({"kind": "bad_job_ledger", "file": p.name,
                              "why": "不是 dict 或缺 id"})
            continue
        out.append(job)
    out.sort(key=lambda j: str(j.get("created") or ""))
    return out


def _read_events(events_path, anomalies) -> list:
    try:
        import event_memory as EM
    except Exception as exc:                  # ★不许静默✗★
        anomalies.append({"kind": "event_module_unavailable",
                          "why": "%s: %s" % (type(exc).__name__, str(exc)[:80])})
        return []
    try:
        led = EM.load(events_path)
    except EM.EventMemoryError as exc:        # ★坏事件文件如实报 ✗ 不许当没有✗★
        anomalies.append({"kind": "bad_event_ledger", "why": str(exc)[:180]})
        return []
    except Exception as exc:                  # ★不许静默✗★
        anomalies.append({"kind": "bad_event_ledger",
                          "why": "%s: %s" % (type(exc).__name__, str(exc)[:100])})
        return []
    events = led.get("events") or []
    return [e for e in events if isinstance(e, dict)]


def _job_evidence(job: dict) -> list:
    """★账本里的证据指针✗★：`steps[].evidence` ＋ `plan[].evidence` ＋ result 里的 reason="""
    ev = []
    for s in (job.get("steps") or []):
        if isinstance(s, dict) and str(s.get("evidence") or "").strip():
            ev.append(str(s["evidence"]).strip()[:240])
    for it in (job.get("plan") or []):
        if isinstance(it, dict) and str(it.get("evidence") or "").strip():
            ev.append(str(it["evidence"]).strip()[:240])
    if job.get("evidence"):
        ev.append(str(job["evidence"]).strip()[:240])
    return ev


def _code_of(text: str) -> str | None:
    """从证据/结果串里抠 `reason=<有限码>`（★只认 say.py 的码 ✗ 不认自造✗★）"""
    try:
        import say as S
        codes = set(S.CODES)
    except Exception:                         # ★不许静默✗★
        print("reporter: say 模块不可用", file=sys.stderr)
        codes = set()
    for m in re.finditer(r"reason=([a-z_]+)", str(text or "")):
        if m.group(1) in codes:
            return m.group(1)
    return None


# ── period 窗口 ───────────────────────────────────────────────────────────
def _period_window(period, now: float) -> dict:
    if period is None or period == "today":
        lt = time.localtime(now)
        start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        return {"kind": "today", "start": start, "end": None, "label": "今天"}
    if period == "all":
        return {"kind": "all", "start": None, "end": None, "label": "全部"}
    if isinstance(period, bool):
        raise ValueError("period 不许是 bool：%r" % (period,))
    if isinstance(period, int):
        if period < 0:
            raise ValueError("period 天数不许为负：%r" % (period,))
        return {"kind": "days", "days": period, "start": now - period * 86400,
                "end": now, "label": "最近 %d 天" % period}
    if isinstance(period, str):
        s = period.strip()
        if s.startswith("job:") and s[4:].strip():
            return {"kind": "job", "job_id": s[4:].strip(), "start": None,
                    "end": None, "label": "job %s" % s[4:].strip()}
        if s.startswith("events:"):
            try:
                n = int(s[7:])
            except ValueError:
                raise ValueError("events:N 的 N 必须是整数：%r" % (period,)) from None
            if n < 0:
                raise ValueError("events:N 的 N 不许为负：%r" % (period,))
            return {"kind": "events", "n": n, "start": None, "end": None,
                    "label": "最近 %d 条事件" % n}
    raise ValueError("period 只收 today/all/int/job:<id>/events:<n>：%r" % (period,))


def _in_ts_window(ts, win) -> bool:
    if ts is None:
        return win["kind"] in ("today", "all", "days") and win["kind"] != "today"
    if win.get("start") is not None and ts < win["start"]:
        return False
    if win.get("end") is not None and ts > win["end"]:
        return False
    return True


def _event_matches_job(ev, job_id) -> bool:
    evd = ev.get("evidence") or {}
    if not isinstance(evd, dict):
        evd = {}
    if str(evd.get("mission") or "") == job_id:
        return True
    ref = str(evd.get("ref") or "")
    return job_id in ref


# ── 汇报条目 ──────────────────────────────────────────────────────────────
def _job_item(job: dict, anomalies: list) -> dict | None:
    status = str(job.get("status") or "")
    goal = str(job.get("goal") or "")[:120]
    evid = _job_evidence(job)
    jid = str(job.get("id"))
    if status == "done":
        if not evid:
            anomalies.append({"kind": "done_no_evidence", "job": jid,
                              "why": "账本标 done ✗ 但挖不出任何证据指针 ⇒ 不算完成"})
            return {"kind": "done_unverified", "job": jid,
                    "summary": "账本标 done 但无证据（未验证）：%s" % goal,
                    "evidence": []}
        return {"kind": "done", "job": jid, "summary": "做成：%s" % goal,
                "evidence": evid}
    if status == "failed":
        return {"kind": "failed", "job": jid,
                "summary": "失败：%s（%s）" % (goal, str(job.get("result") or "")[:120]),
                "evidence": evid}
    if status == "open":
        return {"kind": "open", "job": jid,
                "summary": "在做：%s（下一步：%s）"
                           % (goal, str(job.get("next") or "")[:80] or "未登记"),
                "evidence": evid}
    if status in ("dropped", "cancelled"):
        return {"kind": "cancelled", "job": jid, "summary": "取消：%s" % goal,
                "evidence": evid}
    return {"kind": "unknown_status", "job": jid,
            "summary": "状态不明（%r）：%s" % (status, goal), "evidence": evid}


def _event_item(ev: dict) -> dict:
    evd = ev.get("evidence") or {}
    ref = ""
    if isinstance(evd, dict):
        ref = str(evd.get("ref") or "")
    elif evd:
        ref = str(evd)
    what = str(ev.get("what") or "").strip()
    k = str(ev.get("kind") or "?")
    return {"kind": "event:" + k, "event_id": ev.get("id"),
            "summary": "%s%s" % (k, ("：" + what[:100]) if what else ""),
            "important": bool(ev.get("important")),
            "evidence": [ref] if ref else []}


def _verdict_item(v: dict, anomalies: list) -> dict:
    ok = bool(v.get("ok"))
    if not ok:
        anomalies.append({"kind": "verdict_fail",
                          "why": str(v.get("why") or "unknown")[:120],
                          "pos": v.get("pos")})
    return {"kind": "verdict", "ok": ok,
            "summary": "校验%s：%s%s" % ("通过" if ok else "红",
                                        str(v.get("action") or "?"),
                                        (" ｜ " + str(v.get("why") or ""))[:80]),
            "evidence": [str(v.get("evidence") or v.get("ref") or
                             "verdict ok=%s why=%s" % (ok, v.get("why")))[:200]]}


def _reason_item(rec: dict) -> dict:
    return {"kind": "reason",
            "summary": "理由：%s（action=%s）"
                       % (str(rec.get("reason") or "")[:100],
                          str(rec.get("action") or "?")),
            "important": bool(rec.get("important")),
            "evidence": [str(rec.get("evidence")
                             or "reasons ts=%s action=%s"
                             % (rec.get("ts"), rec.get("action")))[:200]]}


# ── 渲染（★三个长度等级都用同一批 items/counts ✗ 数字不许新编✗★）────────
def _render(level: str, counts: dict, items: list, anomalies: list,
            next_steps: list, period_label: str) -> str:
    if (counts["jobs"] == 0 and counts["events"] == 0 and counts["verdicts"] == 0
            and counts["reasons"] == 0 and not anomalies):
        return "%s没有记录（job 账本 0 件 ／ 事件 0 条）。" % period_label
    if level == "one":
        txt = ("%s：任务 %d 件（成 %d／败 %d／在做 %d）｜事件 %d 条（重要 %d）｜异常 %d 条"
               % (period_label, counts["jobs"], counts["jobs_done"], counts["jobs_failed"],
                  counts["jobs_open"], counts["events"], counts["events_important"],
                  counts["anomalies"]))
        if anomalies:
            txt += "：%s" % str(anomalies[0].get("kind"))[:24]
        elif counts["jobs_failed"]:
            bad = [it for it in items if it.get("kind") == "failed"]
            if bad:
                txt += "：%s" % bad[0]["summary"][:40]
        return txt[:MAX_ONE_CHARS]
    if level == "para":
        lines = ["%s：任务 %d 件（成 %d／败 %d／在做 %d）｜事件 %d 条（重要 %d）｜异常 %d 条"
                 % (period_label, counts["jobs"], counts["jobs_done"],
                    counts["jobs_failed"], counts["jobs_open"], counts["events"],
                    counts["events_important"], counts["anomalies"])]
        for it in items[:3]:
            lines.append("· " + it["summary"])
        if anomalies:
            lines.append("异常：" + "；".join(str(a.get("kind")) for a in anomalies[:3]))
        if next_steps:
            lines.append("下一步：" + next_steps[0])
        return "\n".join(lines)
    # full
    lines = ["== %s 汇报（full）==" % period_label,
             "任务 %d 件：成 %d ／ 败 %d ／ 在做 %d ／ 取消 %d"
             % (counts["jobs"], counts["jobs_done"], counts["jobs_failed"],
                counts["jobs_open"], counts["jobs_cancelled"]),
             "事件 %d 条（重要 %d）｜校验 %d 条（红 %d）｜理由 %d 条｜异常 %d 条"
             % (counts["events"], counts["events_important"], counts["verdicts"],
                counts["verdict_fail"], counts["reasons"], counts["anomalies"])]
    if not items:
        lines.append("（没有可展开的条目）")
    for it in items:
        lines.append("· " + it["summary"])
        for ev in (it.get("evidence") or [])[:4]:
            lines.append("    证据=" + str(ev)[:200])
    if anomalies:
        lines.append("── 异常 ──")
        for a in anomalies:
            lines.append("· [%s] %s%s" % (a.get("kind"),
                                          ("job=" + a["job"] + " ") if a.get("job") else "",
                                          str(a.get("why") or a.get("file") or "")[:200]))
    if next_steps:
        lines.append("── 下一步建议 ──")
        for s in next_steps[:5]:
            lines.append("· " + s)
    return "\n".join(lines)


# ── 主入口 ────────────────────────────────────────────────────────────────
def report(period="today", level="full", jobs_dir=None, events_path=None,
           verdicts=None, reasons_records=None, max_items=200, now=None) -> dict:
    """★生成汇报✗★（只读三处事实；★空账本如实说没有记录✗★）"""
    if level not in LEVELS:
        raise ValueError("level 只收 %s：%r" % ("/".join(LEVELS), level))
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 0:
        raise ValueError("max_items 必须是 >=0 的整数：%r" % (max_items,))
    if verdicts is not None and not isinstance(verdicts, (list, tuple)):
        raise ValueError("verdicts 只收列表：%r" % (type(verdicts).__name__,))
    if reasons_records is not None and not isinstance(reasons_records, (list, tuple)):
        raise ValueError("reasons_records 只收列表：%r"
                         % (type(reasons_records).__name__,))
    now = time.time() if now is None else float(now)
    win = _period_window(period, now)
    anomalies = []
    jobs = _read_jobs(jobs_dir, anomalies)
    events = _read_events(events_path, anomalies)
    # ★理由（reasons）默认自己读窗口内日志；判据里显式注入以保确定性✗★
    if reasons_records is None:
        try:
            import reasons as R
            days = 1
            if win["kind"] == "days":
                days = max(1, int(win.get("days") or 1))
            elif win["kind"] == "all":
                days = int(R.KEEP_DAYS)
            reasons_records = R.load(days=days)
        except Exception as exc:              # ★不许静默✗★
            anomalies.append({"kind": "reason_log_unreadable",
                              "why": "%s: %s" % (type(exc).__name__, str(exc)[:100])})
            reasons_records = []

    # ── 选窗口内的任务 ──
    sel_jobs = []
    for job in jobs:
        if win["kind"] == "job":
            if str(job.get("id")) == win["job_id"]:
                sel_jobs.append(job)
            continue
        if win["kind"] == "events":
            continue                          # ★只看事件的周期 ⇒ 不混任务✗★
        ts = _parse_ts(job.get("updated")) or _parse_ts(job.get("created"))
        if _in_ts_window(ts, win):
            sel_jobs.append(job)

    # ── 选窗口内的事件 ──
    sel_events = []
    if win["kind"] == "job":
        sel_events = [e for e in events if _event_matches_job(e, win["job_id"])]
    elif win["kind"] == "events":
        sel_events = events[-win["n"]:] if win["n"] else []
    else:
        sel_events = [e for e in events if _in_ts_window(float(e.get("ts") or 0), win)]

    # ── 装配条目 ──
    items = []
    for job in sel_jobs:
        it = _job_item(job, anomalies)
        if it:
            items.append(it)
    for ev in sel_events:
        items.append(_event_item(ev))
    sel_verdicts = [v for v in (verdicts or []) if isinstance(v, dict)]
    for v in sel_verdicts:
        items.append(_verdict_item(v, anomalies))
    sel_reasons = [r for r in (reasons_records or []) if isinstance(r, dict)]
    if win["kind"] == "job":
        sel_reasons = [r for r in sel_reasons
                       if str(r.get("mission") or "") == win["job_id"]]
    elif win["kind"] in ("today", "days") and win.get("start") is not None:
        sel_reasons = [r for r in sel_reasons
                       if (_parse_ts(r.get("ts")) or 0) >= win["start"]]
    for r in sel_reasons:
        items.append(_reason_item(r))

    if len(items) > max_items:
        # ★重要事件/理由不丢✗★：截断时先保重要条目，再按原顺序取其余
        important = [it for it in items if it.get("important")]
        rest = [it for it in items if not it.get("important")]
        keep_n = max_items - min(len(important), max_items)
        kept_ids = {id(x) for x in (important[:max_items] + rest[:keep_n])}
        hidden = len(items) - len(kept_ids)
        items = [it for it in items if id(it) in kept_ids]
        anomalies.append({"kind": "items_truncated",
                          "why": "还有 %d 条未展开（max_items=%d ✗ 重要条目已保住）"
                                 % (hidden, max_items)})
    important_items = [it for it in items if it.get("important")]
    counts = {
        "jobs": len(sel_jobs),
        "jobs_done": sum(1 for j in sel_jobs if j.get("status") == "done"),
        "jobs_failed": sum(1 for j in sel_jobs if j.get("status") == "failed"),
        "jobs_open": sum(1 for j in sel_jobs if j.get("status") == "open"),
        "jobs_cancelled": sum(1 for j in sel_jobs
                              if j.get("status") in ("dropped", "cancelled")),
        "events": len(sel_events),
        "events_important": sum(1 for e in sel_events if e.get("important")),
        "verdicts": len(sel_verdicts),
        "verdict_fail": sum(1 for v in sel_verdicts if not v.get("ok")),
        "reasons": len(sel_reasons),
        "anomalies": len(anomalies),
        "important_items": len(important_items),
    }

    # ── 下一步建议（★只从已有事实推 ✗ 不编任务✗★）──
    next_steps = []
    for job in sel_jobs:
        if job.get("status") == "failed":
            next_steps.append("处理失败：%s（result=%s）"
                              % (job.get("id"), str(job.get("result") or "")[:80]))
        elif job.get("status") == "open":
            next_steps.append("接着做：%s → %s"
                              % (job.get("id"),
                                 str(job.get("next") or "")[:80] or "未登记下一步"))
    if any(a.get("kind") == "done_no_evidence" for a in anomalies):
        next_steps.append("补齐 done 任务的证据指针（或把它降级为未验证）")
    if any(a.get("kind") in ("bad_job_ledger", "bad_event_ledger") for a in anomalies):
        next_steps.append("先修坏账本（见异常里的文件/原因）")
    if not next_steps and counts["events"]:
        next_steps.append("无需收尾：窗口内事件都已入账")

    # ── say 码（★有限集 ✗ 自造码降级 unknown✗★）──
    say_code = "ok"
    if counts["jobs_failed"] or anomalies:
        say_code = "unknown"
        for it in items:
            c = _code_of(it.get("summary")) or _code_of(" ".join(it.get("evidence") or []))
            if c:
                say_code = c
                break
    elif counts["jobs_done"]:
        say_code = "done"
    elif counts["jobs_open"]:
        say_code = "start"

    text = _render(level, counts, items, anomalies, next_steps, win["label"])
    return {"schema": SCHEMA, "ok": True, "period": period, "level": level,
            "window": {k: win.get(k) for k in ("kind", "start", "end", "label")},
            "counts": counts, "items": items, "anomalies": anomalies,
            "next_steps": next_steps, "text": text, "say_code": say_code,
            "evidence_ok": all(it.get("evidence") for it in items
                               if it.get("kind") in ("done", "failed"))}


def to_say(rep: dict, log_say: bool = False) -> dict:
    """★短回执 ↔ say.py 语码兼容✗★：把 say_code 落成 say 的有限机器码回执"""
    try:
        import say as S
    except Exception as exc:                  # ★不许静默✗★
        return {"ok": False, "why": "say_unavailable:%s" % type(exc).__name__}
    code = str(rep.get("say_code") or "unknown")
    if code not in S.CODES:
        code = S.UNKNOWN
    rec = S.say(code, detail=str(rep.get("text") or "")[:80], log=log_say)
    return {"ok": True, "code": rec["code"], "known": rec["known"], "text": rec["text"]}


# ── CLI ───────────────────────────────────────────────────────────────────
def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="L7 汇报官：jobs+事件+校验+理由 ⇒ 人话汇报")
    ap.add_argument("--period", default="today")
    ap.add_argument("--level", default="full")
    ap.add_argument("--jobs-dir", default="")
    ap.add_argument("--events", default="")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    period = ns.period
    if period in ("all", "today"):
        pass
    elif period.startswith("job:") or period.startswith("events:"):
        pass
    else:
        try:
            period = int(period)
        except ValueError:
            print("REPORTER error: --period 只收 today/all/int/job:<id>/events:<n>")
            return 2
    try:
        rep = report(period=period, level=ns.level,
                     jobs_dir=ns.jobs_dir or None,
                     events_path=ns.events or None)
    except ValueError as exc:                 # ★坏参数明确报✗★
        print("REPORTER error: %r" % (exc,))
        return 2
    if ns.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(rep["text"])
        print("SAY %s" % to_say(rep)["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
