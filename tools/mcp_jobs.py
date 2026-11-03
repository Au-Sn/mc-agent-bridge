#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_jobs.py —— ★长任务账本那 6 件工具★（v2.19 从 `tools/mc_mcp.py` 抽出 ✓）

★为什么先拆这一组✗★：`ast` 量出来它们**只依赖 `cut`** ✓ 而 `jobs_store` 全是
**函数体内的局部 import** ✗ ⇒ 拆出来**零循环依赖** ✓
（比感知组安全得多 ✓ —— 那一组缠着 `mapread`/`pathplan` ✓）

★★纪律：这一刀**一个字都没改**✗★★（同第一刀 `mcp_core.py` ✓）
  · 判据 ✓：`py tools/mcp_surface.py --diff tmp/surface_before.json`
    ⇒ 工具面必须**逐字节相同** ✓
"""
from __future__ import annotations

from mcp_core import (
    cut,
)

def t_job_plan(job_id, steps):
    """★给一件活写一份**步骤清单**★ ✗（2026-09-29 第 22 轮 ✓ 优先级③"批量作业编排"✓）

    一行一步 ✓ 行内用 `｜` 或 `|` 分开「**做什么 ｜ 怎么算做成了**」✓（判据建议写 ✓）
    写完就能 `job_next` 查"下一步是哪一步"✓ 而且**跨会话/跨重启都记得** ✓
    """
    from jobs_store import plan as jplan
    from jobs_store import next_plan_step as jnext
    from jobs_store import plan_progress as jprog
    try:
        j = jplan(str(job_id), str(steps or ""))
    except Exception as e:
        return cut("写不了计划 ✗：%s: %s" % (type(e).__name__, e)), True
    if j is None:
        return cut("没有这件活 %s ✗（先 job_list 看看 ✓）" % job_id), True
    d, t = jprog(j)
    nxt = jnext(j)
    return cut("%s 的计划写好了 ✓：%d 步（已完成 %d ✓）\n下一步 ⇒ %s\n"
               "★记住 ✓：把某一步标成做完要带**证据**（世界真值 ✓）—— 用 job_step 的 plan_i ✓★"
               % (j["id"], t, d, (nxt or {}).get("do", "（都做完了 ⇒ 收尾 ✓）"))), False

def t_job_next(job_id):
    """★这件活的**下一步**是哪一步★ ✓（顺序固定 ✓ 做过的不再催 ✓）"""
    from jobs_store import load as jload
    from jobs_store import next_plan_step as jnext
    from jobs_store import plan_progress as jprog
    j = jload(str(job_id))
    if j is None:
        return cut("没有这件活 %s ✗" % job_id), True
    its = j.get("plan") or []
    if not its:
        return cut("%s 还没写步骤清单 ✗ ⇒ 先用 `job_plan` 写一份 ✓（不然跨会话就丢了 ✓）\n"
                   "现在记的下一步（自由文本）：%s" % (j["id"], j.get("next") or "-")), False
    d, t = jprog(j)
    nxt = jnext(j)
    L = ["%s：%d/%d 步做完 ✓ ｜ 目标：%s" % (j["id"], d, t, j.get("goal"))]
    for it in its:
        flag = "✓" if it.get("done_at") else ("⇒" if nxt and it["i"] == nxt["i"] else "·")
        L.append("  %s %d) %s%s%s" % (flag, it["i"], it["do"],
                                      ("  ｜判据：" + it["judge"]) if it.get("judge") else "",
                                      ("  ｜证据：" + it["evidence"]) if it.get("evidence") else ""))
    if nxt:
        L.append("★下一步就做第 %d 步 ✓ 做完用 `job_step(..., plan_i=%d, evidence=世界真值)` 记上 ✓★"
                 % (nxt["i"], nxt["i"]))
    else:
        L.append("★计划上的步骤都做完了 ⇒ 用 `job_close` 收尾 ✓★")
    return cut("\n".join(L)), False

def t_job_step(job_id, note, next_step="", evidence="", wait_s=0, plan_i=0):
    """★记一步★ ✓（`plan_i>0` ⇒ 顺便把计划里的第 i 步标成做成了 ✓ **必须带证据** ✗）"""
    from jobs_store import step as jstep          # ★旧版是局部 import ✓ 我这也得有 ✗
    from jobs_store import mark_plan_step as jmark
    j = jstep(str(job_id), str(note), str(next_step or ""), str(evidence or ""),
              float(wait_s or 0))
    if j is None:
        return cut("没有这件活 %s ✗（先 job_list 看看 ✓）" % job_id), True
    plan_note = ""
    if int(plan_i or 0) > 0:
        try:
            j2 = jmark(str(job_id), int(plan_i), str(evidence or ""))
            if j2 is not None:
                from jobs_store import plan_progress as jprog
                d, t = jprog(j2)
                plan_note = ("\n★计划第 %d 步标成做成了 ✓（%d/%d ✓）｜ 下一步 ⇒ %s★"
                             % (int(plan_i), d, t, j2.get("next") or "-"))
        except Exception as e:
            # ★没有证据就**不许**算完成 ✗（P-family："我说我做完了"不算 ✓）
            return cut("记下了（%s 第 %d 步）✗ 但**计划步骤没标上**：%s: %s\n"
                       "  ⇒ 要标完成就必须给**证据**（世界真值 ✓ 例如「背包 4→0」✓）"
                       % (j["id"], len(j.get("steps") or []), type(e).__name__, e)), True
    wait_note = ("；这件活先等到 %s 再动 ✓" % j["not_before"]) if j.get("not_before") else ""
    return cut("记下了（%s 第 %d 步）下一步：%s%s%s"
               % (j["id"], len(j.get("steps") or []), j.get("next") or "-",
                  wait_note, plan_note)), False

def t_job_open(goal, next_step=""):
    from jobs_store import open_job, open_jobs
    warn = ""
    try:
        old = open_jobs()
        if old:
            warn = ("⚠ 账本上已经有 %d 件没做完的活：%s\n"
                    "    ⇒ 如果这件跟上面是**同一件事** ⇒ 别开新账 ✗ 用 `job_step` 接着旧的做 ✓\n"
                    "    （确实要开新的 ⇒ 先把旧的那件 `job_close` 收掉 ✓ 说清为什么换 ✓）\n"
                    % (len(old), ", ".join("%s(%s)" % (o["id"], o["goal"][:14]) for o in old[:3])))
    except Exception:
        warn = ""
    j = open_job(str(goal), str(next_step or ""))
    return cut("%s开了一件活 %s\n%s" % (warn, j["id"], j["goal"])), False

def t_job_list():
    from jobs_store import all_jobs, fmt
    js = all_jobs()
    if not js:
        return cut("账本上还没有任何活。"), False
    openn = [j for j in js if j.get("status") == "open"]
    parts = ["未做完 %d 件 / 一共 %d 件" % (len(openn), len(js))]
    for j in js[-6:]:
        parts.append(fmt(j, 2))
    return cut("\n".join(parts)), False

def t_job_close(job_id, result, status="done"):
    from jobs_store import close as jclose
    j = jclose(str(job_id), str(result), str(status or "done"))
    if j is None:
        return cut("没有这件活 %s ✗" % job_id), True
    return cut("收尾了 %s [%s]：%s" % (j["id"], j["status"], j.get("result"))), False

