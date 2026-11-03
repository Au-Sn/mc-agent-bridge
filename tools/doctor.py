#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor.py -- ★一条命令回答"为什么跑不起来"✗★（只读 · 不改世界 · 不写盘）

规格（docs/评估四-解绑与优先级.md 的 P0）：
  分发第一版的用户支持成本全在这一步 ⇒ 用**人话**说出哪一环坏了/哪一环不知道。

检查项（★全部只读 ✗ 不碰方块/不写状态✗★）：
  D1 config   `dsh.env` 在不在、关键值从哪来（env/dsh.env/default）
  D2 实例     MC_HOME / MODS_DIR / SAVE_DIR 存在
  D3 数据     recipes / tags / exceptions / 导出快照 齐不齐，条数**读生成结果**（不写死）
  D4 版本     `mod/gradle.properties` 的版本 vs 已装 `dshbridge-*.jar` 文件名
  D5 token    HTTP token 文件（2.56+ 写通道要它；/health 除外）
  D6 健康     直连端口 `paths.health_url()` 的 `/health` 能不能通（**读 only**；连不上 = unknown 不判死）
  D7 进程     有没有 java/javaw 进程（判不了一律 unknown ✗ 不猜）
  D8 判据     关键判据入口在不在、能不能编译
  D9 世界档案 `state/world_profile.json`（跨整合包：锚点/测试平台/no_dig；无 ⇒ unknown 不判死）
退出码：**0 全好 / 1 有硬问题 / 2 部分未知**（★不知道 ≠ 通过✗★）。`--json` 给机器读。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import paths as PA            # noqa: E402

OK, FAIL, UNKNOWN = "ok", "fail", "unknown"
EXIT_OK, EXIT_FAIL, EXIT_UNKNOWN = 0, 1, 2


def _ck(cid, name, status, detail, evidence=None) -> dict:
    return {"id": cid, "name": name, "status": status,
            "detail": str(detail)[:240], "evidence": evidence or []}


def _health_default(timeout: float = 1.5):
    """只读探活：GET /health（★不改世界 ✗ 不发 /cmd✗★）"""
    try:
        with urllib.request.urlopen(PA.health_url(), timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace").strip(), None
    except Exception as exc:                  # ★不许静默✗★（下面把它变成 unknown）
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:120])


def _process_default():
    """本机有没有 java 进程：`tasklist`（只读）。判不了 ⇒ None（★不猜✗★）"""
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                           text=True, encoding="gbk", errors="replace", timeout=8)
        if r.returncode != 0:
            print("doctor: tasklist rc=%d" % r.returncode, file=sys.stderr)
            return None
        lines = [ln for ln in (r.stdout or "").splitlines()
                 if re.search(r'"(?:java|javaw)\.exe"', ln, re.I)]
        return [ln.split('","')[0].strip('"') for ln in lines]
    except Exception as exc:                  # ★不许静默✗★
        print("doctor: 查进程失败 %r ⇒ 当未知" % (exc,), file=sys.stderr)
        return None


def _data_check(root: pathlib.Path) -> dict:
    """离线数据四件套：★条数一律读生成结果 ✗ 不写死 24779/20764✗★"""
    items = {}
    missing = []
    recipes = root / "build" / "recipes.json"
    tags = root / "state" / "tags_category.json"
    exceptions = root / "state" / "exceptions.json"
    snapdir = root / "state" / "export_snapshots"
    counts = {}
    try:
        if recipes.is_file():
            d = json.loads(recipes.read_text(encoding="utf-8", errors="replace"))
            items["recipes"] = {"path": str(recipes), "count": len(d)}
        else:
            missing.append("build/recipes.json")
    except Exception as exc:                  # ★不许静默✗★
        items["recipes"] = {"path": str(recipes), "error": str(exc)[:120]}
        missing.append("build/recipes.json(坏)")
    try:
        if tags.is_file():
            d = json.loads(tags.read_text(encoding="utf-8", errors="replace"))
            n = d.get("count") if isinstance(d, dict) else None
            if n is None and isinstance(d, dict):
                n = len(d.get("categories") or d)
            items["tags"] = {"path": str(tags), "count": n}
        else:
            missing.append("state/tags_category.json")
    except Exception as exc:                  # ★不许静默✗★
        items["tags"] = {"path": str(tags), "error": str(exc)[:120]}
        missing.append("state/tags_category.json(坏)")
    try:
        if exceptions.is_file():
            d = json.loads(exceptions.read_text(encoding="utf-8", errors="replace"))
            n = len(d.get("entries") or []) if isinstance(d, dict) else len(d)
            items["exceptions"] = {"path": str(exceptions), "count": n}
        else:
            missing.append("state/exceptions.json")
    except Exception as exc:                  # ★不许静默✗★
        items["exceptions"] = {"path": str(exceptions), "error": str(exc)[:120]}
        missing.append("state/exceptions.json(坏)")
    snaps = sorted(snapdir.glob("*__*__*.json")) if snapdir.is_dir() else []
    if snaps:
        try:
            d = json.loads(snaps[-1].read_text(encoding="utf-8", errors="replace"))
            n = d.get("count")
            if n is None and isinstance(d.get("blocks"), dict):
                n = len(d["blocks"])
            items["export"] = {"path": str(snaps[-1]), "count": n}
        except Exception as exc:              # ★不许静默✗★
            items["export"] = {"path": str(snaps[-1]), "error": str(exc)[:120]}
            missing.append("state/export_snapshots/*.json(坏)")
    else:
        missing.append("state/export_snapshots/*.json")
    counts = {k: (v.get("count") if isinstance(v, dict) else None)
              for k, v in items.items()}
    status = FAIL if missing else OK
    detail = ("齐：" + " ｜ ".join("%s=%s" % (k, counts.get(k)) for k in
                                  ("recipes", "tags", "export", "exceptions"))
              if not missing else "缺/坏：" + "、".join(missing))
    return _ck("data", "离线数据四件套", status, detail, [items])


def _version_check(root: pathlib.Path, home: pathlib.Path) -> dict:
    gp = root / "mod" / "gradle.properties"
    want = PA.read_gradle_version(gp)
    mods = home / "mods"
    jars = sorted(mods.glob("dshbridge*.jar")) if mods.is_dir() else []
    if not want:
        return _ck("version", "模组版本单一真源", FAIL,
                   "读不到 %s 的 mod_version" % gp)
    if not jars:
        return _ck("version", "已装 jar 版本", FAIL,
                   "已装里没有 dshbridge*.jar（实例 mods=%s）" % mods)
    got = []
    for j in jars:
        m = re.search(r"dshbridge[-_]?(\d+\.\d+\.\d+)", j.name)
        if m:
            got.append((j.name, m.group(1)))
    if not got:
        return _ck("version", "已装 jar 版本", UNKNOWN,
                   "jar 名里读不出版本：%s" % [j.name for j in jars][:3])
    bad = [(n, v) for n, v in got if v != want]
    if bad:
        return _ck("version", "已装 jar 版本", FAIL,
                   "gradle=%s 但已装=%s（先 install_mod）" % (want, bad[:3]))
    return _ck("version", "已装 jar 版本", OK,
               "gradle=%s ＝ 已装 %s" % (want, got[0][0]))


def _token_check(home: pathlib.Path, candidates=None) -> dict:
    import os
    envv = (os.environ.get("DSH_HTTP_TOKEN") or "").strip()
    if envv:
        return _ck("token", "HTTP token", OK, "环境变量 DSH_HTTP_TOKEN 已给（不落盘）")
    cands = list(candidates) if candidates is not None else PA.token_file_candidates()
    for p in cands:
        try:
            if pathlib.Path(p).is_file():
                return _ck("token", "HTTP token", OK, "文件：%s" % p)
        except OSError as exc:                # ★不许静默✗★
            print("doctor: 检查 token 文件失败 %r" % (exc,), file=sys.stderr)
    return _ck("token", "HTTP token", FAIL,
               "没有 token（2.56+ 写通道会被拒；/health 除外）：%s"
               % [str(p) for p in cands][:3])


def _judges_check(root: pathlib.Path) -> dict:
    names = ("check_all.py", "portability_test.py", "humanlike_test.py")
    bad = []
    for n in names:
        p = root / "tools" / n
        if not p.is_file():
            bad.append((n, "不在"))
            continue
        try:
            compile(p.read_text(encoding="utf-8", errors="replace"), str(p), "exec")
        except SyntaxError as exc:            # ★不许静默✗★
            bad.append((n, "语法错 L%s" % exc.lineno))
    return _ck("judges", "关键判据可跑（入口在＋能编译）", FAIL if bad else OK,
               "缺/坏：%s" % (bad or "无"))


def _world_profile_check(root, path=None) -> dict:
    """★世界档案（跨整合包）✗★：不存在 ⇒ unknown（不算失败）；存在但坏 ⇒ fail

    换包/换存档只改 `state/world_profile.json`；没配时 recover/soak 会打印"用本机默认"。
    """
    wp = pathlib.Path(path) if path else (pathlib.Path(root) / "state" / "world_profile.json")
    if not wp.is_file():
        return _ck("world_profile", "世界档案 world_profile", UNKNOWN,
                   "不存在（本机旧默认仍可用；换包/新机跑 "
                   "`py tools/world_profile.py --init` 再按新世界改值）— 不算失败")
    try:
        import world_profile as WP
        doc, reason = WP.load(str(wp))
    except Exception as exc:              # ★不许静默✗★
        return _ck("world_profile", "世界档案 world_profile", FAIL,
                   "读不了（%s: %s）" % (type(exc).__name__, str(exc)[:120]))
    if doc is None:
        return _ck("world_profile", "世界档案 world_profile", FAIL, reason[:240])
    tp = doc.get("test_platform") or {}
    return _ck("world_profile", "世界档案 world_profile", OK,
               "pack=%s anchor=%s soak=%s radius=%s zones=%d"
               % (doc.get("pack_name"),
                  WP._fmt_pt(doc.get("anchor")), WP._fmt_pt(doc.get("soak_anchor")),
                  tp.get("radius"), len(doc.get("no_dig_zones") or [])))


def run_doctor(root=None, home=None, health_fn=None, process_fn=None,
               no_net: bool = False, save_name=None, token_files=None) -> dict:
    """★跑全套检查✗★（可注入 ⇒ 判据完全不碰真网络/真进程/真盘）"""
    root = pathlib.Path(root) if root else PA.ROOT
    home = pathlib.Path(home) if home else PA.MC_HOME
    save_name = save_name or PA.SAVE_NAME
    checks = []

    desc = PA.describe()
    checks.append(_ck("config", "dsh.env / 环境事实来源", OK,
                      "dsh.env %s；MC_HOME←%s；BOT←%s"
                      % ("在" if desc["dsh_env_exists"] else "不在（用内置默认）",
                         desc["values"]["MC_HOME"]["source"],
                         desc["values"]["BOT_NAME"]["source"]),
                      [{"values": {k: v for k, v in desc["values"].items()}}]))
    checks.append(_ck("home", "实例目录 MC_HOME", OK if home.is_dir() else FAIL,
                      str(home)))
    mods = home / "mods"
    checks.append(_ck("mods", "mods 目录", OK if mods.is_dir() else FAIL, str(mods)))
    save = home / "saves" / save_name
    checks.append(_ck("save", "存档目录 SAVE_DIR",
                      OK if save.is_dir() else FAIL, str(save)))
    checks.append(_data_check(root))
    checks.append(_world_profile_check(root))
    checks.append(_version_check(root, home))
    checks.append(_token_check(home, candidates=token_files))

    if no_net:
        health = _ck("health", "直连 /health", UNKNOWN, "跳过（--no-net / 判据注入）")
        htxt = None
    else:
        fn = health_fn or _health_default
        try:
            htxt, herr = fn()
        except Exception as exc:              # ★不许静默✗★
            htxt, herr = None, "%s: %s" % (type(exc).__name__, str(exc)[:100])
        if htxt and "ok" in htxt.lower():
            health = _ck("health", "直连 /health", OK, "回执：%s" % htxt[:80])
        else:
            health = _ck("health", "直连 /health", UNKNOWN,
                         "连不上/没起（★不是判死 ✗ 游戏可能没开✗★）：%s" % (herr or htxt))
    checks.append(health)

    fn2 = process_fn or _process_default
    try:
        procs = fn2()
    except Exception as exc:                  # ★不许静默✗★
        procs = None
        print("doctor: 进程检查失败 %r ⇒ unknown" % (exc,), file=sys.stderr)
    if procs:
        proc = _ck("process", "游戏进程", OK, "发现 %d 个 java 进程" % len(procs))
    elif procs is None and health["status"] == OK:
        proc = _ck("process", "游戏进程", OK, "进程判不了，但 /health 通 ⇒ 有进程")
    elif procs == [] and health["status"] == OK:
        proc = _ck("process", "游戏进程", OK, "没看到 javaw，但 /health 通 ⇒ 有进程")
    elif procs is None:
        proc = _ck("process", "游戏进程", UNKNOWN, "判不了（不猜）")
    else:
        proc = _ck("process", "游戏进程", UNKNOWN, "没看到 java/javaw（可能没开游戏）")
    checks.append(proc)

    checks.append(_judges_check(root))

    fails = [c for c in checks if c["status"] == FAIL]
    unknowns = [c for c in checks if c["status"] == UNKNOWN]
    exit_code = EXIT_FAIL if fails else (EXIT_UNKNOWN if unknowns else EXIT_OK)
    summary = {"ok": len([c for c in checks if c["status"] == OK]),
               "fail": len(fails), "unknown": len(unknowns),
               "total": len(checks), "exit": exit_code}
    text = render(checks, summary)
    return {"schema": "dshbridge/doctor@1", "checks": checks, "summary": summary,
            "exit": exit_code, "text": text}


def render(checks, summary) -> str:
    mark = {OK: "[OK]  ", FAIL: "[FAIL]", UNKNOWN: "[??]  "}
    lines = ["== DSH doctor =="]
    for c in checks:
        lines.append("%s %-6s %s" % (mark[c["status"]], c["id"], c["detail"]))
    lines.append("-- 硬问题 %d ／ 未知 %d ／ 通过 %d（共 %d）--"
                 % (summary["fail"], summary["unknown"], summary["ok"],
                    summary["total"]))
    if summary["fail"]:
        lines.append("结论：有**硬问题**（先修上面 [FAIL] 的项）")
    elif summary["unknown"]:
        lines.append("结论：**部分未知**（[??] 不算通过：可能只是游戏没开）")
    else:
        lines.append("结论：全部通过")
    return "\n".join(lines)


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="一条命令回答：为什么跑不起来")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-net", action="store_true", help="不探 /health（纯离线）")
    ns = ap.parse_args(argv)
    rep = run_doctor(no_net=ns.no_net)
    if ns.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(rep["text"])
    return rep["exit"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
