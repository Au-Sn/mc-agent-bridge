#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_public.py -- ★把当前 HEAD 导成"可公开"的干净快照目录（GitHub 用）★

WHY（用户口径 2026-11-03）：
  "检查一下有没有什么深度绑定本电脑的环境的情况吧，实在是缺的就先补完……
   到时候看一下传到github上吧"
  ⇒ 本仓库历史里仍有：工具链 433MB / 第三方 jar / 运行日志 / 初始提交里的 secrets/deepseek.key
  ⇒ **公开仓库不要推这份历史**，而是用本工具从 HEAD 的**跟踪树**导出一份干净快照：
     · 只含 `git archive HEAD` 里的文件（被 .gitignore 掉的本机物天然不在）
     · 无 `dsh.env`（只有 dsh.env.example）/ 无 mod/jdk17.zip / 无 mod/gdist / 无 logs 运行痕迹 / 无 downloads 第三方 jar
     · 可选 `--init-git` 直接在导出目录建一个**单提交**的干净 git 仓库（可直接 push 到 GitHub）

用法：
  py tools/export_public.py                      # 导出到 tmp/cleanroom（默认）
  py tools/export_public.py --out tmp/pub-2026   # 自定目录
  py tools/export_public.py --init-git           # 顺便 git init + 单提交（branch main）
  py tools/export_public.py --zip-only           # 只产 tmp/public_export.zip 不解压
  py tools/export_public.py --check              # 只检查当前跟踪树是否"可公开"（不导出）

机器行 / 退出码：
  EXPORTPUBLIC ok=1 files=N bytes=N zip=<path>  → 0
  EXPORTPUBLIC ok=0 ...                          → 1（检查不过或导出失败）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp"

# 公开快照里**必须**存在的文件（缺了别人跑不起来 / 不像一个项目）
REQUIRED = [
    "README.md",
    "INSTALL.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "dsh.env.example",
    "tools/paths.py",
    "tools/doctor.py",
    "tools/recover.py",
    "tools/check_all.py",
    "tools/portability_test.py",
    "mod/build.gradle",
    "mod/src",
    "state/exceptions.json",
]
# 公开快照里**禁止**出现的东西（深绑定本机 / 第三方分发 / 运行痕迹 / 体积炸弹）
FORBIDDEN_SUBSTR = [
    "dsh.env",
    "mod/jdk17.zip",
    "mod/gradle-8.1.1-bin.zip",
    "mod/gdist/",
    "downloads/",
    "backups/",
    "secrets/",
]
FORBIDDEN_PREFIX = ["logs/"]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def say(s=""):
    print(s, flush=True)


def git(args, **kw):
    return subprocess.run(["git"] + args, cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", **kw)


def head_info():
    r = git(["rev-parse", "--short", "HEAD"])
    return (r.stdout or "").strip() or "?"


def tracked_files():
    r = git(["ls-files", "-z"])
    if r.returncode != 0:
        raise SystemExit("git ls-files 失败：%s" % (r.stderr or "")[:200])
    return [p for p in r.stdout.split("\0") if p]


def check_tree(files):
    """返回 (ok, problems) —— 对**当前跟踪树**做公开性检查。"""
    problems = []
    for req in REQUIRED:
        if not any(f == req or f.startswith(req.rstrip("/") + "/") for f in files):
            problems.append("缺少必需文件：%s" % req)
    for f in files:
        p = f.replace("\\", "/")
        for fs in FORBIDDEN_SUBSTR:
            # dsh.env 特判：允许 dsh.env.example
            if fs == "dsh.env" and p.endswith("dsh.env.example"):
                continue
            if p == fs or p.startswith(fs) or fs in ("/" + p) or p.split("/")[0:1] == [fs.rstrip("/")]:
                problems.append("禁止入库：%s" % p)
                break
        else:
            for pre in FORBIDDEN_PREFIX:
                if p.startswith(pre) and not p.endswith(".gitkeep"):
                    problems.append("禁止入库（运行痕迹）：%s" % p)
                    break
    # 大文件（GitHub 单文件 >100MB 硬拒；>50MB 警告）
    big = []
    total = 0
    for f in files:
        fp = ROOT / f
        try:
            sz = fp.stat().st_size
        except OSError:
            continue
        total += sz
        if sz > 50 * 1024 * 1024:
            big.append((f, sz))
    for f, sz in big:
        problems.append("单文件 >50MB（GitHub 警告/可能拒收）：%s %.1fMB" % (f, sz / 1e6))
    return (not problems), problems, total


def build_zip(zip_path):
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    r = git(["archive", "--format=zip", "--output=%s" % zip_path, "HEAD"])
    if r.returncode != 0:
        raise SystemExit("git archive 失败：%s" % ((r.stderr or "")[:300]))
    return zip_path


def _force_rmtree(p: Path):
    """Windows 上 git 的 pack/*.idx 是只读的 ⇒ shutil.rmtree 会 PermissionError。

    2026-11-03 发布轮实测：第二次导出到已存在的 cleanroom（里面有 .git）时失败；
    这里先把整棵树的文件改成可写，再删（失败就如实抛出，不静默留半棵树）。
    """
    if not p.exists():
        return
    for root, _dirs, files in os.walk(str(p)):
        for fn in files:
            fp = Path(root) / fn
            try:
                os.chmod(str(fp), 0o666)
            except OSError as exc:
                print("export_public: chmod 失败 %s（%r）" % (fp, exc), file=sys.stderr)

    def onerror(func, path, _exc):
        try:
            os.chmod(path, 0o666)
            func(path)
        except Exception as exc:  # 删不干净就报出来，别留半棵树
            print("export_public: 删除失败 %s（%r）" % (path, exc), file=sys.stderr)
            raise
    shutil.rmtree(str(p), onerror=onerror)


def safe_extract(zip_path, out_dir):
    _force_rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path)) as zf:
        zf.extractall(str(out_dir))
    return out_dir


def dir_stats(d: Path):
    n = 0
    total = 0
    top = {}
    for p in d.rglob("*"):
        if not p.is_file():
            continue
        n += 1
        sz = p.stat().st_size
        total += sz
        parts = p.relative_to(d).parts
        k = parts[0] if len(parts) > 1 else "(root)"
        top[k] = top.get(k, 0) + sz
    return n, total, top


def init_git(out_dir, msg):
    cmds = [
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=dsh-agent", "-c", "user.email=dsh-agent@localhost",
         "commit", "-q", "-m", msg],
    ]
    for c in cmds:
        r = subprocess.run(c, cwd=str(out_dir), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return False, (" ".join(c[:2]), (r.stderr or r.stdout or "")[:300])
    return True, ""


def main(argv):
    ap = argparse.ArgumentParser(description="导出可公开的干净快照")
    ap.add_argument("--out", default=str(TMP / "cleanroom"))
    ap.add_argument("--zip-only", action="store_true")
    ap.add_argument("--init-git", action="store_true", help="在导出目录建单提交 git 仓库（branch main）")
    ap.add_argument("--check", action="store_true", help="只检查当前跟踪树，不导出")
    ap.add_argument("--force", action="store_true", help="即使检查不过也导出（仅供本地预演/联调）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    files = tracked_files()
    ok, problems, total = check_tree(files)
    say("== export_public: HEAD %s ｜ 跟踪文件 %d ｜ %.1f MB ==" % (head_info(), len(files), total / 1e6))
    if (args.check or not ok) and not (args.force and not args.check):
        for p in problems:
            say("  ★问题✗★ %s" % p)
        say("  ⇒ 检查%s（%d 个问题）" % ("通过 ✓" if ok else "不通过 ✗", len(problems)))
        say("EXPORTPUBLIC ok=%d files=%d bytes=%d problems=%d"
            % (1 if ok else 0, len(files), total, len(problems)))
        if args.json:
            print(json.dumps({"ok": ok, "problems": problems, "files": len(files),
                              "bytes": total}, ensure_ascii=False))
        return 0 if ok else 1
    if (not ok) and args.force:
        say("  ⚠ --force：检查有 %d 个问题仍继续导出（%s）" % (len(problems), "; ".join(problems[:3])))

    zip_path = TMP / "public_export.zip"
    build_zip(zip_path)
    say("  归档：%s（%.1f MB）" % (zip_path, zip_path.stat().st_size / 1e6))
    if args.zip_only:
        say("EXPORTPUBLIC ok=1 files=%d bytes=%d zip=%s" % (len(files), total, zip_path))
        return 0

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    safe_extract(zip_path, out_dir)
    n, dbytes, top = dir_stats(out_dir)
    say("  导出目录：%s（%d 文件 / %.1f MB）" % (out_dir, n, dbytes / 1e6))
    for k, v in sorted(top.items(), key=lambda kv: -kv[1])[:12]:
        say("    %8.2f MB  %s" % (v / 1e6, k))

    # 导出后复检：禁止项扫描（比跟踪树检查更严，直接扫目录）
    bad = []
    for p in out_dir.rglob("*"):
        rel = p.relative_to(out_dir).as_posix()
        if rel in ("dsh.env",) or rel.startswith("secrets/") or rel.startswith("downloads/"):
            bad.append(rel)
        if rel.startswith("mod/gdist/") or rel in ("mod/jdk17.zip", "mod/gradle-8.1.1-bin.zip"):
            bad.append(rel)
        if rel.startswith("logs/") and not rel.endswith(".gitkeep"):
            bad.append(rel)
    if bad:
        say("  ★导出目录里仍有禁止项（前 10）：%s" % bad[:10])
        say("EXPORTPUBLIC ok=0 files=%d bytes=%d forbidden=%d" % (n, dbytes, len(bad)))
        return 1

    if args.init_git:
        okg, err = init_git(out_dir, "public snapshot of mc-agent-bridge (from private HEAD %s)" % head_info())
        if not okg:
            say("  ★git init/commit 失败：%s %s" % err)
            say("EXPORTPUBLIC ok=0 files=%d bytes=%d" % (n, dbytes))
            return 1
        say("  git：已在导出目录建单提交仓库（branch main）")

    say("EXPORTPUBLIC ok=1 files=%d bytes=%d out=%s" % (n, dbytes, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
