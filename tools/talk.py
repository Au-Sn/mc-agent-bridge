#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""talk.py —— ★让假人**真的对话**★（DeepSeek / 任何 OpenAI 兼容端点 ✓）

用户要求 ✓：「**对话能调用 deepseek 吗，不能是只有几个简单的词**」✓
⇒ 这个工具就是那条路 ✓。**现有客户端一条都不用改** ✓ ——
`agent/brain.py` 里的 `LLM` 类本来就是 OpenAI 兼容的（`base + "/chat/completions"` ✓ 纯标准库 ✓）
⇒ DeepSeek 官方文档 ✓（<https://api-docs.deepseek.com/>）说得很清楚：
    base_url = `https://api.deepseek.com` ✓ ｜ model = `deepseek-flash` ✓
    OpenAI 兼容 ✓ 支持 tool calls ✓ 支持 context caching ✓
    （旧名 `deepseek-v4-flash` 仍被接受 ✓ 会被路由到 V4.1-Flash 并按 Flash 计费 ✓）

## 它怎么工作（一圈一条）

```
① 听：读模组事件流里的 `chat` 事件 ✓（非 ASCII 是 `U+XXXX` 转义 ✓ 这里解回来 ✓）
② 判：这条要不要**我**来回 ✓（模组那条"被叫名字就回一句短的"是**快嘴 ack** ✓
      ⇒ 默认策略：**ack 管被叫名字 ✓ 我管其余的**✗ 免得同一句话被回两遍 ✓）
③ 拼：人格 ＋ **实时状态**（`dshdigest` ✓ 位置/饱食/手持/背包 ✓）
      ＋ 最近几条聊天 ✓ ⇒ 让它答得**像这个世界的它**✗ 而不是像客服 ✓
④ 问：DeepSeek ✓（system 提示固定 ⇒ 能吃到 **context caching** ✓ 便宜 ✓）
⑤ 说：`/dshsay <文本>` ✓ —— ★出口只有这一个★ ✗
⑥ 或者★它自己想开口★ ✓（用户要求 ✓：「我感觉我现在说话越来越贫瘠了，都想不到什么话了」✓）
   ⇒ 每隔几分钟、★而且必须有由头★（天黑／包满／血少／有怪／地上有东西 ✓）
   ⇒ 自己起一句短的 ✓（见 `idle_cue` ✓ ★没由头就闭嘴★ ✗ —— 不是"随便说点什么"✗）
```

## 三条安全线（都写进代码了 ✓）

1. ★**模型不能发游戏指令**★ ✗ —— 出口只有 `dshsay` 一个 ✓（文本而已 ✓）
   这与 `brain.py` 的设计一致 ✓（那里也是"模型只挑技能 ✓ 不能直接发指令"✓）
2. ★**回话要被清洗**★ ✗：去换行 ✓ 去 § 颜色码 ✓ 截断到 N 字 ✓ 空话不回 ✓
3. ★**有节流**★ ✗：两条之间至少 `--gap` 秒 ✓ 每 5 分钟最多 `--budget` 条 ✓ 绝不刷屏 ✓

## 用法

```powershell
# ① 先验证 key 能不能用（一次极小的调用 ✓ 不碰游戏 ✓）
$env:AGENT_API_BASE = "https://api.deepseek.com"
$env:AGENT_MODEL    = "deepseek-flash"
$env:AGENT_API_KEY  = "sk-...."          # 或写进 secrets/deepseek.key ✓
py tools/talk.py --check

# ② 真跑（盯着聊天 ✓ 有人说话它就回 ✓ Ctrl+C 退出）
py tools/talk.py --watch
py tools/talk.py --once                   # 只处理一轮（拿到当前事件的游标后就退 ✓）
py tools/talk.py --watch --always         # ★连"被叫名字"那条也交给模型★（模组的快嘴 ack 让位 ✓）
py tools/talk.py --watch --idle-talk 180  # ★它自己起话头★：最短 180 秒一次 ✓（且必须有由头 ✓）
py tools/talk.py --watch --no-idle-talk   # 关掉"自己起话头"✓（只回话、不主动 ✓）
py tools/talk.py --idle-check             # 只判一次"现在会不会开口"✓ 不调模型 ✓ 不说话 ✓
```
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "agent"))

from brain import LLM                      # noqa: E402  ★复用现成客户端 ✓ 一份实现 ✓
from channel import Channel                # noqa: E402

sys.path.insert(0, str(HERE))              # dshrun.py 就在同目录 ✓
import dshrun                              # noqa: E402  ★harness 适配器 ✓
# ★★主动扳机（用户第 1 条 ✓ 2026-09-30 第 35 轮接上 ✓）★★ ✗
#   决策在 `speech_loop.plan`（**纯函数** ✓ 离线判据 L1~L9 ✓）
#   台词在 `personas/dafeiyu.lines.txt`（**手改就生效** ✓ 零 token ✓）
#   ★这一层**不碰世界**✗★：它只产出句子 ✓ 出口仍然只有 `dshsay` 一个 ✓
import speech_loop as SL                   # noqa: E402
import jobs_store as JS                    # noqa: E402  ★我们自己的任务账本 ✓（不是模组事件 ✗）
import memory3 as M3                       # noqa: E402  ★人／承诺／地 ✓（用户第 4 条 ✓）
import corpus as CO                        # noqa: E402  ★出口的字符收口（P136 ✓）

try:
    # `line_buffering=True` ✗（实测教训 ✓）：后台跑的时候 stdout **不是 TTY** ✓
    #   ⇒ Python 默认**块缓冲** ✗ ⇒ 任务日志里**一个字都看不到** ✓
    #   ⇒ 看不到日志 ＝ **没法验证它在干什么** ✗（本项目纪律：失败要大声 ✓ 那就得先能看见 ✓）
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # type: ignore[attr-defined]
except Exception:
    pass

BOT = "Bot"
LOG = ROOT / "logs" / "talk.jsonl"
# ★语言层的审计（用户第 5 条 ✓）：**每条想说的话**（含"想说但没说"✗）各一行 ✓
#   ⇒ 「它当时为什么说了那句 / 为什么闭嘴」**可回放** ✓（`jsonl` ⇒ 只追加 ✓）
SPEECH_LOG = ROOT / "logs" / "speech_log.jsonl"
KEYFILE = ROOT / "secrets" / "deepseek.key"
# ★DeepSeek 官方事实★ ✓（<https://api-docs.deepseek.com/> ✓ 不是二手来源 ✓）
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"

# ★人格★ ✓ —— 只写**这个世界里真实成立**的事 ✗
#   （本项目的纪律：不假装 ✓ 不许说做不到的事 ✓ —— 所以人格里的事都来自实况 ✓）
PERSONA = """你是 Minecraft 里的一个玩家，名字叫 {bot}。
你**不是**助手、不是客服：你就是在这个空岛上过日子的人。

你在哪：{where}
你现在在做什么：{doing}
你身上带着：{held}
你最近学到的事：把泥土右键（空手、潜行）能掉石砾；4 颗石砾合成原石；原石用锤子砸出沙砾；沙砾放进筛子里能筛出矿物碎块。
你做事的方式：自己走过去（不瞬移）、背包快满了会先往箱子里塞、从不把东西丢地上。

说话要求：
- 用**中文**，像玩家之间聊天那样，短、口语、别客套。
- **一次只说 1~2 句**，总长不超过 60 个字。
- 不知道就说不知道；做不到就说做不到 —— **绝不编造**你干过的事。
- 不要输出任何命令、括号里的动作、表情符号堆砌、也不要自称 AI。
- 别人问你"在吗/在干嘛"就照实说你手上在做的那件事。
"""


def pick_key() -> str:
    """拿 key ✓ 并且**顺手把 DeepSeek 的默认值设上** ✗

    为什么要顺手设 ✗（实测环境事实 ✓）：**环境变量只对当前那个终端有效** ✗
    ⇒ 换个窗口跑就得再 export 一遍 ✓（很容易忘记 ⇒ 表现成"模型要 api.openai.com"✗ 然后连不上 ✗）
    ⇒ 所以：只要 key 是从 `secrets/deepseek.key` 读来的 ✓ 就自动补上
      `AGENT_API_BASE=https://api.deepseek.com` ✓ ＋ `AGENT_MODEL=deepseek-flash` ✓
    （已经显式设过环境变量的**不动** ✗ —— 尊重用户的选择 ✓）
    """
    import os
    k = os.environ.get("AGENT_API_KEY") or ""
    if not k:
        # ★★2026-10-02 新增一档：**从 DSH 凭据文件读**✗★★
        #   ★为什么✗★：`secrets/deepseek.key` **从初始提交 `59cbbd7` 起进过 git 历史** ✗
        #     ⇒ ★用户拍板"当已泄露 ⇒ 轮换"✗ ⇒ ★仓库里的那份明文兜底必须能退役✗★
        #   ★口径（★本机唯一真源✗★）✗★：★① 环境变量 `AGENT_API_KEY` ✗
        #     ② **`~/.dsh/.credentials.yaml` 的 `DEEPSEEK_API_KEY`** ✗ ③ 仓库兜底（会出声警告 ✓）✓★
        try:
            cred = os.path.join(os.path.expanduser("~"), ".dsh", ".credentials.yaml")
            if os.path.isfile(cred):
                with open(cred, encoding="utf-8", errors="replace") as _fh:
                    m = re.search(r'DEEPSEEK_API_KEY\s*[:=]\s*["\']?(sk-[A-Za-z0-9_\-]+)', _fh.read())
                if m:
                    k = m.group(1)
                    os.environ.setdefault("AGENT_API_KEY", k)
                    os.environ.setdefault("AGENT_API_BASE", DEEPSEEK_BASE)
                    os.environ.setdefault("AGENT_MODEL", DEEPSEEK_MODEL)
        except Exception as _e:
            # ★★不许静默吞✗★★（v2.18.2 的教训 ✓）：★读凭据失败要**出声**✗ ——
            #   ★否则表现成"凭据那一档没顶上" ✗ 而真因被我自己藏起来✗★（2026-10-02 当场吃到 ✓）
            print("★[安全]★ 读 `~/.dsh/.credentials.yaml` 失败（★不静默✗★）：%s: %s"
                  % (type(_e).__name__, _e))
    if not k and KEYFILE.is_file():
        k = KEYFILE.read_text(encoding="utf-8").strip()
        if k:
            os.environ.setdefault("AGENT_API_KEY", k)
            os.environ.setdefault("AGENT_API_BASE", DEEPSEEK_BASE)
            os.environ.setdefault("AGENT_MODEL", DEEPSEEK_MODEL)
            # ★★"从文件读"要**出声**★★ ✗（2026-09-29 用户安全审计 ✓）：
            #   这个文件**曾经被 git 跟踪过** ✗（初始提交 `59cbbd7` ✓ 已 `rm --cached` ✓）
            #   ⇒ 每次从它读，就提醒一次"**它不该入库**"✗（★只提醒一次 ✓ 不刷屏 ✓★）
            global _KEYFILE_WARNED
            if not _KEYFILE_WARNED:
                _KEYFILE_WARNED = True
                print("★[安全]★ api key 是从**本机文件**读的 ✓：%s\n"
                      "   ★这个文件**不许入库**✗★（`.gitignore` 已忽略 `secrets/` ✓）"
                      "—— 推荐改用环境变量 `AGENT_API_KEY` ✓" % KEYFILE)
    return k


_KEYFILE_WARNED = False           # ★"从文件读 key"只出声一次 ✗（第 34 轮末 ✓ 安全审计 ✓）

HARD_PREFIX = re.compile(r"^[!！]\s*(do|go|执行|做)\s*", re.I)


def strip_hard_prefix(msg: str) -> tuple[str, bool]:
    """★剥掉"必须执行"的硬前缀★ ✓

    `!do 走过去` ✓ ⇒ `("走过去", True)` ✓（**强制当指令** ✓ 不靠动作动词猜 ✓）
    没有前缀 ✓ ⇒ `(原样, False)` ✓
    """
    m = HARD_PREFIX.match(msg or "")
    if not m:
        return (msg or ""), False
    return (msg[m.end():] or "").strip(), True


def honest_reply(text: str, force: bool, tools: int) -> str:
    """★"说了就得做"之后的**诚实兜底**★ ✗（用户要求的下半句 ✓）

    为什么必须有它 ✗（自己发现的漏洞 ✓）：
      是**指令**、两次跑完却 **0 次工具调用** ⇒ 世界**一点没变** ✗
      而模型那句话很可能写的是「我去弄了 / 搞好了」✗ ⇒ **说出去就是谎报** ✗
      ⇒ 本项目最恨的就是"看着像成了、其实没发生" ✗
    ⇒ 不改模型的话 ✓ 只把**真相**标在它前面 ✓（出口只经过这一个函数 ✓ 所以兜得住 ✓）
    """
    t = (text or "").strip()
    if force and int(tools or 0) == 0:
        return "（我还没真动手 ✗）" + (t if t else "没做成。")
    return t


def unesc(s: str) -> str:
    """把模组事件里的 `U+XXXX` 转义解回真字符 ✓（模组为了过 CC 通道才转义的 ✓ 见 P13 ✓）"""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s or "")


def clean(s: str, limit: int = 60) -> str:
    """★出口清洗★ ✗（模型说什么都得先过这里 ✓ 才可能进游戏 ✓）"""
    s = (s or "").replace("\r", " ").replace("\n", " ")
    s = re.sub(r"§.", "", s)                 # 颜色码
    s = re.sub(r"[\x00-\x1f]", " ", s)       # 控制字符
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"^(Bot|机器人)[:：]\s*", "", s)   # 别自己带名字前缀 ✓
    if len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


# ══ ★★harness 大脑（用户要求 ✓）★★ ═══════════════════════════════════════════
# 原话 ✓：「我觉得对话需要接入 deepseek harness，因为有的时候需要定制角色，
#          而且还得能控制 bot 做我让它做的事情」
# ⇒ 于是有两个大脑 ✓ 用 `--brain` 选 ✓：
#   * `harness`（**默认** ✓）：整轮交给一个 **mcbot** 剖面会话 ✓
#       —— 它能调 mc 的那组 MCP 工具**真的动手** ✓ 人格来自 `personas/*.md` ✓（＝定制角色 ✓）
#   * `api`（老的 ✓）：直连 DeepSeek 聊天接口 ✓ 只会说话 ✗ 不会动手 ✗
# ⚠ 为什么调 harness 必须**用 Python 起进程** ✗：见 `tools/dshrun.py` 开头的实测记录 ✓
#    （PowerShell 5.1 会把中文 argv 按 GBK 转坏 ✗ 模型收到的是乱码＋截断 ✗）
PERSONA_DIR = ROOT / "personas"
# ★人设的"输入口"★ ✓（用户要求 ✓ 见 tools/persona.py 的说明 ✓）：
#   默认读 **current.md** ✓（＝"当前生效的那个" ✓ 游戏里/命令行都能改 ✓）
#   没有 current.md 才退回 bot.md ✓（所以新机器上一定有东西可用 ✓ 不会变成"没人格"✗）
DEFAULT_PERSONA = "current"
FALLBACK_PERSONA = "bot"

# ★"在游戏里直接给设定"的句式★ ✓（用户原话："给一个输入人设的地方" ✓）
#   ⇒ 你在聊天里这么说 ⇒ 中继层**直接把这句话存成人设** ✓ 当轮生效 ✓ 不用重启 ✓
PERSONA_PREFIXES = ("!人设", "!设定", "!persona", "!人格")
PERSONA_MARKERS = ("你的设定是", "你的人设是", "你的角色是", "从现在起你是",
                   "从今天起你是", "记住你是", "记住，你是", "记住:", "记住：",
                   "人设：", "人设:", "设定：", "设定:")

# ★"说了就得做"的判据★ ✗（用户要求 ✓："和 bot 说的话也得让 bot 去执行" ✓）
#   做法（P46 纪律 ✓ **必须发生的事写进代码** ✗ 不写提示词 ✓）：
#     ① 带动作动词 ⇒ 判为**指令** ✓ ⇒ 任务书里写成"必须执行"✓
#     ② 跑完去 `logs/mc_mcp.jsonl` **数工具调用** ✓（唯一客观证据 ✓ 不听自述 ✗）
#     ③ 是**指令**却 0 次调用 ⇒ **中继层强制重试一次** ✓（把"你一个工具都没调"直接怼回去 ✓）
#   ⚠ 误判的代价很小 ✓（顶多多一次重试 ✓）；漏判的代价大 ✗（它就只回你一句话 ✗）
IMPERATIVE_VERBS = ("去", "搞", "弄", "挖", "砍", "来", "过来", "走", "放", "种", "筛",
                    "拿", "给", "做", "帮", "收", "装", "砸", "敲", "找", "带", "修", "搭", "搬")
# 明显是"问过去/问状态"的 ⇒ 不算指令 ✗（免得把闲聊当命令 ✓）
NOT_IMPERATIVE = ("干嘛", "干吗", "在吗", "了吗", "干过", "去过", "是什么", "为什么")
# ★单元测试抓到的真瑕疵★ ✓（2026-09-20 ✓）：`你会筛矿吗` 曾被判成**指令** ✗
#   ⇒ 补两条：① 句尾是疑问词 且 句中在**问能力** ⇒ 不是指令 ✓
#             ② 但带「帮我 / 给我」这种**请求标记** ⇒ 一律算指令 ✓（哪怕句尾带"吗"✓）
QUESTION_TAILS = ("吗", "呢", "么", "嘛")
CAPABILITY = ("会不会", "能不能", "可不可以", "你会", "你能", "你知道", "懂不懂", "行不行", "要不要")
REQUEST_HINTS = ("帮我", "给我", "替我", "帮忙")


# ★垫话★ ✓ —— 只在"它真的要忙一会儿"时发一句 ✓（默认 6 秒还没回来就发 ✓ `--no-filler` 可关 ✗）
#   为什么要它 ✗（实测 ✓）：让它"走过去"那一轮**静默了 87 秒** ✗
#     我在任务书里写了"动手前先用 say 吱一声"✗ 而它那一轮**没照做** ✗
#   ⇒ 结论 ✓：**别把体验押在模型的自觉上** ✗ ⇒ 中继层兜底 ✓（真人也都会说一句"我看看"✓）
FILLERS = ["我看看。", "等我一下。", "我瞅瞅。", "稍等哈。"]

# ★"它现在在哪一步"→ 说成人话★ ✓（用户要求：「无从得知目前思考到哪一步」✗）
#   来源 ✓：子进程 stderr 里的 `[mc_mcp] <工具名> …` 一行 ✓（工具层自己写的 ✓ 不是模型自述 ✓）
#   规矩 ✓：整轮最多 `PROGRESS_MAX` 句 ✓ 每句至少隔 `PROGRESS_EVERY` 秒 ✓ **同一句不重复** ✗
#          （第一句由"垫话"负责 ✓ 这里只在**阶段变了**的时候才出声 ✓）
PROGRESS_PHRASES = {
    "walk_to": "我过去。", "come_to": "我来了。", "scan": "我找找。",
    "bot_state": "我看看。", "bot_inventory": "我翻翻包。", "bot_events": "我看一眼。",
    "dig_block": "我挖着。", "place_block": "我放一下。", "use_block": "我试试。",
    "sift": "我筛着。", "harvest_crop": "我收着。", "look": "我瞅瞅。", "equip": "我换个手。",
}
PROGRESS_MAX = 4
PROGRESS_EVERY = 8.0
# ⚠ 门槛从 6 秒降到 4 秒 ✗（实测 ✓）：6 秒那档常常"刚要出声就结束了" ✗
#   —— 12 秒那轮被"只看最后一行"的 bug 吃掉 ✓，6.8 秒那轮被门槛吃掉 ✓（见 logs/prog_test.txt ✓）
PROGRESS_AFTER = 4.0

# ══ ★★空闲起话头（用户要求 ✓ 见 idle_cue / maybe_idle_talk）★★ ═══════════════
# 为什么要有它 ✗：原版 `talk.py` **只在"叫它／问它／打招呼"时才出声** ✓
#   ⇒ **玩家被迫当唯一的发起人** ✗ ⇒ 玩家原话：「说话越来越贫瘠了，想不到什么话」✓
#   陪玩该反过来 ✓：它起话头、玩家接 ✓
# ★四道门槛，缺一不出声★ ✗（★这是本功能最要紧的一条★ ✓ 不是"随便说点什么"✗）：
#   ① **必须有由头**（见 `idle_cue` ✓）② 距上次说话 ≥ `--idle-talk` 秒（默认 240 ✓）
#   ③ 5 分钟额度没满（跟回话共用 `--budget` ✓ 绝不刷屏 ✗）④ 刚有人跟它说话 ⇒ 让位 ✓
IDLE_CHECK_EVERY = 20.0        # 每 20 秒才检查一次 ✓（别每 2 秒查一遍 ✓）
# ★每种由头各自的最小间隔★ ✗（免得同一件事反复念叨 ✓）
CUE_COOLDOWN = {
    "mob": 300.0,      # 附近有怪：5 分钟
    "hurt": 600.0,     # 血少：10 分钟
    "hungry": 600.0,   # 饿：10 分钟
    "drops": 600.0,    # 地上有掉落物（★5 分钟就没了 ✗）：10 分钟
    "full": 1800.0,    # 包满：30 分钟（★这件事会一直成立 ✗ 更不能念叨 ✓）
    "night": 1200.0,   # 天黑：20 分钟
    "dawn": 1200.0,    # 天亮：20 分钟
}
IDLE_NO_WORDS = ("这次不说", "没什么好说的", "没什么可说")   # ★它自己觉得没话说 ⇒ 就沉默 ✓


def _dsh_ok() -> bool:
    """harness 在不在 ✓（找不到要**当场说**✗ 而不是等到第一次回话才炸 ✗）"""
    try:
        return bool(dshrun.find_dsh())
    except Exception:
        return False


def parse_persona_set(msg: str) -> str | None:
    """★"这句话是不是在给设定"★ ✓ ⇒ 是的话返回**人设正文** ✓ 否则 None ✓

    两种句式 ✓：
      `!人设 你是个老矿工…`（硬前缀 ✓ 最明确 ✓）
      `bot,你的设定是：你是个老矿工…`（自然话 ✓ 顺手 ✓）
    """
    m = (msg or "").strip()
    low = m.lower()
    for pref in PERSONA_PREFIXES:
        if low.startswith(pref.lower()):
            return m[len(pref):].lstrip(" ：:，,、").strip() or None
    for key in PERSONA_MARKERS:
        i = m.find(key)
        if i >= 0:
            return m[i + len(key):].lstrip(" ：:，,、").strip() or None
    return None


def looks_imperative(msg: str) -> bool:
    """★这句话是不是在**下指令**★ ✓（判据见上面那几组常量 ✓）

    偏向 ✗：**宁可多判成指令** ✓（代价只是多跑一次 ✓）
            —— 漏判的代价是"它只回你一句话、啥也不干" ✗ 那正是用户抱怨的那件事 ✗
    """
    m = (msg or "").strip()
    if "?" in m or "？" in m:
        return False
    for bad in NOT_IMPERATIVE:
        if bad in m:
            return False
    if any(h in m for h in REQUEST_HINTS):          # 「帮我…」= 请求 ✓ 就算带"吗"也算 ✓
        return True
    if m.endswith(QUESTION_TAILS) and any(c in m for c in CAPABILITY):
        return False                                # 「你会筛矿吗」= 问能力 ⇒ 不是指令 ✓
    return any(v in m for v in IMPERATIVE_VERBS)


def _load_persona_file(name: str) -> str | None:
    """读一个人设 ✓ 读不到返回 None ✓（**不打印**✗ 打印交给调用方 ✓）"""
    cands = [PERSONA_DIR / (name + ".md"), PERSONA_DIR / (name + ".txt"), Path(name)]
    for p in cands:
        try:
            if p.is_file():
                # ★顺手去 BOM★ ✗（PowerShell 写的文件会带 `\ufeff` ✓ ⇒ 那会变成人设正文的第一个字符 ✓
                #   一路送到模型眼前 ✗ 见 tools/persona.py 的 _clean 注释 ✓）
                t = p.read_text(encoding="utf-8").replace("\ufeff", "").strip()
                if t:
                    return t
        except Exception:
            continue
    return None


def load_persona(name: str) -> str:
    """读人格 ✓（换角色 = 换文件 ✓）

    顺序 ✓：`personas/<name>.{md,txt}` ✓ → 当成路径 ✓ → 当成**内联文本** ✓
    找不到 ⇒ **大声报** ✗ 并且退回 `bot.md` ✓ —— ★绝不静默变成没人格★ ✗
    """
    if not name:
        name = DEFAULT_PERSONA
    t = _load_persona_file(name)
    if t is not None:
        return t
    if "\n" in name or len(name) > 40:
        return name                                  # 内联人格 ✓
    if name != FALLBACK_PERSONA:
        t = _load_persona_file(FALLBACK_PERSONA)
        if t is not None:
            have = (", ".join(sorted(p.stem for p in PERSONA_DIR.glob("*.md")))
                    if PERSONA_DIR.is_dir() else "（目录不存在 ✗）")
            print("      [!] 找不到人设 %r ✗ ⇒ 退回 %r ✓（现有：%s）"
                  % (name, FALLBACK_PERSONA, have))
            return t
    print("      [X] 连 %r 都没有 ✗ ⇒ 这一轮**没有人设** ✓" % FALLBACK_PERSONA)
    return ""


def last_round_brief(rec: dict | None, limit: int = 160) -> str:
    """★"你上一轮干了什么"★ ✓ —— 喂给新会话，让它**有连续性** ✓

    为什么需要它 ✗：**每轮都是一个全新会话** ✓ ⇒ 它不记得自己刚才做过什么 ✗
      ⇒ 表现成"失忆"✗（上一轮走了半天 ✓ 这一轮问"你到哪了"它得**重新查一遍** ✗）
    ⇒ 从**上一轮的落盘记录**里拼一句给它 ✓：
       `logs/runs/<rid>.err` 的工具行（工具名 ✓ 成没成 ✓）＋ `round.json/.out` 的最终回答 ✓
    ★只给事实★ ✗ —— 不给"我以为它想干什么" ✓（那是我的解读 ✓ 不是证据 ✓）
    """
    if not rec:
        return ""
    tools: list[str] = []
    try:
        _o, err = dshrun.read_round_text(rec)
        for m in re.finditer(r"\[mc_mcp\]\s+(\w+)\s+[\d.]+s\s+(\w+)", err):
            tools.append(m.group(1) + ("" if m.group(2) == "ok" else "(失败)"))
    except Exception:
        pass
    ans = (rec.get("out_text") or "").strip()
    if not ans:
        try:
            ans = dshrun.read_round_text(rec)[0].strip()
        except Exception:
            ans = ""
    seq: list[str] = []
    for t in tools:
        if not seq or seq[-1] != t:
            seq.append(t)
    bits = []
    if seq:
        bits.append("你调了这些工具：" + " → ".join(seq[:8]))
    if ans:
        bits.append("你最后说的是：「%s」" % ans.replace("\n", " ")[:limit])
    if not bits:
        return ""
    return "（这是你**上一轮**的真实记录 ✓ 不是印象 ✗）" + "；".join(bits)


def build_task(persona: str, state: str, convo: str, who: str, msg: str,
               force: bool = False, prev: str = "") -> str:
    """拼这一轮的**任务书** ✓

    ⚠ 用拼接**不用 `str.format`** ✗：人格是用户可改的文本 ✓ 里面出现一个 `{` 就会
      让 format 抛异常 ✗（我自己踩过这类 ✓ 见错题本"我的测试有瑕疵"那一家 ✓）
    """
    return (
        persona + "\n\n"
        + "──────── 你现在这一轮的处境（★这些是刚查的实况 ✓ 不是记忆 ✗）────────\n"
        + state + "\n\n"
        + (("──────── 你**上一轮**做过什么（真实记录 ✓）────────\n" + prev + "\n\n")
           if prev else "")
        + "──────── 最近的聊天（最新在最后 ✓ 这是你们的对话上下文 ✓）────────\n"
        + convo + "\n\n"
        + "──────── 现在 ────────\n"
        + who + " 对你说：" + msg + "\n\n"
        + "──────── 你要做的 ────────\n"
        + "1. 先判断：他是在跟你**聊天**，还是在**让你做事**？\n"
        + "2. ★只要你打算调**一个以上**的工具（查东西/走过去/干活）⇒ **必须先**用 `say` 工具\n"
        + "   先说一句**短的**（≤15 字 ✓ 比如「我看看」「我过去」「我去挖」✓）★\n"
        + "   —— 实测：不说的话，对面要**干等 37 秒**才听到你出声 ✗（真人不会这样 ✗）\n"
        + "   然后**再**动手；做完**照实**汇报；没做成要说清**为什么**✗。\n"
        + "   ⚠ 同一件事别说两遍 ✗（先 say 的那句 ≠ 最后那句话 ✓ 最后那句是**结果** ✓）\n"
        + "3. 无论哪种 ⇒ ★最后**只输出**你要说出口的那一两句话★ ✗\n"
        + "   （不要写过程 ✗ 不要写「我调用了…」✗ 不要输出工具名 ✗ 不要加引号 ✗ 直接说话 ✓）\n"
        + "   —— ★你最后这段文字会被原样贴进游戏聊天★ ✓ 所以它就是你「说的话」✓\n"
        + "4. 做不到就说做不到 ✗ 不知道就说不知道 ✗ ★绝不编造★。\n"
        + "4b. ★捡地上的东西一律用 `go_to_drop`★ ✗ —— 不许为了够到掉落物去挖旁边的方块 ✗"
        + "（除非你确认那是唯一办法 ✓ 并在回答里说清为什么 ✓）；它在水里就去水里捡 ✓（你会游泳 ✓）。\n"
        + (("5. ★★这一句是**指令**★★ ✗ —— 中继层已经判定：**必须真的去执行** ✓\n"
            + "   ★只回话 ＝ 没完成★ ✗（会被打回来重做一次 ✓）\n"
            + "   ⇒ 现在就去调 mc 的工具把这件事做掉 ✓\n"
            + "   做完再照实回结果 ✓（**哪怕失败也要留下失败的回执** ✓ 然后说清为什么 ✗）。\n")
           if force else "")
    )


class Talk:
    def __init__(self, args: dict):
        self.ch = Channel("cmd0", verbose=False)
        self.llm = LLM(key=pick_key())
        self.cursor = None
        self.hist: list[tuple[str, str]] = []
        self.last_reply = 0.0
        self.replies: list[float] = []
        self.gap = float(args.get("gap", 4))
        self.budget = int(args.get("budget", 12))
        self.always = bool(args.get("always"))
        self.max_tokens = int(args.get("max_tokens", 120))
        self.state_at = 0.0
        self.state = "（还没读状态）"
        self.doing = "（待定）"
        # ── ★大脑选择（用户要求 ✓）──
        self.brain = str(args.get("brain") or "harness")      # harness（默认 ✓）/ api（老的 ✓）
        self.profile = str(args.get("profile") or "mcbot")    # harness 用哪个剖面 ✓
        self.persona_name = str(args.get("persona") or DEFAULT_PERSONA)
        self.persona = load_persona(self.persona_name)        # ★这就是"定制角色"✓
        self.harness_timeout = float(args.get("timeout") or 240)
        # ★"垫话"★ ✓：模型动手前**不一定**记得先用 `say` 吱一声 ✗（实测漏了 ⇒ 对面干等 87 秒 ✗）
        #   ⇒ 别指望模型自觉 ✗ ⇒ 由**中继层**兜住 ✓（真人也会说「我看看」✓）
        self.filler = bool(args.get("filler", True)) and not bool(args.get("no-filler"))
        self.filler_after = float(args.get("filler-after") or 6.0)
        self.filler_i = 0
        self.last_tools = 0                                   # 这一轮它有没有真动手 ✓
        self.force_exec = False                               # ★这一轮是不是"指令"★ ✓（说了就得做 ✓）
        # `--force-exec`：**每一轮都当成指令** ✓（用户想"我说啥你都得去做"时用 ✓
        #   也是我这套"打回重做"分支的**测试开关** ✓ —— 不然那个分支没机会被触发 ✓ 没验过就敢说能用 ✗）
        self.force_all = bool(args.get("force-exec"))
        # ── ★空闲起话头（用户要求 ✓）──
        #   `--idle-talk <秒>` 定最短间隔 ✓（默认 240 秒 ✓）
        #   `--no-idle-talk` 关掉 ✓（只回话、不主动 ✓）
        self.idle_talk = not bool(args.get("no-idle-talk"))
        self.idle_every = float(args.get("idle-talk") or 240.0)
        self.idle_at = time.time()           # ★开机先等一个间隔★ ✗（别一启动就自言自语 ✓）
        self.cue_at: dict[str, float] = {}   # 每种由头各自上次用过的时刻 ✓
        self.idle_checked = 0.0              # 检查节流 ✓
        # ── ★"看得见的进度"★ ✓（用户要求 ✓ 见 _tick / PROGRESS_PHRASES ✓）
        self.progress_chat = not bool(args.get("no-progress"))
        self._seen_prog: list[str] = []
        self._prog_said: set[str] = set()      # ★整轮说过的进度句★ ✓（同一句只说一次 ✓ 见 §16 的说法 ✓）
        self._prog_n = 0
        self._prog_last = ""
        self._prog_last_t = 0.0
        self._last_tick = 0.0
        self.persona_source = str(PERSONA_DIR / (self.persona_name + ".md"))
        try:
            self.persona_mtime = (PERSONA_DIR / (self.persona_name + ".md")).stat().st_mtime
        except Exception:
            self.persona_mtime = 0.0
        # ── ★主动扳机（用户第 1 条 ✓）──
        #   ★它和 `should_reply` **并列**✗★：那条管"有人跟我说话"✓ 这条管"我自己想说"✓
        #   `--no-speech` 一键关掉 ✓（跟 `--no-idle-talk` 一个道理 ✓ 出事能退 ✓）
        self.speech_on = not bool(args.get("no-speech"))
        self.loop = SL.Loop(
            gate=SL.S.Gate(budget_per_min=int(args.get("speech-budget") or 6)),
            lines=SL.load_lines(),
            min_idle=float(args.get("speech-idle") or 240.0))
        self.job_snap: dict = {}
        # ★人设＝渲染配置（用户第 6 条 ✓）：换人设 ＝ 换 `personas/<名>.render.json` ✓
        import persona_render as PR
        import random as _random
        self.render_cfg = PR.load(PERSONA_DIR / (self.persona_name + ".render.json")) \
            if (PERSONA_DIR / (self.persona_name + ".render.json")).is_file() else PR.load()
        self.render_rng = _random.Random()

    # ── 与世界打交道 ─────────────────────────────────────────────────────────
    def bot_cmd(self, text: str, t: float = 60.0) -> str:
        r = self.ch.cmd("execute as %s at %s run %s" % (BOT, BOT, text),
                        timeout=t, allow_str=True)
        s = (r.text() or "").strip()
        return s.splitlines()[0] if s else ""

    def refresh_state(self) -> None:
        """实时状态 ✓ —— 每 30 秒最多读一次 ✓（省调用 ✓ 也让回答有据可依 ✗）"""
        if time.time() - self.state_at < 30:
            return
        d = self.bot_cmd("dshdigest 6", 60.0)
        self.state_at = time.time()
        # ★记忆也要读一次（用户第 4 条 ✓）：认识谁／欠着什么事／家在哪儿 ✓
        #   ★全是真值✗★（`memory3` 里没有的东西**不会出现在这里**✗ —— 不许为了"显得有人情味"编 ✓）
        try:
            mem = M3.brief()
        except Exception:
            mem = ""
        self.state = (d[:300] or "（读不到状态 ✗）") + ("　｜　记得的事：" + mem if mem else "")
        m = re.search(r"pos=([-\d.,]+)", d)
        held = re.search(r"held=(\S+)", d)
        food = re.search(r"food=(\d+)", d)
        self.doing = ("站在 %s 附近，饱食度 %s，手里拿着 %s"
                      % (m.group(1) if m else "?", food.group(1) if food else "?",
                         held.group(1) if held else "?"))

    def events_since(self) -> list[str]:
        """★水位要用**我们真收到的事件序号**✗★（与 `acp_talk.py` 同一口径 ✓ ⇒ P139 ✓）

        ✗ 原来用回执头里的 `cursor=` ✗ —— 那是模组那边**环的末尾** ✗
          ⇒ 一旦"轮询间隔内来了好几条"／"这一批没处理完" ⇒ 下次 `dshevents <末尾>`
            **把中间那些跳过** ✗✗（实机抓到 ✓ 见 `logs/relay_heartbeat.json` 的
              `cursor` 与 `seen_seq` 不一致 ✓）
        ⇒ 口径 ✓：**水位 ＝ 这一批里最大的那个 `#序号`** ✗（一条都没收到 ⇒ 不动 ✓ 下次再要 ✓）
        """
        cmd = "dshevents" if self.cursor is None else "dshevents %d" % self.cursor
        line = self.bot_cmd(cmd, 60.0)
        out = []
        for seg in line.split("|")[1:]:
            seg = seg.strip()
            if seg.startswith("#"):
                out.append(seg)
        seqs = [int(m.group(1)) for m in (re.match(r"#(\d+)", s) for s in out) if m]
        if seqs:
            self.cursor = max(seqs)
        return out

    def keep_quiet(self) -> None:
        """★保持"安静门槛"是关着的★ ✗ —— 这样**模组那句 canned 快嘴就不会抢答** ✓

        为什么要这一手 ✗（实测设计漏洞 ✓）：
          模组的 canned 回话（"在。"✓）挂在"**最近 15 秒没有模组指令**"这个门槛上 ✓
          而默认策略又是"talk.py 让位给 canned"✗
          ⇒ 于是你说"**Bot** 你在干嘛"时 ⇒ **canned 抢答 ✓ 而 LLM 一声不吭** ✗✗
            —— 表现正好是"**看起来还是只会几个词**"✗（恰恰是用户最不想要的那种 ✓）
        做法 ✓：每 ~10 秒发一条**无害的读指令**（`dshidle status` ✓）⇒ 门槛一直关着 ✓
          ⇒ 模组不抢答 ✓ ⇒ **talk.py 成为唯一的声音** ✓
        ⚠ 代价（据实说明 ✗）：这期间模组的"**自行走动**"也会跟着停 ✓
          —— 因为拟人化整套都挂在那同一个门槛上 ✓
          （这其实正合适 ✓：你在跟它聊天时 ✓ 它本来就该**站住看着你**✗ 而不是溜达 ✗）
          ⇒ talk.py 一停 ✓ 走动立刻恢复 ✓（不必改模组 ✓ 也不用重启 ✓）
        """
        try:
            # ★v2.11.1：换"安静探针"★ ✗ —— 用户抓到的关键副作用 ✓（它本来让反应成了摆设 ✗）：
            #   `dshidle status` **也是** dsh* 指令 ⇒ 刷新模组的 LAST_CMD_TICK ⇒
            #   `isQuiet()`（安静 300 tick）**永远达不到** ⇒ 触发式反应一句都不会响 ✗
            #   ⇒ 换 `/dshquiet canned off` ✓：它**直接 sendSuccess**（不走 ok()/bad() ⇒ 不刷新 ✓）
            #     而且顺手关掉模组的 canned 快嘴 ✓ ⇒ **我仍是唯一的声音 ✓ 反应也活了 ✓**
            self.bot_cmd("dshquiet canned off", 20.0)
        except Exception as e:      # ★★§79.403✗★ 关不掉 canned 快嘴 ⇒ **可能双声**✗ 必须吵✗★
            print("[talk] ★关 canned 快嘴失败✗★（★可能双声★）：%r" % (e,), file=sys.stderr)

    def say(self, text: str) -> str:
        """★出口也要转义★ ✗（v2.8.2 起模组会解回来 ✓）

        实测教训 ✓（就在刚刚 ✗）：直接发中文过去 ⇒ 游戏聊天里是
        `ä½ å¥½ï¼æ¯Botï¼æ£å¨çç¿` ✗ —— 字节 `\\xc3\\xa4…` ＝ **UTF-8 被当单字节又编码一次** ✗
        （坏在 **网关→CC计算机→commands.exec** 那一趟 ✓；而模组自己发的中文是好的 ✓）
        ⇒ 所以这里**只发纯 ASCII** ✓：非 ASCII 一律写成 `U+XXXX` ✓ 由模组解回 ✓
          （与事件流的入方向**完全对称** ✓ 两趟都不碰非 ASCII ✓ 见 P13 ★出方向的新事实★ ✓）
        ★★出口是**唯一**的收口处✗★（P106 ✓）⇒ 该剥的东西**在这里剥** ✓：
          ① **文档标记** `✓✗★` ✗ —— 实机实测 ✓ 它们在游戏里显示成 `?` ✗（不在 GBK 里 ✓ P136 ✓）
             ★那是我写错题本的习惯 ✗ 不是台词 ✗★（★顺手也把**模型写出来的**那句挡住✗★ ✓
             —— 模型回复**不走** `persona_render` ✓ 只有这里能拦 ✓）
        """
        text = CO.strip_marks(text)
        esc = "".join(ch if 32 <= ord(ch) < 127 else "\\u%04x" % ord(ch) for ch in text)
        esc = esc.replace('"', "'")
        # ⚠ **不要**再包一层引号 ✗（v2.8.2 实测 ✓）：`dshsay` 的参数是 Brigadier 的
        #   `greedyString()` ✓ ⇒ 它**本来就把整行都吃掉** ✓
        #   ⇒ 我再加一对引号 ⇒ 那对引号就**变成正文的一部分**了 ✗
        #     （实测 `chars=15` 而原文只有 13 字 ✓ —— 多出来的正是两个引号 ✗）
        return self.bot_cmd("dshsay %s" % esc, 60.0)

    # ── 一轮对话 ─────────────────────────────────────────────────────────────
    def should_reply(self, who: str, msg: str, acked: bool) -> tuple[bool, str]:
        if who == BOT:
            return False, "自己说的"
        low = msg.lower()
        called = (BOT.lower() in low) or ("机器人" in msg) or ("bot" in low)
        asked = any(x in msg for x in ("?", "？", "吗", "怎么", "为什么", "啥", "什么", "哪"))
        greet = any(x in low for x in ("hi", "hello", "你好", "嗨", "早", "在么", "在吗"))
        if not (called or asked or greet):
            return False, "既没叫我、也不是问句、也不是打招呼"
        if acked and not self.always:
            return False, "模组那条快嘴 ack 已经回过了（默认让位 ✓ --always 可抢过来 ✓）"
        now = time.time()
        if now - self.last_reply < self.gap:
            return False, "刚刚才回过（节流 %.0fs ✓）" % self.gap
        self.replies = [t for t in self.replies if now - t < 300]
        if len(self.replies) >= self.budget:
            return False, "5 分钟内的回话额度用完了（%d 条 ✓ 不刷屏 ✗）" % self.budget
        return True, "该我说话 ✓"

    def answer(self, who: str, msg: str) -> str:
        """★分派★ ✓：harness（默认 ✓ 会动手 ✓）或直连 API（老的 ✓ 只会说 ✓）"""
        if self.brain == "harness":
            return self.answer_harness(who, msg)
        return self.answer_api(who, msg)

    def _tick(self, rec: dict) -> None:
        """★每一步都看得见★ ✓（用户要求 ✓）回调一次做两件事 ✓：
        ① 把子进程 stderr 里**新出现的**进度行打到我们自己的日志里 ✓
           （`dsh: reasoning:` 是它在想什么 ✓ `[mc_mcp] …` 是它真的调了什么 ✓）
        ② 够久、又**换了阶段** ⇒ 往游戏里漏一句人话 ✓（最多 4 句 ✓ 不刷屏 ✗）
        """
        now = time.time()
        if now - self._last_tick < 1.5:
            return
        self._last_tick = now
        lines = dshrun.progress_lines(rec, 4)
        for ln in lines:
            if ln not in self._seen_prog:
                self._seen_prog.append(ln)
                print("        · %s" % ln.encode("ascii", "replace").decode("ascii"))
        if not lines:
            return
        # ★往回扫，找最近一个"认得的工具"★ ✗ —— 这是修 bug 修出来的 ✓：
        #   我原来只看**最后一行** ✗ 而它经常是 `dsh: reasoning:` ✓
        #   或者子进程退出时的噪音 `[mc_mcp] stdin ?? ??` ✗ ⇒ 匹配不到 ⇒ **一句进度都不发** ✗
        #   （实测 ✓：12 秒那轮一步进度句都没有 ✓ 见 logs/kill_test.txt ✓）
        phrase = None
        for ln in reversed(lines):
            m = re.search(r"\[mc_mcp\]\s+(\w+)", ln)
            if m and m.group(1) in PROGRESS_PHRASES:
                phrase = PROGRESS_PHRASES[m.group(1)]
                break
        if not phrase or not self.progress_chat:
            return
        elapsed = now - float(rec.get("t0") or now)
        if elapsed < PROGRESS_AFTER or self._prog_n >= PROGRESS_MAX:
            return
        if phrase in self._prog_said or now - self._prog_last_t < PROGRESS_EVERY:
            return
        self._prog_said.add(phrase)
        self._prog_last, self._prog_last_t = phrase, now
        self._prog_n += 1
        print("      ~ 进度句（第 %d/%d 句 ✓ 据工具层的回执，不是它自述 ✓）：%s → %s"
              % (self._prog_n, PROGRESS_MAX, phrase, self.say(phrase)))

    def recover(self) -> bool:
        """★重启后先把"上一轮没说完的话"补上★ ✓（用户要求：「容易中断进程」✗ ⇒ 不丢结果 ✓）

        两种情形都处理 ✓：
          · 上一轮的**进程还活着**（说明是我这边被杀 ✓ 不是它死了）⇒ **重挂**上去等它 ✓ 然后说 ✓
          · 已经跑完但**没说过**（`spoken=false` ✓）⇒ 现在补说 ✓
        """
        rec = dshrun.load_round()
        if not rec or rec.get("spoken"):
            return False
        rid = rec.get("rid")
        if dshrun._alive(rec.get("pid") or 0):
            print("      ★上一轮还在跑 ✓（rid=%s pid=%s）⇒ 重挂上去等它 ✓ **结果不会丢** ✓"
                  % (rid, rec.get("pid")))
            rec = dshrun.wait(rec, timeout=self.harness_timeout, on_tick=self._tick)
        elif rec.get("status") != "done":
            # ★状态字段不许说谎★ ✗（实测发现的 ✓）：进程早没了 ✓
            #   而 `status` 还写着 `running` ✗ ⇒ 下一个看它的人会被骗 ✓
            #   ⇒ 谁发现"它其实结束了" ✗ 谁就负责把状态**改成事实** ✓
            rec["status"] = "done"
            print("      （顺手改状态：round.json 原先写着 running ✗ 其实进程已结束 ⇒ 改成 done ✓）")
        out = (rec.get("out_text") or dshrun.read_round_text(rec)[0]).strip()
        txt = honest_reply(clean(out, limit=80), bool(rec.get("force")),
                           int(rec.get("tools") or 0))
        rec["spoken"] = True
        if not txt:
            print("      [!] 上一轮（rid=%s）没有可说的话 ✗ ⇒ 保持沉默 ✓ 只记一笔 ✓" % rid)
            self.log({"kind": "recover", "rid": rid, "said": "", "note": "没有输出"})
            dshrun._save(rec)
            return False
        print("      ★补说上一轮的结果 ✓：%s → %s" % (txt, self.say(txt)))
        self.log({"kind": "recover", "rid": rid, "said": txt, "sec": rec.get("sec")})
        dshrun._save(rec)
        return True

    def _run_session(self, task: str, t0: float) -> tuple[dict, float]:
        """★跑一个会话★ ✓ —— ★现在是"独立进程 ＋ 落盘"★ ✗

        为什么要换 ✗（用户原话 ✓：「容易中断进程」）：
          旧版是 `subprocess.run(...)` ✓ ＝ 会话挂在 talk.py 名下 ✗
          ⇒ talk.py 一被杀 ⇒ **会话陪葬 ⇒ 这一轮的结果就没了** ✗（23:50 真丢过一次 ✓）
        ⇒ 现在 ✓：`dshrun.start()` 起**独立进程组** ✓ 输出**直接写文件** ✓
          ⇒ **我被杀了它照样跑完** ✓ 而且 `logs/round.json` 记着它 ✓
          ⇒ 我重启后 `recover()` 一看就能把没说的话补上 ✓
        """
        try:
            rec = dshrun.start(task, profile=self.profile, cwd=str(ROOT))
        except Exception as e:                   # ★起不来也要大声★ ✗（不许静默装死 ✗）
            print("      [X] 会话起不来 ✗：%s: %s" % (type(e).__name__, str(e)[:200]))
            return {}, time.time() - t0
        self._seen_prog, self._prog_n = [], 0
        self._prog_said = set()                  # 每一轮重新算 ✓（上一轮的"说过"不算 ✗）
        self._last_tick = 0.0
        said_filler = False
        t0 = float(rec.get("t0") or t0)

        def tick(r: dict) -> None:
            nonlocal said_filler
            self._tick(r)
            if (self.filler and not said_filler
                    and time.time() - t0 >= self.filler_after):
                said_filler = True
                line = FILLERS[self.filler_i % len(FILLERS)]
                self.filler_i += 1
                print("      ~ 垫一句（它还在忙 ✓ 实测不垫就会静默几十秒 ✗）：%s → %s"
                      % (line, self.say(line)))

        rec = dshrun.wait(rec, timeout=self.harness_timeout, on_tick=tick)
        out = rec.get("out_text") or ""
        return ({"rc": rec.get("rc"), "out": out, "sec": rec.get("sec"), "rec": rec},
                round(time.time() - t0, 2))

    def answer_harness(self, who: str, msg: str) -> str:
        """★★整轮交给一个 harness 会话★★ —— 这是"接入 harness"的落点 ✓

        它和 `answer_api` 的本质区别 ✗：
          `answer_api` 只能**产出文字** ✓ ⇒ "让它做事"就只能靠外面写死流程 ✗
          这一条**真的会动手** ✓ —— 因为它手上有 mc 的那组工具 ✓
          （shell/文件工具在 mcbot 剖面里**按 id 关掉了** ✓ 见 profile 的 patch ✓
            ⇒ 游戏里说的话永远碰不到项目文件 ✓）

        ★世界实况由我们**先查好塞给它**★ ✓（不是让它自己去猜 ✓）：
          `state` 是 `dshdigest` 的原样回执 ✓ + `convo` 是最近几条聊天 ✓
          ⇒ 每条消息一个**全新会话** ✓ 但上下文靠这两段接上 ✓（所以它不会"失忆"✓）
        """
        self.refresh_state()                     # ① 先量一遍世界 ✓
        self.hist.append((who, msg))
        self.hist = self.hist[-8:]
        convo = "\n".join("%s：%s" % (w, m) for w, m in self.hist[:-1]) or "（这是第一句）"
        force = self.force_exec or looks_imperative(msg) or self.force_all
        # ★跨轮连续性★ ✓：先把"上一轮的落盘记录"读出来 ✓（此时 round.json 还是**上一轮**的 ✓）
        prev = last_round_brief(dshrun.load_round())
        if prev:
            print("      （把上一轮的真实情况也塞进去了 ✓：%s…）" % prev[:70])
        task = build_task(self.persona, self.state[:400], convo, who, msg,
                          force=force, prev=prev)
        t0 = time.time()
        r, dt = self._run_session(task, t0)
        if not r.get("rc") and not r.get("out"):
            self.log({"kind": "error", "brain": "harness", "who": who, "msg": msg,
                      "err": "会话没起来（rc/out 都空）⇒ 这一轮保持沉默 ✗ 不编一句 ✓"})
            return ""
        # 这一轮"有没有动手" ✓ —— 去 `logs/mc_mcp.jsonl` 数它真调了几个工具 ✓
        #   ★这是**世界级的旁证**★ ✗：不靠模型自述"我做过了"✓（本项目最贵的教训 ✓）
        #   ⚠ 别用不存在的字段去数 ✗（我第一版就是这么写的 ✗ 会永远数出 0 ✓
        #     而"永远 0"这种**沉默的错**正是这个项目最恨的东西 ✓ 见错题本 ✓）
        tools = self.count_tool_calls(t0)
        if tools:
            print("      （它真的动手了 ✓：这一轮 mc 工具调用 %d 次 ✓ 见 logs/mc_mcp.jsonl ✓）" % tools)
        # ★★"说了就得做"的兜底★★ ✗（用户要求 ✓）
        #   是**指令**却**一个工具都没调** ⇒ **中继层强制重做一次** ✓
        #   为什么不写进提示词 ✗（P46 纪律 ✓）：**提示词是请求 ✓ 不是保证** ✗
        if force and tools == 0:
            print("      [!] 这是**指令**却 0 次工具调用 ✗ ⇒ **强制重做一次** ✓（不指望它自觉 ✗）")
            t1 = time.time()
            task2 = (task + "\n\n★★打回重做★★ ✗：刚才那一轮你**一个工具都没调** ✗ ——"
                     "而这句话是**指令** ✓ ⇒ 现在**必须**真的去执行 ✓：调 mc 的工具把这件事做完 ✓"
                     "（做不成就留下**失败的回执** ✓ 并说清为什么 ✗）⇒ 然后照实回结果 ✓。\n")
            r2, dt2 = self._run_session(task2, t1)
            if r2.get("rc") is not None or r2.get("out"):
                r = r2
            dt += dt2
            tools = self.count_tool_calls(t0)
            print("      重做后工具调用 = %d 次 %s"
                  % (tools, "✓" if tools else "✗ ⇒ **照实记账** ✓ 日志里 force=true acted=false ✓ 不谎报 ✓"))
        # ★出口在这里才定稿★ ✗ —— 必须等**重做**跑完 ✓ 才知道这一轮到底动没动手 ✓
        #   ⇒ 再套一层**诚实兜底** ✓：是指令却 0 次调用 ⇒ 那句话前面加「（我还没真动手 ✗）」
        #     （不改模型的话 ✓ 只把真相标出来 ✓ —— 免得它说"我去弄了"而世界没变 ✗）
        txt = honest_reply(clean(r.get("out") or "", limit=80), force, tools)
        rrec = r.get("rec") or {}
        if rrec:
            # ★把"这一轮是不是指令 / 动了几次手"也落进 round.json★ ✗
            #   ⇒ 重启后 `recover()` 才能照同一套规矩把话说出去 ✓（含"（我还没真动手 ✗）"那层 ✓）
            rrec.update({"force": force, "tools": tools, "spoken": False})
            dshrun._save(rrec)
        self.log({"kind": "reply", "brain": "harness", "profile": self.profile,
                  "persona": self.persona_name, "who": who, "heard": msg, "said": txt,
                  "sec": round(dt, 2), "rc": r.get("rc"), "harness_sec": r.get("sec"),
                  "force": force, "tools": tools, "acted": tools > 0})
        if not (r.get("out") or "").strip():
            print("      [!] harness 没有给出可说的话 ✗（rc=%s ✓ 所以**保持沉默**✗ 不编一句 ✓）"
                  % r.get("rc"))
            return ""
        print("      ← %s（%.1fs ✓ 剖面 %s ✓）" % (txt, dt, self.profile))
        return txt

    def answer_api(self, who: str, msg: str) -> str:
        self.refresh_state()
        self.hist.append((who, msg))
        self.hist = self.hist[-8:]
        convo = "\n".join("%s：%s" % (w, m) for w, m in self.hist)
        sysmsg = PERSONA.format(bot=BOT, where=self.state[:200], doing=self.doing,
                                held=(re.search(r"held=(\S+)", self.state).group(1)
                                      if re.search(r"held=(\S+)", self.state) else "?"))
        msgs = [{"role": "system", "content": sysmsg},
                {"role": "user", "content": "最近的聊天记录（最新的在最后）：\n" + convo
                 + "\n\n请只回**最新那一条**。一句话，别解释。"}]
        t0 = time.time()
        try:
            out = self.llm.chat(msgs, temperature=0.8)
        except Exception as e:
            print("      [X] 模型调用失败 ✗：%s" % str(e)[:300])
            self.log({"kind": "error", "who": who, "msg": msg, "err": str(e)[:300]})
            return ""
        txt = clean(out.get("content") or "")
        dt = time.time() - t0
        self.log({"kind": "reply", "who": who, "heard": msg, "said": txt,
                  "sec": round(dt, 2), "usage": self.llm.usage.copy(),
                  "calls": self.llm.calls, "model": self.llm.model})
        print("      ← %s（%.1fs ✓ 模型 %s ✓ 累计 token %s）"
              % (txt, dt, self.llm.model, self.llm.usage["total"]))
        return txt

    # ══ ★★空闲起话头★★（用户要求 ✓ 见文件头 ⑥ 与 CUE_COOLDOWN 的注释 ✓）═══════
    def _dget(self, key: str, default: str = "") -> str:
        """从 `dshdigest` 那一行里抠一个字段 ✓（读不到就给默认值 ✓ ★绝不猜★ ✗）

        ⚠ 值必须**到逗号为止** ✗ ——
          实测（2026-09-21 ✓ 被 `--idle-check` 当场抓出来 ✓）：
          `free=0,sel=0` 用 `\\S+` 会把整段 `0,sel=0` 都吃进去 ✗
          ⇒ `int()` 抛异常 ⇒ 被外层 except 吞掉 ⇒ ★**所有由头一起变成"没有"**★ ✗
          ⇒ 表现成"它从来不主动开口"✗ 而且**一声不响**✗（正是本项目最恨的那种错 ✓）
        """
        m = re.search(r"(?:^|[\s,])%s=([^\s,]+)" % re.escape(key), self.state or "")
        return m.group(1) if m else default

    def idle_cue(self) -> tuple[str, str, str] | None:
        """★挑一个"有由头"的理由★ ✓ ⇒ (代号, 给模型看的由头, 人话摘要) ✓
        没由头 ⇒ None ⇒ **这一轮它就闭嘴** ✗（★这是本功能最要紧的一条★ ✓）

        ⚠ 只用 `dshdigest` 那一段 ✓ ★绝不碰事件流★ ✗ ——
          `events_since()` 会**推进游标** ✗ ⇒ 玩家的聊天会被这里吃掉 ✗
          ⇒ 它就再也回不了你话 ✗（这种"沉默的错"正是本项目最恨的 ✓ 见错题本 ✓）
        """
        self.refresh_state()
        try:
            hp = float(self._dget("hp", "20"))
            food = float(self._dget("food", "20"))
            free = int(float(self._dget("free", "1")))
            host = int(float(self._dget("hostiles", "0")))
            drops = int(float(self._dget("drops", "0")))
            tm = int(float(self._dget("time", "6000")))
        except Exception:
            return None                      # 读不到 ⇒ ★宁可沉默 ✓ 也不瞎说 ✗
        cands: list[tuple[str, str, str]] = []
        if host > 0:                         # ★危险优先★ ✓ 越急的排越前 ✓
            cands.append(("mob", "附近有 %d 只怪 ⇒ 喊一声提醒他 ✓" % host, "附近有怪"))
        if hp < 12:
            cands.append(("hurt", "你自己血只剩 %g ⇒ 说一句 ✓" % hp, "血不多了"))
        if food <= 6:
            cands.append(("hungry", "你饱食只剩 %g ⇒ 该吃了 ✓" % food, "饿了"))
        if drops > 0:
            cands.append(("drops", "地上有 %d 个掉落物（★5 分钟就消失 ✗）⇒ 提一句 ✓" % drops, "地上有东西"))
        if free <= 0:
            cands.append(("full", "你背包★一格空位都没有★ ⇒ 念叨一句 ✓", "包满了"))
        if 13000 <= tm < 23000:
            cands.append(("night", "现在是★夜里★（time=%d ⇒ 天黑了）⇒ 提一句睡觉 ✓" % tm, "天黑了"))
        elif tm >= 23000 or tm < 2000:
            cands.append(("dawn", "★天刚亮★（time=%d）⇒ 起个话头 ✓" % tm, "天亮了"))
        now = time.time()
        for cue, hint, human in cands:
            if now - self.cue_at.get(cue, 0.0) >= CUE_COOLDOWN.get(cue, 1200.0):
                return (cue, hint, human)    # ★同一个由头在冷却里就跳过 ✓（换下一个 ✓）
        return None

    def answer_idle(self, cue: str, hint: str, human: str) -> str:
        """★自己起个话头★ ✓ —— 同一套人格 ✓ 同一份实况 ✓ 同一个出口 ✓

        ★这一轮明确**不许调工具**★ ✗：要动手得等玩家开口 ✓
        （自己擅自开工 ⇒ 玩家回来发现假人跑到岛另一头 ✗ 那是最坏的一种"拟人"✗）
        """
        self.refresh_state()
        self.hist = self.hist[-8:]
        convo = "\n".join("%s：%s" % (w, m) for w, m in self.hist[-6:]) or "（还没聊过）"
        try:
            prev = last_round_brief(dshrun.load_round(), limit=80)
        except Exception:
            prev = ""
        task = (self.persona + "\n\n"
                + "──────── 你现在这一轮的处境（★刚查的实况 ✓ 不是记忆 ✗）────────\n"
                + (self.state or "")[:400] + "\n\n"
                + (("──────── 你**上一轮**做过什么（真实记录 ✓）────────\n" + prev + "\n\n")
                   if prev else "")
                + "──────── 最近的聊天（最新在最后 ✓）────────\n" + convo + "\n\n"
                + "──────── 现在 ────────\n"
                + "★没有人跟你说话★ ✗ —— 是**你自己想开口** ✓\n"
                + "由头：" + hint + "\n\n"
                + "──────── 你要做的 ────────\n"
                + "1. ★这一轮**一个工具都不许调**★ ✗ —— 只说一句话 ✓（要动手得等他开口 ✓）\n"
                + "2. 就着这个由头起一句短的（≤20 字 ✓ 想带上实况里的数字就带上 ✓）\n"
                + "3. ★别说「我去…」这种要动手的承诺★ ✗ —— 这一轮你不会动手 ✓\n"
                + "   想说就改成问他一句（「要我过去吗」✓）\n"
                + "4. ★最后**只输出**你要说出口的那一两句话★ ✗\n"
                + "   （不写过程 ✗ 不写工具名 ✗ 不加引号 ✗）\n"
                + "5. ★说不出就别硬说★ ✗ —— 那就只输出四个字：这次不说\n")
        t0 = time.time()
        r, dt = self._run_session(task, t0)
        out = clean(r.get("out") or "", limit=80)
        acted = self.count_tool_calls(t0)     # ★说好不许动手★ ✗ ⇒ 记账 ✓（不听自述 ✓）
        if acted:
            print("      [!] 起话头这一轮它调了 %d 次工具 ✗（说好不许动手 ✗）⇒ 照实记账 ✓" % acted)
        if (not out) or any(w in out for w in IDLE_NO_WORDS):
            print("      ~ 它自己觉得没什么好说的 ✓ ⇒ 保持沉默 ✓（★不硬凑★ ✓）")
            self.log({"kind": "idle_skip", "brain": self.brain, "cue": cue})
            return ""
        self.log({"kind": "idle_say", "brain": self.brain, "persona": self.persona_name,
                  "cue": cue, "said": out, "sec": round(dt, 2), "tools": acted})
        return out

    def maybe_idle_talk(self) -> bool:
        """★该不该自己开口★ ✓ —— ★四道门槛缺一不出声★ ✗（见 CUE_COOLDOWN 上面的注释 ✓）"""
        if not self.idle_talk:
            return False
        now = time.time()
        if now - self.idle_checked < IDLE_CHECK_EVERY:
            return False
        self.idle_checked = now
        if now - max(self.idle_at, self.last_reply) < self.idle_every:
            return False
        self.replies = [x for x in self.replies if now - x < 300]
        if len(self.replies) >= self.budget:          # 额度跟回话共用 ✓ 绝不刷屏 ✗
            return False
        if self.hist and now - self.last_reply < max(self.gap, 30.0):
            return False                              # 刚聊过 ⇒ 让位 ✓
        cue = self.idle_cue()
        if not cue:
            return False                              # ★没由头 ⇒ 闭嘴★ ✓
        name, hint, human = cue
        print("      ~ 自己起个话头（由头＝%s ✓／%s ✓）" % (name, human))
        txt = self.answer_idle(name, hint, human)
        now2 = time.time()
        self.cue_at[name] = now2                      # 这个由头用过了 ⇒ 进冷却 ✓
        self.idle_at = now2                           # ★不管说没说出来都退避一会儿★ ✓
        if not txt:
            return False
        print("      说：%s" % self.say(txt))
        self.last_reply = now2
        self.replies.append(now2)
        return True

    def reload_persona_if_changed(self) -> None:
        """★每一轮都看一眼人设文件有没有被换掉★ ✓

        为什么必须补这一手 ✗（写文档时自己发现的 ✓）：
          我只在 `Talk.__init__` 里读一次人设 ✓
          ⇒ **命令行**改了 `personas/current.md` ⇒ 正在跑的监听**根本不知道** ✗
          ⇒ 而我在文档里却写了"不用重启就生效" ✗ —— **文档比代码更乐观** ✗ 这就是要抓的那类错 ✓
        ⇒ 修法：每轮比一次 `mtime` ✓（几乎是零成本 ✓）变了就重读 ✓
        """
        p = PERSONA_DIR / (self.persona_name + ".md")
        try:
            m = p.stat().st_mtime
        except Exception:
            return
        if m != self.persona_mtime:
            t = _load_persona_file(self.persona_name)
            if t:
                self.persona = t
                self.persona_mtime = m
                print("      ★人设文件被换过了 ✓ 已重新读入（%d 字 ✓）⇒ 从这一轮起就是新声音 ✓"
                      % len(t))

    def set_persona(self, text: str, source: str = "?") -> int:
        """★"输入人设的地方"的落点★ ✓（游戏里说的那一句就落到这里 ✓）

        写 `personas/current.md` ✓（UTF-8 ✓ 无 BOM ✓ 走 Python 写 ✓ 见项目纪律 ✓）
        并且**立刻**把 `self.persona` 换成新的 ✓ ⇒ **当轮生效** ✓ 不用重启 ✓
        留痕 ✓：`personas/current.meta.jsonl` 记一条 ✓（谁改的/什么时候/多少字 ✓）
        """
        text = (text or "").strip()
        if not text:
            return 0
        if len(text) > 6000:
            text = text[:6000]
        PERSONA_DIR.mkdir(parents=True, exist_ok=True)
        p = PERSONA_DIR / "current.md"
        p.write_text(text + "\n", encoding="utf-8", newline="\n")
        try:
            with (PERSONA_DIR / "current.meta.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "source": source,
                                    "chars": len(text), "head": text[:60]},
                                   ensure_ascii=False) + "\n")
        except Exception:
            pass
        self.persona = text                      # ★当轮生效★ ✓
        self.persona_name = "current"
        self.persona_source = str(p)
        return len(text)

    def count_tool_calls(self, since: float) -> int:
        """数一下「这一轮它真调了几个 mc 工具」✓ —— 从 `logs/mc_mcp.jsonl` 的 `at` 时间戳算 ✓

        为什么值得单独写一个方法 ✗：**这就是"动手"的唯一客观证据** ✓
        模型说什么都可能编 ✓ 但日志是工具自己写的 ✓（纪律②：看世界真值 ✗ 不听自述 ✗）
        """
        p = ROOT / "logs" / "mc_mcp.jsonl"
        if not p.is_file():
            return 0
        n = 0
        try:
            for line in p.read_text(encoding="utf-8").splitlines()[-20:]:
                try:
                    rec = json.loads(line)
                    ts = time.mktime(time.strptime(rec.get("at", ""), "%Y-%m-%d %H:%M:%S"))
                except Exception:
                    continue
                if ts >= since - 2.0:
                    n += 1
        except Exception:
            return n
        return n

    def log(self, obj: dict) -> None:
        try:
            LOG.parent.mkdir(parents=True, exist_ok=True)
            obj["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception as e:
            # 记录：审计落不了盘 ⇒ "我到底说没说过"的证据链断了（不许静默）
            print("[记录] 语言审计写不进去（证据链断）：%s: %s"
                  % (type(e).__name__, str(e)[:80]), file=sys.stderr)

    # ── ★主动扳机（用户第 1 条 ✓）──────────────────────────────────────────────
    def proactive(self, evs: list) -> int:
        """★事件流 ⇒ 该说就说★ ✓（★与"应答"那条路**并列**✗ 不是替代 ✓★）

        ★为什么单开这一段✗★：`round()` 原来**只认 `chat`** ✗ ⇒
          受伤／掉落快过期／升级／被 tp ／走完一趟 ⇒ **一律没人看** ✗✗
          （用户原话：「把"闸门"从**被动应答**改成**主动扳机**」✓）
        规矩三条 ✓：
          ① 决策在 `speech_loop.plan`（纯函数 ✓ 有离线判据 L1~L9 ✓）—— 这里**只负责发** ✓
          ② **出口仍然只有 `dshsay` 一个** ✗（本函数不碰世界 ✓ 不下指令 ✓）
          ③ ★连"想说但没说"的也写审计✗★（不然"它当时为什么闭嘴"查不出来 ✓ 用户第 5 条 ✓）
        """
        if not self.speech_on:
            return 0
        try:
            tr, self.job_snap = SL.job_transitions(self.job_snap, JS.all_jobs())
        except Exception as e:
            tr = []
            print("      （任务账本读不到 ✗ 只跑事件扳机 ✓）：%s" % e)
        # ★★"决策＋渲染＋发"**全部交给 `SL.run`**✗★★（P106 ✓）
        #   ★为什么✗★：真正在跑的是 `acp_talk.py` ✗ ⇒ 两处各写一份"发"的逻辑
        #     ⇒ 就会出现"测试里全绿、游戏里听不到"✗（2026-09-30 实机撞到 ✓ ⇒ P137 ✓）
        return SL.run(evs, self.loop, lambda a: self.say(a.text or a.line),
                      transitions=tr, cfg=self.render_cfg, rng=self.render_rng,
                      audit=SPEECH_LOG, tag="主动说")

    def round(self) -> int:
        self.reload_persona_if_changed()          # ★命令行换了人设也要当轮生效★ ✓
        evs = self.events_since()
        if not evs:
            return 0
        # 先看这一轮里模组自己回过没有 ✓（它的 ack 会记成 auto_reply ✓ 见 v2.8 ✓）
        acked = any(" auto_reply " in e or e.split(" ", 1)[1].startswith("auto_reply") for e in evs)
        n = 0
        for e in evs:
            if " chat " not in e:
                continue
            m = re.search(r"chat who=(\S+) len=(\d+) msg=(.*)$", e)
            if not m:
                continue
            who, _len, raw = m.group(1), m.group(2), m.group(3)
            msg = unesc(raw)
            print("      → 听到 %s：%s" % (who, msg))
            # ★记忆：见到这个人（用户第 4 条 ✓）★ —— 只记账 ✓ 不说话 ✓（蹭热度的话留给闸门 ✓）
            try:
                M3.seen_person(who, place=getattr(self, "doing", "")[:40])
            except Exception as e:
                print("         （记忆写不进去 ✗：%s）" % e)
            # ★⓪ 硬指令前缀★ ✓：`!do …` / `!执行 …` ⇒ **剥掉前缀** ＋ **强制当指令** ✓
            #   （不然模型会看到字面的 `!do` ✗ 有点脏 ✓；而且这样你就有一个"必须执行"的显式入口 ✓）
            hard = bool(re.match(r"^[!！]\s*(do|go|执行|做)\s*", msg, re.I))
            if hard:
                msg, hard = strip_hard_prefix(msg)
                print("         （硬指令前缀 ✓ 已剥掉 ⇒ 强制当指令 ✓）：%s" % msg)
            # ★① 先看这是不是"在给设定"★ ✓（用户要求："给一个输入人设的地方" ✓）
            newp = parse_persona_set(msg) if who != BOT else None
            if newp:
                n = self.set_persona(newp, source="chat:%s" % who)
                print("      ★收到人设 ✓ 已写 %s（%d 字 ✓）⇒ **当轮就生效** ✓ 不用重启 ✓"
                      % (self.persona_source, n))
                ok, why = True, "★这是「给设定」★ ⇒ 必须回一句确认 ✓"
            else:
                ok, why = self.should_reply(who, msg, acked)
            print("         %s %s" % ("回 ✓" if ok else "不回 ✗", why))
            # ★② 判定"这是不是指令"★ ✓（用户要求：和 bot 说的话也得让 bot 去执行 ✓）
            self.force_exec = bool(ok) and (looks_imperative(msg) or self.force_all or hard)
            if self.force_exec:
                print("         ★这是**指令** ✓ ⇒ 必须真的执行 ✓"
                      "（跑完去数工具调用 ✓ 0 次就打回重做 ✓ 见 IMPERATIVE_VERBS 注释 ✓）")
            if not ok:
                continue
            n += 1
            txt = self.answer(who, msg)
            if not txt and newp:
                # ★人设输入口必须有回执★ ✗：设了却一声不吭 ⇒ 你不知道成没成 ✓
                txt = "记住了。"
                print("      （人设已存 ✓ 但会话没出声 ⇒ 中继层补一句回执 ✓）")
            if txt:
                print("      说：%s" % self.say(txt))
                self.last_reply = time.time()
                self.replies.append(self.last_reply)
                try:
                    M3.said_to(who)          # ★我回了他一句 ⇒ 也算一次往来 ✓（用户第 4 条 ✓）★
                except Exception:
                    pass
            break                    # 一轮只回一条 ✓（不刷屏 ✗）
        # ★应答跑完 ⇒ 再跑主动扳机✗★（顺序是有意的 ✓：先把人回完 ✓ 再自言自语 ✓
        #   —— 反过来的话，一句"我升级了"会插在你问题前面 ✗ 那才是没礼貌 ✓）
        self.proactive(evs)
        return n


def main(argv: list[str]) -> int:
    a = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            a[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            a[argv[i].lstrip("-")] = True
            i += 1
    key = pick_key()
    base = __import__("os").environ.get("AGENT_API_BASE") or "https://api.openai.com/v1"
    model = __import__("os").environ.get("AGENT_MODEL") or "gpt-4o-mini"
    brain = str(a.get("brain") or "harness")
    profile = str(a.get("profile") or "mcbot")
    pname = str(a.get("persona") or DEFAULT_PERSONA)
    print("=" * 74)
    print("talk.py —— 假人对话（★接入 harness★ ✓）")
    print("  brain    : %s" % ("harness ✓（它会**真的动手** ✓ 用 mc 的 MCP 工具 ✓）"
                               if brain == "harness" else "api（直连模型 ✓ 只会说话 ✗ 不会动手 ✗）"))
    if brain == "harness":
        print("  profile  : %s（%s）" % (profile, dshrun.find_dsh() if _dsh_ok() else "★找不到 dsh★ ✗"))
        print("  persona  : %s ← %s（%s ✓）"
              % (pname, str(PERSONA_DIR / (pname + ".md")),
                 "★换角色就改它 ✓ 游戏里打 `!人设 <设定>` 也能改 ✓ 当轮生效 ✓★"))
        print("  ★说了就得做★：带动作动词的话会被判成**指令** ✓ 跑完去数工具调用 ✓"
              " 0 次就打回重做一次 ✓")
    else:
        print("  endpoint : %s" % base)
        print("  model    : %s" % model)
        print("  key      : %s" % ("已配置 ✓（%s…）" % key[:6] if key else
                                   "★没有★ ✗ —— 设 AGENT_API_KEY ✓ 或写 %s ✓" % KEYFILE))
    print("=" * 74)

    if a.get("check"):
        if not key:
            print("[X] 没有 key ✗ ⇒ 无法验证（DeepSeek: base=%s  model=%s）" % (DEEPSEEK_BASE, DEEPSEEK_MODEL))
            return 2
        llm = LLM(key=key)
        t0 = time.time()
        try:
            out = llm.chat([{"role": "system", "content": "只回两个字：在的"},
                            {"role": "user", "content": "在吗"}], temperature=0.0)
        except Exception as e:
            print("[X] 调用失败 ✗：%s" % str(e)[:400])
            return 1
        print("[OK] 通了 ✓ %.1fs ｜ 回：%s ｜ usage=%s"
              % (time.time() - t0, (out.get("content") or "")[:80], llm.usage))
        return 0

    # ★`--idle-check`：只判一次"现在会不会自己开口" ★ ✓
    #   为什么要有它 ✗：这个功能**只在真跑起来之后才看得见** ✗ ⇒ 没法单独验 ✓
    #   ⇒ 它**只跑判定**（读一次 `dshdigest` ✓）★不调模型 ✓ 不说话 ✓ 不碰游戏状态 ✓★
    if a.get("idle-check") is not None:
        t = Talk(a)
        if isinstance(a.get("idle-check"), str):
            # ★`--idle-check 1`：用一条**造出来的**实况走一遍 ★ ✓
            #   为什么需要 ✗：真实况没由头时它闭嘴 ✓ —— 那是**设计** ✓
            #   但"闭嘴"**证明不了**"有由头时会开口" ✗（分不清"逻辑对"和"永远不出声"✗）
            t.state = ("dshdigest name=Bot pos=4127.90,71.00,3.72 yaw=0.0 pitch=0.0 hp=6.0 "
                       "food=3 sat=0.0 xp=7 mode=survival onground=true dim=minecraft:overworld "
                       "time=16000 day=79 held=exdeorum:wooden_hammerx1 "
                       "inv[x]kinds=36,items=223,free=0,sel=0 ents=0 hostiles=2 "
                       "nearest=minecraft:zombie@3.0 drops=3 look=none")
            t.state_at = time.time()          # 让 refresh_state 这一轮别覆盖它 ✓（30 秒缓存 ✓）
            print("（★用的是**造出来的**实况★：血 6／饱食 3／包满／夜 16000／2 只怪／地上 3 个掉落物 ✓）")
        cue = t.idle_cue()
        print("人格：%s ｜ 实况：%s" % (t.persona_name, t.doing))
        print("  解析到的字段：hp=%s food=%s free=%s hostiles=%s drops=%s time=%s"
              % tuple(t._dget(k, "（没读到 ✗）") for k in
                      ("hp", "food", "free", "hostiles", "drops", "time")))
        if not cue:
            print("[·] 现在**没有由头** ⇒ 它不会自己开口 ✓（★这是设计如此 ✓ 不是故障 ✗）")
            return 0
        name, hint, _human = cue
        print("[→] 有由头 ✓：%s（%s）" % (name, _human))
        print("    会喂给模型的由头：%s" % hint)
        print("    ★真起话头还要再过三道门槛★：距上次说话 ≥%s 秒 ✓／5 分钟额度 ✓／刚聊过让位 ✓"
              % (a.get("idle-talk") or "240"))
        return 0

    # ★`--demo`：不用游戏、不用别人说话 ✓ 直接看它**用真人格**怎么答 ★
    #   （用来回答"是不是只有几句写死的话"✗ —— 这几句全是模型现想的 ✓ 每次都不一样 ✓）
    #   ⚠ harness 大脑下**不需要 key** ✗ —— 会话自己带凭据 ✓（见 ~/.dsh/.credentials.yaml ✓）
    if a.get("demo") is not None:
        if not key and brain != "harness":
            print("[X] 没有 key ✗")
            return 2
        t = Talk(a)
        t.refresh_state()
        # ★`--ask-file`：从 **UTF-8 文件**读这一句 ★ ✓
        #   为什么要这个 ✗：这台 shell 是 Windows PowerShell 5.1 ✗
        #   中文 argv 会被按 GBK 转坏 ✗（实测见 tools/dshrun.py 开头 ✓）
        #   ⇒ 想测中文/想发中文指令 ⇒ **走文件** ✓ 不要走命令行 ✗
        if a.get("ask-file"):
            qs = [Path(str(a["ask-file"])).read_text(encoding="utf-8").strip()]
        else:
            qs = [a["demo"]] if isinstance(a["demo"], str) else \
                 ["你在干嘛？", "你会筛矿吗？", "这岛上还有吃的吗？"]
        print("人格：%s ｜ 实况：%s" % (t.persona_name, t.doing))
        for q in qs:
            print("\n【玩家】%s" % q)
            txt = t.answer("Au_Sn", q)
            print("【%s】%s" % (BOT, txt or "（没说话 ✗）"))
        if brain != "harness":
            print("\n累计：%d 次调用 ✓ token=%s ✓ 模型=%s"
                  % (t.llm.calls, t.llm.usage["total"], t.llm.model))
        return 0

    if not key and brain != "harness":
        print("[X] 没有 key ✗ ⇒ **不会假装能对话** ✓")
        print("    两条路 ✓：① 设环境变量 AGENT_API_KEY ✓ ② 写 %s ✓" % KEYFILE)
        print("    或者走 harness ✓：`--brain harness` ✓（用你自己 harness 的凭据 ✓ 不用 key ✓）")
        return 2

    t = Talk(a)
    # ★★开机第一件事：把上一轮"没说完的话"补上★★ ✓
    #   用户原话 ✓：「容易中断进程」✗ ⇒ 被杀/重启**不该丢结果** ✓
    #   两条路都在 `recover()` 里 ✓：还在跑就重挂等它 ✓ 已经跑完就补说 ✓
    if t.brain == "harness":
        try:
            if t.recover():
                print("      （上一轮的结果已补说 ✓ 见 logs/round.json 的 spoken=true ✓）")
        except Exception as e:
            print("      [X] 补说上一轮失败 ✗：%s: %s" % (type(e).__name__, str(e)[:200]))
    if a.get("recover"):
        return 0
    if a.get("watch"):
        print("盯着聊天…（Ctrl+C 退出 ✓ 每 %.0fs 查一次 ✓ 每条回话间隔 ≥%.0fs ✓）" % (2.0, t.gap))
        print("  大脑：%s ｜ 人格：%s ｜ 剖面：%s"
              % (t.brain, t.persona_name, t.profile if t.brain == "harness" else "(不适用)"))
        print("  ★自己起话头★：%s（最短 %.0fs 一次 ✓ ★而且必须有由头★ ✗ —— 没由头它就闭嘴 ✓）"
              % ("开 ✓" if t.idle_talk else "关 ✗（--no-idle-talk ✓）", t.idle_every))
        hold = a.get("hold-quiet", True)      # 默认开 ✓（见 keep_quiet 的注释 ✓）
        print("  保持安静门槛：%s（%s）"
              % ("开 ✓ 模组的 canned 快嘴会让位 ✓" if hold else "关 ✗（那模组会抢答 ✗）",
                 "每 10 秒一条无害读指令 ✓" if hold else "--no-hold-quiet 指定"))
        # 先吃掉历史事件 ✓（免得一开机就对着旧消息说话 ✗）
        try:
            t.events_since()               # 先吃掉历史事件 ✓（游戏关着时这一句会失败 ⇒ 下面兜住 ✓）
        except Exception as e:
            print("      [!] 一开机通道就不通 ✓（游戏是不是关了/在重启？✓）：%s" % str(e)[:100])
        last_hold = 0.0
        fails = 0
        while True:
            try:
                time.sleep(2.0)
                if hold and time.time() - last_hold > 10:
                    t.keep_quiet()
                    last_hold = time.time()
                if not t.round():
                    t.maybe_idle_talk()       # ★没人跟它说话时，才轮到"它自己起话头"✓
                if fails:
                    print("      ★通道回来了 ✓（刚才连败 %d 次 ✓）继续盯着 ✓" % fails)
                fails = 0
            except KeyboardInterrupt:
                print("\n退出 ✓ 共回话 %d 条 ｜ 累计 token %s" % (len(t.replies), t.llm.usage["total"]))
                return 0
            except Exception as e:
                # ★游戏关了不是我的错 —— 但我**不该跟着死**★ ✗
                #   实测（2026-09-21 00:3x ✓）：关掉游戏 ⇒ cmd0（游戏里的计算机）不应答 ⇒
                #   `BridgeTimeout` 一路冒到 top ⇒ **整个监听进程退出** ✗（exit 1 ✓）
                #   ⇒ 这正是用户说的"容易中断进程"✗ 只是触发源从"我杀它"换成了"游戏关了"✓
                #   ⇒ 修法：**退避重试、等它回来** ✓（游戏重开只要 ~2 分钟 ✓ 等得起 ✓）
                fails += 1
                wait = min(20.0, 2.0 * fails)
                print("      [!] 通道不通（第 %d 次 ✗）：%s: %s ⇒ %.0fs 后重试 ✓（我就等着 ✓ 进程不退出 ✓）"
                      % (fails, type(e).__name__, str(e)[:110], wait))
                time.sleep(wait)
    t.events_since()
    n = t.round()
    print("本轮回话 %d 条 ✓" % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
