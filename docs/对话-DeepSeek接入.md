# 对话：让假人用 DeepSeek 说话（不是几句写死的话 ✓）

> 用户要求原话 ✓：「**对话能调用 deepseek 吗，不能是只有几个简单的词，这方面应该有现成的参考**」✓
>
> 答案 ✓：**能 ✓ 而且几乎不用写新代码** ✗ —— 本项目**早就有**一个 OpenAI 兼容的 LLM 客户端 ✓
> （`agent/brain.py` 里的 `LLM` 类 ✓ 纯标准库 ✓ 只 `base + "/chat/completions"` ✓ 还支持 tool calls ✓）
> 只是**从来没配过 key** ✗（`doctor` 一直报"未配置 → 只能用 plan/script 模式"✗）。
> 新增的 `tools/talk.py` 就是那条**对话**通道 ✓（听聊天 ✓ 想内容 ✓ 说话 ✓）。

---

## 1. 接入事实（官方文档 ✓ 不是二手来源 ✓）

来源 ✓：<https://api-docs.deepseek.com/> ＋ <https://api-docs.deepseek.com/quick_start/pricing> ✓

| 项 | 值 |
|---|---|
| base_url（OpenAI 格式 ✓） | **`https://api.deepseek.com`** ✓ |
| 模型名 | **`deepseek-flash`** ✓（旧名 `deepseek-v4-flash` / `deepseek-v4-flash-vision-exp` 仍被接受 ✓ 会被路由到 V4.1-Flash 并按 Flash 价计费 ✓）｜另有 `deepseek-v4-pro` ✓ |
| 兼容性 | **OpenAI 兼容 ✓ 支持 tool calls ✓ JSON 输出 ✓ Responses API ✓ Anthropic 格式也行 ✓** |
| 上下文 | **1M** ✓（我们的 system 提示固定 ⇒ 能吃到 **context caching** ✓） |
| 价格（每 1M token ✓ off-peak ＝ 表价一半 ✓） | 输入(缓存命中) **$0.003~0.006** ✓ ｜输入(未命中) **$0.15~0.3** ✓ ｜输出 **$0.6~1.2** ✓ |

**折算成这个项目的实际成本** ✓：一次闲聊 ≈ system 提示（≈400 token ✓ 命中缓存 ⇒ 近乎免费 ✓）
＋ 最近几条聊天（≈100 token ✓）＋ 回话（≈40 token ✓）
⇒ **一条回话约 0.00002 美元量级** ✓ ⇒ 聊一整天也就几分钱 ✓

### 1.1 ★本机实测的两个前提★（2026-09-19 深夜 ✓ 都是实测 ✓）

1. ★**DeepSeek 通**★ ✓：不带有效 key 直接 POST ⇒ **HTTP 401**（0.2 秒 ✓
   `"Authentication Fails, Your api key: test is invalid"` ✓）⇒ **网络到得了 ✓ 只差 key** ✓
2. ★**OpenAI 不通**★ ✗：`https://api.openai.com/v1` ⇒ `WinError 10061 目标计算机积极拒绝` ✗
   ⇒ ⇒ **DeepSeek 不只是"可以"✗ 而是这台机器上唯一可行的那个** ✓✓

## 2. 它怎么工作（一圈一条 ✓ 全在 `tools/talk.py` ✓）

```
① 听 ✓ 读模组事件流里的 `chat` 事件 ✓（非 ASCII 是 U+XXXX 转义 ✓ 这里解回来 ✓）
② 判 ✓ 这条要不要**我**回 ✗ —— 模组那条"被叫名字就回一句短的"是**快嘴 ack** ✓
       ⇒ 默认策略 ✓「**ack 管被叫名字 ✓ 我管其余的**」✗
         （这样同一句话不会被回两遍 ✗；想让模型全接管 ⇒ `--always` ✓）
③ 拼 ✓ 人格 ＋ **实时状态**（`dshdigest` ✓ 位置/饱食/手持 ✓，30 秒最多读一次 ✓）
       ＋ 最近 8 条聊天 ✓ ⇒ 让它答得**像这个世界的它** ✗ 而不是像客服 ✓
④ 问 ✓ DeepSeek ✓（system 提示固定 ⇒ 吃缓存 ✓ 便宜 ✓；`temperature 0.8` ✓）
⑤ 说 ✓ `/dshsay <文本>` ✓ —— ★出口只有这一个★ ✗
```

## 3. 三条安全线（都焊在代码里 ✓）

1. ★**模型不能发游戏指令**★ ✗ —— 出口只有 `dshsay` 一个 ✓ 只送文本 ✓
   这与 `brain.py` 的既有设计一致 ✓（那里也是"模型只挑技能 ✓ 不能直接发指令"✓）⇒ **注入在结构上被排除** ✓
2. ★**回话要清洗**★ ✗：去换行 ✓ 去 `§` 颜色码 ✓ 去控制字符 ✓ 截断到 60 字 ✓ 空话不回 ✓
3. ★**有节流**★ ✗：两条之间 ≥4 秒 ✓ 每 5 分钟最多 12 条 ✓ ⇒ 绝不刷屏 ✓

## 4. ★出口也要转义★（本轮实测踩出来的新事实 ✗ 详见错题本 **P38** ✓）

- 实测 ✓：智能体把中文直接发给 `dshsay` ⇒ 游戏聊天里是
  `<Bot> ä½ å¥½ï¼æ¯Botï¼æ£å¨çç¿` ✗（字节 `\xc3\xa4…` ＝ **UTF-8 被当成单字节又编码了一次** ✗）
  ⇒ 坏在 **网关→CC 计算机→`commands.exec`** 那一趟 ✗
- ⚠ 而**模组自己**发的中文是**好的** ✓：实测日志里 `<Bot> 来了？` ✓ `<Bot> 该收的应该快熟了。` ✓
  ⇒ **坏的只是"从外面送进来"那一趟** ✗
- ⇒ 修法 ✓（v2.8.2 ✓）：与事件流**完全对称** ✓ —— 外面只发**纯 ASCII** 的 `U+XXXX` ✓
  **模组那边 `unesc()` 解回来** ✓ ⇒ 两趟都不碰非 ASCII ✓✓

## 5. 现成参考（用户问的"应该有的"✓）

| 参考 | 它给了什么 |
|---|---|
| ★[mindcraft-ce](https://github.com/mindcraft-ce/mindcraft-ce)★ ✓ | **最贴近的一个** ✓：LLM 驱动的 Minecraft 智能体 ✓ **会跟玩家聊天** ✓ 有技能库 ✓ 玩家能用聊天下指令 ✓ —— 本项目 `docs/智能体层-说明.md` **第 3 行起就参考了它** ✓（"技能库 ＋ 模型每回合挑一个技能"✓） |
| [soy-tuber/minecraft-ai-wrapper](https://github.com/soy-tuber/minecraft-ai-wrapper) ✓ | 本地 LLM 版（Nemotron ＋ vLLM ✓）—— "不想花钱/不想出网"时的路子 ✓ |
| [slatgoth/aibot_minecraft](https://github.com/slatgoth/aibot_minecraft) ✓ | Mineflayer ＋ Ollama ✓ 带**记忆**与技能 ✓ |
| [Voyager](https://github.com/MineDojo/Voyager) ✓ | 经典：LLM 写代码当技能 ✓ 长期记忆 ✓（我们没走"写代码"那条 ✗ 因为身体是服务端假人 ✓） |
| [DeepSeek 官方 Tool Calls](https://api-docs.deepseek.com/guides/tool_calls) ✓ | 我们的 `brain.py` 要走 tool calling 时的直接依据 ✓ |

**我们与它们的差别** ✓（不是"更好"✗ 是**形态不同** ✓）：
它们多数把 LLM 塞进**客户端**（Mineflayer 直连服务器 ✓ 能拿到完整客户端视野 ✓）；
我们的身体是**服务端权威的 Carpet 假人** ✓
⇒ 好处 ✓：世界视角与真玩家一致 ✓（可被 `/data` 读 ✓ 可被别的模组正常对待 ✓）
⇒ 代价 ✓：**没有客户端** ⇒ 一切"按键/界面/瞄准"的事都得靠模组搬回服务端 ✓（这就是 `dshbridge` 存在的理由 ✓）

## 6. 怎么用（三步 ✓）

```powershell
# ① 配 key ★已经配好了 ✓★ —— 就写在 secrets/deepseek.key 里（一行 ✓ 无 BOM ✓ 纯 LF ✓）
#    ★不用再设环境变量★ ✓ —— `talk.py` 读到这个文件时会**自动**补上
#      AGENT_API_BASE=https://api.deepseek.com ✓ AGENT_MODEL=deepseek-flash ✓
#    （为什么这么设计 ✗：**环境变量只对当前那个终端有效** ✗ —— 换个窗口就得重设 ✓ 很容易忘 ✓
#      忘了的表现是"它去连 api.openai.com"✗ 然后连不上 ✗ ⇒ 干脆从文件推 ✓）

# ② 先验证（一次极小调用 ✓ 不碰游戏 ✓）—— ★实测已通过 ✓★
py tools/talk.py --check
#   → [OK] 通了 ✓ 0.7s ｜ 回：在的 ｜ usage={'prompt': 38, 'completion': 80, 'total': 118}

# ③ 看它**用真人格**怎么答（不用游戏 ✓ 不用别人说话 ✓）—— ★实测已通过 ✓★
py tools/talk.py --demo
py tools/talk.py --demo "你叫什么？"

# ④ 真跑（盯着聊天 ✓ 有人说话它就回 ✓）
py tools/talk.py --watch          # Ctrl+C 退出 ✓ 退出时打印累计 token ✓
py tools/talk.py --watch --always # 连"被叫名字"也交给模型 ✓（模组的快嘴 ack 让位 ✓）
py tools/talk.py --once           # 只处理一轮 ✓
```

### 6.1 ★实测：真对话长什么样（2026-09-19 深夜 ✓ 模型现想的 ✓ 不是写死的 ✓）★

| 玩家 | Bot（`deepseek-flash` ✓） |
|---|---|
| 你在干嘛？ | **在岛上砸石头筛矿呢，你呢？** ✓（与 `dshdigest` 里"手里拿着木锤"**一致** ✓）|
| 你会筛矿吗？ | **会啊，沙砾放筛子里就能筛出矿物碎块。** ✓（与人格里的真实知识一致 ✓）|
| 这岛上还有吃的吗？ | **我身上就一把锤子，没吃的，岛上有啥我也还没摸清。** ✓★（**诚实说"没有"** ✓ 没有编 ✗）|

延迟 ✓ **1.0~1.2 秒/条** ✓ ｜ 3 条共 **1343 token** ✓（≈450/条 ✓ 大头是**被缓存**的 system 提示 ✓）
⇒ 一条回话 ≈ **0.00007 美元** ✓（缓存命中时更低 ✓）—— 这就是"**不是几句简单的话**"的代价 ✓

**账目去哪看** ✓：`logs/talk.jsonl` ✓（每条回话都记：听到了什么 ✓ 回了什么 ✓ 用了多久 ✓ 累计 token ✓ 模型名 ✓）
⇒ 花的钱**可对账** ✓（不是"感觉不贵" ✗）

## 6.5 ⚠ 关于这个 key（据实说明 ✓）

- 它现在**明文放在** `secrets/deepseek.key` ✓（就在本仓库里 ✓ **不在任何版本控制里** ✓ 本项目没有 git ✗）
- ⚠ 它**也在本会话的聊天记录里出现过一次** ✗ ⇒ **如果**这份工作区或聊天记录将来要给别人/上传 ✗
  ⇒ **先去 platform.deepseek.com 把它吊销重开一个** ✓（改动很小：把新 key 覆盖写进那个文件 ✓ 立刻生效 ✓）
- `AGENT_MODEL` 想换成 `deepseek-v4-pro` ✓ 就在同一个文件旁边设环境变量覆盖即可 ✓（或改 `talk.py` 的默认值 ✓）

## 7. 边界（据实登记 ✗）

- **假人发的不是签名聊天** ✗（1.20.1 起聊天要客户端签名 ✓ 假人没有客户端 ✓）—— 形状一样 ✓ 但**不是**签名聊天 ✓
- 智能体不在跑 `talk.py` 时 ✓，只有模组那几句**快嘴短句** ✓（打招呼 ✓ 被叫名字回一句 ✓ 偶尔自语 ✓）
  ⇒ 要"真对话"就得让 `talk.py` 挂着 ✓（或者以后把它做成常驻服务 ✗ —— 待办 ✓）
- `talk.py` 现在**只管聊天** ✗：不回话进"行动"（模型说"我去砍树"也不会真去砍 ✗）
  —— 那是 `brain.py` 的活儿 ✓ 两者**刻意分开** ✓（对话 ≠ 行动 ✓ 混在一起最容易出事 ✗）
