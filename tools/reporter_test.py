#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reporter_test.py -- 模块 L7 汇报官的离线判据（★不需要游戏 ✗ 合成账本/事件✗★）

规格 §10.3／§14.1／§14.4：L7 无权限 · 只读账本/事件/校验/理由 · 只报开始与结束。

CHECKS
  R1  ★空账本如实说"没有记录"★（三个等级都不编"完成"）
  R2  合成账本：条目与证据一一对应（做成/失败/在做 各自证据指针）
  R3  ★没有证据不出现"完成"★：账本标 done 但没证据 ⇒ 异常 done_no_evidence ＋ 未验证
  R4  ★坏账本/坏事件文件如实报★（异常进 anomalies ✗ 不静默少报）
  R5  长度分级：one ≤160 字单行 ／ para 多行 ／ full 带证据指针（同一批 counts）
  R6  period：today 只看今天 ／ all 看全部（旧账/旧事件）
  R7  period=job:<id>：只报那件活 ＋ 挂着该 mission 的事件
  R8  period=events:N：只取最近 N 条事件（不混任务）
  R9  verifier verdict：红判定进条目＋异常；绿不报异常
  R10 reasons：重要理由进条目（带证据指针）
  R11 与 say.py 语码兼容：短回执落 say 码（有限集内）
  R12 坏参数抛 ValueError（level/period/max_items）
  R13 确定性：同输入两次汇报逐字相同
  R14 ★H 接线端到端★：做一件事（注入假执行器）⇒ event_memory 有它
      ⇒ reporter 能把它汇报出来（含证据指针；不连游戏）
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import reporter as RP          # noqa: E402
import event_memory as EM      # noqa: E402


def _ts_str(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def write_job(jobs_dir, jid, status, goal, evidence=None, result="", next_="",
              created=None):
    job = {"id": jid, "goal": goal, "status": status, "owner": "Bot",
           "created": created or _ts_str(time.time()),
           "updated": created or _ts_str(time.time()),
           "next": next_, "steps": [], "plan": [], "result": result}
    if evidence is not None:
        job["steps"].append({"at": _ts_str(time.time()), "note": "done",
                             "evidence": evidence})
    (pathlib.Path(jobs_dir) / (jid + ".json")).write_text(
        json.dumps(job, ensure_ascii=False), encoding="utf-8")
    return job


class FakeDsh:
    """给 primitives 的假 dsh：digest 带递增 time=，dig 回执成功"""

    def __init__(self, ticks=6):
        self.cmds = []
        self.t = 1000
        self.ticks = ticks

    def __call__(self, cmd, t=45.0):
        self.cmds.append(cmd)
        if "dshdigest" in cmd:
            self.t += self.ticks
            return ("dshdigest reason=ok pos=1.0,70.0,1.0 time=%d hp=20.0 food=18 items=5"
                    % self.t)
        return "dshdig %s ok" % cmd.split(" ", 1)[-1][:30]


def main() -> int:
    checks = []
    now = time.time()
    today_start = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    yesterday = today_start - 3600.0

    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)

        # ── R1 空账本：如实说没有记录 ──
        empty_jobs = base / "empty_jobs"
        empty_jobs.mkdir()
        missing_events = base / "no_events.json"
        reps1 = [RP.report(period="today", level=lv, jobs_dir=empty_jobs,
                           events_path=missing_events, reasons_records=[]) for lv in
                 ("one", "para", "full")]
        no_fake_success = all(("做成" not in r["text"] and "完成" not in r["text"])
                              for r in reps1)
        checks.append(("R1 ★空账本如实说没有记录★（不编完成）",
                       all(r["ok"] and r["counts"]["jobs"] == 0
                           and r["counts"]["events"] == 0 for r in reps1)
                       and all("没有记录" in r["text"] for r in reps1)
                       and no_fake_success,
                       "text=%r" % (reps1[2]["text"][:80],)))

        # ── R2 合成账本：条目与证据一一对应 ──
        jd2 = base / "jobs2"
        jd2.mkdir()
        write_job(jd2, "j-done", "done", "去挖三块铁",
                  evidence="SUMMARY task pass=1 fail=0 total=1")
        write_job(jd2, "j-fail", "failed", "把石头搬回家",
                  evidence="receipt=dshdig refused reason=no_dig_zone",
                  result="failed:no_dig_zone")
        write_job(jd2, "j-open", "open", "整理箱子", next_="走到箱子")
        ev2 = base / "events2.json"
        EM.append("dig", "挖了一块铁", evidence={"kind": "receipt",
                                            "ref": "verify=dig_verified"},
                  when=now - 5, where=(1, 70, 1), path=ev2)
        rep2 = RP.report(period="today", level="full", jobs_dir=jd2,
                         events_path=ev2, reasons_records=[], now=now)
        by_kind = {}
        for it in rep2["items"]:
            by_kind.setdefault(it["kind"], []).append(it)
        done_ok = (by_kind.get("done") and by_kind["done"][0]["job"] == "j-done"
                   and any("SUMMARY" in e for e in by_kind["done"][0]["evidence"]))
        fail_ok = (by_kind.get("failed") and "no_dig_zone" in by_kind["failed"][0]["summary"]
                   and by_kind["failed"][0]["evidence"])
        open_ok = (by_kind.get("open") and "整理箱子" in by_kind["open"][0]["summary"])
        ev_ok = [it for it in rep2["items"] if it["kind"] == "event:dig"]
        checks.append(("R2 合成账本：做成/失败/在做/事件 各带证据指针",
                       rep2["counts"] == {"jobs": 3, "jobs_done": 1, "jobs_failed": 1,
                                          "jobs_open": 1, "jobs_cancelled": 0,
                                          "events": 1, "events_important": 1,
                                          "verdicts": 0, "verdict_fail": 0,
                                          "reasons": 0, "anomalies": 0,
                                          "important_items": 1}
                       and done_ok and fail_ok and open_ok and len(ev_ok) == 1
                       and ev_ok[0]["evidence"] == ["verify=dig_verified"],
                       "counts=%s kinds=%s" % (rep2["counts"], sorted(by_kind))))

        # ── R3 ★无证据不称完成★ ──
        jd3 = base / "jobs3"
        jd3.mkdir()
        write_job(jd3, "j-nolabel", "done", "没留证据的活")
        rep3 = RP.report(period="today", level="full", jobs_dir=jd3,
                         events_path=base / "none3.json", reasons_records=[])
        kinds3 = [it["kind"] for it in rep3["items"]]
        checks.append(("R3 ★没有证据不出现完成★（done⇒未验证＋异常）",
                       rep3["counts"]["jobs_done"] == 1
                       and "done" not in kinds3 and "done_unverified" in kinds3
                       and any(a["kind"] == "done_no_evidence" for a in rep3["anomalies"])
                       and "未验证" in rep3["text"] and "做成" not in rep3["text"],
                       "kinds=%s anomalies=%s" % (kinds3,
                                                  [a["kind"] for a in rep3["anomalies"]])))

        # ── R4 ★坏账本/坏事件文件如实报★ ──
        jd4 = base / "jobs4"
        jd4.mkdir()
        write_job(jd4, "j-ok", "done", "好的活", evidence="ev-ok")
        (jd4 / "j-broken.json").write_text("{ this is not json", encoding="utf-8")
        bad_ev = base / "bad_events.json"
        bad_ev.write_text("{broken event file", encoding="utf-8")
        rep4 = RP.report(period="today", level="full", jobs_dir=jd4,
                         events_path=bad_ev, reasons_records=[])
        a4 = [a["kind"] for a in rep4["anomalies"]]
        checks.append(("R4 ★坏账本/坏事件文件如实报★（不静默少报）",
                       rep4["ok"] is True and "bad_job_ledger" in a4
                       and "bad_event_ledger" in a4
                       and rep4["counts"]["jobs"] == 1
                       and any(it["kind"] == "done" for it in rep4["items"]),
                       "anomalies=%s" % (a4,)))

        # ── R5 长度分级 ──
        reps5 = [RP.report(period="today", level=lv, jobs_dir=jd2,
                           events_path=ev2, reasons_records=[]) for lv in
                 ("one", "para", "full")]
        one_txt = reps5[0]["text"]
        checks.append(("R5 长度分级：one≤160 单行 ／ para 多行 ／ full 带证据",
                       len(one_txt) <= 160 and "\n" not in one_txt
                       and len(reps5[1]["text"].splitlines()) >= 2
                       and "证据=" in reps5[2]["text"]
                       and all(r["counts"]["jobs"] == 3 for r in reps5),
                       "one=%d字 para=%d行 full=%d字"
                       % (len(one_txt), len(reps5[1]["text"].splitlines()),
                          len(reps5[2]["text"]))))

        # ── R6 period：today vs all ──
        jd6 = base / "jobs6"
        jd6.mkdir()
        write_job(jd6, "j-today", "done", "今天的活", evidence="ev-today")
        write_job(jd6, "j-old", "done", "昨天的活", evidence="ev-old",
                  created=_ts_str(yesterday))
        ev6 = base / "events6.json"
        EM.append("dig", "今天挖", evidence="ev-now", when=now - 5, path=ev6)
        EM.append("dig", "昨天挖", evidence="ev-old", when=yesterday, path=ev6)
        rep6t = RP.report(period="today", level="full", jobs_dir=jd6,
                          events_path=ev6, reasons_records=[], now=now)
        rep6a = RP.report(period="all", level="full", jobs_dir=jd6,
                          events_path=ev6, reasons_records=[], now=now)
        checks.append(("R6 period：today 只看今天 ／ all 看全部",
                       rep6t["counts"]["jobs"] == 1 and rep6t["counts"]["events"] == 1
                       and rep6a["counts"]["jobs"] == 2 and rep6a["counts"]["events"] == 2
                       and {it["job"] for it in rep6a["items"] if it.get("job")}
                       == {"j-today", "j-old"},
                       "today=%s all=%s" % (rep6t["counts"], rep6a["counts"])))

        # ── R7 period=job:<id> ──
        rep7 = RP.report(period="job:j-today", level="full", jobs_dir=jd6,
                         events_path=ev6, reasons_records=[], now=now)
        ev7 = [it for it in rep7["items"] if it["kind"].startswith("event:")]
        checks.append(("R7 period=job:<id>：只报那件活＋挂它 mission 的事件",
                       rep7["counts"]["jobs"] == 1
                       and [it["job"] for it in rep7["items"]
                            if it.get("job")] == ["j-today"]
                       and len(ev7) == 0,     # 这些事件没挂 mission ⇒ 不该混进来
                       "jobs=%d events=%d" % (rep7["counts"]["jobs"],
                                              rep7["counts"]["events"])))

        # ── R8 period=events:N ──
        rep8 = RP.report(period="events:1", level="full", jobs_dir=jd6,
                         events_path=ev6, reasons_records=[], now=now)
        checks.append(("R8 period=events:N：只取最近 N 条事件（不混任务）",
                       rep8["counts"]["events"] == 1 and rep8["counts"]["jobs"] == 0
                       and len([it for it in rep8["items"]
                                if it["kind"].startswith("event:")]) == 1,
                       "events=%d jobs=%d" % (rep8["counts"]["events"],
                                              rep8["counts"]["jobs"])))

        # ── R9 verifier verdict ──
        verdicts9 = [{"ok": True, "why": "dig_verified", "action": "dig",
                      "pos": [1, 70, 1]},
                     {"ok": False, "why": "dig_not_done", "action": "dig",
                      "pos": [2, 70, 2]}]
        rep9 = RP.report(period="today", level="para", jobs_dir=empty_jobs,
                         events_path=base / "none9.json", verdicts=verdicts9,
                         reasons_records=[])
        checks.append(("R9 verifier verdict：红判定进条目＋异常，绿不报异常",
                       rep9["counts"]["verdicts"] == 2
                       and rep9["counts"]["verdict_fail"] == 1
                       and any(a["kind"] == "verdict_fail" for a in rep9["anomalies"])
                       and len([it for it in rep9["items"]
                                if it["kind"] == "verdict"]) == 2,
                       "verdicts=%s anomalies=%s"
                       % (rep9["counts"]["verdicts"],
                          [a["kind"] for a in rep9["anomalies"]])))

        # ── R10 reasons ──
        reasons10 = [{"ts": now, "reason": "挖了矿石", "action": "dig",
                      "important": True, "mission": "j-x"}]
        rep10 = RP.report(period="today", level="full", jobs_dir=empty_jobs,
                          events_path=base / "none10.json",
                          reasons_records=reasons10)
        checks.append(("R10 reasons：重要理由进条目（带证据指针）",
                       rep10["counts"]["reasons"] == 1
                       and any(it["kind"] == "reason" and it["evidence"]
                               for it in rep10["items"])
                       and "理由" in rep10["text"],
                       "reasons=%d" % rep10["counts"]["reasons"]))

        # ── R11 say 语码兼容 ──
        rep11a = RP.report(period="today", level="one", jobs_dir=jd2,
                           events_path=ev2, reasons_records=[])
        rep11b = RP.report(period="today", level="one", jobs_dir=jd3,
                           events_path=base / "none3.json", reasons_records=[])
        say11a, say11b = RP.to_say(rep11a), RP.to_say(rep11b)
        try:
            import say as S
            known_ok = say11a["code"] in S.CODES and say11b["code"] in S.CODES
        except Exception as exc:              # ★不许静默✗★
            known_ok = False
            print("  （R11 say 模块不可用：%r）" % (exc,))
        checks.append(("R11 与 say.py 语码兼容（短回执落有限码）",
                       rep11a["say_code"] in ("done", "unknown", "no_dig_zone")
                       and say11a["known"] is True and say11b["known"] is True
                       and known_ok and "reason=" in say11a["text"],
                       "a=%s b=%s" % (say11a["text"][:40], say11b["text"][:40])))

        # ── R12 坏参数抛 ──
        bad12 = []
        for name, fn in [
            ("level 错", lambda: RP.report(level="huge")),
            ("period 对象", lambda: RP.report(period=object())),
            ("events:-1", lambda: RP.report(period="events:-1")),
            ("max_items=-1", lambda: RP.report(period="today", max_items=-1)),
        ]:
            try:
                fn()
                bad12.append((name, "没抛"))
            except ValueError as exc:
                print("  （R12 预期拒绝：%s ⇒ ValueError ✓）" % name)
            except Exception as exc:
                bad12.append((name, "抛了 %s" % type(exc).__name__))
        checks.append(("R12 坏参数 ⇒ ValueError", not bad12,
                       str(bad12[:2]) if bad12 else "4/4 都抛了"))

        # ── R13 确定性 ──
        r13a = RP.report(period="today", level="full", jobs_dir=jd2,
                         events_path=ev2, reasons_records=[], now=now)
        r13b = RP.report(period="today", level="full", jobs_dir=jd2,
                         events_path=ev2, reasons_records=[], now=now)
        checks.append(("R13 确定性：同输入两次汇报逐字相同",
                       r13a["text"] == r13b["text"]
                       and json.dumps(r13a["counts"], sort_keys=True)
                       == json.dumps(r13b["counts"], sort_keys=True),
                       "len=%d" % len(r13a["text"])))

        # ── R15 ★重要事件不丢（截断时先保重要）★ ──
        ev15 = base / "events15.json"
        for i in range(4):
            EM.append("verify", "普通校验 %d" % i, evidence="ev-n%d" % i,
                      when=now - 10 + i, path=ev15)
        EM.append("damage", "重要：被炸", evidence={"kind": "receipt",
                                               "ref": "damage src=mob"},
                  when=now - 1, path=ev15)
        rep15 = RP.report(period="today", level="full", jobs_dir=empty_jobs,
                          events_path=ev15, reasons_records=[], max_items=2, now=now)
        kinds15 = [it["kind"] for it in rep15["items"]]
        checks.append(("R15 ★重要事件不丢★（max_items 截断先保重要）",
                       len(rep15["items"]) <= 2
                       and rep15["counts"]["important_items"] >= 1
                       and any(it.get("kind") == "event:damage" and it.get("important")
                               for it in rep15["items"])
                       and any(a["kind"] == "items_truncated"
                               for a in rep15["anomalies"]),
                       "items=%s important=%d" % (kinds15,
                                                  rep15["counts"]["important_items"])))

        # ── R14 ★H 接线端到端★：做一件事 ⇒ 事件账本有它 ⇒ reporter 能汇报 ──
        jd14 = base / "jobs14"
        jd14.mkdir()
        ev14 = base / "events14.json"
        write_job(jd14, "j-e2e", "open", "去挖一块石头", next_="挖 (1,70,3)")
        import reasons as R
        old_logdir, old_index = R.LOGDIR, R.INDEX
        R.LOGDIR, R.INDEX = base / "reasons14", base / "reasons14_index.json"
        try:
            import primitives as P
            import verifier as V
            fake_dsh = FakeDsh()
            fake_ver = type("V", (), {
                "verify_dig": staticmethod(lambda pos: {"ok": True,
                                                       "why": "dig_verified"})})
            allow = type("N", (), {"allowed": staticmethod(lambda pos: (True, None))})
            pr = P.Primitives(dsh=fake_dsh, verifier=fake_ver, permit=allow,
                              log=True, events=str(ev14))
            r14 = pr.dig((1, 70, 3), mission="j-e2e")
            # 校验官那条路径也接：临时注册记录器（真实现由 primitives(log=True) 注）
            V.set_recorder(lambda kind, verdict, pos: EM.record(
                "verify" if verdict.get("ok") else "verify_fail", what=kind,
                evidence={"kind": "verifier",
                          "ref": "verify_dig ok=%s why=%s"
                                 % (verdict.get("ok"), verdict.get("why"))},
                where=pos, important=not verdict.get("ok"), path=str(ev14)))
            v14 = V.verify_dig((1, 70, 3), read=lambda pos: "")
            V.set_recorder(None)
        finally:
            R.LOGDIR, R.INDEX = old_logdir, old_index
            try:
                import reasons as _R2
                _R2.set_event_recorder(None)
            except Exception as exc:          # ★不许静默✗★
                print("  （R14 清理由记录器失败：%r）" % (exc,))
        write_job(jd14, "j-e2e", "done", "去挖一块石头",
                  evidence="SUMMARY task pass=1 fail=0 total=1")
        led14 = EM.load(ev14)
        ev_dig = [e for e in led14["events"] if e.get("kind") == "dig"]
        rep14 = RP.report(period="job:j-e2e", level="full", jobs_dir=jd14,
                          events_path=ev14, reasons_records=[], now=time.time())
        ev_items = [it for it in rep14["items"] if it["kind"].startswith("event:")]
        checks.append(("R14 ★H 接线端到端★：做一件事⇒事件账本有它⇒reporter 能汇报",
                       r14.get("ok") is True and len(ev_dig) == 1
                       and ev_dig[0]["evidence"].get("mission") == "j-e2e"
                       and "verify=" in str(ev_dig[0]["evidence"].get("ref"))
                       and v14.get("ok") is True
                       and any(it["kind"] == "event:dig" for it in ev_items)
                       and rep14["counts"]["jobs"] == 1
                       and rep14["counts"]["events"] >= 2
                       and "证据=" in rep14["text"]
                       and any(it["kind"] == "done" and it["evidence"]
                               for it in rep14["items"]),
                       "事件=%d 条目=%s counts=%s"
                       % (len(led14["events"]),
                          [it["kind"] for it in ev_items][:5],
                          rep14["counts"])))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:130]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => reporter 有红（%d 项不对）" % bad)
        print("REPORTER ok=0 bad=%d" % bad)
        return 1
    print("  => reporter 全绿（只引用证据／空账本如实／异常必报／分级／H 接线端到端）")
    print("REPORTER ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
