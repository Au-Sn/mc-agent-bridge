#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain.py — 大脑层：让大模型来"决定做什么"，但所有执行都必须经过技能层的验收

与参考项目的对应关系：
  mindcraft / MineBot 那一类项目的结构是「LLM 大脑 + 游戏内身体」。
  我们这里身体是 Carpet 假人（服务端权威），手脚是 ComputerCraft 计算机，
  大脑就是这一层。模型每一回合做的事只有一件：**从技能表里挑一个技能并给参数**。

三条铁律（写在代码里，不靠提示词自觉）：
  1. 模型不能直接发游戏指令，只能说技能名 —— 命令注入从结构上被排除。
  2. 技能执行完必须有世界状态验收（技能层负责），失败会把错误原文回给模型。
  3. 同一个技能+同一组参数连续重复 3 次 → 判定"它在原地打转"，
     注入一条提示并把这件事写进日志，避免无限烧钱。

API：任何 OpenAI 兼容端点都可以（只用到 chat/completions + tool calling）。
环境变量：
    AGENT_API_BASE   默认 https://api.openai.com/v1
    AGENT_API_KEY    没有它就只能跑 --script 脚本模式
    AGENT_MODEL      默认 gpt-4o-mini

用法：
    py agent/brain.py ask "砍一棵树，把木板放进箱子，然后回来" --steps=12
    py agent/brain.py plan "帮我造一个平台"          # 只出计划，不执行（安全预览）
    py agent/brain.py script agent/plans/smoke.json  # 不用 API，跑确定性脚本
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channel import Channel, BridgeError      # noqa: E402
# ★★2026-11-03（§79.543 联调时发现，HEAD 既有 bug）✗★★：`channel.py` 会
#   `sys.path.insert(0, tools/)` 并 `import paths` ⇒ 此时 `memory` 会先解析到
#   `tools/memory.py`（没有 Facts/GoalStack/Journal）⇒ `py tools/talk.py --help` 直接崩 ✗
#   ⇒ 在这几个同名模块前**再把 agent/ 放回最前**（agent/memory.py 才是这里要的 ✓）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory import Facts, GoalStack, Journal   # noqa: E402
from reflex import Reflex                      # noqa: E402
from skills import Skills                      # noqa: E402
from world import World                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system.md"


# --------------------------------------------------------------------------- #
# LLM 客户端（纯标准库，避免额外依赖）
# --------------------------------------------------------------------------- #

class LLM:
    def __init__(self, base: str | None = None, key: str | None = None,
                 model: str | None = None, timeout: float = 120.0):
        self.base = (base or os.environ.get("AGENT_API_BASE") or "https://api.openai.com/v1").rstrip("/")
        self.key = key or os.environ.get("AGENT_API_KEY") or ""
        self.model = model or os.environ.get("AGENT_MODEL") or "gpt-4o-mini"
        self.timeout = timeout
        self.calls = 0
        self.usage = {"prompt": 0, "completion": 0, "total": 0}

    def available(self) -> bool:
        return bool(self.key)

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             temperature: float = 0.2) -> dict:
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        req = urllib.request.Request(
            self.base + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer %s" % self.key},
            method="POST")
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise BridgeError("模型接口返回 HTTP %s：%s" % (e.code, detail))
        except Exception as e:
            raise BridgeError("连不上模型接口 %s：%s: %s（沙箱可能禁止外网，"
                              "或需要设置 AGENT_API_BASE）" % (self.base, type(e).__name__, e))
        u = data.get("usage") or {}
        for k in ("prompt", "completion", "total"):
            self.usage[k] += int(u.get(k + "_tokens", 0) or 0)
        try:
            return data["choices"][0]["message"]
        except Exception:
            raise BridgeError("模型返回格式不是 OpenAI 兼容格式：%s"
                              % json.dumps(data, ensure_ascii=False)[:400])


# --------------------------------------------------------------------------- #
# 大脑
# --------------------------------------------------------------------------- #

class Brain:
    def __init__(self, skills: Skills, world: World, reflex: Reflex | None = None,
                 llm: LLM | None = None, dry_run: bool = False, verbose: bool = True):
        self.skills = skills
        self.w = world
        self.reflex = reflex
        self.llm = llm or LLM()
        self.dry_run = dry_run
        self.verbose = verbose
        self.journal = Journal("brain")
        self.goals = GoalStack()
        self.facts = Facts()
        self.history: list[dict] = []
        self._recent: list[str] = []

    # -- 提示词 -------------------------------------------------------------- #

    def base_prompt(self) -> str:
        if PROMPT_PATH.is_file():
            txt = PROMPT_PATH.read_text(encoding="utf-8")
        else:
            txt = "你是一台 Minecraft 假人的大脑。只能用给定的技能。"
        return (txt
                + "\n\n## 你可以用的技能\n" + self.skills.help_text()
                + "\n\n## 已知事实（只有核实过的才在这里）\n" + self.facts.text()
                + "\n\n## 目标栈\n" + self.goals.text())

    def state_message(self, goal: str, events: list[dict] | None = None) -> str:
        parts = ["## 当前世界状态\n" + self.w.text()]
        if events:
            parts.append("## 刚才发生的事（反射层记录）\n" + "\n".join(
                "- [%s] %s" % (e.get("kind"), e.get("text")) for e in events))
        if self.history:
            parts.append("## 你刚才的动作与结果\n" + "\n".join(self.history[-6:]))
        parts.append("## 本次目标\n" + goal)
        parts.append("请只输出一次技能调用（可以先用 scan/verify 看清情况）。"
                     "全部完成时调用 done。")
        return "\n\n".join(parts)

    # -- 一回合 -------------------------------------------------------------- #

    def step(self, goal: str, events: list[dict] | None = None,
             tools: list[dict] | None = None) -> list[dict]:
        """问模型一次，并执行它挑的技能。返回这一回合的技能执行结果列表。"""
        msgs = [{"role": "system", "content": self.base_prompt()},
                {"role": "user", "content": self.state_message(goal, events)}]
        tools = tools if tools is not None else self.skills.tools()
        msg = self.llm.chat(msgs, tools=tools)
        calls = msg.get("tool_calls") or []
        results: list[dict] = []

        if not calls:
            text = (msg.get("content") or "").strip()
            self.history.append("（模型没有调用技能）%s" % text[:200])
            if self.verbose:
                print("[大脑] 模型没有调用技能，只说：%s" % text[:300])
            return [{"ok": False, "error": "模型没有调用技能", "said": text}]

        for call in calls[:2]:                      # 一回合最多执行两个，防止连环误操作
            fn = (call.get("function") or {})
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            if self.dry_run:
                results.append({"ok": True, "skill": name, "args": args,
                                "evidence": "【预览模式】没有真的执行"})
                self.history.append("（预览）%s %s" % (name, json.dumps(args, ensure_ascii=False)))
                continue
            out = self.skills.run(name, args)
            out["args"] = args
            results.append(out)
            self.history.append("%s(%s) → %s" % (name, json.dumps(args, ensure_ascii=False),
                                                 (out.get("evidence") or out.get("error") or "")[:160]))
            # 原地打转检测：同技能同参数连续 3 次
            sig = "%s:%s" % (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
            self._recent = (self._recent + [sig])[-6:]
            if self._recent.count(sig) >= 3:
                warn = ("检测到原地打转：%s 已经重复 3 次，说明方法有问题，"
                        "请换一个思路或先 scan/verify 看清情况。" % sig)
                self.history.append("【系统提示】" + warn)
                self.journal.write("loop_warning", summary=warn)
                if self.verbose:
                    print("[!] " + warn)
            if out.get("finished"):
                self.done_flag = True
        return results

    # -- 主循环 -------------------------------------------------------------- #

    def run(self, goal: str, max_steps: int = 12, tools: list[dict] | None = None) -> dict:
        if not self.llm.available() and not self.dry_run:
            return {"ok": False, "error": "没有 AGENT_API_KEY，无法调用模型。"
                                          "可以先用 --dry-run 预览，或跑脚本模式。"}
        self.goals.push(goal, note="brain.run")
        self.journal.write("goal", summary=goal)
        self.done_flag = False
        log: list[dict] = []
        for i in range(max_steps):
            if self.verbose:
                print("\n===== 第 %d/%d 回合 =====" % (i + 1, max_steps))
            events = self.reflex.drain() if self.reflex else []
            try:
                results = self.step(goal, events, tools=tools)
            except BridgeError as e:
                self.journal.write("error", summary=str(e))
                return {"ok": False, "error": str(e), "steps": i}
            log.append({"step": i + 1, "results": results})
            if getattr(self, "done_flag", False) and not self.dry_run:
                self.goals.close("done", note=(results[-1].get("evidence") or "")[:200])
                return {"ok": True, "finished": True, "steps": i + 1, "log": log,
                        "usage": self.llm.usage}
        self.goals.close("shelved", note="步数用尽")
        return {"ok": False, "error": "步数用尽仍未完成", "steps": max_steps, "log": log,
                "usage": self.llm.usage}

    # -- 确定性脚本模式（不用 API，也能演示与回归测试） ---------------------- #

    def run_script(self, plan_path: Path) -> dict:
        """plan 格式：[{"skill": "scan", "args": {"radius": 5}, "expect_ok": true}, ...]"""
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        steps = plan.get("steps") if isinstance(plan, dict) else plan
        if not isinstance(steps, list):
            return {"ok": False, "error": "plan 必须是步骤数组"}
        out_log = []
        for i, st in enumerate(steps):
            name = st.get("skill")
            args = st.get("args") or {}
            want = st.get("expect_ok", True)
            note = st.get("note", "")
            if self.verbose:
                print("\n--- 脚本第 %d/%d 步：%s %s %s" % (i + 1, len(steps), name,
                                                          json.dumps(args, ensure_ascii=False), note))
            r = self.skills.run(name, args)
            out_log.append({"step": i + 1, "skill": name, "ok": r.get("ok"),
                            "evidence": r.get("evidence"), "error": r.get("error")})
            if bool(r.get("ok")) != bool(want) and st.get("strict", True):
                return {"ok": False, "failed_at": i + 1, "log": out_log,
                        "error": "第 %d 步 %s 的验收结果与预期不符（预期 ok=%s）"
                                 % (i + 1, name, want)}
        return {"ok": True, "log": out_log}


# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    mode = argv[0]
    dry = "--dry-run" in argv
    allow_scaffold = "--allow-scaffold" in argv
    steps = 12
    for a in argv:
        if a.startswith("--steps="):
            steps = int(a.split("=", 1)[1])

    ch = Channel("cmd0")
    w = World(ch)
    sk = Skills(ch, w, allow_scaffold=allow_scaffold)
    rx = Reflex(w, ch, skills=sk, dry_run=True)     # 大脑开跑时反射层只观察（避免抢指令）
    br = Brain(sk, w, reflex=rx, dry_run=dry)

    if mode == "plan":
        goal = " ".join(a for a in argv[1:] if not a.startswith("--"))
        r = br.run(goal, max_steps=steps)
    elif mode == "ask":
        goal = " ".join(a for a in argv[1:] if not a.startswith("--"))
        rx.paused = False
        rx.start()
        try:
            r = br.run(goal, max_steps=steps)
        finally:
            rx.stop()
    elif mode == "script":
        r = br.run_script(Path(argv[1]))
    else:
        print("未知模式：%s（可用 ask / plan / script）" % mode)
        return 2
    print("\n" + json.dumps(r, ensure_ascii=False, indent=1)[:4000])
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
