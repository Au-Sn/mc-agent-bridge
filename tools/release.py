#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release.py -- ★一键发版链（**检查模式优先** ✗ 2026-11-02 D2/D3）★

★为什么有它✗★（优化路线 ADR-8 / 审计 P1）：
  ★发版是"4 步人肉"：改版本 → 构建 → 验 jar → 装包 → 重启 → 文档带出 ✗ 全靠记得 ✗★
  ⇒ ★任何一步漏了都不会有人吭声 ✗★（"构建成功 ≠ 改动进去了"是项目最贵的一条教训 P150）
  ⇒ 本脚本把**发版前必须成立的五件事**变成一条命令：`py tools/release.py --check`

★五件（缺一即 BLOCK ✗ 每件都自己说清证据）✗★：
  R1 版本单一真源：`mod/gradle.properties` 的 mod_version ＝ `mod/build/libs` 最新 jar 文件名里的版本
     ＝ 游戏 `mods/` 里**实际安装**的 jar 版本（装包一致性）
  R2 jar 内特征抽样：★从 `tools/install_mod.py` 的 `NEED` 列表**读出来**（AST 解析 ✗ 不另抄一份 ✗）★
     ⇒ 每个必需字符串都必须能在 jar 的 .class 字节里找到（少一个 ⇒ 装的是旧 jar ⇒ BLOCK）
  R3 发版清单：`state/release_manifest.json` 里**当前版本**那条记录的 字节/sha256 必须与现 jar 一致
     （首次/新版本 ⇒ 先跑 `--record` ⇒ 缺证据一律 BLOCK ✗ 不许"没记录就当过"）
  R4 文档版本一致：调 `tools/doc_consistency_test.py`（D7 闸门 ✗ **复用 C1 逻辑** ✗ 不重复造）
     ⇒ 必须整体 PASS（它已含 C1b：gradle 版本 ↔ 四份入口文档）
  R5 工作区干净度 ＋ HEAD 可追溯：`git status` 只许**运行痕迹白名单**（logs/ tmp/ bridge/ state/ …）；
     必须在一个分支上（detached HEAD ⇒ BLOCK）；HEAD / manifest 记录的 commit 必须是**库里存在的对象**

★用法✗★：
  py tools/release.py --check        # 五件全查 ⇒ `RELEASE: PASS` / `RELEASE: BLOCK`；退出码 0 / 1
  py tools/release.py --record       # 验 jar 特征后写 manifest（版本/字节/sha256/commit/时间）
  py tools/release.py --check --json # 机器可读（给 CI / 未来 release_check 视图）
  py tools/release.py --record --dry-run   # 只打印将写入什么 ✗ 不写盘 ✓

★纪律✗★：
  · ★检查模式**零写盘**✗★（只有 `--record` 写 manifest）
  · ★不信任自述✗★：版本从 gradle.properties 读、特征从 jar 字节读、文档从闸门读、干净度从 git 读
  · ★缺证据 = BLOCK✗★（没有 manifest／没有 jar／取不到 git ⇒ 一律 BLOCK ✗ 不许 INCONCLUSIVE 放行）
  · ★不写死版本号✗★（所有数字现算 ✗ 换 2.57.0/2.58.0 不用改本文件）
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBS = ROOT / "mod" / "build" / "libs"
GRADLE = ROOT / "mod" / "gradle.properties"
INSTALL_MOD = ROOT / "tools" / "install_mod.py"
DOC_TEST = ROOT / "tools" / "doc_consistency_test.py"
MANIFEST = ROOT / "state" / "release_manifest.json"
GAME_DIR = Path(r"D:\pcl2\.minecraft\versions\All the Mods 9 - To the Sky - atm9sky")
SCHEMA = "dshbridge-release-manifest@1"

# ★工作区干净度白名单✗★：这些是**运行痕迹**（不属于源码 ✗ 出没出息都不该阻塞发版 ✓）
#   源码/文档/配置/模组/工具出现改动 ⇒ **必须 BLOCK**（要让发版对应一个可追溯的 commit ✓）
DIRTY_ALLOW_PREFIX = (
    "logs/", "tmp/", "bridge/", "state/", "jobs/", "downloads/",
    "memory/", ".gradle-home/", "backups/",
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---------------------------------------------------------------- 基础事实
def read_gradle_version(root: Path = ROOT) -> str | None:
    p = root / "mod" / "gradle.properties"
    try:
        m = re.search(r"^mod_version\s*=\s*(\S+)\s*$",
                      p.read_text(encoding="utf-8", errors="replace"), re.M)
        return m.group(1) if m else None
    except OSError as e:
        print("[release] 读不到 %s：%s" % (ROOT / "mod" / "gradle.properties", e))
        return None


def parse_version(name: str) -> tuple | None:
    m = re.search(r"dshbridge-(\d+)\.(\d+)\.(\d+)\.jar$", name)
    return tuple(int(g) for g in m.groups()) if m else None


def _ver_tuple(v: str) -> tuple:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", v or "")
    return tuple(int(g) for g in m.groups()) if m else (0, 0, 0)


def list_jars(libs: Path = LIBS) -> list:
    """⇒ [(ver_tuple, path)] ✗ 只认 `dshbridge-x.y.z.jar`（历史备份/半成品不参与）"""
    out = []
    try:
        for p in libs.glob("dshbridge-*.jar"):
            v = parse_version(p.name)
            if v:
                out.append((v, p))
    except OSError as e:
        print("[release] 列 %s 失败：%s（缺证据 ⇒ 后面按 BLOCK 处理）" % (libs, e))
    return sorted(out, key=lambda kv: (kv[0], kv[1].stat().st_mtime if kv[1].is_file() else 0))


def newest_jar(libs: Path = LIBS):
    js = list_jars(libs)
    return js[-1][1] if js else None


def jar_info(path: Path) -> dict:
    """★只信 jar 字节✗★：⇒ 位置/字节数/sha256/class 数/全部 class 字节拼起来的文本"""
    b = path.read_bytes()
    info = {"path": str(path), "name": path.name, "bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest(), "classes": 0, "text": ""}
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith(".class")]
            info["classes"] = len(names)
            info["text"] = b"\n".join(z.read(n) for n in names).decode("utf-8", "ignore")
    except (zipfile.BadZipFile, OSError) as e:
        info["error"] = "%s: %s" % (type(e).__name__, str(e)[:60])
    return info


def load_need(install_mod: Path = INSTALL_MOD) -> list | None:
    """★从 install_mod.py 的 `NEED = [...]` 读必需特征串✗★（AST ✗ **不另抄一份**）

    ★为什么用 AST✗★：import install_mod **会执行它**（文件尾 `raise SystemExit(main())`）✗
      ⇒ 直接 import 会把安装流程跑一遍 ✗★ ✓
    """
    try:
        tree = ast.parse(install_mod.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError) as e:
        print("[release] 读不了 %s 的 NEED：%s" % (install_mod, e))
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "NEED":
                    try:
                        val = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError) as e:
                        print("[release] NEED 不是字面量列表：%s（%s）" % (install_mod, e))
                        return None
                    if isinstance(val, list) and all(isinstance(x, str) for x in val):
                        return val
    return None


def mods_dir() -> Path:
    import os
    g = os.environ.get("DSH_GAME_DIR")
    return (Path(g) / "mods") if g else (GAME_DIR / "mods")


def installed_jars(mods: Path = None) -> list:
    mods = mods or mods_dir()
    try:
        return sorted(p for p in mods.glob("dshbridge-*.jar"))
    except OSError as e:
        print("[release] 列游戏 mods/ 失败：%s（缺证据 ⇒ R1 会 BLOCK）" % (mods, e))
        return []


# ---------------------------------------------------------------- git
def _git(project_root: Path, args: list) -> tuple:
    """⇒ (rc, stdout)；取不到 ⇒ (99, '')（★不抛异常 ✗ 由调用方判 BLOCK✗★）"""
    try:
        r = subprocess.run(["git"] + args, cwd=str(project_root),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=25)
        return r.returncode, (r.stdout or "").strip()
    except Exception:
        return 99, ""


def git_head(project_root: Path) -> str | None:
    rc, out = _git(project_root, ["rev-parse", "HEAD"])
    return out if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", out) else None


def git_abbrev_head(project_root: Path) -> str | None:
    rc, out = _git(project_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    return out if rc == 0 and out and out != "HEAD" else None


def git_dirty(project_root: Path) -> list | None:
    """⇒ `git status --porcelain` 的行列表；取不到 ⇒ None"""
    rc, out = _git(project_root, ["status", "--porcelain"])
    if rc != 0:
        return None
    return [ln for ln in out.splitlines() if ln.strip()]


def _dirty_path(line: str) -> str:
    """porcelain 行 ⇒ 路径（处理 ` M x` / `?? x` / 重命名 `R  a -> b`）"""
    s = line[3:] if len(line) > 3 else ""
    if " -> " in s:
        s = s.split(" -> ", 1)[1]
    return s.strip().strip('"')


def dirty_blocking(lines: list) -> list:
    bad = []
    for ln in lines:
        p = _dirty_path(ln).replace("\\", "/")
        if not any(p == pre[:-1] or p.startswith(pre) for pre in DIRTY_ALLOW_PREFIX):
            bad.append(ln)
    return bad


# ---------------------------------------------------------------- manifest
def load_manifest(path: Path = MANIFEST) -> dict | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError) as e:
        print("[release] manifest 读不了/不是 JSON：%s：%s" % (path, e))
        return None


def manifest_record(ver: str, path: Path = MANIFEST) -> dict | None:
    d = load_manifest(path)
    if not d:
        return None
    rel = d.get("releases")
    rec = (rel or {}).get(ver) if isinstance(rel, dict) else None
    return rec if isinstance(rec, dict) else None


def record_release(project_root: Path = ROOT, libs: Path = None,
                   mods: Path = None, manifest: Path = None,
                   dry_run: bool = False) -> dict:
    """★--record✗★：验 jar 特征后写 manifest（版本/字节/sha256/commit/时间）"""
    libs = libs or (project_root / "mod" / "build" / "libs")
    manifest = manifest or (project_root / "state" / "release_manifest.json")
    ver = read_gradle_version(project_root)
    jar = newest_jar(libs)
    out = {"version": ver, "jar": None, "recorded": False, "reason": ""}
    if not ver:
        out["reason"] = "读不到 gradle.properties 的 mod_version"
        return out
    if not jar:
        out["reason"] = "build/libs 里没有 dshbridge-x.y.z.jar"
        return out
    if ".".join(str(x) for x in parse_version(jar.name)) != ver:
        out["reason"] = "build/libs 最新 jar=%s ≠ 源码版本 %s（先构建）" % (jar.name, ver)
        return out
    info = jar_info(jar)
    need = load_need(project_root / "tools" / "install_mod.py")
    if need is None:
        out["reason"] = "读不到 install_mod.py 的 NEED 列表"
        return out
    missing = [k for k in need if k not in info.get("text", "")]
    if missing:
        out["reason"] = "jar 缺特征 %d/%d（先重构建）：%s" % (len(missing), len(need), missing[:4])
        return out
    rec = {
        "version": ver, "jar": jar.name, "bytes": info["bytes"], "sha256": info["sha256"],
        "classes": info["classes"], "features_checked": len(need) - len(missing),
        "features_total": len(need), "commit": git_head(project_root) or "",
        "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    out.update({"jar": jar.name, "record": rec, "reason": "ok"})
    if dry_run:
        out["recorded"] = False
        out["dry_run"] = True
        return out
    d = load_manifest(manifest) or {}
    d["schema"] = SCHEMA
    d["updated_at"] = rec["recorded_at"]
    d["latest"] = ver
    d.setdefault("releases", {})
    if not isinstance(d["releases"], dict):
        d["releases"] = {}
    d["releases"][ver] = rec
    manifest.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest.with_suffix(manifest.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(manifest)
    out["recorded"] = True
    return out


# ---------------------------------------------------------------- 五件检查
def run_doc_gate(project_root: Path = ROOT) -> tuple:
    """⇒ (rc, tail)；复用 D7 闸门（它已包含 C1b 版本 ↔ 入口文档）"""
    p = project_root / "tools" / "doc_consistency_test.py"
    if not p.is_file():
        return 99, "doc_consistency_test.py 不在（缺证据）"
    try:
        r = subprocess.run([sys.executable, str(p)], cwd=str(project_root),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out
    except Exception as e:
        return 98, "%s: %s" % (type(e).__name__, str(e)[:80])


def check_release(project_root: Path = ROOT, libs: Path = None, mods: Path = None,
                  manifest: Path = None, doc_gate_runner=None,
                  git_status_lines=None, head=None, branch=None,
                  need: list = None, git_runner=None) -> dict:
    """★五件全查 ✗ 零写盘✗★ ⇒ {verdict, checks, reasons, facts}

    参数都可注入（判据用假项目/假 git 测 PASS/BLOCK ✗ 不依赖本仓当前状态 ✓）
    """
    project_root = Path(project_root)
    run_git = git_runner or _git     # ★可注入✗★：判据用假 git 测 R5b ✗ 不碰真仓 ✓
    libs = libs or (project_root / "mod" / "build" / "libs")
    manifest = manifest or (project_root / "state" / "release_manifest.json")
    mods = mods or mods_dir()
    checks, reasons = [], []

    def add(cid, name, ok, detail):
        checks.append({"id": cid, "name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            reasons.append("%s %s：%s" % (cid, name, detail))

    ver = read_gradle_version(project_root)
    jar = newest_jar(libs)
    info = jar_info(jar) if jar else None
    facts = {"version": ver, "jar": jar.name if jar else None,
             "bytes": info["bytes"] if info else None,
             "sha256": info["sha256"] if info else None}

    # ---- R1 版本单一真源（源码 ↔ 构建物 ↔ 安装物）
    if not ver:
        add("R1", "版本单一真源", False, "读不到 mod/gradle.properties 的 mod_version")
    elif not jar:
        add("R1", "版本单一真源", False, "build/libs 里没有 dshbridge-x.y.z.jar")
    elif ".".join(str(x) for x in parse_version(jar.name)) != ver:
        add("R1", "版本单一真源", False,
            "源码版本 %s ≠ 构建物最新 %s（先构建）" % (ver, jar.name))
    else:
        inst = installed_jars(mods)
        if len(inst) != 1:
            add("R1", "版本单一真源", False,
                "游戏 mods/ 里 dshbridge*.jar 应恰好 1 个（实际 %d 个：%s）"
                % (len(inst), [p.name for p in inst]))
        else:
            iv = ".".join(str(x) for x in (parse_version(inst[0].name) or (0, 0, 0)))
            same = (iv == ver) and (inst[0].stat().st_size == info["bytes"])
            add("R1", "版本单一真源", same,
                "gradle=%s ｜ build/libs=%s（%d B）｜ installed=%s（%d B）"
                % (ver, jar.name, info["bytes"], inst[0].name, inst[0].stat().st_size))

    # ---- R2 jar 内特征抽样（NEED 从 install_mod.py AST 读，不另抄）
    need = need if need is not None else load_need(project_root / "tools" / "install_mod.py")
    if info is None:
        add("R2", "jar 内特征", False, "没有可检查的 jar")
    elif not need:
        add("R2", "jar 内特征", False, "读不到 install_mod.py 的 NEED 列表（缺证据）")
    elif info.get("error"):
        add("R2", "jar 内特征", False, "jar 读不了：%s" % info["error"])
    else:
        missing = [k for k in need if k not in info["text"]]
        add("R2", "jar 内特征", not missing,
            "class=%d ｜ 特征 %d/%d %s"
            % (info["classes"], len(need) - len(missing), len(need),
               ("缺：" + str(missing[:5])) if missing else "全在 ✓"))

    # ---- R3 manifest 字节/sha256
    if not ver:
        add("R3", "发版清单", False, "没有版本，无法查 manifest")
    else:
        rec = manifest_record(ver, manifest)
        if not rec:
            add("R3", "发版清单", False,
                "state/release_manifest.json 里没有 %s 的记录 ⇒ 先跑 `--record`" % ver)
        elif info is None:
            add("R3", "发版清单", False, "没有 jar，无法对账")
        elif (rec.get("sha256") != info["sha256"]) or (int(rec.get("bytes", -1)) != info["bytes"]):
            add("R3", "发版清单", False,
                "manifest 记录 %s B/sha=%s ≠ 现 jar %d B/sha=%s"
                % (rec.get("bytes"), str(rec.get("sha256"))[:16], info["bytes"],
                   info["sha256"][:16]))
        else:
            add("R3", "发版清单", True,
                "manifest[%s] = %s B sha256=%s commit=%s"
                % (ver, rec.get("bytes"), info["sha256"][:16],
                   str(rec.get("commit") or "?")[:12]))

    # ---- R4 文档版本一致（复用 D7 闸门的 C1）
    if doc_gate_runner is None:
        rc, out = run_doc_gate(project_root)
    else:
        rc, out = doc_gate_runner()
    tail = ""
    if isinstance(out, str):
        lines = [ln.strip() for ln in out.splitlines()
                 if "SUMMARY" in ln or "=> doc_consistency" in ln or "C1b" in ln]
        tail = " ｜ ".join(lines[-2:])[:220] if lines else out.strip().splitlines()[-1][:160] if out.strip() else ""
    add("R4", "文档版本一致", rc == 0,
        "doc_consistency %s（rc=%s）%s" % ("PASS" if rc == 0 else "FAIL/BLOCK", rc, tail))

    # ---- R5 工作区干净度 ＋ HEAD 可追溯
    dlines = git_status_lines if git_status_lines is not None else git_dirty(project_root)
    h = head if head is not None else git_head(project_root)
    br = branch if branch is not None else git_abbrev_head(project_root)
    if dlines is None:
        add("R5", "工作区干净度", False, "取不到 git status（缺证据 ⇒ BLOCK）")
    else:
        bad = dirty_blocking(dlines)
        add("R5", "工作区干净度", not bad,
            "dirty=%d ｜ 白名单外=%d %s" % (len(dlines), len(bad), bad[:4] if bad else "✓"))
    if not h:
        add("R5b", "HEAD 可追溯", False, "取不到 git HEAD（缺证据 ⇒ BLOCK）")
    elif not br:
        add("R5b", "HEAD 可追溯", False, "detached HEAD（发版必须在分支上）")
    else:
        rc, _ = run_git(project_root, ["cat-file", "-e", h])
        rec = manifest_record(ver, manifest) if ver else None
        mc = (rec or {}).get("commit") or ""
        mc_ok = True
        if mc:
            rc2, _ = run_git(project_root, ["cat-file", "-e", mc])
            mc_ok = rc2 == 0
        add("R5b", "HEAD 可追溯", rc == 0 and mc_ok,
            "HEAD=%s（分支 %s）｜ manifest commit=%s %s"
            % (h[:12], br, mc[:12] or "（无记录）", "✓" if mc_ok else "（★git 里不存在✗★）"))

    verdict = "PASS" if all(c["ok"] for c in checks) else "BLOCK"
    return {"verdict": verdict, "checks": checks, "reasons": reasons, "facts": facts}


# ---------------------------------------------------------------- 输出
def _print_report(res: dict) -> None:
    f = res["facts"]
    print("== release check: dshbridge %s ==" % (f.get("version") or "?"))
    for c in res["checks"]:
        print("  %-3s %s %-14s %s"
              % (c["id"], "PASS" if c["ok"] else "BLOCK", c["name"], c["detail"]))
    if res["verdict"] == "PASS":
        print("RELEASE: PASS")
    else:
        print("RELEASE: BLOCK")
        for i, r in enumerate(res["reasons"], 1):
            print("  reason %d: %s" % (i, r))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--check", action="store_true", help="五件全查（默认）")
    ap.add_argument("--record", action="store_true", help="写 state/release_manifest.json")
    ap.add_argument("--dry-run", action="store_true", help="配合 --record：只打印不写盘")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    a = ap.parse_args(argv)

    if a.record:
        out = record_release(dry_run=a.dry_run)
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            if out.get("recorded") or out.get("dry_run"):
                rec = out["record"]
                print("== release record: dshbridge %s ==" % rec["version"])
                print("  jar=%s  bytes=%d  sha256=%s" % (rec["jar"], rec["bytes"], rec["sha256"][:16]))
                print("  commit=%s  features=%d/%d  recorded_at=%s"
                      % ((rec["commit"] or "?")[:12], rec["features_checked"],
                         rec["features_total"], rec["recorded_at"]))
                print("RECORD: %s" % ("DRY-RUN（没写盘）" if out.get("dry_run") else "WROTE manifest ✓"))
            else:
                print("RECORD: FAIL（%s）" % out.get("reason", "?"))
        return 0 if out.get("recorded") or out.get("dry_run") else 2

    res = check_release()
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        _print_report(res)
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
