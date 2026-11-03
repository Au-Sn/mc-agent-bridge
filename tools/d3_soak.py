#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""d3_soak.py —— ★D3「身体不出事」长跑观测★ ✗（离线设计 ✓ 真连世界 ✓ 2026-10-01 ✓）

WHY（为什么 D3 是**唯一一条会让前面全部作废**的判据 ✗）：
  这个项目的交付物是「**能换脑的在场层**」✓ —— 而★"一个会掉进虚空、把一整包家当弄丢的身体，
  接到再好的脑上也不是伙伴"✗★（见 `docs/接口契约-伙伴v1.0.md` §9 ✓）。
  ⇒ D3 要求的不是"它会做什么" ✗ 而是 ★"**连续 3 小时不掉虚空／不丢物品／不卡死**"✗★ ✓

★为什么不只是"挂机看着"✗★：站着不动**什么也证明不了** ✓
  ⇒ 口径 ✓：用项目自己的 **`/dshidle on radius 4`**（拟人化：半径 4 内小步溜达 ✓）
    ★逼它**真的反复走路**✗★ —— 掉虚空都是从"走"开始的 ✓（§22 那两次都是 ✓）
  ⚠ 而 idle 有个闸 ✓：★"最近 15 秒无模组指令"才自作主张✗★ ⇒
    所以采样间隔必须 **>= 120 秒**（一次采样只发 2 条 ✓）✓ 否则它整天被我压着不动 ✗
  ⚠ 也因此 ★**电池在跑的时候不许开 idle**✗★（**P25** ✓）—— 现在是电池跑完之后 ✓

判据（**先写死** ✓ 不许事后改 ✗）：
  D3a ★零掉虚空★ ：期间新增的 `bot_died` 事件数 == **0** ✓
        （★保险只保证不毁家当 ✗ 不保证不掉下去 ✗ ⇒ 这一条**不许**拿"东西没丢"替代 ✓★）
  D3b ★零丢物品★ ：背包 `items` 计数**从不减少** ✓（idle 溜达不该消耗任何东西 ✓）
  D3c ★不卡死★   ：每次采样都拿到回执 ✓（桥超时数 == 0 ✓）＋ 换过的**不同格数 > 1** ✓
  D3d 模式         ：全程 `mode=survival` ✓（★创造模式会让"自给"证据失真 ✗ P17 ✓★）
  ⚠ 附记 ✓：`hp` / `food` 也记下来 ✓ —— 掉血说明它撞了/摔了 ✓ 那要单独看 ✓

用法 ✓：
  py tools/d3_soak.py --minutes 180            # 跑 3 小时（默认间隔 120 秒）
  py tools/d3_soak.py --minutes 2 --interval 20   # 自测（短跑 ✓ 验采样链通不通 ✓）

★★2026-11-02 迁移（★旧车道已死✗★）✗★★：
  原来走 `agent.channel.Channel("cmd0")`（Python → 网关 → **CC 计算机** → 模组 ✗）
  ⇒ 2026-11-01 一次 fill 把 CC 计算机填掉 ⇒ 整套断线 ✗
  ⇒ 2.53.0 起模组自己开 `127.0.0.1:8766`（`tools/direct.py`）⇒ 本观察器**改走直连** ✓
  口径：`/cmd` **自己包 `execute as Bot at @s run`** ⇒ 这里发**裸指令**（dshdigest 1 …）
  ★idle 判据/采样间隔/还原语义**一条没改**✗★（只换车道 ✓ 见 `soak_suite_test.py` F1 守卫）
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import direct as D          # noqa: E402  ★直连 8766（模组自己包的 /cmd ✓）★

LOG = ROOT / "logs" / "d3_soak.jsonl"


def say(s=""):
    print(s, flush=True)


def main(argv) -> int:
    mins = 180.0
    interval = 120.0
    radius = 6
    if "--minutes" in argv:
        mins = float(argv[argv.index("--minutes") + 1])
    if "--interval" in argv:
        interval = float(argv[argv.index("--interval") + 1])
    if "--radius" in argv:
        radius = int(argv[argv.index("--radius") + 1])
    # ★采样间隔必须 >= 120 秒✗★（**2026-10-01 自测实测** ✓）：
    #   `dshidle` 的闸是 `quiet_ticks=300`（★最近 **15 秒**无模组指令才自作主张✗★）
    #   ⇒ 我拿 20 秒间隔自测 ⇒ ★每一次采样都把它的静默计时清零✗★
    #   ⇒ 两分钟里假人**一步没动** ✗ ⇒ `D3c` 当场红 ✓（★这条红是**对的**✗★ —— 它抓的是**我**）
    if interval < 120:
        say("⚠ 间隔 %.0f 秒 < 120 秒 ⇒ ★idle 会被压得不动✗★（只见于自测 ✓ 真跑请 >=120 ✓）"
            % interval)
    say("D3 soak: %.0f 分钟 ｜ 采样间隔 %.0f 秒 ｜ idle 半径 %d" % (mins, interval, radius))

    # ★★2026-11-02 直连迁移✗★★：以前这里 `from channel import Channel; ch = Channel(...)`
    #   ⇒ 现在只走 `tools/direct.py`（POST 127.0.0.1:8766/cmd ✓ 2~4ms ✓）
    #   ★口径✗★：/cmd 自己包 `execute as Bot at @s run` ⇒ 发**裸指令** ✓
    def dsh(text, t=40.0):
        try:
            r = D.post(text, timeout=t)
        except Exception as exc:          # ★不许静默✗★
            return "ERR:exception:%s:%s" % (type(exc).__name__, exc)
        if r is None:
            return "ERR:bridge_none(8766 不通/超时)"
        return (r or "").strip()

    def digest():
        t = dsh("dshdigest 1")
        if t.startswith("ERR:") or "pos=" not in t:
            return None, t
        g = lambda k, d=None: (re.search(k + r"=([^\s]+)", t).group(1)
                               if re.search(k + r"=([^\s]+)", t) else d)
        inv = re.search(r"inv\[x\]kinds=(\d+),items=(\d+),free=(\d+)", t)
        return {
            "pos": g("pos"), "hp": g("hp"), "food": g("food"), "mode": g("mode"),
            "onground": g("onground"),
            "kinds": int(inv.group(1)) if inv else None,
            "items": int(inv.group(2)) if inv else None,
            "free": int(inv.group(3)) if inv else None,
            "raw_ok": True,
        }, t

    def died_count():
        t = dsh("dshevents")
        if t.startswith("ERR:"):
            return None, t
        n = len(re.findall(r"#\d+ bot_died phase=enter", t))
        return n, t

    # ---- 开局：记 idle 原状 ⇒ 打开溜达 ✓（结束要还原 ✗ 不越权 ✓）----
    # ★★2026-10-01 实测踩到的坑✗★★：我第一版发的是 `dshidle on radius 6` ✗
    #   而模组的签名是 `idleCmd(op, radius)` ✓（**`on` 后面直接跟数字**✓）
    #   ⇒ Brigadier **解析失败** ✗ ⇒ `humanoid` 根本没开 ✗ ⇒ ★假人两分钟一步没动✗★
    #   ★而我犯的更大一个错是✗★：**把那条回执丢掉了** ✗（★不看回执 ⇒ 失败无声✗★ **P116**）
    #   ⇒ 口径 ✓：① 用对语法 ✓ ② ★**回读状态并断言**✗★ ③ 断言不过就**大声中止** ✗
    st0 = dsh("dshidle status")
    say("idle 原状: %s" % st0[:130])
    was_on = bool(re.search(r"humanoid\s*=\s*true", st0, re.I))
    _m = re.search(r"radius=(\d+)", st0)
    base_radius = int(_m.group(1)) if _m else radius
    # ★★真语法（从注册表读出来的 ✗ 不是猜的 ✓）★★：
    #   `dshidle on` **不接受任何参数** ✗；半径是**单独一条** `dshidle radius <n>` ✓
    #   ⇒ 所以必须**两条** ✓（我连猜错两次 ✗：`on radius 6` ✗ `on 6` ✗）
    say("dshidle radius %d -> %s" % (radius, dsh("dshidle radius %d" % radius)[:130]))
    say("dshidle on      -> %s" % dsh("dshidle on")[:130])
    st1 = dsh("dshidle status")
    if not re.search(r"humanoid\s*=\s*true", st1, re.I):
        say("★idle 没开成 ✗ 中止★（回读=%s）" % st1[:130])
        return 2
    say("idle 已开并**回读确认** ✓（期望 radius=%d）：%s" % (radius, st1[:130]))

    d0, raw0 = digest()
    if d0 is None:
        say("★开局就拿不到 digest ✗ 中止★：%s" % raw0[:160])
        return 2
    n0, _ = died_count()
    if n0 is None:
        say("★读不到事件流（dshevents）⇒ 死亡 oracle 做不了 ✗ 中止★（exit 2）")
        return 2
    died_max = n0
    base_items = d0["items"]
    say("基线：pos=%s items=%s kinds=%s mode=%s ｜ bot_died 累计=%s"
        % (d0["pos"], d0["items"], d0["kinds"], d0["mode"], n0))

    t_end = time.time() + mins * 60.0
    cells = set()
    timeouts = 0
    samples = 0
    min_items = base_items or 0
    worst_hp = 100.0
    modes = set()
    non_survival = 0
    LOG.parent.mkdir(parents=True, exist_ok=True)
    f = LOG.open("a", encoding="utf-8", newline="\n")

    while time.time() < t_end:
        time.sleep(interval)
        samples += 1
        d, raw = digest()
        if d is None:
            timeouts += 1
            rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "sample": samples,
                   "ok": False, "raw": raw[:200]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            say("[%d] ★拿不到回执✗★ %s" % (samples, raw[:100]))
            continue
        dn, _ = died_count()
        if dn is not None:
            # ★事件环只留 400 条 ⇒ 计数可能因 trim 变小 ✗ 取**历史最大值**才诚实✓★
            died_max = max(died_max, dn)
        if d["pos"]:
            p = d["pos"].split(",")
            if len(p) == 3:
                cells.add((int(float(p[0])), int(float(p[1])), int(float(p[2]))))
        if d["items"] is not None:
            min_items = min(min_items, d["items"])
        try:
            worst_hp = min(worst_hp, float(d["hp"]))
        except Exception as e:
            # 记录：这一采样的血量没算进 worst_hp ⇒ soak 结论会**偏乐观**
            say("[记录] 第 %d 采样血量解析不了（worst_hp 偏乐观）：%r（%s）"
                % (samples, d.get("hp"), type(e).__name__))
        modes.add(d["mode"])
        if d["mode"] != "survival":
            non_survival += 1
        rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "sample": samples, "ok": True,
               "pos": d["pos"], "hp": d["hp"], "food": d["food"], "mode": d["mode"],
               "items": d["items"], "kinds": d["kinds"], "free": d["free"],
               "bot_died_total": dn, "cells_so_far": len(cells)}
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        left = int((t_end - time.time()) / 60)
        say("[%d] %s ｜ items=%s hp=%s mode=%s ｜ bot_died=%s ｜ 不同格=%d ｜ 还剩 %d 分"
            % (samples, d["pos"], d["items"], d["hp"], d["mode"], dn, len(cells), left))

    f.close()
    d1, _ = digest()
    n1, _ = died_count()
    if n1 is not None:
        died_max = max(died_max, n1)
    new_died = (died_max - n0) if (n0 is not None) else None

    say("")
    say("================ D3 判定 ================")
    a = (new_died == 0)
    say("D3a 零掉虚空：新增 bot_died = %s（必须 0）=> %s" % (new_died, a))
    b = (min_items >= (base_items or 0))
    say("D3b 零丢物品：items 基线 %s ／ 期间最低 %s => %s" % (base_items, min_items, b))
    c = (timeouts == 0) and (len(cells) > 1)
    say("D3c 不卡死：桥超时 %d 次 ／ 到过的不同格 %d（要 >1）=> %s"
        % (timeouts, len(cells), c))
    d_ = (non_survival == 0)
    say("D3d 模式：见过的模式 %s ／ 非 survival 采样 %d => %s"
        % (sorted(modes), non_survival, d_))
    say("（附记 ✓）最低 hp = %s ｜ 采样 %d 次" % (worst_hp, samples))
    ok = a and b and c and d_
    say("=> D3 %s%s" % ("PASS" if ok else "FAIL",
                        "" if ok else "  ★不许粉饰✗★（明细在 logs/d3_soak.jsonl ✓）"))
    # ---- 还原 idle 原状 ✓ ----
    # ★真语法（2026-10-01 实测）：`dshidle on` **不接受参数** ✗ 半径单独一条 `dshidle radius <n>` ✓
    #   （旧版这里写成 `dshidle on <n>` ✗ 是死语法 ⇒ 还原从来没生效 ✗ 本次一并修掉 ✓）
    dsh("dshidle radius %d" % base_radius)
    if was_on:
        dsh("dshidle on")
    else:
        dsh("dshidle off")
    say("idle 已还原（原状 humanoid=%s radius=%d）：%s"
        % (was_on, base_radius, dsh("dshidle status")[:130]))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
