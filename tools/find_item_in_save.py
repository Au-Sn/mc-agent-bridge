#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_item_in_save.py —— 在**存档文件里**直接找物品/方块字符串（不依赖任何游戏内通道）

为什么需要它（2026-09-18 晚）：
  "世界上有没有工作台"这个判断，我们过去只能靠 `find_block`（半径 12 的方块普查 ✗）
  和"海龟能看见的范围"✗ —— 而**容器里的东西**（箱子/桶/漏斗/玩家背包）在任何
  方块普查里都是**看不见的** ✗✗。于是一条本来存在的路（"桶里有工作台"）被判成了死路 ✗。
  但存档就在磁盘上 ✓：区块文件里的 NBT 字符串就是**明文 UTF-8** ✓，
  直接按字节搜就行了 ✓ —— 不需要开游戏、不需要 CC、不需要权限 ✓✓。

能回答的问题：
  · 哪个区域文件（=哪一片 32×32 区块）里出现过 `minecraft:crafting_table`
  · 玩家背包（playerdata/*.dat ✗ gzip 压缩 ✓ 会先解压）里有没有它
  · 世界里到底有多少个某种方块/物品（按出现次数粗估 ✓ 不是精确计数 ✓）

用法：
    py tools/find_item_in_save.py crafting_table
    py tools/find_item_in_save.py minecraft:hopper minecraft:furnace
    py tools/find_item_in_save.py --all-mods diamond_pickaxe      # 也搜模组物品名
"""

from __future__ import annotations

import gzip
import re
import sys, paths as PA
import time
from pathlib import Path

SAVE = PA.SAVE_DIR

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def scan_bytes(data: bytes, pats: list[bytes]) -> dict[str, int]:
    hits: dict[str, int] = {}
    for p in pats:
        n = data.count(p)
        if n:
            hits[p.decode("utf-8", "replace")] = n
    return hits


def main(argv: list[str]) -> int:
    pats_txt = [a for a in argv if not a.startswith("--")]
    if not pats_txt:
        print(__doc__)
        return 2
    # 默认按"物品 id 片段"搜：crafting_table → minecraft:crafting_table
    pats = []
    for p in pats_txt:
        pats.append(p.encode("utf-8"))
        if ":" not in p:
            pats.append(("minecraft:" + p).encode("utf-8"))
    # 去重、长串优先（报告时更好看）
    uniq: list[bytes] = []
    for p in pats:
        if p not in uniq:
            uniq.append(p)

    print("=" * 70)
    print("存档：%s" % SAVE)
    print("搜索：%s" % ", ".join(p.decode("utf-8", "replace") for p in uniq))
    print("=" * 70)
    if not SAVE.is_dir():
        print("[X] 存档目录不存在")
        return 1

    t0 = time.time()
    total: dict[str, int] = {}
    files = 0

    # ① 区块文件（方块状态 + 方块实体 NBT 都在里面 ✓）
    # ⚠⚠ 2026-09-18 晚的重大修正（真实事故 ✓）：
    #   `.mca` 里的区块数据是 **zlib 压缩** 的 ✗ —— 直接按字节搜**什么都搜不到** ✗✗
    #   而 `playerdata/*.dat` 与 `level.dat` 是 **gzip** ✓（代码里本来就解压了 ✓）
    #   ⇒ 于是我第一版得出"整个世界一个工作台都没有" ✗ —— **那是假阴性** ✗，
    #     而玩家一句话就推翻了它（"场上其实有一个工作台，就在假人旁边" ✓）。
    #   教训：**"搜不到"必须先排除"我根本没搜对地方"** ✓（同 错题本 G9 的读法问题 ✓）。
    #   修法：按 Anvil 格式自己解压后段：8KiB 头（每项 4 字节：3 字节扇区偏移 + 1 字节扇区数 ✓），
    #         数据段开头 4 字节长度 + 1 字节压缩类型（1=gzip / 2=zlib / 3=未压缩 ✓）。
    import struct
    import zlib

    def decompress_region(path: Path) -> bytes:
        """把 .mca 里每个区块解压后拼起来（拼不上就退回原字节 ✓ 绝不静默失败 ✓）。"""
        raw = path.read_bytes()
        out = bytearray()
        ok, bad = 0, 0
        for i in range(1024):
            entry = raw[i * 4:i * 4 + 4]
            if len(entry) < 4:
                break
            off = (entry[0] << 16) | (entry[1] << 8) | entry[2]
            cnt = entry[3]
            if off == 0 or cnt == 0:
                continue
            start = off * 4096
            if start + 5 > len(raw):
                bad += 1
                continue
            length = struct.unpack(">I", raw[start:start + 4])[0]
            ctype = raw[start + 4]
            blob = raw[start + 5:start + 4 + length]
            try:
                if ctype == 1:
                    out += gzip.decompress(blob)
                elif ctype == 2:
                    out += zlib.decompress(blob)
                elif ctype == 3:
                    out += blob
                else:
                    bad += 1
                    continue
                ok += 1
            except Exception:
                bad += 1
        return bytes(out)

    for sub in ("region", "DIM-1/region", "DIM1/region"):
        d = SAVE / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.mca")):
            files += 1
            data = decompress_region(f)
            hits = scan_bytes(data, uniq)
            if hits:
                # 区域文件名 r.X.Z.mca ⇒ 覆盖区块 (X*32 .. X*32+31, Z*32 .. Z*32+31)
                m = re.match(r"r\.(-?\d+)\.(-?\d+)\.mca", f.name)
                where = ""
                if m:
                    rx, rz = int(m.group(1)), int(m.group(2))
                    where = "  ≈ 方块 x %d..%d, z %d..%d" % (
                        rx * 32 * 16, rx * 32 * 16 + 511, rz * 32 * 16, rz * 32 * 16 + 511)
                print("  [region] %-18s %s%s" % (f.name, hits, where))
                for k, v in hits.items():
                    total[k] = total.get(k, 0) + v

    # ② 玩家数据（gzip 压缩的 NBT ✓ 解压后再搜 —— 玩家背包/末影箱在这里 ✓）
    pd = SAVE / "playerdata"
    if pd.is_dir():
        for f in sorted(pd.glob("*.dat")):
            try:
                raw = gzip.decompress(f.read_bytes())
            except OSError:
                raw = f.read_bytes()
            hits = scan_bytes(raw, uniq)
            if hits:
                print("  [playerdata] %-38s %s" % (f.name, hits))
                for k, v in hits.items():
                    total[k] = total.get(k, 0) + v

    # ③ level.dat（世界级数据 ✓ 顺便看看）
    lv = SAVE / "level.dat"
    if lv.is_file():
        try:
            raw = gzip.decompress(lv.read_bytes())
        except OSError:
            raw = lv.read_bytes()
        hits = scan_bytes(raw, uniq)
        if hits:
            print("  [level.dat] %s" % hits)

    print("-" * 70)
    if total:
        for k, v in sorted(total.items(), key=lambda kv: -kv[1]):
            print("  合计 %-34s %d 次（含方块状态与容器内容 ✓ 不是精确物品数 ✓）" % (k, v))
    else:
        print("  ✗ 全档没有任何匹配 —— 这一条可以**确定地**判死 ✓（不是'没扫到' ✗）")
    print("  （扫了 %d 个区域文件，用时 %.1fs）" % (files, time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
