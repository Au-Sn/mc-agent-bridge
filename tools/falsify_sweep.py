#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/falsify_sweep.py -- ★反驳扫描（机制版）✗ "判据真的会红吗"（§79.324／§79.325）

★纪律✗★：★"★没有 oracle 不许宣布修好★"✗ ⇒ ★**判据**同理✗★：
  ★没被**注入故障**验过的判据 ✗ 你可能**不知道它会不会红** ✗ 它可能**永远绿**✗★ ✓
★★做法✗★★：★每一条 ✗ **照着它声明守护的那个点**造一个故障 ✗
  ★○ 先跑一次（应绿）✗ ○ 注入 ✗ ○ 再跑（**必须红**）✗ ○ **按原字节**还原 ✗ ○ 再跑（应绿）✗★ ✓
★为什么**不进闸门**✗★：★它会**改源码** ✗ 不能当闸门项（★已进 `gate_coverage` 的声明表✗★）✗★ ✓
用法✗★：`py tools/falsify_sweep.py`（★跑全部✗★）或 `--list`（★只列✗★）
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOOLS = ROOT / "tools"
STATE = ROOT / "state"
DOCS = ROOT / "docs"


def run(script, timeout=900):
    r = subprocess.run([sys.executable, "-B", "-X", "utf8", str(TOOLS / script)],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    tail = [l.strip() for l in ((r.stdout or "") + (r.stderr or "")).splitlines()
            if l.strip().startswith("=>")]
    return r.returncode, (tail[-1][:120] if tail else "")



def _snap(path):
    """★★§79.327✗★★：★**快照＋还原必须包含 mtime**✗★ ——
    ★"★按原字节还原★"只还原内容 ✗ 而 `generated_freshness` 看的是 **mtime**✗★ ⇒
    ★★还原之后闸门会莫名其妙红 ✗ 而 `git status` 又显示干净（★同一个坑我踩了一次✗★）✗★★ ✓
    ★返回一个**还原函数**✗★ ✓
    """
    p = pathlib.Path(path)
    orig = p.read_bytes()
    st = p.stat()

    def undo():
        p.write_bytes(orig)
        os.utime(p, (st.st_atime, st.st_mtime))
    return undo


class Case:
    """★一个故障：注入（返回还原函数）✗ 用哪个判据验✗ 期望红✗★"""

    def __init__(self, tag, judge, why, inject):
        self.tag, self.judge, self.why, self.inject = tag, judge, why, inject


# ★★六个故障 ✗ 每条都**照着判据声明守护的那个点**造✗★★
def _fake_judge_file():
    p = TOOLS / "_sweep_fake_judge.py"
    p.write_text('#!/usr/bin/env python3\n'
                 '# -*- coding: utf-8 -*-\n'
                 'print("=> sweep_fake %s" % ("PASS" if True else "FAIL"))\n'
                 'raise SystemExit(0)\n', encoding="utf-8")

    def undo():
        if p.exists():
            p.unlink()
    return undo


def _bad_contract_expect():
    p = STATE / "contracts" / "truth_v1.json"
    _undo = _snap(p)
    orig = p.read_bytes()
    d = json.loads(orig.decode("utf-8"))
    for it in d["items"]:
        if it["id"] == "slab_half":
            it["expect"] = 0.55
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return _undo


def _break_height_branch():
    p = TOOLS / "pathplan.py"
    _undo = _snap(p)
    orig = p.read_bytes()
    t = orig.decode("utf-8")
    old = "        h = height_of(block)\n        return h is not None and h <= STEP_MAX"
    new = "        h = height_of(block)\n        return True   # ★注入故障✗★"
    if old not in t:
        return None
    p.write_text(t.replace(old, new, 1), encoding="utf-8")
    return _undo


def _gate_two_tuple():
    p = TOOLS / "check_all.py"
    _undo = _snap(p)
    orig = p.read_bytes()
    t = orig.decode("utf-8")
    anchor = '    ("world_touch_test.py"'
    i = t.find(anchor)
    if i < 0:
        return None
    p.write_text(t[:i] + '    ("_sweep_two_tuple.py", "★注入故障：二元组✗★"),\n' + t[i:],
                 encoding="utf-8")
    return _undo


def _dod_wrong_number():
    p = DOCS / "DoD-对账表.md"
    _undo = _snap(p)
    orig = p.read_bytes()
    t = orig.decode("utf-8")
    if "未声明 0" not in t:
        return None
    p.write_text(t.replace("未声明 0", "未声明 5", 1), encoding="utf-8")
    return _undo


def _kb_policy_flip():
    # ★★§79.325 修✗★★：★原来**在进程内**改 `K.PHYS_LEVELS` ✗ 而判据跑在**子进程**✗★ ⇒
    #   ★注入**根本没生效**（★`F6` 坏时也 rc=0 ✗ 是**我的用例错了** ✗ 不是判据的问题✗★）✗★ ⇒
    #   ★★改成**改文件** ✗ 让子进程真的读到★✗★ ✓
    p = TOOLS / "blockkb.py"
    _undo = _snap(p)
    orig = p.read_bytes()
    t = orig.decode("utf-8")
    m = re.search(r'^PHYS_LEVELS = \([^\n]*\)\s*$', t, re.M)
    if not m:
        return None
    p.write_text(t[:m.start()] + 'PHYS_LEVELS = ("registry", "name_fallback")   # ★注入故障✗★'
                 + t[m.end():], encoding="utf-8")
    return _undo



def _drop_one_exception():
    """★F7✗★：★从例外表**删一条** ✗ "未声明"就变大 ✗ 而 U4 说"只许变小"⇒ 必须红✗★"""
    p = STATE / "exceptions.json"
    _undo = _snap(p)
    orig = p.read_bytes()
    d = json.loads(orig.decode("utf-8"))
    ents = d.get("entries")
    if not isinstance(ents, list) or not ents:
        return None
    d["entries"] = ents[:-1]          # ★少一条 ⇒ 一条件变成"未声明"✗★
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return _undo


def _debt_bad_row():
    """★F8✗★：★往 §79.14 的欠账表插一行**只有 2 格** ⇒ `D7` 必须红✗★"""
    p = DOCS / "当前阶段-状态与交接.md"
    _undo = _snap(p)
    orig = p.read_bytes()
    t = orig.decode("utf-8")
    lines = t.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if "★欠账表" in ln and "§79.14" in ln:
            lines.insert(i + 1, "| ★S7 注入行 | 只有两格 |\n")
            p.write_text("".join(lines), encoding="utf-8")
            return _undo
    return None



def _unpin_stdout():
    """★F9✗★：★删掉 `mcp_walk` 的 stdout pin ✗ 而它**会** print ⇒ `stdio_guard.S3` 必须红✗★"""
    p = TOOLS / "mcp_walk.py"
    _undo = _snap(p)
    t = p.read_text(encoding="utf-8")
    m = re.search(r"try:\n    sys\.stdout\.reconfigure\(encoding=\"utf-8\", errors=\"replace\"\)\n"
                  r"except Exception:\n    pass\n", t)
    if not m:
        return None
    p.write_text(t[:m.start()] + t[m.end():], encoding="utf-8")
    return _undo


def _touch_upstream():
    """★F10✗★：★把 `exceptions.json` 的 **mtime** 弄新（★内容不动✗★）⇒ `generated_freshness` 必须红✗★"""
    p = STATE / "exceptions.json"
    _undo = _snap(p)
    os.utime(p, None)          # ★只动时间 ✗ 不改内容✗★
    return _undo


CASES = [
    Case("F1", "gate_coverage_test.py", "★塞一个像判据但不在表里的文件 ✗ `C1` 必须红✗★",
         _fake_judge_file),
    Case("F2", "truth_contract_test.py", "★`slab_half` 的 `expect` 改错 ✗ `T4` 必须红✗★",
         _bad_contract_expect),
    Case("F3", "a3_wired_test.py", "★`is_auto_step` 的高度档永远 True ✗ `W1/W2/W6` 必须红✗★",
         _break_height_branch),
    Case("F4", "gate_tables_test.py", "★`GATE` 里塞一个二元组 ✗ `G1b` 必须红✗★",
         _gate_two_tuple),
    Case("F5", "generated_docs_test.py", "★DoD 表" + "「未声明 0」" + "改成 5 ✗ `G4` 必须红✗★",
         _dod_wrong_number),
    Case("F6", "evidence_ladder_test.py", "★把 `PHYS_LEVELS` 换成语义等级 ✗ 铁律①的梯子必须红✗★",
         _kb_policy_flip),
    Case("F7", "u1_declared_test.py", "★从例外表删一条 ⇒ 未声明变大 ✗ `U4`（只许变小）必须红✗★",
         _drop_one_exception),
    Case("F8", "debt_fresh_test.py", "★欠账表插一行 2 格 ✗ `D7`（每行正好 3 格）必须红✗★",
         _debt_bad_row),
    Case("F9", "stdio_guard_test.py", "★拆掉 `mcp_walk` 的 stdout pin ✗ `S3` 必须红✗★",
         _unpin_stdout),
    Case("F10", "generated_freshness_test.py", "★把上游 mtime 弄新 ✗ `N1~N3`（生成物不许比上游旧）必须红✗★",
         _touch_upstream),
]


def main(argv) -> int:
    if "--list" in argv:
        for c in CASES:
            print("  %-3s %-26s %s" % (c.tag, c.judge, c.why))
        return 0
    print("== falsify_sweep：★判据真的会红吗✗★ ==")
    ok = [True]
    proved = 0
    for c in CASES:
        before_rc, _ = run(c.judge)
        undo = None
        bad_rc, bad_tail = -1, ""
        try:
            undo = c.inject()
            if undo is None:
                print("  %-3s ★注入不了 ✗ 跳过（★锚点变了✗★）%s" % (c.tag, c.judge))
                ok[0] = False
                continue
            bad_rc, bad_tail = run(c.judge)
        finally:
            if undo:
                undo()
        after_rc, _ = run(c.judge)
        good = (before_rc == 0 and bad_rc != 0 and after_rc == 0)
        ok[0] &= good
        proved += 1 if good else 0
        print("  %-3s %s %-26s ★坏时 rc=%s（★应非 0✗★）✗ 还原 rc=%s（★应 0✗★）✗ %s"
              % (c.tag, "✓" if good else "不符合", c.judge, bad_rc, after_rc, bad_tail[:64]))
    print("")
    print("== 汇总：**%d／%d** 条判据被证明**真的会红** ==" % (proved, len(CASES)))
    print("=> falsify_sweep %s" % ("PASS ✓" if ok[0] else "FAIL"))
    print("FALSIFY ok=%d proved=%d total=%d" % (1 if ok[0] else 0, proved, len(CASES)))
    return 0 if ok[0] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
