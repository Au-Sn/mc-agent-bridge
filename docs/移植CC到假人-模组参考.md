# 把 CC 的能力移植到假人身上 · 以及"女仆模组"一类同伴 AI 的参考

> 结论先写：**打包时不该把 ComputerCraft 一起带上** ✓ —— 它太臃肿 ✗：
> 一个完整模组 + 计算机方块 + 海龟 + 无线网络 + 我们那 150 KB 的 Lua 桥 ✓，
> 而其中**绝大部分能力是在绕开"假人没有 GUI"这件事** ✗。
> 正确方向是：**把这些能力直接做在假人（或一个同伴实体）身上** ✓ ——
> 近期用无头客户端补齐 GUI 类动作 ✓，目标形态是**一个模组** ✓。

本文分三部分：① CC 到底给了我们什么、怎么替换 ✓ ② 两条落地路线 ✓ ③ 同类模组的设计参考 ✓。

---

## 1. CC 给了我们什么，以及怎么替换

| 能力 | CC 里的做法 | 移植到假人身上怎么做 |
|---|---|---|
| 挖 / 放 / 右键 / 取放物品 | `turtle.dig/place/suck/drop` ✓ | **假人本来就会** ✓（`dig_at` / `place_at` / `use_once` / `sneak_place` ✓ 已在用 ✓） |
| 读周边方块 | `commands.getBlockInfo` ✓ | `/data get block` + **`blocks_around`** ✓（已做 ✓ 196 格一次读完 ✓） |
| **合成** | `turtle.craft`（必须先装备工作台 ✓） | ⚠ **无 GUI 做不到** ✗ —— 见下 ✓ |
| 容器 / 熔炉 / 附魔 / 交易 | 海龟只能 `suck`/`drop` ✓（容量有限 ✗） | ⚠ 同上 ✓（都要"打开界面"✗） |
| 反射 / 肌肉记忆 | 游戏内 Lua 每拍 ✓（实测够用 ✓） | **模组 tick 级** ✓（更快、更省、不受 HTTP 影响 ✓） |
| "一个作业 = 一条指令" | `run_job` ✓ | 模组侧 **task/intent 系统** ✓（= 女仆那一套 ✓ 见第 3 节 ✓） |
| 绝对坐标导航 | GPS 主机 + `locate` ✓ | 假人/模组侧直接用真实坐标 ✓（假人**本来就有绝对坐标** ✓ 不需要 GPS ✗） |
| 无线遥控 | rednet + modem ✓ | 同一条 HTTP/JSON 协议 ✓ 但端点在模组里 ✓（**去掉整个 CC 依赖** ✓） |

**关键洞察** ✓：我们绕的这一大圈，本质上是"**用一个方块世界的机器人去替一个没有客户端的玩家做 GUI 动作**" ✗。
既然如此，**不要绕** ✓：要么让"玩家"真的有一个能点界面的客户端 ✓，要么在服务端**绕过界面直接调用逻辑** ✓。

---

## 2. 两条落地路线

### 路线 A（近期可用 ✓ 零模组 ✓）：给这套系统补一个"无头客户端"

- **mineflayer**（Node.js 的无头 Minecraft 客户端 ✓）天生就能做 CC 做不到的事：
  合成（`bot.craft` ✓）、开箱子（`openContainer` ✓）、熔炉（`smeltItem` ✓）、
  交易（`tradeWithVillager` ✓）、附魔（`enchantItem` ✓）、点击窗口（`clickWindow` ✓）、
  以及**成熟的寻路**（A\* + 跳跃 + 搭桥 ✓）。
- 本会话的工具集里**已经挂着这样一套 MCP 工具** ✓（`craft_item` / `open_container` / `transfer_items` /
  `smelt_item` / `click_window` / `wiki` …… ✓）—— 连上它 ✓ 就等于**立刻**补上 GUI 类能力 ✓
  （前提：世界要"对局域网开放" ✓ 或跑在独立服务端上 ✓）。
- 分工建议 ✓：**假人 `Bot`** 继续做"世界里的手"（替身玩家、真背包、真挖掘 ✓ 自给链的主角 ✓）；
  **无头客户端**做"界面里的手"（合成/容器/交易 ✓）。两者都由 `agent/` 指挥 ✓。

### 路线 B（目标形态 ✓ 一个模组）：`dsh-companion`

一个 Forge 1.20.1 模组，四块积木：

1. **AgentBridge**：把现在这套 HTTP/JSON 协议**原样**搬进模组 ✓（网关→模组端点 ✓ 去掉 CC ✓）
2. **TaskSystem**：可插拔任务 + 优先级 + 抢占/恢复 ✓（直接照女仆的 `IMaidTask` 抄 ✓）
3. **Actor**：假人（服务端玩家 ✓ 真背包 ✓）或自己的同伴实体 ✓（后者能自定义模型/动画 ✓）
4. **Reflex**：tick 级反射（保命/进食/还击/卡住检测 ✓ 把现在 Lua 里那套原样移植 ✓）

打包体积对比 ✓：现在 ≈ 模组(CC) + 世界里的机器 + 150 KB Lua + Node 网关 ✗；
目标 ≈ **一个 jar** ✓。这就是"不臃肿"的答案 ✓。

---

## 3. 同类模组的设计参考（可直接抄的部分）

| 参考 | 里面有什么值得抄的 |
|---|---|
| [Touhou Little Maid — Task Architecture / `IMaidTask`](https://deepwiki.com/TartaricAcid/TouhouLittleMaid/9.1-broom-system-and-controls) | **任务即插件**：每个任务实现统一接口 ✓ 有优先级 ✓ 可被抢占 ✓ 每 tick 驱动 ✓ —— 我们现在的 `plan JSON` + `job_*.lua` 正是它的雏形 ✓ |
| [Touhou-Little-Maid-Companionship](https://github.com/Re-Summer75/Touhou-Little-Maid-Companionship)（1.20.1 ✓ 扩展模组 ✓ 带 `docs/architecture/intent-ai-data.md` ✓） | **"意图"驱动** ✓：不是"执行脚本"✗ 而是"我饿了/我想工作/我想跟随"✓ → 由**需求**选任务 ✓；再加成长/饱食状态 ✓ —— 正好把我们的 reflex 与 plans 缝成一个整体 ✓ |
| [minecraft-codex-companion](https://github.com/Hakurei-git/minecraft-codex-companion)（Forge 1.20.1 ✓ 本地优先 ✓ 支持 MCP ✓） | **AI 同伴 + 外部智能体**的完整先例 ✓：聊天、合成、建造、深层挖矿 ✓ —— 证明"LLM 指挥同伴"这条路线在 1.20.1 上已经有人走通 ✓；它的 MCP 接法值得我们对照 ✓ |
| [nekostulAICompanion](https://modrinth.com/mod/nekostulaicompanion/version/1.1)（1.20.1 ✓） | 小型 AI 同伴模组的实现规模参考 ✓（一个人也能写出来 ✓） |

**三条可以直接落地的设计原则** ✓：

1. **任务要能被中断和恢复** ✓（我们现在的 `job_*.lua` 一旦开跑就独占通道 ✗ —— 女仆那套不是这样 ✓）
2. **行为用数据描述，不要写死在代码里** ✓（我们已经在用 `agent/plans/*.json` ✓ 这个方向是对的 ✓）
3. **反射放在最底层、永远优先** ✓（保命 > 玩家命令 > 长期计划 ✓ —— 现在的 Lua 反射层已经是这个优先级 ✓ 移植时保持 ✓）

---

## 4. 不管走哪条路，都该给假人补的能力（按价值排序）

1. ✅ **周边方块读取 `blocks_around`**（已做 ✓ 一次 196 格 ✓ 带坐标与方位 ✓）
2. ⬜ **无 GUI 合成** ✓（路线 A 用 mineflayer ✓ / 路线 B 在模组里直接调 `RecipeManager` ✓）
3. ⬜ **背包自我管理** ✗（今天踩的坑：主背包里的物品假人**动不了** ✗ —— 模组/mineflayer 里这个限制不存在 ✓）
4. ⬜ **容器读写**（箱子/桶/漏斗 ✓ 取料与入库 ✓ —— 熔炼线的地基 ✓）
5. ⬜ **熔炼线**（假人把燃料+矿石丢在漏斗上 → 炉子 → 出炉自动拾取 ✓ 全程零界面 ✓）
6. ⬜ **寻路**（现在是 `/player move` 逐格挪 ✓ 慢且脆 ✗ → 换 A\* ✓）
7. ⬜ **聊天交互**（AP 的 `chatBox` 已经在 cc0 上 ✓ 可让假人"听懂人话" ✓）
8. ⬜ **AE2 ME Bridge 接入**（目标第 3 条 ✓ 免界面按需合成与物流 ✓ —— 有了它，合成这条腿就彻底不依赖 GUI ✗✓）

---

## 5. 2026-09-18 深夜补：**路线 A 在这个包上是死的** ✗ + **包里其实已有现成通路** ✓

### 5.1 无头客户端进不来（实测 ✓ 一句就够）

```
[连 localhost:57323 → ] Kicked during login:
  {"text":"This server has mods that require Forge to be installed on the client. ..."}
```

- **原因**：Forge 服务端要求客户端完成 FML 握手 ✗ —— mineflayer 走的是**原版协议** ✓ 所以被踢 ✗
  （不是端口问题 ✓ 端口是玩家现给的 57323 ✓ 我连的是对的 ✓）
- ⇒ **路线 A（无头客户端）对 Forge 整合包不成立** ✗（除非找到 1.20.1 的 Forge 握手插件 ✗ 目前没有 ✓）
- ⇒ 而且本机**没有 JDK/gradle** ✗（`java`/`javac`/`gradle` 都不在 PATH ✓ PCL 用的是自带 JRE ✗）
  ⇒ 真要写模组 ✓ 得先下 JDK（约 200 MB ✓ 有网 ✓ 可行 ✓）—— **但在动手写之前，先看第 5.2 节** ✓

### 5.2 ★关键发现★ 这个包里**已经有"免界面通路"的参考实现** ✓✓

我把 mods 目录按用途筛了一遍 ✓（这也回答了"应该有参考" ✓）：

| 已安装的模组 | 它提供的"通路" | 对我们的意义 |
|---|---|---|
| **`exmachinis-deorum-3.0.3`** | **`exmachinis:flux_sieve`（自动筛）** ✓ **`flux_hammer`（自动锤）** ✓ `flux_compactor` ✓ `item_buffer` ✓ | ★**加工链的答案**★：纯方块 ✓ **零 GUI** ✓ 上面漏斗喂料、下面漏斗出料 ✓ —— 假人只要"把东西丢上去" ✓（正是目标第 2 条的形态 ✓）⚠ 需要 **FE 电力** ✗ |
| **`IntegratedCrafting-1.20.1-1.2.0`** | 自动合成接口（按需合成 ✓ 可从相邻容器取料 ✓） | **合成**✓ 的逻辑通路（配合 Integrated Dynamics 的变量卡驱动 ✓ 仍然不需要点界面 ✓） |
| **`appliedenergistics2-forge-15.4.2`** | **AE2 自动合成**（样板 + 分子装配室 ✓） | ★目标第 3 条点名的就是它★ ✓ 而且 AP 的 **ME Bridge** 能把 AE2 网络直接暴露给 CC ✓✓ |
| `modular-routers-12.1.1` | 物品路由（无 GUI ✓） | 物流 ✓ 替代漏斗的升级版 ✓ |
| `craftingstation` / `crafting-on-a-stick` / `craftingtweaks` | 各种"工作台"变体 | ⚠ 都还是要**点界面** ✗ 对假人无用 ✗ |

**外部参考（搜索所得 ✓ 可对照实现 ✓）**：

- [Applied Energistics 2 · 自动合成机制（官方手册原文）](https://raw.githubusercontent.com/AppliedEnergistics/Applied-Energistics-2/b06743029314072279d55f2dfe6e3ad40ec3c780/guidebook/ae2-mechanics/autocrafting.md)
  —— "把合成变成通路"最完整的官方说明 ✓（样板供应器 / 分子装配室 / 按需合成 ✓）
- [Advanced Fake Players（CurseForge）](https://www.planetminecraft.com/mod/advanced-fake-players/) —— 假人动作集的参考 ✓
- [Duzo's Fake Players（GitHub）](https://github.com/Duzos/fakeplayer) —— 更完整的假人动作实现 ✓（含容器/合成类动作 ✓）
- [GugleCarpetAddition（GitHub Releases）](https://github.com/Gu-ZT/gugle-carpet-addition/releases) —— **Carpet 的扩展** ✓ 给假人加了很多动作/规则 ✓ 值得对照它到底加了什么 ✓
- [Fake Player（CurseForge）](https://www.curseforge.com/minecraft/mc-mods/fake-player/files/8351423/dependencies) —— 另一条"假人当执行体"的路线 ✓

**结论（路线 B'）** ✓：**先别写模组** ✗ —— 先用**包里已有的方块**把通路搭出来 ✓✓：
`自动筛（Ex Machinis）→ 石砾 → 圆石 → 熔炉 → 铁 → 漏斗线` ✓ 而**通用合成**交给
`IntegratedCrafting` 或 `AE2` ✓ —— 等到这些都不够用时 ✓ 再写那个"一个 jar"的模组 ✓。

### 5.3 附带查实的一个**真 bug** ✗（这条会一直挡着"筛矿"）

- **现象**：假人在筛子旁用 `sift` 技能连点 **25 秒** ✓ 筛子 NBT 里 `progress` **仍然是 `0.0f`** ✗
  （同一次读到的还有 `mesh: exdeorum:iron_mesh` ✓ `contents: {gravel ×1}` ✓ —— 筛子本身是好的 ✓）
- **结论**：**假人的右键没有落到筛子上** ✗ —— 不是"太慢" ✓ 是"没生效" ✗
  （这也解释了为什么 `docs/当前阶段-状态与交接.md` §12.2 里"让假人先走到筛子旁再 sift"一直没验收通过 ✗）
- **绕法** ✓：改由**海龟的 `turtle.place()`** 做"用物品右键方块" ✓（CC 那条路是给装筛网/撒种子用的 ✓）
  —— 对应 `cc-tweaked/job_sift.lua` ✓（它会自己转 4 个方向用 `inspect` 认出筛子 ✓ 不依赖朝向记录 ✓）
- **终极绕法** ✓：**Ex Machinis 的自动筛** ✓ —— 连右键都不需要了 ✓（见 5.2 ✓）

