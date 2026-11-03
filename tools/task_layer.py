#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task_layer.py -- 模块 A 任务层：★优先级 ＋ 依赖 ＋ claim 租约 ＋ 可中断状态机✗★

规格（docs/方案-拟人化模块.md §2.6 / §14.1）：
  * 用户/交接缺口：「`exec_task` 只能按给定的一串坐标依次走 ✗ **没有优先级 ✗ 没有中断 ✗
    没有依赖**」⇒ 本模块在 `tools/exec_task.py`（执行）与 `tools/jobs_store.py`（账本口径）之上
    补出**任务层**：★不改 `exec_task` 现有对外行为✗★。
  * A 模块要的是三件事：
      ① **看账本**：任务落盘（原子写）⇒ 跨进程/跨重启读得回
      ② **挑下一步**：`priority` 高者先跑；`depends_on` 未满足 ⇒ **不执行**
      ③ **执行 → 记账**：单步推进 `step()`；成功**必须带证据**；失败**如实停**
  * **claim 租约**：同一个任务同一时刻只许一个执行者（★防双执行✗★）；租约过期 ⇒
    可被接管（接管留痕），崩溃留下的 `running` 会被恢复成 `interrupted`。
  * **可中断状态机**：
      pending → claimed → running → done / failed / interrupted / cancelled
      interrupted → pending（`resume`）／failed → pending（`reopen`，显式人工重试）
    ★非法迁移抛 `TaskStateError`✗★（不许"从 pending 直接 done"这种假账）。

与 `exec_task`／`jobs_store` 的关系（★不重造 ✗ 复用✗★）：
  * 计划项格式与 `jobs_store.plan` **同一口径**（`do｜judge`），`next_plan_step`／
    `plan_progress` 直接复用 `jobs_store` 的实现；
  * `to_job()`／`brief()` 把任务映射成 `jobs_store` 的 job 形态（`jobs_store.fmt` 出人话）；
  * 默认执行器 `_default_execute()` 把带 `goals` 的计划项交给
    `exec_task.parse_goals` ＋ `exec_task.run_goals`（每段重读位置／失败如实停是它的既有保证）。

存储：`state/tasks.json`（schema ＋ **原子写** tmp＋os.replace）；**坏账本必须抛
`TaskLedgerError`**（不许静默当空账 —— 那会把"任务丢了"冒充"没有任务"）。
"""
from __future__ import annotations

import json
import os
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

import jobs_store as JS            # noqa: E402  ★复用账本口径（纯函数 ＋ fmt）✗不重造✗★

SCHEMA = "dshbridge/tasks@1"
STATE = ROOT / "state" / "tasks.json"

STATES = ("pending", "claimed", "running", "done", "failed", "interrupted", "cancelled")
ACTIVE = ("claimed", "running")
FINAL = ("done", "failed", "cancelled")
TRANSITIONS = {
    # ★pending → failed 是合法的✗★：依赖死了的 pending 任务**没跑就失败**（如实，不是假装在做）
    "pending": {"claimed", "cancelled", "interrupted", "failed"},
    # ★claimed → claimed 只用于"租约过期后被接管"✗★（迁移历史里写 claim_takeover）
    "claimed": {"claimed", "running", "pending", "interrupted", "cancelled", "failed"},
    "running": {"pending", "done", "failed", "interrupted", "cancelled"},
    "interrupted": {"pending", "cancelled", "failed"},
    "done": set(),
    "failed": {"pending"},
    "cancelled": set(),
}


class TaskLedgerError(RuntimeError):
    """任务账本坏了／形状不对（★必须抛 ✗ 不许静默当空账✗★）。"""


class TaskStateError(ValueError):
    """非法状态迁移（★不许造"没跑就 done"的假账✗★）。"""


# ── 小工具 ────────────────────────────────────────────────────────────────
def _now() -> float:
    return time.time()


def _iso(ts=None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_now() if ts is None else float(ts)))


def _path(path=None) -> pathlib.Path:
    return pathlib.Path(path) if path else STATE


def _fresh() -> dict:
    return {"schema": SCHEMA, "seq": 0, "tasks": {}, "saved_at": None}


def _slug(s: str, n: int = 10) -> str:
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", s or "")
    return s[:n] or "task"


def _new_id(ledger: dict, goal: str) -> str:
    seq = int(ledger.get("seq") or 0) + 1
    ledger["seq"] = seq
    return "t%04d-%s" % (seq, _slug(goal))


def _norm_plan(plan) -> list:
    """计划项：`"做什么｜怎么算做成了"` ／ dict（可带 `goals` 给默认执行器）。"""
    if plan is None:
        return []
    if isinstance(plan, str):
        plan = plan.splitlines()
    if not isinstance(plan, (list, tuple)):
        raise ValueError("plan 只收 str/list：%r" % (plan,))
    out = []
    for i, item in enumerate(plan):
        if isinstance(item, str):
            ln = item.strip()
            if not ln:
                continue
            do, judge = ln, ""
            for sep in ("｜", "|"):
                if sep in ln:
                    do, _, judge = ln.partition(sep)
                    break
            rec = {"i": len(out) + 1, "do": do.strip(), "judge": judge.strip(),
                   "done_at": "", "evidence": ""}
        elif isinstance(item, dict):
            do = str(item.get("do") or "").strip()
            if not do:
                continue
            rec = {"i": len(out) + 1, "do": do, "judge": str(item.get("judge") or "").strip(),
                   "done_at": "", "evidence": ""}
            if item.get("goals") is not None:
                rec["goals"] = item["goals"]
        else:
            raise ValueError("plan[%d] 只收 str/dict：%r" % (i, item))
        out.append(rec)
    return out


def _history(task: dict, frm: str, to: str, why: str = "") -> None:
    task.setdefault("history", []).append({"at": _iso(), "from": frm, "to": to,
                                           "why": str(why or "")[:200]})


def _transition(task: dict, to: str, why: str = "") -> None:
    """★状态机唯一入口✗★：非法迁移 ⇒ 抛（★不写假账✗★）"""
    frm = task.get("state")
    if frm not in STATES:
        raise TaskLedgerError("任务 %r 的状态 %r 不在状态机里" % (task.get("id"), frm))
    if to not in STATES:
        raise TaskStateError("目标状态 %r 不在状态机里（允许 %s）" % (to, ",".join(STATES)))
    if to not in TRANSITIONS[frm]:
        raise TaskStateError("非法迁移：%s → %s（任务 %s）"
                             % (frm, to, task.get("id")))
    task["state"] = to
    task["updated"] = _iso()
    _history(task, frm, to, why)
    if to in FINAL:
        task["claim"] = None


# ── 读 / 写（★坏账本必须抛✗★）─────────────────────────────────────────
def _validate_task(tid, t) -> None:
    if not isinstance(t, dict):
        raise TaskLedgerError("tasks[%r] 不是 dict" % (tid,))
    for key in ("id", "goal", "state", "priority", "depends_on", "plan"):
        if key not in t:
            raise TaskLedgerError("tasks[%r] 缺 %r ⇒ 账本坏了" % (tid, key))
    if t["id"] != tid:
        raise TaskLedgerError("tasks 键 %r 与 id %r 不一致" % (tid, t["id"]))
    if t["state"] not in STATES:
        raise TaskLedgerError("tasks[%r].state=%r 不在状态机里" % (tid, t["state"]))
    if isinstance(t["priority"], bool) or not isinstance(t["priority"], int):
        raise TaskLedgerError("tasks[%r].priority 不是整数" % (tid,))
    if not isinstance(t["depends_on"], list):
        raise TaskLedgerError("tasks[%r].depends_on 不是列表" % (tid,))
    if not isinstance(t["plan"], list):
        raise TaskLedgerError("tasks[%r].plan 不是列表" % (tid,))
    claim = t.get("claim")
    if claim is not None and not isinstance(claim, dict):
        raise TaskLedgerError("tasks[%r].claim 不是 dict" % (tid,))


def load(path=None) -> dict:
    """★读账本✗★：不存在 ⇒ 新账本；**存在但坏了 ⇒ 抛**（不静默当空账）。"""
    p = _path(path)
    if not p.is_file():
        return _fresh()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:                  # ★不许静默✗★
        raise TaskLedgerError("读 %s 失败：%r（★坏账本必须抛✗★）" % (p, exc)) from exc
    if not isinstance(d, dict):
        raise TaskLedgerError("%s 顶层不是 dict" % (p,))
    if d.get("schema") != SCHEMA:
        raise TaskLedgerError("%s schema=%r（要 %r）⇒ 拒绝猜"
                              % (p, d.get("schema"), SCHEMA))
    if not isinstance(d.get("tasks"), dict):
        raise TaskLedgerError("%s 的 tasks 不是 dict ⇒ 账本坏了" % (p,))
    for tid, t in d["tasks"].items():
        _validate_task(tid, t)
    d.setdefault("seq", len(d["tasks"]))
    if isinstance(d["seq"], bool) or not isinstance(d["seq"], int):
        raise TaskLedgerError("%s 的 seq 不是整数" % (p,))
    return d


def save(ledger: dict, path=None) -> pathlib.Path:
    """★原子写✗★（同目录 tmp ＋ `os.replace`）；写失败必须抛（不许"以为记上了"）。"""
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ledger["saved_at"] = round(_now(), 3)
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
            print("task_layer: 清临时文件失败 %r" % (exc,), file=sys.stderr)
    return p


# ── 账本查询 ──────────────────────────────────────────────────────────────
def all_tasks(path=None) -> list:
    return list(load(path)["tasks"].values())


def get(tid: str, path=None) -> dict | None:
    return load(path)["tasks"].get(tid)


def _deps_ready(ledger: dict, task: dict) -> tuple:
    """`(能否跑, 还没好但正常的依赖, 已经死掉的依赖)`"""
    unmet, dead = [], []
    for dep in task.get("depends_on") or []:
        d = ledger["tasks"].get(dep)
        if d is None:
            dead.append(dep)                    # ★依赖悬空 ⇒ 不许猜它好了✗★
        elif d.get("state") == "done":
            continue
        elif d.get("state") in ("failed", "cancelled"):
            dead.append(dep)
        else:
            unmet.append(dep)
    return (not unmet and not dead), unmet, dead


def blocked(path=None) -> list:
    """★还没跑但被挡住的✗★：`[{id, depends_on, unmet, dead}]`（依赖未满足／依赖死了）"""
    ledger = load(path)
    out = []
    for t in ledger["tasks"].values():
        if t.get("state") != "pending":
            continue
        ready, unmet, dead = _deps_ready(ledger, t)
        if not ready:
            out.append({"id": t["id"], "depends_on": list(t.get("depends_on") or []),
                        "unmet": unmet, "dead": dead})
    return out


def _runnable_in(ledger: dict, now=None) -> list:
    now = _now() if now is None else float(now)
    out = []
    for t in ledger["tasks"].values():
        if t.get("state") != "pending":
            continue
        ready, _u, _d = _deps_ready(ledger, t)
        if not ready:
            continue
        claim = t.get("claim")
        if claim and float(claim.get("expires_at") or 0) > now:
            continue                            # ★别人租着 ✗ 不抢✗★
        out.append(t)
    out.sort(key=lambda t: (-int(t.get("priority") or 0), str(t.get("created") or ""),
                            str(t.get("id"))))
    return out


def runnable(path=None) -> list:
    """★现在能跑的（按优先级降序／先来后到）✗★"""
    return list(_runnable_in(load(path)))


# ── 状态机操作 ────────────────────────────────────────────────────────────
def add(goal: str, priority: int = 5, depends_on=None, plan=None,
        path=None) -> dict:
    """★登记一件任务✗★（`depends_on` 必须指向账本里已有的任务 ✗ 悬空依赖不猜✗★）"""
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("goal 不能为空")
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ValueError("priority 必须是整数：%r" % (priority,))
    deps = [] if depends_on is None else list(depends_on)
    if not all(isinstance(d, str) and d for d in deps):
        raise ValueError("depends_on 必须是任务 id 列表：%r" % (depends_on,))
    ledger = load(path)
    unknown = [d for d in deps if d not in ledger["tasks"]]
    if unknown:
        raise ValueError("依赖不存在：%s（★不许登记悬空依赖✗★）" % (unknown,))
    plan_items = _norm_plan(plan)
    if not plan_items:
        plan_items = _norm_plan([goal])         # ★没给计划 ⇒ 一步就是目标本身✗★
    task = {"id": _new_id(ledger, goal), "goal": goal, "state": "pending",
            "priority": priority, "depends_on": deps, "plan": plan_items,
            "plan_done": 0, "steps": [], "history": [],
            "next": plan_items[0]["do"], "result": "", "evidence": "",
            "created": _iso(), "updated": _iso(), "claim": None,
            "interrupted_reason": ""}
    ledger["tasks"][task["id"]] = task
    save(ledger, path)
    return task


def _claim_in(ledger: dict, tid: str, owner: str, lease_s: float, now=None) -> dict:
    now = _now() if now is None else float(now)
    task = ledger["tasks"].get(tid)
    if task is None:
        return {"ok": False, "why": "unknown_task", "task": None}
    claim = task.get("claim")
    takeover = False
    if claim and float(claim.get("expires_at") or 0) > now:
        return {"ok": False, "why": "lease_held",
                "holder": claim.get("owner"), "expires_in": round(
                    float(claim.get("expires_at") or 0) - now, 3), "task": task}
    if claim:
        takeover = True
    ready, unmet, dead = _deps_ready(ledger, task)
    if not ready:
        return {"ok": False, "why": "deps_not_ready", "unmet": unmet, "dead": dead,
                "task": task}
    if task.get("state") not in ("pending", "claimed", "interrupted"):
        return {"ok": False, "why": "not_claimable:%s" % task.get("state"), "task": task}
    frm = task["state"]
    if frm == "interrupted":
        _transition(task, "pending", "claim_after_interrupt")
        frm = "pending"
    _transition(task, "claimed", "claim_takeover" if takeover else "claim")
    task["claim"] = {"owner": str(owner), "claim_id": "c-%s-%d" % (tid, int(now * 1000)),
                     "claimed_at": round(now, 3),
                     "expires_at": round(now + max(0.0, float(lease_s)), 3),
                     "lease_s": float(lease_s)}
    task["next"] = (JS.next_plan_step(task) or {}).get("do", task.get("next") or "")
    return {"ok": True, "why": "claimed", "task": task, "claim": task["claim"],
            "takeover": takeover}


def claim(tid: str, owner: str = "Bot", lease_s: float = 60.0, path=None) -> dict:
    """★认领（租约）✗★：同任务同刻只许一个执行者；过期可接管（留痕）。"""
    ledger = load(path)
    r = _claim_in(ledger, tid, owner, lease_s)
    if r.get("ok"):
        save(ledger, path)
    return {k: v for k, v in r.items() if k != "task"} | {"task": r.get("task")}


def start(tid: str, claim_id: str = "", path=None) -> dict:
    """claimed → running（★claim_id 对不上 ⇒ 拒✗★）"""
    ledger = load(path)
    task = ledger["tasks"].get(tid)
    if task is None:
        raise TaskLedgerError("unknown task: %r" % (tid,))
    if task.get("state") != "claimed":
        raise TaskStateError("只有 claimed 能 start（现在是 %r）" % task.get("state"))
    claim = task.get("claim") or {}
    if claim_id and claim.get("claim_id") != claim_id:
        raise TaskStateError("claim_id 对不上：%r ≠ %r" % (claim_id, claim.get("claim_id")))
    _transition(task, "running", "start")
    save(ledger, path)
    return task


def release(tid: str, claim_id: str = "", why: str = "release", path=None) -> dict:
    ledger = load(path)
    task = ledger["tasks"].get(tid)
    if task is None:
        raise TaskLedgerError("unknown task: %r" % (tid,))
    claim = task.get("claim") or {}
    if claim_id and claim.get("claim_id") != claim_id:
        raise TaskStateError("claim_id 对不上")
    _transition(task, "pending", why)
    task["claim"] = None
    save(ledger, path)
    return task


def interrupt(tid: str, why: str = "interrupted", path=None) -> dict:
    """★可中断✗★：pending/claimed/running → interrupted（清租约，进度保留）"""
    ledger = load(path)
    task = ledger["tasks"].get(tid)
    if task is None:
        raise TaskLedgerError("unknown task: %r" % (tid,))
    _transition(task, "interrupted", why)
    task["claim"] = None
    task["interrupted_reason"] = str(why or "")[:200]
    save(ledger, path)
    return task


def resume(tid: str, path=None) -> dict:
    """interrupted → pending（★进度与计划项都不丢✗★）"""
    ledger = load(path)
    task = ledger["tasks"].get(tid)
    if task is None:
        raise TaskLedgerError("unknown task: %r" % (tid,))
    if task.get("state") != "interrupted":
        raise TaskStateError("只有 interrupted 能 resume（现在是 %r）" % task.get("state"))
    _transition(task, "pending", "resume")
    task["interrupted_reason"] = ""
    save(ledger, path)
    return task


def cancel(tid: str, why: str = "cancelled", path=None) -> dict:
    ledger = load(path)
    task = ledger["tasks"].get(tid)
    if task is None:
        raise TaskLedgerError("unknown task: %r" % (tid,))
    _transition(task, "cancelled", why)
    task["claim"] = None
    task["result"] = "cancelled:" + str(why or "")[:120]
    save(ledger, path)
    return task


def reopen(tid: str, why: str = "manual_retry", path=None) -> dict:
    """failed → pending（★只有显式人工重试才许 ✗ 不许自动重试掩盖失败✗★）"""
    ledger = load(path)
    task = ledger["tasks"].get(tid)
    if task is None:
        raise TaskLedgerError("unknown task: %r" % (tid,))
    _transition(task, "pending", why)
    task["claim"] = None
    task["result"] = ""
    save(ledger, path)
    return task


def finish(tid: str, ok: bool, result: str = "", evidence: str = "", path=None) -> dict:
    """claimed/running → done/failed（★done 必须带证据 ✗ 没证据不算完成✗★）"""
    ledger = load(path)
    task = ledger["tasks"].get(tid)
    if task is None:
        raise TaskLedgerError("unknown task: %r" % (tid,))
    ev = str(evidence or "").strip()
    if ok and not ev:
        raise ValueError("refusing to mark done without evidence（★没证据不算完成✗★）")
    _transition(task, "done" if ok else "failed",
                "finish:" + (str(result or "")[:80]))
    task["claim"] = None
    task["result"] = ("ok" if ok else ("failed:" + (str(result or "") or "unknown")))
    task["evidence"] = ev
    save(ledger, path)
    return task


# ── 进程恢复 / 依赖阻断 ───────────────────────────────────────────────────
def recover_expired(ledger: dict, now=None) -> list:
    """★崩溃恢复✗★：租约过期的 claimed/running ⇒ interrupted（**不重新执行**，留给人决定）。"""
    now = _now() if now is None else float(now)
    out = []
    for task in ledger["tasks"].values():
        state = task.get("state")
        if state not in ACTIVE:
            continue
        claim = task.get("claim") or {}
        exp = float(claim.get("expires_at") or 0)
        if claim and exp > now:
            continue
        _transition(task, "interrupted", "lease_expired")
        task["claim"] = None
        task["interrupted_reason"] = "lease_expired"
        out.append(task["id"])
    return out


def mark_dep_blocked(ledger: dict) -> list:
    """★依赖死了 ⇒ 依赖它的任务**如实失败**✗★（不执行、不假装还在等）"""
    out = []
    for task in ledger["tasks"].values():
        if task.get("state") != "pending":
            continue
        _ready, unmet, dead = _deps_ready(ledger, task)
        if dead and not unmet:
            _transition(task, "failed", "dep_failed:" + ",".join(dead))
            task["claim"] = None
            task["result"] = "dep_failed:" + ",".join(dead)
            task["evidence"] = "dep:" + ",".join(dead)
            out.append(task["id"])
    return out


# ── 执行（★包装 exec_task ✗ 不改它对外行为✗★）─────────────────────────────
def _default_execute(task: dict, step: dict) -> dict:
    """默认执行器：计划项带 `goals` ⇒ 交给 `exec_task.parse_goals/run_goals`。

    ★没有可执行内容就如实失败 ✗ 不许"看起来做完了"✗★。
    """
    spec = step.get("goals")
    if spec is None:
        return {"ok": False, "why": "no_executable_step",
                "evidence": ""}
    try:
        import exec_task as ET
        if isinstance(spec, str):
            goals = ET.parse_goals(spec)
        else:
            goals = [tuple(g) if isinstance(g, (list, tuple)) else g for g in spec]
        if not goals:
            return {"ok": False, "why": "empty_goals", "evidence": ""}
        ok, rep = ET.run_goals(goals, dry=False)
        return {"ok": bool(ok),
                "evidence": "SUMMARY task pass=%s fail=%s total=%s"
                            % (rep.get("pass"), rep.get("fail"), rep.get("total")),
                "report": rep}
    except Exception as exc:                  # ★不许静默✗★
        return {"ok": False, "why": "exec_unavailable:%s:%s"
                                    % (type(exc).__name__, str(exc)[:80]), "evidence": ""}


def _next_step(task: dict) -> dict | None:
    return JS.next_plan_step(task)            # ★复用账本口径✗★


def _mark_step(task: dict, i: int, evidence: str) -> None:
    ev = str(evidence or "").strip()
    if not ev:
        raise ValueError("refusing to mark step done without evidence")
    for it in task.get("plan") or []:
        if int(it.get("i") or 0) == int(i):
            it["done_at"] = _iso()
            it["evidence"] = ev[:400]
            break
    else:
        raise ValueError("plan step %r 不存在" % (i,))
    done, total = JS.plan_progress(task)      # ★复用账本口径✗★
    task["plan_done"] = done
    nxt = _next_step(task)
    task["next"] = nxt["do"] if nxt else "（计划上的步骤都做完了 ⇒ 该收尾）"


def step(execute_fn=None, owner: str = "Bot", lease_s: float = 60.0,
         path=None, dry: bool = False) -> dict:
    """★单步推进✗★：看账本 → 恢复/依赖检查 → 挑下一步（优先级）→ 认领 → 执行 → 记账。

    返回：`{ok, why, task_id, step, state, recovered, blocked, ...}`。
    ★失败如实停✗★：执行器失败 ⇒ 任务 failed（不自动重试第二遍来"碰运气"）。
    ★证据强制✗★：执行器说 ok 但没给 evidence ⇒ 记 failed/no_evidence（不许假完成）。
    """
    ledger = load(path)
    recovered = recover_expired(ledger)
    dep_failed = mark_dep_blocked(ledger)
    if recovered or dep_failed:
        save(ledger, path)
    cands = _runnable_in(ledger)
    waiting = blocked(path=path) if not cands else None
    if not cands:
        return {"ok": False, "why": "no_runnable", "task_id": None, "step": None,
                "state": None, "recovered": recovered, "dep_failed": dep_failed,
                "waiting": waiting,
                "runnable": 0,
                "states": {s: sum(1 for t in ledger["tasks"].values() if t.get("state") == s)
                           for s in STATES}}
    task = cands[0]
    tid = task["id"]
    cl = _claim_in(ledger, tid, owner, lease_s)
    if not cl.get("ok"):
        save(ledger, path)
        return {"ok": False, "why": "claim_failed:" + str(cl.get("why")), "task_id": tid,
                "step": None, "state": task.get("state"), "recovered": recovered,
                "dep_failed": dep_failed}
    task = cl["task"]
    _transition(task, "running", "step_start")
    step_info = _next_step(task)
    if step_info is None:
        # 计划已全部完成 ⇒ 收尾（这条路径不会把没证据的当完成：证据来自已有计划项）
        ev = "plan_complete:" + ",".join(it.get("evidence", "") for it in task["plan"])[:300]
        _transition(task, "done", "plan_complete")
        task["claim"] = None
        task["result"] = "ok"
        task["evidence"] = ev
        save(ledger, path)
        return {"ok": True, "why": "done", "task_id": tid, "step": None,
                "state": task["state"], "recovered": recovered, "dep_failed": dep_failed}
    plan_step = {"i": int(step_info.get("i") or 0), "do": step_info.get("do"),
                 "judge": step_info.get("judge"), "goals": step_info.get("goals")}
    save(ledger, path)                        # ★这里是崩溃窗口：死在这儿 ⇒ running+租约✗★
    if dry:
        # ★dry：只看打算做什么 ✗ 不执行 ✗ 不记账 ✗ 状态回到 pending✗★
        _transition(task, "pending", "dry_release")
        task["claim"] = None
        save(ledger, path)
        return {"ok": True, "why": "dry", "task_id": tid, "step": plan_step,
                "state": task["state"], "recovered": recovered,
                "dep_failed": dep_failed, "executed": False}
    fn = execute_fn or _default_execute
    try:
        res = fn(task, plan_step)
    except Exception as exc:                  # ★不许静默✗★
        res = {"ok": False, "why": "executor_exception:%s:%s"
                                   % (type(exc).__name__, str(exc)[:80]),
               "evidence": ""}
    if not isinstance(res, dict):
        res = {"ok": False, "why": "executor_bad_return:%s" % type(res).__name__,
               "evidence": ""}
    evidence = str(res.get("evidence") or "").strip()
    if res.get("ok") and not evidence:
        res = {"ok": False, "why": "no_evidence",
               "evidence": "", "detail": str(res)[:200]}
    if res.get("ok"):
        _mark_step(task, plan_step["i"], evidence)
        task.setdefault("steps", []).append(
            {"at": _iso(), "note": "step %d ok" % plan_step["i"], "evidence": evidence[:300]})
        nxt = _next_step(task)
        if nxt is None:
            _transition(task, "done", "plan_complete")
            task["claim"] = None
            task["result"] = "ok"
            task["evidence"] = evidence[:400]
            save(ledger, path)
            return {"ok": True, "why": "done", "task_id": tid, "step": plan_step,
                    "state": task["state"], "evidence": evidence,
                    "recovered": recovered, "dep_failed": dep_failed,
                    "plan_done": task["plan_done"]}
        _transition(task, "pending", "step_done")
        task["claim"] = None
        save(ledger, path)
        return {"ok": True, "why": "step_ok", "task_id": tid, "step": plan_step,
                "state": task["state"], "evidence": evidence, "next": task["next"],
                "recovered": recovered, "dep_failed": dep_failed,
                "plan_done": task["plan_done"]}
    why = str(res.get("why") or "unknown")[:200]
    _transition(task, "failed", "execute_failed:" + why)
    task["claim"] = None
    task["result"] = "failed:" + why
    task["evidence"] = evidence
    task.setdefault("steps", []).append(
        {"at": _iso(), "note": "step %d failed: %s" % (plan_step["i"], why),
         "evidence": evidence[:300]})
    save(ledger, path)
    return {"ok": False, "why": why, "task_id": tid, "step": plan_step,
            "state": task["state"], "evidence": evidence,
            "recovered": recovered, "dep_failed": dep_failed}


# ── 与 jobs_store 的对账（★同一账本口径 ✗ 不另造✗★）──────────────────────
_STATUS_MAP = {"pending": "open", "claimed": "open", "running": "open",
               "interrupted": "open", "done": "done", "failed": "failed",
               "cancelled": "dropped"}


def to_job(task: dict) -> dict:
    """★任务 ⇒ jobs_store 的 job 形态✗★（字段名对齐 ⇒ `jobs_store.fmt` 能直接读）"""
    return {"id": task.get("id"), "goal": task.get("goal"),
            "status": _STATUS_MAP.get(task.get("state"), "open"),
            "created": task.get("created"), "updated": task.get("updated"),
            "next": task.get("next") or "", "steps": list(task.get("steps") or []),
            "result": ("" if task.get("state") not in ("done", "failed", "cancelled")
                       else (task.get("result") or task.get("state"))),
            "plan": list(task.get("plan") or []),
            "plan_done": int(task.get("plan_done") or 0),
            "priority": task.get("priority"),
            "depends_on": list(task.get("depends_on") or []),
            "state": task.get("state")}


def brief(path=None, limit: int = 3) -> str:
    """★人话任务书✗★：未完成任务的优先级／下一步（借 `jobs_store.fmt` 的既有口径）"""
    ledger = load(path)
    rows = [t for t in ledger["tasks"].values()
            if t.get("state") not in ("done", "cancelled")]
    rows.sort(key=lambda t: (-int(t.get("priority") or 0), str(t.get("created") or "")))
    if not rows:
        return ""
    lines = ["──────── ★A 任务层账本（跨重启 ✓）★ ────────"]
    for t in rows[:limit]:
        lines.append(JS.fmt(to_job(t), steps=2))
    if len(rows) > limit:
        lines.append("（还有 %d 件排后面 ✓）" % (len(rows) - limit))
    blocked_now = blocked(path=path)
    if blocked_now:
        lines.append("★被依赖挡住的★：" + " ｜ ".join(
            "%s(等 %s)" % (b["id"], ",".join(b["unmet"] or b["dead"]))
            for b in blocked_now[:3]))
    return "\n".join(lines) + "\n"


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
        if "--add" in argv:
            goal = _arg(argv, "--add") or ""
            pri = int(_arg(argv, "--priority", "5") or 5)
            dep = _arg(argv, "--dep", "")
            deps = [x for x in re.split(r"[,，]", dep or "") if x.strip()]
            plan = _arg(argv, "--plan", "")
            task = add(goal, priority=pri, depends_on=deps,
                       plan=plan.splitlines() if plan else None, path=path)
            print(json.dumps(task, ensure_ascii=False))
            return 0
        if "--list" in argv:
            print(json.dumps(all_tasks(path), ensure_ascii=False))
            return 0
        if "--runnable" in argv:
            print(json.dumps(runnable(path), ensure_ascii=False))
            return 0
        if "--blocked" in argv:
            print(json.dumps(blocked(path), ensure_ascii=False))
            return 0
        if "--brief" in argv:
            print(brief(path), end="")
            return 0
        if "--show" in argv:
            print(json.dumps(get(_arg(argv, "--show"), path), ensure_ascii=False))
            return 0
        if "--resume" in argv:
            print(json.dumps(resume(_arg(argv, "--resume"), path), ensure_ascii=False))
            return 0
        if "--cancel" in argv:
            print(json.dumps(cancel(_arg(argv, "--cancel"),
                                    _arg(argv, "--why", "manual_cancel") or "",
                                    path), ensure_ascii=False))
            return 0
        if "--stats" in argv or not argv:
            led = load(path)
            print(json.dumps({"path": str(_path(path)), "seq": led.get("seq"),
                              "states": {s: sum(1 for t in led["tasks"].values()
                                                if t.get("state") == s) for s in STATES},
                              "runnable": len(runnable(path)),
                              "blocked": len(blocked(path))},
                             ensure_ascii=False))
            return 0
    except (TaskLedgerError, TaskStateError, ValueError) as exc:   # ★明确报错✗★
        print("TASKLAYER error: %r" % (exc,))
        return 2
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
