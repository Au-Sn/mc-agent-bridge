#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bootstrap_test.py -- `bootstrap.py export` 的离线判据（★用假生成器 ✗ 不跑真数据链✗★）

CHECKS
  B1 --dry：只打印计划，**一次生成器都不跑**（run 调用数 = 0）
  B2 全好：按顺序跑完 4 步 ＋ 四份产物齐 ⇒ 退出码 0
  B3 产物缺 ⇒ 退出码 1，且**点名缺哪份**（不许假装成功）
  B4 生成器硬失败 ⇒ 立即停（后面的步骤不跑）＋ 退出码 1
  B5 ★条数读生成结果★：假产物里写 3／9／13 ⇒ 输出是 3／9／13（不写死 24779/20764）
  B6 可选步（kb_export）不可用 ⇒ 退出码 2（部分未知 ≠ 通过）
  B7 确定性：同输入两次 JSON 结果一致
  B8 bootstrap.py 源码里没有本包硬编码数字（24779／20764）
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import bootstrap as B          # noqa: E402


def fake_root(td):
    root = td / "repo"
    for d in ("build", "state/export_snapshots", "docs", "tools"):
        (root / d).mkdir(parents=True, exist_ok=True)
    return root


def writer(root: pathlib.Path, *, recipes=3, tags=9, snap=13, divergence=True,
           migration=True):
    """假生成器：按产物写文件（★值可控 ⇒ 能验"条数读生成结果"✗★）"""
    def run(cmd, cwd):
        name = pathlib.Path(cmd[1]).stem if len(cmd) > 1 else ""
        if name == "tag_census":
            (root / "state" / "tags_category.json").write_text(
                json.dumps({"count": tags, "categories": {}}), encoding="utf-8")
        if name == "recipe_index":
            (root / "build" / "recipes.json").write_text(
                json.dumps({("r%d" % i): {} for i in range(recipes)}), encoding="utf-8")
        if name == "divergence":
            if divergence:
                (root / "docs" / "分歧清单.md").write_text("# 分歧\n", encoding="utf-8")
            if migration:
                (root / "docs" / "迁移准备度.md").write_text("# 准备度\n", encoding="utf-8")
        if name == "kb_export":
            (root / "state" / "export_snapshots" /
             "2.56.0__dshbridge_registry_blocks@1__x.json").write_text(
                json.dumps({"count": snap}), encoding="utf-8")
        return 0, "fake ok"
    return run


def steps():
    return [
        {"name": "tag_census", "cmd": ["py", "tag_census.py"], "optional": False},
        {"name": "recipe_index", "cmd": ["py", "recipe_index.py", "--build"],
         "optional": False},
        {"name": "divergence", "cmd": ["py", "divergence.py", "--by-namespace"],
         "optional": False},
        {"name": "kb_export", "cmd": ["py", "kb_export.py"], "optional": True},
    ]


def main() -> int:
    checks = []
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        # B1 --dry 不跑生成器
        root1 = fake_root(td / "dry")
        calls = []
        r1 = B.run_export(dry=True, root=root1, run=lambda c, w: calls.append(c),
                          steps=steps())
        checks.append(("B1 --dry：只打印计划（生成器一次都没跑）",
                       r1["ok"] is True and r1["dry"] is True and calls == []
                       and len(r1["steps"]) == 4 and "bootstrap export" in r1["text"],
                       "calls=%d steps=%d" % (len(calls), len(r1["steps"]))))

        # B2 全好
        root2 = fake_root(td / "ok")
        order = []

        def run2(cmd, cwd):
            order.append(pathlib.Path(cmd[1]).stem)
            return writer(root2)(cmd, cwd)
        r2 = B.run_export(root=root2, run=run2, steps=steps())
        checks.append(("B2 全好：按顺序跑完 4 步 ＋ 四份产物齐 ⇒ 退出码 0",
                       r2["exit"] == 0 and r2["ok"] is True
                       and order == ["tag_census", "recipe_index", "divergence",
                                     "kb_export"]
                       and not r2["missing"],
                       "exit=%s order=%s" % (r2["exit"], order)))

        # B3 产物缺 ⇒ 1 且点名
        root3 = fake_root(td / "missing")
        r3 = B.run_export(root=root3, run=writer(root3, divergence=False,
                                                 migration=False), steps=steps())
        checks.append(("B3 产物缺 ⇒ 退出码 1 且点名缺哪份",
                       r3["exit"] == 1 and r3["ok"] is False
                       and "divergence" in r3["missing"] and "migration" in r3["missing"],
                       "exit=%s missing=%s" % (r3["exit"], r3["missing"])))

        # B4 生成器硬失败 ⇒ 停
        root4 = fake_root(td / "fail")
        ran = []

        def run4(cmd, cwd):
            ran.append(pathlib.Path(cmd[1]).stem)
            if pathlib.Path(cmd[1]).stem == "recipe_index":
                return 1, "boom"
            return writer(root4)(cmd, cwd)
        r4 = B.run_export(root=root4, run=run4, steps=steps())
        checks.append(("B4 生成器硬失败 ⇒ 立即停（后面不跑）＋ 退出码 1",
                       r4["exit"] == 1 and r4["stopped"] == "recipe_index"
                       and ran == ["tag_census", "recipe_index"],
                       "exit=%s stopped=%s ran=%s" % (r4["exit"], r4.get("stopped"), ran)))

        # B5 条数读生成结果
        root5 = fake_root(td / "counts")
        r5 = B.run_export(root=root5, run=writer(root5, recipes=3, tags=9, snap=13),
                          steps=steps())
        c5 = r5["counts"]
        checks.append(("B5 ★条数读生成结果★（3/9/13 而不是 24779/20764）",
                       c5.get("recipes") == 3 and c5.get("tags") == 9
                       and c5.get("block_count") == 13
                       and "24779" not in r5["text"] and "20764" not in r5["text"],
                       "recipes=%s tags=%s block_count=%s"
                       % (c5.get("recipes"), c5.get("tags"), c5.get("block_count"))))

        # B6 可选步不可用 ⇒ 2
        root6 = fake_root(td / "partial")

        def run6(cmd, cwd):
            if pathlib.Path(cmd[1]).stem == "kb_export":
                return 4, "INCONCLUSIVE: 导出不在"
            return writer(root6)(cmd, cwd)
        r6 = B.run_export(root=root6, run=run6, steps=steps())
        checks.append(("B6 可选步（kb_export）不可用 ⇒ 退出码 2（部分未知）",
                       r6["exit"] == 2 and r6["ok"] is False
                       and any(s["status"] == "inconclusive" for s in r6["steps"]),
                       "exit=%s" % r6["exit"]))

        # B7 确定性
        root7 = fake_root(td / "det")
        ra = B.run_export(root=root7, run=writer(root7), steps=steps())
        rb = B.run_export(root=root7, run=writer(root7), steps=steps())
        ja = json.dumps({k: ra[k] for k in ("exit", "missing", "counts", "stopped")},
                        sort_keys=True)
        jb = json.dumps({k: rb[k] for k in ("exit", "missing", "counts", "stopped")},
                        sort_keys=True)
        checks.append(("B7 确定性：同输入两次结果一致", ja == jb, ja[:100]))

        # B8 源码不写死本包数字
        src = (ROOT / "tools" / "bootstrap.py").read_text(encoding="utf-8",
                                                          errors="replace")
        hard = [n for n in ("24779", "20764", "13046872") if n in src]
        checks.append(("B8 src 不写死本包数字（换整合包只重生成）",
                       not hard, "命中=%s" % (hard or "无")))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:130]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => bootstrap 有红（%d 项不对）" % bad)
        print("BOOTSTRAP ok=0 bad=%d" % bad)
        return 1
    print("  => bootstrap 全绿（顺序／缺文件必报／硬失败即停／条数读生成结果）")
    print("BOOTSTRAP ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
