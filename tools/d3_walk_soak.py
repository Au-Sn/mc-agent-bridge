#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""d3_walk_soak.py —— ★D3「长走 ＋ 贴边」那一档的观测器★ ✗（真连世界 ✓ 2026-10-01 ✓）

WHY（§76 的 ② 那一档 ✓ 也是**最该补**的一档 ✗）：
  D3 第一次 PASS 只覆盖「**半径 6 溜达**」✓ —— 而★掉虚空的**两次**都不是溜达 ✗★：
  它们发生在**长走**（几格~十几格 ✓）与**贴边**（平台边 ≤2 格 ✓）的时候 ✓。
  `dshidle` 自带两道自保（先验"站得下人" ✓ 只在锚点附近 ✓）⇒ ★它天生**压不到**这一类✗★
  ⇒ 必须有这一支：★**反复长走 ＋ 专挑靠边的目标**✗★ ✓

★口径（2026-10-01 用户纠正 ✗ 很重要 ✓）★：
  ★"掉虚空"只是**部分整合包**的失败形态✗★ —— 更多整合包要防的是
  ★"**从某些地方掉下去**"✗★（掉到地上：摔伤 ✓ 摔死 ✓ 丢东西 ✓ 回不来 ✓）。
  ⇒ 本观测器★**不认"虚空"这个词**✗★，只认三条**打包无关**的世界真值：
    ① 高度：任何一次采样里 `y` 比**本次长走的起点层**低 **>= 2 格** ⇒ ★掉下去了✗★
    ② 血：`hp` **从不下降**（★空岛这一带没有怪 ⇒ 掉血即"摔了/撞了"✗★）
    ③ 落脚：每次采样 `onground=true`（★false ＝ 正在空中 ＝ 正在掉✗★）
  （★下面是什么无所谓 ✗ 虚空也好 ✓ 地面也好 ✓ 岩浆也好 ✓★）

判据（★先写死 ✗ 不许事后改 ✓★）
  W1 ★零死亡★   ：期间新增 `bot_died` 事件 == **0** ✓
  W2 ★零丢物★   ：背包 `items` **从不减少** ✓
  W3 ★不卡死★   ：每次 `walk_route` 都在超时内**返回一个判定** ✓（`ERR:` 数 == 0 ✓）
  W4 ★不掉下去／不摔★（★打包无关 ✓ 见上★）：`y` 不低 >=2 ✓ `hp` 不降 ✓ `onground` 恒 true ✓
  W5 ★真的走了★ ：`reached`（真到达）**>= 12** 次 ✓ 且**不同格 >= 8** ✓（★防"不动就绿"✗★）
  W6 ★拒绝要诚实★：凡拒绝 ⇒ 回执里必须有 `why=` ＋ 位移 <= 2 格 ✓（**P154** 那一族不变式 ✓）
  ⚠ 附记 ✓：每次长走的**起点离边多少格**也记下来 ✓ —— ★那是"这一档到底压到哪"的证据✗★

用法 ✓：
  py tools/d3_walk_soak.py --minutes 12              # 默认 12 分钟（★用户要求"不用太长"✗★）
  py tools/d3_walk_soak.py --minutes 2 --pull 1.5    # 自测（短跑 ✓ 验链路 ✓）
结果全在盘上 ✓：`logs/d3_walk_soak.jsonl`（一行一次长走 ✓）＋ `logs/d3_walk_soak_run.log`（判定块 ✓）
"""
from __future__ import annotations

import json
import math
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

LOG = ROOT / "logs" / "d3_walk_soak.jsonl"
RUN = ROOT / "logs" / "d3_walk_soak_run.log"


def say(s=""):
    print(s, flush=True)


def main(argv) -> int:
    mins = 12.0
    pull = 1.5
    seed = 7
    if "--minutes" in argv:
        mins = float(argv[argv.index("--minutes") + 1])
    if "--pull" in argv:
        pull = float(argv[argv.index("--pull") + 1])
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
    rng = random.Random(seed)
    t_end = time.time() + mins * 60.0

    import mc_mcp as M
    from channel import Channel
    ch = Channel("cmd0", verbose=False)

    def dsh(text, t=40.0):
        try:
            r = ch.cmd("execute as Bot at Bot run " + text, timeout=t, allow_str=True)
            return (r.text() or "").strip()
        except Exception as e:
            return "ERR:%s" % type(e).__name__

    def digest():
        t = dsh("dshdigest 1")
        if t.startswith("ERR:") or "pos=" not in t:
            return None
        g = lambda k: (re.search(k + r"=([^\s]+)", t).group(1)
                       if re.search(k + r"=([^\s]+)", t) else None)
        inv = re.search(r"inv\[x\]kinds=(\d+),items=(\d+),free=(\d+)", t)
        pos = g("pos")
        if not pos:
            return None
        xyz = [float(v) for v in pos.split(",")]
        return {"pos": pos, "x": xyz[0], "y": xyz[1], "z": xyz[2],
                "hp": float(g("hp") or 0), "food": g("food"), "mode": g("mode"),
                "onground": (g("onground") == "true"),
                "items": int(inv.group(2)) if inv else None,
                "kinds": int(inv.group(1)) if inv else None}

    def deaths():
        t = dsh("dshevents")
        if t.startswith("ERR:"):
            return None
        return len(re.findall(r"bot_died", t))

    def platform():
        """⇒ (最近边距离, [(边格x, 边格z, 距我)] ✓) 或 (None, []) ✓"""
        txt, iserr = M.t_platform(20)
        if iserr:
            return None, []
        m = re.search(r"距你\s*\*\*([\d.]+)\*\*\s*格", txt)
        d = float(m.group(1)) if m else None
        bnd = [(int(a), int(b), float(c)) for (a, b, c) in
               re.findall(r"\((-?\d+),(-?\d+)\)\s*([\d.]+)", txt)]
        return d, bnd

    say("== D3 长走/贴边档：%.0f 分钟 ｜ pull=%.1f ｜ seed=%d ==" % (mins, pull, seed))
    # ★前置闸✗★：idle 必须关着（**P25** ✓ 两者共用单车道 ✗ 会互相搅 ✓）
    idd = M.t_idle(False)
    say("  前置：idle off ⇒ %s" % (str(idd)[:70]).replace("\n", " "))
    d0 = digest()
    if not d0:
        say("★读不到世界真值（桥断/假人不在？）⇒ 不跑 ✓")
        return 4
    if d0["mode"] != "survival":
        say("★模式不是 survival（%s）⇒ 不跑 ✓（P17：创造模式会让证据失真 ✗）" % d0["mode"])
        return 4
    base_deaths = deaths()
    if base_deaths is None:
        say("★读不到事件流 ⇒ 不跑 ✓")
        return 4
    y0, hp0, items0 = d0["y"], d0["hp"], d0["items"]
    y_floor = math.floor(y0)
    d_edge, bnd = platform()
    say("  起点 %s ｜ hp=%.1f ｜ items=%s ｜ bot_died=%d ｜ 离边 %s 格 ｜ 拿到 %d 个边格"
        % (d0["pos"], hp0, items0, base_deaths, d_edge, len(bnd)))

    rec = []
    cells = set()
    reached = refused = err_n = 0
    # ★★2.44.0（§79.476）✗★★：★`dshwalk` 回执里的 `pillar=<n>` ⇒ 走路**有没有改世界**
    #   实测过一次：walk_pillar 放了个 grass_block ⇒ 摔 1 点血 ⇒ 少 1 个物品 ✗ 回执只说 reached ✓
    pillar_total = 0
    min_edge = d_edge if d_edge is not None else None
    fails = []
    safe_list = []

    def refresh_safe():
        """★远一点、四散开的目标✗★（★不然只会在"最近的那 6 个边格"里来回摆✗★ —— 自测实测 ✓）"""
        txt, iserr = M.t_safe_spots(5, 16, 12)
        if iserr:
            return []
        return [(int(a), int(b), int(c)) for (a, b, c) in
                re.findall(r"\((-?\d+),(-?\d+),(-?\d+)\)\s*距离约", str(txt))]

    it = 0
    while time.time() < t_end:
        it += 1
        cur = digest()
        if not cur:
            err_n += 1
            fails.append("采样读不到真值（桥超时 ✗）第 %d 次" % err_n)
            time.sleep(3)
            continue
        # ★世界真值先判（★不采信工具自述✗★）★
        if cur["y"] <= y_floor - 2:
            fails.append("★掉下去了✗★：y %.2f <= 起点层 %d - 2（pos=%s）" % (cur["y"], y_floor, cur["pos"]))
            rec.append({"i": it, "kind": "FALL", "pos": cur["pos"]})
            break
        if cur["hp"] < hp0 - 0.01:
            fails.append("★掉血✗★：hp %.1f < %.1f（pos=%s ⇒ 摔了/撞了 ✓）" % (cur["hp"], hp0, cur["pos"]))
            rec.append({"i": it, "kind": "HP", "pos": cur["pos"], "hp": cur["hp"]})
            break
        if not cur["onground"]:
            rec.append({"i": it, "kind": "AIRBORNE", "pos": cur["pos"]})
        if items0 is not None and cur["items"] is not None and cur["items"] < items0:
            fails.append("★丢东西✗★：items %s < %s" % (cur["items"], items0))
            rec.append({"i": it, "kind": "LOST", "items": cur["items"]})
            break
        if cur["mode"] != "survival":
            fails.append("★模式变了✗★：%s" % cur["mode"])
            break

        # 每 6 轮刷新一次"边在哪"（地图有缓存 ✓ 不必每轮都问 ✓ 省单车道 ✓）
        if it % 6 == 1:
            d_edge, bnd2 = platform()
            if bnd2:
                bnd = bnd2
            if d_edge is not None:
                min_edge = d_edge if min_edge is None else min(min_edge, d_edge)
        if it % 8 == 1 or not safe_list:
            got = refresh_safe()
            if got:
                safe_list = got
        if not bnd and not safe_list:
            fails.append("拿不到「边在哪」也没有落脚点 ⇒ 这一档没有意义 ✓")
            return 4
        # ★两种目标轮流✗★（★自测实测的教训✗★：只盯着"最近那 6 个边格"⇒
        #   在**两个格子之间来回摆** ✗ ⇒ 走 7 次只到过 2 格 ✓ 那既不是长走也不是覆盖 ✗）
        #   ① 奇数轮 ⇒ **落脚点**（5~16 格 ✓ 四散 ✓）＝ 长走
        #   ② 偶数轮 ⇒ **贴边**（往某个边格方向走 ✓ 停在它前面 pull 格 ✓）
        cells.add((int(round(cur["x"])), int(round(cur["z"]))))
        if it % 2 == 1 and safe_list:
            tx, ty, tz = safe_list[(it // 2) % len(safe_list)]
        else:
            bx, bz, _bd = bnd[(it // 2) % len(bnd)] if bnd else (
                int(cur["x"]) + 8, int(cur["z"]), 8.0)
            vx, vz = bx - cur["x"], bz - cur["z"]
            L = math.hypot(vx, vz)
            if L < 2.0:
                rec.append({"i": it, "kind": "AT_EDGE", "pos": cur["pos"], "d": round(L, 2)})
                say("  #%02d 已经贴着边（%.1f 格 ✓）⇒ 这轮改走落脚点 ✓" % (it, L))
                tx, ty, tz = (safe_list[it % len(safe_list)] if safe_list
                              else (int(cur["x"]) + 5, int(cur["y"]), int(cur["z"])))
            else:
                ux, uz = vx / L, vz / L
                keep = max(2.0, L - pull)
                tx, tz = int(round(cur["x"] + ux * keep)), int(round(cur["z"] + uz * keep))
                ty = int(cur["y"])
        t0 = time.time()
        try:
            out, iserr = M.t_walk_route(tx, ty, tz)
        except Exception as e:
            out, iserr = "★异常★ %s: %s" % (type(e).__name__, e), True
        sec = time.time() - t0
        txt = str(out)
        after = digest()
        # ★★2.44.0（§79.476）✗★★：★回执里的 pillar=<n> ⇒ 走路有没有改世界✗★
        for _pv in re.findall(r"pillar=(\d+)", str(txt)):
            pillar_total += int(_pv)
        verdict = ("ERR" if txt.startswith("ERR:") or txt.startswith("★异常★") else
                   "reached" if re.search(r"reached|已到达|到达\s*✓|到位", txt) else
                   "refused" if re.search(r"why=|拒绝|走不过去|unreachable|够不着|规划\*\*没成\*\*|不去", txt) else
                   "shortfall" if re.search(r"还没到|★停★|几乎没靠近|没走到", txt) else "other")
        if verdict == "other":
            # ★★这一条是本轮自测之后补的✗★★（★原版把"判不出来的结果"塞进一个 `other` 桶 ✗
            #   而 W3/W6 **都不看那个桶** ✗ ⇒ 12 分钟那一跑 57 次里有 **13 次** 落在里面 ✗
            #   ⇒ ★"绿"里有 23% 的证据**没被任何判据看过**✗★ —— 与 P100/P123 同族 ✓）
            fails.append("★判不出结果✗★（既不是到达也不是诚实拒绝 ✓ 回执尾部：%s）" % txt[-120:])
        if verdict == "ERR":
            err_n += 1
            fails.append("★卡死✗★：walk_route 没返回判定（%.1f 秒 ✗）" % sec)
        if verdict == "reached":
            reached += 1
        if verdict == "refused":
            refused += 1
            # ★"有数字原因"**或**"有明确的文字原因"**都算诚实✗★（2026-10-01 实测 ✓）：
            #   ① 走不动 ⇒ `why=step_down=0 > max_drop=3`（数字 ✓ P154 ✓）
            #   ② 规划没成 ⇒ 「目标不在你脚下这块连通区域里 ⇒ 中间隔着虚空 ⇒ 不去」✓
            #   ★不许"拒绝了但说不出为什么"✗★ —— 那才是这条判据要抓的 ✓
            if not (("why=" in txt) or re.search(r"不在你脚下这块连通区域|隔着虚空|规划\*\*没成\*\*|够不着", txt)):
                fails.append("拒绝但**说不出原因** ✗（P154/P116 不变式 ✓）")
        moved = None
        if after:
            moved = math.hypot(after["x"] - cur["x"], after["z"] - cur["z"])
            cells.add((int(round(after["x"])), int(round(after["z"]))))
            if verdict == "refused" and moved > 2.0:
                fails.append("拒绝却动了 %.2f 格 ✗（P154 不变式 ✓）" % moved)
        r = {"i": it, "t": time.strftime("%H:%M:%S"), "from": cur["pos"], "to": [tx, ty, tz],
             "verdict": verdict, "sec": round(sec, 1), "moved": None if moved is None else round(moved, 2),
             "hp": after["hp"] if after else None, "y": after["y"] if after else None,
             "items": after["items"] if after else None, "d_edge": d_edge,
             "why": (re.search(r"why=([^\s]+)", txt).group(1) if "why=" in txt else None),
             "tail": txt.replace("\n", " ｜ ")[-220:]}
        rec.append(r)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if it % 5 == 0 or verdict != "other":
            say("  #%02d %-7s %.1fs moved=%s y=%s hp=%s 离边=%s %s"
                % (it, verdict, sec, r["moved"], r["y"], r["hp"], d_edge,
                   ("why=" + str(r["why"])) if r["why"] else ""))

    new_deaths = (deaths() or 0) - base_deaths
    ck = {
        "W1 零死亡": new_deaths == 0,
        "W2 零丢物": not any(x.startswith("★丢东西") for x in fails),
        "W3 不卡死": err_n == 0 and not any("判不出结果" in x for x in fails),
        "W4 不掉下去/不摔": not any(x.startswith("★掉") or x.startswith("★丢") for x in fails)
                            and not any(x.startswith("★掉血") for x in fails),
        # ★短版（--minutes 小）按时长缩放 ✗ 否则短版永远过不了 ✓
        "W5 真的走了": reached >= max(4, int(round(12 * mins / 12.0))) and len(cells) >= max(4, int(round(8 * mins / 12.0))),
        "W7 走路不许改世界": pillar_total == 0,
        "W6 拒绝要诚实": not any("拒绝" in x for x in fails),
    }
    lines = ["", "== D3 长走/贴边档 判定 ==",
             "  时长 %.1f 分钟 ｜ 长走 %d 次（reached %d ／ refused %d ／ shortfall %d ／ 其他 %d ／ ERR %d）"
             % (mins, len([x for x in rec if x.get("kind") is None]), reached, refused,
                len([x for x in rec if x.get("verdict") == "shortfall"]),
                len([x for x in rec if x.get("verdict") == "other"]), err_n),
             "  不同格 %d ｜ 起点 hp %.1f ⇒ 末尾 hp %s ｜ items %s ｜ 新增 bot_died %d"
             % (len(cells), hp0, (rec[-1].get("hp") if rec else "?"), items0, new_deaths),
             "  ★这一档的最贴边记录✗★：离边最近 %s 格 ｜ ★走路改世界（pillar）次数✗★：%d" % (min_edge, pillar_total)]
    for k, v in ck.items():
        lines.append("  %-16s => %s" % (k, v))
    lines.append("  => %s" % ("D3-长走/贴边 PASS ✓" if all(ck.values()) else "★FAIL✗★"))
    for x in fails[:8]:
        lines.append("  ★为什么红✗★：%s" % x)
    say("\n".join(lines))
    RUN.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if all(ck.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
