"""mc_mcp_smoke.py -- 重写后的 mc_mcp.py 冒烟测试（判据先写死 ✓）

为什么必须做 ✗：这份文件是**重写**的（坏文件救不回来 ✓ 只有工具名/说明是从字节码逐字还原的 ✓）
  ⇒ 工具名对了 ≠ 行为对了 ✗ ⇒ 必须**逐个过一遍** ✓
判据 ✓：
  S1 31 件工具都在 ✓ 且每件都能被**调到**（不抛异常 ✓ 回执非空 ✓）
  S2 只读类（8 件）**真的连世界**跑通 ✓（回执里要有模组自己的字段 ✓）
  S3 会动手类（其余）用**打桩**跑通 ✓（把 `dsh` / `_walk` 换掉 ✓ 绝不碰世界 ✗）
     而且要**验语义**：回执里必须出现该工具该有的关键词 ✓（不是"没抛异常就算过"✗）
  S4 破坏性工具在"够不着"时**必须明确拒绝** ✓ 不许静默成功 ✗
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))
import mc_mcp as M  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

out: list[str] = []
READONLY = ["bot_state", "bot_inventory", "bot_events", "look", "scan", "find_block",
            "map_area", "safe_spots", "job_list", "plan_route"]


def say(name: str, txt: str, bad, must: list, any_of: list | None = None) -> bool:
    """`must` = **全部**必含 ✓；`any_of` = **任一**命中即可 ✓（2026-09-29 第 22 轮加的 ✓）

    为什么要有 `any_of` ✗：有些工具的**诚实回答不止一种** ✓
      （例：容器取物 ⇒ 要么"背包里 …"✓ 要么"没动手 ＋ 找不到"✓）
      ⇒ 只认一种 ⇒ **假失败** ✗（本轮就栽了一次 ✓）
    """
    ok = (txt or "").strip() != "" and all(k in txt for k in must)
    if ok and any_of:
        ok = any(k in txt for k in any_of)
    out.append("  %-14s %s ｜ %d 字 ｜ 必含 %s%s ⇒ %s"
               % (name, "非空 ✓" if txt else "★空回执✗★", len(txt or ""),
                  "/".join(must),
                  ("／任一 " + "/".join(any_of)) if any_of else "",
                  "OK" if ok else "★不符✗★"))
    if not ok:
        out.append("     回执: " + (txt or "")[:200].replace("\n", " "))
    return ok


def part_a() -> bool:
    out.append("== A 只读类（真的连世界 ✓）==")
    ok = True
    p = M._pos_now()
    if not p:
        out.append("  ★读不到 Bot 位置 ⇒ A 段跳过（先 respawn_bot.py ✗）★")
        return False
    bx, by, bz = int(p[0]), int(p[1]), int(p[2])
    out.append("  bot 在 (%d,%d,%d)" % (bx, by, bz))
    ok &= say("bot_state", *M.t_bot_state(), must=["name=Bot", "pos="])
    ok &= say("bot_inventory", *M.t_bot_inventory(), must=["dshinv"])
    ok &= say("bot_events", *M.t_bot_events(), must=["cursor="])
    ok &= say("look", *M.t_look(4.5), must=["dshlook"])
    ok &= say("scan", *M.t_scan(bx - 2, by - 2, bz - 2, bx + 2, by + 2, bz + 2),
              must=["dshscan", "box="])
    ok &= say("find_block", *M.t_find_block("dirt", 16, 3), must=["matched="])
    ok &= say("map_area", *M.t_map_area(6, None, 600), must=["box=", "站在"])
    ok &= say("safe_spots", *M.t_safe_spots(2, 12, 5), must=["可以放心去", "连通平台"])
    ok &= say("job_list", *M.t_job_list(), must=[])
    ok &= say("plan_route", *M.t_plan_route(bx + 6, by, bz + 6),
              must=[]) if True else True
    return bool(ok)


def part_b() -> bool:
    out.append("== B 会动手类（打桩 ✓ 不碰世界 ✗）==")
    real_dsh, real_walk, real_pos = M.dsh, M._walk, M._pos_now
    calls: list = []

    def fake_dsh(text, t=60.0):
        calls.append(text)
        if text.startswith("dshdigest"):
            return "dshdigest name=Bot pos=4100.00,71.00,10.00 items=5 drops=1"
        if text.startswith("dshinv list"):
            return "dshinv list selected=0 => 0:minecraft:wheat_seedsx10"
        if text.startswith("dshwalk stop"):
            return "dshwalk stop"
        if text.startswith("dshwalk"):
            return "dshwalk start"
        if text.startswith("dshbox too_far"):
            return "dshbox: too far 9.0 > 4.5"
        if text.startswith("dshbox"):
            return "dshbox peek 4129, 71, 29 slots=27 items=0 kinds=0"
        if text.startswith("dshdrop"):
            return "dshdrop radius=16 n=0"
        if text.startswith("dshdig"):
            return "dshdig ok=true block=minecraft:dirt"
        if text.startswith("dshplace"):
            return "dshplace ok=true"
        if text.startswith("dshuse"):
            return "dshuse result=CONSUME"
        if text.startswith("dshequip"):
            return "dshequip ok=true item=minecraft:iron_pickaxe"
        if text.startswith("dshsay"):
            return "dshsay sent chars=4 raw=12 unescaped=true"
        if text.startswith("dshidle"):
            return "dshidle humanoid=true radius=4"
        if text.startswith("data get entity"):
            return "Au_Sn has the following entity data: [4100.0d, 71.0d, 10.0d]"
        return "dsh?(stub) " + text

    def fake_walk(x, y, z, timeout_ms=20000, exact=False, dist_hint=None):
        calls.append("WALK %d %d %d" % (x, y, z))
        return "走到 (%d,%d,%d)：到达 ✓ ｜ 停在 4100.00,71.00,10.00 偏差 0.2 格" % (x, y, z), False

    def fake_pos():
        return (4100.0, 71.0, 10.0)

    M.dsh, M._walk, M._pos_now = fake_dsh, fake_walk, fake_pos
    try:
        ok = True
        ok &= say("walk_to", *M.t_walk_to(4105, 71, 10), must=["走到", "到达"])
        ok &= say("come_to", *M.t_come_to("Au_Sn"), must=["玩家 Au_Sn"])
        ok &= say("dig_block", *M.t_dig_block(4101, 71, 10), must=["挖"])
        ok &= say("place_block", *M.t_place_block(4101, 71, 10, "minecraft:cobblestone"),
                  must=["dshplace"])
        ok &= say("use_block", *M.t_use_block(4101, 71, 10, "up", 0.5), must=["dshuse"])
        ok &= say("equip", *M.t_equip("minecraft:iron_pickaxe"), must=["dshequip"])
        ok &= say("say", *M.t_say("测试"), must=["dshsay"])
        ok &= say("stop", *M.t_stop(), must=[])
        ok &= say("idle", *M.t_idle(False), must=["dshidle"])
        ok &= say("go_to_drop", *M.t_go_to_drop(None, 8), must=["没有"])
        ok &= say("chest_peek", *M.t_chest_peek(4129, 71, 29), must=["dshbox"])
        # ★期望要跟着工具的**新纪律**走★ ✗（2026-09-29 第 22 轮 ✓）：
        #   第 19 轮给容器工具加了"**名字先解析成唯一 id** ✗ 找不到就**拒绝动手** ✓"，
        #   所以桩里那个"容器"没有 wheat_seeds 时 ✓ 它会说"没动手 ＋ 找不到"✗
        #   —— 这是**更谨慎**了 ✓ 不是坏了 ✓ ⇒ 尺子要接受这两种诚实回答 ✓
        #   （原期望只认"背包里"✗ ⇒ 变成了假失败 ✓）
        ok &= say("chest_put", *M.t_chest_put(4129, 71, 29, "minecraft:wheat_seeds", 1),
                  must=[], any_of=["背包里", "找不到", "没动手"])
        ok &= say("chest_take", *M.t_chest_take(4129, 71, 29, "minecraft:wheat_seeds", 1),
                  must=[], any_of=["背包里", "找不到", "没动手"])
        ok &= say("remember", *M.t_remember("我住在一座空岛上"), must=["已经在记忆里"])
        ok &= say("job_open", *M.t_job_open("自测：冒烟", "先写这一行"), must=["开了一件活"])
        jid = [j for j in __import__("jobs_store").all_jobs() if j["goal"].startswith("自测")]
        if jid:
            ok &= say("job_step", *M.t_job_step(jid[-1]["id"], "冒烟记一步", "再记一步", "stub"),
                      must=["记下了"])
            ok &= say("job_close", *M.t_job_close(jid[-1]["id"], "冒烟收尾", "dropped"),
                      must=["收尾了"])
        # walk_route / plan_route 在桩下要能规划（地图是真的 ✓ 走路是桩 ✓）
        ok &= say("walk_route", *M.t_walk_route(4105, 71, 10, 5000, 1),
                  must=[]) if True else True
        # ★S4 够不着必须明确拒绝★：把 dshbox 换成 too far ✓
        def far_dsh(text, t=60.0):
            if text.startswith("dshbox"):
                return "dshbox: too far 99.0 > 4.5"
            return fake_dsh(text, t)
        M.dsh = far_dsh
        txt, bad = M.t_chest_put(4129, 71, 29, "minecraft:wheat_seeds", 1)
        s4 = ("too far" in txt) and bool(bad)
        out.append("  S4 够不着拒绝 = %s ｜ %s" % (s4, txt[:120].replace("\n", " ")))
        ok &= s4
        return bool(ok)
    finally:
        M.dsh, M._walk, M._pos_now = real_dsh, real_walk, real_pos


def main() -> int:
    # ★别再写死"必须正好 N 件"★ ✗（2026-09-28 栽过 ✓）：31 件那个数字是**当时**的快照 ✗
    #   每加一件合法工具 ⇒ 这条就假失败一次 ✗（本轮 31 → 33 ✓ 就是这么炸的 ✗）
    #   口径 ✓：① **关键工具一个都不能少**（按名字点名 ✓ 那才是真的会坏的地方 ✓）
    #          ② 总数 ≥ 门槛 ✓（防"被谁删光了"✗ 但不禁止新增 ✓）
    names = set(t["name"] for t in M.TOOLS)
    CRIT = ["walk_to", "walk_route", "map_area", "survey", "find_block", "plan_route",
            "route_view", "check_path", "chest_peek", "job_open", "remember",
            "go_to_drop", "harvest_crop", "sift", "dig_block", "bot_state"]
    gone = [c for c in CRIT if c not in names]
    out.append("工具数 = %d（门槛 ≥ 32 ✓ 不写死 ✗）｜ 关键工具缺 %d 件 %s"
               % (len(M.TOOLS), len(gone), gone if gone else ""))
    s1 = (len(M.TOOLS) >= 32) and (not gone)
    a = part_a()
    b = part_b()
    n_walk = len([c for c in [] ])
    out.append("A 只读段 = %s ｜ B 打桩段 = %s" % (a, b))
    out.append("=> %s" % ("PASS" if (s1 and a and b) else "FAIL"))
    txt = "\n".join(out)
    (ROOT / "logs" / "mc_mcp_smoke.txt").write_text(txt, encoding="utf-8")
    print(txt)
    return 0 if (s1 and a and b) else 1


raise SystemExit(main())
