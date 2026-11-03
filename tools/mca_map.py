#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mca_map.py — 直接从世界存档的 region/*.mca 生成地图（PNG + 文字统计）

为什么值得做（回答"能不能从文件拿地图，而不用人盯小地图"）：
  ATM9 用的是 FTB Chunks，它**不写地图瓦片** ✗（存档里只有 264 字节的认领数据 ✓）。
  但真正的"地图本体"一直在磁盘上 ✓：`region/r.<X>.<Z>.mca` 存着每个区块**逐格方块数据** ✓，
  比小地图颜色信息多得多 ✓ —— 能精确到格子 ✓ 能离线统计 ✓ 能出任意高度的切片 ✓。
  而且它在区块保存时自动更新 ✓（实测文件时间戳就是几分钟前 ✓）→ 近实时 ✓。

实现要点（都是这个格式的硬规矩 ✓）：
  · .mca 结构：前 4096 字节 = 位置表（每区块 3 字节偏移 + 1 字节扇区数），
    再 4096 字节时间戳；区块数据 = 4 字节长度 + 1 字节压缩方式(1/2=zlib) + 压缩体 ✓
  · 1.18+ 区块 NBT 不再有 "Level" 外壳 ✓（sections 直接挂在根上 ✓）
  · 方块用调色板 + 位压缩：bits = max(4, ceil(log2(调色板大小))) ✓
    1.16+ 的打包**不跨 long** ✓（每 long 放 64//bits 个值 ✓）

用法：
    py tools/mca_map.py --out build/base.png --x0 4100 --x1 4160 --z0 -10 --z1 40
    py tools/mca_map.py --out build/base.png --top          # 只画地表（默认）
    py tools/mca_map.py --slice 70 --out build/y70.png      # 画 y=70 那一层的平面图
"""

from __future__ import annotations

import argparse
import glob
import os
import struct
import sys, paths as PA
import zlib

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE = str(PA.SAVES_DIR)

# ---------------------------------------------------------------- NBT 解析
TAG_END, TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG = 0, 1, 2, 3, 4
TAG_FLOAT, TAG_DOUBLE, TAG_BYTE_ARRAY = 5, 6, 7
TAG_STRING, TAG_LIST, TAG_COMPOUND = 8, 9, 10
TAG_INT_ARRAY, TAG_LONG_ARRAY = 11, 12


class R:
    def __init__(self, b):
        self.b, self.i = b, 0

    def take(self, n):
        v = self.b[self.i:self.i + n]
        self.i += n
        return v

    def u1(self):
        v = self.b[self.i]; self.i += 1; return v

    def i1(self):
        v = struct.unpack_from(">b", self.b, self.i)[0]; self.i += 1; return v

    def i2(self):
        v = struct.unpack_from(">h", self.b, self.i)[0]; self.i += 2; return v

    def i4(self):
        v = struct.unpack_from(">i", self.b, self.i)[0]; self.i += 4; return v

    def i8(self):
        v = struct.unpack_from(">q", self.b, self.i)[0]; self.i += 8; return v

    def f4(self):
        v = struct.unpack_from(">f", self.b, self.i)[0]; self.i += 4; return v

    def f8(self):
        v = struct.unpack_from(">d", self.b, self.i)[0]; self.i += 8; return v

    def s(self):
        n = struct.unpack_from(">H", self.b, self.i)[0]; self.i += 2
        v = self.b[self.i:self.i + n].decode("utf-8", "replace"); self.i += n
        return v


def read_payload(r: R, t: int):
    if t == TAG_BYTE:
        return r.i1()
    if t == TAG_SHORT:
        return r.i2()
    if t == TAG_INT:
        return r.i4()
    if t == TAG_LONG:
        return r.i8()
    if t == TAG_FLOAT:
        return r.f4()
    if t == TAG_DOUBLE:
        return r.f8()
    if t == TAG_BYTE_ARRAY:
        n = r.i4(); return r.take(n)
    if t == TAG_STRING:
        return r.s()
    if t == TAG_LIST:
        et = r.u1(); n = r.i4()
        return [read_payload(r, et) for _ in range(n)]
    if t == TAG_COMPOUND:
        out = {}
        while True:
            tt = r.u1()
            if tt == TAG_END:
                return out
            name = r.s()
            out[name] = read_payload(r, tt)
    if t == TAG_INT_ARRAY:
        n = r.i4(); return [r.i4() for _ in range(n)]
    if t == TAG_LONG_ARRAY:
        n = r.i4(); return [r.i8() for _ in range(n)]
    raise ValueError("未知 NBT 类型 %d" % t)


def parse_nbt(data: bytes):
    r = R(data)
    t = r.u1()
    if t != TAG_COMPOUND:
        raise ValueError("根不是 compound（是 %d）" % t)
    r.s()
    return read_payload(r, t)


# ---------------------------------------------------------------- region 读取
def read_chunk(mca_bytes: bytes, cx: int, cz: int):
    """cx/cz 是 region 内 0..31 的区块序号。"""
    idx = (cx % 32) + (cz % 32) * 32
    off = struct.unpack_from(">I", b"\x00" + mca_bytes[idx * 4:idx * 4 + 3])[0]
    if off == 0:
        return None
    ln = struct.unpack_from(">I", mca_bytes, off * 4096)[0]
    comp = mca_bytes[off * 4096 + 4]
    body = mca_bytes[off * 4096 + 5: off * 4096 + 4 + ln]
    if comp == 2:
        body = zlib.decompress(body)
    elif comp == 1:
        import gzip
        body = gzip.decompress(body)
    return parse_nbt(body)


def block_at(chunk, x, y, z):
    """取某格方块名（调色板 + 不跨 long 的位压缩）。"""
    for sec in chunk.get("sections", []):
        if sec.get("Y") != (y >> 4):
            continue
        bs = sec.get("block_states")
        if not bs:
            return None
        pal = bs.get("palette") or []
        if not pal:
            return None
        data = bs.get("data")
        if not data:                       # 调色板只有一项 → 整层都是它
            return pal[0].get("Name")
        bits = max(4, (len(pal) - 1).bit_length())
        per = 64 // bits
        i = ((y & 15) * 16 + (z & 15)) * 16 + (x & 15)
        lv = data[i // per]
        v = ((lv >> ((i % per) * bits)) & ((1 << bits) - 1))
        if v >= len(pal):
            return None
        return pal[v].get("Name")
    return None


# ---------------------------------------------------------------- 颜色
def color_of(name):
    if not name or name == "minecraft:air":
        return None
    n = name.split(":")[-1]
    table = {
        "grass_block": (106, 170, 64), "dirt": (134, 96, 67), "dirt_path": (148, 122, 65),
        "oak_planks": (162, 130, 78), "oak_log": (109, 82, 50), "oak_leaves": (60, 140, 40),
        "stone": (125, 125, 125), "cobblestone": (110, 110, 110), "gravel": (131, 127, 126),
        "sand": (219, 207, 163), "water": (63, 118, 228), "lava": (207, 92, 15),
        "glass": (200, 220, 230), "andesite": (136, 136, 136), "diorite": (200, 200, 200),
        "granite": (150, 105, 90), "deepslate": (80, 80, 85), "snow": (240, 240, 250),
    }
    if n in table:
        return table[n]
    if "leaves" in n:  return (60, 140, 40)
    if "log" in n:     return (109, 82, 50)
    if "planks" in n:  return (162, 130, 78)
    if "slab" in n or "stairs" in n: return (170, 140, 90)
    if "glass" in n:   return (200, 220, 230)
    if "grass" in n or "moss" in n: return (106, 170, 64)
    if "brick" in n or "tile" in n: return (150, 120, 110)
    return (90, 90, 120)


def write_png(path, w, h, px):
    """px: 每像素 3 字节的 bytearray"""
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += px[y * w * 3:(y + 1) * w * 3]
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, "wb").write(png)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"build\base.png")
    ap.add_argument("--x0", type=int, default=4100)
    ap.add_argument("--x1", type=int, default=4160)
    ap.add_argument("--z0", type=int, default=-10)
    ap.add_argument("--z1", type=int, default=40)
    ap.add_argument("--slice", type=int, default=None, help="只看某一层（不给则取地表）")
    ap.add_argument("--ymax", type=int, default=90)
    ap.add_argument("--scale", type=int, default=1,
                    help="整数放大倍数（1 格 = N×N 像素）。默认 1 时小区域只有几十像素，"
                         "人/模型都看不清 ✗ —— 要看图就 --scale 8 ✓")
    args = ap.parse_args(argv)

    world = glob.glob(os.path.join(BASE, "* (1)"))[0]
    rd = os.path.join(world, "region")
    w = args.x1 - args.x0
    h = args.z1 - args.z0
    px = bytearray(b"\x20\x20\x28" * (w * h))
    counts = {}
    loaded = set()

    for rx in range(args.x0 >> 9, (args.x1 >> 9) + 1):
        for rz in range(args.z0 >> 9, (args.z1 >> 9) + 1):
            path = os.path.join(rd, "r.%d.%d.mca" % (rx, rz))
            if not os.path.isfile(path):
                continue
            mca = open(path, "rb").read()
            loaded.add(path)
            for lx in range(32):
                for lz in range(32):
                    cx, cz = rx * 32 + lx, rz * 32 + lz
                    if not (args.x0 >> 4 <= cx <= args.x1 >> 4 and args.z0 >> 4 <= cz <= args.z1 >> 4):
                        continue
                    ch = read_chunk(mca, lx, lz)
                    if ch is None:
                        continue
                    for x in range(cx * 16, cx * 16 + 16):
                        if not (args.x0 <= x < args.x1):
                            continue
                        for z in range(cz * 16, cz * 16 + 16):
                            if not (args.z0 <= z < args.z1):
                                continue
                            if args.slice is not None:
                                nm = block_at(ch, x, args.slice, z)
                            else:
                                nm = None
                                for y in range(args.ymax, -64, -1):
                                    t = block_at(ch, x, y, z)
                                    if t and t != "minecraft:air":
                                        nm = t
                                        break
                            c = color_of(nm)
                            if not c:
                                continue
                            px[((z - args.z0) * w + (x - args.x0)) * 3:
                               ((z - args.z0) * w + (x - args.x0)) * 3 + 3] = bytes(c)
                            counts[nm] = counts.get(nm, 0) + 1

    sc = max(1, args.scale)
    if sc > 1:
        big = bytearray(w * sc * h * sc * 3)
        for row in range(h):
            line = bytearray()
            for col in range(w):
                p = px[(row * w + col) * 3:(row * w + col) * 3 + 3]
                line += bytes(p) * sc
            for k in range(sc):
                off = ((row * sc + k) * w * sc) * 3
                big[off:off + len(line)] = line
        px, w, h = big, w * sc, h * sc

    write_png(args.out, w, h, px)
    print("区域      : x %d..%d  z %d..%d   (%d×%d 格，放大 %d 倍 → %d×%d 像素)"
          % (args.x0, args.x1, args.z0, args.z1,
             args.x1 - args.x0, args.z1 - args.z0, sc, w, h))
    print("读取 region: %d 个文件" % len(loaded))
    print("输出      : %s" % os.path.abspath(args.out))
    print("方块分布 Top15：")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:15]:
        print("   %-42s %d" % (k, v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
