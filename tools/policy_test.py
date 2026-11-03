#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""policy_test.py -- ★接入策略的判据✗★（离线 ✓ 秒级 ✓ P1~P5 ✓ 2026-10-02 ✓）

WHY ✓：`mcp_policy` 是**新加的机制**（动作边界 ＋ 分层授权 ＋ 目的留痕 ✓ 参考外部同题项目 ✓）
  ⇒ ★新机制没有守卫 = 会烂✗★（本项目老规矩 ✓）⇒ 这里给它五条最小判据 ✓

判据（★先写死 ✗ 不许事后改 ✓★）
  P1 ★没有策略文件 ⇒ 照旧放行✗★（★但必须**说得出**"机制没开"✓ —— 不许静默 ✓）
  P2 ★策略在但坏了 ⇒ **拒绝**✗★（★宁可拒绝 ✗ 不静默放行✓★）
  P3 ★授权表：不在表里 ⇒ `capability_not_granted`✗★（★明确拒绝 ✗ 不是忽略✓★）
  P4 ★边界：越界 ⇒ `out_of_bounds`✗★；界内 ⇒ 放行 ✓（★由**唯一那一个**坐标正则挑参数✓ P106/P152 ✓）
  P5 ★目的留痕：要求了 purpose 而没写 ⇒ 拦✗★；写了 ⇒ 放行 ✓
  ★测试用**临时策略文件**✗★（★绝不动真仓库里的 tools/bridge_policy.json✗★）
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

Fake = ROOT / "tools" / "bridge_policy.json"
saved = Fake.read_bytes() if Fake.is_file() else None
ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def fresh():
    import mcp_policy
    importlib.reload(mcp_policy)
    mcp_policy.load(force=True)
    return mcp_policy


try:
    if Fake.is_file():
        Fake.unlink()
    P = fresh()
    allowed, why = P.check("dig_block", {"x": 9999, "y": 71, "z": 9})
    check("P1", allowed and "没有策略文件" in P.load()["note"],
          "没策略文件 ⇒ 放行 ✓ 且说明里写着「机制没开」 ✓")
    Fake.write_text("{ 这不是 json", encoding="utf-8")
    P = fresh()
    allowed, why = P.check("dig_block", {"x": 4110, "y": 71, "z": 9})
    check("P2", (not allowed) and "policy_broken" in why, "策略坏了 ⇒ 拒绝 ✓（%s）" % why[:40])
    Fake.write_text(json.dumps({"enabled": True, "allow": ["bot_state", "scan"],
                                "bounds": {"x0": 4100, "x1": 4140, "z0": -10, "z1": 40,
                                           "y0": 60, "y1": 90},
                                "require_purpose": ["scan"]}), encoding="utf-8")
    P = fresh()
    a, w = P.check("dig_block", {"x": 4110, "y": 71, "z": 9})
    check("P3", (not a) and "capability_not_granted" in w, "未授权 ⇒ 明确拒绝 ✓（%s）" % w[:46])
    # ★注：P4/P5 用的 `scan` **必须在授权表里**✗★ —— 否则会在 P3 那道闸就被拦下 ✗
    #   ★（第一版测试就是这么错的 ✗ 三个闸的**先后**是 P3 → P4 → P5 ✓ 判据要按这个顺序写 ✓）★
    a2, w2 = P.check("scan", {"x": 9999, "y": 71, "z": 9})
    a3, w3 = P.check("scan", {"x": 4112, "y": 71, "z": 9})
    # ★注：边界与目的是**两道闸**（`check` 管边界/授权 ✓ `purpose_missing` 管目的 ✓）
    #   ⇒ ★判据要分别问 ✗ 第一版我把它们混在 `check` 里 ⇒ 假红 ✓（P152：先看清接口再写判据 ✓）★
    check("P4", (not a2) and "out_of_bounds" in w2 and a3 and not w3,
          "越界拒 ✓（%s）｜界内放行 ✓" % w2[:40])
    m_no = P.purpose_missing("scan", {"x": 4112, "y": 71, "z": 9})
    m_yes = P.purpose_missing("scan", {"x": 4112, "y": 71, "z": 9, "purpose": "看看脚下"})
    check("P5", m_no and not m_yes, "缺 purpose ⇒ 拦 ✓；写了 ⇒ 放行 ✓")
    # ★P6 限流✗★（抄 dsh-mc-bridge 的形状 ✓）：★第一次放行 ✓ 紧接着再来 ⇒ `rate_limited` ＋ retryAfterMs✗★
    Fake.write_text(json.dumps({"enabled": True, "allow": ["scan"],
                                "rate_limit": {"scan": 400}}), encoding="utf-8")
    P = fresh()
    a1, _ = P.rate_ok("scan")
    a2, ms = P.rate_ok("scan")
    import time as _t
    _t.sleep(0.45)
    a3, _ = P.rate_ok("scan")
    check("P6", a1 and (not a2) and ms > 0 and a3,
          "首次放行 ✓ 紧接再来 ⇒ 拦（retryAfterMs=%d ✓）｜等过去 ⇒ 放行 ✓" % ms)
    # ★P7 权限**交集**✗★（抄他们"块动作要 BLOCKS ＋ NAVIGATION" ✓）：★缺一个就拒 ✗ 并说出缺哪个✓★
    Fake.write_text(json.dumps({"enabled": True, "grant": ["navigation"],
                                "require_perm": {"dig_block": ["blocks", "navigation"]},
                                "allow": None}), encoding="utf-8")
    P = fresh()
    a7, w7 = P.check("dig_block", {"x": 4110, "y": 71, "z": 9})
    check("P7", (not a7) and "blocks" in w7, "缺 blocks ⇒ 明确拒并点出缺哪个 ✓（%s…）" % w7[:52])
    # ★P8 改世界**互斥**✗★：★拿锁 ⇒ 别人再拿 ⇒ 明确拒 ✗ 不排队✓★
    Fake.write_text(json.dumps({"enabled": True, "allow": None,
                                "mutating": ["dig_block", "place_block"]}), encoding="utf-8")
    P = fresh()
    g1, _ = P.acquire_mutating("dig_block")
    g2, holder = P.acquire_mutating("place_block")
    P.release_mutating("dig_block")
    g3, _ = P.acquire_mutating("place_block")
    check("P8", g1 and (not g2) and holder == "dig_block" and g3,
          "拿到 ✓ 别人再拿 ⇒ 拒（占着的是 %s ✓）｜释放后 ⇒ 拿到 ✓" % holder)
finally:
    if saved is not None:
        Fake.write_bytes(saved)
    else:
        Fake.unlink(missing_ok=True)

print("=> policy_test %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
