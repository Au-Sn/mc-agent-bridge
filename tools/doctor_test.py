#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor_test.py -- 模块「一条命令回答为什么跑不起来」的离线判据（★不碰游戏/网络/真盘✗★）

CHECKS
  D1 全好夹具 ⇒ 退出码 0（每项都 OK）
  D2 MC_HOME 不在 ⇒ 退出码 1（home=FAIL）
  D3 离线数据缺 recipes ⇒ 退出码 1（data=FAIL 且点名缺什么）
  D4 已装 jar 版本 ≠ gradle ⇒ 退出码 1（version=FAIL）
  D5 没有 token ⇒ 退出码 1（token=FAIL；不做白名单绕）
  D6 /health 不通 ⇒ 退出码 2（**部分未知 ≠ 通过**）
  D7 进程判不了 ⇒ unknown；若 /health 通则进程算 OK（有证据）
  D8 --no-net ⇒ 退出码 2（跳过网络探活）
  D9 关键判据入口语法错 ⇒ 退出码 1（judges=FAIL）
  D10 CLI `--no-net --json` 输出可解析（真仓库只读；不碰网络）
  D11 计数一律读生成结果（改夹具里的 count ⇒ 输出跟着变，不写死 24779/20764）
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

import doctor as DOC          # noqa: E402
import paths as PA            # noqa: E402

SAVE = PA.SAVE_NAME


def make_fixture(td: pathlib.Path, *, with_home=True, jar_ver="2.56.0",
                 gradle="2.56.0", token=True, recipes=True, tags_count=9,
                 snap_count=13, judges_ok=True):
    root = td / "repo"
    home = td / "game"
    for d in ("build", "state/export_snapshots", "state", "mod", "tools",
              "game/mods", "game/saves/" + SAVE, "game/config/dshbridge"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (home / "mods").mkdir(parents=True, exist_ok=True)
    (home / "saves" / SAVE).mkdir(parents=True, exist_ok=True)
    (home / "config" / "dshbridge").mkdir(parents=True, exist_ok=True)
    if recipes:
        (root / "build" / "recipes.json").write_text(
            json.dumps({"a": 1, "b": 2, "c": 3}), encoding="utf-8")
    (root / "state" / "tags_category.json").write_text(
        json.dumps({"count": tags_count, "categories": {}}), encoding="utf-8")
    (root / "state" / "exceptions.json").write_text(
        json.dumps({"entries": [1, 2, 3]}), encoding="utf-8")
    (root / "state" / "export_snapshots" / "2.56.0__dshbridge_registry_blocks@1__20261102.json"
     ).write_text(json.dumps({"count": snap_count, "blocks": {}}), encoding="utf-8")
    # 2026-11-03 跨整合包就绪轮（§79.541）：doctor 新增 D9 world_profile ⇒ 全好夹具必须带**合法**档案，
    # 否则"无档案 = unknown" 会让 D1（exit 0）假红。
    (root / "state" / "world_profile.json").write_text(json.dumps({
        "schema": "dshbridge/world_profile@1",
        "pack_name": "fixture",
        "anchor": [0, 64, 0],
        "soak_anchor": [0, 64, 0],
        "test_platform": {"center": [0, 64, 0], "radius": 3,
                          "box": [-5, 63, -5, 5, 66, 5]},
        "no_dig_zones": [{"name": "home", "box": [0, 64, 0, 0, 64, 0]}],
        "contract_fixture": "state/contracts",
        "notes": "fixture",
    }), encoding="utf-8")
    (root / "mod" / "gradle.properties").write_text(
        "minecraft_version=1.20.1\nmod_version=%s\n" % gradle, encoding="utf-8")
    (home / "mods" / ("dshbridge-%s.jar" % jar_ver)).write_bytes(b"jar")
    if token:
        (home / "config" / "dshbridge" / "http_token.txt").write_text("tok",
                                                                      encoding="utf-8")
    for n in ("check_all.py", "portability_test.py", "humanlike_test.py"):
        body = "print('ok')\n" if judges_ok else "def broken(:\n"
        (root / "tools" / n).write_text(body, encoding="utf-8")
    return root, home


def run_fixture(root, home, **kw):
    token_files = kw.pop("token_files",
                         [home / "config" / "dshbridge" / "http_token.txt"])
    return DOC.run_doctor(
        root=root, home=home, save_name=SAVE,
        health_fn=kw.pop("health_fn", lambda: ("ok dshbridge-http", None)),
        process_fn=kw.pop("process_fn", lambda: ["javaw.exe"]),
        token_files=token_files,
        **kw)


def _status(rep, cid):
    for c in rep["checks"]:
        if c["id"] == cid:
            return c["status"]
    return None


def main() -> int:
    checks = []
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        # D1 全好 ⇒ exit 0
        root, home = make_fixture(td / "ok")
        r1 = run_fixture(root, home)
        checks.append(("D1 全好夹具 ⇒ 退出码 0（每项 OK）",
                       r1["exit"] == 0 and r1["summary"]["fail"] == 0
                       and r1["summary"]["unknown"] == 0
                       and "结论：全部通过" in r1["text"],
                       "exit=%s summary=%s" % (r1["exit"], r1["summary"])))

        # D2 MC_HOME 不在 ⇒ 1
        root2, home2 = make_fixture(td / "nohome")
        home2 = home2 / "does_not_exist"
        r2 = run_fixture(root2, home2,
                         token_files=[home2 / "config" / "dshbridge" / "http_token.txt"])
        checks.append(("D2 MC_HOME 不在 ⇒ 退出码 1（home=FAIL）",
                       r2["exit"] == 1 and _status(r2, "home") == "fail",
                       "exit=%s home=%s" % (r2["exit"], _status(r2, "home"))))

        # D3 缺 recipes ⇒ 1 且点名
        root3, home3 = make_fixture(td / "nodata", recipes=False)
        r3 = run_fixture(root3, home3)
        d3 = [c for c in r3["checks"] if c["id"] == "data"][0]
        checks.append(("D3 缺 recipes ⇒ 退出码 1（data=FAIL 且点名）",
                       r3["exit"] == 1 and d3["status"] == "fail"
                       and "recipes" in d3["detail"],
                       "%s ｜ %s" % (d3["status"], d3["detail"][:90])))

        # D4 jar 版本不一致 ⇒ 1
        root4, home4 = make_fixture(td / "ver", jar_ver="2.55.0", gradle="2.56.0")
        r4 = run_fixture(root4, home4)
        checks.append(("D4 jar 版本 ≠ gradle ⇒ 退出码 1（version=FAIL）",
                       r4["exit"] == 1 and _status(r4, "version") == "fail",
                       "exit=%s version=%s" % (r4["exit"], _status(r4, "version"))))

        # D5 没 token ⇒ 1
        root5, home5 = make_fixture(td / "notoken", token=False)
        r5 = run_fixture(root5, home5)
        checks.append(("D5 没有 token ⇒ 退出码 1（token=FAIL）",
                       r5["exit"] == 1 and _status(r5, "token") == "fail",
                       "exit=%s token=%s" % (r5["exit"], _status(r5, "token"))))

        # D6 /health 不通 ⇒ 2
        root6, home6 = make_fixture(td / "down")
        r6 = run_fixture(root6, home6, health_fn=lambda: (None, "URLError: refused"))
        checks.append(("D6 /health 不通 ⇒ 退出码 2（部分未知 ≠ 通过）",
                       r6["exit"] == 2 and _status(r6, "health") == "unknown"
                       and "部分未知" in r6["text"],
                       "exit=%s health=%s" % (r6["exit"], _status(r6, "health"))))

        # D7 进程判不了 ⇒ unknown；/health 通 ⇒ 进程算 OK
        root7, home7 = make_fixture(td / "proc")
        r7a = run_fixture(root7, home7, process_fn=lambda: None)
        r7b = run_fixture(root7, home7, process_fn=lambda: None,
                          health_fn=lambda: (None, "refused"))
        checks.append(("D7 进程判不了 ⇒ unknown；/health 通则进程算 OK",
                       _status(r7a, "process") == "ok"
                       and _status(r7b, "process") == "unknown"
                       and r7b["exit"] == 2,
                       "health通=%s health断=%s" % (_status(r7a, "process"),
                                                    _status(r7b, "process"))))

        # D8 --no-net ⇒ 2
        root8, home8 = make_fixture(td / "nonet")
        r8 = run_fixture(root8, home8, no_net=True)
        checks.append(("D8 --no-net ⇒ 退出码 2（跳过网络探活）",
                       r8["exit"] == 2 and _status(r8, "health") == "unknown",
                       "exit=%s health=%s" % (r8["exit"], _status(r8, "health"))))

        # D9 判据入口坏 ⇒ 1
        root9, home9 = make_fixture(td / "badjudge", judges_ok=False)
        r9 = run_fixture(root9, home9)
        checks.append(("D9 关键判据语法错 ⇒ 退出码 1（judges=FAIL）",
                       r9["exit"] == 1 and _status(r9, "judges") == "fail",
                       "exit=%s judges=%s" % (r9["exit"], _status(r9, "judges"))))

        # D11 ★计数读生成结果★：改夹具 count ⇒ 输出跟着变
        root11, home11 = make_fixture(td / "counts", tags_count=41, snap_count=77)
        r11 = run_fixture(root11, home11)
        d11 = [c for c in r11["checks"] if c["id"] == "data"][0]
        counts = (d11["evidence"] or [{}])[0]
        checks.append(("D11 ★计数读生成结果★（不改 24779/20764 字面量）",
                       counts.get("tags", {}).get("count") == 41
                       and counts.get("export", {}).get("count") == 77
                       and "24779" not in r11["text"] and "20764" not in r11["text"],
                       "tags=%s export=%s"
                       % (counts.get("tags", {}).get("count"),
                          counts.get("export", {}).get("count"))))

        # D12 世界档案坏 ⇒ 1（2026-11-03 §79.541：D9 world_profile 坏档必须 fail，不许 unknown 混过去）
        root12, home12 = make_fixture(td / "badwp")
        (root12 / "state" / "world_profile.json").write_text("{bad json", encoding="utf-8")
        r12 = run_fixture(root12, home12)
        checks.append(("D12 世界档案坏 ⇒ 退出码 1（world_profile=fail）",
                       r12["exit"] == 1 and _status(r12, "world_profile") == "fail",
                       "exit=%s world_profile=%s"
                       % (r12["exit"], _status(r12, "world_profile"))))

    # D10 CLI --no-net --json（真仓库只读；不碰网络）
    import subprocess
    env = dict(__import__("os").environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "doctor.py"),
                        "--no-net", "--json"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=str(ROOT), env=env,
                       timeout=120)
    ok10 = False
    detail10 = "rc=%s" % p.returncode
    try:
        rep10 = json.loads(p.stdout or "{}")
        ok10 = (isinstance(rep10.get("checks"), list)
                and rep10.get("schema") == "dshbridge/doctor@1"
                and rep10.get("exit") in (0, 1, 2)
                and isinstance(rep10.get("text"), str))
        detail10 = "rc=%s checks=%d exit=%s" % (p.returncode,
                                                len(rep10.get("checks") or []),
                                                rep10.get("exit"))
    except Exception as exc:                  # ★不许静默✗★
        detail10 += " 解析失败 %r" % (exc,)
    checks.append(("D10 CLI --no-net --json 输出可解析（只读，不碰网络）", ok10, detail10))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:130]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => doctor 有红（%d 项不对）" % bad)
        print("DOCTOR ok=0 bad=%d" % bad)
        return 1
    print("  => doctor 全绿（0/1/2 三态 ✗ 未知不算通过 ✗ 条数读生成结果）")
    print("DOCTOR ok=1 checks=%d" % len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
