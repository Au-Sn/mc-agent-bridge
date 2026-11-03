#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_verify.py -- ★统一回执包装：动作发完，由**框架**回读世界真值✗★（2026-10-02 ✓ 欠账 ③ ✓）

WHY（★P164 家族的**系统解** ✗ 不是"每个工具自觉"✓★）：
  ★"回执没报错 ≠ 世界变了"✗★ —— 2026-10-01/02 我犯了 **三次**（`dig` ✗ `/dshjump` ✗ 以及
  "单次扫描就宣布清干净" ✗）⇒ ★靠每个工具自觉 ⇒ 一定会漏✗★
  ⇒ 口径 ✓：★把它做成**所有改世界动作**的**构造属性**✗★ ——
  ★动作返回之后 ✗ **框架**再去读一次世界 ✗ 不一致就把这一次**标红**✗★（★工具自己说成功也没用✓★）

判据（★先写死 ✗ 不许事后改 ✓ 离线可测 ✓）
  Q1 ★不认识的动作 ⇒ `verified=unavailable`✗★（★明写"没有独立读数" ✗ 不许静默 ✓★）
  Q2 ★读数说"和工具声称的不一致" ⇒ 框架必须**把这次标红**✗★（★不许只加一行提示 ✓★）
  Q3 ★读数本身就是错的（抛异常）⇒ `verified=error`✗★ 并附类型名 ✓（★不静默 ✗ P174 ✓★）
  Q4 ★不是改世界动作 ⇒ 框架**什么都不加**✗★（★别给只读工具刷噪声✓★）
  Q5 ★"哪些工具要验"只有**一处**定义✗★ ⇒ ★直接用 `mcp_policy` 的 `mutating`✗★（P106 ✓）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★★独立读数（★可注入 ✗ 测试里替换它 ✓★）★★
def scan_cell(x, y, z):
    """读**一格**的方块名（★空气 ⇒ `air` ✗ 读不到 ⇒ None✗★）"""
    from mcp_core import dsh
    t = dsh("dshscan %d %d %d %d %d %d" % (int(x), int(y), int(z), int(x), int(y), int(z)), 30.0) or ""
    m = re.search(r"counts\[([^\]]*)\]", t)
    if not m:
        return None
    if not m.group(1).strip():
        return "air" if "air=1" in t else None
    return m.group(1).split(",")[0].rsplit(":", 1)[0]


def pos_now():
    from mcp_core import _pos_now
    return _pos_now()


# ★★每个动作的"独立读数"✗★★（★只写"读了世界才能判"的那些✗★）
def v_dig_block(a):
    x, y, z = a.get("x"), a.get("y"), a.get("z")
    b = scan_cell(x, y, z)
    if b is None:
        return None, "★verified=error✗★：那一格读不到（%s）" % str((x, y, z))
    if b == "air":
        return True, "★verified=true✗★：世界真值 (%s) = air ✓" % str((x, y, z))
    return False, ("★verified=false ✗ 世界真值说它**还在**✗★：(%s) = %s "
                   "⇒ ★这一条动作**没成** ✗ 不许当成功✓★" % (str((x, y, z)), b))


def v_place_block(a):
    x, y, z, item = a.get("x"), a.get("y"), a.get("z"), str(a.get("item") or "")
    b = scan_cell(x, y, z)
    short = item.split(":")[-1]
    if b is None:
        return None, "★verified=error✗★：那一格读不到（%s）" % str((x, y, z))
    if short and short in b:
        return True, "★verified=true✗★：世界真值 (%s) = %s ✓" % (str((x, y, z)), b)
    return False, ("★verified=false ✗ 世界真值说那一格是 %s ✗ 而我说放的是 %s✗★"
                   "（%s ⇒ ★不许当成功✓★）" % (b, item or "?", str((x, y, z))))


def v_walk(a):
    """★走类的验证✗★：★到位了没有 ✗ 按"格＋层"判✗（P104/P142 那一族的教训 ✓）"""
    x, y, z = a.get("x"), a.get("y"), a.get("z")
    p = pos_now()
    if p is None:
        return None, "★verified=error✗★：读不到 Bot 坐标"
    near = abs(p[0] - float(x)) <= 1.4 and abs(p[2] - float(z)) <= 1.4 and abs(p[1] - float(y)) <= 2.0
    if near:
        return True, "★verified=true✗★：实测 (%0.2f,%0.2f,%0.2f) 就在目标附近 ✓" % (p[0], p[1], p[2])
    return False, ("★verified=false ✗ 实测 (%0.2f,%0.2f,%0.2f) ✗ 离目标 (%s,%s,%s) 还差✗★"
                   % (p[0], p[1], p[2], x, y, z))


def v_equip(a):
    """★换手持物✗★：★独立读数是 `dshdigest` 的 `held=`✗★（★不是听 `dshequip` 自述✓★）"""
    want = str(a.get("item") or "").split(":")[-1]
    if not want:
        return None, "★verified=unavailable✗★：这次没给 item ✗ 无从复核 ✓"
    from mcp_core import dsh
    t = dsh("dshdigest 1", 40.0) or ""
    m = re.search(r"held=([^\s]+)", t)
    held = m.group(1) if m else "?"
    if want in held:
        return True, "★verified=true✗★：`held=%s` ✓（含 %s ✓）" % (held, want)
    return False, ("★verified=false ✗ `held=%s` ✗ 与要求的 %s 不一致✗★"
                   "（★换手会被别的动作挤掉 ✗ P33 那一族 ✓★）" % (held, want))


def _peek(x, y, z):
    """★读容器的内容✗★（★懒导入 `mc_mcp` 免得循环 ✓★）⇒ 文本回执（★解析出来的数会**印在判词里**✗
    所以解析错了当场看得见 ✓ P152 ✓）"""
    import mc_mcp as M
    out, _bad = M.t_chest_peek(int(x), int(y), int(z))
    return str(out)


def _count_in(text, item):
    """★从容器回执里数某个物品有几件✗★（★数不到 ⇒ 0 ✓ 并在判词里印出"数到几个"✓★）"""
    short = str(item).split(":")[-1]
    n = 0
    for m in re.finditer(r"([a-z0-9_:\-]+)x(\d+)", text or ""):
        if m.group(1).split(":")[-1] == short:
            n += int(m.group(2))
    return n


def _digest_items():
    """★读背包总件数✗★（★`dshdigest` 的 `items=` ✗ 只取数字✓★）"""
    from mcp_core import dsh
    t = dsh("dshdigest 1", 40.0) or ""
    m = re.search(r"items=(\d+)", t)
    return int(m.group(1)) if m else None


def pre_items(a):
    """★动手前的背包总件数✗★（★`drop_item` 那类"少了几件"的读数要它 ✓★）"""
    return {"items": _digest_items()}


def v_items_delta(a, pre, want):
    """★按"背包少了 n 件"判✗★（★`want` 是要少几件 ✓ 负数＝要少✓★）"""
    if not pre or pre.get("items") is None:
        return None, "★verified=unavailable✗★：没拿到「动手前」的背包数 ✓"
    b0 = pre["items"]
    b1 = _digest_items()
    if b1 is None:
        return None, "★verified=error✗★：事后读不到背包数 ✓"
    if b1 - b0 == want:
        return True, "★verified=true✗★：背包 **%d → %d**（%+d ✓ 期望 %+d ✓）" % (
            b0, b1, b1 - b0, want)
    # ★★据实标注✗★★（2026-10-02 ✓）：★这只证明"东西离手了" ✗
    #   ★**不**证明"它掉在地上看得见"✗★（★那一条另有欠账 ⑪ ✓ 由地面 witnesses 管✓★）
    return False, ("★verified=false ✗ 背包 **%d → %d**（%+d ✗ 期望 %+d✗★）"
                   "⇒ ★这一条**不是它说的那样** ✗ 不许当成功✓★" % (b0, b1, b1 - b0, want))


def pre_chest(a):
    """★动手**之前**先把容器数一遍✗★（★"前后对比"那形态 ✗ 没有它就没法判增量✓★）"""
    return {"at": _peek(a.get("x"), a.get("y"), a.get("z"))}


def _v_chest(a, pre, want_delta):
    if not pre or "at" not in pre:
        return None, "★verified=unavailable✗★：没拿到「动手前」的容器快照 ✓"
    item = a.get("item")
    cnt = int(a.get("count") or 1)
    b0 = _count_in(pre["at"], item)
    b1 = _count_in(_peek(a.get("x"), a.get("y"), a.get("z")), item)
    delta = b1 - b0
    if delta == want_delta * cnt:
        return True, "★verified=true✗★：容器里 %s **%d → %d**（增量 %+d ✓ 期望 %+d ✓）" % (
            str(item).split(":")[-1], b0, b1, delta, want_delta * cnt)
    return False, ("★verified=false ✗ 容器里 %s **%d → %d**（增量 %+d ✗ 期望 %+d✗★）"
                   "⇒ ★这一条**不是它说的那样** ✗ 不许当成功✓★"
                   % (str(item).split(":")[-1], b0, b1, delta, want_delta * cnt))


def v_chest_put(a, pre=None):
    return _v_chest(a, pre, +1)


def v_chest_take(a, pre=None):
    return _v_chest(a, pre, -1)


PRE = {
    "chest_put": pre_chest,
    "chest_take": pre_chest,
    "chest_put_many": pre_chest,
    "chest_take_many": pre_chest,
    "drop_item": pre_items,
}


def pre(name: str, args: dict):
    """★框架在动作**之前**调用✗★（★拿不到就返回 None ✗ 判词里会说 unavailable ✓★）"""
    fn = PRE.get(name)
    if fn is None:
        return None
    try:
        return fn(args or {})
    except Exception as e:
        return {"__error__": "%s: %s" % (type(e).__name__, e)}


VERIFIERS = {
    # ★统一签名 `(args, pre)`✗★（★需要"动手前快照"的用得上 ✗ 用不上的忽略它 ✓★）
    "dig_block": lambda a, p: v_dig_block(a),
    "place_block": lambda a, p: v_place_block(a),
    "walk_to": lambda a, p: v_walk(a),
    "walk_route": lambda a, p: v_walk(a),
    "move_relative": lambda a, p: v_walk(a),
    "equip": lambda a, p: v_equip(a),
    "chest_put": lambda a, p: v_chest_put(a, p),
    "chest_take": lambda a, p: v_chest_take(a, p),
    # ★丢物品✗★：★按"背包少了 n 件"判✗★ —— ★只证明**离手** ✗ 不证明**落在地上**（欠账 ⑪ ✓）★
    "drop_item": lambda a, p: v_items_delta(a, p, -max(1, int(a.get("times") or 1))),
}


# ★★"自己就会回读世界"的动作✗★★（★登记它们 ✗ 免得被误报成"没有独立读数"✗★ 2026-10-02 ✓）
#   ★判据✗★：★动作自己的回执里**已经**带 `verified=`✗★（★`jump` 回读 y ✓ `look_at` 回读 yaw/pitch ✓★）
#   或★它的实现里明确拿世界真值自证✗★（`harvest_crop` 收完重扫 ✓ `sift` 读筛子 NBT ✓）
SELF_VERIFIED = {"jump", "look_at", "harvest_crop", "sift",
                 # ★★2026-10-02 补（P2 动作即语言✗）★★：★它们**自己也回读 yaw/pitch**✗★
                 #   ⇒ ★与 `jump`/`look_at` 同一档 ✗ 报 `by-tool`✗ 不是"没人验"✗★
                 "gesture", "point_at",
                 # ★★2026-10-02 清账✗★★：★这两个**本来就在自己逐件对账**✗★ ——
                 #   ★`chest_*_many` 的说明写着"动手前后各读一次容器与背包 ⇒ 逐件对账 ✓
                 #     **对不上绝不报成功**✗"★ ⇒ ★它们属于 `by-tool` ✗ 不属于"没人验"✗★
                 #   （★我先前把它们记成 `unavailable` ✗ ⇒ ★又是"没看它自己怎么写的"✗ ✓★）
                 "chest_put_many", "chest_take_many"}


def drop_witness(receipt, ground_ok=False, items_delta=0):
    """★★"挖掉的东西**掉了没有**"✗★★：★三条尺子合一 ✗ 每条证明的东西不同✗★（欠账 ⑯-② ✓ 2026-10-03 ✓）

    ★为什么需要它✗★（★2026-10-03 实测 ✓）：★在**刚放下的那一格**上测掉落**永远测不准**✗★ ——
      ★假人贴着那格 ✗ 掉落物**当场被捡** ✗ 于是"地上有实体"与"背包件数涨了"**两条同时为假**✗
      而它**其实掉了**✗★ ✓

    ★三条尺子（★能证明什么 ✗ 写清楚✓★）★
      ① ★`dropped=true`（模组的回执 ✗ 来自 `destroyBlock(…, true, …)` 的返回值✓）★
         ⇒ ★证明"**战利品生成了**"✗ ✗ **不**证明"地上有一件能捡的"✗★（★后者是 ⑪ 那条✓★）
      ② ★`ground_ok`（原生命令 `@e[type=item]` ✗ 半径内真有掉落实体✓）★
         ⇒ ★证明"地上有"✗ ✗ 但**贴着那格时会被"已捡走"打成假**✗★
      ③ ★`items_delta`（背包件数变化 ✗ 复用 `pre_items` 那份✓）★
         ⇒ ★证明"东西到手了"✗ ✗ 但**净变化可能为 0**✗（★掉一件又捡回一件✓★）
    ★合并口径✗★：★① 为真 ⇒ 判"**战利品生成了**"（★ok ✓ 但判词**必须写明**它没证明"地上有"✗★）；
      ★③ > 0 ⇒ 判"到手了"（★更强 ✓★）；★三条全假 ⇒ 判红✗★ ✓
    """
    if "dropped=true" in (receipt or ""):
        return True, ("★dropped=true✗★ ⇒ ★判：**战利品生成了**✗★"
                      "（★据实 ✗ 这一条**不**证明「地上有一件能捡的」✗ —— 那是另一条判据 ✓ 见 ⑪✓★）"
                      "%s" % ("；★地上也确有实体✗★ ✓" if ground_ok else "；地上没有实体／已捡走 ✓"))
    if items_delta > 0:
        return True, "★背包 **+%d**✗★ ⇒ ★判：到手了✗★（★比「回执怎么说」更硬 ✓★）" % items_delta
    if ground_ok:
        return True, "★地上有掉落实体✗★ ✓（★回执没给 `dropped=` ✗ 但世界说它掉了✓★）"
    return False, ("★三条尺子**全假**✗★（★回执里没有 `dropped=true` ✗ 地上没有实体 ✗ 背包没涨✓★）"
                   "⇒ ★**不许**当成「掉了」✗★")


def check(name: str, args: dict, pre_state=None):
    """⇒ None（不是改世界动作 ✗ 什么都不加 ✓）或 (True/False/None, note) ✓

    ★`pre_state` 由框架在动作**之前**取好并传进来✗★（★"前后对比"那类读数需要它 ✓★）
    ★`SELF_VERIFIED` 里的动作 ⇒ 报 `by-tool`✗★（★明说"它自己验了" ✗ 与"没人验"**分开**✓★）
    """
    import mcp_policy as P
    acts = P.load().get("mutating") or set()
    if name not in acts:
        return None
    if name in SELF_VERIFIED:
        return (None, "★verified=by-tool✗★（★`%s` **自己回读了世界**✗ ⇒ 看它回执里的 `verified=` ✓★）"
                % name)
    fn = VERIFIERS.get(name)
    if fn is None:
        return (None, "★verified=unavailable✗★（★`%s` 是改世界动作 ✗ 但**还没有独立读数**✗ "
                      "⇒ ★不许当成已验证✓★）" % name)
    try:
        return fn(args or {}, pre_state)
    except Exception as e:
        return (None, "★verified=error✗★（读世界时抛了 %s: %s ✗ ★不静默✗★）"
                % (type(e).__name__, e))


if __name__ == "__main__":
    import mcp_policy as P
    print("★自检✗★：验的是「框架会怎么判」✗ 不连世界（用一个**假读数**替换 ✓）")
    print("  改世界动作 %d 个 ✓ 其中有独立读数的 %d 个 ✓"
          % (len(P.load().get("mutating") or set()), len(VERIFIERS)))
    print("  只读工具（bot_state）⇒ %s" % (check("bot_state", {}),))
    print("  没读数的动作（harvest_crop）⇒ %s" % (check("harvest_crop", {})[1][:70],))
    globals()["scan_cell"] = lambda x, y, z: "air"
    print("  注入假读数（那格=air ✓）⇒ dig_block ⇒ %s"
          % (v_dig_block({"x": 1, "y": 2, "z": 3}),))
    globals()["scan_cell"] = lambda x, y, z: "minecraft:cobblestone"
    print("  注入假读数（那格=cobblestone ✓）⇒ dig_block ⇒ %s"
          % (v_dig_block({"x": 1, "y": 2, "z": 3})[1][:90],))
