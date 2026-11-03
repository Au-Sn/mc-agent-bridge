#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""a3_ab.py -- ★A3 那条的一键 A/B★（`AUTO_STEP_BY_HEIGHT` 开／关两臂）（§79.283）

★用户裁决 A3 的原话✗★：★"★寻路层接 max_height ✗ **先加开关 A/B 并行跑 ✗ 绿了再换默认**★"✗★ ✓
★为什么需要它✗★：★开关已经有了（★`pathplan.AUTO_STEP_BY_HEIGHT` ✗ 默认**关**✗★）✗★ ⇒
  ★但"★两臂到底**不一样**吗 ✗ 会不会两边都绿但**什么都没变**★"**从来没人量过**✗★ ✓
  ★★⇒ 这个工具只回答一件事✗★★：★★把开关翻过去 ✗ **判据的结论有没有变**✗ 差在哪✗★★ ✓
  ★（★两臂**完全一样** ⇒ 说明**没接上** ✗ 那是**红** ✗ 不是"★A/B 通过★"✗★）✗★ ✓

★它跑两臂✗★：
  · ★`pathplan_height_test`✗★（★离线 ✗ 秒级✗★）—— ★H1~H5 就是这条开关的判据✗★ ✓
  · ★`check_all --walk`✗★（★要世界 ✗ 加 `--with-walk` 才跑✗★）
★输出✗★：★人读的表 ＋ `logs/a3_ab.txt` 首行**纯 ASCII**（D3）✗ 退出码 0／4✗★ ✓
"""
from __future__ import annotations

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

TOOLS = ROOT / "tools"
ARMS = (("off", "0"), ("on", "1"))
JUDGES = ("pathplan_height_test.py",)


def run(args, env_extra=None, timeout=1200):
    e = dict(os.environ)
    if env_extra:
        e.update(env_extra)
    return subprocess.run([sys.executable, "-B", "-X", "utf8"] + [str(a) for a in args],
                          cwd=str(ROOT), env=e, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def line_of(out):
    return next((l.strip() for l in (out or "").splitlines()
                 if "=>" in l or l.startswith("SUMMARY ")), "")


def main(argv) -> int:
    with_walk = "--with-walk" in argv
    print("== a3_ab：`AUTO_STEP_BY_HEIGHT` 两臂 ==")
    # ★第 0 步：这条 A/B **要导出**（★没有高度 ✗ 开关就是个摆设✗★）✗★
    import export_guard as EG
    try:
        p = EG.require("a3_ab.py")
        print("   导出在：%s" % p.name)
    except Exception as e:
        print("   ★缺输入★：%s" % str(e)[:360])
        print("")
        print("   ★⇒ 这一步只能人做：开游戏 ⇒ 在游戏里跑 `/dshkb` ⇒ 再回来跑本脚本★")
        _write(["ok=0 export=missing"], False)
        return 4

    rows = {}
    for arm, val in ARMS:
        print("")
        print("── 臂 %s（★AUTO_STEP_BY_HEIGHT=%s✗★）──" % (arm, val))
        for j in JUDGES:
            r = run([TOOLS / j], {"AUTO_STEP_BY_HEIGHT": val})
            lt = line_of(r.stdout + r.stderr)
            rows[(arm, j)] = (r.returncode, lt)
            print("   %-26s rc=%-3s ｜ %s" % (j, r.returncode, lt[:78]))
        if with_walk:
            r = run([TOOLS / "check_all.py", "--walk"], {"AUTO_STEP_BY_HEIGHT": val})
            lt = line_of(r.stdout + r.stderr)
            rows[(arm, "walk")] = (r.returncode, lt)
            print("   %-26s rc=%-3s ｜ %s" % ("check_all --walk", r.returncode, lt[:78]))

    print("")
    print("── 两臂比一比（★这一节才是 A3 要的答案✗★）──")
    keys = sorted({k[1] for k in rows})
    diff, same = [], []
    for j in keys:
        a, b = rows.get(("off", j)), rows.get(("on", j))
        if not a or not b:
            continue
        if (a[0], a[1]) != (b[0], b[1]):
            diff.append(j)
            print("   ★变了✗★ %-26s 关：rc=%s %s" % (j, a[0], a[1][:52]))
            print("   %-30s 开：rc=%s %s" % ("", b[0], b[1][:52]))
        else:
            same.append(j)
            print("   没变   %-26s rc=%s" % (j, a[0]))
    print("")
    # ★★2026-10-18（★§79.304✗★）✗★★：★这个判法**错了**✗★ ——
    #   ★`pathplan_height_test` **自己内部**就把两臂都测了 ✗ 所以它两臂**都 PASS** ✗★ ⇒
    #   ★拿"★判据结论相同★"当"★没接上★"会**误报**✗★ ✓
    #   ★★正确判法✗★★：★交给 `a3_wired_test.py`（★拿"★名字与高度打架★"的方块 ✗
    #     两臂**行为**必然相反✗★）✗★ ⇒ ★这里只**转述**它的结论 ✗ 不再自己判✗★ ✓
    print("")
    print("★（★A3 的" + chr(12300) + "接没接上" + chr(12301) +
          "由 `a3_wired_test.py` 判 ✗ 它拿" + chr(12300) + "名字与高度打架" + chr(12301) +
          "的方块做两臂子进程 ✗ 那才是**行为**证据✗★）✗★")
    if not diff:
        print("★★两臂**判据结论一样**✗★★ ⇒ ★这不是" + chr(12300) + "没接上" + chr(12301) +
              "（★`pathplan_height_test` 内部就测了两臂✗★）✗ "
              "★请看 `a3_wired_test.py` 的 `diff`✗★")
        _write(["ok=0 same=%d" % len(same)] + ["%s=same" % j for j in same], False)
        return 1
    ok = all(rows[("off", j)][0] == 0 and rows[("on", j)][0] == 0 for j in diff)
    print("★两臂**有差异**（%d 条）✗ 而**两臂都绿**：%s✗★"
          % (len(diff), "✓" if ok else "★否 ✗ 有一臂红 ⇒ 先看它✗★"))
    print("★⇒ 下一步（★用户 A3 的口径✗★）：★两臂都绿 ⇒ 才谈" + "「" + "换默认" + "」"
          " ✗ 而且换之前要**再跑一遍全量**✗★")
    _write(["ok=%d diff=%d same=%d" % (1 if ok else 0, len(diff), len(same))]
           + ["%s=diff" % j for j in diff], ok)
    return 0 if ok else 1


def _write(extra, ok: bool):
    head = "A3AB %s" % " ".join(extra)
    out = ROOT / "logs" / "a3_ab.txt"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(head + chr(10), encoding="utf-8")
        print("")
        print("机器行（纯 ASCII）⇒ %s" % head[:130])
    except Exception as e:
        print("★写日志失败★：%s" % type(e).__name__)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
