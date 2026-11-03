#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""u1_declared_test.py -- ★铁律②那个数的**算术判据**✗★（U1~U3 ✗ 离线 ✓ 2026-10-05）

★★它**不**判"★未声明该不该是 0★"✗★★（★那要你先裁定 ✗ §79.189✓★）✗★ ✓
★它只判**算术自洽**✗★：★分档不许漏 ✗ 声明与未声明必须加起来等于决策级✗★ ✓
★（★§79.186 那条教训的同一形态✗★：★"★数对不上★"必须先于"★数好不好★"✗★）✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== u1_declared：U1~U3 ==")
r = __import__("subprocess").run(
    [sys.executable, "-X", "utf8", str(ROOT / "tools" / "u1_declared.py")],
    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
out = r.stdout or ""
nums = {}
for key, pat in (("inc", r"不一致 (\d+) 条"), ("dec", r"决策级 (\d+) 条"),
                 ("yes", r"已声明✗★\s+(\d+)"), ("no", r"未声明✗★★\s+(\d+)")):
    m = re.search(pat, out) if (re := __import__("re")) else None
    nums[key] = int(m.group(1)) if m else None

check("U1", all(v is not None for v in nums.values()),
      "★四个数都读到了✗★ ⇒ %s" % nums)
check("U2", (nums.get("dec") or 0) <= (nums.get("inc") or -1),
      "★决策级 ≤ 不一致✗★ ⇒ %s ≤ %s" % (nums.get("dec"), nums.get("inc")))
check("U3", (nums.get("yes") or 0) + (nums.get("no") or 0) == (nums.get("dec") or -1),
      "★★已声明 ＋ 未声明 **必须**等于决策级✗★★ ⇒ %s ＋ %s vs %s"
      % (nums.get("yes"), nums.get("no"), nums.get("dec")))

# ★★2026-10-13（★第四轮扫描✗★）✗★★：★铁律②那个数**只许变小**✗★ ✓
#   ★真相（★2026-10-13✗★）✗★：★决策级不一致 **2165** 条里 ✗ **未声明 624** 条（★29%✗★）✗★
#   ★⇒ ★**铁律②现在是破的**✗★ —— ★而这条判据（★U1~U3✗★）原来**只查三个算术**✗★ ⇒
#     ★★它盖不住这件事 ✗ 而台账里多轮写着"★未声明 0 ✗ 由它守着★"✗ 那句话是**错的**✗★★ ✓
#   ★口径✗★：★这个数**记账**（★`state/u1_account.json`✓★）✗ ★**变大就必须红**✗★ ✓
#     ★（★"★不许悄悄变多★" ✗ 而"★补到 0★"是**下一步的活**✗ 不是改判据✓★）✗★ ✓
_acct = {}
try:
    _acct = json.loads((ROOT / "state" / "u1_account.json").read_text(encoding="utf-8"))
except Exception:
    _acct = {}
_allowed = int(_acct.get("undeclared") or 0)
_live = int(nums.get("no") or 0)
check("U4", _live <= _allowed,
      "★未声明的数**只许变小**★：★记账 %d ✗ 现在 %d✗★ ⇒ %s"
      % (_allowed, _live,
         ("★变小了 ✓（★离" + chr(12300) + "0" + chr(12301) + "更近✓★）" if _live < _allowed
          else "★没变（★仍是**未声明** ✗ 这是**欠账**不是通过✗★）" if _live == _allowed
          else "★★变大了 ✗✗ — 有新的不一致没配声明★")))

# ★★2026-10-13（★§79.264✗★）✗★★：★"★能离线守的那一半★"必须**收支平衡**✗★★ ✓
#   ★口径✗★：★**冲突型**（★语义 ✗ 现在就能声明✓★）的未声明数**必须是 0**✗★ ——
#     ★它与"★决策级那 624★"**不是一回事**：★后者**卡在缺 `collision`** ✗ 写了就是违规✗★ ✓
#   ★（★所以这条判据**现在就该是绿的** ✗ 而它一红就说明"★能补的没补★"✗★）✗★ ✓
try:
    _sem = int((_acct.get("semantic_undeclared") if isinstance(_acct, dict) else 0) or 0)
except Exception:
    _sem = 0
check("U5", _sem == 0,
      "★冲突型（★语义✗★）未声明必须是 **0** ✗ 记账说 %d★（★这一半**离线就能补** ✗ "
      "与卡导出的那 624 条不是一回事✗★）" % _sem)

print("=> u1_declared %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
print("   ★注意✗★：★「未声明该不该是 0」**不**在这条的判据里✗★ —— ★那是裁定 ✗ 不是算术✗★")
sys.exit(0 if ok[0] else 1)
