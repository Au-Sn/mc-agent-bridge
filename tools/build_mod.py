#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_mod.py —— 不用 gradle 也能**验编译**（因为这台机器现在下不到 gradle 发行版 ✗）

## 为什么需要它 ✗（实测 2026-09-23 ✓）
  · `gradlew.bat build` 直接失败 ✓：`~/.gradle/wrapper/dists/gradle-8.1.1-bin/…` 里
    **只有一个 `.part`**（下载中断的残骸 ✗）⇒ 它又要去 `services.gradle.org` 下 ✗
    ⇒ 这台机器**连不上**（`SocketTimeoutException: Connect timed out` ✗）
  · 但**依赖全在本地缓存里** ✓（`forge_gradle/minecraft_user_repo` 有映射过的 MC＋Forge ✓
    `forge_gradle/maven_downloader` 有全部库 ✓）⇒ 用 `javac` 直接编**能过** ✓
  ⇒ 于是：**编译正确性**用这个脚本保证 ✓；**出正式 jar**（要 reobf）仍然得等 gradle 能跑 ✓

## 用法
    py tools/build_mod.py            # 只验编译（快 ✓ 输出 ASCII ✓）
    py tools/build_mod.py --jar      # 顺带打一个**开发用** jar（★没有 reobf★ ✗ 只能用于验证 ✓）
判据 ✓：javac 退出码 0 ✓ 且 class 文件数 ≥ 5 ✓（少于 5 ⇒ 只编了一部分 ⇒ 大声报 ✗）
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "mod" / "src" / "main" / "java"
RES = ROOT / "mod" / "src" / "main" / "resources"
OUT = ROOT / "mod" / "build" / "javac_check"
GRADLE_CACHE = Path(os.environ.get("USERPROFILE", "")) / ".gradle" / "caches" / "forge_gradle"
JDK = ROOT / "mod" / "jdk" / "jdk-17.0.20.1+1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _has(z: Path, prefix: str) -> bool:
    try:
        with zipfile.ZipFile(z) as f:
            for n in f.namelist():
                if n.startswith(prefix):
                    return True
    except Exception:
        return False
    return False


MC_KEEP = "forge-1.20.1-47.2.20_mapped_official_1.20.1.jar"


def classpath() -> tuple:
    """编译用的 classpath ✓ **每个 jar 都要先验一遍能打开** ✗

    ⚠ 实测 2026-09-23 ✓：缓存里有个**残缺 jar**（`mcp_repo/.../mergeMappings/output.jar` ✓
      下载中断留下的 ✗）⇒ javac 报 `zip END header not found` ✗ 而**退出码是 2** ✓
      看起来像"代码有错"✗ ⇒ 花了我一轮才定位 ✓

    ⚠ 更要命的一条 ✗：Minecraft 的类在缓存里**有好几份**（映射过的官方名 ✓ SRG 名 ✓
      binpatched ✓ injected ✓ vanilla client ✓）⇒ 一股脑塞进 classpath ⇒
      javac 从**名字不对的那一份**里解析 `ServerPlayer` ✗ ⇒ 报
      「找不到符号: 方法 getGameProfile()」✗ —— 看着像我的代码错 ✗ 其实是**类路径撞车** ✗
      ⇒ 纪律：★Minecraft 的类**只留映射过官方名的那一个 jar**★ ✗
         （判据：除了它，任何**含 `net/minecraft/` 的 jar 一律不上 classpath** ✓）
    """
    good, bad, skipped = [], [], []
    roots = [GRADLE_CACHE, Path(os.environ.get("USERPROFILE", "")) / ".gradle" / "caches" / "modules-2"]
    for root in roots:
        if not root.is_dir():
            continue
        for j in root.rglob("*.jar"):
            n = j.name
            if n.endswith("-sources.jar") or n.endswith("-javadoc.jar"):
                continue      # ★sources jar 绝对不能上 classpath★ ✗（javac 会去编 Forge 的源码 ✗）
            if n.startswith("forge-1.20.1-47.2.20") and n.endswith(("-srg.jar", "-userdev.jar")):
                continue
            try:
                if not zipfile.is_zipfile(j):
                    bad.append(j)
                    continue
            except Exception:
                bad.append(j)
                continue
            if n != MC_KEEP and _has(j, "net/minecraft/"):
                skipped.append(j)          # ← SRG/binpatched/client 这些重复的 MC ✗
                continue
            good.append(j)
    return sorted(set(good)), bad, skipped


def main(argv) -> int:
    javac = JDK / "bin" / "javac.exe"
    if not javac.is_file():
        print("no javac at %s" % javac)
        return 2
    cp, broken, skipped = classpath()
    if not cp:
        print("no cached deps under %s" % GRADLE_CACHE)
        return 2
    if broken:
        print("⚠ 缓存里有 %d 个**坏的 jar**（下载残缺 ✓ 已跳过 ✗）：" % len(broken))
        for b in broken[:5]:
            print("   " + re.sub(r"[^\x20-\x7e]", "?", str(b))[:160])
    if skipped:
        print("（另有 %d 个含 net/minecraft/ 的重复 jar 被**故意**排除 ✓ 只留 %s ✓）"
              % (len(skipped), MC_KEEP))
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    srcs = sorted(str(p) for p in SRC.rglob("*.java"))
    cpstr = os.pathsep.join(str(p) for p in cp)
    # ★必须走 @argfile★ ✗（实测 2026-09-23 ✓）：111 个 jar 的全路径拼起来超过
    #   Windows 的命令行上限 ⇒ javac 直接 `exit=2` 而且**一条像样的错误都不给** ✗
    #   （表现是"编译失败但看不出为什么"✗ —— 所以我先把 stderr 全打出来才找到 ✓）
    # ★@argfile 里**反斜杠会被吃掉**★ ✗（实测 ✓：`用户目录路径` 变成 `C:Users...` ✗
    #   表现同样是"exit=2 一条像样错误都没有"✗）⇒ 一律换成**正斜杠** ✓（Java 在 Windows 上认 ✓）
    def fw(p) -> str:
        return str(p).replace("\\", "/")

    argfile = OUT.parent / "javac_args.txt"
    args = ['-nowarn', '-encoding', 'UTF-8', '-cp', '"%s"' % fw(cpstr), '-d', '"%s"' % fw(OUT)]
    args += ['"%s"' % fw(s) for s in srcs]
    argfile.write_text("\n".join(args), encoding="utf-8")
    cmd = [str(javac), "@%s" % argfile]
    print("javac: %d 个源文件 ｜ classpath %d 个 jar ｜ 参数走 @argfile（太长 ✗）"
          % (len(srcs), len(cp)))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    err = (r.stderr or "") + (r.stdout or "")
    bad = [ln for ln in err.splitlines() if "error" in ln.lower() or "错误" in ln]
    if bad:
        print("★编译错误 %d 条★" % len(bad))
        for ln in bad[:25]:
            print("   " + re.sub(r"[^\x20-\x7e]", "?", ln)[:200])
    elif r.returncode != 0:
        print("★javac exit=%s 但没匹配到 error 行 ⇒ 把原文打出来★" % r.returncode)
        for ln in err.splitlines()[:20]:
            print("   " + re.sub(r"[^\x20-\x7e]", "?", ln)[:200])
    nclass = len(list(OUT.rglob("*.class")))
    print("=> javac exit=%s ｜ 产出的 class 文件 %d 个" % (r.returncode, nclass))
    if r.returncode != 0 or nclass < 5:
        print("★编译没通过★ ✗（不许当成「编好了」✗）")
        return 1
    print("编译通过 ✓（注意：这只证明**源码编得过** ✓ 正式 jar 还要 reobf ✗）")
    if "--jar" in argv:
        ver = "dev"
        gp = ROOT / "mod" / "gradle.properties"
        for ln in gp.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith("mod_version="):
                ver = ln.split("=", 1)[1].strip()
        jar = ROOT / "mod" / "build" / "libs" / ("dshbridge-%s-javac-dev.jar" % ver)
        jar.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as z:
            for p in OUT.rglob("*.class"):
                z.write(p, str(p.relative_to(OUT)))
            if RES.is_dir():
                for p in RES.rglob("*"):
                    if p.is_file():
                        z.write(p, str(p.relative_to(RES)))
        print("开发用 jar: %s (%d B) ★没有 reobf ⇒ 别丢进 mods/ 当真★"
              % (jar.name, jar.stat().st_size))
    return 0


raise SystemExit(main(sys.argv[1:]))
