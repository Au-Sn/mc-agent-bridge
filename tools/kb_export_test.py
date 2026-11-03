#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_export_test.py -- ★导出验收器的判据★（V1~V6 ✓ 全离线 ✓ 合成数据 ✓ 2026-10-03）"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import kb_export as KE  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


def mk(**kw):
    base = {"schema": KE.SCHEMA, "exported_at": "2026-10-04T00:00:00", "mod_version": "2.19.0",
            "count": 2, "errors": 0,
            "blocks": {"a:x": {"family": "full", "max_height": 1.0, "empty": False},
                       "a:y": {"family": "other", "max_height": 0.9375, "empty": False}}}
    base.update(kw)
    return base


def has(problems, needle):
    return any(needle in x for x in problems)


print("== kb_export_test：V1~V6 ==")
check("V0", KE.validate(mk())[0], "★合规的一份 ⇒ 过✗★")
for k in ("schema", "exported_at", "mod_version", "count"):
    _o, _p = KE.validate(mk(**{k: ""}))
    check("V1·%s" % k, has(_p, "V1"), "★缺 %s ⇒ 报 V1✗★ ⇒ %s" % (k, _p[:1]))
_o, _p = KE.validate(mk(schema="something/else"))
check("V1·schema值", has(_p, "schema 不是"), "★schema 值不对也要报✗★")
_o, _p = KE.validate(mk(count=99))
check("V2", has(_p, "V2"), "★`count` 与条数不符 ⇒ 报（★说谎✗★）⇒ %s" % [x for x in _p if "V2" in x])
_o, _p = KE.validate(mk(blocks={"a:x": {"family": "月亮", "max_height": 1.0}} , count=1))
check("V3", has(_p, "V3"), "★族不在闭集 ⇒ 报✗★ ⇒ %s" % _p[:1])
_o, _p = KE.validate(mk(blocks={"a:x": {"family": "other"}}, count=1))
check("V4", has(_p, "V4"), "★★`other` 缺 `max_height` ⇒ 报✗★★ ⇒ %s" % _p[:1])
_o, _p = KE.validate(mk(blocks={"a:x": {"family": "none", "max_height": 0.5, "empty": True}},
                        count=1))
check("V5", has(_p, "V5"), "★`empty=true` 却有高度 ⇒ 自相矛盾要报✗★ ⇒ %s" % _p[:1])
_o, _p = KE.validate(mk(errors=3))
check("V6", has(_p, "V6"), "★导出自己报错 ⇒ 必须说出来✗★ ⇒ %s" % _p[:1])
check("V7", set(KE.FAMILIES) == {"full", "slab", "snow_layer", "fence_15", "canopy", "none",
                                 "other", "liquid"},
      "★闭集就是用户拍板的七类 ＋ liquid✗★ ⇒ %s" % "／".join(KE.FAMILIES))

print("=> kb_export %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
sys.exit(0 if ok[0] else 1)
