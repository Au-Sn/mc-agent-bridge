#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jobs_store.py —— ★长任务的"账本"★ ✓（一份实现 ✓ 两边共用 ✓ 不抄第二份 ✗）

为什么必须有它 ✗（用户原话 ✓：「目前看来似乎要进行长任务还有点吃力」✓）：
  现在的形态 ✗：`一轮聊天 = 一轮任务` ✓
    · 大脑一轮结束（`stop=end_turn`）⇒ 它**就停了** ✗ 没人接着推 ✗
    · 会话本身可能被重启/换剖面/进程死掉 ✗ ⇒ **它做的事全丢** ✗
    · 用户只能靠聊天记录回忆"干到哪了" ✗
  ⇒ 长任务要的是三件东西 ✓：
    ① **任务本身有账** ✓（goal / 下一步 / 做过什么 / 证据 ✓ 落盘 ✓ 跨重启 ✓）
    ② **大脑随时能读到这本账** ✓（每轮注入任务书 ✓ 见 `brief()` ✓）
    ③ **有人在没人催的时候推它一步** ✓（中继的自动续跑 ✓ 见 acp_talk.py ✓）

★纪律（本项目老账 ✓）★：
  · 只记**事实** ✗：每步必须能挂"证据"（工具回执 / 世界真值 / 文件 ✓）
  · 状态只有四种 ✓：`open`（没做完 ✓）/ `done` / `failed` / `dropped` ✓ —— 不许含糊 ✗
  · 一个任务一条文件 ✓ `jobs/<id>.json` ✓ 人对可读可编辑 ✓

用法（给别的脚本 ✓）：`from jobs_store import open_job, open_jobs, step, close, brief`
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "jobs"
STATUSES = ("open", "done", "failed", "dropped")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _now_plus(sec: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + sec))


def waiting_s(job: dict) -> float:
    """这件活还要等多少秒才能再动 ✓（0 = 现在就可以动 ✓）"""
    try:
        return max(0.0, float(job.get("not_before_epoch") or 0) - time.time())
    except Exception:
        return 0.0


def runnable_jobs() -> list[dict]:
    """★现在**可以**推进的活★ ✓（中继的自动续跑只认这个 ✓ 见 acp_talk.py ✓）"""
    return [j for j in open_jobs() if waiting_s(j) <= 0]


def _slug(s: str, n: int = 12) -> str:
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", s or "")
    return s[:n] or "job"


def new_id(goal: str) -> str:
    return "j%s-%s%02d" % (time.strftime("%m%d-%H%M%S"), _slug(goal, 8), random.randint(0, 99))


def path_of(job_id: str) -> Path:
    return JOBS / ("%s.json" % job_id)


def save(job: dict) -> dict:
    JOBS.mkdir(parents=True, exist_ok=True)
    job["updated"] = _now()
    p = path_of(job["id"])
    p.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return job


def load(job_id: str) -> dict | None:
    p = path_of(job_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        # 记录：账本读坏 ⇒ 调用方会把"这件活"当成空账（静默少条数据）
        print("[记录] 账本读不到 %s（%s）-> 这件活会被当成没有"
              % (p.name, type(e).__name__), file=sys.stderr)
        return None


def all_jobs() -> list[dict]:
    if not JOBS.is_dir():
        return []
    out = []
    for p in sorted(JOBS.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            # 记录：跳过一本坏账 ⇒ 未完成清单里会静默少一件（不许）
            print("[记录] 账本读不到 %s（%s）-> 清单里少一件"
                  % (p.name, type(e).__name__), file=sys.stderr)
            continue
    out.sort(key=lambda j: j.get("created", ""))
    return out


def open_jobs() -> list[dict]:
    return [j for j in all_jobs() if j.get("status") == "open"]


def plan(job_id: str, spec: str) -> dict | None:
    """★给一件活写一份**步骤清单**★ ✗（2026-09-29 第 22 轮 ✓ 优先级③"批量作业编排"✓）

    为什么必须有它 ✗：账本原来只有一句自由文本的 `next` ✗
      ⇒ **多步的活**（"把一箱沙砾筛完 ⇒ 装桶 ⇒ 送回去"✓）**没法登记**✗
      ⇒ 跨会话/跨重启以后 ✓ 我**不知道自己做到第几步了** ✗（只能重读聊天记录猜 ✗）
    写法 ✓（人/大脑都好写 ✓）：**一行一步** ✓ 行内用 `｜`（或 `|` ✓）分开
      「做什么 ｜ 怎么算做成了 ✓」——
      ```
      去箱子取 8 个沙砾｜背包里 gravel >= 8（世界真值 ✓）
      筛 8 下｜筛子产出增加 或 背包 items 增加
      把产出存回箱子｜容器读数对得上
      ```
    ★每步的"判据"是可选项 ✗ 但**强烈建议写** ✓：不写就会变成"我说我做完了"✗（P-family ✓）
    """
    job = load(job_id)
    if job is None:
        return None
    items = []
    for ln in (spec or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        for sep in ("｜", "|"):
            if sep in ln:
                do, _, judge = ln.partition(sep)
                break
        else:
            do, judge = ln, ""
        do = do.strip()
        if not do:
            continue
        items.append({"i": len(items) + 1, "do": do, "judge": judge.strip(),
                      "done_at": "", "evidence": ""})
    if not items:
        raise ValueError("plan is empty (one step per line, `do | judge`)")
    job["plan"] = items
    job["plan_done"] = 0
    if not (job.get("next") or "").strip():
        job["next"] = items[0]["do"]
    return save(job)


def next_plan_step(job: dict) -> dict | None:
    """★下一个**还没做成**的步骤★ ✓（顺序固定 ✓ 不重复催同一件 ✗）"""
    for it in (job.get("plan") or []):
        if not it.get("done_at"):
            return it
    return None


def plan_progress(job: dict) -> tuple:
    """`(done, total)` ✓"""
    its = job.get("plan") or []
    done = len([it for it in its if it.get("done_at")])
    return done, len(its)


def mark_plan_step(job_id: str, i: int, evidence: str) -> dict | None:
    """★把第 `i` 步标成做成了★ ✗ —— **必须带证据** ✓（没证据 ⇒ 不算完成 ✗）

    为什么强制证据 ✗：这条正是本项目的核心纪律 ✓ —— "**我说我做完了**"不算 ✗
      （P105 的"悄悄搬错东西"✓ P106 的"口径各说各话"✓ 都是这个病 ✓）
    """
    job = load(job_id)
    if job is None:
        return None
    its = job.get("plan") or []
    i = int(i or 0)
    if not (1 <= i <= len(its)):
        raise ValueError("plan step %d out of range 1..%d" % (i, len(its)))
    if not (evidence or "").strip():
        raise ValueError("refusing to mark step %d done without evidence" % i)
    its[i - 1]["done_at"] = _now()
    its[i - 1]["evidence"] = (evidence or "").strip()
    job["plan_done"] = plan_progress(job)[0]
    nxt = next_plan_step(job)
    job["next"] = nxt["do"] if nxt else "（计划上的步骤都做完了 ⇒ 该收尾 ✓）"
    return save(job)


def open_job(goal: str, next_step: str = "", owner: str = "Bot") -> dict:
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("goal is empty")
    job = {"id": new_id(goal), "goal": goal, "status": "open", "owner": owner,
           "created": _now(), "updated": _now(), "next": (next_step or "").strip(),
           "steps": [], "result": ""}
    return save(job)


def step(job_id: str, note: str, next_step: str = "", evidence: str = "",
         wait_s: float = 0) -> dict | None:
    """记一步 ✓ `wait_s>0` ⇒ 这件活**先等一会儿再做** ✓（见下面"为什么要等"✗）

    ⚠ 为什么必须能"等" ✗（实测 2026-09-23 ✓）：巡田那件活登记了"等麦子熟" ✓
      而中继每 90 秒就推一次 ✗ ⇒ 它每轮都跑去田里看一遍 ✗（麦子要几分钟才熟 ✓）
      ⇒ 白跑 ✓ 白烧 token ✓ 而且聊天里反复念同一句 ✗
      ⇒ 所以：**这一件活自己声明"我什么时候才需要再看"** ✓ 由中继照着等 ✓
    """
    job = load(job_id)
    if job is None:
        return None
    job.setdefault("steps", []).append({"at": _now(), "note": (note or "").strip(),
                                        "evidence": (evidence or "").strip()})
    if next_step is not None:
        job["next"] = (next_step or "").strip()
    if wait_s and float(wait_s) > 0:
        job["not_before"] = _now_plus(float(wait_s))
        job["not_before_epoch"] = time.time() + float(wait_s)
    elif "not_before" in job:
        job.pop("not_before", None)
        job.pop("not_before_epoch", None)
    return save(job)


def close(job_id: str, result: str, status: str = "done") -> dict | None:
    job = load(job_id)
    if job is None:
        return None
    if status not in STATUSES:
        status = "done"
    job["status"] = status
    job["result"] = (result or "").strip()
    job["next"] = ""
    return save(job)


def fmt(job: dict, steps: int = 3) -> str:
    """一行/几行的**人话** ✓（给模型看也给人看 ✓ 只用 ASCII 标点 ✓ 免得过通道时坏 ✗）"""
    st = job.get("steps") or []
    head = "%s [%s] %s" % (job["id"], job.get("status", "?"), job.get("goal", ""))
    w = waiting_s(job)
    if w > 0:
        head += " （正在等：还要 %.0f 秒 ✓）" % w
    tail = []
    if job.get("next"):
        tail.append("下一步: %s" % job["next"])
    for s in st[-steps:]:
        ev = (" (证据: %s)" % s["evidence"]) if s.get("evidence") else ""
        tail.append("  已做 %s: %s%s" % (s.get("at", "?")[11:], s.get("note", ""), ev))
    if job.get("result"):
        tail.append("结果: %s" % job["result"])
    n = len(st)
    if n > steps:
        tail.insert(0, "  (更早的 %d 步已省略)" % (n - steps))
    return "\n".join([head] + tail)


def brief(max_jobs: int = 2, max_steps: int = 3) -> str:
    """★给任务书用的一段★ ✓（每轮注入 ✓ ⇒ 换会话/重启也能接着干 ✓）

    没有未完成的任务 ⇒ 返回空串 ✓（**不要**硬塞一句"你没有任务"✗ —— 那是噪音 ✓）
    """
    js = open_jobs()
    if not js:
        return ""
    parts = ["──────── ★你手上**还没做完**的活（账本 ✓ 跨重启 ✓）★ ────────"]
    for j in js[:max_jobs]:
        parts.append(fmt(j, max_steps))
    if len(js) > max_jobs:
        parts.append("（还有 %d 件排后面 ✓）" % (len(js) - max_jobs))
    parts.append("⇒ 这些是**你自己之前登记**的 ✓ 接着做 ✓ 每做完一步用 `job_step` 记一笔 ✓"
                 "整件做完用 `job_close` 收尾 ✓ ★不许假装它不存在★ ✗")
    parts.append("⇒ 若下一步**要等**（等麦子熟 ✓ 等机器出料 ✓）⇒ 在 `job_step` 里带 `wait_s=秒数` ✓"
                 "中继会照着等 ✓ 你就不会被反复叫起来白跑一趟 ✓")
    return "\n".join(parts) + "\n"

