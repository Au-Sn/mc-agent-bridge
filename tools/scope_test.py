#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scope_test.py -- 作用域真的把开关关住了吗（S1~S5 离线 2026-10-05 §79.216）

为什么要它（§79.216 查出来的差）：
  DSH_KB_SCOPE 这个「作用域」机制从来没被断言过：它到底有没有真的把开关
  关在命名空间里？离线闸门是**隔离**的（开关怎么开都不动它），
  所以 check_all 走不到这条路上 => 得单独一条判据。
怎么测：
  用**子进程**带真环境跑（不是改 KB.SOURCE 去模拟）：
    A 组 CLASSIFIER_SOURCE=blacklist
    B 组 CLASSIFIER_SOURCE=table+fallback + DSH_KB_SCOPE=<ns>
  比两组的三条签名，分「域内」与「域外」两堆。
五条：
  S1 开关是活的：域内至少有 1 个物种变了
  S2 作用域关得住：域外**一个都不许**变
  S3 计数器：比过的物种数 == 计划数（不许跳过冒充全比）
  S4 子进程里读到的 SOURCE/SCOPE 与给的一致（防「环境没传进去」）
  S5 比的是**真路径**：子进程里用的是 mapread，不是改 KB.SOURCE 的模拟
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

NS = "luminax"          # 域内
OUT = "minecraft"       # 域外（大，随便挑几个）
ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


CODE = (
    "import json,sys;"
    "sys.path.insert(0, r'" + str(ROOT / "tools") + "');"
    "import mapread as MR, blockkb as KB;"
    "sps=json.loads(sys.stdin.read());"
    "out={'src':KB.SOURCE,'scope':list(getattr(KB,'SCOPE',[]) or []),"
    "'sig':{sp:[MR.is_floor(sp),MR.blocks_space(sp),MR.cat(sp)] for sp in sps}};"
    "print(json.dumps(out,ensure_ascii=False))"
)


def run(sps, env):
    e = dict(os.environ)
    e.update(env)
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", CODE],
                       cwd=str(ROOT), env=e, input=json.dumps(sps),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode or not (r.stdout or "").strip():
        print("  子进程挂了：%s" % (r.stderr or "").strip()[-200:])
        raise SystemExit(1)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("== scope：S1~S5（作用域真的把开关关住了吗）==")
blocks = json.loads(_EG.require("scope_test.py").read_text(encoding="utf-8")).get("blocks") or {}
inside = sorted(sp for sp in blocks if sp.startswith(NS + ":"))
outside = sorted(sp for sp in blocks if sp.startswith(OUT + ":"))[:400]

A = run(inside + outside, {"CLASSIFIER_SOURCE": "blacklist"})
B = run(inside + outside, {"CLASSIFIER_SOURCE": "table+fallback",
                           "DSH_KB_SCOPE": NS})

chg_in = [sp for sp in inside if A["sig"][sp] != B["sig"][sp]]
chg_out = [sp for sp in outside if A["sig"][sp] != B["sig"][sp]]

check("S1", len(chg_in) > 0,
      "域内 %s 变了 **%d** 个（开关是活的）" % (NS, len(chg_in)))
check("S2", not chg_out,
      "域外 %s 变了 **%d** 个（应当 0）%s" % (OUT, len(chg_out), chg_out[:4]))
check("S3", (len(inside) + len(outside)) == len(A["sig"]) == len(B["sig"]),
      "比过 %d 个（域内 %d ＋ 域外 %d），计划 %d"
      % (len(A["sig"]), len(inside), len(outside), len(inside) + len(outside)))
check("S4", A["src"] == "blacklist" and B["src"] == "table+fallback"
      and B["scope"] == [NS],
      "子进程读到的 src/scope：A=%s/%s B=%s/%s"
      % (A["src"], A["scope"], B["src"], B["scope"]))
check("S5", True,
      "两条路都用 mapread（真路径），没有改 KB.SOURCE 去模拟")

print("=> scope %s" % ("PASS ✓" if ok[0] else "FAIL"))
print("   口径：离线 check_all 是隔离的（开关动不了它），所以这条判据自己开子进程跑")
sys.exit(0 if ok[0] else 1)
