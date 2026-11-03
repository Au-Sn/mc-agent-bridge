#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_species.py -- ★单种可回退✗★（任务书阶段 4 的最后一件 ✓ 2026-10-04）

★它干什么✗★
  · ★`show <物种>`✗★：★这个物种**今天谁说它什么** —— 模型（★名字那条老路✓★）／
    碰撞槽（★表✓★）／语义槽（★标签✓★）三处一次看全 ✗ 并标出"★切换后会听谁的★"✗★ ✓
  · ★`drop <物种> [--claim …]`✗★：★把**这一条**从例外表里摘掉✗★ ⇒ ★下一次它就回落到
    `table+fallback` 的老路（★单种可回退✓★）✗ 而且**留痕**到 `logs/kb_rollback.log`✗★ ✓

★★两条纪律✗★★
  ① ★回退**必须留痕**✗★（★谁 ✗ 什么时候 ✗ 退了什么 ✗ 为什么 ✓★）——
     ★"★可回退★"如果**没有痕迹** ✗ 那它和"★悄悄改掉★"没法区分✗★ ✓
  ② ★`drop` 只动**例外表**✗★ ✗ ★不许去改导出 ✓ 也不许改判定代码✗★ ✓
     （★导出是**观测** ✗ 不是配置 ✓ 观测不许被"★退掉★"✗★）
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOG = ROOT / "logs" / "kb_rollback.log"


def show(species: str) -> int:
    """★三处一次看全✗★"""
    import blockkb as KB
    import mapread as MR
    KB.SOURCE = "table"
    KB.load_all()
    model = MR.shape(species)
    phys = KB.PHYS.get(species)
    sem = KB.TABLE.get(species)
    print("== %s ==" % species)
    print("  模型（★名字那条老路✗★）        ：%s" % model)
    print("  碰撞槽（★物理真值✓★）        ：%s" % (("%s（★%s✗★ 来源 %s）"
          % (phys["fam"], phys["level"], str(phys.get("src"))[:48])) if phys else "★没有✗★"))
    print("  语义槽（★标签 ✗ 只影响归属✓★）：%s" % (("%s（★%s✗★）" % (sem["fam"], sem["level"]))
          if sem else "★没有✗★"))
    for mode in ("blacklist", "table", "table+fallback"):
        KB.SOURCE = mode
        print("  ★%s★ 档下：is_floor=%-5s blocks_space=%-5s"
              % (mode, MR.is_floor(species), MR.blocks_space(species)))
    KB.SOURCE = "table+fallback"
    return 0


def drop(species: str, claim: str = "", why: str = "", store=None, log=None) -> int:
    """★摘掉**这一条**✗★（★回退 ⇒ 下次回落老路✓★）＋ 留痕"""
    import exception_table as ET
    # ★★默认参数陷阱✗★★：★`ET.load(path=STORE)` 的默认值在**函数定义时**就绑定了✗★ ⇒
    #   ★改 `ET.STORE` 对已定义的函数**无效** ✗ 所以我这里**调用时**取一次✗★ ✓
    store = pathlib.Path(store) if store else ET.STORE
    log = pathlib.Path(log) if log else LOG
    entries = ET.load(store)
    hit = [e for e in entries if e.get("species") == species
           and (not claim or e.get("claim") == claim)]
    if not hit:
        print("★表里没有 %s%s ⇒ 什么都没退 ✗（它本来就走回落✓★）"
              % (species, ("（★claim=%s✗★）" % claim) if claim else ""))
        return 2
    keep = [e for e in entries if e not in hit]
    store.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    store.write_text(_json.dumps({"schema": "dshbridge/exceptions@1", "entries": keep},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write("%s\t%s\tclaims=%s\twhy=%s\n"
                % (time.strftime("%Y-%m-%d %H:%M:%S"), species,
                   "／".join(e.get("claim", "?") for e in hit), why or "（★没写理由✗★）"))
    print("★已退✗★ %s 的 %d 条（%s）⇒ 表里现在 %d 条 ｜ 留痕 %s"
          % (species, len(hit), "／".join(e.get("claim", "?") for e in hit), len(keep), log.name))
    print("  ★下一次它就走 `table+fallback` 的回落（★老路✓★）✗ 而回落会写在 `declared` 里✗★ ✓")
    print("  已重生成 %s ✓" % ET.render().name)
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("show", "drop"))
    ap.add_argument("species")
    ap.add_argument("--claim", default="")
    ap.add_argument("--why", default="")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        return show(a.species)
    return drop(a.species, a.claim, a.why)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
