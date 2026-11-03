# Carpet 假人路线：进度与实测事实

> 更新：2026-09-12 15:45　状态：**通道已通，机器人能干真活，砍树作业已跑通**

## 一、已经确证的事实（全部有日志/回传证据，不是推断）

### 通道层

| 事实 | 证据 |
|---|---|
| Carpet 假人模组装好且无冲突 | 日志 `carpet.mixins.json:Commands_customCommandsMixin` 已应用 ✓ 无崩溃 ✓ |
| 假人是服务端真实玩家 | `Bot[local] logged in with entity id 1205` ✓ `list` 回传含 `Bot` ✓ |
| CC 指令电脑能执行任意指令 | `say MCAGENT_ACCEPTANCE_1` → 游戏日志出现 `[@] MCAGENT_ACCEPTANCE_1` ✓ |
| 指令电脑权限够用（等级 2） | `player Bot stop` 等指令全部 `success: true` ✓ |

### API 层（都是实测出来的，别凭记忆改）

| API | 实测结论 |
|---|---|
| `commands.exec(cmd)` | 返回 **3 个值**：成功标志、输出表、结果码。⚠ 用 `local ok, out = pcall(...)` 会吞掉输出 |
| `commands.execAsync(cmd)` | 返回任务 id；持续动作（如 `attack continuous`）**必须**用它，同步会永久阻塞 |
| `commands.getBlockInfo(x,y,z)` | 单点读取，**约 50ms/次**（走服务器线程），只适合少量确认 |
| `commands.getBlockInfos(minX,minY,minZ,maxX,maxY,maxZ)` | 批量读取；**有内置体积上限**，17³=4913 会报 `Too many blocks`；实测按 4³ 分块安全 |
| getBlockInfos 的遍历顺序 | **y（最外）→ z → x（最内）**。用"批量 vs 单点逐格"对照实验、穷举 6 种排列确定 |
| 返回项结构 | `{ name = "minecraft:oak_log", state = {}, tags = {...} }` —— **不含坐标**，坐标要靠顺序推算 |
| 其它可用方法 | `getBlockPosition()`、`list()`、`getBlockInfos` |

### `/player` 假人（从 jar 常量池提取的完整子命令表）

```
spawn [in <维度>] [at <x y z>] [facing <方向>] [gamemode <模式>]
stop | stopAll | kill | shadow | mount | dismount
use | jump | attack | drop | dropStack | swapHands | hotbar <0-8>
sneak | unsneak | sprint | unsprint
look north|south|east|west|up|down | look at <x y z> | rotation
turn left|right|back | move forward|backward | stopMovement
动作修饰：once | continuous | interval <ticks>
```
**没有 `craft` 子命令**（核对过全部字面量）→ 合成交给 CC 海龟（`turtle.craft()` 不需要工具升级件）。

### 假人实体层

| 事实 | 证据 |
|---|---|
| 假人**继承真人的背包** | 背包实测：火把 / 洒水壶 / 手册 / 能力瓶…，手持是火把（不是斧头） |
| 可以用原版 `/data` 读它 | `data get entity Bot Inventory` / `Pos` / `SelectedItemSlot` 均可用 → Agent 有可靠的读状态手段 |
| 输出前缀会被本地化成中文 | 中文客户端下 `joined the game` 变成"加入了游戏" ✗ → 解析只取数字/方括号内容，不认文案 |

## 二、砍树作业（`chop_tree`）—— 第一个"一条指令做完一件事"的动作

流程：普查找木头 → 读坐标判定够不够得着 → 自动挑工具（斧头优先）→ 从低往高逐段
`look at` + `attack continuous` + 轮询确认方块消失 → 补一轮重试 → 停手 → 再普查复查 → 聊天栏报告。

两次实测对比（同一棵树）：

| | 第一次 | 第二次（修复后） |
|---|---|---|
| 耗时 | 121.1 s | **18.2 s** |
| 成功 | 5 段 | 5 段 + 补上 y=71 = **整棵树** |
| 失败报告 | 9 条统一写"超时"（误导） | 8 条如实标 `out_of_reach` + 真实距离 7.2/10.3/… |
| 工具 | `none(徒手)` ✗ | `minecraft:diamond_axe` slot 5 ✓ |

三个真实 bug（都靠"回传结果不合理"发现）：

1. **`pcall` 吞掉多返回值**（犯两次）：`commands.exec` 的 3 个返回值只接住 1 个 →
   ① 三条不同指令都回传 `"true"` ② 背包永远解析出 0 件物品（退化成徒手砍树）。
   → 已加 **lua_lint 规则**（只针对 `commands.exec`，加规则时自测命中 + 排除 `getBlockInfo` 误报）。
2. **瞄准点取方块中心反而砍错格**：Bot 站在树干正下方时视线太陡，射线先碰到上面那一格 →
   "要砍 y=71"实际砍掉 y=72（报告里 y=72 显示 `already air` 就是铁证）→ 改瞄 `y+0.2`。
3. **够不着却伪装成超时**：8 格外的树每格白等 10 秒 → 现在先算距离、如实标记 +
   重跑时直接跳过 → 省下 90 多秒。

## 三、运维层：机器"退出后没人管"的问题

真实事故：为修中文乱码重启网关，打断了两台机器的 HTTP 请求 → 主循环末尾的 `sleep`
在 `pcall` 保护圈之外 → 两台机器全部退出到 shell 提示符，**外部既看不到也拉不起来**，
只能等人进游戏按 Ctrl+R。

修复：
1. **最外层看门狗**：`while true do pcall(main) ... end`，除非收到明确的
   quit / shutdown / reboot（用 `EXIT_NOW` 标志区分"故意停"），否则 5 秒后自动重启。
2. **`startup` 先 `load()` 检查再落盘**：原版是"先覆盖本地副本再检查" ✗ ——
   新程序有语法错误时会把**好用的副本覆盖成坏文件**，下次网关不可达就没退路了。
3. 中文乱码：文件桥的 `log.jsonl` / `state.json` 此前只修了 HTTP 那条路 →
   现在两处写入都过 `repair_cc_text()`（该函数对已修文本幂等）。

## 四、还缺的能力（按优先级）

| 能力 | 为什么需要 | 大致做法 |
|---|---|---|
| **走过去（walk_to）** | 那两棵树在 7~10 格外，够不着。天空岛走路是高危动作：一步踏空就是掉虚空 | `look at` 目标 → 每步先确认前方**下方**有落脚方块、前方是空气 → 再 `move forward` → 位置轮询；位置掉下去就立刻停手报告 |
| **补种（replant）** | 原需求："先将树砍掉然后补种" | `/give` 树苗 → `look at` 泥土方块 + `use` → 再普查确认出现 `oak_sapling` |
| **木头变木板** | 原需求的后半句 | 海龟 `craft()`：Bot 掉落 → 海龟 `suck()` 拾取 → 合成 → 统计核对数量 |
| **开平台** | 原需求的最终产物 | 假人手持木板 `use` 放置（或海龟 `placeDown`），逐格推进 |

## 五、后续补充的实测事实（2026-09-12 15:50）

| 事实 | 证据与后果 |
|---|---|
| **`hotbar` 子命令是 1 起算** | 发 `player Bot hotbar 5` → `SelectedItemSlot` 变成 **4**。差一位的后果极隐蔽：以为拿了斧头、实际拿了拴绳，**不报错**，Bot 徒手砍完整棵树，报告里还写着 `tool=diamond_axe` |
| `/player use once` 能种树苗 | 世界里实测生成 2 个 `oak_sapling`：(4125,71,10) 与 (4126,71,10) ✓ |
| 放置类操作会被"最近的方块面"决定 | 想种在 (4123,71,10)，实际种在 (4125,71,10)——射线先撞上 Bot 面前那一格。**必须以世界实际结果为准**，不能以传入参数为准 |
| `data get block` 只能读方块实体 | 读空气/泥土/原木必须用 `commands.getBlockInfo`。用 `data get block` 探测空气会返回失败码 0，容易被误读成"操作没生效" |
| Lua 局部函数必须先声明 | `readBlock` 写在 `plant_sapling` 之后 → 运行期 `attempt to call global 'readBlock' (a nil value)`。底层工具函数统一放在文件最前面（与 `packReturns` 同处） |
| 三处索引陷阱同源 | `commands.exec` 的值在 packReturns 的下标 2/3，`getBlockInfo` 的在 2。已收敛为**唯一入口** `readBlock()`，并在 lua_lint 里为本类错误加了规则 |

### 已完成的用户需求

- **砍树** ✓ 完整砍掉基地旁的橡树（6 段原木全清，含站树下够不到、需要"第二轮重试"的 y=71 那段）
- **补种** ✓ 树苗已种回平台（2 处，实测确认）

### 仍未完成

- **走过去（walk_to）**：另有两棵树在 7~10 格外，Bot 够不着。天空岛走路高危（一步踏空=掉虚空），
  需要"每步先验证前方下方有落脚方块"的安全走法，而不是直接用 `move forward`。
- **木头变木板**：Carpet 无 `craft` 子命令 → 交给 CC 海龟 `turtle.craft()`（不需要工具升级件），
  流程为 Bot 掉落 → 海龟 `suck()` → 合成 → 核对数量。
- **开平台**：假人手持木板 `use` 逐个放置，或海龟 `placeDown`。
## 六、假人 = 真玩家吗？能用模组的"一键砍树"吗？（全部实测，2026-09-12 16:00）

### 背包/物品：与玩家一致（有证据）

| 能力 | 证据 |
|---|---|
| 标准玩家背包（Slot 0-35 + SelectedItemSlot） | `data get entity Bot Inventory` / `SelectedItemSlot` 均可读，结构与真玩家相同 |
| 会被 `/give` 正常发放 | `give Bot minecraft:diamond_axe` → 落到 slot 5 |
| 会被 `/enchant` 正常附魔 | `enchant Bot apotheosis:chainsaw 1` → slot 5 出现 `Enchantments: [{id:"apotheosis:chainsaw",lvl:1s}]` |
| **会自己捡起地上的掉落物** | 在它脚下 `/summon item ... diamond` → 背包出现 `Slot: 8b minecraft:diamond`；树叶凋落的树苗也被捡走（4→5）；Chainsaw 砍倒的原木进了 `Slot: 9b` |
| 物品 NBT 完整（附魔/自定义名/耐久） | 木斧显示 `display.Name = "And My Axe!"` + `unbreaking lvl 3`；钻石斧 `Damage: 8` |
| **出生时继承真人的背包副本** | 火把 / 洒水壶 / 手册 / 能力瓶 —— 与真人当时的背包一致 |

尚未验证（不要当成已知）：Curios 饰品栏、末影箱 EnderItems、进阶/任务进度、
以及需要客户端 GUI 的行为（背包界面、JEI、箱子界面操作）。

### 模组功能：分两类，结论完全不同

**① 靠客户端按键的 → 假人用不了（FTB Ultimine）**

从 `ftb-ultimine` 字节码提取的触发链：

```
FTBUltimineClient → net/minecraft/client/KeyMapping
                  → ClientRawInputEvent$Key
                  → KeyPressedPacket        （按键状态由客户端打包上传）
                  → FTBUltimine.setKeyPressed(...)
```

服务端只是**接收**按键状态，自己不判断；假人没有客户端，没人替它按键 →
键状态永远 false → **Ultimine 对假人永不触发**。该模组的服务端配置里 10 个选项
全部以 "with the Ultimine key held" 为前提，没有任何"无需按键"的开关。

**② 靠附魔 / 服务端逻辑的 → 假人完全可用（Apotheosis Chainsaw，已实测）**

`enchantment.apotheosis.chainsaw`（描述：Trees will be annihilated）——
对 Bot 的钻石斧附魔后，**只瞄最下面一格砍一下**，5 格测试树全部消失，
且掉落物被它自己捡走。对照组：同样的动作、**未附魔**时只砍掉瞄的那一格，
上方原木原样悬空（第一次砍真树的报告 `remaining: 8` 正是这个现象）。

同理可用（同一机制：服务端在正常破坏方块时判定，尚未逐个实测）：
- `ensorcellation:excavating`（范围挖掘）
- `improved_exp:rock_crusher`（矿脉）

包里另有**不依赖按键**的自动化途径：
Occultism 的 Foliot Lumberjack（会砍树的工人精灵）、XyCraft Vein Logic Module、
Blood Magic veinmine charge、Thermal/IE/Redstone Arsenal 的 Excavator 系列工具。
## 七、筛矿机制完全查清并跑通（2026-09-12 18:2x）

### 结论：之前所有"右键无效"都是**瞄准**问题，不是机制问题

`SieveBlock` 有自定义碰撞形状（`SHAPE = Shapes.box(...)`），是**矮碗形**，
顶面远低于 y+1。一直瞄 `sy+0.99`（方块顶部）→ 射线**从筛子上方掠过**、
完全打不中 → 表现为"右键毫无反应、指令却每次成功"。
**改为瞄 `sy+0.15~0.2`（碗内）后立刻成功**：`/data get block` 出现
`mesh: {id:"exdeorum:iron_mesh", Count:1b}` ✓。

教训：不要假定方块的"可点击面"在哪；`sift` 作业已改为**自动试多个高度**，
并用"原料是否被消耗"作为唯一判定，全都不生效才报失败并列出试过的高度。

### 已实测确认的机制

| 事实 | 证据 |
|---|---|
| 每个筛子**各自**需要一个筛网 | 任务书原文 "Each Sieve in the group needs its own mesh" ✓；装上后 NBT 出现 mesh 字段 ✓ |
| 筛网靠**右键筛子**装入（`EBlock.use` → `isValidMesh`/`setMesh`） | 装入后 NBT 变化 ✓；`AbstractSieveBlockEntity` 有 `isValidMesh/setMesh/getMesh/popOutMesh` ✓ |
| 手持**要筛的方块**右键 | 任务书原文 "Right-clicking the middle Sieve with the item you want to sieve" ✓ |
| 掉落物**自动进假人背包** | `sift` 的背包差异直接读到 `exdeorum:aluminum_ore_chunk: 2` ✓ |
| 逐块**推进度**，不是一次一块 | 140 次点击 ≈ 12 块（约 11 次/块，铁筛网）；`progress` 字段存在 ✓ |
| 一次掷骰可能**什么都不出** | 32 次点击（1 块）→ `gained {}` 但 `spent {gravel:1}` ✓ |
| 5×5 共 25 筛，点**中间**一次筛 25 个 | 任务书 `desc.mesh` 原文 ✓（同步点击） |
| 自动点击器无需电力、前期优于机械筛 | ClickMachine 无能量接口 ✓；机械筛需 FE + 升级 ✓（任务书 start2 ✓） |

### 砾石产出表（ATM9 实际配方，来自 KubeJS + jar，离线可查）

```
线筛网:  stone_pebble×4 40%  flint 20%  coal 10%  iron_ore_chunk 10%
         copper_ore_chunk 8%  gold_ore_chunk 3%  lapis 3%  diamond 2%  emerald 1%
铁筛网:  deepslate_pebble×3 55%  stone_pebble×4 50%  coal 15%  flint 15%
         iron_ore_chunk 14%  copper_ore_chunk 12%  gold_ore_chunk 6%  diamond 5%  emerald 4%
金/钻石/下界合金筛网另有更高概率与专属掉落（含 gold_nugget 等）
```
注意：**低阶筛网某些掉落反而更好**（任务书明确提示 ✓），所以不能一味升级。

### 工具修正（都是真实踩坑）

- `recipe_index.py`：筛矿配方字段是 `ingredient`（单数）+ `mesh`，此前按 `ingredients`/`input`
  解析 → 筛矿配方"原料为空"、无法回答"砾石能筛出什么"。已修正，并新增 `--input`/`--mesh` 过滤
  与 `result_amount` 的 `n`/`p`（数量/概率）解析 ✓。
- `bot_inv`：槽位号可能是**负数**（副手 = `Slot: -106b`），原正则 `(%d+)` 直接漏掉副手 ✗ → 已改为 `(-?%d+)` ✓。
- `jar_strings.py`：新增 `--class` 过滤（只看某个类的引用）✓ —— 正是靠它定位到交互在基类
  `EBlock`、状态在 `AbstractSieveBlockEntity` ✓。