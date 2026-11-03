#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_coverage_test.py -- ★判据有没有**进闸门**★（C1~C4 ✗ 离线 ✗ 2026-10-18 §79.319）

★为什么有它✗★（★§79.308 那条"★判据没进闸门 ＝ 它不存在★"✗★）✗★：
  ★`hop_cost.py` 里**早就有**"★建图次数 ≤2★"这条判据 ✗ 却**从来不在 `GATE` 里**✗★ ⇒
  ★于是"★`t_route_view` 每次重建 4 张图★"**一直没人管**✗★ ✓
★判法✗★：
  ★盘上每个 `tools/*.py` ✗ 只要它**同时**写了 `PASS` 与 `FAIL`（★说明它是个**会判红的判据**✗★）✗★
  ⇒ ★它**必须**在 `GATE` 的某张表里 ✗ 或者在同一张**声明表**里带**理由**✗★ ✓
★声明的那些**不许悄悄变多**✗★：★`C4` 拿**基线数**比（★§79.271 那条"★未声明的数只许变小★"✗★）✗★ ✓
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★★声明表✗★★：★这些是"★像判据但不是闸门项★"的 ✗ 每条要有理由✗★ ✓
DECLARED = {
    # 名: 理由
    "smoke_all.py": "★冒烟总跑 ✗ 不是判据本身（★它转述别的判据✓★）",
    "d3_soak.py": "★浸泡压测 ✗ 手动跑 ✗ 不进闸门（★世界侧 ✗ 要长窗口✓★）",
    "d3_walk_soak.py": "★同上✗★（★浸泡✗★）",
    "d3_work_soak.py": "★同上✗★（★浸泡✗★）",
    "kb_bench.py": "★微基准 ✗ 只报数不判红（★§79.92✗★）",
    "go_now.py": "★入口向导 ✗ 不是判据✗★",
    "export_arrived.py": "★导出回来的一次性链 ✗ 不是闸门项（★它自己跑一串判据✗★）",
    "e1_window.py": "★实机窗口跑单 ✗ 用户在场才跑✗★",
    "drop_semantics_test.py": "★要世界（★drop: 只禁下坡的蹦 ✗ 上台阶必需的跳必须允许✗★）✗ "
                              "进 world_regress 跑 ✗ 手动实机（★§79.454✗★）",
    "world_audit.py": "★oracle ✗ 只报数不判红 ✓ 不进闸门（★§79.302✗★）",
    "model_check.py": "★要世界（★拿 dshscan 单格核世界模型 ✗ 离线造不出✗★）✗ 手动实机跑（★§79.371✗★）",
    "height_conv_test.py": "★要世界（★拿 digest 的 y ＋ dshscan 核「脚格／支撑格」约定✗★）✗ 手动实机跑（★§79.372✗★）",
    "house_nav_test.py": "★要世界（**进屋回归** ✗ 规划开门 ＋ 执行到达 ＋ 人在屋内 ＋ 门没被挖✗★）✗ 手动实机跑（★§79.398✗★）",
    "world_regress.py": "★要世界（**一键实机回归** ✗ 串起 model_check／height_conv／collision_classes／house_nav ✗ 游戏不通记†测不了†✗★）✗ 手动实机跑（★§79.422✗★）",
    "motion_stat_test.py": "★要世界（**运动统计判据** ✗ 跑／跳／速度全由模组 do_done 的 move= 报数 ✗ 不看人眼 ✗ §79.436✗★）✗ 手动实机跑",
    "truth_measure.py": "★真值实测尺 ✗ 会改世界 ✗ 不进闸门✗★",
    "respawn_bot.py": "★拉假人 ✗ 施工工具✗★",
    "postrestart_check.py": "★重启后自检 ✗ 手动跑✗★",
    "acp_probe.py": "★通道探针 ✗ 施工工具✗★",
    "credit_check.py": "★信用检查 ✗ 手动✗★",
    "ladder_probe.py": "★梯子探针 ✗ 施工✗★",
    "slice_check.py": "★切片检查 ✗ 施工✗★",
    "check_all.py": "★闸门本体 ✗ 自己不能是闸门项（★自指✗★）✗★",
    "mc_mcp_smoke.py": "★MCP 工具冒烟 ✗ 手动跑（★它测的是 stdio 契约 ✗ 不是世界✗★）✗★",
    "acp_act_test.py": "★要 **ACP 大脑 ＋ 世界**（★“resident brain 能不能真的移动假人”✗★）✗ 不是离线闸门项 ✗ 手动实机跑✗★",
    "ob_test.py": "★“识别道中障碍物”的验收 ✗ **要世界**（★道中障碍 ✗ 离线造不出✗★）✗★",
    "r3_twomode.py": "★世界侧两模式对照 ✗ 手动实机跑✗★（★未书面化 ✗ 待补一句理由 ✗ 但不许漂✗★）",
    "runbook_after_restart.py": "★重启后按跑单自检 ✗ 世界侧 ✗ 手动✗★",
    "speech_live_test.py": "★执行者（★语音 ✗ speech✗★）侧 ✗ **不在本任务书范围**✗★",
    "speech_relay_live_test.py": "★同上（★中继✗★）✗ 不在范围✗★",
    "stash2.py": "★施工小工具 ✗ 不是判据（★它的 PASS/FAIL 是“干完了吗”✗★）✗★",
    "step_assist.py": "★施工小工具 ✗ 不是判据✗★",
    "v2120_check.py": "★v2.12 的一次性版本检查 ✗ 历史工具✗★",

    "v2130_check.py": "★v2.13 的一次性版本检查 ✗ 历史工具（★与 v2120_check 同类✗★）✗★",
    "falsify_sweep.py": "★反驳扫描（机制版）✗ **会改源码** ⇒ 不能当闸门项（★改了立刻还原✗★）✗ §79.324／§79.325: 每条的故障是照着它声明守护的那个点造的, 跑完按**原字节**写回✗★",
    "soak_suite.py": "★D3 压测 **runner** ✗ 要游戏 ＋ 长窗口（3h×3 夜）✗ 不进离线闸门 ✓（它的判据是 `soak_suite_test.py` ✗ 离线进 GATE ✗ 2026-11-02 接手轮 §79.523）★",
    "release.py": "★发版链 **操作工具** ✗ 不是判据本体（它按当前仓/当前 jar 判 PASS/BLOCK ✗ 依赖真实工作区与 git 状态 ✗ "
                  "进闸门会随未提交改动假红 ✓）✗ 判据是 `release_check_test.py`（假项目离线可红 ✗ 已进 GATE ✗ 2026-11-02 第二轮 §79.531）★",
}
BASELINE_FILE = ROOT / "state" / "gate_coverage_baseline.json"


def looks_like_judge(src: str) -> bool:
    """★像判据✗？★条件：★同时**写死** `PASS` 与 `FAIL` ✗ 且有一条 `=> ` 结论行**✗★ ✓"""
    has_pass = '"PASS' in src or "'PASS" in src or 'PASS ✓' in src
    has_fail = '"FAIL' in src or "'FAIL" in src or 'FAIL（' in src
    has_arrow = "=>" in src
    return has_pass and has_fail and has_arrow


def main() -> int:
    ok = [True]
    gate_src = (ROOT / "tools" / "check_all.py").read_text(encoding="utf-8")
    # ★`GATE` 里出现过的脚本名✗★
    gate_names = set(re.findall(r'\("([A-Za-z0-9_]+\.py)"', gate_src))

    judges, unlisted, declared_hit = [], [], []
    for p in sorted((ROOT / "tools").glob("*.py")):
        try:
            src = p.read_text(encoding="utf-8")
        except Exception as e:
            # 记录：读不到一个 .py ⇒ 可能漏数一个"像判据"的脚本（C1 可能假绿）
            print("  ★记录✗★ C1 读不到（少看一个 .py ⇒ 可能假绿）：%s（%s）"
                  % (p.name, type(e).__name__))
            continue
        if not looks_like_judge(src):
            continue
        judges.append(p.name)
        if p.name in gate_names:
            continue
        if p.name in DECLARED:
            declared_hit.append(p.name)
            continue
        unlisted.append(p.name)

    print("== gate_coverage: C1~C4 ==")
    print("  ★像判据的脚本（★写死 PASS/FAIL ＋ 有 `=> `✗★）= **%d** 个" % len(judges))
    print("  ★在 `GATE` 里✗★ = **%d** ｜ ★声明豁免✗★ = **%d** ｜ ★**两边都不是**✗★ = **%d**"
          % (len([j for j in judges if j in gate_names]), len(declared_hit), len(unlisted)))
    if unlisted:
        print("  ★★没进闸门也没声明（★这才是要治的✗★）✗★：" % ())
        for n in unlisted[:12]:
            print("     · %s" % n)
    ok[0] &= not unlisted
    print("  C1   %s ★像判据的**必须**在 `GATE` 里 ✗ 或**声明＋理由**★"
          % ("✓" if not unlisted else "不符合"))

    # ★C2 声明表里不许有**已经进了闸门**的（★要么声明 ✗ 要么进表 ✗ 不许两头占✗★）
    both = [n for n in DECLARED if n in gate_names]
    ok[0] &= not both
    print("  C2   %s ★声明表与 `GATE` 不许两头都占✗★ ⇒ %s"
          % ("✓" if not both else "不符合", both or "（没有 ✓）"))

    # ★C3 计数器✗★：扫过的 .py 数 与 像判据的数 都要 > 0（★不许"★一个都没扫★"✗★）
    n_all = len(list((ROOT / "tools").glob("*.py")))
    ok[0] &= n_all > 0 and len(judges) > 0
    print("  C3   %s ★计数器✗★：扫过 **%d** 个 .py ✗ 其中像判据 **%d** 个（★都 > 0 ✗ 不许空转✓★）"
          % ("✓" if (n_all and judges) else "不符合", n_all, len(judges)))

    # ★C4 未声明的数**只许变小**✗★（★基线落盘 ✗ §79.271 同一个模式✗★）
    n_un = len(unlisted)
    base = None
    if BASELINE_FILE.is_file():
        try:
            base = int(json.loads(BASELINE_FILE.read_text(encoding="utf-8")).get("unlisted"))
        except Exception:
            base = None
    if base is None:
        BASELINE_FILE.write_text(json.dumps({"unlisted": n_un, "at": "2026-10-18",
                                             "why": "★基线 ✗ 以后只许变小✗★"},
                                            ensure_ascii=False, indent=1), encoding="utf-8")
        print("  C4   ✓ ★第一次跑 ✗ 基线已落 `state/gate_coverage_baseline.json`（★未声明 ＝ %d✗★）"
              % n_un)
    else:
        ok[0] &= n_un <= base
        print("  C4   %s ★未声明只许变小✗★：基线 **%d** ⇒ 现在 **%d**"
              % ("✓" if n_un <= base else "不符合", base, n_un))

    print("")
    if unlisted:
        print("  ★治法✗★：★要么把它挂进 `GATE` ✗ 要么在 `DECLARED` 里写理由 ✗ 二者选一✗★")
    print("=> gate_coverage %s" % ("PASS ✓" if ok[0] else "FAIL"))
    sys.stdout.write("GATECOVERAGE ok=%d judges=%d ingate=%d declared=%d unlisted=%d\n"
                     % (1 if ok[0] else 0, len(judges),
                        len([j for j in judges if j in gate_names]),
                        len(declared_hit), len(unlisted)))
    return 0 if ok[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
