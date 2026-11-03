#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mod_contract.py -- ★契约围栏：把**模组现在的判定**锁住★（用户 ①补 ✗ 任务书阶段 1）

★契约的角色（★按 ①补 改过✗★）✗★：★不是"对齐双实现" ✗ 而是
  ★**守卫未来对模组判定逻辑的任何改动**✗★ ✓
  ⇒ 所以它比的是"★模组**今天**给出什么★" ✗ 不是"★我认为它应该给什么★"✗★ ✓
  ⇒ ★任何一格名字变了 ✗ 任何一个计数器变了 ✗ 地图上任何一个字母变了 ✗ 都算"★模组逻辑动过★"✗★ ✓

★锁什么✗★
  ① ★与站位无关那一半✗★：盒级计数器（`vol`／`solid`／`air`／`kinds` ✓ `solid` 是模组的**物理读数**✓★）
     ＋ 逐种计数 ＋ 逐格物种（★名字切掉方块状态 ✗ 见 §79.97✓★）
  ② ★与站位有关那一半（2026-10-03 第二轮加✗★）✗★：★`/dshmap <radius>` 的**地图原文**✗★ ——
     ★它相对**假人位置**✗★ ⇒ ★契约里必须**一并记下站位** ✗ 复核时先回去站好 ✗
     站不回去（★或站好之后被打断✓★）⇒ ★**测不了** ✗ 不许拿别处的图比✗★ ✓

★站位怎么定（★不许猜 ✗ 从**快照**里算✓★）★：★找一个"★脚下实心 ＋ 脚／头两格都是空气★"的格子 ✗
  且尽量靠近盒子中心（★这样地图能罩住整片夹具✓★）✗★ ✓
★站位怎么去（★不许"★我发过 tp 了★"✓★）✗★：★`tp` 之后**当场回读** `dshdigest` ✗
  偏一点就**重来** ✗ 重来还不行 ⇒ **测不了**（★常驻脑会把人遛走 ✗ 这是真的 ✓★）✓
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CONTRACT_DIR = ROOT / "state" / "contracts"
MAP_RADIUS = 8          # ★`/dshmap` 最大 32 ✗ 8 给的是 17×17 一片 ✗ 够罩住 13×13 的夹具✓★


def species_of(name: str) -> str:
    """★"★这一格的名字★" ⇒ "★物种★"✗★ —— ★切掉 `,属性=值` 那一段✗★（§79.97）"""
    return (name or "air").split(",", 1)[0]


# ── ★站位（★纯函数 ✗ 好离线判✓★）──────────────────────────────────────────────
def stance_for(snap: dict, box: dict, keyfn=None):
    """★从快照里算出该站哪一格✗★ ⇒ `(x, y, z, why)`

    ★判据✗★：① 脚下那格**实心**（★快照说不是 air✓★）② 脚那格 air ③ 头那格 air
      ★排序✗★：★离盒子中心**近**的优先✗★（★这样 `/dshmap` 罩得住整片✓★）
    ★算不出来 ⇒ 返回 `None` ＋ 原因 ✗ 不许瞎给一个✗★ ✓
    """
    if keyfn is None:
        keyfn = lambda x, y, z: "%d,%d,%d" % (x, y, z)  # noqa: E731
    cx = (box["x0"] + box["x1"]) / 2.0
    cz = (box["z0"] + box["z1"]) / 2.0
    cands = []
    for y in range(box["y0"], box["y1"] + 1):
        for x in range(box["x0"], box["x1"] + 1):
            for z in range(box["z0"], box["z1"] + 1):
                below = snap.get(keyfn(x, y - 1, z))
                feet = snap.get(keyfn(x, y, z))
                head = snap.get(keyfn(x, y + 1, z))
                if below is None or below == "air":
                    continue
                if feet != "air" or head != "air":
                    continue
                cands.append((abs(x - cx) + abs(z - cz), x, y, z))
    if not cands:
        return None, "★快照里找不到「脚下实心 ＋ 脚头两格空气」的格子 ✗ 站不了✗★"
    cands.sort()
    _d, x, y, z = cands[0]
    return (x, y, z), "★离中心最近的一个（★偏 %s 格✓★）" % cands[0][0]


# ── ★与世界打交道的那几件✗★ ────────────────────────────────────────────────────
def _bot_pos(tries=6):
    """★问服务器要**假人**的真实坐标 ✗ 读不到回 None ✗ 不许猜✗★"""
    import mc_mcp as M
    for _ in range(tries):
        try:
            t = str(M.dsh("dshdigest 4", 40.0) or "")
        except Exception:
            t = ""
        m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", t)
        if m:
            return float(m.group(1)), float(m.group(2)), float(m.group(3))
    return None


def goto_stance(x, y, z, tol=0.35, tries=5):
    """★站到那一格 ✗ 并且**当场回读**✗★ —— ★对不上就重来 ✗ 还不行 ⇒ 测不了✗★"""
    import mc_mcp as M
    want = (x + 0.5, float(y), z + 0.5)
    last = None
    for i in range(tries):
        try:
            M.dsh("tp Bot %.2f %.2f %.2f" % want, 40.0)
        except Exception as e:
            return None, "★tp 失败✗★ %s" % type(e).__name__
        time.sleep(0.35)
        cur = _bot_pos()
        if cur is None:
            return None, "★回读不到坐标✗★"
        last = cur
        if (abs(cur[0] - want[0]) <= tol and abs(cur[1] - want[1]) <= tol
                and abs(cur[2] - want[2]) <= tol):
            return cur, ""
    return None, ("★站不回去✗★（★要走 %s ✗ 实到 %s ⇒ 多半是**常驻脑**在走✓★）"
                  % (want, last))


def capture_map(radius=MAP_RADIUS):
    """★抓 `/dshmap` 的**原文**✗★（★它相对假人位置 ✗ 所以调用方必须先站好✗★）"""
    import mc_mcp as M
    try:
        t = str(M.dsh("dshmap %d" % int(radius), 90.0) or "")
    except Exception as e:
        return None, "★dshmap 失败✗★ %s" % type(e).__name__
    if "dshmap" not in t:
        return None, "★回执里没有 dshmap ✗ 读不到✗★"
    return t.strip(), ""


# ── ★抓 / 比 / 存✗★ ───────────────────────────────────────────────────────────
def capture(fixture_id: str, verbose: bool = False, with_map: bool = True) -> dict:
    """★抓一份契约✗★ —— ★全部来自**模组回执** ✗ 不经过我的名字分类器✗★"""
    import fixture_scan as FS
    import fixtures as FX
    have = [f for f in FX.list_fixtures() if f.get("id") == fixture_id]
    if not have:
        raise RuntimeError("★清单里没有 `%s`✗★" % fixture_id)
    box = have[0]["box"]
    world, stat, kinds = FS.batch_scan((box["x0"], box["y0"], box["z0"],
                                        box["x1"], box["y1"], box["z1"]), verbose=verbose)
    c = {
        "fixture": fixture_id,
        "box": box,
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "counters": {k: stat.get(k) for k in ("vol", "solid", "air", "kinds")},
        "counts": {k: v for k, v in kinds},
        "species_per_cell": {k: species_of(v) for k, v in world.items()},
    }
    if not with_map:
        return c
    # ★站位 ＝ 从**快照**里算 ✗ 不是从世界现猜✓★
    snap = {}
    for (x, y, z) in FX.cells_of(box):
        snap[FX.key(x, y, z)] = world.get(FX.key(x, y, z), "air")
    st, why = stance_for(snap, box, keyfn=FX.key)
    if st is None:
        c["map"] = {"ok": False, "why": why}
        return c
    pos, _w2 = goto_stance(*st)
    if pos is None:
        c["map"] = {"ok": False, "why": _w2, "stance": list(st)}
        return c
    raw, err = capture_map()
    if raw is None:
        c["map"] = {"ok": False, "why": err, "stance": list(st)}
        return c
    c["map"] = {"ok": True, "stance": list(st), "radius": MAP_RADIUS,
                "got": [round(v, 2) for v in pos], "raw": raw}
    return c


def diff_contract(old: dict, new: dict) -> list:
    """★两份契约的差异✗★ ⇒ ★逐条列清 ✗ 空列表 ＝ 一致✗★（★纯函数 ✗ 好离线判✓★）"""
    out = []
    for k in ("vol", "solid", "air", "kinds"):
        a = (old.get("counters") or {}).get(k)
        b = (new.get("counters") or {}).get(k)
        if a != b:
            out.append("★计数器 %s：%s ⇒ %s✗★" % (k, a, b))
    ca, cb = old.get("counts") or {}, new.get("counts") or {}
    for name in sorted(set(ca) | set(cb)):
        if ca.get(name) != cb.get(name):
            out.append("★逐种计数 %s：%s ⇒ %s✗★" % (name, ca.get(name), cb.get(name)))
    sa, sb = old.get("species_per_cell") or {}, new.get("species_per_cell") or {}
    for cell in sorted(set(sa) | set(sb)):
        if sa.get(cell) != sb.get(cell):
            out.append("★格子 %s：%s ⇒ %s✗★" % (cell, sa.get(cell), sb.get(cell)))
    # ★地图那一半（★只在两边都成功时比 ✗ 一边失败 ⇒ 让调用方判"测不了"✓★）
    ma, mb = old.get("map") or {}, new.get("map") or {}
    if ma.get("ok") and mb.get("ok"):
        if ma.get("raw") != mb.get("raw"):
            la = (ma.get("raw") or "").splitlines()
            lb = (mb.get("raw") or "").splitlines()
            out.append("★地图原文变了（★站位 %s ⇒ %s ✗ 行数 %d ⇒ %d✓★）"
                       % (ma.get("stance"), mb.get("stance"), len(la), len(lb)))
            for i in range(max(len(la), len(lb))):
                x = la[i] if i < len(la) else "（没有）"
                y = lb[i] if i < len(lb) else "（没有）"
                if x != y:
                    out.append("   ★第 %d 行：%s ⇒ %s✗★" % (i + 1, x[:60], y[:60]))
                    break
    if len(out) > 40:
        out = out[:40] + ["★（还有 %d 条没列 ✗ 太多 ⇒ 多半是整片被改过✗★）" % (len(out) - 40)]
    return out


def path_of(fixture_id: str) -> pathlib.Path:
    return CONTRACT_DIR / ("%s.json" % fixture_id)


def save(c: dict, fixture_id: str) -> pathlib.Path:
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    p = path_of(fixture_id)
    p.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def load(fixture_id: str):
    p = path_of(fixture_id)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def check(fixture_id: str) -> int:
    """★复核✗★ ⇒ 0 一致 ／ 1 有差异（★打印差异✗★）／ 4 **测不了**（★契约或夹具不在✓★）

    ★★"测不了"必须带字面 `INCONCLUSIVE`✗★★（★闸门口径 ✗ 否则会被当成**硬失败** ＝ 乱叫✓★）
    """
    old = load(fixture_id)
    if old is None:
        print("INCONCLUSIVE: ★契约不在 ⇒ **测不了**✗★（★先 `--capture` ✗ 别当通过✓★）")
        return 4
    try:
        new = capture(fixture_id)
    except Exception as e:
        print("INCONCLUSIVE: ★抓不到（★世界／夹具不在✓★）⇒ **测不了**✗★：%s: %s"
              % (type(e).__name__, e))
        return 4
    mb = new.get("map") or {}
    if (old.get("map") or {}).get("ok") and not mb.get("ok"):
        print("INCONCLUSIVE: ★地图那一半这次抓不到 ⇒ **测不了**✗★（★%s✗★）"
              % mb.get("why", "?"))
        return 4
    d = diff_contract(old, new)
    if not d:
        print("=> ★契约一致✗★（★%d 格 ✗ %d 种 ✗ 计数器 %s ✗ 地图 %s✓★）"
              % (len(old.get("species_per_cell") or {}), len(old.get("counts") or {}),
                 old.get("counters"),
                 "✓" if (old.get("map") or {}).get("ok") else "★没锁✗★"))
        return 0
    print("=> ★契约**不一致**✗★（★模组逻辑动过 ✗ 或世界被动过✓★）：")
    for ln in d:
        print("   %s" % ln)
    return 1


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="calib_v1")
    ap.add_argument("--capture", action="store_true", help="★抓一份新契约（★会覆盖旧的✗★）")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-map", action="store_true", help="★只抓与站位无关那半✗★")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.capture:
        c = capture(a.id, verbose=a.verbose, with_map=not a.no_map)
        p = save(c, a.id)
        m = c.get("map") or {}
        print("★契约已写✗★ %s（★%d 格 ✗ %d 种 ✗ 计数器 %s ✗ 地图 %s✓★）"
              % (p, len(c["species_per_cell"]), len(c["counts"]), c["counters"],
                 ("✓ 站 %s" % (m.get("stance"),)) if m.get("ok")
                 else ("★没抓到✗★ %s" % m.get("why"))))
        return 0
    return check(a.id)


if __name__ == "__main__":
    # ★★2026-10-13（★§79.269 预演抓的**真 bug**✗★）✗★★：★这里**原来**还兼着
    #   `--export-fence` 那条分支 ✗ 而 `export_fence` **定义在本文件末尾**✗★ ⇒
    #   ★★Python 从上往下执行 ⇒ 调用时那个名字**还不存在**✗★ ⇒
    #     `NameError: name 'export_fence' is not defined`✗★★ ✓
    #   ★真身✗★：★是我 §79.228 把"★导出那一半★"**追加到文件末尾** ✗ 而 `__main__` 块在**中间**✗★ ✓
    #   ★⇒ 那条分支**搬到文件末尾**（★紧接定义之后✗★）✗ 这里只管夹具那一半✗★ ✓
    #   ★★但**只搬不够**✗★★：★这个块在文件**中间** ✗ 它一 `sys.exit` ⇒ 末尾那个块
    #     **永远到不了**✗★ ⇒ 实测报 `unrecognized arguments: --export-fence`✗★ ✓
    #   ★⇒ 见到 `--export-fence` **不要退** ✗ 把活留给末尾（★那里名字才可见✓★）✗★ ✓
    if "--export-fence" not in sys.argv:
        sys.exit(main(sys.argv[1:]))

# ##########################################################################
# ★★导出那一半✗★★（★2026-10-13 ✗ 用户裁决 B1③／B2✗★）
#   ★用户原话✗★：★"★`mod_contract` 接上导出（★任务书 V1 原话 ✗ 现在从不引用导出✓★）★"✗★ ✓
#   ★它在整条线里的位置✗★：★契约**两件**✗★ ——
#     · ★回归围栏✗★（★本文件上面那一半 ✗ 跟"★昨天捕获的夹具★"比 ✗ **记账**✓★）✗★ ✓
#     · ★真值契约✗★（★`state/contracts/truth_v1.json` ✗ 期望只许来自**物理实测**✗ **验收**✓★）✗★ ✓
#   ★这一半问的是✗★：★模组的**注册表导出**变了没有✗★（★`family`／`max_height` 是模组的物理读数✗★）✗★ ✓
#   ★口径✗★：★第一次跑 ⇒ **记账**（★记下 schema／mod_version／count／摘要✓★）✗
#     ★以后跑 ⇒ 比 ✗ 不一样就**红**✗ 而且要**点名**是哪些物种变了✗★ ✓
#   ★缺导出 ⇒ ★走 `export_guard` ✗ 硬红 ＋ 一句人话✗★（★不许裸抛✓★）✗★ ✓
# ##########################################################################
FENCE = ROOT / "state" / "contracts" / "export_fence.json"


def export_fence(path=None, record=False, fence_path=None):
    """★导出那一半的围栏✗★ ⇒ `(ok, 说明)`"""
    import export_guard as EG
    fp = pathlib.Path(fence_path) if fence_path else FENCE
    p = EG.require("mod_contract.export_fence")
    d = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    blocks = d.get("blocks") or {}
    body = json.dumps(blocks, ensure_ascii=False, sort_keys=True)
    now = {"schema": d.get("schema"), "mod_version": d.get("mod_version"),
           "count": d.get("count"), "blocks_sha256_12": hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]}
    if record or not fp.is_file():
        fp.parent.mkdir(parents=True, exist_ok=True)
        now["recorded_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now["sample"] = {k: blocks[k] for k in sorted(blocks)[:8]}
        fp.write_text(json.dumps(now, ensure_ascii=False, indent=1), encoding="utf-8")
        return True, "★第一次跑 ⇒ 已记账✗★：%s（%s／%s ✗ %s 个方块）" % (
            fp.name, now["mod_version"], now["schema"], now["count"])
    old = json.loads(fp.read_text(encoding="utf-8"))
    diffs = [k for k in ("schema", "mod_version", "count", "blocks_sha256_12")
             if old.get(k) != now.get(k)]
    if not diffs:
        return True, "★与记账一致✗★（%s ✗ %s 个方块 ✗ 摘要 %s）" % (
            now["mod_version"], now["count"], now["blocks_sha256_12"])
    return False, ("★模组的**导出**动过了✗★：变了 %s ⇒ 记账 %s ⇒ 现在 %s"
                   % ("／".join(diffs), old.get("blocks_sha256_12"), now["blocks_sha256_12"]))


# ★★文件末尾的入口✗★★（★`export_fence` 刚在上面定义好 ✗ 所以这里看得见它✓★）
if __name__ == "__main__" and "--export-fence" in sys.argv:
    _ok, _why = export_fence(record=("--record" in sys.argv))
    print("%s %s" % ("★PASS★" if _ok else "★FAIL★", _why))
    sys.exit(0 if _ok else 1)
