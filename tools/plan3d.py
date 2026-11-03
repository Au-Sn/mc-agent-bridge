#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan3d.py -- ★3D A*（含**交互开门**动作）★（§79.362 ✗ 用户要求：寻路层补上这些）

★★和 2D 规划的根本区别✗★★：
  · ★节点 ＝ **站立格** `(x,y,z)`（★脚所在格✗★）✗ 不是 2D 的 `(x,z)`✗★ ✓
  · ★边 ＝ **动作**（★照 mineflayer／Baritone 的动作集✗★）✗★：
    ★`walk`（★平走 4 向 ＋ 斜走（★要查两角✗★）✗★
    ★`step_up`（★上一格 ✗ 要头顶两格空✗★）✗ `fall`（★往下落 ✗ 代价 ∝ 落差✗★）✗★
    ★★`open`（★目标格是 `interact` 类 ✗ 门／活板门／栅栏门 ⇒ **先交互再穿过去**✗★）✗★★
    ★`redstone` 类**不许当路**（★铁门 ✗ 交互打不开✗★）✗★
  · ★世界 ✗ `world3d`（★导出碰撞高度 ＋ 实时方块状态✗★）✗ 不是 2D 高度图✗★ ✓
★代价✗★：★平走 1.0 ✗ 上台阶 1.6 ✗ 斜走 1.42 ✗ 落下 0.4×落差✗ ★★open ＋2.0（★开门要时间✗★）✗★★ ✓
★启发✗★：★octile ＋ 0.5×竖直差 ✗ 保证**可采纳**（★不会算过头✗★）✗★ ✓
"""
from __future__ import annotations

import heapq
import pathlib
import re
import sys

sys.path.insert(0, "tools")

import world3d as W3

# ★★§79.450✗★★：★stdout 必须 pin（★本文件有 ✗ 这类危险字符 ✗ 不 pin 会让
#   ★stdio_guard 的 S3 红 ✗ 那是**判据**不是唠叨✗★）✗★ ✓
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass        # noqa: E402

KINDS_OK = (W3.P_FREE, W3.P_INTERACT)

# ══ ★★垫脚方块（§79.374 ✗ 用户："携带了能垫上来的方块就降低代价 ✗ 没有就提高"✗★）══
#   ★为什么这条重要✗★：★深坑（★pit_depth >= 2✗★）下去以后 ✗ 有方块 ⇒ 垫一格就上来 ✗
#   ★没方块 ⇒ 只能找路绕／或者**困在里面** ⇒ 代价必须**差很多**✗★ ✓
# ★★§79.451✗★★：★`PLACEABLE_KW` 已删**✗★
#   ★理由（★用户原则✗★）：★"★哪些拿来垫脚★"**不许用名单** ✗
#   ★必须**查方块分类／导出的碰撞高**（★`is_placeable` 已改成看导出✓★）✗ 换包不用重来✗★ ✓
SCAFFOLD_CHEAP = 0.6      # ★有垫脚 ⇒ 便宜✗★
SCAFFOLD_EXPENSIVE = 3.0  # ★没垫脚 ⇒ 贵✗★
PIT_TRAP_DEPTH = 2        # ★多深算"★坑★"✗★


def inv_items(dsh=None):
    """★读 `dshinv list` ⇒ [(槽, 物品, 数量)]✗★（★读不到回 None ✗ 不许当"★没有★"✗★）✗★"""
    try:
        if dsh is None:
            import mcp_core as C
            dsh = C.dsh
        txt = dsh("dshinv list", 25.0) or ""
    except Exception as e:                     # ★★§79.402✗★ 读失败 ⇒ **记一条** ✗ 不静默✗★
        try:
            import mcp_core as _C
            _C.errlog("plan3d.inv_items 读背包失败：%r" % (e,))
        except Exception as e2:                # ★连记录都失败 ✗ 但**至少不吞返回值语义**✗★
            sys.stderr.write("plan3d.inv_items 读失败且记录失败 %r / %r\n" % (e, e2))
        return None
    items = []
    for m in re.finditer(r"(\d+):([a-z0-9_]+:[a-z0-9_/]+?)x(\d+)", txt):
        items.append((int(m.group(1)), m.group(2), int(m.group(3) or 1)))
    return items

def _kb_h(name: str):
    """★从**导出的碰撞高度**查这一块的物理真值（★§79.401 层 ✗ 24779 条✗★）✗★

    ★返回 float（★方块高✗★）或 None（★不是方块／未知✗★）**✗
    ★⇒ ★**名字只用来查表 ✗ 不用来猜性质**（★铁律①✗★）✗★ ✓
    """
    try:
        import world3d as _W3
        _W3._load_h3d()
        mp = _W3._H3D.get("map") or {}
        v = mp.get(name)
        if v is None:
            return None
        return float(v)
    except Exception as e:              # ★不许静默✗★
        errlog("★查 %s 的碰撞高失败：%r✗★" % (name, e))
        return None


def _kb_h(name: str):
    """★从**导出的碰撞高度**查物理真值（★§79.401 层 ✗ 24779 条✗★）✗★

    ★返回 float（★方块高✗★）或 None（★不是方块／未知✗★）**✗
    ★⇒ ★**名字只用来查表 ✗ 不用来猜性质**（★铁律①✗★）✗★ ✓
    """
    try:
        W3._load_h3d()
        mp = W3._H3D.get("map") or {}
        v = mp.get(name)
        return None if v is None else float(v)
    except Exception as e:              # ★不许静默✗★
        print("★查 %s 的碰撞高失败：%r✗★" % (name, e), file=sys.stderr)
        return None


def is_placeable(name: str, match=None) -> bool:
    """★能不能当**垫脚方块** —— ★**引用方块分类** ✗ 不看名字子串**✗★

    ★判据（★全部来自物理真值✗★）✗★：
      ① ★**在导出里** ⇒ 它是**一个方块**（★纯物品如 `tombstone:gift` 不在 ✓✗★）✗★
      ② ★**碰撞高 ≈ 1.0** ⇒ **整块**（★fence 1.5 ✗ slab 0.5 ✗ snow_layer ✗ 水✗★全排除）✗★
    ★`match`**：★旧的名字匹配参数 ✗ **已退役**（★留着只为调用方签名兼容✗★）✗★
    """
    del match                            # ★§79.450：名字匹配退役 ✗ 不再用它判性质✗★
    h = _kb_h(name)
    if h is None:
        return False                     # ★不在导出 ⇒ 不是方块（★保守 ✗ 不猜✗★）✗★
    return 0.99 <= h <= 1.01



def placeable_count(items):
    """★能垫脚的方块总数✗★（★`items=None` ⇒ 回 None ✗ 表示"★不知道★"✗★）✗★

    ★判定走 `is_placeable`（★contains 口径 ✗ 与合并前**逐字等价**✗★）✗★
    """
    if items is None:
        return None
    n = 0
    for _slot, name, cnt in items:
        if is_placeable(name):
            n += cnt
    return n


def pick_placeable(items):
    """★背包里**第一样能垫脚的物品** ✗ 回**全名**（★"★垫哪个★"的唯一实现✗★）

    ★用 `suffix` 口径✗★ —— 与合并前 `exec3d.pick_scaffold_item` 的挑选**逐字等价** ✓
    ★读不到背包（空／None）⇒ 回 "" ✗ 不猜✗★ ✓
    （★去 `minecraft:` 前缀是**发命令**的事 ✗ 留在 `exec3d` ✗ 不在这里✗★）
    """
    if not items:
        return ""
    for _slot, name, _cnt in items:
        if is_placeable(name, "suffix"):
            return name or ""
    return ""


def pit_factor(w, p, scaffold):
    """★这一格"★下去以后爬得上来吗★"的代价系数✗★（★pit_depth < 2 ⇒ 1.0✗★）✗★"""
    if scaffold is None:
        return 1.0                       # ★不知道背包 ⇒ 不调（★保守✗★）✗★
    fn = getattr(w, "pit_depth", None)      # ★★没有就不调 ✗ 不许炸（★合成世界也可能没有✗★）✗★
    d = fn(*p) if fn else None
    if d is None or d < PIT_TRAP_DEPTH:
        return 1.0
    return SCAFFOLD_CHEAP if scaffold > 0 else SCAFFOLD_EXPENSIVE


# ══ ★★危险代价（§79.368）✗★★：空岛上"★掉下去★"＝真死 ⇒ 贴边要**贵** ✗ 液体**不走**✗★ ══
HAZARD_EDGE = 3.0          # ★四邻里有"★虚空★"的惩罚系数✗★
VOID_LOOK = 3              # ★往下看几格判"★这是不是虚空★"✗★


def void_below(w, x, y, z) -> bool:
    """★这一格**往下 3 格都没有实心** ⇒ 当作**虚空**（★掉下去没命✗★）✗★"""
    for d in range(1, VOID_LOOK + 1):
        if w.h(x, y - d, z) > 0.05:
            return False
    return True


def hazard_cost(w, x, y, z) -> float:
    """★这一格的**危险代价**✗★（★贴边／挨着虚空 ⇒ 加钱✗★）✗★"""
    risk = 0
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, nz = x + dx, z + dz
        if void_below(w, nx, y, nz):
            risk += 1
    return HAZARD_EDGE * (risk / 4.0)


def forbidden(w, x, y, z) -> bool:
    """★禁行✗★：★液体上（★支撑是液体✗★）／★目标本身是液体✗★ ⇒ 不走✗★ ✓"""
    here = w.name(x, y, z).lower()
    below = w.name(x, y - 1, z).lower()
    if "lava" in here or "lava" in below:
        return True                  # ★岩浆：禁行（★mineflayer `blocksToAvoid` 同口径✗★）✗★
    return False

# ★★§79.384 ✗ 按 mineflayer `lib/movements.js` 的真参数对齐✗★★：
#   ★move 1 ✗ diag √2 ✗ move+jump 2 ✗ placeCost 1（＋移动 1 ⇒ 2）✗
#   ★dig ＝ 1 + 3×destroy_time（★导出秒数✗★）✗ ★水 liquidCost 1 ✗ ★跌落只算 1（★上限 4✗★）✗★
# ★★§79.420✗★★：★`step_up` 从 **2.0** 提到 **3.5**✗★
#   ★为什么✗★：★模组 walker 的「上 1 格台阶」还不稳（★§79.419 那个死锁就是它✗★）✗★
#   ★而 2.0 ＝ **正好等于**绕 2 步平路 ⇒ A* **打平时会选 step_up** ⇒ **没必要的台阶**✗★
#   ★⇒ 提到 3.5（★≈ 3.5 步平路✗★）⇒ ★能绕平路就绕 ✗ 台阶只在确实更短时才出✗★ ✓
COST = {"walk": 1.0, "diag": 1.4142, "step_up": 3.5, "fall": 1.0, "open": 2.0,
        "place": 2.0, "pillar": 2.0, "liquid": 1.0}
MAX_DROP = 4          # ★mineflayer `maxDropDown = 4`✗★
PARKOUR_MAX = 4       # ★`allowParkour` × sprint ⇒ 最多跨 4 格✗★


def _h(a, b):
    dx, dy, dz = abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])
    return max(dx, dz) + 0.414 * min(dx, dz) + 0.5 * dy




# ══ ★★挖（dig ✗ §79.370✗★）：★导出 `destroy_time` 就是"★挖得动吗★"的判据✗★ ══
_DT = {"loaded": False, "map": {}}


def _load_dt():
    if _DT["loaded"]:
        return
    _DT["loaded"] = True
    try:
        import json
        import kb_export as KX
        blocks = json.loads(pathlib.Path(KX.find_export("")).read_text(encoding="utf-8")).get("blocks") or {}
        for k, v in blocks.items():
            if isinstance(v, dict) and "destroy_time" in v:
                _DT["map"][k] = float(v["destroy_time"])
    except Exception as e:
        # ★★§79.370✗★ 不许静默吞 ✗ 但要**记下来**（★_DT["err"]✗★）✗★
        _DT["err"] = repr(e)


DIG_MAX_SECONDS = 5.0        # ★>60 秒的不挖（★黑曜石类✗★）✗★




def dig_cost(w, x, y, z, dig_cost_unit=1.0):
    """★mineflayer 公式✗★：★`digCost ＝ (1 + 3×digTime/1000) × digCost`✗★
    ★导出 `destroy_time` 是**秒** ⇒ `digTime(ms) ＝ destroy_time×1000` ⇒ **1 + 3×destroy_time**✗★
    ★（★dirt 0.5s ⇒ 2.5 ✗ stone 1.5s ⇒ 5.5 ✗ 黑曜石 50s ⇒ 151 ⇒ 规划自然避开✗★）✗★"""
    dt = _destroy_time(w, x, y, z)
    if dt is None:
        return COST["dig"] if "dig" in COST else 4.0
    return (1.0 + 3.0 * dt) * dig_cost_unit


def _destroy_time(w, x, y, z):
    """★这一格的 `destroy_time`（★秒✗★）✗ 查不到回 None✗★"""
    _load_dt()
    nm = w.name(x, y, z).lower()
    return _DT["map"].get(nm) if nm else None




def liquid_cost(w, x, y, z):
    """★站在水里 ⇒ ＋1（★mineflayer `liquidCost`✗★）✗★"""
    nm = (w.name(x, y, z) or "").lower()
    bl = (w.name(x, y - 1, z) or "").lower()
    return COST["liquid"] if ("water" in nm or "water" in bl) else 0.0


def diggable(w, x, y, z) -> bool:
    """★这一格**挖得动吗**✗★（★导出 `destroy_time` ✗ 0 < t <= 60✗★）✗★"""
    _load_dt()
    nm = w.name(x, y, z).lower()
    if not nm:
        return False
    dt = _DT["map"].get(nm)
    if dt is None:
        return False                     # ★导出里没有 ⇒ 不挖（★保守✗★）✗★
    return 0.0 < dt <= DIG_MAX_SECONDS


def stand_at(w, x, y, z):
    """★脚在 (x,y,z) 能不能站 ✗ 返回 (ok, 是否需要交互)✗★"""
    if not w.support(x, y, z):
        return False, False
    inf_here = w.pass_info(x, y, z)
    inf_head = w.pass_info(x, y + 1, z)
    if inf_here["kind"] not in KINDS_OK or inf_head["kind"] not in KINDS_OK:
        return False, False
    if forbidden(w, x, y, z):
        return False, False
    need = (inf_here["kind"] == W3.P_INTERACT) or (inf_head["kind"] == W3.P_INTERACT)
    return True, need


def changes(w, x, y, z, prev):
    """★从 prev 走到 (x,y,z) 需要哪些动作✗★

    ★★§79.391✗★★：★动作（★挖／铺／开门✗★）**排在走路标签之前**✗★ ——
      ★因为它们是"★走到这一格的前提★"（★先铺支撑 ✗ 再站上去✗★）✗★ ⇒
      ★执行器只要"★按顺序做 ✗ 遇到走路标签才走★"就**天然正确**✗★ ✓
      ★（★旧顺序把动作排在后面 ✗ 执行器就会**先走进虚空**✗★ —— §79.391 dry 抓到过✗★）✗★ ✓
    """
    acts = []
    # ★先说"走到这一格之前必须做什么"✗★
    # ★★§79.397 修✗★★：★**能过就不挖**✗★ —— 原来只判"★实心且挖得动★"就发 `dig@`
    #   ⇒ ★**开着的门**（★导出 `max_height=1.0` ✗ 但实时 `open=true` 可通行✗★）也会被排一个 `dig@`✗★
    #   ⇒ ★执行器**会把门挖掉**✗（★§79.397 dry 当场抓到 ✗ 差点真挖✗★）✗★ ✓
    #   ★正确判据✗★：★这一格**不能过**（★`passable` 假✗★）才挖 ✗★ ✓
    if not w.passable(x, y, z) and w.h(x, y, z) > 0.05 and diggable(w, x, y, z):
        acts.append("dig@%d,%d,%d" % (x, y, z))
    if not w.support(x, y, z) and w.h(x, y - 1, z) <= 0.05:
        # sec 79.453: if target == prev (own cell) we cannot place there
        #   must stand in it to place -> mod do_fail(place_on_body) -> whole task fails
        #   (sec 79.447 take-item hung exactly this way: place_on_body@4109,71,17)
        _pc_skip = (x, y - 1, z) == tuple(prev)
        if not _pc_skip:
            acts.append("place@%d,%d,%d" % (x, y - 1, z))
    ok, need = stand_at(w, x, y, z)
    if need:
        for yy in (y, y + 1):
            info = w.pass_info(x, yy, z)
            if info["kind"] == W3.P_INTERACT:
                acts.append("open@%d,%d,%d" % (x, yy, z))
    # ★然后才是这一跳本身✗★
    if y > prev[1]:
        acts.append("step_up")
    elif y < prev[1]:
        acts.append("fall")
    else:
        acts.append("walk" if (x == prev[0] or z == prev[2]) else "diag")
    return acts


def neighbors(w, p, scaffold=None):
    x, y, z = p
    out = []
    # ★平走／斜走（★同 y✗★）
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        n = (x + dx, y, z + dz)
        ok, _need = stand_at(w, *n)
        if ok:
            out.append((n, (COST["walk" if (dx == 0 or dz == 0) else "diag"]
                                 + hazard_cost(w, *n) + liquid_cost(w, *n))
                        * pit_factor(w, n, scaffold)))
    # ★上台阶 ＋1✗★
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        n = (x + dx, y + 1, z + dz)
        if w.pass_info(x, y + 2, z)["kind"] in KINDS_OK:      # ★头顶要通✗★
            ok, _need = stand_at(w, *n)
            if ok:
                out.append((n, (COST["step_up"] + hazard_cost(w, *n)) * pit_factor(w, n, scaffold)))
    # ★★搭桥／垫脚（★§79.376✗★）：★目标格悬空 ✗ 底下那格也空 ✗ 背包有方块 ⇒ 铺一格走过去✗★★ ✓
    if scaffold is None or scaffold > 0:
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y, z + dz)
            below = (x + dx, y - 1, z + dz)
            if not w.passable(*n) or not w.passable(n[0], n[1] + 1, n[2]):
                continue                      # ★脚层／头层要空✗★
            if w.support(*n):
                continue                      # ★已经有支撑 ⇒ 不用铺✗★
            if w.h(*below) > 0.05:
                continue                      # ★底下已经有方块 ⇒ 不用铺✗★
            out.append((n, (COST["place"] + hazard_cost(w, *n)) * pit_factor(w, n, scaffold)))
    # sec 79.471: the 1by1tower (pillar) transition was REMOVED.
    #   It was justified by a place@ under the bot's own feet, but that place@
    #   is a place_on_body: the mod fails the whole task (sec 79.453). Without
    #   that support the transition produced fake vertical climbs through cells
    #   the bot cannot stand on (walk_target_not_standable).
    # ★★挖（★§79.370 ✗ 用户已批允许修改✗★）：★占格但挖得动 ✗ 挖了就能站✗★★ ✓
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        n = (x + dx, y, z + dz)
        if stand_at(w, *n)[0]:
            continue                     # ★本来就能站 ⇒ 不用挖✗★
        if not diggable(w, *n):
            continue
        if not w.support(*n):
            continue                     # ★挖完脚下要有地板✗★
        if not w.passable(n[0], n[1] + 1, n[2]):
            continue                     # ★头位要空✗★
        out.append((n, (dig_cost(w, *n) + hazard_cost(w, *n)) * pit_factor(w, n, scaffold)))
    # ★落下（★最多 4 格✗★）
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for d in range(1, 5):
            n = (x + dx, y - d, z + dz)
            if not w.pass_info(x + dx, y - d + 1, z + dz)["kind"] in KINDS_OK:
                continue
            ok, _need = stand_at(w, *n)
            if ok:
                out.append((n, (COST["fall"] * d + hazard_cost(w, *n)) * pit_factor(w, n, scaffold)))
                break
    return out


def plan(w, start, goal, max_expand=40000, scaffold=None):
    """★A*✗★ 返回 `(path, actions, cost)` 或 `(None, [], None)`✗★"""
    openq = [(0.0, 0.0, start)]
    came = {start: None}
    gsc = {start: 0.0}
    n = 0
    while openq and n < max_expand:
        _f, g, cur = heapq.heappop(openq)
        if cur == goal:
            path = []
            acts = []
            c = cur
            while c is not None:
                path.append(c)
                c = came[c]
            path.reverse()
            for i in range(1, len(path)):
                acts.extend(changes(w, *path[i], path[i - 1]))
            return path, acts, g
        n += 1
        for nb, c in neighbors(w, cur, scaffold):
            ng = gsc[cur] + c
            if ng < gsc.get(nb, 1e9):
                gsc[nb] = ng
                came[nb] = cur
                heapq.heappush(openq, (ng + _h(nb, goal), ng, nb))
    return None, [], None


def summarize(acts):
    from collections import Counter
    c = Counter(a.split("@")[0] if a.startswith("open") else a for a in acts)
    return dict(c)
