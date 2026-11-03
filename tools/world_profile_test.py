#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world_profile_test.py -- ★跨整合包世界档案的离线判据✗★（W1~W6 ✓ 不需要游戏 ✓ 秒级 ✓）

WHY（用户口径 2026-11-03）：
  「哪怕是一个勉强能用的，也不能只在一个 1.20.1 的 ATM9 整合包里运行。」
  代码不绑定整合包；绑死的是**世界常量**（锚点/测试平台/不可挖区/契约夹具）。
  `tools/world_profile.py` 把它们收成一个可读文件；**没有档案必须明确说'没有'**，
  不许静默用本机默认 —— 本判据就是守这条的（先自检能红 ✓）。

判据（W1~W6；错误一律"明确失败"，不许静默兜底）：
  W1 无文件 ⇒ load 返回 None ＋原因；--show 退出码 2（"还没配"=INCONCLUSIVE，不是坏）
  W2 合法档案 ⇒ recover/soak_suite/doctor 三处都**真的读到**（纯函数注入，不连游戏）
  W3 坏 JSON／缺字段 ⇒ 明确失败（load 返回 None＋原因；--check 退出码 1）
  W4 `--init` 幂等（第二次"内容一致未重写"）＋生成的示例可读、带"示例"标注
  W5 优先级 CLI ＞ 环境变量 ＞ 档案 ＞ 无（★无档案不许给本机默认✗★）
  W6 档案里不允许本机绝对路径（盘符/用户主目录）；--init 产物也不许有
用法：
  py tools/world_profile_test.py           # 0=全绿；1=有红
  py tools/world_profile_test.py --only W4
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import world_profile as WP  # noqa: E402


# ------------------------------------------------------------------ 小工具
def _run(argv, timeout=120):
    import subprocess
    return subprocess.run([str(a) for a in argv], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=dict(os.environ))


def _wp(args, timeout=120):
    return _run([sys.executable, "-B", "-u", "-X", "utf8",
                 ROOT / "tools" / "world_profile.py"] + list(args), timeout)


def _doc(**over):
    d = WP.example_document()
    d.update(over)
    return d


def _write(path: Path, doc) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _abs_sample() -> str:
    """□ 本机绝对路径样本（★不写死在源码里✗★：拼出来，避免自己被 portability 判据误报）"""
    return "C:" + os.sep + "Users" + os.sep + "alice" + os.sep + "world"


# ------------------------------------------------------------------ W1
def W1_missing_file():
    """无档案 ⇒ 返回 None＋原因，不许静默给本机默认"""
    with tempfile.TemporaryDirectory(prefix="wp_w1_") as td:
        missing = Path(td) / "no_such_profile.json"
        doc, reason = WP.load(missing)
        assert doc is None, "无档案居然返回了档案：%r" % (doc,)
        for tok in ("不存在", "不静默", "world_profile"):
            assert tok in reason, "原因里缺 %r：%s" % (tok, reason)
        val, source, why = WP.resolve_anchor("anchor", path=missing)
        assert val is None and source == "none", "无档案/无CLI/无env 居然给了锚点：%r" % (val,)
        assert why, "无档案必须给出原因"
        r = _wp(["--file", missing, "--show"])
        assert r.returncode == 2, "无档案 --show 应退出 2（还没配=INCONCLUSIVE），实际 %d" % \
            r.returncode
        out = (r.stdout or "") + (r.stderr or "")
        assert "WORLDPROFILE ok=0" in out and "no_file" in out, "机器行不对：%s" % out[-300:]
        return "无档案 ⇒ None+原因；--show exit2 且打印'还没配'"


# ------------------------------------------------------------------ W2
def W2_consumed_by_tools():
    """合法档案 ⇒ recover/soak_suite/doctor 三处都读到（注入纯函数，不连游戏）"""
    with tempfile.TemporaryDirectory(prefix="wp_w2_") as td:
        p = Path(td) / "world_profile.json"
        _write(p, _doc(anchor=[100, 65, -3], soak_anchor=[101, 66, -4]))
        # ① recover：默认锚点来自档案
        import recover
        got = recover.default_anchor(profile_path=str(p))
        assert got == "100 65 -3", "recover 没读到档案锚点：%r" % (got,)
        # ② soak_suite：默认浸泡锚点来自档案
        import soak_suite
        got2 = soak_suite.default_anchor(profile_path=str(p))
        assert tuple(got2) == (101, 66, -4), "soak_suite 没读到档案锚点：%r" % (got2,)
        # ③ doctor：世界档案检查变 ok
        import doctor
        ck = doctor._world_profile_check(root=td, path=str(p))
        assert ck["status"] == "ok", "doctor 没认档案：%r" % (ck,)
        # ④ 机器行（子进程 --show）
        r = _wp(["--file", p, "--show"])
        assert r.returncode == 0, "--show 合法档案应 exit0：%s" % (r.stdout or r.stderr)
        out = (r.stdout or "") + (r.stderr or "")
        assert "WORLDPROFILE ok=1" in out and "anchor=100,65,-3" in out, \
            "机器行没体现档案锚点：%s" % out[-400:]
        return "recover/soak/doctor 三处都真读到档案值（--show 机器行一致）"


# ------------------------------------------------------------------ W3
def W3_bad_document():
    """坏 JSON／缺字段 ⇒ 明确失败，不许兜底"""
    with tempfile.TemporaryDirectory(prefix="wp_w3_") as td:
        bad = Path(td) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        doc, reason = WP.load(bad)
        assert doc is None and "不是合法 JSON" in reason, "坏 JSON 未明确失败：%r" % (reason,)
        r = _wp(["--file", bad, "--check"])
        assert r.returncode == 1, "坏 JSON --check 应 exit1，实际 %d" % r.returncode
        out = (r.stdout or "") + (r.stderr or "")
        assert "WORLDPROFILE ok=0" in out and "invalid" in out, "坏 JSON 机器行不对：%s" % out[-300:]
        # 缺字段（anchor）
        d = _doc()
        d.pop("anchor")
        errs = WP.validate(d)
        assert any("anchor" in e for e in errs), "缺 anchor 未报错：%r" % (errs,)
        missing_field = Path(td) / "no_anchor.json"
        _write(missing_field, d)
        doc2, reason2 = WP.load(missing_field)
        assert doc2 is None and "anchor" in reason2, "缺 anchor 未明确失败：%r" % (reason2,)
        r2 = _wp(["--file", missing_field, "--check"])
        assert r2.returncode == 1, "缺字段 --check 应 exit1，实际 %d" % r2.returncode
        return "坏 JSON/缺字段 ⇒ load None+原因；--check exit1"


# ------------------------------------------------------------------ W4
def W4_init_idempotent():
    """--init 幂等 + 生成可读示例（第二次内容一致不重写；改过的拒绝覆盖）"""
    with tempfile.TemporaryDirectory(prefix="wp_w4_") as td:
        p = Path(td) / "sub" / "world_profile.json"
        r1 = _wp(["--init", "--file", p])
        out1 = (r1.stdout or "") + (r1.stderr or "")
        assert r1.returncode == 0 and "action=written" in out1, "首次 --init 失败：%s" % out1[-400:]
        assert p.is_file(), "--init 没写文件"
        text1 = p.read_text(encoding="utf-8", errors="replace")
        # 可读 + 字段齐 + 标注示例
        d = json.loads(text1)
        assert d.get("schema") == WP.SCHEMA and d.get("pack_name"), "示例档案字段不齐"
        for k in ("anchor", "soak_anchor", "test_platform", "no_dig_zones",
                  "contract_fixture", "notes"):
            assert k in d, "示例档案缺字段 %s" % k
        assert "示例" in str(d.get("notes")), "示例档案没标注'示例，换包请改'"
        assert not WP.has_abs_path(text1), "示例档案里出现了本机绝对路径"
        # 幂等：第二次内容一字不差
        r2 = _wp(["--init", "--file", p])
        out2 = (r2.stdout or "") + (r2.stderr or "")
        assert r2.returncode == 0 and "action=unchanged" in out2, \
            "第二次 --init 不是幂等：%s" % out2[-400:]
        assert p.read_text(encoding="utf-8", errors="replace") == text1, \
            "幂等那次居然重写了文件"
        # 改过的档案：默认拒绝覆盖（保护改好的世界值）
        changed = json.loads(text1)
        changed["anchor"] = [1, 2, 3]
        _write(p, changed)
        r3 = _wp(["--init", "--file", p])
        assert r3.returncode == 1 and "action=exists" in ((r3.stdout or "") + (r3.stderr or "")), \
            "已存在且不同却允许覆盖（会冲掉改好的世界值）"
        # --force 才覆盖
        r4 = _wp(["--init", "--file", p, "--force"])
        assert r4.returncode == 0 and "action=written" in ((r4.stdout or "") + (r4.stderr or "")), \
            "--force 覆盖失败"
        return "--init 幂等(unchanged)+拒绝覆盖改过的+--force 可覆盖；示例字段齐/带'示例'/无绝对路径"


# ------------------------------------------------------------------ W5
def W5_priority():
    """优先级：CLI ＞ env ＞ 档案 ＞ 无（无档案不许给本机默认）"""
    with tempfile.TemporaryDirectory(prefix="wp_w5_") as td:
        p = Path(td) / "world_profile.json"
        _write(p, _doc(anchor=[1, 2, 3], soak_anchor=[4, 5, 6]))
        val, src, _ = WP.resolve_anchor("anchor", path=p)
        assert val == (1, 2, 3) and src == "profile", "档案优先档不对：%r/%r" % (val, src)
        val, src, _ = WP.resolve_anchor("anchor", path=p,
                                        env={"DSH_WORLD_ANCHOR": "7 8 9"})
        assert val == (7, 8, 9) and src == "env", "env 优先档不对：%r/%r" % (val, src)
        val, src, _ = WP.resolve_anchor("anchor", path=p, cli="10 11 12",
                                        env={"DSH_WORLD_ANCHOR": "7 8 9"})
        assert val == (10, 11, 12) and src == "cli", "CLI 优先档不对：%r/%r" % (val, src)
        # soak_anchor：专用 env 优先；没专用 env 时回落到世界锚点 env
        val, src, _ = WP.resolve_anchor("soak_anchor", path=p,
                                        env={"DSH_SOAK_ANCHOR": "20 21 22"})
        assert val == (20, 21, 22) and src == "env", "soak 专用 env 没生效：%r" % (val,)
        val, src, _ = WP.resolve_anchor("soak_anchor", path=p,
                                        env={"DSH_WORLD_ANCHOR": "30 31 32"})
        assert val == (30, 31, 32) and src == "env", "soak 回落世界 env 没生效：%r" % (val,)
        # 无档案/无 env/无 CLI ⇒ None（★不给本机默认✗★）
        val, src, why = WP.resolve_anchor("anchor", path=Path(td) / "missing.json", env={})
        assert val is None and src == "none" and why, "无档案却兜底了默认：%r" % (val,)
        # CLI 写坏 ⇒ 明确抛错（不静默）
        try:
            WP.resolve_anchor("anchor", cli="1 2", env={})
        except ValueError as exc:
            assert "--anchor" in str(exc) or "anchor" in str(exc), "CLI 解析错误没说明白：%s" % exc
        else:
            raise AssertionError("CLI 只给 2 个数却没报错")
        return "CLI>env>档案>无；无档案给 None+原因；坏 CLI 明确抛错"


# ------------------------------------------------------------------ W6
def W6_no_absolute_paths():
    """档案里不许出现本机绝对路径（盘符/用户主目录）；contract_fixture 必须相对"""
    bad1 = _doc()
    bad1["notes"] = "world data at " + _abs_sample() + " (本机)"
    errs1 = WP.validate(bad1)
    assert any("绝对路径" in e for e in errs1), "含本机绝对路径却没报错：%r" % (errs1,)
    bad2 = _doc(contract_fixture=("D:" + os.sep + "pkg" + os.sep + "contracts"))
    errs2 = WP.validate(bad2)
    assert any("相对" in e or "绝对" in e for e in errs2), \
        "contract_fixture 绝对路径没报错：%r" % (errs2,)
    bad3 = _doc(contract_fixture="state/../outside")
    errs3 = WP.validate(bad3)
    assert any(".." in e for e in errs3), "contract_fixture 用 .. 跳出仓库没报错：%r" % (errs3,)
    # 合法示例必须通过，且 --init 文本里没有绝对路径
    assert not WP.validate(_doc()), "合法示例居然校验失败：%r" % (WP.validate(_doc()),)
    with tempfile.TemporaryDirectory(prefix="wp_w6_") as td:
        p = Path(td) / "wp.json"
        WP.write_example(p)
        text = p.read_text(encoding="utf-8", errors="replace")
        assert not WP.has_abs_path(text), "--init 产物里有本机绝对路径"
    return "绝对路径/.. 逃逸都判红；合法示例与 --init 产物无绝对路径"


CHECKS = [
    ("W1 无档案 ⇒ None+原因，不静默兜底", W1_missing_file),
    ("W2 recover/soak/doctor 真读到档案", W2_consumed_by_tools),
    ("W3 坏 JSON/缺字段 ⇒ 明确失败", W3_bad_document),
    ("W4 --init 幂等＋示例可读带标注", W4_init_idempotent),
    ("W5 优先级 CLI>env>档案>无", W5_priority),
    ("W6 档案不许本机绝对路径", W6_no_absolute_paths),
]


def main(argv) -> int:
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        only = argv[i + 1].split(",") if i + 1 < len(argv) else None
    bad = 0
    ran = 0
    print("== world_profile 判据（W1~W6：跨整合包世界档案 ✓ 离线 ✓）==")
    for name, fn in CHECKS:
        if only and not any(name.startswith(o) for o in only):
            continue
        ran += 1
        try:
            detail = fn()
            print("  PASS %-40s | %s" % (name, str(detail)[:220]))
        except AssertionError as exc:
            bad += 1
            print("  FAIL %-40s | %s" % (name, str(exc)[:400]))
        except Exception as exc:               # ★不许静默✗★
            bad += 1
            print("  FAIL %-40s | %s: %s" % (name, type(exc).__name__, str(exc)[:300]))
            traceback.print_exc()
    assert ran > 0, "一条判据都没跑（--only 写错了？）"
    print("  ---- %d/%d ----" % (ran - bad, ran))
    if bad:
        print("  => world_profile FAIL（跨包世界档案层不合格）")
        print("WORLDPROFILE ok=0 checks=%d fail=%d" % (ran, bad))
        return 1
    print("  => world_profile PASS（无档案不兜底/三处接线/坏档案能红/init 幂等/优先级/无绝对路径）")
    print("WORLDPROFILE ok=1 checks=%d" % ran)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
