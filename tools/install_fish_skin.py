#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""install_fish_skin.py —— 把一张**真皮肤 PNG** 装成"假人专用"资源包 ✓（纯标准库 ✓）

为什么是这个做法 ✗（实测环境 ✓，不是猜 ✓）：
  · 假人是 Carpet 的**离线假人** ⇒ GameProfile 里**没有** textures 属性 ⇒ 它显示的是
    **默认皮肤**（客户端按 UUID 从那 18 张里挑一张 ✗）
  · 模组列表里**没有任何服务端皮肤模组** ✗（只有 appleSkin ＝ 食物 HUD）
  · 而**看它的人只有你**（单机 ✓）⇒ 只要覆盖**客户端**渲染用的默认皮肤贴图 ✓
    ⇒ 你看它就是大肥鱼 ✓ 不用装模组 ✓ 不用重启游戏 ✓（F3+T 重载就行 ✓）

★18 张的依据★ ✗（实测 ✓ 读客户端 jar 得到的 ✓ 不是猜 ✓）：
  `assets/minecraft/textures/entity/player/{wide,slim}/*.png` 各 9 张：
  `steve / alex / ari / efe / kai / makena / noor / sunny / zuri` ✓

★wide/slim 必须换算★ ✗（这是本脚本最值钱的一处 ✓）：
  · 一套皮肤只有**一个**模型：slim（Alex 型）手臂宽 **3** 像素 ✓ wide（Steve 型）**4** 像素 ✓
  · 而我们要**铺满两张表**（因为不知道 UUID 会挑到哪张 ✗）
  · ⇒ 4 宽的手臂贴图直接塞进 slim 表 ⇒ **手臂错位** ✗（多出来那 1 列会显示成乱边 ✓）
  · ⇒ 本脚本按面做换算 ✓：wide→slim 把第 4 列**留空** ✓；slim→wide 把第 3 列**补到第 4 列** ✓
  · 涉及的四块：右臂 (40,16) ✓ 左臂 (32,48) ✓ 右袖 (40,32) ✓ 左袖 (48,48) ✓
    （腿两张模型都是 4 像素 ✓ 不用换算 ✓）

用法：
    py tools/install_fish_skin.py --png skins/deepseek.png --inspect        # 只看：它是什么模型 ✓
    py tools/install_fish_skin.py --png skins/deepseek.png --out <目录> --preview
    py tools/install_fish_skin.py --png skins/deepseek.png                  # 装进游戏实例（★要放宽实例目录写权限★）
    py tools/install_fish_skin.py --png skins/catgirl.png --model slim      # 判错了就手动指定 ✓

产出：<out>/DSH_BlueFish/{pack.mcmeta, README.txt, assets/minecraft/textures/entity/player/…}
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

# ★控制台必须重配成 UTF-8★ ✗（本项目踩过 **两次** ✓ 见 tools/persona.py 的注释 ✓）：
#   不重配 ⇒ 打中文/`✓` 到 GBK 控制台 ⇒ `UnicodeEncodeError` ⇒ **退出码变 1** ✗
#   ⇒ 看起来像"工具坏了" ✗ 其实功能全对 ✓ —— 我自己 2026-09-20 又踩了一次 ✓ 记在这里 ✓
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)   # type: ignore[attr-defined]
except Exception:
    pass

import paths as PA  # noqa: E402  ★解绑：实例路径只从 paths 来✗不写死✗★

GAME = PA.MC_HOME
DEFAULT_OUT = GAME / "resourcepacks"
NAMES = ["steve", "alex", "ari", "efe", "kai", "makena", "noor", "sunny", "zuri"]
# ★四肢方块的六个面★ ✓（皮肤布局就是这套坐标 ✓ 1.20.1 与老版一致 ✓）
#   (方块左上角 x, y) ⇒ 顶 4x4 ／ 底 4x4 ／ 右 4x12 ／ 前 4x12 ／ 左 4x12 ／ 后 4x12
ARM_BLOCKS = [(40, 16), (32, 48), (40, 32), (48, 48)]     # 右臂 左臂 右袖 左袖
EMPTY = (0, 0, 0, 0)


def read_png(path: Path):
    """读 64×64 的 RGBA8 PNG ✓（只用标准库 ✓ 只认这一种格式 ✓ 认不出就**大声报** ✗）"""
    b = path.read_bytes()
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("[X] 不是 PNG ✗：%s" % path)
    i, idat, meta = 8, b"", None
    while i + 8 <= len(b):
        ln = struct.unpack(">I", b[i:i + 4])[0]
        tag = b[i + 4:i + 8]
        data = b[i + 8:i + 8 + ln]
        if tag == b"IHDR":
            meta = struct.unpack(">IIBBBBB", data)
        elif tag == b"IDAT":
            idat += data
        elif tag == b"IEND":
            break
        i += 12 + ln
    if not meta:
        raise SystemExit("[X] 没有 IHDR ✗")
    w, h, depth, ctype = meta[0], meta[1], meta[2], meta[3]
    if (w, h) != (64, 64) or depth != 8 or ctype != 6:
        raise SystemExit("[X] 只支持 64×64 的 RGBA8 PNG ✗（这张是 %d×%d depth=%d ctype=%d）"
                         % (w, h, depth, ctype))
    raw = zlib.decompress(idat)
    stride = 64 * 4
    px = [[EMPTY for _ in range(64)] for _ in range(64)]
    prev = bytearray(stride)
    p = 0
    for y in range(64):
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            bb = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            if ft == 1:
                line[x] = (line[x] + a) & 0xFF
            elif ft == 2:
                line[x] = (line[x] + bb) & 0xFF
            elif ft == 3:
                line[x] = (line[x] + ((a + bb) >> 1)) & 0xFF
            elif ft == 4:
                pp = a + bb - c
                pa, pb, pc = abs(pp - a), abs(pp - bb), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (bb if pb <= pc else c)
                line[x] = (line[x] + pr) & 0xFF
        for x in range(64):
            px[y][x] = tuple(line[x * 4:x * 4 + 4])
        prev = line
    return px


def write_png(path: Path, px, w: int = 64, h: int = 64) -> None:
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


def detect_model(px) -> tuple[str, float]:
    """★判它是 wide 还是 slim★ ✓ —— 判据：手臂那四块的**第 4 列**是不是整列透明 ✓
    （slim 皮肤按约定把那列留空 ✓；wide 皮肤会画满 ✓）
    返回 (结论, 透明比例 ✓) —— 比例一起报出来 ✓ 免得"判错还不自知"✗"""
    tot = blank_col = 0
    for (bx, by) in ARM_BLOCKS:
        for (ox, oy, w, h) in ((bx + 4, by + 4, 4, 12), (bx, by + 4, 4, 12),
                               (bx + 8, by + 4, 4, 12), (bx + 12, by + 4, 4, 12)):
            for y in range(oy, oy + h):
                tot += 1
                if px[y][ox + 3][3] == 0:
                    blank_col += 1
    r = (blank_col / tot) if tot else 0.0
    return ("slim" if r > 0.9 else "wide"), r


def convert(px, target: str):
    """把整张皮肤的手臂四块换算到目标模型 ✓（腿不用动 ✓ 两张模型腿都是 4 宽 ✓）"""
    out = [row[:] for row in px]
    for (bx, by) in ARM_BLOCKS:
        for (ox, oy, w, h) in ((bx, by, 4, 4), (bx + 4, by, 4, 4),
                               (bx, by + 4, 4, 12), (bx + 4, by + 4, 4, 12),
                               (bx + 8, by + 4, 4, 12), (bx + 12, by + 4, 4, 12)):
            if target == "slim":                     # ★第 4 列留空★ ✓（多余那列会显示成乱边 ✗）
                for k in range(h):
                    out[oy + k][ox + 3] = EMPTY
                    if w == 4 and h == 4:
                        out[oy + 3][ox + 3] = EMPTY
            else:                                    # ★把第 3 列补到第 4 列★ ✓（补上少的那条 ✓）
                for k in range(h):
                    if out[oy + k][ox + 3][3] == 0:
                        out[oy + k][ox + 3] = out[oy + k][ox + 2]
                if w == 4 and h == 4:
                    if out[oy + 3][ox + 3][3] == 0:
                        for x in range(4):
                            out[oy + 3][ox + x] = out[oy + 2][ox + x]
    return out


def preview(px) -> list:
    """出一张"穿上看什么样"的正面图 ✓（光看 64×64 贴图**看不出好不好看** ✗ 纪律：改了要能看见 ✓）"""
    pw, ph = 16, 32
    bg = (24, 24, 30, 255)
    out = [[bg for _ in range(pw)] for _ in range(ph)]

    def blit(sx, sy, sw, sh, dx, dy) -> None:
        for y in range(sh):
            for x in range(sw):
                c = px[sy + y][sx + x]
                if c[3] and 0 <= dx + x < pw and 0 <= dy + y < ph:
                    out[dy + y][dx + x] = c

    blit(8, 8, 8, 8, 4, 0)         # 脸 ✓
    blit(20, 20, 8, 12, 4, 8)      # 身（正面 ✓）
    blit(44, 20, 4, 12, 0, 8)      # 右臂 ✓
    blit(36, 52, 4, 12, 12, 8)     # 左臂 ✓
    blit(4, 20, 4, 12, 4, 20)      # 右腿 ✓
    blit(20, 52, 4, 12, 8, 20)     # 左腿 ✓
    return out


def main(argv: list[str]) -> int:
    def arg(name, default=None):
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return argv[i + 1]
        return default

    png = arg("--png")
    if not png:
        print(__doc__)
        return 2
    src = Path(png)
    if not src.is_file():
        print("[X] 没有这个文件 ✗：%s" % src)
        return 2
    px = read_png(src)
    guessed, ratio = detect_model(px)
    forced = arg("--model")
    model = forced if forced in ("wide", "slim") else guessed
    print("[i] %s" % src.name)
    print("[i] 判模型 = %s ✓（第 4 列透明比例 %.1f%% ✓ 阈值 90%% ✓）%s"
          % (guessed, ratio * 100, "" if not forced else "→ ★手动指定为 %s★" % model))
    if "--inspect" in argv:      # ⚠ 是**开关**（没有值 ✓）⇒ 必须用 `in` 判 ✗
        return 0                 #   （用 arg() 读会拿到 None ✗ ⇒ **不提前返回** ✗ ⇒ 直接往实例目录写 ✗
                                 #    实测 2026-09-20 ✓：三条 --inspect 全都在**试图装包** ✗ 被权限挡住才发现 ✓）
    other = "slim" if model == "wide" else "wide"
    out_root = Path(arg("--out") or DEFAULT_OUT)
    pack = out_root / arg("--name", "DSH_BlueFish")
    base = pack / "assets" / "minecraft" / "textures" / "entity" / "player"
    n = 0
    for sub, img in ((model, px), (other, convert(px, other))):
        for nm in NAMES:
            write_png(base / sub / (nm + ".png"), img)
            n += 1
    (pack / "pack.mcmeta").write_text(
        '{\n  "pack": {\n    "pack_format": 15,\n'
        '    "description": "DSH Blue Fish - %s (default skin override)"\n  }\n}\n' % src.stem,
        encoding="utf-8", newline="\n")
    (pack / "README.txt").write_text(
        "把默认玩家皮肤换成蓝色大肥鱼（给假人 Bot 用）\n"
        "来源皮肤：%s（原模型 %s）\n"
        "启用：选项 -> 资源包 -> 选中 %s -> F3+T 重载\n"
        "停用：把它挪到左边或取消勾选 -> F3+T\n"
        "换一张：py tools/install_fish_skin.py --png skins/xxx.png\n"
        "覆盖范围：wide/ 与 slim/ 各 9 张（共 18 张 ✓ wide 与 slim 之间已做手臂换算 ✓）\n"
        % (src.name, model, pack.name), encoding="utf-8", newline="\n")
    print("[ok] pack = %s" % pack)
    print("[ok] png = %d 张（%s 9 ＋ %s 9 ✓ 已换算 ✓）" % (n, model, other))
    if "--preview" in argv:
        pv = preview(px)
        pv_path = out_root / (pack.name + "_预览_%s.png" % model)
        write_png(pv_path, pv, 16, 32)      # ⚠ 预览是 16×32 ✗ 别用默认的 64×64 ✓
        print("[ok] 预览 = %s" % pv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
