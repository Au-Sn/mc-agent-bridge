#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""family_vocab_test.py -- 四族词汇 ＋ L1~L4 退役（V1~V5 离线 2026-10-13 §79.245）

用户裁决 C1：§11 的 L1-L4 速记退役（与 L0-L6 运行时栈撞名），
统一为一套：真值族={phys, sem}／执行族={exec}／政策族={policy}。
★V3 是要害✗★：★一个符号只许有**一个**族 ✗ 而且 `UNKNOWN` 必须在 phys 里✗★ ✓
★V4 是"退役"的机械形态✗★：★旧名**只许出现在退役清单里** ✗ 不许散在代码里✗★ ✓
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import families as FAM

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


print("== family_vocab: V1~V5 ==")

check("V1", tuple(FAM.FAMILIES) == ("phys", "sem", "exec", "policy"),
      "四族就是 %s（★真值族 phys／sem ✗ 执行族 exec ✗ 政策族 policy✗★）"
      % ("／".join(FAM.FAMILIES)))

_bad_sym = [k for k, v in FAM.SYMBOLS.items()
            if not (isinstance(v, tuple) and len(v) == 2 and v[0] in FAM.FAMILIES
                    and str(v[1]).strip())]
check("V2", not _bad_sym,
      "每个符号都要写清「族 ＋ 为什么」⇒ 缺的：%s" % (_bad_sym or "（没有 ✓）"))

# ★V3：★物理那一族的符号必须**只问碰撞** ✗ 不许碰标签／政策✗★
_phys = [k for k, v in FAM.SYMBOLS.items() if v[0] == "phys"]
_policy = [k for k, v in FAM.SYMBOLS.items() if v[0] == "policy"]
check("V3", ("mapread.is_floor" in _phys) and ("mapread.is_landing" in _policy)
      and ("environment.standable_physical" in _phys)
      and ("environment.standable" in _policy),
      "★同一件事的两半各有其族✗★：物理那半 %s ✗ 政策那半 %s"
      % ("／".join(sorted(_phys)[:3]), "／".join(sorted(_policy)[:3])))

# ★V4：退役词汇的机械形态
#   ★★第一版我写的是"★全仓不许出现 `L1`~`L4`★" ✗ 一量就发现**不对**✗★★：
#   ★裸出现 **91** 次 ✗ 而其中绝大多数是**别的含义**✗★ ——
#   ★`speech_*` 的对话自检编号 L1~L9 ✗ 我自己写的 `probe_limit` L1~L5 ✗ 等✗★ ✓
#   ★⇒ 口径改成✗★：★只有"★挨着 层／族／§11★"的才算**旧词汇**✗★ ✓
#   ★（★这是同一族第四次 ✗ 先量再写✗★）✗★ ✓
# ★（★§79.245 收尾：我替换 V4 那段时把这个 `pat` 一起删掉了 ✗ 与 §79.239 同族 ✓★）
pat = re.compile(r"\bL([1-4])\b")
NEAR = tuple(getattr(FAM, "RETIRED_NEAR", ("层", "族", "§11")))
_near = {}
for p in sorted((ROOT / "tools").glob("*.py")):
    txt = p.read_text(encoding="utf-8", errors="replace")
    # ★★2026-10-13（★§79.245 收尾✗★）✗★★：★要把 `check_all.py` 也算进"★定义处★"✗★ ——
    #   ★因为我往闸门表里写的**描述**（★"★退役那种 `L1`~`L4`（挨着层／族／§11）★"✓★）
    #   **自己**触发了这条扫描 ✗★ ⇒ ★这是"★判据被自己人绊倒★"第三次✗★
    #   （★§79.194 的表项 ★§79.243 的 T5 ✓★）✗★ ✓
    #   ★口径✗★：★"★描述退役这件事★"与"★还在用旧词汇★"**不是一回事**✗★ ✓
    if p.name in ("families.py", "family_vocab_test.py"):
        continue
    # ★★2026-10-13（★审计实验 FV-V4-checkall-exempt✗★）✗★★：★原来**整个** `check_all.py`
    #   都被跳过 ✗ 而它上面只是"★描述退役这件事★" ✗★ ⇒ ★盲区比必要的大✗★ ✓
    #   ★现在只挖掉两样✗★：★① `GATE = [` 那张表 ② 含「退役」二字的行（★那是"★**说**这件事★"✓★）✗
    #     ★文件里**别处**照扫✗ —— ★真正"用"旧词汇的行仍会被抓✗★ ✓
    #   ★（★实验确认：只跳整个文件时 ✗ 往别处塞旧词汇它抓不到✓★）✗★ ✓
    #   ★（★上一轮我两次补丁都**没打上**：锚点被更早的补丁改过 ✗ 而补丁"静默没匹配"✗★ ——
    #     ★"★补丁没打上要说出来★" ✗ 又是一课✓★）✗★ ✓
    if p.name == "check_all.py":
        txt = re.sub(r"GATE = \[.*?^\]", "", txt, count=1, flags=re.S | re.M)
        txt = chr(10).join(l for l in txt.split(chr(10)) if "退役" not in l)
    for m in pat.finditer(txt):
        ctx = txt[max(0, m.start() - 14):m.end() + 14]
        if any(k in ctx for k in NEAR):
            _near[p.name] = _near.get(p.name, 0) + 1
check("V4", sum(_near.values()) <= int(getattr(FAM, "RETIRED_NEAR_COUNT", 0)),
      "★挨着「层／族／§11」的 `L1`~`L4`（★退役那种✗★）不许超过登记的 %d 次★⇒ 现在 %d 次：%s"
      % (int(getattr(FAM, "RETIRED_NEAR_COUNT", 0)), sum(_near.values()),
         _near or "（没有 ✓）"))

_txt = "".join(p.read_text(encoding="utf-8", errors="replace")
               for p in sorted((ROOT / "tools").glob("*.py")))
# ★★2026-10-13 修（★审计缺陷② ✗ §79.252✗★）✗★★：★原来这一条**恒真**✗★ ——
#   ★`_txt` 里有 `families.py` **自己**（★那个文件当然含 `L1`~`L4`✓★）✗★ ⇒
#   ★审计把 `RETIRED` 清空 ✗ 它照样绿 ✗ 判词还自己印"★0 个旧名 ✗ 各带理由✓★"✗★ ✓
#   ★⇒ 口径✗★：★清单**不许空**✗ 每条**理由要够实**（★≥12 字✗★）✗★ ✓
_empty = [k for k, v in FAM.RETIRED.items() if len(str(v).strip()) < 12]
check("V5", len(FAM.RETIRED) >= 1 and not _empty,
      "退役清单**不许空**✗ 每条理由要够实（★%d 个旧名 ✗ 理由太短的：%s✗★）"
      % (len(FAM.RETIRED), _empty or "（没有 ✓）"))

print("=> family_vocab %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
