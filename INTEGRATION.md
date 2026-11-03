# INTEGRATION — 把任意 AI / Agent 接到这副 Minecraft 身体上

> **本仓库的定位是一个组件：AI 的 Minecraft「可信身体层」。**
> 我们负责：**身体 / 动作 / 感知 / 安全 / 验证 / 恢复 / 接口**；
> 不负责：**人格内容 / 任务策略 / 模型能力** —— 那些留在你的脑侧（人格可用 SillyTavern V2 角色卡，
> 见 [PERSONA-CARDS.md](PERSONA-CARDS.md)；换整合包见 [PACK-PORTING.md](PACK-PORTING.md)）。
>
> 本文写给**其他 AI/Agent 项目的作者**：怎么把我们的身体接进你的循环，以及你会拿到/不会拿到什么。
> 安装游戏侧与环境配置见 `INSTALL.md`；MCP 工具逐件说明见 `docs/接口契约-伙伴v1.0.md`。

---

## 0. 先明确边界（接之前先对齐）

| 层 | 谁负责 | 内容 |
|---|---|---|
| **身体层（本仓库）** | 我们 | 服务端 Carpet 假人；动作原语（走/挖/放/用/容器/合成）；感知（方块/背包 NBT/事件流）；安全护栏（禁区/批量守卫/token/Origin/raw 白名单）；世界真值回读；判据体系；重启后一条命令恢复；HTTP/MCP/Python 三种接口 |
| **脑侧（你的项目）** | 你 | 模型与推理；任务策略/规划；对话与人格内容；记忆的语义（我们只提供事件与地标存储接口）；成本与安全策略 |
| **人格/角色** | 可插拔 | 用 **SillyTavern V2 角色卡**（JSON）描述；本仓库只提供 persona 目录与渲染接口，**不自造格式**（见 [PERSONA-CARDS.md](PERSONA-CARDS.md)） |
| **世界知识** | 可插拔 | 方块分类/配方等是**按整合包生成**的知识资产；换包按 [PACK-PORTING.md](PACK-PORTING.md) 重新生成 |

> 一句话：**我们给你一副"能被验证的身体"，不给你"人设与脑子"。**

---

## 1. 三种接入方式（按耦合度从低到高）

| 方式 | 适合 | 传输 | 依赖 |
|---|---|---|---|
| **A. HTTP 直连**（推荐起步） | 任何语言/进程/远端脑 | `POST http://127.0.0.1:8766/cmd`（文本指令）＋ `/raw` ＋ `GET /health` | 只要 HTTP 客户端 |
| **B. MCP 工具面** | 已经是 MCP 客户端（Claude/Harness/自研） | stdio 一行一条 JSON（MCP `2024-11-05`） | `py tools/mc_mcp.py` 作为 MCP server |
| **C. Python 层直接 import** | Python 项目、想拿到聚合工具 | 进程内函数调用（`tools/mcp_*.py`、`tools/direct.py`） | 仓库目录可 import；纯标准库 |

**端口**：直连 HTTP 默认 **8766**（`dsh.env` 的 `DSH_PORT` / 模组 `-Ddshbridge.port=` 可改）。
**旧网关 :8765＋CC 计算机只是内部后备链路**，新接入方不要走它。

### A. HTTP 直连：端点

| 端点 | 方法 | 说明 | 认证 |
|---|---|---|---|
| `/health` | GET | 探活，返回 `ok dshbridge-http` | 不需要 token |
| `/cmd` | POST | body 是**一条服务器指令文本**（UTF-8），返回文本回执 | `X-DSH-Token` 必填 |
| `/raw` | POST | 以**服务器身份**执行（只放行白名单，主要用于拉起假人） | `X-DSH-Token` 必填 |
| 响应头 | — | `X-DSH-Req: <id>` 回显本次请求号（可配合 `/dshreqs` 对账） | — |

- **token 从哪来**：模组启动时在实例的 `config/dshbridge/http_token.txt` 生成/读取（`<你的实例路径>/config/dshbridge/http_token.txt`）；
  也可用环境变量 `DSH_HTTP_TOKEN` 直接给，或用 `HTTP_TOKEN_FILE` 指定文件。
- **世界指令要玩家上下文**：指令写成 `execute as <假人名> at <假人名> run <dsh 指令>`（例如
  `execute as Bot at Bot run dshdigest`）。`/raw` 例外，它本来就是服务器身份。
- **世界写操作是单车道**：`/cmd` 与 `/raw` 在模组内由**单线程 world lane** 串行执行（保序、绝不并行写世界）；
  `/health` 不经过车道，所以慢动作不会堵探活。读类请求可以并发。

### B. MCP 工具面（55 件）

- 传输：**stdio，一行一条 JSON**（不是 `Content-Length` 分帧）。
- 失败信号：**唯一机器可读的是 `isError`**（正文是给人读的中文＋记号，别拿正文当判据）。
- 启动：把 `py tools/mc_mcp.py` 配成 MCP server（工作目录 = 仓库根；Python 3.10+，无三方依赖）。
- 工具清单与参数：`docs/接口契约-伙伴v1.0.md`（由 `tools/gen_contract.py` 从代码生成，`contract_test.py` 双向对账）。

最小 MCP 客户端配置（以支持 `mcpServers` 的客户端为例）：

```json
{
  "mcpServers": {
    "mc-bridge": {
      "command": "py",
      "args": ["tools/mc_mcp.py"],
      "cwd": "<本仓库路径>"
    }
  }
}
```

### C. Python 层直接 import

```python
import sys
sys.path.insert(0, "tools")       # 仓库根目录下运行
import direct                     # 直连 HTTP（token 自动找）
import mcp_core                   # 聚合能力（dsh() 内部直连优先 → 后备通道）
import mcp_walk                   # 走/导航类聚合
```

Python 层是**纯标准库**，可直接在你自己的进程里用；它负责把"多次桥往返"聚合成"一次调用"。

---

## 2. 最小可跑示例

> 前提：游戏已开、世界已进、模组已装、`py tools\doctor.py` 硬问题 0（见 `INSTALL.md`）。
> 坐标/假人名/端口都从 `dsh.env` 或占位符取，勿写死本机路径。

### 2.1 探活（不需要 token）

```bash
curl -s http://127.0.0.1:8766/health      # ⇒ ok dshbridge-http
```

```powershell
Invoke-RestMethod http://127.0.0.1:8766/health
```

```python
import sys; sys.path.insert(0, "tools")
import direct
print(direct.health())        # ⇒ 'ok dshbridge-http'（连不上回 None）
```

```javascript
const r = await fetch("http://127.0.0.1:8766/health");
console.log(await r.text());  // ok dshbridge-http
```

### 2.2 取 token 并执行一条世界指令

```bash
TOKEN=$(cat "<你的实例路径>/config/dshbridge/http_token.txt")
curl -s -X POST "http://127.0.0.1:8766/cmd" \
  -H "X-DSH-Token: $TOKEN" \
  --data-binary "execute as Bot at Bot run dshdigest"
```

```python
import sys; sys.path.insert(0, "tools")
import direct
print(direct.post("execute as Bot at Bot run dshdigest"))   # token 由 direct 自动读取
```

```javascript
import fs from "node:fs";
const token = fs.readFileSync("<你的实例路径>/config/dshbridge/http_token.txt", "utf8").trim();
const r = await fetch("http://127.0.0.1:8766/cmd", {
  method: "POST",
  headers: { "X-DSH-Token": token },
  body: "execute as Bot at Bot run dshdigest",
});
console.log(await r.text());
```

### 2.3 读增量事件 / 态势

```text
execute as Bot at Bot run dshevents     # 增量事件流（事件环有上限，夜里跑长测要轮询 drain）
execute as Bot at Bot run dshdigest     # 一条指令拿态势：pos/mode/hp/onground…
execute as Bot at Bot run dshver        # 模组版本 + 能力面
```

```python
import sys; sys.path.insert(0, "tools")
import direct
print(direct.post("execute as Bot at Bot run dshevents"))
print(direct.post("execute as Bot at Bot run dshdigest 1"))
```

### 2.4 一个动作 + 世界真值回读（写操作必须回读）

```python
import sys; sys.path.insert(0, "tools")
import direct
# 示例：让假人向前走一格（真实指令集以模组 /dsh* 指令面为准；MCP 工具层有更高层封装）
print(direct.post("execute as Bot at Bot run dshwalk to <x> <y> <z> 4000"))
# 回读确认：位置真的变了吗？没变就别当成功
print(direct.post("execute as Bot at Bot run dshdigest"))
```

> 原则：**执行者的自述不算数，回读世界真值才算数**。写操作（挖/放/容器/合成）不是幂等的，
> 失败重试前先回读，确认上一次到底做成了没有。

### 2.5 拉起假人（世界重启后）

```python
import sys; sys.path.insert(0, "tools")
import direct
print(direct.raw("player Bot spawn at <x> <y> <z>"))   # /raw = 服务器身份（白名单内）
```

更省事的方式是直接跑仓库自带的一条命令：`py tools\recover.py`（幂等：探活→不在就 spawn→切生存→回读确认）。

---

## 3. 能力清单（55 件 MCP 工具的分类视图）

| 类别 | 件数 | 代表工具 | 你能拿到什么 |
|---|---:|---|---|
| 感知 / 态势 | 10 | `bot_state` `bot_inventory` `bot_events` `whereami` `look` `scan` `survey` `map_area` `find_block` `safe_spots` | 方块/背包 **NBT 真值**、地形扫描、事件流 |
| 移动 / 导航 | 13 | `walk_to` `nav3d` `goto_route` `walk_route` `check_path` `plan_route` `route_view` `walk_progress` `platform` | 带防坠闸的寻路与进度 |
| 方块 / 物品动作 | 8 | `dig_block` `place_block` `use_block` `equip` `harvest_crop` `sift` `drop_item` `go_to_drop` | 受许可与批量守卫约束的写动作 |
| 容器 / 背包 | 6 | `chest_peek` `chest_put` `chest_take` `chest_put_many` `chest_take_many` `move_slot` | 开容器、逐件对账、不静默丢物 |
| 行为 / 拟人 | 8 | `gesture` `idle_beat` `follow_gaze` `point_at` `lead_to` `idle` `stop` `freeze` | 手势/视线/待机/冻结；**没有"人格内容"** |
| 任务 / 账本 | 8 | `job_open` `job_plan` `job_next` `job_list` `job_step` `job_close` `action_status` `cancel` | 多步作业账本（证据指针、可中断） |
| 记忆 | 1 | `remember` | 地标/事实持久化（语义由你解释） |
| 发言 | 1 | `say` | 唯一说话口子（防注入的转义约定） |
| **合计** | **55** | 逐件参数见 `docs/接口契约-伙伴v1.0.md` | |

> **人设不在 55 件里**：它是可插拔的"内容/渲染"，用 SillyTavern V2 角色卡描述；本仓库负责把
> 角色卡渲染进 prompt/说话风格，不提供人格库（见 [PERSONA-CARDS.md](PERSONA-CARDS.md)）。

---

## 4. 安全边界（默认按"不可信输入"设计）

1. **只听本机**：模组 HTTP 只监听 `127.0.0.1`。**不要**把它反向代理到公网；要远程接就把脑放在同一台机器/隧道里。
2. **写通道要 token**：`/cmd` 与 `/raw` 必须带 `X-DSH-Token`（`/health` 除外）。
3. **浏览器不可用**：任何带 `Origin` 头的请求一律拒绝（防 CSRF）——浏览器 JS 驱动不了身体，这是**设计**。
4. **`/raw` 白名单**：只放行少量服务器身份命令（如拉起假人）；白名单外一律拒绝并给理由。
5. **单世界车道**：世界写操作串行保序；别用并发压写世界（读可以并发）。
6. **体积/时限**：请求体有上限；世界车道有超时。远程/慢客户端请自己设超时并处理 `ERR:timeout reason=lane`。

## 5. 错误语义与处理配方

| 情形 | HTTP | 响应体（前缀/原因） | 怎么处理 |
|---|---|---|---|
| 缺 token | 401 | `ERR:auth reason=missing_token` | 读 token 文件/环境变量后重试 |
| token 错 | 401 | `ERR:auth reason=bad_token` | 重新读取 token（游戏重启后可能轮换） |
| 带 `Origin` 头（浏览器） | 403 | `ERR:csrf reason=origin_header` | 从非浏览器客户端发请求 |
| `/raw` 白名单外 | 403 | `ERR:raw_denied reason=not_whitelisted` | 改用 `/cmd` 或允许的白名单命令 |
| 请求体过大 | 413 | `ERR:body_too_large reason=limit` | 拆小/改用文件式批量工具 |
| 世界车道超时 | 200 | `ERR:timeout reason=lane` | 短动作重试；长动作先回读状态再决定 |
| 指令业务失败 | 200 | `ERR:...`（如 `ERR:no_bot`） | 视为失败；按原因修复（如 `recover.py`） |
| 正常 | 200 | 人读文本；成功判据看回读的世界真值 | 写操作**必须**回读确认 |

**MCP 侧**：机器判失败只看 `isError`；正文只给人看。
**判据侧**：环境不满足时输出 `INCONCLUSIVE`（例如游戏没开、缺样本）——**INCONCLUSIVE 不是 PASS**，
你的 CI 不要把两者混为一谈。

## 6. 明确"不提供"的东西（避免误期待）

- ❌ **通用寻路/移动**：本项目寻路是"够用"级（拆跳＋每跳验真＋防坠），复杂地形/长途不如 Baritone。
- ❌ **跨 Minecraft 版本**：只支持 **Forge 1.20.1**（本项目在 47.2.20 开发）。其他版本/加载器未支持。
- ❌ **人格内容与对话剧本**：不自造人格格式；用 SillyTavern V2 角色卡（[PERSONA-CARDS.md](PERSONA-CARDS.md)）。
- ❌ **任务策略/规划质量**：由你的脑负责；我们只提供动作、真值回读与账本。
- ❌ **多假人/多世界集群/游戏客户端自动化**：当前是"一个身体、一个世界"。
- ❌ **绕过反作弊/服务端规则**：它就是一个服务端假人，不提供任何作弊能力。

## 7. 推荐集成架构（脑外置）

```
你的项目（脑）                          本仓库（身体层组件）
┌─────────────────────────┐          ┌─────────────────────────────────────┐
│ 人格卡（SillyTavern V2） │          │  HTTP :8766 /cmd /raw /health       │
│ 观察 → 决策 → 动作       │ ───────► │  MCP 55 工具（stdio，一行一 JSON）  │
│ 回读验收 → 记账 → 汇报   │ ◄─────── │  Python 层（mcp_*.py，可 import）   │
└─────────────────────────┘          │  ├ 动作原语 + 安全护栏              │
                                     │  ├ 世界真值回读（NBT）              │
                                     │  ├ 判据/验证/恢复（可离线跑）        │
                                     │  └ 人格渲染接口（不含内容）          │
                                     └─────────────────────────────────────┘
```

建议循环：**先看（whereami/look/survey）→ 再动（工具/指令）→ 再回读（digest/事件）→ 失败按原因修
（先查 `py tools\doctor.py`，假人不在跑 `py tools\recover.py`）→ 记账（jobs/事件）**。

## 8. 接入 checklist

1. [ ] 游戏/世界在跑，模组 2.5x 已加载（`py tools\direct.py --health` ⇒ `ok dshbridge-http`）。
2. [ ] 你能读到 token（实例 `config/dshbridge/http_token.txt` 或环境变量）。
3. [ ] `GET /health` 通；`POST /cmd "execute as <Bot> at <Bot> run dshver"` 回版本。
4. [ ] 能拿到态势：`dshdigest`；能读事件：`dshevents`。
5. [ ] 一条写动作 + 世界真值回读闭环跑通（不看自述，看回读）。
6. [ ] 处理了 401/403/`ERR:`/`timeout` 四类错误；写操作非幂等有回读/重试策略。
7. [ ] 人格卡/策略在你侧，不在身体层；换模型不需要改身体。
8. [ ] 不把 `8766` 暴露到公网；token 不进日志/仓库。

## 9. 相关文档

- `README.md` —— 组件定位与全貌
- `INSTALL.md` —— 从零跑起来（含每步实测状态）
- `docs/接口契约-伙伴v1.0.md` —— **55 件工具逐件表**、失败语义、三条硬边界、D1~D7 验收判据
- `docs/项目总览.md` —— 当前能力/判据/世界资产/实测数据
- [PERSONA-CARDS.md](PERSONA-CARDS.md) —— 人格卡（SillyTavern V2）模板（可插拔）
- [SPEECH-DEMO.md](SPEECH-DEMO.md) —— 语言层观感剧本（台词/口癖/换卡前后对照）
- [DEMO.md](DEMO.md) —— 演示剧本与录制手册（三场景/目标台词/rubric）
- [PACK-PORTING.md](PACK-PORTING.md) —— 换整合包/世界档案迁移指南
- `docs/开源发布-清单.md` —— 发布/分发注意事项

> 说明：本文示例按当前协议（2.58.0：HTTP 加固/token/Origin/raw 白名单/world lane）编写；
> 本机没有第二个接入方，**外部项目端到端接入未实测**（见 `tmp/ledger/docs-542.md`）。
