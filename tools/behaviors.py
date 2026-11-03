#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""behaviors.py -- 模块 D 行为库：★可注册 ✗ 每个行为带 manifest✗★

规格（§2.5 / §6.5 / §16 M4）：
  * 「行为库 6 条**不够** ✗ 后续**必然增加**」⇒ 做成**注册表** ✗ 加行为只加一个条目✗★
  * 每个行为必须声明：**前置条件／所需工具／是否破坏性／怎么验**✗★
  * ★破坏性行为必须自报 `destructive=True`** ⇒ 判据会拒绝"★偷偷挖★"的行为✗★
  * ★没实现/拿不准的行为要**如实报**（`not_implemented` 或 `plan_only:*`）✗ 不许假装✗★

行为（9/9 已实现；`implemented=True` 是"有真实现"的机器可读标记）：
  go_out_and_back   往返（★已验 §79.480 5/5✗★）
  enter_house       进屋（★借 exec3d 的"开门不挖门"路径 ✗ 独立校验到达✗★）
  leave_house       出屋（同上，目标是屋外点）
  mine_ore          挖矿（★破坏性 ✗ 走 `prims.dig` ⇒ 自动过模块 I 许可链✗★）
  chop_tree         砍树（★破坏性 ✗ 借方块**分类**找原木族 ⇒ 逐格 `prims.dig` ✗ 树叶不碰✗★）
  take_from_chest   从箱子取（★走 `prims.use` ✗ 已验 take_item 9/9✗★）
  store_to_chest    存进箱子（★借容器工具 `dshstore` ＋ 背包真值核对✗★）
  handle_night      夜里做别的事（★用户定：**不强制睡**✗ 只观测＋列可选动作✗★）
  scan_and_report   只读侦察（★不动世界✗★）

★离线可判✗★：所有行为只通过 `prims`（原语/假原语）和可选注入钩子碰世界；
判据用假原语跑，不需要游戏。注入钩子（有就用 ✗ 没有走真实现）：
  `prims.navigate(goal, mission=)`        进屋/出屋的导航（真实现 = `exec3d.execute`，计划里开门不挖门）
  `prims.verify_arrived(goal)`            独立校验到达（真实现 = `verifier.verify_arrived`，只信世界真值）
  `prims.verify_dig(pos)`                 独立校验挖掉（真实现 = `verifier.verify_dig`）
  `prims.find_logs(base, radius)`         找原木族（真实现 = `world3d` 读块 ＋ `blockkb.category_of`）
  `prims.stand_near(pos)`                 找容器旁边站位（真实现 = `exec_task.find_stand_near`）
  `prims.chest_target()` / `prims.held_item()` / `prims.inv_count(item)` / `prims.container_store(...)`
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

REGISTRY = {}
LOG_CATEGORY = "原木"          # ★方块**分类**里的"原木族"（不是名字表 ✗ `blockkb.category_of` 给✗★）


def behavior(name: str, *, destructive: bool, needs=(), verify="", on_real_world=False,
             implemented: bool = True):
    """注册一个行为（★`destructive` 是**必填** ✗ 逼作者想清楚✗★）"""
    def deco(fn):
        REGISTRY[name] = {"name": name, "destructive": bool(destructive),
                          "needs": list(needs), "verify": verify,
                          "on_real_world": bool(on_real_world),
                          "implemented": bool(implemented), "run": fn}
        return fn
    return deco


def _ok(name, **kw):
    return {"ok": True, "behavior": name, **kw}


def _fail(name, why, **kw):
    return {"ok": False, "behavior": name, "why": why, **kw}


def _not_impl(name):
    return _fail(name, "not_implemented")


# ── 注入点／真实现兜底（★同一件事只许一处实现✗★）─────────────────────────
def _hook(prims, name):
    fn = getattr(prims, name, None)
    return fn if callable(fn) else None


def _trace(prims, code, mission="", action="", important=False, detail="", pos=None):
    """★有后果的动作必须留痕✗★（借原语的 reasons 通道 ✗ 没有就写 reasons.py）"""
    fn = _hook(prims, "_reason")
    if fn:
        try:
            return fn(code, pos=pos, mission=mission, action=action,
                      important=important, detail=detail)
        except Exception as exc:              # ★不许静默✗★
            print("behaviors: 留痕失败 %r" % (exc,), file=sys.stderr)
    try:
        import reasons as R
        return R.because(code, mission=mission, pos=pos, action=action,
                         important=important, detail=detail)
    except Exception as exc:                  # ★不许静默✗★
        print("behaviors: 写 reasons 失败 %r" % (exc,), file=sys.stderr)
        return None


def _dsh(prims, cmd, timeout=45.0):
    """借原语的 `dsh` 通道（`Primitives.dsh`）；没有 ⇒ None（★不假装发过✗★）"""
    fn = _hook(prims, "dsh")
    if not fn:
        return None
    try:
        return (fn(cmd, timeout) or "").strip()
    except Exception as exc:                  # ★不许静默✗★
        print("behaviors: dsh(%r) 失败 %r" % (cmd[:40], exc), file=sys.stderr)
        return None


def _bot_cell(prims):
    fn = _hook(prims, "bot_cell")
    if fn:
        try:
            return fn()
        except Exception as exc:
            print("behaviors: bot_cell 失败 %r" % (exc,), file=sys.stderr)
            return None
    try:
        import exec3d as E3
        return E3.bot_cell()
    except Exception as exc:                  # ★不许静默✗★
        print("behaviors: 读假人位置失败 %r" % (exc,), file=sys.stderr)
        return None


def _walk(prims, cell, mission):
    fn = _hook(prims, "walk_to")
    if not fn:
        return {"ok": False, "why": "no_walk_primitive"}
    try:
        return fn(tuple(int(v) for v in cell), mission=mission)
    except Exception as exc:                  # ★不许静默✗★
        return {"ok": False, "why": "walk_exception:%s:%s"
                                    % (type(exc).__name__, str(exc)[:60])}


def _dig(prims, pos, mission):
    fn = _hook(prims, "dig")
    if not fn:
        return {"ok": False, "why": "no_dig_primitive"}
    try:
        return fn(tuple(int(v) for v in pos), mission=mission)
    except Exception as exc:                  # ★不许静默✗★
        return {"ok": False, "why": "dig_exception:%s:%s"
                                    % (type(exc).__name__, str(exc)[:60])}


def _verify_dig(prims, pos):
    fn = _hook(prims, "verify_dig")
    if fn:
        try:
            return fn(tuple(int(v) for v in pos))
        except Exception as exc:              # ★不许静默✗★
            return {"ok": False, "why": "verify_dig_exception:%s" % type(exc).__name__}
    try:
        import verifier as V
        return V.verify_dig(tuple(int(v) for v in pos))
    except Exception as exc:                  # ★不许静默✗★
        return {"ok": False, "why": "verify_unavailable:%s" % type(exc).__name__}


def _verify_arrived(prims, goal):
    fn = _hook(prims, "verify_arrived")
    if fn:
        try:
            return fn(tuple(int(v) for v in goal))
        except Exception as exc:              # ★不许静默✗★
            return {"ok": False, "why": "verify_arrived_exception:%s" % type(exc).__name__}
    try:
        import verifier as V
        return V.verify_arrived(tuple(int(v) for v in goal))
    except Exception as exc:                  # ★不许静默✗★
        return {"ok": False, "why": "verify_unavailable:%s" % type(exc).__name__}


def _navigate(prims, goal, mission=""):
    """★走"开门不挖门"的已验路径✗★（真实现 = `exec3d.execute`；判据里注入假导航）"""
    fn = _hook(prims, "navigate")
    if fn:
        try:
            return fn(tuple(int(v) for v in goal), mission=mission)
        except Exception as exc:              # ★不许静默✗★
            return {"ok": False, "why": "nav_exception:%s:%s"
                                        % (type(exc).__name__, str(exc)[:60])}
    try:
        import exec3d as E3
        ok, rep = E3.execute(tuple(int(v) for v in goal), dry=False)
        return {"ok": bool(ok), "source": "exec3d",
                "why": None if ok else (rep.get("reason") or "not_arrived"),
                "arrived": bool(rep.get("arrived")),
                "bad": [str(b)[:60] for b in (rep.get("bad") or [])[:6]],
                "end": rep.get("end"), "steps": rep.get("steps")}
    except Exception as exc:                  # ★不许静默✗★
        return {"ok": False, "why": "nav_exception:%s:%s"
                                    % (type(exc).__name__, str(exc)[:60]), "source": "exec3d"}


def _inv_total(prims, item=None):
    """背包真值：优先注入 `inv_count(item)`，否则读 `dshinv list`；读不到 ⇒ None（不猜）。"""
    fn = _hook(prims, "inv_count")
    if fn:
        try:
            return fn(item)
        except Exception as exc:              # ★不许静默✗★
            print("behaviors: inv_count 失败 %r" % (exc,), file=sys.stderr)
            return None
    out = _dsh(prims, "dshinv list", 30.0)
    if not out:
        return None
    total = 0
    for m in re.finditer(r"(\d+):([a-z0-9_:.]+)x(\d+)", out):
        if not item or item in m.group(2):
            total += int(m.group(3))
    return total


# ── 已实现：往返／只读侦察／挖矿／取箱 ────────────────────────────────────
@behavior("go_out_and_back", destructive=False, verify="两端 arrived（L4 校验）",
          on_real_world=True)
def go_out_and_back(prims, goal, back, mission=""):
    """★去 goal ✗ 再回 back✗★（★§79.480 已验 5/5✗★）"""
    legs = []
    r1 = _walk(prims, goal, mission)
    legs.append(r1)
    if not r1.get("ok"):
        return _fail("go_out_and_back", "leg1_failed", legs=legs)
    r2 = _walk(prims, back, mission)
    legs.append(r2)
    if not r2.get("ok"):
        return _fail("go_out_and_back", "leg2_failed", legs=legs)
    return _ok("go_out_and_back", legs=legs)


@behavior("scan_and_report", destructive=False, verify="不产生任何 dig/place",
          on_real_world=True)
def scan_and_report(prims, mission=""):
    """★只读侦察✗★（★快照 ＋ 报机器/危险✗★）"""
    try:
        import perceive as P
        snap = P.snapshot(radius=6, caps=1)
    except Exception as exc:        # ★不许静默✗★
        return _fail("scan_and_report", "perceive_failed:" + str(exc)[:60])
    if snap.get("error"):
        return _fail("scan_and_report", snap["error"])
    machines = snap.get("machines") or []
    hazards = snap.get("hazards") or []
    return _ok("scan_and_report",
               machines=[{"pos": m["pos"], "id": m["id"], "facing": m.get("facing")}
                         for m in machines[:5]],
               hazards=[h["pos"] for h in hazards[:5]],
               kinds=len(snap.get("nearby") or {}))


@behavior("mine_ore", destructive=True, needs=("pickaxe",), verify="目标格真值变 air ＋ 掉落进包")
def mine_ore(prims, target, mission=""):
    """★挖一个目标格✗★（★破坏性 ✗ 走 primitives.dig ⇒ 自动过模块 I✗★）"""
    r = _dig(prims, target, mission)
    if not r.get("ok"):
        return _fail("mine_ore", r.get("why") or "dig_failed", step=r,
                     refused_before_dsh=bool(r.get("refused_before_dsh")))
    return _ok("mine_ore", step=r)


@behavior("take_from_chest", destructive=False, verify="物品数增加 ＋ 真值里箱子内容减少")
def take_from_chest(prims, pos, item="", count=1, mission=""):
    """★从箱子取✗★（★已验 take_item 9/9 ✗ 这里走 use 原语✗★）"""
    r = _walk_or_use(prims, pos, mission)
    if not r.get("ok"):
        return _fail("take_from_chest", r.get("why") or "use_failed", step=r)
    return _ok("take_from_chest", step=r)


def _walk_or_use(prims, pos, mission):
    """取箱：优先 `use` 原语（既有口径）；没有 use 原语时如实失败（不发明通道）。"""
    fn = _hook(prims, "use")
    if not fn:
        return {"ok": False, "why": "no_use_primitive"}
    try:
        return fn(tuple(int(v) for v in pos), "up", mission=mission)
    except TypeError:
        try:
            return fn(tuple(int(v) for v in pos), mission=mission)
        except Exception as exc:              # ★不许静默✗★
            return {"ok": False, "why": "use_exception:%s" % type(exc).__name__}
    except Exception as exc:                  # ★不许静默✗★
        return {"ok": False, "why": "use_exception:%s" % type(exc).__name__}


# ── 新实现：进出屋（门只开不挖）──────────────────────────────────────────
def _house_spec(house, kind):
    """`house` 可以是 dict（inside/outside/door/goal/target）或一个坐标（按 kind 当目标）。"""
    if isinstance(house, dict):
        inside = house.get("inside") or house.get("goal") or house.get("target")
        outside = house.get("outside") or house.get("door_outside")
        door = house.get("door")
        return {"inside": tuple(int(v) for v in inside) if inside else None,
                "outside": tuple(int(v) for v in outside) if outside else None,
                "door": tuple(int(v) for v in door) if door else None}
    if isinstance(house, (tuple, list)) and len(house) == 3:
        goal = tuple(int(v) for v in house)
        return {"inside": goal if kind == "enter" else None,
                "outside": goal if kind == "leave" else None, "door": None}
    return None


def _home_goal(prims):
    """进屋的兜底目标：注入 `home_goal()`，否则问 L6 地标（★不认名字 ✗ 问记忆✗★）"""
    fn = _hook(prims, "home_goal")
    if fn:
        try:
            v = fn()
            return tuple(int(x) for x in v) if v else None
        except Exception as exc:              # ★不许静默✗★
            print("behaviors: home_goal 失败 %r" % (exc,), file=sys.stderr)
            return None
    try:
        import memory as M
        rec = M.get("home")
        return tuple(rec["pos"]) if rec else None
    except Exception as exc:                  # ★不许静默✗★
        print("behaviors: 读 home 地标失败 %r" % (exc,), file=sys.stderr)
        return None


def _nav_then_verify(prims, goal, mission, name):
    """★导航（开门不挖门）＋ **独立校验到达**✗★ —— 两条都过才算成。"""
    nav = _navigate(prims, goal, mission)
    if not nav.get("ok"):
        return _fail(name, "nav_failed:" + str(nav.get("why") or "unknown"), nav=nav,
                     goal=list(goal))
    ver = _verify_arrived(prims, goal)
    if not ver.get("ok"):
        return _fail(name, "not_arrived:" + str(ver.get("why") or "unknown"),
                     nav=nav, verify=ver, goal=list(goal))
    return _ok(name, goal=list(goal), nav=nav, verify=ver, door_dig=0)


@behavior("enter_house", destructive=False, needs=("door_or_passage",),
          verify="独立校验脚格=屋内目标 ＋ 门没被挖（只开不挖）")
def enter_house(prims, house=None, mission=""):
    """★进屋✗★：走"开门不挖门"路径（`exec3d` 计划里有 `open@` ✗ 不许 `dig@门`）"""
    spec = _house_spec(house, "enter") or {}
    goal = spec.get("inside") or _home_goal(prims)
    if goal is None:
        return _fail("enter_house", "no_house_target",
                     hint="house={'inside':(x,y,z)} 或至少一个坐标／已登记 home 地标")
    _trace(prims, "enter_house", mission=mission, action="walk",
           detail="door_dig=0 (open, not dig)")
    return _nav_then_verify(prims, goal, mission, "enter_house")


@behavior("leave_house", destructive=False, needs=("door_or_passage",),
          verify="独立校验脚格=屋外目标 ＋ 门没被挖（只开不挖）")
def leave_house(prims, house=None, mission=""):
    """★出屋✗★：目标必须是**屋外点**（不能拿 home 当目标 —— 那是往里走）"""
    spec = _house_spec(house, "leave") or {}
    goal = spec.get("outside")
    if goal is None:
        return _fail("leave_house", "no_leave_target",
                     hint="house={'outside':(x,y,z)}（★屋外点 ✗ 不许拿 home 冒充✗★）")
    _trace(prims, "leave_house", mission=mission, action="walk",
           detail="door_dig=0 (open, not dig)")
    return _nav_then_verify(prims, goal, mission, "leave_house")


# ── 新实现：砍树（分类找原木 ⇒ 逐格 dig ⇒ 树叶不碰）────────────────────────
def _discover_logs_live(base, radius=6):
    """★真实现✗★：`world3d` 读附近方块 ＋ `blockkb.category_of` 只收**原木族**（★不认名字✗★）"""
    try:
        import world3d as W3
        import blockkb as KB
        x, y, z = (int(v) for v in base)
        r = int(radius)
        w = W3.World3D()
        w.fetch_region((x - r, y - 4, z - r, x + r, y + 8, z + r))
        out = []
        for bx in range(x - r, x + r + 1):
            for by in range(y - 4, y + 9):
                for bz in range(z - r, z + r + 1):
                    nm = w.name(bx, by, bz)
                    if not nm:
                        continue
                    if KB.category_of(nm) == LOG_CATEGORY:
                        out.append((bx, by, bz))
        return out, "world3d+category"
    except Exception as exc:                  # ★不许静默✗★
        return [], "classify_failed:%s:%s" % (type(exc).__name__, str(exc)[:60])


def _tree_targets(prims, tree):
    """`tree`：`{"logs":[...]}` 直接用；或 `{"pos":(x,y,z),"radius":n}`／裸坐标 ⇒ 找原木族。"""
    logs, source = None, "given"
    base = None
    radius = 6
    if isinstance(tree, dict):
        if tree.get("logs"):
            logs = tree["logs"]
        base = tree.get("pos") or tree.get("base") or tree.get("target")
        radius = int(tree.get("radius") or 6)
    elif isinstance(tree, (tuple, list)) and len(tree) == 3:
        base = tree
    if logs is None:
        fn = _hook(prims, "find_logs")
        if fn:
            if base is None:
                base = _bot_cell(prims)
            if base is None:
                return [], "no_base"
            try:
                logs, source = fn(tuple(int(v) for v in base), radius), "injected_find_logs"
            except Exception as exc:          # ★不许静默✗★
                return [], "find_logs_exception:%s" % type(exc).__name__
        else:
            base = tuple(int(v) for v in base) if base else _bot_cell(prims)
            if base is None:
                return [], "no_base"
            logs, source = _discover_logs_live(base, radius)
    out = []
    for pos in logs or []:
        try:
            out.append(tuple(int(v) for v in pos))
        except (TypeError, ValueError) as exc:   # ★坏坐标不许静默跳过✗★
            print("behaviors: 原木坐标坏 %r（%r）" % (pos, exc), file=sys.stderr)
    # ★近的优先（先砍得着的）✗ 只取前 64 格（一次行为不做无限事）
    if base is not None:
        bx, by, bz = (int(v) for v in base)
        out.sort(key=lambda p: abs(p[0] - bx) + abs(p[1] - by) + abs(p[2] - bz))
    return out[:64], source


@behavior("chop_tree", destructive=True, needs=("axe",),
          verify="原木格真值变 air ＋ 树叶一格不动 ＋ 掉落有读数")
def chop_tree(prims, tree=None, mission=""):
    """★砍树✗★：找**原木族**（分类）⇒ 逐格 `prims.dig`（过模块 I）⇒ 每格独立校验空气。"""
    targets, source = _tree_targets(prims, tree)
    if not targets:
        return _fail("chop_tree", "no_logs_found", source=source,
                     hint="tree={'logs':[(x,y,z),...]} 或 {'pos':(x,y,z),'radius':n}")
    inv_before = _inv_total(prims)
    steps = []
    for pos in targets:
        r = _dig(prims, pos, mission)
        steps.append({"pos": list(pos), "ok": bool(r.get("ok")), "why": r.get("why")})
        if not r.get("ok"):
            refused = bool(r.get("refused_before_dsh"))
            return _fail("chop_tree",
                         "dig_failed%s:%s" % (":no_dig_zone" if refused else "",
                                              r.get("why") or "unknown"),
                         done=len([s for s in steps if s.get("ok")]),
                         total=len(targets), steps=steps, source=source,
                         refused_before_dsh=refused)
    bad = []
    for pos in targets:
        v = _verify_dig(prims, pos)
        if not v.get("ok"):
            bad.append({"pos": list(pos), "why": v.get("why")})
    if bad:
        return _fail("chop_tree", "not_all_removed", steps=steps, bad=bad[:5],
                     total=len(targets), source=source)
    inv_after = _inv_total(prims)
    drops = {"verified": inv_before is not None and inv_after is not None,
             "before": inv_before, "after": inv_after}
    if drops["verified"]:
        drops["delta"] = int(inv_after) - int(inv_before)
    _trace(prims, "chop_tree", mission=mission, action="dig", important=True,
           detail="logs=%d (leaves untouched)" % len(targets))
    return _ok("chop_tree", total=len(targets), steps=steps, leaves_untouched=True,
               drops=drops, source=source)


# ── 新实现：存进箱子（容器工具 ＋ 背包真值核对）──────────────────────────
def _chest_target(prims, pos):
    if pos is not None:
        return tuple(int(v) for v in pos)
    fn = _hook(prims, "chest_target")
    if fn:
        try:
            v = fn()
            return tuple(int(x) for x in v) if v else None
        except Exception as exc:              # ★不许静默✗★
            print("behaviors: chest_target 失败 %r" % (exc,), file=sys.stderr)
            return None
    try:
        import memory as M
        base = _bot_cell(prims)
        if base is None:
            return None
        rec = M.near("chest", base, radius=48)
        return tuple(rec[0]["pos"]) if rec else None
    except Exception as exc:                  # ★不许静默✗★
        print("behaviors: 找箱子失败 %r" % (exc,), file=sys.stderr)
        return None


def _stand_near(prims, pos):
    fn = _hook(prims, "stand_near")
    if fn:
        try:
            v = fn(tuple(int(x) for x in pos))
            return tuple(int(x) for x in v) if v else None
        except Exception as exc:              # ★不许静默✗★
            print("behaviors: stand_near 失败 %r" % (exc,), file=sys.stderr)
            return None
    try:
        import exec_task as ET
        near, _w = ET.find_stand_near(tuple(int(x) for x in pos))
        return tuple(near) if near else None
    except Exception as exc:                  # ★不许静默✗★
        print("behaviors: exec_task.find_stand_near 失败 %r" % (exc,), file=sys.stderr)
        return None


@behavior("store_to_chest", destructive=False,
          verify="容器 `put=N` ＋ 背包真值减少 N（不信单边回执）")
def store_to_chest(prims, pos=None, item="", count=1, mission=""):
    """★把东西存进箱子✗★：站位 → 走 → `dshstore` → 回执 ＋ 背包真值**双边核对**。"""
    chest = _chest_target(prims, pos)
    if chest is None:
        return _fail("store_to_chest", "no_chest_target",
                     hint="pos=(x,y,z) 或已登记 chest 地标")
    it = (item or "").strip()
    if not it:
        fn = _hook(prims, "held_item")
        if fn:
            try:
                it = str(fn() or "").strip()
            except Exception as exc:          # ★不许静默✗★
                print("behaviors: held_item 失败 %r" % (exc,), file=sys.stderr)
        if not it:
            return _fail("store_to_chest", "no_item_specified",
                         hint="item='minecraft:xxx'（★没指定就不猜手上拿的是什么✗★）")
    try:
        n = int(count)
    except (TypeError, ValueError):
        return _fail("store_to_chest", "bad_count:%r" % (count,))
    if n <= 0:
        return _fail("store_to_chest", "bad_count:%r" % (count,))
    inv_before = _inv_total(prims, it)
    near = _stand_near(prims, chest)
    if near is None:
        return _fail("store_to_chest", "no_stand_cell", chest=list(chest),
                     inv_before=inv_before)
    walked = _walk(prims, near, mission)
    if not walked.get("ok"):
        return _fail("store_to_chest", "walk_failed:" + str(walked.get("why") or "unknown"),
                     stand=list(near), chest=list(chest))
    fn = _hook(prims, "container_store")
    if fn:
        try:
            res = fn(tuple(chest), it, n, mission=mission)
        except Exception as exc:              # ★不许静默✗★
            return _fail("store_to_chest", "container_exception:%s" % type(exc).__name__,
                         stand=list(near), chest=list(chest))
        if not isinstance(res, dict):
            return _fail("store_to_chest", "container_bad_return:%s" % type(res).__name__)
        put = res.get("put")
        reply = str(res.get("reply") or "")[:160]
        why = res.get("why")
    else:
        reply = _dsh(prims, "dshstore %d %d %d %s %d"
                     % (chest[0], chest[1], chest[2], it, n), 40.0)
        if reply is None:
            return _fail("store_to_chest", "no_container_channel",
                         stand=list(near), chest=list(chest))
        m = re.search(r"put=(\d+)", reply)
        w = re.search(r"why=(\w+)", reply)
        put = int(m.group(1)) if m else None
        why = w.group(1) if w else None
    if put is None:
        return _fail("store_to_chest", "no_put_field" + (":" + why if why else ""),
                     reply=reply, stand=list(near), chest=list(chest))
    if int(put) != n:
        return _fail("store_to_chest", "put_mismatch:%d<%d" % (int(put), n),
                     reply=reply, put=int(put), stand=list(near), chest=list(chest))
    inv_after = _inv_total(prims, it)
    inv_check = {"before": inv_before, "after": inv_after, "verified": False}
    if inv_before is not None and inv_after is not None:
        inv_check["verified"] = True
        inv_check["delta"] = int(inv_after) - int(inv_before)
        if inv_check["delta"] > -int(put):
            return _fail("store_to_chest",
                         "inv_mismatch:delta=%d<-%d" % (inv_check["delta"], int(put)),
                         reply=reply, inv=inv_check, stand=list(near), chest=list(chest))
    _trace(prims, "store_to_chest", mission=mission, action="store", important=True,
           pos=chest, detail="item=%s n=%d put=%d" % (it, n, int(put)))
    return _ok("store_to_chest", put=int(put), item=it, count=n, reply=reply,
               inv=inv_check, stand=list(near), chest=list(chest))


# ── 新实现：夜里做别的事（★不强制睡✗★）────────────────────────────────────
NIGHT_START = 13000           # 原版 time：白天 0~12000，黄昏 ~13000，夜 ~18000
NIGHT_END = 23000


def _world_time(prims):
    fn = _hook(prims, "world_time")
    if fn:
        try:
            v = fn()
            if v is None:
                return None               # ★注入源说"读不到" ⇒ 如实当读不到✗★
            if isinstance(v, dict):
                return {"time": int(v.get("time") or 0), "day": v.get("day")}
            return {"time": int(v), "day": None}
        except Exception as exc:              # ★不许静默✗★
            print("behaviors: world_time 失败 %r" % (exc,), file=sys.stderr)
            return None
    out = _dsh(prims, "dshdigest", 30.0)
    if not out:
        return None
    m = re.search(r"\btime=(\d+)", out)
    if not m:
        return None
    d = re.search(r"\bday=(\d+)", out)
    return {"time": int(m.group(1)), "day": d.group(1) if d else None}


@behavior("handle_night", destructive=False,
          verify="只观测／给可选动作 ＋ **不强制睡**（用户定：玩家说睡才睡）")
def handle_night(prims, mission=""):
    """★夜里做别的事✗★：读时间 ⇒ 报"是不是夜里"＋ 列可选动作；**绝不自己跑去睡**。

    ★拿不准就如实说 plan_only ✗ 不许假装做了事✗★：读不到世界时间 ⇒ `plan_only:no_world_time`。
    """
    plan = ["scan_and_report（夜里看一眼四周）",
            "store_to_chest（整理箱子）",
            "idle_look_around（发呆／环顾）"]
    w = _world_time(prims)
    if w is None:
        return _fail("handle_night", "plan_only:no_world_time",
                     forced_sleep=False, plan=plan,
                     hint="注入 world_time() 或 dshdigest 里带 time= 才判得了昼夜")
    tm = int(w.get("time") or 0)
    night = bool(tm >= NIGHT_START or tm < 1000)
    return _ok("handle_night", time=tm, day=w.get("day"), night=night,
               forced_sleep=False, did="none", plan=plan,
               why="not_forced_to_sleep")


# ── 执行入口 ──────────────────────────────────────────────────────────────
def run(name: str, prims, **kw):
    b = REGISTRY.get(name)
    if not b:
        return {"ok": False, "behavior": name, "why": "unknown_behavior"}
    try:
        return b["run"](prims, **kw)
    except Exception as exc:          # ★不许静默✗★
        return {"ok": False, "behavior": name, "why": "exception:" + str(exc)[:80]}


def main(argv) -> int:
    if argv and argv[0] == "--list":
        print("行为库 %d 个（已实现 %d）："
              % (len(REGISTRY), sum(1 for b in REGISTRY.values() if b["implemented"])))
        for n, b in REGISTRY.items():
            print("  %-18s 已实现=%-5s 破坏性=%-5s 需要=%-14s 验=%s"
                  % (n, b["implemented"], b["destructive"],
                     ",".join(b["needs"]) or "-", b["verify"][:40]))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
