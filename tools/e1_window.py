#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e1_window.py -- E1 实机窗口的**一条命令**（§79.251 用户裁决 E1）

用户原话：探针排一次**专用实机窗口**：攒批重启 ＋ 用户领 ㉘(4103,69,20) ＋ 3 个真目标 ＋
世界侧判据，**一次做完**（别挂台账里等）。
★这份脚本的用处✗★：★把"★等游戏开着的时候要做的事★"**全部收进一条命令**✗ ——
  不然每次都靠现场想 ✗ 一定会漏（★§77 那种"★入口当天就过期★"就是这么来的✓★）✗★ ✓
★它按顺序做**能自动做的** ✗ 并把**只能人做的**印成清单✗★ ✓
★输出✗★：★人读的那半随便 ✗ 机器那半（★`logs/e1_window.txt` 首行✗★）是**纯 ASCII**✗★（D3 口径）✓
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★用户在 ㉘ 那个位置（★台账 §79.201 记的✓★）
E1_SPOT = (4103, 69, 20)
# ★三个"★已知可达★"的真目标（★要用户带着走一遍 ✗ 用来验探针说"★能到★"是不是真的✗★）
# ★★2026-10-18（★复核 P2-12a/b ✗ §79.279✗★）✗★★：★原来三个目标只有**名字** ✗
#   而机器键是 `name.split()[0]`✗★ ⇒ ★三个名字都以「㉘」开头 ⇒ **键全撞成 `probe_㉘`**✗★ ⇒
#   ★★而且那一行带着 U+3258 ✗ 与"★机器行纯 ASCII★"（D3）**自相矛盾**✗★★ ✓
#   ★修法✗★：★每个目标**自带一个 ASCII 键**✗（`key` ✗ `label` ✗ `pos`）✗★ ✓
E1_TARGETS = [
    ("orig", "㉘ 原位", (4103, 69, 20)),
    ("up1", "㉘ 上方一格", (4103, 70, 20)),
    ("east2", "㉘ 东向两格", (4105, 69, 20)),
]


def step(n, title):
    print("")
    print("── %d %s ──" % (n, title))


def main() -> int:
    import export_guard as EG
    ascii_lines = []
    step(1, "导出在不在（★没有就先开游戏跑 /dshkb✗★）")
    try:
        p = EG.require("e1_window.py")
        print("   导出在：%s（%.1f KB）" % (p.name, p.stat().st_size / 1024.0))
        ascii_lines.append("export=present")
    except Exception as e:
        print("   ★缺输入✗★：%s" % str(e)[:400])
        print("")
        print("   ★⇒ 这一步只能人做✗★：★开游戏 ⇒ 在游戏里跑 `/dshkb` ⇒ 再回来跑本脚本★")
        ascii_lines.append("export=missing")
        _write(ascii_lines, ok=False)
        return 4

    step(2, "落成**版本化快照**（★B1① ✗ 免得再被环境吃掉✗★）")
    r = subprocess_capture([sys.executable, "-X", "utf8", str(ROOT / "tools" / "kb_snapshot.py"),
                            "save"])
    print("   %s" % r.strip()[:300])
    ascii_lines.append("snapshot=%s" % ("done" if "保存" in r or "快照" in r or "save" in r.lower()
                                        else "unknown"))

    step(3, "导出围栏：第一次跑就**记账**（★B1② ✗ 以后导出动过会点名✗★）")
    r = subprocess_capture([sys.executable, "-X", "utf8", str(ROOT / "tools" / "mod_contract.py"),
                            "--export-fence", "--record"])
    print("   %s" % r.strip()[:300])

    step(4, "★只能人做的✗★：真值契约里**还没实测**的那几条（★这就是 E1 的清单✗★）")
    import json
    truth = json.loads((ROOT / "state" / "contracts" / "truth_v1.json").read_text(encoding="utf-8"))
    todo = [i for i in truth.get("items", []) if i.get("status") != "measured"]
    print("   待实测 **%d** 条：" % len(todo))
    for i in todo:
        print("     · %-24s %s" % (i.get("id"), str(i.get("what"))[:56]))
        print("       怎么量：%s" % str(i.get("how_to_measure"))[:96])
    ascii_lines.append("truth_unmeasured=%d" % len(todo))

    step(5, "★只能人做的✗★：先站到这三个点上（★探针会照着它们说「能不能到」✗★）")
    for _k, name, pos in E1_TARGETS:
        print("     · %-12s %s" % (name, pos))

    step(6, "自动那一半：对那三个点跑可达探针（★要世界 ✗ 现在就能跑✗★）")
    import reach_probe as RP
    for _k, name, pos in E1_TARGETS:
        try:
            d = RP.reach_probe(E1_SPOT, pos, timeout_ms=20000)
            print("     %-12s ⇒ reachable=%s why_not=%s"
                  % (name, d.get("reachable"), d.get("why_not")))
            ascii_lines.append("probe_%s=%s" % (_k, d.get("reachable")))
        except Exception as e:
            print("     %-12s ⇒ ★探针自己炸了✗★：%s" % (name, type(e).__name__))
            ascii_lines.append("probe_%s=error" % _k)

    step(7, "世界侧判据（★攒批跑 ✗ 一次跑完✗★）")
    print("   跑：py tools/check_all.py --walk（★WALK 那 3 条 ✗ 要世界✗★）")
    print("   跑完把 SUMMARY 行贴回台账 ✗ 并把真值契约里量到的数写进去（★删 `unmeasured` ✗ 改 `measured`✓★）")
    _write(ascii_lines, ok=True)
    return 0


def subprocess_capture(args):
    import subprocess
    try:
        r = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return "★跑不动✗★：%s" % type(e).__name__


def _write(lines, ok: bool):
    head = "E1WINDOW ok=%d %s" % (1 if ok else 0, " ".join(lines))
    out = ROOT / "logs" / "e1_window.txt"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(head + chr(10), encoding="utf-8")
        print("")
        print("机器行（★纯 ASCII ✗ D3✗★）⇒ %s" % head[:110])
    except Exception as e:
        print("★写日志失败✗★：%s" % type(e).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
