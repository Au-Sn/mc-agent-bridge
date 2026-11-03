#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cold_start_test.py -- ★冷启动 D8 判据✗★：干净副本离"换台电脑能跑"还差什么（2026-11-03 ✓）

WHY（用户口径 2026-11-03）：
  「换一台电脑必须还能跑；缺的先补完；将来上 GitHub」⇒ 需要一条**机器判据**回答
  "**干净副本里缺什么**"，而不是靠人肉 checklist（错题本 P91：没证据就靠记忆 ✗）。

口径（三条严格分开，★不许混✗★）：
  · **DIST**        必须随仓库分发（缺 ⇒ 红）：README/INSTALL/LICENSE/dsh.env.example、
                    tools/paths.py|doctor.py|recover.py|check_all.py|portability_test.py、
                    mod 构建入口、离线数据（recipes/tags/export/exceptions）……
  · **BOOTSTRAP**   应由首跑/bootstrap 生成（缺 ⇒ 只记 unknown，不算分发缺失）：
                    dsh.env（从 example 复制）、token 文件、logs/、jobs/、缓存……
  · **DOC**         文档缺失/过期（缺 ⇒ 记 warn，单独列给人看）
  · **RUNTIME**     本机运行证据/本机路径**不该**进公开仓库（有 ⇒ 红，防"把家底带上 GitHub"）
  · **ENV**         本机环境未就绪（无游戏/没配 dsh.env）⇒ **部分未知，不是失败**（三分类）

检查（默认 --fast：只读文件/静态，毫秒级 ✓ 可进 GATE；--full 才跑子进程）：
  S1 必需文件存在（DIST 白名单；逐条给"为什么需要/谁该补"）
  S2 `dsh.env` **不许出现**（只能有 dsh.env.example）
  S3 禁止随仓库分发：`secrets/`、`downloads/`、`logs/`（非空运行痕迹）、`backups/`、
     `mod/jdk*`、`mod/gdist/`、`mod/.gradlehome/`、`mod/build/`、`node_modules/`、
     `*.zip > --max-big-mb`、`.gradle-home/`
  S4 大文件（> --max-big-mb，默认 50MB；GitHub 单文件 100MB 硬限 ⇒ 留余量）
  S5 本机绑定泄漏：根脚本/配置/state JSON 里的 `C:\\Users\\`、`D:\\pcl2`、`/home/<user>`、
     实例名（`tools/*.py` 的权威判定交给 `tools/portability_test.py` —— --full 跑它；
     docs/*.md 只记 warn，不当红）
  S6 离线数据完整：`build/recipes.json`、`state/tags_category.json`、`state/exceptions.json`、
     `state/export_snapshots/*.json` 能解析且非空（doctor D3 就靠这四件）
  S7 `dsh.env.example` 关键键齐全（MC_HOME/INSTANCE_NAME/SAVE_NAME/BOT_NAME/DSH_PORT/
     GATEWAY_PORT/MOD_VERSION_FILE）——**模板**随仓库走，真值不进库

  --full 追加（会慢 ~1-3 分钟，手工/发版前跑，不进 GATE 默认）：
  F1 `py tools/portability_test.py`（环境绑定权威判据）⇒ 必须 `PORTABILITY ok=1`
  F2 `py tools/doctor.py --no-net --json` ⇒ 三态：无游戏时 unknown/ENV 失败**不算失败**；
     只有 `data`/`judges` 这类**分发内容**失败才算红
  F3 `py tools/check_all.py --offline` ⇒ 解析 `SUMMARY pass=.. fail=..`（期望 fail=0），
     并摘出红项（干净副本里"少了某个被 GATE 引用的脚本"会在这里暴露）

自检能红（`--selfcheck`，离线 ✓ 不碰真仓 ✓）：
  用 tempfile 造一个"合成好副本"⇒ 应绿；再逐项注入坏样本（删必需文件 / 塞 dsh.env /
  塞 secrets/ / 塞 51MB zip / 塞 C:\\Users\\ 路径 / 弄坏离线数据 JSON）⇒ 每项必须变红；
  再还原 ⇒ 必须变绿。输出 `COLDSTART_SELFTEST ok=1 cases=N`。**GATE 建议跑这条**。

机器行：`COLDSTART ok=1 checks=N fail=0 warn=3 unknown=0 dir=... mode=fast`
退出码：0 全绿 ／ 1 有红（DIST/RUNTIME/坏数据） ／ 2 INCONCLUSIVE（缺干净副本目录，
或 --full 时只有 ENV/unknown——**测不了不算 PASS**）

用法：
  py tools/cold_start_test.py --selfcheck                 # GATE 用（秒级、离线）
  py tools/cold_start_test.py                             # 查当前仓库跟踪树（GATE 默认）
py tools/cold_start_test.py --dir tmp/cleanroom          # 查干净导出副本
  py tools/cold_start_test.py --full                      # 追加跑 portability/doctor/check_all
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

OK, FAIL, WARN, UNKNOWN = "ok", "fail", "warn", "unknown"

# ── 必需文件（DIST）─────────────────────────────────────────────────────
# (相对路径, 类别, 为什么需要)
REQUIRED: list[tuple[str, str, str]] = [
    ("README.md", "DIST", "入口说明：不认字也知道这项目是干什么的"),
    ("INSTALL.md", "DIST", "换一台电脑的第一份说明书（缺 = 用户跑不起来）"),
    ("LICENSE", "DIST", "开源发布必须有许可证（用户要求将来上 GitHub）"),
    ("dsh.env.example", "DIST", "环境事实模板；真 dsh.env 不进库"),
    (".gitignore", "DIST", "防工具链/日志/本机环境再次回流进仓库"),
    ("tools/paths.py", "DIST", "环境事实唯一入口（解绑的地基）"),
    ("tools/doctor.py", "DIST", "一条命令回答'为什么跑不起来'（分发第一版支持成本）"),
    ("tools/recover.py", "DIST", "D4：世界重启后一条命令恢复"),
    ("tools/check_all.py", "DIST", "闸门本体（干净副本没有它 = 没有验收）"),
    ("tools/portability_test.py", "DIST", "环境绑定判据（换机必须能跑它）"),
    ("mod/build.gradle", "DIST", "模组构建入口（用户要自己编译就得有）"),
    ("mod/gradle.properties", "DIST", "版本单一真源"),
    ("mod/settings.gradle", "DIST", "Gradle 工程入口"),
    ("mod/src/main/java/com/dsh/bridge", "DIST", "模组源码（META-INF/skins 等资源同树）"),
    ("build/recipes.json", "DIST", "离线配方数据（doctor D3 四件套之一）"),
    ("state/tags_category.json", "DIST", "离线标签数据（doctor D3 四件套之一）"),
    ("state/exceptions.json", "DIST", "错题/例外数据（doctor D3 四件套之一）"),
    ("state/export_snapshots", "DIST", "离线导出快照目录（doctor D3 四件套之一）"),
]

# ── 不允许随仓库分发（RUNTIME / 工具链 / 第三方 / 本机环境）──────────────
FORBIDDEN = [
    ("dsh.env", "RUNTIME", "本机环境事实：入公开库 = 泄露主机路径/实例名；只发 dsh.env.example"),
    ("secrets", "RUNTIME", "密钥目录（深绑本机；曾把 key 带进 git 历史过，P91）"),
    ("downloads", "RUNTIME", "第三方 mod jar（Carpet/AP/CC…）应从各自官方源下载，不随仓库"),
    ("backups", "RUNTIME", "本机备份（体积大、含历史现场）"),
    ("logs", "RUNTIME", "运行痕迹（会话/玩家名/截图）；只允许空 logs/.gitkeep 占位"),
    ("mod/jdk", "RUNTIME", "JDK 工具链 468MB 级；换机用 bootstrap 下载"),
    ("mod/jdk17.zip", "RUNTIME", "JDK 压缩包 >100MB，GitHub 单文件硬限"),
    ("mod/gdist", "RUNTIME", "Gradle 发行版；bootstrap 下载"),
    ("mod/gradle-8.1.1-bin.zip", "RUNTIME", "Gradle 压缩包；bootstrap 下载"),
    ("mod/.gradlehome", "RUNTIME", "工作区内的 gradle home（缓存/工具链）"),
    ("mod/build", "RUNTIME", "编译产物（jar 由构建生成）"),
    ("mod/mirrorcache", "RUNTIME", "本地 maven 镜像缓存（第三方产物）"),
    ("mod/run", "RUNTIME", "运行目录（world/logs）"),
    (".gradle-home", "RUNTIME", "缓存目录"),
    ("node_modules", "RUNTIME", "依赖目录"),
    ("tmp", "RUNTIME", "临时目录（导出时不应包含）"),
]
# logs/ 例外：只允许占位（空目录或 .gitkeep）
LOGS_ALLOWED = {".gitkeep", ""}

# ── 本机绑定泄漏（S5）────────────────────────────────────────────────────
LEAK_PATTERNS = [
    ("C:\\Users", re.compile(r"C:\\\\?Users", re.I)),
    ("C:/Users", re.compile(r"C:/Users", re.I)),
    ("D:\\pcl2", re.compile(r"D:\\\\?pcl2", re.I)),
    ("D:/pcl2", re.compile(r"D:/pcl2", re.I)),
    ("/home/<user>", re.compile(r"/home/[A-Za-z][\w.-]*/")),
    ("实例名(All the Mods 9)", re.compile(r"All the Mods 9")),
]
# S5 扫描范围：根脚本/配置 + state JSON（RUNTIME 证据）；docs 只 warn；
# tools/*.py 交给 portability_test.py（--full 的权威判定，例外表在它里头）
SCAN_FAST_DIRS = ("", "state", "mod")          # 相对根；tools 不在内（portability 管）
SCAN_FAST_EXTS = (".py", ".ps1", ".cmd", ".bat", ".json", ".gradle", ".properties",
                  ".toml", ".yml", ".yaml", ".sh", ".env", ".md")
SCAN_SKIP_NAMES = {"soak_freeze.json"}          # 冻结清单里是 sha256，不含路径

ENV_EXAMPLE_KEYS = ("MC_HOME", "INSTANCE_NAME", "SAVE_NAME", "BOT_NAME", "DSH_PORT",
                    "GATEWAY_PORT", "MOD_VERSION_FILE")

DATA_JSONS = [("build/recipes.json", "recipes"),
              ("state/tags_category.json", "tags"),
              ("state/exceptions.json", "exceptions")]


# ══════════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════════

def _rec(cid, name, status, detail, category=None):
    return {"id": cid, "name": name, "status": status, "detail": str(detail)[:500],
            "category": category}


def _txt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return "%.1fMB" % (n / 1024.0 / 1024.0)
    if n >= 1024:
        return "%.1fKB" % (n / 1024.0)
    return "%dB" % n


def _read_text(p: Path, limit=4_000_000):
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except Exception as exc:
        print("cold_start: 读不了 %s（%r）" % (p, exc), file=sys.stderr)
        return ""


def _git_tracked(base: Path):
    """若 base 是 git 仓库根 ⇒ 返回跟踪文件相对路径 set（posix）；否则 None（导出副本模式）。

    为什么需要它（2026-11-03 Lead 接管修复）：
      · GATE 默认跑本脚本**不带参数** ⇒ 不能依赖 tmp/cleanroom（未跟踪的本机目录，换机没有）
      · 仓库里"禁止物"要看**是否被跟踪**，不是"盘上有没有"：
        本机盘上有 mod/jdk17.zip/logs/dsh.env 是正常的（.gitignore 忽略），
        只有"进了版本库"才是发布问题
    """
    if not (base / ".git").exists():
        return None
    r = subprocess.run(["git", "ls-files", "-z"], cwd=str(base),
                       capture_output=True)
    if r.returncode != 0:
        print("cold_start: git ls-files 失败 rc=%d ⇒ 按导出副本模式检查磁盘"
              % r.returncode, file=sys.stderr)
        return None
    return {x.decode("utf-8", "replace") for x in r.stdout.split(b"\0") if x}


def _iter_files(base: Path, sub=""):
    """遍历 base/sub（不跟 .git / 大目录；用于 S3/S4/S5）"""
    root = base / sub if sub else base
    if not root.is_dir():
        return
    for path, dirs, files in os.walk(root):
        rel = Path(path).relative_to(base)
        # 跳过 .git 与已知大目录内部（S3 只判断"顶层目录在不在"）
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for fn in files:
            yield Path(path) / fn, rel / fn


# ══════════════════════════════════════════════════════════════════════════
# S1 必需文件
# ══════════════════════════════════════════════════════════════════════════

def check_required(base: Path) -> list:
    out, missing = [], []
    for rel, cat, why in REQUIRED:
        p = base / rel
        if not p.exists():
            out.append(_rec("req:" + rel, rel, FAIL,
                            "缺：%s（%s）" % (why, cat), cat))
            missing.append(rel)
    if not missing:
        out.append(_rec("req:all", "必需文件 %d 项齐全" % len(REQUIRED), OK, "", "DIST"))
    # export_snapshots 必须至少有一个 json（doctor D3 靠它）
    snap = base / "state" / "export_snapshots"
    if snap.is_dir():
        js = [p for p in snap.glob("*.json") if p.is_file()]
        if not js:
            out.append(_rec("req:export_snap", "state/export_snapshots/*.json", FAIL,
                            "目录在但没有 json（doctor D3 export 会判 fail）", "DIST"))
    return out


# ══════════════════════════════════════════════════════════════════════════
# S2 dsh.env 不许出现
# ══════════════════════════════════════════════════════════════════════════

def check_no_env(base: Path) -> list:
    tracked = _git_tracked(base)
    if tracked is not None:
        if "dsh.env" in tracked:
            return [_rec("env:absent", "dsh.env 不许随仓库（版本库）", FAIL,
                         "dsh.env 被 git 跟踪 ⇒ 入公开库会泄露主机路径/实例名；只发 dsh.env.example",
                         "RUNTIME")]
        on_disk = (base / "dsh.env").exists()
        return [_rec("env:absent", "dsh.env 不在版本库 ✓", OK,
                     "（盘上有本机 dsh.env 是正常的，被 .gitignore 忽略%s）"
                     % ("；本机副本存在" if on_disk else ""), "RUNTIME")]
    p = base / "dsh.env"
    if p.exists():
        return [_rec("env:absent", "dsh.env 不许随仓库", FAIL,
                     "dsh.env 在干净副本里（含主机路径/实例名；应只发 dsh.env.example）",
                     "RUNTIME")]
    return [_rec("env:absent", "dsh.env 不存在 ✓", OK, "", "RUNTIME")]


# ══════════════════════════════════════════════════════════════════════════
# S3 禁止随仓库分发的东西
# ══════════════════════════════════════════════════════════════════════════

def check_forbidden(base: Path, max_big_mb: float = 50.0) -> list:
    out = []
    tracked = _git_tracked(base)
    if tracked is not None:
        hit = []
        for rel, cat, why in FORBIDDEN:
            if rel == "logs":
                bad = [x for x in tracked
                       if x.startswith("logs/") and x.rsplit("/", 1)[-1] not in LOGS_ALLOWED]
                if bad:
                    hit.append(_rec("forbid:logs", "logs/ 里有运行痕迹（版本库）", FAIL,
                                    "%d 个文件（例：%s）⇒ %s" % (len(bad), bad[0], why), cat))
                continue
            if rel in tracked or any(x.startswith(rel + "/") for x in tracked):
                hit.append(_rec("forbid:" + rel, rel, FAIL,
                                "被版本库跟踪 ⇒ %s" % (why), cat))
        if hit:
            return hit + [_rec("forbid:all", "有禁止物被跟踪", FAIL, "", "RUNTIME")]
        return [_rec("forbid:all", "工具链/第三方/运行痕迹 均不在版本库 ✓", OK, "", "RUNTIME")]
    for rel, cat, why in FORBIDDEN:
        p = base / rel
        if not p.exists():
            continue
        if rel == "logs" and p.is_dir():
            files = [x for x in p.rglob("*") if x.is_file()
                     and x.name not in LOGS_ALLOWED]
            if not files:
                out.append(_rec("forbid:logs", "logs/ 只有占位 ✓", OK, "", cat))
                continue
            out.append(_rec("forbid:logs", "logs/ 里有运行痕迹", FAIL,
                            "%d 个文件（例：%s）⇒ %s" % (len(files), files[0].name, why), cat))
            continue
        if p.is_file():
            out.append(_rec("forbid:" + rel, rel, FAIL,
                            "存在 %s ⇒ %s" % (_txt_size(p.stat().st_size), why), cat))
        else:
            n = sum(1 for _ in p.rglob("*") if _.is_file())
            out.append(_rec("forbid:" + rel, rel, FAIL,
                            "目录存在（%d 文件）⇒ %s" % (n, why), cat))
    if not any(r["status"] == FAIL for r in out):
        out.append(_rec("forbid:all", "工具链/第三方/运行痕迹 均不在副本 ✓", OK, "", "RUNTIME"))
    return out


# ══════════════════════════════════════════════════════════════════════════
# S4 大文件
# ══════════════════════════════════════════════════════════════════════════

def check_big_files(base: Path, max_big_mb: float = 50.0) -> list:
    limit = int(max_big_mb * 1024 * 1024)
    big = []
    tracked = _git_tracked(base)
    files = ([(base / r, Path(r)) for r in tracked] if tracked is not None
             else _iter_files(base))
    for p, rel in files:
        try:
            sz = p.stat().st_size
        except OSError as exc:
            print("cold_start: stat 失败 %s（%r）" % (p, exc), file=sys.stderr)
            continue
        if sz > limit:
            big.append((sz, str(rel)))
    if big:
        big.sort(reverse=True)
        return [_rec("big:files", "大文件 > %gMB" % max_big_mb, FAIL,
                     "%d 个（例：%s %s）⇒ GitHub 单文件 100MB 硬限，先移出版本库"
                     % (len(big), _txt_size(big[0][0]), big[0][1]), "RUNTIME")]
    return [_rec("big:files", "无 >%gMB 大文件 ✓" % max_big_mb, OK, "", "RUNTIME")]


# ══════════════════════════════════════════════════════════════════════════
# S5 本机绑定泄漏
# ══════════════════════════════════════════════════════════════════════════

def check_path_leaks(base: Path) -> list:
    hits_code, hits_docs, scanned = [], [], 0
    tracked = _git_tracked(base)
    files = ([(base / r, Path(r)) for r in tracked] if tracked is not None
             else _iter_files(base))
    for p, rel in files:
        r = str(rel).replace("\\", "/")
        if r.startswith("tools/"):
            continue                         # 权威判定=portability_test.py（--full）
        if r.startswith(".git/"):
            continue
        if p.suffix.lower() not in SCAN_FAST_EXTS:
            continue
        if p.name in SCAN_SKIP_NAMES:
            continue
        scanned += 1
        try:
            if p.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        txt = _read_text(p, 2_000_000)
        found = [name for name, pat in LEAK_PATTERNS if pat.search(txt)]
        if not found:
            continue
        (hits_docs if p.suffix.lower() == ".md" else hits_code).append(
            (r, found))
    out = []
    if hits_code:
        sample = "; ".join("%s(%s)" % (h[0], ",".join(h[1])) for h in hits_code[:6])
        out.append(_rec("leak:code", "本机绑定泄漏（代码/配置/state）", FAIL,
                        "%d 个文件：%s ⇒ 换台电脑路径就错；RUNTIME 证据应移出仓库"
                        % (len(hits_code), sample), "RUNTIME"))
    else:
        out.append(_rec("leak:code", "代码/配置/state 无本机绝对路径 ✓", OK,
                        "扫描 %d 个文件（tools/*.py 交给 portability_test）" % scanned,
                        "DIST"))
    if hits_docs:
        out.append(_rec("leak:docs", "文档里提到本机路径（只警告）", WARN,
                        "%d 个文档：%s" % (len(hits_docs),
                                          "; ".join(h[0] for h in hits_docs[:5])), "DOC"))
    return out


# ══════════════════════════════════════════════════════════════════════════
# S6 离线数据完整
# ══════════════════════════════════════════════════════════════════════════

def _data_count(d) -> int:
    if isinstance(d, list):
        return len(d)
    if not isinstance(d, dict):
        return 0
    for k in ("count", "n", "total"):
        if isinstance(d.get(k), int):
            return d[k]
    for k in ("blocks", "items", "recipes", "categories", "exceptions", "entries"):
        if isinstance(d.get(k), (list, dict)):
            return len(d[k])
    return len(d)


def check_data(base: Path) -> list:
    out = []
    ok_all = True
    for rel, key in DATA_JSONS:
        p = base / rel
        if not p.is_file():
            out.append(_rec("data:" + key, rel, FAIL, "缺（doctor D3 会判 fail）", "DIST"))
            ok_all = False
            continue
        try:
            if p.stat().st_size > 64 * 1024 * 1024:
                out.append(_rec("data:" + key, rel, WARN,
                                "太大（%s）⇒ 可考虑 LFS/bootstrap 生成"
                                % _txt_size(p.stat().st_size), "DIST"))
                continue
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            n = _data_count(d)
            if n <= 0:
                out.append(_rec("data:" + key, rel, FAIL, "能解析但内容为空（%d）" % n, "DIST"))
                ok_all = False
            else:
                out.append(_rec("data:" + key, rel, OK, "%d 条（%s）"
                                % (n, _txt_size(p.stat().st_size)), "DIST"))
        except Exception as exc:
            out.append(_rec("data:" + key, rel, FAIL,
                            "解析失败：%s（%r）" % (rel, exc), "DIST"))
            ok_all = False
    snap = base / "state" / "export_snapshots"
    if snap.is_dir():
        bad = []
        good = 0
        for p in sorted(snap.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                if _data_count(d) > 0:
                    good += 1
            except Exception as exc:
                print("cold_start: 导出快照解析失败 %s（%r）" % (p, exc), file=sys.stderr)
                bad.append(p.name)
        if bad:
            out.append(_rec("data:export", "export_snapshots", FAIL,
                            "坏文件：%s" % bad[:4], "DIST"))
            ok_all = False
        elif good:
            out.append(_rec("data:export", "export_snapshots", OK, "%d 个好快照" % good, "DIST"))
    return out if out else [_rec("data:all", "离线数据四件套", OK, "", "DIST")]


# ══════════════════════════════════════════════════════════════════════════
# S7 dsh.env.example 键齐全
# ══════════════════════════════════════════════════════════════════════════

def check_env_example(base: Path) -> list:
    p = base / "dsh.env.example"
    if not p.is_file():
        return [_rec("env:example", "dsh.env.example", FAIL,
                     "缺：模板决定换机要改哪几个键", "DIST")]
    txt = _read_text(p)
    have = set(re.findall(r"(?m)^\s*([A-Z][A-Z0-9_]*)\s*=", txt))
    miss = [k for k in ENV_EXAMPLE_KEYS if k not in have]
    if miss:
        return [_rec("env:example", "dsh.env.example", FAIL,
                     "缺键：%s" % miss, "DIST")]
    return [_rec("env:example", "dsh.env.example", OK, "关键键齐全", "DIST")]


# ══════════════════════════════════════════════════════════════════════════
# --full：子进程可运行性（在本副本里跑）
# ══════════════════════════════════════════════════════════════════════════

def _run_child(base: Path, argv, timeout=600.0):
    t0 = time.time()
    try:
        r = subprocess.run([str(a) for a in argv], cwd=str(base),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout,
                           env=dict(os.environ))
        return r.returncode, (r.stdout or "") + (r.stderr or ""), time.time() - t0
    except subprocess.TimeoutExpired:
        return 124, "(超时 %.0fs)" % timeout, time.time() - t0
    except Exception as exc:
        return 125, ("起不来：%r" % (exc,)), time.time() - t0


def check_portability(base: Path) -> list:
    p = base / "tools" / "portability_test.py"
    if not p.is_file():
        return [_rec("full:portability", "portability_test", FAIL, "脚本不在", "DIST")]
    rc, out, sec = _run_child(base, [sys.executable, "-B", "-u", "-X", "utf8",
                                     "tools/portability_test.py"], 300)
    line = [l for l in out.splitlines() if l.startswith("PORTABILITY")]
    detail = line[-1] if line else out.strip().splitlines()[-1][:200] if out.strip() else "(无输出)"
    if rc == 0 and line and "ok=1" in line[-1]:
        return [_rec("full:portability", "portability_test（环境绑定权威判定）", OK,
                     "%s（%.1fs）" % (detail[:160], sec), "DIST")]
    return [_rec("full:portability", "portability_test", FAIL,
                 "rc=%d %s ⇒ tools/*.py 里还有环境绑定/或本副本跑不动它" % (rc, detail[:200]),
                 "DIST")]


def check_doctor(base: Path) -> list:
    p = base / "tools" / "doctor.py"
    if not p.is_file():
        return [_rec("full:doctor", "doctor", FAIL, "脚本不在", "DIST")]
    rc, out, sec = _run_child(base, [sys.executable, "-B", "-u", "-X", "utf8",
                                     "tools/doctor.py", "--no-net", "--json"], 300)
    data = None
    for ln in out.splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                data = json.loads(ln)
                break
            except Exception as exc:
                # 不静默吞：doctor 可能把多行 JSON 打在多行里 ⇒ 后面还有"整体解析"兜底
                print("cold_start: doctor JSON 行解析失败（%r）⇒ 试整体解析" % (exc,),
                      file=sys.stderr)
                continue
    if data is None:
        # doctor 可能把 JSON 打到多行；从第一个 { 试整体解析
        i = out.find("{")
        if i >= 0:
            try:
                data = json.loads(out[i:])
            except Exception:
                data = None
    if data is None:
        return [_rec("full:doctor", "doctor --no-net", UNKNOWN,
                     "跑不出 JSON（rc=%d）：%s ⇒ 不算失败、也不算通过" % (rc, out[-160:]),
                     "ENV")]
    checks = data.get("checks") or []
    hard_ids = {"data", "judges", "config"}
    env_ids = {"home", "mods", "save", "version", "token", "health", "process"}
    hard = [c for c in checks if c.get("id") in hard_ids and c.get("status") == FAIL]
    env_bad = [c for c in checks if c.get("id") in env_ids
               and c.get("status") in (FAIL, UNKNOWN)]
    unknowns = [c for c in checks if c.get("status") == UNKNOWN]
    detail = ("rc=%d 检查 %d：ok=%d fail=%d unknown=%d"
              % (rc, len(checks),
                 len([c for c in checks if c.get("status") == OK]),
                 len([c for c in checks if c.get("status") == FAIL]),
                 len(unknowns)))
    if hard:
        return [_rec("full:doctor", "doctor --no-net", FAIL,
                     detail + "；分发内容有硬问题：%s"
                     % [(c["id"], (c.get("detail") or "")[:80]) for c in hard], "DIST")]
    if env_bad or unknowns:
        return [_rec("full:doctor", "doctor --no-net", UNKNOWN,
                     detail + "；本机环境未就绪（无游戏/未配 dsh.env）⇒ **不是失败**（三分类）",
                     "ENV")]
    return [_rec("full:doctor", "doctor --no-net", OK, detail, "DIST")]


def check_gate_offline(base: Path) -> list:
    p = base / "tools" / "check_all.py"
    if not p.is_file():
        return [_rec("full:gate", "check_all --offline", FAIL, "脚本不在", "DIST")]
    t0 = time.time()
    rc, out, sec = _run_child(base, [sys.executable, "-B", "-u", "-X", "utf8",
                                     "tools/check_all.py", "--offline"], 1200)
    summary = ""
    for ln in out.splitlines():
        if "SUMMARY" in ln:
            summary = ln.strip()
    fails = [ln.strip() for ln in out.splitlines()
             if re.search(r"\bFAIL\b", ln) and not ln.strip().startswith("=>")]
    nums = re.search(r"pass=(\d+)\s+fail=(\d+).*?total=(\d+)", summary) if summary else None
    if not summary:
        return [_rec("full:gate", "check_all --offline", UNKNOWN,
                     "没拿到 SUMMARY（rc=%d，%.0fs）⇒ 测不了不算 PASS：%s"
                     % (rc, sec, out[-200:]), "ENV")]
    if not nums:
        return [_rec("full:gate", "check_all --offline", WARN,
                     "SUMMARY 形状变了：%s" % summary[:200], "DOC")]
    npass, nfail, ntotal = (int(x) for x in nums.groups())
    if nfail == 0:
        return [_rec("full:gate", "check_all --offline", OK,
                     "%s（%.0fs）" % (summary[:160], sec), "DIST")]
    return [_rec("full:gate", "check_all --offline", FAIL,
                 "%s（%.0fs）⇒ 干净副本跑不全；红项例：%s"
                 % (summary[:160], sec, "; ".join(fails[:5])[:400]), "DIST")]


# ══════════════════════════════════════════════════════════════════════════
# 汇总 / 机器行
# ══════════════════════════════════════════════════════════════════════════

def run_checks(base: Path, full: bool = False, max_big_mb: float = 50.0) -> list:
    checks = []
    checks += check_required(base)
    checks += check_no_env(base)
    checks += check_forbidden(base, max_big_mb)
    checks += check_big_files(base, max_big_mb)
    checks += check_path_leaks(base)
    checks += check_data(base)
    checks += check_env_example(base)
    if full:
        checks += check_portability(base)
        checks += check_doctor(base)
        checks += check_gate_offline(base)
    return checks


def summarize(checks) -> dict:
    return {
        "ok": len([c for c in checks if c["status"] == OK]),
        "fail": len([c for c in checks if c["status"] == FAIL]),
        "warn": len([c for c in checks if c["status"] == WARN]),
        "unknown": len([c for c in checks if c["status"] == UNKNOWN]),
        "total": len(checks),
    }


CAT_LABEL = {
    "DIST": "必须随仓库分发",
    "BOOTSTRAP": "应由 bootstrap/首跑生成",
    "DOC": "文档缺失/过期",
    "RUNTIME": "本机运行痕迹/本机绑定（不该进公开仓库）",
    "ENV": "本机环境未就绪（不是分发缺失）",
}


def render(checks, summ, base: Path, mode: str) -> None:
    print("== cold_start（%s）：%s ==" % (mode, base))
    for c in checks:
        tag = {"ok": "✓", "fail": "✗", "warn": "!", "unknown": "?"}[c["status"]]
        print("  %s [%-7s] %-40s %s" % (tag, (c.get("category") or "-"),
                                        c["name"][:40], c["detail"][:220]))
    print("  ---- checks=%d ok=%d fail=%d warn=%d unknown=%d ----"
          % (summ["total"], summ["ok"], summ["fail"], summ["warn"], summ["unknown"]))
    if summ["fail"]:
        print("  ★缺什么（按类别）✗★")
        seen = set()
        for c in checks:
            if c["status"] != FAIL:
                continue
            cat = c.get("category") or "DIST"
            if cat in seen:
                continue
            seen.add(cat)
            items = [x["name"] for x in checks if x["status"] == FAIL
                     and (x.get("category") or "DIST") == cat]
            print("    [%s] %s：%s" % (cat, CAT_LABEL.get(cat, "?"), "；".join(items[:8])))


def machine_line(summ, base: Path, mode: str) -> str:
    ok = 1 if (summ["fail"] == 0 and summ["unknown"] == 0) else 0
    return ("COLDSTART ok=%d checks=%d fail=%d warn=%d unknown=%d dir=%s mode=%s"
            % (ok, summ["total"], summ["fail"], summ["warn"], summ["unknown"],
               str(base).replace("\\", "/"), mode))


# ══════════════════════════════════════════════════════════════════════════
# --selfcheck：合成好副本 → 逐项注入坏样本（必须变红）→ 还原（必须变绿）
# ══════════════════════════════════════════════════════════════════════════

def _build_fixture(root: Path) -> None:
    """造一个"最小但完整"的合成干净副本（不带游戏/工具链）。"""
    def w(rel, text="x\n"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    w("README.md", "# fixture\n")
    w("INSTALL.md", "# install\n")
    w("LICENSE", "MIT\n")
    w(".gitignore", "dsh.env\nlogs/\n")
    w("dsh.env.example",
      "MC_HOME=\nINSTANCE_NAME=\nPACK_NAME=\nSAVE_NAME=\nBOT_NAME=\n"
      "DSH_PORT=8766\nGATEWAY_PORT=8765\nMOD_VERSION_FILE=mod/gradle.properties\n")
    for rel in ("tools/paths.py", "tools/doctor.py", "tools/recover.py",
                "tools/check_all.py", "tools/portability_test.py"):
        w(rel, "# fixture stub\n")
    w("mod/build.gradle", "// fixture\n")
    w("mod/gradle.properties", "mod_version=0.0.0\n")
    w("mod/settings.gradle", "// fixture\n")
    w("mod/src/main/java/com/dsh/bridge/Dummy.java", "class Dummy {}\n")
    w("build/recipes.json", json.dumps({"count": 3, "recipes": ["a", "b", "c"]}))
    w("state/tags_category.json", json.dumps({"count": 2, "tags": ["t1", "t2"]}))
    w("state/exceptions.json", json.dumps({"count": 1, "exceptions": ["p1"]}))
    w("state/export_snapshots/1.0__x@1__20260101.json",
      json.dumps({"count": 1, "blocks": {"minecraft:stone": 1}}))
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / ".gitkeep").write_text("", encoding="utf-8")


def _fast_fail_ids(base: Path) -> set:
    checks = run_checks(base, full=False, max_big_mb=50.0)
    return {c["id"] for c in checks if c["status"] == FAIL}


def selfcheck() -> int:
    cases, ok = [], True
    with tempfile.TemporaryDirectory(prefix="coldstart_fixture_") as td:
        base = Path(td) / "good"
        _build_fixture(base)
        # ① 合成好副本必须绿（这是"绿"的证明；它要是本来就红，后面"变红"没意义）
        fail = _fast_fail_ids(base)
        cases.append(("green:fixture", not fail, sorted(fail)))
        ok &= not fail

        def mutate(name, fn, expect_id):
            nonlocal ok
            # ★Windows 文件名不能有 ':' ✗ 用例名只用于显示✗★
            dirname = "case_" + re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
            b = Path(td) / dirname
            if b.exists():
                shutil.rmtree(b)
            shutil.copytree(base, b)
            fn(b)
            ids = _fast_fail_ids(b)
            good = expect_id in ids
            cases.append((name, good, ("期望红 %s；实际红=%s" % (expect_id, sorted(ids)))
                          if not good else sorted(ids)))
            ok &= good

        # ② 删必需文件 ⇒ req:INSTALL.md 红
        mutate("red:missing_install", lambda b: (b / "INSTALL.md").unlink(),
               "req:INSTALL.md")
        # ③ 塞 dsh.env ⇒ env:absent 红
        mutate("red:dsh_env", lambda b: (b / "dsh.env").write_text("MC_HOME=x\n"),
               "env:absent")
        # ④ 塞 secrets/ ⇒ forbid:secrets 红
        def _secrets(b):
            (b / "secrets").mkdir()
            (b / "secrets" / "deepseek.key").write_text("k")
        mutate("red:secrets", _secrets, "forbid:secrets")
        # ⑤ 塞 >50MB 文件（稀疏写法，不真占盘）⇒ big:files 红
        def _big(b):
            p = b / "mod" / "jdk17.zip"
            with p.open("wb") as f:
                f.seek(51 * 1024 * 1024)
                f.write(b"\0")
        mutate("red:big_zip", _big, "big:files")
        # ⑥ 塞 C:\Users 泄漏 ⇒ leak:code 红
        def _leak(b):
            (b / "start_gateway.cmd").write_text('cd C:\\Users\\alice\\game\n')
        mutate("red:path_leak", _leak, "leak:code")
        # ⑦ 弄坏离线数据 JSON ⇒ data:recipes 红
        def _badjson(b):
            (b / "build" / "recipes.json").write_text("{not json", encoding="utf-8")
        mutate("red:bad_data_json", _badjson, "data:recipes")
        # ⑧ logs/ 放运行痕迹 ⇒ forbid:logs 红
        def _logs(b):
            (b / "logs" / "run.log").write_text("2026-11-03 trace\n")
        mutate("red:logs", _logs, "forbid:logs")

    bad = [c for c in cases if not c[1]]
    print("== cold_start --selfcheck ==")
    for name, good, detail in cases:
        print("  %s %-26s %s" % ("PASS" if good else "FAIL", name, str(detail)[:260]))
    print("  ---- %d/%d ----" % (len(cases) - len(bad), len(cases)))
    if bad:
        print("  => cold_start selfcheck FAIL（判据自己抓不到坏样本）")
        print("COLDSTART_SELFTEST ok=0 cases=%d bad=%d" % (len(cases), len(bad)))
        return 1
    print("  => cold_start selfcheck PASS（好副本绿；删文件/塞 dsh.env/secrets/大文件/"
          "绝对路径/坏 JSON/日志 每一项都能变红；还原后回绿）")
    print("COLDSTART_SELFTEST ok=1 cases=%d" % len(cases))
    return 0


# ══════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════

def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="冷启动 D8 判据：干净副本离能跑还差什么（默认 --fast，只查文件/静态）")
    ap.add_argument("--dir", default=None,
                    help="干净副本目录（导出副本模式）；不传 = 检查当前仓库跟踪树（GATE 默认）")
    ap.add_argument("--full", action="store_true",
                    help="追加运行 portability_test / doctor --no-net / check_all --offline")
    ap.add_argument("--fast", action="store_true",
                    help="只做文件/静态检查（默认就是它；写出来是为了显式）")
    ap.add_argument("--selfcheck", action="store_true",
                    help="用合成副本自检能红（离线，不碰真仓；GATE 建议跑这条）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--max-big-mb", type=float, default=50.0,
                    help="大文件阈值 MB（默认 50；GitHub 单文件 100MB 硬限）")
    args = ap.parse_args(argv)

    if args.selfcheck:
        return selfcheck()

    base = Path(args.dir).resolve() if args.dir else ROOT.resolve()
    repo_mode = (base / ".git").exists()
    mode = ("full" if args.full else "fast") + ("-repo" if repo_mode else "-export")
    if not base.is_dir():
        print("INCONCLUSIVE 缺输入：干净副本目录不存在：%s" % base)
        print("  ⇒ 先跑 `py tools/export_public.py`（或 `git archive HEAD` 解压到该目录）")
        print("COLDSTART ok=0 checks=0 fail=0 warn=0 unknown=1 dir=%s mode=%s inconclusive=1"
              % (str(base).replace("\\", "/"), mode))
        return 2
    checks = run_checks(base, full=args.full, max_big_mb=args.max_big_mb)
    summ = summarize(checks)
    print(machine_line(summ, base, mode))
    if args.json:
        print(json.dumps({"machine": machine_line(summ, base, mode),
                          "summary": summ, "checks": checks}, ensure_ascii=False, indent=1))
    else:
        render(checks, summ, base, mode)
        print("  " + machine_line(summ, base, mode))
    if summ["fail"]:
        return 1
    if summ["unknown"]:
        print("  => INCONCLUSIVE（有 %d 项测不了：本机环境未就绪 ≠ 分发缺失；不算 PASS）"
              % summ["unknown"])
        return 2
    print("  => cold_start PASS（干净副本 %d 项检查全绿；--full 未跑时只证明文件/静态面）"
          % summ["total"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
