#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world_audit.py —— ★读取器的 **oracle**（对账环）★ ✗（2026-10-01 立 ✓ 用户方案第 1 步 ✓）

WHY（★为什么它必须第一个做✗★）：
  ★没有度量 ⇒ "修好了"无从验证 ✗★ —— 现在发现读错的唯一方式，是 **bot 撞墙／摔死／误报不可达**
  之后被人撞上 ✗（P78/P92/P140 ✓）⇒ 每轮修复都可能是"修一个、造两个"✗ 错题越记越多 ✓
  ⇒ 本工具把"老是读不对"从**一种感觉**变成★**一张可数、可分类、可追踪的清单**✗★ ✓

★★它与"三层切分"的关系✗★★（用户 2026-10-01 定的边界 ✓ 本工具只做第一层的一半 ✓）：
  ① ★身体尺寸✗★：**必须显式入参**（如 `standable(x, y, z, box)` ✓）
     ★不许把 0.6×1.8 这类数埋在模组里当魔法数✗★ —— 它是**实测常量** ✓ 但来源要写在参数上 ✓
  ② ★理论包线✗★：来自游戏物理（原版跳跃 **1.25** 格 ✓ 自动上台阶 **0.6** ✓）——
     模组**可以算** ✓ 但返回值★必须带 `theoretical` 标记✗★，与实测值**分字段存放** ✓
  ③ ★实践系数✗★：只能来自**校准场**（真实跳跃成功率 ✓ 走一步真实耗时 ✓ 湿滑面表现 ✓）——
     ★进配置、带版本号✗★ ⇒ 本工具**不猜**这些数 ✓（★猜测是过去 N 轮循环的一半 ✗★）

判据（★先写死 ✗ 不许事后改 ✓ —— ★第一版**只报数** ✗ 不判红 ✓ P98 ✓★）
  ★失配类别（★一处定义✗★ P106）★：
    M1 ★模型/扫描 与 **原生命令**不符✗★   —— 拿 `execute if block <pos> <id>` 当**独立参照** ✓
       （★为什么它算独立：原生命令走**游戏自己**的方块表 ✗ 不经过我们的扫描器/建图/缓存/解析 ✓）
    M2 ★同一个扫描器**连问两次**答案不同✗★ —— ★这就是 2026-10-01 那个
       `matched=0` vs `matched=6` 的形状 ✗★（★它今天**没有归宿** ✗ 只能靠肉眼撞见 ✓）
    M3 ★读不出来／说不清✗★（空回执 ✓ 分页异常 ✓ "unknown" ✓）—— ★不许静默✗★
  ★抽格（★分层 ✗ 不许纯随机 ✓★）：① 脚下 ＋ 四邻（**正在接触**的格 ✓）
    ② 半径内**随机**（宽覆盖 ✓）③ 脚下**上下各 3 层**（多层/洞穴那一类 ✓）
  ★输出✗★：按类别**计数** ＋ 前若干个**现场原文** ✓ ⇒ `logs/world_audit.jsonl` ✓

用法 ✓：`py tools/world_audit.py --radius 12 --random 24`
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOG = ROOT / "logs" / "world_audit.jsonl"

# ★身体尺寸：★显式常量**放在这一处**✗★（★将来必须作为参数传下去 ✗ 不许埋进模组 ✓★）
BODY = {"width": 0.6, "height": 1.8, "edge_tol": 0.3, "note": "★实测常量 ✗ 不是理论值 ✓★"}
# ★理论包线：游戏物理给的（★字段上永远带 theoretical ✗ 与实测分开放 ✓★）
THEORY = {"jump_blocks": 1.25, "auto_step": 0.6, "tag": "theoretical"}


def say(s=""):
    print(s, flush=True)


def main(argv) -> int:
    radius = 12
    n_rand = 24
    seed = 20261001
    if "--radius" in argv:
        radius = int(argv[argv.index("--radius") + 1])
    if "--random" in argv:
        n_rand = int(argv[argv.index("--random") + 1])
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
    rng = random.Random(seed)

    import mc_mcp as M
    from channel import Channel
    ch = Channel("cmd0", verbose=False)

    def cmd(t, tmo=30.0):
        try:
            return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
        except Exception as e:
            return "ERR:%s" % type(e).__name__

    def pos():
        m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)",
                      cmd("execute as Bot at Bot run dshdigest 1"))
        return tuple(int(float(v)) for v in m.groups()) if m else None

    def scan1(x, y, z):
        """★一次单格读✗★ ⇒ (方块 id 或 'air', 原始回执) ✓"""
        t = cmd("execute as Bot at Bot run dshscan %d %d %d %d %d %d" % (x, y, z, x, y, z))
        m = re.search(r"counts\[([^\]]*)\]", t)
        if "ERR:" in t or "dshscan" not in t:
            return None, t
        if not m or not m.group(1).strip():
            return ("air" if "air=1" in t else None), t
        return m.group(1).split(",")[0].rsplit(":", 1)[0], t

    def vanilla(x, y, z, blk):
        """★独立参照✗★：原生命令问"这一格是不是 <blk>" ⇒ True/False/None ✓"""
        t = cmd("execute if block %d %d %d %s" % (x, y, z, blk))
        if "ERR:" in t:
            return None
        if "passed" in t or t.strip().endswith("1") or t.strip() == "1":
            return True
        if "failed" in t or t.strip().endswith("0"):
            return False
        return None

    p = pos()
    if not p:
        say("★读不到假人坐标 ⇒ 桥断/假人不在 ⇒ 测不了 ✓（exit 4 ✓）")
        return 4
    bx, by, bz = p
    cells = [(bx, by, bz), (bx + 1, by, bz), (bx - 1, by, bz), (bx, by, bz + 1), (bx, by, bz - 1)]
    for dy in (-3, -2, -1, 1, 2, 3):
        cells.append((bx, by + dy, bz))
    for _ in range(n_rand):
        cells.append((bx + rng.randint(-radius, radius), by + rng.randint(-3, 3),
                      bz + rng.randint(-radius, radius)))
    seen, uniq = set(), []
    for c in cells:
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    say("== world_audit：oracle 第一版（★只报数 ✗ 不判红 ✓★）==")
    say("  身体=%s ｜ 理论=%s" % (BODY, THEORY))
    say("  抽格 %d 个（分层：接触 5 ＋ 上下 6 ＋ 随机 %d ✓）｜ 半径 %d" % (len(uniq), n_rand, radius))
    M1 = M2 = M3 = 0
    recs = []
    for (x, y, z) in uniq:
        a1, t1 = scan1(x, y, z)
        a2, t2 = scan1(x, y, z)
        if a1 is None or a2 is None:
            M3 += 1
            recs.append({"cell": [x, y, z], "cls": "M3", "a1": a1, "a2": a2,
                         "t1": t1[:160], "t2": t2[:160]})
            continue
        if a1 != a2:
            M2 += 1
            recs.append({"cell": [x, y, z], "cls": "M2", "a1": a1, "a2": a2,
                         "t1": t1[:160], "t2": t2[:160]})
            continue
        vb = vanilla(x, y, z, a1 if a1 != "air" else "minecraft:air")
        if vb is None:
            M3 += 1
            recs.append({"cell": [x, y, z], "cls": "M3", "a1": a1, "vanilla": None})
        elif vb is False:
            M1 += 1
            recs.append({"cell": [x, y, z], "cls": "M1", "a1": a1, "vanilla": False})
    with LOG.open("a", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    say("  ★M1 模型/扫描 vs 原生命令不符✗★ = %d" % M1)
    say("  ★M2 同一扫描器两次不一致✗★     = %d" % M2)
    say("  ★M3 读不出来/说不清✗★          = %d" % M3)
    say("  一致 = %d ／ 共 %d" % (len(uniq) - len(recs), len(uniq)))
    for r in recs[:5]:
        say("    现场 %s %s a1=%s a2=%s" % (r["cell"], r["cls"], r.get("a1"), r.get("a2")))
    say("  ★口径✗★：第一版**只报数** ✗ 不判红 ✓（说不出物理下限就不许拍阈值 ✓ P98 ✓）；"
        "现场已存 %s ✓" % LOG.name)
    # ★★第 2 轮：把**区域扫描**也纳入对账✗★★（M4/M5 ✓ 2026-10-01 ✓）
    #   ★为什么要它✗★：今天那个 `matched=0` → `matched=6` 的翻脸 **不在单格读上** ✗
    #     它出在**带过滤/分页/子串匹配的区域扫描**那一条路 ✗（单格 29/29 全一致 ✓）
    #   M4 ★同一条区域查询跑两遍✗★：`counts[...]` ＋ `matched=` 必须逐字相同 ✓
    #   M5 ★命中格逐格复核✗★：拿坐标 ⇒ **单格读 ×2 ＋ 原生命令** 三方对账 ✓
    def region(q):
        t = cmd("execute as Bot at Bot run dshscan " + q)
        m = re.search(r"counts\[([^\]]*)\]", t)
        mm = re.search(r"matched=(\d+)", t)
        return (m.group(1) if m else None), (int(mm.group(1)) if mm else None), t

    bx0, bz0 = bx - 8, bz - 8
    QUERIES = ["%d 71 %d %d 73 %d" % (bx0, bz0, bx0 + 16, bz0 + 16),
               "%d 70 %d %d 72 %d" % (bx0, bz0, bx0 + 16, bz0 + 16),
               "%d 69 %d %d 71 %d" % (bx0, bz0, bx0 + 8, bz0 + 8)]
    M4 = M5 = 0
    m5_cells = 0          # ★★P152：断言**输入边界**✗★ —— ★"复核了 0 格"必须说出来 ✗ 不许印个 0 就完 ✓★
    rrecs = []
    for q in QUERIES:
        c1, n1, t1 = region(q)
        c2, n2, t2 = region(q)
        if c1 is None or c2 is None or c1 != c2 or n1 != n2:
            M4 += 1
            rrecs.append({"cls": "M4", "q": q, "c1": (c1 or "")[:200], "c2": (c2 or "")[:200],
                          "n1": n1, "n2": n2})
    # M5：拿一批"命中格"的坐标，逐格三方对账（★子串匹配 ⇒ 用 find_block 取坐标 ✓★）
    for key in ("minecraft:oak_planks", "minecraft:cobblestone"):
        got = str(M.t_find_block(key, 16, 4)[0])
        cells2 = [(int(a), int(b), int(c)) for (a, b, c) in
                  re.findall(r"\((-?\d+),(-?\d+),(-?\d+)\)", got)][:3]
        for (x, y, z) in cells2:
            m5_cells += 1
            a1, _ = scan1(x, y, z)
            a2, _ = scan1(x, y, z)
            if a1 is None or a2 is None or a1 != a2:
                M5 += 1
                rrecs.append({"cls": "M5", "cell": [x, y, z], "a1": a1, "a2": a2})
                continue
            vb = vanilla(x, y, z, a1 if a1 != "air" else "minecraft:air")
            if vb is not True:
                M5 += 1
                rrecs.append({"cls": "M5", "cell": [x, y, z], "a1": a1, "vanilla": vb})
    with LOG.open("a", encoding="utf-8") as f:
        for r in rrecs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    say("  ★M4 同一条区域查询两遍不一致✗★ = %d（查了 %d 条 ✓）" % (M4, len(QUERIES)))
    if m5_cells == 0:
        say("  ★M5 测不了✗★：一个「命中格」都没取到 ⇒ ★这一行的 0 **不算数**✗★（P152 ✓）")
    else:
        say("  ★M5 命中格逐格复核不符✗★       = %d（复核实打实 **%d 格** ✓）" % (M5, m5_cells))
    for r in rrecs[:5]:
        say("    现场 %s" % json.dumps(r, ensure_ascii=False)[:180])

    # ★★第 3 轮：★照今天那个翻脸**当时的形状**打✗★★（M6 ✓ 2026-10-01 ✓）
    #   今天的翻脸发生在：★**带 `match=` 子串过滤的区域扫描** ＋ **改世界之后**✗★
    #     （同一个盒子：先 `matched=0` ✗ 十几分钟后又 `matched=6` ✓）
    #   ⇒ M6 用**当时那把尺子、那个形状**：
    #     ① 改世界**前**跑 2 遍 ② **放一块**之后再跑 2 遍 ③ **挖掉**之后再跑 2 遍 ✓
    #     判读 ✓：每两遍必须一致 ✓ 放完之后**必须 +1**（★看不见刚发生的变化 ✗ 就是今天那个病 ✓★）
    #     ★顺手给第③档取证✗★：★挖完 `items` 必须 **+1**（掉落物 ✗ 现状是 +0 ⇒ 模组侧 `/dshdig` 判红 ✓★）
    def scan_box():
        t = str(M.t_scan(bx - 6, 70, bz - 6, bx + 6, 73, bz + 6,
                         match="minecraft:cobblestone", max_=48)[0])
        m = re.search(r"counts\[([^\]]*)\]", t)
        mm = re.search(r"matched=(\d+)", t)
        cb = 0
        for part in (m.group(1).split(",") if m else []):
            if part.startswith("minecraft:cobblestone:"):
                cb = int(part.rsplit(":", 1)[1])
        return cb, (int(mm.group(1)) if mm else None)

    def items_now():
        m = re.search(r"items=(\d+)", cmd("execute as Bot at Bot run dshdigest 1"))
        return int(m.group(1)) if m else None

    def run_m6():
        # ★★M7 顺手做在里面✗★★：每一步都记 (items, held, drops ✓) ⇒
        #   ① place 花了几个 ② dig 之后**地上有没有掉落物**✗ ③ 走过去捡回来几个 ✗
        #   ★这样"每轮 -1"就有归属了 ✗ 不用再猜 ✓（也顺带验 P33：换手会不会把上一摞弄丢 ✗）★
        def row():
            t = cmd("execute as Bot at Bot run dshdigest 1")
            g = lambda k: (re.search(k + r"=([^\s]+)", t).group(1)
                           if re.search(k + r"=([^\s]+)", t) else "?")
            return {"items": g("items"), "held": g("held"), "drops": g("drops"), "pos": g("pos")}

        if "minecraft:cobblestone" not in str(M.t_bot_inventory()[0]):
            cmd("give Bot minecraft:cobblestone 8")
            time.sleep(0.5)
            supplied = True
        else:
            supplied = False
        a1, a2 = scan_box(), scan_box()
        r0 = row()
        rows2 = [(int(a), int(b), int(c)) for (a, b, c) in
                 re.findall(r"\((-?\d+),(-?\d+),(-?\d+)\)\s*距离约", str(M.t_safe_spots(4, 6, 4)))]
        if not rows2:
            return None
        tx2, ty2, tz2 = rows2[0]
        M.t_walk_to(tx2, ty2, tz2, exact=True)
        px2, py2, pz2 = tx2 + 1, ty2, tz2
        pr = str(M.t_place_block(px2, py2, pz2, "minecraft:cobblestone")[0])[:180]
        time.sleep(1.0)
        pb = scan1(px2, py2, pz2)[0]
        b1, b2 = scan_box(), scan_box()
        r1 = row()
        if pb != "minecraft:cobblestone":
            return {"before": [a1, a2], "after_place": [b1, b2], "after_dig": None,
                    "items": [r0["items"], r1["items"]], "cell": [px2, py2, pz2],
                    "place_receipt": pr, "dig_receipt": "★没放下去 ⇒ **不挖**✗★",
                    "cell_block_after_place": pb, "cell_block_after_dig": pb,
                    "rows": {"before": r0, "after_place": r1}, "supplied": supplied}
        dr = cmd("execute as Bot at Bot run dshdig %d %d %d" % (px2, py2, pz2))
        time.sleep(1.5)
        c1, c2 = scan_box(), scan_box()
        db = scan1(px2, py2, pz2)[0]
        r2 = row()
        M.t_walk_to(px2, py2, pz2, exact=True)
        time.sleep(2.0)
        r3 = row()
        return {"before": [a1, a2], "after_place": [b1, b2], "after_dig": [c1, c2],
                "items": [r0["items"], r1["items"], r2["items"], r3["items"]],
                "cell": [px2, py2, pz2], "place_receipt": pr, "dig_receipt": dr[:200],
                "cell_block_after_place": pb, "cell_block_after_dig": db,
                "rows": {"before": r0, "after_place": r1, "after_dig": r2, "after_pickup": r3},
                "supplied": supplied}

    # ★★测量前置闸：世界**安不安静**✗★★（2026-10-01 ✓ 机制，不是猜"谁在动手" ✓）
    #   今天的 `matched=0 → 6` 翻脸当场被解释成"我自己那一跑在后台放方块" ✗
    #   而 relay_hold 不在 ⇒ 谁在动手这件事**不该靠猜** ✗ ⇒ ★改成量它：两次指纹必须相同✗★
    def fingerprint():
        vals = [re.search(r"items=(\d+)", cmd("execute as Bot at Bot run dshdigest 1"))]
        vals = [m.group(1) if m else "?" for m in vals]
        for (fx, fy, fz) in [(bx, by, bz), (bx + 3, by, bz), (bx - 3, by, bz),
                             (bx, by, bz + 3), (bx, by, bz - 3)]:
            vals.append(scan1(fx, fy, fz)[0])
        return tuple(vals)

    f1 = fingerprint()
    time.sleep(3.0)
    f2 = fingerprint()
    STABLE = (f1 == f2)
    say("  ★世界安静吗✗★（两次指纹相同）：%s ｜ %s vs %s" % (STABLE, f1, f2))

    # ★★2026-10-18（★§79.305 ✗ 治 §79.303✗★）✗★★：★M6 要**改世界**（★放一块 ✗ 挖掉✗★）✗
    #   它撞上 `BridgeTimeout` 时 ✗ **整份结果**会跟着陪葬（★traceback ✗ 没有机器行✗★）✗★ ⇒
    #   ★★M6 **测不了就测不了** ✗ M1~M5 的数**照交**✗★★ ✓（★"★算完了★"和"★交出去了★"是两件事✗★）✗★ ✓
    try:
        m6 = run_m6() if STABLE else None
    except Exception as _e:      # ★不许静默：下面 say 出来 ✓★
        say("  ★M6 **测不了**✗★：%s: %s ✗ ⇒ ★M1~M5 的数照交 ✗ M6 这一档这次没有✗★"
            % (type(_e).__name__, str(_e)[:120]))
        m6 = None
    if not STABLE:
        say("  ★M6 不做✗★：★世界在动 ✗ 改世界的实验没有意义 ✓（也不许据此下任何结论 ✓）★")
    if not m6:
        say("  ★M6 测不了✗★：挑不到落脚点 ／ 或世界在动 ✓")
    elif m6.get("after_dig") is None:
        say("  ★M6 测不了✗★：★那一格不是我放下去的 ⇒ 按安全闸**不挖**✗★（%s）"
            % m6.get("cell_block_after_place"))
        say("      放的回执：%s" % m6.get("place_receipt", "")[:160])
    else:
        say("  ★M6 同一把尺子、改世界前/后✗★：%s" % json.dumps(m6, ensure_ascii=False))
        b, ap, ad = m6["before"], m6["after_place"], m6["after_dig"]
        say("   ① 每两遍一致？ before=%s after_place=%s after_dig=%s"
            % (b[0] == b[1], ap[0] == ap[1], ad[0] == ad[1]))
        say("   ② ★放一块之后看得见吗✗★（方块数应 +1）：%s ⇒ %s" % (b[0], ap[0]))
        say("      前提核对 ✓ 放完那一格 = %s ｜ 挖完 = %s" % (m6["cell_block_after_place"],
                                                          m6["cell_block_after_dig"]))
        say("      放的回执：%s" % m6["place_receipt"])
        say("      ★挖的回执✗★：%s" % m6["dig_receipt"])
        say("   ③ ★挖掉之后回到原值吗✗★：%s ⇒ %s" % (ap[0], ad[0]))
        rowsd = m6.get("rows") or {}
        for k in ("before", "after_place", "after_dig", "after_pickup"):
            if k in rowsd:
                say("      %-13s items=%-3s held=%-22s drops=%s"
                    % (k, rowsd[k]["items"], rowsd[k]["held"], rowsd[k]["drops"]))
        say("   ★补素材？✗★ %s（★据实：这一批方块是 give 来的 ✗ 不是「自给」✓）" % m6.get("supplied"))
        say("   ★第③档取证✗★：items %s ⇒ %s（★挖完应 +1 ✗ 现状见数 ✓）"
            % (m6["items"][0], m6["items"][1]))
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"cls": "M6", **m6}, ensure_ascii=False) + "\n")

    _machine = "WORLDAUDIT ok=1 M1=%d M2=%d M3=%d M4=%d M5=%d stable=%d m6=%s" % (
        M1, M2, M3, M4, M5, 1 if STABLE else 0, "yes" if m6 else "no")
    try:
        (ROOT / "logs" / "world_audit.txt").write_text(_machine + "\n", encoding="utf-8")
    except Exception as _e2:
        say("  ★机器行写不出来✗★：%s" % type(_e2).__name__)
    say("=> world_audit DONE（M1=%d M2=%d M3=%d M4=%d M5=%d）" % (M1, M2, M3, M4, M5))
    say("   ★机器行（纯 ASCII ✗ D3✗★）⇒ %s" % _machine)
    return 0


if __name__ == "__main__":
    # ★★2026-10-18（★§79.305✗★）✗★★：★**任何**异常都不许以 traceback 收场✗★ ——
    #   ★要留一条**能读的**机器行 ✗ 退 **4**（★"★测不了★" ✗ 不是"★world_audit 坏了★"✗★）✗★ ✓
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as _e:
        _m = "WORLDAUDIT ok=0 err=%s" % type(_e).__name__
        try:
            (ROOT / "logs" / "world_audit.txt").write_text(_m + "\n", encoding="utf-8")
        except Exception:
            pass
        print("INCONCLUSIVE: ★world_audit 没跑完★：%s: %s ✗ 不是判据坏✗★"
              % (type(_e).__name__, str(_e)[:160]))
        print("   ★机器行（纯 ASCII）⇒ %s" % _m)
        sys.exit(4)
