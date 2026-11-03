#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""environment_test.py -- ★有名查询的判据✗★（E1~E7 ✗ 全离线 ✓ 2026-10-05）

★★这一层最容易出的错是**串族**✗★★：★政策偷偷改了真值 ✗ 或执行族冒充真值✗★ ⇒
★判据的**一半**在查这个✗★ ✓
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import blockkb as KB  # noqa: E402
import environment as ENV  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== environment_test：E1~E7 ==")

# ★一格视图（★离线造一盒✗★）
CELLS = {
    # ★★"★脚站在 y=65★"这一层要**三格齐**：★脚下 64 ＋ 本格 65 ＋ 头上 66✗★★
    (0, 64, 0): "minecraft:stone",          # ★脚下是石头 ⇒ 能站✗★
    (0, 65, 0): "minecraft:air", (0, 66, 0): "minecraft:air",
    (1, 64, 0): "minecraft:water",
    (1, 65, 0): "minecraft:air", (1, 66, 0): "minecraft:air",
    (2, 64, 0): "minecraft:oak_leaves",     # ★脚下是树冠 ⇒ **不算落脚**✗★
    (2, 65, 0): "minecraft:air", (2, 66, 0): "minecraft:air",
    (3, 64, 0): "minecraft:lava",
    (3, 65, 0): "minecraft:air", (3, 66, 0): "minecraft:air",
    (4, 64, 0): "minecraft:ladder",         # ★脚下是梯子 ✗ 不是落脚点✗★
    (4, 65, 0): "minecraft:air", (4, 66, 0): "minecraft:air",
    (5, 64, 0): "minecraft:stone",          # ★脚下是石头 ✗ 而**本格是石头** ⇒ 站不进去✗★
    (5, 65, 0): "minecraft:stone", (5, 66, 0): "minecraft:air",
}
ENV.bind(CELLS, "test")

# ---- E1 三栏齐 ✗ 且每个查询都在表里
_bad = [q for q in ("standable", "safe", "swimmable", "climbable",
                    "parkourable", "ascendable", "is_liquid", "canopy")
        if ENV.family_of(q) is None]
check("E1", not _bad, "★三栏（★truth／exec／policy✗★）都声明了✗★ ⇒ 缺 %s" % (_bad or "无"))

# ---- E2 ★真值：站得住 ✗ 但要按**政策**排除树冠✗★
_down = (0, 64, 0)
check("E2", (ENV.standable((0, 65, 0)) is True)
      and (ENV.standable((2, 65, 0)) is False)
      and (ENV.standable((5, 65, 0)) is False),
      "★石头上面**能站** ✗ 树叶上面**不算落脚** ✗ **格子里塞满石头 ⇒ 站不进去**✗★"
      " ⇒ %s ／ %s ／ %s" % (ENV.standable((0, 65, 0)), ENV.standable((2, 65, 0)),
                             ENV.standable((5, 65, 0))))

# ---- E3 ★树冠是**政策**族（★不是真值✗★）
check("E3", ENV.family_of("canopy") == "policy" and ENV.canopy((2, 64, 0)) is True,
      "★`canopy` 归**政策栏** ✗ 且认得出树叶✗★")

# ---- E4 ★液体是真值 ✗ 而 `lava`／`water` **在碰撞上同类**✗★
check("E4", ENV.is_liquid((1, 64, 0)) is True and ENV.is_liquid((3, 64, 0)) is True,
      "★water 与 lava 都算液体（★碰撞同类✓★）✗★ ⇒ %s ／ %s"
      % (ENV.is_liquid((1, 64, 0)), ENV.is_liquid((3, 64, 0))))

# ---- E5 ★★执行族**没测过**的必须回 `None`✗★★（★不许冒充✗★）
check("E5", ENV.swimmable((1, 64, 0)) is None and ENV.climbable((4, 64, 0)) is None,
      "★★`swimmable`／`climbable` **没在校准场测过** ⇒ 必须 `None`✗★★ ⇒ %s ／ %s"
      % (ENV.swimmable((1, 64, 0)), ENV.climbable((4, 64, 0))))

# ---- E6 ★★政策**不许**动真值✗★★
_before = KB.blocks_space("minecraft:oak_leaves")
ENV.canopy((2, 64, 0))
ENV.safe((3, 64, 0))
_after = KB.blocks_space("minecraft:oak_leaves")
check("E6", _before == _after,
      "★★问过政策族之后 ✗ `blocks_space` **必须不变**✗★★ ⇒ %s ⇒ %s" % (_before, _after))

# ---- E7 ★★`safe` 现在**没有声明来源** ⇒ 必须 `None`✗★★
# ★§79.222：E7/E7b 用**自己**两格（★在前面的 E1~E6 都跑完之后才绑定✗★）✗★
ENV.bind({(0, 0, 0): "minecraft:lava", (0, 0, 1): "minecraft:stone"},
         "★E7/E7b 自己摆的夹具✗★")
_CELL_LAVA = (0, 0, 0)
_CELL_STONE = (0, 0, 1)

check("E7",
      ENV.safe(_CELL_LAVA) is False,
      "safe(lava) ＝ **False**（危险，政策默认回避进入）"
      " —— 2026-10-13 改（用户裁决 C5 / §79.222）：这条**原来断言的是缺口**"
      "（safe 恒回 None，因为类别表 27 类里没有 岩浆/火，按 ㉜ 不许从名字猜）；"
      "C5 把 岩浆/火 类别补上了（显式标签 id，§79.221），来源有了，所以 safe 接上三态。"
      "★这不是放宽判据：判据的主张从「没有来源，只能不知道」变成「有来源了，必须答」★")

check("E7b",
      ENV.safe(_CELL_STONE) is True and ENV.safe((99, 99, 99)) is None,
      "safe(石头) ＝ **True**（已知且不危险） ✗ safe(没绑定／读不到) ＝ **None**"
      " —— 守住另一头：★有了来源也**不许**对读不到的格子假装安全★，"
      "★更不许把不是危险的格子判成危险★ ⇒ %s ／ %s"
      % (ENV.safe(_CELL_STONE), ENV.safe((99, 99, 99))))

# ★★C3（★§79.230✗★）✗★★：E8/E9 用**自己**的格子（★前面的都跑完才绑定✗★）
ENV.bind({(0, 1, 0): "minecraft:air", (0, 2, 0): "minecraft:air",
          (0, 0, 0): "minecraft:oak_leaves"}, "★E8 自己摆的夹具（树叶 ＋ 空气）✗★")

check("E8",
      (ENV.canopy((0, 0, 0)) is True)
      and (ENV.standable((0, 1, 0))
           == (ENV.standable_physical((0, 1, 0)) is True and ENV.canopy((0, 0, 0)) is not True)),
      "★结构关系✗★：`standable` ≡ `standable_physical` ∧ ¬`canopy`"
      " —— 2026-10-13 改（用户裁决 C3）：这条**原来断言**「树叶上物理说能站、政策说不落脚」，"
      "而实测 `is_floor(oak_leaves)` **在名字模型下本来就是 False** ⇒ 那个前提在当前档位不成立"
      "（只有把开关拨到 table、导出说树叶是 full 时它才成立）。"
      "★所以改成断言**任何档位都成立**的那条★：政策只能**减**不能**加** —— "
      "`standable` 必须恰好等于「物理说能站 且 政策没说别去」⇒ canopy=%s physical=%s standable=%s"
      % (ENV.canopy((0, 0, 0)), ENV.standable_physical((0, 1, 0)), ENV.standable((0, 1, 0))))

# ★E9：机械查 —— 只查**调用**（带括号），不查文档串里的引用
_src = (ROOT / "tools" / "environment.py").read_text(encoding="utf-8")
_i = _src.find("def standable_physical")
_body = _src[_i:_src.find("\ndef ", _i + 10)]
_calls = [k for k in ("is_landing(", "canopy(", "safe(") if k in _body]
check("E9",
      ("is_floor(" in _body) and not _calls,
      "`standable_physical` 里**只许调用** `is_floor`，不许**调用** "
      "`is_landing`／`canopy`／`safe`（★政策不许进物理那一问✗★）⇒ 违规调用：%s"
      % (_calls or "无（文档串里提到不算 ✗ 这条只查调用）"))

print("=> environment %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
