#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inspect_jar.py — 装模组前核对依赖（读 jar 内声明的**真实**版本，不靠文件名猜）

为什么不能用文件名猜版本：
    实测踩坑——curios-forge-5.14.1+1.20.1.jar 会被猜成 1.20.1，
    Botania-1.20.1-448-FORGE.jar 会被猜成 1.20.1，全部误判。
    唯一可靠来源是每个 jar 里 META-INF/mods.toml 的 `version="..."`。

本工具做的事：
    1. 扫描 mods/ 目录下所有 jar，读出每个 mod 的 **modId + 真实版本**
    2. 读目标 jar 声明的依赖及其 versionRange
    3. 逐条判定：已装？版本满足？不满足？
       —— 只对 mandatory=true 的依赖计为"装上去会崩"

用法：
    # 检查某个 jar 能否安全装入某整合包
    py tools/inspect_jar.py --jar downloads/AdvancedPeripherals-1.20.1-0.7.44r.jar \
        --mods "<实例的 mods 目录>"

    # 只看某个整合包装了哪些模组与版本
    py tools/inspect_jar.py --list --mods "<mods 目录>"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# --------------------------------------------------------------------------- #
# 版本区间（Forge mods.toml 的 Maven 风格写法）
# --------------------------------------------------------------------------- #
def vtuple(v: str):
    parts = re.findall(r"\d+", v or "")
    return tuple(int(p) for p in parts) if parts else (0,)


def vcmp(a: str, b: str) -> int:
    ta, tb = vtuple(a), vtuple(b)
    n = max(len(ta), len(tb))
    ta += (0,) * (n - len(ta))
    tb += (0,) * (n - len(tb))
    return (ta > tb) - (ta < tb)


def satisfies(version: str, rng: str):
    rng = (rng or "").strip()
    if not rng or rng == "*":
        return True, "未限定"
    if not rng.startswith("[") and not rng.startswith("("):
        return True, "裸版本 %s（Forge 视为不限制）" % rng
    lo_incl = rng.startswith("[")
    hi_incl = rng.endswith("]")
    body = rng[1:-1]
    if "," not in body:
        return vcmp(version, body) == 0, "要求精确等于 %s" % body
    lo, hi = [p.strip() for p in body.split(",", 1)]
    if lo:
        c = vcmp(version, lo)
        if c < 0 or (c == 0 and not lo_incl):
            return False, "低于下界 %s" % lo
    if hi:
        c = vcmp(version, hi)
        if c > 0 or (c == 0 and not hi_incl):
            return False, "高于上界 %s" % hi
    return True, "落在 %s" % rng


# --------------------------------------------------------------------------- #
# 读 jar
# --------------------------------------------------------------------------- #
MODS_BLOCK = re.compile(r"\[\[mods\]\]", re.I)
DEP_BLOCK = re.compile(r"\[\[dependencies\.([^\]]+)\]\]", re.I)
TOML_CANDIDATES = ("META-INF/mods.toml", "META-INF/neoforge.mods.toml")


def _read_toml(jar_path: str) -> str | None:
    try:
        with zipfile.ZipFile(jar_path) as z:
            names = set(z.namelist())
            for cand in TOML_CANDIDATES:
                if cand in names:
                    return z.read(cand).decode("utf-8", "replace")
    except Exception:
        return None
    return None


def jar_identity(jar_path: str):
    """返回 [(modId, version)]"""
    text = _read_toml(jar_path)
    if not text:
        return []
    out = []
    for chunk in MODS_BLOCK.split(text)[1:]:
        chunk = re.split(r"\n\s*\[\[", chunk)[0]
        mid = re.search(r'modId\s*=\s*"([^"]+)"', chunk)
        ver = re.search(r'\bversion\s*=\s*"([^"]*)"', chunk)
        if mid:
            out.append((mid.group(1), ver.group(1) if ver else "?"))
    return out


def jar_deps(jar_path: str):
    """返回 [(modId, versionRange, mandatory)]"""
    text = _read_toml(jar_path)
    if not text:
        return []
    out = []
    parts = DEP_BLOCK.split(text)
    for i in range(1, len(parts) - 1, 2):
        for chunk in re.split(r"\n\s*\[\[", parts[i + 1]):
            mid = re.search(r'modId\s*=\s*"([^"]+)"', chunk)
            if not mid:
                continue
            vr = re.search(r'versionRange\s*=\s*"([^"]*)"', chunk)
            md = re.search(r'mandatory\s*=\s*(true|false)', chunk)
            out.append((mid.group(1),
                        vr.group(1) if vr else "",
                        (md.group(1) == "true") if md else True))
    return out


SPECIAL_SKIP = {"minecraft", "forge", "neoforge", "fml", "javafml"}


def scan_installed(mods_dir: str) -> dict:
    """返回 {modId: (filename, version)}——读 jar 内真实版本，不靠文件名"""
    index = {}
    if not mods_dir or not os.path.isdir(mods_dir):
        return index
    for fn in sorted(os.listdir(mods_dir)):
        if not fn.lower().endswith(".jar"):
            continue
        path = os.path.join(mods_dir, fn)
        for mid, ver in jar_identity(path):
            index.setdefault(mid.lower(), (fn, ver))
    return index


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按 jar 内真实版本核对依赖")
    ap.add_argument("--jar", help="要检查的 jar")
    ap.add_argument("--mods", help="整合包 mods 目录")
    ap.add_argument("--list", action="store_true", help="只列出 mods 里的模组与版本")
    args = ap.parse_args(argv)

    if args.list:
        idx = scan_installed(args.mods)
        print("mods 目录：%s" % args.mods)
        print("解析出 %d 个模组：\n" % len(idx))
        for mid in sorted(idx):
            fn, ver = idx[mid]
            print("  %-28s %-18s %s" % (mid, ver, fn))
        return 0

    if not args.jar or not os.path.isfile(args.jar):
        print("[X] 需要 --jar 指向存在的文件（或使用 --list）")
        return 2

    deps = jar_deps(args.jar)
    if not deps:
        print("[X] 读不到依赖声明（可能不是 Forge 模组）")
        return 1

    idx = scan_installed(args.mods) if args.mods else {}
    print("=" * 74)
    print("Jar : %s" % os.path.basename(args.jar))
    ident = jar_identity(args.jar)
    if ident:
        print("自身: %s" % ", ".join("%s@%s" % (m, v) for m, v in ident))
    if idx:
        print("对照: %s（解析出 %d 个模组）" % (args.mods, len(idx)))
    print("=" * 74)

    bad = []
    for mid, rng, mand in deps:
        head = "  %-22s range=%-24s %s" % (mid, rng or "*", "必装" if mand else "可选")
        if mid.lower() in SPECIAL_SKIP:
            print(head + "  → 跳过（游戏本体/加载器）")
            continue
        if not idx:
            print(head)
            continue

        hit = idx.get(mid.lower())
        if not hit:
            print(head + ("  → [缺失]" if mand else "  → [可选且未装]"))
            if mand:
                bad.append((mid, rng, "未安装"))
            continue

        fn, ver = hit
        ok, why = satisfies(ver, rng)
        if ok:
            print(head + "  → ok  (已装 %s, v%s)" % (fn, ver))
        else:
            print(head + "  → [不满足] 已装 v%s：%s" % (ver, why))
            if mand:
                bad.append((mid, rng, "已装 v%s，%s" % (ver, why)))

    print("=" * 74)
    if not idx:
        print("未提供 --mods，仅列出依赖声明")
    elif not bad:
        print("结论：所有**必装**依赖都满足 ✓  可以安全装入")
    else:
        print("结论：有 %d 处必装依赖不满足，装上会启动崩溃 ✗" % len(bad))
        for mid, rng, why in bad:
            print("      - %s 需要 %s，实际 %s" % (mid, rng, why))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
