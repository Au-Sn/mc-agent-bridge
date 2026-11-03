# SPEECH-DEMO.md —— 语言表现层（活人感）观感对照剧本

> ⚠ **本文是"目标示例"，不是模型实测记录** —— 左边的"现在"是我按旧行为写的样张，
> 右边的"加风格层"是**目标观感**（提示词风格段＋后处理＋调度共同作用）。
> 真实效果取决于你接的 LLM；判据（`tools/speech_alive_test.py`）只保证可机检的底线：
> **不 AI 腔 / 不超长 / 十轮不重复 / 失败不谎报 / 上下文有引用 / 口癖不刷屏 / 主动发言不硬凑**。

## 0. 这一层是什么（一句话）

人设卡是**输入**；真正被看到的是**它怎么说话**。语言表现层 = 三件事：

1. **风格提示**（`speech_style.render_style_guide()` 追加进任务书）：称呼、句长、口癖概率、失败规矩；
2. **回复后处理**（`speech_style.postprocess()`）：去 AI 腔、截长、低概率口癖/emoji、**十轮去重**；
3. **调度**：`failure_line()`（失败诚实）、`proactive_line()`（5 个主动发言场景）、出口节奏（按字数 0.3~1.2s）。

风格配置在 `personas/<id>.speech.json`，或角色卡 `data.extensions.dsh_speech`
（示例卡 `personas/packs/examples/{dafeiyu,laokuang,guanjia}.json` 都带了；
当前运行时示例：`personas/current.speech.json`）。换人设/换风格不用改代码。

---

## 场景一：玩家回岛（主动发言 · `player_online`）

**现在的说话方式（只有通用人格，没人起话头/没风格约束）**
1. 「你好，我是 Bot。请问有什么可以帮您的吗？」
2. （沉默 —— 如果不问它，它就不开口）
3. 「作为一个 AI，我无法确定你指的是什么。」

**加风格层之后（目标观感）**
1. 「<主人>，你来了。本鲸巡游回来了。」
2. 「来了啊。今天先挖矿还是先筛？先说好，小鱼干得管够。」
3. 「……半天没声了，<主人>？」

> 这一层做了什么：主动发言池按场景取句（不再沉默）；称呼固定 `<主人>`；`postprocess` 把"我是 Bot/请问有什么可以帮您"整句删掉；句长卡在 60 字内。

---

## 场景二：收田失败（失败诚实 · `failure_line` + 后处理）

**现在的说话方式（模型自由发挥，容易报喜）**
1. 「已完成小麦收割，共收获 32 株。」（实际 0 株 ⇒ **谎报**）
2. 「操作成功，祝您游戏愉快！」
3. 「作为 AI 我无法直接操作游戏，但你可以自己试试。」

**加风格层之后（目标观感）**
1. 「没成。水把田冲了，一株都没收到。」
2. 「卡住了。桶在箱子里，我拿不到。先记着，回头补。」
3. 「没弄好，啧。作物没了，我先把水排掉，重新种一次。」

> 这一层做了什么：`failure_line(reason)` 先认错 → 说事实（原因/物品）→ 给下一步；
> 模板里**不含"完成/成功/搞定"**；`postprocess` 再把模型可能带出来的"已完成/操作成功"整句删掉；
> 若模型输出纯 AI 腔 ⇒ 回退到失败话术，而不是让"假成功"进游戏。

---

## 场景三：天黑（主动发言 · `nightfall` / 情绪映射）

**现在的说话方式（通用人格，容易客套/说明书腔）**
1. 「天色已晚，建议你注意安全并准备休息。」
2. 「当前时间是夜晚，周边可能存在敌对生物。」
3. 「如果你需要帮助，请随时告诉我。」

**加风格层之后（目标观感）**
1. 「天黑了。收工。」
2. 「夜里了，别走远。本鲸在门口。」
3. 「这个点还不睡？账合上了，明天再说。」（管家）

> 这一层做了什么：场景话术池 + 情绪映射（`emotion_lines.night`）；句长预算压到 1~2 短句；
> 「建议/请注意/请随时告诉我」这类客服腔由 AI 腔规则处理；同一场景连续出现会由 `recent_said` 去重（不会每轮都"天黑了"）。

---

## 怎么亲手看一遍（离线，不碰游戏）

```powershell
# 1) 看某张卡的风格约束（或默认）
py tools/speech_style.py --guide personas/current.speech.json

# 2) 试试后处理（把 AI 腔喂进去 ⇒ 看到它被怎么处理）
py tools/speech_style.py --post "作为一个AI语言模型，我无法访问你的实时坐标。希望以上回答对你有帮助。"

# 3) 失败诚实话术
py tools/speech_style.py --failure "前面是岩浆" --ctx "target=铁矿"

# 4) 主动发言
py tools/speech_style.py --proactive nightfall --ctx "address=<主人>"

# 5) 判据（先自检能红，再验真实）
py tools/speech_alive_test.py     # SPEECHALIVE ok=1 checks=11
```

## 接线点（`tools/talk.py`，最小改动，未改对外行为）

| 位置 | 做什么 |
|---|---|
| `Talk.__init__` | `self.speech = SS.load_for_persona(PERSONA_DIR, persona_name)`（阅读风格 profile）＋ `recent_said`／`style_rng`／`sleep_fn` |
| `_style_task_persona()` | 任务书 = 人设 ＋ `SS.render_style_guide()`（风格约束进 prompt） |
| `answer_harness` / `answer_api` / `recover` / `answer_idle` | 拿到回复后走 `_style_reply()`（`postprocess`＋去重；失败且未动手 ⇒ `failure_line`） |
| `say()` | `SS.rhythm_delay()` 算 0.3~1.2s 节奏；**默认不睡**（`sleep_fn` 可注入，判据用） |
| `reload_persona_if_changed` / `set_persona` | 换人设时同步重载风格 profile |

## 边界（别误读）

- **不保证"像人"**：这一层只保证可机检的底线；具体文采仍取决于模型质量。
- **失败话术不是"免责"**：它只保证"做砸了就说没成"，不替模型补一句假成功。
- **不联网、不碰游戏**：`speech_style.py` 纯函数；判据全离线。
- 风格太强时（口癖概率/句长）可改 `personas/current.speech.json`；不想主动发言用 `--no-speech`。
