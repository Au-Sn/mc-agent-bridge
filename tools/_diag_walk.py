#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_diag_walk.py -- ★临时诊断★（只读 ＋ 走路 ＋ 必要时 /damage ✓ 绝不 tp/挖/改模式 ✗）

要回答的四件事 ✓：
  Q1 `dshwalk` 到底**被谁**拒（模组安全规则？还是**根本没到模组** ✗）
  Q2 走不动/走一半停：**规划没路** 还是 **执行被拦**
  Q3 `put_many` 失败是不是同一个根因
  Q4 有没有"换个目标/起点就能走通"的最小反例

纪律 ✓：
  · 世界真值优先（`dshdigest` 的 pos=/onground= ✓ 不听工具自述 ✗）
  · 模组回执里的中文过 CC 终端会变 `?` ⇒ 我把**原始码点**一起落盘 ✓
    （这样"第几个字符开始是 `?`"这种信息不会丢 ✓）
  · 事件流（`dshevents`）纯 ASCII ✓ ⇒ 它是"到底走没走"的主要证据 ✓

用法：
    py -X utf8 tools\\_diag_walk.py            # 跑 A 段（诊断用户的原始命令）
    py -X utf8 tools\\_diag_walk.py B          # 跑 B 段（对照：换个目标能不能走通）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from channel import Channel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


OUT = ROOT / "logs" / "_diag_walk.txt"
_buf: list[str] = []


def flush() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(_buf) + "\n", encoding="utf-8")


def say(s: str = "") -> None:
    _buf.append(str(s))
    try:
        print(str(s).encode("ascii", "replace").decode("ascii"), flush=True)
    except Exception:
        pass
    flush()


def codes(s: str, n: int = 400) -> str:
    """把一段文本的**码点**摊开 ✓（`?` 到底是不是真问号 ✗ 一眼看得出 ✓）"""
    out = []
    for ch in s[:n]:
        o = ord(ch)
        out.append(ch if 32 < o < 127 else "\\u%04x" % o)
    return "".join(out)


CH = Channel("cmd0", verbose=False)


def run(text: str, tmo: float = 60.0) -> str:
    """发一条游戏指令 ✓ 回原文（不猜形状 ✓）"""
    t0 = time.time()
    try:
        r = CH.cmd("execute as Bot at Bot run %s" % text, timeout=tmo, allow_str=True)
        txt = (r.text() or "").strip()
    except Exception as e:
        txt = "EXC:%s:%s" % (type(e).__name__, e)
    say("[%.1fs] %s" % (time.time() - t0, text))
    return txt


def show(tag: str, txt: str, full: bool = True) -> None:
    lines = txt.splitlines() or [""]
    say("  %s: %d lines" % (tag, len(lines)))
    for ln in (lines if full else lines[:6]):
        say("     | " + ln)
    say("  %s.codes: %s" % (tag, codes(txt)))


def pos_now(tag: str):
    txt = run("dshdigest 6")
    say("  %s digest: %s" % (tag, txt.splitlines()[0] if txt else ""))
    import re
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", txt)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def seg_A() -> None:
    say("=" * 78)
    say("A 段：★用户那条命令到底被谁拒★")
    say("  判据 A1：回执第 2 行含 `<--[HERE]` ⇒ Brigadier 语法错（根本没进模组 ✗）")
    say("  判据 A2：`dshevents` 里**没有** walk_start ⇒ 也说明没进模组 ✗")
    say("=" * 78)
    v = run("dshver")
    show("dshver", v)
    p0 = pos_now("A0 起点")

    e0 = run("dshevents")
    show("A0 dshevents（基线）", e0)

    # ── A1 用户的**原样**命令（逗号 ✓）──────────────────────────────────────
    say("-" * 70)
    say("A1 原样命令（逗号分隔）: dshwalk 4134,72,6")
    a1 = run("dshwalk 4134,72,6", 40.0)
    show("A1", a1)
    say("  A1 判据：第2行含 `<--[HERE]` = %s" % ("<--[HERE]" in a1))
    time.sleep(1.5)
    e1 = run("dshevents")
    show("A1 之后 dshevents", e1)
    say("  A1 判据：事件里出现 walk_start = %s" % ("walk_start" in e1))

    # ── A2 同样的错法用在 dshpath 上 ────────────────────────────────────────
    say("-" * 70)
    say("A2 对照：dshpath 4134,72,6（同样的逗号）")
    a2 = run("dshpath 4134,72,6", 40.0)
    show("A2", a2)

    # ── A3 正确写法：空格分隔 ✓ 只看不走的规划 ──────────────────────────────
    say("-" * 70)
    say("A3 正确写法：dshpath 4134 72 6（空格 ✓ 只规划不走 ✓）")
    a3 = run("dshpath 4134 72 6", 40.0)
    show("A3", a3)

    # ── A4 地图（纯 ASCII ✓ 含 y 高度偏移行 ＋ b 占用行 ✓）─────────────────
    say("-" * 70)
    say("A4 dshmap 16（世界真值图 ✓ 含 y<z>| 高度偏移 与 b<z>| 我这一层被谁占着 ✓）")
    a4 = run("dshmap 16", 90.0)
    show("A4", a4)

    # ── A5 真走一次用户想去的那个点（空格写法 ✓）───────────────────────────
    say("-" * 70)
    say("A5 真走：dshwalk 4134 72 6 8000（判据：世界真值 pos= 变了才算走 ✓）")
    e5 = run("dshevents")
    a5 = run("dshwalk 4134 72 6 8000", 90.0)
    show("A5 start", a5)
    time.sleep(3.0)
    st = run("dshwalk")
    show("A5 status", st)
    time.sleep(6.0)
    st2 = run("dshwalk")
    show("A5 status2", st2)
    e5b = run("dshevents")
    show("A5 之后 dshevents（★关键证据★ walk_start/walk_done/why ✓）", e5b)
    p1 = pos_now("A5 终点")
    say("  A5 世界真值：%s -> %s  位移=%.2f" % (p0, p1,
        (sum((a - b) ** 2 for a, b in zip(p0, p1)) ** 0.5) if (p0 and p1) else -1.0))
    say("  A5 walk_start 事件：%s" % ("; ".join(
        [ln for ln in (e5b or "").split(" | ") if "walk_start" in ln]) or "(无)"))


def seg_B() -> None:
    say("=" * 78)
    say("B 段：★对照组★ —— 换目标/换写法，看能不能真走通（判据：世界真值位移 ≥ 2 格 ✓）")
    say("=" * 78)
    p0 = pos_now("B0 起点")
    if not p0:
        say("★读不到 pos ⇒ 停 ✗★")
        return
    bx, by, bz = int(p0[0]), int(round(p0[1])), int(p0[2])
    say("B0 起点格 = (%d,%d,%d)" % (bx, by, bz))

    # B1：**同层**短走（3 格），四个方向都试一次 ✓
    for dx, dz, name in ((3, 0, "东 +X"), (-3, 0, "西 -X"), (0, 3, "南 +Z"), (0, -3, "北 -Z")):
        tgt = (bx + dx, by, bz + dz)
        say("-" * 70)
        say("B1 %s 同层短走 -> %s" % (name, tgt))
        e = run("dshevents")
        cur = e.splitlines()[0][:120] if e else ""
        run("dshwalk %d %d %d 6000" % tgt, 60.0)
        time.sleep(3.0)
        st = run("dshwalk")
        show("B1 status", st, full=False)
        e2 = run("dshevents")
        new = [ln for ln in e2.splitlines()[0].split(" | ")[1:]
               if ("walk_done" in ln or "walk_start" in ln)]
        say("     新事件: %s" % (" ;; ".join(new[-3:]) if new else "(无)"))
        p = pos_now("B1 终点")
        say("     位移=%.2f  （%s -> %s）" % (
            (sum((a - b) ** 2 for a, b in zip(p0, p)) ** 0.5) if p else -1.0, p0, p))
        time.sleep(0.5)

    # B2：用户那个点换成"只规划"看模组怎么说 ✓
    say("-" * 70)
    say("B2 dshpath 4134 72 6 / 4134 73 6 / 4128 72 8（模组自己那条 A* ✓）")
    for t in ("4134 72 6", "4134 73 6", "4134 71 6", "4128 72 8", "4114 71 5"):
        txt = run("dshpath " + t, 40.0)
        show("B2 %s" % t, txt, full=False)
    say("done")


def raw(tag: str, text: str) -> None:
    """★不经过 text() ★ 把 Lua 回来的原始结构整个摊开（看 `...` 和 `?` 到底是谁加的 ✗）"""
    try:
        r = CH.cmd("execute as Bot at Bot run %s" % text, timeout=45.0, allow_str=True)
        say("RAW %s: %s" % (tag, __import__("json").dumps(r.data, ensure_ascii=False)))
        res = r.data.get("result")
        if isinstance(res, dict):
            for i, l in enumerate(res.get("lines") or []):
                say("RAW %s.line[%d] len=%d codes=%s" % (tag, i, len(l), codes(l, 200)))
            say("RAW %s.ret_types=%s success=%s" % (tag, res.get("ret_types"), res.get("success")))
    except Exception as e:
        say("RAW %s EXC %s %s" % (tag, type(e).__name__, e))


def parse_map(lines: list[str]):
    """把 `dshmap` 的三类行解析成表 ✓（y<z>| 高度偏移 / b<z>| 占用 / <z>| 地表字符 ✓）"""
    import re
    head = lines[0]
    m = re.search(r"box=(-?\d+),(-?\d+)\.\.(-?\d+),(-?\d+).*blevel=(-?\d+)", head)
    x0, z0, x1, z1, bl = (int(g) for g in m.groups())
    off = {"0": 0, "A": 1, "B": 2, "a": -1, "b": -2, "c": -3, "d": -4, "e": -5, "f": -6}
    ytab, btab, ctab = {}, {}, {}
    for ln in lines[1:]:
        zs, _, body = ln.partition("|")
        if zs.startswith("y"):
            z = int(zs[1:])
            for i, ch in enumerate(body):
                ytab[(x0 + i, z)] = (bl + off[ch]) if ch in off else None
        elif zs.startswith("b"):
            z = int(zs[1:])
            for i, ch in enumerate(body):
                btab[(x0 + i, z)] = ch
        elif re.fullmatch(r"-?\d+", zs):
            z = int(zs)
            for i, ch in enumerate(body):
                ctab[(x0 + i, z)] = ch
    return (x0, z0, x1, z1, bl), ytab, btab, ctab, head


def seg_C() -> None:
    say("=" * 78)
    say("C 段：★世界真值：假人到底站在什么上面★ ＋ ★走路的对照实验★")
    say("  判据 C1：`dshmap` 的 y 行说『假人自己那格』比四邻高几格（高出 2 ⇒ 安全规则会拦 ✓）")
    say("  判据 C2：`block_state` 独立读出的方块名（不许猜 ✗）")
    say("  判据 C3：**同层**目标 ⇒ 世界真值位移 > 0.5 格 ✓")
    say("  判据 C4：**降 2 格**目标 ⇒ `result=edge` 且位移 ≈ 0 ✗（复现）")
    say("  判据 C5：**降 1 格**目标 ⇒ 应当**照走**（证明闸只拦 ≥2 格 ✗）")
    say("=" * 78)

    raw("逗号写法", "dshwalk 4134,72,6")
    raw("短逗号", "dshwalk 1,2")
    raw("纯未知命令", "zzznosuchcmd")
    raw("缺参数", "dshwalk 4134 72")

    p = pos_now("C0 起点")
    mp = run("dshmap 16", 90.0)
    lines = mp.splitlines()
    (bx0, bz0, bx1, bz1, bl), ytab, btab, ctab, head = parse_map(lines)
    say("C0 图头: %s" % head[:150])
    say("C0 假人 blevel=%d 站在 %s ⇒ blockPos=(%d,%d,%d)"
        % (bl, p, int(p[0]), int(p[1]), int(p[2])))

    cx, cz = int(p[0]), int(p[2])
    say("-- 假人周围 7x7 的『可站脚层 y』表（世界真值 ✓ 来自 /dshmap 的 y 行 ✓）--")
    say("      " + " ".join("x%-4d" % (cx + dx) for dx in range(-3, 4)))
    for dz in range(-3, 4):
        row = []
        for dx in range(-3, 4):
            yy = ytab.get((cx + dx, cz + dz))
            row.append("%-5s" % ("." if yy is None else yy))
        say("z%-4d %s" % (cz + dz, " ".join(row)))
    say("-- 同范围『脚层/头层被谁占着』(b 行 ✓ '.'=空 ✓) --")
    for dz in range(-3, 4):
        say("z%-4d %s" % (cz + dz, "".join(
            btab.get((cx + dx, cz + dz), "?") for dx in range(-3, 4))))

    # ── C2 独立读方块（世界真值 ✓ 不看图 ✗）──────────────────────────────
    say("-" * 70)
    say("C2 block_state 逐格独立读（★这才是『它站在什么上面』的硬证据★）")
    probes = []
    for dz in (0, 1):
        for dy in range(69, 76):
            probes.append((cx, dy, cz + dz))
    for dx in (-1, 1):
        for dy in range(69, 75):
            probes.append((cx + dx, dy, cz))
    for (x, y, z) in probes:
        try:
            d = CH.verify_block(x, y, z, timeout=30.0)
            nm = d.get("name") or d.get("block") or d
        except Exception as e:
            nm = "EXC:%s" % type(e).__name__
        say("   (%d,%d,%d) = %s" % (x, y, z, nm))

    # ── C3/C4/C5 走路对照 ✓ ────────────────────────────────────────────────
    p = pos_now("C3 起点（真值）")
    bx, by, bz = int(p[0]), int(p[1]), int(p[2])

    def walk_probe(tag, tgt, want):
        pp = pos_now("%s 走之前" % tag)
        e = run("dshevents")
        try:
            cur = int(e.splitlines()[0].split("cursor=")[1].split(" ")[0])
        except Exception:
            cur = -1
        run("dshwalk %d %d %d 8000" % tgt, 60.0)
        time.sleep(2.5)
        st = run("dshwalk")
        sv = st.splitlines()[0] if st else ""
        e2 = run("dshevents %d" % cur if cur >= 0 else "dshevents")
        new = [x for x in (e2.splitlines()[0].split(" | ")[1:] if e2 else [])
               if "walk_done" in x or "walk_start" in x]
        pa = pos_now("%s 走之后" % tag)
        moved = ((sum((a - b) ** 2 for a, b in zip(pp, pa))) ** 0.5) if (pp and pa) else -1.0
        say("  %s 目标=%s want=%s" % (tag, tgt, want))
        say("     status: %s" % sv[:230])
        for x in new:
            say("     ev: %s" % x[:230])
        say("     真值 %s -> %s 位移=%.2f ⇒ 判据 %s" % (pp, pa, moved, want))
        return moved

    # 找一个"同层(y=73)"的邻格 ✓
    same = [k for k, v in ytab.items() if v == by and 0 < abs(k[0] - bx) + abs(k[1] - bz) <= 2]
    same.sort(key=lambda k: abs(k[0] - bx) + abs(k[1] - bz))
    say("C3 同层候选（图说脚层=%d 的邻格）: %s" % (by, same[:6]))
    for k in same[:2]:
        walk_probe("C3 同层", (k[0], by, k[1]), "位移应 > 0.5 ✓ 且 result=reached")

    # 找"降 1 格"和"降 2 格"的邻格 ✓
    d1 = sorted([k for k, v in ytab.items() if v == by - 1 and abs(k[0] - bx) + abs(k[1] - bz) <= 3],
                key=lambda k: abs(k[0] - bx) + abs(k[1] - bz))
    d2 = sorted([k for k, v in ytab.items() if v == by - 2 and abs(k[0] - bx) + abs(k[1] - bz) <= 3],
                key=lambda k: abs(k[0] - bx) + abs(k[1] - bz))
    say("C5 降 1 格候选: %s" % d1[:6])
    say("C4 降 2 格候选: %s" % d2[:6])
    for k in d1[:2]:
        walk_probe("C5 降1", (k[0], by - 1, k[1]), "应当**照走**（result 不该是 edge ✗）")
    for k in d2[:2]:
        walk_probe("C4 降2", (k[0], by - 2, k[1]), "应 result=edge 且位移≈0 ✗（复现用户的红项 ✓）")

    # 收尾：真值 ＋ 事件
    pos_now("C9 最终")
    e = run("dshevents")
    say("C9 事件尾部: %s" % (e.splitlines()[0][-800:] if e else ""))
    say("done")


def seg_D() -> None:
    say("=" * 78)
    say("D 段：★对照组 ＋ put_many 的代码路径★（只走 ＋ 只读 ✓ 不动容器 ✗）")
    say("  判据 D1：**降 1 格**的目标 ⇒ 世界真值 y 真的降下来（73 → 72 ✓）")
    say("  判据 D2：从 y=72 **再降 1 格** ⇒ 到 y=71（＝平台层 ✓）⇒ 说明『走』本身没坏 ✓")
    say("  判据 D3：**一步降 2 格** ⇒ 必须复现 `result=edge` ＋ 位移 ≈ 0 ✗（第二次独立复现 ✓）")
    say("  判据 D4：`chest_put_many` 用**不存在的物品名** ⇒ 只走不搬 ⇒ 能看见它在哪一步死 ✗")
    say("=" * 78)
    p0 = pos_now("D0 起点（真值）")
    bx, by, bz = int(p0[0]), int(p0[1]), int(p0[2])

    def step(tag, tgt, want):
        e = run("dshevents")
        try:
            cur = int(e.splitlines()[0].split("cursor=")[1].split(" ")[0])
        except Exception:
            cur = -1
        pp = pos_now("%s 之前" % tag)
        run("dshwalk %d %d %d 8000 exact" % tgt, 60.0)
        time.sleep(2.5)
        st = run("dshwalk")
        e2 = run("dshevents %d" % cur if cur >= 0 else "dshevents")
        new = [x for x in (e2.splitlines()[0].split(" | ")[1:] if e2 else [])
               if "walk_done" in x or "walk_start" in x]
        pa = pos_now("%s 之后" % tag)
        moved = ((sum((a - b) ** 2 for a, b in zip(pp, pa))) ** 0.5) if (pp and pa) else -1.0
        say("  %s 目标=%s（判据：%s）" % (tag, tgt, want))
        say("     status: %s" % (st.splitlines()[0][:230] if st else ""))
        for x in new:
            say("     ev: %s" % x[:230])
        say("     真值 %s -> %s 位移=%.2f ｜ y 变了 %.2f"
            % (pp, pa, moved, (pa[1] - pp[1]) if (pp and pa) else 0.0))
        return pa

    # ── D3：一步降 2 格（复现用户的红项 ✓ 第二次独立复现 ✓）────────────────
    step("D3 降2格", (bx - 1, by - 2, bz), "必须 result=edge ＋ 位移≈0 ✗")

    # ── D1：降 1 格（应当照走 ✓）──────────────────────────────────────────
    pa = step("D1 降1格", (4122, 72, 7), "y 应当真的从 73 变成 72 ✓")
    if pa and abs(pa[1] - 72.0) < 0.6:
        # ── D2：再降 1 格 ⇒ 到平台层 y=71 ─────────────────────────────────
        step("D2 再降1格", (4124, 71, 7), "y 应当到 71（＝平台层 ✓）")
    else:
        say("  ★D1 没降下去 ⇒ D2 跳过（如实说 ✗ 不假装 ✓）★")
    say("  （下面是『走回去』—— 只走 1 格的台阶 ✓ 判据：能回到 y=73）")
    step("D5 爬回1", (4122, 72, 6), "y 应当 +1 → 72 ✓")
    step("D6 爬回2", (4122, 73, 5), "y 应当 +1 → 73 ✓（回到原处 ⇒ 状态复原 ✓）")

    # ── D4：put_many 的代码路径（不存在的物品名 ⇒ 不碰容器 ✓）──────────────
    say("-" * 70)
    say("D4 t_chest_put_many(4122,72,4, 不存在的物品名) —— 只会走 ＋ 读 ✓ **不会搬任何东西** ✗")
    try:
        import mc_mcp as M
        t0 = time.time()
        nav_before = M._pos_now()
        txt, err = M.t_chest_put_many(4122, 72, 4, "no_such_item_zzz:1")
        sec = time.time() - t0
        say("   %.1fs err=%s" % (sec, err))
        for ln in (txt or "").splitlines():
            say("   | " + ln)
        say("   真值：%s -> %s" % (nav_before, M._pos_now()))
    except Exception as e:
        say("   EXC %s: %s" % (type(e).__name__, e))

    # ── D7：工具层的 walk_to（用户看到的那一层 ✓）──────────────────────────
    say("-" * 70)
    say("D7 工具层 walk_to 到平台层（用户实际调的那一层 ✓）")
    try:
        import mc_mcp as M
        for tgt in ((4121, 71, 4), (4124, 71, 8)):
            t0 = time.time()
            txt, bad = M.t_walk_to(tgt[0], tgt[1], tgt[2], 20000)
            say("   walk_to %s ⇒ err=%s %.1fs" % (tgt, bad, time.time() - t0))
            for ln in (txt or "").splitlines():
                say("   | " + ln)
            say("   真值：%s" % (M._pos_now(),))
    except Exception as e:
        say("   EXC %s: %s" % (type(e).__name__, e))
    pos_now("D9 最终")
    e = run("dshevents")
    say("D9 事件尾: %s" % (e.splitlines()[0][-600:] if e else ""))
    say("done")


def seg_E() -> None:
    say("=" * 78)
    say("E 段：★put_many 到底死在哪一步★ ＋ ★那句中文回执到底说什么★ ＋ ★把假人放回原处★")
    say("  判据 E1：`_near(4122,72,4)`（`_box_many` 的第一步 ✓ 只走不搬 ✓）⇒ 若返回 bad "
        "⇒ **put_many 一行 dshbox 都不会发** ✓（＝电池里的 dshbox=0 ✓）")
    say("  判据 E2：世界真值证明 `4123,72,4` / `4122,72,5` 到底站不站得住（独立读 ✓）")
    say("  判据 E3：把『回执第一行』跟一条**已知英文**的失败对照 ⇒ 判断 `?` 是不是真的本地化中文")
    say("  判据 E4：走回桶顶（y=73）⇒ 世界真值 pos= 回到 73.00")
    say("=" * 78)

    # ── E3：回执里的 `?` 到底是什么 ───────────────────────────────────────
    for t in ("dshwalk 9999999 71 5", "dshwalk notanum 71 5", "data get entity NoSuchEntity Pos",
              "zzznosuchcmd", "dshwalk 4134,72,6"):
        raw("E3[%s]" % t, t)

    # ── E2：那两个"候选落脚格"在世界里到底怎样 ───────────────────────────
    say("-" * 70)
    say("E2 独立读（世界真值 ✓）：_near 会去的那两格")
    for (x, y, z) in ((4123, 72, 4), (4123, 71, 4), (4122, 72, 5), (4122, 73, 5),
                      (4122, 71, 4), (4122, 72, 4), (4123, 71, 5), (4123, 72, 5)):
        try:
            d = CH.verify_block(x, y, z, timeout=30.0)
            nm = d.get("name") or d.get("block") or d
        except Exception as e:
            nm = "EXC:%s" % type(e).__name__
        say("   (%d,%d,%d) = %s" % (x, y, z, nm))

    # ── E1：真跑 `_near`（走 + 读 ✓ 不碰容器 ✗）────────────────────────────
    say("-" * 70)
    say("E1 真跑 M._near(4122,72,4)（这就是 put_many 的第一步 ✓ 只走 ✓）")
    try:
        import mc_mcp as M
        b0 = M._pos_now()
        t0 = time.time()
        txt, bad = M._near(4122, 72, 4)
        say("   _near 用了 %.1fs bad=%s" % (time.time() - t0, bad))
        for ln in (txt or "").splitlines():
            say("   | " + ln)
        say("   真值：%s -> %s" % (b0, M._pos_now()))
        say("   ⇒ 判据 E1：bad=True ⇒ `_box_many` 会在**不读容器、不发 dshbox**的情况下返回 ✗ "
            "（＝电池里 dshbox=0 ✓）")
    except Exception as e:
        say("   EXC %s: %s" % (type(e).__name__, e))

    # ── E4：放回原处（桶顶 y=73 ✓ 只走 ✓）────────────────────────────────
    say("-" * 70)
    say("E4 走回桶顶 (4122,73,4)：判据 ⇒ pos= 回到 73.00")
    for tgt in ((4122, 73, 4), (4122, 73, 4)):
        e = run("dshevents")
        try:
            cur = int(e.splitlines()[0].split("cursor=")[1].split(" ")[0])
        except Exception:
            cur = -1
        run("dshwalk %d %d %d 15000 exact" % tgt, 60.0)
        time.sleep(3.0)
        st = run("dshwalk")
        say("   status: %s" % (st.splitlines()[0][:220] if st else ""))
        pos_now("E4 之后")
    e = run("dshevents")
    say("E4 事件尾: %s" % (e.splitlines()[0][-400:] if e else ""))
    say("done")


def seg_F() -> None:
    say("=" * 78)
    say("F 段：★put_many 的两条导航分支逐条真跑★（只走 ✓ 不碰容器 ✗）")
    say("  判据 F1：`M._walk(4123,72,4)`（`_near` 的第一选择 ✓）⇒ bad=?  ＋ 世界真值")
    say("  判据 F2：`M._walk(4122,72,5)`（`_near` 的第二选择 ✓）⇒ bad=?  ＋ 世界真值")
    say("  判据 F3：之后走回桶顶 ⇒ pos= 回到 y=73.00（状态复原 ✓）")
    say("=" * 78)
    try:
        import mc_mcp as M
        for tag, tgt in (("F1", (4123, 72, 4)), ("F2", (4122, 72, 5))):
            b0 = M._pos_now()
            t0 = time.time()
            txt, bad = M._walk(tgt[0], tgt[1], tgt[2], 25000)
            b1 = M._pos_now()
            say("  %s M._walk%s ⇒ bad=%s（%.1fs）" % (tag, tgt, bad, time.time() - t0))
            for ln in (txt or "").splitlines():
                say("     | " + ln)
            say("     真值：%s -> %s" % (b0, b1))
        say("  ⇒ 两条都 bad ⇒ `_near` 返回 bad ⇒ `_box_many` 在**不读容器、不发 dshbox** 的情况下"
            "退出 ✗（正是电池里 `dshbox=0` 那个形状 ✓）")
    except Exception as e:
        say("  EXC %s: %s" % (type(e).__name__, e))
    say("-" * 70)
    say("F3 复原：走回桶顶")
    for _ in range(2):
        run("dshwalk 4122 73 4 15000 exact", 60.0)
        time.sleep(2.5)
        st = run("dshwalk")
        say("   status: %s" % (st.splitlines()[0][:200] if st else ""))
        pos_now("F3")
    say("done")


def seg_G() -> None:
    say("=" * 78)
    say("G 段：★把电池里那些『真红项』的目标逐个问一遍★（只读 ✓ 不走 ✓）")
    say("  判据 G1：`dshpath <x> <y> <z>` 的 `goal_standable` —— false ⇒ **那个目标格本身站不住** ✗")
    say("           ⇒ 那一项的红是『目标挑错了』✓ 不是『安全规则拦』✗")
    say("  判据 G2：route_view/route_verify 里『地图说 y=70 有地板、世界说没有』的那几格，")
    say("           用 block_state 独立读 y=68..72 ⇒ 看到底有没有地板（世界真值 ✓）")
    say("=" * 78)
    say("G1 电池真红过的目标（`dshpath` 只规划 ✓ 不走 ✓）：")
    for t in ((4114, 71, 5), (4106, 72, 4), (4120, 72, 16), (4124, 71, 3),
              (4137, 73, 20), (4134, 72, 6), (4121, 71, 4), (4117, 71, 6)):
        txt = run("dshpath %d %d %d" % t, 40.0)
        say("     %s" % (txt.splitlines()[0][:240] if txt else ""))
    say("-" * 70)
    say("G2 route_view 说『地图 floor=70 / 世界 None』的那三格：")
    for (x, z) in ((4126, 14), (4129, 17), (4133, 21), (4108, 19)):
        row = []
        for y in range(68, 73):
            try:
                d = CH.verify_block(x, y, z, timeout=30.0)
                nm = d.get("name") or d.get("block") or str(d)
            except Exception as e:
                nm = "EXC:%s" % type(e).__name__
            row.append("y%d=%s" % (y, nm))
        say("   (%d,%d): %s" % (x, z, " ｜ ".join(row)))
    say("done")


def main(argv) -> int:
    seg = (argv[0].upper() if argv else "A")
    say("### _diag_walk.py 段=%s  at=%s" % (seg, time.strftime("%Y-%m-%d %H:%M:%S")))
    if seg == "A":
        seg_A()
    elif seg == "B":
        seg_B()
    elif seg == "C":
        seg_C()
    elif seg == "D":
        seg_D()
    elif seg == "E":
        seg_E()
    elif seg == "F":
        seg_F()
    elif seg == "G":
        seg_G()
    else:
        say("未知段 ✗")
        return 2
    say("### end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
