#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""make_fish_skin.py —— 生成"蓝色大肥鱼"皮肤资源包（纯标准库 ✓ 不用 PIL ✓）

为什么走资源包 ✗（实测环境 ✓）：
  · 模组列表里**没有**任何服务端皮肤模组（只有 appleSkin ＝ 食物 HUD ✗）
  · 假人是 Carpet 的离线假人 ⇒ 皮肤 ＝ **默认皮肤**（按 UUID 从那 18 张里挑 ✗）
  · 而**看它的人只有你**（单机 ✓）⇒ 只要覆盖**客户端**渲染用的默认皮肤贴图 ✓
    你看它就是大肥鱼 ✓ 不用装模组 ✓ 不用重启 ✓
⇒ 于是把 **wide/ 与 slim/ 各 9 张**（1.20.1 共 18 张默认皮肤 ✓ 见下）全写成同一张鱼 ✓
   —— 这样不管它被分到哪一张 ✓ 都是鱼 ✓（不赌 UUID ✗）

★18 张的依据★ ✗（2026-09-20 实测 ✓ 不是猜 ✓）：
  直接读客户端 jar（实例目录里的版本 jar ✓）里的
  `assets/minecraft/textures/entity/player/{wide,slim}/*.png` ⇒ 各 9 张：
  `steve / alex / ari / efe / kai / makena / noor / sunny / zuri` ✓
  ⚠ 上一版**漏了 `wide/alex.png`** ✗ ⇒ 万一 Bot 被分到那一张 ⇒ **显示成原版** ✗
    （"少写一个文件 ⇒ 静默不对" 正是本项目最恨的那类错 ✓ 所以写在这里 ✓）

用法：
    py tools/make_fish_skin.py                      # 直接写进游戏实例（★要放宽实例目录写权限★ ✗）
    py tools/make_fish_skin.py --out <目录>          # 只写到别处（★先在沙箱里验证★ ✓）
    py tools/make_fish_skin.py --out <目录> --preview  # 顺带出一张"穿上看什么样"的预览图 ✓
产出：<out>/DSH_BlueFish/{pack.mcmeta, README.txt, assets/minecraft/textures/entity/player/...}
启用：游戏里 选项 → 资源包 → 选中 DSH_BlueFish → 按 F3+T 重载 ✓（或关游戏后改 options.txt ✓）
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import paths as PA  # noqa: E402  ★解绑：实例路径只从 paths 来✗不写死✗★


GAME = PA.MC_HOME
DEFAULT_OUT = GAME / "resourcepacks"
W = H = 64
NAMES = ["steve", "alex", "ari", "efe", "kai", "makena", "noor", "sunny", "zuri"]

# ── 调色板 ✓（蓝色大肥鱼 ✓ 主色取 DeepSeek 品牌蓝 #4D6BFE ✓ 一眼认得出来 ✓）
BRAND = (77, 107, 254, 255)    # 背/身主蓝
DEEP = (44, 64, 190, 255)      # 深蓝：背鳍／鳍／阴影
LIGHT = (126, 146, 255, 255)   # 高光
BELLY = (234, 240, 255, 255)   # 白肚皮
GROOVE = (196, 208, 255, 255)  # 腹褶（鲸鱼肚子上那几道 ✓）
EYE_W = (252, 253, 255, 255)
EYE_B = (18, 20, 28, 255)
MOUTH = (30, 40, 110, 255)
EMPTY = (0, 0, 0, 0)


def blank() -> list:
    return [[EMPTY for _ in range(W)] for _ in range(H)]


def rect(px, x0, y0, w, h, c) -> None:
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            if 0 <= x < W and 0 <= y < H:
                px[y][x] = c


def write_png(path: Path, px, w: int = W, h: int = H) -> None:
    raw = b"".join(b"\x00" + b"".join(struct.pack("4B", *px[y][x]) for x in range(w))
                   for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def paint(slim: bool = False) -> list:
    """标准皮肤布局 ✓（1.20.1 与老版一致 ✓）：
       头   (0..31, 0..15)   ＋ hat 覆盖层 (32..63, 0..15)
       身   (16..39,16..31)  ＋ jacket 层   (16..39,32..47)
       右腿 (0..15,16..31) ／ 左腿 (16..31,48..63) ＋ pants 层
       右臂 (40..55,16..31) ／ 左臂 (32..47,48..63) ＋ sleeve 层
       ★slim（Alex 型）手臂只有 3 像素宽★ ✗ ⇒ 第 4 列留空 ✓（别把图案塞到看不见的列里 ✗）
    """
    px = blank()

    # ── 头：鲸鱼脸 ✓ ─────────────────────────────────────────────────────
    rect(px, 0, 0, 32, 16, BRAND)          # 整块蓝 ✓
    rect(px, 8, 0, 8, 8, BRAND)            # 头顶
    rect(px, 9, 1, 3, 1, LIGHT)            # 头顶高光 ✓
    rect(px, 11, 3, 2, 1, DEEP)            # 喷气孔 ✓（鲸鱼那个小洞 ✓）
    rect(px, 24, 8, 8, 8, BRAND)           # 后脑
    rect(px, 24, 8, 8, 4, DEEP)            # 后脑上半深蓝 ✓
    rect(px, 0, 8, 8, 8, BRAND)            # 右侧脸
    rect(px, 0, 8, 2, 8, DEEP)             # 侧面往后收深一点 ✓
    rect(px, 16, 8, 8, 8, BRAND)           # 左侧脸
    rect(px, 22, 8, 2, 8, DEEP)
    # 正面脸（8..15, 8..15）：上蓝下白 ✓ 两只眼 ✓ 一张扁嘴 ✓
    rect(px, 8, 8, 8, 3, BRAND)            # 额头 ✓
    rect(px, 8, 11, 8, 5, BELLY)           # 白下巴 ✓（鲸鱼最认得出的一处 ✓）
    rect(px, 9, 9, 2, 2, EYE_W)            # 左眼白 ✓
    rect(px, 13, 9, 2, 2, EYE_W)           # 右眼白 ✓
    rect(px, 10, 10, 1, 1, EYE_B)          # 瞳孔 ✓
    rect(px, 14, 10, 1, 1, EYE_B)
    rect(px, 9, 13, 6, 1, MOUTH)           # 扁嘴 ✓
    rect(px, 9, 12, 1, 1, MOUTH)           # 嘴角上翘 ✓（在笑 ✓）
    rect(px, 14, 12, 1, 1, MOUTH)
    rect(px, 8, 12, 1, 1, LIGHT)           # 脸颊高光 ✓
    rect(px, 15, 12, 1, 1, LIGHT)

    # ── 身体：白肚皮 ＋ 腹褶 ✓ 背后一条背鳍 ✓ ─────────────────────────────
    rect(px, 16, 16, 24, 16, BRAND)
    rect(px, 20, 16, 8, 4, BRAND)          # 顶（肩 ✓）
    rect(px, 28, 16, 8, 4, BELLY)          # 底 ✓
    # 正面（20..27, 20..31）
    rect(px, 20, 20, 8, 2, BRAND)          # 胸口 ✓
    rect(px, 20, 22, 8, 10, BELLY)         # ★大白肚皮★ ✓ 大肥鱼的灵魂 ✓
    for yy in (24, 26, 28, 30):            # 腹褶 ✓
        rect(px, 21, yy, 6, 1, GROOVE)
    # 背面（32..39, 20..31）：★背鳍★ ✓
    rect(px, 32, 20, 8, 12, BRAND)
    rect(px, 35, 22, 2, 9, DEEP)           # 鳍的竖脊 ✓
    rect(px, 34, 24, 4, 6, DEEP)           # 鳍面 ✓
    rect(px, 32, 20, 8, 1, LIGHT)          # 肩线高光 ✓
    # 两侧（16..19 / 28..31, 20..31）
    rect(px, 16, 20, 4, 12, BRAND)
    rect(px, 28, 20, 4, 12, BRAND)
    rect(px, 16, 28, 4, 4, DEEP)           # 侧面下缘深一点 ✓
    rect(px, 28, 28, 4, 4, DEEP)

    # ── 手臂：蓝底 ＋ 深蓝鳍尖 ✓（slim 只画 3 像素宽 ✓）────────────────────
    aw = 3 if slim else 4
    for bx in (40, 32):                    # 右臂 (40,16) ／ 左臂 (32,48)
        by = 16 if bx == 40 else 48
        rect(px, bx, by, 16, 16, BRAND)
        rect(px, bx + 4, by + 4, aw, 12, BRAND)      # 正面 ✓
        rect(px, bx + 4, by + 4, aw, 1, LIGHT)       # 袖口高光 ✓
        rect(px, bx + 4, by + 12, aw, 4, DEEP)       # ★鳍尖★ ✓
        rect(px, bx + 4 + aw, by + 4, 4 - aw, 12, EMPTY)   # slim：第 4 列留空 ✓
        rect(px, bx + 8, by + 4, 4, 12, BRAND)       # 背面／侧面 ✓
        rect(px, bx + 8, by + 12, 4, 4, DEEP)

    # ── 腿：蓝底 ＋ 尾鳍纹 ✓ ──────────────────────────────────────────────
    for bx in (0, 16):                     # 右腿 (0,16) ／ 左腿 (16,48)
        by = 16 if bx == 0 else 48
        rect(px, bx, by, 16, 16, BRAND)
        rect(px, bx + 4, by + 4, 4, 12, BRAND)       # 正面 ✓
        rect(px, bx + 4, by + 9, 4, 1, DEEP)         # 尾鳍：中间收一下 ✓
        rect(px, bx + 4, by + 12, 1, 2, DEEP)        # 分叉 ✓
        rect(px, bx + 7, by + 12, 1, 2, DEEP)
        rect(px, bx + 4, by + 14, 4, 2, BELLY)       # 脚底白 ✓（鱼也没鞋 ✓）
        rect(px, bx + 8, by + 4, 4, 12, BRAND)       # 侧面 ✓
        rect(px, bx + 8, by + 12, 4, 4, DEEP)
    # 覆盖层（hat/jacket/sleeve/pants）留空 ✓（免得挡住鱼身 ✓）
    return px


def preview(px) -> list:
    """出一张"穿上看什么样"的图 ✓：正面拼一版（头 ＋ 身 ＋ 两臂）✓
    —— 光看 64×64 那张贴图**看不出好不好看** ✗（本项目纪律：改了就要能看见 ✓）"""
    pw, ph = 16, 24
    bg = (26, 26, 32, 255)
    out = [[bg for _ in range(pw)] for _ in range(ph)]

    def blit(sx, sy, sw, sh, dx, dy) -> None:
        for y in range(sh):
            for x in range(sw):
                c = px[sy + y][sx + x]
                if c[3] and 0 <= dx + x < pw and 0 <= dy + y < ph:
                    out[dy + y][dx + x] = c

    blit(8, 8, 8, 8, 4, 0)        # 脸 ✓
    blit(20, 20, 8, 12, 4, 8)     # 身（正面）✓
    blit(44, 20, 4, 12, 0, 8)     # 右臂 ✓
    blit(36, 52, 4, 12, 12, 8)    # 左臂 ✓
    return out


def main(argv: list[str]) -> int:
    out_root = DEFAULT_OUT
    want_preview = "--preview" in argv
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 >= len(argv):
            print("[X] --out 后面要给目录 ✗")
            return 2
        out_root = Path(argv[i + 1])
    pack = out_root / "DSH_BlueFish"
    base = pack / "assets" / "minecraft" / "textures" / "entity" / "player"
    n = 0
    for sub in ("wide", "slim"):
        px = paint(slim=(sub == "slim"))
        for nm in NAMES:                     # ★9 个名字两张表都写满★ ✓（共 18 ✓）
            write_png(base / sub / (nm + ".png"), px)
            n += 1
    (pack / "pack.mcmeta").write_text(
        '{\n  "pack": {\n    "pack_format": 15,\n'
        '    "description": "DSH Blue Fish - blue fat fish default skin"\n  }\n}\n',
        encoding="utf-8", newline="\n")
    (pack / "README.txt").write_text(
        "把默认玩家皮肤换成蓝色大肥鱼（给假人 Bot 用）\n"
        "启用：选项 -> 资源包 -> 选中 DSH_BlueFish -> F3+T 重载\n"
        "停用：把它挪到左边或取消勾选 -> F3+T\n"
        "重新生成：py tools/make_fish_skin.py（要写实例目录时需放宽权限）\n"
        "覆盖范围：wide/ 与 slim/ 各 9 张默认皮肤（共 18 张）\n", encoding="utf-8", newline="\n")
    print("[ok] pack = %s" % pack)
    print("[ok] png files = %d（wide 9 ＋ slim 9 ✓）" % n)
    print("[ok] each = %d bytes" % (base / "wide" / "steve.png").stat().st_size)
    if want_preview:
        pv = preview(paint(slim=False))
        write_png(out_root / "DSH_BlueFish_预览.png", pv, 16, 24)
        print("[ok] 预览 = %s" % (out_root / "DSH_BlueFish_预览.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
