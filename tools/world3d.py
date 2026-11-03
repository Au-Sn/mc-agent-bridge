#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world3d.py -- ★3D 体素世界模型（v2：**区域式懒加载**）★（§79.355 ✗ O1）

★★v2 比 v1 快在哪✗★★（★都是实测✗★）✗★：
  · ★`dshscan` 一页**能装 2000 格**（★回包 55 KB ✗ 解析数与 `shown` 相等 ⇒ **不截断**✗★）✗★
  · ★v1 按 **16³ 区块**读 ⇒ 一个区块只 788 实心格 ✗ **一趟只运 40%**✗★
  · ★v2 按**大盒子（★REGION✗★）**读 ⇒ 一趟 2000 格 ⇒ **约 3 倍**✗★ ✓
★关键设计✗★：★**"★缺失 ＝ 空气★"只在**读过的区域**内成立**✗★ ⇒ 所以要记 `known`（★盒子的时间戳✗★）✗
  ★不在已知区域 ⇒ **懒读它所在的 REGION** ✗ 读不到 ⇒ 返回 `None`（★未知 ✗ 不许假装是空气✗★）✗★ ✓
"""
from __future__ import annotations

import pathlib          # ★★§79.401✗★★：★`_load_h3d()` 用它读导出 ✗ **原来根本没 import**✗★
                        #   ⇒ ★每次都 `NameError` ✗ 又被 `except: pass` 吞掉✗★
                        #   ⇒ ★**导出表一直是空的** ✗ `collision_h` 只靠名字兜底✗★ ✓
import re
import sys            # ★★§79.401 的教训✗★★：★模块级依赖**显式 import** ✗ 别藏进 try★
                      #   （★`pathlib` 就是藏没的 ⇒ `NameError` 被 `except: pass` 吞
                      #     ⇒ **导出表从没加载**✗★）✗★ ✓
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REGION = (32, 16, 32)         # ★一次懒读的粒度（★≈2000 格/页 ✗ 3 页约 1.8 秒✗★）✗★
PAGE_LIMIT = 2000             # ★实测安全 ✗ 不截断✗★
MAX_PAGES = 6
AIRISH = ("air",)
SOFT = ("torch", "flower", "grass", "sapling", "vine", "rail", "carpet", "button",
        "pressure_plate", "sign", "banner", "candle", "lantern", "tripwire",
        "redstone_wire", "lever", "ladder", "scaffolding", "chain", "string")
# ★★§79.356（★用户裁决✗★）✗★★：★"★门这种可打开的★"独立成**可过但要交互**一类✗★
#   ★细分✗★：★door ✗ trapdoor ✗ fence_gate ✗ gate（★红石门✗★）✗★ ✓
DOORISH = ("_door", "trapdoor", "fence_gate")
DOOR_KIND = (("trapdoor", "trapdoor"), ("fence_gate", "gate"), ("_door", "door"))
REDSTONE_ONLY = ("iron_door", "iron_trapdoor")      # ★交互打不开 ✗ 要红石✗★
# ★通行性四态 ＋ 未知✗★
P_FREE, P_INTERACT, P_REDSTONE, P_BLOCKED, P_UNKNOWN = "free", "interact", "redstone", "blocked", "unknown"
UNKNOWN = None


# ★★§79.359✗★★：★**碰撞高度**的真源 ＝ 导出（★`max_height` ✗ 每块都有✗★）✗★
#   ★名字只在导出里查不到时兜底 ✗ 而且**明确标出是兜底**✗★ ✓
_H3D = {
    "has_be": {},"loaded": False, "map": {}, "src": "", "err": [], "skipped": 0, "raw": 0}


def _load_h3d():
    """★把导出里的 `max_height` 装进表 ✗★

    ★★§79.401 修✗★★：★这里原来**两条致命问题**✗★：
    1. ★`try` 把**整个循环**包住 ✗ 且 `except: pass`**✗★ ⇒
       ★只要**一条**的 `max_height` 不是数字（★`null`／字符串／缺字段✗★）
       ⇒ ★**整张表被放弃** ✗ 变成 **0 条** ✗ 而且**一声不响**✗★ ✓
       ★后果✗★：★`collision_h` **永远**走**名字兜底** ✗
       ⇒ ★`pink_petals` 兜底成 **1.0** ✗ 规划把**能站的格判成墙**✗★ ✓
    2. ★`_H3D["loaded"] = True` 放在 try **之前** ✗ 失败后**永不重试**✗★ ✓
    ★现在✗★：★**逐条**兜 ✗ 坏条目记进 `err` ✗ 计数 ✗ 加载失败**能被查出来**✗★ ✓
    """
    if _H3D["loaded"]:
        return _H3D
    try:
        import json
        import kb_export as KX
        p = pathlib.Path(KX.find_export(""))
        blocks = json.loads(p.read_text(encoding="utf-8")).get("blocks") or {}
        _H3D["raw"] = len(blocks)
        for k, v in blocks.items():
            if not isinstance(v, dict) or "max_height" not in v:
                _H3D["skipped"] += 1
                continue
            try:
                _H3D["map"][k] = float(v["max_height"])
                # §79.486: 机器最硬的信号不是名字 ✗ 是"有没有方块实体" ✓
                _H3D["has_be"][k] = bool(v.get("has_block_entity"))
            except (TypeError, ValueError):
                # ★逐条兜✗★：★坏的记下来 ✗ 不影响别人✗★ ✓
                _H3D["skipped"] += 1
                if len(_H3D["err"]) < 20:
                    _H3D["err"].append("%s=%r" % (k, v.get("max_height")))
        _H3D["src"] = p.name
        _H3D["loaded"] = True
    except Exception as e:                      # ★不许静默✗★
        _H3D["err"].append("load: %r" % (e,))
        _H3D["loaded"] = False                  # ★允许重试✗★
    return _H3D


_H_FALLBACK = ((":air", 0.0), ("carpet", 0.0625), ("snow", 0.125), ("slab", 0.5),
               ("stairs", 1.0), ("fence", 1.5), ("wall", 1.5), ("_door", 1.0),
               ("trapdoor", 0.1875), ("pane", 1.0), ("leaves", 1.0))

# ★★§79.393✗★★：★**真没碰撞**的方块（★导出把它们记成 1.0 ✗ 那是导出的一处数据缺陷✗★）✗★
#   ★实测✗★：★`minecraft:pink_petals` 导出 `max_height=1.0` ✗ 实际**碰撞为空**
#   （★人能站进去 ✗ 模组 `floorOk` 也不把它当地板✗★）✗★ ⇒ ★这些按 **0.0** 算✗★ ✓
#   ⚠★**必须是"★后缀★"匹配** ✗ 不能用"★包含★"✗★：★`grass` 包含匹配会命中 `grass_block`✗★
#     ⇒ ★整个地面变成可穿透 ✗ `model_check` 当场掉到 87.5% ✗（★我犯过 ✗ 记下来✗★）✗★ ✓
_NO_COLLISION_SUFFIX = (
    "petals", "torch", "_sapling", "short_grass", "tall_grass", "seagrass",
    "fern", "bush", "sprout", "_vine", "vine", "_roots", "roots",
    "sugar_cane", "kelp", "kelp_plant", "lily_pad", "coral", "coral_fan",
    "lever", "button", "tripwire", "redstone_wire",
    "wheat", "carrots", "potatoes", "beetroots", "melon_stem",
    "pumpkin_stem", "cave_vines", "cave_vines_plant", "small_dripleaf",
    "big_dripleaf_stem", "glow_lichen", "hanging_roots", "spore_blossom",
)



def occupied_cells(h) -> int:
    """★碰撞高 `h` **占几格**（★§79.451 ✗ 通用 ✗ 不看方块名✗★）✗★

    ★`h=1.0` ⇒ 1 ✗ `h=1.5`（栅栏）⇒ 2 ✗ `h=2.0` ⇒ 2 ✗ `h=2.5` ⇒ 3✗★ ✓
    ★⇒ ★换任何模组包 ✗ 只要有导出 ✗ 自动就对✗★ ✓
    """
    if h is None:
        return 0
    try:
        h = float(h)
    except (TypeError, ValueError):
        return 0
    if h <= 0.05:
        return 0
    import math as _m
    return max(1, int(_m.ceil(h - 1e-9)))



def collision_h(name: str) -> float:
    """★这一块的**碰撞高度**✗★（★导出优先 ✗ 名字兜底✗★）✗★

    ★★§79.393 修✗★★：★原来只切了 `[…]` ✗ **没切逗号状态**✗★ ⇒
      ★`minecraft:pink_petals,facing=north,flower_amount=4` 这类**带状态**的名字**查不到导出**✗
      ⇒ 兜底 **1.0** ⇒ ★**所有带状态的小方块都被当成整块**✗★
      （★花瓣／火把／地毯／花盆全中招 ✗ 规划层因此**把能站的地方判成墙**✗★）✗★ ✓
    ★现在✗★：★**两段都切**（`[…]` 和 `,状态`✗★）✗★ ✓
    """
    _load_h3d()
    n = (name or "").split("[", 1)[0].split(",", 1)[0].strip().lower()
    if not n:
        return 0.0
    # ★★§79.401✗★★：★**导出优先**✗ —— 导出里有的**一律信它**✗★
    #   （★模组按**真碰撞盒**算 ✗ `pink_petals` 导出就是 0.0 ✓ 本来就对✓★）✗★
    #   ★我一开始把"★覆盖表★"排在导出**前面** ✗ 那是**两套真相** ✗ 危险✗★
    if n in _H3D["map"]:
        return _H3D["map"][n]
    # ★★§79.401✗★★：★导出里**没有**的才用**名字兜底**✗★
    #   （★`short_grass` 这种 1.20.3 改名后导出里没有的✗★）
    #   ⚠★**后缀**匹配 ✗ 不是"包含"✗★（★"包含"会让 `grass_block` 变 0 ✗ 地面穿透✗★）✗★
    for suf in _NO_COLLISION_SUFFIX:
        if n.endswith(suf):
            return 0.0
    if n.endswith(":air") or n.endswith("_air"):
        return 0.0
    for kw, h in _H_FALLBACK:
        if kw in n:
            return h
    return 1.0        # ★查不到就按整块 ✗ 保守✗★


class World3D:
    def __init__(self, dsh=None, ttl=300.0):
        if dsh is None:
            sys.path.insert(0, "tools")
            import mcp_core as C
            dsh = C.dsh
        self.dsh = dsh
        self.ttl = ttl
        self.cells = {}            # (x,y,z) -> 方块名[状态]（★只有实心✗★）
        self.known = []            # [(box, t)]：★读全了的盒子✗★
        self.calls = 0
        self.pages = 0
        self.seconds = 0.0
        self.loaded_regions = set()
        self.partial = []          # ★没读全的盒子（§79.371）✗★
        self.errors = []           # ★dshscan 回包不合法时**留原文**✗★
        # ★★模组 2.27.0 的 `tick=`／`hash=`（★2026-10-27 ✗ task-6✗★）✗★★
        self.region_meta = {}      # box -> {"tick": int, "hash": int, "keys": set(格子)}
        self.last_tick = None      # ★最近一次扫到的 `tick=`（★旧模组 ⇒ None✗★）
        self.last_hash = None      # ★最近一次扫到的 `hash=`（★旧模组 ⇒ None✗★）
        self.last_reused = 0       # ★最近一次 fetch **复用了吗**（0／1 ✗ `stats()` 里看得见✗★）
        self.reuse_total = 0       # ★累计复用几次（★同区两次 fetch 的现场证据✗★）
        self.legacy_warned = False # ★旧模组：只警告一次 ✗ 不刷屏✗★
        self.legacy_scans = 0      # ★旧模组回包计数（★诚实计数 ✗ 不假装支持✗★）
        # sec 79.472: a dead/slow link must not turn planning into a hang.
        self.frozen = False       # ★冻结：规划期间**不许**再抓（★模型固定✗★）
        self.fetch_fail = 0       # ★连续抓取失败次数✗★
        self.max_fail = 3         # ★熔断阈值：连续失败这么多次就不许再抓✗★

    # ── 区域 ──────────────────────────────────────────────────────
    @staticmethod
    def region_of(x, y, z):
        rx, ry, rz = REGION
        return (x // rx, y // ry, z // rz)

    def region_box(self, rk):
        rx, ry, rz = REGION
        cx, cy, cz = rk
        return (cx * rx, cy * ry, cz * rz,
                cx * rx + rx - 1, cy * ry + ry - 1, cz * rz + rz - 1)

    def _known_at(self, x, y, z) -> bool:
        now = time.time()
        for (b, t) in self.known:
            if now - t > self.ttl:
                continue
            if b[0] <= x <= b[3] and b[1] <= y <= b[4] and b[2] <= z <= b[5]:
                return True
        return False

    def _mark_known(self, box) -> None:
        """★把一个盒子标成「读完」✗★ —— ★同一盒子**替换**时间戳 ✗ 不重复堆✗★ ✓"""
        tb = tuple(box)
        self.known = [(bb, tp) for (bb, tp) in self.known if tuple(bb) != tb]
        self.known.append((tb, time.time()))
        self.loaded_regions.add(tb[:3])

    def fetch_region(self, box) -> bool:
        """★读一整个盒子✗★ —— ★**只有读完才算 known**✗★（★§79.371 保真度✗★）

        ★★旧版的 bug✗★★：★结尾**无条件** `known.append` ⇒ 只读 1 页／撞 MAX_PAGES／中途失败
          都把**整盒**标成已知 ⇒ 没扫到的格被当**空气** ⇒ "★模型说没地板而现实有★"✗★ ✓
        ★★现在✗★★：★`page == npages` 才算读完 ✗ 否则进 `partial` ✗ 且**返回 False**✗★ ✓
        ★★tick／hash 复用（★模组 2.27.0✗★）✗★★：
          ★回包头里现在有 `tick=<gameTime> hash=<内容哈希>`✗★ ⇒ ★同一个 box **再扫一次**✗：
          ★hash 与缓存一致 ＋ tick 变新 ＋ 旧 cells 还在（★没被 invalidate✗★）⇒ **直接复用**✗★ ✓
          ★（★hash 是「名字＋数量」的滚动哈希 ✗ **不含位置** ✗ 见 `tmp/scan_hash.md` 风险一节✗★）
          ★旧模组（没有这两个字段）⇒ **按原行为** ✗ 但打一行 `stderr` 警告（★不许静默降级✗★）✓
        ★★hash 变了 ⇒ **真重建**✗★★：★把上一遍有、这一遍没有的格子**剔掉**✗★
          ★（★否则「世界变了」只表现为「少读到几格」 ✗ 被挖掉的方块会留**幽灵**✗★）✓
        """
        b = box
        page = 1
        npages = 1
        seen = 0
        new_keys = set()          # ★这一遍**真读到了**哪些格（★重建时剔幽灵用✗★）
        tick = hsh = None
        while page <= npages and seen < MAX_PAGES:
            cmd = 'dshscan %d %d %d %d %d %d ":" %d %d' % (
                b[0], b[1], b[2], b[3], b[4], b[5], PAGE_LIMIT, page)
            t0 = time.time()
            self.calls += 1
            self.pages += 1
            txt = self.dsh(cmd, 150.0) or ""
            self.seconds += time.time() - t0
            head = txt.splitlines()[0] if txt else ""
            if "dshscan box=" not in head:
                self.errors.append({"box": b, "page": page, "raw": (txt or "")[:200]})
                self.fetch_fail += 1        # sec 79.472 breaker
                return False
            m = re.search(r"page=(\d+)/(\d+)", head)
            if not m:
                self.errors.append({"box": b, "page": page, "raw": head[:200]})
                self.fetch_fail += 1        # sec 79.472 breaker
                return False
            seen, npages = int(m.group(1)), int(m.group(2))
            if page == 1:
                # ★★模组 2.27.0：`tick=`／`hash=`（★只在第一页定这一次 ✗ 后面页同值✗★）✗★★
                tm = re.search(r"\btick=(-?\d+)", head)
                hm = re.search(r"\bhash=(-?\d+)", head)
                tick = int(tm.group(1)) if tm else None
                hsh = int(hm.group(1)) if hm else None
                if tick is None or hsh is None:
                    # ★旧模组 ⇒ **保持原行为** ✗ 但必须留下记录（★不许静默降级✗★）✗★ ✓
                    self.legacy_scans += 1
                    self.last_tick, self.last_hash, self.last_reused = None, None, 0
                    if not self.legacy_warned:
                        self.legacy_warned = True
                        print("★[world3d] 警告✗★：`dshscan` 回包没有 `tick=`／`hash=`"
                              "（★旧模组 < 2.27.0✗★）⇒ ★判断不了世界变没变 ✗ 按原行为每次重建★"
                              "（★这行就是「不静默」的记录 ✗ 不代表通过✗★）", file=sys.stderr)
                else:
                    self.last_tick, self.last_hash, self.last_reused = tick, hsh, 0
                    _meta = self.region_meta.get(tuple(b))
                    if (_meta is not None and _meta.get("hash") == hsh
                            and _meta.get("tick") is not None and tick > _meta["tick"]
                            and self.coverage(box) == 1.0):
                        # ★★世界没变 ⇒ 复用✗★★：★不解析 cells ✗ 也不读后面那 N-1 页✗★ ✓
                        self._mark_known(box)
                        _meta["tick"] = tick
                        self.last_reused = 1
                        self.reuse_total += 1
                        self.fetch_fail = 0         # sec 79.472 success resets breaker
                        return True
            i = head.find("cells[")
            sec = head[i + 6:] if i >= 0 else ""
            toks = list(re.finditer(r"(-?\d+),(-?\d+),(-?\d+):", sec))
            for k, t2 in enumerate(toks):
                end = toks[k + 1].start() if k + 1 < len(toks) else len(sec)
                pos = (int(t2.group(1)), int(t2.group(2)), int(t2.group(3)))
                self.cells[pos] = sec[t2.end():end].strip().rstrip("]").strip()
                new_keys.add(pos)
            page = seen + 1
        if seen < npages:
            # ★没读完 ⇒ **不标 known** ✗ 只记账（★自检会看到✗★）✗★
            self.partial.append({"box": b, "page": seen, "npages": npages})
            self.fetch_fail += 1        # sec 79.472 breaker
            return False
        # ★★读完了 ✗ 才做三件事✗★★：①剔幽灵 ②记 meta ③标 known
        _old = self.region_meta.get(tuple(b))
        if _old is not None and _old.get("hash") is not None and hsh is not None:
            for pos in (_old.get("keys") or set()) - new_keys:
                self.cells.pop(pos, None)     # ★上一遍有、这一遍没有 ⇒ 那格现在是**空气**✗★
        if tick is not None and hsh is not None:
            self.region_meta[tuple(b)] = {"tick": tick, "hash": hsh, "keys": new_keys}
        else:
            self.region_meta.pop(tuple(b), None)   # ★旧模组 ⇒ 不留 meta（下次也复用不了）＝原行为✗★
        self._mark_known(box)
        self.fetch_fail = 0         # sec 79.472 success resets breaker
        return True

    def coverage(self, box):
        """★这个盒子"★已知了几成★"✗★（★1.0 ⇒ 读完 ✗ 0 ⇒ 没读全 ✗ 自检用✗★）✗★"""
        for b, tp in self.known:
            if tp >= 0 and b[:6] == tuple(box)[:6]:
                return 1.0
        return 0.0

    def _ensure(self, x, y, z) -> bool:

        # sec 79.472: never fetch while frozen, and stop after the breaker trips.

        if self.frozen or self.fetch_fail >= self.max_fail:

            return False

        if self._known_at(x, y, z):

            return True

        return self.fetch_region(self.region_box(self.region_of(x, y, z)))


    def freeze(self):

        """★冻结模型✗★：★规划前调用 ✗ 之后 get() 对未知格直接回 UNKNOWN ✗ 不再现抓✗★"""

        self.frozen = True


    def unfreeze(self):

        """★解冻✗★：★下一次真正要动手前再抓✗★"""

        self.frozen = False

        self.fetch_fail = 0

    # ── 单格 ──────────────────────────────────────────────────────
    def invalidate(self, box=None):
        """★交互／世界改变后**作废**缓存✗★（★§79.358 第 3 条✗★）✗★"""
        if box is None:
            self.cells.clear()
            self.known.clear()
            self.loaded_regions.clear()
            self.region_meta.clear()          # ★tick/hash 也一起作废（★否则复用会拿旧 keys✗★）
            return
        self.known = [(b, tp) for (b, tp) in self.known
                      if not (b[0] <= box[3] and box[0] <= b[3]
                              and b[1] <= box[4] and box[1] <= b[4]
                              and b[2] <= box[5] and box[2] <= b[5])]
        self.cells = {k: v for k, v in self.cells.items()
                      if not (box[0] <= k[0] <= box[3] and box[1] <= k[1] <= box[4]
                              and box[2] <= k[2] <= box[5])}
        self.region_meta = {k: v for k, v in self.region_meta.items()
                            if not (k[0] <= box[3] and box[0] <= k[3]
                                    and k[1] <= box[4] and box[1] <= k[4]
                                    and k[2] <= box[5] and box[2] <= k[5])}
        self.loaded_regions.clear()

    def get(self, x, y, z):
        """★返回 方块名[状态] ／ ""（★空气✗★）／ None（★未知 ✗ 没读过✗★）✗★"""
        if (x, y, z) in self.cells:
            return self.cells[(x, y, z)]
        if self._known_at(x, y, z):
            return ""
        if self._ensure(x, y, z):
            return self.cells.get((x, y, z), "")
        return UNKNOWN

    def name(self, x, y, z) -> str:
        """★方块名✗★（★切掉 […] 和 ,状态 两段✗★）✗★"""
        v = self.get(x, y, z)
        if v is None:
            return ""
        return v.split("[", 1)[0].split(",", 1)[0]

    def state(self, x, y, z) -> str:
        v = self.get(x, y, z)
        if not v or "[" not in v:
            return ""
        return v[len(v.split("[", 1)[0]):]

    def h(self, x, y, z) -> float:
        """★这一格的**碰撞高度**✗★（★未知 ⇒ -1 ✗ 不许当 0✗★）✗★"""
        v = self.get(x, y, z)
        if v is None:
            return -1.0
        return collision_h(v)

    def solid(self, x, y, z) -> bool:
        """★"★实心★"＝ 碰撞高度 > 0.05（★占这一格 ✗ 人不能待在里面✗★）✗★"""
        return self.h(x, y, z) > 0.05

    def pass_info(self, x, y, z) -> dict:
        """★通行性：free／interact／redstone／blocked／unknown✗★

        ★★§79.361 更正（★用户实测✗★）✗★★：★门是**状态相关**方块 ✗
          ★**实时状态 `open=` 才是判据** ✗ 导出的 `max_height` 是**默认状态**的值，
          只能用于**没有状态字段**的方块✗★ ⇒ ★上一版（§79.360）拿默认状态覆盖实时状态是**错的**✗★ ✓
        """
        v = self.get(x, y, z)
        if v is None:
            return {"kind": P_UNKNOWN, "subtype": "", "action": None, "why": "没读到"}
        # ★★§79.451✗★★：★下方方块**溢出**进这一格 ⇒ 这一格也被占✗★
        #   ★通用 ✗ 不看任何方块名：★h > 1.0 ⇒ 占 ceil(h) 格（栅栏 1.5 ⇒ 占 2 格）✗★
        _below = self.get(x, y - 1, z)
        _occ = occupied_cells(collision_h(_below)) if _below is not None else 0
        if _occ > 1:
            return {"kind": P_BLOCKED, "subtype": "tall_block", "action": None,
                    "why": "下方方块高过 1 格（h=%s ⇒ 占 %d 格）⇒ 占到这一格"
                           % (collision_h(_below), _occ)}
        n = v.split("[", 1)[0].lower()
        # ★★① 有 `open=` 的（★门／活板门／栅栏门✗★）⇒ **实时状态优先**✗★★
        if "open=" in v:
            sub = ""
            for key, name in DOOR_KIND:
                if key in n:
                    sub = name
                    break
            if any(k in n for k in REDSTONE_ONLY):
                return {"kind": P_REDSTONE, "subtype": sub or "door", "action": "redstone",
                        "why": "铁门类 ⇒ 交互打不开 ✗ 要红石"}
            if "open=true" in v:
                return {"kind": P_FREE, "subtype": sub, "action": None,
                        "why": "★实时 open=true ⇒ **真的能过**（★实际碰撞已是空✗★）✗★"}
            return {"kind": P_INTERACT, "subtype": sub, "action": "use",
                    "why": "★实时 open=false ⇒ 可过但要交互（use）✗★"}
        # ★② 没有状态字段 ⇒ 用碰撞高度✗★
        hh = collision_h(v)
        if hh <= 0.05:
            return {"kind": P_FREE, "subtype": "", "action": None,
                    "why": "碰撞高 %.2f ⇒ 空" % hh}
        return {"kind": P_BLOCKED, "subtype": "", "action": None,
                "why": "碰撞高 %.2f ⇒ 占格" % hh}

    def passable(self, x, y, z) -> bool:
        """★能过 ＝ free 或 interact✗★（★interact 的代价由规划层加✗★）✗★"""
        return self.pass_info(x, y, z)["kind"] in (P_FREE, P_INTERACT)

    def support(self, x, y, z) -> bool:
        """★脚在 (x,y,z) 时**踩得住吗**✗★ ＝ 下面那格碰撞高 > 0.05 ✗★"""
        return self.h(x, y - 1, z) > 0.05

    def standable(self, x, y, z) -> bool:
        """★能站 ✗ ＝ 踩得住 ＋ 本格空 ＋ 头顶格空✗★（★1.8 高 ⇒ 要两格空✗★）✗★

        ★★为什么仓库里**还有**一套 `mapread.Map.standable`（★§79.438 ✗ task-8 ✗ 不合并✗★）✗★★：
          ★这一层是 **3D 体素**✗★（★`dshscan` 逐格读 ＋ 导出碰撞高 ＋ 实时 `open=` 状态✗★）⇒
            ★能答**任意一格** ✗ 数据**现读** ✗ 准但贵✗★ ✓
          ★`mapread.Map.standable` 是 **2.5D 快图**✗★（★`dshmap` 一柱一个字母
            ＋ 模组按碰撞箱的结论 ＋ 名字兜底✗★）⇒ ★便宜 ✗ 但只答「建图那一刻那一柱」✗★ ✓
          ★⇒ ★同一个问题 ✗ **两种数据层** ✗ 不合并（★合并会丢掉「快」或「准」其中一项✗★）✗★ ✓
          ★⇒ 分界线✗★：★只有 `dshmap`／要快 ⇒ 用 `mapread.Map.standable` ✗
            要任意 y／要实时状态／要 3D ⇒ 用**这里**✗★ ✓
        """
        return self.support(x, y, z) and self.passable(x, y, z) and self.passable(x, y + 1, z)

    # ── ★"★脚下高度／坑深★"✗★（★§79.372 ✗ 用户提醒"★差一格会全部失效★"✗★）──────
    def surface(self, x, z, y_hint, radius=4):
        """★这一列里**离 y_hint 最近的可站脚格**✗★（★没读到就回 None ✗ 不许猜✗★）✗★"""
        best = None
        bestd = 10 ** 9
        for y in range(y_hint - radius, y_hint + radius + 1):
            v = self.get(x, y, z)
            if v is None:
                continue                      # ★没读到 ✗ 不算✗★
            if self.standable(x, y, z):
                d = abs(y - y_hint)
                if d < bestd:
                    best, bestd = y, d
        return best

    def pit_depth(self, x, y, z):
        """★"★坑多深★"✗★ ＝ **四邻的可站面** 里最高的 − 自己脚格 ✗★
        （★0 ⇒ 和邻边齐平 ✗ 1 ⇒ 矮 1 格 ✗ 2 ⇒ 矮 2 格（★爬不出来 ✗ 得跳＋垫脚✗★）✗★ ✓）
        """
        best = None
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s = self.surface(x + dx, z + dz, y)
            if s is not None and (best is None or s > best):
                best = s
        if best is None:
            return None
        return best - y

    def pit_report(self, x, y, z):
        """★四面各多高**＋**坑深✗★（★给人看的✗★）✗★"""
        dirs = {(1, 0): "东", (-1, 0): "西", (0, 1): "南", (0, -1): "北"}
        face = {}
        for (dx, dz), tag in dirs.items():
            s = self.surface(x + dx, z + dz, y)
            face[tag] = None if s is None else (s - y)
        return {"feet": (x, y, z), "faces": face, "pit_depth": self.pit_depth(x, y, z)}


    def interactables(self):
        """★把已读到的所有★可过但要交互／要红石★的格子列出来✗★ ✓"""
        out = []
        for (x, y, z) in sorted(self.cells):
            info = self.pass_info(x, y, z)
            if info["kind"] in (P_INTERACT, P_REDSTONE):
                out.append((x, y, z, info["kind"], info["subtype"],
                            self.cells[(x, y, z)].split("[", 1)[0]))
        return out

    # ── 统计 ─────────────────────────────────────────────────────
    def stats(self) -> dict:
        """★调用方看得见的计数✗★ —— ★`tick`／`hash`／`reused` 是模组 2.27.0 的复用证据✗★ ✓"""
        inter = self.interactables()
        return {"cells": len(self.cells), "regions": len(self.loaded_regions),
                "calls": self.calls, "pages": self.pages,
                "seconds": round(self.seconds, 2),
                "tick": self.last_tick, "hash": self.last_hash,
                "reused": self.last_reused, "reuse_total": self.reuse_total,
                "legacy_scans": self.legacy_scans,
                "interact": sum(1 for i in inter if i[3] == P_INTERACT),
                "redstone": sum(1 for i in inter if i[3] == P_REDSTONE)}

    # ── 剖面 ─────────────────────────────────────────────────────
    def slice_x(self, x, z0, z1, y0, y1) -> str:
        out = ["     z=%d..%d  x=%d" % (z0, z1, x)]
        for y in range(y1, y0 - 1, -1):
            row = []
            for z in range(z0, z1 + 1):
                v = self.get(x, y, z)
                row.append("?" if v is None else ("#" if self.solid(x, y, z) else "."))
            out.append("%+4d %s" % (y, "".join(row)))
        return "\n".join(out)

    def slice_z(self, z, x0, x1, y0, y1) -> str:
        out = ["     x=%d..%d  z=%d" % (x0, x1, z)]
        for y in range(y1, y0 - 1, -1):
            row = []
            for x in range(x0, x1 + 1):
                v = self.get(x, y, z)
                row.append("?" if v is None else ("#" if self.solid(x, y, z) else "."))
            out.append("%+4d %s" % (y, "".join(row)))
        return "\n".join(out)

    def top_roof(self, x0, z0, x1, z1, y0, y1) -> str:
        """★俯视：每列**最高实心**在哪一层（★能看到屋顶／墙顶的轮廓✗★）✗★"""
        out = ["     屋顶俯视 x=%d..%d z=%d..%d" % (x0, x1, z0, z1)]
        out.append("      " + "".join(str(abs(x) % 10) for x in range(x0, x1 + 1)))
        for z in range(z0, z1 + 1):
            row = []
            for x in range(x0, x1 + 1):
                top = None
                for y in range(y1, y0 - 1, -1):
                    v = self.get(x, y, z)
                    if v is None:
                        top = "?"
                        break
                    if self.solid(x, y, z):
                        top = y - y0
                        break
                if top is None:
                    row.append(".")
                elif top == "?":
                    row.append("?")
                else:
                    row.append("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[min(int(top), 35)])
            out.append("%+5d %s" % (z, "".join(row)))
        return "\n".join(out)
