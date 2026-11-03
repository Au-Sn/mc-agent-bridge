#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_enchant_names.py — 扫全包 jar 的语言文件，找"连锁挖掘/砍树"相关的附魔或物品名

动机：FTB Ultimine 用不了（触发靠客户端按键包），那就得确认包里**还有没有别的路**：
      某些包会提供不需要按键的替代（附魔、工具右键、方块）。
      这类东西的名字一定出现在语言文件里，而语言文件是最省事的入口。

用法：
    py tools/scan_enchant_names.py                 # 默认关键词
    py tools/scan_enchant_names.py vein,timber,lumberjack,chainsaw,felling
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys, paths as PA
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

MODS = str(PA.MODS_DIR)
DEFAULT_KWS = ["vein", "timber", "lumberjack", "chainsaw", "felling", "tree_capitator",
               "treecapitator", "excavat", "area_min", "bulk", "连锁"]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("keywords", nargs="?", default="")
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args(argv)
    kws = [k.strip().lower() for k in (args.keywords or "").split(",") if k.strip()] or DEFAULT_KWS

    jars = sorted(glob.glob(os.path.join(MODS, "*.jar")))
    print("扫描 %d 个 jar，关键词：%s" % (len(jars), ", ".join(kws)))
    found = 0
    for j in jars:
        try:
            z = zipfile.ZipFile(j)
        except Exception as e:
            # 记录：一个 jar 打不开 ⇒ 名单静默少一个模组的名字
            print("[记录] jar 打不开（名单少一个模组）：%s: %s"
                  % (os.path.basename(j), type(e).__name__), file=sys.stderr)
            continue
        for n in z.namelist():
            if not (n.endswith("en_us.json") and "/lang/" in n):
                continue
            try:
                data = json.loads(z.read(n).decode("utf-8", "replace"))
            except Exception as e:
                # 记录：一个语言文件读不了 ⇒ 名单静默少一片
                print("[记录] 语言文件读不了（名单少一片）：%s: %s"
                      % (n, type(e).__name__), file=sys.stderr)
                continue
            for k, v in data.items():
                blob = (str(k) + " " + str(v)).lower()
                if any(w in blob for w in kws):
                    # 只要附魔/物品/方块这类实体名，滤掉说明文本
                    if not any(t in k for t in ("enchantment", "item.", "block.", "effect", "tooltip")):
                        continue
                    print("  %-52s = %-34s  <= %s" % (k[:52], str(v)[:34], os.path.basename(j)))
                    found += 1
                    if found >= args.limit:
                        print("  … 达到上限")
                        return 0
    if found == 0:
        print("  （没有命中：包里没有这类不靠按键的替代品）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
