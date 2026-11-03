#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""declare_collision.py -- ★物理裁决器：拿碰撞导出**逐条判**那 1716 条决策级分歧✗★

★它是什么✗★：★决策级分歧（★"★挡人／能站★"真的翻了✓★）每一条都要 `collision` 证据 ✗
  而"★碰撞证据★"就是 `/dshkb` 的导出✗★ ⇒ ★这个工具把它**接上**✗★ ✓

★★三条纪律（★写死 ✗ 违反即退回✗★）✗★★
  ① ★只写**碰撞槽**✗★ ⇒ ★永远不动那 91 条语义族（★两槽拆分保证 ✓ §79.113✓★）
  ② ★导出**没覆盖**的物种 ⇒ **不猜**✗★（★计入"★导出没覆盖★" ✗ 不许退化成名字兜底✓★）
  ③ ★导出说 `canopy` ⇒ **拒**✗★（★树冠是语义 ✗ 碰撞看不出 ⇒ 混进来就破铁律 1✓★）

★它**不**做什么✗★：★不改判定代码 ✗ 不碰语义槽 ✗ 不在导出缺失时"★就当作没事★"✗★ ✓
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EXPORT = ROOT / "logs" / "blockkb.json"


def read_export(path: pathlib.Path = EXPORT) -> dict:
    """★读导出✗★ —— ★不在／读不动 ⇒ **抛**✗★（★不许"★那就没得判★"地滑过去✓★）"""
    if not path.is_file():
        raise RuntimeError("★导出不在✗★：%s（★先让 `/dshkb` 跑一次 ✓ 别当成空✓★）" % path)
    d = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(d, dict) or not isinstance(d.get("blocks"), dict):
        raise RuntimeError("★导出形状不对 ✗ 不静默当空✗★：%s" % path)
    # ★★防呆✗★★：★schema 不对就**拒**✗★ —— ★免得把合成／别处的 JSON 当成真导出 ✗
    #   （★这是"★不许把假数据当真数据★"的机械形态 ✗ 见 §79.115✓★）
    if d.get("schema") != "dshbridge/registry_blocks@1":
        raise RuntimeError("★schema 不对 ✗ 不当成真导出✗★：%r（★要 `dshbridge/registry_blocks@1`✓★）"
                           % d.get("schema"))
    return d


def adjudicate(rows, export: dict, kb) -> dict:
    """★逐条判✗★ ⇒ `{declared, agreed, not_covered, refused, why}`

    ★输入✗★：`rows` ＝ `[(物种, 黑名单族, 标签族, 级别文字), …]`（★决策级那批✓★）
    ★返回里每一类都**有数**✗★（★这就是"★一条都不许没声明★"的机械形态✓★）
    """
    blocks = (export or {}).get("blocks") or {}
    out = {"declared": 0, "agreed": 0, "not_covered": 0, "refused": 0, "why": {},
           "examples": {"declared": [], "refused": []}}

    def bump(k):
        out["why"][k] = out["why"].get(k, 0) + 1

    for (sp, black, _exp, lvl) in rows:
        lv = str(lvl or "")
        if not lv.startswith("★★决策级"):
            continue                       # ★只管决策级 ✗ 其余交给别的工具✗★
        ent = blocks.get(sp)
        if ent is None:
            out["not_covered"] += 1
            bump("★导出没覆盖✗★")
            continue
        fam, why = kb.family_from_export(ent if isinstance(ent, dict) else {})
        if not fam:
            out["refused"] += 1
            bump("★导出给的不合用 ✗ %s★" % why)
            if len(out["examples"]["refused"]) < 5:
                out["examples"]["refused"].append((sp, why))
            continue
        # ★★两条判定都要比✗★★（2026-10-04 修的真漏洞 ✓）
        #   ★现象✗★：★原来只比 `blocks_space` ✗ 于是 **"★只差 `is_floor`★" 那一类**被算成
        #     "★导出支持黑名单★"✗★ —— ★实测 `mcwdoors` 有 **201** 条（★门被名字判成 `fence`
        #     ⇒ `is_floor=False` ✗ 而关着的门顶面 1.0 ⇒ **能站** ✓ 碰撞侧对✓★）✗★ ✓
        #   ★⇒ 口径✗★：★两条判定**任一**不同 ⇒ 就是**真的改了决策** ⇒ **必须声明**✗★ ✓
        _same = (kb.blocks_space_fam(fam) == kb.blocks_space_fam(black)
                 and kb.is_floor_fam(fam) == kb.is_floor_fam(black))
        if _same:
            out["agreed"] += 1
            bump("★导出与黑名单在**两条判定**上都一致✗★")
            continue
        # ★真的翻了 ⇒ 写**碰撞槽**（★等级 collision ✗ 出处写到条目与高度✓★）
        ok = kb.put(sp, fam, "collision",
                    "dshkb:%s 物种=%s 族=%s max_height=%s（★几何 ⇒ 物理真值✓★）"
                    % (export.get("schema"), sp, ent.get("family"), ent.get("max_height")))
        if ok:
            out["declared"] += 1
            bump("★已声明（★碰撞证据✓★）✗★")
            if len(out["examples"]["declared"]) < 5:
                out["examples"]["declared"].append((sp, black, fam))
        else:
            out["refused"] += 1
            bump("★被 put 拒（★升级语义／等级条款✓★）")
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--export", default="")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--top", type=int, default=6)
    a = ap.parse_args(argv)

    import blockkb as kb
    import declare_semantic as DS
    rows = DS.rows_all()
    import kb_export as KX
    path = KX.find_export(a.export)
    try:
        export = read_export(path)
    except Exception as e:
        print("INCONCLUSIVE: %s: %s" % (type(e).__name__, e))
        return 4
    print("== declare_collision ✗ 分歧 %d 条 ｜ 导出 %s（★count=%s ✗ errors=%s✓★）=="
          % (len(rows), path.name, export.get("count"), export.get("errors")))
    # ★★2026-10-13（★§79.267 预演抓的**安全缺口**✗★）✗★★：
    #   ★现象✗★：★`--dry` 在 `adjudicate` **之前**就返回 ✗ 于是它**只印一句
    #     "★--dry ⇒ 只报数 ✗ 不写表★"** ✗★ ⇒ ★★"★先看计划再决定写不写★"**做不到**✗★★ ✓
    #   ★（★而真导出到的那一次是**一次性窗口** ✗ 到那时才发现就晚了✓★）✗★ ✓
    #   ★修法✗★：★计划**照算照印** ✗ 只是**不落盘**✗ ——
    #     ★`adjudicate` 只写**内存里的 KB**（★`kb.PHYS`✗★）✗ **不动例外表**✓★ ✓
    kb.SOURCE = "table"
    r = adjudicate(rows, export, kb)
    print("  已声明 **%d** ｜ 导出支持黑名单 %d ｜ ★导出没覆盖 %d✗★ ｜ 拒 %d"
          % (r["declared"], r["agreed"], r["not_covered"], r["refused"]))
    for k, v in sorted(r["why"].items(), key=lambda kv: -kv[1]):
        print("     %-52s %d" % (k, v))
    for (sp, black, fam) in r["examples"]["declared"][:a.top]:
        print("     ★声明✗★ %-44s 黑名单 %-8s ⇒ 碰撞 %-8s" % (sp, black, fam))
    for (sp, why) in r["examples"]["refused"][:a.top]:
        print("     ★拒✗★   %-44s %s" % (sp, why[:50]))
    if a.dry:
        print("  ★--dry ⇒ 计划在上面 ✗ **没写表**★（★真表哈希请自行复核✓★）")
        return 0
    if a.apply:
        import exception_table as ET
        # ★把碰撞槽里**真的**进来的那些也记进例外表（★出处＝导出✗★）—— ★只记物理主张✗★
        n = 0
        fails = []
        for sp, e in list(kb.PHYS.items()):
            ok, _w = ET.add({"species": sp, "claim": "blocks_space",
                             "verdict": bool(kb.blocks_space(sp)), "evidence": "collision",
                             "source": "★`/dshkb` 导出（★%s✗★）✗ 族 %s ⇒ 物理真值"
                                       % (export.get("schema"), e["fam"]),
                             "by": "★自动：`declare_collision`（★§79.115✗★）"})
            if ok:
                n += 1
            else:
                # ★★不许静默跳过✗★★（2026-10-04 修：★第一版只数成功的 ✗ 于是
                #   "★声明了 1118 ✗ 表里只多 580★"这件事**没人吭声**✗★ ✓）
                fails.append((sp, str(_w)[:70]))
        if fails:
            print("  ★被拒 %d 条 ✗ 前 5 条理由✗★：" % len(fails))
            for (sp, w) in fails[:5]:
                print("     %-44s %s" % (sp, w))
        print("  例外表新增 %d 条（★全是物理主张 ＋ collision 证据✓★）｜ 表里 %d 条"
              % (n, len(ET.load())))
        print("  已重生成 %s ✓" % ET.render().name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
