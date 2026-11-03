#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""errata_guard_test.py -- ★把"高代价的错题"钉成**可执行的回归判据**★ ✓（离线 ✓ 不需要游戏 ✓）

WHY（2026-09-29 用户审计指出 ✓）：
  错题本已经 **120+ 条** ✓ 而且确实被引用（交接文档 46 处 ✓ 代码注释里到处都是 ✓）——
  可"**读过 ≠ 防住**"✗：同一个坑会以**变种**形式再踩一次 ✓
  （第 31／32／34 轮的"到达判定 ✗"与"跳跃高度 ✗"**本质上都是同一类**：
    ★**没验过的假设直接发货**★ ✗）
  ⇒ 这份判据把 **9 条最贵的错题**各配一个**最小复现** ✓
    能离线断言的 ⇒ **跑行为** ✓；只能"防止这行代码回来"的 ⇒ **查源码** ✓（F1/F3/F4 已经用过这招 ✓）
  ★它必须**不需要游戏**★ ✓ ⇒ 可以当**发货前闸门** ✓（`check_all.py --offline` ✓）

CRITERIA（每条对应一条错题 ✓ 跑之前先写 ✓）：
  E1  P111 `legend=` 与 `ylegend=` 互为子串 ⇒ 必须按**字段边界**取 ⇒ 拿到的是**方块名表** ✗ 不是偏移表 ✓
  E2  P114 字母格"名字说它不是地板"**不许把整柱丢掉** ⇒ 格子要**在图上** ✗
  E3  P125 `is_climbable`：整方块 ✓ 能跳／1.5 的墙 ✗ 不能（★不许把墙当"能跳"★ ✗）
  E4  P119/P121 `max_rise`：整方块 +1 ⇒ 允许 ✓；**墙 +1 ⇒ 必须拒绝** ✗（真跑起来停在半格外 ✓）
  E5  P120 `_descent_guard`：真下降且回不来 ⇒ **拦住** ✓；同层目的地 ⇒ 放行 ✓
  E6  P122 合成成功要认**回执里真有的字段**（`done=` ✓／`ok=true` ✓ 都认 ✗ 不许只认一个 ✓）
  E7  P116 走完之后"没到"必须带**为什么**（源码里两句都得在 ✓）
  E8  P32/P104 "到没到"**不许只看距离**（源码里不许出现 `ok_arrive = in_cell or` ✗）
  E9  P31 障碍记忆**要带层**（`BLOCKED_LV` 与 `blocked_here` 必须在 ✓）
  E10 P129 同一种格式**只许一把尺子**：`errata_archive.py` 里读 `### P<n>` 的正则字面量
            **只能有一处** ✗ ＋ **逐字相同**的重复块必须被删掉 ✓（正文不同的**一块都不许删** ✗）
  E11 P131 ★事件名**只许从模组源码抄**✗★：`speech.EVENT_KINDS` ＋ `SKIP_EVENTS` 的键
            必须与 `DshBridgeMod.java` 里 `ev("…")` 的**字面量集合完全一致**（双向 ✓）
            —— 多一个 ＝ 我编了个不存在的事件 ✗（那种扳机**永远不会响**✗）；
               少一个 ＝ 模组发了事件**我们压根不知道** ✗（表现一样：都不出声 ✓）

ASCII-only 输出 ✓（控制台是 GBK ✓ 中文只走 UTF-8 重定向 ✓）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mapread as MR      # noqa: E402
import mc_mcp as M        # noqa: E402
import pathplan as PP     # noqa: E402


def say(s):
    print(s, flush=True)


def fake_reader(payload):
    r = MR.Reader.__new__(MR.Reader)
    r.calls = 1
    r.verbose = False
    r.ab = lambda cmd, tmo=60.0: payload
    r.save = lambda m, max_age=600.0: None
    return r


def main():
    ok = True
    BY = 72
    LEG = "G:minecraft:grass_block,W:mcwfences:oak_wall"
    YLEG = "0:same,A:+1,B:+2,a:-1,b:-2,c:-3,d:-4,e:-5,f:-6,.:none"

    # ---- E1 (P111)：`ylegend=` 在前、`legend=` 在后 ⇒ 必须取到**方块名表** ----
    head = ("dshmap box=0,0..1,0 from=1,%d,1 standable=2 blocked=0 blevel=%d "
            "ylegend=%s legend=%s" % (BY, BY, YLEG, LEG))
    payload = "\n".join([head, "0|GG", "y0|00", "b0|.."])
    m1 = fake_reader(payload).build_dshmap(radius=1, max_age=1.0)
    e1 = bool(m1) and (m1.meta.get("legend") or {}).get("G") == "minecraft:grass_block" \
        and int(m1.meta.get("letters_kept") or 0) == 0
    say("E1 (P111) legend 字段边界: legend[G]=%r letters_kept=%s => %s"
        % ((m1.meta.get("legend") or {}).get("G") if m1 else None,
           m1.meta.get("letters_kept") if m1 else None, e1))
    ok &= e1

    # ---- E2 (P114)：字母说"地板是墙"（不是地板）⇒ 格子必须**留在图上** ----
    m2 = MR.Map(0, 60, 0, 1, 76, 1)
    m2.cols[(0, 0)] = {70: "minecraft:grass_block"}
    m2.cols[(1, 0)] = {70: "minecraft:grass_block",
                       71: "mcwfences:sandstone_grass_topped_wall"}
    m2.meta.update({"blevel": 71, "has_offsets": True,
                    "mod_standable": {"0,0": 71, "1,0": 72}})
    e2 = bool(m2.cols.get((1, 0))) and (m2.standable(1, 0, below=73) is True)
    say("E2 (P114) 墙头那一柱留在图上且 72 层可站: col=%s standable=%s => %s"
        % (m2.cols.get((1, 0)) is not None, m2.standable(1, 0, below=73), e2))
    ok &= e2

    # ---- E3 (P125)：跳跃高度按方块判 ----
    e3 = (PP.is_climbable("minecraft:oak_planks") is True) \
        and (PP.is_climbable("mcwfences:sandstone_grass_topped_wall") is False) \
        and (PP.is_climbable("minecraft:oak_slab") is True)
    say("E3 (P125) is_climbable: 整方块=%s 墙=%s 半砖=%s => %s"
        % (PP.is_climbable("minecraft:oak_planks"),
           PP.is_climbable("mcwfences:sandstone_grass_topped_wall"),
           PP.is_climbable("minecraft:oak_slab"), e3))
    ok &= e3

    # ---- E4 (P119/P121)：+1 整方块允许 ✓ ／ +1 墙**必须拒绝** ✗ ----
    def mk(block):
        mm = MR.Map(0, 60, 0, 1, 76, 1)
        mm.cols[(0, 0)] = {70: "minecraft:grass_block"}
        mm.cols[(1, 0)] = {70: "minecraft:grass_block", 71: block}
        mm.meta.update({"blevel": 71, "has_offsets": True,
                        "mod_standable": {"0,0": 71, "1,0": 72}})
        return mm
    p_full = PP.Planner(mk("minecraft:oak_planks"), level=71, max_up=1)
    p_wall = PP.Planner(mk("mcwfences:sandstone_grass_topped_wall"), level=71, max_up=1)
    e4 = (p_full.ok(1, 0) is True) and (p_wall.ok(1, 0) is False) \
        and (p_full.max_rise(1, 0, 71) == 1) and (p_wall.max_rise(1, 0, 71) == 0)
    say("E4 (P119/121) 整方块+1 允许=%s ／ 墙+1 拒绝=%s => %s"
        % (p_full.ok(1, 0), not p_wall.ok(1, 0), e4))
    ok &= e4

    # ---- E5 (P120)：回程守卫 ----
    def mk2(cells, feet):
        mm = MR.Map(0, 60, 0, 3, 76, 3)
        for k, v in cells.items():
            mm.cols[k] = dict(v)
        mm.meta.update({"blevel": 71, "has_offsets": True,
                        "mod_standable": {"%d,%d" % k: v for k, v in feet.items()}})
        return mm
    G = "minecraft:grass_block"
    S = "minecraft:stone"
    flat = mk2({(0, 0): {70: G}, (1, 0): {70: G}}, {(0, 0): 71, (1, 0): 71})
    pit = mk2({(0, 0): {70: G}, (1, 0): {68: G},
               (1, 1): {70: S, 71: S, 72: S}, (1, -1): {70: S, 71: S, 72: S},
               (2, 0): {70: S, 71: S, 72: S}}, {(0, 0): 71, (1, 0): 69})
    g_flat, _w1 = M._descent_guard(flat, 71, 0, 0, (1, 71, 0))
    g_pit, w_pit = M._descent_guard(pit, 71, 0, 0, (1, 69, 0))
    e5 = (g_flat is True) and (g_pit is False) and ("出不来" in w_pit)
    say("E5 (P120) 同层放行=%s ／ 单向坑拦住=%s（理由含'出不来'=%s） => %s"
        % (g_flat, not g_pit, "出不来" in w_pit, e5))
    ok &= e5

    # ---- E6 (P122)：合成成功字段 ---- #
    sa = (ROOT / "tools" / "step_assist.py").read_text(encoding="utf-8")
    e6 = ("done=" in sa) and ("ok=true" in sa)
    say("E6 (P122) step_assist 同时认 done= 与 ok=true => %s (done=%s ok=%s)"
        % (e6, "done=" in sa, "ok=true" in sa))
    ok &= e6

    # ---- E7/E8/E9：只能靠"这行不许回来"的 —— 查源码 ✓ ----
    # ★v2.19 拆 god file（第三/四刀）之后✗★：`mc_mcp.py` 不再是一个人 ✗
    #   （走路 ⇒ `mcp_walk.py` ✓ 看/地图/容器 ⇒ `mcp_percept.py` ✓ 量测 ⇒ `mcp_geo.py` ✓）
    #   ⇒ 这里改成读**这一层全部**的源码 ✓ ★判据本身一个字没改✗★（E7 要的两个字串 ✓
    #     E8 要的"那行不许回来" ✓ E9 要的 `BLOCKED_LV` ＋ `pathplan.blocked_here` ✓）
    src = "\n".join((ROOT / "tools" / _f).read_text(encoding="utf-8")
                    for _f in ("mc_mcp.py", "mcp_walk.py", "mcp_percept.py", "mcp_geo.py"))
    e7 = ("为什么没到" in src) and ("为什么停" in src)
    e8 = "ok_arrive = in_cell or" not in src
    e9 = ("BLOCKED_LV" in src) and ("def blocked_here" in (ROOT / "tools" / "pathplan.py")
                                    .read_text(encoding="utf-8"))
    say("E7 (P116) '没到必须说为什么' 在源码里 => %s" % e7)
    say("E8 (P32/104) '到没到'不再只看距离（没有 `ok_arrive = in_cell or`）=> %s" % e8)
    say("E9 (P31) 障碍记忆带层（BLOCKED_LV + blocked_here）=> %s" % e9)
    ok &= bool(e7 and e8 and e9)

    # ---- E10 (P129)：★同一种格式只许**一把尺子**✗ ＋ 逐字重复必须能删掉 ✓ ----
    import tempfile                                       # noqa: E402
    import errata_archive as EA                           # noqa: E402
    asrc = (ROOT / "tools" / "errata_archive.py").read_text(encoding="utf-8")
    # ★数"读标题"的正则字面量✗★：出现两个 ⇒ 就是"两把尺子"回来了 ✗（P129 的真因 ✓）
    n_rulers = len(re.findall(r"['\"][^'\"]*### \(P", asrc))
    body_a = "### P19.1 同一条（标题**不带点** ✓）\n\n- 正文一\n- 正文二\n"
    # ★合成样本里的编号**必须挑真存在的**✗★（第一版我随手编了个不存在的子编号 ⇒
    #   反而被 `errata_index_test.py` 的 G2「不悬空」抓住 ✗ —— ★判据自己也要守判据 ✓★）
    body_b = "### P127 正文真的不一样\n\n- 甲\n"
    body_b2 = "### P127 正文真的不一样\n\n- 乙（改过了 ✗）\n"
    txt = "前言\n\n" + body_a + "\n---\n\n# 小节\n\n" + body_a + "\n" + body_b + "\n" + body_b2
    tmp = Path(tempfile.gettempdir()) / "errata_dedupe_guard.md"
    tmp.write_text(txt, encoding="utf-8")
    n_drop, dups = EA.dedupe_identical(tmp)
    after = tmp.read_text(encoding="utf-8")
    e10 = (n_rulers == 1) and (n_drop == 1) and dict(dups) == {"P19.1": 2, "P127": 2} \
        and (after.count("### P19.1") == 1) and (after.count("### P127") == 2) \
        and ("乙（改过了 ✗）" in after)
    say("E10 (P129) 标题正则字面量 %d 处（要 1 ✓）｜ 逐字重复删掉 %d 块（要 1 ✓）"
        "｜ 正文不同的重复**留着**（P127 还有 %d 份 ✓）=> %s"
        % (n_rulers, n_drop, after.count("### P127"), e10))
    ok &= e10

    # ---- E11 (P131)：★事件名只许从模组源码抄✗★ ----
    import speech as SP                                   # noqa: E402
    modsrc = (ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge"
              / "DshBridgeMod.java")
    mtext = modsrc.read_text(encoding="utf-8") if modsrc.is_file() else ""
    emits = set(re.findall(r'ev\("([a-z_]+)"', mtext))
    ours = set(SP.EVENT_KINDS) | set(SP.SKIP_EVENTS)
    extra = sorted(ours - emits)          # ★我编的（模组根本不发 ✗）★
    missed = sorted(emits - ours)         # ★模组发的（我们没做决定 ✗）★
    e11 = bool(emits) and (not extra) and (not missed)
    say("E11 (P131) 事件名对账：模组 %d 个 ｜ 我们 %d 个（触发 %d ＋ 故意不说 %d）"
        " ｜ 我编的 %s ｜ 漏掉的 %s => %s"
        % (len(emits), len(ours), len(SP.EVENT_KINDS), len(SP.SKIP_EVENTS),
           extra[:5], missed[:5], e11))
    ok &= e11

    say("---- E1..E11 = %s ----" % ok)
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
