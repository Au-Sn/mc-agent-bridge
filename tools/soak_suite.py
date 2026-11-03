#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""soak_suite.py —— ★D3「身体不出事」混合长跑观测器 ＋ 记分卡★（2026-11-02 ✓）

WHY（见 `reports/mc-bridge-optimization/30-verify.md` 第三节 ✓）：
  D3 要求的是 ★"连续 3 小时（或 2000 次调用）不掉下去／不丢物品／不卡死"★ ✗
  旧的三个观察器各自只压一档、都不到 3h，也从来没人把"跑没跑够"写成机器可读的
  **记分卡** ✗ ⇒ 这次收口：一份套件吃四档（mixed/idle/walk/work），driver 侧计数，
  每轮 `/dshevents` 增量 oracle，hard/soft 分开记，INCONCLUSIVE 不算 PASS。

★车道（2026-11-02 迁移 ✗）★：
  旧 d3_soak 走 `agent.channel.Channel`（CC 计算机/网关 8765）⇒ 已失效 ✗
  现在直连：`POST http://127.0.0.1:8766/cmd`（`tools/direct.py` ✓）
  ★模组 `/cmd` 自己包 `execute as Bot at @s run` ⇒ 这里发**裸指令**✗★
  （`dshdigest 1` / `dshevents` / `dshwalk x y z`，不要再手包 execute）

判据（★先写死 ✗ 不许事后改✓★；口径见契约 §9 与 30-verify §3.2）：
  硬失败（任一 ⇒ FAIL，退出码 1）：
    H_DEATH 期间新增 bot_died > 0 ｜ H_ITEM_LOSS 背包低于"基线−已解释消耗"
    H_FALL y 比基线低 >= 2 ｜ H_MODE 任何采样非 survival ｜ H_ERR driver 拿到
    ERR/超时/None（ERR>0 即红）
  软失败（分开记 ✗ 不直接改退出码）：掉血、damage、空中、世界刻停走/变慢、
    事件环丢事件（同时会把 verdict 拉成 INCONCLUSIVE）、落地掉落物、world 残留、
    到达率低、walk pillar>0、外来 mut、事件流过密（yaw 写者噪声）。
  INCONCLUSIVE（退出码 2，★绝不算 PASS✗★）：桥不通／指令车道不可用／没有 Bot／
    非 survival（★需要 Lead 设 ✗ 本套件不偷偷改模式✓★）／事件流读不到或丢事件／
    没有可放方块／起点不在测试区／世界刻整体停住／没被真正压到／人工中断／套件自身异常。

★安全边界（全是硬规则✓）★：
  · 只在起点 `--radius` 内走/干活；place/dig 只动**自己刚放的那一格**；
  · 动手前问项目自己的 `no_dig.allowed()`（家/屋/CC 机）＋ 虚空平台写死禁区；
  · 走路目标先做**世界真值**校验（脚格空气+脚下实心）；不靠回执自述；
  · 起跑点必须在测试区锚点半径内（默认家附近 16 格），否则拒跑（I_UNSAFE_START）；
  · 身边 1.8 格内有实体（真人/商人/怪）⇒ 这一轮不放方块（不往活物身上放方块）。

用法：
  py tools/soak_suite.py --profile mixed --minutes 20
  py tools/soak_suite.py --profile idle --minutes 5 --interval 60
  py tools/soak_suite.py --profile mixed --minutes 180 --max-calls 2000   # 3h 满档

前置条件（跑之前逐条核）：
  ① 游戏在跑、Bot 在线、8766 health ok；② Bot 是 **survival**（Lead 设，本套件不改）；
  ③ 起点在锚点附近的安全平台；④ 事件环先记 cursor，之后每轮增量 drain；
  ⑤ 无人正对 Bot 发指令/改世界（真人挂机可以，但别在测试区动手）；
  ⑥ work 档背包里要有可放方块；⑦ idle 档建议 `--interval >= 60`（模组有"15 秒无指令
  才自作主张"的闸，P25）。

★本文件是 runner（要游戏 ⇒ 不进离线闸门）；判据在 tools/soak_suite_test.py（离线）★
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
STATE = ROOT / "state"
LOGS = ROOT / "logs"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCHEMA = "dshbridge/soak_scorecard@1"
MIX = {"idle": 0.20, "walk": 0.30, "work": 0.50}
FULL_BAR_CALLS_DEFAULT = 2000

# ★测试区锚点✗★：默认值只是**本机旧默认**；有 `state/world_profile.json` 时以档案 `soak_anchor` 为准
HOME_ANCHOR = (4121, 71, 15)
SAFE_START_RADIUS = 16.0
# ★虚空平台✗★：x4145..4160 z2..17 y=70（另一块 256 格 stone，别往里走）
VOID_PLATFORM_BOX = (4145, 70, 2, 4160, 70, 17)
HOME_FALLBACK_BOX = (4115, 71, 19, 4129, 79, 32)


def default_anchor(profile_path=None) -> tuple:
    """★锚点解析（唯一口径）✗★：world_profile.soak_anchor 优先；无档案 ⇒ 本机旧默认＋**明确打印**"""
    try:
        import world_profile as WP
        val, source, why = WP.resolve_anchor("soak_anchor", path=profile_path)
    except Exception as exc:              # ★不许静默✗★
        print("soak: world_profile 解析失败 (%s: %s) ⇒ 用本机默认 soak 锚点 %s"
              % (type(exc).__name__, str(exc)[:120], HOME_ANCHOR), file=sys.stderr)
        return HOME_ANCHOR
    if val is not None:
        return tuple(val)
    print("soak: %s ⇒ 用本机默认 soak 锚点 %s（world_profile 未配置）" % (why, HOME_ANCHOR),
          file=sys.stderr)
    return HOME_ANCHOR

PLACEABLE = [
    "minecraft:cobblestone", "minecraft:dirt", "minecraft:gravel", "minecraft:sand",
    "minecraft:stone", "minecraft:oak_planks", "minecraft:andesite", "minecraft:diorite",
    "minecraft:granite", "minecraft:deepslate", "minecraft:netherrack", "minecraft:clay",
    "minecraft:oak_log", "minecraft:birch_log", "minecraft:white_wool",
]

HARD_CODES = ("H_DEATH", "H_ITEM_LOSS", "H_FALL", "H_MODE", "H_ERR", "H_STUCK")
# ★只把"身体/世界"事件原文写进 jsonl✗★ —— yaw 写者那种每 tick 两条的噪声只计数
#   （否则 3 小时日志会被 yaw_bracket/yaw_write 撑爆 ✗ 实测 80 条/秒）
INTERESTING_EVENTS = {"bot_died", "bot_revived", "damage", "mode", "inv", "mut",
                      "walk_done", "walk_refuse", "walk_start", "humanoid",
                      "auto_eat", "drop", "tp", "mut_undo"}
SOFT_CAP = 40
MAX_SAMPLES = 20000
ROUND_GAP_SEC = 0.30
WALK_POLL_SEC = 1.20
WALK_TIMEOUT_MIN = 4.0
WALK_TIMEOUT_MAX = 15.0
WORK_RECOVER_SEC = 10.0


# ══════════════════════════════════════════════════════════════════════════
# 解析层（★只解析回执原文 ✗ 不信自述✓★；纯函数，离线判据可单测）
# ══════════════════════════════════════════════════════════════════════════

_KV_RE = re.compile(r"(?<![\[\]a-zA-Z0-9_])([a-zA-Z_][a-zA-Z0-9_]*)=([^\s\]\)]+)")


def parse_kv(text: str) -> dict:
    """`k=v` 的松散解析（`inv[x]kinds=` 这种带方括号的不参与，单独解析）"""
    return {k: v for (k, v) in _KV_RE.findall(text or "")}


def now_iso(ts: float = None) -> str:
    ts = time.time() if ts is None else ts
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts))


def parse_digest(text: str):
    """`dshdigest` 回执 ⇒ dict ／ None（★判不了就 None ✗ 不猜✓★）"""
    if not text or text.strip().startswith("ERR:") or "dshdigest" not in text:
        return None
    kv = parse_kv(text)
    if "pos" not in kv or "hp" not in kv:
        return None
    try:
        x, y, z = (float(v) for v in kv["pos"].split(","))
    except Exception as exc:
        print("soak_suite.parse_digest: pos=%r 解析失败：%r ⇒ 判不了（返回 None）"
              % (kv.get("pos"), exc), file=sys.stderr)
        return None
    inv = re.search(r"inv\[x\]kinds=(\d+),items=(\d+),free=(\d+),sel=(\d+)", text)
    if not inv:
        return None
    near_m = re.search(r"nearest=([^\s@]+)@([\d.]+)", text)
    near_dist = float(near_m.group(2)) if near_m else None
    try:
        return {
            "name": kv.get("name"), "pos": (x, y, z), "x": x, "y": y, "z": z,
            "yaw": float(kv.get("yaw", "nan")), "pitch": float(kv.get("pitch", "nan")),
            "hp": float(kv["hp"]), "food": int(kv.get("food", -1)),
            "mode": kv.get("mode"), "onground": kv.get("onground") == "true",
            "dim": kv.get("dim"), "time": int(kv.get("time", -1)),
            "day": int(kv.get("day", -1)),
            "kinds": int(inv.group(1)), "items": int(inv.group(2)),
            "free": int(inv.group(3)), "sel": int(inv.group(4)),
            "held": kv.get("held"), "drops": int(kv.get("drops", 0)),
            "hostiles": int(kv.get("hostiles", 0)), "ents": int(kv.get("ents", 0)),
            "nearest": kv.get("nearest"), "nearest_dist": near_dist, "raw": text,
        }
    except Exception as exc:
        print("soak_suite.parse_digest: 字段解析失败：%r ⇒ 判不了（返回 None）"
              % (exc,), file=sys.stderr)
        return None


def parse_events(text: str, since):
    """`/dshevents [since]` 回执 ⇒ dict ／ None（★含丢事件检测✗★）

    ★为什么必须检测丢事件✗★：模组事件环 EVENT_KEEP=400 且单次最多展示 **40** 条
    ⇒ 两次 drain 之间新事件 > 40 ⇒ 早的先被截掉（还在环里但没 API 能取）
    ⇒ 死亡可能正好落在被截掉的那段里 ⇒ 死亡证明不完整 ⇒ 必须报 INCONCLUSIVE。
    """
    if not text or text.strip().startswith("ERR:"):
        return None
    m = re.search(r"dshevents\b.*?\btotal=(\d+)\s+new=(\d+)\s+cursor=(\d+)", text, re.S)
    if not m:
        return None
    total, new, cursor = (int(v) for v in m.groups())
    body = text[m.end():]
    events = []
    for chunk in body.split(" | "):
        chunk = chunk.strip()
        if not chunk.startswith("#"):
            continue
        mm = re.match(r"#(\d+)\s+(\S+)\s*(.*)$", chunk)
        if mm:
            events.append({"seq": int(mm.group(1)), "kind": mm.group(2),
                           "data": mm.group(3), "raw": chunk})
    shown = len(events)
    truncated = shown < new
    gap = 0
    complete = True
    if since is not None and since >= 0:
        expected = total - since
        if expected > new:
            gap += expected - new
        if events:
            first = min(e["seq"] for e in events)
            if first > since + 1:
                gap += first - (since + 1)
        if truncated or gap > 0:
            complete = False
    return {"cursor": cursor, "total": total, "new": new, "shown": shown,
            "events": events, "complete": complete, "gap": gap,
            "truncated": truncated, "since": since}


def parse_scan_cell(text: str):
    """`dshscan x y z x y z`（单格）⇒ dict ／ None（世界真值 ✓）"""
    if not text or text.strip().startswith("ERR:") or "dshscan" not in text:
        return None
    kv = parse_kv(text)
    if "solid" not in kv or "air" not in kv:
        return None
    counts = {}
    m = re.search(r"counts\[([^\]]*)\]", text)
    if m and m.group(1).strip():
        for part in m.group(1).split(","):
            if ":" in part:
                k, v = part.rsplit(":", 1)
                if v.isdigit():
                    counts[k] = int(v)
    block = None
    for k in counts:
        if k != "air":
            block = k
            break
    return {"solid": int(kv["solid"]), "air": int(kv["air"]),
            "counts": counts, "block": block, "hash": kv.get("hash"),
            "tick": kv.get("tick"), "raw": text}


def parse_idle(text: str):
    """`/dshidle status` ⇒ dict ／ None"""
    if not text or text.strip().startswith("ERR:") or "dshidle" not in text:
        return None
    kv = parse_kv(text)
    if "humanoid" not in kv:
        return None

    def _i(k, d=0):
        raw = str(kv.get(k, d)).rstrip("s")
        try:
            return int(float(raw))
        except Exception as exc:
            print("soak_suite.parse_idle: %s=%r 解析失败（按 %d 记）：%r"
                  % (k, raw, d, exc), file=sys.stderr)
            return d
    return {"humanoid": str(kv.get("humanoid")).lower() == "true",
            "radius": _i("radius"), "strolls": _i("strolls"),
            "looks": _i("looks"), "lines": _i("lines"),
            "anchor": kv.get("anchor"), "autoeat": kv.get("autoeat"),
            "raw": text}


def parse_auto(text: str):
    """`/dshauto` ⇒ dict ／ None"""
    if not text or text.strip().startswith("ERR:") or "dshauto" not in text:
        return None
    kv = parse_kv(text)
    if "eat" not in kv:
        return None
    return {"eat": str(kv["eat"]).lower() == "true",
            "idle": str(kv.get("idle")).lower() == "true", "raw": text}


def parse_ver(text: str):
    """`/dshver` ⇒ dict ／ None"""
    if not text or text.strip().startswith("ERR:") or "dshver" not in text:
        return None
    m = re.search(r"version=([^\s]+)", text)
    feat = re.search(r"features=([^\s]+)", text)
    if not m:
        return None
    return {"version": m.group(1),
            "features": feat.group(1).split(",") if feat else [],
            "raw": text}


def parse_walk_start(text: str):
    """`/dshwalk x y z` 的即时回执 ⇒ dict ／ None（`reachable` 是模组自己的判断 ✓）"""
    if not text or text.strip().startswith("ERR:") or "dshwalk start" not in text:
        return None
    kv = parse_kv(text)
    return {"reachable": str(kv.get("reachable")).lower() == "true",
            "path": int(kv.get("path", 0) or 0), "to": kv.get("to"),
            "exact": str(kv.get("exact")).lower() == "true", "raw": text}


def parse_walk_status(text: str):
    """`/dshwalk`（无参数 = status）⇒ dict ／ None

    结果取值（模组 `finish()` 的 how）：reached／stopped_by_agent／timeout／edge／
    unreachable／blocked／humanoid_off。
    """
    if not text or text.strip().startswith("ERR:") or "dshwalk" not in text:
        return None
    if "status=none" in text:
        return {"status": "none", "done": True, "result": "none", "raw": text}
    kv = parse_kv(text)
    st = kv.get("status")
    if st not in ("done", "running"):
        return None
    at = kv.get("at")
    try:
        at = tuple(float(v) for v in at.split(",")) if at else None
    except Exception:
        at = None
    return {"status": st, "done": st == "done", "result": kv.get("result"),
            "why": kv.get("why"), "at": at, "reachable": kv.get("reachable"),
            "ticks": kv.get("ticks"), "path": kv.get("path"),
            "detours": kv.get("detours"), "raw": text}


def parse_inv_list(text: str):
    """`/dshinv list` ⇒ [{slot,item,count}] ／ None（放在 dict["items"]）"""
    if not text or text.strip().startswith("ERR:") or "dshinv list" not in text:
        return None
    rows = []
    for m in re.finditer(r"(\d+):([A-Za-z0-9_.:\-]+)x(\d+)", text):
        rows.append({"slot": int(m.group(1)), "item": m.group(2),
                     "count": int(m.group(3))})
    return {"items": rows, "raw": text}


def parse_mode_event(data: str):
    m = re.search(r"from=(\w+)\s+to=(\w+)", data or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def event_int(data: str, key: str, default=None):
    m = re.search(r"\b%s=(-?\d+)" % re.escape(key), data or "")
    return int(m.group(1)) if m else default


def event_pos(data: str):
    m = re.search(r"pos=(-?\d+),(-?\d+),(-?\d+)", data or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def cell_of(pos) -> tuple:
    """★脚格规则（与 `mcp_core.cell_of` 同一口径 ✗ 全仓唯一实现那份✓）★"""
    x, y, z = (float(v) for v in pos)
    return (int(math.floor(x)), int(math.ceil(y - 1e-9)), int(math.floor(z)))


def in_box(box, pos) -> bool:
    x, y, z = pos
    return box[0] <= x <= box[3] and box[1] <= y <= box[4] and box[2] <= z <= box[5]


def dist2d(a, b) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[2]) - float(b[2]))


def touch_allowed(pos, allow_void_platform: bool = False):
    """★这一格能不能动世界✗★ ⇒ `(bool, zone_name)`

    ★必须问项目自己的 `no_dig` ✗ 不许自己再写一份✓★（§79.471 的教训）。
    ★虚空平台默认为禁区；`allow_void_platform=True` 时它是"指定测试平台"（Lead 2026-11-02
      拍板：平台 x4145..4160 z2..17 y=70 是逐格验过的干净测试区，半径 3 跑）✗★
    """
    if in_box(VOID_PLATFORM_BOX, tuple(pos)) and not allow_void_platform:
        return False, "void_platform(写死禁区)"
    try:
        import no_dig as ND
        ok, zone = ND.allowed(tuple(pos))
        if not ok:
            return False, (zone or {}).get("name", "no_dig")
    except Exception as exc:
        print("soak_suite.touch_allowed: no_dig 不可用（%r）⇒ 用兜底禁区 %s"
              % (exc, HOME_FALLBACK_BOX), file=sys.stderr)
        if in_box(HOME_FALLBACK_BOX, tuple(pos)):
            return False, "fallback_home_box(no_dig 读不出)"
    return True, None


def within_anchor(pos, anchor, radius) -> bool:
    return (dist2d(pos, anchor) <= radius
            and anchor[1] - 6 <= float(pos[1]) <= anchor[1] + 6)


# ══════════════════════════════════════════════════════════════════════════
# driver：每次 dsh 调用**计数**（满档证据）＋ 失败立刻进 hard 账
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Reply:
    cmd: str
    text: str = None
    ok: bool = False
    err: str = None
    ms: float = 0.0

    def tail(self, n: int = 160) -> str:
        if self.text is None:
            return "<None>"
        return self.text.replace("\n", " ｜ ")[:n]


def _direct_transport(cmd: str, timeout: float):
    import direct as D
    return D.post(cmd, timeout=timeout)


def _direct_health(timeout: float = 2.0):
    import direct as D
    return D.health(timeout=timeout)


class Driver:
    """★所有世界读写只走这里 ✗ 调用数 = 满档证据✓★"""

    def __init__(self, transport=None, health_fn=None, timeout: float = 20.0, log=None):
        self.transport = transport or _direct_transport
        self.health_fn = health_fn or _direct_health
        self.timeout = timeout
        self.log = log
        self.calls = 0
        self.calls_action = 0     # ★不含 /dshevents oracle drain✗★（满档门槛按这个数算）
        self.errors = []
        self.on_error = None
        self.latency_ms = []

    def call(self, cmd: str, timeout: float = None) -> Reply:
        t0 = time.monotonic()
        text = None
        err = None
        try:
            text = self.transport(cmd, timeout or self.timeout)
        except Exception as exc:
            err = "exception:%s:%s" % (type(exc).__name__, exc)
        ms = (time.monotonic() - t0) * 1000.0
        self.calls += 1
        # ★满档门槛只看"动作/观测"调用 ✗ 不含事件 oracle drain✗★
        #   WHY：事件很密时自适应 drain 会把调用数灌上去 ⇒ 8 分钟也能"满档"= 冒充 ✗
        if not cmd.startswith("dshevents"):
            self.calls_action += 1
        self.latency_ms.append(ms)
        if err is None:
            if text is None:
                err = "bridge_none(超时/连不上)"
            elif not str(text).strip():
                err = "empty_reply"
            elif str(text).strip().startswith("ERR:"):
                err = str(text).strip()[:120]
        ok = err is None
        rep = Reply(cmd=cmd, text=(None if text is None else str(text)), ok=ok,
                    err=err, ms=ms)
        if not ok:
            self.errors.append(rep)
        if self.log is not None:
            self.log.record({"type": "call", "cmd": cmd[:120], "ok": ok,
                             "err": err, "ms": round(ms, 2),
                             "reply": rep.tail(140)})
        if (not ok) and self.on_error is not None:
            self.on_error(self, rep)
        return rep

    def health(self, timeout: float = 2.0) -> Reply:
        t0 = time.monotonic()
        text = None
        try:
            text = self.health_fn(timeout)
        except Exception as exc:
            text = "ERR:exception:" + type(exc).__name__
        ms = (time.monotonic() - t0) * 1000.0
        self.calls += 1
        self.calls_action += 1
        ok = bool(text and "ok" in str(text))
        rep = Reply(cmd="HEALTH", text=(None if text is None else str(text)),
                    ok=ok, err=None if ok else "health_failed", ms=ms)
        if self.log is not None:
            self.log.record({"type": "call", "cmd": "HEALTH", "ok": ok,
                             "err": rep.err, "ms": round(ms, 2),
                             "reply": rep.tail(80)})
        if not ok:
            self.errors.append(rep)
        return rep

    def digest(self, radius: int = 1) -> Reply:
        return self.call("dshdigest %d" % int(radius))

    def events(self, since=None) -> Reply:
        return self.call("dshevents" if since is None else "dshevents %d" % int(since))

    def scan_cell(self, x, y, z) -> Reply:
        return self.call("dshscan %d %d %d %d %d %d" % (x, y, z, x, y, z))

    def inv_list(self) -> Reply:
        return self.call("dshinv list")

    def ver(self) -> Reply:
        return self.call("dshver")

    def auto_status(self) -> Reply:
        return self.call("dshauto")

    def idle_status(self) -> Reply:
        return self.call("dshidle status")

    def idle_on(self) -> Reply:
        return self.call("dshidle on")

    def idle_off(self) -> Reply:
        return self.call("dshidle off")

    def idle_radius(self, n: int) -> Reply:
        return self.call("dshidle radius %d" % int(n))

    def walk(self, x, y, z, exact: bool = False, ms: int = 10000) -> Reply:
        if exact:
            return self.call("dshwalk %d %d %d %d exact" % (x, y, z, ms))
        return self.call("dshwalk %d %d %d" % (x, y, z))

    def walk_status(self) -> Reply:
        return self.call("dshwalk")

    def walk_stop(self) -> Reply:
        return self.call("dshwalk stop")

    def place(self, x, y, z, item: str) -> Reply:
        return self.call('dshplace %d %d %d "%s"' % (x, y, z, item))

    def dig(self, x, y, z) -> Reply:
        return self.call("dshdig %d %d %d" % (x, y, z))


class StepLog:
    """`logs/soak_<ts>.jsonl` —— 一行一笔（调用／采样／oracle／轮次／判定）"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = self.path.open("w", encoding="utf-8", newline="\n")
        self.n = 0

    def record(self, rec: dict):
        if "t" not in rec:
            rec = dict(rec)
            rec["t"] = now_iso()
        self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.f.flush()
        self.n += 1

    def close(self):
        try:
            self.f.close()
        except Exception as exc:
            print("soak_suite.StepLog.close: 关日志失败（%r），记录数=%d"
                  % (exc, self.n), file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════
# Mixed 调度：按轮次 20%／30%／50%（★任何前缀都尽量接近比例✗★）
# ══════════════════════════════════════════════════════════════════════════

class MixedSchedule:
    """最大余额法：每轮取"欠得最多"的那一档 ⇒ 任意前缀都接近 20/30/50。

    ★为什么不用纯随机✗★：短跑（5~10 分钟）纯随机有 ~10% 概率某一档一次都不出现
    ⇒ 混合档就没覆盖到 ⇒ 记分卡会假装 cover 了（P100 同族）。
    """

    def __init__(self, seed: int, mix=None, profile: str = "mixed"):
        self.profile = profile
        self.mix = dict(mix or MIX)
        self.rng = random.Random(seed)
        self.acc = {k: 0.0 for k in self.mix}
        self.used = {k: 0 for k in self.mix}

    def next_kind(self) -> str:
        if self.profile in self.mix:
            self.used[self.profile] += 1
            return self.profile
        for k in self.acc:
            self.acc[k] += self.mix[k]
        best = max(self.acc.values())
        cands = [k for k in self.acc if abs(self.acc[k] - best) < 1e-9]
        k = self.rng.choice(cands) if len(cands) > 1 else cands[0]
        self.acc[k] -= 1.0
        self.used[k] += 1
        return k


# ══════════════════════════════════════════════════════════════════════════
# 判定核心：★所有"红/不红"都在这里 ✗ 离线判据直接喂假读数验它✓★
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class SoakParams:
    profile: str = "mixed"
    minutes: float = 180.0
    interval: float = 30.0
    radius: int = 4
    seed: int = 7
    max_calls: int = FULL_BAR_CALLS_DEFAULT
    anchor: tuple = HOME_ANCHOR
    allow_void_platform: bool = False   # True ⇒ 允许在虚空测试平台(x4145..4160 z2..17)上跑

    def planned_sec(self) -> float:
        return self.minutes * 60.0

    def as_dict(self) -> dict:
        return {"profile": self.profile, "minutes": self.minutes,
                "interval": self.interval, "radius": self.radius,
                "seed": self.seed, "max_calls": self.max_calls,
                "anchor": list(self.anchor),
                "allow_void_platform": self.allow_void_platform}


class SoakCore:
    """判据状态机（★纯逻辑 + 账本 ✓ 不做任何 I/O ✗ 便于离线单测✓★）"""

    def __init__(self, params: SoakParams):
        self.p = params
        self.armed = False
        self.hard = []
        self.soft = []
        self.inc = []
        self.soft_seen = {}
        self.baseline = None
        self.final = None
        self.cursor = None
        self.cursor_start = None
        self.cursor_end = None
        self.last_drain_at = None
        self.event_rate = 0.0
        self.event_rate_recent = 0.0     # ★衰减峰值✗★：决定 drain 频率（防"刚静下来就睡大觉"）
        self.event_rate_peak = 0.0
        self._yaw_burst_seen = False     # 见过 ≥20 条/秒 ⇒ 之后所有 sleep 一律细粒度 drain
        self.noise_events = 0
        self._flood_warned = False
        self.deaths = 0
        self.death_seqs = set()
        self.event_kinds = {}
        self.events_seen = 0
        self.event_gaps = 0
        self.event_truncated = 0
        self.oracle_drains = 0
        self.rounds = []
        self.samples = 0
        self.cells = set()
        self.cells_xz = set()
        self.floor0 = None
        self.baseline_y = None
        self.hp0 = None
        self.min_hp = None
        self.items0 = None
        self.min_items = None
        self.exp_loss = 0
        self._exp_round = 0
        self.stall_sec = 0.0
        self.stall_windows = 0
        self.still_air_sec = 0.0           # 悬空且原地不动累计秒数（卡死检测用）
        self.still_air_samples = 0
        self.damage_events = 0
        self.inv_neg_events = 0
        self.inv_large_drop_events = 0
        self.mode_events = 0
        self.humanoid_events = 0
        self.auto_eat_events = 0
        self.walk_start_events = 0
        self.walk_done_events = 0
        self.walk_refuse_events = 0
        self.walk_pillar = 0
        self.world_mut = set()
        self.walk_attempts = 0
        self.walk_reached = 0
        self.walk_refused = 0
        self.walk_max_moved = 0.0
        self.work_attempts = 0
        self.place_true = 0
        self.dig_true = 0
        self.work_cells = {}
        self.idle_rounds = 0
        self.idle_humanoid_confirmed = False
        self.idle_strolls0 = None
        self.idle_strolls_last = None
        self.walk_running = False
        self.idle_live = False
        self.idle_baseline = None
        self.auto_status = None
        self.ver = None
        self.placeable = []
        self._failed_items = set()
        self._place_streak = {}
        self._pending_place_consumes = 0   # 已 place 但还没看到 -1 事件（解释用）
        self.started_at = None
        self.ended_at = None
        self.ended_unix = None
        self.aborted = None
        self._last_sample = None
        self._last_sample_at = None
        self._last_tick = None
        self.status = "running"
        self.cleanup_errors = []
        self.preconditions = {}

    # ── 记账 ────────────────────────────────────────────────────────────
    def _mk(self, code, detail, extra=None):
        d = {"code": code, "detail": detail, "at": now_iso()}
        if extra:
            d.update(extra)
        return d

    def hard_codes(self):
        return {h["code"] for h in self.hard}

    def add_hard(self, code, detail, extra=None):
        for h in self.hard:
            if h["code"] == code:
                h["count"] = h.get("count", 1) + 1
                h["last"] = detail
                return
        self.hard.append(self._mk(code, detail, extra))

    def has_hard(self) -> bool:
        return bool(self.hard)

    def add_soft(self, code, detail, extra=None):
        n = self.soft_seen.get(code, 0) + 1
        self.soft_seen[code] = n
        if n <= SOFT_CAP:
            self.soft.append(self._mk(code, detail, extra))
        elif n == SOFT_CAP + 1:
            self.soft.append(self._mk(code, "同类软失败超过 %d 条，后续只计数" % SOFT_CAP,
                                      {"count": n}))

    def add_inc(self, code, detail):
        if any(i["code"] == code for i in self.inc):
            return
        self.inc.append(self._mk(code, detail))

    def note_error(self, driver, reply: Reply):
        """driver 任何一次调用拿到 ERR ⇒ ★ERR>0 即红✗★（preflight 前只记环境）"""
        if not self.armed:
            return
        self.add_hard("H_ERR", "调用失败：%s ⇒ %s" % (reply.cmd, reply.err),
                      {"cmd": reply.cmd, "err": reply.err})

    # ── 基线 ────────────────────────────────────────────────────────────
    def set_baseline(self, d: dict, idle_st, auto_st, ver, inv, ev_cursor, now,
                     preconditions=None):
        self.armed = True
        self.started_at = now
        self.baseline = {
            "pos": list(d["pos"]), "mode": d["mode"], "hp": d["hp"],
            "food": d["food"], "items": d["items"], "kinds": d["kinds"],
            "free": d["free"], "onground": d["onground"],
            "time": d["time"], "day": d["day"], "dim": d["dim"],
            "held": d["held"], "events_cursor": ev_cursor,
            "idle": None if idle_st is None else {
                "humanoid": idle_st["humanoid"], "radius": idle_st["radius"],
                "strolls": idle_st["strolls"], "looks": idle_st["looks"]},
            "auto_eat": None if auto_st is None else auto_st["eat"],
            "mod_version": None if ver is None else ver["version"],
            "features": None if ver is None else ver["features"],
            "inventory": None if inv is None else inv["items"],
        }
        self.baseline_y = float(d["y"])
        self.floor0 = int(math.floor(self.baseline_y))
        self.hp0 = float(d["hp"])
        self.min_hp = float(d["hp"])
        self.items0 = int(d["items"]) if d["items"] is not None else None
        self.min_items = self.items0
        self.cursor = ev_cursor
        self.cursor_start = ev_cursor
        self.idle_baseline = idle_st
        self.idle_strolls0 = idle_st["strolls"] if idle_st else None
        self.idle_strolls_last = self.idle_strolls0
        self.idle_humanoid_confirmed = bool(idle_st and idle_st["humanoid"])
        self.auto_status = auto_st
        self.ver = ver
        self.placeable = []
        if inv:
            have = {r["item"] for r in inv["items"]}
            for want in PLACEABLE:
                if want in have:
                    self.placeable.append(want)
        self.cells.add(cell_of(d["pos"]))
        self.cells_xz.add((int(math.floor(d["x"])), int(math.floor(d["z"]))))
        self._last_sample = d
        self._last_sample_at = now
        self.last_drain_at = now          # 第一次 drain 的速率估计有个参照
        self._last_tick = d["day"] * 24000 + d["time"]
        self.preconditions = preconditions or {}
        if auto_st is not None and auto_st.get("eat"):
            self.add_soft("S_AUTOEAT_ON", "Bot 的自动进食是开着的 ⇒ 物品减少先按"
                          "'吃了'解释（仍要求最终对得上账）")

    # ── 事件 oracle（增量）──────────────────────────────────────────────
    def observe_events(self, now, ev, reply=None):
        if ev is None:
            self.add_soft("S_EVENT_READ", "这一轮读不到事件流 ⇒ 死亡证明不完整")
            self.add_inc("I_EVENT_GAP", "读不到 /dshevents（%s）"
                         % (None if reply is None else reply.tail(80)))
            return
        self.oracle_drains += 1
        if self.last_drain_at is not None:
            dt = max(1e-3, float(now) - self.last_drain_at)
            # ★速率估计：dt>=0.02 才采信（校准睡 0.05s 时浮点可能略小）；
            #   低估速率无害（只会睡久一点），高估速率更安全（drain 更勤）；
            #   **峰值**只在 dt>=0.2 才更新 —— 否则连续 drain（dt≈1ms）会把峰值估成
            #   几百上千条/秒（实测伪影 event_rate_peak=437.9）
            if dt >= 0.02:
                rate = ev["new"] / dt
                self.event_rate = (rate if self.event_rate <= 0
                                   else 0.6 * self.event_rate + 0.4 * rate)
                # ★衰减峰值✗★：走路时模组每 tick 写 2 条 yaw（≈40 条/秒）⇒ 若只看
                #   平滑均值，走完一停就掉到 20 以下 ⇒ 下一段走动一来就丢事件
                #   （2026-11-02 45min full-bar 档 gaps=1319 的真因）。近期峰值 10%/drain 衰减。
                self.event_rate_recent = max(rate, self.event_rate_recent * 0.90)
                if dt >= 0.2:
                    self.event_rate_peak = max(self.event_rate_peak, rate)
                if self.event_rate >= 20.0 and not self._flood_warned:
                    self._flood_warned = True
                    self.add_soft("S_EVENT_FLOOD",
                                  "事件流很密（≈%.0f 条/秒，如 yaw 写者每 tick 两条）⇒ "
                                  "改为切片高频 drain 保住 oracle；这本身是事件环可读性问题"
                                  % self.event_rate)
                # ★见过一次爆发就永久切细粒度 drain✗★：模组"走路时每 tick 两条 yaw"
                #   是 burst（40+ 条/秒），间隙平滑均值会掉下去 ⇒ 若再按"稀疏"睡大觉，
                #   下一段走动的 burst 会把 400 条环灌满 ⇒ oracle gap（45min 实测踩过）
                if rate >= 20.0:
                    self._yaw_burst_seen = True
        self.last_drain_at = float(now)
        if not ev["complete"]:
            self.event_gaps += ev["gap"]
            if ev["truncated"]:
                self.event_truncated += 1
            self.add_soft("S_EVENT_GAP", "事件环丢事件：since=%s total=%d new=%d "
                          "shown=%d gap=%d" % (ev["since"], ev["total"], ev["new"],
                                               ev["shown"], ev["gap"]))
            self.add_inc("I_EVENT_GAP", "事件环丢过事件（最近一次 since=%s new=%d "
                         "gap=%d）⇒ 无法证明期间零死亡"
                         % (ev["since"], ev["new"], ev["gap"]))
        for e in ev["events"]:
            self.events_seen += 1
            k = e["kind"]
            self.event_kinds[k] = self.event_kinds.get(k, 0) + 1
            if k not in INTERESTING_EVENTS:
                self.noise_events += 1
                continue
            data = e["data"]
            if k == "bot_died":
                if e["seq"] not in self.death_seqs:
                    self.death_seqs.add(e["seq"])
                    self.deaths += 1
                    self.add_hard("H_DEATH", "新增 bot_died：#%d %s" % (e["seq"], data),
                                  {"event": e["raw"]})
            elif k == "damage":
                self.damage_events += 1
                self.add_soft("S_DAMAGE", "受损事件：%s" % data, {"event": e["raw"]})
            elif k == "mode":
                self.mode_events += 1
                fr, to = parse_mode_event(data)
                self.add_soft("S_MODE_EVENT", "模式事件：%s → %s" % (fr, to),
                              {"event": e["raw"]})
            elif k == "inv":
                delta = event_int(data, "delta")
                if delta is not None and delta < 0:
                    # ★自己 place 花掉的那 1 个不是"丢东西"✗★（每 place 一条 -1 事件）
                    if delta == -1 and self._pending_place_consumes > 0:
                        self._pending_place_consumes -= 1
                        continue
                    self.inv_neg_events += 1
                    if delta <= -2:
                        self.inv_large_drop_events += 1
                    self.add_soft("S_INV_DROP", "背包减少 delta=%s（%s）" % (delta, data),
                                  {"event": e["raw"]})
            elif k == "mut":
                pos = event_pos(data)
                if pos is not None:
                    self.world_mut.add(pos)
            elif k == "walk_done":
                self.walk_done_events += 1
                pv = event_int(data, "pillar", 0) or 0
                if pv > 0:
                    self.walk_pillar += pv
                    self.add_soft("S_WALK_PILLAR", "走路放了 %d 块方块（改了世界）" % pv,
                                  {"event": e["raw"]})
            elif k == "walk_start":
                self.walk_start_events += 1
            elif k == "walk_refuse":
                self.walk_refuse_events += 1
            elif k == "humanoid":
                self.humanoid_events += 1
            elif k == "auto_eat":
                self.auto_eat_events += 1
                self.exp_loss += 1
                self._exp_round += 1
        self.cursor = ev["cursor"]
        self.cursor_end = ev["cursor"]

    # ── 每次 digest 采样 ────────────────────────────────────────────────
    def observe_sample(self, now, d: dict):
        self.samples += 1
        if self.samples > MAX_SAMPLES:
            return
        self.cells.add(cell_of(d["pos"]))
        self.cells_xz.add((int(math.floor(d["x"])), int(math.floor(d["z"]))))
        if self.baseline_y is not None and d["y"] <= self.baseline_y - 2.0 + 1e-6:
            self.add_hard("H_FALL", "y=%.2f 比基线 %.2f 低 >= 2 格（pos=%.2f,%.2f,%.2f）"
                          % (d["y"], self.baseline_y, d["x"], d["y"], d["z"]),
                          {"pos": list(d["pos"])})
        if d["mode"] != "survival":
            self.add_hard("H_MODE", "采样模式=%s（要求 survival；需要 Lead 设 gamemode）"
                          % d["mode"], {"pos": list(d["pos"])})
        if self.items0 is not None and d["items"] is not None:
            self.min_items = (d["items"] if self.min_items is None
                              else min(self.min_items, d["items"]))
        if d["hp"] is not None:
            if self.min_hp is None:
                self.min_hp = d["hp"]
            elif d["hp"] < self.min_hp - 1e-6:
                self.add_soft("S_HP_DROP", "hp %.1f → %.1f（pos=%.2f,%.2f,%.2f）"
                              % (self.min_hp, d["hp"], d["x"], d["y"], d["z"]))
                self.min_hp = d["hp"]
        if not d["onground"]:
            self.add_soft("S_AIRBORNE", "onground=false（pos=%.2f,%.2f,%.2f yaw=%.1f）"
                          % (d["x"], d["y"], d["z"], d["yaw"]))
            # ★卡死检测（D3c）✗★：悬空 + 位置不动持续 >=4s ⇒ 身体卡住了（真事故）
            prev = self._last_sample
            if (prev is not None
                    and math.hypot(d["x"] - prev["x"], d["z"] - prev["z"]) < 0.15
                    and abs(d["y"] - prev["y"]) < 0.15):
                prev_at = self._last_sample_at
                self.still_air_sec += max(0.0, (now - prev_at) if prev_at else 0.0)
                self.still_air_samples += 1
                if self.still_air_sec >= 4.0:
                    self.add_hard("H_STUCK",
                                  "悬空且位置连续不动 %.1f 秒（pos=%.2f,%.2f,%.2f，"
                                  "samples=%d）⇒ 身体卡死（D3c）"
                                  % (self.still_air_sec, d["x"], d["y"], d["z"],
                                     self.still_air_samples),
                                  {"pos": list(d["pos"])})
            else:
                self.still_air_sec = 0.0
                self.still_air_samples = 0
        else:
            self.still_air_sec = 0.0
            self.still_air_samples = 0
        if d.get("drops"):
            self.add_soft("S_GROUND_DROPS", "附近有 %d 个掉落物" % d["drops"])
        if self._last_sample is not None and self._last_tick is not None:
            prev_at = self._last_sample_at
            wall_dt = None if prev_at is None else (now - prev_at)
            tick = d["day"] * 24000 + d["time"]
            if wall_dt is not None and wall_dt >= 5.0:
                dtick = tick - self._last_tick
                if dtick <= 0:
                    self.stall_windows += 1
                    self.stall_sec += wall_dt
                    self.add_soft("S_WORLD_STALL", "世界刻 %d 没走（墙钟 %.1f 秒）"
                                  % (dtick, wall_dt))
                    if self.stall_sec >= 30.0:
                        self.add_inc("I_WORLD_STALLED",
                                     "世界刻累计停走 %.1f 秒 ⇒ 墙钟证据无效"
                                     % self.stall_sec)
                elif dtick < wall_dt * 20.0 * 0.2:
                    self.add_soft("S_WORLD_SLOW", "世界刻只走了 %d（墙钟 %.1f 秒，"
                                  "期望 ~%.0f）" % (dtick, wall_dt, wall_dt * 20.0))
            self._last_tick = tick
        self._last_sample = d
        self._last_sample_at = now

    # ── 每轮结束的物品对账 ──────────────────────────────────────────────
    def check_items_round(self, kind, start_items, end_items):
        if end_items is None or start_items is None:
            self.add_soft("S_ITEM_UNREAD", "这一轮读不到 items ⇒ 账对不上")
            return
        allowed = start_items - self._exp_round
        if end_items < allowed:
            self.add_hard("H_ITEM_LOSS",
                          "%s 轮：items %s ⇒ %s（本轮起点 %s，已解释消耗 %d）"
                          % (kind, start_items, end_items, start_items, self._exp_round),
                          {"round": kind})
        self._exp_round = 0

    # ── 轮次账本 ────────────────────────────────────────────────────────
    def note_round(self, kind, duration, detail=None):
        self.rounds.append(kind)
        if kind == "idle":
            self.idle_rounds += 1

    def note_walk(self, reached, result, moved, target):
        self.walk_attempts += 1
        if reached:
            self.walk_reached += 1
        elif result in ("unreachable", "blocked", "edge", "timeout", "humanoid_off",
                        "stopped_by_agent"):
            self.walk_refused += 1
        self.walk_max_moved = max(self.walk_max_moved, float(moved or 0.0))

    def note_work(self, placed, dug, cell, item):
        self.work_attempts += 1
        self.place_true += 1 if placed else 0
        self.dig_true += 1 if dug else 0
        if cell is not None:
            rec = self.work_cells.setdefault(tuple(cell),
                                             {"placed": False, "dug": False,
                                              "item": item})
            rec["placed"] = rec["placed"] or bool(placed)
            rec["dug"] = rec["dug"] or bool(dug)
            rec["item"] = item

    def next_placeable(self):
        for it in self.placeable:
            if it not in self._failed_items:
                return it
        return None

    def mark_item_failed(self, item):
        self._failed_items.add(item)

    def reset_failed_items(self):
        """★别因为一次 place 失败就永久禁用一件方块✗★（2026-11-02 实测踩过）"""
        self._failed_items.clear()
        self._place_streak.clear()

    def note_place_ok(self, item):
        self._place_streak.pop(item, None)
        self._failed_items.discard(item)

    def note_place_fail(self, item):
        """连续 3 次放不下才把这一件从候选里摘掉（单次失败可能只是那个格子刁）"""
        n = self._place_streak.get(item, 0) + 1
        self._place_streak[item] = n
        if n >= 3:
            self.mark_item_failed(item)

    # ── 收尾：活动证据 / 世界改动 / 判定 / 记分卡 ───────────────────────
    def activity_report(self):
        strolls_delta = None
        if self.idle_strolls0 is not None and self.idle_strolls_last is not None:
            strolls_delta = self.idle_strolls_last - self.idle_strolls0
        act = {
            "rounds": len(self.rounds),
            "by_kind": {k: self.rounds.count(k) for k in MIX},
            "distinct_cells": len(self.cells),
            "distinct_xz": len(self.cells_xz),
            "walk_attempts": self.walk_attempts, "walk_reached": self.walk_reached,
            "walk_refused": self.walk_refused,
            "walk_max_moved": round(self.walk_max_moved, 2),
            "work_attempts": self.work_attempts, "place_world_true": self.place_true,
            "dig_world_true": self.dig_true,
            "idle_rounds": self.idle_rounds,
            "idle_humanoid_confirmed": self.idle_humanoid_confirmed,
            "idle_strolls_delta": strolls_delta,
            "samples": self.samples,
        }
        planned = max(self.p.planned_sec(), 1.0)
        act["activity_ok"] = self.activity_ok(act, planned)
        return act

    def activity_ok(self, act, planned_sec):
        """★没被真正压到 ⇒ 测了等于没测✗★（INCONCLUSIVE，不是 PASS）"""
        long_enough = planned_sec >= 180.0
        if not long_enough:
            return act["distinct_xz"] >= 1
        if self.p.profile == "idle":
            return (act["distinct_xz"] >= 2
                    and (act["idle_strolls_delta"] or 0) >= 1)
        if self.p.profile == "walk":
            return (act["walk_attempts"] >= 2 and act["walk_reached"] >= 1
                    and act["distinct_xz"] >= 2)
        if self.p.profile == "work":
            return (act["work_attempts"] >= 1 and act["place_world_true"] >= 1
                    and act["dig_world_true"] >= 1)
        return (act["idle_rounds"] >= 1 and act["walk_reached"] >= 1
                and act["place_world_true"] >= 1 and act["dig_world_true"] >= 1
                and act["distinct_xz"] >= 2)

    def world_report(self):
        ours = set(self.work_cells.keys())
        residue = []
        for cell, rec in sorted(self.work_cells.items()):
            if rec["placed"] and not rec["dug"]:
                residue.append({"pos": list(cell), "why": "place 了没挖回"})
        foreign = sorted(self.world_mut - ours)
        rep = {
            "mut_events": len(self.world_mut),
            "our_cells": len(ours),
            "foreign_mut": [list(p) for p in foreign[:20]],
            "foreign_mut_count": len(foreign),
            "work_cells": [{"pos": list(c), "placed": r["placed"],
                            "dug": r["dug"], "item": r["item"]}
                           for c, r in sorted(self.work_cells.items())],
            "residue": residue,
            "work_atomic_place_dig": (self.place_true == self.dig_true),
            "walk_pillar": self.walk_pillar,
        }
        if foreign:
            self.add_soft("S_FOREIGN_MUT", "有 %d 处 mut 不是本套件动的（别的玩家/进程"
                          "改世界）" % len(foreign),
                          {"positions": [list(p) for p in foreign[:5]]})
        if residue:
            self.add_soft("S_WORLD_RESIDUE", "有 %d 格自己放下去没复原" % len(residue),
                          {"residue": residue[:5]})
        return rep

    def finalize(self, now, final_digest=None, activity=None, world=None,
                 duration=None, calls=None, calls_action=None, paths=None,
                 status="finished", aborted=None, extra_inc=None):
        self.ended_at = now
        self.ended_unix = time.time()
        if aborted:
            self.aborted = aborted
        for code, detail in (extra_inc or []):
            self.add_inc(code, detail)
        if final_digest is not None:
            self.final = {
                "pos": list(final_digest["pos"]), "mode": final_digest["mode"],
                "hp": final_digest["hp"], "food": final_digest["food"],
                "items": final_digest["items"], "kinds": final_digest["kinds"],
                "onground": final_digest["onground"],
                "time": final_digest["time"], "day": final_digest["day"],
                "held": final_digest["held"],
            }
            if final_digest["items"] is not None and self.items0 is not None:
                allowed = self.items0 - self.exp_loss
                if final_digest["items"] < allowed:
                    self.add_hard("H_ITEM_LOSS", "收尾 items %s < 基线 %s − 已解释 %d"
                                  % (final_digest["items"], self.items0, self.exp_loss))
        elif self.baseline is not None:
            self.add_inc("I_NO_FINAL_DIGEST", "跑完拿不到收尾 digest ⇒ 最终状态未证明")
        if activity is None:
            activity = self.activity_report()
        if self.armed and not activity.get("activity_ok", False):
            self.add_inc("I_NOT_ACTIVE",
                         "活动证据不足：%s ⇒ 这一档没有真正压到身体"
                         % {k: activity.get(k) for k in
                            ("by_kind", "distinct_xz", "walk_attempts", "walk_reached",
                             "work_attempts", "place_world_true", "dig_world_true",
                             "idle_strolls_delta")})
        if world is None:
            world = self.world_report()
        if self.hard:
            verdict, exit_code = "FAIL", 1
        elif self.inc:
            verdict, exit_code = "INCONCLUSIVE", 2
        else:
            verdict, exit_code = "PASS", 0
        planned_sec = self.p.planned_sec()
        duration = float(duration if duration is not None else
                         ((now - self.started_at) if self.started_at else 0.0))
        duration_ok = duration >= planned_sec * 0.95
        calls = int(calls or 0)
        calls_action = int(calls_action if calls_action is not None else calls)
        calls_oracle = max(0, calls - calls_action)
        # ★满档门槛按**动作调用**算 ✗ 不算 oracle drain✗★（见 Driver.calls_action 注释）
        full_bar = calls_action >= int(self.p.max_calls)
        # ★D3 绝对口径（契约 §9 / 30-verify §3.2）✗★：混合档 3 小时 **且** 调用数
        #   >= 2000 才叫"满 3h×2000 次"（--minutes 短跑/--max-calls 改门槛都不算）
        spec_min_sec = 180.0 * 60.0 * 0.95
        full_spec = bool(self.p.profile == "mixed"
                         and calls >= FULL_BAR_CALLS_DEFAULT
                         and duration >= spec_min_sec)
        criteria = {
            "D3a_zero_death": self.deaths == 0 and self.event_gaps == 0,
            "D3b_zero_item_loss": "H_ITEM_LOSS" not in self.hard_codes(),
            "D3c_no_hang_err": not ({"H_ERR", "H_STUCK"} & self.hard_codes()),
            "D3d_survival": "H_MODE" not in self.hard_codes(),
            "D3e_no_fall": "H_FALL" not in self.hard_codes(),
            "oracle_complete": self.event_gaps == 0,
            "activity_exercised": bool(activity.get("activity_ok")),
            "fully_specced_run": full_spec,
        }
        sc = {
            "schema": SCHEMA,
            "generated_at": now_iso(now),
            "generated_unix": time.time(),
            "verdict": verdict,
            "exit_code": exit_code,
            "profile": self.p.profile,
            "duration_sec": round(duration, 1),
            "duration_planned_sec": round(planned_sec, 1),
            "duration_ok": duration_ok,
            "started_at": now_iso(self.started_at) if self.started_at else None,
            "ended_at": now_iso(now),
            "calls": calls,
            "calls_action": calls_action,
            "calls_oracle": calls_oracle,
            "calls_full_bar": int(self.p.max_calls),
            "d3_calls_min": FULL_BAR_CALLS_DEFAULT,
            "d3_duration_min_sec": round(spec_min_sec, 1),
            "full_bar": full_bar,
            "full_spec_mixed_3h": full_spec,
            "rounds": {"total": len(self.rounds),
                       "by_kind": {k: self.rounds.count(k) for k in MIX},
                       "mix_ratio": (MIX if self.p.profile == "mixed"
                                     else {self.p.profile: 1.0})},
            "activity": activity,
            "hard_failures": self.hard,
            "soft_failures": self.soft,
            "soft_codes": dict(self.soft_seen),
            "inconclusive_reasons": self.inc,
            "hard_count": len(self.hard),
            "soft_count": sum(self.soft_seen.values()),
            "oracle": {
                "cursor_start": self.cursor_start, "cursor_end": self.cursor_end,
                "drains": self.oracle_drains, "events_seen": self.events_seen,
                "gaps": self.event_gaps, "truncated_drains": self.event_truncated,
                "event_rate_peak": round(self.event_rate_peak, 1),
                "noise_events": self.noise_events,
                "bot_died": self.deaths, "damage": self.damage_events,
                "inv_neg": self.inv_neg_events,
                "inv_large_drop": self.inv_large_drop_events,
                "mode": self.mode_events, "humanoid": self.humanoid_events,
                "auto_eat": self.auto_eat_events,
                "walk_start": self.walk_start_events, "walk_done": self.walk_done_events,
                "walk_refuse": self.walk_refuse_events,
                "kinds": self.event_kinds,
            },
            "world": world,
            "baseline": self.baseline,
            "final": self.final,
            "preconditions": dict(self.preconditions),
            "params": self.p.as_dict(),
            "criteria": criteria,
            "aborted_early": bool(self.aborted),
            "aborted_reason": self.aborted,
            "cleanup_errors": self.cleanup_errors,
            "evidence": paths or {},
        }
        self.status = verdict
        return sc


# ══════════════════════════════════════════════════════════════════════════
# I/O 辅助（都通过 driver ✗ 调用数全算✓）＋ 自适应事件 drain
# ══════════════════════════════════════════════════════════════════════════

def _sample(ctx) -> dict:
    rep = ctx.driver.digest()
    d = parse_digest(rep.text)
    if d is None:
        return None
    ctx.core.observe_sample(ctx.clock(), d)
    ctx.step.record({"type": "sample", "pos": [round(v, 2) for v in d["pos"]],
                     "hp": d["hp"], "food": d["food"], "mode": d["mode"],
                     "onground": d["onground"], "items": d["items"],
                     "time": d["time"], "day": d["day"],
                     "drops": d["drops"], "cells": len(ctx.core.cells)})
    return d


def _drain(ctx) -> dict:
    rep = ctx.driver.events(ctx.core.cursor)
    ev = parse_events(rep.text, ctx.core.cursor) if rep.ok else None
    ctx.core.observe_events(ctx.clock(), ev, rep)
    if ev is not None:
        interest = [e["raw"] for e in ev["events"] if e["kind"] in INTERESTING_EVENTS]
        ctx.step.record({"type": "oracle", "since": ev["since"], "cursor": ev["cursor"],
                         "new": ev["new"], "shown": ev["shown"],
                         "complete": ev["complete"], "gap": ev["gap"],
                         "noise": len(ev["events"]) - len(interest),
                         "events": interest})
    return ev


def _nap(ctx, seconds: float):
    """睡一段（★事件密时切片睡＋片间 drain✗★）。

    WHY：模组 `dshevents` 单次最多展示 **40** 条 ⇒ 若一次睡 1.2 秒而事件 80 条/秒，
    醒来一看 new=96 shown=40 ⇒ 中间那段（可能含 bot_died）永远看不到 ✗
    ⇒ drain 间隔按**实测速率**收：chunk = 28/rate，保证每次 new<=40
    （环只留 400 条 ⇒ 速率再高也必须 < 环容量；80/s ⇒ chunk≈0.35s ✓）。
    """
    left = max(0.0, float(seconds))
    if left <= 0:
        return
    # ★用"平滑速率"与"衰减峰值"的大者✗★：只看均值会在走动间隙误判"事件稀疏"
    #   ⇒ 睡太久 ⇒ 事件环被下一段走动灌满 ⇒ oracle gap（R-fullbar 实测踩过）
    rate = max(0.0, float(ctx.core.event_rate or 0.0),
               float(getattr(ctx.core, "event_rate_recent", 0.0) or 0.0))
    # ★见过走动 burst 之后：drain 速率下限抬到"历史峰值"✗★
    #   （峰值 42 条/秒 ⇒ chunk≈0.5s ⇒ 两次 drain 之间最多 ~21 条 < 单次展示上限 40）
    if getattr(ctx.core, "_yaw_burst_seen", False):
        rate = max(rate, float(ctx.core.event_rate_peak or 0.0))
    if rate <= 0.0 and left > 1.0:
        # ★先短睡 0.05 秒校准事件速率✗★ —— 否则第一次长睡按 rate=0 睡满 10 秒，
        #   事件环被灌满 ⇒ 丢事件（2.55.1 yaw 洪水下踩过的坑）。0.05 秒在
        #   520 条/秒时也只有 ~26 条 < 单次展示上限 40 ✓
        dt = min(0.05, left)
        ctx.sleep(dt)
        left -= dt
        _drain(ctx)
        rate = max(0.0, float(ctx.core.event_rate or 0.0))
    chunk = 10.0 if rate < 20.0 else max(0.05, min(2.0, 22.0 / rate))
    while left > 1e-6:
        if ctx.core.has_hard():
            return
        dt = min(chunk, left)
        ctx.sleep(dt)
        left -= dt
        if rate >= 20.0:
            _drain(ctx)
        elif ctx.clock() - (ctx.core.last_drain_at or 0.0) >= 2.0:
            _drain(ctx)
    if rate < 20.0 and ctx.clock() - (ctx.core.last_drain_at or 0.0) >= 2.0:
        _drain(ctx)


def _sleep_with_drain(ctx, seconds: float):
    """静默窗口专用（idle 溜达时**不许发**指令 ✗ 但事件还得 drain ✓）"""
    _nap(ctx, seconds)


def _cell_block(driver: Driver, cell):
    rep = driver.scan_cell(*cell)
    return parse_scan_cell(rep.text)


# ══════════════════════════════════════════════════════════════════════════
# 三档轮次
# ══════════════════════════════════════════════════════════════════════════

def round_idle(ctx, first: bool = False) -> dict:
    """溜达档：打开 idle（半径）⇒ 静默 interval 秒 ⇒ 采样 ⇒ 关 idle。

    ★静默是重点✗★：`dshidle` 有"最近 15 秒无模组指令"的闸（P25）⇒ 我一直发采样
    它就不动 ⇒ 那个"绿"什么也证明不了（d3_soak.py 头注释里已记过这个坑）。
    """
    core = ctx.core
    d0 = _sample(ctx)
    if d0 is None:
        return {"kind": "idle", "ok": False, "why": "digest_unreadable"}
    start_items = d0["items"]
    idle_st = parse_idle(ctx.driver.idle_status().text)
    if idle_st is None:
        core.add_soft("S_IDLE_STATUS", "读不到 idle 状态")
        return {"kind": "idle", "ok": False, "why": "idle_status_unreadable"}
    # ★平台模式：先回到锚点附近再开 idle✗★ —— 否则每轮 anchor 重置会让它一路漂到平台边
    if ctx.p.allow_void_platform and dist2d(d0["pos"], ctx.p.anchor) > 2.0:
        ax, ay, az = (int(v) for v in ctx.p.anchor)
        ctx.driver.walk(ax, ay, az, exact=True, ms=8000)
        for _ in range(6):
            _nap(ctx, 1.0)
            dd = _sample(ctx)
            if dd is not None and dist2d(dd["pos"], ctx.p.anchor) <= 1.2:
                break
    if idle_st["radius"] != ctx.p.radius:
        ctx.driver.idle_radius(ctx.p.radius)
    ctx.driver.idle_on()
    st2 = parse_idle(ctx.driver.idle_status().text)
    if st2 is None or not st2["humanoid"]:
        core.add_inc("I_IDLE_OFF", "idle 开不起来（回读 humanoid=%s）"
                     % (None if st2 is None else st2["humanoid"]))
        return {"kind": "idle", "ok": False, "why": "idle_not_on"}
    core.idle_live = True
    core.idle_humanoid_confirmed = True
    quiet = max(float(ctx.p.interval), 5.0)
    out = {"kind": "idle", "ok": True, "quiet_sec": quiet,
           "start": {"pos": [round(v, 2) for v in d0["pos"]], "items": start_items}}
    # ★真·静默窗口✗★：事件稀疏时**一次 drain 都不发**。
    #   WHY：drain 也是 /cmd ⇒ 模组每次 /cmd 都刷新 LAST_CMD_TICK ⇒ "最近 15 秒无指令"
    #   的溜达闸永远不开 ⇒ idle 16 轮 strolls Δ0（2026-11-02 实测踩到）。
    #   安全前提：`rate*quiet < 300` ⇒ 静默期事件数远小于环容量 400 ✓
    #   ⚠ 速率未知（第一轮）时先校准一次，否则会按"稀疏"睡满 ⇒ 环被灌满丢事件
    if (core.event_rate or 0.0) <= 0.0 and (core.event_rate_recent or 0.0) <= 0.0:
        ctx.sleep(min(0.05, quiet))
        _drain(ctx)
    rate = max(0.0, float(core.event_rate or 0.0),
               float(core.event_rate_recent or 0.0))
    if getattr(core, "_yaw_burst_seen", False):
        rate = max(rate, float(core.event_rate_peak or 0.0))
    if rate * quiet < 300.0:
        ctx.sleep(quiet)                          # 真静默：让它有机会溜达
        _drain(ctx)
    else:
        _sleep_with_drain(ctx, quiet)             # 事件密：只能切片 drain 保 oracle
    d1 = _sample(ctx)
    out["end"] = None if d1 is None else {
        "pos": [round(v, 2) for v in d1["pos"]], "items": d1["items"],
        "hp": d1["hp"], "mode": d1["mode"]}
    st_end = parse_idle(ctx.driver.idle_status().text)
    if st_end is not None:
        core.idle_strolls_last = st_end["strolls"]
        out["strolls"] = st_end["strolls"]
        out["looks"] = st_end["looks"]
    else:
        core.add_soft("S_IDLE_STATUS_END", "收尾读不到 idle 状态")
    ctx.driver.idle_off()
    core.idle_live = False
    _drain(ctx)
    core.check_items_round("idle", start_items, None if d1 is None else d1["items"])
    if d1 is not None:
        out["moved"] = round(dist2d(d0["pos"], d1["pos"]), 2)
    return out


def _cand_in_play_area(cand, ctx) -> bool:
    """候选格是否在允许的活动区内：锚点半径 + （平台模式）平台安全盒内"""
    if dist2d(cand, ctx.p.anchor) > SAFE_START_RADIUS + 2:
        return False
    if ctx.p.allow_void_platform:
        # 平台内部安全盒（16×16 石台去掉 1 格边缘 ⇒ x4146..4159 z3..16 都在实心台上）
        if not in_box((4146, 70, 3, 4159, 72, 16), tuple(cand)):
            return False
        ax, ay, az = (int(v) for v in ctx.p.anchor)
        if abs(cand[0] - ax) > 5 or abs(cand[2] - az) > 5:
            return False
    return True


def _walk_candidates(ctx, d0):
    """纯挑选候选格（真正"站得住"要调用方扫世界真值 ✓）"""
    base = cell_of(ctx.core.baseline["pos"])
    cur = cell_of(d0["pos"])
    cands = []
    r = int(ctx.p.radius)
    rx, ry, rz = base
    for _ in range(12):
        dx = ctx.rng.randint(-r, r)
        dz = ctx.rng.randint(-r, r)
        if abs(dx) + abs(dz) < 2:
            continue
        cand = (rx + dx, ry, rz + dz)
        if cand == cur or cand in cands:
            continue
        if dist2d(cand, cur) < 1.5:
            continue
        if not _cand_in_play_area(cand, ctx):
            continue
        if in_box(VOID_PLATFORM_BOX, cand) and not ctx.p.allow_void_platform:
            continue
        ok, _zone = touch_allowed(cand, ctx.p.allow_void_platform)
        if not ok:
            continue
        cands.append(cand)
        if len(cands) >= 3:
            break
    return cands


def round_walk(ctx) -> dict:
    core = ctx.core
    d0 = _sample(ctx)
    if d0 is None:
        return {"kind": "walk", "ok": False, "why": "digest_unreadable"}
    start_items = d0["items"]
    out = {"kind": "walk", "ok": False}
    cands = _walk_candidates(ctx, d0)
    if not cands:
        core.add_soft("S_NO_WALK_TARGET", "半径 %d 内挑不出安全目标" % ctx.p.radius)
        _drain(ctx)
        return out
    target = None
    for cand in cands:
        feet_scan = _cell_block(ctx.driver, cand)
        below_scan = _cell_block(ctx.driver, (cand[0], cand[1] - 1, cand[2]))
        if feet_scan is None or below_scan is None:
            continue
        if feet_scan["air"] != 1 or below_scan["solid"] != 1:
            continue
        target = cand
        break
    if target is None:
        core.add_soft("S_WALK_TARGET_UNSAFE", "候选目标没有'脚格空气＋脚下实心'")
        _drain(ctx)
        return out
    out["target"] = list(target)
    out["from"] = [round(v, 2) for v in d0["pos"]]
    ws = parse_walk_start(ctx.driver.walk(target[0], target[1], target[2]).text)
    if ws is None:
        core.add_soft("S_WALK_START_UNREADABLE", "walk 回执解析不了")
        _drain(ctx)
        return out
    core.walk_running = True
    if not ws["reachable"]:
        core.note_walk(False, "unreachable", 0.0, target)
        core.walk_running = False
        ctx.driver.walk_stop()
        out.update({"result": "unreachable", "moved": 0.0})
        ctx.step.record({"type": "walk", "target": list(target),
                         "reachable": False, "result": "unreachable"})
        _drain(ctx)
        core.check_items_round("walk", start_items, d0["items"])
        return out
    deadline = ctx.clock() + max(WALK_TIMEOUT_MIN,
                                 min(WALK_TIMEOUT_MAX, float(ctx.p.interval) * 0.6))
    st = None
    prev_at = None
    still = 0
    while ctx.clock() < deadline:
        if core.has_hard():
            break
        _nap(ctx, WALK_POLL_SEC)
        st = parse_walk_status(ctx.driver.walk_status().text)
        if st is not None and st.get("at") is not None:
            at = st["at"]
            if (prev_at is not None and st["status"] == "running"
                    and math.hypot(at[0] - prev_at[0], at[2] - prev_at[2]) < 0.15):
                still += 1
            elif prev_at is not None:
                still = 0
            prev_at = at
            if still >= 3:
                core.add_hard("H_STUCK",
                              "walk 回执 reachable=true 但连续 %d 次轮询位置不动"
                              "（at=%.2f,%.2f,%.2f）⇒ 身体卡死（D3c）"
                              % (still, at[0], at[1], at[2]))
                ctx.driver.walk_stop()
                core.walk_running = False
                break
        if st is not None and st["done"]:
            break
    if st is None or not st["done"]:
        ctx.driver.walk_stop()
        st = parse_walk_status(ctx.driver.walk_status().text) or st
    core.walk_running = False
    d1 = _sample(ctx)
    if d1 is None:
        _drain(ctx)
        return out
    reached = bool(st and st["result"] == "reached")
    if not reached and st is not None and st.get("at") is not None:
        if cell_of(st["at"]) == tuple(target):
            reached = True
    if cell_of(d1["pos"]) == tuple(target):
        reached = True
    moved = dist2d(d0["pos"], d1["pos"])
    core.note_walk(reached, (st or {}).get("result"), moved, target)
    out.update({"result": (st or {}).get("result"), "reached": reached,
                "moved": round(moved, 2), "why": (st or {}).get("why")})
    ctx.step.record({"type": "walk", "target": list(target), "reachable": True,
                     "result": out["result"], "reached": reached,
                     "moved": out["moved"], "from": out["from"]})
    _drain(ctx)
    core.check_items_round("walk", start_items, d1["items"])
    out["ok"] = True
    return out


def _work_candidates(ctx, feet):
    fx, fy, fz = feet
    cells = [(fx + 1, fy, fz), (fx - 1, fy, fz), (fx, fy, fz + 1), (fx, fy, fz - 1)]
    ctx.rng.shuffle(cells)
    good = []
    for c in cells:
        if not _cand_in_play_area(c, ctx):
            continue
        if in_box(VOID_PLATFORM_BOX, c) and not ctx.p.allow_void_platform:
            continue
        ok, _z = touch_allowed(c, ctx.p.allow_void_platform)   # ★no_dig✗★
        if not ok:
            continue
        good.append(c)
    return good


def _walk_then_pickup(ctx, cell, items_before, rounds: int = 8):
    """走到 cell（模组说不可达就如实返回 False）⇒ 等掉落物进背包。
    ⇒ `(items, walk_started)`；items 可能仍是 None（没读到 digest）。
    """
    ws = parse_walk_start(
        ctx.driver.walk(cell[0], cell[1], cell[2], exact=True, ms=8000).text)
    if ws is None or not ws["reachable"]:
        return None, False
    items = None
    prev_at = None
    still = 0
    for _ in range(rounds):
        if ctx.core.has_hard():
            break
        _nap(ctx, 1.0)
        st = parse_walk_status(ctx.driver.walk_status().text)
        if st is not None and st.get("at") is not None:
            at = st["at"]
            if (prev_at is not None and st.get("status") == "running"
                    and math.hypot(at[0] - prev_at[0], at[2] - prev_at[2]) < 0.15):
                still += 1
            elif prev_at is not None:
                still = 0
            prev_at = at
            if still >= 3:
                # ★回执说 reachable，人却不动 ⇒ 卡死 ✗ 立刻停，不越走越远✗★
                ctx.core.add_hard("H_STUCK",
                                  "捡回时走路卡死：回执 reachable=true 但连续 %d 次"
                                  "位置不动（at=%.2f,%.2f,%.2f）"
                                  % (still, at[0], at[1], at[2]))
                ctx.driver.walk_stop()
                return None, False
        dd = _sample(ctx)
        if dd is not None:
            items = dd["items"]
            if items is not None and items_before is not None and items >= items_before:
                break
    return items, True


def round_work(ctx) -> dict:
    """干活档：放一块**自己刚放的方块**再挖回来（★不挖平台本身✗★），必须捡得回来。"""
    core = ctx.core
    d0 = _sample(ctx)
    if d0 is None:
        return {"kind": "work", "ok": False, "why": "digest_unreadable"}
    start_items = d0["items"]
    feet = cell_of(d0["pos"])
    out = {"kind": "work", "ok": False, "feet": list(feet)}
    if not core.placeable:
        core.add_inc("I_NO_PLACEABLE", "背包里没有可放方块 ⇒ work 档测不了")
        _drain(ctx)
        return out
    item = core.next_placeable()
    if item is None:
        # ★别永久禁死✗★：可能只是某一次碰上了刁格子 ⇒ 重置名单再试
        core.reset_failed_items()
        core.add_soft("S_NO_USABLE_ITEM", "所有候选方块之前都放失败过 ⇒ 重置名单重试")
        item = core.next_placeable()
    if item is None:
        core.add_inc("I_NO_PLACEABLE", "背包里没有可放方块 ⇒ work 档测不了")
        _drain(ctx)
        return out
    # ★旁边有实体（真人/怪/商人/别的假人）⇒ 这一轮不动世界✗★
    #   WHY：`dshplace` 是直接把方块放下去 ⇒ 放进实体格子会挤压/窒息它 ✗
    #   口径：只挡"贴着"的实体（nearest<=1.8 格），或 6 格内有敌对怪
    probe = parse_digest(ctx.driver.digest(2).text)
    if probe is not None:
        nd = probe.get("nearest_dist")
        too_close = ((probe.get("ents") or 0) > 0 and nd is not None and nd <= 1.8)
        hostile_close = ((probe.get("hostiles") or 0) > 0 and nd is not None and nd <= 6.0)
        if too_close or hostile_close:
            core.add_soft("S_ENTITY_NEARBY",
                          "半径 2 内有实体 %s（最近 %s 格）⇒ 这轮不放方块"
                          % (probe.get("nearest"), nd))
            out["skipped"] = "entity_nearby"
            _drain(ctx)
            return out
    items_before = start_items
    placed = False
    target = None
    prep = None
    tried = []
    # ★放不下就换邻格再试✗★（实测 18:34：某一格 `no usable support face` 而邻格都行）
    for cand in _work_candidates(ctx, feet):
        sc = _cell_block(ctx.driver, cand)
        if sc is None or sc["air"] != 1:
            continue
        below = _cell_block(ctx.driver, (cand[0], cand[1] - 1, cand[2]))
        if below is None or below["solid"] != 1:
            continue
        # ★头顶净空✗★：脚格空气+脚下实心还不够 —— 头顶实心就**站不进去**
        #   ⇒ 掉落物也捡不回来（2026-11-02 长档第 81 轮真因：头顶是 oak_log）
        above = _cell_block(ctx.driver, (cand[0], cand[1] + 1, cand[2]))
        if above is None or above["air"] != 1:
            core.add_soft("S_WORK_NO_HEADROOM", "候选 %s 头顶不是空气 ⇒ 跳过（站不进去）"
                          % list(cand))
            continue
        prep = ctx.driver.place(cand[0], cand[1], cand[2], item)
        mid = _cell_block(ctx.driver, cand)
        tried.append(cand)
        if mid is not None and mid["solid"] == 1:
            placed = True
            target = cand
            break
        core.add_soft("S_PLACE_FAILED", "place 在 %s 没生效（%s）⇒ 换邻格再试"
                      % (list(cand), prep.tail(80)))
    if not placed:
        core.note_place_fail(item)
        core.note_work(False, False, None, item)
        out["placed_world"] = False
        out["place_reply"] = (prep.tail(160) if prep is not None else "no_candidate")
        out["tried"] = [list(c) for c in tried]
        ctx.step.record({"type": "work", "target": None, "item": item,
                         "placed_world": False, "dig_world": False,
                         "items_before": items_before, "items_after": None,
                         "tried": [list(c) for c in tried],
                         "place_reply": out["place_reply"]})
        _drain(ctx)
        # place 没生效 ⇒ 世界/背包都没动 ⇒ 用本轮起点的 items 对账（不是"读不到"）
        core.check_items_round("work", start_items, d0["items"])
        return out
    core.note_place_ok(item)
    core._pending_place_consumes += 1     # 接下来会有一条 inv delta=-1（自己花掉的）
    out["target"] = list(target)
    out["item"] = item
    out["placed_world"] = True
    out["place_reply"] = prep.tail(120)
    rep = ctx.driver.dig(target[0], target[1], target[2])
    after = _cell_block(ctx.driver, target)
    if after is None or after["solid"] != 0:
        ctx.driver.dig(target[0], target[1], target[2])   # 再挖一次（掉落/第一次没成）
        _nap(ctx, 0.5)
        after = _cell_block(ctx.driver, target)
    dug = bool(after is not None and after["air"] == 1)
    out["dig_world"] = dug
    out["dig_reply"] = rep.tail(120)
    if not dug:
        core.add_soft("S_DIG_NO_WORLD", "dig 没让世界变回去（%s）" % rep.tail(100))
    core.note_work(True, dug, target, item)
    # ★捡回来✗★：掉落物要进背包（最多 WORK_RECOVER_SEC 秒；不进就走过去捡）
    _nap(ctx, 1.2)                                    # 掉落物落地/吸附的喘息
    waited = 0.0
    items_after = None
    while waited <= WORK_RECOVER_SEC:
        if core.has_hard():
            break
        dd = _sample(ctx)
        items_after = None if dd is None else dd["items"]
        if (items_after is not None and items_before is not None
                and items_after >= items_before):
            break
        _nap(ctx, 1.5)
        waited += 1.5
    if items_after is None or items_before is None or items_after < items_before:
        # 还差 ⇒ 走过去捡（★目标格站不进去就试它四邻✗★ —— 掉落物在目标格附近，
        # 站在邻格也能吸到；2026-11-02 长档就死在"只试目标格、而它没净空"上）
        core.add_soft("S_PICKUP_SLOW", "等了 %.1f 秒没自动捡起来 ⇒ 走过去捡" % waited)
        recovery = []
        got, walked = _walk_then_pickup(ctx, target, items_before)
        recovery.append({"try": list(target), "walked": walked,
                         "items": got})
        if got is not None:
            items_after = got
        if items_after is None or items_before is None or items_after < items_before:
            tx, ty, tz = target
            for nb in [(tx + 1, ty, tz), (tx - 1, ty, tz),
                       (tx, ty, tz + 1), (tx, ty, tz - 1)]:
                if core.has_hard():
                    break
                if items_after is not None and items_before is not None \
                        and items_after >= items_before:
                    break
                nb_feet = _cell_block(ctx.driver, nb)
                nb_below = _cell_block(ctx.driver, (nb[0], nb[1] - 1, nb[2]))
                nb_above = _cell_block(ctx.driver, (nb[0], nb[1] + 1, nb[2]))
                if (nb_feet is None or nb_feet["air"] != 1
                        or nb_below is None or nb_below["solid"] != 1
                        or nb_above is None or nb_above["air"] != 1):
                    continue
                got, walked = _walk_then_pickup(ctx, nb, items_before)
                recovery.append({"try": list(nb), "walked": walked, "items": got})
                if got is not None:
                    items_after = got
        out["recovery"] = recovery
    out["items_before"] = items_before
    out["items_after"] = items_after
    out["ok"] = True
    ctx.step.record({"type": "work", "target": list(target), "item": item,
                     "placed_world": placed, "dig_world": dug,
                     "items_before": items_before, "items_after": items_after,
                     "residue": not dug})
    _drain(ctx)
    core.check_items_round("work", items_before,
                           d0["items"] if items_after is None else items_after)
    return out


# ══════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class RunCtx:
    driver: Driver
    core: SoakCore
    p: SoakParams
    rng: random.Random
    clock: object
    sleep: object
    step: StepLog
    out: object
    t_end: float
    schedule: MixedSchedule


def _unique_path(directory: Path, stem: str, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / (stem + suffix)
    i = 2
    while p.exists():
        p = directory / ("%s-%d%s" % (stem, i, suffix))
        i += 1
    return p


def _preflight(ctx) -> bool:
    """准备阶段：★任何一项不满足 ⇒ INCONCLUSIVE（退出码 2）✗ 绝不当 PASS✓★"""
    core, driver, p, out = ctx.core, ctx.driver, ctx.p, ctx.out
    pre = {}
    h = driver.health()
    pre["bridge"] = h.ok
    if not h.ok:
        core.add_inc("I_BRIDGE", "直连 8766 不通：%s" % h.tail(120))
        return False
    out("  直连 ok：%s" % h.tail(80))
    ver = parse_ver(driver.ver().text)
    pre["mod_version"] = None if ver is None else ver["version"]
    if ver is None:
        core.add_inc("I_CMD_LANE", "dshver 拿不到 ⇒ /cmd 车道不可用")
        return False
    out("  dshver=%s features=%s" % (ver["version"], ",".join(ver["features"][:8])))
    rep = driver.digest()
    d = parse_digest(rep.text)
    pre["bot"] = d is not None
    if d is None:
        core.add_inc("I_NO_BOT", "拿不到 dshdigest（Bot 不在/不在线？）：%s" % rep.tail(120))
        return False
    out("  Bot=%s pos=%.2f,%.2f,%.2f mode=%s hp=%.1f items=%s"
        % (d["name"], d["x"], d["y"], d["z"], d["mode"], d["hp"], d["items"]))
    pre["survival"] = d["mode"] == "survival"
    if not pre["survival"]:
        core.add_inc("I_NOT_SURVIVAL",
                     "Bot 模式是 %s，D3d 要求 survival ⇒ 需要 Lead 设；本套件不自动改"
                     % d["mode"])
        return False
    pre["safe_start"] = within_anchor(d["pos"], tuple(p.anchor), SAFE_START_RADIUS)
    if not pre["safe_start"]:
        core.add_inc("I_UNSAFE_START",
                     "起点 %.2f,%.2f,%.2f 不在锚点 %s 半径 %.0f 内 ⇒ 拒跑（安全边界）"
                     % (d["x"], d["y"], d["z"], p.anchor, SAFE_START_RADIUS))
        return False
    rep = driver.events(None)
    ev = parse_events(rep.text, None)
    pre["events"] = ev is not None
    if ev is None:
        core.add_inc("I_EVENTS", "读不到 /dshevents（死亡 oracle 没法做）：%s"
                     % rep.tail(120))
        return False
    out("  事件环：total=%d cursor=%d（从这里开始做增量 oracle）"
        % (ev["total"], ev["cursor"]))
    idle_st = parse_idle(driver.idle_status().text)
    pre["idle_status"] = idle_st is not None
    if idle_st is None and p.profile in ("idle", "mixed"):
        core.add_inc("I_IDLE_STATUS", "读不到 /dshidle status ⇒ idle/mixed 压不起来")
        return False
    auto_st = parse_auto(driver.auto_status().text)
    pre["autoeat_off"] = bool(auto_st is not None and not auto_st["eat"])
    inv = parse_inv_list(driver.inv_list().text)
    pre["inventory"] = inv is not None
    pre["plugin"] = {"anchor": list(p.anchor), "radius": p.radius,
                     "void_platform": list(VOID_PLATFORM_BOX),
                     "no_dig": "tools/no_dig.py"}
    core.set_baseline(d, idle_st, auto_st, ver, inv, ev["cursor"], ctx.clock(), pre)
    # ★平台模式：起点 3×3 必须空旷✗★（脚格空气+脚下实心+头顶空气）—— 不够空旷就拒跑
    if p.allow_void_platform:
        bad = []
        fx, fy, fz = cell_of(d["pos"])
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = (fx + dx, fy, fz + dz)
                feet = _cell_block(driver, c)
                below = _cell_block(driver, (c[0], c[1] - 1, c[2]))
                above = _cell_block(driver, (c[0], c[1] + 1, c[2]))
                if not (feet is not None and feet["air"] == 1
                        and below is not None and below["solid"] == 1
                        and above is not None and above["air"] == 1):
                    bad.append(c)
        pre["open_3x3"] = not bad
        if bad:
            core.add_inc("I_UNSAFE_START",
                         "平台模式要求起点 3×3 空旷（脚格空气+脚下实心+头顶空气），"
                         "实际不满足：%s" % [list(c) for c in bad[:6]])
            return False
        out("  平台模式：起点 3×3 空旷 ✓")
    if p.profile in ("work", "mixed") and not core.placeable:
        core.add_inc("I_NO_PLACEABLE",
                     "背包里找不到可放方块（试过 %s），work/mixed 测不了"
                     % ",".join(PLACEABLE[:8]))
        return False
    if auto_st is not None and auto_st["eat"]:
        out("  ⚠ 自动进食是开着的（物品减少会按'吃了'解释）")
    if idle_st is not None:
        out("  idle 原状：humanoid=%s radius=%d strolls=%d"
            % (idle_st["humanoid"], idle_st["radius"], idle_st["strolls"]))
        # ★开局把 idle 收归本套件管✗★（原状已记在 baseline，收尾还原）：
        #   否则它会在 round 之间的空档里溜达 ⇒ 位置/事件被它搅（P25 同族）
        if idle_st["humanoid"]:
            driver.idle_off()
            core.idle_live = False
            out("  idle 原为开 ⇒ 先关掉（收尾还原原状）")
    if inv is not None:
        n = sum(r["count"] for r in inv["items"])
        out("  背包：%d 类 / %d 个（可放方块候选：%s）"
            % (len(inv["items"]), n, ",".join(core.placeable[:4]) or "无"))
    return True


def _restore_idle_and_walk(ctx):
    """收尾还原：★不越权改世界✗ 只还原 idle 开关/半径，停掉自己开的走✗★"""
    core, driver = ctx.core, ctx.driver
    try:
        if core.idle_live:
            driver.idle_off()
            core.idle_live = False
        if core.walk_running:
            driver.walk_stop()
            core.walk_running = False
        base = core.idle_baseline
        if base is not None:
            cur = parse_idle(driver.idle_status().text)
            if cur is None or cur["radius"] != base["radius"]:
                driver.idle_radius(base["radius"])
            if base["humanoid"]:
                driver.idle_on()
                ctx.sleep(0.2)
            else:
                driver.idle_off()
    except Exception as exc:
        core.cleanup_errors.append("%s: %s" % (type(exc).__name__, exc))


def _write_scorecard(sc: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(sc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def _verdict_text(sc: dict) -> str:
    act = sc["activity"]
    orc = sc["oracle"]
    by = sc["rounds"]["by_kind"]
    lines = []
    lines.append("")
    lines.append("================ soak_suite 判定 ================")
    lines.append("  profile=%s ｜ 计划 %.1f 分钟 ｜ 实际 %.1f 秒（%.1f 分钟）"
                 % (sc["profile"], sc["duration_planned_sec"] / 60.0,
                    sc["duration_sec"], sc["duration_sec"] / 60.0))
    lines.append("  调用数 %d（动作 %d ＋ oracle %d；满档门槛按**动作** %d ⇒ %s）｜ "
                 "轮次 %d（idle %d ／ walk %d ／ work %d）"
                 % (sc["calls"], sc.get("calls_action", sc["calls"]),
                    sc.get("calls_oracle", 0), sc["calls_full_bar"],
                    "满档 ✓" if sc["full_bar"] else "★未满档（短跑只记实际次数 ✗ 不冒充）★",
                    sc["rounds"]["total"], by.get("idle", 0), by.get("walk", 0),
                    by.get("work", 0)))
    lines.append("  活动：不同格 %d ｜ walk 到达 %d/%d（最远 %.1f 格）｜ "
                 "place 真生效 %d ／ dig 真生效 %d ｜ idle %d 轮（strolls Δ%s）"
                 % (act.get("distinct_cells", 0), act.get("walk_reached", 0),
                    act.get("walk_attempts", 0), act.get("walk_max_moved", 0),
                    act.get("place_world_true", 0), act.get("dig_world_true", 0),
                    act.get("idle_rounds", 0), act.get("idle_strolls_delta")))
    lines.append("  事件 oracle：cursor %s→%s ｜ %d 次 drain ｜ 共见 %d 条（噪声 %d）｜ "
                 "峰值 %.0f 条/秒 ｜ bot_died=%d damage=%d inv-=%d mode=%d ｜ "
                 "gap=%d truncated=%d"
                 % (orc.get("cursor_start"), orc.get("cursor_end"), orc.get("drains", 0),
                    orc.get("events_seen", 0), orc.get("noise_events", 0),
                    orc.get("event_rate_peak", 0), orc.get("bot_died", 0),
                    orc.get("damage", 0), orc.get("inv_neg", 0), orc.get("mode", 0),
                    orc.get("gaps", 0), orc.get("truncated_drains", 0)))
    w = sc.get("world") or {}
    lines.append("  世界改动：mut %d（我方格 %d ／ 外来 %d）｜ 残留 %d ｜ walk pillar %d"
                 % (w.get("mut_events", 0), w.get("our_cells", 0),
                    w.get("foreign_mut_count", 0), len(w.get("residue") or []),
                    w.get("walk_pillar", 0)))
    lines.append("  硬失败 %d ｜ 软失败 %d ｜ INCONCLUSIVE %d ｜ 满档(3h/2000)=%s"
                 % (sc["hard_count"], sc["soft_count"],
                    len(sc["inconclusive_reasons"]), sc["full_spec_mixed_3h"]))
    for h in sc["hard_failures"][:8]:
        lines.append("  ★为什么红✗★ [%s] %s" % (h["code"], h["detail"]))
    for i in sc["inconclusive_reasons"][:8]:
        lines.append("  ⚠ 测不了 [%s] %s" % (i["code"], i["detail"]))
    if sc["soft_failures"]:
        shown = {}
        for s in sc["soft_failures"]:
            shown.setdefault(s["code"], []).append(s["detail"])
        for code, ds in shown.items():
            lines.append("  ⚠ 软失败 [%s] ×%d：%s"
                         % (code, len(ds), "; ".join(ds[:3])[:200]))
    lines.append("  判据：%s" % json.dumps(sc["criteria"], ensure_ascii=False))
    lines.append("  => SOAK %s（exit=%d）｜ 证据 %s ／ %s"
                 % (sc["verdict"], sc["exit_code"],
                    sc["evidence"].get("jsonl"), sc["evidence"].get("run_log")))
    return "\n".join(lines)


def run_soak(driver: Driver, p: SoakParams, *, clock=time.time, sleep=time.sleep,
             log_dir=None, scorecard_path=None, out=None):
    """跑一档 ⇒ 记分卡 dict（同时落盘）。★任何异常都要留下 INCONCLUSIVE 记分卡✗★"""
    out = out or (lambda s: print(s, flush=True))
    log_dir = Path(log_dir or LOGS)
    scorecard_path = Path(scorecard_path or (STATE / "soak_scorecard.json"))
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(clock()))
    jsonl = _unique_path(log_dir, "soak_%s" % ts, ".jsonl")
    runlog = jsonl.with_suffix(".run.log")
    step = StepLog(jsonl)
    core = SoakCore(p)
    driver.log = step
    driver.on_error = core.note_error
    core.started_at = clock()
    rng = random.Random(int(p.seed))
    schedule = MixedSchedule(int(p.seed), MIX, p.profile)
    t_end = clock() + p.planned_sec()
    ctx = RunCtx(driver=driver, core=core, p=p, rng=rng, clock=clock, sleep=sleep,
                 step=step, out=out, t_end=t_end, schedule=schedule)
    out("== soak_suite：profile=%s 计划 %.1f 分钟 ｜ interval=%.0fs radius=%d "
        "seed=%d max_calls=%d ==" % (p.profile, p.minutes, p.interval, p.radius,
                                     p.seed, p.max_calls))
    pre_ok = False
    try:
        pre_ok = _preflight(ctx)
        if pre_ok:
            out("  起跑：%s" % p.as_dict())
            while True:
                now = clock()
                if now >= ctx.t_end:
                    break
                if core.has_hard():
                    core.aborted = "hard_failure"
                    out("  ★已有硬失败 ⇒ 提前收尾（不再继续动世界）★")
                    break
                kind = schedule.next_kind()
                t_round0 = clock()
                try:
                    if kind == "idle":
                        r = round_idle(ctx)
                    elif kind == "walk":
                        r = round_walk(ctx)
                    else:
                        r = round_work(ctx)
                except Exception as exc:
                    core.add_inc("I_INTERNAL", "轮次异常 %s: %s"
                                 % (type(exc).__name__, exc))
                    step.record({"type": "internal_error", "kind": kind,
                                 "trace": traceback.format_exc()[-1200:]})
                    core.aborted = "internal_error"
                    break
                dur = clock() - t_round0
                core.note_round(kind, dur, r)
                step.record({"type": "round", "n": len(core.rounds), "kind": kind,
                             "dur": round(dur, 2), "result": r})
                out("[%d] %-4s %5.1fs %s ｜ calls=%d hard=%d soft=%d ｜ %s"
                    % (len(core.rounds), kind, dur,
                       (("pos=%s" % (r.get("end") or {}).get("pos"))
                        if kind == "idle" else
                        ("target=%s result=%s" % (r.get("target"), r.get("result")))
                        if kind == "walk" else
                        ("target=%s 世界放=%s 挖=%s items %s⇒%s"
                         % (r.get("target"), r.get("placed_world"),
                            r.get("dig_world"), r.get("items_before"),
                            r.get("items_after")))),
                       driver.calls, len(core.hard), sum(core.soft_seen.values()),
                       "★HARD★" if core.has_hard() else ""))
                _nap(ctx, ROUND_GAP_SEC)
    except KeyboardInterrupt:
        core.add_inc("I_INTERRUPTED", "收到 Ctrl-C：没跑完 ⇒ 不算 PASS")
        core.aborted = "interrupted"
    except Exception as exc:
        core.add_inc("I_INTERNAL", "套件异常 %s: %s" % (type(exc).__name__, exc))
        step.record({"type": "internal_error", "trace": traceback.format_exc()[-1200:]})
        core.aborted = "internal_error"
    # ── 收尾：preflight 失败时也只做"能做的" ──────────────────────────
    final_d = None
    try:
        if core.baseline is not None:
            final_d = parse_digest(driver.digest().text)
            if final_d is not None:
                core.observe_sample(clock(), final_d)
            rep = driver.events(core.cursor)
            ev = parse_events(rep.text, core.cursor) if rep.ok else None
            core.observe_events(clock(), ev, rep)
            if parse_inv_list(driver.inv_list().text) is not None:
                pass
            _restore_idle_and_walk(ctx)
    except Exception as exc:
        core.cleanup_errors.append("finalize:%s: %s" % (type(exc).__name__, exc))
    world = core.world_report() if core.baseline is not None else {}
    activity = (core.activity_report() if core.baseline is not None
                else {"activity_ok": False, "by_kind": {}, "distinct_xz": 0})
    duration = clock() - (core.started_at or clock())
    sc = core.finalize(clock(), final_digest=final_d, activity=activity, world=world,
                       duration=duration, calls=driver.calls,
                       calls_action=driver.calls_action, status="finished",
                       paths={"jsonl": str(jsonl).replace("\\", "/"),
                              "run_log": str(runlog).replace("\\", "/"),
                              "scorecard": str(scorecard_path).replace("\\", "/"),
                              "jsonl_lines": step.n},
                       aborted=core.aborted)
    sc["preconditions"] = dict(sc.get("preconditions") or {})
    sc["preconditions"]["preflight_ok"] = pre_ok
    sc["driver"] = {"calls": driver.calls, "calls_action": driver.calls_action,
                    "calls_oracle": max(0, driver.calls - driver.calls_action),
                    "errors": len(driver.errors),
                    "latency_ms_avg": round(sum(driver.latency_ms) /
                                            max(1, len(driver.latency_ms)), 2)}
    try:
        _write_scorecard(sc, scorecard_path)
    except Exception as exc:
        out("★写 scorecard 失败✗★：%s: %s" % (type(exc).__name__, exc))
    text = _verdict_text(sc)
    out(text)
    try:
        runlog.write_text(text + "\n", encoding="utf-8")
    except Exception as exc:
        out("★写 run log 失败✗★：%s: %s" % (type(exc).__name__, exc))
    step.close()
    return sc


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════
# 代码冻结（3 夜无人值守期间"跑一半换实现"必须被照出来 ✗）
# ══════════════════════════════════════════════════════════════════════════

FREEZE_SCHEMA = "dshbridge/soak_freeze@1"
FREEZE_FILES = ("tools/soak_suite.py", "tools/soak_suite_test.py",
                "tools/d3_soak.py", "tools/soak_night.ps1")


def _sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze_write(path: Path) -> int:
    """把当前实现文件的 sha256 写成冻结清单（离线 ✓）"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    files = {}
    for rel in FREEZE_FILES:
        p = ROOT / rel
        files[rel] = _sha256_file(p) if p.is_file() else None
    data = {"schema": FREEZE_SCHEMA, "generated_at": now_iso(),
            "generated_unix": time.time(), "files": files}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    os.replace(str(tmp), str(path))
    print("FREEZE WRITTEN %s  files=%d" % (path, len(files)))
    for rel, h in files.items():
        print("  %-28s %s" % (rel, h))
    return 0


def freeze_check(path: Path) -> int:
    """核对实现文件与冻结清单一致（不一致 ⇒ exit 2，**不许继续跑**）"""
    path = Path(path)
    if not path.is_file():
        print("FREEZE MISSING %s ⇒ 先跑 `py tools/soak_suite.py --freeze write`" % path)
        return 2
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print("FREEZE BAD %s ⇒ %r" % (path, exc))
        return 2
    if data.get("schema") != FREEZE_SCHEMA:
        print("FREEZE BAD schema=%r（期望 %s）" % (data.get("schema"), FREEZE_SCHEMA))
        return 2
    want = data.get("files") or {}
    bad = []
    for rel in FREEZE_FILES:
        p = ROOT / rel
        got = _sha256_file(p) if p.is_file() else None
        if got != want.get(rel):
            bad.append({"file": rel, "expected": want.get(rel), "actual": got})
    if bad:
        print("FREEZE CHANGED（★跑一半换实现✗★）:")
        for b in bad:
            print("  %-28s expected=%s actual=%s"
                  % (b["file"], (b["expected"] or "?")[:12], (b["actual"] or "?")[:12]))
        return 2
    print("FREEZE OK %s（%d 个实现文件与冻结清单一致）" % (path, len(want)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="D3 soak 套件：mixed/idle/walk/work ＋ 事件 oracle ＋ 记分卡",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--profile", default="mixed",
                    choices=["mixed", "idle", "walk", "work"])
    ap.add_argument("--minutes", type=float, default=180.0)
    ap.add_argument("--interval", type=float, default=30.0,
                    help="idle 静默秒数／walk 超时参照；idle 档建议 >=60")
    ap.add_argument("--radius", type=int, default=4,
                    help="溜达/走路目标半径（安全起见 4~6）")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-calls", type=int, default=FULL_BAR_CALLS_DEFAULT,
                    help="满档门槛（调用数 >= 它才算满档；短跑只记实际次数）")
    ap.add_argument("--anchor", default=None,
                    help="测试区锚点 x,y,z（默认取 world_profile.soak_anchor；"
                         "无档案时用本机默认 4121,71,15，会打印说明；起点必须在它半径 16 内）")
    ap.add_argument("--allow-void-platform", action="store_true",
                    help="允许在虚空测试平台（x4145..4160 z2..17 y=70）上跑；"
                         "平台模式会加 3×3 空旷 preflight + 平台安全盒 + idle 先回锚点")
    ap.add_argument("--freeze", choices=["write", "check"], default=None,
                    help="代码冻结清单：write 写 state/soak_freeze.json；"
                         "check 核对（不一致 exit 2）—— 3 夜无人值守用")
    ap.add_argument("--freeze-file", default=str(STATE / "soak_freeze.json"),
                    help="冻结清单路径")
    return ap


def main(argv) -> int:
    try:
        ns = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if ns.freeze == "write":
        return freeze_write(Path(ns.freeze_file))
    if ns.freeze == "check":
        return freeze_check(Path(ns.freeze_file))
    try:
        if ns.anchor is not None and str(ns.anchor).strip():
            anchor = tuple(int(v) for v in str(ns.anchor).split(","))
        else:
            anchor = tuple(default_anchor())          # ★world_profile 优先✗★
        if len(anchor) != 3:
            raise ValueError("anchor 必须是 x,y,z")
    except Exception as exc:
        print("--anchor 解析失败：%s" % exc)
        return 2
    p = SoakParams(profile=ns.profile, minutes=float(ns.minutes),
                   interval=float(ns.interval), radius=int(ns.radius),
                   seed=int(ns.seed), max_calls=int(ns.max_calls), anchor=anchor,
                   allow_void_platform=bool(ns.allow_void_platform))
    if p.allow_void_platform:
        if p.radius > 3:
            print("⚠ 平台模式半径 %d：测试平台 16×16 建议 --radius 3" % p.radius)
        if p.interval < 30:
            print("⚠ 平台模式 interval %.0fs 偏小：idle 需要 >=15s 静默才动" % p.interval)
    if p.profile == "idle" and p.interval < 60:
        print("⚠ idle 档间隔 %.0f 秒偏小：dshidle 要'最近 15 秒无指令'才自作主张"
              "（P25）⇒ 采样太密会把它压得不动，建议 --interval 60~120" % p.interval)
    if p.radius > 6:
        print("⚠ 半径 %d 偏大：测试区只保证小范围安全（建议 4~6）" % p.radius)
    driver = Driver()
    sc = run_soak(driver, p)
    return int(sc["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
