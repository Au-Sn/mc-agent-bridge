#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""soak_suite_test.py -- ★soak_suite 的离线判据★（2026-11-02 ✓ 不需要游戏 ✓ 秒级 ✓）

WHY（这是"判据先自检能红"那一环 ✗ 见 30-verify §4.3 / 项目 falsify 口径 ✓）：
  soak_suite 是 D3 的**唯一证人口** ✗ 如果它自己会"怎么都绿" ⇒ 3 小时白跑 ✗
  ⇒ 这份 test 用一个**假世界**（FakeWorld：可注入死亡/掉血/丢物/模式漂移/事件环丢事件/
    世界刻停走/放挖/走路）把判定链整条跑一遍，验四件事：
    ① 硬失败判定（死亡／丢物／坠 y>=2／非 survival／ERR）**注入必须红**；
    ② 事件 oracle 是**增量**（cursor 单调、同一事件只计一次、丢事件必须报 INCONCLUSIVE）；
    ③ INCONCLUSIVE 口径（测不了**绝不**算 PASS；退出码 2）；
    ④ scorecard 自洽（字段齐；verdict/exit 可由 hard/inc 重算；full_bar 由**动作调用数**
       算出来（不含 oracle drain），短跑不许冒充满档；证据文件真的在盘上）。
  另加**反证（canary）**：临时把某一条判据"关掉"⇒ 同一注入**不再红** ✗
  ⇒ 证明"红"确实来自那条判据（不是测试自己写死了一个红 ✗）。

★不许写死本包的运行数字✗★：全部用**自己造的数**（假锚点 100,71,100、假调用门槛等）；
  断言只校验"关系"（如 `full_bar == (calls_action >= max_calls)`），不校验"上次跑了几次"。

CHECKS（分组）：
  A 解析层        A1~A6
  B 硬失败判定    B1~B6（含 B7 变体：同一硬失败只留一条+计数）
  C oracle        C1~C3（增量/去重/丢事件/世界刻停走）
  D INCONCLUSIVE  D1~D6（桥断/非 survival/无方块/没压到/世界停/死亡必须是 FAIL）
  E scorecard     E1~E7（自洽/PASS/证据/full_bar/短跑不冒充/3min 计划）
  F d3_soak 迁移  F1（直连、不许再 channel、保留 idle 语义）
  G canary 自检   G1~G3（关掉判据 ⇒ 注入不再红）

用法：py tools/soak_suite_test.py        # 0=全绿；1=有红
"""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import soak_suite as S  # noqa: E402

ANCHOR = (100, 71, 100)              # ★假锚点（不是本包真实测试区的数字）✗
POS = (100.3, 70.94, 100.7)
GROUND_Y = 70
D3_SOAK = ROOT / "tools" / "d3_soak.py"


# ══════════════════════════════════════════════════════════════════════════
# 假世界：一个够小的服务器（回执格式与模组一致；可注入各种身体事故）
# ══════════════════════════════════════════════════════════════════════════

class FakeClock:
    def __init__(self, t0: float = 1_762_000_000.0):
        self.t = float(t0)

    def time(self) -> float:
        return self.t

    def sleep(self, dt: float):
        self.t += max(0.0, float(dt))


class FakeWorld:
    def __init__(self, pos=POS, mode="survival", items=32, item="minecraft:dirt",
                 anchor=ANCHOR, day=373, tod=2192):
        self.pos = [float(v) for v in pos]
        self.hp = 20.0
        self.food = 20
        self.mode = mode
        self.onground = True
        self.tick_total = day * 24000 + tod
        self.inv = {item: int(items)} if items else {}
        self.ground_y = GROUND_Y
        self.blocks = {}                 # 本套件放下去的方块
        self.events = []
        self.seq = 500
        self.idle_humanoid = False
        self.idle_radius = 6
        self.strolls = 0
        self.looks = 0
        self.auto_eat = False
        self.walk_task = None
        self.unreachable = False
        self.place_works = True
        self.pickup_works = True
        self.drop_on_ground = False      # True ⇒ 掉落物留在原地，走近才捡（测捡回策略）
        self.ground_items = []           # [{"item":..., "pos":(x,y,z)}]
        self.pickup_radius = 0.9         # 假拾取半径（相邻格 1.2 不自动捡 ⇒ 要走近）
        self.stuck = False               # True ⇒ 走路回执说 reachable 但人不动（模拟卡死）
        self.frozen = False              # True ⇒ 世界刻不前进（模拟暂停/静默停摆）
        self.cmd_count = 0
        self.plan = []                   # [(after_cmd_n, fn(world)), ...] 注入
        self.rng = random.Random(11)
        self.digest_override = None
        self.drops = 0
        self.noise_rate = 0.0            # 事件/秒（模拟 2.55.1 的 yaw 洪水）
        self.noise_movement_only = False  # True ⇒ 只在"走路"时冒噪声（模拟模组走路写 yaw）
        self._idle_acc = 0.0
        self.anchor = tuple(anchor)

    # ── 世界真值 ────────────────────────────────────────────────────────
    def items(self) -> int:
        return sum(v for v in self.inv.values() if v > 0)

    def block_at(self, x, y, z):
        if (x, y, z) in self.blocks:
            return self.blocks[(x, y, z)]
        if y == self.ground_y:
            return "minecraft:grass_block"      # 假世界：一层平地
        return "minecraft:air"

    def feet_cell(self):
        return S.cell_of(self.pos)

    def emit(self, kind, data=""):
        self.seq += 1
        self.events.append({"seq": self.seq, "kind": kind, "data": data})
        while len(self.events) > 400:
            self.events.pop(0)

    # ── 回执 ────────────────────────────────────────────────────────────
    def digest_text(self) -> str:
        if self.digest_override is not None:
            return self.digest_override
        kinds = sum(1 for v in self.inv.values() if v > 0)
        items = self.items()
        free = max(0, 36 - kinds)
        return ("dshdigest reason=ok name=Bot pos=%.2f,%.2f,%.2f yaw=0.0 pitch=0.0 "
                "hp=%.1f food=%d sat=5.0 xp=0 mode=%s onground=%s dim=minecraft:overworld "
                "time=%d day=%d held=none inv[x]kinds=%d,items=%d,free=%d,sel=0 "
                "ents=0 hostiles=0 nearest=none drops=%d look=minecraft:grass_block@up/1.00"
                % (self.pos[0], self.pos[1], self.pos[2], self.hp, self.food, self.mode,
                   str(self.onground).lower(), self.tick_total % 24000,
                   self.tick_total // 24000, kinds, items, free, self.drops))

    def events_text(self, since) -> str:
        since = -1 if since is None else int(since)
        rows = [e for e in self.events if e["seq"] > since]
        show = rows[-40:]
        head = "dshevents watched=Bot total=%d new=%d cursor=%d" % (
            self.seq, len(rows), self.seq)
        return head + "".join(" | #%d %s %s" % (e["seq"], e["kind"], e["data"])
                              for e in show)

    def scan_text(self, cell) -> str:
        x, y, z = cell
        b = self.block_at(x, y, z)
        air = 1 if b == "minecraft:air" else 0
        solid = 0 if air else 1
        return ("dshscan box=%d,%d,%d..%d,%d,%d tick=%d hash=1 vol=1 solid=%d air=%d "
                "kinds=1 matched=0 shown=0 page=1/1 us=1 counts[%s:1] "
                "cells[pass a match= to list cells]"
                % (x, y, z, x, y, z, self.tick_total, solid, air, b))

    def inv_text(self) -> str:
        parts = ["dshinv list selected=0 =>"]
        n = 0
        slots = 0
        for it, c in sorted(self.inv.items()):
            if c > 0:
                parts.append(" %d:%sx%d" % (slots, it, c))
                n += 1
            slots += 1
        parts.append(" (%d used)" % n)
        return "".join(parts)

    def _step_walk(self):
        """假世界的走路推进（sleep / status 都会推一步；真实模组是异步 tick 走）"""
        if self.stuck:
            return                       # ★模拟"回执说 reachable，人却不动"✗★
        t = self.walk_task
        if t is None or t["done"]:
            return
        tx, ty, tz = t["target"]
        dx, dz = (tx + 0.5) - self.pos[0], (tz + 0.5) - self.pos[2]
        dist = math.hypot(dx, dz)
        if dist <= 2.0:
            self.pos[0] = tx + 0.5
            self.pos[2] = tz + 0.5
            t["done"] = True
            t["result"] = "reached"
            self.emit("walk_done", "result=reached at=%.2f,%.2f,%.2f want=%d,%d,%d "
                      "dist=0.10 mode=auto ticks=20 detours=0 step_downs=0 pillar=0"
                      % (self.pos[0], self.pos[1], self.pos[2], tx, ty, tz))
        else:
            self.pos[0] += dx / dist * 2.0
            self.pos[2] += dz / dist * 2.0
        self._try_pickup()

    def walk_status_text(self) -> str:
        t = self.walk_task
        if t is None:
            return "dshwalk status=none (no active or recent walk)"
        if not t["done"]:
            self._step_walk()
        at = "%.2f,%.2f,%.2f" % tuple(self.pos)
        if t["done"]:
            return ("dshwalk status=done target=%d,%d,%d at=%s dist=0.10 mode=auto "
                    "result=%s ticks=20 detours=0 step_downs=0 sprint=no path=4/4 "
                    "replans=0 reachable=true next=- in_water=false why=none"
                    % (t["target"][0], t["target"][1], t["target"][2], at, t["result"]))
        dist = math.hypot(t["target"][0] + 0.5 - self.pos[0],
                          t["target"][2] + 0.5 - self.pos[2])
        return ("dshwalk status=running target=%d,%d,%d at=%s dist=%.2f mode=auto "
                "result=- ticks=20 detours=0 step_downs=0 sprint=no path=1/4 "
                "replans=0 reachable=true next=- in_water=false why=none"
                % (t["target"][0], t["target"][1], t["target"][2], at, dist))

    def start_walk(self, target) -> str:
        if self.unreachable:
            return ("dshwalk start to=(%d,%d,%d) exact=false budget_ms=10000 from=%.2f,%.2f,%.2f "
                    "path=0 reachable=false nearest=%d,%d,%d"
                    % (target[0], target[1], target[2], self.pos[0], self.pos[1],
                       self.pos[2], target[0], target[1], target[2]))
        self.walk_task = {"target": tuple(target), "done": False, "result": "reached"}
        self.emit("walk_start", "to=%d,%d,%d exact=false ms=10000 from=%.2f,%.2f,%.2f "
                  "path=4 reachable=true nearest=-"
                  % (target[0], target[1], target[2], self.pos[0], self.pos[1], self.pos[2]))
        return ("dshwalk start to=(%d,%d,%d) exact=false budget_ms=10000 from=%.2f,%.2f,%.2f "
                "path=4 reachable=true nearest=-"
                % (target[0], target[1], target[2], self.pos[0], self.pos[1], self.pos[2]))

    def stop_walk(self) -> str:
        if self.walk_task is not None and not self.walk_task["done"]:
            self.walk_task["done"] = True
            self.walk_task["result"] = "stopped_by_agent"
            self.emit("walk_done", "result=stopped_by_agent at=%.2f,%.2f,%.2f pillar=0"
                      % tuple(self.pos))
        return "dshwalk stop: nothing to stop" if self.walk_task is None else \
            "dshwalk stop at=%.2f,%.2f,%.2f" % tuple(self.pos)

    # ── 命令分发 ────────────────────────────────────────────────────────
    def handle(self, cmd: str, timeout: float = 20.0) -> str:
        out = self._handle(cmd, timeout)
        self._try_pickup()
        return out

    def _try_pickup(self):
        """掉落物在原地：走近（<=1.6 格）才自动捡（模拟真实拾取半径）"""
        keep = []
        for it in self.ground_items:
            dx = it["pos"][0] - self.pos[0]
            dz = it["pos"][2] - self.pos[2]
            if math.hypot(dx, dz) <= self.pickup_radius:
                self.inv[it["item"]] = self.inv.get(it["item"], 0) + 1
                self.emit("inv", "delta=+1 items=%d held=%s"
                          % (self.items(), it["item"]))
            else:
                keep.append(it)
        self.ground_items = keep

    def _handle(self, cmd: str, timeout: float = 20.0) -> str:
        cmd = (cmd or "").strip()
        self.cmd_count += 1
        self._run_plan()
        try:
            if cmd.startswith("dshdigest"):
                return self.digest_text()
            if cmd == "dshevents":
                return self.events_text(None)
            if cmd.startswith("dshevents "):
                return self.events_text(int(cmd.split()[1]))
            if cmd == "dshver":
                return ("dshver version=2.55.1 features=scan,digest,look,walk,events,"
                        "auto,map,path,http autoeat=false idle=false")
            if cmd == "dshauto" or cmd.startswith("dshauto "):
                return ("dshauto eat=%s minfood=14 idle=false (idle defaults OFF)"
                        % str(self.auto_eat).lower())
            if cmd == "dshidle status" or cmd == "dshidle":
                return ("dshidle humanoid=%s radius=%d quiet_ticks=300 anchor=%.1f,%.1f,%.1f "
                        "looks=%d strolls=%d lines=0 heard=0 replied=0 greeted=0 "
                        "autoeat=false idlelook=false"
                        % (str(self.idle_humanoid).lower(), self.idle_radius,
                           self.pos[0], self.pos[1], self.pos[2], self.looks, self.strolls))
            if cmd == "dshidle on":
                self.idle_humanoid = True
                self.emit("humanoid", "on radius=%d" % self.idle_radius)
                return "dshidle humanoid=true radius=%d" % self.idle_radius
            if cmd == "dshidle off":
                self.idle_humanoid = False
                self.emit("humanoid", "off")
                return "dshidle humanoid=false radius=%d" % self.idle_radius
            if cmd.startswith("dshidle radius "):
                self.idle_radius = int(cmd.split()[2])
                return "dshidle humanoid=%s radius=%d" % (
                    str(self.idle_humanoid).lower(), self.idle_radius)
            if cmd == "dshinv list":
                return self.inv_text()
            if cmd == "dshwalk":
                return self.walk_status_text()
            if cmd == "dshwalk stop":
                return self.stop_walk()
            if cmd.startswith("dshwalk "):
                parts = cmd.split()
                target = (int(parts[1]), int(parts[2]), int(parts[3]))
                return self.start_walk(target)
            if cmd.startswith("dshscan "):
                ints = [int(v) for v in cmd.split()[1:]]
                if len(ints) == 6:
                    return self.scan_text((ints[0], ints[1], ints[2]))
                return "ERR:test_bad_scan"
            if cmd.startswith("dshplace "):
                return self.do_place(cmd)
            if cmd.startswith("dshdig "):
                return self.do_dig(cmd)
            return "dsh?: unknown %s" % cmd[:60]
        except Exception as exc:          # ★假世界自己坏了要大声✗★
            return "ERR:fake_world:%s:%s" % (type(exc).__name__, exc)

    def _run_plan(self):
        while self.plan and self.cmd_count >= self.plan[0][0]:
            _, fn = self.plan.pop(0)
            fn(self)

    def do_place(self, cmd: str) -> str:
        x, y, z = (int(v) for v in cmd.split()[1:4])
        item = cmd.split('"')[1] if '"' in cmd else "minecraft:dirt"
        b = self.block_at(x, y, z)
        if not self.place_works or b != "minecraft:air":
            return 'dshplace FAIL pos=%d,%d,%d why=test_refused' % (x, y, z)
        self.blocks[(x, y, z)] = item
        if self.inv.get(item, 0) > 0:
            self.inv[item] -= 1
        self.emit("mut", "pos=%d,%d,%d was=minecraft:air now=%s" % (x, y, z, item))
        self.emit("inv", "delta=-1 items=%d held=%s" % (self.items(), item))
        return 'dshplace pos=%d,%d,%d item=%s placed=%s ok' % (x, y, z, item, item)

    def do_dig(self, cmd: str) -> str:
        x, y, z = (int(v) for v in cmd.split()[1:4])
        b = self.blocks.pop((x, y, z), None)
        if b is None:
            return "dshdig FAIL pos=%d,%d,%d why=already_air" % (x, y, z)
        if self.pickup_works:
            self.inv[b] = self.inv.get(b, 0) + 1
            self.emit("inv", "delta=+1 items=%d held=%s" % (self.items(), b))
        elif self.drop_on_ground:
            # 掉落物留在原地：要走近才捡得到（真实拾取半径 ~1 格）
            self.ground_items.append({"item": b, "pos": (x + 0.5, y + 0.2, z + 0.5)})
        self.emit("mut", "pos=%d,%d,%d was=%s now=minecraft:air" % (x, y, z, b))
        return "dshdig pos=%d,%d,%d now=minecraft:air drops=1 ok" % (x, y, z)


class FakeRuntime:
    """假时钟 + 假世界联动：sleep 会推进世界刻（除非 frozen）并让 idle 溜达"""

    def __init__(self, clock: FakeClock, world: FakeWorld):
        self.clock = clock
        self.world = world

    def sleep(self, dt: float):
        self.clock.sleep(dt)
        w = self.world
        if not w.frozen:
            w.tick_total += int(round(float(dt) * 20.0))
        if w.noise_rate > 0.0:            # 洪水：按速率补事件（模拟 yaw_write 每 tick 报）
            active = True
            if w.noise_movement_only:
                active = bool(w.walk_task is not None and not w.walk_task["done"])
            if active:
                for _ in range(int(round(w.noise_rate * float(dt)))):
                    w.emit("yaw_write", "handler=external")
        w._step_walk()                    # 真实模组的走路是异步 tick 推进的
        if w.idle_humanoid:               # 静默窗口里它真的在溜达（半径内小步）
            w._idle_acc += float(dt)
            while w._idle_acc >= 4.0:
                w._idle_acc -= 4.0
                dx, dz = w.rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
                w.pos[0] += dx
                w.pos[2] += dz
                w.strolls += 1


# ══════════════════════════════════════════════════════════════════════════
# 跑一次假 soak
# ══════════════════════════════════════════════════════════════════════════

def params(**over) -> S.SoakParams:
    kw = dict(profile="mixed", minutes=0.5, interval=5.0, radius=3, seed=7,
              max_calls=2000, anchor=ANCHOR)
    kw.update(over)
    return S.SoakParams(**kw)


def run_fake(world: FakeWorld = None, p: S.SoakParams = None, transport=None,
             health_fn=None, clock: FakeClock = None, tmp: Path = None):
    world = world or FakeWorld()
    p = p or params()
    clock = clock or FakeClock()
    rt = FakeRuntime(clock, world)
    tmp = Path(tmp or tempfile.mkdtemp(prefix="soak_test_"))
    logdir = tmp / "logs"
    scp = tmp / "state" / "soak_scorecard.json"
    health = health_fn or (lambda timeout=2.0: "ok dshbridge-http")
    drv = S.Driver(transport=(transport or world.handle), health_fn=health)
    outs = []
    sc = S.run_soak(drv, p, clock=clock.time, sleep=rt.sleep, log_dir=logdir,
                    scorecard_path=scp, out=lambda s: outs.append(s))
    return sc, {"tmp": tmp, "logdir": logdir, "scorecard": scp,
                "driver_calls": drv.calls, "driver_calls_action": drv.calls_action,
                "outs": outs}


def core_unit(p: S.SoakParams = None):
    """造一个已完成基线的 core（★不动 I/O ✗ 直接喂假读数✓★）"""
    p = p or params()
    w = FakeWorld()
    core = S.SoakCore(p)
    d = S.parse_digest(w.digest_text())
    idle = S.parse_idle(w.handle("dshidle status"))
    auto = S.parse_auto(w.handle("dshauto"))
    ver = S.parse_ver(w.handle("dshver"))
    inv = S.parse_inv_list(w.handle("dshinv list"))
    core.set_baseline(d, idle, auto, ver, inv, 500, 1000.0,
                      preconditions={"unit": True})
    return core, d


def digest_variant(d: dict, **over) -> dict:
    out = dict(d)
    out.update(over)
    return out


# ══════════════════════════════════════════════════════════════════════════
# 检查
# ══════════════════════════════════════════════════════════════════════════

def A1_parse_digest():
    w = FakeWorld()
    d = S.parse_digest(w.digest_text())
    assert d is not None, "digest 解析失败"
    assert d["mode"] == "survival" and d["items"] == 32 and d["name"] == "Bot"
    assert abs(d["x"] - POS[0]) < 1e-6 and d["onground"] is True
    assert d["day"] * 24000 + d["time"] > 0
    return "fields ok pos=%s items=%s" % (d["pos"], d["items"])


def A2_parse_digest_rejects():
    assert S.parse_digest("ERR:no_bot") is None
    assert S.parse_digest("dshdigest reason=ok name=Bot") is None
    assert S.parse_digest("") is None
    return "ERR/缺字段均拒绝"


def A3_parse_events_increment():
    text = ("dshevents watched=Bot total=7 new=2 cursor=7"
            " | #6 inv delta=-1 items=31"
            " | #7 bot_died phase=enter who=Bot")
    ev = S.parse_events(text, 5)
    assert ev["complete"] is True and ev["gap"] == 0
    assert ev["cursor"] == 7 and ev["new"] == 2 and ev["shown"] == 2
    assert [e["kind"] for e in ev["events"]] == ["inv", "bot_died"]
    assert S.event_int(ev["events"][0]["data"], "delta") == -1
    return "cursor=7 new=2 complete=True"


def A4_parse_events_gap():
    # since=40；环里可见 #61..#100（40 条）但 new=60 ⇒ 丢了 #41..#60
    body = "".join(" | #%d noise i=%d" % (i, i) for i in range(61, 101))
    text = "dshevents watched=Bot total=100 new=60 cursor=100" + body
    ev = S.parse_events(text, 40)
    assert ev["complete"] is False, "丢事件必须判 incomplete"
    assert ev["gap"] == 20 and ev["truncated"] is True
    return "gap=%d truncated=%s" % (ev["gap"], ev["truncated"])


def A5_parse_scan():
    w = FakeWorld()
    air = S.parse_scan_cell(w.scan_text((101, 71, 101)))
    solid = S.parse_scan_cell(w.scan_text((101, 70, 101)))
    assert air["air"] == 1 and air["solid"] == 0
    assert solid["solid"] == 1 and "minecraft:grass_block" in solid["counts"]
    return "air/solid 世界真值都认得"


def A6_parse_others():
    w = FakeWorld()
    idle = S.parse_idle(w.handle("dshidle status"))
    assert idle is not None and idle["humanoid"] is False and idle["radius"] == 6
    auto = S.parse_auto(w.handle("dshauto"))
    assert auto is not None and auto["eat"] is False
    ver = S.parse_ver(w.handle("dshver"))
    assert ver is not None and ver["version"] == "2.55.1" and "digest" in ver["features"]
    inv = S.parse_inv_list(w.handle("dshinv list"))
    assert inv is not None and inv["items"][0]["item"] == "minecraft:dirt"
    assert inv["items"][0]["count"] == 32
    start = S.parse_walk_start(w.handle("dshwalk 105 71 101"))
    assert start is not None and start["reachable"] is True and start["path"] == 4
    st = S.parse_walk_status(w.handle("dshwalk"))
    assert st is not None and st["status"] == "running", "走 2 格后应还在 running"
    stop_text = w.handle("dshwalk stop")
    assert not str(stop_text).startswith("ERR:"), "walk stop 回执不该是 ERR"
    done = S.parse_walk_status(
        "dshwalk status=done target=105,71,101 at=105.50,70.94,101.50 dist=0.10 "
        "mode=auto result=stopped_by_agent ticks=20 detours=0 step_downs=0 sprint=no "
        "path=4/4 replans=0 reachable=true next=- in_water=false why=none")
    assert done is not None and done["status"] == "done"
    assert done["result"] == "stopped_by_agent"
    return "idle/auto/ver/inv/walk 全解析"


def B1_death_hard():
    w = FakeWorld()
    w.plan = [(10, lambda ww: ww.emit("bot_died", "phase=enter who=Bot"))]
    sc, _ = run_fake(w)
    codes = {h["code"] for h in sc["hard_failures"]}
    assert "H_DEATH" in codes, "bot_died 注入必须触发 H_DEATH（实际 %s）" % codes
    assert sc["verdict"] == "FAIL" and sc["exit_code"] == 1
    return "H_DEATH ⇒ FAIL/1"


def B2_item_loss_hard():
    core, _ = core_unit()
    core.check_items_round("idle", 32, 31)
    assert "H_ITEM_LOSS" in core.hard_codes(), "items 32⇒31 必须红"
    # 已解释消耗（吃了一个）⇒ 允许
    core2, _ = core_unit()
    core2._exp_round = 1
    core2.check_items_round("idle", 32, 31)
    assert "H_ITEM_LOSS" not in core2.hard_codes(), "吃了 1 个而少 1 个不应算丢"
    return "丢物红；吃掉的解释放行"


def B3_fall_hard():
    core, d = core_unit()
    core.observe_sample(1001.0, digest_variant(d, y=d["y"] - 2.5,
                                               pos=(d["x"], d["y"] - 2.5, d["z"])))
    assert "H_FALL" in core.hard_codes(), "y 低 >=2 必须红"
    core2, d2 = core_unit()
    core2.observe_sample(1001.0, digest_variant(d2, y=d2["y"] - 0.5,
                                                pos=(d2["x"], d2["y"] - 0.5, d2["z"])))
    assert "H_FALL" not in core2.hard_codes(), "只低 0.5 格不应红"
    return "降 >=2 红；降 0.5 不红"


def B4_mode_hard():
    core, d = core_unit()
    core.observe_sample(1001.0, digest_variant(d, mode="creative"))
    assert "H_MODE" in core.hard_codes(), "非 survival 必须红"
    return "creative ⇒ H_MODE"


def B5_err_hard():
    core, _ = core_unit()
    rep = S.Reply(cmd="dshdigest 1", ok=False, err="ERR:timeout")
    core.note_error(None, rep)
    assert "H_ERR" in core.hard_codes(), "ERR>0 必须红"
    # preflight 前（未 armed）不算 hard（那是环境不满足 ⇒ INCONCLUSIVE）
    core2 = S.SoakCore(params())
    core2.note_error(None, rep)
    assert not core2.hard, "未 armed 的 ERR 不应进 hard（应走 INCONCLUSIVE）"
    return "armed 后 ERR 红；preflight 前不红"


def B6_dedup():
    core, _ = core_unit()
    ev = S.parse_events("dshevents watched=Bot total=502 new=2 cursor=502"
                        " | #501 bot_died phase=enter"
                        " | #502 bot_died phase=enter", 500)
    core.observe_events(1002.0, ev)
    n1 = len([h for h in core.hard if h["code"] == "H_DEATH"])
    core.observe_events(1003.0, ev)          # 同一条重复喂 ⇒ 不许重复计数
    n2 = len([h for h in core.hard if h["code"] == "H_DEATH"])
    assert core.deaths == 2, "两条不同 seq 的死亡都要计（实际 %d）" % core.deaths
    assert n1 == 1 and n2 == 1, "同类硬失败只留一条明细（+count），不重复堆"
    assert core.hard[0].get("count") == 2
    return "deaths=%d 明细=%d count=%s" % (core.deaths, n2, core.hard[0].get("count"))


def C1_oracle_increment():
    core, _ = core_unit()
    text = "dshevents watched=Bot total=502 new=2 cursor=502 | #501 inv delta=+1 items=33 | #502 bot_died phase=enter"
    ev = S.parse_events(text, 500)
    core.observe_events(1001.0, ev)
    assert core.cursor == 502 and core.deaths == 1
    # 增量：下一轮 since=502，没有新事件 ⇒ 不许再把 #502 算一遍
    ev2 = S.parse_events("dshevents watched=Bot total=504 new=2 cursor=504"
                         " | #503 inv delta=-1 items=32 | #504 mut pos=1,2,3 was=x now=y", 502)
    core.observe_events(1002.0, ev2)
    assert core.deaths == 1, "已计入的死亡事件不许重复计数"
    assert core.cursor == 504 and (1, 2, 3) in core.world_mut
    return "cursor 单调 500→502→504；同一死亡只计一次"


def C2_event_gap_inconclusive():
    core, _ = core_unit()
    body = "".join(" | #%d noise i=%d" % (i, i) for i in range(521, 561))
    ev = S.parse_events("dshevents watched=Bot total=560 new=60 cursor=560" + body, 500)
    core.observe_events(1001.0, ev)
    assert "I_EVENT_GAP" in {i["code"] for i in core.inc}, "丢事件必须 INCONCLUSIVE"
    assert "S_EVENT_GAP" in core.soft_seen
    sc = core.finalize(1002.0, activity={"activity_ok": True}, world={},
                       duration=10, calls=10, paths={})
    assert sc["verdict"] == "INCONCLUSIVE" and sc["exit_code"] == 2
    assert sc["criteria"]["D3a_zero_death"] is False
    return "gap ⇒ INCONCLUSIVE/2，且 D3a 不成立"


def C3_world_stall():
    core, d = core_unit()
    same_tick = digest_variant(d, x=d["x"] + 1.0, pos=(d["x"] + 1.0, d["y"], d["z"]))
    core.observe_sample(1060.0, same_tick)     # 墙钟走了 60s，世界刻没动
    assert "I_WORLD_STALLED" in {i["code"] for i in core.inc}, "世界刻停走必须 INCONCLUSIVE"
    return "停走 60s ⇒ I_WORLD_STALLED"


def D1_bridge_down():
    sc, info = run_fake(health_fn=lambda timeout=2.0: None,
                        transport=lambda c, t: None)
    assert sc["verdict"] == "INCONCLUSIVE" and sc["exit_code"] == 2, \
        "桥不通必须 INCONCLUSIVE/2（实际 %s/%s）" % (sc["verdict"], sc["exit_code"])
    assert not sc["hard_failures"], "桥不通不该记硬失败"
    assert Path(info["scorecard"]).is_file(), "测不了也要留记分卡"
    return "INCONCLUSIVE/2，记分卡仍落盘"


def D2_mode_precondition():
    sc, _ = run_fake(FakeWorld(mode="creative"))
    inc = {i["code"] for i in sc["inconclusive_reasons"]}
    assert "I_NOT_SURVIVAL" in inc, "非 survival 必须 INCONCLUSIVE（不许偷偷改模式）"
    assert sc["verdict"] == "INCONCLUSIVE" and sc["exit_code"] == 2
    assert not sc["hard_failures"]
    return "I_NOT_SURVIVAL / 不自动改"


def D3_no_placeable():
    w = FakeWorld()
    w.inv = {"minecraft:stone_shovel": 1}
    sc, _ = run_fake(w)
    inc = {i["code"] for i in sc["inconclusive_reasons"]}
    assert "I_NO_PLACEABLE" in inc and sc["exit_code"] == 2
    return "没可放方块 ⇒ 测不了/2"


def D4_not_active():
    w = FakeWorld()
    w.unreachable = True           # 走不到 + 别的照旧 ⇒ 混合档"没压到"
    # ★>=3 分钟才会启用"认真压到"的活动门槛✗★（短跑只要求动过 ✓ 口径见 activity_ok）
    sc, _ = run_fake(w, params(minutes=3.0, interval=5.0))
    inc = {i["code"] for i in sc["inconclusive_reasons"]}
    assert "I_NOT_ACTIVE" in inc, "没真的走成/干成必须报没压到（实际 inc=%s）" % inc
    assert sc["verdict"] == "INCONCLUSIVE" and sc["exit_code"] == 2
    return "走不动 ⇒ I_NOT_ACTIVE/2"


def D5_death_is_fail_not_inc():
    w = FakeWorld()
    w.plan = [(10, lambda ww: ww.emit("bot_died", "phase=enter who=Bot"))]
    sc, _ = run_fake(w)
    assert sc["exit_code"] == 1 and sc["verdict"] == "FAIL", "死亡必须是 FAIL/1 不是测不了"
    return "FAIL/1"


def D6_world_frozen():
    w = FakeWorld()
    w.frozen = True
    # idle 静默 30s ⇒ 一次就攒够"停走 >=30s"的证据（门槛见 SoakCore.observe_sample）
    sc, _ = run_fake(w, params(minutes=2.0, interval=30.0))
    inc = {i["code"] for i in sc["inconclusive_reasons"]}
    assert "I_WORLD_STALLED" in inc, "世界停走必须 INCONCLUSIVE（墙钟证据无效）"
    assert sc["exit_code"] == 2
    return "frozen ⇒ I_WORLD_STALLED/2"


def E1_pass_scenario():
    sc, info = run_fake(p=params(minutes=3.0, interval=5.0))
    assert sc["verdict"] == "PASS", "干净假世界 3 分钟混合档必须 PASS（实际 %s：%s）" % (
        sc["verdict"], sc["inconclusive_reasons"] or sc["hard_failures"])
    assert sc["exit_code"] == 0
    assert sc["hard_count"] == 0 and not sc["inconclusive_reasons"]
    assert sc["activity"]["activity_ok"] is True
    assert sc["activity"]["walk_reached"] >= 1
    assert sc["activity"]["place_world_true"] >= 1 and sc["activity"]["dig_world_true"] >= 1
    assert sc["activity"]["idle_rounds"] >= 1
    return "PASS/0 且三档都真出现"


def E2_scorecard_consistent():
    p = params(minutes=1.0, interval=5.0)
    sc, info = run_fake(p=p)
    sp = Path(info["scorecard"])
    assert sp.is_file(), "记分卡没落盘"
    disk = json.loads(sp.read_text(encoding="utf-8"))
    for k in ("schema", "generated_at", "generated_unix", "verdict", "exit_code",
              "profile", "duration_sec", "calls", "calls_action", "calls_oracle",
              "calls_full_bar", "full_bar", "driver",
              "d3_calls_min", "d3_duration_min_sec", "rounds", "activity",
              "hard_failures", "soft_failures", "inconclusive_reasons", "oracle",
              "world", "baseline", "criteria", "evidence", "params", "generated_at"):
        assert k in disk, "scorecard 缺字段：%s" % k
    assert disk["calls_action"] + disk["calls_oracle"] == disk["calls"]
    assert disk["schema"] == S.SCHEMA
    assert disk["profile"] == "mixed"
    # verdict / exit 必须能由 hard/inc 重算出来
    exp = ("FAIL" if disk["hard_failures"]
           else ("INCONCLUSIVE" if disk["inconclusive_reasons"] else "PASS"))
    assert disk["verdict"] == exp and disk["exit_code"] == {"FAIL": 1, "INCONCLUSIVE": 2,
                                                            "PASS": 0}[exp]
    assert disk["hard_count"] == len(disk["hard_failures"])
    assert disk["soft_count"] == sum(disk["soft_codes"].values())
    assert disk["rounds"]["total"] == sum(disk["rounds"]["by_kind"].values())
    # 证据文件在盘上，jsonl 每行都是合法 JSON
    for key in ("jsonl", "run_log"):
        fp = Path(disk["evidence"][key])
        assert fp.is_file(), "证据文件不存在：%s" % fp
    lines = Path(disk["evidence"]["jsonl"]).read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 5, "jsonl 太短（%d 行）" % len(lines)
    types = set()
    for ln in lines:
        rec = json.loads(ln)
        types.add(rec.get("type"))
    assert "call" in types and "sample" in types and "oracle" in types
    assert "baseline" not in types  # 基线记在 scorecard 里；jsonl 只有过程（约定）
    # oracle 游标必须是单调推进的
    assert disk["oracle"]["cursor_end"] >= disk["oracle"]["cursor_start"]
    return "字段齐/verdict 可重算/jsonl %d 行/types=%s" % (len(lines), sorted(types))


def E3_full_bar_honest():
    # ★满档门槛按"动作调用"算 ✗ 不能拿 oracle drain 灌满✗★（冒充满档 = P100 同族）
    p1 = params(minutes=0.5, max_calls=2000)
    sc1, info1 = run_fake(p=p1)
    assert sc1["calls_action"] > 0
    assert sc1["calls_action"] + sc1["calls_oracle"] == sc1["calls"]
    assert sc1["full_bar"] == (sc1["calls_action"] >= p1.max_calls)
    assert sc1["full_bar"] is False, "短跑不许冒充满档"
    # ② 把门槛调小（反证：full_bar 是算出来的，不是写死 2000）
    p2 = params(minutes=0.5, max_calls=5)
    sc2, _ = run_fake(p=p2)
    assert sc2["full_bar"] == (sc2["calls_action"] >= 5) and sc2["full_bar"] is True
    # ③ 但"满 D3 绝对口径"仍必须 false（3h 没跑）
    assert sc2["full_spec_mixed_3h"] is False
    # ④ 计数必须等于 driver 实际调用数（不许自己编）
    assert sc1["calls"] == info1["driver_calls"]
    assert sc1["calls_action"] == info1["driver_calls_action"]
    assert sc1["driver"]["calls"] == info1["driver_calls"]
    assert sc1["driver"]["calls_action"] == info1["driver_calls_action"]
    return ("calls=%d（动作 %d＋oracle %d）/门槛=%d；门槛调小才满档；full_spec 仍 false"
            % (sc1["calls"], sc1["calls_action"], sc1["calls_oracle"], p1.max_calls))


def E4_duration_and_rounds():
    p = params(minutes=1.0, interval=5.0)
    sc, _ = run_fake(p=p)
    assert abs(sc["duration_planned_sec"] - 60.0) < 1e-6
    assert sc["duration_sec"] >= 55.0, "实际时长应接近计划（实际 %.1f）" % sc["duration_sec"]
    assert sc["duration_ok"] is True
    assert sc["rounds"]["total"] >= 3
    kinds = {k for k, v in sc["rounds"]["by_kind"].items() if v > 0}
    assert "idle" in kinds and "walk" in kinds and "work" in kinds, \
        "混合档 1 分钟内三档都该出现（实际 %s）" % kinds
    return "duration=%.1fs rounds=%d kinds=%s" % (sc["duration_sec"],
                                                   sc["rounds"]["total"], sorted(kinds))


def E5_mixed_ratio():
    """调度器：任何前缀都接近 20/30/50（不靠运气 ✗ 短跑也覆盖到三档）"""
    sch = S.MixedSchedule(seed=7)
    kinds = [sch.next_kind() for _ in range(20)]
    got = {k: kinds.count(k) for k in S.MIX}
    assert got == {"idle": 4, "walk": 6, "work": 10}, "20 轮必须正好 4/6/10（实际 %s）" % got
    # 前 5 轮就应该三档都露过面（短跑覆盖）
    first5 = set(kinds[:5])
    assert first5 == {"idle", "walk", "work"}, "前 5 轮要覆盖三档（实际 %s）" % first5
    return "20 轮=4/6/10，前 5 轮覆盖三档"


def F1_d3_soak_migrated():
    assert D3_SOAK.is_file(), "d3_soak.py 不见了"
    text = D3_SOAK.read_text(encoding="utf-8", errors="replace")
    code_lines = [ln.strip() for ln in text.splitlines()]
    # ★看**代码行**（不是注释/文档里的历史说明）✗★
    assert not any(ln.startswith("from channel import") for ln in code_lines), \
        "d3_soak 还有 import channel"
    assert not any(ln.startswith("ch = Channel(") for ln in code_lines), \
        "d3_soak 还在 new Channel（旧 CC 车道）"
    assert not any(ln.startswith("import channel") for ln in code_lines)
    assert ("import direct as D" in text) or ("import direct\n" in text), \
        "d3_soak 没迁到 direct"
    assert "D.post(" in text, "d3_soak 没有真的走 direct.post"
    # 保留 idle 语义：D3a~D3d 判据与 dshidle 开关都还在
    for tok in ("D3a", "D3b", "D3c", "D3d", "dshidle"):
        assert tok in text, "d3_soak 迁移丢了 %s" % tok
    return "direct.post ✓ 无 channel 代码行 ✓ D3a~D3d+dshidle 保留"


# ── G：canary（关掉某条判据 ⇒ 同一注入不再红）────────────────────────────
class _NoDeathCore(S.SoakCore):
    def observe_events(self, now, ev, reply=None):
        super().observe_events(now, ev, reply)
        self.hard = [h for h in self.hard if h["code"] != "H_DEATH"]


class _NoFallCore(S.SoakCore):
    def observe_sample(self, now, d):
        super().observe_sample(now, d)
        self.hard = [h for h in self.hard if h["code"] != "H_FALL"]


class _NoItemLossCore(S.SoakCore):
    def check_items_round(self, kind, start_items, end_items):
        super().check_items_round(kind, start_items, end_items)
        self.hard = [h for h in self.hard if h["code"] != "H_ITEM_LOSS"]


class _NoGapCore(S.SoakCore):
    def observe_events(self, now, ev, reply=None):
        super().observe_events(now, ev, reply)
        self.inc = [i for i in self.inc if i["code"] != "I_EVENT_GAP"]
        self.soft_seen.pop("S_EVENT_GAP", None)


def _patched_run(old_cls, core_cls, world=None, p=None):
    S.SoakCore, saved = core_cls, S.SoakCore
    try:
        return run_fake(world, p)
    finally:
        S.SoakCore = saved


def G1_canary_death():
    w = FakeWorld()
    w.plan = [(10, lambda ww: ww.emit("bot_died", "phase=enter who=Bot"))]
    sc_broken, _ = _patched_run(None, _NoDeathCore, w)
    codes = {h["code"] for h in sc_broken["hard_failures"]}
    assert "H_DEATH" not in codes, "canary 失效：关掉死亡判据后仍然红（说明红来自别处）"
    # 正常判据下同一注入必须红（正反两面都验）
    w2 = FakeWorld()
    w2.plan = [(10, lambda ww: ww.emit("bot_died", "phase=enter who=Bot"))]
    sc, _ = run_fake(w2)
    assert "H_DEATH" in {h["code"] for h in sc["hard_failures"]}
    return "关掉判据 ⇒ 不红；恢复 ⇒ 红（红确实来自 H_DEATH）"


def G2_canary_fall():
    def fall(w):
        w.pos[1] = 67.5
    w = FakeWorld()
    w.plan = [(10, fall)]
    sc_broken, _ = _patched_run(None, _NoFallCore, w)
    assert "H_FALL" not in {h["code"] for h in sc_broken["hard_failures"]}
    w2 = FakeWorld()
    w2.plan = [(10, fall)]
    sc, _ = run_fake(w2)
    assert "H_FALL" in {h["code"] for h in sc["hard_failures"]}
    return "fall 判据可被单独关掉/恢复"


def G3_canary_event_gap():
    def flood(w):
        for i in range(60):
            w.emit("noise", "i=%d" % i)
    w = FakeWorld()
    w.plan = [(10, flood)]
    sc_broken, _ = _patched_run(None, _NoGapCore, w)
    assert "I_EVENT_GAP" not in {i["code"] for i in sc_broken["inconclusive_reasons"]}, \
        "canary 失效：关掉丢事件判据后仍报 I_EVENT_GAP"
    w2 = FakeWorld()
    w2.plan = [(10, flood)]
    sc, _ = run_fake(w2)
    assert "I_EVENT_GAP" in {i["code"] for i in sc["inconclusive_reasons"]}
    return "事件环丢事件判据可被单独关掉/恢复"


def B7_place_consume_explained():
    """自己 place 花掉的 -1 不是丢物（否则软失败会被自己的正常动作刷屏）"""
    core, _ = core_unit()
    ev = S.parse_events("dshevents watched=Bot total=502 new=2 cursor=502"
                        " | #501 inv delta=-1 items=31 held=minecraft:dirt", 500)
    core.observe_events(1001.0, ev)
    assert "S_INV_DROP" in core.soft_seen, "没有在途 place 时 -1 应该记软"
    core2, _ = core_unit()
    core2._pending_place_consumes = 1
    ev2 = S.parse_events("dshevents watched=Bot total=502 new=1 cursor=502"
                         " | #501 inv delta=-1 items=31 held=minecraft:dirt", 500)
    core2.observe_events(1001.0, ev2)
    assert "S_INV_DROP" not in core2.soft_seen, "自己 place 的 -1 被误报成丢物"
    assert core2._pending_place_consumes == 0
    return "在途 place 的 -1 已被解释，不刷软失败"


def H1_flood_adaptive_drain():
    """事件洪水（如 2.55.1 的 yaw 噪声 80 条/秒）下，自适应 drain 必须保住 oracle。"""
    w = FakeWorld()
    w.noise_rate = 80.0
    sc, _ = run_fake(w, params(minutes=1.0, interval=10.0))
    assert sc["oracle"]["gaps"] == 0, \
        "洪水下 oracle 丢了事件（gaps=%s）⇒ 自适应 drain 没保住" % sc["oracle"]["gaps"]
    assert sc["oracle"]["truncated_drains"] == 0, "洪水下出现截断 ⇒ drain 间隔不够密"
    assert sc["oracle"]["noise_events"] > 0, "假世界没真的造出噪声"
    assert sc["calls_oracle"] > 0
    assert "S_EVENT_FLOOD" in sc["soft_codes"], "洪水必须留下软警告（供复核）"
    assert sc["verdict"] == "PASS", "洪水本身不该把 verdict 拉红/测不了（oracle 完整）"
    return ("gaps=0 truncated=0 noise=%d calls_oracle=%d verdict=%s"
            % (sc["oracle"]["noise_events"], sc["calls_oracle"], sc["verdict"]))


def I1_work_headroom():
    """★头顶没净空的格子不许选✗★（2026-11-02 长档第 81 轮真因）"""
    # ① 四邻头顶全堵死 ⇒ 一次都不许放（软警告 + 不许硬失败、不许崩）
    w = FakeWorld()
    feet = w.feet_cell()
    nbs = [(feet[0] + 1, feet[1], feet[2]), (feet[0] - 1, feet[1], feet[2]),
           (feet[0], feet[1], feet[2] + 1), (feet[0], feet[1], feet[2] - 1)]
    for nb in nbs:
        w.blocks[(nb[0], nb[1] + 1, nb[2])] = "minecraft:oak_log"
    sc, _ = run_fake(w, params(profile="work", minutes=1.0, interval=5.0))
    assert "S_WORK_NO_HEADROOM" in sc["soft_codes"], "头顶被堵居然没报警（试了没？）"
    assert sc["activity"]["place_world_true"] == 0, "头顶被堵还放下了方块？"
    assert not sc["hard_failures"], "头顶被堵不该判硬失败（这是选择问题不是身体问题）"
    # ② 只留一个邻格有净空 ⇒ 必须换到那一格放成功
    w2 = FakeWorld()
    feet2 = w2.feet_cell()
    nbs2 = [(feet2[0] + 1, feet2[1], feet2[2]), (feet2[0] - 1, feet2[1], feet2[2]),
            (feet2[0], feet2[1], feet2[2] + 1), (feet2[0], feet2[1], feet2[2] - 1)]
    for nb in nbs2[:3]:
        w2.blocks[(nb[0], nb[1] + 1, nb[2])] = "minecraft:oak_log"
    sc2, _ = run_fake(w2, params(profile="work", minutes=1.0, interval=5.0))
    assert sc2["activity"]["place_world_true"] >= 1, "留了一个有净空的邻格却没放成功"
    assert not sc2["hard_failures"]
    return "全堵⇒0 次放置+软警告；留一格⇒换格放成功"


def I2_pickup_ground_fallback():
    """掉落物没自动捡起时：走过去（目标格/四邻）必须能捡回来（不许直接判丢）"""
    w = FakeWorld()
    w.pickup_works = False
    w.drop_on_ground = True
    sc, _ = run_fake(w, params(minutes=1.0, interval=5.0))
    assert "S_PICKUP_SLOW" in sc["soft_codes"], "掉落物没自动捡起居然没记软警告"
    assert "H_ITEM_LOSS" not in {h["code"] for h in sc["hard_failures"]}, \
        "走近能捡回来的掉落物被误判为丢物"
    assert sc["final"]["items"] == sc["baseline"]["items"], \
        "收尾物品 %s ≠ 基线 %s（捡回策略没生效）" % (sc["final"]["items"],
                                                    sc["baseline"]["items"])
    assert sc["verdict"] == "PASS"
    return "掉落物在→走近捡回，items 回到基线，未误判"


def J1_stuck_hard():
    """★walk 说 reachable 但人不动 ⇒ 必须判 H_STUCK 红（D3c 不卡死）✗★

    这是 2026-11-02 第 2 次长档的真实事故：Bot 悬空原地不动 2 分钟，
    dshwalk 一直 reachable=true，旧判据只把它当 S_AIRBORNE 软失败 ⇒ 漏判。
    """
    w = FakeWorld()
    w.stuck = True
    sc, _ = run_fake(w, params(profile="walk", minutes=1.0, interval=5.0))
    codes = {h["code"] for h in sc["hard_failures"]}
    assert "H_STUCK" in codes, "walk 不动居然没判 H_STUCK（实际 %s）" % codes
    assert sc["verdict"] == "FAIL" and sc["exit_code"] == 1
    assert sc["criteria"]["D3c_no_hang_err"] is False, "D3c 判据没被卡死拉红"
    # 对照：世界正常时不许误报 H_STUCK
    sc2, _ = run_fake(FakeWorld(), params(profile="walk", minutes=1.0, interval=5.0))
    assert "H_STUCK" not in {h["code"] for h in sc2["hard_failures"]}, \
        "正常走路的假世界被误判卡死"
    return "卡死⇒H_STUCK/FAIL；正常走路不误报"


def _ps_exe():
    """找 Windows PowerShell（本机是 5.1；GATE 环境不依赖 pwsh 7）"""
    for name in ("powershell", "pwsh"):
        p = shutil.which(name)
        if p:
            return p
    raise AssertionError("没有 powershell/pwsh ⇒ 夜间判据没法离线跑")


def _run(argv, timeout=240):
    return subprocess.run([str(a) for a in argv], cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=dict(os.environ))


def _make_freeze(tmpdir) -> Path:
    fp = Path(tmpdir) / "freeze.json"
    r = _run([sys.executable, "-B", "-u", "-X", "utf8",
              ROOT / "tools" / "soak_suite.py", "--freeze", "write",
              "--freeze-file", fp])
    assert r.returncode == 0, ("freeze write 失败：%s"
                               % ((r.stdout or "") + (r.stderr or ""))[-400:])
    assert fp.is_file()
    return fp


def _night(args):
    return _run([_ps_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 ROOT / "tools" / "soak_night.ps1"] + list(args))


def K1_night_static():
    """3 夜无人值守脚本的静态契约（参数/前置/失败即停/冻结/归档/不许破坏性操作）"""
    p = ROOT / "tools" / "soak_night.ps1"
    assert p.is_file(), "tools/soak_night.ps1 不存在"
    text = p.read_text(encoding="utf-8", errors="replace")
    required = ["param(", "Nights", "Minutes", "Interval", "Radius", "Anchor",
                "Profile", "DryRun", "Offline", "SimulateFailNight", "FreezeFile",
                "Test-Preflight", "Test-Freeze", "dshidle off",
                "soak_scorecard_night", "_FAIL_", "failure-stop", "FAILURE-STOP",
                "--allow-void-platform", "NIGHT_DRYRUN ok=1", "schtasks", "Tee-Object"]
    missing = [t for t in required if t not in text]
    assert not missing, "soak_night.ps1 缺契约要素：%s" % missing
    forbidden = ["Stop-Process", "taskkill", "Restart-Computer", "shutdown ",
                 "git ", "check_all", "rm -rf"]
    found = [t for t in forbidden if t in text]
    assert not found, "soak_night.ps1 含破坏性/越权操作：%s" % found
    return "参数/前置/冻结/失败即停/归档都在，且无 kill/重启/git/check_all"


def K2_night_dryrun_offline():
    """-DryRun -Offline：不连游戏、不落 state，只验参数/文件/冻结并打出 3 夜计划"""
    with tempfile.TemporaryDirectory(prefix="soaknight_") as td:
        fp = _make_freeze(td)
        r = _night(["-DryRun", "-Offline", "-FreezeFile", fp, "-Nights", "3"])
        out = (r.stdout or "") + (r.stderr or "")
        assert r.returncode == 0, ("dry-run 应 exit 0（实际 %d）：%s"
                                   % (r.returncode, out[-800:]))
        for tok in ("DRYRUN PLAN 1/3", "DRYRUN PLAN 3/3", "DRYRUN OK",
                    "NIGHT_DRYRUN ok=1", "expected_action~"):
            assert tok in out, "dry-run 输出缺 %r：%s" % (tok, out[-500:])
        assert "soak_scorecard_night3" in out
        return "3 夜计划 + 冻结 OK + exit 0（离线、未连游戏）"


def K3_night_param_red():
    """参数非法必须 exit 2（先自检能红：坏参数不许"看起来 OK"）"""
    with tempfile.TemporaryDirectory(prefix="soaknight_") as td:
        fp = _make_freeze(td)
        r1 = _night(["-DryRun", "-Offline", "-FreezeFile", fp, "-Nights", "0"])
        o1 = (r1.stdout or "") + (r1.stderr or "")
        assert r1.returncode == 2, "-Nights 0 应 exit 2（实际 %d）" % r1.returncode
        assert "-Nights" in o1
        r2 = _night(["-DryRun", "-Offline", "-FreezeFile", fp,
                     "-Anchor", "not-an-anchor"])
        o2 = (r2.stdout or "") + (r2.stderr or "")
        assert r2.returncode == 2, "-Anchor 非法应 exit 2（实际 %d）" % r2.returncode
        assert "Anchor" in o2
        return "-Nights 0 / -Anchor 非法 ⇒ exit 2（能红）"


def K4_night_failure_stop():
    """夜晚失败必须**失败即停**（后面的夜不再跑），exit 1 并打原因"""
    with tempfile.TemporaryDirectory(prefix="soaknight_") as td:
        fp = _make_freeze(td)
        r = _night(["-DryRun", "-Offline", "-FreezeFile", fp,
                    "-SimulateFailNight", "2"])
        out = (r.stdout or "") + (r.stderr or "")
        assert r.returncode == 1, ("模拟第 2 夜失败应 exit 1（实际 %d）：%s"
                                   % (r.returncode, out[-600:]))
        assert "STOP night 2/3" in out, "失败即停输出缺 STOP night 2/3：%s" % out[-500:]
        assert "failure-stop" in out
        assert "DRYRUN PLAN 3/3" not in out, "失败即停后竟然还打了第 3 夜计划"
        return "夜 2 失败 ⇒ exit 1 + STOP，不再打夜 3"


def K5_freeze_red():
    """代码冻结：写→核对 OK；篡改/缺失 ⇒ exit 2（跑一半换实现必须被照出来）"""
    with tempfile.TemporaryDirectory(prefix="soakfreeze_") as td:
        fp = _make_freeze(td)
        ok = _run([sys.executable, "-B", "-u", "-X", "utf8",
                   ROOT / "tools" / "soak_suite.py", "--freeze", "check",
                   "--freeze-file", fp])
        assert ok.returncode == 0, "刚写的冻结清单核对居然失败：%s" % (ok.stdout or "")
        data = json.loads(Path(fp).read_text(encoding="utf-8"))
        files = data.get("files") or {}
        for rel in ("tools/soak_suite.py", "tools/soak_suite_test.py",
                    "tools/d3_soak.py", "tools/soak_night.ps1"):
            assert rel in files, "冻结清单缺 %s" % rel
        data["files"]["tools/soak_suite.py"] = "0" * 64
        Path(fp).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        bad = _run([sys.executable, "-B", "-u", "-X", "utf8",
                    ROOT / "tools" / "soak_suite.py", "--freeze", "check",
                    "--freeze-file", fp])
        out = (bad.stdout or "") + (bad.stderr or "")
        assert bad.returncode == 2, "冻结哈希被改后仍 exit %d" % bad.returncode
        assert "FREEZE CHANGED" in out
        missing = Path(td) / "nope.json"
        r3 = _run([sys.executable, "-B", "-u", "-X", "utf8",
                   ROOT / "tools" / "soak_suite.py", "--freeze", "check",
                   "--freeze-file", missing])
        assert r3.returncode == 2
        return "写→check OK；篡改/缺失 ⇒ exit 2（能红）"


def H2_bursty_movement_noise():
    """★走动时才冒的 yaw 事件（≈45 条/秒）也不许把 oracle 搞 gap✗★

    2026-11-02 45min full-bar 档真因：模组走路时每 tick 写 2 条 yaw ⇒ 平均速率在
    "走/停"之间来回跳；只看平滑均值会在停下来的间隙误判"稀疏"⇒ 睡大觉 ⇒ 下一段
    走动把 400 条环灌满 ⇒ gaps=1319。修法：drain 频率看"衰减峰值"。
    """
    w = FakeWorld()
    w.noise_rate = 45.0
    w.noise_movement_only = True
    sc, _ = run_fake(w, params(minutes=2.0, interval=20.0))
    assert sc["oracle"]["gaps"] == 0, "走动噪声下 oracle 丢了事件（gaps=%s）" % \
        sc["oracle"]["gaps"]
    assert sc["oracle"]["truncated_drains"] == 0, "走动噪声下出现截断（drain 不够密）"
    assert sc["oracle"]["noise_events"] > 0, "假世界没真的造出走动噪声"
    assert sc["verdict"] == "PASS", "走动噪声本身不该把 verdict 拉红：%s" % \
        sc["inconclusive_reasons"]
    return ("gaps=0 truncated=0 noise=%d drains=%d verdict=PASS"
            % (sc["oracle"]["noise_events"], sc["oracle"]["drains"]))


CHECKS = [
    ("A1 parse_digest 全字段", A1_parse_digest),
    ("A2 parse_digest 拒绝坏回执", A2_parse_digest_rejects),
    ("A3 parse_events 增量+游标", A3_parse_events_increment),
    ("A4 parse_events 丢事件检测", A4_parse_events_gap),
    ("A5 parse_scan 世界真值", A5_parse_scan),
    ("A6 idle/auto/ver/inv/walk 解析", A6_parse_others),
    ("B1 注入 bot_died ⇒ H_DEATH/FAIL", B1_death_hard),
    ("B2 丢物 ⇒ H_ITEM_LOSS（吃掉要放行）", B2_item_loss_hard),
    ("B3 坠 y>=2 ⇒ H_FALL", B3_fall_hard),
    ("B4 非 survival ⇒ H_MODE", B4_mode_hard),
    ("B5 ERR>0 ⇒ H_ERR（preflight 前不算）", B5_err_hard),
    ("B6 同类硬失败去重+计数", B6_dedup),
    ("B7 自己 place 的 -1 不算丢物", B7_place_consume_explained),
    ("C1 oracle 增量/去重", C1_oracle_increment),
    ("C2 丢事件 ⇒ INCONCLUSIVE", C2_event_gap_inconclusive),
    ("C3 世界刻停走 ⇒ I_WORLD_STALLED", C3_world_stall),
    ("D1 桥不通 ⇒ INCONCLUSIVE/2", D1_bridge_down),
    ("D2 非 survival 前置 ⇒ INCONCLUSIVE/2", D2_mode_precondition),
    ("D3 没可放方块 ⇒ INCONCLUSIVE/2", D3_no_placeable),
    ("D4 没压到身体 ⇒ I_NOT_ACTIVE/2", D4_not_active),
    ("D5 死亡必须 FAIL/1（不是测不了）", D5_death_is_fail_not_inc),
    ("D6 世界停走 ⇒ INCONCLUSIVE/2", D6_world_frozen),
    ("E1 干净世界 ⇒ PASS/0（三档真出现）", E1_pass_scenario),
    ("E2 scorecard 自洽+证据落盘", E2_scorecard_consistent),
    ("E3 full_bar 由实际调用数算（短跑不冒充）", E3_full_bar_honest),
    ("E4 时长/轮次/混合档覆盖", E4_duration_and_rounds),
    ("E5 调度 20/30/50 且短跑也覆盖", E5_mixed_ratio),
    ("F1 d3_soak 已迁直连（无 channel）", F1_d3_soak_migrated),
    ("G1 canary：关掉死亡判据 ⇒ 不再红", G1_canary_death),
    ("G2 canary：关掉坠落判据 ⇒ 不再红", G2_canary_fall),
    ("G3 canary：关掉丢事件判据 ⇒ 不再红", G3_canary_event_gap),
    ("H1 事件洪水下自适应 drain 保住 oracle", H1_flood_adaptive_drain),
    ("H2 走动 burst 噪声（45/s）也不许 gap", H2_bursty_movement_noise),
    ("I1 work 选格必须查头顶净空", I1_work_headroom),
    ("I2 掉落物没自动捡起⇒走近捡回（不误判丢物）", I2_pickup_ground_fallback),
    ("J1 卡死（reachable 但人不动）⇒ H_STUCK 红", J1_stuck_hard),
    ("K1 夜间脚本静态契约（参数/前置/失败即停/冻结）", K1_night_static),
    ("K2 夜间 -DryRun -Offline ⇒ 3 夜计划+exit0", K2_night_dryrun_offline),
    ("K3 夜间坏参数 ⇒ exit 2（能红）", K3_night_param_red),
    ("K4 夜间失败即停（夜2失败⇒不再跑夜3）", K4_night_failure_stop),
    ("K5 代码冻结：篡改/缺失 ⇒ exit 2（能红）", K5_freeze_red),
]


def main(argv) -> int:
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].split(",")
    bad = 0
    t0 = time.time()
    for name, fn in CHECKS:
        if only and not any(name.startswith(o) for o in only):
            continue
        try:
            detail = fn()
            print("  PASS %-46s | %s" % (name, str(detail)[:150]))
        except AssertionError as exc:
            bad += 1
            print("  FAIL %-46s | %s" % (name, str(exc)[:300]))
        except Exception:
            bad += 1
            print("  FLUNK %-45s | %s" % (name, traceback.format_exc().strip()
                                           .splitlines()[-1][:300]))
    total = len(CHECKS) if not only else sum(1 for n, _ in CHECKS
                                             if any(n.startswith(o) for o in only))
    print("  ---- %d/%d ---- (%.1fs offline, no game needed)"
          % (total - bad, total, time.time() - t0))
    if bad:
        print("  => soak_suite FAIL (%d)" % bad)
        print("SOAK_SUITE ok=0 bad=%d checks=%d" % (bad, total))
        return 1
    print("  => soak_suite PASS（硬失败能红/INCONCLUSIVE 不算 PASS/记分卡自洽/无 channel）")
    print("SOAK_SUITE ok=1 checks=%d" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
