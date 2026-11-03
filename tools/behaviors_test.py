#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""behaviors_test.py -- 模块 D 行为库的判据（★离线 ✗ 用假原语✗★）

规格 §2.5 / §6.5 / §16 M4：
  * 可注册（★加行为只加一个条目✗★）
  * 每个行为必须有 manifest：**破坏性／前置／怎么验／是否真实现**✗★
  * ★破坏性行为必须诚实自报**（判据拒绝"★偷偷挖★"✗★）✗
  * ★没实现/拿不准的要**如实报**（`not_implemented` 或 `plan_only:*`）✗ 不许假装✗★

CHECKS
  B1  注册表 9/9 ＋ 每个 manifest 齐全（含 `implemented` 标记）
  B2  go_out_and_back：两段都到 ⇒ ok；第二段失败 ⇒ **如实失败**
  B3  mine_ore：原语返回 `no_dig_zone` ⇒ **如实失败并带上这个原因**（★走了许可链✗★）
  B4  ★破坏性标记诚实★：mine_ore／chop_tree 必须 True；其余 7 条必须 False
  B5  ★9/9 已实现★：`implemented=True` 且 5 条新行为**不再报 not_implemented**、
      缺前置时**如实失败**（边界：真实现 ↔ plan-only／缺输入）
  B6  enter_house／leave_house：开门不挖门（dig 0 次）＋ **独立校验到达**
      （导航说到了但世界真值没到 ⇒ 必须红，不许信自述）
  B7  chop_tree：借**方块分类**找原木族（不写名字表）＋ 逐格 dig ＋ 树叶不碰 ＋
      许可拒绝／校验不过 ⇒ 如实停
  B8  store_to_chest：`put=N` ＋ **背包真值双边核对**；put 不符／背包不符 ⇒ 如实失败
  B9  handle_night：★不强制睡★（零 dig/place/sleep 指令）；读不到时间 ⇒ `plan_only:*` 不冒充
  B10 未知行为 ⇒ `unknown_behavior`（不崩）
  B11 行为抛异常 ⇒ `run` 包住报 `exception:`（不崩）
  B12 ★从 not_implemented 转实现要有证据★：5 条新行为 ok 时必须带**校验证据字段**
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

import behaviors as B          # noqa: E402


class FakePrims:
    """假原语：按脚本回答 ＋ 记录每类调用（★验"调没调／调了几次"✗★）"""

    def __init__(self, walk=None, dig=None, use=None, navigate=None, arrived=None,
                 dig_truth=None, find_logs=None, stand_near=None, world_time=None,
                 chest_target=None, held_item=None, inv_counts=None, dsh=None,
                 container_store=None, bot_cell=None, home_goal=None):
        self.walk = list(walk or [])
        self.dig_r = dig
        self.use_r = use
        self.navigate_r = navigate
        self.arrived_r = arrived
        self.dig_truth = dig_truth
        self.find_logs_r = find_logs
        self.stand_near_r = stand_near
        self.world_time_r = world_time
        self.chest_target_r = chest_target
        self.held_item_r = held_item
        self.inv_counts = list(inv_counts or [])
        self.dsh_r = dsh
        self.container_store_r = container_store
        if container_store is not None:
            # ★只有显式给了假容器通道才注入 ✗ 否则走 behaviors 的真 dshstore 路径✗★
            self.container_store = (
                lambda pos, item, n, mission="": container_store)
        self.bot_cell_r = bot_cell
        self.home_goal_r = home_goal
        self.calls = {"walk": [], "dig": [], "use": [], "dsh": [], "navigate": []}

    # ── 原语 ──
    def walk_to(self, cell, timeout=30.0, mission=""):
        self.calls["walk"].append(tuple(cell))
        if self.walk:
            return self.walk.pop(0)
        return {"ok": True, "kind": "walk", "why": "arrived", "ticks": 10}

    def dig(self, pos, mission=""):
        self.calls["dig"].append(tuple(pos))
        return self.dig_r or {"ok": True, "kind": "dig", "why": "dig_verified", "ticks": 5}

    def use(self, pos, face="up", mission=""):
        self.calls["use"].append(tuple(pos))
        return self.use_r or {"ok": True, "kind": "use", "why": None, "ticks": 3}

    def dsh(self, cmd, timeout=45.0):
        self.calls["dsh"].append(cmd)
        if callable(self.dsh_r):
            return self.dsh_r(cmd)
        return self.dsh_r or ""

    # ── 注入钩子（有就走注入 ✗ 没有就由 behaviors 走真实现）──
    def navigate(self, goal, mission=""):
        self.calls["navigate"].append(tuple(goal))
        if callable(self.navigate_r):
            return self.navigate_r(goal)
        return self.navigate_r or {"ok": True, "why": "arrived", "source": "fake"}

    def verify_arrived(self, goal):
        if callable(self.arrived_r):
            return self.arrived_r(goal)
        return self.arrived_r or {"ok": True, "why": "arrived", "goal": list(goal)}

    def verify_dig(self, pos):
        if callable(self.dig_truth):
            return self.dig_truth(pos)
        return {"ok": True, "why": "dig_verified", "pos": list(pos)}

    def find_logs(self, base, radius=6):
        return list(self.find_logs_r or [])

    def stand_near(self, pos):
        return self.stand_near_r

    def world_time(self):
        if callable(self.world_time_r):
            return self.world_time_r()
        return self.world_time_r

    def chest_target(self):
        return self.chest_target_r

    def held_item(self):
        return self.held_item_r

    def inv_count(self, item=None):
        if callable(self.inv_counts):
            return self.inv_counts(item)
        if self.inv_counts:
            return self.inv_counts.pop(0)
        return None

    def bot_cell(self):
        return self.bot_cell_r

    def home_goal(self):
        return self.home_goal_r


def main() -> int:
    checks = []

    # ── B1 manifest 完整（9/9）──
    bad1 = []
    for n, b in B.REGISTRY.items():
        if not isinstance(b.get("destructive"), bool):
            bad1.append((n, "destructive"))
        if not isinstance(b.get("implemented"), bool):
            bad1.append((n, "implemented"))
        if not (b.get("verify") or "").strip():
            bad1.append((n, "verify"))
        if not callable(b.get("run")):
            bad1.append((n, "run"))
        if b.get("name") != n:
            bad1.append((n, "name"))
        if not isinstance(b.get("needs"), list):
            bad1.append((n, "needs"))
    checks.append(("B1 注册表 9/9 ＋ manifest 齐全（含 implemented）",
                   len(B.REGISTRY) == 9 and not bad1,
                   "%d 个行为 ｜ 不全 %s" % (len(B.REGISTRY), bad1[:3])))

    # ── B2 往返 ──
    ok2a = B.run("go_out_and_back", FakePrims(),
                 goal=(1, 70, 3), back=(1, 70, 1))
    ok2b = B.run("go_out_and_back",
                 FakePrims(walk=[{"ok": True, "why": "arrived"},
                                 {"ok": False, "why": "not_at_goal"}]),
                 goal=(1, 70, 3), back=(1, 70, 1))
    checks.append(("B2 往返：两段都到 ⇒ ok ／ 第二段失败 ⇒ 如实失败",
                   ok2a["ok"] is True and ok2b["ok"] is False and ok2b["why"] == "leg2_failed",
                   "a=%s b=%s(%s)" % (ok2a["ok"], ok2b["ok"], ok2b.get("why"))))

    # ── B3 挖矿被许可层拒 ⇒ 如实带原因 ＋ 确实走了 prims.dig（许可链入口）──
    fp3 = FakePrims(dig={"ok": False, "why": "no_dig_zone", "refused_before_dsh": True})
    r3 = B.run("mine_ore", fp3, target=(1, 70, 3))
    checks.append(("B3 挖矿：原语报 no_dig_zone ⇒ 如实失败（走 prims.dig 许可链）",
                   r3["ok"] is False and r3["why"] == "no_dig_zone"
                   and r3.get("refused_before_dsh") is True
                   and fp3.calls["dig"] == [(1, 70, 3)],
                   "%s ｜ dig 调用=%s" % (r3.get("why"), fp3.calls["dig"])))

    # ── B4 破坏性标记诚实 ──
    expect = {"mine_ore": True, "chop_tree": True,
              "scan_and_report": False, "go_out_and_back": False,
              "take_from_chest": False, "enter_house": False,
              "leave_house": False, "store_to_chest": False, "handle_night": False}
    bad4 = [(n, B.REGISTRY[n]["destructive"]) for n, want in expect.items()
            if n in B.REGISTRY and B.REGISTRY[n]["destructive"] is not want]
    checks.append(("B4 ★破坏性标记诚实（9/9）★", not bad4,
                   str(bad4[:3]) if bad4 else "全部正确"))

    # ── B5 ★9/9 已实现 ＋ 5 条新行为不再 not_implemented（缺前置如实失败）──
    bare = FakePrims(bot_cell=None, home_goal=None, dsh="", inv_counts=[])
    expected_why = {"enter_house": "no_house_target",
                    "leave_house": "no_leave_target",
                    "chop_tree": "no_logs_found",
                    "store_to_chest": "no_chest_target",
                    "handle_night": "plan_only:no_world_time"}
    bad5 = []
    if not all(b["implemented"] for b in B.REGISTRY.values()):
        bad5.append("还有 implemented=False 的")
    for n, want in expected_why.items():
        r = B.run(n, bare)
        if r.get("why") == "not_implemented":
            bad5.append((n, "还报 not_implemented"))
        elif r.get("ok") is not False or r.get("why") != want:
            bad5.append((n, "缺前置没如实失败：ok=%s why=%s" % (r.get("ok"), r.get("why"))))
    checks.append(("B5 ★9/9 已实现：不再 not_implemented，缺前置如实失败★",
                   not bad5, str(bad5[:3]) if bad5 else "5/5 边界正确"))

    # ── B6 进出屋：开门不挖门 ＋ 独立校验到达 ──
    fp6 = FakePrims(navigate={"ok": True, "why": "arrived"}, arrived={"ok": True})
    r6a = B.run("enter_house", fp6, house={"inside": (4120, 71, 27),
                                           "door": (4122, 71, 18)})
    fp6b = FakePrims(navigate={"ok": True, "why": "arrived"},
                     arrived={"ok": False, "why": "not_at_goal"})
    r6b = B.run("enter_house", fp6b, house=(4120, 71, 27))
    fp6c = FakePrims(navigate={"ok": False, "why": "no_path"}, arrived={"ok": True})
    r6c = B.run("leave_house", fp6c, house={"outside": (4110, 71, 8)})
    checks.append(("B6 进出屋：开门不挖门（dig=0）＋ 独立校验（导航说到了不算）",
                   r6a["ok"] is True and r6a.get("door_dig") == 0
                   and r6a["goal"] == [4120, 71, 27]
                   and fp6.calls["dig"] == [] and fp6.calls["navigate"] == [(4120, 71, 27)]
                   and r6b["ok"] is False and str(r6b["why"]).startswith("not_arrived:")
                   and r6c["ok"] is False and str(r6c["why"]).startswith("nav_failed:"),
                   "a=%s b=%s c=%s dig=%d"
                   % (r6a.get("ok"), r6b.get("why"), r6c.get("why"), len(fp6.calls["dig"]))))

    # ── B7 chop_tree：分类找原木／逐格 dig／树叶不碰／拒绝与校验不过如实停 ──
    try:
        import blockkb as KB
        cat_log = KB.category_of("minecraft:oak_log")
        cat_leaf = KB.category_of("minecraft:oak_leaves")
    except Exception as exc:                  # ★不许静默✗★
        cat_log, cat_leaf = "?", "error:%s" % type(exc).__name__
    fp7 = FakePrims(bot_cell=(100, 70, 100))
    r7a = B.run("chop_tree", fp7, tree={"logs": [(100, 71, 100), (100, 72, 100)]})
    fp7b = FakePrims(bot_cell=(100, 70, 100),
                     dig={"ok": False, "why": "no_dig_zone", "refused_before_dsh": True})
    r7b = B.run("chop_tree", fp7b, tree={"logs": [(100, 71, 100), (101, 71, 100)]})
    fp7c = FakePrims(bot_cell=(100, 70, 100),
                     dig_truth=lambda pos: {"ok": False, "why": "dig_not_done"})
    r7c = B.run("chop_tree", fp7c, tree={"logs": [(100, 71, 100)]})
    checks.append(("B7 砍树：分类找原木族 ＋ 逐格 dig ＋ 树叶不碰 ＋ 拒绝/校验不过如实停",
                   cat_log == B.LOG_CATEGORY and cat_leaf != B.LOG_CATEGORY
                   and r7a["ok"] is True and r7a["total"] == 2
                   and r7a["leaves_untouched"] is True
                   and len(fp7.calls["dig"]) == 2
                   and r7b["ok"] is False and "no_dig_zone" in r7b["why"]
                   and len(fp7b.calls["dig"]) == 1
                   and r7c["ok"] is False and r7c["why"] == "not_all_removed",
                   "分类=%r/%r ｜ a=%s b=%s c=%s"
                   % (cat_log, cat_leaf, r7a.get("ok"), r7b.get("why"), r7c.get("why"))))

    # ── B8 store_to_chest：put=N ＋ 背包真值双边核对 ──
    st8 = FakePrims(stand_near=(101, 70, 20), inv_counts=[10, 8],
                    dsh='dshstore ok put=2 left=0')
    r8a = B.run("store_to_chest", st8, pos=(100, 71, 20), item="minecraft:dirt", count=2)
    st8b = FakePrims(stand_near=(101, 70, 20), inv_counts=[10, 10],
                     dsh='dshstore ok put=2')
    r8b = B.run("store_to_chest", st8b, pos=(100, 71, 20), item="minecraft:dirt", count=2)
    st8c = FakePrims(stand_near=(101, 70, 20), inv_counts=[10, 8],
                     dsh='dshstore ok put=1')
    r8c = B.run("store_to_chest", st8c, pos=(100, 71, 20), item="minecraft:dirt", count=2)
    checks.append(("B8 存箱：put=2 ＋ 背包 -2 才算成；put 不符／背包不符 ⇒ 如实失败",
                   r8a["ok"] is True and r8a["put"] == 2
                   and r8a["inv"]["verified"] is True and r8a["inv"]["delta"] == -2
                   and any("dshstore" in c for c in st8.calls["dsh"])
                   and r8b["ok"] is False and r8b["why"].startswith("inv_mismatch")
                   and r8c["ok"] is False and r8c["why"] == "put_mismatch:1<2",
                   "a=%s b=%s c=%s" % (r8a.get("ok"), r8b.get("why"), r8c.get("why"))))

    # ── B9 handle_night：★不强制睡★ ＋ plan_only 不冒充 ──
    fp9 = FakePrims(world_time={"time": 18000, "day": 12})
    r9a = B.run("handle_night", fp9)
    fp9b = FakePrims(world_time={"time": 6000, "day": 12})
    r9b = B.run("handle_night", fp9b)
    fp9c = FakePrims()                        # 没有时间源
    r9c = B.run("handle_night", fp9c)
    cmds9 = " ".join(fp9.calls["dsh"] + fp9c.calls["dsh"]).lower()
    checks.append(("B9 handle_night：夜里也只报选择不睡；无时间源 ⇒ plan_only",
                   r9a["ok"] is True and r9a["night"] is True
                   and r9a["forced_sleep"] is False
                   and r9b["ok"] is True and r9b["night"] is False
                   and r9c["ok"] is False and r9c["why"] == "plan_only:no_world_time"
                   and fp9.calls["dig"] == [] and "sleep" not in cmds9,
                   "夜=%s/昼=%s 无源=%s" % (r9a.get("night"), r9b.get("night"),
                                            r9c.get("why"))))

    # ── B10 未知行为 ──
    r10 = B.run("does_not_exist", FakePrims())
    checks.append(("B10 未知行为 ⇒ unknown_behavior",
                   r10["ok"] is False and r10["why"] == "unknown_behavior", str(r10.get("why"))))

    # ── B11 异常被包住 ──
    def boom(prims, **kw):
        raise RuntimeError("boom")
    B.REGISTRY["_boom"] = {"name": "_boom", "destructive": False, "needs": [],
                           "verify": "x", "on_real_world": False,
                           "implemented": True, "run": boom}
    r11 = B.run("_boom", FakePrims())
    B.REGISTRY.pop("_boom", None)
    checks.append(("B11 行为抛异常 ⇒ run 包住",
                   r11["ok"] is False and str(r11["why"]).startswith("exception:"),
                   str(r11.get("why"))[:50]))

    # ── B12 ★转实现要有证据字段★（ok 不能只是一个布尔）──
    evid12 = {
        "enter_house": B.run("enter_house", FakePrims(
            navigate={"ok": True}, arrived={"ok": True}), house=(4120, 71, 27)),
        "leave_house": B.run("leave_house", FakePrims(
            navigate={"ok": True}, arrived={"ok": True}), house={"outside": (4110, 71, 8)}),
        "chop_tree": r7a,
        "store_to_chest": r8a,
        "handle_night": r9a,
    }
    bad12 = []
    need = {"enter_house": ("nav", "verify"), "leave_house": ("nav", "verify"),
            "chop_tree": ("steps", "total"), "store_to_chest": ("put", "inv"),
            "handle_night": ("forced_sleep", "did")}
    for n, r in evid12.items():
        for k in need[n]:
            if k not in r:
                bad12.append((n, "缺 " + k))
    checks.append(("B12 ★从 not_implemented 转实现要有证据★（ok 不只是一个布尔）",
                   not bad12, str(bad12[:3]) if bad12 else "5/5 都带证据字段"))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:130]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => behaviors 有红（%d 项不对）" % bad)
        print("BEHAVIORS ok=0 bad=%d" % bad)
        return 1
    print("  => behaviors 全绿（9/9 真实现 ✗ 破坏性标记诚实 ✗ 缺前置如实失败 ✗ 转实现有证据）")
    print("BEHAVIORS ok=1 checks=%d registered=%d"
          % (len(checks), len(B.REGISTRY)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
