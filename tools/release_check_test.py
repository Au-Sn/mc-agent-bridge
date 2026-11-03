#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release_check_test.py -- ★发版链 release.py 的离线判据（RC1~RC10 ✗ 2026-11-02）★

★为什么有它✗★（ADR-8 / 本任务「判据先自检能红」）：
  ★发版链最危险的失败是"★看起来 PASS ✗ 其实证据是缺的★"✗★ ——
    · manifest 没记录 ⇒ 若判据"没记录就当过" ⇒ 发版链等于没有 ✗
    · jar 里没新特征 ⇒ 装的是旧 jar ✗ 却 PASS ✗（P150 那一族）
    · 文档版本没跟上 ⇒ 入口文档对下一个人说谎 ✗（D7 已抓过一次）
  ⇒ 本判据用**假项目/假 jar/假 git/假闸门**把 release.check_release 的每条判定
    分别逼红一次 ✗ 再逼绿一次 ✓（★不写死本包版本号/字节数/特征串✗★：全部现造 ✓）

★口径✗★：
  · 只在 **临时目录** 里造假项目（系统 temp ✗ 不碰真仓 ✗ 用完删 ✓）
  · 假 NEED 用 `["alpha","beta"]`（假项目的 install_mod.py）⇒ 与真包 NEED 解耦 ✓
  · PASS 用例必须 PASS；每个 BLOCK 用例必须 BLOCK **且原因指向对应的 R 项** ✓
  · ★缺证据 → BLOCK✗★（R3 无 manifest／R5 无 git ⇒ 必须 BLOCK ✗ 不是 SKIP ✓）
  · ★自检能红✗★（M1）：把期望表整体取反 ⇒ 判据必须能发现，否则它自己不会红 ✓
"""
from __future__ import annotations

import hashlib
import io
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import release as R  # noqa: E402

ok = [True]
RESULTS = []

FAKE_NEED = ["alpha", "beta"]
FAKE_VER = "9.9.9"


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    RESULTS.append((tag, bool(cond)))
    print("  %-5s %s %s" % (tag, "✓" if cond else "★红✗★", note))


def _fake_git(dirty_text="", head="a" * 40, branch="master", valid_objects=True):
    """假 git：只回答 release.py 用到的四条命令（★不碰真仓✗★）"""
    def run(project_root, args):
        if args[:2] == ["rev-parse", "HEAD"]:
            return (0, head) if head is not None else (1, "")
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            return (0, branch) if branch is not None else (1, "")
        if args[:1] == ["status"]:
            return (0, dirty_text)
        if args[:1] == ["cat-file"]:
            return (0, "") if valid_objects else (1, "")
        return (99, "")
    return run


def make_project(base: Path, ver=FAKE_VER, jar_ver=None, need=None) -> dict:
    """★造一个假项目✗★：gradle.properties ＋ build/libs/<jar> ＋ tools/install_mod.py ＋ mods/ 安装件"""
    need = list(FAKE_NEED if need is None else need)
    jar_ver = jar_ver or ver
    proj = base
    (proj / "mod" / "build" / "libs").mkdir(parents=True, exist_ok=True)
    (proj / "mod" / "gradle.properties").write_text("mod_version=%s\n" % ver, encoding="utf-8")
    (proj / "tools").mkdir(parents=True, exist_ok=True)
    (proj / "tools" / "install_mod.py").write_text(
        "NEED = %r\n" % (need,), encoding="utf-8")
    jar = proj / "mod" / "build" / "libs" / ("dshbridge-%s.jar" % jar_ver)
    _write_jar(jar, " ".join(need))
    mods = proj / "mods"
    mods.mkdir(exist_ok=True)
    shutil.copy2(jar, mods / jar.name)
    (proj / "state").mkdir(exist_ok=True)
    return {"proj": proj, "jar": jar, "mods": mods,
            "manifest": proj / "state" / "release_manifest.json"}


def _write_jar(path: Path, class_text: str) -> None:
    """写一个最小 jar：只有一个 .class，内容就是我们要找的特征串"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("com/dsh/Fake.class", class_text.encode("utf-8"))


def run_check(env: dict, **kw) -> dict:
    return R.check_release(project_root=env["proj"], libs=env["proj"] / "mod" / "build" / "libs",
                           mods=env["mods"], manifest=env["manifest"],
                           doc_gate_runner=kw.pop("doc_gate", lambda: (0, "=> doc_consistency PASS ✓")),
                           git_status_lines=kw.pop("dirty", []),
                           head=kw.pop("head", "a" * 40),
                           branch=kw.pop("branch", "master"),
                           git_runner=kw.pop("git_runner", _fake_git()),
                           **kw)


def verdict_of(env: dict, **kw) -> dict:
    return run_check(env, **kw)


def reasons_text(res: dict) -> str:
    return "；".join(res.get("reasons") or [])


def has_reason_prefix(res: dict, prefix: str) -> bool:
    return any(r.startswith(prefix) for r in (res.get("reasons") or []))


print("== release_check：发版链 RC1~RC10（假项目/假 jar/假 git）==")
tmp = Path(tempfile.mkdtemp(prefix="dsh_release_test_"))
try:
    # ---------------- RC1 PASS：证据齐全 ⇒ PASS
    env = make_project(tmp / "p1")
    rec = R.record_release(env["proj"], libs=env["proj"] / "mod" / "build" / "libs",
                           manifest=env["manifest"])
    rc1 = verdict_of(env)
    check("RC1", rc1["verdict"] == "PASS" and rec.get("recorded"),
          "证据齐全（record 成功）⇒ %s ｜ 检查 %d 项全绿"
          % (rc1["verdict"], sum(1 for c in rc1["checks"] if c["ok"])))
    m1 = (env["manifest"].read_text(encoding="utf-8") if env["manifest"].is_file() else "")
    import json as _json
    _md = _json.loads(m1) if m1 else {}
    _jr = env["jar"].read_bytes()
    _rec = ((_md.get("releases") or {}).get(FAKE_VER) or {})
    check("RC1b", _rec.get("sha256") == hashlib.sha256(_jr).hexdigest()
          and _rec.get("bytes") == len(_jr),
          "manifest 记录 ＝ 真 jar 字节/sha256（%s B sha=%s…）"
          % (_rec.get("bytes"), str(_rec.get("sha256"))[:12]))

    # ---------------- RC2 BLOCK：sha 不匹配必红
    env2 = make_project(tmp / "p2")
    R.record_release(env2["proj"], libs=env2["proj"] / "mod" / "build" / "libs",
                     manifest=env2["manifest"])
    md = _json.loads(env2["manifest"].read_text(encoding="utf-8"))
    md["releases"][FAKE_VER]["sha256"] = "0" * 64
    env2["manifest"].write_text(_json.dumps(md), encoding="utf-8")
    r2 = verdict_of(env2)
    check("RC2", r2["verdict"] == "BLOCK" and has_reason_prefix(r2, "R3"),
          "manifest sha 被改 ✗ ⇒ %s ｜ 原因指向 R3：%s"
          % (r2["verdict"], [x for x in r2["reasons"] if x.startswith("R3")][:1]))

    # ---------------- RC3 BLOCK：版本不一致必红
    env3 = make_project(tmp / "p3", ver="9.9.10", jar_ver="9.9.9")
    R.record_release(env3["proj"], libs=env3["proj"] / "mod" / "build" / "libs",
                     manifest=env3["manifest"])
    r3 = verdict_of(env3)
    check("RC3", r3["verdict"] == "BLOCK" and has_reason_prefix(r3, "R1"),
          "源码 9.9.10 ≠ 构建物 9.9.9 ✗ ⇒ %s ｜ %s"
          % (r3["verdict"], [x for x in r3["reasons"] if x.startswith("R1")][:1]))

    # ---------------- RC4 BLOCK：jar 缺特征必红
    env4 = make_project(tmp / "p4")
    R.record_release(env4["proj"], libs=env4["proj"] / "mod" / "build" / "libs",
                     manifest=env4["manifest"])
    _write_jar(env4["jar"], "alpha only")                      # 只有 alpha ✗ 缺 beta
    shutil.copy2(env4["jar"], env4["mods"] / env4["jar"].name)  # 安装件同字节 ⇒ R1 仍绿
    md = _json.loads(env4["manifest"].read_text(encoding="utf-8"))
    import hashlib as _h
    md["releases"][FAKE_VER]["sha256"] = _h.sha256(env4["jar"].read_bytes()).hexdigest()
    md["releases"][FAKE_VER]["bytes"] = env4["jar"].stat().st_size
    env4["manifest"].write_text(_json.dumps(md), encoding="utf-8")
    r4 = verdict_of(env4)
    check("RC4", r4["verdict"] == "BLOCK" and has_reason_prefix(r4, "R2"),
          "jar 缺特征串 beta ✗ ⇒ %s ｜ %s"
          % (r4["verdict"], [x for x in r4["reasons"] if x.startswith("R2")][:1]))

    # ---------------- RC5 BLOCK：缺 manifest 记录 ⇒ 缺证据必 BLOCK（不许"没记录就当过"）
    env5 = make_project(tmp / "p5")
    r5 = verdict_of(env5)
    check("RC5", r5["verdict"] == "BLOCK" and has_reason_prefix(r5, "R3"),
          "没跑过 --record（manifest 缺记录）⇒ %s ｜ %s"
          % (r5["verdict"], [x for x in r5["reasons"] if x.startswith("R3")][:1]))

    # ---------------- RC6 BLOCK：文档闸门不过必红（复用 D7 C1）
    env6 = make_project(tmp / "p6")
    R.record_release(env6["proj"], libs=env6["proj"] / "mod" / "build" / "libs",
                     manifest=env6["manifest"])
    r6 = verdict_of(env6, doc_gate=lambda: (1, "C1b ★红✗★ 入口文档 9.9.9 ≠ 真源 9.9.10"))
    check("RC6", r6["verdict"] == "BLOCK" and has_reason_prefix(r6, "R4"),
          "入口文档版本不一致（D7 闸门 FAIL）✗ ⇒ %s ｜ %s"
          % (r6["verdict"], [x for x in r6["reasons"] if x.startswith("R4")][:1]))

    # ---------------- RC7 工作区：源码脏 ⇒ BLOCK；只有运行痕迹 ⇒ PASS（白名单）
    env7 = make_project(tmp / "p7")
    R.record_release(env7["proj"], libs=env7["proj"] / "mod" / "build" / "libs",
                     manifest=env7["manifest"])
    r7a = verdict_of(env7, dirty=[" M tools/hotfix.py", "?? tmp/scratch.py"])
    r7b = verdict_of(env7, dirty=[" M logs/check_all.txt", "?? tmp/scratch.py",
                                  " M state/no_dig.json"])
    check("RC7", r7a["verdict"] == "BLOCK" and has_reason_prefix(r7a, "R5")
          and r7b["verdict"] == "PASS",
          "源码脏 ⇒ BLOCK（%s）；只有 logs/tmp/state 运行痕迹 ⇒ PASS（%s）"
          % (r7a["verdict"], r7b["verdict"]))

    # ---------------- RC8 缺 git 证据 ⇒ BLOCK（不是 SKIP）；detached HEAD ⇒ BLOCK
    env8 = make_project(tmp / "p8")
    R.record_release(env8["proj"], libs=env8["proj"] / "mod" / "build" / "libs",
                     manifest=env8["manifest"])
    r8a = run_check(env8, dirty=None)                     # 取不到 git status
    r8b = run_check(env8, dirty=[], head=None)            # 取不到 HEAD
    r8c = run_check(env8, dirty=[], branch=None)          # detached HEAD
    check("RC8", r8a["verdict"] == "BLOCK" and has_reason_prefix(r8a, "R5")
          and r8b["verdict"] == "BLOCK" and has_reason_prefix(r8b, "R5b")
          and r8c["verdict"] == "BLOCK" and has_reason_prefix(r8c, "R5b"),
          "缺 git 证据 ⇒ BLOCK（%s/%s/%s）★缺证据不等于通过✗★"
          % (r8a["verdict"], r8b["verdict"], r8c["verdict"]))

    # ---------------- RC9 record 的边界：版本不匹配/缺 jar ⇒ 如实失败（不写假记录）
    env9 = make_project(tmp / "p9", ver="9.9.11", jar_ver="9.9.9")
    bad9 = R.record_release(env9["proj"], libs=env9["proj"] / "mod" / "build" / "libs",
                            manifest=env9["manifest"])
    check("RC9", (not bad9.get("recorded")) and (not env9["manifest"].is_file())
          and "≠" in (bad9.get("reason") or ""),
          "版本不匹配时 --record 必须**失败且不写盘** ⇒ recorded=%s reason=%s"
          % (bad9.get("recorded"), (bad9.get("reason") or "")[:48]))

    # ---------------- RC10 record 幂等：同版本重录 ⇒ 只有一条记录、内容一致
    env10 = make_project(tmp / "p10")
    a = R.record_release(env10["proj"], libs=env10["proj"] / "mod" / "build" / "libs",
                         manifest=env10["manifest"])
    b = R.record_release(env10["proj"], libs=env10["proj"] / "mod" / "build" / "libs",
                         manifest=env10["manifest"])
    md = _json.loads(env10["manifest"].read_text(encoding="utf-8"))
    check("RC10", a.get("recorded") and b.get("recorded")
          and len(md.get("releases") or {}) == 1 and md.get("latest") == FAKE_VER
          and md["releases"][FAKE_VER]["sha256"] == a["record"]["sha256"],
          "重录幂等 ⇒ releases=%d latest=%s" % (len(md.get("releases") or {}), md.get("latest")))

    # ---------------- M1 ★自检能红✗★：期望表取反 ⇒ 必须能发现（否则本判据不会红）
    def expect_mismatch(pairs):
        return [(tag, got, want) for (tag, got, want) in pairs if got != want]
    good = [("RC1", rc1["verdict"] == "PASS", True), ("RC2", r2["verdict"] == "BLOCK", True)]
    flipped = [("RC1", rc1["verdict"] == "PASS", False), ("RC2", r2["verdict"] == "BLOCK", False)]
    check("M1", expect_mismatch(good) == [] and expect_mismatch(flipped) != [],
          "★自检能红✗★：期望表正常 ⇒ 无差；整体取反 ⇒ 发现 %d 处差（判据本身可红 ✓）"
          % len(expect_mismatch(flipped)))

    # ---------------- M2 计数器：至少 10 条断言 ＋ 至少 8 个 PASS/BLOCK 结果被真算过
    _verdicts = [rc1["verdict"], r2["verdict"], r3["verdict"], r4["verdict"], r5["verdict"],
                 r6["verdict"], r7a["verdict"], r7b["verdict"], r8a["verdict"],
                 r8b["verdict"], r8c["verdict"]]
    check("M2", len(RESULTS) >= 10 and _verdicts.count("PASS") >= 1
          and _verdicts.count("BLOCK") >= 6,
          "计数器：断言 %d 条 ｜ 真跑过 %d 次判定（PASS %d / BLOCK %d）✗ 不许空转"
          % (len(RESULTS), len(_verdicts), _verdicts.count("PASS"), _verdicts.count("BLOCK")))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

_reds = [t for (t, o) in RESULTS if not o]
print("")
print("=> release_check %s（%d 条断言 ✗ 红 %d：%s）"
      % ("PASS ✓" if ok[0] else "FAIL", len(RESULTS), len(_reds), _reds or "无"))
print("RELEASECHECK ok=%d checks=%d" % (1 if ok[0] else 0, len(RESULTS)))
sys.exit(0 if ok[0] else 1)
