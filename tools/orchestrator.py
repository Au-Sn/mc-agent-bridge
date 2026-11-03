#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator.py -- 模块 L 的会话骨架：★判别 → 落 job → 执行 → 只回两条✗★

规格（§10.3 / §14.1 / §19）：
  * ★L1 对话官✗★：`intent.classify` 四类 ⇒ ★chat/query **绝不落 job**✗★
  * ★L2 规划官✗★：`task/mixed` ⇒ **落一条 `jobs/`**（★带验收判据✗★）✗★
  * ★L3 执行官✗★：读 job ⇒ 调 `behaviors.run` ⇒ **独立校验**（★由 behaviors/verifier 做✗★）✗★
  * ★发言口径✗★：★一条任务**只发 2 条消息**（★开始 ＋ 结束✗★）✗ 中间静默✓★
  * ★延迟✗★：★chat **0 次往返**（★不查世界✗★）✗ query 只读**缓存快照**✗★
"""
from __future__ import annotations

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

JOBS = ROOT / "jobs"
MSG_LOG = ROOT / "logs" / "messages.jsonl"


def _jobs_dir(jobs_dir=None) -> pathlib.Path:
    p = pathlib.Path(jobs_dir) if jobs_dir else JOBS
    p.mkdir(parents=True, exist_ok=True)
    return p


def _say(user_text: str, reply: str, kind: str, jobs_dir=None, log=True) -> dict:
    """★一条消息✗★（★所有对用户说的都走这里 ✗ 方便数"一条任务几条消息"✗★）"""
    rec = {"ts": time.time(), "kind": kind, "to_user": reply,
           "from_user": user_text}
    if log:
        try:
            d = pathlib.Path(jobs_dir) if jobs_dir else ROOT / "logs"
            d.mkdir(parents=True, exist_ok=True)
            p = d / "messages.jsonl"
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as exc:          # ★不许静默✗★
            print("orchestrator: 记消息失败 %r" % (exc,), file=sys.stderr)
    return rec


def _make_job(task_text: str, jobs_dir=None) -> dict:
    """★落一条 job ✗ 带验收判据（★不写判据的 job 不许存在✗★）"""
    d = _jobs_dir(jobs_dir)
    jid = "j%d-%s" % (int(time.time()), re.sub(r"[^\w\u4e00-\u9fff]+", "-", task_text)[:24])
    job = {"id": jid, "goal": task_text, "status": "open",
           "created": time.strftime("%Y-%m-%d %H:%M"),
           "next": "执行侧接单", "steps": [], "plan": [], "plan_done": 0,
           "result": "",
           "accept": "★验收：世界真值由 L4 独立核过 ✗ 失败要带 reason★"}
    (d / (jid + ".json")).write_text(json.dumps(job, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    return job


def _cached_snapshot(max_ms: int = 1500):
    try:
        import perceive as P
        return P.read_cache(max_ms=max_ms)
    except Exception as exc:              # ★不许静默✗★
        print("orchestrator: 读缓存失败 %r" % (exc,), file=sys.stderr)
        return None


def _chat_reply(intent: str, text: str, snap) -> str:
    if intent == "query":
        if not snap:
            return "★我还没有最新的世界信息 ⇒ 说不了 ✗（缓存过期）★"
        bot = snap.get("bot") or {}
        pos = bot.get("pos")
        machines = len(snap.get("machines") or [])
        hazards = len(snap.get("hazards") or [])
        return ("我在 %s ｜ 血 %.0f ｜ 背包 %s 件 ｜ 附近机器 %d 台 ✗ 危险 %d 处"
                % (pos, float(bot.get("hp") or 0), bot.get("items"), machines, hazards))
    # chat
    return "在的 ✗ 你说"


def handle(text: str, jobs_dir=None, log=True) -> dict:
    """★L1：一句话 ⇒ `{intent, need_exec, reply, job, messages}`✗★"""
    try:
        import intent as I
    except Exception as exc:              # ★不许静默✗★
        return {"intent": "chat", "need_exec": False,
                "reply": "（判别模块坏了 ✗ 我先不动手）", "job": None,
                "messages": [], "error": str(exc)[:80]}
    r = I.classify(text)
    intent = r["intent"]
    msgs = []

    if intent in ("chat", "query"):
        snap = _cached_snapshot() if intent == "query" else None
        reply = _chat_reply(intent, text, snap)
        msgs.append(_say(text, reply, intent, jobs_dir, log))
        return {"intent": intent, "need_exec": False, "reply": reply,
                "job": None, "messages": msgs, "round_trips": 0 if intent == "chat" else 0}

    # task / mixed
    if intent == "mixed":
        part = r.get("chat_part") or ""
        reply = _chat_reply("chat", part, None) if part else "好"
        msgs.append(_say(text, reply, "chat", jobs_dir, log))

    job = _make_job(r.get("task_part") or text, jobs_dir)
    start_msg = "★开始：%s★" % (job["goal"][:60],)
    msgs.append(_say(text, start_msg, "start", jobs_dir, log))
    return {"intent": intent, "need_exec": True, "reply": start_msg,
            "job": job, "messages": msgs, "round_trips": 0}


def finish(job: dict, ok: bool, why: str = "", jobs_dir=None, log=True) -> dict:
    """★L3 收尾：★**第二条也是最后一条**消息**✗★"""
    d = _jobs_dir(jobs_dir)
    p = d / (job["id"] + ".json")
    if p.is_file():
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:          # ★不许静默✗★
            print("orchestrator: 读 job 失败 %r" % (exc,), file=sys.stderr)
    job["status"] = "done" if ok else "failed"
    job["result"] = ("ok" if ok else ("failed:" + (why or "unknown")))
    job["next"] = ""
    (d / (job["id"] + ".json")).write_text(json.dumps(job, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    end = ("★结束：做到了 ★" if ok else "★结束：没做到 ✗ reason=%s★" % (why or "unknown"))
    msg = _say("", end, "done" if ok else "fail", jobs_dir, log)
    return {"ok": ok, "job": job, "reply": end, "message": msg}


def run_job(job: dict, prims=None, behaviors_run=None) -> dict:
    """★L3：读 job ⇒ 按 goal 找行为 ⇒ 跑 ⇒ 返回结果（★消息由调用方发✗★）"""
    goal = job.get("goal") or ""
    try:
        import behaviors as B
    except Exception as exc:              # ★不许静默✗★
        return {"ok": False, "why": "behaviors_import_failed:" + str(exc)[:50]}
    name = None
    for n in B.REGISTRY:
        if n in goal or n.replace("_", "") in goal:
            name = n
            break
    if name is None:
        # ★关键词兜底（★只做映射 ✗ 不做判别✗★）
        if "挖" in goal:
            name = "mine_ore"
        elif "往返" in goal or "回来" in goal:
            name = "go_out_and_back"
        elif "看" in goal or "侦察" in goal:
            name = "scan_and_report"
        elif "箱子" in goal or "取" in goal:
            name = "take_from_chest"
    if name is None:
        return {"ok": False, "why": "no_behavior_for_goal"}
    fn = behaviors_run or B.run
    return {"behavior": name, "result": fn(name, prims, mission=job.get("id"))}


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 0
    r = handle(" ".join(argv))
    print("INTENT %s ｜ need_exec=%s ｜ round_trips=%s" % (r["intent"], r["need_exec"],
                                                         r.get("round_trips")))
    print("reply:", r["reply"])
    if r["job"]:
        print("job:", r["job"]["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
