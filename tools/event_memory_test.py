#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""event_memory_test.py -- 模块 H 事件记忆的离线判据（★不需要游戏 ✗ 临时状态文件✗★）

规格 §2.8 / §21 / §16 M6：「记不住发生过什么」＋「选择性保留 ✗ 别让日志无限累计」。

CHECKS
  H1  写入→读回：kind/what/where/objects/day 逐字一致（事件层）
  H2  证据指针：事件 → 哪个 job／哪条回执，检索结果原样带得回来
  H3  跨进程读回：子进程写 ⇒ 父进程读（★重启门✗★）
  H4  ★选择性保留：上限到了也只丢"不重要"的，重要事件一条不丢★
  H5  容量上限：全局上限与每天上限都真的封住（★不许无限累计✗★）
  H6  按天保留：太老的非重要事件删，但跨天统计（days）不丢
  H7  ★坏文件必须抛★（JSON 坏／schema 不对／events 不是列表／事件缺字段）
  H8  ★空/坏数据不冒充★（空 kind／空指针／重要事件没证据／时间窗倒置／未知天不编造）
  H9  时间窗过滤（time_window／since／until；边界含）
  H10 地点过滤（精确／半径；没 where 的事件不算命中）
  H11 重要度过滤（important=True／importance=normal）
  H12 事实层：由事件推导计数／最后位置／重要项（★没事件就没事实✗★）
  H13 某天小结：分类计数／重要项带证据／首末时间／追加总数
  H14 校验失败 ⇒ 文件不变（★不许写半条✗★）＋ 原子写不留 tmp
  H15 CLI：--append／--stats 能跨进程对本文件操作
  H16 检索 limit／kind 列表；recent(n) 边界（n=0 ⇒ 空表不返回全部）
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

import event_memory as EM          # noqa: E402


def _sub(args) -> str:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "event_memory.py")] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT), env=env, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("subprocess 失败 rc=%d out=%r err=%r"
                           % (r.returncode, (r.stdout or "")[-300:], (r.stderr or "")[-300:]))
    return r.stdout or ""


def main() -> int:
    checks = []
    now = time.time()                  # ★保留策略按时钟裁旧事件 ⇒ 判据里的"现在"必须真实✗★
    with tempfile.TemporaryDirectory() as td:
        st = pathlib.Path(td) / "event_memory.json"

        # ── H1 写入→读回 ──
        t0 = now - 60
        e1 = EM.append("dig", "挖了 3 个铁矿石", evidence={"kind": "receipt", "ref": "dshdig 4100 70 5"},
                       when=t0, where=(4100, 70, 5), objects=["iron_ore"], path=st)
        rows = EM.recent(5, path=st)
        r = rows[-1] if rows else {}
        checks.append(("H1 写入→读回逐字一致",
                       r.get("kind") == "dig" and r.get("what") == "挖了 3 个铁矿石"
                       and r.get("where") == [4100, 70, 5]
                       and r.get("objects") == [{"id": "iron_ore"}]
                       and r.get("day") == EM.day_of(t0) and r.get("id") == e1["id"],
                       "kind=%r where=%r objects=%r" % (r.get("kind"), r.get("where"),
                                                        r.get("objects"))))

        # ── H2 证据指针 ──
        EM.append("place", "把箱子放在屋里", evidence={"kind": "job", "id": "j1102-abc"},
                  when=t0 + 1, where=(4120, 71, 20), path=st)
        q2 = EM.query(kind="place", path=st)
        ev2 = (q2[-1].get("evidence") or {}) if q2 else {}
        checks.append(("H2 证据指针：事件 → job／回执，检索带回来",
                       ev2.get("kind") == "job" and ev2.get("ref") == "j1102-abc",
                       str(ev2)[:90]))

        # ── H3 跨进程读回（重启门）──
        out3 = _sub(["--state", str(st), "--recent", "5"])
        back = json.loads(out3)
        checks.append(("H3 ★跨进程读回★（子进程写 ⇒ 父进程读）",
                       len(back) >= 2 and any(x.get("kind") == "place" for x in back),
                       "%d 条 ｜ kinds=%s" % (len(back), sorted({x.get("kind") for x in back}))))

        # ── H4 选择性保留：重要不丢 ──
        st4 = pathlib.Path(td) / "retention.json"
        old = (EM.MAX_EVENTS, EM.MAX_PER_DAY, EM.KEEP_DAYS)
        try:
            EM.MAX_EVENTS, EM.MAX_PER_DAY = 12, 6
            for i in range(30):
                EM.append("walk", "走了一段", evidence="step-%d" % i,
                          when=t0 + i, path=st4)
            EM.append("dig", "重要：挖掉一块", evidence="dshdig 1 2 3", when=t0 + 40, path=st4)
            EM.append("damage", "重要：被苦力怕炸", evidence={"kind": "receipt",
                                                       "ref": "damage src=creeper"},
                      when=t0 + 41, path=st4)
            EM.append("fail", "重要：任务失败", evidence={"kind": "job", "id": "j-bad"},
                      when=t0 + 42, path=st4)
            led4 = EM.load(st4)
        finally:
            EM.MAX_EVENTS, EM.MAX_PER_DAY, EM.KEEP_DAYS = old
        kinds4 = [e.get("kind") for e in led4["events"]]
        imp4 = [e for e in led4["events"] if e.get("important")]
        walk4 = [e for e in led4["events"] if e.get("kind") == "walk"]
        checks.append(("H4 ★重要不丢：上限内只裁不重要★",
                       len([e for e in imp4]) == 3
                       and {"dig", "damage", "fail"} <= set(kinds4)
                       and len(walk4) <= 6 and len(led4["events"]) <= 12,
                       "总 %d ｜ 重要 %d ｜ walk %d"
                       % (len(led4["events"]), len(imp4), len(walk4))))

        # ── H5 容量上限（纯 prune：多天 ＋ 全局/每天两条规则）──
        now5 = time.time()
        ev5 = []
        for d in range(3):
            for i in range(10):
                ev5.append({"id": "n%02d%02d" % (d, i), "ts": now5 - 3600 + d * 60 + i,
                            "day": EM.day_of(now5 - 3600 + d * 60 + i), "kind": "walk",
                            "what": "", "where": None, "objects": [],
                            "evidence": None, "important": False, "importance": "normal"})
        ev5.append({"id": "imp1", "ts": now5 - 3601, "day": EM.day_of(now5 - 3601),
                    "kind": "dig", "what": "重要", "where": None, "objects": [],
                    "evidence": {"kind": "receipt", "ref": "x"},
                    "important": True, "importance": "high"})
        led5 = {"schema": EM.SCHEMA, "seq": 32, "events": ev5,
                "days": {EM.day_of(now5 - 3600): {"n": 10, "first": now5 - 3600,
                                                  "last": now5 - 3540, "kept": 10}},
                "saved_at": None}
        st5 = EM.prune(led5, now=now5, max_events=6, max_per_day=100, keep_days=14)
        ids5 = {e["id"] for e in led5["events"]}
        checks.append(("H5 容量上限：全局 6 条 ＋ 重要必留",
                       len(led5["events"]) == 6 and "imp1" in ids5
                       and "n0209" in ids5 and "n0000" not in ids5,
                       "prune=%s ｜ 剩 %d" % (st5, len(led5["events"]))))

        # ── H6 按天保留：旧的非重要删、days 统计不丢 ──
        old_day_ts = now5 - 20 * 86400
        led6 = {"schema": EM.SCHEMA, "seq": 3,
                "events": [
                    {"id": "old1", "ts": old_day_ts, "day": EM.day_of(old_day_ts),
                     "kind": "walk", "what": "", "where": None, "objects": [],
                     "evidence": None, "important": False, "importance": "normal"},
                    {"id": "old2", "ts": old_day_ts + 5, "day": EM.day_of(old_day_ts),
                     "kind": "walk", "what": "", "where": None, "objects": [],
                     "evidence": None, "important": False, "importance": "normal"},
                    {"id": "keep1", "ts": now5, "day": EM.day_of(now5),
                     "kind": "walk", "what": "", "where": None, "objects": [],
                     "evidence": None, "important": False, "importance": "normal"}],
                "days": {EM.day_of(old_day_ts): {"n": 2, "first": old_day_ts,
                                                 "last": old_day_ts + 5, "kept": 2}},
                "saved_at": None}
        st6 = EM.prune(led6, now=now5, max_events=100, max_per_day=100, keep_days=14)
        d6 = led6["days"][EM.day_of(old_day_ts)]
        checks.append(("H6 按天保留：旧内容删除、跨天统计仍在",
                       st6["by_rule"]["age"] == 2 and len(led6["events"]) == 1
                       and d6.get("n") == 2 and d6.get("kept") == 0,
                       "stats=%s ｜ 旧天 index=%s" % (st6, d6)))

        # ── H7 坏文件必须抛（四类坏法）──
        bad7 = []
        p7 = pathlib.Path(td) / "bad7.json"
        cases = [
            ("{bad json", "坏 JSON"),
            (json.dumps({"schema": "other/schema@9", "events": [], "days": {}}), "schema 不对"),
            (json.dumps({"schema": EM.SCHEMA, "events": "nope", "days": {}}), "events 不是列表"),
            (json.dumps({"schema": EM.SCHEMA, "events": [{"id": "e1", "kind": "dig"}],
                         "days": {}}), "事件缺 ts/day"),
        ]
        for raw, why in cases:
            p7.write_text(raw, encoding="utf-8")
            try:
                EM.load(p7)
                bad7.append((why, "没抛"))
            except EM.EventMemoryError as exc:
                print("  （H7 预期抛错：%s ⇒ EventMemoryError ✓）" % why)
            except Exception as exc:            # 抛错类型也必须对
                bad7.append((why, "抛了 %s" % type(exc).__name__))
        checks.append(("H7 ★坏文件必须抛 EventMemoryError★（四类坏法）",
                       not bad7, str(bad7[:3]) if bad7 else "4/4 都抛了"))

        # ── H8 空/坏数据不冒充 ──
        st8 = pathlib.Path(td) / "guard.json"
        bad8 = []
        for name, fn in [
            ("空 kind", lambda: EM.append("", "x", path=st8)),
            ("空证据指针", lambda: EM.append("walk", "x", evidence={}, path=st8)),
            ("重要事件没证据", lambda: EM.append("dig", "x", path=st8)),
            ("where 形状错", lambda: EM.append("walk", "x", evidence="r", where=(1, 2), path=st8)),
            ("objects 空串", lambda: EM.append("walk", "x", evidence="r", objects=[""], path=st8)),
            ("时间窗倒置", lambda: EM.query(time_window=(100.0, 50.0), path=st8)),
            ("重要性取值错", lambda: EM.query(importance="???", path=st8)),
        ]:
            try:
                fn()
                bad8.append((name, "没报错"))
            except (ValueError, EM.EventMemoryError) as exc:
                print("  （H8 预期拒绝：%s ⇒ %s ✓）" % (name, type(exc).__name__))
            except Exception as exc:
                bad8.append((name, "抛了 %s" % type(exc).__name__))
        unknown_s = EM.summarize("19990101", path=st8)
        unknown_f = EM.facts("19990101", path=st8)
        checks.append(("H8 ★空/坏数据不冒充★（7 类校验 ＋ 未知天不编造）",
                       not bad8 and unknown_s["events"] == 0 and unknown_s["known_day"] is False
                       and unknown_s["facts"] == [] and unknown_f["has_data"] is False
                       and unknown_f["facts"] == [],
                       str(bad8[:3]) if bad8 else "7/7 全报 ＋ 未知天空表"))

        # ── H9 时间窗过滤 ──
        st9 = pathlib.Path(td) / "window.json"
        a = EM.append("walk", "早", evidence="r1", when=now + 1, path=st9)
        b = EM.append("walk", "中", evidence="r2", when=now + 2, path=st9)
        c = EM.append("walk", "晚", evidence="r3", when=now + 3, path=st9)
        ids = lambda rows: sorted(x["id"] for x in rows)
        w1 = EM.query(time_window=(b["ts"], c["ts"]), path=st9)
        w2 = EM.query(since=b["ts"], until=b["ts"], path=st9)   # ★边界含✗★
        w3 = EM.since(c["ts"], path=st9)
        checks.append(("H9 时间窗过滤（含边界）",
                       ids(w1) == sorted([b["id"], c["id"]])
                       and ids(w2) == [b["id"]] and ids(w3) == [c["id"]],
                       "窗=%d since=%d tail=%d" % (len(w1), len(w2), len(w3))))

        # ── H10 地点过滤 ──
        st10 = pathlib.Path(td) / "place.json"
        EM.append("dig", "近", evidence="r", when=now + 10, where=(100, 70, 5), path=st10)
        EM.append("dig", "远", evidence="r", when=now + 11, where=(103, 70, 5), path=st10)
        EM.append("dig", "没坐标", evidence="r", when=now + 12, path=st10)
        exact = EM.query(place=(100, 70, 5), radius=0, path=st10)
        near3 = EM.query(place=(100, 70, 5), radius=3, path=st10)
        checks.append(("H10 地点过滤（精确 1 ／ 半径 3 ⇒ 2）",
                       len(exact) == 1 and exact[0]["what"] == "近" and len(near3) == 2,
                       "exact=%d radius3=%d" % (len(exact), len(near3))))

        # ── H11 重要度过滤 ──
        st11 = pathlib.Path(td) / "imp.json"
        EM.append("walk", "普通", evidence="r", when=now + 20, path=st11)
        EM.append("damage", "重要", evidence={"kind": "receipt", "ref": "src=mob"},
                  when=now + 21, path=st11)
        hi = EM.query(important=True, path=st11)
        lo = EM.query(importance="normal", path=st11)
        checks.append(("H11 重要度过滤（high 1 ／ normal 1）",
                       len(hi) == 1 and hi[0]["kind"] == "damage"
                       and len(lo) == 1 and lo[0]["kind"] == "walk",
                       "high=%d normal=%d" % (len(hi), len(lo))))

        # ── H12 事实层 ──
        st12 = pathlib.Path(td) / "facts.json"
        d12 = EM.day_of(now + 30)
        EM.append("dig", "挖 1", evidence="r1", when=now + 30, where=(10, 71, 10), path=st12)
        EM.append("dig", "挖 2", evidence="r2", when=now + 31, where=(11, 71, 10), path=st12)
        EM.append("fail", "失败", evidence={"kind": "job", "id": "j12"},
                  when=now + 32, path=st12)
        f12 = EM.facts(d12, path=st12)
        facts12 = {(x.get("fact"), x.get("kind"), x.get("n")) for x in f12["facts"]}
        lw12 = [x for x in f12["facts"] if x.get("fact") == "last_where"]
        checks.append(("H12 事实层：计数／最后位置／重要项都由事件推导",
                       f12["has_data"] and ("count", "dig", 2) in facts12
                       and any(x.get("kind") == "dig" and x.get("where") == [11, 71, 10]
                               for x in lw12)
                       and any(x.get("fact") == "important_count" and x.get("n") == 3
                               for x in f12["facts"]),
                       "facts=%d ｜ last_where=%s" % (len(f12["facts"]), lw12)))

        # ── H13 某天小结 ──
        s13 = EM.summarize(d12, path=st12)
        first_ok = abs(float(s13["first_ts"] or 0) - (now + 30)) < 1e-2
        last_ok = abs(float(s13["last_ts"] or 0) - (now + 32)) < 1e-2
        checks.append(("H13 小结：分类计数／重要项带证据／首末时间",
                       s13["events"] == 3 and s13["by_kind"] == {"dig": 2, "fail": 1}
                       and len(s13["important"]) == 3
                       and any(x["evidence"].get("ref") == "j12" for x in s13["important"])
                       and first_ok and last_ok
                       and s13["appended"] == 3 and s13["known_day"] is True,
                       "by_kind=%s appended=%s first_ok=%s" % (s13["by_kind"],
                                                              s13["appended"], first_ok)))

        # ── H14 校验失败 ⇒ 文件不变 ＋ 原子写不留 tmp ──
        st14 = pathlib.Path(td) / "atomic.json"
        EM.append("walk", "先记一条", evidence="r", when=now + 40, path=st14)
        before14 = len(EM.load(st14)["events"])
        try:
            EM.append("dig", "没证据的重要事件", path=st14)
        except ValueError as exc:
            print("  （H14 预期拒绝：重要事件没证据 ⇒ ValueError ✓）")
        after14 = len(EM.load(st14)["events"])
        tmps = list(pathlib.Path(td).glob("atomic.json*"))
        checks.append(("H14 校验失败 ⇒ 文件不变 ＋ 原子写不留 tmp",
                       before14 == after14 == 1 and tmps == [st14],
                       "before=%d after=%d ｜ 目录=%s"
                       % (before14, after14, [p.name for p in tmps])))

        # ── H15 CLI 跨进程 append／stats ──
        st15 = pathlib.Path(td) / "cli.json"
        spec = json.dumps({"kind": "walk", "what": "cli-write",
                           "evidence": {"kind": "receipt", "ref": "cli-ref"},
                           "when": now + 50}, ensure_ascii=False)
        _sub(["--state", str(st15), "--append", spec])
        stats15 = json.loads(_sub(["--state", str(st15), "--stats"]))
        rows15 = json.loads(_sub(["--state", str(st15), "--recent", "3"]))
        checks.append(("H15 CLI 跨进程 append／stats／recent",
                       stats15.get("events") == 1 and len(rows15) == 1
                       and (rows15[0].get("evidence") or {}).get("ref") == "cli-ref",
                       "events=%s recent=%d" % (stats15.get("events"), len(rows15))))

        # ── H16 检索 limit／kind 列表 ＋ recent(n) 边界 ──
        st16 = pathlib.Path(td) / "limit.json"
        for i in range(5):
            EM.append("walk" if i % 2 == 0 else "dig", "第%d条" % i,
                      evidence="r%d" % i, when=now + 60 + i, path=st16)
        last2 = EM.query(kind=["walk"], limit=2, path=st16)
        back2 = EM.query(limit=2, path=st16)
        checks.append(("H16 limit／kind 列表 ＋ recent(0) 空表",
                       len(last2) == 2 and last2[-1]["what"] == "第4条"
                       and [x["what"] for x in back2] == ["第3条", "第4条"]
                       and EM.recent(0, path=st16) == [],
                       "walk-last2=%s tail2=%s" % ([x["what"] for x in last2],
                                                   [x["what"] for x in back2])))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:120]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => event_memory 有红（%d 项不对）" % bad)
        print("EVENTMEMORY ok=0 bad=%d" % bad)
        return 1
    print("  => event_memory 全绿（★事件→事实→检索 ✗ 选择性保留 ✗ 坏文件必抛✗★）")
    print("EVENTMEMORY ok=1 checks=%d important_kinds=%d"
          % (len(checks), len(EM.IMPORTANT_KINDS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
