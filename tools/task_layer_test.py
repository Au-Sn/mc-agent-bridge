#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task_layer_test.py -- 模块 A 任务层的离线判据（★不需要游戏 ✗ 假执行器✗★）

规格 §2.6 / §14.1：优先级／依赖／claim 租约／可中断状态机／"看账本→挑下一步→执行→记账"。

CHECKS
  T1  优先级排序：priority 高者先跑（runnable 的次序）
  T2  依赖阻断：depends_on 未做完 ⇒ 不执行；做完 ⇒ 自动解锁
  T3  ★依赖死了 ⇒ 依赖它的任务如实失败★（dep_failed ✗ 不执行、不假等）
  T4  ★claim 租约防双执行★：别人租着 ⇒ 第二次 claim 被拒 ＋ step 不碰它
  T5  租约过期 ⇒ 可接管（takeover 留痕）
  T6  中断恢复：interrupted 不被 step 选中；resume 后接着跑完
  T7  ★崩溃恢复★：账本里 running＋租约过期 ⇒ step 恢复成 interrupted（不重跑），resume 后跑完
  T8  ★失败如实停★：执行器说失败 ⇒ 任务 failed 带原因，不自动重试
  T9  执行器抛异常 ⇒ 记 failed/executor_exception（不崩）
  T10 ★证据强制✗★：执行器说 ok 但没 evidence ⇒ failed/no_evidence（不算完成）
  T11 dry：只挑一步看计划，不执行、不记账
  T12 跨进程账本读回（子进程 add ⇒ 父进程 load／list）
  T13 ★坏账本必须抛 TaskLedgerError★（坏 JSON／schema／tasks／state 不在机里）
  T14 非法状态迁移抛 TaskStateError（pending 直接 done／done 再 cancel）
  T15 与 jobs_store 对账：to_job 状态映射 ＋ brief 用人话读出 goal
  T16 finish 成功必须带证据；失败允许不带
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import task_layer as TL          # noqa: E402


def fake_exec(script, calls=None):
    """假执行器：按剧本回答；调用一次记一笔（★验"调了几次／调的是哪步"✗★）"""
    calls = calls if calls is not None else []
    script = list(script)

    def fn(task, step):
        calls.append({"task": task.get("id"), "i": step.get("i"),
                      "do": step.get("do")})
        if script:
            res = script.pop(0)
        else:
            res = {"ok": True, "evidence": "ev-auto"}
        if callable(res):
            return res(task, step)
        return res

    return fn, calls


def _sub(args) -> str:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "task_layer.py")] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT), env=env, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("subprocess 失败 rc=%d out=%r err=%r"
                           % (r.returncode, (r.stdout or "")[-300:], (r.stderr or "")[-300:]))
    return r.stdout or ""


def main() -> int:
    checks = []
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)

        # ── T1 优先级排序 ──
        st1 = base / "t1.json"
        lo = TL.add("低优先", priority=1, path=st1)
        hi = TL.add("高优先", priority=9, path=st1)
        mid = TL.add("中优先", priority=5, path=st1)
        order = [t["id"] for t in TL.runnable(st1)]
        checks.append(("T1 优先级排序（9 > 5 > 1）",
                       order == [hi["id"], mid["id"], lo["id"]],
                       "%s" % [t["goal"] for t in TL.runnable(st1)]))

        # ── T2 依赖阻断／解锁 ──
        st2 = base / "t2.json"
        a2 = TL.add("先做 A", priority=10, plan=["第一步｜成了", "第二步｜成了"], path=st2)
        b2 = TL.add("再做 B", priority=1, depends_on=[a2["id"]],
                    plan=["B 一步｜成了"], path=st2)
        run0 = [t["id"] for t in TL.runnable(st2)]
        blocked0 = TL.blocked(st2)
        ex2, calls2 = fake_exec([{"ok": True, "evidence": "ev-a1"},
                                 {"ok": True, "evidence": "ev-a2"},
                                 {"ok": True, "evidence": "ev-b1"}])
        r2a = TL.step(ex2, path=st2)                 # A 第 1 步
        run1 = [t["id"] for t in TL.runnable(st2)]
        r2b = TL.step(ex2, path=st2)                 # A 第 2 步 ⇒ A done
        run2 = [t["id"] for t in TL.runnable(st2)]
        r2c = TL.step(ex2, path=st2)                 # B 一步 ⇒ done
        b2_now = TL.get(b2["id"], st2)
        a2_now = TL.get(a2["id"], st2)
        checks.append(("T2 依赖阻断／解锁（A 没完 ⇒ B 不可跑；A 完 ⇒ B 能跑）",
                       run0 == [a2["id"]]
                       and blocked0 and blocked0[0]["id"] == b2["id"]
                       and blocked0[0]["unmet"] == [a2["id"]]
                       and r2a["why"] == "step_ok" and r2b["why"] == "done"
                       and run2 == [b2["id"]] and r2c["why"] == "done"
                       and a2_now["state"] == "done" and b2_now["state"] == "done"
                       and [c["task"] for c in calls2] == [a2["id"], a2["id"], b2["id"]],
                       "run0=%d blocked=%s 序列=%s" % (len(run0), blocked0,
                                                       [c["i"] for c in calls2])))

        # ── T3 ★依赖死了 ⇒ 依赖者也如实失败★ ──
        st3 = base / "t3.json"
        a3 = TL.add("会失败的 A", priority=9, plan=["一步｜成了"], path=st3)
        b3 = TL.add("依赖它的 B", priority=5, depends_on=[a3["id"]],
                    plan=["B 一步｜成了"], path=st3)
        ex3, calls3 = fake_exec([{"ok": False, "why": "sim_fail_A"}])
        r3 = TL.step(ex3, path=st3)                  # A 失败
        r3b = TL.step(ex3, path=st3)                 # 再推进 ⇒ B 应被标记 dep_failed
        b3_now = TL.get(b3["id"], st3)
        checks.append(("T3 ★依赖死了 ⇒ 依赖者如实失败（dep_failed ✗ 不执行）★",
                       r3["ok"] is False and r3["why"] == "sim_fail_A"
                       and b3_now["state"] == "failed"
                       and "dep_failed" in (b3_now.get("result") or "")
                       and len(calls3) == 1 and r3b["ok"] is False,
                       "B=%s(%s) ｜ 执行器只被调 %d 次"
                       % (b3_now["state"], b3_now.get("result"), len(calls3))))

        # ── T4 claim 租约防双执行 ──
        st4 = base / "t4.json"
        a4 = TL.add("独占任务", priority=5, plan=["一步｜成了"], path=st4)
        c1 = TL.claim(a4["id"], owner="A", lease_s=60, path=st4)
        c2 = TL.claim(a4["id"], owner="B", lease_s=60, path=st4)
        ex4, calls4 = fake_exec([])
        r4 = TL.step(ex4, owner="C", path=st4)
        checks.append(("T4 ★claim 租约防双执行★（B 被拒 ＋ step 不碰租出去的任务）",
                       c1.get("ok") is True and c2.get("ok") is False
                       and c2.get("why") == "lease_held"
                       and r4["ok"] is False and r4["why"] == "no_runnable"
                       and len(calls4) == 0,
                       "c1=%s c2=%s step=%s" % (c1.get("why"), c2.get("why"),
                                                r4.get("why"))))

        # ── T5 租约过期 ⇒ 可接管 ──
        st5 = base / "t5.json"
        a5 = TL.add("短租约任务", priority=5, plan=["一步｜成了"], path=st5)
        c5a = TL.claim(a5["id"], owner="A", lease_s=0.02, path=st5)
        time.sleep(0.05)
        c5b = TL.claim(a5["id"], owner="B", lease_s=60, path=st5)
        t5 = TL.get(a5["id"], st5)
        hist = (t5.get("history") or [])[-1]
        checks.append(("T5 租约过期 ⇒ 可接管（takeover 留痕）",
                       c5a.get("ok") is True and c5b.get("ok") is True
                       and c5b.get("takeover") is True
                       and hist.get("why") == "claim_takeover"
                       and (t5.get("claim") or {}).get("owner") == "B",
                       "takeover=%s ｜ 末条历史=%s" % (c5b.get("takeover"), hist)))

        # ── T6 中断恢复 ──
        st6 = base / "t6.json"
        a6 = TL.add("两步任务", priority=5, plan=["一｜成了", "二｜成了"], path=st6)
        ex6, calls6 = fake_exec([{"ok": True, "evidence": "ev1"},
                                 {"ok": True, "evidence": "ev2"}])
        s6a = TL.step(ex6, path=st6)                 # 完成第 1 步 ⇒ 回 pending
        TL.interrupt(a6["id"], "user_says_stop", path=st6)
        s6b = TL.step(ex6, path=st6)                 # interrupted ⇒ 不该被选中
        TL.resume(a6["id"], path=st6)
        s6c = TL.step(ex6, path=st6)                 # 第 2 步 ⇒ done
        t6 = TL.get(a6["id"], st6)
        checks.append(("T6 中断恢复：interrupted 不被选中，resume 后接着跑完",
                       s6a["why"] == "step_ok" and s6a["plan_done"] == 1
                       and s6b["why"] == "no_runnable"
                       and s6c["why"] == "done" and s6c["plan_done"] == 2
                       and t6["state"] == "done" and len(calls6) == 2,
                       "a=%s b=%s c=%s 状态=%s" % (s6a["why"], s6b["why"], s6c["why"],
                                                   t6["state"])))

        # ── T7 ★崩溃恢复：running＋租约过期 ⇒ interrupted（不重跑）★ ──
        st7 = base / "t7.json"
        a7 = TL.add("崩溃任务", priority=5, plan=["一｜成了", "二｜成了"], path=st7)
        ex7, calls7 = fake_exec([{"ok": True, "evidence": "ev1"},
                                 {"ok": True, "evidence": "ev2"}])
        TL.step(ex7, path=st7)                       # 做完第 1 步
        led7 = TL.load(st7)
        t7 = led7["tasks"][a7["id"]]
        t7["state"] = "running"
        t7["claim"] = {"owner": "dead-proc", "claim_id": "c-dead",
                       "claimed_at": time.time() - 120,
                       "expires_at": time.time() - 60, "lease_s": 60}
        TL.save(led7, st7)
        r7 = TL.step(ex7, path=st7)                  # 恢复 ⇒ 这一步不该执行
        n_after_recover = len(calls7)
        t7_recovered = TL.get(a7["id"], st7)
        TL.resume(a7["id"], st7)
        r7b = TL.step(ex7, path=st7)
        t7_final = TL.get(a7["id"], st7)
        checks.append(("T7 ★崩溃恢复★：租约过期的 running ⇒ interrupted（不重跑）",
                       a7["id"] in (r7.get("recovered") or [])
                       and r7["why"] == "no_runnable"
                       and t7_recovered["state"] == "interrupted"
                       and t7_recovered["interrupted_reason"] == "lease_expired"
                       and n_after_recover == 1
                       and [c["i"] for c in calls7] == [1, 2]
                       and r7b["why"] == "done" and t7_final["state"] == "done",
                       "recovered=%s 状态=%s 恢复时调用=%d 全序列=%s"
                       % (r7.get("recovered"), t7_recovered["state"], n_after_recover,
                          [c["i"] for c in calls7])))

        # ── T8 ★失败如实停✗★ ──
        st8 = base / "t8.json"
        a8 = TL.add("失败任务", priority=5, plan=["一步｜成了", "二步｜成了"], path=st8)
        ex8, calls8 = fake_exec([{"ok": False, "why": "no_path"}])
        r8 = TL.step(ex8, path=st8)
        t8 = TL.get(a8["id"], st8)
        r8b = TL.step(ex8, path=st8)
        checks.append(("T8 ★失败如实停★：failed＋原因，不自动重试",
                       r8["ok"] is False and r8["why"] == "no_path"
                       and t8["state"] == "failed"
                       and t8.get("result") == "failed:no_path"
                       and r8b["why"] == "no_runnable" and len(calls8) == 1,
                       "state=%s result=%s 调用=%d"
                       % (t8["state"], t8.get("result"), len(calls8))))

        # ── T9 执行器抛异常 ⇒ 记失败不崩 ──
        st9 = base / "t9.json"
        a9 = TL.add("抛异常任务", priority=5, plan=["一步｜成了"], path=st9)

        def boom(task, step):
            raise RuntimeError("boom")
        r9 = TL.step(boom, path=st9)
        t9 = TL.get(a9["id"], st9)
        checks.append(("T9 执行器抛异常 ⇒ failed/executor_exception",
                       r9["ok"] is False
                       and str(r9["why"]).startswith("executor_exception:")
                       and t9["state"] == "failed",
                       "%s ｜ %s" % (r9.get("why"), t9["state"])))

        # ── T10 ★证据强制✗★ ──
        st10 = base / "t10.json"
        a10 = TL.add("没证据任务", priority=5, plan=["一步｜成了"], path=st10)
        ex10, _c10 = fake_exec([{"ok": True}])
        r10 = TL.step(ex10, path=st10)
        t10 = TL.get(a10["id"], st10)
        checks.append(("T10 ★没证据不算完成★（ok 但无 evidence ⇒ failed/no_evidence）",
                       r10["ok"] is False and r10["why"] == "no_evidence"
                       and t10["state"] == "failed",
                       "%s ｜ %s" % (r10.get("why"), t10["state"])))

        # ── T11 dry：只看计划不执行 ──
        st11 = base / "t11.json"
        a11 = TL.add("dry 任务", priority=5, plan=["一｜成了"], path=st11)
        ex11, calls11 = fake_exec([])
        r11 = TL.step(ex11, dry=True, path=st11)
        t11 = TL.get(a11["id"], st11)
        checks.append(("T11 dry：挑一步看计划，不执行不记账",
                       r11["ok"] is True and r11["why"] == "dry"
                       and r11.get("executed") is False and len(calls11) == 0
                       and t11["state"] == "pending" and t11["plan_done"] == 0,
                       "why=%s executed=%s 状态=%s"
                       % (r11.get("why"), r11.get("executed"), t11["state"])))

        # ── T12 跨进程账本读回 ──
        st12 = base / "t12.json"
        out12 = _sub(["--state", str(st12), "--add", "cross-proc-task",
                      "--priority", "7", "--plan", "go|arrived"])
        created = json.loads(out12)
        led12 = TL.load(st12)
        listed = json.loads(_sub(["--state", str(st12), "--list"]))
        checks.append(("T12 跨进程账本读回（子进程 add ⇒ 父进程 load／list）",
                       created.get("priority") == 7
                       and len(led12["tasks"]) == 1
                       and listed[0]["goal"] == "cross-proc-task"
                       and listed[0]["plan"][0]["do"] == "go",
                       "priority=%s tasks=%d" % (created.get("priority"),
                                                 len(led12["tasks"]))))

        # ── T13 ★坏账本必须抛 TaskLedgerError★ ──
        bad13 = []
        p13 = base / "bad13.json"
        cases = [
            ("{bad json", "坏 JSON"),
            (json.dumps({"schema": "other@9", "tasks": {}}), "schema 不对"),
            (json.dumps({"schema": TL.SCHEMA, "tasks": []}), "tasks 不是 dict"),
            (json.dumps({"schema": TL.SCHEMA, "tasks": {"x": {"id": "x", "goal": "g",
                                                              "state": "飞", "priority": 1,
                                                              "depends_on": [], "plan": []}}}),
             "state 不在状态机里"),
        ]
        for raw, why in cases:
            p13.write_text(raw, encoding="utf-8")
            try:
                TL.load(p13)
                bad13.append((why, "没抛"))
            except TL.TaskLedgerError as exc:
                print("  （T13 预期抛错：%s ⇒ TaskLedgerError ✓）" % why)
            except Exception as exc:
                bad13.append((why, "抛了 %s" % type(exc).__name__))
        checks.append(("T13 ★坏账本必须抛 TaskLedgerError★（四类坏法）",
                       not bad13, str(bad13[:3]) if bad13 else "4/4 都抛了"))

        # ── T14 非法状态迁移抛 TaskStateError ──
        st14 = base / "t14.json"
        a14 = TL.add("迁移任务", priority=5, plan=["一｜成了"], path=st14)
        bad14 = []
        try:
            TL.finish(a14["id"], True, evidence="ev", path=st14)
            bad14.append("pending 直接 finish 没抛")
        except TL.TaskStateError as exc:
            print("  （T14 预期拒绝：pending 直接 finish ⇒ TaskStateError ✓）")
        ex14, calls14 = fake_exec([{"ok": True, "evidence": "ev1"}])
        TL.step(ex14, path=st14)
        try:
            TL.cancel(a14["id"], "late", path=st14)
            bad14.append("done 还能 cancel")
        except TL.TaskStateError as exc:
            print("  （T14 预期拒绝：done 再 cancel ⇒ TaskStateError ✓）")
        try:
            TL.resume(a14["id"], path=st14)
            bad14.append("pending 也能 resume")
        except TL.TaskStateError as exc:
            print("  （T14 预期拒绝：pending resume ⇒ TaskStateError ✓）")
        checks.append(("T14 非法状态迁移抛 TaskStateError（3 类）",
                       not bad14, str(bad14) if bad14 else "3/3 都抛了"))

        # ── T15 与 jobs_store 对账 ──
        st15 = base / "t15.json"
        a15 = TL.add("去把箱子整理一下", priority=8, plan=["走到箱子｜arrived"], path=st15)
        job15 = TL.to_job(a15)
        brief15 = TL.brief(st15)
        a15b = TL.add("已完成任务", priority=1, plan=["一｜成了"], path=st15)
        ex15, _c15 = fake_exec([{"ok": True, "evidence": "ev1"},
                                {"ok": True, "evidence": "ev2"}])
        TL.step(ex15, path=st15)                 # 先跑 priority 8 的（它还在）
        TL.step(ex15, path=st15)                 # 再跑剩下的
        job15_done = TL.to_job(TL.get(a15["id"], st15))
        job15b = TL.to_job(TL.get(a15b["id"], st15))
        checks.append(("T15 与 jobs_store 对账：to_job 状态映射 ＋ brief 出人话",
                       job15["status"] == "open" and job15["goal"] == "去把箱子整理一下"
                       and job15_done["status"] == "done" and job15b["status"] == "done"
                       and "去把箱子整理一下" in brief15
                       and "下一步" in brief15,
                       "pending→%s done→%s brief_len=%d"
                       % (job15["status"], job15_done["status"], len(brief15))))

        # ── T16 finish 成功必须带证据 ──
        st16 = base / "t16.json"
        a16 = TL.add("收尾任务", priority=5, plan=["一｜成了"], path=st16)
        cl16 = TL.claim(a16["id"], owner="A", lease_s=60, path=st16)
        bad16 = []
        try:
            TL.finish(a16["id"], True, evidence="", path=st16)
            bad16.append("成功没证据也收了")
        except ValueError as exc:
            print("  （T16 预期拒绝：成功没证据 ⇒ ValueError ✓）")
        try:
            TL.finish(a16["id"], False, result="sim_fail", path=st16)
        except Exception as exc:
            bad16.append("失败收尾抛了 %s" % type(exc).__name__)
        t16 = TL.get(a16["id"], st16)
        checks.append(("T16 finish：成功必须带证据；失败允许不带",
                       not bad16 and t16["state"] == "failed"
                       and t16.get("result") == "failed:sim_fail",
                       str(bad16) if bad16 else "%s/%s" % (t16["state"], t16.get("result"))))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:130]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => task_layer 有红（%d 项不对）" % bad)
        print("TASKLAYER ok=0 bad=%d" % bad)
        return 1
    print("  => task_layer 全绿（优先级／依赖／租约／中断恢复／失败如实停）")
    print("TASKLAYER ok=1 checks=%d states=%d" % (len(checks), len(TL.STATES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
