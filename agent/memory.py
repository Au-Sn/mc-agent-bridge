#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memory.py — 记忆：目标栈 / 事实本 / 行动日志

为什么需要：
  大模型的上下文会被清空、会被压缩。真正可靠的长时记忆只能落在磁盘上。
  这一层就是它的"体外记忆"，也顺便成为复盘和错题本的素材来源。

三个东西，各司其职：
  - GoalStack：当前目标与子目标的栈。压栈/出栈/挂起，跨回合存活。
  - Facts：世界事实（"门在 (4119,71,9)"、"平台在 y=70"），带来源与时间。
    只有经过世界状态核实的事实才允许写进来 —— 记错的事实比没事实更糟。
  - Journal：只追加的行动流水（jsonl + 人类可读 markdown），出问题时的第一现场。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
MEM_DIR = AGENT_DIR / "memory"


def _now() -> float:
    return time.time()


def _stamp(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or _now()))


@dataclass
class Goal:
    text: str
    created: float = field(default_factory=_now)
    status: str = "active"          # active | done | failed | shelved
    parent: str = ""
    note: str = ""

    def line(self) -> str:
        return "[%s] %s%s" % (self.status, self.text, ("  (%s)" % self.note) if self.note else "")


class GoalStack:
    def __init__(self, path: Path = MEM_DIR / "goals.json"):
        self.path = Path(path)
        self.goals: list[Goal] = []
        self.load()

    def load(self) -> None:
        if self.path.is_file():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.goals = [Goal(**g) for g in raw]
            except Exception:
                self.goals = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(g) for g in self.goals], ensure_ascii=False, indent=1),
                             encoding="utf-8")

    def push(self, text: str, parent: str = "", note: str = "") -> Goal:
        g = Goal(text=text, parent=parent, note=note)
        self.goals.append(g)
        self.save()
        return g

    def active(self) -> Goal | None:
        for g in reversed(self.goals):
            if g.status == "active":
                return g
        return None

    def close(self, status: str = "done", note: str = "") -> Goal | None:
        g = self.active()
        if g:
            g.status = status
            if note:
                g.note = note
            self.save()
        return g

    def text(self, limit: int = 8) -> str:
        if not self.goals:
            return "（还没有目标）"
        return "\n".join("  " + g.line() for g in self.goals[-limit:])


class Facts:
    """只有"亲眼核实过"的事实才准写进来。"""

    def __init__(self, path: Path = MEM_DIR / "facts.json"):
        self.path = Path(path)
        self.items: list[dict] = []
        self.load()

    def load(self) -> None:
        if self.path.is_file():
            try:
                self.items = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.items = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")

    def add(self, key: str, value, source: str) -> dict:
        rec = {"key": key, "value": value, "source": source, "ts": _now(), "at": _stamp()}
        self.items = [i for i in self.items if i.get("key") != key] + [rec]
        self.save()
        return rec

    def get(self, key: str, default=None):
        for i in reversed(self.items):
            if i.get("key") == key:
                return i.get("value")
        return default

    def text(self, limit: int = 20) -> str:
        if not self.items:
            return "（还没有已核实的事实）"
        return "\n".join("  %s = %s   [来源:%s %s]" % (i["key"], i["value"], i.get("source"), i.get("at"))
                         for i in self.items[-limit:])


class Journal:
    """只追加的行动流水。出问题时先看它，不要先猜。"""

    def __init__(self, prefix: str = "journal", dirpath: Path = MEM_DIR):
        self.dir = Path(dirpath)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jsonl = self.dir / ("%s.jsonl" % prefix)
        self.md = self.dir / ("%s.md" % prefix)

    def write(self, kind: str, **fields) -> None:
        rec = {"ts": _now(), "at": _stamp(), "kind": kind}
        rec.update(fields)
        with open(self.jsonl, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        line = "**%s** `%s`" % (rec["at"], kind)
        detail = fields.get("summary") or fields.get("text") or fields.get("note")
        if detail:
            line += " — %s" % str(detail)[:400]
        with open(self.md, "a", encoding="utf-8") as fh:
            fh.write("- " + line.replace("\n", " ") + "\n")

    def tail(self, n: int = 20) -> list[dict]:
        if not self.jsonl.is_file():
            return []
        out = []
        for ln in self.jsonl.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
        return out
