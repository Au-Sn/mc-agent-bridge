#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixture_scan.py -- ★批量扫一个盒子 ＋ 把校准网格登记成"测试件"★（只读世界 ✓ 只写**声明**）

★为什么需要"批量扫"✗★（★今天量出来的✗★）：★逐格问一次世界是 **608 ms**✗★ ⇒
  ★校准盒 1859 格 ＝ 19 分钟 ✗ 根本不能做快照✗★ ✓
★批量怎么做✗★（★与"★为什么慢 ⇒ 改批量原语★"那条老教训同源✓★）：
  ① ★一次**不匹配**的扫** ✗ 拿回执里的 `counts[…]` ⇒ ★这个盒子里到底有哪几种方块✗★ ✓
  ② ★每种**匹配**一次** ✗ `max_=1000` ⇒ 回执 `cells[x,y,z:名字 …]` 一次拿全✗★ ✓
  ③ ★没被列到的格子 ⇒ **空气**✗★（★这是"★那一刻世界的样子★"的口径 ✓ 见 `fixtures.snapshot` 的注释✓★）
  ⇒ ★1 ＋ kinds 次调用✗★（本例 17 次 ✗ 约 12 秒 ✓ 而逐格要 19 分钟 ✓）

★它写什么✗★：★只写**声明**（★`state/test_fixtures.json` 的清单 ✗ 与
  `state/fixtures/<id>.snapshot.json` 的快照✓★）—— ★这两个正是**该留档**的东西 ✗
  不是探针噪声 ✓★ ✓（★口径✗★：★"★探针不许动真数据★"说的是**知识表／世界** ✗
  不是"★不许留下声明★"✓★）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import fixtures as FX  # noqa: E402

SNAP_DIR = ROOT / "state" / "fixtures"


def _scan_raw(box, match=None, max_=1000):
    import mc_mcp as M
    out, bad = M.t_scan(*box, match=match, max_=max_)
    return str(out or ""), bool(bad)


def counts_of(txt: str):
    """★回执 `counts[a:1,b:2,…]` ⇒ [(名字, 个数), …]✗★（★顺序＝按个数降序 ✓ 模组给的✓★）"""
    m = re.search(r"counts\[([^\]]*)\]", txt)
    if not m:
        return []
    out = []
    for part in m.group(1).split(","):
        if ":" not in part:
            continue
        nm, _, n = part.rpartition(":")
        out.append((nm.strip(), int(n) if n.strip().isdigit() else 0))
    return out


def cells_of(txt: str):
    """★回执 `cells[x,y,z:名字 …]` ⇒ {"x,y,z": 名字}✗★（★空格分隔 ✗ 分页由 max_ 管✓★）

    ★★2026-10-03 修的真错✗★★：★原来用 `rpartition(":")` ✗ 而**名字本身带冒号**
      （`minecraft:oak_planks`✓★）⇒ ★切出来的是 `4118,70,-5:minecraft` ／ `oak_planks`✗★ ✓
      ★现象✗★：★`world` 有 211 条 ✗ 而按坐标去查**一条都查不到** ⇒ 快照写成**全 air**✗★ ✓
      ★更要命的✗★：★我那条自检"我数到 211 ＝ 回执说 solid=211"**照样过**✗★ ——
      ★因为只比了**条数** ✗ 没比**名字**✗★ ✓ ⇒ ★自检也要加"名字不许带冒号"这一条✓★
    """
    m = re.search(r"cells\[([^\]]*)\]", txt)
    if not m:
        return {}
    out = {}
    for part in m.group(1).split():
        if ":" not in part:
            continue
        # ★按**第一个**冒号切 ✗ 不是最后一个✗★
        pos, _, nm = part.partition(":")
        out[pos.strip()] = nm.strip()
    return out


def batch_scan(box, verbose=False):
    """★批量扫 ✗ 返回 ({"x,y,z": 名字}, 统计)✗★ —— ★空气**不列**（口径同 fixtures.snapshot✓★）"""
    txt, bad = _scan_raw(box, max_=1)
    if bad:
        raise RuntimeError("★第一次扫就失败了 ✗ 不做快照✗★")
    kinds = counts_of(txt)
    # ★★2026-10-03 加的一条核对✗★★：★`counts[…]` **自己也会被截断**✗★ ——
    #   ★现象✗★：★宽盒（41×21×51 ✗ 40+ 种）那次 ✗ 我数到 4120 格 ✗ 而回执说 `solid=4299`✗
    #     ★差 179 格 ✗ 真因是"★物种清单不全★" ✗ 不是"★我漏读格子★"✗★ ✓
    #   ⇒ ★口径✗★：★回执里 `kinds=N` 是**权威** ✗ 我解析出来的种数必须**等于**它 ✗
    #     不等就是**被截断** ⇒ **吵**（★不许当成"★就这几种★"✓★）✗★ ✓
    _kh = re.search(r"kinds=(\d+)", txt)
    if _kh and len(kinds) != int(_kh.group(1)):
        raise RuntimeError("★`counts` 被截断了 ✗ 解析出 %d 种 ✗ 回执说 kinds=%d ⇒ "
                           "★物种清单不全 ✗ 换小一点的盒子✗★" % (len(kinds), int(_kh.group(1))))
    stat = {"vol": None, "solid": None, "air": None, "kinds": len(kinds), "calls": 1}
    m = re.search(r"vol=(\d+) solid=(\d+) air=(\d+) kinds=(\d+)", txt)
    if m:
        stat.update({"vol": int(m.group(1)), "solid": int(m.group(2)),
                     "air": int(m.group(3)), "kinds": int(m.group(4))})
    world = {}
    for nm, _n in kinds:
        got = _cells_paged(box, nm, stat)
        if got is None:
            # ★★不许静默跳过✗★★（2026-10-03：第一版就是 `continue` ⇒ "我数到 0 格"却没人吭声）
            raise RuntimeError("★这一种取不回来 ✗ 不做快照✗★：%s" % nm)
        world.update(got)
        if verbose:
            print("     %-46s 格子 %d" % (nm, len(got)))
    # ★自检✗★：★我数到的非空气格数 必须**等于**回执自己说的 `solid`✗★
    if stat.get("solid") is not None and len(world) != stat["solid"]:
        raise RuntimeError("★自检不过 ✗ 我数到 %d 格 ✗ 回执说 solid=%d ⇒ 取数漏了✗★"
                           % (len(world), stat["solid"]))
    # ★★自检 2（2026-10-03 补 ✗ 上面那条"只数条数"曾经**放过了**全 air 的快照）✗★★
    #   ★每条名字都必须是"★命名空间:路径★"的形状 ✗ 键必须是"★三个整数★"✗★
    #   ★★注意（★自检当场教我的✗★）✗★★：★名字**会带方块状态**✗★ ——
    #     实测 `minecraft:grass_block,snowy=false` ✓
    #     还有 `minecraft:chest,facing=east,type=SINGLE,waterlogged=false` ✓
    #     ⇒ ★值里**有大写**（`SINGLE`✓★）✗ 而且属性**可以多个**✗ ⇒ 正则两边都要放✗★ ✓
    #     （★这就意味着"★物种★"和"★这一格的名字★"**不是一回事** ✗ 物种要切掉逗号那段✗★ ✓）
    bad_keys = [k for k in world if not re.match(r"^-?\d+,-?\d+,-?\d+$", k)]
    bad_names = [v for v in world.values()
                 if not re.match(r"^[a-z0-9_]+:[a-z0-9_/]+(,[a-z0-9_]+=[A-Za-z0-9_]+)*$", v)]
    if bad_keys or bad_names:
        raise RuntimeError("★自检不过 ✗ 键／名字形状不对 ✗ 键例 %s 名字例 %s✗★"
                           % (bad_keys[:2], bad_names[:2]))
    return world, stat, kinds


def _dshscan_raw(box, name: str, max_: int, page: int):
    """★发一条 `dshscan <盒> "名字" <max> <page>`✗★

    ★为什么自己发✗★：★中间层的 `t_scan` 把页号写死成 **1**✗★ ⇒ ★翻页只能自己发✗★ ✓
    （★语法是**引号位置参数** ✗ 我一开始手搓成 `match=` 被模组拒了 ✓ 见 §79.94✓★）
    """
    import mc_mcp as M
    cmd = ('dshscan %d %d %d %d %d %d "%s" %d %d'
           % (box[0], box[1], box[2], box[3], box[4], box[5], name, int(max_), int(page)))
    try:
        return str(M.dsh(cmd, 60.0) or "")
    except Exception as e:
        return "ERR:%s:%s" % (type(e).__name__, e)


def _cells_paged(box, name: str, stat: dict):
    """★把一种方块的所有格子取回来✗★ —— ★小页翻页 ＋ 见到"截断"就缩页✗★

    ★为什么小页✗★：★回执有**长度上限** ✗ 一页 125 格会被截断（★实测 ✓ 而且它末尾会写
      `…（截断 ✓ 原文 N 字 ✓）`✗★）⇒ ★看到"截断"就**不许**把这一页当好✗★ ✓
    ★缩到最小还截断 ⇒ ★如实失败**（返回 None ✗ 由调用方抛）✗ 不许凑一个残缺的快照✗★ ✓
    """
    out = {}
    max_ = 25
    page = 1
    pages = None
    while True:
        txt = _dshscan_raw(box, name, max_, page)
        stat["calls"] += 1
        if "截断" in txt:
            if max_ <= 6:
                # ★最小页还截断 ⇒ 这条路走不通 ✗ 说出来✗★
                return None
            max_ = max(6, max_ // 2)
            page = 1
            out = {}
            pages = None
            continue
        if "ERR:" in txt and not txt.startswith("dshscan"):
            return None
        got = cells_of(txt)
        out.update(got)
        m = re.search(r"page=(\d+)/(\d+)", txt)
        if not m:
            return None
        page, pages = int(m.group(1)), int(m.group(2))
        if page >= pages:
            break
        page += 1
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", required=True, help="x0,y0,z0,x1,y1,z1")
    ap.add_argument("--id", default="")
    ap.add_argument("--purpose", default="★校准网格：方块形状/归属判定的对照件✗★")
    ap.add_argument("--created-by", default="round7（任务书阶段 1 契约围栏）")
    ap.add_argument("--dry", action="store_true", help="★只看 ✗ 不登记 ✗ 不快照✗★")
    a = ap.parse_args(argv)

    x0, y0, z0, x1, y1, z1 = (int(v) for v in a.box.split(","))
    box = {"x0": x0, "y0": y0, "z0": z0, "x1": x1, "y1": y1, "z1": z1}
    print("== fixture_scan ✗ 盒 %s（★%d 格✗★）==" % (a.box, len(list(FX.cells_of(box)))))
    world, stat, kinds = batch_scan((x0, y0, z0, x1, y1, z1), verbose=True)
    print("  扫完：固体格 %s（★回执说的✗★）｜ 我数到 **%d** 格非空气 ｜ 调用 %d 次"
          % (stat.get("solid"), len(world), stat["calls"]))
    print("  种类 %d ⇒ 前 6：%s"
          % (stat["kinds"], "／".join("%s(%d)" % (k, n) for k, n in kinds[:6])))
    if a.dry:
        print("  ★--dry ⇒ 不登记 ✗ 不快照✗★ ✓")
        return 0
    if not a.id:
        print("★没有 --id ⇒ 不登记✗★")
        return 2

    # ★登记（★已存在 ⇒ 如实说 ✗ 不覆盖✗★）
    have = [f for f in FX.list_fixtures() if f.get("id") == a.id]
    if have:
        print("  清单里已经有 `%s` ⇒ ★不重复登记 ✗ 也不改它✗★" % a.id)
    else:
        FX.add_fixture(a.id, box, a.purpose, a.created_by)
        print("  已登记进清单 ✓（★%s✗★）" % FX.MANIFEST)

    # ★快照（★那一刻世界的样子 ✗ 含"该是空气"这件事 ✗ 见 fixtures.snapshot 的口径✓★）
    snap = {}
    for (x, y, z) in FX.cells_of(box):
        snap[FX.key(x, y, z)] = world.get(FX.key(x, y, z), "air")
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    sp = SNAP_DIR / ("%s.snapshot.json" % a.id)
    sp.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    named = sum(1 for v in snap.values() if v != "air")
    print("  快照已写 ✓ %s（★%d 格 ✗ 其中非空气 %d✓★）" % (sp, len(snap), named))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
