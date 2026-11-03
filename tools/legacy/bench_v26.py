#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_v26.py —— 模组 v2.6 的**验收基准**（只测不改 ✓ 全 ASCII 判据 ✓）

为什么要有它 ✗（不是"跑一遍感觉一下"✗）：
  v2.6 的说法是"**看**和**走**从秒级变原生" ✓ ⇒ 那就必须给出**数字** ✗（这是纪律①✓）
  而且要**两边对账** ✗：不能只听模组自报"我扫了 2268 格" ✗
  ⇒ 拿**老办法**（Lua 的 `snapshot` ✓ 它没被删掉 ✓）扫**同一个区域** ✗
  ⇒ **两边格数必须一致** ✓（不一致就说明新的那套有问题 ✗ —— 这才叫验收 ✓）

六项判据（每一项都独立可判 ✓）：
  B0 版本：`/dshver` 必须回 **2.6.0** ✓（否则跑的还是旧 jar ✗ 后面全部无意义 ⇒ 直接退出 ✓）
  B1 感知·小区域：原生 scan 2268 格（老办法实测 **3.5 s** ✗）⇒ 目标 **< 200 ms**
     ＋ **与老办法的 matched 数一致** ✓（交叉验证 ✓）
  B2 感知·大区域：原生 scan 7696 格（老办法**直接超时** ✗）⇒ 目标 **< 500 ms**
  B3 态势：一条 `dshdigest` 拿全（位置/血/饿/背包空位/掉落物/准星）⇒ 字段齐全 ✓
  B4 准星：`dshlook` 的方块必须与**桥接 `crosshair`** 说的一致 ✓（两套独立机制对账 ✓）＋ 可达性字段 ✓
  B5 走位：沿**小麦田的株位**连续走 5 步（＝收割那条路的走位 ✓ 只是走、不挖 ✓）
     ⇒ 全部 `reached` ✓ ＋ **兜底 tp 次数 = 0** ✓（人感①：不再瞬移 ✓）
  B6 事件：事件流里能看到 `walk_start/walk_done` ✓ 且 **一条 `warp` 都没有** ✓
     （`warp` 是模组自己的"有人瞬移它"哨兵 ✗ ⇒ 它没报 = 这几步**真的是走过去的** ✓✓）

用法：py tools/bench_v26.py
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))

from channel import Channel  # noqa: E402
from world import World      # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

SMALL = (4100, 70, 2, 4126, 73, 22)      # 2268 格 ✓ 与那轮要 3.5 s 的老办法同尺寸 ✓
BIG = (4096, 66, 0, 4136, 79, 32)        # 41*14*33 = 18942 格 ✓（老办法 7696 格就已超时 ✗）
FARM = (4104, 70, 6, 4116, 72, 18)


def main() -> int:
    ch = Channel("cmd0", verbose=False)
    w = World(ch)
    fails: list[str] = []

    def game(text: str, t: float = 90.0) -> str:
        r = ch.cmd(text, timeout=t, allow_str=True)
        s = (r.text() or "").strip()
        return s.splitlines()[0] if s else "(no reply)"

    def bot(text: str, t: float = 120.0) -> str:
        return game("execute as Bot at Bot run " + text, t)

    def kv(txt: str) -> dict:
        return {k: v for k, _, v in (tok.partition("=") for tok in (txt or "").split() if "=" in tok)}

    def check(name: str, ok: bool, detail: str = "") -> None:
        print("   %s %s%s" % ("[OK]  " if ok else "[FAIL]", name, (" ｜ " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    print("=" * 74)
    print("模组 v2.6 验收基准")
    print("=" * 74)

    # ── B0 版本（**先确认跑的是新 jar** ✗ 否则后面全是白测 ✓）────────────────────
    t0 = time.time()
    v = bot("dshver", 60.0)
    print("[B0] 版本 ｜ 往返 %.2fs ｜ %s" % (time.time() - t0, v[:160]))
    if "version=2.6" not in v:
        print("\n结论：**跑的还是旧版** ✗ —— 模组改动必须**关掉游戏进程重启** ✗")
        print("      （退到主菜单再进世界**不加载模组** ✗）⇒ 先重启游戏再跑本脚本 ✓")
        return 2

    # ── B1 感知·小区域 ＋ 交叉验证（与老办法对账 ✓）────────────────────────────
    print("\n[B1] 原生扫描 %d 格（老办法实测 3.5 s ✗）" % _vol(SMALL))
    t0 = time.time()
    s1 = bot("dshscan %d %d %d %d %d %d \"wheat\" 200 1" % SMALL, 120.0)
    dt1 = time.time() - t0
    k1 = kv(s1)
    us1 = int(k1.get("us", "10**9") if str(k1.get("us", "")).isdigit() else 10 ** 9)
    print("      模组自报：us=%s solid=%s matched=%s ｜ 端到端往返 %.2fs" % (k1.get("us"), k1.get("solid"), k1.get("matched"), dt1))
    check("B1a 原生扫描 < 200 ms", us1 < 200_000, "实测 %s us" % k1.get("us"))
    # ⚠ 交叉验证的**取数**要照别的工具的做法 ✗（我第一版写错了层级 ⇒ 拿到 None ✗
    #   而"None == 33"必然是 FAIL ✗ ⇒ 看起来像"新的那套有问题"✗ 其实**是我的读数坏了** ✗
    #   —— 同一族教训：错题本 **P22**（自证/读数代码自己会说谎 ✗）✓
    #   正确姿势 ✓：`as_dict()` 之后先试 `result` 再退回整表 ✓ 并**把原始回执打出来** ✓
    snap_r = ch.call("snapshot", dict(zip(("x0", "y0", "z0", "x1", "y1", "z1"), SMALL),
                                     match="wheat", maxcells=400), timeout=120.0, allow_str=True)
    try:
        sd = snap_r.as_dict()
    except Exception:
        sd = {}
    payload = sd.get("result") if isinstance(sd.get("result"), dict) else sd
    old = (payload or {}).get("matched_n")
    if old is None:
        print("      老办法原始回执：%s" % str(sd)[:300])
    print("      老办法（Lua snapshot）：matched_n=%s ｜ 往返 %.2fs" % (old, time.time() - t0 - dt1))
    check("B1b 与老办法格数一致（两边对账）", old is not None and str(old) == str(k1.get("matched")),
          "新=%s 老=%s" % (k1.get("matched"), old))

    # ── B2 感知·大区域（老办法**超时** ✗）────────────────────────────────────────
    print("\n[B2] 原生扫描 %d 格（老办法 7696 格就已超时 ✗）" % _vol(BIG))
    t0 = time.time()
    s2 = bot("dshscan %d %d %d %d %d %d" % BIG, 180.0)
    dt2 = time.time() - t0
    k2 = kv(s2)
    us2 = int(k2.get("us", "0") or 0)
    print("      vol=%s solid=%s kinds=%s us=%s ｜ 端到端往返 %.2fs" % (k2.get("vol"), k2.get("solid"), k2.get("kinds"), k2.get("us"), dt2))
    check("B2 大区域（18942 格）< 500 ms", 0 < us2 < 500_000, "实测 %s us" % k2.get("us"))

    # ── B3 一条指令一份态势 ─────────────────────────────────────────────────────
    print("\n[B3] 一条 dshdigest 拿全态势")
    t0 = time.time()
    d = bot("dshdigest 8", 90.0)
    print("      %s" % d[:400])
    kd = kv(d)
    need = ("pos", "hp", "food", "mode", "held", "look")
    check("B3 digest 字段齐全", all(x in kd for x in need),
          "缺=%s" % [x for x in need if x not in kd])
    mfree = re.search(r"free=(\d+)", d)
    check("B3b digest 报出了背包空位", bool(mfree), "free=%s" % (mfree.group(1) if mfree else "?"))

    # ── B4 准星：两套机制对账 ───────────────────────────────────────────────────
    print("\n[B4] dshlook 与桥接 crosshair 对账")
    lk = bot("dshlook", 60.0)
    print("      模组 dshlook：%s" % lk[:200])
    cross = ch.call("crosshair", {}, timeout=60.0, allow_str=True)
    cd = cross.as_dict() if isinstance(cross.result, dict) else {}
    hit = cd.get("hit") or {}
    kl = kv(lk)
    print("      桥接 crosshair：name=%s face=%s" % (hit.get("name"), hit.get("face")))
    same_block = (not hit.get("name")) or (kl.get("block") == hit.get("name"))
    check("B4 两套射线说同一个方块", same_block, "模组=%s 桥接=%s" % (kl.get("block"), hit.get("name")))
    # ⚠ 判据要**接受"什么都没打中"** ✗（B4 第一次跑就栽在这里 ✓ 但那不是模组的错 ✗）：
    #   射线打进空气时，模组回的是 `dshlook none dist=…` ✓ —— **没有** `reachable` ✓
    #   因为"够不够得着"对空气没有意义 ✓
    #   ⇒ 我第一版硬要求 `reachable` 存在 ✗ ⇒ 把"正常"判成"失败" ✗（同族 P10 ✓：判据别比现实更严 ✗）
    if kl.get("block") or kl.get("entity"):
        check("B4b 命中方块时带 reachable", "reachable" in kl,
              "reachable=%s dist=%s" % (kl.get("reachable"), kl.get("dist")))
    else:
        check("B4b 未命中时如实回 none（这本身也是对的 ✓）", lk.strip().startswith("dshlook none"),
              lk[:120])

    # ── B5 走位：沿小麦田的株位走 5 步（收割那条路的走位 ✓ 只走不挖 ✓）─────────
    print("\n[B5] 沿小麦株位连续走 5 步（收割的走位路径 ✓ 只是走、不挖 ✓）")
    sw = bot("dshscan %d %d %d %d %d %d \"wheat\" 200 1" % FARM, 120.0)
    cells = []
    if "cells[" in sw:
        for tok in sw.split("cells[", 1)[1].rstrip("]").split():
            if ":" in tok and "," in tok:
                xyz = tok.split(":", 1)[0].split(",")
                if len(xyz) == 3 and all(p.lstrip("-").isdigit() for p in xyz):
                    cells.append(tuple(int(p) for p in xyz))
    cells.sort()
    # ★ 选**离假人最近的** 5 株 ✗（而不是坐标排序的前 5 个 ✓）——
    #   为什么 ✗：投第一版时它挑出 (4106,71,15) ⇒ 第一腿就有 **17 格** ✗
    #   而收割那条路走的是"**相邻株位**"✓（一格一格挪 ✓）
    #   ⇒ 拿 17 格的长腿去考"收割走位"是我自己**把题目出错了** ✗（同族：P10 别发明比现实更严的判据 ✗）
    p0 = w.pos() or (4120.5, 71.0, 4.5)
    cells.sort(key=lambda c: (c[0] - p0[0]) ** 2 + (c[2] - p0[2]) ** 2)
    pick = cells[:5]
    print("      从感知里拿到 %d 个株位 ⇒ 取**离假人最近**的 %d 个：%s" % (len(cells), len(pick), pick))
    if len(pick) < 2:
        check("B5 有可走的株位", False, "扫描没拿到 cells ✗（match 参数或 scan 有问题？）")
    else:
        ev0 = kv(bot("dshevents", 60.0)).get("cursor", "0")
        reached, modes, speeds = 0, [], []
        for (x, y, z) in pick:
            t0 = time.time()
            st = bot("dshwalk %d %d %d 15000 exact" % (x, y, z), 90.0)
            start = None
            deadline = time.time() + 22.0
            line = ""
            while time.time() < deadline:
                time.sleep(0.35)
                line = bot("dshwalk", 30.0)
                if kv(line).get("status") == "done":
                    break
            dt = time.time() - t0
            k = kv(line)
            res = k.get("result", "?")
            d0 = None
            try:
                x0, y0, z0 = [float(v) for v in (p0 if start is None else start)]
                xa, ya, za = [float(v) for v in str(k.get("at", "0,0,0")).split(",")]
                d0 = ((xa - p0[0]) ** 2 + (za - p0[2]) ** 2) ** 0.5
            except Exception:
                d0 = None
            print("      → (%d,%d,%d)：%s 停在 %s 偏差 %s 格 驱动=%s 用时 %.1fs %s"
                  % (x, y, z, res, k.get("at"), k.get("dist"), k.get("mode"), dt,
                     ("why=" + k["why"]) if k.get("why") not in (None, "none") else ""))
            if res == "reached":
                reached += 1
            modes.append(k.get("mode", "?"))
            try:
                xa, ya, za = [float(v) for v in str(k.get("at", "")).split(",")]
                moved = ((xa - p0[0]) ** 2 + (za - p0[2]) ** 2) ** 0.5
                if moved > 0.5:
                    speeds.append(moved / max(0.1, dt))
                p0 = (xa, ya, za)
            except Exception:
                pass
        if speeds:
            print("      实测步行速度 ≈ %.2f 格/秒（真人步行 4.3 ✗ ⇒ 这条是**真发现** ✓ 见文档 ✓）"
                  % (sum(speeds) / len(speeds)))
        check("B5 五步全部走到", reached == len(pick), "到 %d / 共 %d" % (reached, len(pick)))
        # ★ 注意这条判据的**逻辑**✗：本脚本**从不主动 `tp`** ✓ ⇒ 只要事件流里没有 `warp` ✓
        #   这几步就**确实是走出来的** ✓（模组的 `warp` 哨兵是独立机制 ✓ 不是我自己声明 ✓）
        ev = bot("dshevents %s" % (ev0 or 0), 90.0)
        print("      事件流（新的一段）：%s" % ev[:400])
        check("B6 事件流里有 walk 记录", "walk_done" in ev, "")
        check("B6b 事件流里**没有 warp**（＝没有瞬移 ⇒ 是走过去的 ✓）", " warp " not in ev, "")
        print("      驱动方式统计：%s（input=原版移动输入 ✓ manual=直接 move() ✓）" % modes)

    print("=" * 74)
    if fails:
        print("结论：**%d 项没通过 ✗** —— %s" % (len(fails), "／".join(fails)))
    else:
        print("结论：★v2.6 全部判据通过 ✓★（看/走都成了原生行为 ✓ 而且没有瞬移 ✓）")
    print("=" * 74)
    return 0 if not fails else 1


def _vol(box) -> int:
    x0, y0, z0, x1, y1, z1 = box
    return (x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1)


if __name__ == "__main__":
    raise SystemExit(main())
