#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recover.py -- ★D4「一条命令恢复」✗ 幂等 ✗ 直连优先✗★（2026-11-02 重写自 CC 时代旧版）

★为什么重写✗★：旧版是 2026-09-19 的 **CC 车道**流程（`agent.channel` ← cc0/cmd0，再跑
  sift 守卫/给海龟装工具那套 09 月作业）✗ 而 CC 车道在直连改造后已经**失效** ✗
  ⇒ 拿它当"重启后恢复"会一开始就 `ERR:BridgeError` ✗ 却看起来像"世界没起来"✗★ ✓

★它做的事（顺序固定 ✗ 每步都有硬证据 ✗ 失败分步如实说）✗★：
  S0 直连探活：`GET /health`（127.0.0.1:8766）⇒ 不通 = 游戏关了/模组没起 ⇒ 硬故障 exit 1（**不瞎试**）
  S1 读 Bot：`POST /cmd  execute as Bot at Bot run dshdigest 1` ⇒ 回执带 `name=Bot` ⇒ 在
  S2 不在 ⇒ `POST /raw  player Bot spawn at <锚点>`（★以**服务器身份**跑 ✗ 解开"拉假人要先有假人"死结✓★）
     然后**回读 digest** 直到出现 `name=Bot`（最多 3 次 × 1.5s ✗ 不信 spawn 的回执自述）
  S3 核对游戏模式：digest 的 `mode=` 必须是 `survival`
     （★创造模式下挖方块不掉落 ⇒ 一切"自给"证据失真 ✗ 这是用命换来的教训 P17✓★）
     不是 ⇒ `POST /raw  gamemode survival Bot` ⇒ 回读确认
  S4 确认现场：digest 必须有 `pos=`／`onground=`／`mode=survival`（缺 ⇒ 部分未知 exit 2）
  S5 清中继暂停旗：`logs/relay_hold` 挂着时中继会**闭嘴** ✗ 恢复后应摘掉（摘了要报告 ✓）

★幂等✗★：已经就绪 ⇒ **不 spawn 不改模式**（打印 `ALREADY-READY`）⇒ 反复跑没有副作用 ✓
★退出码✗★：0 已恢复/本来就绪 ｜ 1 硬故障（health 不通 / spawn 失败 / 切生存失败）｜ 2 部分未知（有回执但读不全）
★注入式✗★：`recover(transport=...)` 可注入假通道 ⇒ `tools/recover_test.py` 全离线；默认 `DirectTransport`。

用法：
    py tools/recover.py                     # 真恢复（默认 live ✗ 这条就是重启后的那一条命令）
    py tools/recover.py --dry-run           # 只探测与报告 ✗ 不发 spawn/gamemode/删旗
    py tools/recover.py --anchor "4121 71 16"
    py tools/recover.py --json              # 机器可读（给 CI / 台账）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BOT = "Bot"
DEFAULT_ANCHOR = "4121 71 16"          # ★重生锚点✗★：家/屋外侧的安全落脚（与 respawn_bot 旧口径一致 ✓）
DEFAULT_FLAGS = ROOT / "logs"
RELAY_HOLD = "relay_hold"


# ---------------------------------------------------------------- 默认通道（直连）
class DirectTransport:
    """生产通道：`tools/direct.py`（127.0.0.1:8766 ✗ token 由 direct 自己处理 ✓）"""

    def __init__(self):
        import direct as D
        self.D = D

    # ★静默吞异常会把"通道坏了"伪装成"游戏没起来"✗★（§79.401 那一族）⇒ 每次都 print 原因 ✓
    def health(self, timeout: float = 2.0):
        try:
            return self.D.health(timeout=timeout)
        except Exception as e:
            print("[recover] direct.health 异常：%s: %s" % (type(e).__name__, str(e)[:120]))
            return None

    def post(self, cmd: str, timeout: float = 20.0):
        try:
            return self.D.post(cmd, timeout=timeout)
        except Exception as e:
            print("[recover] direct.post 异常：%s: %s" % (type(e).__name__, str(e)[:120]))
            return None

    def raw(self, cmd: str, timeout: float = 20.0):
        try:
            return self.D.raw(cmd, timeout=timeout)
        except Exception as e:
            print("[recover] direct.raw 异常：%s: %s" % (type(e).__name__, str(e)[:120]))
            return None


# ---------------------------------------------------------------- 解析
def parse_kv(text: str) -> dict:
    """★从回执里抠 `k=v` 字段✗★（digest 一行里有 pos=/mode=/onground=/hp=）"""
    out = {}
    for k, v in re.findall(r"(\w+)=([^\s|]+)", text or ""):
        out.setdefault(k, v)
    return out


def bot_ready(digest: str) -> tuple:
    """⇒ (present, mode, kv)；present 只看**回执里的名字**✗ 不看命令自述 ✓"""
    k = parse_kv(digest or "")
    present = (k.get("name") == BOT) or re.search(r"\bname=%s\b" % BOT, digest or "") is not None
    return present, k.get("mode"), k


# ---------------------------------------------------------------- 主流程
def recover(transport, anchor: str = DEFAULT_ANCHOR, flags_dir: Path = DEFAULT_FLAGS,
            dry_run: bool = False, attempts: int = 3, retry_delay: float = 1.5,
            sleep=time.sleep) -> dict:
    """★D4 一条命令恢复✗★ ⇒ {exit, steps, bot, spawned, gamemode_fixed, flags_removed}

    ★判据友好✗★：所有 IO 都走 `transport`；`sleep` 可注入 ⇒ 离线测试**不需要等** ✓
    """
    steps = []
    result = {"exit": 0, "steps": steps, "bot": {}, "spawned": False,
              "gamemode_fixed": False, "flags_removed": [], "dry_run": dry_run}

    def step(sid, name, status, detail=""):
        steps.append({"id": sid, "name": name, "status": status, "detail": detail})

    # ---- S0 直连探活
    health = transport.health()
    if not (health and "ok" in str(health)):
        step("S0", "直连探活", "FAIL",
             "127.0.0.1:8766 /health 不通（游戏关了 / 模组没起 / 正在重启）⇒ 不尝试 /raw")
        result.update({"exit": 1, "reason": "direct health unavailable"})
        return result
    step("S0", "直连探活", "OK", "health=%r" % (str(health)[:60],))

    # ---- S1 读 Bot（digest 是唯一真值：只认回执里的 name=Bot）
    digest = transport.post("execute as Bot at Bot run dshdigest 1") or ""
    present, mode, kv = bot_ready(digest)
    step("S1", "读 Bot", "OK" if present else "MISS",
         "digest=%s" % (digest.splitlines()[0][:110] if digest else "(无回执)"))

    # ---- S2 不在 ⇒ spawn（/raw 服务器身份）＋回读
    if not present:
        if dry_run:
            step("S2", "召唤 Bot", "DRY", "会执行 /raw: player %s spawn at %s" % (BOT, anchor))
            # ★dry-run 不产生状态 ✗ 所以后面 S3/S4 的"确认现场"无从谈起 ⇒ 如实停在这里 ✓
            hold = Path(flags_dir) / RELAY_HOLD
            if hold.is_file():
                step("S5", "清中继暂停旗", "DRY", "%s 在 ⇒ 会删除" % RELAY_HOLD)
            else:
                step("S5", "清中继暂停旗", "SKIP", "%s 没挂 ⇒ 无事可做" % RELAY_HOLD)
            result.update({"exit": 0, "reason": "dry-run"})
            return result
        else:
            r = transport.raw("player %s spawn at %s" % (BOT, anchor))
            result["spawned"] = r is not None
            step("S2", "召唤 Bot", "OK" if r is not None else "FAIL",
                 "player %s spawn at %s ⇒ %r" % (BOT, anchor, (r or "")[:90]))
            if r is None:
                result.update({"exit": 1, "reason": "spawn command bridge error"})
                return result
            for i in range(max(1, attempts)):
                sleep(retry_delay)
                digest = transport.post("execute as Bot at Bot run dshdigest 1") or ""
                present, mode, kv = bot_ready(digest)
                if present:
                    break
            if not present:
                step("S2b", "回读 Bot", "FAIL",
                     "spawn 后 %d 次回读仍没有 name=Bot ⇒ 不许假装成功" % attempts)
                result.update({"exit": 1, "reason": "bot absent after spawn"})
                return result
            step("S2b", "回读 Bot", "OK", "digest=%s" % digest.splitlines()[0][:110])
    else:
        step("S2", "召唤 Bot", "SKIP", "★已在世界**不重复 spawn**✗★（幂等）")

    # ---- S3 游戏模式必须是 survival
    mode = kv.get("mode") or mode
    if mode == "survival":
        step("S3", "核对游戏模式", "OK", "mode=survival ✓（挖掘会正常掉落 ✓）")
    elif dry_run:
        step("S3", "核对游戏模式", "DRY", "mode=%r ⇒ 会执行 /raw: gamemode survival %s" % (mode, BOT))
    else:
        r = transport.raw("gamemode survival %s" % BOT)
        fixed = r is not None
        step("S3", "切生存", "OK" if fixed else "FAIL",
             "gamemode survival %s ⇒ %r" % (BOT, (r or "")[:90]))
        if not fixed:
            result.update({"exit": 1, "reason": "gamemode command bridge error"})
            return result
        sleep(retry_delay)
        digest2 = transport.post("execute as Bot at Bot run dshdigest 1") or ""
        _p2, mode2, kv2 = bot_ready(digest2)
        if mode2 == "survival":
            result["gamemode_fixed"] = True
            kv = kv2
            step("S3b", "回读模式", "OK", "mode=survival ✓")
        else:
            step("S3b", "回读模式", "FAIL", "切完仍 mode=%r ⇒ 硬故障" % (mode2,))
            result.update({"exit": 1, "reason": "gamemode not survival after fix"})
            return result

    # ---- S4 确认现场（pos/onground/mode）
    kw = parse_kv(transport.post("execute as Bot at Bot run dshdigest 1") or "")
    mode = kw.get("mode") or mode
    need = {k: kw.get(k) for k in ("pos", "onground", "mode")}
    result["bot"] = {"pos": need.get("pos"), "onground": need.get("onground"),
                     "mode": mode, "hp": kw.get("hp"), "name": kw.get("name")}
    missing = [k for k, v in need.items() if not v]
    if missing:
        step("S4", "确认现场", "UNKNOWN", "digest 缺字段 %s ⇒ 部分未知（exit 2）" % missing)
        result.update({"exit": 2, "reason": "incomplete digest: %s" % missing})
        return result
    step("S4", "确认现场", "OK",
         "pos=%s onground=%s mode=%s hp=%s" % (need["pos"], need["onground"], mode, kw.get("hp")))

    # ---- S5 清中继暂停旗（挂着会闭嘴 ✗ 恢复后应摘掉）
    hold = Path(flags_dir) / RELAY_HOLD
    if hold.is_file():
        if dry_run:
            step("S5", "清中继暂停旗", "DRY", "%s 在 ⇒ 会删除" % hold)
        else:
            try:
                hold.unlink()
                result["flags_removed"].append(RELAY_HOLD)
                step("S5", "清中继暂停旗", "OK", "%s 已删（中继可以继续说话/续跑 ✓）" % RELAY_HOLD)
            except OSError as e:
                step("S5", "清中继暂停旗", "UNKNOWN",
                     "%s 删不掉：%s ⇒ 部分未知（exit 2）" % (RELAY_HOLD, type(e).__name__))
                result.update({"exit": 2, "reason": "relay_hold unlink failed"})
                return result
    else:
        step("S5", "清中继暂停旗", "SKIP", "%s 没挂 ⇒ 无事可做" % RELAY_HOLD)

    result["exit"] = 0
    result["reason"] = "ready" if not result["spawned"] else "recovered"
    return result


# ---------------------------------------------------------------- 输出
def _print_report(res: dict) -> None:
    for s in res["steps"]:
        mark = {"OK": "[OK ]", "SKIP": "[-- ]", "DRY": "[DRY]", "MISS": "[!! ]",
                "FAIL": "[X  ]", "UNKNOWN": "[?? ]"}.get(s["status"], "[?  ]")
        print("  %s %s %-8s %s" % (mark, s["id"], s["name"], s["detail"]))
    b = res.get("bot") or {}
    if b.get("pos"):
        print("  BOT pos=%s onground=%s mode=%s hp=%s"
              % (b.get("pos"), b.get("onground"), b.get("mode"), b.get("hp")))
    if res.get("dry_run") and res["exit"] == 0:
        print("RECOVER: DRY-RUN（没有做任何改动 ✗ 状态见上）")
        return
    ready = (res["exit"] == 0 and not res.get("spawned") and not res.get("gamemode_fixed"))
    tag = "ALREADY-READY" if ready else "RECOVERED"
    if res["exit"] == 0:
        print("RECOVER: READY（%s）" % tag)
    elif res["exit"] == 1:
        print("RECOVER: HARD-FAIL（%s）" % res.get("reason", "?"))
    else:
        print("RECOVER: PARTIAL-UNKNOWN（%s）" % res.get("reason", "?"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--anchor", default=DEFAULT_ANCHOR, help="Bot 重生坐标（默认 %(default)s）")
    ap.add_argument("--dry-run", action="store_true", help="只探测/报告，不发 spawn/gamemode/删旗")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--attempts", type=int, default=3, help="spawn 后回读次数（默认 3）")
    ap.add_argument("--flags-dir", default=str(DEFAULT_FLAGS), help="中继旗标目录（默认 logs/）")
    a = ap.parse_args(argv)
    if a.attempts < 1:
        print("RECOVER: HARD-FAIL（--attempts 必须 ≥1）")
        return 2
    try:
        res = recover(DirectTransport(), anchor=a.anchor, flags_dir=Path(a.flags_dir),
                      dry_run=a.dry_run, attempts=a.attempts)
    except Exception as e:      # ★连通道构造都失败 ⇒ 硬故障，但要说清是什么✗★
        print("RECOVER: HARD-FAIL（未预期异常：%s: %s）" % (type(e).__name__, str(e)[:120]))
        return 1
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        _print_report(res)
    return res["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
