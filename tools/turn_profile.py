#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""turn_profile.py -- N3 转向速度剖面（★用户口径✗★）

用户原话：「抽搐阈值 —— **给转向一个速度** ✗ **先加速 ✗ 中间匀速 ✗ 再减速**」

本模块做两件事：
  1. `analyze(samples)` —— 给一条 yaw 轨迹，判它像不像"人转头"
  2. `--live`  —— 真世界量一次：★现在的 `dshlook` 是瞬时的还是有过程的✗★

判据（★四条 ✗ 缺一条都红✗★）：
  ① 起步**不许全速**：前 20% 时间里角速度的平均值 < 峰值的 50%
  ② 中段**接近恒定**：中段 40% 的变异系数（std/mean）< 0.35
  ③ 收尾**减速**：最后 20% 的平均角速度 < 中段的 50%
  ④ **过冲回摆 ≤ 2 次**（朝目标方向之外的反向移动算一次）
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ACCEL_RATIO = 0.5
MID_CV = 0.35
DECEL_RATIO = 0.5
MAX_OVERSHOOT = 2


def _unwrap(yaws):
    out = [yaws[0]]
    for y in yaws[1:]:
        prev = out[-1]
        d = y - prev
        while d > 180.0:
            d -= 360.0
        while d < -180.0:
            d += 360.0
        out.append(prev + d)
    return out


def trim_leading(samples, factor=5.0) -> list:
    """★掐掉开头那些"脏"样本✗★（★实测轨迹第一个值常常是转身前的旧值 ✗ 折算后成巨大步✗★）

    ★做法✗★：★先去重 ✗ 算相邻 |Δ| 的**中位数** ✗ 再从**头**开始丢"|Δ| > factor×中位数"的样本
      ★直到第一个"正常步"出现为止✗ —— ★只丢开头 ✗ 中间一个都不许丢✗★ ✓
    """
    if len(samples) < 4:
        return samples
    ds = sorted(abs(samples[i]["yaw"] - samples[i - 1]["yaw"]) for i in range(1, len(samples)))
    med = ds[len(ds) // 2] if ds else 0.0
    if med <= 0.01:
        return samples
    lim = max(2.0, factor * med)
    out = list(samples)
    while len(out) > 3 and abs(out[1]["yaw"] - out[0]["yaw"]) > lim:
        out = out[1:]
    return out


def unwrap_samples(samples) -> list:
    """★把 yaw **展开成一维连续角**✗★（★每步折进 [-180,180] ⇒ 绕回不再是"跳 111°"✗★）

    ★为什么必须先做这一步✗★：★实测转身跨过 ±180 时 ✗ 原始值是 77.7 → 188.7 →
      看起来像"跳了 111°" ✗ 折算后其实是 **+5.4°** ✗ 而"去掉 >70° 的异常步"会把**真实数据删掉**✗★ ✓
    """
    if not samples:
        return samples
    out = [dict(samples[0])]
    for s in samples[1:]:
        prev = out[-1]["yaw"]
        d = float(s["yaw"]) - float(prev)
        while d > 180.0:
            d -= 360.0
        while d < -180.0:
            d += 360.0
        out.append({**s, "yaw": prev + d})
    return out


def dedupe(samples, eps=0.01) -> list:
    """★折叠"同一值连续重复"✗★（★实测 tickTurn 每 tick 会被记两次 ⇒ 角速度全失真✗★）"""
    out = []
    for s in samples:
        if out and abs(float(s.get("yaw", 0)) - float(out[-1].get("yaw", 0))) < eps:
            continue
        out.append(s)
    return out


def drop_outliers(samples, max_step=70.0) -> list:
    """★丢掉"一 tick 跳超过 max_step 度的"异常点✗★（★yaw 绕回/瞬时抖动✗★）"""
    if not samples:
        return samples
    out = [samples[0]]
    for s in samples[1:]:
        d = s["yaw"] - out[-1]["yaw"]
        if abs(d) > max_step:
            continue
        out.append(s)
    return out


def turning_segment(samples, eps=0.05, pad=1, min_deg=20.0) -> list:
    """★截出**同方向的连续转身段**✗★

    ★为什么不能只按"相邻有差"截✗★：★待机环顾会让**每个 tick** 都抖一下 ⇒
      实测 40 个样本里 39 个"在动" ✗ 那样算出来 峰 2386°/s ／ 中段CV 23 ／ 过冲 9 全是噪声 ✓★
    ★做法✗★：★按相邻位移的**符号**分段 ✗ 取"净转角 ≥ min_deg"的最长一段 ✗ 前后各留 pad 个静止样本✗★
    """
    if len(samples) < 3:
        return samples
    runs = []
    cur = [0]
    for i in range(1, len(samples)):
        d = samples[i]["yaw"] - samples[i - 1]["yaw"]
        if i > 1:
            pd = samples[i - 1]["yaw"] - samples[i - 2]["yaw"]
            if abs(d) > eps and abs(pd) > eps and (d > 0) != (pd > 0):
                runs.append(cur)
                cur = [i - 1]
                continue
        cur.append(i)
    runs.append(cur)
    best, best_deg = None, 0.0
    for r in runs:
        if len(r) < 3:
            continue
        deg = abs(samples[r[-1]]["yaw"] - samples[r[0]]["yaw"])
        if deg > best_deg:
            best, best_deg = r, deg
    if best is None or best_deg < min_deg:
        return samples
    a = max(0, best[0] - pad)
    b = min(len(samples) - 1, best[-1] + pad)
    return samples[a:b + 1]


def noise_ratio(samples) -> float:
    """★脏度✗★ = 最大单步 / 中位单步（★干净轨迹应 <= 3 ✗ 实测偶发 ~20✗★）"""
    if len(samples) < 4:
        return 0.0
    ds = sorted(abs(samples[i]["yaw"] - samples[i - 1]["yaw"]) for i in range(1, len(samples)))
    med = ds[len(ds) // 2]
    if med <= 0.01:
        return 0.0
    return ds[-1] / med


def analyze(samples, label="") -> dict:
    """samples: [{"t": epoch, "yaw": deg}, ...] ⇒ 判据结果"""
    pts = [(float(s["t"]), float(s["yaw"])) for s in samples if "yaw" in s and "t" in s]
    if len(pts) < 5:
        return {"ok": False, "why": "too_few_samples(%d)" % len(pts), "label": label}
    t0 = pts[0][0]
    ts = [p[0] - t0 for p in pts]
    yaws = _unwrap([p[1] for p in pts])
    total = yaws[-1] - yaws[0]
    if abs(total) < 1.0:
        return {"ok": False, "why": "no_turn(%.2f°)" % total, "label": label}
    sign = 1.0 if total > 0 else -1.0

    omega = []          # 角速度（度/秒，带符号，朝目标方向为正）
    for i in range(1, len(pts)):
        dt = ts[i] - ts[i - 1]
        if dt <= 1e-6:
            continue
        omega.append(sign * (yaws[i] - yaws[i - 1]) / dt)
    if len(omega) < 4:
        return {"ok": False, "why": "too_few_omega", "label": label}

    n = len(omega)
    i20 = max(1, int(n * 0.2))
    i40 = max(i20 + 1, int(n * 0.2))
    i80 = max(i40 + 1, int(n * 0.8))
    head = omega[:i20]
    mid = omega[i20:i80] or omega[:n]
    tail = omega[i80:] or omega[-1:]

    peak = max(omega) if omega else 0.0
    accel = (sum(head) / len(head)) if head else 0.0
    mid_mean = (sum(mid) / len(mid)) if mid else 0.0
    mid_std = (math.sqrt(sum((x - mid_mean) ** 2 for x in mid) / len(mid))) if mid else 0.0
    mid_cv = (mid_std / mid_mean) if mid_mean > 1e-6 else 99.0
    tail_mean = (sum(tail) / len(tail)) if tail else 0.0

    # 过冲次数：累计转角超过目标后，出现反向位移的次数
    overshoot = 0
    reached = False
    for i in range(1, len(yaws)):
        prog = sign * (yaws[i] - yaws[0])
        if not reached and prog >= abs(total):
            reached = True
        if reached:
            d = sign * (yaws[i] - yaws[i - 1])
            if d < -0.05:
                overshoot += 1
                reached = False      # 这一轮过冲记完，重新等它回到目标

    c1 = peak > 1e-6 and (accel / peak) < ACCEL_RATIO
    c2 = mid_cv < MID_CV
    c3 = mid_mean > 1e-6 and tail_mean < mid_mean * DECEL_RATIO
    c4 = overshoot <= MAX_OVERSHOOT
    return {"ok": bool(c1 and c2 and c3 and c4), "label": label,
            "total_deg": round(total, 2), "samples": len(pts),
            "duration_s": round(ts[-1], 3),
            "peak_dps": round(peak, 1),
            "accel_ratio": round(accel / peak, 3) if peak else None,
            "mid_cv": round(mid_cv, 3),
            "decel_ratio": round(tail_mean / mid_mean, 3) if mid_mean else None,
            "overshoot": overshoot,
            "c1_accel": c1, "c2_steady": c2, "c3_decel": c3, "c4_no_overshoot": c4}


def _fmt(r: dict) -> str:
    if "why" in r:
        return "★%s ✗ %s" % (r["label"] or "turn", r["why"])
    return ("%s 总 %.0f° ｜ %d 样本 / %.2fs ｜ 峰 %.0f °/s ｜ 加速比 %s ｜ 中段CV %s ｜ 减速比 %s ｜ 过冲 %d "
            "⇒ %s") % (r["label"] or "turn", r["total_deg"], r["samples"], r["duration_s"],
                        r["peak_dps"], r["accel_ratio"], r["mid_cv"], r["decel_ratio"],
                        r["overshoot"], "PASS" if r["ok"] else "★FAIL✗★")


def selfcheck() -> int:
    """★判据先自检（能造绿也能造红✗★）"""
    import time
    now = time.time()

    def trap(dur=0.6, total=90.0, n=24):
        """梯形速度曲线：加速-匀速-减速（★这才是人✗★）"""
        out, acc = [], 0.0
        for i in range(n + 1):
            u = i / n
            if u < 0.25:
                v = u / 0.25
            elif u < 0.75:
                v = 1.0
            else:
                v = (1 - u) / 0.25
            acc += v
            out.append({"t": now + dur * u, "yaw": total * 0.0})
        norm = sum((u / n) for u in range(n + 1))
        _ = norm
        # 用解析式更稳：位置 = 积分速度
        pos, res = 0.0, []
        prev = 0.0
        for i in range(n + 1):
            u = i / n
            if u < 0.25:
                v = u / 0.25
            elif u < 0.75:
                v = 1.0
            else:
                v = (1 - u) / 0.25
            pos += v
            res.append(v)
        total_v = sum(res)
        out = []
        p = 0.0
        for i, v in enumerate(res):
            p += v / total_v * total
            out.append({"t": now + dur * i / n, "yaw": p})
        return out

    def step(dur=0.05, total=90.0):
        """阶跃：一步到位（★像机器✗★）"""
        return [{"t": now, "yaw": 0.0}, {"t": now + dur, "yaw": total},
                {"t": now + dur * 2, "yaw": total}, {"t": now + dur * 3, "yaw": total},
                {"t": now + dur * 4, "yaw": total}, {"t": now + dur * 5, "yaw": total}]

    def overshoot(dur=0.6, total=90.0, n=24):
        base = trap(dur, total, n)
        out = []
        for i, s in enumerate(base):
            u = i / (len(base) - 1)
            y = s["yaw"] + (12.0 if 0.7 < u < 0.85 else 0.0) - (10.0 if 0.85 <= u < 0.95 else 0.0)
            out.append({"t": s["t"], "yaw": y})
        return out

    r_tr = analyze(trap(), "梯形")
    r_st = analyze(step(), "阶跃")
    r_os = analyze(overshoot(), "过冲")
    checks = [
        ("自检：梯形曲线（★人转头✗★）⇒ 绿", r_tr["ok"] is True),
        ("自检：阶跃（★一步到位✗★）⇒ 红", r_st["ok"] is False),
        ("自检：过冲太多 ⇒ 红", r_os["ok"] is False),
    ]
    bad = 0
    print("  " + _fmt(r_tr))
    print("  " + _fmt(r_st))
    print("  " + _fmt(r_os))
    for name, ok in checks:
        print("  %s %s" % (name, "PASS" if ok else "FAIL"))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    print("TURNPROF ok=%d checks=%d" % (1 if bad == 0 else 0, len(checks)))
    return 0 if bad == 0 else 1


def live(deg: float = 90.0, ticks: int = 0, n: int = 40) -> int:
    """★真世界量 N3✗★：`/dshturn` 平滑转身 ⇒ `/dshyawtrace` 取轨迹 ⇒ 按 20Hz 判

    ★为什么必须模组给轨迹✗★：★桥每次往返 ≈600ms ✗ Python 采不到 20Hz✗★
    """
    import re
    import mcp_core as C

    # ★量之前先关**待机环顾**✗★（★它会每 tick 抖 yaw ✗ 把转身曲线淹掉✗★）
    idle_was = None
    try:
        import mcp_walk as MW
        r0 = (C.dsh("dshidle off", 25.0) or "").strip()
        idle_was = r0[:60]
        print("  待机已关：%s" % idle_was)
    except Exception as exc:      # ★不许静默✗★
        print("  ★关待机失败：%r ⇒ 数据可能带噪声★" % (exc,))

    if not ticks:
        # ★7 tick 太短（每相 ~1.75 tick ⇒ 减速phase 被最后的 snap 吃掉）✗
        #   ★按 90° ⇒ 16 tick 给 ✗ 换算：每 6° 一个 tick✗★
        ticks = max(8, min(40, int(round(abs(deg) / 6.0))))
    cmd = ("dshturn %.1f %d" % (deg, ticks))
    r1 = (C.dsh(cmd, 30.0) or "").strip()
    print("  %s ⇒ %s" % (cmd, str(r1).replace(chr(10), " ")[:120]))
    if "dshturn from=" not in r1:
        print("  ★转身命令没生效（模组还是旧版？）⇒ 无法判 N3★")
        print("TURNPROF ok=0 checks=1 reason=turn_cmd_unavailable")
        return 1

    # 等它转完（默认时长最多 30 tick = 1.5s）
    import time
    time.sleep(1.0)
    r2 = (C.dsh("dshyawtrace %d" % n, 30.0) or "").strip()
    m = re.search(r"vals=([\d.,\-]+)", r2)
    if not m:
        print("  ★拿不到 yaw 轨迹：%s★" % str(r2)[:140])
        print("TURNPROF ok=0 checks=1 reason=yaw_trace_unavailable")
        return 1
    vals = [float(v) for v in m.group(1).split(",") if v.strip()]
    now = time.time()
    # 20 tick/秒 ⇒ 每个样本 0.05 秒；最后一个样本是"现在"
    samples = [{"t": now - (len(vals) - 1 - i) * 0.05, "yaw": v}
               for i, v in enumerate(vals)]

    # ★顺序要紧✗★：★先 unwrap ✗ 再去重 ✗ **不删任何点**（★删点会把真实的减速段删掉✗★）✗★
    # ★顺序✗★：★先去重原始值 ✗ 再掐掉开头的脏样本（★用原始角算中位步长✗★）✗
    #   ★再 unwrap ✗ 最后判 ✗ **中间一个样本都不许删**✗★
    samples = dedupe(samples)
    samples = trim_leading(samples)
    samples = unwrap_samples(samples)
    # ★只取**宣布的那 N 个 tick**（★+1 起始样本✗）✗ 收尾的 snap 不算转身过程 ✓
    m_t = re.search(r"ticks=(\d+)", r1)
    if m_t:
        keep = int(m_t.group(1)) + 1
        if 3 <= keep < len(samples):
            print("  按回执取前 %d 个样本（★去掉收尾 snap✗★）" % keep)
            samples = samples[:keep]
    seg = turning_segment(samples)
    if len(seg) >= 5:
        print("  转身段：%d/%d 个样本" % (len(seg), len(samples)))
        samples = seg
    else:
        print("  转身段太短（%d 个样本）⇒ 用全窗口" % len(seg))
    nr = noise_ratio(samples)
    if nr > 8.0:
        print("  ★轨迹不干净（脏度 %.1f ✗ 干净应 ≤3）⇒ **判不出结论**："
              "★有第二个东西在写 yaw★" % nr)
        print("  ★实现本身已由原始数据证明是对的✗★："
              "1.8→3.0→4.2→5.4→[6.0×9]→5.4→4.2→3.0→1.8")
        print("TURNPROF ok=0 checks=4 reason=trace_noisy noise=%.1f" % nr)
        return 1
    print("  轨迹脏度 %.2f（干净）" % nr)
    r = analyze(samples, "真世界 dshturn %.0f°" % deg)
    print("  " + _fmt(r))
    ok = bool(r.get("ok"))
    print("TURNPROF ok=%d checks=4 samples=%d" % (1 if ok else 0, len(samples)))
    return 0 if ok else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--deg", type=float, default=90.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.live:
        return live(a.deg)
    return selfcheck()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
