#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator_test.py -- 模块 L 会话骨架的判据（★离线 ✗ 临时 jobs 目录✗★）

规格 §10.3 / §14.4 / §19：
  ★L-a chat 绝不动世界**（`need_exec=False` ＋ **0 条 job**）✗★
  ★L-c `task` 必落 `jobs/` 且带**验收判据**✗★
  ★L-d `mixed` 必拆成"一句回复 ＋ 一条 job"✗★
  ★L-f 一条任务**恰好 2 条消息**（开始 ＋ 结束）✗★

CHECKS
  O1 chat ⇒ need_exec=False ＋ **0 条 job** ＋ 有回复
  O2 query ⇒ 同上（★只读缓存✗★）
  O3 task ⇒ need_exec=True ＋ **恰好 1 条 job** ＋ job 里有 `accept` 验收判据
  O4 mixed ⇒ **1 条 job ＋ 1 条聊天回复**（★顺序：先聊后做✗★）
  O5 ★一条任务恰好 2 条消息★（handle 的 start ＋ finish 的 done）
  O6 失败收尾要带 `reason=`（★不许"没做到"还装作没事✗★）
  O7 job 落盘可读回，状态从 open → done/failed
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import orchestrator as O          # noqa: E402


def _msgs(td) -> list:
    p = Path(td) / "messages.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    checks = []

    with tempfile.TemporaryDirectory() as td:
        # O1 chat
        r1 = O.handle("你好呀", jobs_dir=td)
        n_jobs = len(list(Path(td).glob("*.json")))
        checks.append(("O1 chat ⇒ 不动世界（0 条 job ＋ 有回复）",
                       r1["need_exec"] is False and n_jobs == 0 and bool(r1["reply"]),
                       "jobs=%d reply=%s" % (n_jobs, r1["reply"][:28])))

        # O2 query
        r2 = O.handle("你现在在哪", jobs_dir=td)
        n_jobs2 = len([p for p in Path(td).glob("*.json")])
        checks.append(("O2 query ⇒ 不动世界", r2["need_exec"] is False and n_jobs2 == 0,
                       "jobs=%d" % n_jobs2))

        # O3 task
        r3 = O.handle("帮我挖三个铁矿", jobs_dir=td)
        jobs3 = [p for p in Path(td).glob("*.json")]
        job3 = r3["job"] or {}
        checks.append(("O3 task ⇒ 恰好 1 条 job 且带验收判据",
                       r3["need_exec"] is True and len(jobs3) == 1
                       and "验收" in (job3.get("accept") or ""),
                       "jobs=%d accept=%s" % (len(jobs3), (job3.get("accept") or "")[:24])))

        # O4 mixed
        r4 = O.handle("你好啊，顺便去把门关上", jobs_dir=td)
        msgs4 = [m for m in _msgs(td) if m.get("from_user") == "你好啊，顺便去把门关上"]
        kinds4 = [m["kind"] for m in msgs4]
        checks.append(("O4 mixed ⇒ 1 条聊天回复 ＋ 1 条 job（先聊后做）",
                       r4["intent"] == "mixed" and r4["job"] is not None
                       and kinds4[:1] == ["chat"] and "start" in kinds4,
                       "kinds=%s" % (kinds4,)))

        # O5 一条任务恰好 2 条消息
        before = len(_msgs(td))
        r5 = O.handle("去砍两棵树", jobs_dir=td)
        job5 = r5["job"]
        mid = [m for m in _msgs(td)[before:] if m.get("kind") in ("start",)]
        O.finish(job5, True, jobs_dir=td)
        all5 = [m for m in _msgs(td)[before:] if m.get("from_user") == "去砍两棵树"
                or m.get("kind") == "done"]
        n5 = len([m for m in _msgs(td)[before:]])
        checks.append(("O5 一条任务恰好 2 条消息（start ＋ done）",
                       len(mid) == 1 and n5 == 2, "start=%d 总=%d" % (len(mid), n5)))

        # O6 失败收尾要带 reason=
        before6 = len(_msgs(td))
        r6 = O.handle("帮我挖三个铁矿", jobs_dir=td)
        O.finish(r6["job"], False, why="no_dig_zone", jobs_dir=td)
        tail6 = [m for m in _msgs(td)[before6:] if m.get("kind") == "fail"]
        checks.append(("O6 失败收尾带 reason=",
                       bool(tail6) and "reason=no_dig_zone" in tail6[0]["to_user"],
                       tail6[0]["to_user"][:50] if tail6 else "（没有失败消息）"))

        # O7 job 落盘 → done
        p7 = Path(td) / (r6["job"]["id"] + ".json")
        d7 = json.loads(p7.read_text(encoding="utf-8"))
        checks.append(("O7 job 落盘可读回 ＋ 状态变 failed",
                       d7.get("status") == "failed" and d7.get("result", "").startswith("failed:"),
                       "status=%s result=%s" % (d7.get("status"), d7.get("result"))))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => orchestrator FAIL (%d)" % bad)
        print("ORCH ok=0 bad=%d" % bad)
        return 1
    print("  => orchestrator PASS (chat never creates jobs; a task emits exactly 2 messages)")
    print("ORCH ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
