"""pyc_tools_text.py -- 把 31 件工具的**名字＋说明**按顺序打出来（重写文件时逐字照抄 ✓）"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
J = ROOT / "logs" / "mc_mcp_pyc_strings.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

acc = json.loads(J.read_text(encoding="utf-8"))
mod = acc[0]
consts = mod["consts"]

# 工具名顺序（模块级出现顺序 ✓）
NAMES = ["bot_state", "bot_inventory", "bot_events", "walk_to", "come_to", "look", "dig_block",
         "place_block", "use_block", "equip", "scan", "harvest_crop", "sift", "say", "stop",
         "idle", "go_to_drop", "job_open", "job_list", "job_step", "job_close", "chest_peek",
         "chest_put", "chest_take", "map_area", "find_block", "plan_route", "walk_route",
         "safe_spots", "survey", "remember"]

i = 0
for c in consts:
    if c in NAMES:
        # 名字后面紧跟的就是它的 description（源码里是相邻的常量 ✓）
        nxt = consts[consts.index(c) + 1] if consts.index(c) + 1 < len(consts) else ""
        i += 1
        print("%2d) %s :: %s" % (i, c, nxt[:400].replace("\n", " ")))
print()
print("== 关键函数的运行时句子（还原语气 ✓）==")
for ent in acc:
    if ent["name"] in ("t_map_area", "t_find_block", "t_safe_spots", "t_survey", "t_remember",
                       "t_walk_route", "t_plan_route", "t_job_open", "t_job_step", "t_job_close",
                       "t_job_list", "t_chest_peek", "t_chest_put", "t_chest_take", "_box",
                       "_goto_reach", "t_scan", "t_harvest", "t_sift", "t_go_to_drop"):
        ss = [s for s in ent["consts"] if len(s) > 6]
        if ss:
            print("-- %s" % ent["name"])
            for s in ss[:12]:
                print("     |" + s[:170].replace("\n", " "))
