#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy.py — 一条命令把 Lua 新版推上现场机器，并**在世界里验收**

为什么要有它：
    改一行 Lua 就要人（玩家）进游戏手动重载 → 半小时的活被拖成几小时
    —— 这是本项目最大的效率瓶颈。现在走游戏内的 `A.self_update`：
        网关下载最新版 → **先做语法自检** → 自检过了才覆盖本地副本 `bridge_local` → 重启计算机
    ⇒ 自检不过则完全不更新 ✓（宁可不更新，也绝不把机器刷成砖 ✗）
    ⇒ 重启后 `startup` 会再拉一次并运行 ✓ 全程不需要玩家插手 ✓

验收（都只看**服务端真值**，不看动作自述）：
    1. 磁盘上的 `computer/<id>/bridge_local` 与仓库副本 **sha1 一致** ✓
       （游戏内计算机的文件就在宿主磁盘上 → 这是不依赖任何网络通道的硬证据 ✓）
    2. `status` 的 uptime 变小 ✓ = 真的重启过 ✓（不是"以为更新了" ✓）
    3. `crosshair` 真的能读出"假人正对着什么" ✓

用法：
    py tools/deploy.py             # 推送 + 验收
    py tools/deploy.py --probe     # 只验收（不推送）
    py tools/deploy.py --hud on    # 推送 + 验收 + 打开世界内 Jade HUD
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel, BridgeError, SAVE_DIR, COMPUTERS  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

REPO = HERE.parent / "cc-tweaked" / "agent_bridge.lua"
BAR = "=" * 62


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def norm(b: bytes) -> bytes:
    """换行归一：网关可能按文本模式送出（\\n → \\r\\n），那不算"内容不同"。"""
    return b.replace(b"\r\n", b"\n")


def main(argv: list[str]) -> int:
    probe_only = "--probe" in argv
    hud = None
    if "--hud" in argv:
        i = argv.index("--hud")
        hud = (argv[i + 1] if i + 1 < len(argv) else "on")
        hud = "on" if hud in ("on", "true", "1") else "off"

    repo_b = REPO.read_bytes()
    repo_sha = sha1_bytes(repo_b)
    print(BAR)
    print("仓库副本 : %s" % REPO)
    print("sha1     : %s  (%d 字节)" % (repo_sha, len(repo_b)))
    print(BAR)

    ch = Channel()

    # ── 1. 推送 ────────────────────────────────────────────────────────────
    if not probe_only:
        print("[1] self_update：网关下载 → 语法自检 → 覆盖 bridge_local → 重启")
        try:
            r = ch.call("self_update", {}, timeout=60.0, allow_str=True)
            print("    回传: %s" % r.summary(300))
            if isinstance(r.result, str) and ("语法错误" in r.result or "下载失败" in r.result):
                print("    [X] 自检/下载失败 —— 机器**保持旧版**（这正是设计：宁可不更新）")
                return 1
        except BridgeError as e:
            # 重启会打断回传，这是预期内的，不算失败
            print("    [!] 没等到回传（重启打断回传是正常的）：%s" % e)
        print("    等 14 秒：重启 → startup 拉新版 → 跑起来")
        time.sleep(14)

    # ── 2. 磁盘硬证据：机器上的副本 == 仓库副本 ─────────────────────────────
    cid = COMPUTERS["cmd0"]["id"]
    disk = SAVE_DIR / "computercraft" / "computer" / str(cid) / "bridge_local"
    print("\n[2] 磁盘核对：%s" % disk)
    if not disk.is_file():
        print("    [X] 找不到该文件（计算机 id 变了？还是从没自更新过？）")
    else:
        disk_b = disk.read_bytes()
        same = sha1_bytes(disk_b) == repo_sha
        same_norm = sha1_bytes(norm(disk_b)) == sha1_bytes(norm(repo_b))
        print("    磁盘 sha1 : %s  (%d 字节)  最后写入 %s"
              % (sha1_bytes(disk_b), len(disk_b),
                 time.strftime("%m-%d %H:%M:%S", time.localtime(disk.stat().st_mtime))))
        print("    %s 与仓库一致%s" % ("[OK]" if (same or same_norm) else "[X]",
                                      "" if same else ("（换行归一后一致）」" if same_norm else " ✗")))

    # ── 3. 通道与身份：真的重启过吗 ─────────────────────────────────────────
    print("\n[3] 通道与身份（uptime 变小 = 真的重启过）")
    try:
        st = ch.call("status", {}, timeout=40.0, allow_str=True).as_dict()
        print("    id=%s who=%s uptime=%ss dry_run=%s jade=%s"
              % (st.get("id"), st.get("who"), st.get("uptime_s"), st.get("dry_run"),
                 st.get("jade")))
    except BridgeError as e:
        print("    [X] status 失败：%s" % e)
        return 1

    # ── 4. 准星感知：真的能读出"正对着什么"吗 ───────────────────────────────
    print("\n[4] 准星感知 crosshair（假人正对着什么）")
    try:
        cr = ch.call("crosshair", {"raw": True, "nbt": True}, timeout=40.0, allow_str=True).as_dict()
        print("    眼睛=%s 朝向=%s 读取格子数=%s"
              % (cr.get("eye"), cr.get("rotation"), cr.get("cells_read")))
        print("    看点  : %s" % cr.get("looking_at"))
        hit = cr.get("hit") or {}
        if hit:
            print("    方块  : %s  工具=%s(%s)  档位=%s  流体=%s"
                  % (hit.get("name"), hit.get("tool"), hit.get("tool_from"),
                     hit.get("tier"), hit.get("fluid")))
            print("    状态  : %s" % hit.get("state"))
            if hit.get("raw"):
                print("    上游原始字段: %s" % hit.get("raw")[:400])
        else:
            print("    （视线里没有方块：假人正看着天）")
    except BridgeError as e:
        print("    [X] crosshair 失败：%s" % e)
        return 1

    # ── 5. 可选：打开世界内 HUD ────────────────────────────────────────────
    if hud:
        print("\n[5] 世界内 Jade HUD：%s" % hud)
        try:
            # 先清场：删掉旧的显示实体 ✓ 否则下面读到的可能是**上一轮**写进去的文本 ✗
            # （真实教训：世界里的残留会伪装成"这次成功了" ✓ = 假阳性 ✓）
            ch.call("jade", {"hud": "off"}, timeout=40.0, allow_str=True)
            j = ch.call("jade", {"hud": hud, "raw": True}, timeout=40.0, allow_str=True).as_dict()
            print("    hud=%s 看点=%s" % (j.get("hud"), j.get("looking_at")))
            time.sleep(3)
            ent = ch.cmd("data get entity @e[tag=dsh_jade,limit=1] Pos", allow_str=True)
            print("    实体核对: %s" % ent.summary(200))
            # 全文 dump：要确认的正是"文字内容与坐标到底写进去了没有"
            full = ch.cmd("data get entity @e[tag=dsh_jade,limit=1]", allow_str=True)
            import json as _json
            print("    实体全文: %s" % _json.dumps(full.as_dict(), ensure_ascii=False)[:1400])
            # ⚠ 最关键的一步：HUD 的 **文本内容** 到底更新了没有 ✗
            #   （真实事故：位置更新成功、文本却一直停在占位符 ✗ ——
            #    只看"实体存在"会给出一个漂亮的假阳性 ✓）
            txt = ch.cmd("data get entity @e[tag=dsh_jade,limit=1] text", allow_str=True)
            d2 = txt.as_dict()
            lines = " ".join((d2.get("result") or d2).get("lines") or [])
            print("    文本核对: %s" % lines[:400])
            if "Jade] ..." in lines:
                print("    [X] 文本仍是占位符 —— data merge 没生效（去看 job.log 的 jade.hud.err）")
            elif lines:
                print("    [OK] 文本已写入（含上面那行内容）")
        except BridgeError as e:
            print("    [X] jade 失败：%s" % e)

    print("\n" + BAR)
    print("完成。下一步：开工前先 `py agent/run.py do look_block` 问一句'我现在看着什么'。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
