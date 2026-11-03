#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory_test.py -- 模块 L6 记忆官的判据（★离线 ✗ 临时状态文件✗★）

规格 §2.8 / §21：
  * ★持久化：重启后**逐字读回**✗★
  * ★**选择性保留**：每类封顶 ✗ 超了丢最旧（★不许无限累计✗★）✗
  * ★地标用**分类**认（★有方块实体 ⇒ 可交互✗★）✗ 不认名字✗★

CHECKS
  M1 put/get 往返（同名覆盖 ⇒ 位置更新）
  M2 ★持久化：换一个实例（重新读盘）逐字读回★
  M3 near() 按切比雪夫距离筛 ＋ 排序
  M4 forget() 删掉
  M5 ★封顶：塞 100 条只留 cap 个 ✗ 且留的是**最新**的★
  M6 ★分类认地标：有方块实体的 ⇒ interactable ✗ 普通石头 ⇒ 空★
  M7 未知类别 ⇒ 报错（★不许悄悄写进别的类✗★）
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import memory as M          # noqa: E402


def main() -> int:
    checks = []
    with tempfile.TemporaryDirectory() as td:
        st = Path(td) / "landmarks.json"

        # M1 put/get ＋ 同名覆盖
        M.put("home", "家", (4115, 71, 19), path=st)
        M.put("home", "家", (4116, 71, 19), path=st)
        r = M.get("home", "家", path=st)
        checks.append(("M1 put/get ＋ 同名覆盖（位置更新）",
                       r and r["pos"] == [4116, 71, 19], str(r.get("pos") if r else None)))

        # M2 持久化（重新读盘）
        raw = json.loads(st.read_text(encoding="utf-8"))
        again = M.get("home", "家", path=st)
        checks.append(("M2 持久化：读盘后逐字一致",
                       raw["kinds"]["home"][0]["pos"] == again["pos"], str(again["pos"])))

        # M3 near
        for i in range(5):
            M.put("chest", "箱%d" % i, (4100 + i * 10, 71, 5), path=st)
        near = M.near("chest", (4100, 71, 5), radius=12, path=st)
        checks.append(("M3 near 按切比雪夫距离筛＋排序",
                       len(near) >= 2 and near[0]["name"] == "箱0"
                       and all(n["dist"] <= 12 for n in near),
                       "%d 个 最近=%s" % (len(near), near[0]["name"] if near else "-")))

        # M4 forget
        M.forget("chest", "箱0", path=st)
        checks.append(("M4 forget 删掉", M.get("chest", "箱0", path=st) is None,
                       str(M.get("chest", "箱0", path=st))))

        # M5 封顶 ＋ 留最新
        cap = M.CAP["chest"]
        for i in range(100):
            M.put("chest", "批量%d" % i, (4000 + i, 71, 0), path=st)
            time.sleep(0.001)
        arr = M.all_of("chest", path=st)
        newest = arr[-1]["name"] if arr else ""
        checks.append(("M5 ★封顶：%d 条只留 %d ✗ 且留最新★" % (100, cap),
                       len(arr) <= cap and newest == "批量99",
                       "剩 %d 条 ｜ 最新=%s" % (len(arr), newest)))

        # M6 分类认地标
        k_machine = M.landmark_kind("minecraft:furnace")
        k_stone = M.landmark_kind("minecraft:stone")
        checks.append(("M6 ★分类认地标（熔炉⇒interactable ✗ 石头⇒空）★",
                       k_machine == "interactable" and k_stone == "",
                       "%r / %r" % (k_machine, k_stone)))

        # M7 未知类别要报错
        try:
            M.put("does_not_exist", "x", (0, 0, 0), path=st)
            ok7 = False
        except ValueError:
            ok7 = True
        checks.append(("M7 未知类别 ⇒ 报错", ok7, "ValueError" if ok7 else "没报错"))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => memory FAIL (%d)" % bad)
        print("MEMORY ok=0 bad=%d" % bad)
        return 1
    print("  => memory PASS (persisted, capped selectively, landmarks identified by classification)")
    print("MEMORY ok=1 checks=%d kinds=%d" % (len(checks), len(M.KINDS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
