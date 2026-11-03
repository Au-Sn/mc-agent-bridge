#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verifier_test.py -- 模块 L4 独立校验官的判据

规格 §14.1／§14.4：★"写世界的只有一个 ✗ 验世界的独立于它"★
  L-g ★执行官写的每个动作都被校验官独立核过★
  L-h ★校验官红过之后 ⇒ 执行官不许继续★

CHECKS（★大部分注入假 reader ⇒ 离线 ✗ 不碰世界✗★）
  V1 挖：真值现在是空气 ⇒ ok
  V2 挖：真值现在还是方块 ⇒ **红**（★这就是独立性：只看真值✗★）
  V3 放：真值等于期望 ⇒ ok
  V4 放：真值不等 ⇒ 红 ＋ 报出实际是什么
  V5 到达：脚格精确相等 ⇒ ok；差一格 ⇒ 红（★"近"不等于"到"✗★）
  V6 读不到 ⇒ 一律红（★不许"读不到就算过"✗★）
  V7 ★接口不接受"执行者说成了"★：verify_dig 的签名里没有 claim 参数（结构化检查）
  V8 真世界冒烟：读一格已知方块，真值与 `dshscan` 一致
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import verifier as V          # noqa: E402


def fake_reader(mapping):
    def read(pos):
        return mapping.get(tuple(pos), "★读不到★")
    return read


def main() -> int:
    checks = []

    checks.append(("V1 挖：真值空气 ⇒ ok",
                   V.verify_dig((1, 70, 1), read=fake_reader({(1, 70, 1): ""}))["ok"] is True,
                   "air"))
    bad = V.verify_dig((1, 70, 1), read=fake_reader({(1, 70, 1): "minecraft:stone"}))
    checks.append(("V2 挖：真值还是方块 ⇒ 红", bad["ok"] is False,
                   "%s ｜ now=%s" % (bad["why"], bad["now"])))

    checks.append(("V3 放：真值等于期望 ⇒ ok",
                   V.verify_place((2, 70, 2), "mekanism:energized_smelter",
                                  read=fake_reader({(2, 70, 2):
                                                    "mekanism:energized_smelter,active=false"}))["ok"] is True,
                   "match"))
    bad3 = V.verify_place((2, 70, 2), "minecraft:furnace",
                          read=fake_reader({(2, 70, 2): "minecraft:stone"}))
    checks.append(("V4 放：真值不等 ⇒ 红并报实际", bad3["ok"] is False and "stone" in bad3["now"],
                   "%s now=%s" % (bad3["why"], bad3["now"])))

    bot_ok = {"pos": (100.2, 70.0, 200.4), "feet": 70}
    bot_bad = {"pos": (100.2, 70.0, 201.9), "feet": 70}
    ok5 = (V.verify_arrived((100, 70, 200), bot=bot_ok)["ok"] is True
           and V.verify_arrived((100, 70, 200), bot=bot_bad)["ok"] is False)
    checks.append(("V5 到达：脚格精确相等（近≠到）", ok5,
                   "ok=%s bad=%s" % (V.verify_arrived((100, 70, 200), bot=bot_ok)["ok"],
                                     V.verify_arrived((100, 70, 200), bot=bot_bad)["ok"])))

    unread = V.verify_dig((9, 9, 9), read=fake_reader({}))
    checks.append(("V6 读不到 ⇒ 一律红", unread["ok"] is False and unread["why"] == "verify_unreadable",
                   unread["why"]))

    params = list(inspect.signature(V.verify_dig).parameters)
    checks.append(("V7 接口不接受执行者的自述", not any(
        p in params for p in ("claim", "report", "said", "asserted")),
        str(params)))

    # V8 真世界冒烟（只读）
    try:
        import mcp_core as C
        d = (C.dsh("dshdigest", 30.0) or "").strip()
        m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", d)
        if m:
            x, y, z = (int(float(m.group(i))) for i in (1, 2, 3))
            below = (x, y - 1, z)
            got = V._truth_cell(below)
            # 与 dshscan 再读一次对照
            txt = (C.dsh('dshscan %d %d %d %d %d %d ":" 8 1' % (below + below), 40.0) or "")
            mm = re.search(r"cells\[([^\]]*)\]", txt)
            want = (mm.group(1).split(":", 1)[1] if mm else "")
            ok8 = (got == want) and got not in ("", "★读不到★")
            checks.append(("V8 真世界冒烟：读的一格与 dshscan 一致", ok8,
                           "below=%s got=%r" % (below, got[:40])))
        else:
            checks.append(("V8 真世界冒烟：读的一格与 dshscan 一致", False, "读不到假人"))
    except Exception as exc:          # ★不许静默✗★
        checks.append(("V8 真世界冒烟：读的一格与 dshscan 一致", False, "异常 %r" % (exc,)))

    badn = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            badn += 1
    print("  ---- %d/%d ----" % (len(checks) - badn, len(checks)))
    if badn:
        print("  => verifier FAIL (%d)" % badn)
        print("VERIFIER ok=0 bad=%d" % badn)
        return 1
    print("  => verifier PASS (world truth only; nothing is accepted on the executor's word)")
    print("VERIFIER ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
