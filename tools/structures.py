#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""structures.py -- 模块 K 第 1 级：★包内结构文件检索 ＋ 读成坐标表✗★

用户口径（规格 §10.2 / §13）：
  「产线蓝图**应该是可以搜索的**」⇒ 包里**真有** 261 个 `.nbt` 结构（★Create 64 ✗ IE 47 ✗ BloodMagic 48✗★）
  「若没有就让 dsh **自己设计**」⇒ 所以本模块是**检索**这一级 ✓

接口：
  find(pattern)              -> [(jar, path)]              ★检索✗★
  read(jar, path)            -> {size, palette, blocks}    ★读 NBT（★手写解析器 ✗ 只用标准库✗★）✗★
  to_cells(bp, origin)       -> [{dx,dy,dz,block,props}]   ★转成**现有蓝图 `cells` 格式**✗★
  ids(bp)                    -> set(block id)              ★供"★这些方块注册表里有吗★"核对✗★

★为什么手写 NBT✗★：★不引第三方依赖 ✗ 结构文件只用到 12 种标签✗★ ✓
"""
from __future__ import annotations

import gzip
import pathlib
import struct
import sys, paths as PA
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACK = PA.MODS_DIR
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class _R:
    def __init__(self, b: bytes):
        self.b, self.i = b, 0

    def take(self, n):
        v = self.b[self.i:self.i + n]
        if len(v) != n:
            raise ValueError("NBT truncated")
        self.i += n
        return v

    def u(self, fmt, n):
        return struct.unpack(">" + fmt, self.take(n))[0]

    def string(self):
        n = self.u("H", 2)
        return self.take(n).decode("utf-8", errors="replace")


def _payload(r: _R, tag: int):
    if tag == 1:
        return r.u("b", 1)
    if tag == 2:
        return r.u("h", 2)
    if tag == 3:
        return r.u("i", 4)
    if tag == 4:
        return r.u("q", 8)
    if tag == 5:
        return r.u("f", 4)
    if tag == 6:
        return r.u("d", 8)
    if tag == 7:
        return list(r.take(r.u("i", 4)))
    if tag == 8:
        return r.string()
    if tag == 9:
        et = r.u("b", 1)
        n = r.u("i", 4)
        return [_payload(r, et) for _ in range(max(0, n))]
    if tag == 10:
        out = {}
        while True:
            t = r.u("b", 1)
            if t == 0:
                return out
            name = r.string()
            out[name] = _payload(r, t)
    if tag == 11:
        n = r.u("i", 4)
        return list(struct.unpack(">" + "i" * n, r.take(4 * n)))
    if tag == 12:
        n = r.u("i", 4)
        return list(struct.unpack(">" + "q" * n, r.take(8 * n)))
    raise ValueError("unknown NBT tag %d" % tag)


def parse_nbt(raw: bytes) -> dict:
    """★字节 ⇒ dict✗★（★自动认 gzip✗★）"""
    buf = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    r = _R(buf)
    t = r.u("b", 1)
    if t != 10:
        raise ValueError("root tag is not Compound (%d)" % t)
    r.string()                       # 根名字
    return _payload(r, 10)


def find(pattern: str = "", limit: int = 400, pack=None) -> list:
    """★在包内 jar 里检索结构文件✗★"""
    p = pathlib.Path(pack) if pack else PACK
    out = []
    for jar in sorted(p.glob("*.jar")):
        try:
            with zipfile.ZipFile(jar) as z:
                for nm in z.namelist():
                    if not nm.endswith(".nbt"):
                        continue
                    if "/structures/" not in nm and not nm.startswith("structures/"):
                        continue
                    if pattern and pattern.lower() not in nm.lower():
                        continue
                    out.append((jar.name, nm))
                    if len(out) >= limit:
                        return out
        except Exception as exc:          # ★不许静默✗★
            print("structures: 跳过 %s（%r）" % (jar.name, exc), file=sys.stderr)
    return out


def read(jar_name: str, path: str, pack=None) -> dict:
    """★读一个结构文件 ⇒ `{size,palette,blocks}`✗★"""
    p = pathlib.Path(pack) if pack else PACK
    with zipfile.ZipFile(p / jar_name) as z:
        raw = z.read(path)
    nbt = parse_nbt(raw)
    size = nbt.get("size") or [0, 0, 0]
    pal = []
    for e in (nbt.get("palette") or []):
        if isinstance(e, dict):
            pal.append({"id": e.get("Name") or "", "props": e.get("Properties") or {}})
    blocks = []
    for b in (nbt.get("blocks") or []):
        if not isinstance(b, dict):
            continue
        st = b.get("state")
        pos = b.get("pos") or [0, 0, 0]
        blocks.append({"pos": [int(v) for v in pos],
                       "state": int(st) if st is not None else -1,
                       "nbt": bool(b.get("nbt"))})
    return {"size": [int(v) for v in size], "palette": pal, "blocks": blocks,
            "source": {"jar": jar_name, "path": path}}


def to_cells(bp: dict, origin=(0, 0, 0)) -> list:
    """★转成现有蓝图的 `cells` 格式✗★（★dx/dy/dz 相对锚点 ＋ block 名字✗★）"""
    ox, oy, oz = (int(v) for v in origin)
    pal = bp.get("palette") or []
    cells = []
    for b in bp.get("blocks") or []:
        st = b.get("state", -1)
        if st < 0 or st >= len(pal):
            continue
        e = pal[st]
        if not e.get("id"):
            continue
        x, y, z = b["pos"]
        cells.append({"dx": x, "dy": y, "dz": z, "block": e["id"],
                      "props": e.get("props") or {}})
    return cells


def ids(bp: dict) -> set:
    return {e.get("id") for e in (bp.get("palette") or []) if e.get("id")}


def main(argv) -> int:
    if argv and argv[0] == "--find":
        pat = argv[1] if len(argv) > 1 else ""
        rows = find(pat, limit=30)
        print("find(%r) ⇒ %d 条（前 30）" % (pat, len(rows)))
        for j, nm in rows:
            print("  %-40s %s" % (j[:40], nm[:70]))
        return 0
    if argv and argv[0] == "--read":
        bp = read(argv[1], argv[2])
        print("size=%s ｜ palette=%d ｜ blocks=%d"
              % (bp["size"], len(bp["palette"]), len(bp["blocks"])))
        for e in bp["palette"][:12]:
            print("  %-48s %s" % (e["id"][:48], str(e["props"])[:36]))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
