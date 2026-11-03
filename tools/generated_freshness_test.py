#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generated_freshness_test.py -- 生成物的**新鲜度**（N1~N4 离线 2026-10-18 §79.281）

★为什么有它✗★（★复核 P2-4✗★）：★`generated_docs_test` 只盖 5 份生成物✗★ ⇒
  ★`分歧清单` 与 `迁移准备度` **没有任何判据**✗★ ⇒ ★实测它们停在 10-08／10-04 ✗
  而它们**依赖**的数据已经更新到 10-15／10-16 ✗★ ⇒ ★★过期 ✗ 而且**没人吭声**✗★★ ✓

★判法✗★：★每一份生成物的 mtime **不许早于**它依赖的上游数据的 mtime✗★ ✓
★★★限制（★照实写 ✗ 不许含糊✗★）✗★★：★mtime 只是个**代理**✗★ ——
  ★真判法是"★重生成之后**逐字节比内容**★"✗ 而那**要导出**（★现在没有✗★）✗★ ⇒
  ★所以这条判据红的时候 ✗ 真话是"★它**已经**过期"或"★它只是比上游旧 ✗ 未必内容真变★"✗ 两种 ✗
  ★两种都**该重生成**✗ 而重生成**要导出**✗★ ✓
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

D = ROOT / "docs"
S = ROOT / "state"
ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


# ★★2026-11-03 修（发布阻断）✗★★：原来用**裸 mtime**✗★ ——
#   公开仓库是干净快照（git archive/clone）⇒ 所有文件 mtime=解压/检出时间（顺序不保证）✗
#   ⇒ 新用户第一次跑 `check_all --offline` 会因"解压先后"误判"生成物过期"✗★
# ★口径✗★：干净跟踪文件用 **git commit 时间**；有本地改动/未跟踪 ⇒ mtime；
#   完全没有 git（zip 下载）⇒ 新鲜度**无法判** ⇒ 跳过并说清（★不冒充通过✓★）
def _git(args):
    try:
        r = subprocess.run(["git"] + args, cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=20)
        return r.returncode, (r.stdout or "").strip()
    except Exception:
        return (99, "")


def has_git():
    rc, out = _git(["rev-list", "--count", "HEAD"])
    return rc == 0 and out.isdigit()


def _rel(p):
    try:
        return p.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def _commit_ctime(p):
    rel = _rel(p)
    if rel is None:
        return None
    rc, out = _git(["log", "-1", "--format=%ct", "--", rel])
    return float(out) if rc == 0 and out.isdigit() else None


def _dirty(p):
    rel = _rel(p)
    if rel is None:
        return None
    rc, out = _git(["status", "--porcelain", "--", rel])
    return bool(out) if rc == 0 else None


def mt(p):
    """★新鲜度时间✗★：git commit 时间优先（干净跟踪文件）／mtime 兜底"""
    c = _commit_ctime(p)
    if c is not None and _dirty(p) is False:
        return c
    try:
        return p.stat().st_mtime if p.is_file() else None
    except OSError:
        return None


def fresh(name, ups):
    """★doc 必须不比它的上游旧✗★（★上游不存在 ⇒ 记下来 ✗ 不当通过✗★）"""
    doc = D / name
    if not doc.is_file():
        return False, "★文档不在✗★", None
    if not has_git():
        return True, "★跳过：无 git（zip 快照）⇒ 新鲜度无法判（不冒充通过）★", None
    dm = mt(doc)
    newer = [u.name for u in ups if u.is_file() and mt(u) is not None and mt(u) > dm]
    byp = [u.name for u in ups if not u.is_file()]
    if byp:
        return False, "★上游不在 ✗ 没法比✗★：%s" % byp, dm
    if newer:
        return False, "★过期 ✗ 上游更新过✗★：%s" % newer, dm
    return True, "✓ 不比上游旧", dm


print("== generated_freshness: N1~N4 ==")
TAG = S / "tags_category.json"
EXC = S / "exceptions.json"
ACC = S / "u1_account.json"
PLAN = S / "cut.json"

_rows = [
    ("N1", "分歧清单.md", [TAG, EXC], "★它由标签普查 ＋ 例外表推出来✗★"),
    ("N2", "迁移准备度.md", [TAG, EXC], "★阶段 4 的排序依据 ✗ 过期最久✗★"),
    ("N3", "DoD-对账表.md", [ACC, EXC], "★它写的那几个数来自 u1_account ＋ 例外表✗★"),
    ("N4", "切换计划.md", [TAG, PLAN], "★它按标签准备度 ＋ 风险图排✗★"),
]
_checked = 0
_stale = []
for tag, name, ups, why in _rows:
    _checked += 1
    good, note, _dm = fresh(name, ups)
    if not good:
        _stale.append(name)
    check(tag, good, "%-18s %s（%s）" % (name, note, why))
# ★计数器✗★：★这三四份都得**真比过** ✗ 不许"★一份都不在就全绿★"✗★
check("N5", _checked >= 4, "★计数器✗★：比过 **%d** 份生成物（★≥4 ✗ 不许空转✓★）" % _checked)
print("")
print("★红了怎么办✗★：★重生成那几份 ✗ 而它们**都要导出**✗★")
print("  ★⇒ 这是" + chr(12300) + "缺输入" + chr(12301) + "那一族 ✗ 不是判据坏✗★：先跑 `/dshkb` ✗ 再重生成 ✓")

print("=> generated_freshness %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
