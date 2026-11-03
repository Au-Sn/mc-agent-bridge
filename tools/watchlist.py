#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchlist.py -- ★观察名单：**第五种状态** `contradicted`✗★（任务书 §4 ✓ 2026-10-03）

★它是干什么的✗★：★分歧里有**一小撮**两边都**信心十足但说法不同**的✗★ ——
  ★对它们 ✗ "★不知道★"是**错的说法**（★那是 `unknown`✓★）✗ "★挑一个★"是**禁止**的✗★ ✓
  ⇒ ★正确的做法是**隔离 ＋ 强制重读 ＋ 明确"★未裁决★"**✗ 而**这本账**就是那个状态✗★ ✓

★★判据（★写死 ✗ 违反即退回✗★）✗★★
  C1 ★必须写明**两条通道各说什么**✗★（★「★模型说 A ✗ 标签说 B✗★」 ✗ 不许只写"★有冲突★"✓★）
  C2 ★必须有**隔离理由**与**重读条件**✗★（★写清「★什么时候该回来看★」✗ 否则它会烂在表里✓★）
  C3 ★**不许静默解决**✗★：★一旦有人给了结论 ✗ 那次**状态变更**要留痕 ✗
     （★回到 `exception_table` ⇒ 这里要**关掉**并记下"★什么时候 ✗ 凭什么✗★"✓★）
  C4 ★名单**只能机械生成**✗★（★从冲突分析来 ✗ 不许手写 ✗ 手写就会变成"★我记得的清单★"✓★）
  C5 ★名单上的物种**不许**被自动声明✗★（★它还没裁决 ✓ `pick_semantic` 本来就不收冲突 ✓
     这里再**明确**一次 ✓★）

★存储✗★：★机器真相 `state/watch.json` ✗ 人看的那份 `docs/观察名单.md` 由它**生成**✗★ ✓
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STORE = ROOT / "state" / "watch.json"
DOC = ROOT / "docs" / "观察名单.md"
SCHEMA = "dshbridge/watch@1"


def validate(entry: dict) -> tuple:
    """★能不能进观察名单✗★ ⇒ `(ok, why)`（★C1／C2✗★）"""
    if not str(entry.get("species") or "").strip():
        return False, "★C0 缺物种✗★"
    if entry.get("state") != "contradicted":
        return False, "★C1 状态必须写死是 `contradicted`✗★"
    ch = entry.get("channels") or {}
    if not str(ch.get("model") or "").strip():
        return False, "★C1 要写**模型**那一侧说了什么✗★"
    if not (ch.get("tags") or []):
        return False, "★C1 要写**标签**那一侧说了什么✗★"
    if not str(entry.get("why_isolated") or "").strip():
        return False, "★C2 要有**隔离理由**✗★"
    if not str(entry.get("recheck") or "").strip():
        return False, "★C2 要有**重读条件**（★什么时候回来看✓★）✗★"
    return True, "✓"


def load(path: pathlib.Path = STORE) -> list:
    """★坏文件**不许**当成空名单✗★（★那会让"★未裁决★"看起来像"★没有★"✓★）"""
    if not path.is_file():
        return []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError("★观察名单坏了 ✗ 不静默当成空✗★：%s" % e)
    if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
        raise RuntimeError("★观察名单形状不对 ✗ 不静默当成空✗★")
    return d["entries"]


def save(entries: list, path: pathlib.Path = STORE) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": SCHEMA, "entries": entries},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def build(rows, recheck: str = "★导出到来 ⇒ 读碰撞形状重判；或有人给出逐条的世界证据 ⇒ 关掉本条✗★",
          reason: str = "★两条通道都**有结论**而结论不同 ✗ 而今天**没有**能裁决它的证据"
                        "（★碰撞形状拿不到 ✗ §79.103✓★）⇒ 隔离 ✗ 不许挑一个✗★") -> list:
    """★从冲突行**机械**生成名单✗★ ⇒ `rows` ＝ `[(物种, 模型族, [标签族…], 理由), …]`

    ★C4✗★：★只吃这些行 ✗ **不许**手写条目✗★ ✓
    """
    out = []
    for (sp, model_fam, tag_fams, why) in rows:
        e = {"species": sp, "state": "contradicted",
             "channels": {"model": model_fam, "tags": sorted(set(tag_fams))},
             "why_isolated": "%s（★%s✓★）" % (reason, why),
             "recheck": recheck,
             "since": time.strftime("%Y-%m-%d")}
        ok, w = validate(e)
        if ok:
            out.append(e)
        else:
            raise RuntimeError("★机械生成的条目**没过自己的判据**✗★：%s ⇒ %s" % (sp, w))
    return out


def is_watched(species: str, path: pathlib.Path = STORE) -> bool:
    return any(e.get("species") == species for e in load(path))


def render(entries=None, path: pathlib.Path = DOC) -> pathlib.Path:
    entries = entries if entries is not None else load()
    lines = ["# 观察名单（★生成物 ✗ 别手改 ✗ 改 `state/watch.json`✓★）", "",
             # ★D4（★§79.238✗★）：原来这里是「生成时间 %H:%M:%S」✗★ ——
             #   ★每秒都变 ⇒ 哈希比对永远不相等 ⇒ 每跑一次就脏一次✗★ ✓
             #   ★改成从**条目自己**取最早那条的"起于" ✗ 内容只随数据变✗★ ✓
             "> 工具 `tools/watchlist.py` ｜ 条目 **%d** ｜ 最早起于 %s"
             % (len(entries), min([str(e.get("since") or "") for e in entries] or ["-"])), "",
             "★这是什么✗★：★**第五种状态** `contradicted`✗★ —— ★两条通道都**有结论**而结论不同 ✗"
             "而今天**没有**能裁决它的证据✗★ ✓",
             "★它**不是** `unknown`✗★（★那是「★没人说话★」✓★）✗ ★也**不是**「★待办★」✗★"
             "（★它**明确未裁决** ✗ 谁都不许拿它当依据✓★）", "",
             "| 物种 | 模型说 | 标签说 | 隔离理由 | 重读条件 | 起于 |",
             "|---|---|---|---|---|---|"]
    for e in entries:
        ch = e.get("channels") or {}
        lines.append("| `%s` | %s | %s | %s | %s | %s |"
                     % (e.get("species"), ch.get("model"),
                        "／".join(ch.get("tags") or []),
                        str(e.get("why_isolated"))[:60], str(e.get("recheck"))[:50],
                        e.get("since", "-")))
    if not entries:
        lines.append("| ★（空 ✗ 而「空」的意思要说清：★今天没有任何**已知**的未裁决项✓★） | | | | | |")
    lines += ["", "★纪律✗★：★名单上的物种**不许**被自动声明 ✗ 也**不许**被当成「一致」✗★"
              "（★它**未裁决** ✗ 任何依据都不成立✓★）✓"]
    # ★D4（★§79.238✗★）：写盘走"内容没变就不写"✗★
    import docwrite as _DW
    _DW.write_if_changed(path, "\n".join(lines) + "\n")
    return path


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="★从冲突分析机械重建名单✗★")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args(argv)
    if a.build:
        import divergence as DV
        import mapread as MR
        import tag_census as TC
        jars, vanilla, roots = TC.sources_of(None)
        src, _u, _s = TC.scan(jars, roots, want_universe=False)
        vsrc, _v, _vs = TC.scan(vanilla, [], want_universe=False)
        full = TC.closure(*TC.build(src + vsrc))
        from_tag = TC.invert(full)
        ft = TC.family_tags(full)
        rows = []
        for sp in sorted(from_tag):
            fams = [f for f, ids in ft.items()
                    if any(t in ids for t in (from_tag.get(sp) or ()))]
            got = sorted({DV.TAG_FAMILY[f] for f in fams if f in DV.TAG_FAMILY})
            if len(got) > 1:
                rows.append((sp, MR.shape(sp), got,
                             "★标签侧自相冲突✗★：%s" % "／".join(
                                 sorted(f for f in fams if f in DV.TAG_FAMILY))))
        entries = build(rows)
        save(entries)
        print("★观察名单已重建✗★：%d 条 ⇒ %s" % (len(entries), STORE))
    print("★观察名单✗★：%d 条" % len(load()))
    for e in load()[:8]:
        ch = e.get("channels") or {}
        print("   %-42s 模型 %-8s 标签 %s" % (e.get("species"), ch.get("model"),
                                              "／".join(ch.get("tags") or [])))
    if a.render:
        print("已生成 %s ✓" % render().name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
