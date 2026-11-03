#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_mod_deps.py — 装模组前先核对依赖版本区间（避免启动崩溃）

背景（真实事故）：
    直接装 AdvancedPeripherals 0.7.46r 进 ATM9，启动即崩：
        Mod advancedperipherals requires computercraft 1.116.1 or above
        Currently, computercraft is 1.115.1
    原因是**只确认了"依赖模组存在"，没确认"版本区间满足"**。

本工具做的事：
    1. 从 Modrinth 拉取指定模组在指定 MC 版本 / 加载器下的全部版本
    2. 逐个下载 jar（带缓存）并读取里面的 META-INF/mods.toml
    3. 解析它声明的依赖及其 versionRange，判断本机已装版本是否满足
    4. 输出**最新的兼容版本**（可直接拿去装）

用法：
    py tools/check_mod_deps.py \
        --project advancedperipherals --mc 1.20.1 --loader forge \
        --target-mod computercraft --target-version 1.115.1

    # 只想看某个模组的依赖声明，不判定：
    py tools/check_mod_deps.py --project advancedperipherals --mc 1.20.1 --loader forge --show-only

    # 直接下载最新兼容版到指定路径：
    py tools/check_mod_deps.py ... --download-to "downloads/"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

API = "https://api.modrinth.com/v2"
UA = {"User-Agent": "mc-agent-bridge/0.1 (mod dependency checker)"}
CACHE = os.path.join("downloads", "cache")


def http_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def http_file(url: str, out: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    return out


# --------------------------------------------------------------------------- #
# Maven 风格版本区间（Forge mods.toml 用的写法）
# --------------------------------------------------------------------------- #
def vtuple(v: str):
    """把 1.116.1 / 0.7.46r 之类转成可比较元组"""
    parts = re.findall(r"\d+", v or "")
    return tuple(int(p) for p in parts) if parts else (0,)


def vcmp(a: str, b: str) -> int:
    ta, tb = vtuple(a), vtuple(b)
    n = max(len(ta), len(tb))
    ta = ta + (0,) * (n - len(ta))
    tb = tb + (0,) * (n - len(tb))
    return (ta > tb) - (ta < tb)


def satisfies(version: str, rng: str) -> tuple[bool, str]:
    """
    判断 version 是否落在 Forge 的 versionRange 内。
    支持：[1.0,)、[1.0,2.0)、(1.0,2.0]、[1.0]、以及裸版本号（Forge 视为"任意版本"）
    """
    rng = (rng or "").strip()
    if not rng or rng == "*":
        return True, "未限定（任意版本）"

    if not rng.startswith("[") and not rng.startswith("("):
        # 裸版本：Forge 当作"推荐版本"，不构成硬限制
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
    return True, "落在区间 %s" % rng


# --------------------------------------------------------------------------- #
# 读 jar 里的 mods.toml
# --------------------------------------------------------------------------- #
DEP_BLOCK = re.compile(r"\[\[dependencies\.(?P<owner>[^\]]+)\]\]", re.I)


def read_deps(jar_path: str):
    """返回 [(modId, versionRange, mandatory)]"""
    out = []
    try:
        with zipfile.ZipFile(jar_path) as z:
            name = None
            for cand in ("META-INF/mods.toml", "META-INF/neoforge.mods.toml"):
                if cand in z.namelist():
                    name = cand
                    break
            if not name:
                return None
            text = z.read(name).decode("utf-8", "replace")
    except Exception as e:
        print("    [!] 读取 jar 失败：%r" % (e,))
        return None

    # 按 [[dependencies.x]] 分块
    parts = DEP_BLOCK.split(text)
    # parts: [前言, owner1, body1, owner2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1]
        # 一个块里可能有多条依赖，用 [[ 或文件尾分隔
        for chunk in re.split(r"\n\s*\[\[", body):
            mid = re.search(r'modId\s*=\s*"([^"]+)"', chunk)
            if not mid:
                continue
            vr = re.search(r'versionRange\s*=\s*"([^"]*)"', chunk)
            md = re.search(r'mandatory\s*=\s*(true|false)', chunk)
            out.append((
                mid.group(1),
                (vr.group(1) if vr else ""),
                (md.group(1) == "true") if md else True,
            ))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Modrinth 模组版本兼容性核对")
    ap.add_argument("--project", required=True, help="模组 slug 或 project id（如 advancedperipherals）")
    ap.add_argument("--mc", default="1.20.1", help="Minecraft 版本")
    ap.add_argument("--loader", default="forge", help="加载器：forge / neoforge / fabric")
    ap.add_argument("--target-mod", help="要核对的依赖 modId（如 computercraft）")
    ap.add_argument("--target-version", help="本机已装版本（如 1.115.1）")
    ap.add_argument("--limit", type=int, default=8, help="最多检查几个版本（从新到旧）")
    ap.add_argument("--show-only", action="store_true", help="只列出依赖声明，不做判定")
    ap.add_argument("--download-to", help="把最新兼容版本下载到该目录")
    args = ap.parse_args(argv)

    q = urllib.parse.urlencode({
        "game_versions": json.dumps([args.mc]),
        "loaders": json.dumps([args.loader]),
    })
    url = "%s/project/%s/version?%s" % (API, args.project, q)
    print("查询：%s" % url)
    try:
        versions = http_json(url)
    except Exception as e:
        print("[X] 拉取版本列表失败：%r" % (e,))
        return 1

    if not versions:
        print("[X] 该 MC 版本 / 加载器下没有任何版本")
        return 1

    versions.sort(key=lambda v: v.get("date_published", ""), reverse=True)
    print("共 %d 个版本，检查最新 %d 个：\n" % (len(versions), min(args.limit, len(versions))))

    best = None
    for v in versions[: args.limit]:
        vnum = v.get("version_number", "?")
        pub = (v.get("date_published") or "")[:10]
        files = [f for f in v.get("files", []) if f.get("primary")] or v.get("files", [])
        if not files:
            continue
        f = files[0]
        cache_path = os.path.join(CACHE, f.get("filename") or (vnum + ".jar"))
        print("  [%s] %s  (%s)" % (vnum, f.get("filename"), pub))
        try:
            jar = http_file(f["url"], cache_path)
        except Exception as e:
            print("      [!] 下载失败：%r" % (e,))
            continue

        deps = read_deps(jar)
        if deps is None:
            print("      [!] jar 内无 mods.toml")
            continue

        if not deps:
            print("      （未声明任何依赖）")

        verdict = None
        for mid, vr, mand in deps:
            mark = ""
            if args.target_mod and mid.lower() == args.target_mod.lower():
                if args.target_version:
                    ok, why = satisfies(args.target_version, vr)
                    mark = "  => 本机 %s %s（%s）" % (
                        args.target_version, "满足" if ok else "不满足", why)
                    if mand:
                        verdict = ok
            print("      dep: %-22s range=%-16s mandatory=%-5s%s" % (mid, vr or "*", mand, mark))

        if args.show_only:
            continue

        if args.target_mod and args.target_version:
            if verdict is True:
                print("      >>> 兼容 ✓")
                if best is None:
                    best = (vnum, f)
                break
            elif verdict is False:
                print("      >>> 不兼容 ✗")
            else:
                print("      >>> 未声明对 %s 的依赖（按无约束处理）" % args.target_mod)
                if best is None:
                    best = (vnum, f)
        print()

    if best:
        print("=" * 60)
        print("结论：最新兼容版本 = %s" % best[0])
        print("      文件 = %s" % best[1].get("filename"))
        print("      URL  = %s" % best[1]["url"])
        if args.download_to:
            out = os.path.join(args.download_to, best[1].get("filename"))
            http_file(best[1]["url"], out)
            print("      已下载到 = %s" % out)
    elif not args.show_only:
        print("=" * 60)
        print("结论：前 %d 个版本里没有找到兼容的（可加大 --limit 继续往前找）" % args.limit)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
