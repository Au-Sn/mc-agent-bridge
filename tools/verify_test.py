#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_test.py -- ★统一回执包装的判据（Q1~Q5 ✗ 离线 ✓ 秒级 ✓ 2026-10-02 ✓ 欠账 ③ ✓）

WHY ✓：包装是"所有改世界动作的**构造属性**" ✗ 它一旦坏掉 ⇒ ★"回执说谎"那一族会**静默复活**✗★
  ⇒ ★它自己必须被判据钉住 ✗ 而且**不许连世界**（用**注入的假读数** ✓✓）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import mcp_verify as V  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== verify_test：统一回执包装 Q1~Q5 ==")
# ★Q5：口径只有一处 ⇒ 直接来自 mcp_policy.mutating ✓
import mcp_policy as P  # noqa: E402
acts = P.load().get("mutating") or set()
check("Q5", len(acts) > 5, "改世界动作来自 `mcp_policy.mutating`（%d 个 ✓ 一处定义 ✓）" % len(acts))

# ★Q4：只读工具**什么都不加** ✓
check("Q4", V.check("bot_state", {}) is None, "`bot_state` ⇒ None（★不加噪声✓★）")

# ★Q1：是动作但没独立读数 ⇒ `verified=unavailable` ✓（★明写 ✗ 不静默✓★）
#   ★注✗★：`harvest_crop` **已经**被登记成 SELF（★它自带世界真值自证✗★）⇒ ★这里换成 `use_block`✗★
#   （★"判据要跟着被测量的东西走" ✗ 第一版我拿 `harvest_crop` 当样本 ⇒ 登记之后**假红**了✓★）
r1 = V.check("use_block", {})
check("Q1", r1 is not None and r1[0] is None and "unavailable" in r1[1],
      "`use_block` ⇒ %s…" % (r1[1][:46] if r1 else "-"))

# ★Q2/Q3：★注入假读数✗★ —— 不一致 ⇒ 必须 `False`（框架会据此**标红** ✓）；抛异常 ⇒ error ✓
V.scan_cell = lambda x, y, z: "air"                      # noqa: E731
a_true, n_true = V.v_dig_block({"x": 1, "y": 2, "z": 3})
V.scan_cell = lambda x, y, z: "minecraft:cobblestone"    # noqa: E731
a_false, n_false = V.v_dig_block({"x": 1, "y": 2, "z": 3})
check("Q2", a_true is True and a_false is False and "verified=false" in n_false,
      "读数=air ⇒ true ✓ ｜ 读数=cobblestone ⇒ **false**（框架据此标红 ✓）")
V.scan_cell = lambda x, y, z: (_ for _ in ()).throw(RuntimeError("boom"))   # noqa: E731
r3 = V.check("dig_block", {"x": 1, "y": 2, "z": 3})
check("Q3", r3 is not None and r3[0] is None and "error" in r3[1],
      "读数抛异常 ⇒ %s…" % (r3[1][:44] if r3 else "-"))

# ★Q6/Q7：★"前后对比"那类（`chest_put`）✗★ —— ★用**注入的假容器读数**验 ✗ 不连世界✓★
_seq = {"n": 0}


def _fake_peek(x, y, z):
    _seq["n"] += 1
    return ("slot1:minecraft:cobblestonex3" if _seq["n"] == 1
            else "slot1:minecraft:cobblestonex4")


V._peek = _fake_peek
_args = {"x": 1, "y": 2, "z": 3, "item": "minecraft:cobblestone", "count": 1}
_pre = V.pre("chest_put", _args)
ok6, note6 = V.check("chest_put", _args, _pre)
check("Q6", ok6 is True and "3 → 4" in note6,
      "容器 3⇒4 ⇒ true ✓（%s…）" % note6[:44])

V._peek = lambda x, y, z: "slot1:minecraft:cobblestonex3"
_pre2 = V.pre("chest_put", _args)
ok7, note7 = V.check("chest_put", _args, _pre2)
check("Q7", ok7 is False and "verified=false" in note7,
      "★容器**没变** ⇒ false✗★（★框架据此**把这次标红**✗ ✓）")

# ★Q8：★"自己就会回读"的动作 ⇒ 必须报 `by-tool`✗★（★与 `unavailable` **分开** ✗ 别混成一档✓★）
r8 = V.check("jump", {})
r8b = V.check("look_at", {})
check("Q8", r8 is not None and "by-tool" in r8[1] and "unavailable" not in r8[1]
      and r8b is not None and "by-tool" in r8b[1],
      "`jump`／`look_at` ⇒ by-tool ✓（★它们自己回读 y／yaw ✓★）")

# ★Q9：★批量容器动作**本来就在逐件对账**✗★ ⇒ 必须报 `by-tool`（★我先前误记成 unavailable✗★）
r9 = V.check("chest_put_many", {})
check("Q9", r9 is not None and "by-tool" in r9[1],
      "`chest_put_many` ⇒ by-tool ✓（★它的说明写着「对不上绝不报成功」✗★）")

# ★Q10：★"没有读数"的名单**只许**是白名单里那几个✗★ ——
#   ★以后**新加**一个改世界动作 ✗ 却忘了给它配读数 ⇒ **这一条就会红**✗★（★这才是判据的本意✓★）
_ALLOWED_NO_READBACK = {"use_block"}      # ★`use_block` 的效果是**状态类**（拉杆/门/按钮 ✓）⇒ 暂无独立读数 ✓★
import mcp_policy as P2  # noqa: E402
_acts = P2.load().get("mutating") or set()
_bad = {a for a in _acts if a not in V.VERIFIERS and a not in V.SELF_VERIFIED}
check("Q10", _bad == _ALLOWED_NO_READBACK,
      "没读数的＝%s ✓（★白名单＝%s ✗ 多一个就红✓★）"
      % (", ".join(sorted(_bad)) or "（空 ✓）", ", ".join(sorted(_ALLOWED_NO_READBACK))))

# ★★Q11/Q12：★"掉落了没有"三条尺子合一✗★★（欠账 ⑯-② ✓ 2026-10-03 ✓）
#   ★场景✗★：★刚放下的那一格 ✗ 假人贴着它 ⇒ 掉落物**当场被捡** ✗
#     ⇒ ★"地上有"与"背包涨了"**同时为假** ✗ 而它**其实掉了**✗★
ok11, n11 = V.drop_witness("dshdig 1,2,3 was=Block{minecraft:cobblestone} now=air dropped=true",
                           ground_ok=False, items_delta=0)
check("Q11", ok11 and "战利品生成了" in n11 and "地上有一件能捡的" in n11,
      "★`dropped=true` ⇒ 判成 ✓ 但判词**明写它没证明什么**✗★（%s…）" % n11[:52])

ok12, n12 = V.drop_witness("dshdig … now=air", ground_ok=False, items_delta=0)
check("Q12", (not ok12) and "全假" in n12,
      "★三条全假 ⇒ 判红✗★（★不许当成「掉了」✓★）")

print("=> verify_test %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)