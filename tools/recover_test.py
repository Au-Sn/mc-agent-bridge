#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recover_test.py -- ★D4 recover.py 的离线判据（RE1~RE10 ✗ 2026-11-02）★

★为什么有它✗★：`recover.py` 是**重启窗口里唯一要跑的那条命令** ✗ 它一旦"看起来成功"而 Bot 其实不在，
  后面所有 live 判据都会以假前提开跑 ✗（P17 那一族的翻版：spawn 出来是创造模式 ⇒ 自给证据全失真）
  ⇒ 用**注入假通道**把每条分支离线逼一遍：spawn/切生存/确认/幂等/退出码 ✗ 一次都不许"假装" ✓

★口径✗★：
  · 假通道（FakeTransport）记录**每一次** post/raw ✗ 断言"该调的调了 ✗ 不该调的没调"✓
  · `sleep` 注入成空函数 ⇒ 不真等 ✓
  · 全部断言不写死本包坐标/版本（锚点用假值）✓
  · ★自检能红✗★（M1）：期望表整体取反 ⇒ 判据必须能发现 ✓
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import recover as RC  # noqa: E402

ok = [True]
RESULTS = []
NO_SLEEP = lambda _s: None       # noqa: E731  ★判据里不等真时间✗★


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    RESULTS.append((tag, bool(cond)))
    print("  %-5s %s %s" % (tag, "✓" if cond else "★红✗★", note))


def digest_text(bot) -> str:
    """假 dshdigest 回执（★只保留 recover.py 真正会读的字段✗★）"""
    if not bot:
        return "dshdigest reason=no_bot"
    return ("dshdigest reason=ok name=Bot pos=%s yaw=0.0 pitch=0.0 hp=%s food=20 "
            "sat=5.0 xp=0 mode=%s onground=%s dim=minecraft:overworld"
            % (bot.get("pos", "1.0,2.0,3.0"), bot.get("hp", "20.0"),
               bot.get("mode", "survival"), bot.get("onground", "true")))


class FakeTransport:
    """★假通道✗★：脚本化 health/spawn/gamemode，并**记录所有调用**"""

    def __init__(self, health="ok dshbridge-http", bot=None, spawn_ok=True,
                 spawn_creates=True, gm_ok=True):
        self.health_reply = health
        self.bot = dict(bot) if bot else None
        self.spawn_ok = spawn_ok
        self.spawn_creates = spawn_creates
        self.gm_ok = gm_ok
        self.post_calls = []
        self.raw_calls = []

    def health(self, timeout=2.0):
        return self.health_reply

    def post(self, cmd, timeout=20.0):
        self.post_calls.append(cmd)
        if "dshdigest" in cmd:
            return digest_text(self.bot)
        return ""

    def raw(self, cmd, timeout=20.0):
        self.raw_calls.append(cmd)
        if "player" in cmd and "spawn" in cmd:
            if not self.spawn_ok:
                return None
            if self.spawn_creates:
                self.bot = {"mode": "creative", "pos": "4120.5,71.0,16.5", "onground": "true"}
            return "Spawned Bot"
        if "gamemode survival" in cmd:
            if not self.gm_ok:
                return None
            if self.bot:
                self.bot["mode"] = "survival"
            return "Set Bot's game mode to survival"
        return ""


def run(t, flags_dir, anchor="1 2 3", dry_run=False, attempts=3):
    return RC.recover(t, anchor=anchor, flags_dir=flags_dir, dry_run=dry_run,
                      attempts=attempts, retry_delay=0.0, sleep=NO_SLEEP)


def spawns(t):
    return [c for c in t.raw_calls if "spawn" in c]


print("== recover：D4 一条命令恢复 RE1~RE10（注入假通道）==")
tmp = Path(__import__("tempfile").mkdtemp(prefix="dsh_recover_test_"))
try:
    # ---------------- RE1 health 不通 ⇒ 硬故障 exit 1，且★一条 /raw 都不发✗★
    t1 = FakeTransport(health=None, bot=None)
    r1 = run(t1, tmp / "f1")
    check("RE1", r1["exit"] == 1 and r1["steps"][0]["status"] == "FAIL"
          and not t1.raw_calls and not spawns(t1),
          "health 不通 ⇒ exit=%s ｜ post=%d raw=%d（★不瞎试 /raw✗★）"
          % (r1["exit"], len(t1.post_calls), len(t1.raw_calls)))

    # ---------------- RE2 Bot 不在 ⇒ spawn 一次＋回读出现 ⇒ 切生存?（spawn 出来是创造）⇒ 恢复成功
    t2 = FakeTransport(bot=None)
    r2 = run(t2, tmp / "f2")
    check("RE2", r2["exit"] == 0 and r2["spawned"] and len(spawns(t2)) == 1
          and any("gamemode survival" in c for c in t2.raw_calls)
          and r2["bot"].get("mode") == "survival",
          "缺 Bot ⇒ spawn=1 次 + 切生存 ⇒ exit=%s mode=%s pos=%s"
          % (r2["exit"], r2["bot"].get("mode"), r2["bot"].get("pos")))

    # ---------------- RE3 已经就绪 ⇒ 幂等：★0 次 spawn / 0 次 raw✗★
    t3 = FakeTransport(bot={"mode": "survival", "pos": "4120.5,71.0,16.5", "onground": "true"})
    r3 = run(t3, tmp / "f3")
    check("RE3", r3["exit"] == 0 and not spawns(t3) and not t3.raw_calls
          and r3["spawned"] is False and not r3["gamemode_fixed"],
          "已就绪 ⇒ exit=%s ｜ spawn=%d raw=%d（幂等：不重复 spawn ✓）"
          % (r3["exit"], len(spawns(t3)), len(t3.raw_calls)))

    # ---------------- RE4 Bot 在但是创造模式 ⇒ 只切生存、不 spawn
    t4 = FakeTransport(bot={"mode": "creative", "pos": "5,6,7", "onground": "true"})
    r4 = run(t4, tmp / "f4")
    check("RE4", r4["exit"] == 0 and r4["gamemode_fixed"] and not spawns(t4)
          and r4["bot"].get("mode") == "survival",
          "创造模式 ⇒ gamemode survival（不 spawn）⇒ exit=%s fixed=%s mode=%s"
          % (r4["exit"], r4["gamemode_fixed"], r4["bot"].get("mode")))

    # ---------------- RE5 spawn 命令桥断（raw 回 None）⇒ 硬故障 exit 1（不许当成功）
    t5 = FakeTransport(bot=None, spawn_ok=False)
    r5 = run(t5, tmp / "f5")
    check("RE5", r5["exit"] == 1 and r5["spawned"] is False
          and any(s["status"] == "FAIL" for s in r5["steps"]),
          "spawn 命令失败 ⇒ exit=%s（★不许假装成功✗★）" % r5["exit"])

    # ---------------- RE6 spawn 发出去了但 Bot 一直不出现 ⇒ exit 1（回读是唯一真值）
    t6 = FakeTransport(bot=None, spawn_creates=False)
    r6 = run(t6, tmp / "f6", attempts=3)
    check("RE6", r6["exit"] == 1 and "bot absent" in (r6.get("reason") or "")
          and len(t6.post_calls) >= 3,
          "spawn 后 %d 次回读仍无 Bot ⇒ exit=%s reason=%s"
          % (len([c for c in t6.post_calls if "dshdigest" in c]), r6["exit"],
             (r6.get("reason") or "")[:40]))

    # ---------------- RE7 切生存命令失败（raw None）⇒ 硬故障 exit 1
    t7 = FakeTransport(bot={"mode": "creative", "pos": "1,2,3", "onground": "true"}, gm_ok=False)
    r7 = run(t7, tmp / "f7")
    check("RE7", r7["exit"] == 1 and any(s["id"] == "S3" and s["status"] == "FAIL"
                                         for s in r7["steps"]),
          "gamemode survival 失败 ⇒ exit=%s" % r7["exit"])

    # ---------------- RE8 Bot 在但 digest 缺 pos/onground ⇒ 部分未知 exit 2
    class TruncTransport(FakeTransport):
        def post(self, cmd, timeout=20.0):
            self.post_calls.append(cmd)
            if "dshdigest" in cmd:
                return "dshdigest reason=ok name=Bot mode=survival hp=20.0"   # 缺 pos/onground
            return ""
    t8 = TruncTransport()
    r8 = run(t8, tmp / "f8")
    check("RE8", r8["exit"] == 2 and "incomplete" in (r8.get("reason") or ""),
          "digest 缺字段 ⇒ exit=%s reason=%s（部分未知 ✗ 不是 PASS）"
          % (r8["exit"], (r8.get("reason") or "")[:44]))

    # ---------------- RE9 中继暂停旗：挂着 ⇒ 摘掉并报告；没挂 ⇒ SKIP；dry-run 不删
    fd = tmp / "flags9"
    fd.mkdir()
    (fd / "relay_hold").write_text("x", encoding="utf-8")
    t9 = FakeTransport(bot={"mode": "survival", "pos": "1,2,3", "onground": "true"})
    r9 = run(t9, fd)
    cleared = r9["exit"] == 0 and "relay_hold" in r9["flags_removed"] and not (fd / "relay_hold").exists()
    (fd / "relay_hold").write_text("x", encoding="utf-8")
    t9b = FakeTransport(bot=None)
    r9b = run(t9b, fd, dry_run=True)
    kept = r9b["exit"] == 0 and (fd / "relay_hold").exists() and not t9b.raw_calls
    check("RE9", cleared and kept,
          "relay_hold 摘要：live ⇒ 删了（%s）｜dry-run ⇒ 保留且零 /raw（%s）"
          % (cleared, kept))

    # ---------------- RE10 幂等连跑：第一次 spawn，第二次 ALREADY-READY 不再 spawn
    fd10 = tmp / "flags10"
    fd10.mkdir()
    t10 = FakeTransport(bot=None)
    a, b = run(t10, fd10), run(t10, fd10)
    r10 = b
    check("RE10", a["exit"] == 0 and b["exit"] == 0 and len(spawns(t10)) == 1
          and b["spawned"] is False,
          "连跑两次：spawn 总次数=%d（第二次幂等 ✓）" % len(spawns(t10)))

    # ---------------- M1 ★自检能红✗★：期望表取反必须能被发现
    def mismatch(pairs):
        return [(tag, got, want) for (tag, got, want) in pairs if got != want]
    good = [("RE1", r1["exit"] == 1, True), ("RE2", r2["exit"] == 0, True),
            ("RE3", len(spawns(t3)) == 0, True)]
    flipped = [(tag, got, not want) for (tag, got, want) in good]
    check("M1", mismatch(good) == [] and mismatch(flipped) != [],
          "★自检能红✗★：期望表取反 ⇒ 发现 %d 处差（判据本身可红 ✓）" % len(mismatch(flipped)))

    # ---------------- M2 计数器：断言数 ＋ 退出码三态都真跑过 ＋ raw/post 调用被记录
    codes = [r1["exit"], r2["exit"], r3["exit"], r4["exit"], r5["exit"], r6["exit"],
             r7["exit"], r8["exit"], r9["exit"], r10["exit"]]
    check("M2", len(RESULTS) >= 10 and set(codes) >= {0, 1, 2}
          and len(t2.raw_calls) >= 2,
          "计数器：断言 %d 条 ｜ 退出码集合 %s ｜ 假通道记录 raw=%d post=%d"
          % (len(RESULTS), sorted(set(codes)), len(t2.raw_calls), len(t2.post_calls)))
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

_reds = [t for (t, o) in RESULTS if not o]
print("")
print("=> recover %s（%d 条断言 ✗ 红 %d：%s）"
      % ("PASS ✓" if ok[0] else "FAIL", len(RESULTS), len(_reds), _reds or "无"))
print("RECOVER ok=%d checks=%d" % (1 if ok[0] else 0, len(RESULTS)))
sys.exit(0 if ok[0] else 1)
