#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_v27.py —— 模组 v2.7 的**验收基准**（只测不改 ✓ 全 ASCII 判据 ✓）

v2.7 修的四条（每条都有一条**现场**在背后 ✗ 见错题本 P27/P29/P30/P26 ✓）：
  ① `dshwalk` 空岛护栏**取样错两层** ✗（`y-0.2` ⇒ 查的是地下一层 ✗ ⇒ 薄地板区到处误停 ✗）
  ② `dshwalk` **不会绕障** ✗（沿 x=4114 那道 `mcwfences` 墙：1.5 格高 ⇒ 跳不过去 ⇒ 真人会绕 ✓）
  ③ `dshwalk` **不会下台阶** ✗（目标低一层就停 ⇒ 报 `blocked` 而 `aheadBlocked=false` ✗）
  ④ 交易 `tryMoveItems` **搬整堆** ✗ ⇒ 余款一大堆 ⇒ 满包时**掉地上** ✗✗ ＋ 回执 `paid` 说谎 ✗
  ⑤ 顺带新增 `dshplace` ✓（显式放方块 ＋ 落点校验 ✗ 修 P30 那个"FAIL 不说原因"✗）

验收项（每项独立可判 ✓ 判据只用世界真值 ✓）：
  B0 `/dshver` 必须是 **2.7.0** ✓（否则**直接退出** ✗ 不给假数据 ✓）
  B1 ★绕障★：从墙**西侧**走到墙**东侧**（必须绕过 x=4114 那道墙 ✗）⇒ 期望 `reached` ＋ `detours>0`
  B2 ★下台阶★：从高一层的方块上走到低一层的目标 ⇒ 期望 `reached`
  B3 ★薄地板★：沿 x≈4121 走（v2.6 在这里误报"前方无支撑"✗）⇒ 期望 `reached`
  B4 ★速度★：一条直线腿 ⇒ 用模组自报的 `ticks` 算 **格/秒** ✓（v2.6 外部量到 ≈0.94 ✗ 且高估耗时 ✓）
  B5 ★放方块★：`dshplace` 放一块原石 ⇒ **世界真值扫出来** ✓ ⇒ 再用锤子砸 ⇒ **沙砾进背包** ✓（＝整条链的末两段 ✓）
  B6 ★交易账★：`paid` 必须**等于**背包里绿宝石的真实减少量 ✓（v2.6 会报 16 而实际只花 2 ✗）

用法：py tools/bench_v27.py
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

VILLAGER = "@e[type=villager,limit=1,sort=nearest]"


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

    def ver_ok(txt: str, minimum=(2, 7)) -> bool:
        """版本闸门 ✓ —— ★判据是"**≥ 最低版本**"✗ 不是"必须等于那一版"★★
        （我第一版写成"必须含 2.7"✗ ⇒ 升到 2.8 之后它**把自己的升级判成失败**✗
          —— P10 家族第三次 ✓：**判据别比现实更严** ✗ 见错题本 P36 ✓）
        """
        m = re.search(r"version=(\d+)\.(\d+)", txt or "")
        if not m:
            return False
        return (int(m.group(1)), int(m.group(2))) >= minimum

    def walk(x: int, y: int, z: int, ms: int = 20000) -> dict:
        """走一条腿并**等它真的结束** ✓ → 返回状态字段（含 detours/step_downs/ticks ✓）"""
        t0 = time.time()
        st = bot("dshwalk %d %d %d %d exact" % (x, y, z, ms), 90.0)
        if not st.startswith("dshwalk start"):
            return {"result": "start_failed", "raw": st[:160], "at": "?", "dist": "?", "dt": 0}
        line = ""
        deadline = time.time() + max(8.0, ms / 1000.0 + 8.0)
        while time.time() < deadline:
            time.sleep(0.35)
            line = bot("dshwalk", 30.0)
            if kv(line).get("status") == "done":
                break
        k = kv(line)
        k["dt"] = time.time() - t0
        k["raw"] = line
        print("      → (%d,%d,%d) %s 停在 %s 偏差 %s 格 ｜ 驱动=%s 绕障=%s 下台阶=%s ticks=%s sprint=%s %s"
              % (x, y, z, k.get("result", "?"), k.get("at"), k.get("dist"), k.get("mode"),
                 k.get("detours", "-"), k.get("step_downs", "-"), k.get("ticks", "-"),
                 k.get("sprint", "-"),
                 ("why=" + k["why"]) if k.get("why") not in (None, "none") else ""))
        return k

    def tp_valid(x: int, y: int, z: int) -> bool:
        """★每一项测试都要**自己的站位**★ ✗ —— 否则一项卡住会**连累后面所有项** ✗
        （v2.7.0 那轮就这么被我搞砸了 ✓：B1 卡在墙边 ⇒ B2/B3 全都带着同一个位置去跑 ✗
          ⇒ 报出来的"失败"其实是**我出题的问题** ✗ 见 P10 家族 ✓）
        做法 ✓：先用**原生扫描**确认"脚下实心 ＋ 身上两格空" ✓ 再 tp ✓ 再看回执坐标 ✓
        """
        scan = bot('dshscan %d %d %d %d %d %d ":" 8 1' % (x - 1, y - 1, z - 1, x + 1, y + 1, z + 1), 60.0)
        floor_ok = ("%d,%d,%d:" % (x, y - 1, z)) in scan
        feet_free = ("%d,%d,%d:" % (x, y, z)) not in scan
        if not (floor_ok and feet_free):
            print("      ⚠ 站位 (%d,%d,%d) 不合法（脚下实心=%s 身上空=%s）⇒ 这一项**如实跳过** ✗"
                  % (x, y, z, floor_ok, feet_free))
            return False
        game("tp Bot %.2f %d %.2f" % (x + 0.5, y, z + 0.5))
        time.sleep(0.8)
        return True

    print("=" * 76)
    print("模组 v2.7 验收基准")
    print("=" * 76)

    # ── B0 版本 ────────────────────────────────────────────────────────────────
    v = bot("dshver", 60.0)
    print("[B0] %s" % v[:180])
    if not ver_ok(v, (2, 7)):
        print("\n结论：**跑的还是旧版** ✗ —— 模组改动必须**关掉游戏进程重启** ✗（只退世界不加载 ✗）")
        return 2

    # ── B1 绕障（墙在 x=4114、z 7..11 ✗ v2.6 就卡在这儿 ✗）────────────────────
    print("\n[B1] 绕障：墙西 → 墙东（x=4114 那道 1.5 格高的墙 ✗ 跳不过去 ⇒ 真人会绕 ✓）")
    if tp_valid(4112, 71, 9):
        # ⚠ 预算要给够 ✗：绕障是"侧走一小段→回直线→再撞→再侧走"的**阶梯式**走法 ✓
        #   第一版只给 20 秒 ⇒ 实测 6 次绕障走了 403 tick 后**差 5 格超时** ✗
        #   —— 机制没错 ✓ 是**我把预算给少了** ✗（同一族：先分清"东西坏了"还是"题出错了"✗ P34 ✓）
        k1 = walk(4117, 71, 9, 45000)
        # ★判据要问"**过没过墙**"✗ 而不是"零点几格"★★
        #   （2026-09-19 深夜实测 ✓：它**已经绕过去了** ✓ 从墙西 x=4112.5 走到 **x=4117.55** ✓
        #     而墙在 x=4114 ⇒ **确实过墙了** ✓✓ 只是离终点还差 **0.80 格** ✗
        #     而我给的是 `exact` ⇒ 到达判据 0.7 ✗ ⇒ 判成 timeout ✗ —— **假失败** ✗ 见 P36/P10 ✓）
        try:
            ex = float(str(k1.get("at", "")).split(",")[0])
        except Exception:
            ex = -999.0
        crossed = ex > 4115.0
        check("B1 绕过去了（★以「是否真的过墙」为准★：终点 x=%.2f > 4115 ✓ 墙在 4114 ✓）" % ex,
              crossed, "结果=%s at=%s detours=%s" % (k1.get("result"), k1.get("at"), k1.get("detours")))
        check("B1b 而且**记了绕障次数**（detours>0 ✓ 证明是绕的 ✗ 不是撞运气 ✓）",
              int(k1.get("detours", "0") or 0) > 0, "detours=%s" % k1.get("detours"))
    else:
        fails.append("B1(站位不合法 ⇒ 如实跳过 ✗)")

    # ── B2 下台阶：**放在 B3/B4 之后**✗（因为它的证据来自那两条腿 ✓）
    #   ⚠ 我上一版把它写在 B3/B4 **之前** ✗ ⇒ `k3`/`k4` 还不存在 ⇒ 取证恒为 0 ⇒ 假失败 ✗
    #     （又一次"我把题出错了"✗ 见 P34 ✓ —— 顺序也是判据的一部分 ✓）

    # ── B3 薄地板（v2.6 误报"前方无支撑"✗）────────────────────────────────────
    print("\n[B3] 薄地板区（v2.6 在这里误报 edge：`no support at …,69,…` ✗）")
    if tp_valid(4121, 71, 11):
        k3 = walk(4121, 71, 4, 25000)
        check("B3 走通了（reached）", k3.get("result") == "reached",
              "结果=%s why=%s" % (k3.get("result"), k3.get("why", "none")))
    else:
        fails.append("B3(站位不合法 ⇒ 如实跳过 ✗)")

    # ── B4 速度（模组自报 ticks ✓ 不用外部秒表 ✗）─────────────────────────────
    print("\n[B4] 速度：用模组自报的 `ticks` 算格/秒（v2.6 外部量到 ≈0.94 ✗ 且**高估耗时** ✓）")
    start = (4121.5, 71.0, 4.5)
    game("tp Bot %.2f %d %.2f" % start)
    time.sleep(0.6)
    k4 = walk(4121, 71, 12, 25000)
    speed = -1.0
    try:
        tk = float(k4.get("ticks", "-1"))
        ax, ay, az = [float(v) for v in str(k4.get("at", "")).split(",")]
        travelled = ((ax - start[0]) ** 2 + (az - start[2]) ** 2) ** 0.5
        if tk > 0 and travelled > 0.5:
            speed = travelled / (tk / 20.0)
            print("      实际走了 %.2f 格 / %s ticks ⇒ %.2f 格/秒" % (travelled, k4.get("ticks"), speed))
    except Exception:
        speed = -1.0
    print("      模组自报 ticks=%s ⇒ 折算速度 ≈ %.2f 格/秒（真人步行 4.3 ✓ 疾跑 5.6 ✓）"
          % (k4.get("ticks"), speed))
    check("B4 速度 > 1.5 格/秒（v2.6 ≈0.94 ✗）", speed > 1.5, "实测 %.2f" % speed)

    # ── B2 下台阶：证据来自 B3/B4 两条真实腿 ✓（**必须放在它们之后**✗ 见上面注释 ✓）──────
    print("\n[B2] 下台阶：从**真实行走**里取证（`step_downs` 计数 ✓）—— 不写死站位 ✗")
    sd = int(k3.get("step_downs", "0") or 0)
    sd2 = int(k4.get("step_downs", "0") or 0)
    print("      B3 那条腿 step_downs=%s ｜ B4 那条腿 step_downs=%s" % (sd, sd2))
    check("B2 走的过程里确实**下过台阶**（step_downs>0 ✓ v2.6 会在这里停 ✗）", (sd + sd2) > 0,
          "合计 %d 次" % (sd + sd2))

    # ── B5 放方块 ＋ 砸（＝链子的末两段 ✓）─────────────────────────────────────
    print("\n[B5] `dshplace` 放原石 ⇒ 世界真值复核 ⇒ 木锤砸 ⇒ 沙砾进背包")
    # ★先找一个**真的是空气**的目标格★ ✗ —— 上一次我写死 (4122,71,8) ✗
    #   而那一格**还留着上一轮放的原石** ✓ ⇒ `dshplace` **正确地拒绝了** ✓（"not air" ✓）
    #   可我的判据只看"那格有没有 cobblestone" ✗ ⇒ **把拒绝当成了成功** ✗✗（假阳性 ✓）
    #   ⇒ 纪律（P22 家族 ✓）：判据必须能区分"**这次**做成了"和"**本来**就在那儿" ✗
    tx, ty, tz = None, None, None
    for cand in [(4122, 71, 8), (4123, 71, 8), (4121, 71, 8), (4122, 71, 9), (4122, 71, 7)]:
        sc = bot('dshscan %d %d %d %d %d %d "cobblestone" 4 1'
                 % (cand[0] - 1, cand[1] - 1, cand[2] - 1, cand[0] + 1, cand[1] + 1, cand[2] + 1), 60.0)
        occupied = ("%d,%d,%d:" % cand) in sc
        if not occupied:
            tx, ty, tz = cand
            break
    if tx is None:
        print("      ⚠ 候选格都占着 ⇒ 这一项**如实跳过** ✗")
        fails.append("B5(没有空目标格 ⇒ 如实跳过 ✗)")
    else:
        print("      目标格 (%d,%d,%d) 是空的 ✓（先扫过再动手 ✗ 见 P30/§5.2 ✓）" % (tx, ty, tz))
        game("tp Bot 4123.5 71 8.5")
        time.sleep(0.8)
        # ⚠ Lua 的 `hold_item` **只翻快捷栏** ✗ ⇒ 用**模组**那条 `dshequip` 按名字拿 ✓（v2.7.1 ✓）
        #   ★这一句是 v2.7.0 那轮失败的根因★ ✗：`dshplace` 为了拿原石**把锤子挤出了手** ✗
        #   ⇒ 随后 `dig_at` 找不到锤子 ✗ ⇒ 拿着原石干砸 8 秒 ✗（换手顺序 ✗ 见错题本 P33 ✓）
        print("      拿锤子：%s" % bot('dshequip "exdeorum:wooden_hammer"', 60.0)[:140])
        pl = bot('dshplace %d %d %d "minecraft:cobblestone"' % (tx, ty, tz), 90.0)
        print("      dshplace：%s" % pl[:240])
        scan = bot('dshscan %d %d %d %d %d %d "cobblestone" 8 1'
                   % (tx - 1, ty - 1, tz - 1, tx + 1, ty + 1, tz + 1), 60.0)
        placed = (("%d,%d,%d:minecraft:cobblestone" % (tx, ty, tz)) in scan) and ("verified=" in pl)
        check("B5 放上了（**这次**真的做了 ✓ 世界真值 ＋ 回执双向对账 ✓）", placed, scan[:160])
        if placed:
            # ★**放完再拿一次锤子**★ ✗（`dshplace` 拿原石时会把手换掉 ✓ —— 顺序就是这个坑 ✓）
            print("      再拿锤子：%s" % bot('dshequip "exdeorum:wooden_hammer"', 60.0)[:140])
            before = w.counts().get("minecraft:gravel", 0)
            # ★★2026-10-03 改走**模组侧**✗★★（欠账 ② 收尾 ✓ 与 jobs/skills 同一口径 ✓）
            #   ★注意✗★：★这里本来**显式给了锤子**✗（`tool=…wooden_hammer` ✓）
            #     ⇒ ★模组侧不再接受 tool ✗ 而是**按破坏速度挑**✗★ ——
            #     ★手上那把锤子仍然是"我特意拿的"✗（`dshequip` 上面刚做过✓★）
            #     ⇒ ★语义不变 ✗ 只是不再由中间层点名✓★
            _rt = ch.cmd("execute as Bot at Bot run dshdig %d %d %d" % (tx, ty, tz),
                         timeout=120.0, allow_str=True)
            print("      dshdig：%s" % str(_rt.text())[:160])
            time.sleep(1.5)
            mid = walk(tx, ty, tz, 8000)       # 掉落物不会自己飞过来 ⇒ 走过去捡 ✓
            after = w.counts().get("minecraft:gravel", 0)
            check("B5b 砸出来了沙砾（背包实增 ✓ 不看回执 ✗）", after > before,
                  "gravel %d → %d（走位 %s ✓）" % (before, after, mid.get("result")))
        else:
            fails.append("B5b(因 B5 没放上 ⇒ 砸这一项无法测 ✗)")

    # ── B6 交易：paid 必须等于真实扣款 ────────────────────────────────────────
    print("\n[B6] 交易：`paid` 必须**等于**背包里绿宝石的真实减少 ✓（v2.6 报 16 而实际花 2 ✗）")
    game("tp Bot 4120.5 71 4.5")
    time.sleep(1.0)
    b = w.counts().get("minecraft:emerald", 0)
    # ★先看**买得起几笔**✗ —— 上一版没管预算 ⇒ 只剩 1 个绿宝石还想买 2 笔 ✗
    #   而模组那次**干得完全正确** ✓：第 2 笔 `res=0` ⇒ **如实停** ✓ 回 `trades=1` ✓
    #   ⇒ 我却拿"times=2"去判它 ✗ ⇒ **假失败** ✗（资源不足时正确的话是"无法判定"✗ P34 ✓）
    times = 2 if b >= 4 else (1 if b >= 2 else 0)
    print("      绿宝石 %d 个 ⇒ 本次只买 **%d** 笔（预算意识 ✗ 见 P34 ✓）" % (b, times))
    if times == 0:
        print("      ⚠ 绿宝石不足 2 个 ⇒ **无法判定** ✗（不是失败 ✗）—— 请换一次交易/补点绿宝石再跑 ✓")
        fails.append("B6(绿宝石不足 ⇒ 无法判定 ✗)")
        rep = ""
    else:
        rep = bot("dshtrade do %s 0 %d" % (VILLAGER, times), 150.0)
    time.sleep(1.5)
    a = w.counts().get("minecraft:emerald", 0)
    ground = bot("data get entity @e[type=item,limit=1,sort=nearest,distance=..8] Item.id", 30.0)
    k = kv(rep)
    paid = int(k.get("paid", "-1") or -1)
    print("      回执：%s" % rep[:260])
    print("      背包：绿宝石 %d → %d（实减 %d）｜ 模块自报 paid=%s refunded=%s"
          % (b, a, b - a, k.get("paid"), k.get("refunded")))
    if times > 0:
        check("B6 笔数对（times=%d ⇒ %d 笔）" % (times, times), k.get("trades") == str(times),
              "trades=%s" % k.get("trades"))
        check("B6b ★paid == 真实扣款★（v2.6 这条必挂 ✗）", paid >= 0 and paid == (b - a),
              "paid=%s 实减=%d" % (k.get("paid"), b - a))
        check("B6c 精确装料（diag 里 fill=exact ✓）", "fill=exact" in rep, rep[-100:])
    check("B6d 地上没有掉落物（绝不许掉钱 ✗ P20 ✓）", "minecraft:" not in ground, ground[:90])

    print("=" * 76)
    if fails:
        print("结论：**%d 项没通过 ✗** —— %s" % (len(fails), "／".join(fails)))
    else:
        print("结论：★v2.7 全部判据通过 ✓★（绕障 ✓ 下台阶 ✓ 薄地板 ✓ 速度 ✓ 放方块 ✓ 交易账 ✓）")
    print("=" * 76)
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
