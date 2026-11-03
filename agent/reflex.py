#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reflex.py — 反射层：不经过大模型的保命与还击

为什么必须独立于大脑：
  走 API 的一次决策要几百毫秒到几秒。等模型想明白"我该不该还手"，
  假人已经被打死了、或者已经掉进虚空了。
  所以：**威胁响应与生存永远走本地确定性逻辑**，模型只负责"想干什么大事"。

职责（用户明确提过的两条都在这里）：
  1. 被攻击时主动还击（不需要模型同意）
  2. 低血/低饥饿时自己吃东西；实在不行就撤
  3. 位置长时间不动 → 判定"可能卡住"并记录下来，交给大脑处理
  4. 记录"刚才被谁打了/发生了什么"，作为事件队列喂给大脑

设计约束：
  - 一台计算机同一时刻只能吃一条指令，所以反射层和技能层共用 Channel 的内部锁；
    反射层的每次 tick 都很短（1~3 条指令），不会把大脑饿死。
  - 所有判断只用权威数据（data get entity / execute），不用动作自述。
"""

from __future__ import annotations

import math
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channel import Channel, BridgeError     # noqa: E402
from memory import Journal                   # noqa: E402
from world import World                      # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

HOSTILE_WORDS = ("zombie", "skeleton", "spider", "creeper", "slime", "witch", "enderman",
                 "pillager", "vindicator", "blaze", "ghast", "phantom", "drowned", "husk",
                 "stray", "silverfish", "piglin", "hoglin", "magma_cube", "warden", "ravager")


class Reflex:
    def __init__(self, world: World, ch: Channel, skills=None, interval: float = 4.0,
                 threat_radius: int = 12, low_health: float = 8.0, low_food: int = 6,
                 bot: str = "Bot", dry_run: bool = False, verbose: bool = True):
        self.w = world
        self.ch = ch
        self.skills = skills
        self.interval = interval
        self.threat_radius = threat_radius
        self.low_health = low_health
        self.low_food = low_food
        self.bot = bot
        self.dry_run = dry_run          # True = 只观察不动手（第一次上线时先用它看行为）
        self.verbose = verbose
        self.journal = Journal("reflex")
        self.events: list[dict] = []    # 待大脑消费的事件队列
        self.paused = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_pos: tuple | None = None
        self._still_since: float | None = None
        self.stats = {"ticks": 0, "fights": 0, "meals": 0, "stuck_warnings": 0, "errors": 0}

    # -- 生命周期 ------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="reflex", daemon=True)
        self._thread.start()
        self.journal.write("start", summary="反射层启动 interval=%ss dry_run=%s"
                           % (self.interval, self.dry_run))

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self.journal.write("stop", summary=json_dumps(self.stats))

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self.paused:
                try:
                    self.tick()
                except BridgeError as e:
                    self.stats["errors"] += 1
                    self.journal.write("error", summary="通道错误：%s" % e)
                except Exception as e:
                    self.stats["errors"] += 1
                    self.journal.write("error", summary="%s: %s" % (type(e).__name__, e))
            self._stop.wait(self.interval)

    # -- 一次心跳 ------------------------------------------------------------ #

    def push(self, kind: str, text: str, **extra) -> None:
        ev = {"ts": time.time(), "kind": kind, "text": text}
        ev.update(extra)
        self.events.append(ev)
        self.journal.write("event", summary="%s：%s" % (kind, text))

    def drain(self, limit: int = 10) -> list[dict]:
        out = self.events[:limit]
        self.events = self.events[limit:]
        return out

    def tick(self) -> dict:
        self.stats["ticks"] += 1
        out: dict = {"ts": time.time()}

        v = self.w.vitals()
        out["vitals"] = v
        if not v.get("alive") and v.get("health") is not None:
            self.push("death", "假人生命为 0（已死）")
            return out
        if v.get("health") is None:
            self.push("offline", "查不到假人生命值：可能不在线")
            return out

        hp = float(v["health"])
        food = v.get("food")

        # 位置：用来判断"卡住"和"掉下去"
        p = self.w.pos()
        out["pos"] = p
        if p is not None:
            if self._last_pos and math.dist(p, self._last_pos) < 0.15:
                if self._still_since is None:
                    self._still_since = time.time()
                elif time.time() - self._still_since > 25:
                    self.stats["stuck_warnings"] += 1
                    self.push("stuck", "位置 %.1f 秒没变，可能卡住了" % (time.time() - self._still_since))
                    self._still_since = None
            else:
                self._still_since = None
            self._last_pos = p

        # 威胁：先看有没有敌对生物
        try:
            ents = self.w.entities(radius=self.threat_radius)
        except BridgeError:
            ents = []
        foes = [e for e in ents if any(w in e.get("id", "").lower() for w in HOSTILE_WORDS)]
        out["foes"] = [e.get("id") for e in foes]

        if foes:
            self.push("threat", "半径 %d 内有敌对生物：%s" % (self.threat_radius,
                                                              [f.get("id") for f in foes[:4]]))
            if hp <= self.low_health:
                if not self.dry_run and self.skills:
                    self.stats["meals"] += 1
                    self.skills.run("eat", {})
                self.push("action", "血太少（%s），先吃东西" % hp)
            else:
                if not self.dry_run and self.skills:
                    self.stats["fights"] += 1
                    r = self.skills.run("attack", {"radius": self.threat_radius, "seconds": 8})
                    self.push("fight", "还击结果：%s" % (r.get("evidence") or r.get("error")))
        elif food is not None and food <= self.low_food:
            self.push("hungry", "饥饿值 %s 偏低" % food)
            if not self.dry_run and self.skills:
                self.stats["meals"] += 1
                self.skills.run("eat", {})

        return out


def json_dumps(o) -> str:
    import json
    return json.dumps(o, ensure_ascii=False)


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    interval = 4.0
    for a in argv:
        if a.startswith("--interval="):
            interval = float(a.split("=", 1)[1])
    ch = Channel("cmd0")
    w = World(ch)
    r = Reflex(w, ch, skills=None, interval=interval, dry_run=dry)
    print("反射层自测：dry_run=%s interval=%ss（Ctrl+C 结束）" % (dry, interval))
    r.start()
    try:
        while True:
            time.sleep(interval)
            for ev in r.drain():
                print("  [事件] %s: %s" % (ev["kind"], ev["text"]))
            print("  统计：%s" % json_dumps(r.stats))
    except KeyboardInterrupt:
        r.stop()
        print("\n已停止。%s" % json_dumps(r.stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
