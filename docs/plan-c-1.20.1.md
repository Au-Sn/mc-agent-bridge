# 方案 C 设计文档 — CC:Tweaked + Advanced Peripherals（Minecraft 1.20.1 / Forge）

> 目标：在一个 **Forge 1.20.1 整合包**里，放一个**由外部 Agent 通过 API 驱动的在场执行体**。
> 约束：不能依赖原版协议 bot（Forge 会拒绝），也不强制多开一个真实客户端。

---

## 1. 一句话方案

用游戏内 **Computer（计算机）+ 外设 + 海龟** 当"手和眼"，用 **HTTP** 把它的感知与动作暴露给外部 Agent。
因为它是**服务端方块实体**，所以**天然绕过 Forge 的客户端模组校验**。

### 为什么选这条路

| 优势 | 说明 |
|---|---|
| 不受加载器限制 | CC:Tweaked 有 Forge / NeoForge / Fabric 三版，1.20.1 稳定可用 |
| 绕过 Forge 客户端校验 | 它不是客户端 → 不会收到 "mods that require Forge to be installed on the client" |
| **感知天然模组友好** | Geo Scanner 返回**方块 ID**（含模组方块）；Block Reader 直接读 **NBT/方块状态** |
| 有天然网络出口 | CC 的 `http` API 可主动访问网关 → Agent 进得来，不用端口穿透到游戏里 |
| 可扩展成"集群" | 无线调制解调器 + 多只海龟 = 一支机器人工队 |

### 相比方案 A / B 的取舍

| | 方案 C（本方案） | 方案 A（服务端假玩家） | 方案 B（真实客户端） |
|---|---|---|---|
| 模组"当它是玩家" | ❌ | ✅ | ✅ |
| 能点模组 GUI | ❌ | ❌ | ✅ |
| 能读模组方块/NBT | ✅ | ✅ | ✅ |
| 需要额外客户端 | ❌ | ❌ | ✅（多开一个） |
| 需要写 Java | ❌ | ✅ | ✅ |
| 上手速度 | **最快** | 中 | 慢 |

**结论**：C 是**最快跑通"Minecraft × Agent"闭环**的一条，先用它验证 Agent 的规划能力，
再用 A/B 补齐"真玩家身份"。

---

## 2. 系统拓扑

```
┌──────────────┐   HTTP    ┌──────────────────┐   HTTP    ┌───────────────────────────┐
│   Agent      │ ────────► │     Gateway      │ ◄──────── │  CC 计算机（游戏内）        │
│ (LLM / 脚本) │ ◄──────── │ (agent_gateway.py)│ ────────► │   ├ Chat Box        (说话) │
└──────────────┘           │  指令队列/状态/日志 │           │   ├ Geo Scanner     (扫方块)│
                           └──────────────────┘           │   ├ Block Reader    (读NBT) │
                                                          │   ├ Player Detector (玩家)  │
                                                          │   ├ Inventory Mgr   (库存)  │
                                                          │   └ Wireless Modem ──┐      │
                                                          └──────────────────────┼──────┘
                                                                                 │ 无线
                                                          ┌──────────────────────┴──────┐
                                                          │ 海龟群 Turtle ×N（挖/放/攻击）│
                                                          └─────────────────────────────┘
```

**数据流**

1. Agent 把指令写入 Gateway（`POST /api/command` 或 GET 形式的 `/api/push`）
2. 计算机每 tick 轮询 `GET /api/next?who=mine1` 取一条指令
3. 计算机执行（本地动作或通过无线转发给海龟）
4. 计算机把结果 `POST /api/state` 回报
5. Agent 读 `GET /api/state?who=mine1` 拿最新感知

---

## 3. 所需模组与方块（1.20.1）

### 模组

| 模组 | 加载器 | 作用 |
|---|---|---|
| **CC:Tweaked** | Forge 1.20.1 | 计算机 / 海龟 / 外设 / http API |
| **Advanced Peripherals** | Forge 1.20.1 | Chat Box、Geo Scanner、Block Reader、Player Detector、Inventory Manager、ME/RS Bridge |

> 版本请对齐：CC:Tweaked 与 Advanced Peripherals 的 **1.20.1 Forge** 分支都需与你的 Forge 版本匹配。

### 方块清单（最少配置）

| 方块 | 数量 | 用途 |
|---|---|---|
| Advanced Computer（高级计算机） | 1 | 主控，跑 `agent_bridge.lua` |
| Wireless Modem（无线调制解调器） | N+1 | 计算机 1 个 + 每只海龟 1 个，**同一频道** |
| Turtle（海龟，建议 Advanced） | N | 挖 / 放 / 攻击的执行体 |
| Chat Box | 1 | 与玩家/聊天交互 |
| Geo Scanner | 1 | 半径扫方块（**含模组方块**） |
| Block Reader | 1 | 读单个方块的 NBT / 状态（机器状态） |
| Player Detector | 1 | 玩家列表与坐标 |
| Inventory Manager | 1 | 贴箱子，做库存读写（**分类整理就靠它**） |

> 外设必须**贴在计算机相邻面上**（或用有线/无线网络桥接）。

---

## 4. 接口设计（Gateway ↔ 游戏）

### 4.1 Agent → 游戏（下发指令）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/command` | **推荐**。JSON body：`{"who":"mine1","cmd":"forward","args":{}}` |
| GET | `/api/push?who=mine1&cmd=forward&k=v` | **GET 友好形式**，便于只有 GET 能力的 Agent 使用 |

**指令语义**：队列语义。`/api/next` 取走一条即出队；指令带 `id`，结果按 `id` 回传。

### 4.2 游戏 → Agent（回报状态）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/state` | 回报执行结果与感知快照 |
| GET | `/api/state?who=mine1` | Agent 读取最新状态 |
| GET | `/api/log?n=50` | 最近事件日志（审计用） |

### 4.3 文件分发（部署用）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/files/<name>` | 把 `cc-tweaked/` 下的脚本发给游戏内计算机 |

游戏内一键安装：

```
wget run http://<gateway-host>:8765/files/agent_bridge.lua
```

### 4.4 指令表（`agent_bridge.lua` 支持）

**基础（所有机型）**

| cmd | 参数 | 说明 |
|---|---|---|
| `status` | — | 回报位置、朝向、燃料、外设列表 |
| `sleep` | `ms` | 等待（限流用） |
| `say` | `text` | 通过 Chat Box 发话 |
| `chat_read` | — | 读取最近聊天 |
| `players` | `radius` | Player Detector 列玩家 |
| `scan` | `radius` | Geo Scanner 扫方块（**返回模组方块 ID**） |
| `block_info` | `side` 或 `x,y,z` | Block Reader 读 NBT/状态 |
| `inv_list` | — | 列出自身 16 格 |
| `select` | `slot` | 选中槽位 1–16 |
| `equip_left` / `equip_right` | — | 装备/卸载左右手（Advanced Turtle） |

**海龟移动与作业**

| cmd | 参数 | 说明 |
|---|---|---|
| `forward` / `back` / `up` / `down` | `n`（默认 1） | 移动，遇障自动尝试开挖 |
| `turn_left` / `turn_right` | — | 转向 |
| `dig` / `dig_up` / `dig_down` | — | 挖掘 |
| `place` / `place_up` / `place_down` | — | 放置 |
| `attack` / `attack_up` / `attack_down` | — | 攻击 |
| `drop` / `drop_up` / `drop_down` | — | 丢弃 |
| `suck` / `suck_up` / `suck_down` | — | 吸取掉落物 |
| `refuel` | `n` | 补充燃料 |
| `goto` | `x,y,z` | **高层**：简化三维寻路（直线 + 破障 + 爬升），带步数上限 |
| `tunnel` | `dir,length` | **高层**：挖一条水平隧道 |
| `mine_column` | `depth` | **高层**：向下挖一柱（采矿） |

> `goto` 是**简化实现**（不是 Baritone 级 A*），设计目标是"短距可靠"，长距离请拆成多个航点。
> 后续如需强寻路，再接方案 B 的 Baritone。

---

## 5. 能力边界（提前知道，避免踩空）

| 能做 | 不能做 |
|---|---|
| ✅ 挖方块、放方块、攻击实体 | ❌ **不是玩家**：模组不会把它当玩家，触发不了"玩家使用物品"的模组逻辑 |
| ✅ 读方块 ID（含模组方块）、读 NBT/方块状态 | ❌ **不能点模组 GUI**：GUI 是客户端渲染的，服务端方块实体点不了 |
| ✅ 读写相邻箱子 / ME / RS 网络库存 | ❌ 不能"装备被模组识别的工具并获得属性加成"（部分可用左右手绕过） |
| ✅ 在聊天里收发消息 | ❌ 不能进入/跟随玩家（会移动，但需要你写路径或跟点名） |
| ✅ 组网多只海龟并行作业 | ❌ 不能跨维度（除非配 chunk loader 且走传送门逻辑，需另行设计） |

**因此**：C 适合"**资源与建造类助手**"（挖矿、伐木、平整、建材、库存分类、值守汇报），
不适合"**玩法类助手**"（跟玩家一起打模组 Boss、用模组机器做流水线）。
后者的正解是方案 A / B。

---

## 6. 部署步骤（1.20.1 逐步）

### 步骤 1：服务端模组

1. 把 **CC:Tweaked(Forge 1.20.1)** 与 **Advanced Peripherals(Forge 1.20.1)** 放进 `mods/`
2. 起服，确认日志无缺失依赖

### 步骤 2：放行 HTTP 访问

编辑服务端配置 `config/computercraft-server.toml`。
CC:Tweaked 默认**会阻止访问私有网段**，需要显式放行你的网关地址：

```toml
[http]
    enabled = true

[[http.rules]]
    # 允许访问本机/内网（网关就跑在这台机器上）
    host = "$private"
    action = "allow"

[[http.rules]]
    host = "*"
    action = "deny"
```

> `$private` 是 CC:Tweaked 的伪域名，代表私有网段（127.0.0.0/8、10.0.0.0/8、
> 192.168.0.0/16、172.16.0.0/12、fc00::/7）。
> 改完**重启服务端**生效。

### 步骤 3：启动网关

```bash
python gateway/agent_gateway.py --port 8765 --root cc-tweaked
```

浏览器访问 `http://127.0.0.1:8765/` 应看到看板。

### 步骤 4：游戏内布置

1. 放下 **Advanced Computer**，旁边贴 **Chat Box / Geo Scanner / Block Reader / Player Detector / Inventory Manager**
2. 计算机与海龟各插 **Wireless Modem**，用 `modem.open(1)` 同一频道
3. 在计算机上：

```
wget run http://<网关IP>:8765/files/agent_bridge.lua
```

程序会自动：
- 生成 `bridge.cfg`（默认 `who=mine1`、网关地址）
- 进入主循环：轮询 → 执行 → 回报

> 首次运行建议先把 `bridge.cfg` 里的 `dry_run = true` 打开，确认指令通路后再关闭。

### 步骤 5：冒烟测试（按顺序）

| 测试 | 指令 | 期望 |
|---|---|---|
| 1 通路 | `status` | 回报位置/朝向/外设列表 |
| 2 感知 | `scan&radius=6` | 返回方块列表，**能看到模组方块 ID** |
| 3 执行 | `forward` | 海龟移动一格 |
| 4 库存 | `inv_list` | 列出 16 格 |
| 5 交互 | `say&text=hello` | 游戏内聊天出现 hello |
| 6 高层 | `tunnel&dir=north&length=5` | 挖出一条 5 格隧道 |

---

## 7. 与方案 A / B 的衔接

- **协议复用**：本方案的指令表（第 4.4 节）刻意设计成"加载器无关"。
  将来写**方案 A 的服务端假玩家模组**时，**同一套指令名和 JSON 结构可以直接复用**，
  Agent 侧代码零改动，只换掉"执行体"。
- **感知升级**：方案 A 可以直接读服务端世界模型（比 Geo Scanner 半径扫描更完整）。
- **需要真玩家身份 / GUI 操作**时，切方案 B。

---

## 8. 后续可加的能力（按价值排序）

1. **库存分类自动化**：Inventory Manager + 规则表（本项目之前的教训：分类要留 1 格间隔，否则会合并成大箱子）
2. **多海龟编队**：`tunnel` / `mine_column` 分发到多台并行
3. **任务级封装**：把"平整这块地""挖 24 个铁矿""把箱子按类别分"写成 Lua 宏，Agent 只说目标
4. **看板截图**：Geo Scanner 的扫描结果渲染成 ASCII 地图回传，让 Agent 有"视觉"
