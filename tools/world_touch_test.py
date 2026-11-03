#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world_touch_test.py -- 世界触碰**清单可机器统计**（W1~W4 离线 2026-10-13 §79.256）

★出处✗★：欠账 **⑦「测试世界与真实世界分离」** 的方案第三层 ——
★"★把**破坏性**测试赶到**指定区** ✗ 约定「改世界」的测试只在校准网格/测试平台里做 ✗
基地/农场/筛子一律只读✗」✗ 而**配套**是✗★：
★★"★每条判据在文件头写明 `只读`／`改世界（限某区）` ⇒ **清单可机器统计** ✗
越界可查★"✗★★ ✓
★这一层是**零成本**的（★纪律 ＋ 清单 ✗ 不要新机制✓★）✗ 但它**必须先能统计**✗★ ✓
★口径✗★：★"★碰世界★"＝源码里出现会连世界的调用（★`Reader()` ✗ `_LIVE.x(` ✗
`batch_scan(` ✗ `.pos()` 之类✓★）✗ ★不是"★提到世界两个字★"✗★ ✓
★而**没标注**的（★历史遗留✗★）**必须声明 ＋ 给替换触发**✗ —— 与 `NOT_SHAPE_FAMILY` 同一个模式✗★ ✓
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

import check_all as CA

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


PAT = re.compile(r"MR\.Reader\(|_LIVE\.\w+\(|batch_scan\(|fixture_scan\.|\.pos\(\)|"
                 r"FS\.batch_scan\(|dsh_live|world_up")
# ★★没标注的历史遗留✗★★：★声明 ＋ 替换触发（★下次动到它就补标注✗★）✗★ ✓
# ★★误报声明✗★★：★`offline_purity_test.py` 命中的是它**自己写的模式字符串**✗★
#   ★（★它正是**禁止**别人连世界的那个判据 ✗ 与 §79.235 的 P1 同一件事✓★）✗★ ✓
FALSE_POSITIVE = {
    "offline_purity_test.py": "★它是**禁止**连世界的判据 ✗ 命中的是模式字符串本身✗★",
    "world_touch_test.py": "★本判据自己 ✗ 同理✗★",
    "probe_limit_test.py": "★判词字符串里提到 `Reader().get(` ✗ 不是调用✗★",
    # 2026-11-02 第二轮（§79.530）：它扫的正是"禁写死端口/实例名/绝对路径"的**模式字符串**，
    # 不是任何连世界调用 ✗ 与 offline_purity 同一族误报。
    "portability_test.py": "★解绑判据 ✗ 它扫的就是端口/实例名/路径**模式字符串**✗ 不是调用✗★",
}

DECLARED = {
    "area_verify_test.py": "★区域核对 ✗ 只读（★扫了比一比✓★）✗ 补标注时要分清；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "chest_many_test.py": "★多箱子测试 ✗ 疑似**改世界**（★放箱子✓★）⇒ 补标注时应写「限测试平台」；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "edge_avoid_test.py": "★贴边走 ✗ 疑似**改世界**（★摆方块✓★）；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "kb_audit.py": "★只报数不判红 ✗ 只读✗★；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "m1_verify.py": "★第一里程碑核对 ✗ 只读✗★；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "mapnames_test.py": "★地图名字 ✗ 只读（★读图✓★）；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "mod_contract.py": "★契约围栏 ✗ 只读（★读导出✓★）；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "plan_verify_test.py": "★规划核对 ✗ 只读（★扫路径✓★）；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "platform_test.py": "★平台测试 ✗ 疑似**改世界**；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "prefix_guard_test.py": "★前缀守卫 ✗ 只读✗★；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "r8_guard_test.py": "★守卫 ✗ 只读✗★；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "r9_target_guard_test.py": "★守卫 ✗ 只读✗★；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "route_verify_test.py": "★走一遍核对 ✗ 只读（★走 + 读回 ✓ 不改方块✓★）；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "shape_learn_test.py": "★学形状 ✗ 疑似**改世界**（★摆形状✓★）；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "step_route_test.py": "★上台阶 ✗ 疑似**改世界**（★摆台阶✓★）；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "verdict_levels_test.py": "★判词分级 ✗ 只读✗★；★历史遗留 ✗ 没标注 ✗★ ⇒ ★替换触发：**下次动到它就补头部标注**（★`★世界★：只读` 或 `★世界★：改世界（限某区）`✓★）✗★ ✓",
    "r2_verify.py": "★寻路世界判据 ✗ 只读（★走 + 读回 ✓ 不改方块✓★）✗ 下次动它时在头部补 `★世界★：只读`✗★",
    "r3_verify.py": "★同上 ✗ 只读✗★",
    "route_view_test.py": "★同上 ✗ 只读✗★",
    "gesture_test.py": "★要世界 ✗ 现在测不了（★†测不了†✓★）✗ 补标注时一并写清「★世界★：改世界（限测试平台）」✗★",
}

print("== world_touch: W1~W4 ==")

_touch, _marked, _examined = {}, [], 0
for s, _d, _t in CA.GATE:
    p = ROOT / "tools" / s
    if not p.is_file():
        continue
    _examined += 1
    txt = p.read_text(encoding="utf-8", errors="replace")
    if not PAT.search(txt):
        continue
    if s in FALSE_POSITIVE:        # ★误报 ✗ 不算碰世界✗★
        continue
    _touch[s] = len(PAT.findall(txt))
    head = "\n".join(txt.splitlines()[:24])
    if "★世界★" in head:
        _marked.append(s)

check("W1", bool(_touch), "清单：闸门里 **%d** 个脚本碰世界（★共查 %d 个✗★）"
      % (len(_touch), _examined))

_undeclared = sorted(k for k in _touch if (k not in _marked) and (k not in DECLARED))
check("W2", not _undeclared,
      "★碰世界的必须要么**头部标注**✗ 要么**声明 ＋ 替换触发**✗★ ⇒ 没声明的：%s"
      % (_undeclared or "（没有 ✓）"))

check("W3", _examined == len(CA.GATE),
      "★计数器✗★：查过 %d ／ GATE 里 %d（★不许「全跳光冒充全查」✗★）"
      % (_examined, len(CA.GATE)))

print("      ★碰世界清单✗★（★这就是「清单可机器统计」✗★）✗★：")
for k in sorted(_touch):
    _tag = "已标注" if k in _marked else ("已声明" if k in DECLARED else "★没标注也没声明✗★")
    print("        %-30s %2d 处 ✗ %s" % (k, _touch[k], _tag))
check("W4", len(_marked) + len(DECLARED) >= len(_touch),
      "★标注 %d ＋ 声明 %d ≥ 碰世界 %d✗★（★这个数不会自己变小 ✗ 只会随着补标注变大✓★）"
      % (len(_marked), len(DECLARED), len(_touch)))

print("=> world_touch %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
