#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dsh_cli.py -- ★DSH 可执行的**唯一**入口解析 ＋ 薄封装★（§79.365

★为什么要它✗★：★以前 `dsh_acp`／`dsh_live`／`dsh_live2`／`dsh_live3`／`dshrun` **5 份**
  `find_dsh()` 各写一遍 ✗ 改一处别处不动 ⇒ ★"★谁是权威★"永远说不清✗★ ✓
★现在✗★：★只此一份 ✗ 旧的 5 个已归档到 `tools/legacy/`（★保留可查 ✗ 不再使用✗★）✗★ ✓
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys, paths as PA

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def find_dsh() -> str | None:
    """★找 DSH 可执行：环境变量 → PATH → 常见安装位置✗★

    ★大脑层接缝✗★：本机路径不写死在业务代码里；找不到就返回 None，
    调用方用 `find_dsh_or_report()` 打印"需要配置 DSH_CMD/DSH_HOME"并非零退出。
    """
    for env in ("DSH_CMD", "DSH_BIN", "DSH_EXE", "DSH_HOME"):
        v = os.environ.get(env)
        if v and pathlib.Path(v).is_file():
            return v
        if v:
            for name in ("dsh.exe", "dsh.cmd", "dsh"):
                p = pathlib.Path(v) / name
                if p.is_file():
                    return str(p)
    w = shutil.which("dsh") or shutil.which("dsh.exe")
    if w:
        return w
    for pat in PA.DSH_EXE_GLOBS:
        import glob
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return None


def find_dsh_or_report(stream=None) -> str | None:
    """★找不到就**明确报错**✗★（打印配置提示；返回 None ⇒ 调用方非零退出）"""
    p = find_dsh()
    if p is None:
        print("需要配置 DSH_CMD / DSH_HOME（dsh 可执行文件路径），"
              "或把 dsh 加进 PATH", file=stream or sys.stderr)
    return p


def run(args, cwd=None, timeout=300):
    """★跑一次 DSH ✗ 返回 (rc, 输出)✗★"""
    import subprocess
    exe = find_dsh_or_report()
    if not exe:
        return 127, "（★找不到 DSH 可执行：需要配置 DSH_CMD / DSH_HOME✗★）"
    r = subprocess.run([exe] + [str(a) for a in args], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


if __name__ == "__main__":
    p = find_dsh_or_report()
    print("find_dsh ⇒ %s" % p)
    print("DSHCLI ok=%d" % (1 if p else 0))
    # ★未配置 ⇒ 非零退出✗★（否则脚本调用方会把"没找到"当成"成功"✗）
    raise SystemExit(0 if p else 2)
