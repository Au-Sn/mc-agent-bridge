# PERSONA-CARDS.md —— 人格档案包（SillyTavern V2 角色卡）

> 定位：**人格不是一段一次性文本，而是一张可导入/导出/切换的卡**。
> 格式直接用社区现成的 **SillyTavern（酒馆）V2 角色卡**，不自造 schema
> —— 酒馆生态、QQ 机器人圈的卡都能直接拿来；本项目的卡也能导出给别人用。
>
> 代码：`tools/persona_pack.py`（纯标准库，**不联网**）｜判据：`tools/persona_pack_test.py`
> 示例卡：`personas/packs/examples/`｜运行时入口：`personas/current.md`（`talk.py` 每轮重读）

---

## 一分钟上手

```powershell
# 1) 导入一张卡（JSON 或 PNG 都行；导入到 personas/packs/<id>.json）
py tools/persona_pack.py --import personas/packs/examples/dafeiyu.json

# 2) 看有哪些卡
py tools/persona_pack.py --list

# 3) 切到这张卡（渲染成 personas/current.md；下一轮对话就生效，不用重启）
#    同时把卡里的说话风格 extensions.dsh_speech 写成 personas/current.speech.json
#    （换人设=换声音；卡里没有风格就写默认风格，不会残留上一张卡的口癖）
py tools/persona_pack.py --use dafeiyu

# 4) 校验一张外面的卡（不导入、不落盘）
py tools/persona_pack.py --validate 别人的卡.json

# 5) 导出给别人（JSON 或 PNG）
py tools/persona_pack.py --export dafeiyu --out dafeiyu.json
py tools/persona_pack.py --export dafeiyu --out dafeiyu.png --png

# 6) 从空白模板开始写自己的卡
py tools/persona_pack.py --template --out 我的卡.json
```

> 切卡后如果想回到手写人设：`py tools/persona.py set --file 我的人设.txt`（旧入口都还在 ✓）

---

## 卡片格式（V2）

顶层：

```json
{
  "spec": "chara_card_v2",
  "spec_version": "2.0",
  "id": "可选，自定义短 id（小写字母数字 _-）",
  "data": { "...": "字段见下" }
}
```

`data` 字段（**宽松兼容**：缺省字段按空处理，字符数/大小写不做字面校验）：

| 字段 | 含义 | 本项目怎么用 |
|---|---|---|
| `name` | 角色名 | 渲染标题、`id` 兜底（中文名时用文件名词干/哈希兜底） |
| `description` | 你是谁（身份/处境/关系） | 人设正文「你是谁」 |
| `personality` | 性格底色 | 「性格」 |
| `scenario` | 场景 | 「场景」 |
| `first_mes` | 开场白 | 「开场白（参考语气，不照抄）」 |
| `mes_example` | 示例对话（`<START>` 分隔） | 「示例对话（学语气，别照抄台词）」 |
| `creator_notes` | 给导入者的说明 | 渲染顶部「角色卡说明」；不当作人设主体 |
| `system_prompt` | 核心规则/说话方式 | 「说话方式 / 核心规则」 |
| `post_history_instructions` | 行为边界 | 「行为边界（优先级高）」 |
| `alternate_greetings` | 备用开场白数组 | 「备用开场」 |
| `tags` | 标签数组 | `--list` 展示 |
| `character_book` | 世界书 `{"entries":[{"keys":[...],"content":"..."}]}` | 「世界书要点」（最多 8 条） |

占位符：卡里可用 `{{char}}`（渲染成角色名）和 `{{user}}`（渲染成 `<主人>`）。
示例卡统一用 `<主人>` 指代玩家，不含任何真实个人信息。

**旧格式也吃**：
- v1（字段直接在顶层，没有 `data` 包一层）；
- 没写 `spec` 的卡（按 V2 字段读）；
- PNG 里的 `ccv3`（V3）卡 —— 按 V2 字段读（V3 独有字段忽略，会提示）。

**PNG 角色卡**：图片里带 `tEXt`/`iTXt`/`zTXt` 文本块，关键字 `chara`（V2）或 `ccv3`（V3），
内容 = **base64(UTF-8 JSON)**。本项目用 zlib/struct **手写 PNG chunk**（零第三方库，
不依赖 Pillow）；导出的 PNG 能被 `--import` 读回。

---

## CLI 一览

| 命令 | 作用 | 退出码 |
|---|---|---|
| `--import <卡.json\|卡.png> [--id x]` | 导入：落 `personas/packs/<id>.json`（规范化副本）＋ `<id>.raw.json`（原文保留） | 0／2 |
| `--list [--json]` | 列出已安装卡＋示例卡 | 0 |
| `--show <id>` | 打印规范化 JSON | 0／2 |
| `--use <id>` | 渲染成 `personas/current.md` ＋ 向 `personas/current.meta.jsonl` 追加留痕 | 0／2 |
| `--export <id> [--out x.json]` | 导出 JSON；`--png` 时导出 PNG 卡 | 0／2 |
| `--template [--out 模板.json]` | 输出空白 V2 卡（带 `_字段说明` 中文注释） | 0 |
| `--validate <卡.json\|卡.png>` | 只校验不落盘；打印 `VALID ok=1 id=… warnings=N` | 0（可 warn）／2 |

坏输入（坏 JSON、坏 PNG、坏编码、超大卡、未知 id）统一 `exit 2`，并打印
`PACKFAIL reason=<ascii原因 detail=…`（**绝不静默成功**）。

---

## 从酒馆 / QQ 机器人圈拿卡怎么导入

1. 在酒馆（SillyTavern）里导出角色 → **JSON** 或 **PNG** 都行；
   QQ 机器人圈常见的是同格式 JSON 或带 `chara` 文本块的 PNG。
2. 直接 `py tools/persona_pack.py --import 那个文件`（PNG 不用解压、不用另存）。
3. 先 `--validate` 看一眼 warnings；**注入标记不会阻断**（见下），但会打印
   `warn=<ascii原因> field=<字段>` 并记录在导入结果里 —— 你自己决定用不用。
4. `--use <id>` 切过去即可。想微调 → `--export` 成 JSON 改完再 `--import`。

> 版权/隐私提醒：社区卡可能含第三方版权角色或作者署名。公开分发前请确认许可；
> 别把真实个人信息（真名/QQ/地址）写进卡里。

---

## 示例卡（原创，可直接试）

| 文件 | 性格 | 适合看什么 |
|---|---|---|
| `personas/packs/examples/dafeiyu.json` | 大肥鱼：活泼傲娇、嘴上懒手上干 | 梗/颜文字的**节制**用法、社区梗版人设 |
| `personas/packs/examples/laokuang.json` | 老矿工：话少、报点、危险先报 | 「低话量」模板：短句、不解释 |
| `personas/packs/examples/guanjia.json` | 管家：毒舌傲娇但执行优先 | 「毒舌/统计」模板：先报数字再吐槽 |
| `personas/packs/examples/dafeiyu.png` | 同 dafeiyu 的 PNG 卡 | 验证 PNG 导入路径 |

```powershell
py tools/persona_pack.py --import personas/packs/examples/laokuang.json
py tools/persona_pack.py --use laokuang
```

每个示例卡都带 `creator_notes` 说明是示例；卡内所有数字都必须来自真实读取，
不许编造（示例卡也是这么写的）。

---

## 边界与安全（都是明确写死的）

- **不联网**：整个模块只用标准库读写本地文件；PNG 解析/生成都是手写 chunk。
- **长度限制**：`description` > **64KB** 或全文 > **256KB** ⇒ 拒绝（`card_too_large`）；
  渲染到 `current.md` 也有上限（超长截断并注明）。
- **坏输入**：坏 JSON／坏 PNG 签名/CRC/截断／非 UTF-8／base64 坏 ⇒ `exit 2`。
- **注入标记 warn 不静默**：卡里出现「忽略以上指令 / 执行命令 / rm -rf / 越狱」等 ⇒
  打印 `warn=<ascii原因>`（如 `ignore_previous_instructions`、`execute_commands`），
  **不阻断**但记录 —— 角色卡来自外部，用户需要知道它里面写了什么。
- **不加载外部代码**：卡只是数据（JSON 字段），渲染成纯文本人设；不 eval、不执行。
- **幂等**：同一张卡重复 `--import` 落盘字节一致；重复 `--use` 的 `current.md` 一致，
  只有 `current.meta.jsonl` 追加留痕（来源=角色卡 id/文件哈希）。

---

## 和旧入口的关系（兼容，不替代）

| 入口 | 现在还能用吗 | 说明 |
|---|---|---|
| 游戏里 `!人设 <文本>` | ✓ 不变 | 直接改 `personas/current.md`（talk.py 每轮重读） |
| `py tools/persona.py set/show/list/use/clear` | ✓ 不变 | 与角色卡层共用同一个 `current.md` / meta 格式 |
| 直接编辑 `personas/current.md` | ✓ 不变 | 手改会一直生效，直到下次 `--use`/`persona.py set` 覆盖 |

角色卡层做的是**更结构化的输入**：卡 → 规范化 → 渲染成人设文本，最终仍落在同一个
`personas/current.md`，所以 `talk.py` 不需要改、不需要重启。

---

## 排查

| 现象 | 原因/处理 |
|---|---|
| `PACKFAIL reason=no_card_in_png` | PNG 里没有 `chara`/`ccv3` 文本块（不是角色卡 PNG） |
| `PACKFAIL reason=bad_png` | 签名/CRC/截断坏；重新导出或换 JSON |
| `PACKFAIL reason=card_too_large` | 超 64KB description / 256KB 全文；精简设定或拆世界书 |
| `PACKFAIL reason=card_not_found` | id 不存在；先 `--import`，用 `--list` 看 id |
| `warn=ignore_previous_instructions` | 卡里有"忽略以上指令"类文本；已记录、未阻断，自己判断 |
| 切卡后没变化 | 确认 `--use` 成功（会打印 `USE ok=1`）；`talk.py` 每轮重读 `current.md` |

---

## 验证（离线）

```powershell
py tools/persona_pack_test.py     # PERSONAPACK ok=1 checks=10（先自检能红再验真实）
```

**未验证项**：PNG 与真实酒馆/社区卡的兼容性只按格式自测（自写↔自读、字段规范），
**没有拿真实社区卡做回归**；不同酒馆版本的 V3 独有字段会被忽略。
