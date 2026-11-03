#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""acp_talk.py —— ★游戏聊天 ⇄ 常驻 ACP 会话★（v2 ✓）

为什么有 v2 ✗（实测 ✓ 2026-09-23 ✓）：
  v1 给大脑的只有一句
      "%s 在游戏里对你说：%s（用一两句中文回他，口语，60 字以内）"
  ⇒ 三个后果 ✗：
    ① **没有人设** ✗ —— 「定制角色」这条要求在这条路上是断的 ✗
       （人设只在 `talk.py --brain harness` 那条路上生效 ✓ 两条路不一致 ✗）
    ② **没有实况** ✗ —— 它会瞎猜自己在哪 / 手里拿着什么 ✗
    ③ **没有"说了就得做"** ✗ —— 而换剖面之前它连工具都没有 ✗ ⇒ 表现就是"只会回话、不动手" ✗
       （这正是用户那句「让它干活它不运行」的**第二个**原因 ✓ 头一个是没有 mc 工具 ✓）

v2 的做法 ✓：**复用 `talk.py` 里那一整套任务书** ✓
  `T.build_task(人设 ✓ 实况 ✓ 上下文 ✓ 指令强制 ✓)` —— 一份实现 ✓ 不抄第二份 ✗（错题本老账 ✓）
  ⇒ 两条大脑路径（`--brain harness` / `--brain acp`）**看到的处境一致** ✓

链路 ✓：
  游戏聊天 → 本文件 → logs/acp_inbox.jsonl → acp_serve.py（常驻会话 ✓）
    → mc 那组 MCP 工具（★真的动手★ ✓）→ logs/acp_outbox.jsonl → /dshsay（出口唯一 ✓）

★"动没动手"的客观判据（不听它自述 ✗ 纪律② ✓）★ 两个都要看 ✓：
  · `logs/acp_outbox.jsonl` 里这一轮的 `updates.tool_call` 次数 ✓（ACP 自己报的 ✓）
  · `logs/mc_mcp.jsonl` 里这一时段**工具服务自己写的**记录条数 ✓（世界真值 ✓）
  ⇒ 判为"指令"却 **0 次** ⇒ ★打回重做一次★ ✓（把"你一个工具都没调"直接怼回去 ✓）

用法：py tools/acp_talk.py --once "你在干嘛"      # 走一整条链（含真的说出来 ✓）
      py tools/acp_talk.py --watch               # 常驻盯着聊天 ✓
      py tools/acp_talk.py --watch --force-exec  # 每句都当指令（说了就得做 ✓）
      py tools/acp_talk.py --watch --persona menghulu
"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "agent"))
import talk as T                     # noqa: E402  ★复用：人设/任务书/清洗/转义 ✓
from channel import Channel          # noqa: E402
from jobs_store import brief as JOBS_BRIEF   # noqa: E402  ★长任务账本 ✓ 一份实现 ✓
from jobs_store import runnable_jobs as RUNNABLE_JOBS   # noqa: E402
# ★★主动扳机（用户第 1 条 ✓ 2026-09-30 接上 ✓）★★ ✗
#   ★为什么要在**这里**接✗★：`start_all.ps1` 起的**就是它**✗（见 `Start-Svc "acp talk …"` ✓）
#     ⇒ ★它才是"真的在跑的那个"✗★；`talk.py --brain harness` 那条路**只在测试里用过** ✗
#     ⇒ 我原来只把扳机接进 `talk.Talk` ⇒ ★"测试里全绿、游戏里听不到"✗★（实机撞到 ✓ ⇒ P137 ✓）
#   ★口径✗★：**决策／渲染／发送全走 `speech_loop`**✗（`plan` ✓ `polish` ✓ `run` ✓）
#     本文件**不许**自己再写一套 ✗（P106 ✓）；出口仍然只有 `/dshsay` 一个 ✓
import speech_loop as SL              # noqa: E402
import jobs_store as JS               # noqa: E402  ★任务账本 ⇒ 播报/邀功/求助 ✓

# ★★自动续跑的那句话★★ ✓（用户原话：「长任务还有点吃力」✓ 见 jobs_store.py 的说明 ✓）
CONTINUE_PROMPT = (
    "（没有人跟你说话 ✓ 这是**自动续跑** ✓ 不是 Au_Sn 在问 ✓）\n"
    "你账本上还有**没做完**的活（见上面「你手上还没做完的活」那一段 ✓）\n"
    "⇒ 现在**只推进一步** ✓：\n"
    "   ① 先 `job_list` 看清楚第一步该干什么 ✓ 必要时 `bot_state` 看实况 ✓\n"
    "   ② 用工具把**这一步**做掉 ✓（别一口气贪多 ✗）\n"
    "   ③ 做完用 `job_step` 记一笔（note ✓ next_step ✓ evidence 填**客观证据** ✓）\n"
    "   ④ 整件活全做完了 ⇒ 用 `job_close` 收尾 ✓\n"
    "   ⑤ 中间卡住（缺料/缺工具/路不通）⇒ **如实**记进 job_step 并说清要什么 ✓\n"
    "最后**只输出一句**进度话（≤30 字 ✓ 比如「收了 33 株小麦 ✓ 下一步去取沙砾」✓）\n"
    "★不许假装账本不存在★ ✗ ★不许说\"等你指示\"★ ✗（没人跟你说话 ✓ 就是让你自己往前走 ✓）")


INBOX = ROOT / "logs" / "acp_inbox.jsonl"
OUTBOX = ROOT / "logs" / "acp_outbox.jsonl"
META = ROOT / "logs" / "acp_session.json"
MCPLOG = ROOT / "logs" / "mc_mcp.jsonl"
TALLLOG = ROOT / "logs" / "acp_talk.jsonl"
# ★"暂停自动续跑"的旗子★ ✗（2026-09-23 ✓）：`tools/check_all.py` 跑验收时会挂上它 ✓
#   为什么需要 ✗：验收里那些"跑完假人还在原地/在连通平台里"的判据 ✓
#     会被**自动续跑**把假人挪走而搅黄 ✗（实测：r8/r9 单跑 PASS ✓ 进总检就 FAIL ✗）
#   ⇒ 与其靠"记得先停中继"✗ 不如让它**自己看旗子** ✓（纪律做成结构 ✓ 见 P46 ✓）
HOLD = ROOT / "logs" / "relay_hold"
BOT = "Bot"

# ══ ★"催它干活"★ ✓（实测 2026-09-23 17:39 ✓ 用户原话：「bot, 你怎么不行动」）════════
# 为什么单列一组 ✗：这类话**一个动作动词都没有** ✗ ⇒ `T.looks_imperative` 判不出来 ✗
#   （实测回执：`force=False acted=False tool_log=0` ✓ ⇒ 它只回了句话 ✗ 正是用户在抱怨的事 ✗）
#   ⇒ 命中这组 ⇒ ①强制动手 ✓ ②★让它自己挑一件有用的活★ ✓ ③**不许反问"要不要我做"** ✗
#      （用户偏好原话：「这种不需问我，先执行」✓）
NUDGE_WORDS = ("不行动", "没行动", "不动弹", "怎么不动", "干活", "做事", "做点事",
               "动起来", "去干", "开始工作", "别闲着", "偷懒", "摸鱼", "不干活",
               "干点啥", "干些什么")


def main(argv: list[str]) -> int:
    def opt(name: str, default=None):
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    once = opt("--once")
    watch = ("--watch" in argv) or (once is None)
    persona_name = str(opt("--persona") or T.DEFAULT_PERSONA)
    force_all = "--force-exec" in argv
    limit = int(opt("--limit") or 80)
    timeout = float(opt("--timeout") or 300.0)
    # ★自动续跑★ ✓（长任务 ✓）：`--continue-every <秒>` ✓ 默认 90 ✓ `--no-continue` 关掉 ✓
    #   ① 只在**没人说话**的时候走（`cont_gap` 秒内有人说话就让位 ✓）
    #   ② 账本上**确实有没做完的活**才走 ✓
    #   ③ 一轮最多连着推 `--continue-max` 次 ✓（默认 6 ✓ 免得它自己空转烧钱 ✗）
    #   ④ 一轮里**一次工具都没调** ⇒ 立刻停 ✓ 并且说出来 ✗
    cont_on = "--no-continue" not in argv
    cont_every = float(opt("--continue-every") or 90.0)
    cont_max = int(opt("--continue-max") or 6)
    cont_gap = float(opt("--continue-gap") or 45.0)

    ch = Channel("cmd0", verbose=False)

    def raw(t: str, tmo: float = 60.0) -> str:
        try:
            return (ch.cmd(t, timeout=tmo, allow_str=True).text() or "").strip()
        except Exception as e:
            return "ERR:%s" % type(e).__name__

    def asbot(t: str, tmo: float = 60.0) -> str:
        return raw("execute as %s at %s run %s" % (BOT, BOT, t), tmo)

    # ── 前提检查（★必须的 ✗★）────────────────────────────────────────────
    dig = asbot("dshdigest 4")
    if "name=Bot" not in dig:
        print("PRECHECK FAIL: no fake player Bot")
        return 1
    if not META.is_file():
        print("PRECHECK FAIL: no acp_session.json (is acp_serve.py running?)")
        return 1
    sid = json.loads(META.read_text(encoding="utf-8")).get("sessionId", "?")
    print("PRECHECK ok; session=%s persona=%s force=%s"
          % (sid[:12], persona_name, force_all))

    # ── ★人设★ ✓（改文件立刻生效 ✓ 不用重启 ✓ 见 talk.py 的 reload ✓）──────
    state_p = {"at": 0.0}
    persona = {"text": T.load_persona(persona_name), "mtime": 0.0, "name": persona_name}

    def persona_path() -> Path:
        return T.PERSONA_DIR / (persona["name"] + ".md")

    def persona_now() -> str:
        try:
            m = persona_path().stat().st_mtime
        except Exception:
            m = 0.0
        if m and m != persona["mtime"]:
            if persona["mtime"]:
                print("PERSONA reload %s (mtime changed)" % persona_path().name)
            persona["text"] = T.load_persona(persona["name"])
            persona["mtime"] = m
        return persona["text"]

    # ★"在游戏里直接给设定"★ ✓（用户要求"给一个输入人设的地方" ✓）
    def set_persona(text: str, source: str) -> int:
        text = (text or "").strip()[:6000]
        if not text:
            return 0
        T.PERSONA_DIR.mkdir(parents=True, exist_ok=True)
        p = T.PERSONA_DIR / "current.md"
        p.write_text(text + "\n", encoding="utf-8", newline="\n")
        try:
            with (T.PERSONA_DIR / "current.meta.jsonl").open("a", encoding="utf-8",
                                                             newline="\n") as f:
                f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "source": source, "chars": len(text),
                                    "head": text[:60]}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        persona["name"] = "current"
        persona["text"] = text
        try:
            persona["mtime"] = p.stat().st_mtime
        except Exception:
            persona["mtime"] = 0.0
        return len(text)

    # ── ★实况★ ✓（每 30 秒最多读一次 ✓ 让回答有据可依 ✓）───────────────────
    def state_now() -> str:
        if time.time() - state_p["at"] < 30 and state_p.get("text"):
            return state_p["text"]
        d = asbot("dshdigest 6", 60.0)
        state_p["at"] = time.time()
        state_p["text"] = (d[:300] or "（读不到状态 ✗）")
        return state_p["text"]

    def mc_tool_calls_since(t0: float) -> int:
        """★工具服务自己写的记录★ ✓（世界真值 ✓ 不听自述 ✗）"""
        if not MCPLOG.is_file():
            return 0
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0))
        n = 0
        try:
            for line in MCPLOG.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line).get("at", "") >= stamp:
                        n += 1
                except Exception:
                    continue
        except Exception:
            return 0
        return n

    hist: list[str] = []

    def is_nudge(msg: str) -> bool:
        """★这句是不是"催它干活"★ ✓（判据见 NUDGE_WORDS 的注释 ✓）"""
        m = (msg or "").strip()
        return any(w in m for w in NUDGE_WORDS)

    def ask(text: str, tmo: float) -> dict:
        """投进收件箱 ⇒ 等发件箱那一条 ⇒ **返回整条记录** ✓（含 updates ✓ 便于判"动手"✓）"""
        rid = "talk-" + uuid.uuid4().hex[:8]
        with INBOX.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"id": rid, "text": text}, ensure_ascii=False) + "\n")
        t0 = time.time()
        while time.time() - t0 < tmo:
            time.sleep(1.0)
            if not OUTBOX.is_file():
                continue
            for line in OUTBOX.read_text(encoding="utf-8").splitlines()[-60:]:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("id") == rid:
                    r["_wall"] = round(time.time() - t0, 1)
                    return r
        return {"id": rid, "answer": "", "stop": "TIMEOUT", "_wall": tmo}

    def esc(s: str) -> str:
        """★出口必须转义★ ✗（v1 当场漏过一次 ✓ 代价是游戏里乱码 ✗ 见 P13/P39 ✓）"""
        return "".join(c if 32 <= ord(c) < 127 else "\\u%04x" % ord(c)
                       for c in (s or "")).replace('"', "'")

    def say(msg: str) -> str:
        return asbot("dshsay %s" % esc(msg))

    def clean_out(s: str) -> str:
        """出口清洗 ✓ 复用 `T.clean` ✓ 再加两道游戏聊天不吃的 ✗（markdown ✓ 换行 ✓）"""
        s = re.sub(r"\*\*|__|`{1,3}", "", s or "")          # 粗体/反引号 ⇒ 聊天里是噪音 ✗
        s = re.sub(r"^\s*[-*•]\s*", "", s, flags=re.M)      # 行首列表符号 ✓
        s = re.sub(r"^\s*#+\s*", "", s, flags=re.M)         # 标题 ✓
        return T.clean(s, limit=limit)

    def build(who: str, msg: str, force: bool, redo: bool = False,
              prev_note: str = "", nudge: bool = False) -> str:
        """★这一轮的任务书★ ✓ —— 直接复用 talk.py 的 `build_task` ✓（一份实现 ✓）"""
        task = T.build_task(persona_now(), state_now(),
                            "\n".join(hist[-6:]) or "（这是今天第一句 ✓）",
                            who, msg, force=force, prev=prev_note)
        # ★长任务账本★ ✓（`jobs/*.json` ✓ 跨会话/跨重启 ✓）——
        #   插在「你要做的」**之前** ✓：让规则仍然在最后（离模型最近 ✓）
        try:
            jb = JOBS_BRIEF()
        except Exception:
            jb = ""
        if jb:
            marker = "──────── 你要做的 ────────"
            if marker in task:
                head, tail = task.split(marker, 1)
                task = head + jb + "\n" + marker + tail
            else:
                task = task + "\n" + jb
        if nudge:
            task += (
                "\n──────── ★★他在催你干活★★ ────────\n"
                "他这句话**不是闲聊** ✗ —— 是在抱怨你**不动手** ✓\n"
                "⇒ ★自己挑一件对当前处境有用的活干起来★ ✓\n"
                "   （先看 `bot_inventory` ✓ 再看 `scan` ✓ 再决定 ✓\n"
                "    有砂砾就筛 ✓ 有庄稼就收 ✓ 有矿石就挖 ✓ 背包满了就整理/存起来 ✓）\n"
                "⇒ ★**不要问他\"要不要我做X\"** ✗★ —— 他的偏好是**先做**再汇报 ✓\n"
                "⇒ 先 `say` 一句**短的**（≤15 字 ✓ 例如「那我筛砂砾去」✓）⇒ 再动手 ✓\n"
                "⇒ 做完照实汇报 ✓（干了什么 ✓ 拿到什么 ✓ 失败就说清为什么 ✗）\n"
                "最后仍然**只输出你要说出口的那一两句话** ✓\n")
        if redo:
            task += (
                "\n──────── ★★打回重做★★ ────────\n"
                "你上一轮**只回了话** ✗ —— 中继层数过你的工具调用：**0 次** ✗\n"
                "他那一句是**指令** ✓ ⇒ ★只回话等于没做★ ✗\n"
                "⇒ 现在**立刻**去调 mc 的工具把这件事做掉 ✓ 然后照实回结果 ✓\n"
                "（做不到也要留下失败的回执 ✓ 并说清为什么 ✗）\n"
                "最后仍然**只输出你要说出口的那一两句话** ✓\n")
        return task

    def turn(who: str, msg: str, force: bool, nudge: bool = False) -> tuple[str, dict]:
        """走一轮 ✓ 含"说了就得做"的强制重做 ✓ 返回 (要说的话 ✓, 记录 ✓)"""
        force = force or nudge
        t0 = time.time()
        rec = ask(build(who, msg, force, nudge=nudge), timeout)
        n_acp = int(((rec.get("updates") or {}).get("tool_call") or 0))
        n_log = mc_tool_calls_since(t0)
        acted = (n_acp > 0) or (n_log > 0)
        print("TURN sec=%s nudge=%s tool_call_acp=%d tool_log=%d acted=%s stop=%s"
              % (rec.get("_wall"), nudge, n_acp, n_log, acted, rec.get("stop")))
        if force and not acted and rec.get("stop") != "TIMEOUT":
            print("NOT ACTED -> redo once (force=True)")
            t1 = time.time()
            rec2 = ask(build(who, msg, force, redo=True, nudge=nudge), timeout)

            n_acp2 = int(((rec2.get("updates") or {}).get("tool_call") or 0))
            n_log2 = mc_tool_calls_since(t1)
            if (n_acp2 > 0) or (n_log2 > 0):
                rec2["_redo"] = True
                rec2["_redo_seen"] = {"acp": n_acp2, "log": n_log2}
                rec = rec2
                acted = True
            else:
                rec = rec2
                print("REDO still 0 tools (acp=%d log=%d)" % (n_acp2, n_log2))
        rec["_acted"] = acted
        rec["_tool_acp"] = n_acp
        rec["_tool_log"] = n_log
        txt = clean_out(rec.get("answer") or "")
        return txt, rec

    def log(obj: dict) -> None:
        obj = dict(obj)
        obj.setdefault("at", time.strftime("%Y-%m-%d %H:%M:%S"))
        obj.setdefault("brain", "acp")
        obj.setdefault("persona", persona["name"])
        with TALLLOG.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # ── `--once`：走一整条链 ✓（含真的说出来 ✓）便于验收 ──────────────────
    if once is not None:
        print("ASK: %s" % once.encode("ascii", "replace").decode("ascii")[:80])
        force = force_all or T.looks_imperative(once)
        cue = is_nudge(once)
        out, rec = turn("Au_Sn", once, force, nudge=cue)
        print("ANSWER len=%d force=%s nudge=%s" % (len(out), force, cue))
        r = say(out)
        print("SAY -> %s" % r[:120])
        log({"kind": "once", "heard": once, "said": out, "force": force, "nudge": cue,
             "acted": rec.get("_acted"), "tool_acp": rec.get("_tool_acp"),
             "tool_log": rec.get("_tool_log"), "stop": rec.get("stop"),
             "sec": rec.get("_wall"), "redo": rec.get("_redo", False)})
        return 0

    # ── `--watch`：常驻盯着聊天 ✓ ──────────────────────────────────────────
    #   ★外加"没人催也往前走"★ ✓（长任务的关键 ✓ 见 CONTINUE_PROMPT ✓）
    print("WATCH: reading chat, answering via ACP session (Ctrl+C to stop)")
    print("CONTINUE: every %ss if open jobs exist and nobody is talking (max %d in a row)%s"
          % (cont_every, cont_max, " [disabled]" if not cont_on else ""))
    cursor = None
    last_hold = 0.0
    last_reply = 0.0
    last_continue = time.time()
    cont_run = 0
    fails = 0
    # ── ★主动扳机（用户第 1 条 ✓）★ ────────────────────────────────────────
    #   `--no-speech` 一键关掉 ✓（跟 `talk.py` 同一个开关名 ✓ 出事能退 ✓）
    speech_on = not bool(opt("no-speech"))
    loop = SL.Loop(gate=SL.S.Gate(budget_per_min=int(opt("speech-budget") or 6)),
                   lines=SL.load_lines(),
                   min_idle=float(opt("speech-idle") or 240.0))
    import persona_render as PR
    import random as _random
    try:
        render_cfg = PR.load()
    except Exception:
        render_cfg = dict(PR.DEFAULT_CFG)
    render_rng = _random.Random()
    job_snap: dict = {}
    it = 0                                   # ★心跳用的轮次计数✗★（P139 ✓）
    # ★stdout 重定向 ⇒ 块缓冲 ⇒ 日志看不见 ✗（本项目早有这条教训 ✓ 见 talk.py 与 P126 ✓）
    #   ⇒ 中继的日志必须**行缓冲** ✓ 否则"它在干什么"只能靠猜 ✗
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
    print("SPEECH: %s (budget=%d/min, idle=%ss)" %
          ("on" if speech_on else "OFF", loop.gate.budget_per_min, int(loop.min_idle)))
    while True:
        it += 1
        try:
            time.sleep(2.0)
            now = time.time()
            if now - last_hold > 10:
                asbot("dshquiet canned off", 20.0)   # 让模组 canned 快嘴让位 ✓（不刷 LAST_CMD_TICK ✓）
                last_hold = now
            # ★★`since` 要用**我们自己处理到哪**✗★★（2026-09-30 **实机**抓到 ✓ ⇒ P139 ✓）
            #   ✗ 原来用回执头里的 `cursor=` ✗ —— 那是**环的末尾**（模组那边的事件序号 ✓）
            #     ⇒ 一旦"轮询间隔内来了多条事件"／"这一批我们没处理完" ✗
            #       ⇒ `cursor` 已经跑到末尾 ✗ ⇒ 下次 `dshevents <末尾>` **把中间那些跳过**✗✗
            #   ★实测证据✗★：心跳里 `cursor=255` 而 `seen_seq=253` ✗ ——
            #     中间那两条（#254/#255）**再也没人提起** ✗（服务端日志里我们一句都没说 ✓）
            #   ⇒ 口径 ✓：**水位＝`loop.seen_seq`**（我们真的处理到哪 ✗ 不是对面说末尾在哪 ✗）
            line = asbot("dshevents" if cursor is None else "dshevents %d" % loop.seen_seq, 60.0)
            m = re.search(r"cursor=(\d+)", line)
            if m:
                cursor = int(m.group(1))
            raw_events = [s.strip() for s in line.split("|")[1:] if s.strip()]
            heard: list[tuple[str, str]] = []
            for seg in line.split("|")[1:]:
                mm = re.search(r"chat who=(\S+) len=(\d+) msg=(.*)$", seg.strip())
                if not mm:
                    continue
                who, msg = mm.group(1), T.unesc(mm.group(3))
                if who == BOT:
                    continue
                heard.append((who, msg))
                hist.append("%s: %s" % (who, msg))
            del hist[:-20]
            # ── ★主动扳机：★先把这一批事件过一遍闸 ✗ 再谈"要不要答人" ✓ ───────
            #   顺序是**有意的**✗：主动那几句带延迟（≤6s ✓）⇒ 放在应答**前面**
            #     ⇒ 万一它正在"酝酿" ✓ 玩家的话也只会晚 2 秒读到 ✓ 不会丢 ✓
            #     （`heard` 是这一批已经读进来的 ✓ 迟一轮处理而已 ✓）
            #   ★危险开关✗★：`logs/relay_hold` 旗子挂着时（跑验收 ✓）**一律不说** ✗
            #     —— 验收里那些"假人还在原地 ✓ 平台连通"的判据会被主动挪动/说话搅黄 ✓
            #       （与"自动续跑也要看旗子"同一个理由 ✓ 见 P46 ✓）
            if speech_on and not HOLD.exists():
                try:
                    tr, job_snap = SL.job_transitions(job_snap, JS.all_jobs())
                except Exception:
                    tr = []
                try:
                    # ★★出口复用这个文件里**已有的** `say()`✗★★（P106 ✓）
                    #   ★不许在这儿手搓 `dshsay`✗★ —— 它必须过 `esc()` ✗
                    #     （v1 漏过一次 ⇒ 游戏里乱码 ✓ 见 P13/P39 ✓ ★我刚差点又漏一次✗★）
                    said = SL.run(raw_events, loop, lambda a: say(a.text or a.line),
                                  transitions=tr, cfg=render_cfg, rng=render_rng,
                                  audit=ROOT / "logs" / "speech_log.jsonl", tag="主动说")
                except Exception as e:
                    print("SPEECH FAIL:", e)
                    said = -1
            # ── ★心跳（2026-09-30 加 ✓ ⇒ P139 ✓）────────────────────────────
            #   ★为什么加✗★：中继"不出声"时，我看不出是
            #     ①**没收到事件**（cursor/new=0 ✗）还是 ②**收到了但没说话**（闸门/台词库 ✗）
            #     ⇒ 而它的 stdout 重定向之后是**块缓冲**✗ ⇒ 日志里一个字都没有 ✗
            #     ⇒ ★把"每轮看到什么"写成**文件**✗★ ⇒ 一眼可查 ✓ 不用猜 ✓
            try:
                (ROOT / "logs" / "relay_heartbeat.json").write_text(json.dumps({
                    "at": time.strftime("%H:%M:%S"), "iter": it, "cursor": cursor,
                    "events": len(raw_events), "seen_seq": loop.seen_seq,
                    "said": said if "said" in dir() else None,
                    "hold": bool(HOLD.exists()), "speech_on": bool(speech_on),
                    "chat": len(heard)}, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            # ★一条都不许丢★ ✗：先把这一批聊天全读完 ✓ 再挑**最后一条**该答的答 ✓
            #   （v1 是"答完就 break"✗ ⇒ 同一批里后面的聊天被丢掉 ✗）
            target = None
            for who, msg in heard:
                low = msg.lower()
                if T.parse_persona_set(msg):
                    target = (who, msg)          # 给设定 ✓ 一定处理 ✓
                    continue
                if not (("bot" in low) or ("机器人" in msg) or any(
                        x in msg for x in ("?", "？", "吗", "怎么", "为什么", "啥", "什么"))):
                    continue
                target = (who, msg)
            if target is None:
                # ★没人说话 ⇒ 看看账本上有没有没做完的活 ✓ 有就**自己往前推一步** ✓
                #   （这就是"长任务"缺的那一环 ✗：光有账本没人推 ⇒ 活还是停着 ✗）
                if (cont_on and not HOLD.exists() and time.time() - last_reply > cont_gap
                        and time.time() - last_continue > cont_every
                        and cont_run < cont_max):
                    openn = []
                    try:
                        openn = RUNNABLE_JOBS()      # ★只挑"现在就该动"的★ ✓（在等的活会被跳过 ✓）
                    except Exception:
                        openn = []
                    if openn:
                        last_continue = time.time()
                        cont_run += 1
                        print("CONTINUE #%d/%d -> %s"
                              % (cont_run, cont_max,
                                 openn[0]["id"].encode("ascii", "replace").decode("ascii")))
                        out, rec = turn("(自动续跑)", CONTINUE_PROMPT, True, nudge=False)
                        if rec.get("_acted"):
                            print("CONTINUE acted ok (tool_log=%s)" % rec.get("_tool_log"))
                        else:
                            # ★连续两轮没动手 ⇒ 停下并**大声说**✗（不许悄悄空转 ✗）
                            print("CONTINUE dry round -> stop auto-run (no tool calls)")
                            cont_run = cont_max
                        if out:
                            print("SAY -> %s" % say(out)[:120])
                            log({"kind": "continue", "said": out, "job": openn[0]["id"],
                                 "round": cont_run, "acted": rec.get("_acted"),
                                 "tool_log": rec.get("_tool_log"), "stop": rec.get("stop"),
                                 "sec": rec.get("_wall")})
                        last_reply = time.time()
                fails = 0
                continue
            who, msg = target
            if now - last_reply < 4.0:
                continue
            print("HEARD %s: %s" % (who, msg.encode("ascii", "replace").decode("ascii")[:60]))

            # ① 给设定 ⇒ 直接落盘 ✓ **当轮生效** ✓ 不用麻烦大脑 ✓
            ptxt = T.parse_persona_set(msg)
            if ptxt:
                n = set_persona(ptxt, "chat:%s" % who)
                out = "记住了，%d 个字。" % n
                print("PERSONA set chars=%d" % n)
                print("SAY -> %s" % say(out)[:120])
                log({"kind": "persona_set", "who": who, "heard": msg, "chars": n,
                     "said": out})
                last_reply = time.time()
                fails = 0
                continue

            # ② 正常一轮 ✓（是"指令"就必须真做 ✓ 见 turn() 的打回重做 ✓；
            #    "催它干活" ⇒ 自己挑一件活干 ✓ 见 NUDGE_WORDS ✓）
            cue = is_nudge(msg)
            force = force_all or T.looks_imperative(msg)
            # ★人一开口 ⇒ 自动续跑让位 ✓ 并且额度**重置** ✓
            #   （不然"连着 6 次"的计数会跨着好几段沉默累计 ⇒ 你一说话它反而不推了 ✗）
            cont_run = 0
            last_continue = time.time()
            if cue:
                print("NUDGE detected -> force action, brain picks the job")
            out, rec = turn(who, msg, force, nudge=cue)
            if out:
                print("SAY -> %s" % say(out)[:120])
                log({"kind": "reply", "who": who, "heard": msg, "said": out,
                     "force": force, "nudge": cue, "acted": rec.get("_acted"),
                     "tool_acp": rec.get("_tool_acp"), "tool_log": rec.get("_tool_log"),
                     "stop": rec.get("stop"), "sec": rec.get("_wall"),
                     "redo": rec.get("_redo", False)})
                last_reply = time.time()
            else:
                print("EMPTY ANSWER (stop=%s) -> nothing said" % rec.get("stop"))
                log({"kind": "empty", "who": who, "heard": msg, "stop": rec.get("stop")})
            fails = 0
        except KeyboardInterrupt:
            print("bye")
            return 0
        except Exception as e:
            # ★★停止矩阵✗★★（参考外部同题项目 ✓ 2026-10-02 ✓ 治我们自己的一个老毛病 ✓）
            #   ★老毛病✗★：中继对着**死世界**无限轮询 ✗ 网关队列一路撞到 **256** ✗
            #     （实账：有一次轮询了 8 小时 ✓ 开局前必须手工清队列 ✓）
            #   ★口径（抄他们的形状 ✓）✗★：
            #     ① ★4xx/协议/授权类 ⇒ **立刻停**✗★（重试永远不会好 ✓）
            #     ② ★网络/5xx/桥不可用 ⇒ **退避重试** ✓ 但**封顶**✗★
            #     ③ ★连续失败到阈值 ⇒ 落一个 `logs/relay_hold` 旗子 ＋ **退出**✗★
            #        （★旗子是我们已有的机制 ✓ 中继自己看见就不动手 ✓★）
            fatal = any(k in type(e).__name__ for k in
                        ("Auth", "Protocol", "Value", "Key", "Permission", "Forbidden"))
            fails += 1
            if fatal:
                print("★停✗★：%s: %s ⇒ ★这类错误重试不会好 ✗ 直接停 ✓★"
                      % (type(e).__name__, str(e)[:120]))
                try:
                    (ROOT / "logs" / "relay_hold").write_text(
                        "acp_talk 停于 %s：fatal %s\n" % (time.strftime("%H:%M:%S"),
                                                          type(e).__name__), encoding="utf-8")
                except Exception as e:
                    # 记录：停旗没写下去 ⇒ 中继"以为已经停了"（不许静默）
                    print("[记录] 停旗写不出（%s）⇒ 中继仍会自动续跑"
                          % type(e).__name__, file=sys.stderr)
                return 2
            if fails >= 10:
                print("★停✗★：桥连续 **%d** 次不可用 ⇒ ★不再自动轮询✗★"
                      "（★免得把网关队列撞满 ✗ 要恢复：删 logs/relay_hold 或重跑 start_all ✓★）" % fails)
                try:
                    (ROOT / "logs" / "relay_hold").write_text(
                        "acp_talk 停于 %s：连续 %d 次失败\n"
                        % (time.strftime("%H:%M:%S"), fails), encoding="utf-8")
                except Exception as e:
                    # 记录：停旗没写下去 ⇒ 中继"以为已经停了"（不许静默）
                    print("[记录] 停旗写不出（%s）⇒ 中继仍会自动续跑"
                          % type(e).__name__, file=sys.stderr)
                return 2
            wait = min(20.0, 2.0 * fails)
            print("bridge/err (%d): %s ; retry in %.0fs" % (fails, type(e).__name__, wait))
            time.sleep(wait)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
