#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""humanlike_test.py -- 模块 G 判据层：把"像不像人"变成机器判据

规格（docs/方案-拟人化模块.md §0 / §6.1 / §6.2）：
  拟人化 = 这 N 条反例一条都不出现 ＋ 任务能完成。本文件实现其中**不需要新模组能力**的五条：

  N1 ★瞬移★     相邻采样的位移速度 > 12 bps                    （人跑跳极限约 6 bps）
  N2 ★悬空★     onground=False 持续 > 1.5s 且 |Δy| 极小           （要么在掉，要么站在空中）
  N4 ★一帧完成★ 动作消耗的**游戏刻**少于该类动作的下限          （挖/放/吃/开门都有前摇）
  N7 ★无故掉血★ hp 下降但同一时间窗没有 `damage` 事件
  N8' ★留痕★   每条 mut／inv delta／damage 事件都能在 ±窗口内找到理由记录（tools/reasons.py）

★每条都必须能"故意造红"（`--selfcheck` 10 项）⇒ 判据自己先被验过，才允许拿来判别人。
★`--live` 才连游戏；`--selfcheck` 纯离线（进闸门）。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MAX_BPS = 12.0            # N1
AIRBORNE_MS = 1500.0      # N2
AIR_DY = 0.05
REASON_WINDOW_S = 8.0     # N8'

# N4：各类动作的**最小游戏刻**（20 tick = 1 秒）
MIN_TICKS = {
    "dig": 2,             # 再软也要 2 刻
    "place": 1,
    "eat": 32,            # 1.6 秒咀嚼（模组走的是真人路径）
    "open": 1,
}


# ── N1 瞬移 ────────────────────────────────────────────────────────────
def judge_n1(samples) -> tuple:
    """samples: [{"t": epoch, "pos": (x,y,z)}, ...]  ⇒ (ok, detail)"""
    if len(samples) < 2:
        return True, "样本不足（%d）" % len(samples)
    worst = 0.0
    at = None
    for a, b in zip(samples, samples[1:]):
        dt = float(b["t"]) - float(a["t"])
        if dt <= 0.01:
            continue
        d = sum((float(b["pos"][i]) - float(a["pos"][i])) ** 2 for i in range(3)) ** 0.5
        bps = d / dt
        if bps > worst:
            worst, at = bps, (a["pos"], b["pos"], round(dt, 2))
    return worst <= MAX_BPS, "最大 %.2f bps（上限 %.1f）%s" % (worst, MAX_BPS, at or "")


# ── N2 悬空 ────────────────────────────────────────────────────────────
def judge_n2(samples) -> tuple:
    run_start = None
    for s in samples:
        if not s.get("onground", True):
            if run_start is None:
                run_start = s
            elif (float(s["t"]) - float(run_start["t"])) * 1000.0 > AIRBORNE_MS:
                dy = abs(float(s["pos"][1]) - float(run_start["pos"][1]))
                if dy < AIR_DY:
                    return False, "悬空 %.0fms 且 Δy=%.3f（pos=%s）" % (
                        (float(s["t"]) - float(run_start["t"])) * 1000.0, dy, s["pos"])
        else:
            run_start = None
    return True, "最长悬空未超限"


# ── N4 一帧完成 ────────────────────────────────────────────────────────
def judge_n4(actions) -> tuple:
    """actions: [{"kind": "dig"|"place"|"eat"|"open", "ticks": int}, ...]"""
    bad = [(a.get("kind"), a.get("ticks")) for a in actions
           if a.get("kind") in MIN_TICKS and int(a.get("ticks") or 0) < MIN_TICKS[a["kind"]]]
    return not bad, ("前摇不足: %s" % (bad[:4],)) if bad else "%d 个动作时长都够" % len(actions)


# ── N7 掉血必须**来源明确 ＋ 有对策** ──────────────────────────────────
def judge_n7(samples, damages, window=REASON_WINDOW_S) -> tuple:
    """★用户口径✗★：★"★明确伤害来源 ✗ 根据来源给不同对策★"✗★

    damages: [{"t": epoch, "delta": float, "src": "fall|mob|drown|in_wall|starve|..."}, ...]
      · 掉血**没有**对应事件        ⇒ 红（`no_event`）
      · 有事件但 **src 查不到对策**  ⇒ 红（`unknown_src`）★不许"有事件就算过"✗★
      · 有事件且 src 有对策         ⇒ 绿（★并且必须报出对策是什么✗★）
    """
    try:
        import damage_policy as DP
    except Exception as exc:                # ★不许静默✗★
        return False, "加载 damage_policy 失败：%r" % (exc,)

    dmg = list(damages)
    bad = []
    advised = []
    for a, b in zip(samples, samples[1:]):
        drop = float(a.get("hp", 0)) - float(b.get("hp", 0))
        if drop <= 0.01:
            continue
        tb = float(b["t"])
        hits = [d for d in dmg if abs(float(d["t"]) - tb) <= window]
        if not hits:
            bad.append(("no_event", round(drop, 1)))
            continue
        src = hits[-1].get("src") or ""
        adv = DP.advise(src)
        if not adv["known"]:
            bad.append(("unknown_src:%s" % adv["src"], round(drop, 1)))
            continue
        advised.append((adv["src"], adv["action"]))
    if bad:
        return False, "掉血无法解释/无对策: %s" % (bad[:4],)
    if advised:
        return True, "掉血都有来源与对策: %s" % (advised[:4],)
    return True, "无掉血"


# ── N8' 有后果事件必须留痕 ─────────────────────────────────────────────
CONSEQ = ("mut", "inv", "damage")


def judge_n8(events, reasons, window=REASON_WINDOW_S) -> tuple:
    """events: [{"t": epoch, "kind": "mut"|"inv"|"damage", "detail": str}, ...]
       reasons: [{"ts": epoch, "reason": str, "mission": str}, ...]
    ⇒ ★每条有后果事件都要在 ±window 内找到一条理由**"""
    rts = [float(r.get("ts") or 0) for r in reasons if r.get("reason") or r.get("mission")]
    bad = []
    for e in events:
        if e.get("kind") not in CONSEQ:
            continue
        t = float(e["t"])
        if not any(abs(t - rt) <= window for rt in rts):
            bad.append((e.get("kind"), e.get("detail", "")[:32], round(t, 1)))
    return not bad, ("没理由的有后果事件: %s" % (bad[:4],)) if bad else \
                    "%d 条有后果事件都有理由" % len([e for e in events if e.get("kind") in CONSEQ])


# ── 汇总 ───────────────────────────────────────────────────────────────
def run_all(samples, actions, damages, events, reasons) -> list:
    return [
        ("N1 不许瞬移", *judge_n1(samples)),
        ("N2 不许悬空", *judge_n2(samples)),
        ("N4 不许一帧完成", *judge_n4(actions)),
        ("N7 不许无故掉血", *judge_n7(samples, damages)),
        ("N8' 有后果事件必须留痕", *judge_n8(events, reasons)),
    ]


def selfcheck() -> int:
    """★每条判据都要能"故意造红" ⇒ 先验判据，再用判据✗★"""
    now = time.time()
    NOW = now
    good_samples = [{"t": now + i * 0.5, "pos": (0, 70, i * 1.0), "hp": 20.0, "onground": True}
                    for i in range(6)]
    bad_warp = [{"t": now, "pos": (0, 70, 0), "hp": 20.0, "onground": True},
                {"t": now + 0.1, "pos": (0, 70, 30), "hp": 20.0, "onground": True}]
    bad_air = [{"t": now + i * 0.5, "pos": (0, 70, 0), "hp": 20.0, "onground": False}
               for i in range(8)]
    good_actions = [{"kind": "dig", "ticks": 10}, {"kind": "eat", "ticks": 40}]
    bad_actions = [{"kind": "dig", "ticks": 0}, {"kind": "eat", "ticks": 3}]
    good_dmg = [{"t": now, "delta": -1.0, "src": "fall"}]
    bad_hp = [{"t": now, "pos": (0, 70, 0), "hp": 20.0, "onground": True},
              {"t": now + 1.0, "pos": (0, 70, 1), "hp": 18.0, "onground": True}]
    good_ev = [{"t": now, "kind": "mut", "detail": "a"},
               {"t": now + 1, "kind": "inv", "detail": "b"}]
    good_rs = [{"ts": now, "reason": "dig ore", "mission": "m1"},
               {"ts": now + 1, "reason": "pickup", "mission": "m1"}]
    bad_rs = [{"ts": now + 100, "reason": "far away", "mission": "m9"}]

    checks = [
        ("N1 好样本 ⇒ 绿", judge_n1(good_samples)[0] is True),
        ("N1 瞬移 ⇒ 红", judge_n1(bad_warp)[0] is False),
        ("N2 好样本 ⇒ 绿", judge_n2(good_samples)[0] is True),
        ("N2 悬空 ⇒ 红", judge_n2(bad_air)[0] is False),
        ("N4 好动作 ⇒ 绿", judge_n4(good_actions)[0] is True),
        ("N4 一帧完成 ⇒ 红", judge_n4(bad_actions)[0] is False),
        ("N7 掉血有事件且来源已知 ⇒ 绿", judge_n7(bad_hp, good_dmg)[0] is True),
        ("N7 掉血没事件 ⇒ 红", judge_n7(bad_hp, [])[0] is False),
        ("N7 来源未知 ⇒ 红", judge_n7(bad_hp, [{"t": NOW + 1.0, "delta": -1.0,
                                              "src": "some_new_mod_damage"}])[0] is False),
        ("N7 绿时必须报出对策", "fall" in judge_n7(bad_hp, good_dmg)[1]),
        ("N8' 有理由 ⇒ 绿", judge_n8(good_ev, good_rs)[0] is True),
        ("N8' 没理由 ⇒ 红", judge_n8(good_ev, bad_rs)[0] is False),
    ]
    bad = 0
    for name, ok in checks:
        print("  %s %s" % (name, "PASS" if ok else "FAIL"))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => humanlike FAIL（★判据自己都不对 ✗ 不许拿来判别人✗★）")
        print("HUMANLIKE ok=0 bad=%d" % bad)
        return 1
    print("  => humanlike PASS（★五条判据都能故意造红✗ 才允许用✗★）")
    print("HUMANLIKE ok=1 checks=%d" % len(checks))
    return 0


def live(seconds: float = 8.0) -> int:
    """真世界采样（★只读 ✗ 不改世界✗★）"""
    import mcp_core as C
    import reasons as R

    samples, actions, damages = [], [], []
    t_end = time.time() + seconds
    prev = None
    while time.time() < t_end:
        d = (C.dsh("dshdigest", 30.0) or "").strip()
        m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", d)
        if m:
            hp = re.search(r"hp=([\d.]+)", d)
            og = re.search(r"onground=(true|false)", d)
            s = {"t": time.time(),
                 "pos": tuple(float(m.group(i)) for i in (1, 2, 3)),
                 "hp": float(hp.group(1)) if hp else 20.0,
                 "onground": (og.group(1) == "true") if og else True}
            samples.append(s)
            if prev is not None and s["hp"] < prev["hp"] - 0.01:
                damages.append({"t": s["t"], "delta": s["hp"] - prev["hp"], "src": "unknown"})
            prev = s
        time.sleep(0.4)

    ev = (C.dsh("dshevents 0", 40.0) or "")
    events = []
    for kind in ("mut", "inv", "damage"):
        for _ in re.finditer(r"#\d+ " + kind + r"\b", ev):
            events.append({"t": time.time(), "kind": kind, "detail": kind})

    rows = run_all(samples, actions, damages, events, R.load())
    bad = 0
    for name, ok, detail in rows:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(rows) - bad, len(rows)))
    print("HUMANLIKE ok=%d checks=%d samples=%d" % (1 if bad == 0 else 0, len(rows), len(samples)))
    return 0 if bad == 0 else 1


def main(argv) -> int:
    if "--live" in argv:
        secs = 8.0
        if "--seconds" in argv:
            secs = float(argv[argv.index("--seconds") + 1])
        return live(secs)
    return selfcheck()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
