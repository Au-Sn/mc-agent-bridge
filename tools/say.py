#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""say.py -- 模块 F 自述层：**统一回执 ＋ 有限机器码**

用户口径（规格 §2.3 / §6.1 / §10.3）：
  * 「做无意义的事**不需要**理由；但是**在做事件的时候**至少一些地方要**申明理由**」
  * 「发言**可以仅开始和结束**」⇒ 一条任务只该有 2 条消息；**中间的流水进后台日志**
  * 回执必须带**机器码**（★CC 控制台只认 ASCII ✗ 中文只能是附属✗★）

本模块只做两件事：
  1. `say(reason, at, detail)` -> 结构化回执字符串（★机器码必须是**有限集**里的✗★）
  2. 同时把理由写进 `logs/reasons-YYYYMMDD.jsonl`（★N8' 就靠这个判✗★）
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★★机器码**有限集**（★不许自造 ✗ 新增必须先改这里并过判据✗★★）
CODES = {
    "ok": "成功",
    "start": "开始",
    "done": "完成",
    "no_path": "规划不出路",
    "no_stand": "目标站不住",
    "blocked": "被挡",
    "need_tool": "缺工具",
    "need_item": "缺物品",
    "need_scaffold": "缺垫脚方块",
    "danger": "危险",
    "no_dig_zone": "不可挖区域",
    "timeout": "超时",
    "refused": "被拒绝",
    "busy": "忙",
    "no_pos": "读不到位置",
    "stale": "数据过期",
    "unknown": "原因不明",
}

UNKNOWN = "unknown"


def _fmt(reason: str, at=None, detail: str = "", mission: str = "",
         extra: str = "") -> str:
    code = reason if reason in CODES else UNKNOWN
    parts = ["reason=" + code]
    if at is not None:
        try:
            parts.append("at=%d,%d,%d" % (int(at[0]), int(at[1]), int(at[2])))
        except Exception:
            parts.append("at=bad")
    if mission:
        parts.append("mission=" + str(mission)[:40])
    if extra:
        parts.append(str(extra)[:60])
    # ★人话放最后 ✗ 而且**可以没有**（★机器码才是判据用的✗★）
    if detail:
        parts.append("detail=" + str(detail)[:80])
    return " ".join(parts)


def say(reason: str, at=None, detail: str = "", mission: str = "",
        log: bool = True, important: bool = False) -> dict:
    """★说一句话 ＋ 留一条痕**✗★

    ★注意✗★：★无意义动作**不要调这个**（★用户明确说"做无意义的事不需要理由"✗★）
      只有**有后果**（改世界／动物品／受伤／拒绝／失败）才调 ✓
    """
    code = reason if reason in CODES else UNKNOWN
    text = _fmt(reason, at=at, detail=detail, mission=mission)
    rec = {"text": text, "code": code, "known": reason in CODES,
           "raw_reason": reason, "at": list(at) if at else None,
           "detail": detail, "mission": mission}
    if reason not in CODES:
        # ★自造码**不许静默**✗★：降级成 unknown ＋ 明确标出来
        print("say: ★未知机器码 %r ⇒ 降级为 unknown✗★" % (reason,), file=sys.stderr)
        rec["downgraded"] = True
    if log:
        try:
            import reasons as R
            R.because(reason=code, mission=mission, pos=at,
                      action=code, important=important,
                      detail=str(detail)[:120])
            rec["logged"] = True
        except Exception as exc:          # ★不许静默✗★
            print("say: ★写理由日志失败：%r✗★" % (exc,), file=sys.stderr)
            rec["logged"] = False
    return rec


def main(argv) -> int:
    if argv and argv[0] == "--codes":
        print("机器码 %d 个：" % len(CODES))
        for k in sorted(CODES):
            print("  %-14s %s" % (k, CODES[k]))
        return 0
    if argv and argv[0] == "--say":
        reason = argv[1] if len(argv) > 1 else "unknown"
        at = None
        if len(argv) > 2 and "," in argv[2]:
            at = tuple(int(v) for v in argv[2].split(","))
        rec = say(reason, at=at, detail=(argv[3] if len(argv) > 3 else ""), log=False)
        print(rec["text"])
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
