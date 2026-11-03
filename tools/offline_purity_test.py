#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""offline_purity_test.py -- 离线表里的判据**真的**不碰世界吗（P1~P4 2026-10-13 §79.235）

★为什么有它✗★（★§79.234 那一课的推广✗★）：
  `reach_probe` 在 `col_fn=None` 时**自己去连活世界**（★`mapread.Reader().get(...)`✗★）⇒
  ★★"★注入式扫描★"其实一直在偷偷读世界 ✗ 而**"★离线★"这三个字是这一路所有判据的地基**✗★★ ✓
  ★那次是**量出来**的（★17.2 秒✓★）⇒ 这次把它变成**判据**✗★ ✓
口径（★与 `NOT_SHAPE_FAMILY` 同一个模式✗★）：
  · ★离线表里的脚本 ✗ 源码里**不许**出现"★会连世界★"的入口（★调用形式✗★）✗★ ✓
  · ★例外**必须声明 ＋ 写理由**✗★（★不许默默有✗★）✗★ ✓
  · ★计数器✗★：★查过的数必须等于表里的总数 ✗ 防"★全跳光冒充全查★"✗★ ✓
★★P2 是**运行时**的，比源码扫描硬✗★★：★给探针的注入路径上装**绊线** ✗
  ★它要是偷偷调了 ⇒ 当场炸 ✗ 而判据说"★没炸就是没调★"✗★ ✓
  ★★P2 只管**注入**路径 ✗ 真跑那条**照旧**要连世界（★那是它的本分✓★）✗★★ ✓
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

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "不符合", note))


# ★"会连世界"的入口（★调用形式 ✗ 不是提名字✗★）
# ★★2026-10-13 收紧（★§79.235✗★）✗★★：★只认**调用**✗ 不认"提到名字"✗★ ✓
#   ★现象✗★：★`cut34_seam_check.py` 被误报 ✗ 而它**只打桩再还原**（★比的是身份 ✗ 一次都没调用✓★）✗★ ✓
#   ★口径✗★：★"★属性访问★"（`_LIVE.dsh is real[...]`）**不是**连世界 ✗
#     ★"★调用★"（`_LIVE.dsh(...)`）才是✗★ ✓
LIVE = (r"MR\.Reader\(", r"\bReader\(\)\.", r"_LIVE\.\w+\(", r"batch_scan\(",
        r"fixture_scan\.", r"urlopen\(", r"create_connection\(")

# ★例外：**必须**写理由（★这里只有"★名字出现在字符串/注释里★"这一类✗★）
ALLOW = {
    # ★★第四次同族（★§79.256✗★）✗★★：★`world_touch_test.py` 里的
    #   「★连世界入口★」是**模式字符串**（★它正是去**统计**谁连世界的那个判据✗★）
    #   ★不是调用✗★ ✓ ★（★与 P1 自己的例子、`probe_limit` 的判词同一课✗★）✗★ ✓
    "world_touch_test.py": "★它写的正是「连世界入口」的模式串 ✗ 不是调用✗★（★§79.256✗★）",
    "probe_limit_test.py": "★它只是在**判词字符串**里提到 `mapread.Reader().get(...)`（★讲那次 17.2 秒✓★）✗ 不是调用✗★",
    "offline_purity_test.py": "★本判据自己 ✗ 它要写「会连世界」的模式串✓★",
    "check_all.py": "★闸门本体 ✗ 它要**知道**哪些脚本要世界（★WALK 表✓★）✗★",
    "offline_guard.py": "★「要世界就 INCONCLUSIVE」那条守卫本体✗★",
    # ★★2026-11-02 接手轮（§79.522）✗★★：★离线判据里 `urlopen(` 打的是**测试自己起的
    #   127.0.0.1 随机端口假 HTTP 服务器**（★验证 direct.py 真带了 X-DSH-Token / req= 头✗★）
    #   ✗ 不碰游戏 ✗ 不碰世界 ✓ 属于"离线可验的协议层"✓★
    "mod_http_test.py": "★离线段用 127.0.0.1 假 HTTP 服务器验 direct.py 带头（urlopen 只打假服务器 ✗ 不碰世界）✗ ★§79.522✗★",
    "mod_events_test.py": "★离线段同上：假服务器验 req= 与请求头对应（urlopen 只打 127.0.0.1 假服务器）✗ ★§79.522✗★",
}

try:
    import check_all as CA
    offline = list(getattr(CA, "OFFLINE", []) or [])
except Exception as e:
    check("P0", False, "读不到闸门的离线表：%s" % type(e).__name__)
    sys.exit(1)

print("== offline_purity: P1~P4（离线表 %d 项）==" % len(offline))

# ---- P1 源码扫描：离线脚本不许出现"会连世界"的入口（除非声明）
hits, examined = {}, 0
for item in offline:
    name = item[0] if isinstance(item, (tuple, list)) else str(item)
    p = ROOT / "tools" / name
    if not p.is_file():
        continue
    examined += 1
    txt = p.read_text(encoding="utf-8", errors="replace")
    bad = [pat for pat in LIVE if re.search(pat, txt)]
    if bad:
        hits[name] = bad
undeclared = {k: v for k, v in hits.items() if k not in ALLOW}
check("P1", not undeclared,
      "离线表里**没声明**却带着「连世界」入口的：%s" % (undeclared or "（没有 ✓）"))
for k, v in hits.items():
    print("       声明过：%-24s %s —— %s" % (k, v, ALLOW.get(k, "★没写理由✗★")[:44]))

# ---- P2 ★运行时绊线★：注入路径不许碰活世界
import reach_probe as RP
_bomb = {"n": 0}


def _boom(*a, **k):
    _bomb["n"] += 1
    raise AssertionError("★注入路径偷偷连了世界✗★")


_old_col, _old_scan = RP._col_top, RP._default_scan
RP._col_top, RP._default_scan = _boom, _boom
try:
    world = {}
    for x in range(-10, 13):
        for z in range(-10, 13):
            for y in range(-4, 5):
                world[(x, y, z)] = "minecraft:stone" if y <= -3 else "minecraft:air"
    d = RP.reach_probe((0, -2, 0), (2, -2, 0), timeout_ms=60000, budget=None,
                       scan_fn=lambda b: world)
    _err = None
except Exception as e:
    d, _err = {}, "%s: %s" % (type(e).__name__, str(e)[:60])
finally:
    RP._col_top, RP._default_scan = _old_col, _old_scan
check("P2", _err is None and d.get("reachable") == "yes" and _bomb["n"] == 0,
      "★注入路径装绊线✗★（`_col_top`／`_default_scan` 一调就炸）⇒ 结果=%s ✗ 绊线响了几次=%d"
      "%s" % (d.get("reachable"), _bomb["n"], ("  ★炸了✗★：" + _err) if _err else ""))

# ---- P3 绑定纯度：没绑定 ⇒ 一律 None（★"从哪读必须是给进来的"✗★）
import environment as ENV
_q = [ENV.standable((0, 0, 0)), ENV.standable_physical((0, 0, 0)), ENV.safe((0, 0, 0))]
check("P3", all(v is None for v in _q),
      "没绑定时三条查询全 `None`（★不许猜 ✗ 不许偷偷读✓★）⇒ %s" % (_q,))

# ---- P4 计数器：查过的必须等于表里的总数
check("P4", examined == len(offline),
      "★计数器✗★：查过 %d ／ 表里 %d（★防「全跳光冒充全查」✗★）" % (examined, len(offline)))

print("=> offline_purity %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)
