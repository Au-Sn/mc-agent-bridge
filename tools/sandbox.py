#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sandbox.py -- ★★"沙盒档"✗★★：跑测试前把 `bounds` 收到测试区 ✗ 跑完还原（欠账 ⑦ 第 1 层 ✓）

WHY ✓（方案文档 · 第 1 层 ✓）：
  ★它把"别乱动世界"从**纪律**变成**闸门**✗★ —— ★我们已经有的 `mcp_policy.bounds`
  会让越界调用**明确拒掉**（`out_of_bounds` ✓ 判据 P4 ✓）⇒ ★不需要任何新机制✗★

用法 ✓
  py tools/sandbox.py on            # ★切到沙盒档✗（★先把原档备份 ✓★）
  py tools/sandbox.py off           # ★还原✗（★没有原档 ⇒ 删掉沙盒档 ⇒ 回到"机制没开"✓★）
  py tools/sandbox.py status        # ★看现在是什么档✗ ＋ 沙盒框在哪✓★

★沙盒框（★写死 ✗ 不许随手改✓★）★：★校准网格那一片（x 4110~4130 ✗ y 68~76 ✗ z -8~30 ✓）★
  —— ★它是**现有测试件**所在的那一块 ✓（见 §79.8 ✓ `docs/方案-测试世界与真实世界分离.md` ✓）
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "tools" / "bridge_policy.json"
BACKUP = ROOT / "tools" / "bridge_policy.before_sandbox.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★沙盒允许的坐标框（★写死 ✗ 判据会检查测试件落在里面✓★）
#   ★★形状必须是 `x0/x1/y0/y1/z0/z1`✗★★（2026-10-02 当场吃到 ✓）：
#     ★我第一版写成 `{"x": [lo, hi]}` ✗ ⇒ `mcp_policy` 读 `b.get("x0")` 得 **None** ⇒
#     ★它 `continue` 跳过 ⇒ **围栏静默失效** ✗ 一个字都没拦✗★（★"静默无效的闸门"＝最坏的一种✓★）
SANDBOX_BOUNDS = {"x0": 4110, "x1": 4130, "y0": 68, "y1": 76, "z0": -8, "z1": 30}
# ★沙盒档允许的动作（★够跑"改世界"的测试 ✗ 但**不含**大范围作业✓★）
SANDBOX_ALLOW = ["bot_state", "inventory", "look", "scan", "map_area", "find_block", "whereami",
                 "dig_block", "place_block", "use_block", "equip", "walk_to", "walk_route",
                 "move_relative", "jump", "look_at", "action_status", "cancel", "drop_item",
                 "chest_peek", "chest_put", "chest_take"]


def build():
    return {"enabled": True,
            "allow": SANDBOX_ALLOW,
            "bounds": SANDBOX_BOUNDS,
            "require_purpose": ["scan", "map_area"],
            "rate_limit": {"dig_block": 200, "place_block": 200},
            "mutating": ["dig_block", "place_block", "use_block", "chest_put", "chest_take",
                         "equip", "drop_item", "jump", "look_at"],
            "note": "★沙盒档✗★：由 `tools/sandbox.py on` 写入 ✓ 跑完请 `off` 还原 ✓"}


def on():
    if POLICY.is_file() and not BACKUP.is_file():
        shutil.copy2(POLICY, BACKUP)
        print("★已备份原档✗★ ⇒ %s ✓" % BACKUP.name)
    POLICY.write_text(json.dumps(build(), ensure_ascii=False, indent=1), encoding="utf-8")
    print("★沙盒档已生效✗★：bounds=%s ✓ allow=%d 条 ✓"
          % (SANDBOX_BOUNDS, len(SANDBOX_ALLOW)))
    print("  ★跑完**务必** ✗ `py tools/sandbox.py off` ✓★")


def off():
    if BACKUP.is_file():
        shutil.move(str(BACKUP), str(POLICY))
        print("★已还原成沙盒之前的档✗★ ✓")
    elif POLICY.is_file():
        POLICY.unlink()
        print("★没有原档 ⇒ 删掉沙盒档 ✗ 回到「机制没开」（照旧放行）✗★ ✓")
    else:
        print("★本来就没有策略文件 ✓ 无事可做 ✓★")


def status():
    if not POLICY.is_file():
        print("★当前：**没有策略文件**✗★ ⇒ ★边界／授权／限流**都没开**✗（照旧放行 ✓）★")
        return
    cfg = json.loads(POLICY.read_text(encoding="utf-8"))
    print("★当前策略✗★ enabled=%s ✓ bounds=%s ✓ allow=%d 条 ✓"
          % (cfg.get("enabled"), cfg.get("bounds"), len(cfg.get("allow") or [])))
    print("  沙盒备份在不在：%s ✓" % BACKUP.is_file())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"on": on, "off": off, "status": status}.get(cmd, status)()
