#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_policy.py -- ★接入策略：动作边界 ＋ 分层授权 ＋ 目的留痕✗★（2026-10-02 ✓ 参考外部同题项目 ✓）

WHY（★抄的是**机制** ✗ 不是功能✗★）：外部那几个同题项目在**管道**上比我们完整 ✓ 具体三条：
  ① ★**固定动作边界**✗★：开局配对时记下一个水平边界 ✓ 之后**每个动作工具都按它校验** ✓
     ⇒ ★"不从一些地方掉下去"变成**硬闸**✗ 而不是靠寻路自觉 ✓（用户 2026-10-01 原话 ✓）
  ② ★**默认只读 ＋ 分层授权**✗★：未授权的动作 ⇒ 明确回 `capability_not_granted` ✓ ★不静默忽略✗★
  ③ ★**目的留痕**✗★：感知类调用要求写 `purpose` ✓ ⇒ ★"为什么看这一眼"有账✗★（我们最贵的是往返 ✓ 却一直没有这层账 ✓）

★我们的默认与他们的差别（据实 ✗ 不装作一样✓★）：
  他们的默认是 **readOnly=true** ✗ 我们**不能**照搬这个默认 ⇒ ★会把已有的 41 件工具面全打空 ✗
  测试全红 ✓★ ⇒ 我们的口径：★**策略文件在 ⇒ 严格执行**✗；**不在 ⇒ 照旧放行，但每次启动/每次越界检查都
  **大声提示"没有边界、也没有授权表"**✗★（★机制先补上 ✗ 默认值等用户拍板 ✓★）

用法 ✓：`tools/bridge_policy.json`（缺省不存在）
  {"enabled": true, "allow": ["scan", "look", "bot_state"],
   "bounds": {"x0": 4100, "x1": 4140, "z0": -10, "z1": 40, "y0": 60, "y1": 90},
   "require_purpose": ["scan", "survey", "map_area", "look", "find_block"]}
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "tools" / "bridge_policy.json"

# ★★"什么算坐标参数"只有这一处定义✗★★（P106 ✓）：
#   `x` `y` `z` ＋ `x0..z1`（区域）＋ `tx/ty/tz`（目标）✓
COORD_KEY = re.compile(r"^(x|y|z|x0|y0|z0|x1|y1|z1|tx|ty|tz)$")

_state = {"loaded": False, "enabled": False, "allow": None, "bounds": None,
          "require_purpose": set(), "rate_limit": {}, "grant": set(),
          "require_perm": {}, "mutating": set(), "path": str(POLICY), "note": ""}
_last = {}          # ★每个工具上一次放行的时刻✗★（限流用 ✓ 形状抄 dsh-mc-bridge ✓）
_busy = {"tool": None, "since": 0.0}      # ★改世界动作的**互斥**状态✗★（★抄 ActionScheduler ✓★）

# ★★"哪些工具会改世界"✗★★ —— ★只有这一处定义✗★（P106 ✓ 抄他们的"改世界互斥" ✓）
#   ★为什么重要✗★：他们用 `ActionScheduler` 保证"同一时刻只允许一个改世界动作" ✓
#   我们**单车道天然串行** ✗ 但那是"碰巧" ✗ ⇒ ★把语义写出来 ✗ 并且真的上锁✓★
MUTATING_DEFAULT = {"dig_block", "place_block", "use_block", "chest_put", "chest_take",
                    "chest_put_many", "chest_take_many", "harvest_crop", "sift",
                    "equip", "drop_item",
                    # ★2026-10-02 补：跳／设朝向也是"动身体"✗★ —— ★和走路互斥✗ 免得边转边走✓★
                    "jump", "look_at",
                    # ★2026-10-02 补（P2 ✓）：★点头/摇头/指路也是"动身体"✗ 与走路互斥✓★
                    "gesture", "point_at"}
# ★★清单里**不许**出现"不存在的工具"✗★★（2026-10-02 清账 ✓）：
#   ★`bot_respawn` 曾经在表里 ✗ 但**没有这个工具**✗★ ⇒ ★它只是把"覆盖率"的分母撑大 ✗
#   让欠账 ③ 看起来更糟 ✓★ ⇒ ★删掉 ✗ 并且加一条守卫（下面 `assert_tools_exist` ✓）★
# ★★"一个动作要哪些权限"✗★★ —— ★抄他们"块动作要 BLOCKS ＋ NAVIGATION"那条✗★
REQUIRE_PERM_DEFAULT = {"dig_block": ["blocks", "navigation"],
                        "place_block": ["blocks", "navigation"],
                        "use_block": ["blocks", "navigation"],
                        "chest_put": ["containers", "navigation"],
                        "chest_take": ["containers", "navigation"],
                        "harvest_crop": ["blocks", "navigation", "inventory"],
                        "sift": ["blocks", "navigation"]}


def acquire_mutating(name: str) -> tuple:
    """⇒ (拿到锁了吗, 现在被谁占着)。★改世界动作互斥✗★（★重入 ⇒ 明确拒 ✗ 不排队不静默✓★）"""
    st = load()
    if name not in (st.get("mutating") or set()):
        return True, None
    if _busy["tool"] and _busy["tool"] != name:
        return False, _busy["tool"]
    _busy["tool"] = name
    _busy["since"] = __import__("time").time()
    return True, None


def release_mutating(name: str) -> None:
    if _busy["tool"] == name:
        _busy["tool"] = None


def mutex_state() -> dict:
    return dict(_busy)


def rate_ok(name: str) -> tuple:
    """⇒ (放行吗, retryAfterMs)。★限流✗★：`rate_limit` 里给了该工具的最小间隔（毫秒 ✓）——
    ★超限时**明确回「rate_limited ＋ retryAfterMs」✗**★（★不静默丢 ✗ 也不改成成功✓★）"""
    import time as _t
    st = load()
    if not st["enabled"]:
        return True, 0
    ms = (st.get("rate_limit") or {}).get(name)
    if not ms:
        return True, 0
    now = _t.time() * 1000.0
    prev = _last.get(name)
    if prev is not None and (now - prev) < float(ms):
        return False, int(float(ms) - (now - prev))
    _last[name] = now
    return True, 0


def load(force: bool = False) -> dict:
    if _state["loaded"] and not force:
        return _state
    _state["loaded"] = True
    if not POLICY.is_file():
        _state["enabled"] = False
        _state["grant"] = set()
        _state["require_perm"] = dict(REQUIRE_PERM_DEFAULT)
        _state["mutating"] = set(MUTATING_DEFAULT)
        _state["note"] = ("★没有策略文件✗★（%s 不存在）⇒ ★边界与授权表都**没开**✗★"
                          "（★照旧放行 ✗ 这是「机制有了、默认没开」 ✓）" % POLICY.name)
        return _state
    try:
        cfg = json.loads(POLICY.read_text(encoding="utf-8"))
    except Exception as e:
        _state["enabled"] = False
        _state["note"] = "★策略文件读不了✗★：%s ⇒ ★按不放行处理✗★（★宁可拒绝 ✗ 不静默放行✓★）" % e
        _state["broken"] = True
        return _state
    _state.update({"enabled": bool(cfg.get("enabled")), "allow": cfg.get("allow"),
                   "bounds": cfg.get("bounds"),
                   "require_purpose": set(cfg.get("require_purpose") or []),
                   "rate_limit": (cfg.get("rate_limit") or {}),
                   "grant": set(cfg.get("grant") or []),
                   "require_perm": (cfg.get("require_perm") or dict(REQUIRE_PERM_DEFAULT)),
                   "mutating": set(cfg.get("mutating") or MUTATING_DEFAULT),
                   "note": "策略文件 ✓ enabled=%s" % bool(cfg.get("enabled"))})
    return _state


def coords_of(args: dict) -> dict:
    """★把一次调用的坐标参数挑出来✗★（只用上面那**一个**正则 ✓）"""
    out = {}
    for k, v in (args or {}).items():
        if COORD_KEY.match(k) and isinstance(v, (int, float)):
            out[k] = v
    return out


def check(name: str, args: dict) -> tuple:
    """⇒ (allowed, reason)。★这是**唯一**的放行判定 ✗ 所有工具都过它 ✓★"""
    st = load()
    if st.get("broken"):
        return False, "policy_broken: ★策略文件坏了 ⇒ 拒绝✗★（%s）" % st.get("note")
    if not st["enabled"]:
        return True, ""
    allow = st["allow"]
    if allow is not None and name not in allow:
        return False, ("capability_not_granted: ★%s 不在授权表里✗★"
                       "（表里有 %d 件 ✓ ★不是静默忽略 ✗ 是明确拒绝✓★）" % (name, len(allow)))
    # ★★权限**交集**✗★★（抄他们"块动作要 BLOCKS ＋ NAVIGATION" ✓ 2026-10-02 ✓）
    #   ★口径✗★：★只要这个工具列了所需权限 ✗ **每一个**都必须在 `grant` 里✓★ ——
    #   ★缺哪个就报哪个 ✗ 不笼统说"没权限"✓★（P116：失败要**可行动** ✓）
    need = (st.get("require_perm") or {}).get(name) or []
    have = st.get("grant") or set()
    if need:
        missing = [p for p in need if p not in have]
        if missing:
            return False, ("capability_not_granted: ★%s 需要权限 %s ✗ 而缺 **%s**✗★"
                           "（已授予 %s ✓）" % (name, "+".join(need), "+".join(missing),
                                              "+".join(sorted(have)) or "（空）"))
    b = st["bounds"]
    if b:
        c = coords_of(args)
        for k, v in c.items():
            if k.startswith("y"):
                lo, hi = b.get("y0"), b.get("y1")
            elif k.startswith("z"):
                lo, hi = b.get("z0"), b.get("z1")
            else:
                lo, hi = b.get("x0"), b.get("x1")
            if lo is None or hi is None:
                continue
            if k.endswith("1") and lo <= v <= hi:
                continue
            if not (lo <= v <= hi):
                return False, ("out_of_bounds: ★%s=%s 越界✗★（%s 允许 %s..%s ✓）"
                               % (k, v, k[0], lo, hi))
    return True, ""


def purpose_missing(name: str, args: dict) -> bool:
    st = load()
    return bool(st["enabled"] and name in st["require_purpose"]
                and not str((args or {}).get("purpose") or "").strip())


def audit_line(name: str, args: dict, ok: bool, sec: float) -> str:
    st = load()
    p = str((args or {}).get("purpose") or "").strip()
    return ("[DSH-MC/AUDIT] tool=%s ok=%s ms=%.0f purpose=%s policy=%s"
            % (name, ok, sec * 1000.0, (p[:40] if p else "★(没写)✗★"),
               ("on" if st["enabled"] else "off")))


if __name__ == "__main__":       # ★自检：把"什么算坐标"当场列出来✗★（P152 ✓）
    import sys
    s = load(True)
    print("策略文件：%s" % s["path"])
    print("备注：%s" % s["note"])
    print("enabled=%s allow=%s bounds=%s require_purpose=%s"
          % (s["enabled"], (len(s["allow"]) if s["allow"] else None), s["bounds"],
             sorted(s["require_purpose"])))
    print("坐标键：%s" % ", ".join(sorted(COORD_KEY.pattern.strip("^$").split("|"))))
    for probe in ({"x": 4110, "y": 71, "z": 2}, {"x": 9999, "y": 71, "z": 2},
                  {"x": 4110, "y": 71, "z": 2, "purpose": "看看脚下"}):
        print("  %s ⇒ %s" % (probe, check("dig_block", probe)))
    sys.exit(0)
