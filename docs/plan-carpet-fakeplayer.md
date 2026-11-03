# 路线切换：Carpet 假人（Forge 1.20.1）

> 决策时间：2026-09-12 15:1x　状态：**已安装，待重启验证**
> 上一版路线（CC 海龟专职化）已判定为架构不适配，见文末"为什么换"。

## 一句话方案

不跟 Forge 的客户端握手协议搏斗，也不为每种工作造一台海龟，而是**在服务器内部生成一个"真实玩家"**：
Carpet 的 `/player <名字> spawn` 造出的假人是服务端真正的 `ServerPlayer` 实体——有正常背包、能拿真工具、
能打架、能被怪物打、能正常合成与放置。Agent 通过已有的 CC 通道对它下指令，它就相当于**第二个玩家**。

## 装了什么（可核对事实，不是记忆）

| 项 | 值 |
|---|---|
| 文件 | `forge-carpet-1.20.1-1.0.8+v251027.jar` |
| 来源 | Modrinth 项目 `XqqOkvZz`（Carpet: NeoForged），版本 id `XMYeNIOx` |
| 大小 / SHA1 | 1740072 B / `e9406d0663d812ed2846a406cd902c6d64749fd8`（下载时当场校验通过） |
| 声明依赖 | `forge range=[47,)`、`minecraft [1.20,1.20.1]`，**无其它硬依赖** |
| 环境标记 | `server_only_client_optional`（单人集成服务器可用，客户端无需装） |
| 落地位置 | `D:\pcl2\.minecraft\versions\All the Mods 9 - To the Sky - atm9sky\mods\`（309 个 jar 中的第 309 个） |
| 本地留存 | `mc-agent-bridge\downloads\forge-carpet-1.20.1-1.0.8+v251027.jar` |

jar 内已确认存在（不是靠 Modrinth 标签推断）：

- `carpet/commands/PlayerCommand.class` → `/player` 命令本体
- `carpet/patches/EntityPlayerMPFake.class` → 假人实体
- `carpet/helpers/EntityPlayerActionPack.class` → 假人动作包（攻击/使用/移动等）
- 全套 scarpet 脚本引擎 + fake player 相关 mixin

## 同时改了的世界配置

文件：`saves\新的世界 (1)\serverconfig\computercraft-server.toml`
备份：同目录 `computercraft-server.toml.pre-carpet.bak`

| 行 | 改动 | 原因 |
|---|---|---|
| L23 | `command_require_creative = true` → `false` | 否则必须在创造模式且 OP 才能用指令电脑，机器人无法自主使用 |
| L140 | `command_block_enabled = false` → `true` | 指令电脑执行指令的能力开关 |

写入用 .NET `WriteAllText` + `UTF8Encoding($false)`，并**回读首 3 字节**确认是 `#Th`（35,84,104）而不是 BOM
—— 这是 B13 事故（PowerShell 5.1 的 `-Encoding UTF8` 写出 BOM 导致服务器崩溃）的固定复核动作。

## 回滚方式（两个文件，30 秒）

1. 删 `mods\forge-carpet-1.20.1-1.0.8+v251027.jar`（或改名加 `.disabled`）
2. 把 `computercraft-server.toml.pre-carpet.bak` 覆盖回 `computercraft-server.toml`
3. 重启游戏即可回到改动前状态

## 通道设计

```
Agent(文件桥) → gateway → CC 主计算机 cc0 → 无线调制解调器
                                    ↓
                          CC 指令电脑(computercraft:computer_command)
                                    ↓  commands.exec("player Bot attack")
                          Carpet 假人 Bot（服务端真实玩家实体）
```

- 指令电脑是唯一能执行任意指令的 CC 设备（普通电脑没有 `commands` API）。
- `agent_bridge.lua` 新增两个动作：
  - `cmd` → `commands.exec(text)`，**同步**返回指令输出（用于 `/give`、`/time` 等瞬时指令）
  - `cmd_async` → `commands.execAsync(text)`，投递即返回（用于 `/player Bot attack` 这类持续动作，
    同步版会一直阻塞到动作结束，等于永远不返回）
- 普通电脑上调用这两个动作会明确报错"本机不是指令电脑"，不会静默失败。

## 验收标准（全部要客观证据，不接受"应该可以"）

1. **加载无冲突**：重启后 `py tools/check_carpet_load.py` 显示
   - 无新增 crash-report
   - 无与 `carpet` 相关的 ERROR/异常
   - 日志中出现 carpet 的 mixin/配置行
2. **`/player` 真存在**：玩家在游戏里执行 `/player Bot spawn`，日志应出现 `Bot joined the game`
   （假人走原版登录流程，这是铁证）。同时 Tab 列表里能看到 Bot。
3. **Agent 能驱动它**：通过网关 `{"action":"cmd","text":"player Bot attack"}` 下指令，
   能在游戏里看到 Bot 挥剑。

## `/player` 权威子命令表（从 jar 常量池提取，非记忆）

来源：`forge-carpet-1.20.1-1.0.8+v251027.jar` → `carpet/commands/PlayerCommand.class` 的字面量常量。

```
/player <名字> spawn [in <维度>] [at <x y z>] [facing <方向>] [gamemode <模式>]
/player <名字> stop | stopAll
/player <名字> use | jump | attack | drop | dropStack | swapHands
/player <名字> hotbar <1..9>
/player <名字> kill | shadow | mount | dismount
/player <名字> sneak | unsneak | sprint | unsprint
/player <名字> look north|south|east|west|up|down
/player <名字> look at <x y z>          -- 看向指定坐标（挖矿/放置前的对准）
/player <名字> rotation
/player <名字> turn left|right|back
/player <名字> move forward|backward | stopMovement
```

动作修饰（`makeActionCommand` 的三个分支）：`once` / `continuous` / `interval <ticks>`
→ 例如 `player Bot attack interval 20`。

假人动作枚举（`EntityPlayerActionPack$ActionType`）：`USE`、`ATTACK`、`JUMP`、`DROP_ITEM`、`DROP_STACK`、`SWAP_HANDS`。
另有移动/朝向接口：`setForward`、`setStrafing`、`setSneaking`、`setSprinting`、`setSlot`。

**注意：没有 `craft` 子命令**（已核对全部字面量）。所以分工是：

| 工作 | 由谁做 | 理由 |
|---|---|---|
| 砍树、挖矿、建造、放置、战斗、拾取 | Carpet 假人 | 真玩家实体：真工具、真背包、真战斗判定 |
| 合成、物品分类与箱子整理 | CC 电脑 / 海龟 | 海龟 `craft()` 不需要工具升级件；电脑可读箱子库存 |
| 跨机器协调、状态读取 | CC 主计算机 + 网关 | 已有桥接，负责感知与调度 |

同文件里读到的权限/限制原文：
- `Only fake players can be moved or killed`（只能移动或杀死假人）
- `Non OP players can't control other real players`
- `Cannot shadow fake players`
- 规则开关名 `commandPlayer`（默认开，实测 `/player` 可用）


海龟是**方块实体**，没有玩家背包/工具语义：工具得靠"用钻石工具合成海龟升级件"获得，
每个工作类型（伐木/挖掘/战斗）都要单独一台，且不能自然使用箱子、合成台、门。
要求是"一个能当第二个玩家用的机器人"，海龟的形态与这个要求从根上不匹配——
继续投入只是把不适配做得更精致。Carpet 假人是"真玩家"，一次到位覆盖聊天/建筑/挖矿/合成/打怪全部工作类型。

## 已知风险 / 待验证

- Carpet: NeoForged 是 1.20.1 的 Forge 移植版（beta，5.2 万次下载），与 308 个模组的 mixin 冲突只能实测。
  `CarpetPassthrough`（来自 shetiphiancore）与它**只是名字撞车**，无关。
- 包里 `alltheleaks` 模组已在用 Forge 的假人机制（日志有 `Fake player readout: … name=[Mekanism]`），
  Carpet 的假人是另一套实现，需观察是否互相干扰。
- 指令电脑执行指令时的权限等级为 2；Carpet `/player` 要求 2 —— 刚好够，若实际不够则改用
  RCON 或在游戏里手动授权，届时按证据决定。
