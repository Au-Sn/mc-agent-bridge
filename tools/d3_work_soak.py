#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""d3_work_soak.py —— ★D3 第③档「干活期间」的观测器★ ✗（真连世界 ✓ 2026-10-01 夜 ✓）

WHY（§76 的第 ③ 档 ✓ 也是三档里最后一块 ✗）：
  第 ① 档＝半径 6 溜达（§73 ✓）／第 ② 档＝长走＋贴边（§78 ✓）都压不到
  ★"**一边动世界一边走**"✗★ 这一类 ✓ —— 而"放不下就拒绝 ✓ 掉落物要捡回来 ✓
  容器与背包的账要对得上 ✓"全都发生在这里 ✓

★循环（★一物两用：既动世界又走路✗★）★：
  ① 挑一个**站得住**的落脚点（`safe_spots` 5~8 格 ✓）⇒ `walk_route` 过去
  ② 在它**旁边那一格**`place` 一块方块 ⇒ 立刻 `dig` 掉它（★世界被真正改动 ✗ 但改的是我刚放的那块 ✗★）
  ③ 再 `walk_route` **踩到那一格** ⇒ 把掉落物**捡回来** ✓（★捡不回来就是**丢东西** ✗★）
  ⚠ ★为什么 place→dig 同一格✗★：**不去挖平台本身** ✗（★挖自家的地基＝自己把家拆了 ✗★）

判据（★先写死 ✗ 不许事后改 ✓★ —— 前四条与 §78 同口径 ✓ 打包无关 ✓）
  K1 ★零死亡★   ：新增 `bot_died` == 0 ✓
  K2 ★不凭空丢★ ：每次循环结束时 `items` **不低于**循环开始时 ✓
                  （★`place` 会真的把方块花掉 ✗ 所以口径是"放下去的那块**必须挖回来捡回来**✗★"）
  K3 ★不卡死★   ：每个动作都在超时内返回判定 ✓（`ERR:` == 0 ✓）
  K4 ★不掉下去/不摔★：`y` 不低 >=2 ✓ `hp` 不降 ✓ `onground` 恒 true ✓
  K5 ★真干了活★ ：`place` 成功 >= 6 ✓ 且 `dig` 成功 >= 6 ✓
  K6 ★动完还能走★：每轮都真到达过（`reached` >= 6 ✓）
  ⚠ ★拿不到"能放的方块"⇒ **测不了**（exit 4）✗★ —— 不许当成过 ✓（**P147** ✓）

用法 ✓：`py tools/d3_work_soak.py --minutes 12` ／ 自测 `--minutes 3`
账 ✓：`logs/d3_work_soak.jsonl` ＋ `logs/d3_work_soak_run.log`
"""
from __future__ import annotations

import json
import math
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

LOG = ROOT / "logs" / "d3_work_soak.jsonl"
RUN = ROOT / "logs" / "d3_work_soak_run.log"
PLACEABLE = ["minecraft:cobblestone", "minecraft:dirt", "minecraft:gravel", "minecraft:sand",
             "minecraft:stone", "minecraft:oak_planks", "minecraft:andesite", "minecraft:diorite"]


def say(s=""):
    print(s, flush=True)


def main(argv) -> int:
    mins = 12.0
    if "--minutes" in argv:
        mins = float(argv[argv.index("--minutes") + 1])
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
        p = g("pos")
        if not p:
            return None
        x, y, z = [float(v) for v in p.split(",")]
        return {"pos": p, "x": x, "y": y, "z": z, "hp": float(g("hp") or 0),
                "mode": g("mode"), "onground": (g("onground") == "true"),
                "items": int(inv.group(2)) if inv else None}

    def deaths():
        t = dsh("dshevents")
        return None if t.startswith("ERR:") else len(re.findall(r"bot_died", t))

    def cell_block(x, y, z):
        """★那一格到底是什么方块✗★ —— ★判"活干成了没有"只认这个 ✗ 不认回执 ✓★

        ★为什么必须问世界真值✗★（2026-10-01 实测 ✓ 这一档最贵的一条 ✓）：
          `t_dig_block` 在"够不着"的时候会**返回 iserr=False** ✗
          而回执里藏着一句诚实的「走到 (4111,71,21)：**没到** ✗」✗
          ⇒ ★我原来用"回执里没有 ERR/失败/拒绝 就算成功"✗★ ⇒ 把**没挖**当成了**挖了** ✓
          ⇒ 实测：那一格**还是 oak_planks** ✗（用户当场也看见了那块木板 ✓）
        """
        txt = str(M.t_scan(x, y, z, x, y, z, max_=2)[0])
        m = re.search(r"counts\[([^\]]*)\]", txt)
        if not m or not m.group(1).strip():
            return "air" if "air=1" in txt else "?"
        first = m.group(1).split(",")[0]
        return first.rsplit(":", 1)[0] if ":" in first else first

    def pick_item():
        """★背包里挑一个**能放**的方块✗★（★挑不到 ⇒ 测不了 ✗★）"""
        txt = str(M.t_bot_inventory())
        for it in PLACEABLE:
            short = it.split(":")[1]
            if re.search(r"\b%s\b" % re.escape(short), txt) or it in txt:
                return it, short
        return None, None

    d0 = digest()
    if not d0 or d0["mode"] != "survival":
        say("★前置不满足（读不到真值／不是 survival）⇒ 不跑 ✓")
        return 4
    idd = M.t_idle(False)
    say("  前置：idle off ⇒ %s" % str(idd)[:60].replace("\n", " "))
    b0 = deaths()
    if b0 is None:
        say("★读不到事件流 ⇒ 不跑 ✓")
        return 4
    item, short = pick_item()
    say("== D3 干活档：%.0f 分钟 ｜ 起点 %s ｜ items=%s ｜ 可放方块=%s =="
        % (mins, d0["pos"], d0["items"], item))
    if not item:
        say("★背包里没有可放的方块 ⇒ **测不了**（exit 4 ✗ 不许算过 ✓ P147 ✓）")
        return 4

    y_floor, hp0 = math.floor(d0["y"]), d0["hp"]
    fails, fails_soft, rec = [], [], []
    reached = placed = dug = err_n = cycles = 0
    cells = set()

    while time.time() < t_end:
        cur = digest()
        if not cur:
            err_n += 1
            fails.append("采样读不到真值（桥超时 ✗）")
            time.sleep(3)
            continue
        if cur["y"] <= y_floor - 2 or cur["hp"] < hp0 - 0.01 or not cur["onground"]:
            fails.append("★身体出事✗★：y=%.2f hp=%.1f onground=%s（pos=%s）"
                         % (cur["y"], cur["hp"], cur["onground"], cur["pos"]))
            break
        if cur["mode"] != "survival":
            fails.append("★模式变了✗★ %s" % cur["mode"])
            break
        # ① 挑落脚点 ⇒ 走过去
        rows = [(int(a), int(b), int(c)) for (a, b, c) in
                re.findall(r"\((-?\d+),(-?\d+),(-?\d+)\)\s*距离约", str(M.t_safe_spots(5, 8, 8)))]
        if not rows:
            fails.append("这一带挑不出 5~8 格的落脚点 ⇒ 测不了 ✓")
            return 4
        tx, ty, tz = rows[cycles % len(rows)]
        t0 = time.time()
        out, _e = M.t_walk_route(tx, ty, tz)
        txt = str(out)
        if re.search(r"ERR:|★异常★", txt):
            err_n += 1
            fails.append("walk_route 没返回判定 ✗")
        if "reached" in txt or "已到达" in txt or "到位" in txt:
            reached += 1
        # ② ★放在**头顶那一格**✗★（★自测实测：放在旁格 ⇒ `dig` 要"站到它旁边" ✗
        #   而模组的"到了"是**离目标点 ≤1 格** ✗ ⇒ 停在隔壁格子 + 偏 0.75 格 ⇒ **够不着** ✗
        #   ⇒ 挖了个寂寞 ✗★）。头顶那一格：站上去就够得着 ✓ 掉落物**掉在自己脚下** ⇒ 自动捡 ✓
        px, py, pz = tx + 1, ty, tz          # ★同层邻格✗★（★头顶那一格放不进去✗★：自测 3/3 无效 ✓）
        items_before = cur["items"]
        # ★★动手前先"贴脸"✗★★（2026-10-01 实测的真根因 ✓）：
        #   模组的"到了"是按**离目标点 ≤1 格**判的 ✗ 而 dig 需要**真的站在相邻那一格** ✗
        #   （实测：停在隔壁格子、偏 0.75 格 ⇒ **够不着** ⇒ 回执 `iserr=False` 而世界没变 ✗）
        M.t_walk_to(tx, ty, tz, exact=True)
        before_blk = cell_block(px, py, pz)
        pout = str(M.t_place_block(px, py, pz, item))
        mid_blk = cell_block(px, py, pz)
        w_placed = (before_blk == "air" and mid_blk not in ("air", "?"))
        if w_placed:
            dout = str(M.t_dig_block(px, py, pz))
            time.sleep(1.0)
            after_blk = cell_block(px, py, pz)
            if after_blk != "air":
                dout += " || ★第二次✗★：" + str(M.t_dig_block(px, py, pz))
                time.sleep(1.0)
                after_blk = cell_block(px, py, pz)
            w_dug = (after_blk == "air")
            if w_dug:
                # ★挖掉了 ⇒ 掉落物在**那一格**上 ✗ 得走过去捡 ✓（★不走过去就是真丢✗★）
                M.t_walk_to(px, py, pz, exact=True)
            if not w_dug:
                fails_soft.append("★挖了但世界没变✗★：(%d,%d,%d) 现在还是 %s（回执说 iserr=False ✗）"
                                  % (px, py, pz, after_blk))
        else:
            dout, w_dug = "★没放下去 ⇒ **不挖**✗★（不许挖原有的方块 ✓）", False
            fails_soft.append("★place 没让世界变✗★：(%d,%d,%d) 前=%s 后=%s" % (px, py, pz, before_blk, mid_blk))
        placed += 1 if w_placed else 0
        dug += 1 if w_dug else 0
        if re.search(r"ERR:|★异常★", pout + dout):
            err_n += 1
            fails.append("place/dig 没返回判定 ✗")
        # ③ ★不用再走了✗★：方块放在**头顶** ⇒ 掉落物**掉在自己脚下** ✓ 自动捡 ✓
        time.sleep(1.0)
        after = digest()
        # ★★捡东西有延迟✗★★（2026-10-01 自测实测 ✓）：3 分钟自测里 #01 报 78⇒77 ✗
        #   而 #02~#05 都净 0 ✓ ⇒ 真相是★"我采样太早"✗★（掉落物要一两 tick 才进背包 ✗）
        #   ⇒ 口径改成：★在**最多 6 次 × 1.5 秒**的窗口里等它回到原位✗★ ✓
        #     （★等不回来 ⇒ 才是真丢 ✗★ —— 不许拿"采样早"当借口 ✗）
        waited = 0.0
        while (after is not None and items_before is not None
               and after["items"] is not None and after["items"] < items_before
               and waited < 9.0):
            time.sleep(1.5)
            waited += 1.5
            again = digest()
            if again:
                after = again
        if after:
            cells.add((int(round(after["x"])), int(round(after["z"]))))
            if items_before is not None and after["items"] is not None \
                    and after["items"] < items_before:
                fails.append("★凭空丢了东西✗★：%s ⇒ %s（等了 %.1f 秒仍没捡回来 ✓）"
                             % (items_before, after["items"], waited))
        cycles += 1
        r = {"i": cycles, "t": time.strftime("%H:%M:%S"), "cell": [tx, ty, tz],
             "place_world": w_placed, "dig_world": w_dug, "before": before_blk,
             "mid": mid_blk, "sec": round(time.time() - t0, 1),
             "items_before": items_before, "items_after": after["items"] if after else None,
             "y": after["y"] if after else None, "hp": after["hp"] if after else None,
             "place_tail": pout.replace("\n", " ｜ ")[-120:],
             "dig_tail": dout.replace("\n", " ｜ ")[-140:]}
        rec.append(r)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        say("  #%02d cell=(%d,%d) 世界:放=%s 挖=%s %.1fs items %s⇒%s y=%s hp=%s"
            % (cycles, tx, tz, w_placed, w_dug, r["sec"], items_before, r["items_after"], r["y"], r["hp"]))

    nd = (deaths() or 0) - b0
    ck = {
        "K1 零死亡": nd == 0,
        "K2 不凭空丢": not any("凭空丢" in x for x in fails),
        "K3 不卡死": err_n == 0,
        "K4 不掉下去/不摔": not any("身体出事" in x for x in fails),
        "K5 真干了活": placed >= 6 and dug >= 6,
        "K6 动完还能走": reached >= 6,
    }
    lines = ["", "== D3 干活档 判定 ==",
             "  时长 %.1f 分钟 ｜ 循环 %d ｜ place 成功 %d ／ dig 成功 %d ／ 到达 %d ／ 不同格 %d ／ ERR %d"
             % (mins, cycles, placed, dug, reached, len(cells), err_n),
             "  起点 hp %.1f items %s ⇒ 末尾 %s ｜ 新增 bot_died %d ｜ 方块=%s"
             % (hp0, d0["items"], (rec[-1]["items_after"] if rec else "?"), nd, short),
             "  ★「世界真的变了」才算干活✗★：place 真生效 %d ／ dig 真生效 %d"
             % (placed, dug)]
    for x in fails_soft[:4]:
        lines.append("  ⚠ 记一笔（★不是安全红 ✗ 是**调不动世界**✗★）：%s" % x)
    for k, v in ck.items():
        lines.append("  %-16s => %s" % (k, v))
    lines.append("  => %s" % ("D3-干活档 PASS ✓" if all(ck.values()) else "★FAIL✗★"))
    for x in fails[:8]:
        lines.append("  ★为什么红✗★：%s" % x)
    say("\n".join(lines))
    RUN.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if all(ck.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
