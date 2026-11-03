#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bootstrap.py -- ★按配置重新生成离线数据✗★（`export` 一条命令）

规格（docs/评估四-解绑与优先级.md 的 P0「生成而非引用」）：
  ★"换整合包"不该是 14 条判据变红 ✗ 而是**重新生成一次** ✗ 判据自己对齐✗★
  缺的三件事，这里补齐：① 读 `dsh.env`（经 paths）② 一条命令按顺序跑完
  ③ **条数读生成结果**（★不写死本包数字✗★）

生成链（顺序＝依赖顺序）：
  tag_census → recipe_index --build → divergence --by-namespace → kb_export（验收器）
最后自检四份产物在不在：recipes／tags_category／分歧清单／迁移准备度。

用法：
    py tools/bootstrap.py export           # 真生成（会写那几份数据文件）
    py tools/bootstrap.py export --dry     # 只打印计划 ✗ 不跑生成器（判据/演示用）
    py tools/bootstrap.py export --json    # 机器读
退出码：0 全好 ／ 1 有硬问题（生成失败或产物缺） ／ 2 部分未知（如 kb 导出不可用）
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import paths as PA            # noqa: E402

SCHEMA = "dshbridge/bootstrap@1"
EXIT_OK, EXIT_FAIL, EXIT_UNKNOWN = 0, 1, 2


def default_steps() -> list:
    """生成链（★顺序即依赖✗★）：命令保持可注入 ⇒ 判据用假生成器离线验"""
    py = sys.executable
    return [
        {"name": "tag_census", "cmd": [py, str(PA.TOOLS_DIR / "tag_census.py")],
         "optional": False},
        {"name": "recipe_index",
         "cmd": [py, str(PA.TOOLS_DIR / "recipe_index.py"), "--build"],
         "optional": False},
        {"name": "divergence",
         "cmd": [py, str(PA.TOOLS_DIR / "divergence.py"), "--by-namespace"],
         "optional": False},
        {"name": "kb_export",
         "cmd": [py, str(PA.TOOLS_DIR / "kb_export.py")],
         "optional": True},        # ★验收器：它要游戏侧导出 ✗ 缺了不算生成失败✗★
    ]


def output_paths(root=None) -> dict:
    """四份产物的位置（相对 `root`；判据用假 root 验"缺文件必报"）"""
    root = pathlib.Path(root) if root else PA.ROOT
    return {
        "recipes": root / "build" / "recipes.json",
        "tags": root / "state" / "tags_category.json",
        "divergence": root / "docs" / "分歧清单.md",
        "migration": root / "docs" / "迁移准备度.md",
    }


def read_counts(root=None) -> dict:
    """★条数一律读生成结果✗★（快照 count／tags count／recipes 长度／exceptions 长度）"""
    root = pathlib.Path(root) if root else PA.ROOT
    counts = {}
    try:
        r = root / "build" / "recipes.json"
        if r.is_file():
            d = json.loads(r.read_text(encoding="utf-8", errors="replace"))
            counts["recipes"] = len(d) if hasattr(d, "__len__") else None
    except Exception as exc:                  # ★不许静默✗★
        counts["recipes_error"] = str(exc)[:120]
    try:
        t = root / "state" / "tags_category.json"
        if t.is_file():
            d = json.loads(t.read_text(encoding="utf-8", errors="replace"))
            counts["tags"] = (d.get("count") if isinstance(d, dict) else None) \
                or (len(d) if hasattr(d, "__len__") else None)
    except Exception as exc:                  # ★不许静默✗★
        counts["tags_error"] = str(exc)[:120]
    try:
        e = root / "state" / "exceptions.json"
        if e.is_file():
            d = json.loads(e.read_text(encoding="utf-8", errors="replace"))
            counts["exceptions"] = (len(d.get("entries") or [])
                                    if isinstance(d, dict) else len(d))
    except Exception as exc:                  # ★不许静默✗★
        counts["exceptions_error"] = str(exc)[:120]
    snapdir = root / "state" / "export_snapshots"
    snaps = sorted(snapdir.glob("*__*__*.json")) if snapdir.is_dir() else []
    if snaps:
        try:
            d = json.loads(snaps[-1].read_text(encoding="utf-8", errors="replace"))
            counts["block_count"] = d.get("count")
            counts["snapshot"] = snaps[-1].name
        except Exception as exc:              # ★不许静默✗★
            counts["block_count_error"] = str(exc)[:120]
    return counts


def _run_default(cmd, cwd) -> tuple:
    try:
        r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=1800)
        return r.returncode, ((r.stdout or "") + (r.stderr or ""))[-400:]
    except Exception as exc:                  # ★不许静默✗★
        return 127, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def run_export(dry: bool = False, root=None, run=None, steps=None) -> dict:
    """★跑生成链 ＋ 自检四份产物✗★（`dry=True` 只打印计划，不碰文件）"""
    root = pathlib.Path(root) if root else PA.ROOT
    steps = list(steps or default_steps())
    outs = output_paths(root)
    planned = [{"name": s["name"], "cmd": [str(c) for c in s["cmd"]],
                "optional": bool(s.get("optional"))} for s in steps]
    if dry:
        text = ("== bootstrap export（--dry：只打印计划，不跑生成器）==\n"
                + "\n".join("  · %-12s %s" % (s["name"], " ".join(s["cmd"]))
                            for s in planned)
                + "\n  产物自检：\n"
                + "\n".join("  · %-12s %s" % (k, v) for k, v in outs.items()))
        return {"schema": SCHEMA, "ok": True, "dry": True, "exit": EXIT_OK,
                "steps": planned, "outputs": {k: str(v) for k, v in outs.items()},
                "text": text}
    run = run or _run_default
    results, stopped = [], None
    for s in steps:
        rc, tail = run(s["cmd"], root)
        entry = {"name": s["name"], "cmd": [str(c) for c in s["cmd"]],
                 "rc": rc, "tail": str(tail)[-240:],
                 "optional": bool(s.get("optional")),
                 "status": "ok" if rc == 0 else
                           ("inconclusive" if s.get("optional") else "fail")}
        results.append(entry)
        if rc != 0 and not s.get("optional"):
            stopped = s["name"]          # ★硬失败即停 ✗ 不拿后面的产物硬撑✗★
            break
    missing = [k for k, p in outs.items() if not p.is_file()]
    counts = read_counts(root)
    hard = stopped is not None or bool(missing)
    partial = any(r["status"] == "inconclusive" for r in results)
    exit_code = EXIT_FAIL if hard else (EXIT_UNKNOWN if partial else EXIT_OK)
    ok = exit_code == EXIT_OK
    lines = ["== bootstrap export =="]
    for r in results:
        lines.append("  [%s] %-12s rc=%s%s" % (r["status"], r["name"], r["rc"],
                                               ("  ← 停在这里" if r["name"] == stopped else "")))
    lines.append("  产物：" + ("全在" if not missing else "缺 " + "、".join(missing)))
    lines.append("  条数（读生成结果）：" + " ｜ ".join(
        "%s=%s" % (k, v) for k, v in counts.items() if not k.endswith("_error")))
    lines.append("结论：" + ("完成" if ok else
                            ("有硬问题（生成失败/产物缺）" if hard else "部分未知（kb 导出不可用）")))
    return {"schema": SCHEMA, "ok": ok, "dry": False, "exit": exit_code,
            "steps": results, "stopped": stopped,
            "outputs": {k: str(v) for k, v in outs.items()},
            "missing": missing, "counts": counts, "text": "\n".join(lines)}


def main(argv) -> int:
    import argparse
    sub = argv[0] if argv else ""
    if sub != "export":
        print(__doc__)
        return 0
    ap = argparse.ArgumentParser(description="按配置重新生成离线数据")
    ap.add_argument("export", nargs="?")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    rep = run_export(dry=ns.dry)
    if ns.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(rep["text"])
    return rep["exit"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
