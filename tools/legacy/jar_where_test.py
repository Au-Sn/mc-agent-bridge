"""jar_where_test.py -- 到底哪个 jar 里有 Forge 的类（量一下 ✓ 别猜 ✗）"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

GC = Path.home() / ".gradle" / "caches" / "forge_gradle"
WANT = ["net/minecraftforge/fml/common/Mod.class",
        "net/minecraftforge/eventbus/api/SubscribeEvent.class",
        "net/minecraft/world/level/Level.class",
        "net/minecraft/server/level/ServerPlayer.class"]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> int:
    roots = [GC, Path.home() / ".gradle" / "caches" / "modules-2"]
    jars = []
    for root in roots:
        if root.is_dir():
            jars += [p for p in root.rglob("*.jar")
                     if any(k in p.name.lower() for k in
                            ("forge", "fml", "eventbus", "modlauncher", "minecraft"))]
    jars = sorted(set(jars))
    print("候选 jar %d 个（只看名字里带 forge/fml/eventbus/modlauncher/minecraft 的 ✓）" % len(jars))
    for j in jars:
        try:
            if not zipfile.is_zipfile(j):
                continue
            with zipfile.ZipFile(j) as z:
                names = set(z.namelist())
                hit = [w for w in WANT if w in names]
                if hit:
                    print("%-64s 命中 %d/%d  大小 %d" % (j.name[:64], len(hit), len(WANT), j.stat().st_size))
                    for h in hit:
                        print("      " + h)
        except Exception as e:
            print("%-64s 打不开: %s" % (j.name[:64], type(e).__name__))
    return 0


raise SystemExit(main())
