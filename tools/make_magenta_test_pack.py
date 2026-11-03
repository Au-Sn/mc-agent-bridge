#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_magenta_test_pack.py —— ★判据用资源包：把"默认皮肤"涂成纯品红★

为什么用它判 ✗（前面在"皮肤"上绕了太多轮 ✓ 这次要一次定论 ✓）：
  · 若能变粉红 ⇒ 客户端**确实**会走 `entity/player/{wide,slim}/*.png` ⇒ 路通 ✓
    （那当初资源包"没效果"就是别的原因 ✗ 值得继续查 ✓）
  · 若**一点变化都没有** ⇒ 客户端**连默认皮肤贴图都不走** ✗
    ⇒ 服务端注入 ✗ 与资源包覆盖 ✗ **两条路同时证伪** ⇒ 只剩"客户端皮肤模组"一条 ✓✓
输出：<版本目录>/resourcepacks/ZZ_MagentaSkinTest/（16 张纯色 ✓ pack_format 15 ✓）
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import paths as PA  # noqa: E402  ★解绑：实例路径只从 paths 来✗不写死✗★

GAME = PA.MC_HOME
PACK = GAME / "resourcepacks" / "ZZ_MagentaSkinTest"
W = H = 64
MAGENTA = (255, 0, 255, 255)      # ★纯品红★ ✗ —— 一眼就能分辨 ✓ 不可能看错 ✓


def write_solid(path: Path, rgba) -> None:
    raw = b"".join(b"\x00" + bytes(rgba) * W for _ in range(H))

    def ck(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + ck(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
                     + ck(b"IDAT", zlib.compress(raw, 9))
                     + ck(b"IEND", b""))


def main() -> int:
    wide = ["steve", "ari", "efe", "kai", "makena", "noor", "sunny", "zuri"]
    slim = ["alex"] + wide
    n = 0
    base = PACK / "assets" / "minecraft" / "textures" / "entity" / "player"
    for sub, names in (("wide", wide), ("slim", slim)):
        for nm in names:
            write_solid(base / sub / (nm + ".png"), MAGENTA)
            n += 1
    # 顺手把老版路径也覆盖上（1.20.1 用不到 ✓ 但零成本 ✓ 免得以后又猜一格 ✗）
    write_solid(PACK / "assets" / "minecraft" / "textures" / "entity" / "steve.png", MAGENTA)
    write_solid(PACK / "assets" / "minecraft" / "textures" / "entity" / "alex.png", MAGENTA)
    n += 2
    (PACK / "pack.mcmeta").write_text(
        '{\n  "pack": {\n    "pack_format": 15,\n'
        '    "description": "MAGENTA default-skin test (judgement pack)"\n  }\n}\n',
        encoding="utf-8", newline="\n")
    (PACK / "README.txt").write_text(
        "判据包：把默认玩家皮肤涂成纯品红。\n"
        "用法：选项 -> 资源包 -> 把 ZZ_MagentaSkinTest 移到右边（放最下面=优先级最高）-> F3+T\n"
        "判读：假人变粉红 = 资源包这条路通；完全没变 = 客户端不走默认皮肤贴图。\n"
        "撤销：移回左边 -> F3+T\n", encoding="utf-8", newline="\n")
    print("[ok] pack = %s" % PACK)
    print("[ok] png = %d (wide 8 + slim 9 + legacy 2)" % n)
    print("[ok] sample bytes = %d" % (base / "wide" / "steve.png").stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
