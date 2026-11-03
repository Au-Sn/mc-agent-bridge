#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speech_relay_live_test.py -- ★验**真正在跑的那个进程**（`acp_talk.py`）✗★（W1~W6 ✓）

## 为什么单开一份 ✗（2026-09-30 实机撞到 ✓ ⇒ P137 ✓）
  `speech_live_test.py` 验的是 `talk.Talk.proactive()` ✓ —— 那是**我写的东西**✓
  ★可 `start_all.ps1` 起的是 `acp_talk.py`✗★（它原来**自己**轮询 `dshevents` ✓ 自己 `dshsay` ✗）
  ⇒ ★"我在测试里验过"和"游戏里真能听到"是**两件事**✗★
  ⇒ 这份判据就盯**生产路径**：进程在不在 ✓ 旗子在时闭不闭嘴 ✓ 真**跨过进程边界**说没说出话 ✓

## CRITERIA（跑之前先写 ✓ 证据一律取**游戏服务端日志** ✗ 不取我的自述 ✓）
  W1 进程在   ：`acp_talk.py` **真在跑** ✓（`Win32_Process` 命令行里有它 ✓）
  W2 旗子闭嘴 ：`logs/relay_hold` 挂着（跑验收时 ✓）⇒ 打它一下 ⇒ ★**一个字都不许说**✗★
                （★世界真值✗★：`logs/speech_log.jsonl` **不许多行** ✓；不用看游戏日志 ✓ 因为不说 ✓）
  W3 真能听到 ：旗子撤掉之后 ⇒ `/damage Bot 3` ⇒ **服务端日志**出现 `<Bot> …` ✓
                ★判据为什么从 `damage 1` 改成 `damage 3`✗★（2026-09-30 ✓ ⇒ P139 ✓）：
                  ✗ 打 1 点血时，**回血比模组的采样快** ⇒ 它经常**根本不产生 `damage` 事件** ✗
                  ⇒ 我据此判"中继不说话"✗ ⇒ ★那是**判据的输入不可靠**✗ 不是系统坏 ✗★
                并且**窗口要够长**（≤24 秒 ✓）：中继每 2 秒轮询一次 ✓ 还要走"过闸＋渲染＋延迟"✓
  W4 同批压制 ：连打 5 下 ⇒ 新增**说出去的** ≤2 句 ✓
  W5 台词干净 ：说出去的那几句里**不含** `✓✗★` ✓（P136 在**生产路径**上复验 ✓）
  W6 审计完整 ：每行都有 `why` ✓ `payload` ✓ `source` ✓ 且 `sent=true` 的行 == 真说了的句数 ✓

用法 ✓：`py tools\\speech_relay_live_test.py`（旗子挂着时会自动只跑 W1/W2 ✓ 老实标注 SKIP ✗）
"""
from __future__ import annotations

import json
import re
import subprocess
import sys, paths as PA
import time
from pathlib import Path

ROOT = PA.ROOT
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))

LOG = ROOT / "logs" / "speech_log.jsonl"
HOLD = ROOT / "logs" / "relay_hold"
GAMELOG = PA.LATEST_LOG


def say(s):
    print(s, flush=True)


def rows():
    if not LOG.is_file():
        return []
    out = []
    for ln in LOG.read_text(encoding="utf-8").splitlines()[-300:]:
        try:
            out.append(json.loads(ln))
        except Exception as e:
            # 记录：审计行读不了 ⇒ 少算一行（W4 "≤2 句"可能假绿）
            print("[记录] 审计行读不了（少算一行 ⇒ W4 上界可能假绿）：%s"
                  % type(e).__name__, file=sys.stderr)
    return out


def bot_lines(since_bytes: int = 0):
    """★从**游戏服务端日志**里取 Bot 说过的话 ✗★（★GBK 解码✗★ —— 这文件不是 UTF-8 ✓ P136 ✓）"""
    if not GAMELOG.is_file():
        return []
    raw = GAMELOG.read_bytes()
    t = raw.decode("gbk", errors="replace")
    out = []
    for l in t.splitlines():
        if "<Bot>" in l and "ChatComponent" not in l and "Server thread" in l:
            m = re.search(r"<Bot> (.*)$", l)
            if m:
                out.append(m.group(1).strip())
    return out


def proc_alive() -> bool:
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*acp_talk.py*' }"
             " | Measure-Object).Count"],
            capture_output=True, text=True, timeout=60)
        return int((ps.stdout or "0").strip() or 0) > 0
    except Exception as e:
        say("   （进程查询失败 ✗：%s）" % e)
        return False


def main() -> int:
    ok = True
    from channel import Channel
    ch = Channel("cmd0", verbose=False)

    def cmd(t, to=60.0):
        r = ch.cmd("execute as Bot at Bot run %s" % t, timeout=to, allow_str=True)
        s = (r.text() or "").strip()
        return s.splitlines()[0] if s else ""

    # ---- W1：进程在 ----
    alive = proc_alive()
    say("W1 进程在：`acp_talk.py` 在跑=%s => %s" % (alive, alive))
    ok &= alive
    if not alive:
        say("★中继不在 ⇒ 后面几条无从谈起 ✗（先 `start_all.ps1` ✓）★")
        return 1

    ch.cmd("execute as Bot at Bot run dshdigest 6", timeout=60.0, allow_str=True)   # 先确认桥通 ✓
    time.sleep(0.5)

    # ---- W2：旗子挂着 ⇒ 一个字都不许说 ----
    n0 = len(rows())
    hold = HOLD.exists()
    cmd("damage @s 1")
    time.sleep(12.0)
    added = rows()[n0:]
    spoken = [x for x in added if x.get("line")]
    w2 = (not spoken) if hold else True          # ★旗子在 ⇒ 必须零行有台词 ✗★
    say("W2 旗子闭嘴：旗子挂着=%s ｜ 打它一下之后审计新增 %d 行（有台词的 %d 行）%s => %s"
        % (hold, len(added), len(spoken),
           "（★旗子在 ⇒ 必须 0 句✗★）" if hold else "（旗子没挂 ⇒ 这条跳过 ✓ 归 W3 管 ✓）", w2))
    ok &= w2
    if hold:
        say("   ★旗子还挂着（`check_all` 在跑 ✓）⇒ W3~W6 这轮不跑 ✗ 老实标注：SKIP ✗★")
        say("---- W1..W2 = %s（W3~W6 SKIP ✗ 不许当 PASS ✓）----" % ok)
        say("=> %s" % ("PARTIAL PASS（旗子还挂着 ✓ 跑完再来一次 ✓）" if ok else "FAIL"))
        return 0 if ok else 1

    # ---- W3：真能听到（跨进程 ✓ 证据＝服务端日志 ✓）----
    #   ★这条判据改过两次，两次都是**判据自己错**✗★（都写在这里 ✓ P110/P139 ✓）：
    #     ① 输入不可靠：打 **1** 点血会被回血抹掉 ⇒ 常常**没有事件** ✗ ⇒ 改成打 **3** 点
    #     ② ★没等冷却✗★：W2 那一下已经让"反应类"进了 8 秒冷却 ✗
    #        ⇒ 我这一下**必然被拦** ✗（心跳里 `events=1` 但 `said=0` ✓ 就是证据 ✓）
    #        ⇒ 先等 **25 秒**（反应 8s ✓ 播报 20s ✓ 都过去了 ✓）再打 ✓ 而且允许重试两次 ✓
    canned = ("哎哟", "疼。", "谁打我？", "打我干嘛。", "哎！")
    before_lines = bot_lines()
    n1 = len(rows())
    hit, real, added3 = None, [], []
    time.sleep(25.0)
    for _try in (1, 2):
        before_lines = bot_lines()
        n1 = len(rows())
        cmd("damage @s 3")
        for _i in range(7):                       # ★最多 21 秒✗★
            time.sleep(3.0)
            now_lines = bot_lines()
            if len(now_lines) > len(before_lines):
                hit = now_lines[len(before_lines):]
                break
        added3 = [x for x in rows()[n1:] if x.get("line")]
        real = [l for l in (hit or []) if not any(c == l.strip() for c in canned)]
        if real and added3:
            break
    w3 = bool(real) and bool(added3)
    say("W3 真能听到：服务端日志新增 %s ｜ 审计新增有台词的 %d 行 => %s"
        % (hit, len(added3), w3))
    if not w3:
        try:
            hb = json.loads((ROOT / "logs" / "relay_heartbeat.json").read_text(encoding="utf-8"))
            say("     ☆心跳（★它到底看见了什么✗★）：%s" % hb)
        except Exception:
            pass
    ok &= w3

    # ---- W4：连打 5 下 ⇒ ≤2 句 ----
    n2 = len(rows())
    for _i in range(5):
        cmd("damage @s 1")
    time.sleep(8.0)
    spoken4 = [x for x in rows()[n2:] if x.get("line")]
    w4 = len(spoken4) <= 2
    say("W4 同批压制：连打 5 下 ⇒ 说了 %d 句（要 ≤2 ✓）=> %s" % (len(spoken4), w4))
    ok &= w4

    # ---- W5：台词干净（P136 在生产路径上复验）----
    bad5 = [l for l in (real + [x.get("line") or "" for x in spoken4])
            if any(c in l for c in "✓✗★")]
    w5 = not bad5
    say("W5 台词干净：带 `✓✗★` 的 %s => %s" % (bad5 or "无 ✓", w5))
    ok &= w5

    # ---- W6：审计完整 ----
    allnew = rows()[n1:]
    need = ("why", "payload", "source", "sent", "kind")
    w6 = bool(allnew) and all(all(k in x for k in need) for x in allnew) \
        and (sum(1 for x in allnew if x.get("sent")) == len([x for x in allnew if x.get("line")]))
    say("W6 审计完整：%d 行 ｜ 字段齐=%s ｜ `sent=true` 的行数 == 有台词的行数=%s => %s"
        % (len(allnew), all(all(k in x for k in need) for x in allnew),
           sum(1 for x in allnew if x.get("sent")) == len([x for x in allnew if x.get("line")]), w6))
    ok &= w6

    say("---- W1..W6 = %s ----" % ok)
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
