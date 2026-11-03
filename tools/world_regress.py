#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world_regress.py -- ★一键实机回归（★世界侧判据串起来跑✗★）（§79.422）

★★为什么✗★★：★世界侧判据散在 15＋ 个脚本里 ✗ 每次要**手动一个个跑**✗★
　★⇒ ★回归靠人 ✗ 一忙就漏 ✗ 而"★漏了的判据等于不存在★"✗★ ✓
★★本工具✗★★：★一条命令跑完**世界侧判据**✗ 每个打 PASS／FAIL／†测不了†✗ 末尾打 SUMMARY✗★
★★口径✗★★：★游戏不通（★`dshdigest` 读不到✗★）⇒ **所有世界侧判据都记 †测不了†**
　★**不是失败** ✗ 这正是项目口径（★测不了 ≠ 通过 ✗ 也 ≠ 失败✗★）✗★ ✓
★用法✗★：★`py -B -u -X utf8 tools/world_regress.py [--only name,name]`✗★ ✓
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "tools")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent

# ★世界侧判据（★要游戏 ✗ 顺序按"★快 → 慢✗★"排✗★）✗★
JUDGES = [
    ("collision_classes", "collision_classes_test.py", "★碰撞高度按类（★离线也能跑✗★）✗★"),
    ("model_check", "model_check.py", "★世界模型保真度 24 格✗★"),
    ("height_conv", "height_conv_test.py", "★脚格／支撑格约定 C1~C6✗★"),
    ("house_nav", "house_nav_test.py", "★进屋全程 8 项（★规划＋执行＋在屋里✗★）✗★"),
    ("motion_stat", "motion_stat_test.py", "★运动统计：跑／跳／速度（★模组自己报数 ✗ 不靠人眼✗★）✗★"),
    ("action_type", "action_type_test.py", "★动作类型：jump／drop／parkour／open_door 真的改变行为（★不看画面 ✗ 看 move= 的 jumps✗★）"),
    ("take_item", "take_item_test.py", "★取物品：真的取到 ＋ 拿不到说实话 ＋ **用完放回 ✗ 世界净零**（★成品标准 1✗★）"),
    ("drop_semantics", "drop_semantics_test.py", "★drop: 只禁下坡的蹦 ✗ 上台阶必需的跳必须允许（★2.41.0 修 ✗ §79.454✗★）"),
    ("walk_soak", "walk_soak_test.py", "★长走／贴边 3 分钟 ✗ 不许改世界（★pillar=0✗★）✗ 不许掉血／丢物／卡死（★§79.476✗★）"),
    ("perceive", "perceive_test.py", "★感知层：快照与真值一致 ＋ 分类被问过 ＋ 机器带朝向 ＋ 缓存 0 往返（★§79.489✗★）"),
]


def game_up() -> bool:
    """★游戏通吗✗★：★`dshdigest` 里有 `pos=`** ✗★"""
    # ★★§79.426✗★★：★**判游戏通要看 dshver** ✗ 不是 dshdigest✗★
    #   ★教训✗★：★重启后**假人还没拉出来** ⇒ dshdigest 没有 pos=** ✗
    #   ★⇒ 整个回归被误判成★游戏不通✗★（★4 条全 †测不了† ✗ 2026-10-27 实测✗★）✗★ ✓
    try:
        import mcp_core as C
        o = C.dsh("dshver", 20.0) or ""
        return "version=" in o
    except Exception as e:                    # ★不许静默✗★
        print("  （★探测游戏连通时出错：%r✗★）" % (e,))
        return False


def run_one(script: str, timeout: float = 240.0):
    """★跑一个判据 ✗ 返回 (状态, 末行, 秒数)✗★"""
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, "-B", "-u", "-X", "utf8", str(ROOT / "tools" / script)],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return "FAIL", "★超时 %.0f 秒✗★" % timeout, time.time() - t0
    out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    tail = out[-1] if out else "（没输出）"
    # ★★§79.428✗★★：★**把全文存下来**✗ —— 2026-10-27 那回只留末行 ⇒ ★看不出 C1~C6 哪条红
    #   ⇒ 只能**重跑**才诊断 ✗ 这就是"★判据要能自立★"的反例✗★ ✓
    try:
        (ROOT / "tmp" / ("regress_%s.log" % script.replace(".py", ""))).write_text(
            "\n".join(out), encoding="utf-8")
    except Exception as e:                    # ★不许静默✗★
        print("  （★存 %s 的全文失败：%r✗★）" % (script, e))
    if "INCONCLUSIVE" in tail or "测不了" in tail or "inconclusive=1" in tail:
        st = "INCONC"
    elif r.returncode == 0:
        st = "PASS"
    else:
        st = "FAIL"
    return st, tail[:120], time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ns = ap.parse_args()
    only = {s.strip() for s in ns.only.split(",") if s.strip()}
    todo = [j for j in JUDGES if not only or j[0] in only or j[1] in only]

    print("== world_regress：一键实机回归 ==")
    up = game_up()
    print("  游戏通吗：%s" % ("✓" if up else "★不通 ✗ 全部记 †测不了†✗★"))
    n_pass = n_fail = n_inc = 0
    for name, script, why in todo:
        if not (ROOT / "tools" / script).is_file():
            print("  %-18s ★缺文件✗★ ｜ %s" % (name, script))
            n_fail += 1
            continue
        if not up:
            print("  %-18s †测不了† ｜ %s（★游戏不通✗★）" % (name, why))
            n_inc += 1
            continue
        time.sleep(1.0)                    # ★★§79.428✗★ 判据之间让世界稳定✗★
        st, tail, sec = run_one(script)
        # ★★§79.422✗★★：★世界侧判据**会瞬态红**（★游戏刚起／假人还在动✗★）✗
        #   ⇒ ★红一次先**等 2 秒重试** ✗ 仍红才算红 ✗ 并**如实注明重试过**✗★ ✓
        retried = False
        if st == "FAIL":
            time.sleep(2.0)
            st2, tail2, sec2 = run_one(script)
            retried = True
            sec += sec2
            if st2 == "PASS":
                st, tail = st2, tail2 + "（★重试后过 ✗ 瞬态✗★）"
            else:
                tail = tail2 + "（★重试仍红✗★）"
        mark = {"PASS": "PASS", "FAIL": "★FAIL★", "INCONC": "†测不了†"}[st]
        print("  %-18s %-9s %.1fs ｜ %s" % (name, mark, sec, tail))
        if st == "PASS":
            n_pass += 1
        elif st == "FAIL":
            n_fail += 1
        else:
            n_inc += 1
    total = n_pass + n_fail + n_inc
    print("  ---- 通过 %d ／ 失败 %d ／ 测不了 %d ／ 共 %d ----"
          % (n_pass, n_fail, n_inc, total))
    if n_fail:
        print("  => world_regress ★FAIL★（%d 条世界侧判据红了）" % n_fail)
    elif n_inc:
        print("  => world_regress INCONCLUSIVE（★游戏不通 ⇒ 测不了 ✗ 不是通过✗★）")
    else:
        print("  => world_regress PASS ✓（★世界侧判据全绿✗★）")
    print("SUMMARY regress pass=%d fail=%d inconclusive=%d total=%d"
          % (n_pass, n_fail, n_inc, total))
    return 0 if (n_fail == 0 and n_inc == 0) else (1 if n_fail else 2)


if __name__ == "__main__":
    raise SystemExit(main())
