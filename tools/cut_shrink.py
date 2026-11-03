#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut_shrink.py -- 黑名单萎缩：有多少物种现在靠导出回答（§79.219 离线）

口径（定义清楚，能重算）：
  一个物种「靠导出回答」== 把表关掉（CLASSIFIER_SOURCE=blacklist）它的三条签名会变。
  在 blacklist 档下这个数**恒为 0**（因为那时表本来就没参与）。
  切了一刀之后，被切命名空间里这个数 > 0 == 那些物种**不再靠名字黑名单**。

注意：这不等于「答案更真」。真不真要看世界（还没验）。
它只回答一件事：**承重墙从名字换到导出了多少**。
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import kb_export as KX
import export_guard as _EG  # B1：缺输入硬红＋一句人话

CODE = (
    "import json,sys;"
    "sys.path.insert(0, r'" + str(ROOT / "tools") + "');"
    "import mapread as MR, blockkb as KB;"
    "sps=json.loads(sys.stdin.read());"
    "out={'src':KB.SOURCE,"
    "'sig':{sp:[MR.is_floor(sp),MR.blocks_space(sp),MR.cat(sp)] for sp in sps}};"
    "print(json.dumps(out,ensure_ascii=False))"
)


def sig_of(sps, env):
    e = dict(os.environ)
    for k in ("CLASSIFIER_SOURCE", "DSH_KB_SCOPE"):
        e.pop(k, None)
    e.update(env)
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", CODE], cwd=str(ROOT), env=e,
                       input=json.dumps(sps), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode or not (r.stdout or "").strip():
        print("子进程挂了：%s" % (r.stderr or "").strip()[-200:])
        raise SystemExit(1)
    return json.loads(r.stdout.strip().splitlines()[-1])


# ★★2026-10-18（★复核 P2-8 ✗ §79.276✗★）✗★★：★同 `stage5_report` ✗ 缺输入 ⇒ 人话 ＋ rc 4✗★
try:
    blocks = json.loads(_EG.require("cut_shrink.py").read_text(encoding="utf-8")).get("blocks") or {}
except Exception as _e:
    print("INCONCLUSIVE: %s" % _e)
    print("★这条命令**要导出** ✗ 不是它坏了★ ⇒ 开游戏跑一次 `/dshkb` ✗ 再回来跑它 ✓")
    sys.exit(4)
cfg = {}
p = ROOT / "state" / "cut.json"
if p.is_file():
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
cuts = sorted(cfg.get("cuts") or {})
scope = ",".join(cuts) if cuts else None

print("== 黑名单萎缩（靠导出回答的物种数）==")
print("   落盘切刀：%s" % (scope or "（没有）"))
if not cuts:
    print("   没切 => 这个数恒为 0（表本来就没参与）")
    raise SystemExit(0)

tot_n = tot_dep = 0
for ns in cuts:
    mine = sorted(sp for sp in blocks if sp.startswith(ns + ":"))
    off = sig_of(mine, {"CLASSIFIER_SOURCE": "blacklist"})
    on = sig_of(mine, {"CLASSIFIER_SOURCE": "table+fallback", "DSH_KB_SCOPE": ns})
    dep = [sp for sp in mine if off["sig"][sp] != on["sig"][sp]]
    tot_n += len(mine)
    tot_dep += len(dep)
    print("   %-26s 方块 %5d ✗ 靠导出回答 **%d** ✗ 仍靠名字 %d"
          % (ns, len(mine), len(dep), len(mine) - len(dep)))
    for sp in dep[:5]:
        print("        %s : %s -> %s" % (sp, off["sig"][sp], on["sig"][sp]))
print("")
print("   合计：方块 %d ✗ ★靠导出 **%d** ✗ 仍靠名字 %d★"
      % (tot_n, tot_dep, tot_n - tot_dep))
print("   口径：这个数只说「承重墙换过去多少」，**不说**答案更真（真不真要看世界）")
print("   ★0 的含义✗★：两个来源在这个命名空间上**完全一致** ⇒ 开关拨过去答案不变 ✗ "
      "★承重墙也没换★（★这不代表切失败 ✗ 代表这一次是安全的彩排✓★）")
print("   ★真正的萎缩要从**两个来源不一致**的模组开始✗★（★挑刀表里 乙／丙 那两档✓★）")
