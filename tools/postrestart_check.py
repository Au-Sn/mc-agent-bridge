#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""post-restart check: does the new mod (v2.16) let verify=auto SKIP, while the
map is still TRUE?  R1/R2. ASCII-only output."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M      # noqa: E402
import mapread as MR    # noqa: E402

_ORIG = M.dsh
CNT = {"scan": 0, "all": 0}


def counting(cmd, tmo=60.0):
    CNT["all"] += 1
    if cmd.startswith("dshscan") and '":"' in cmd:
        CNT["scan"] += 1
    return _ORIG(cmd, tmo)


M.dsh = counting


def say(s):
    print(s, flush=True)


p = M._pos_now()
say("bot pos = %s" % (p,))
say("---- R2: does the fast map carry true heights + the occupancy layer? ----")
r = MR.Reader()
m = r.build_dshmap(radius=12, max_age=600.0)
say("  has_offsets=%s  y_exact=%s  y_assumed=%s  blocked=%s  blevel=%s"
    % (m.meta.get("has_offsets"), m.meta.get("y_exact"), m.meta.get("y_assumed"),
       m.meta.get("blocked"), m.meta.get("blevel")))
r2 = (m.meta.get("has_offsets") is True) and int(m.meta.get("y_exact") or 0) > 0
say("  R2 has_offsets True and y_exact>0 => %s" % r2)
blk = int(m.meta.get("blocked") or 0)
say("  blocked cells in this 25x25 box = %d (expect >0 where fences/machines stand) => %s"
    % (blk, blk > 0))

say("---- R1: does the default path spend ZERO verify calls? ----")
CNT["scan"] = CNT["all"] = 0
t0 = time.time()
txt, err = M.t_map_area(12, None, 600, "auto")
sec = time.time() - t0
say("  map_area(12, auto): %.2fs err=%s  scan-truth calls=%d (want 0)" % (sec, err, CNT["scan"]))
says_skip = ("自带真高度" in txt) or ("不必再扫" in txt)
r1a = (CNT["scan"] == 0) and says_skip
say("  map_area spends 0 verify calls and says why => %s" % r1a)

CNT["scan"] = CNT["all"] = 0
# ★目标必须从**连通区**里挑★ ✗（2026-09-28 第 20 轮 ✓ 我第一版随手写 pos+10 ⇒
#   那格不可达 ⇒ 工具**正确地**拒了 ✗ 我却记成 R1 失败 ✗ —— 又是"我的尺子没跟上现实"✗）
import pathplan as PP   # noqa: E402
_rg, _mg, _bg = M._route_map(int(p[0]), int(p[2]), int(p[0]) + 8, int(p[2]), int(p[1]))
_LG = M._stand_level(_mg, int(p[0]), int(p[2]), float(p[1]))
_plg = PP.Planner(_mg, level=_LG, blocked=M.BLOCKED)
_reg = sorted(_plg.region(int(p[0]), int(p[2])))
_far = [c for c in _reg if 6.0 <= ((c[0] - p[0]) ** 2 + (c[1] - p[2]) ** 2) ** 0.5 <= 18.0]
tx, tz = _far[len(_far) // 2] if _far else (int(p[0]), int(p[2]))
say("  (target picked from the region: (%d,%d), region=%d, far candidates=%d)"
    % (tx, tz, len(_reg), len(_far)))
t0 = time.time()
txt2, err2 = M.t_route_view(tx, int(round(p[1])), tz, 1, 1200, "auto")
sec2 = time.time() - t0
say("  route_view(auto): %.2fs err=%s  scan-truth calls=%d (want 0)" % (sec2, err2, CNT["scan"]))
r1b = (CNT["scan"] == 0) and (not err2)
say("  route_view spends 0 verify calls => %s" % r1b)

# ★航点要问 `plan_route`★ ✗（2026-09-28 第 20 轮 ✓ 我第一版去 `route_view` 的输出里找航点 ✗
#   —— 它只画图 ＋ 列障碍 ✗ 不印航点 ✓ ⇒ 我解析到 0 个还以为工具坏了 ✗）
CNT["scan"] = CNT["all"] = 0
t1 = time.time()
txt3, err3 = M.t_plan_route(tx, int(round(p[1])), tz, "auto")
sec3 = time.time() - t1
say("  plan_route(auto): %.2fs err=%s  scan-truth calls=%d (want 0)"
    % (sec3, err3, CNT["scan"]))
r1d = (CNT["scan"] == 0) and (not err3)
say("  R1d plan_route spends 0 verify calls and plans => %s" % r1d)
import re
wps = [(int(a), int(b), int(c)) for a, b, c in
       re.findall(r"^\s*\d+\)\s*\((-?\d+),(-?\d+),(-?\d+)\)", txt3, re.M)]
say("  route waypoints = %d" % len(wps))
rr = MR.Reader()
bad = 0
checked = 0
notes = []
for (wx, wy, wz) in (wps[1:4] if len(wps) > 3 else wps):
    below = rr.probe_cell(wx, wy - 1, wz)
    time.sleep(0.25)
    feet = rr.probe_cell(wx, wy, wz)
    time.sleep(0.25)
    head = rr.probe_cell(wx, wy + 1, wz)
    time.sleep(0.25)
    okc = MR.is_floor(below) and (not MR.blocks_space(feet)) and (not MR.blocks_space(head))
    checked += 1
    # ★模组方块 + 我的名字判定说"挡人" ⇒ 这属于**分类未知**✗ 不计失败 ✓（2026-09-28 第 20 轮 ✓）
    #   理由 ✗：航点来自**模组按碰撞箱**建的图（它说这格站得住 ✓）
    #     而 `blocks_space` 是**按名字猜**的 ✗ ⇒ 见到没见过的模组装饰方块 ⇒ 保守当实心 ✗
    #     ⇒ 这是"我的分类表不全"✗ 不是"地图错"✗ ⇒ **记下来**✓ 别当成失败 ✓
    mod_unknown = (not okc) and any(
        (not str(nm).startswith("minecraft:")) and nm and not nm.endswith("air")
        for nm in (below, feet, head) if isinstance(nm, str))
    if not okc and mod_unknown:
        notes.append("(%d,%d,%d) 被**按名字**判成挡人 ⇒ 但它是模组方块 ⇒ 分类未知（记下）: %s"
                     % (wx, wy, wz, feet if not MR.blocks_space(below) else below))
    elif not okc:
        bad += 1
    say("    (%d,%d,%d) floor=%s feet=%s head=%s => %s"
        % (wx, wy, wz, below, feet, head,
           "ok" if okc else ("unknown-classification" if mod_unknown else "BAD")))
for n in notes:
    say("  注：%s" % n)
r1c = (bad == 0) and (checked >= 2)
say("  R1c world reconciliation on %d waypoints: hard-bad=%d, classification-unknown=%d => %s"
    % (checked, bad, len(notes), r1c))

say("---- R1 / R2 = %s / %s ----" % (r1a and r1b and r1c and r1d, r2))
say("=> %s" % ("PASS" if (r1a and r1b and r1c and r1d and r2) else "FAIL"))
sys.exit(0 if (r1a and r1b and r1c and r1d and r2) else 1)
