# 安装与使用（Minecraft 1.20.1 / Forge）

> 目标：在 10 分钟内跑通 `Agent → 网关 → 游戏内计算机 → 执行 → 回报` 的闭环。

---

## 0. 前置检查

- [ ] 服务端是 **1.20.1**，已装 **CC:Tweaked（Forge）** 与 **Advanced Peripherals（Forge）**
- [ ] 网关所在机器能被游戏内访问（本机开服 → `127.0.0.1` 即可）
- [ ] Python 3.8+（网关只依赖标准库）
- [ ] **整合包能离线启动**：ATM9 里 `Emojiful` 会在 `Minecraft.<init>`（渲染主线程）同步联网，
      一旦 `raw.githubusercontent.com` 不可达就**永久卡死**（详见 `../docs/lessons-learned.md` E6）。
      先把它改成 `.jar.disabled` 再启动，可省掉一次"游戏无响应"的排查
- [ ] **⚠️ 关闭"失去焦点时暂停"**（**方案 C 的硬性前提**）
      - **游戏内按 `F3 + P` 即可切换**（屏幕上会提示「失去焦点时暂停：停用」）——
        这是 1.20.1 唯一的内建切换方式
      - ⚠️ **不要在"辅助功能设置"里找这个开关：1.20.1 已经没有这个菜单项了**
        （该选项在 1.19.4/1.20 被移出 GUI，只留下调试快捷键；
        已核对 1.20.1 的 `en_us.json`，其中只有 `debug.pause_focus.*`，没有 `options.pauseOnLostFocus` 标签）
      - 备用方式：直接改 `options.txt` → `pauseOnLostFocus:false`
        （**必须先关游戏**，否则游戏保存设置时会覆写你的修改；且要用 UTF-8 **无 BOM** 写入，见 lessons-learned B13）
      - **原因**：单人游戏在你切换到浏览器/别的窗口时会暂停整个世界。
        而方案 C 是"Agent 下指令 → 游戏内计算机执行"，**你要一边看浏览器一边让机器人干活**，
        世界一暂停，计算机的 `os.pullEvent` 循环和 HTTP 请求全部停摆 → Agent 的指令永远不会被执行
        （日志特征：`Saving and pausing game...`。注意区分"暂停"与"卡死"，见 lessons-learned E6/F9）
- [ ] **先读 `../docs/lessons-learned.md`**：里面是本项目踩过的 39 个坑，照着纪律走能省掉大量返工
- [ ] 需要确认"游戏窗口到底长什么样"时，用 `& .\tools\grab_window.ps1` 抓真实画面
      （**不要**用全屏截屏判断——它抓不到游戏画面；`-Fix` 还能把跑到屏幕外的窗口搬回来）

---

## 1. 启动网关

```bash
cd mc-agent-bridge
python gateway/agent_gateway.py --port 8765 --root cc-tweaked --cli
```

看到这样的输出即为正常：

```
 MC Agent Bridge gateway
   看板      : http://127.0.0.1:8765/
   脚本目录  : .../cc-tweaked
   可下发    : /files/agent_bridge.lua
   可下发    : /files/turtle_worker.lua
```

浏览器打开 `http://127.0.0.1:8765/`，应看到控制台。

---

## 2. 放行 CC 的 HTTP（关键一步）

CC:Tweaked **默认会拦截对私有网段的请求**，必须放行，否则游戏内 `http.get` 直接失败。

**先找对文件**：`computercraft-server.toml` 在 Forge 1.20.1 里是 **SERVER 类型配置 = 按世界存放**，
不在全局 `config/` 目录（改错地方会"改了没反应"）：

| 目标 | 路径 |
|---|---|
| 已有存档 | `saves\<世界名>\serverconfig\computercraft-server.toml` |
| **新建**存档 | `defaultconfigs\computercraft-server.toml`（创建世界时**复制**进该世界） |

改这一行即可（`$private` = 私有网段，含 `127.0.0.1`）：

```toml
[[http.rules]]
    host = "$private"
    action = "allow"
```

`$private` 代表私有网段（127.0.0.0/8、10.0.0.0/8、192.168.0.0/16、172.16.0.0/12、fc00::/7）。

> ⚠️ **保存方式有讲究：必须是 UTF-8 无 BOM。**
> 用 PowerShell 的 `Set-Content -Encoding UTF8`（PS 5.1）会写入 BOM，
> 游戏加载时会直接崩，报错长这样：
> `ConfigLoadingException: Failed loading config file computercraft-server.toml` /
> `ParsingException: Invalid bare key: ﻿#The`（`#` 前那个看不见的字符就是 BOM）。
> 用记事本 / VS Code「另存为 UTF-8（无 BOM）」最稳。
> 改完回读首字节复核：`23`(`#`) 或 `5B`(`[`) 正常，**`EF BB BF` 必须去掉**。

> **改完必须重启游戏（服务端）才生效。**

---

## 3. 游戏内布置

### 3.1 主计算机

1. 放一台 **Advanced Computer**
2. 相邻面贴上外设（贴哪面都行，程序会自动发现）：

   | 外设 | 作用 | **摆放硬性要求** |
   |---|---|---|
   | **Chat Box** | 在游戏里说话 | 无（注意：**本版没有读取聊天的 API**）|
   | **Geo Scanner** | 扫方块（**含模组方块**）| **需要燃料**，否则 `scan` 随机失败 |
   | **Block Reader** | 读方块/机器状态 | **它面朝的方向必须有方块**，对着空气会返回 nil |
   | **Player Detector** | 玩家位置（**绝对坐标**）| 无 |
   | **Inventory Manager** | 库存读写 | **必须紧贴一个容器**，否则 `listChest` 报错 |

3. 插一个 **Wireless Modem**（可选；要指挥海龟机器人时才需要）

> **本版（AP 0.7.44）实测 API 名**——用程序自带的 `peripheral_api` 指令从游戏里问出来的，
> 不是猜的。写自动化脚本时请以它为准：
>
> | 外设 | 可用方法 |
> |---|---|
> | Block Reader | `getBlockData` `getBlockName` `getBlockStates` `isTileEntity` `getConfiguration` `getName` |
> | Chat Box | `sendMessage` `sendMessageToPlayer` `sendToastToPlayer` `sendFormattedMessage` `sendFormattedMessageToPlayer` `sendFormattedToastToPlayer` `getOperationCooldown` |
> | Geo Scanner | `scan` `chunkAnalyze` `cost` `getFuelLevel` `getMaxFuelLevel` `getFuelConsumptionRate` `setFuelConsumptionRate` `getOperationCooldown` |
> | Player Detector | `getOnlinePlayers` `getPlayer` `getPlayerPos` `getPlayersInRange` `getPlayersInCoords` `getPlayersInCubic` `isPlayerInRange` `isPlayerInCoords` `isPlayerInCubic` `isPlayersInRange` … |
> | Inventory Manager | `listChest` `getItemsChest`（读容器）· `list` `getItems`（读绑定玩家）· `getOwner` `getArmor` `getItemInHand` `getItemOffHand` `addItemToPlayer` `removeItemFromPlayer` `getEmptySpace` `getFreeSlot` `isSpaceAvailable` `isWearing` `isPlayerEquipped` |
>
> 换版本后如果某条指令报"无可用的 API"，**先下发一条 `peripheral_api` 看真实方法名**，
> 不要凭印象改代码。

### 3.2 拉取并运行主程序

**方式 A：跑一次（不落盘）**

```
wget run http://127.0.0.1:8765/files/agent_bridge.lua
```

**方式 B：存到计算机磁盘（推荐，之后每次只要敲一个词）**

```
wget http://127.0.0.1:8765/files/agent_bridge.lua bridge
bridge
```

> ⚠️ **不要写成 `run http://...`** —— CC 的 ROM 里**没有 `run` 这个程序**
> （已核对 CC:Tweaked 1.115.1 的 `rom/programs/` 目录：只有 `http/wget.lua`，
> 且其 `printUsage()` 明确写着 `wget <url> [filename]` / `wget run <url>`）。
> 写成 `run` 会得到 **`No such program: run`**。
>
> 网关是**实时读文件**提供的，所以以后我更新了脚本，你重跑上面那条命令即可。
> ⚠️ 方式 B（存盘）**不能用 wget 覆盖**：CC 的 `wget.lua` 里有
> `if fs.exists(sPath) then print("File already exists") return end` —— **它拒绝覆盖已存在的文件**。
> 要更新存盘脚本，先 `delete bridge`（或 `rm bridge`）再 `wget ... bridge`；
> 或者干脆用方式 A（`wget run <url>`，每次都是最新版）。

> 如果服务端跑在另一台机器，把 `127.0.0.1` 换成**网关机器的内网 IP**。

首次运行会生成 `bridge.cfg`，**默认 `dry_run=true`**（只回报不真执行）——这是故意的，先确认通路。
只读指令（`status` / `scan` / `players` / `block_info` / `chat_read` / `say`）不受 `dry_run` 限制，所以首次就能完整跑通冒烟测试。

### 3.3 海龟执行端（可选：让 Agent 从"能看"变成"能动手"）

主计算机**只能读、不能改动世界**。要让 Agent 真的挖矿/建造/搬运，需要一只海龟。
海龟是独立的计算机，通过 rednet 接收主计算机转发的指令。

**需要**：`computercraft:turtle_advanced` ×1、`computercraft:wireless_modem_normal` ×2

| 步骤 | 操作 | 说明 |
|---|---|---|
| 1 | 在主计算机**剩下的空面（顶面）**贴一个 Wireless Modem | 必须相邻才会被识别为 modem 外设；5 个外设已占 5 面 |
| 2 | 右键地面放置高级海龟 | 海龟与主计算机**必须同一维度** |
| 3 | 右键海龟打开界面，把第二个 Wireless Modem 放进**第 1 格**，关掉界面后运行 `equip 1 left` | 依据 CC 的 ROM 程序 `equip.lua`：`Usage: equip <slot> <side>`；成功打印 `Item equipped` |
| 4 | 把煤放进海龟物品栏，运行 `refuel all` | **海龟移动要烧燃料**；用法 `refuel [number\|all]`（已核对 ROM 的 `refuel.lua`）|
| 5 | 在海龟上运行 `wget run http://<网关IP>:8765/files/turtle_worker.lua` | 会打印 `[worker] 就绪 id=<N> role=miner chan=4200` |
| 6 | 主计算机上重启程序（载入 `discover_turtles`）| 海龟 id 不必手抄 |

**下发海龟指令**：任意指令加 `target=<海龟id>`，例如 `tunnel target=7 dir=north length=8`。
不知道 id 时先下发 **`discover_turtles`** —— 它向 rednet 广播一次并收集应答，直接把 id 报回来。

> ⚠️ **安全开关（一句话切换）**
> `dry_run=true` 时，一切会改动世界的动作（含转发给海龟的挖掘/移动）都会被拦下，
> 只回报 `would_dispatch`；而**只读指令照常执行**（含海龟的 `status` / `inv_list` / `calibrate`）。
>
> ```
> wget run http://<网关IP>:8765/files/agent_bridge.lua          ← 用配置里的默认值（默认演练）
> wget run http://<网关IP>:8765/files/agent_bridge.lua live     ← 真动手
> wget run http://<网关IP>:8765/files/agent_bridge.lua dry      ← 演练
> ```
>
> 依据（已核对 CC 的 `rom/programs/http/wget.lua`）：`run` 分支是
> `pcall(func, table.unpack(tArgs))`，**`<url>` 之后的额外参数会传给程序**。
> 这样就不必去改 `bridge.cfg`（何况 CC 的 wget 拒绝覆盖已存在文件，改文件更麻烦）。

---

## 4. 冒烟测试（按顺序，逐项确认）

在看板或 CLI 里依次下发：

| # | 指令 | 期望结果 |
|---|---|---|
| 1 | `status` | 回报 `peripherals` 列表、`facing`、`dry_run` |
| 2 | `scan radius=6` | 返回 `by_name` 方块计数表（**能看到模组方块 ID**）|
| 3 | `players` | 返回在线玩家 |
| 4 | `say text=hello` | 游戏内聊天出现 hello |
| 5 | `block_info` | 返回所贴方块的 name/state/nbt |

第 1–5 项都通过后，**关闭 dry_run**：

```
edit bridge.cfg      # 把 dry_run=true 改成 false
```
然后重启程序（`Ctrl+T` 终止，重新 `agent_bridge.lua`）。

---

## 5. 海龟集群（可选）

1. 每只海龟插 **Wireless Modem**（与主计算机**同频道**）
2. 在海龟上：

```
wget run http://127.0.0.1:8765/files/turtle_worker.lua
```

3. 记下海龟的 **rednet id**（worker 启动时会打印 `id=...`）
4. 主计算机校准朝向（海龟无法自读朝向，必须校准一次）：

```
GET /api/push?who=mine1&cmd=calibrate&facing=north
```

5. 带 `target` 参数即可把指令转发给某只海龟：

```
GET /api/push?who=mine1&cmd=tunnel&target=7&dir=north&length=8
```

---

## 6. 指令速查

### 基础
`status` · `sleep ms=500` · `say text=...` · `chat_read` · `players [radius=16]`
`scan radius=8` · `block_info` · `inv_list` · `select slot=1` · `refuel n=1`
`peripheral_api [name=...]` · `geo_status`

### 定位与导航（需要 4 台 GPS 主机）
`locate [target=<海龟id>] [samples=3]` —— 绝对坐标（多次采样取中位数）
`player_pos [name=...]` —— 玩家绝对坐标
`discover_turtles [wait=3]` —— 广播发现海龟，**一次带回每只的 id/燃料/朝向/坐标**

`goto target=<id> x= y= z= [max_steps=40] [allow_dig=0] [require_ground=0]`
—— 走到目标**方块**：每步重新定位（3 次采样）、按方块判定抵达、
连续 3 步没靠近就停并回报"卡在哪/朝向是什么"；默认**不挖**、**可悬空**（海龟不受重力）
`calibrate_auto target=<id>` —— 用 GPS 位移自动测定朝向（worker 启动时也会自动做一次）

### 海龟移动与作业
`forward n=1` · `back` · `up` · `down` · `turn_left` · `turn_right`
`dig` · `dig_up` · `dig_down` · `place` · `place_up` · `place_down`
`attack` · `drop` · `suck` · `suck_up` · `suck_down`

### 高层
`go_relative dx=3 dz=-2 dy=0` · `tunnel dir=north length=8` · `mine_column depth=6`
`calibrate facing=north`

### 转发到海龟
任意指令加 `target=<rednet_id>`：
`tunnel target=7 dir=north length=8`

---

## 7. 常见问题

| 现象 | 原因与处理 |
|---|---|
| **`No such program: run`** | 命令名写错。CC 的 ROM 里**没有 `run` 程序**，必须写 **`wget run <url>`**（已核对 CC:Tweaked 1.115.1 的 `rom/programs/`，只有 `http/wget.lua`） |
| `No such program: wget` | 计算机不是 Advanced Computer（普通 Computer 也有 wget；若真没有，说明 `http` API 被关掉了） |
| `wget requires the http API...` | `computercraft-server.toml` 里 `[http] enabled` 为 false |
| `http.get 失败` | `computercraft-server.toml` 未放行 `$private`，或没重启服务端 |
| `attempt to perform arithmetic on a string value` 等 Lua 报错 | 脚本里有 bug：**把报错原文发给 Agent**，并跑 `py tools/lua_lint.py cc-tweaked/agent_bridge.lua`（本机无 lua 解释器，靠 lint + 游戏内实跑验证） |
| 程序跑起来后屏幕出现 `⚠ 本轮异常（已忽略，继续运行）` | 这是**预期内的容错**：某一轮出错不会终止程序，Agent 会同时收到 `event=error` 上报；把屏幕文字发给 Agent 即可 |
| 指令一直 `idle` | `bridge.cfg` 里的 `who` 与下发时用的 `who` 不一致 |
| 放了方块没反应 | `dry_run` 还是 `true`（注意：只读指令不受它限制） |
| `scan` 报"缺少 Geo Scanner" | 外设没贴在计算机相邻面，或版本 API 名不同（程序会自动试多个名字，仍失败请贴到相邻面重试） |
| 海龟不动 | 燃料不足（`refuel`）、红石未开启（`turtle.forward` 被禁用）、或朝向未校准 |
| 海龟无响应 | 主计算机与海龟不在同一维度／频道不同／modem 没 `open` |
| 指令堆积 | 看板看队列长度；`MAX_QUEUE=256` 会丢最旧的，属预期保护 |
| **你切到浏览器后游戏"没反应"** | 单人游戏默认会在**失去焦点时暂停整个世界**（日志特征 `Saving and pausing game...`），此时计算机也不执行指令。按 **`F3 + P`** 关闭该行为（1.20.1 没有菜单项） |

---

## 8. 明确的能力边界（别期待它做这些）

- ❌ **不是玩家**：模组不会把它当玩家，触发不了"玩家使用物品"的模组逻辑
- ❌ **点不了模组 GUI**：GUI 是客户端渲染的
- ❌ 不能跨维度
- ✅ 适合：挖矿、伐木、平整、建材、**库存分类**、值守汇报、地形测绘
- 想做"跟玩家一起玩模组内容"的助手 → 走 **方案 A（服务端假玩家）** 或 **方案 B（真实客户端）**

---

## 9. 这套东西与既有经验的关系

本目录的 `../docs/lessons-learned.md` 里，**"分类箱子"那几条教训直接适用**：

- 分类箱之间**留 1 格间隔**（相邻会合并成大箱子）
- 整叠搬运用 **shift 点击**语义
- **不要相信"完成"回报**，一律用独立清点验收

把这套 CC 方案当成"更听话的手"，把纪律当成"不出错的大脑"。
