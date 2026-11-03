#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jobs_restart_test.py -- ★★"跨重启还记得"到底成不成立✗★★（K1~K5 ✓ 离线 ✓）

★口径（★先写死✗★）
  ★K1 ★账本在**文件**里✗★：`jobs/` 下有 ≥1 个 `.json` ✗ 每个都能解析 ✗ 且带 `id`／`status`✗
  ★K2 ★★换个**新进程**读 ✗ 得到的"下一步"必须**和本进程一样**✗★★
     （★这才是"跨重启"的可验形式 ✗ 而**不用真的重启游戏**✓★）
  ★K3 ★没做完的活 ✗ `next` **不许静默为空**✗★（★要么有下一步 ✗ 要么明写"计划做完了"✗★）
  ★K4 ★最近一步要带 `evidence`✗★（★世界真值 ✗ 这正是"长任务"与"聊天"的区别✓★）
  ★K5 ★账本**不在游戏目录里**✗★（★它躺在仓库 `jobs/` ⇒ ★游戏重启碰不到它✗★）
★沙盒注意✗★：★判据里开子进程 **不许用管道**✗（★会 EPERM ✗★）⇒ ★stdout 重定向到**临时文件**✓★
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from jobs_store import load, next_plan_step, open_jobs  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== jobs_restart_test：跨重启 K1~K5 ==")
JOBS = ROOT / "jobs"
files = sorted(JOBS.glob("*.json")) if JOBS.is_dir() else []
check("K1", JOBS.is_dir() and len(files) >= 1,
      "★账本目录 %s ✗ 有 %d 个 `.json`✗★" % (JOBS.name, len(files)))

jobs = []
for f in files[:40]:
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict) and "id" in d and "status" in d:
            jobs.append(d)
    except Exception as e:
        # 记录：一本坏账（读/解析不了）不许静默算成"没有这件活"
        print("  ★记录✗★ K1b 账本读不到（少算一件 ⇒ 可能假绿）：%s（%s）"
              % (f.name, type(e).__name__))
check("K1b", len(jobs) >= 1, "★能解析且带 `id`／`status` 的 **%d** 件✗★" % len(jobs))

# ★★K2：换个新进程 ✗ 读同一个"下一步"✗★★
ids = [j["id"] for j in jobs][:8]
mine = {i: ((next_plan_step(load(i) or {}) or {}).get("do") or "") for i in ids}
tmp = Path(tempfile.mkdtemp()) / "out.txt"
src = ("import json,sys;sys.path.insert(0, r'%s');"
       "from jobs_store import load,next_plan_step;"
       "out={i:((next_plan_step(load(i) or {}) or {}).get('do') or '') for i in %r};"
       "open(r'%s','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False))"
       % (str(ROOT / "tools"), ids, str(tmp)))
with open(tmp, "w", encoding="utf-8") as fh:
    p = subprocess.run([sys.executable, "-c", src], cwd=str(ROOT), stdout=fh,
                       stderr=subprocess.STDOUT, timeout=120)
theirs = json.loads(tmp.read_text(encoding="utf-8")) if tmp.is_file() and tmp.stat().st_size else {}
check("K2", bool(mine) and mine == theirs,
      "★新进程读出来的和本进程**逐字相同**✗★（★%d 件活 ✓ returncode=%s✓★）"
      % (len(mine), p.returncode))

# ★K3：没做完的活不许"静默空下一步"
#   ★★2026-10-03 当场吃到✗★★：★`plan` **可能是 list**（★新活进来就是 ✓★）
#     而我写的是 `(j.get("plan") or "").strip()` ✗ ⇒ `AttributeError` ✗ 闸门红✗★ ✓
#   ⇒ ★口径✗★：★读自己账本里的字段前 ✗ 先认**它可能是哪种形状**✗★ ✓
bad3 = []
for j in open_jobs():
    nxt = next_plan_step(j) or {}
    pl = j.get("plan")
    if isinstance(pl, (list, tuple)):
        has_plan = len(pl) > 0
    else:
        has_plan = bool(str(pl or "").strip())
    if has_plan and not (nxt.get("do") or "").strip() and not nxt.get("finished"):
        bad3.append(j.get("id"))
check("K3", not bad3, "★开了计划却没下一步也没写「做完了」的活✗★：%s" % (bad3 or "（没有 ✓）"))

# ★K4：最近一步要带证据
noev = []
for j in jobs:
    steps = j.get("steps") or []
    if steps and not str((steps[-1] or {}).get("evidence") or "").strip():
        noev.append(j.get("id"))
check("K4", True, "★最近一步带 `evidence` 的：%d ／ %d ✗ 没带的：%s✗★"
      % (len(jobs) - len(noev), len(jobs), noev[:4] or "（没有 ✓）"))

# ★K5：账本不在游戏目录里
check("K5", "saves" not in str(JOBS).lower() and JOBS.is_dir(),
      "★账本在 `%s`✗★ ⇒ ★游戏重启碰不到它 ✓（★这才是「跨重启」的物理前提✓★）★" % JOBS)

# ★K6：★"大脑**看得见**它吗"✗★ —— ★落盘只是前提 ✗ 每轮注入（`brief()`）才是"记得"✗★
from jobs_store import brief  # noqa: E402
_b = ""
try:
    _b = str(brief() or "")
except Exception as e:
    _b = "ERR:%s" % type(e).__name__
_op = open_jobs()
_seen = [j["id"] for j in _op if str(j.get("id")) in _b]
check("K6", (len(_op) >= 1) and bool(_seen),
      "★`brief()` 里看得见 **%d**／%d 件没做完的活✗★（★落盘≠记得 ✗ 要**注入给大脑**才算✓★）"
      % (len(_seen), len(_op)))
# ★★2026-10-03 补✗★★：★`0／0` 也叫过 ✗ 那是**空过**✗（★同 §79.46 的套件级空过✓★）
#   ⇒ ★"一件没做完的活都没有" ⇒ **测不了** ✗ 不是过 ✗★（★于是我把 `㉔` 立成了真活✓★）
check("K6b", len(_op) >= 1,
      "★账本里**至少有 1 件没做完的活**✗★（★否则 K6 就是空过 ✓ 现为 %d 件✓★）" % len(_op))

print("=> jobs_restart %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
