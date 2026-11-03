#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""primitives.py -- 模块 C 动作原语层：★一个动作 = 许可 → 执行 → 独立校验 → 留痕✗★

规格（§2.4 / §6.3 / §14.1）：
  * 每个原语必须有**前摇**（N4：动作要花游戏刻，不许"一帧完成"）
  * 破坏性动作**先问模块 I**（★不可挖区域 ✗ 命中就拒 ✗ 一次 dsh 都不发✗★）
  * 做完**由 L4 独立校验**（★只看世界真值 ✗ 不信执行者自述✗★）
  * **有后果的事必须留痕**（★模块 F／N8' ✗ 写 reasons✗★）
  * ★★H 接线（§2.8）✗★★：每个原语结束后把**有后果的事件**也写进 `event_memory`
    （★动作 → 事件 → reporter 能汇报✗★）；★`log=False` 或无事件路径时零副作用✗★。

原语：`walk_to(cell)` ／ `dig(pos)` ／ `place(pos, item)` ／ `use(pos, face)` ／ `eat()`

★关键实现细节（都是实测踩出来的）✗★：
  · `dshplace` 的 item 参数是 `StringArgumentType.string()` ⇒ ★**必须加引号** ✗ 否则带 `:` 的 id 不解析✗★
  · 前摇用**游戏刻**量（`dshdigest` 的 `time=`）✗ 不用墙钟（★墙钟被往返 600ms 淹没✗★）✗★
"""
from __future__ import annotations

import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★前摇下限（游戏刻 ✗ 20 刻 = 1 秒）★ —— 与 humanlike_test 的 MIN_TICKS 同口径
MIN_TICKS = {"dig": 2, "place": 1, "use": 1, "eat": 32, "walk": 1}


def _default_dsh():
    import mcp_core as C
    return C.dsh


def _game_time(dsh) -> int:
    d = (dsh("dshdigest", 30.0) or "")
    m = re.search(r"\btime=(\d+)", d)
    return int(m.group(1)) if m else -1


class Primitives:
    def __init__(self, dsh=None, verifier=None, permit=None, log=True, events=None):
        """`log`：是否写 reasons（既有语义）；`events`：事件账本路径（None=按 event_memory 默认）。
        ★`log=False` 且 `events=None` ⇒ **不写任何账**（既有判据的零副作用保证）✗★。"""
        self._dsh = dsh or _default_dsh()
        self._ver = verifier
        self._permit = permit
        self.log = log
        self.events = events
        self.calls = 0
        # ★H 接线：主流程（log=True）把"校验红/绿"与"重要理由"也接进事件账本✗★
        if self.log:
            if self._ver is None:
                try:
                    import verifier as _V
                    _V.set_recorder(self._on_verify)
                except Exception as exc:      # ★不许静默✗★
                    print("primitives: 注册校验事件记录器失败 %r" % (exc,),
                          file=sys.stderr)
            try:
                import reasons as _R
                _R.set_event_recorder(self._on_reason)
            except Exception as exc:          # ★不许静默✗★
                print("primitives: 注册理由事件记录器失败 %r" % (exc,),
                      file=sys.stderr)

    # ── 内部 ──────────────────────────────────────────────────────────
    def dsh(self, cmd, t=45.0) -> str:
        self.calls += 1
        return (self._dsh(cmd, t) or "").strip()

    def _verifier(self):
        if self._ver is None:
            import verifier as V
            self._ver = V
        return self._ver

    def _permit_mod(self):
        if self._permit is None:
            import no_dig as ND
            self._permit = ND
        return self._permit

    def _reason(self, code, pos=None, mission="", action="", detail="", important=False):
        if not self.log:
            return None
        try:
            import reasons as R
            return R.because(code, mission=mission, pos=pos, action=action,
                             important=important, detail=detail)
        except Exception as exc:        # ★不许静默✗★
            print("primitives: 写理由失败 %r" % (exc,), file=sys.stderr)
            return None

    # ── H 接线：事件账本（★best-effort ✗ 记账失败不许把动作带崩✗★）──────────
    def _event(self, kind, what="", evidence=None, where=None, objects=None,
               important=False):
        if self.events is False:
            return None
        if not self.log and self.events is None:
            return None                      # ★既有判据 log=False ⇒ 零副作用✗★
        try:
            import event_memory as EM
        except Exception as exc:              # ★不许静默✗★
            print("primitives: 事件模块不可用 %r" % (exc,), file=sys.stderr)
            return None
        path = self.events if isinstance(self.events, (str, pathlib.Path)) else None
        try:
            return EM.record(kind, what=what, evidence=evidence, where=where,
                             objects=objects, important=important, path=path)
        except Exception as exc:              # ★不许静默✗★（EM.record 本身也不抛）
            print("primitives: 记事件 %r 失败 %r" % (kind, exc), file=sys.stderr)
            return None

    def _on_verify(self, kind, verdict, pos=None):
        """校验官的事件记录器：★红/绿都留证据指针（红更重要）✗★"""
        ok = bool((verdict or {}).get("ok"))
        self._event("verify" if ok else "verify_fail",
                    what=str(kind), where=pos,
                    evidence={"kind": "verifier",
                              "ref": "%s ok=%s why=%s" % (kind, ok,
                                                          (verdict or {}).get("why"))},
                    important=not ok)

    def _on_reason(self, rec):
        """理由记录器：★只有重要理由才进来（reasons 侧已过滤）✗★"""
        if not isinstance(rec, dict):
            return None
        return self._event("reason", what=str(rec.get("reason") or "")[:120],
                           where=rec.get("pos"),
                           evidence={"kind": "reasons",
                                     "mission": str(rec.get("mission") or ""),
                                     "ref": "%s ts=%s action=%s"
                                            % (rec.get("log_file"), rec.get("ts"),
                                               rec.get("action"))},
                           important=bool(rec.get("important")))

    def _windup(self, kind, t0) -> int:
        t1 = _game_time(self._dsh)
        if t0 < 0 or t1 < 0:
            return -1
        return t1 - t0

    # ── 原语 ──────────────────────────────────────────────────────────
    def walk_to(self, cell, timeout=30.0, mission="") -> dict:
        t0 = _game_time(self._dsh)
        out = self.dsh("dshwalk %d %d %d" % tuple(int(v) for v in cell), timeout)
        ok_walk = "dshwalk" in out and ("start" in out or "ok" in out or "reached" in out)
        tk = self._windup("walk", t0)
        v = self._verifier().verify_arrived(cell)
        ok = bool(v.get("ok"))
        self._reason("walk_to" if ok else "walk_failed", pos=cell, mission=mission,
                     action="walk", detail=v.get("why", ""))
        self._event("arrive" if ok else "fail",
                    what="walk_to %s" % (list(cell),), where=cell, important=not ok,
                    evidence={"kind": "verify", "mission": mission,
                              "ref": "verify=%s reply=%s" % (v.get("why"), out[:60])})
        return {"ok": ok, "kind": "walk", "why": v.get("why"),
                "ticks": tk, "windup_ok": tk < 0 or tk >= MIN_TICKS["walk"],
                "evidence": {"reply": out[:120], "verify": v}}

    def dig(self, pos, mission="") -> dict:
        # ★模块 I：先问许可 ✗ 命中就**一次 dsh 都不发**✗★
        ok_zone, zone = self._permit_mod().allowed(tuple(pos))
        if not ok_zone:
            self._reason("no_dig_zone", pos=pos, mission=mission,
                         action="no_dig_zone", important=True,
                         detail=(zone or {}).get("name", ""))
            self._event("fail", what="dig refused: no_dig_zone",
                        where=pos, important=True,
                        evidence={"kind": "permit", "mission": mission,
                                  "ref": "no_dig_zone:%s" % ((zone or {}).get("name"),)})
            return {"ok": False, "kind": "dig", "why": "no_dig_zone",
                    "zone": (zone or {}).get("name"), "refused_before_dsh": True}
        t0 = _game_time(self._dsh)
        out = self.dsh("dshdig %d %d %d" % tuple(int(v) for v in pos))
        tk = self._windup("dig", t0)
        v = self._verifier().verify_dig(tuple(pos))
        ok = bool(v.get("ok"))
        self._reason("dig" if ok else "dig_failed", pos=pos, mission=mission,
                     action="dig", important=True, detail=v.get("why", ""))
        self._event("dig" if ok else "fail", what="dig %s" % (list(pos),), where=pos,
                    important=True,
                    evidence={"kind": "verify", "mission": mission,
                              "ref": "verify=%s reply=%s" % (v.get("why"), out[:60])})
        return {"ok": ok, "kind": "dig", "why": v.get("why"),
                "ticks": tk, "windup_ok": tk < 0 or tk >= MIN_TICKS["dig"],
                "evidence": {"reply": out[:120], "verify": v}}

    def place(self, pos, item, mission="") -> dict:
        ok_zone, zone = self._permit_mod().allowed(tuple(pos))
        if not ok_zone:
            self._reason("no_dig_zone", pos=pos, mission=mission,
                         action="no_dig_zone", important=True,
                         detail="place:" + str((zone or {}).get("name")))
            self._event("fail", what="place refused: no_dig_zone",
                        where=pos, important=True, objects=[item],
                        evidence={"kind": "permit", "mission": mission,
                                  "ref": "no_dig_zone:%s" % ((zone or {}).get("name"),)})
            return {"ok": False, "kind": "place", "why": "no_dig_zone",
                    "zone": (zone or {}).get("name"), "refused_before_dsh": True}
        # ★item 必须加引号✗★（★`StringArgumentType.string()` ⇒ 带 `:` 的裸 id 不解析✗★）
        t0 = _game_time(self._dsh)
        out = self.dsh('dshplace %d %d %d "%s"' % (tuple(int(v) for v in pos) + (item,)))
        tk = self._windup("place", t0)
        v = self._verifier().verify_place(tuple(pos), item)
        ok = bool(v.get("ok"))
        self._reason("place" if ok else "place_failed", pos=pos, mission=mission,
                     action="place", important=True, detail=v.get("why", ""))
        self._event("place" if ok else "fail", what="place %s" % (item,), where=pos,
                    important=True, objects=[item],
                    evidence={"kind": "verify", "mission": mission,
                              "ref": "verify=%s reply=%s" % (v.get("why"), out[:60])})
        return {"ok": ok, "kind": "place", "why": v.get("why"),
                "ticks": tk, "windup_ok": tk < 0 or tk >= MIN_TICKS["place"],
                "evidence": {"reply": out[:120], "verify": v}}

    def use(self, pos, face="up", mission="") -> dict:
        t0 = _game_time(self._dsh)
        out = self.dsh("dshuse %d %d %d %s" % (tuple(int(v) for v in pos) + (face,)))
        tk = self._windup("use", t0)
        ok = "dshuse" in out and "FAIL" not in out
        self._reason("use" if ok else "use_failed", pos=pos, mission=mission,
                     action="use", important=True, detail=out[:80])
        self._event("use" if ok else "fail", what="use %s face=%s" % (list(pos), face),
                    where=pos, important=True,
                    evidence={"kind": "receipt", "mission": mission,
                              "ref": "reply=%s" % (out[:80],)})
        return {"ok": ok, "kind": "use", "why": None if ok else "use_failed",
                "ticks": tk, "windup_ok": tk < 0 or tk >= MIN_TICKS["use"],
                "evidence": {"reply": out[:120]}}

    def eat(self, mission="") -> dict:
        t0 = _game_time(self._dsh)
        before = (self.dsh("dshdigest", 30.0) or "")
        f0 = re.search(r"food=(\d+)", before)
        out = self.dsh("dsheata", 60.0) or self.dsh("dsheat", 60.0)
        tk = self._windup("eat", t0)
        after = (self.dsh("dshdigest", 30.0) or "")
        f1 = re.search(r"food=(\d+)", after)
        ok = bool(f0 and f1 and int(f1.group(1)) >= int(f0.group(1)) and "dsh" in out)
        self._reason("eat" if ok else "eat_failed", mission=mission, action="eat",
                     important=True, detail=out[:80])
        self._event("eat" if ok else "fail", what="eat food=%s->%s"
                    % (f0.group(1) if f0 else "?", f1.group(1) if f1 else "?"),
                    important=True,
                    evidence={"kind": "receipt", "mission": mission,
                              "ref": "reply=%s" % (out[:80],)})
        return {"ok": ok, "kind": "eat", "why": None if ok else "eat_failed",
                "ticks": tk, "windup_ok": tk < 0 or tk >= MIN_TICKS["eat"],
                "evidence": {"reply": out[:120],
                             "food": (f0.group(1) if f0 else None,
                                      f1.group(1) if f1 else None)}}


def main(argv) -> int:
    P = Primitives()
    if argv and argv[0] == "walk":
        print(P.walk_to(tuple(int(v) for v in argv[1].split(","))))
        return 0
    if argv and argv[0] == "dig":
        print(P.dig(tuple(int(v) for v in argv[1].split(","))))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
