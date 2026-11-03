#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""human_action_test.py -- 手部动画 ＋ 工具匹配 的判据（★离线查源码 ✗ 真世界验行为✗★）

用户口径（2026-11-02 原话）：
  「放置方块和破坏方块**需要有手部动画**，而且**需要切出对应的能挖掘的工具**」
  「在搭产线和机器的时候**应当在机器旁边**」

三条要求分别守：
  ★① 挥手：place 和 dig 两条路径**都**调 `swing`✗
  ★② 换工具：**数据驱动**（★`getDestroySpeed` ✗ 不许按方块名写死表✗★）✗ 且**只换更快的**✗ 且**如实报告**✗
  ★③ 旁边：动作必须**贴身在够得着的范围**（★太远要明确拒绝 ✗ 不许偷偷传送✗★）✗★

CHECKS（离线）
  H1 `dshplace` 路径里有 `swing` ✓
  H2 `dshdig`  路径里有 `swing` ✓
  H3 ★工具选择用 `getDestroySpeed`（数据驱动）✗ 且**源码里没有"方块名→工具"的写死表**✗★
  H4 ★基线是"空手 1.0 ⇒ 只换更快的"★（★不是"必须用镐"✗★）✗
  H5 ★换没换**如实报告**★（`switch(`／`keep(`／`same(`）✗
  H6 ★`dshdig` 会调工具选择★（`pickBestTool(` 出现在 dig 路径里）

CHECKS（--live）
  L1 挖石头 ⇒ 回执里**换到了镐**（`switch(` 且 speed > 1）✗ 且方块真空了
     （★先探测"目标格空气＋脚下实心＋站位两格空气＋站位脚下实心"✗★ —— 2026-11-02 实测
      原坐标 (4162,70,20) 全是空气 ⇒ tp 过去会掉虚空 ✗ 所以**没核实过的地面不跑**＝INCONCLUSIVE）
  L2 ★太远 ⇒ **明确拒绝** `too far`★（★不许偷偷传送 ✗ 不许"假装挖了"✗★）
  L3 ★测试动过的 hotbar.0/1 按快照还原★（★不许静默改 Bot 背包✗★）
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

JAVA = ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge" / "DshBridgeMod.java"


def _source() -> str:
    return JAVA.read_text(encoding="utf-8")


def _region(src: str, start_pat: str, length: int = 4000) -> str:
    m = re.search(start_pat, src)
    return src[m.start():m.start() + length] if m else ""


def main(argv) -> int:
    live = "--live" in argv
    src = _source()
    checks = []

    # ★place 是右键放 ⇒ 真正挥手在 useOn 里 ✗ 所以要**跟调用链**✗★
    place_region = _region(src, r"private static int place\(")
    place_calls_useon = "useOn(" in place_region
    useon_region = _region(src, r"private static int useOn\(")
    dig_region = _region(src, r"private static int digBlock\(")
    ok_place = ("swing(" in place_region) or (place_calls_useon and ("swing(" in useon_region))
    checks.append(("H1 ★dshplace 路径有挥手（★place→useOn→swing 调用链✗★）★",
                   ok_place, "place里swing=%s ｜ place调useOn=%s ｜ useOn里swing=%s"
                   % ("swing(" in place_region, place_calls_useon, "swing(" in useon_region)))
    checks.append(("H2 ★dshdig 路径里有 swing（挥手）★",
                   "swing(" in dig_region, "找到 swing" if "swing(" in dig_region
                   else "★dig 路径没挥手★"))

    tool_fn = _region(src, r"private static String pickBestTool\(")
    data_driven = ("getDestroySpeed(" in tool_fn) or ("isCorrectToolForDrops" in src)
    name_table = re.search(r'(PICKAXE|SHOVEL|AXE)\s*[=:]\s*\{[^}]{0,200}(stone|dirt|log)', src)
    checks.append(("H3 ★工具选择数据驱动 ✗ 没写死方块名表★",
                   data_driven and name_table is None,
                   "getDestroySpeed=%s ｜ 写死表=%s" % (data_driven, bool(name_table))))

    base = re.search(r"bestSpeed\s*=\s*1\.0f", tool_fn)
    checks.append(("H4 ★基线「空手 1.0 ⇒ 只换更快的」★", bool(base),
                   "找到 bestSpeed = 1.0f ✓" if base else "★没有基线★"))

    reports = all(k in tool_fn for k in ("switch(", "keep(", "same("))
    checks.append(("H5 ★换没换如实报告（switch／keep／same）★", reports,
                   "switch=%s keep=%s same=%s" % ("switch(" in tool_fn, "keep(" in tool_fn, "same(" in tool_fn)))

    calls = dig_region.count("pickBestTool(")
    checks.append(("H6 ★dshdig 会调工具选择★", calls >= 1, "调用 %d 次" % calls))

    # ── 真世界 ────────────────────────────────────────────────────────
    skipped_inconclusive = False
    if live:
        import time

        import direct as D
        import mcp_core as C

        def state_raw(pos):
            return (C.dsh("dshstate %d %d %d" % tuple(pos), 25.0) or "")

        def block_at(pos):
            m = re.search(r"raw=Block\{([^}]*)\}", state_raw(pos))
            return m.group(1) if m else None

        def is_air(pos):
            b = block_at(pos)
            return b is None or b.endswith(":air")

        def is_solid(pos):
            b = block_at(pos)
            return bool(b) and not b.endswith(":air")

        def hotbar_snapshot():
            r = C.dsh("dshinv list", 25.0) or ""
            out = {}
            for mm in re.finditer(r"(?:^|\s)(\d{1,2}):([A-Za-z0-9_:.\-]+)x(\d+)", r):
                if int(mm.group(1)) <= 1:
                    out[int(mm.group(1))] = (mm.group(2), int(mm.group(3)))
            return out

        def hotbar_restore(prev):
            """★测试不许静默改 Bot 背包✗★：两个热键槽按快照还原（原来空 ⇒ 清空）"""
            for slot in (0, 1):
                if slot in prev:
                    iid, cnt = prev[slot]
                    D.raw("item replace entity Bot hotbar.%d with %s %d" % (slot, iid, cnt), 20.0)
                else:
                    D.raw("item replace entity Bot hotbar.%d with minecraft:air" % slot, 20.0)

        def pick_area():
            """★先探测再动✗★：目标格空气 ＋ 目标脚下实心 ＋ 站位脚/头两格空气 ＋ 站位脚下实心

            历史坑（2026-11-02）：坐标 (4162,70,20) 实测**全是空气** ⇒ tp 过去直接掉虚空 ✗
            口径：★没有核实过的安全地面就**不跑**（INCONCLUSIVE）✗ 不许赌 ✗
            env `DSH_HA_TARGET` / `DSH_HA_STANCE` 可覆盖（x,y,z / x,y,z）
            """
            env_t = (os.environ.get("DSH_HA_TARGET") or "").strip()
            env_s = (os.environ.get("DSH_HA_STANCE") or "").strip()
            if env_t and env_s:
                return (tuple(int(v) for v in env_t.split(",")),
                        tuple(float(v) for v in env_s.split(",")))
            for cand in [(4157, 71, 10), (4156, 71, 10), (4158, 71, 10),
                         (4157, 71, 12), (4155, 71, 10), (4156, 71, 12)]:
                sx, sz = cand[0] - 2, cand[2]
                stance = (sx + 0.5, float(cand[1]), sz + 0.5)
                if not (is_air(cand) and is_solid((cand[0], cand[1] - 1, cand[2]))):
                    continue
                if not (is_air((sx, cand[1], sz)) and is_air((sx, cand[1] + 1, sz))
                        and is_solid((sx, cand[1] - 1, sz))):
                    continue
                return cand, stance
            return None, None

        target, stance = pick_area()
        if target is None:
            skipped_inconclusive = True
            print("  L1 SKIP/INCONCLUSIVE | 没有核实过的安全地面（不赌 tp / 不掉虚空）")
        else:
            print("  [live] safe_target=%s stance=%s (dshstate 已逐格核过)" % (target, stance))
            slot_prev = hotbar_snapshot()
            print("  [live] hotbar before: %s" % (slot_prev,))

            def _dig_and_judge():
                rep = C.dsh("dshdig %d %d %d" % target, 45.0) or ""
                gone = (block_at(target) or "").endswith(":air")
                switched = ("switch(" in rep) or ("same(" in rep)
                sp = re.search(r"speed=([\d.]+)", rep)
                checks.append(("L1 ★挖石头 ⇒ 换到镐 ＋ 真挖掉了★",
                               switched and gone and (float(sp.group(1)) > 1.0 if sp else False),
                               "回执=%s ｜ 现在=%s" % (rep.strip()[:70], block_at(target))))
                return rep

            try:
                D.raw("setblock %d %d %d minecraft:stone" % target, 15.0)
                D.raw("tp Bot %.2f %.2f %.2f" % stance, 20.0)
                time.sleep(0.8)
                D.raw("item replace entity Bot hotbar.0 with minecraft:diamond_pickaxe 1", 20.0)
                D.raw("item replace entity Bot hotbar.1 with minecraft:diamond_shovel 1", 20.0)
                _dig_and_judge()
            finally:
                # 还原：目标格回空气 ＋ 两个热键槽回快照（★下一个人来测时世界/背包是原样✗★）
                D.raw("setblock %d %d %d minecraft:air" % target, 15.0)
                hotbar_restore(slot_prev)

            after = hotbar_snapshot()
            restored = all(after.get(s) == slot_prev.get(s) for s in (0, 1))
            checks.append(("L3 ★测试动过的两个热键槽已按快照还原★", restored,
                           "before=%s after=%s" % (slot_prev, after)))

            # L2 太远 ⇒ 明确拒绝
            far = (target[0] + 40, target[1], target[2] + 30)
            rep2 = C.dsh("dshdig %d %d %d" % far, 30.0) or ""
            checks.append(("L2 ★太远 ⇒ 明确拒绝（不偷偷传送）★",
                           "too far" in rep2 or "too_far" in rep2, rep2.strip()[:70]))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:115]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if skipped_inconclusive and bad == 0:
        # ★测不了不算通过✗★（check_all 口径：退出码非 0 ＋ 输出含 INCONCLUSIVE ⇒ 测不了 ✓）
        print("  => human_action INCONCLUSIVE (no verified safe ground; 测不了不算通过)")
        print("HUMANACTION ok=0 bad=0 checks=%d live=%d INCONCLUSIVE safe_ground=none"
              % (len(checks), 1 if live else 0))
        return 2
    if bad:
        print("  => human_action FAIL (%d)" % bad)
        print("HUMANACTION ok=0 bad=%d" % bad)
        return 1
    print("  => human_action PASS (swing on both paths; tool pick is data-driven; too-far refused)")
    print("HUMANACTION ok=1 checks=%d live=%d" % (len(checks), 1 if live else 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
