#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_arrived.py -- ★导出回来的**一条命令**★（§79.266）

★为什么有它★：`state/u1_account.json` 里写着那 **624** 条决策级分歧"★卡在导出★"——
★它们的判定是"★挡人 True⇒False★"这类**物理主张**，按 R7 证据**只能是 `collision`**，
而 `collision` 只在导出里 ⇒ **拿标签写就是违反铁律①**。
★⇒ 导出一回来，这些活要**按顺序**做完 ✗ 现场想一定会漏（§79.251 同一条教训）★ ✓

★它按顺序做★：
  1 查导出在不在（不在就印 `export_guard` 那句人话 + 退出码 4）
  2 落**版本化快照**（B1①）+ 导出围栏**首次记账**（B1②）
  3 ★补那 624 条物理声明★（走 `declare_collision.py` ✗ 它自己有三条纪律：
    只写碰撞槽 / 导出没覆盖的不猜 / 导出说 canopy 就拒）
  4 重跑关键判据（u1_declared / evidence_ladder / cut_verify / kb_policy / conflict_rule）
  5 印 **A2**（`family_consistency`）与 **B4**（收益刀候选）怎么跑
  6 机器行写 `logs/export_arrived.txt` 首行（纯 ASCII ✗ D3）

★退出码★：0 ＝ 全做完；4 ＝ **有东西没拿到**（不是通过 ✗ 也不是坏）
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOOLS = ROOT / "tools"


def run(args, timeout=900):
    r = subprocess.run([sys.executable, "-B", "-X", "utf8"] + [str(a) for a in args],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def flags_of(tool: str):
    """★从工具源码里探出它的开关（★不写死 ✗ 免得它改名就失效★）"""
    p = TOOLS / tool
    if not p.is_file():
        return []
    txt = p.read_text(encoding="utf-8", errors="replace")
    return sorted(set(re.findall(r'add_argument\(\s*"(--[A-Za-z0-9_-]+)"', txt)))


def step(n, title):
    print("")
    print("── %s %s ──" % (n, title))   # ★2026-10-18: 4.5 步传的是字符串 => 用 %s（改了就要重跑预演, 我这次正是这么栽的）


def main() -> int:
    lines, missing = [], []
    print("== export_arrived：导出回来之后的一条命令 ==")

    step(1, "导出在不在")
    import export_guard as EG
    try:
        p = EG.require("export_arrived.py")
        print("   导出在：%s（%.1f KB）" % (p.name, p.stat().st_size / 1024.0))
        lines.append("export=present")
    except Exception as e:
        print("   ★缺输入★：%s" % str(e)[:400])
        print("")
        print("   ★⇒ 这一步只能人做：开游戏 ⇒ 游戏里跑 `/dshkb` ⇒ 再回来跑本脚本★")
        _write(["export=missing"], ok=False)
        return 4

    # ★★2026-10-18（★复核 P2-12e ✗ §79.279✗★）✗★★：★第 2/3 步原来**只印 rc 不判**✗★ ⇒
    #   ★★"★导出回来后的一条命令★"会对失败说"★完成★"✗★★ ⇒ ★收集失败 ✗ 最后进机器行✗★ ✓
    step_bad = []
    step(2, "落版本化快照（B1①）+ 围栏首次记账（B1②）")
    for tool, args in (("kb_snapshot.py", ["save"]),
                       ("mod_contract.py", ["--export-fence", "--record"])):
        rc, out = run([TOOLS / tool] + args)
        print("   %-20s rc=%s ｜ %s" % (tool, rc, out.splitlines()[-1][:80] if out else ""))
        if rc != 0:
            step_bad.append((tool, rc))

    step(3, "★补那 624 条物理声明★（`declare_collision.py`）")
    fl = flags_of("declare_collision.py")
    print("   它的开关：%s" % (fl or "（★没探到✗★）"))
    write_flag = next((f for f in ("--apply", "--write", "--commit", "--yes") if f in fl), None)
    rc, out = run([TOOLS / "declare_collision.py"])
    print("   ★计划（不写盘）★ rc=%s" % rc)
    for l in out.splitlines()[-8:]:
        print("     %s" % l[:110])
    if write_flag:
        print("   ★要真的写 ✗ 就再加 `%s`（★本脚本不替你写 ✗ 先看计划✓★）" % write_flag)
    else:
        print("   ★它的写法开关没探到 ✗ 看它的用法再决定（★不替你猜✗★）")

    step(4, "重跑关键判据（★这时候那 5 条环境红应当变绿★）")
    for j in ("u1_declared_test.py", "evidence_ladder_test.py", "cut_verify_test.py",
              "kb_policy_test.py", "conflict_rule_test.py"):
        rc, out = run([TOOLS / j], timeout=600)
        tail = next((l.strip() for l in out.splitlines() if "=>" in l), "")
        print("   %-26s rc=%s ｜ %s" % (j, rc, tail[:70]))
        if rc != 0:
            missing.append(j)

    # ★★2026-10-18（★§79.282 ✗ 复核 P2-4✗★）✗★★：★`分歧清单`／`迁移准备度` **过期**✗★
    #   （★`generated_freshness_test` 的 N1／N2 就是撞这个✗★）⇒ ★它们**要导出才能重生成**✗★ ⇒
    #   ★★导出回来这条链上必须**带上它们**✗ 不然 N1／N2 永远红✗★★ ✓
    step("4.5", "重生成那两份过期生成物（★`divergence.py` ✗ 它同时写两份✗★）")
    for args2, tag2 in (([], "分歧清单"), (["--by-namespace"], "迁移准备度")):
        rc, out = run([TOOLS / "divergence.py"] + args2, timeout=900)
        print("   %-14s rc=%s ｜ %s" % (tag2, rc,
                                        (out.strip().splitlines() or [""])[-1][:76]))
        if rc != 0:
            step_bad.append(("divergence.py " + tag2, rc))
    rc, out = run([TOOLS / "generated_freshness_test.py"], timeout=300)
    print("   %-14s rc=%s ｜ %s" % ("freshness", rc, (out.strip().splitlines() or [""])[-1][:70]))

    step(5, "另两件（★A2 ✗ B4✗★）怎么跑")
    print("   A2（★㊲ 重跑 family_consistency ✗ 先报数再定阈值★）：")
    print("      py -u -X utf8 tools\\family_consistency.py    （★有导出才有分母★）")
    print("   B4（★收益刀候选✗★）：")
    print("      py -u -X utf8 tools\\switch_plan.py          （★风险图 ✗ 挑「先切」的★）")
    print("      py -u -X utf8 tools\\cut_measure.py          （★切过去会改多少决策★）")

    # ★★2026-10-18（★§79.279 收尾✗★）✗★★：★`step_bad` 原来**只收集不报**✗★ ⇒
    #   ★★那就是"★改了但没接上★"✗★★ ⇒ ★第 2/3 步失败仍会说"★完成★"✗★ ✓
    rc = 0 if (not missing and not step_bad) else 4
    if missing:
        print("")
        print("★还没绿的：%s（★它们要导出**和**世界 ✗ 别当成坏✗★）" % missing)
    if step_bad:
        print("")
        print("★★第 2/3 步有失败✗★★：%s（★这些是"+"「"+"落快照／记账"+"」"+
              " ✗ 失败会**静默**让后面白跑✓★）" % step_bad)
    _write(lines + ["missing=%d" % len(missing), "step_bad=%d" % len(step_bad)],
           ok=(rc == 0))
    return rc


def _write(extra, ok: bool):
    head = "EXPORTARRIVED ok=%d %s" % (1 if ok else 0, " ".join(extra))
    out = ROOT / "logs" / "export_arrived.txt"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(head + chr(10), encoding="utf-8")
        print("")
        print("机器行（纯 ASCII）⇒ %s" % head[:120])
    except Exception as e:
        print("★写日志失败★：%s" % type(e).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
