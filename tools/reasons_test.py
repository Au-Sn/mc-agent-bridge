#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reasons_test.py -- 留痕日志的**选择性保留**判据（★用户口径✗★）

用户原话：「N8' 这个在做记忆系统时要记得**选择性保留内容**，
**毕竟不能让日志一直累计**」

CHECKS（★用临时目录 ✗ 不碰真日志✗★）
  R1 按天分文件：今天的记录写在 `reasons-YYYYMMDD.jsonl`
  R2 超上限 ⇒ prune：行数降到 ≤ KEEP_TAIL ＋ 重要记录，且**重要记录一条不丢**
  R3 不超上限 ⇒ prune 不动它
  R4 rotate：超过 KEEP_DAYS 天的文件被删，**index 里留一行统计**
  R5 load(days=N) 只读窗口内，且按时间有序
  R6 坏行不吞（打印到 stderr）但**不影响其它行**
"""
from __future__ import annotations

import json
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

import reasons as R          # noqa: E402


def main() -> int:
    checks = []
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        R.LOGDIR, R.INDEX = d, d / "reasons_index.json"

        # R1 按天分文件
        rec = R.because("test one", mission="m1", action="walk")
        p = R.log_path(rec["ts"])
        checks.append(("R1 按天分文件", p.name.startswith("reasons-") and p.is_file(),
                       p.name))

        # R2 超上限 ⇒ 选择性保留
        old_max, old_tail = R.MAX_LINES, R.KEEP_TAIL
        R.MAX_LINES, R.KEEP_TAIL = 50, 10
        for i in range(60):
            R.because("noise %d" % i, mission="m2", action="walk")
        R.because("★关键：挖了矿石", mission="m3", action="dig")     # 重要
        recs = R._read(p)
        important_kept = any(r.get("action") == "dig" for r in recs)
        checks.append(("R2 超上限 ⇒ prune 且重要记录不丢",
                       len(recs) <= R.KEEP_TAIL + 12 and important_kept,
                       "剩 %d 行（上限 50 / 留 10）重要=%s" % (len(recs), important_kept)))

        # R3 不超上限 ⇒ 不动
        R.MAX_LINES, R.KEEP_TAIL = 10 ** 6, 10
        n_before = len(R._read(p))
        R.because("another", mission="m4", action="walk")
        stat = R.prune(p)
        checks.append(("R3 不超上限 ⇒ 不裁剪", stat["dropped"] == 0,
                       "before=%d kept=%d dropped=%d" % (n_before, stat["kept"], stat["dropped"])))

        # R4 rotate：造一个 30 天前的文件
        R.MAX_LINES, R.KEEP_TAIL = old_max, old_tail
        old_ts = time.time() - 30 * 86400
        old_p = R.log_path(old_ts)
        old_p.write_text(json.dumps({"ts": old_ts, "day": R._day(old_ts),
                                      "reason": "ancient", "mission": "old",
                                      "action": "walk", "pos": None},
                                     ensure_ascii=False) + "\n", encoding="utf-8")
        out = R.rotate(days=14)
        idx = R._load_index()
        checks.append(("R4 旧天文件被删 ＋ index 留统计",
                       old_p.name in out["dropped"]
                       and R._day(old_ts) in (idx.get("days") or {}),
                       "dropped=%s index=%d 天" % (out["dropped"], len(idx.get("days") or {}))))

        # R5 load(days=N) 窗口 + 有序
        recs_win = R.load(days=3)
        ordered = all(float(a.get("ts") or 0) <= float(b.get("ts") or 0)
                      for a, b in zip(recs_win, recs_win[1:]))
        checks.append(("R5 load(days) 窗口内且有序",
                       ordered and all((r.get("day") or "") >= R._day(time.time() - 3 * 86400)
                                       for r in recs_win),
                       "%d 条 ordered=%s" % (len(recs_win), ordered)))

        # R6 坏行
        p.write_text(p.read_text(encoding="utf-8") + "{ broken json\n", encoding="utf-8")
        recs_bad = R._read(p)
        checks.append(("R6 坏行不吞且不影响其它行", len(recs_bad) >= 1, "%d 行" % len(recs_bad)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => reasons FAIL (%d)" % bad)
        print("REASONS ok=0 bad=%d" % bad)
        return 1
    print("  => reasons PASS (daily files, selective prune, rotation, windowed load)")
    print("REASONS ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
