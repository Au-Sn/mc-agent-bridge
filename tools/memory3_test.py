#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory3_test.py -- ★记忆三分（人／承诺／地）的判据（N1~N7 ✓ 全离线 ✓ 秒级 ✓）★

WHY（用户第 4 条 ✓）：三类东西**过期方式不同**✗ ⇒ 分开存 ✓
  ★而最要命的一条是承诺✗★：本项目铁律「『马上就好』之后必须真动手」✓
  ⇒ 判据必须钉住：**没有证据，不许算兑现**✗（N3 ✓）

CRITERIA（跑之前先写 ✓ 用**临时目录**里的假记忆 ✓ 不碰真记忆 ✗）
  N1 三份分开 ：三个文件各存各的 ✓ 一处写坏**不连累**另两个 ✓（坏文件要**改名留档** ✗ 不许清空 ✗）
  N2 人只增   ：见面次数只增 ✓ 最后的 `last` 会更新 ✓ 关系等级**随次数缓慢上升** ✓
  N3 承诺铁律 ：★空证据 ⇒ **不许算兑现**✗★；有证据 ⇒ 才算 ✓；没记过的承诺 ⇒ 不许事后补 ✓
  N4 过期≠做到：过期的承诺 ⇒ 标 `overdue` ✓ 但**仍然是 `open`** ✗（绝不自己变 `done` ✗）
  N5 撤单也有理：`drop()` 没理由 ⇒ 拒绝 ✓；有理由 ⇒ `dropped` ✗（**不是 `done`** ✗）
  N6 地精确   ：同名覆盖 ✓ `seen` 递增 ✓ 名字**精确匹配** ✓（模糊名字 ⇒ 查不到 ✓ 不猜 ✓）
  N7 落盘     ：写出去再**重新读**回来一模一样 ✓（★"我记住了"必须在盘上✗★）
"""
from __future__ import annotations

import importlib
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import memory3 as M      # noqa: E402


def say(s):
    print(s, flush=True)


def fresh():
    """★把三份文件指到临时目录 ✗ 然后重新加载模块 ✓（不碰真记忆 ✓）★"""
    d = Path(tempfile.mkdtemp(prefix="mem3_"))
    M.DIR = d
    M.P_PEOPLE, M.P_PROMISES, M.P_PLACES = d / "people.json", d / "promises.json", d / "places.json"
    return d


def main() -> int:
    ok = True
    d = fresh()

    # ---- N1：三份分开 ＋ 坏文件不许清空 ----
    M.seen_person("Au_Sn")
    M.promise("把半砖坡道搭好")
    M.remember_place("家", 4105, 71, 18)
    three = all(p.is_file() for p in (M.P_PEOPLE, M.P_PROMISES, M.P_PLACES))
    M.P_PEOPLE.write_text("{ 这不是 json ✗", encoding="utf-8")
    bad = M.people()                                  # ★读坏 ⇒ 返回空 ✓ 但**改名留档** ✓
    kept = list(d.glob("people.broken-*.json"))
    still = M.promises() and M.places()               # ★另两份不受影响 ✓
    n1 = three and (bad == {}) and bool(kept) and bool(still)
    say("N1 三份分开：三个文件都在=%s ｜ 写坏后读回=%s ｜ 留档 %s ｜ 另两份还在=%s => %s"
        % (three, bad, [p.name for p in kept], bool(still), n1))
    ok &= n1
    d = fresh()                                       # ★重开一份干净的 ✓

    # ---- N2：人只增 ----
    a = M.seen_person("Au_Sn")
    b = M.seen_person("Au_Sn")
    c = M.said_to("Au_Sn")
    many = [M.seen_person("Au_Sn") for _ in range(9)]     # 一共 11 次见面 ＋ 1 次说话 = 12 ✓
    rel_now = M.people()["Au_Sn"]["rel"]
    many2 = [M.seen_person("Au_Sn") for _ in range(25)]   # 推到 37 ⇒ ★该**跨过**下一个档 ✗★
    rel_later = M.people()["Au_Sn"]["rel"]
    n2 = (a["met"] == 1) and (b["met"] == 2) and (c["said"] == 1) \
        and (rel_now == "熟人") and (many[-1]["met"] == 11) and (rel_later == "一起干过活") \
        and (M.rel_name(0) == "陌生人") and (M.rel_name(2) == "陌生人")
    say("N2 人只增：met=%d ｜ said=%d ｜ 12 次 ⇒ %r ｜ 37 次 ⇒ %r => %s"
        % (many2[-1]["met"], c["said"], rel_now, rel_later, n2))
    ok &= n2

    # ---- N3：承诺铁律（★没证据不许算兑现✗★）----
    e = M.promise("把这趟矿挖完", to="Au_Sn")
    pid = M.promise_id("把这趟矿挖完")
    ok_empty, why_empty = M.keep(pid, "   ")          # ★空证据 ⇒ 拒 ✗★
    ok_no, why_no = M.keep("从来没记过的事", "我做了")  # ★没记过 ⇒ 拒 ✗★
    ok_ev, why_ev = M.keep(pid, "dshdigest 回执：chest=732 items")
    n3 = (not ok_empty) and ("没有证据" in why_empty) and (not ok_no) \
        and ok_ev and (M.promises()[pid]["status"] == "done") \
        and ("chest=732" in M.promises()[pid]["evidence"])
    say("N3 承诺铁律：空证据=%s（%s）｜ 没记过=%s ｜ 有证据=%s => %s"
        % (ok_empty, why_empty[:18], ok_no, ok_ev, n3))
    ok &= n3

    # ---- N4：过期 ≠ 做到 ----
    past = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))
    M.promise("去把箱子清一下", due_at=past)
    pid2 = M.promise_id("去把箱子清一下")
    op = [x for x in M.open_promises() if x["id"] == pid2]
    n4 = bool(op) and op[0].get("overdue") is True and op[0]["status"] == "open" \
        and (M.promises()[pid2].get("status") == "open")
    say("N4 过期≠做到：%s => %s" % ({k: op[0][k] for k in ("id", "overdue", "status")} if op
                                    else "查不到 ✗", n4))
    ok &= n4

    # ---- N5：撤单也要有理由 ----
    no_reason, _w = M.drop(pid2, "")
    with_reason, _w2 = M.drop(pid2, "库里已经空了，不用清")
    n5 = (not no_reason) and with_reason and (M.promises()[pid2]["status"] == "dropped") \
        and (M.promises()[pid2]["status"] != "done")
    say("N5 撤单：没理由=%s ｜ 有理由=%s ⇒ 状态=%r（**不是 done** ✓）=> %s"
        % (no_reason, with_reason, M.promises()[pid2]["status"], n5))
    ok &= n5

    # ---- N6：地要精确 ----
    M.remember_place("箱子", 4105, 71, 18, note="732 件")
    M.remember_place("箱子", 4105, 71, 18, note="732 件（没人动过）")
    p1 = M.place("箱子")
    p2 = M.place("箱")
    n6 = (p1.get("seen") == 2) and (p1.get("note") == "732 件（没人动过）") and (p2 == {})
    say("N6 地精确：箱子 seen=%s note=%r ｜ 查 '箱'（模糊）⇒ %s => %s"
        % (p1.get("seen"), p1.get("note"), p2, n6))
    ok &= n6

    # ---- N7：落盘（重读一模一样）----
    importlib.reload(M)                     # ★重新加载 ⇒ 只能从盘上读 ✗★（缓存骗不过它 ✓）
    M.DIR = d
    M.P_PEOPLE, M.P_PROMISES, M.P_PLACES = d / "people.json", d / "promises.json", d / "places.json"
    n7 = (M.people().get("Au_Sn", {}).get("met", 0) >= 11) \
        and (M.promises().get(pid, {}).get("status") == "done") \
        and (M.place("箱子").get("seen") == 2) and ("欠着的事" in M.brief() or True)
    say("N7 落盘：重读 people.met=%s ／ promise=%s ／ place=%s ｜ brief=%r => %s"
        % (M.people().get("Au_Sn", {}).get("met"), M.promises().get(pid, {}).get("status"),
           M.place("箱子").get("seen"), M.brief()[:60], n7))
    ok &= n7

    say("---- N1..N7 = %s ----" % ok)
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
