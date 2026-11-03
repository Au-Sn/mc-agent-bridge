#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut.py -- 开切：把「哪一刀」落盘，并能应用／查状态／回滚（§79.217）

为什么有它（§79.217 查出来的差）：
  开关 CLASSIFIER_SOURCE 只从环境读（blockkb.py:53），而**没有任何**「测试环境配置」落盘，
  start_all.ps1 里也没有 => 所谓「开切」一直缺一个**落盘的切刀配置**。

三个子命令：
  apply <命名空间> [--why 为什么]   把这一刀写进 state/cut.json，并**当场实测**它改了多少
  status                            读 state/cut.json ＋ 现算这一刀现在改多少（数会漂，所以现算）
  rollback                          清空 state/cut.json（★整档回退 ✗ 一秒回到出厂✓）

口径：
  · 本脚本**不改任何数据**，只写一个配置文件 ＋ 打印要设的环境变量
  · 「应用」到运行环境的方式就是那两行环境变量（手册 §2 的写法）
  · 默认作用域**只含这一刀点名的命名空间** => 别处一个都不动（scope_test 守着这条）
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CFG = ROOT / "state" / "cut.json"
BAK = ROOT / "state" / "cut_history.json"


def load():
    if CFG.is_file():
        try:
            return json.loads(CFG.read_text(encoding="utf-8"))
        except Exception as e:
            # 记录：配置读坏 ⇒ 静默当成空配置（等于用错的默认值）
            print("[记录] 配置读不到（退回空配置）：%s: %s"
                  % (type(e).__name__, str(e)[:80]), file=sys.stderr)
            return {}
    return {}


def save(d, history=False):
    CFG.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if history:
        h = []
        if BAK.is_file():
            try:
                h = json.loads(BAK.read_text(encoding="utf-8"))
            except Exception:
                h = []
        h.append(d)
        BAK.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")


def measure(ns):
    """现算这一刀改多少：黑名单 vs 真开关（子进程，真路径）"""
    import kb_export as KX
    blocks = json.loads(KX.find_export("").read_text(encoding="utf-8")).get("blocks") or {}
    mine = sorted(sp for sp in blocks if sp.startswith(ns + ":"))
    CODE = (
        "import json,sys;"
        "sys.path.insert(0, r'" + str(ROOT / "tools") + "');"
        "import mapread as MR;"
        "sps=json.loads(sys.stdin.read());"
        "print(json.dumps({sp:[MR.is_floor(sp),MR.blocks_space(sp),MR.cat(sp)] for sp in sps},"
        "ensure_ascii=False))"
    )
    import os
    out = {}
    for tag, env in (("off", {"CLASSIFIER_SOURCE": "blacklist"}),
                     ("on", {"CLASSIFIER_SOURCE": "table+fallback",
                             "DSH_KB_SCOPE": ns})):
        e = dict(os.environ)
        e.pop("CLASSIFIER_SOURCE", None)
        e.pop("DSH_KB_SCOPE", None)
        e.update(env)
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", CODE], cwd=str(ROOT), env=e,
                           input=json.dumps(mine), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode or not (r.stdout or "").strip():
            print("  子进程挂了：%s" % (r.stderr or "").strip()[-160:])
            return None, None, None
        out[tag] = json.loads(r.stdout.strip().splitlines()[-1])
    chg = [sp for sp in mine if out["off"].get(sp) != out["on"].get(sp)]
    return len(mine), len(chg), chg


def cmd_apply(argv):
    if not argv:
        print("用法：cut.py apply <命名空间> [--why 为什么]")
        return 2
    ns = argv[0]
    why = "（没写为什么，补上）"
    if "--why" in argv:
        why = argv[argv.index("--why") + 1] if len(argv) > argv.index("--why") + 1 else why
    print("== 开切：%s ==" % ns)
    n, c, chg = measure(ns)
    if n is None:
        return 1
    print("   方块 %d 个，★实测会改 %d 个★" % (n, c))
    for sp in chg[:8]:
        print("      %s" % sp)
    d = load()
    d.setdefault("cuts", {})[ns] = {
        "source": "table+fallback",
        "why": why,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "measured_change": c,
        "measured_blocks": n,
    }
    d["scope"] = sorted(d.get("cuts") or {})
    d["note"] = "作用域只含点名的命名空间；整档回退 = cut.py rollback"
    save(d, history=True)
    print("")
    print("   写进 %s" % CFG.name)
    print("   应用到运行环境（两行）：")
    print("      $env:CLASSIFIER_SOURCE = 'table+fallback'")
    print("      $env:DSH_KB_SCOPE = '%s'" % ",".join(d["scope"]))
    print("   ★回滚✗★：cut.py rollback ／ 或把 CLASSIFIER_SOURCE 拨回 blacklist")
    return 0


def cmd_status(argv):
    d = load()
    cuts = d.get("cuts") or {}
    print("== 切刀状态 ==")
    if not cuts:
        print("   ★一个都没切★（%s 不存在或为空）" % CFG.name)
        print("   ⇒ CLASSIFIER_SOURCE 默认 blacklist ＝ 与迁移前逐字相同")
        return 0
    print("   作用域：%s" % ",".join(d.get("scope") or []))
    for ns, info in cuts.items():
        n, c, _chg = measure(ns)
        was = info.get("measured_change")
        print("   %-26s 切于 %s" % (ns, info.get("at")))
        print("      为什么：%s" % info.get("why"))
        print("      切时实测会改 %s ✗ ★现在现算 %s★（★数会漂 ✗ 以现算为准✓★）"
              % (was, c))
    return 0


def cmd_rollback(argv):
    d = load()
    if not (d.get("cuts")):
        print("本来就没切")
        return 0
    old = list(d["cuts"])
    save({"cuts": {}, "scope": [],
          "note": "★已整档回退 ✗ %s★" % datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
         history=True)
    print("== 整档回退 ==")
    print("   摘掉：%s" % ",".join(old))
    print("   运行环境回退：$env:CLASSIFIER_SOURCE = 'blacklist'（或删掉这个变量）")
    print("   ★表与导出一个字都没动✗★ —— 这正是三态可回滚那条设计的意思")
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    return {"apply": cmd_apply, "status": cmd_status,
            "rollback": cmd_rollback}.get(argv[0], lambda a: (print(__doc__), 0)[1])(argv[1:])


if __name__ == "__main__":
    # ★★2026-10-18（★复核 P2-8 ✗ §79.276✗★）✗★★：★`cut.py status` 原来**裸 traceback**
    #   （★`FileNotFoundError` ✗ 它要读的那份状态文件不在✓★）✗★ ⇒
    #   ★入口包一层 ✗ **只接"文件不在"** ✗ 别的异常照样响（★不许顺手全吞✗★）✗★ ✓
    try:
        sys.exit(main(sys.argv[1:]))
    except FileNotFoundError as _e:
        print("INCONCLUSIVE: %s" % _e)
        print("★这条命令要读**盘上的状态文件** ✗ 它不在 ⇒ 不是命令坏了✗★"
              "（★先跑一次导出／切换 ✗ 再看状态✓★）")
        sys.exit(4)
