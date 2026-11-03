#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""no_dig_test.py -- 模块 I 施工许可层的判据（★两向都测✗★）

用户规格 §10.1：默认五类不可挖区（家／屋／箱子周围 3 格／产线／农田），每条带理由、可删。

CHECKS
  I1 家/屋 内部 ⇒ 拒绝（★给理由✗★）
  I2 家外面 ⇒ 允许
  I3 新增一条 ⇒ 立刻生效（拒绝）
  I4 删掉那条 ⇒ 立刻恢复允许
  I5 ★同名的覆盖不堆叠★（forbid 两次同一名字 ⇒ 只有一条，且指新 box）
  I6 ★边界精确★（box 边上那格算里面；再外一格算外面）
  I7 ★状态文件坏了 ⇒ 一律禁止（保守）★
  I8 真世界：家 bbox 里的一格确实被拒（★用当前状态文件，不改它✗★）
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import no_dig as ND          # noqa: E402


def main() -> int:
    checks = []
    STATE = ND.STATE
    backup = STATE.read_text(encoding="utf-8") if STATE.is_file() else None

    try:
        # I1 家里 ⇒ 拒
        ok, zone = ND.allowed((4120, 72, 25))
        checks.append(("I1 家里 ⇒ 拒绝", (not ok) and bool(zone), "zone=%s" % ((zone or {}).get("name"))))

        # I2 家外 ⇒ 允许
        ok2, zone2 = ND.allowed((4100, 72, 5))
        checks.append(("I2 家外 ⇒ 允许", ok2 and zone2 is None, "zone=%s" % (zone2,)))

        # I3 新增 ⇒ 生效
        ND.forbid("测试区", (4000, 60, 0, 4004, 70, 4), "judge 临时区")
        ok3, zone3 = ND.allowed((4002, 65, 2))
        checks.append(("I3 新增区域立刻拒绝", (not ok3) and (zone3 or {}).get("name") == "测试区",
                       "zone=%s" % ((zone3 or {}).get("name"))))

        # I4 删除 ⇒ 恢复
        ND.release("测试区")
        ok4, zone4 = ND.allowed((4002, 65, 2))
        checks.append(("I4 删除后恢复允许", ok4 and zone4 is None, "zone=%s" % (zone4,)))

        # I5 同名覆盖不堆叠
        ND.forbid("覆盖测试", (5000, 60, 0, 5001, 65, 1), "第一版")
        ND.forbid("覆盖测试", (5010, 60, 0, 5011, 65, 1), "第二版")
        n_same = len([z for z in ND.list_zones() if z.get("name") == "覆盖测试"])
        ok5 = (n_same == 1 and ND.allowed((5010, 62, 0))[0] is False
               and ND.allowed((5000, 62, 0))[0] is True)
        checks.append(("I5 同名覆盖不堆叠", ok5, "同名条数=%d" % n_same))
        ND.release("覆盖测试")

        # I6 边界精确
        ND.forbid("边界测试", (3000, 60, 0, 3002, 62, 2), "边界")
        ok6 = (ND.allowed((3002, 62, 2))[0] is False      # 角上：里面
               and ND.allowed((3003, 62, 2))[0] is True   # 再外一格：外面
               and ND.allowed((3000, 60, 0))[0] is False)
        checks.append(("I6 边界精确（含端点，外一格放行）", ok6, "角=%s 外=%s"
                       % (ND.allowed((3002, 62, 2))[0], ND.allowed((3003, 62, 2))[0])))
        ND.release("边界测试")

        # I7 状态坏了 ⇒ 全禁
        STATE.write_text("{ this is not json", encoding="utf-8")
        ok7, z7 = ND.allowed((4120, 72, 25))
        checks.append(("I7 状态文件坏了 ⇒ 保守全禁", (not ok7) and bool(z7), "zone=%s" % ((z7 or {}).get("name"))))
    finally:
        # 恢复原状态（★判据不许改世界✗★）
        if backup is not None:
            STATE.write_text(backup, encoding="utf-8")
        else:
            ND._save({"schema": "dshbridge/no_dig@1", "zones": []})

    # I8 真世界（恢复后的状态文件）
    ok8, z8 = ND.allowed((4120, 72, 25))
    zones = ND.list_zones()
    checks.append(("I8 真状态：家里那格被拒", (not ok8) and (z8 or {}).get("name") in ("家", "屋"),
                   "%d 条区域 ｜ zone=%s" % (len(zones), (z8 or {}).get("name"))))

    # I9/I10 ★真接线✗★：动作表里"挖"命中禁止区 ⇒ validate_table 必须报 dig_bad
    try:
        import exec3d as E3

        class _W:
            def get(self, x, y, z):
                return "minecraft:stone"

            def name(self, x, y, z):
                return "minecraft:stone"

            def h(self, x, y, z):
                return 1.0

            def support(self, x, y, z):
                return True

            def passable(self, x, y, z):
                return False

            def pass_info(self, x, y, z):
                return {"kind": "blocked", "subtype": "", "action": None, "why": ""}

        w = _W()
        _wb, _pb, db_in = E3.validate_table(w, (4120, 72, 25), ["dig:4120,72,25:x"])
        _wb2, _pb2, db_out = E3.validate_table(w, (4100, 72, 5), ["dig:4100,72,5:x"])
        checks.append(("I9 真接线：禁止区里的 dig ⇒ dig_bad 非空",
                       bool(db_in) and "no_dig_zone" in db_in[0], str(db_in[:1])))
        checks.append(("I10 真接线：区域外的 dig ⇒ 不报", not db_out, str(db_out[:1])))
    except Exception as exc:            # ★不许静默✗★
        checks.append(("I9 真接线：禁止区里的 dig ⇒ dig_bad 非空", False, "异常 %r" % (exc,)))
        checks.append(("I10 真接线：区域外的 dig ⇒ 不报", False, "异常 %r" % (exc,)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:110]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => no_dig FAIL (%d)" % bad)
        print("NODIG ok=0 bad=%d" % bad)
        return 1
    print("  => no_dig PASS (blacklist enforced both ways; broken state is fail-closed)")
    print("NODIG ok=1 checks=%d zones=%d" % (len(checks), len(zones)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
