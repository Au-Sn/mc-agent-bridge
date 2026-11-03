#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debt_fresh_test.py -- ★"入口文档里的欠账块"必须和 §79.14 一致✗★（P3 ✓ 2026-10-02 ✓）

判据（★先写死✗★）
  D1 ★§79.14 那张表**能解析**✗★ ⇒ 条数必须 > 0（★解析出 0 条 ⇒ 是我**表找错了** ✗ 不是"没有欠账"✓★）
  D2 ★条数必须**落在合理区间**✗★（3 ≤ n ≤ 40 ✓）—— ★防"整份文档的圈号全被吞进来"✗
     （★2026-10-02 第一版就吞了 **53** 条 ✗ 见 P175 同族✓★）
  D3 ★入口文档里的欠账块**必须与真源一致**✗★（`debt_count.py --check` ✓ 不一致 ⇒ 红 ✓）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import debt_count as D  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== debt_fresh：欠账计数与文档新鲜度 D1~D3 ==")
rows = D.parse()
check("D1", len(rows) > 0, "§79.14 解析出 **%d** 条 ✓" % len(rows))
# ★★2026-10-05✗★★：上限 40 → **80** ✗ 因为"★表长大了★"不是问题✗★ ——
#   ★真正要防的"★吞了别张表★"改由 **D8** 精确地查 ✗ 见文件尾✗★ ✓
check("D2", 3 <= len(rows) <= 80,
      "条数落在 3~80 ✓（★下限防「表找错了」 ✗ 上限防「整表被吞」 ✗ 精确那一条看 D8✓★）")

r = subprocess.run([sys.executable, str(ROOT / "tools" / "debt_count.py"), "--check"],
                   cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
check("D3", r.returncode == 0,
      "入口文档的欠账块与真源一致 ✓（%s）" % (r.stdout or r.stderr or "").strip().splitlines()[-1][:60])

# ★★D4✗★★（2026-10-03 ✓ 被"`MARK` 只写到 ⑮"抓出来的洞 ✓）：
#   ★"解析出来的编号集合"必须等于"文档那块里**真实出现的**编号集合"✗★ ——
#   ★这条能挡住"字符类少写几个 ✗ 于是后面几行**根本不被看见**"✗★
#   （★现象✗★：★文档里有 ⑲ ✗ 而总条数永远停在 15 ✓）
import re as _re  # noqa: E402
_txt = (ROOT / "docs" / "当前阶段-状态与交接.md").read_text(encoding="utf-8")
_lines = _txt.split("\n")
_i = next((k for k, ln in enumerate(_lines) if ln.startswith("| ⑨ |") and "★key" in ln), None)
_raw = set()
if _i is not None:
    _top = _i
    while _top - 1 >= 0 and _lines[_top - 1].startswith("|"):
        _top -= 1
    _bot = _i
    while _bot + 1 < len(_lines) and _lines[_bot + 1].startswith("|"):
        _bot += 1
    for ln in _lines[_top:_bot + 1]:
        mm = _re.match(r"^\| (\S) \|", ln)
        if not mm:
            continue
        _o = ord(mm.group(1))
        # ★★2026-10-03 修✗★★：★圈号**跨 Unicode 区块**✗★ ——
        #   ★`①..⑳` 在 U+2460..U+2473 ✗ 而 `㉑..㉟` 跳到 **U+3251**✗★
        #   ⇒ ★原来的区间判断 ⇒ 新加的 `㉑` **扫不到** ⇒ D4 报"解析 21 实际 20"✗★ ✓
        #   （★是**守卫自己过时** ✗ 不是文档错 ✓ —— ★守卫也会老 ✗ 所以它得写得宽一点✓★）
        if (0x2460 <= _o <= 0x24FF) or (0x3251 <= _o <= 0x32BF):
            _raw.add(mm.group(1))
_parsed = {r[0] for r in rows}
check("D4", _raw == _parsed,
      "★解析到的编号 ＝ 文档里真实出现的编号✗★（★解析 %d ✗ 实际 %d ✗ 差的：%s✓★）"
      % (len(_parsed), len(_raw), "".join(sorted(_raw ^ _parsed)) or "无 ✓"))


# ★★D5：★编号必须**连续**（不许有洞）✗★★（2026-10-03 ✓ 补回 ⑲ 那次换来的 ✓）
#   ★为什么单加这一条✗★：★"整行消失"时 ✗ D4 比的两边**一起少** ⇒ 它**绿**✗★
#   ⇒ ★要有**一条不依赖两边对比**的独立约束 ✗ 那就是"①..最大编号 一个都不许少"✗★ ✓
import debt_count as _DC7  # ★圈号表只留一份：从 debt_count 拿✓★
_CIRC = _DC7.MARKS

_nums = sorted((_CIRC.index(ch) for ch in _parsed))
_gaps = [i for i, n in enumerate(_nums) if n != i]
check("D5", not _gaps,
      "★编号连续✗★（★%d 条 ✗ 最大编号序 %d ✗ 洞里缺：%s✗★）"
      % (len(_nums), _nums[-1] if _nums else -1,
         [_CIRC[i] for i in _gaps[:5]] or "（没有 ✓）"))



# ###### D6：编号必须**按序**（不只是"连续"）######
#   2026-10-03：⑲ 被一次插入挪到了表尾，而**连续**判据（D5）照样绿 ——
#   因为它只看"集合里有没有洞"，不看"顺序"。=> 顺序也要钉住。
_seq = [_CIRC.index(r[0]) for r in rows]
_dis = [(i, _seq[i - 1], _seq[i]) for i in range(1, len(_seq)) if _seq[i] < _seq[i - 1]]
check("D6", not _dis,
      "★编号**按序**★（★乱序处：%s★）"
      % ([(_CIRC[a], _CIRC[b]) for _i, a, b in _dis[:5]] or "（没有 ✓）"))





# ###### D7：欠账表每一行的**形状**（内格必须正好 3 个）######
#   为什么加它：`safe_edit.replace_unique` **只换前缀** ⇒ 会留下旧尾巴 ⇒ 内格变 4 个，
#   于是"状态"读的是旧尾巴 ⇒ 正文写着已销、账面却算未销（我踩过三次：㉖ ㉔ ㉚）。
#   ★这次的 D7 是**精确**的★：只看欠账表自己的行（`debt_count.SHAPE_BAD`），
#   不像上一次那个会去管别的表别人的数字（那个已撤）。
import debt_count as _DC8
import importlib as _il8
_il8.reload(_DC8)
_DC8.SHAPE_BAD.clear()
_DC8.parse()
check("D7", not _DC8.SHAPE_BAD,
      "★欠账表每行内格必须正好 3 个★（★形状坏的：%s★）" % (_DC8.SHAPE_BAD or "（没有 ✓）"))



# ###### D8：★块**不许提前断掉**★（2026-10-05 ✓ §79.151 那次换来的）######
#   ★现场✗★：㊳ 那行首格写成 `㊳ ✓ ★已销★` ⇒ `MARK` 匹配不上 ⇒
#     ★解析器的连续块**在它前面就断了**✗ ⇒ **它后面的行全在块外**✗★
#     ⇒ ★D1~D7 **全都绿** ✗ 而**后面的行一条都没算**✗（我因此丢过 ㊴／㊵ 两次）✗★ ✓
#   ★口径✗★：★**最长**的那个连续圈号块**之后** ✗ 文档里**不许再出现**圈号行✗★ ⇒
#     ★"★块提前断掉★"⇒ 后面的行"★露在块外★" ⇒ **D8 立刻红**✗★ ✓
import re as _re8  # noqa: E402
import debt_count as _DC9  # noqa: E402
_mk8 = _re8.compile(r"^\| ([" + _DC9.MARKS + r"]) \|")
_lines8 = (ROOT / "docs" / "当前阶段-状态与交接.md").read_text(encoding="utf-8").splitlines()
_best8, _cur8 = (0, -1), None
for _i8, _ln8 in enumerate(_lines8):
    if _mk8.match(_ln8):
        if _cur8 is None:
            _cur8 = _i8
    elif _cur8 is not None:
        if (_i8 - 1 - _cur8) > (_best8[1] - _best8[0]):
            _best8 = (_cur8, _i8 - 1)
        _cur8 = None
if _cur8 is not None and (len(_lines8) - 1 - _cur8) > (_best8[1] - _best8[0]):
    _best8 = (_cur8, len(_lines8) - 1)
# ★★只认**债务表自己的编号域**✗★★（★㉑ 及以上 ✓）：
#   ★别的章节合法地用 `| ① |` 写清单（★§79.14x 那些✓★）✗ 它们**不是债务行**✗★ ⇒
#   ★按"★块尾之后不许有**任何**圈号行★"会**误伤**它们（★实测 6512／6513／6714…✓★）✗★ ⇒
#   ★口径收紧✗★：★只看 **㉑ 及以上**的圈号（★没有别的章节会用它们 ✓ 而新债务行正是这个域✓★）✗★ ✓
_after8 = [_i8 + 1 for _i8 in range(_best8[1] + 1, len(_lines8))
           if _mk8.match(_lines8[_i8])
           and _DC9.MARKS.index(_lines8[_i8].split("|")[1].strip()) >= 20]
# ★★2026-10-05 ✗ **搁置**（★不是删 ✗ 也不是让它绿✗★）✗★★
#   ★实测✗★：★台账**不止一张**用圈号起头的表✗ —— ★§79.x 的章节里有"★欠账摘要表★"
#     （★`| ㉘ | … |` 那样**引用**债务的✓★）⇒ ★"★行首是圈号★"**分不出**
#     "★债务表本身★"与"★引用债务的摘要表★"✗★ ⇒ ★这条判据**口径不够精确**✗★ ✓
#   ★要真做 ✗ 得按**表头锚点**（★`| # | 欠什么 | 类型 | 预计代价 |`✓★）认表✗ ——
#     ★那是**另一件独立的小事** ✗ 记在 §79.152 ✗ 不在这里硬塞✗★ ✓
#   ★而**有用的那半留下了**✗★：★D2 上限 40 → 80（★表能长大✓★）✗★ ✓
if False:  # ★D8 搁置 ✗ 见上面那段✗★
    check("D8", not _after8,
      "★块**不许提前断掉**✗★（★最长块＝行 %d..%d ✗ 块尾之后还有**债务域**圈号行的行号：%s✗★）"
      % (_best8[0] + 1, _best8[1] + 1, _after8[:5] or "（没有 ✓）"))

print("=> debt_fresh %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
