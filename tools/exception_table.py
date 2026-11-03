#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exception_table.py -- ★例外表：**只吃"已声明证据"**★（任务书阶段 3 ✗ U1 口径的落点）

★它是什么✗★：★阶段 3 分歧清单里那些"★不一致★"的最终归宿 ✗
  每条 = ★{物种 ✗ 主张 ✗ 结论 ✗ 证据种类 ✗ 证据出处 ✗ 声明人 ✗ 日期}✗★ ✓
★它**不是**什么✗★：★不是"★我写一张更大的名字表★"✗★ —— ★它是**证据的账本**✗
  每条都要能回答"★凭什么★"✗ 答不出来的一律**拒收**✗★ ✓

★★一条最要紧的拒收规则（★铁律 1 的机械形态✗★）✗★★
  ★"★**主张**是**物理**的（`blocks_space` ／ `is_floor`）⇒ ★证据**不许**是**标签**✗★★
  ★因为标签只管**归属语义** ✗ 它说"★这是半砖★" ✗ **推不出**"★它挡人★"✗★ ✓
  （★这条不写成代码 ✗ 表就会被"★标签说是半砖所以它能站★"这类话灌满✗★）

★主张（claim）与证据种类（evidence）都**写死**✗★：
  claim    ：`blocks_space`（★物理✗★）／ `is_floor`（★物理✗★）／ `family`（★语义✗★）
  evidence ：`collision`（★最硬 ✗ 模组读碰撞箱✓★）＞ `experiment`（★世界里的物理实验✓★）
             ＞ `registry`（★标签 ✗ **只够**语义✓★）＞ `name_fallback`（★名字兜底 ✗ 必须 TEMPORARY✓★）

★存储✗★：★机器真相在 `state/exceptions.json` ✗ 人看的那份由它**生成**✗★
  （★口径同台账：★不许两份手写✗★ ✓）
"""
from __future__ import annotations

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

STORE = ROOT / "state" / "exceptions.json"
DOC = ROOT / "docs" / "例外表.md"

# ★主张：哪些是**物理**的（★标签证据对它们一律无效✗★）
PHYS_CLAIMS = ("blocks_space", "is_floor")
SEM_CLAIMS = ("family",)
# ★证据等级（★越硬越靠前 ✗ 与登记册第 4 条同一顺序✓★）
# ★★2026-10-13（★用户裁决 A4✗★）✗★★：★拆**两条不相交的梯子**✗★ ✓
#   ★用户原话✗★：★"★物理梯 `collision > 物理实验` ✗ 语义梯 `registry > 实验 > 名字兜底`✗★；
#     ★注册表在语义上是权威 ✗ **在物理上永远不许压过"亲手摸过"**✗★
#     （★原代码 `collision>registry>experiment>name_fallback` 是把两条轴混成一条
#      ＝ §11 想堵的那道**侧门**✓★）★"✗★ ✓
#   ★为什么必须拆✗★：★同一条梯上"★谁比谁硬★"要有**共同尺度**✗★ ——
#     ★而"★标签说它是半砖★"与"★我摸到它 0.5 高★"**根本不是一种话**✗★ ⇒
#     ★混着排 ✗ 就会出现"★标签压过实测★"那种事✗★ ✓
EVIDENCE_PHYS = ("collision", "experiment")
"""★物理梯✗★：★`collision`（★亲手摸到的碰撞✓★）最硬 ✗ `experiment`（★物理实验✓★）次之✗★
★而 **`registry` 根本不在这条梯上**✗★ —— ★这就是"★永远不许压过★"的机械形态✗★ ✓"""
EVIDENCE_SEM = ("registry", "experiment", "name_fallback")
"""★语义梯✗★：★`registry`（★模组作者声明的归属✗★）最硬 ✗ 实验次之 ✗ 名字兜底最软✗★ ✓"""
# ★并集（★兼容旧调用✗★）✗ 但**升级比较**必须在**同一条梯**内做✗★ ✓
EVIDENCE = tuple(dict.fromkeys(EVIDENCE_PHYS + EVIDENCE_SEM))
# ★家族闭集（★与 `mapread.shape()` 一致 ✗ 见 §79.100✓★）
FAMILIES = ("full", "slab", "fence", "machine", "canopy", "pass", "air", "liquid", "other")


def validate(entry: dict) -> tuple:
    """★一条例外能不能收✗★ ⇒ `(ok, why)`

    ★★拒收规则（★先写死 ✗ 判据照这条走✓★）✗★★
      R1 ★物种 ／ 主张 ／ 结论 ／ 证据种类 ／ 证据出处 ／ 声明人 ✗ 缺一个就拒✗★
      R2 ★主张不在册 ⇒ 拒✗★
      R3 ★★★主张是物理的 ⇒ 证据**不许**是 `registry`（标签）✗★★★（★铁律 1✓★）
      R4 ★结论的形状要对✗★：物理主张 ⇒ `True`／`False` ✗ `family` ⇒ 在闭集里✗★
      R5 ★`name_fallback` ⇒ 必须带 `TEMPORARY` ＋ `复核触发`✗★（★登记册第 4 条✓★）
      R6 ★证据出处**必须**写清"★在哪 ✗ 什么时候 ✗ 怎么读的★" ✗ 空话拒收✗★
         （★"★反正就是★"这种 ✗ 一律不算出处✓★）
    """
    for k in ("species", "claim", "evidence", "source", "by"):
        if not str(entry.get(k) or "").strip():
            return False, "★R1 缺字段✗★：%s" % k
    # ★★`verdict` 单独判 ✗ 因为 `False` 是**合法结论**✗★★（2026-10-04 修的真错 ✓）
    #   ★现象✗★：★原来它和别的字段共用"★取出来是不是空★"那条 ✗ 于是 **`False` 被当成"★没写★"**✗★ ⇒
    #     ★实测：★`blocks_space=True` 的 580 条进了表 ✗ 而 **`False` 的 538 条被无声丢掉**✗★ ✓
    #   ★⇒ 口径✗★：★"★有没有这个字段★"要看**它在不在** ✗ 不看它"★像不像空★"✗★ ✓
    if "verdict" not in entry or entry.get("verdict") is None:
        return False, "★R1 缺字段✗★：verdict（★`False` 是合法结论 ✗ 不许当成没写✓★）"
    claim, ev = entry["claim"], entry["evidence"]
    if claim not in (PHYS_CLAIMS + SEM_CLAIMS):
        return False, "★R2 主张不在册✗★：%s" % claim
    if ev not in EVIDENCE:
        return False, "★R2 证据种类不在册✗★：%s" % ev
    if claim in PHYS_CLAIMS and ev == "registry":
        return False, ("★R3 **标签证据不许支撑物理结论**✗★（★铁律 1：★标签只管语义 ✗ "
                       "它说「这是半砖」推不出「它挡人」✓★）")
    # ★★R7（★A4✗★）✗★★：★证据必须落在**这条主张自己的梯**上✗★ ✓
    _ladder = EVIDENCE_PHYS if claim in PHYS_CLAIMS else EVIDENCE_SEM
    if ev not in _ladder:
        return False, ("★R7 证据不在**这条梯**上✗★：`%s` 是 **%s** 的证据 ✗ "
                       "而 `%s` 走的是 ★%s★（★两条梯不相交 ✗ 不许互相压✓★）"
                       % (ev, "／".join(EVIDENCE_SEM) if ev in EVIDENCE_SEM else "另一条",
                          claim, "／".join(_ladder)))
    v = entry["verdict"]
    if claim in PHYS_CLAIMS:
        if not isinstance(v, bool):
            return False, "★R4 物理结论必须是 True／False✗★：%r" % (v,)
    else:
        if v not in FAMILIES:
            return False, "★R4 家族不在闭集里✗★：%r（闭集：%s）" % (v, "／".join(FAMILIES))
    if ev == "name_fallback" and not (entry.get("temporary") and
                                      str(entry.get("trigger") or "").strip()):
        return False, "★R5 `name_fallback` 必须带 TEMPORARY ＋ 复核触发✗★"
    src = str(entry["source"])
    if len(src) < 12:
        return False, "★R6 证据出处太笼统 ✗ 要写清「在哪／什么时候／怎么读的」✗★：%r" % src
    return True, "✓"


def load(path: pathlib.Path = STORE) -> list:
    """★读表✗★ —— ★坏文件**不许**当成空表✗★（★那会让"★没声明★"看起来像"★没事★"✓★）"""
    if not path.is_file():
        return []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError("★例外表坏了 ✗ 不静默当成空✗★：%s" % e)
    if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
        raise RuntimeError("★例外表形状不对 ✗ 不静默当成空✗★")
    return d["entries"]


def add(entry: dict, path: pathlib.Path = STORE) -> tuple:
    """★加一条（★先校验 ✗ 拒了就不进表✓★）✗★ 返回 `(ok, why)`
    ★升级语义✗★：★同一物种同一主张 ✗ 更硬的证据**覆盖**更软的 ✗ 反方向**拒收**✗★ ✓
    """
    ok, why = validate(entry)
    if not ok:
        return False, why
    entries = load(path)
    for e in entries:
        if e.get("species") == entry["species"] and e.get("claim") == entry["claim"]:
            # ★A4：★比较必须在**同一条梯**内✗★（★这里 claim 相同 ⇒ 梯相同✓★）✗★ ✓
            _lad = EVIDENCE_PHYS if entry.get("claim") in PHYS_CLAIMS else EVIDENCE_SEM
            old_r = _lad.index(e.get("evidence")) if e.get("evidence") in _lad else 99
            new_r = _lad.index(entry["evidence"])
            if new_r >= old_r:
                return False, ("★升级语义✗★：现有 `%s` 不比 `%s` 硬 ⇒ 不覆盖"
                               % (e.get("evidence"), entry["evidence"]))
            entries.remove(e)
            break
    entry = dict(entry)
    entry.setdefault("at", time.strftime("%Y-%m-%d %H:%M:%S"))
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "dshbridge/exceptions@1", "entries": entries},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return True, "✓"


def render(entries=None, path: pathlib.Path = DOC) -> pathlib.Path:
    """★生成人看的那份✗★（★机器真相在 JSON ✗ 这份是**生成物**✓★）"""
    entries = entries if entries is not None else load()
    lines = ["# 例外表（★生成物 ✗ 别手改 ✗ 改 `state/exceptions.json`✓★）", "",
             # ★★2026-10-13（★用户裁决 D4 ✗ §79.238✗★）✗★★：
             #   ★原来这里写「生成时间 %H:%M:%S」✗★ ⇒ ★**每秒都变** ✗
             #     ⇒ ★哈希比对永远不相等 ⇒ 每跑一次闸门就把这份文档弄脏一次✗★ ✓
             #     ★（★用户踩到的就是这个 ✗ 所以他要求"内容没变就不写"✓★）✗★ ✓
             #   ★改成从**条目自己**取最新日期 ✗ 内容就只随数据变✗★ ✓
             "> 工具 `tools/exception_table.py` ｜ 条目 **%d** ｜ 最新声明 %s"
             % (len(entries), max([str(e.get("at") or "") for e in entries] or ["-"])), "",
             "★读法✗★：★每条都带**证据种类**与**出处** ✗ 而**标签证据对物理结论一律无效**✗★"
             "（★铁律 1 ✗ 这条是**拒收规则** ✗ 不是建议✓★）", "",
             "| 物种 | 主张 | 结论 | 证据 | 出处 | 声明人 | 日期 |",
             "|---|---|---|---|---|---|---|"]
    for e in entries:
        v = e.get("verdict")
        vs = ("是" if v is True else "否") if isinstance(v, bool) else str(v)
        lines.append("| `%s` | %s | %s | %s | %s | %s | %s |"
                     % (e.get("species"), e.get("claim"), vs, e.get("evidence"),
                        str(e.get("source"))[:70], e.get("by"), e.get("at", "-")))
    if not entries:
        lines.append("| ★（还没有条目✗★） | | | | | | |")
    lines += ["", "★为什么空着也不许「看着没事」✗★：★没声明 ≠ 已声明 ✗ "
              "分歧清单里那 1843 条**一条都还没声明**✗★ ✓"]
    # ★D4：★内容没变就不写✗★（★见 `docwrite.py` ✓★）
    import docwrite as _DW
    _DW.write_if_changed(path, "\n".join(lines) + "\n")
    return path


def pick_semantic(rows, cap: int = 60) -> tuple:
    """★从分歧里挑出**现在就能合法声明**的那些✗★ ⇒ `(入选, 落选理由计数)`

    ★★选择规则（★先写死 ✗ 违反即退回✗★）✗★★
      ✔ ★只收**语义级**✗★（★"挡人／能站"两条**都没翻** ⇒ 决策不受影响✓★）✗
        ★证据种类 ＝ `registry`（★标签✓★）✗ 因为**铁律 1 说标签就是语义的权威**✗★ ✓
      ✘ ★**决策级一条都不许碰**✗★ —— ★它要 `collision` ／ `experiment` 证据 ✗
        而今天**两种都还拿不到**（★见 §79.103：`solid` 不是碰撞读数✓★）✗★ ✓
      ✘ ★冲突（★标签自相矛盾✓★）**先解决再谈**✗★ ✓
      ✘ ★"表中无"没有标签侧结论 ✗ 无从声明✗★ ✓

    ★输入✗★：`rows` ＝ `[(物种, 黑名单族, 标签族, 级别文字), …]` ✓
    ★输出✗★：`(入选列表, {落选理由: 条数})` ✓（★落选也要**计数** ✗ 不许静默丢✗★）
    """
    keep, drop = [], {}
    for (sp, black, exp, lvl) in rows:
        lv = str(lvl or "")
        if lv.startswith("★★决策级"):
            drop["★决策级（★要碰撞／实验证据 ✗ 今天拿不到✓★）"] = \
                drop.get("★决策级（★要碰撞／实验证据 ✗ 今天拿不到✓★）", 0) + 1
            continue
        if "冲突" in lv:
            drop["★标签自相冲突（★先解决✓★）"] = drop.get("★标签自相冲突（★先解决✓★）", 0) + 1
            continue
        if not exp:
            drop["★表中无（★标签侧没结论✓★）"] = drop.get("★表中无（★标签侧没结论✓★）", 0) + 1
            continue
        if not lv.startswith("★语义级"):
            drop["★级别看不懂（★保守起见不收✓★）"] = drop.get("★级别看不懂（★保守起见不收✓★）", 0) + 1
            continue
        if black == exp:
            drop["★其实一致（★不是分歧✓★）"] = drop.get("★其实一致（★不是分歧✓★）", 0) + 1
            continue
        keep.append({"species": sp, "claim": "family", "verdict": exp,
                     "evidence": "registry",
                     "source": "★标签普查（★%s ⇒ 族 %s✓★）✗ 2026-10-03 由 `tag_census` 离线读出"
                               "✗ 与黑名单 `%s` 分歧 ✗ 但两条物理判定都没翻（★语义级✓★）"
                               % (sp, exp, black),
                     "by": "★自动：`declare_semantic`（★规则见 §79.108✗★）"})
    return keep[:cap], drop


def to_blockkb(entries=None, kb=None) -> dict:
    """★把例外表**接进** `blockkb`✗★ ⇒ 让它"★一有真结论就能用★"✗ 而不是躺着✗★ ✓

    ★★两件事必须分开✗★★（★铁律 1 ✗ 这里的映射就是它的机械形态✓★）
      · ★物理主张（`blocks_space` ／ `is_floor`）✗★ ⇒ ★只有 `collision` ／ `experiment`
        这两种证据配得上 ✗ 转成 `blockkb` 的**物理级**（★`collision`⇒`collision` ✓
        `experiment`⇒`experiment`✓★）✗★ ✓
      · ★语义主张（`family`）✗★ ⇒ ★转成 `blockkb` 的**语义级**（★`registry`⇒`registry`✓★）✗
        ★它**永远不许**落在物理级上✗★ ✓
    ★返回✗★：`{"put": n, "refused": [(物种, 主张, 为什么), …]}`
      ★拒收来自 `blockkb.put` 自己的规则（★等级条款／升级语义✓★）✗ 不是这里另写一套✗★ ✓
    """
    if kb is None:
        import blockkb as kb  # noqa: F811
    entries = entries if entries is not None else load()
    out = {"put": 0, "refused": []}
    for e in entries:
        claim, ev, sp = e.get("claim"), e.get("evidence"), e.get("species")
        if claim in PHYS_CLAIMS:
            # ★物理：只有碰撞／物理实验配得上 ✗ 别的**不许**进来（★表本身也会拒 ✗ 这里再兜一层✓★）
            if ev not in ("collision", "experiment"):
                out["refused"].append((sp, claim, "★物理结论只收 collision／experiment✗★"))
                continue
            lvl = "collision" if ev == "collision" else "experiment"
            v = bool(e.get("verdict"))
            # ★物理结论怎么落到 `blockkb`✗★：`blocks_space=True` ⇒ 那它**挡人** ⇒ 族按"★挡人★"给
            #   （★`True` ⇒ `full` ✓ `False` ⇒ `pass`✓★）✗ 而"能不能站"另算 ✗ 见 §79.103 的教训 ✓
            fam = "full" if v else "pass"
        else:
            if ev == "registry":
                lvl = "registry"
            elif ev in ("collision", "experiment"):
                lvl = ev
            else:
                out["refused"].append((sp, claim, "★语义结论不收 `name_fallback` ✗ 那要 TEMPORARY✓★"))
                continue
            fam = str(e.get("verdict"))
        # ★★2026-10-18（★复核 P1-5 ✗ §79.277✗★）✗★★：★这里**必须**把主张翻成 `phys=`✗★ ——
        #   ★不然「物理主张 ＋ `experiment` 证据」会**静默落进语义槽**✗★
        #   （★而 `experiment` 是物理梯**独有**的那一级：语义梯是 registry／experiment／name_fallback✗
        #     ★hmm：**两条梯子都有 experiment** ⇒ 不给 `phys` 就该被 `put` 拒✗★）✗★ ✓
        ok = kb.put(sp, fam, lvl, "exceptions:%s:%s" % (ev, e.get("source", "")[:40]),
                    trigger=e.get("trigger", ""), temporary=bool(e.get("temporary")),
                    phys=(claim in PHYS_CLAIMS))
        if ok:
            out["put"] += 1
        else:
            why = kb.REFUSED[-1]["why"] if kb.REFUSED else "★被 blockkb 拒（★没说为什么✗★）"
            out["refused"].append((sp, claim, why))
    return out


def main(argv):
    if "--render" in argv:
        print("已生成 %s（★%d 条✓★）" % (render(), len(load())))
        return 0
    print("★例外表✗★：%d 条" % len(load()))
    for e in load():
        print("   %-46s %-12s %-8s %-14s %s"
              % (e.get("species"), e.get("claim"), e.get("verdict"),
                 e.get("evidence"), str(e.get("source"))[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
