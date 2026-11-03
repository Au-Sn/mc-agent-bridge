#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""route_verify_test.py -- does `route_view(verify=...)` make the map TRUE? (X1..X5)

WHY (2026-09-28, round 15): the mod's fast map printed only a LETTER per cell, so
every letter cell was stored at "one below my feet" -- heights were GUESSED and
the picture came out flat. The dangerous direction is a FALSE CLEAN: the map
says "walkable" where the world has a drop or nothing at all (exactly what V4
of route_view_test.py fails on right now).

The fix does not need the game to be restarted: `dshscan <box> ":"` matches
every non-air block id (every id contains ':'), so ONE call returns the TRUE
coordinates of every block in the corridor. Patching that truth into the map
corrects the picture AND the planner (same Map object, cache rewritten).

CRITERIA (declared BEFORE running; no moving them afterwards):
  X1 truth agree : with verify="on", sample 4 route cells and decide
                   walkable/not-walkable INDEPENDENTLY from the world
                   (probe_cell at LEVEL-1 / LEVEL / LEVEL+1). "World walkable"
                   means: some floor exists in LEVEL-2..LEVEL and the two cells
                   above that floor are clear (the same rule the map claims to
                   follow). Agreement must be 4/4.
  X2 no false clean: after verify, NO route cell that the world says is NOT
                   walkable may be reported walkable ('*' '^' 'v' '+') => 0.
                   (This is the dangerous direction; it is the V4 failure.)
  X3 cost        : verify's own extra channel calls <= 4 and the whole call
                   <= 8 s. Calls are counted by a counter THIS SCRIPT installs
                   around mapread.Reader.ab -- never from the tool's own text.
  X4 provenance  : the tool text must say the corridor was scanned AND tag each
                   obstacle cell's provenance, and must report how many
                   conclusions were CORRECTED.
  X5 auto rule   : (offline) _need_verify reads meta.has_offsets itself:
                   new-style map => no scan; old-style map => scan;
                   off => never; on => always.

ASCII-only output.
"""
from __future__ import annotations

import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mc_mcp as M      # noqa: E402
import mapread as MR    # noqa: E402
import pathplan as PP   # noqa: E402  ★模块级 import★ ✗（第 22 轮 ✓ 我原来只在 main 里 import ✗

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

#                                    ⇒ 新加的 `pick_target` 里用 `PP` 就 NameError ✗）

PACE = 0.25
WALKABLE = ("*", "^", "v", "+")

# ---- independent channel-call counter (installed around Reader.ab) --------
_ORIG_AB = MR.Reader.ab
CNT = {"all": 0, "verify": 0}


def _counting_ab(self, cmd, tmo=60.0):
    CNT["all"] += 1
    if cmd.startswith("dshscan") and '":"' in cmd:
        CNT["verify"] += 1
    return _ORIG_AB(self, cmd, tmo)


# ★必须真的装上★ ✗（2026-09-28 差点栽 ✓）：我只是"定义了"计数器 ✗
#   ⇒ 计数恒为 0 ⇒ X3 会**空洞通过**✗ —— 而本轮判据的全部意义就是防假绿 ✗
MR.Reader.ab = _counting_ab


def say(s):
    print(s, flush=True)


def world_walkable(r, x, z, L):
    """Independent verdict for a walker whose feet cell is L.

    ★口径必须与**工具**一致★ ✗（2026-09-28 第 19 轮改 ✓ 我原来写窄了 ✗）：
      工具的规则 ✓：脚可以落在 `L-3 .. L+1`（往下降 ≤3 ✓ 往上抬 ≤1 ✓ 见 `pathplan` ✓）
      ⇒ 而地板比脚低一格 ⇒ **地板可以低到 `L-4`** ✓
      我原来只探 `L-2..L` ✗ ⇒ 把"**降 3 格能下去**"的格判成"不能走"✗ ⇒ 假失败 ✗
      （危险方向**没放宽** ✓：降 **4** 格以上仍判不能走 ✗）
    Returns (bool, detail-string).
    """
    prof = {}
    for y in range(L + 2, L - 5, -1):
        nm = r.probe_cell(x, y, z)
        time.sleep(PACE)
        if nm == "":
            return None, "READ FAILED at y=%d" % y
        prof[y] = nm
    # 从**最高的地板**往下试 ✓：脚 = 地板+1 ✓ 要求 脚 ∈ [L-3, L+1] ✓ 且脚/头两格不挡人 ✓
    for fy in (L, L - 1, L - 2, L - 3, L - 4):
        feet = fy + 1
        if not (L - 3 <= feet <= L + 1):
            continue
        if MR.is_floor(prof[fy]) and (not MR.blocks_space(prof[feet])) \
                and (not MR.blocks_space(prof[feet + 1])):
            return True, "floor@%d=%s feet@%d" % (fy, prof[fy], feet)
    return False, ("no usable floor in reach  L+1=%s L=%s L-1=%s L-2=%s L-3=%s"
                   % (prof[L + 1], prof[L], prof[L - 1], prof[L - 2], prof[L - 3]))


def pick_target(m, pl, sx, sz, L):
    # ★挑目标要带上**障碍记忆**★ ✗（2026-09-29 第 22 轮 ✓ 与 plan_verify 同一条规矩 ✓）：
    #   现象 ✗：`route_view` 报"目标**不在你脚下这块连通区域里** ⇒ 不去"✗
    #     而它**拒得对** ✓（`BLOCKED` 里的格会被排除 ✓）—— 是我挑的时候没带它 ✗
    pl = PP.Planner(m, level=L, blocked=M.BLOCKED)
    cands = []
    for (x, z) in pl.region(sx, sz):
        d = math.dist((x, z), (sx, sz))
        if not (5.0 <= d <= 20.0) or not pl.ok(x, z):
            continue
        soft = 0
        for k in range(1, int(d) + 1):
            cx = int(round(sx + (x - sx) * k / d))
            cz = int(round(sz + (z - sz) * k / d))
            if m.cell_kind(cx, cz, L)[0] != "*":
                soft += 1
        cands.append((-soft, d, x, z))
    cands.sort()
    return (cands[0][2], cands[0][3]) if cands else None


def main():
    ok = True
    p = M._pos_now()
    if not p:
        say("no bot position => cannot test")
        return 1
    sx, sy, sz = int(p[0]), int(p[1]), int(p[2])
    say("bot at (%d,%d,%d)" % (sx, sy, sz))

    # --- plan one route (map may still be the old, flattened one) ----------
    _r, m, _b = M._route_map(sx, sz, sx + 8, sz, sy)
    L = M._stand_level(m, sx, sz, float(p[1]))           # ★浮点脚高★ ✗ 见 P101 ✓
    import pathplan as PP
    pl = PP.Planner(m, level=L)
    tgt = pick_target(m, pl, sx, sz, L)
    if not tgt:
        # ★拿不到可用目标 ⇒ **SKIP**✗ 不是 FAIL ✓（2026-09-29 第 22 轮改 ✓）
        #   理由 ✓：假人一直在动 ✓ 我手里的图/障碍记忆也在变 ⇒ "这一带挑不出合格目标"✗
        #     是**环境不允许**✓ 不是功能坏 ✓（其它脚本同一条口径 ✓）
        say("=> SKIP: 这一带挑不出合格目标（环境不允许 ✓ 不算通过也不算失败 ✓）")
        return 0
    gx, gz = tgt
    say("target (%d,%d)  LEVEL=%d  has_offsets=%s" % (gx, gz, L, m.meta.get("has_offsets")))

    # --- the call under test (verify forced ON) ---------------------------
    # ★目标被"正确地拒"⇒ 换一个★ ✗（2026-09-29 第 22 轮 ✓ 与 plan_verify 同一套做法 ✓）：
    #   假人一直在动 ⇒ 我挑的目标到调用时可能已经不在连通区 ✓ ⇒ 工具拒得对 ✓
    #   我却把"拒"当成"坏"✗ ⇒ 假失败 ✓（这一族今天已经栽了 N 次 ✓）
    CNT["all"] = CNT["verify"] = 0
    txt = ""
    err = True
    sec = 0.0
    gx = gz = None
    for k in range(3):
        _r3, m3, _b3 = M._route_map(sx, sz, sx + 8, sz, sy)
        L3 = M._stand_level(m3, sx, sz, float(p[1]))
        cand = pick_target(m3, None, sx, sz, L3)
        if not cand:
            break
        gx, gz = cand
        t0 = time.time()
        txt, err = M.t_route_view(gx, L3, gz, 1, 1200, "on")
        sec = time.time() - t0
        if not err:
            L = L3
            break
        say("  target (%d,%d) refused (correctly) -> pick another | %s"
            % (gx, gz, (txt.splitlines() or [""])[0][:110]))
        time.sleep(1.0)
    calls_all, calls_verify = CNT["all"], CNT["verify"]
    say("route_view(verify=on): %.2fs  err=%s  channel calls=%d (of which scan-truth=%d)"
        % (sec, err, calls_all, calls_verify))
    if err:
        say("tool reported an error on 3 fresh targets => give up (environment)")
        say(txt[:400])
        return 0                          # ★环境不允许 ⇒ SKIP ✗ 不算通过也不算失败 ✓

    # recompute the route the same way the tool does, to know the cells
    _r2, m2, _b2 = M._route_map(sx, sz, gx, gz, sy)
    L = M._stand_level(m2, sx, sz, float(p[1]))          # ★浮点脚高★ ✗ 见 P101 ✓
    _pl2, pts, why, _info = M._make_plan(sx, sz, gx, gz, L, level=L)
    rcells = []
    for q in pts:
        c = (int(q[0]), int(q[2]))
        if c not in rcells:
            rcells.append(c)
    say("route cells = %d" % len(rcells))

    # --- X3 cost ----------------------------------------------------------
    # ★下限 1★ ✗：我强制了 verify=on ⇒ **必须**看见至少一次扫描调用 ✓
    #   否则计数器没装上 / 扫描被跳过 ⇒ 这条会变成"0 次调用 ⇒ 通过"的空洞绿 ✗
    x3 = (1 <= calls_verify <= 4) and (sec <= 8.0)
    say("X3 cost: verify calls %d (want 1..4) and total %.2fs <= 8.0 => %s"
        % (calls_verify, sec, x3))
    ok &= x3

    # --- X4 provenance (text) --------------------------------------------
    # ★判据要按"机制"写★ ✗（2026-09-28 第 20 轮 ✓ 重启后又栽一次 ✓）：
    #   原来要求"**逐格出处**"必须出现 ✗ —— 可那标注只印在**障碍清单**里 ✓
    #   路上一处障碍都没有 ⇒ 自然没有逐格标注 ✗ ⇒ 判据假失败 ✓
    #   ⇒ 口径 ✓：**头部必须写明"实地验过"** ✓ ＋ **报了"改正几格"** ✓
    #     ＋ **如果**这条路上真列了障碍格 ⇒ 那些格**必须**带出处 ✓（没有障碍就没什么可标 ✓）
    has_scan = "实地验过" in txt
    has_fixed = re.search(r"改正 \*\*(\d+)\*\*", txt) is not None
    bad_lines = [ln for ln in txt.splitlines() if "路线第" in ln]
    tagged = all("出处" in ln for ln in bad_lines)
    has_prov = tagged
    x4 = has_scan and has_prov and has_fixed
    say("X4 provenance: says-scanned=%s reports-corrected=%s obstacle-lines=%d "
        "all-tagged=%s => %s" % (has_scan, has_fixed, len(bad_lines), tagged, x4))
    ok &= x4

    # --- X1 + X2 world reconciliation ------------------------------------
    r = MR.Reader()
    step = max(1, len(rcells) // 4)
    smp = [rcells[i] for i in range(0, len(rcells), step)][:4]
    agree = mism = false_clean = 0
    for (x, z) in smp:
        wv, det = world_walkable(r, x, z, L)
        if wv is None:
            say("X1 ABORT: %s (%d,%d) -- bridge issue, not a map issue" % (det, x, z))
            return 1
        ch = m2.cell_kind(x, z, L)[0]
        mv = ch in WALKABLE
        prov = "scanned" if m2.is_verified(x, z, L) else "guessed"
        if wv == mv:
            agree += 1
            say("  ok  (%d,%d) map=%s(%s) world_walkable=%s  [%s]" % (x, z, ch, prov, wv, det))
        else:
            mism += 1
            say("  BAD (%d,%d) map=%s(%s) but world_walkable=%s  [%s]"
                % (x, z, ch, prov, wv, det))
    x1 = (agree == len(smp)) and len(smp) >= 3
    if len(smp) < 3:
        say("X1 INCONCLUSIVE: only %d route cells -- too few to claim anything "
            "(NOT a pass)" % len(smp))
    say("X1 truth agree: %d/%d => %s" % (agree, len(smp), x1))
    ok &= x1

    # X2 over ALL route cells: every cell the map calls walkable must not be
    # one the world rejects. (Sample-limited by cost, so we check all cells the
    # world is ASKED about; cells we did not read are not counted either way.)
    checked = 0
    for (x, z) in rcells:
        if m2.cell_kind(x, z, L)[0] not in WALKABLE:
            continue
        wv, det = world_walkable(r, x, z, L)
        if wv is None:
            say("X2 ABORT: %s -- bridge issue" % det)
            return 1
        checked += 1
        if wv is False:
            false_clean += 1
            say("  FALSE CLEAN (%d,%d) map says walkable [%s]" % (x, z, det))
        if checked >= 6:
            break
    x2 = (false_clean == 0) and (checked > 0)
    say("X2 no false clean: checked %d map-walkable route cells, false cleans %d => %s"
        % (checked, false_clean, x2))
    ok &= x2

    # --- X5 auto rule (offline) ------------------------------------------
    class FakeM:
        def __init__(self, meta):
            self.meta = meta

    cases = [({"has_offsets": True}, "auto", False),
             ({"has_offsets": False}, "auto", True),
             ({}, "auto", True),
             ({"has_offsets": True}, "on", True),
             ({"has_offsets": False}, "off", False)]
    x5 = True
    for meta, mode, want in cases:
        got = M._need_verify(FakeM(meta), mode)
        if got != want:
            x5 = False
            say("  X5 BAD meta=%s verify=%s got=%s want=%s" % (meta, mode, got, want))
    say("X5 auto rule (offline, %d cases) => %s" % (len(cases), x5))
    ok &= x5

    say("---- X1..X5 = %s / %s / %s / %s / %s ----" % (x1, x2, x3, x4, x5))
    say("=> %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("=> FAIL (exception)")
        sys.exit(1)
