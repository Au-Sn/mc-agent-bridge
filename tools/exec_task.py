#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exec_task.py -- ★多目标任务执行器（★在 `exec3d` 提交器之上✗★）（§79.423）

★★为什么要有它✗★★：★`exec3d` 一次只走**一个目标**✗★
　★而真实任务常是"★先去 A ✗ 再去 B ✗ 再到 C★"** ⇒ 现在要在外面**手动循环**✗★
　★⇒ ★而且每段之间**必须重读实时位置**（★上段可能走偏／被打断✗★）✗ 这点最容易漏✗★ ✓
★★本工具✗★★：★`--goals "x,y,z;x,y,z;…"`** ✗ **依次**跑✗★：
　★① 每段开始前**重新读 `bot_cell()`**（★不用上一段的目标当起点✗★）✗★
　★② 调 `exec3d.execute()`（★它内部已带"★失败用实时位置重试✗★"✗★）✗★
　★③ **某段失败 ⇒ 如实停** ✗ 报告里写清**哪些成了 ✗ 哪些没跑✗★ ✓
　★④ `--dry` ⇒ 每段都**只打印动作表** ✗ 不动世界✗★ ✓
★报告✗★：★`segments[]`（★start／goal／ok／attempts／end✗★）＋ `SUMMARY task pass=N fail=N total=N`**✗★ ✓
"""
from __future__ import annotations

import argparse
import re
import sys
import time

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import exec3d as E3            # noqa: E402


def parse_goals(spec: str):
    """★`"x,y,z;take:x,y,z:item:8;…"` ⇒ [(kind, pos, extra…), …]**✗★

    ★kind✗★：★`walk`（★光坐标 ✗ 旧行为✗★）／`take`／`store`**✗★
    ★坏格式**当场报** ✗ 不猜✗★ ✓
    """
    out = []
    for part in (spec or "").split(";"):
        s = part.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("take:") or low.startswith("store:"):
            kind = "take" if low.startswith("take:") else "store"
            body = s[len(kind) + 1:]
            # ★body = `x,y,z:item[:count]`**（★先按冒号切 ✗ 但 item 里可能有 :✗★）✗★
            v = body.split(":")
            if len(v) < 2:
                raise ValueError("★%s 步格式错（要 pos:item[:count]）：%r✗★" % (kind, part))
            xyz = [q.strip() for q in v[0].split(",") if q.strip()]
            if len(xyz) != 3:
                raise ValueError("★%s 步的坐标错（要 x,y,z）：%r✗★" % (kind, part))
            pos = tuple(int(float(x)) for x in xyz)
            item = v[1].strip()
            count = int(float(v[2])) if len(v) > 2 and v[2].strip() else 1
            if not item:
                raise ValueError("★%s 步缺 item：%r✗★" % (kind, part))
            out.append((kind, pos, item, count))
            continue
        # ★旧格式：光坐标 ⇒ walk✗★
        v = [q.strip() for q in s.replace(":", ",").split(",") if q.strip()]
        if len(v) != 3:
            raise ValueError("目标格式错（要 x,y,z 或 take:x,y,z:item）：%r" % (part,))
        out.append(("walk", tuple(int(float(x)) for x in v), None, 0))
    return out


def find_stand_near(pos, radius=2):
    """★找容器**旁边**站得住的一格（★4 向 ＋ 上下 ✗ 用 world3d 判✗★）✗★

    ★返回 (cell, world) 或 (None, world)**✗ ★找不到就**如实报** ✗ 不许硬走✗★ ✓
    """
    import world3d as W3
    import plan3d as P3
    x, y, z = pos
    lo = (x - radius - 2, y - radius, z - radius - 2)
    hi = (x + radius + 2, y + radius, z + radius + 2)
    w = W3.World3D()
    w.fetch_region((lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]))
    best = None
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                c = (x + dx, y + dy, z + dz)
                if c == (x, y, z):
                    continue
                try:
                    if P3.stand_at(w, *c)[0]:
                        d = abs(dx) + abs(dy) * 2 + abs(dz)
                        if best is None or d < best[0]:
                            best = (d, c)
                except Exception as e:      # ★不许静默✗★
                    print("  （★判 %s 站得住时出错：%r✗★）" % (c, e))
    return (best[1] if best else None), w


def run_goals(goals, dry=False, max_per_seg=400, pause_between=0.6):
    """★依次跑 ✗ 每段重读实时位置 ✗ 失败如实停✗★"""
    segments = []
    n_ok = n_fail = 0
    for k, goal in enumerate(goals):
        start = E3.bot_cell()
        # ★★§79.447✗★ **先解包** ✗ 再打印（★顺序错了会 UnboundLocalError✗★）✗★
        kind = goal[0] if isinstance(goal, tuple) and len(goal) == 4 else "walk"
        gpos = goal[1] if len(goal) == 4 else goal
        gitem = goal[2] if len(goal) == 4 else None
        gcount = goal[3] if len(goal) == 4 else 0
        print("")
        print("══★第 %d/%d 段✗★ %s ⇒ %s（★%s✗★）%s" % (k + 1, len(goals), start, gpos,
                                              kind, "（★--dry✗★）" if dry else ""))
        seg = {"idx": k + 1, "kind": kind, "goal": gpos, "item": gitem, "count": gcount,
               "start_at_plan": start, "ok": False, "attempts": None, "end": None}
        # ★★§79.447✗★ 容器步：★先走到**旁边站得住**的一格 ✗ 再取／放✗★
        if kind in ("take", "store"):
            near, _w = find_stand_near(gpos)
            if near is None:
                print("  ★找不到容器旁边的站位 ✗ 如实失败（★no_stand_cell✗★）✗★")
                seg.update({"reason": "no_stand_cell"})
                segments.append(seg)
                n_fail += 1
                break
            print("  容器 %s ⇒ 站位 %s（★%s ✗ %s ×%d✗★）"
                  % (gpos, near, kind, gitem, gcount))
            if dry:
                print("  ★--dry：会先走到 %s ✗ 再 `dsh%s %s %s %d`**" % (near, kind, gpos, gitem, gcount))
                seg.update({"ok": True, "end": None})
                segments.append(seg)
                n_ok += 1
                continue
            okw, repw = E3.execute(near, max_steps=max_per_seg)
            if not okw:
                seg.update({"reason": "walk_to_container_failed", "end": repw.get("end")})
                segments.append(seg)
                n_fail += 1
                break
            cmd = "dshtake %d %d %d %s %d" % (gpos[0], gpos[1], gpos[2], gitem, gcount) \
                if kind == "take" else \
                "dshstore %d %d %d %s %d" % (gpos[0], gpos[1], gpos[2], gitem, gcount)
            r = E3.C.dsh(cmd, 40.0) or ""
            print("  ★%s ⇒ %r" % (kind, r.strip()[:170]))
            mm = re.search(r"(got|put)=(\d+)", r)
            why = re.search(r"why=(\w+)", r)
            if not mm:
                seg.update({"reason": (why.group(1) if why else "no_got_field"),
                            "end": E3.bot_cell()})
                segments.append(seg)
                n_fail += 1
                break
            seg.update({"ok": True, "got": int(mm.group(2)), "end": E3.bot_cell()})
            segments.append(seg)
            n_ok += 1
            continue
        if start is None:
            print("  ★读不到位置 ✗ 段失败 ✗ 如实停✗★")
            seg["reason"] = "no_pos"
            segments.append(seg)
            n_fail += 1
            break
        ok, rep = E3.execute(gpos, dry=dry, max_steps=max_per_seg)
        seg.update({"ok": bool(ok), "attempts": rep.get("attempts"),
                    "end": rep.get("end"), "reason": rep.get("reason"),
                    "arrived": rep.get("arrived"),
                    "steps": rep.get("steps"), "cost": rep.get("cost")})
        segments.append(seg)
        if ok:
            n_ok += 1
            if not dry and k + 1 < len(goals):
                time.sleep(pause_between)          # ★段间喘口气 ✗ 让世界稳定✗★
        else:
            n_fail += 1
            print("  ★第 %d 段没成（★%s✗★）⇒ **如实停** ✗ 后面的段不跑了✗★"
                  % (k + 1, rep.get("reason") or rep.get("bad")))
            break
    total = len(segments)
    print("")
    print("  ★分段结果✗★：")
    for s in segments:
        print("     %d/%d ⇒ %s ｜ ok=%s ｜ end=%s%s"
              % (s["idx"], len(goals), s["goal"], s["ok"], s["end"],
                 (" ｜ 原因=%s" % s["reason"]) if s.get("reason") else ""))
    try:
        import speech as SP2
        whole = SP2.nav_intent({"segments": segments, "pass": n_ok, "fail": n_fail, "total": total})
    except Exception as e:
        whole = None
        print("  （★整体 Intent 出错：%r✗★）" % (e,))
    if whole is not None:
        print("  ★要说的话✗★：kind=%s ／ %s" % (whole.kind, whole.why))
    print("SUMMARY task pass=%d fail=%d total=%d dry=%d"
          % (n_ok, n_fail, total, 1 if dry else 0))
    return (n_fail == 0 and total == len(goals)), {"segments": segments,
                                                   "pass": n_ok, "fail": n_fail,
                                                   "total": total, "dry": dry}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goals", required=True, help='目标列表："x,y,z;x,y,z;…"')
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--max-per-seg", type=int, default=400)
    ns = ap.parse_args()
    try:
        goals = parse_goals(ns.goals)
    except ValueError as e:                    # ★不许静默✗★
        print("★参数错✗★：%r" % (e,))
        print("SUMMARY task pass=0 fail=0 total=0 dry=%d" % (1 if ns.dry else 0))
        return 2
    if not goals:
        print("★没有目标✗★")
        print("SUMMARY task pass=0 fail=0 total=0 dry=%d" % (1 if ns.dry else 0))
        return 2
    ok, _rep = run_goals(goals, dry=ns.dry, max_per_seg=ns.max_per_seg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
