#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory3.py -- ★记忆分三份：人／承诺／地★（2026-09-30 ✓ 用户第 4 条 ✓ 纯逻辑 ＋ 三个小文件 ✓ 离线 ✓）

## 用户原话要点 ✗
  「记忆切成**人／承诺／地**」✓ —— ★这三类东西**过期方式完全不同**✗★ 这就是要分开的理由：
    · **人**：只增不减 ✓ 越处越熟 ✓（谁来过、说过几次、我答应过谁 ✓）
    · **承诺**：★**必须能兑现、也必须能查**✗★ —— 本项目铁律：
      「『马上就好』之后**必须真动手**」✗ ⇒ 承诺**没有证据不许标成做了** ✗（见 `keep()` ✓）
    · **地**：会**变**（箱子被搬空 ✓ 矿点挖完了 ✓）⇒ 要能覆盖 ✓ 也要能说"我上次看到它是什么时候"✓
  ⇒ ★混在一个字典里 ⇒ 迟早出现"我把一个地点当成一个人"那种事✗★

## 三份文件（★分开存✗★ ⇒ 一个写坏不连累另两个 ✓ 也方便人肉查看 ✓）
  `memory/people.json` ／ `memory/promises.json` ／ `memory/places.json` ✓（纯文本 json ✓ 可读 ✓）

## 纪律（★写在这里免得忘✗★）
  ① ★**承诺没有证据 ⇒ 不许算兑现**✗★（`keep()` 直接拒绝空证据 ✓ 与 P122「认回执里真有的字段」同族 ✓）
  ② ★**过期 ≠ 做到**✗★：过了时间还是 `open` ✓ 只会变成 `overdue` ✓ 绝不会自己变成 `done` ✗
  ③ ★**名字精确匹配**✗★（不许子串 ✗ P105/P107 ✓）—— 查不到就说查不到 ✓
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "memory"
P_PEOPLE = DIR / "people.json"
P_PROMISES = DIR / "promises.json"
P_PLACES = DIR / "places.json"

# ★关系等级：只由"见过几次+说过几次"缓慢推出来✗★（不许手写一个"亲密"就完事 ✓）
REL = ((0, "陌生人"), (3, "见过"), (10, "熟人"), (30, "一起干过活"), (80, "老搭档"))


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _read(p: Path) -> dict:
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        # ★读坏了**不许覆盖**✗★：改名留档 ⇒ 人还能去看 ✓（静默清空 ＝ 记忆被剪 ✗）
        try:
            p.with_suffix(".broken-%s.json" % time.strftime("%H%M%S")).write_text(
                p.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception as e:
            # 记录：连"留档"都失败 ⇒ 坏档下一次写就被覆盖（数据真丢）
            print("[记录] 坏记忆留档失败（%s）-> 下次写会覆盖它：%s"
                  % (type(e).__name__, p.name), file=sys.stderr)
        print("[记录] 记忆文件读坏（已尝试留档，本进程按空记忆走）：%s"
              % p.name, file=sys.stderr)
        return {}


def _write(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(p)          # ★原子替换✗★（写一半被打断 ⇒ 不会留下半份记忆 ✓）


def rel_name(met: int, said: int = 0) -> str:
    """★关系：**只增不减**的等级✗★ ✓（`met` 是见面次数 ＋ `said` 是说话次数 ✓ 各算一份 ✓）"""
    n = int(met or 0) + int(said or 0)
    out = REL[0][1]
    for (k, v) in REL:
        if n >= k:
            out = v
    return out


# ── 人 ────────────────────────────────────────────────────────────────────────
def seen_person(name: str, place: str = "", note: str = "") -> dict:
    """★见到一个人（或收到他一句话 ✓）⇒ 记一笔★ ✓（★次数只增 ✗ 时间更新 ✓★）"""
    d = _read(P_PEOPLE)
    k = str(name or "").strip()
    if not k:
        return {}
    e = d.get(k) or {"met": 0, "said": 0, "first": _now(), "notes": []}
    e["met"] = int(e.get("met") or 0) + 1
    e["last"] = _now()
    if place:
        e["place"] = str(place)
    if note and note not in e["notes"]:
        e["notes"] = (e["notes"] + [str(note)])[-20:]      # ★只留最近 20 条 ✗ 不涨内存 ✓
    e["rel"] = rel_name(e["met"], e.get("said"))
    d[k] = e
    _write(P_PEOPLE, d)
    return e


def said_to(name: str) -> dict:
    """★我回了他一句 ⇒ 单独记（说话次数 ✓）★"""
    d = _read(P_PEOPLE)
    k = str(name or "").strip()
    if not k:
        return {}
    e = d.get(k) or {"met": 0, "said": 0, "first": _now(), "notes": []}
    e["said"] = int(e.get("said") or 0) + 1
    e["rel"] = rel_name(e["met"], e["said"])
    d[k] = e
    _write(P_PEOPLE, d)
    return e


def people() -> dict:
    return _read(P_PEOPLE)


# ── 承诺 ──────────────────────────────────────────────────────────────────────
def promise_id(what: str) -> str:
    return "p" + str(abs(hash(str(what))) % 100000)


def promise(what: str, due_at: str = "", to: str = "") -> dict:
    """★我答应了一件事★ ✓（★记下来 ⇒ 才会有人来查我到底做没做✗★）"""
    d = _read(P_PROMISES)
    k = promise_id(what)
    e = d.get(k) or {}
    e.update({"what": str(what), "to": str(to), "made": _now(),
              "due": str(due_at or ""), "status": "open", "evidence": "", "done": ""})
    d[k] = e
    _write(P_PROMISES, d)
    return e


def keep(pid_or_what: str, evidence: str) -> tuple:
    """★★兑现承诺 —— **必须有证据**✗★★ ✓（返回 `(成没成, 说明)` ✓）

    ★为什么死卡这一条✗★（用户提过一次的原则 ✓ 也是本项目铁律 ✓）：
      「『马上就好』之后**必须真动手**」✗ ⇒ 而"动手了"**不能由我自己说了算**✗
      ⇒ 证据 = 一句**外面能对账**的话 ✓（`dshdigest` 回执 ✓ 任务账本的证据行 ✓ 工具回执 ✓）
      ★空证据 ⇒ **直接拒绝**✗★（连"我觉得我做了"都不收 ✓ —— 那正是最危险的那种自信 ✓）
    """
    ev = str(evidence or "").strip()
    if not ev:
        return False, "★没有证据 ⇒ 不许算兑现 ✗★（本项目铁律：「马上就好」之后必须真动手 ✓）"
    d = _read(P_PROMISES)
    k = pid_or_what if pid_or_what in d else promise_id(pid_or_what)
    if k not in d:
        return False, "没记过这条承诺 ✗（先 `promise()` ✓ 不许事后补一张已完成的单子 ✗）"
    d[k]["status"] = "done"
    d[k]["evidence"] = ev
    d[k]["done"] = _now()
    _write(P_PROMISES, d)
    return True, "兑现 ✓ 证据：%s" % ev


def drop(pid_or_what: str, reason: str) -> tuple:
    """★放弃承诺（★也要有理由 ✗★）★ —— 状态是 `dropped` ✗ **绝不是 `done`** ✗"""
    r = str(reason or "").strip()
    if not r:
        return False, "放弃也要写理由 ✗"
    d = _read(P_PROMISES)
    k = pid_or_what if pid_or_what in d else promise_id(pid_or_what)
    if k not in d:
        return False, "没记过这条承诺 ✗"
    d[k]["status"] = "dropped"
    d[k]["why"] = r
    d[k]["done"] = _now()
    _write(P_PROMISES, d)
    return True, "撤了 ✓ 理由：%s" % r


def open_promises(now: float = None) -> list:
    """★还没兑现的★ ✓ —— ★过期的单独标 `overdue`✗ 但**仍然算没做**✗★"""
    d = _read(P_PROMISES)
    now = float(now if now is not None else time.time())
    out = []
    for (k, e) in sorted(d.items()):
        if e.get("status") != "open":
            continue
        e = dict(e)
        e["id"] = k
        due = str(e.get("due") or "")
        if due:
            try:
                e["overdue"] = time.mktime(time.strptime(due, "%Y-%m-%d %H:%M:%S")) < now
            except Exception:
                e["overdue"] = False
        out.append(e)
    return out


def promises() -> dict:
    return _read(P_PROMISES)


# ── 地 ────────────────────────────────────────────────────────────────────────
def remember_place(name: str, x: float, y: float, z: float, dim: str = "", note: str = "") -> dict:
    """★记一个地方★ ✓（★同名覆盖 ✗ —— 地方会变 ✓ 但**要留住"上次看到"**✗★）"""
    d = _read(P_PLACES)
    k = str(name or "").strip()
    if not k:
        return {}
    old = d.get(k) or {}
    e = {"x": float(x), "y": float(y), "z": float(z), "dim": str(dim or old.get("dim") or ""),
         "note": str(note or old.get("note") or ""), "at": _now(),
         "first": old.get("first") or _now(), "seen": int(old.get("seen") or 0) + 1}
    d[k] = e
    _write(P_PLACES, d)
    return e


def place(name: str) -> dict:
    """★查一个地方（**精确名字**✗ 不许模糊 ✓ P105/P107 ✓）★ —— 查不到 ⇒ `{}` ✓ 不猜 ✓"""
    return dict(_read(P_PLACES).get(str(name or "").strip()) or {})


def places() -> dict:
    return _read(P_PLACES)


def brief(max_people: int = 3, max_promises: int = 3, max_places: int = 3) -> str:
    """★一句话现状★ ✓（给"我认识谁／我答应了什么／我家在哪"这类问题用 ✓ 全是真值 ✓）"""
    ppl = people()
    top = sorted(ppl.items(), key=lambda kv: -(int(kv[1].get("met") or 0) + int(kv[1].get("said") or 0)))[:max_people]
    pr = open_promises()[:max_promises]
    pl = sorted(places().items())[:max_places]
    L = []
    if top:
        L.append("人：" + "／".join("%s（%s ✓ 见过 %d 次）" % (k, v.get("rel"), v.get("met") or 0)
                                   for (k, v) in top))
    if pr:
        L.append("欠着的事：" + "／".join("%s%s" % (e["what"], "（过期了 ✗）" if e.get("overdue") else "")
                                         for e in pr))
    if pl:
        L.append("地方：" + "／".join("%s(%d,%d,%d)" % (k, v["x"], v["y"], v["z"]) for (k, v) in pl))
    return " ｜ ".join(L) if L else "（还什么都没记住 ✓）"
