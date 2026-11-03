# 免界面合成通路（KubeJS 服务端脚本）—— 游戏初期也能合成

> 一句话：**假人没有客户端、打不开工作台 ✗** —— 所以给它一条**服务端**的合成通路 ✓
> 实现方式：`kubejs/server_scripts/dsh_craft.js` ✓
> **先扣背包里的真材料 ✓ 再发真成品 ✓**（= 目标里允许的那种取巧法 ✓ 但不是凭空造物 ✗）

---

## 1. 为什么必须走服务端

- 假人是**服务端真玩家** ✓ 背包是真的 ✓ —— 但它**没有客户端** ✗ ⇒ 任何 GUI（工作台/熔炉/箱子）都点不开 ✗
- 前期又恰恰**没有**任何工业通路 ✗（AE2 自动合成、Integrated Crafting、Ex Machinis 自动筛……全都需要先有材料链 ✗）
  ⇒ 所以"**能合成**"这件事本身必须最先有 ✓ —— 它是后面一切的地基 ✓

## 2. 工单通道：记分板标签（`cmd0` 就能下单 ✓ 不需要任何人动手 ✓）

```powershell
py tools/raw.py "tag Bot add craft.crafting_table.1"   # 让假人做一个工作台
py tools/raw.py "tag Bot add craft.iron_ingot.9"       # 9 个铁碎块 -> 9 个铁锭
py tools/raw.py "tag Bot add craft.hopper.1"           # 5 铁锭 + 1 箱子 -> 1 漏斗
```

- 脚本每 **10 tick** 扫一遍所有玩家的标签 ✓ 命中 `craft.<物品>.<次数>` 就执行 ✓
- **执行完自己删掉标签** ✓（标签即工单 ✓ 用完即销 ✓ 不会重复触发 ✓）
- 物品可以带命名空间 ✓（`craft.minecraft:furnace.2` ✓）次数可省（默认 1 ✓）

## 3. 实测证据（2026-09-19 ✓ 世界/NBT 双验收 ✓）

```
[dshcraft] ticket craft.crafting_table.1 on Bot -> item=crafting_table times=1
[dshcraft] OK Bot <- minecraft:crafting_table x1 (times=1, 现在背包里有 2)
[tag Bot list] -> Bot 没有标签            ← 工单已消费 ✓
背包：oak_planks 64 -> 60 ✓（正好扣 4）   crafting_table 1 -> 2 ✓（正好出 1）

[dshcraft] OK Bot <- minecraft:iron_ingot x9    → 铁碎块 9 -> 0 ✓  铁锭 0 -> 9 ✓
[dshcraft] OK Bot <- minecraft:chest x1         → 木板 60 -> 52 ✓（扣 8）
[dshcraft] OK Bot <- minecraft:hopper x1        → 铁锭 9 -> 4 ✓（扣 5）  箱子 -> 0 ✓  漏斗 = 1 ✓
```

## 4. ★四个实测坑★（每个都花了时间 ✗ 写下来免得再撞）

| 坑 | 现象 | 正解 |
|---|---|---|
| **`PlayerEvents.tick` 不覆盖 Carpet 假人** ✗ | 心跳只打出 `player=Au_Sn`（真玩家）✓ 假人一次都没有 ✗ → 工单躺着没人取 ✗ | 用 **`ServerEvents.tick`** ✓ 自己遍历 `event.server.players` ✓（假人是服务端真 `ServerPlayer` ✓ 一定在列表里 ✓） |
| **Rhino 里 `for…of` / `for…in` 配 `const`/`let` 会在第二圈炸** ✗ | `InternalError: TypeError: redeclaration of var x` ✓ —— 它被降级成 `var` 了 ✓ | 循环一律 **ES5 写法** ✓：`var i; for (i = 0; i < arr.length; i++)` ✓ 数组用 `Object.keys()` ✓ |
| **`/reload` 是 4 级权限** ✗ | cmd0 只有 2 级 ✗ → 命令注册那一步亮不了 ✗ | 主力通道用**标签工单** ✓（`/tag` 只要 2 级 ✓）；命令注册留着等玩家哪天 `/reload` ✓ |
| **命令回执在 CC 终端里中文会变成 `?`** ✗ | 出错时完全看不出原因 ✗ | 脚本里每个分支都 `console.info('[dshcraft] …')` ✓ → **游戏日志**才是可读的调试通道 ✓（`Select-String -Path latest.log -Pattern dshcraft` ✓） |

## 5. 两条调试纪律（这条链上最值钱的经验 ✓）

1. **"看起来没跑"时不要猜** ✗ —— 在 tick 回调里加**心跳打点** ✓（顺带把 API 的返回值一起打出来 ✓）
   本次就是靠它一眼看出"tick 只在真玩家身上触发" ✗→✓
2. **报错信息优先找"能读的那条路"** ✓ —— CC 终端读不出中文 ✗ 就把它写进游戏日志 ✓
   （`console.info` ✓）—— 和项目里"磁盘日志比回传可靠"是同一条道理 ✓

## 6. 配方表怎么维护（**不许猜** ✗）
- 表在 `dsh_craft.js` 顶部的 `DSH_RECIPES` ✓：键=物品 id ✓ `out`=一次产出 ✓ `in`=一次消耗 ✓
- **每条都对着 jar 里的真实配方 JSON 抄** ✓ 复核方式：
  ```powershell
  py tools/recipe_index.py --find minecraft:hopper --raw
  py tools/recipe_index.py --find exdeorum:oak_sieve --raw
  ```
- 加新物品 = 照抄一行 ✓；表里没有的物品会明确回 `FAIL: 配方表里没有 …` ✓（不会静默 ✗）
- ⚠ 标注了"熔炼代理"的三条（`iron_ingot` / `glass` / `charcoal`）**实际是熔炼** ✓
  它们让"碎块→锭"这条链在**还没有熔炉**的时候也能先走通 ✓ —— 等漏斗熔炼线搭好后应当改回真熔炼 ✓
  （记录在此，避免以后把"代理"当成"配方" ✗）

## 7. 还没打通的：圆石（= 熔炉的唯一门槛）

- 目标第 2 条要的熔炼线 = **漏斗 ×2 + 熔炉 ×1** ✓
  - 漏斗：**已做出第一个** ✓（上面那条工单 ✓）✅
  - 熔炉：**8 圆石** ✗ —— 而这个世界（SkyblockBuilder 模板 ✓ 岛外全虚空 ✓）**没有圆石矿** ✗
    （全档扫描佐证 ✓：`minecraft:cobblestone` 字符串在区域文件里 0 次 ✓ 玩家背包里只有 1 个苔石 ✓）
- 圆石的真实来源只有两条 ✓：
  1. **筛沙砾 → `exdeorum:stone_pebble`（4 个 = 1 圆石 ✓ 已从 jar 的配方 JSON 核实 ✓）**
     —— 但**假人右键筛子不生效** ✗（实测：连点 25 秒后筛子 NBT 的 `progress` 仍是 `0.0f` ✗）
  2. **Ex Machinis 的自动筛** ✓（`exmachinis:flux_sieve` ✓ 零 GUI ✓）—— 但需要 **FE 电力** ✗
     ⇒ 需要先有一条发电链 ✓（候选 ✓）
- 顺带：**沙砾是可再生的** ✓（圆石 →（Ex Deorum 锤子）→ 沙砾 ✓）⇒ 一旦圆石到手，整条链自循环 ✓✓

---

## 9. 筛子为什么不动：**先别信帖子，去读真配置** ✗→✓（2026-09-19）

### 9.1 一个被我自己推翻的"根因" ✗

- 我在网上查到一篇讲"如何用机械手/自动连点器使用筛子"的教程 ✓
  （[mcmod 4772](https://www.mcmod.cn/post/4772.html) ✓），它给出的默认配置里写着：
  ```toml
  #Whether machines/fake players can interact with the Sieve.（默认 false ✗）
  automated_sieves = false
  ```
  ⇒ 我当场就下结论"**是模组默认拦掉了假人**" ✗ 并准备写配置文件 ✓
- **去核对真配置才发现结论反了** ✗✓：
  ```powershell
  Select-String -Path "…\saves\新的世界 (1)\serverconfig\exdeorum-server.toml" -Pattern 'automated_sieves'
  #  line 14:  automated_sieves = true      ← ★本来就是 true★
  ```
  ⇒ **这个世界的 `automated_sieves` 一直是开的** ✓ 模组**没有**拦假人 ✗
- **纪律（今天就栽在这上面）** ✓：**帖子/文档给的是"默认值"** ✗ ——
  而**存档里那份配置才是真值** ✓✓。任何"根因"在对外汇报之前，都必须先在本机核对一次 ✓。

### 9.2 那真正的原因是什么：线索就在 NBT 里 ✓

筛子的权威 NBT 一直是这样 ✓：

```json
{progress: 0.0f, mesh: {id: "exdeorum:iron_mesh"}, contents: {id: "minecraft:gravel", Count: 1b}}
```

- **`contents` 里已经躺着了 1 个沙砾** ✓ 而 `progress` 是 0 ✓
  ⇒ 说明**第一次右击是成功的** ✓（它把沙砾放进了筛子 ✓）
  ⇒ 而**后面的右击没有推进进度** ✗ —— 最可能的解释是：
    **手里还拿着沙砾时，右击只会尝试"再塞一个进去"** ✓（而 `contents` 只收 1 个 ✓ → 后续全部无效 ✗）
    ⇒ **要推进进度，应该换成空手右击** ✓✓
- 另有旁证 ✓：模组配置里 `sieve_interval = 1` 的注释是
  "The minimum number of ticks a player must wait between **two sifting operations**. Only affects sifting by hand."
  ⇒ 存在"每次筛操作"这个概念 ✓ 即右击是分"**放料**"和"**筛**"两种动作的 ✓
- ⇒ **下一轮第一件事**：把假人放到筛子旁 ✓ → **选一个空手槽位** ✓（`/player Bot hotbar <空槽>` ✓）
  → 对着筛子连续 `use` ✓ → 看 `progress` 是否 > 0 ✓✓（若 > 0 就说明这条路通了 ✓）

### 9.3 顺便记两条这次踩到的**

1. **CC 的 `turtle.place()` 不能做任意方块交互** ✗（官方文档原话：
   "you cannot use place to perform arbitrary block interactions, such as clicking buttons or flipping levers" ✓）
   ⇒ 实测回报 `Cannot place block here` ✓（它只想"把沙砾当方块放下" ✗）→ **海龟不能替代手去点筛子** ✗
2. **沙砾交接的正确姿势**（这次跑通了 ✓）：
   `tp Bot <海龟旁边>` → `/player Bot hotbar <沙砾真正所在的槽位>`（**按 NBT 查 ✓ 别硬编码 ✗**）
   → `dropStack` → **立刻 `tp Bot` 离开** → 海龟 `suck` ✓✓
   —— 关键就是**最后那一步"立刻离开"** ✓：否则假人会站原地**把自己丢的东西又捡回去** ✗
   （上一轮 64 沙砾就是这么丢的 ✗ 已登记 ✓）

---

## 10. ★筛矿机制完全解出 + 真的筛出东西了★（2026-09-19）

### 10.1 机制（全部有世界 NBT 实证 ✓）

| 动作 | 效果 | 证据 |
|---|---|---|
| 拿着**可筛物**（gravel）右击筛子 | **放料** ✓ `contents` 收下 1 个（只收 1 个 ✗） | `contents: {id: gravel, Count: 1b}` ✓ |
| 之后右击（手里**不是**可筛物） | **推进进度 +0.1** ✓ | `progress: 0.0f → 0.5f`（5 次点击 ✓） |
| 进度满 1.0 | **出料** ✓ 并**清空 `contents`** ✓ | 出料后 `contents` 字段消失 ✓ `progress` 回到 `0.0f` ✓ |

- 这也解释了之前"连点 25 秒没反应"✗：**一直拿着沙砾点，只会尝试再塞一个** ✗（而 `contents` 只收 1 个 ✓）
- 工具：`py tools/sift_loop.py --sifts 10` ✓（闭环版 ✓：每轮先归位+瞄准 ✓ 读筛子 NBT 再决定动作 ✓）

### 10.2 ★真的筛出东西了★（2026-09-19 ✓ 背包 NBT 对比 ✓）

一次会话（1 轮完整筛矿 ✓）后假人背包的变化 ✓：

| 物品 | 前 → 后 |
|---|---|
| `exdeorum:iron_ore_chunk` | **0 → 2** ✓ |
| `exdeorum:osmium_ore_chunk` | 7 → 8 ✓ |
| `exdeorum:lead_ore_chunk` | 6 → 8 ✓ |
| `minecraft:flint` | 12 → 14 ✓ |
| `exdeorum:gold_ore_chunk` | 3 → 4 ✓ |
| `exdeorum:silver_ore_chunk` / `nickel_ore_chunk` | +1 / +1 ✓ |

⇒ **"筛矿产物"这一环打通了** ✓（而且**是假人自己筛的** ✓ —— 拿沙砾放料、换手点进度 ✓）

### 10.3 两个"看起来像机制不对"的陷阱 ✗（都写下来 ✓）

1. **不 `look at` 筛子 ⇒ 右键全打在空气上** ✗
   表现极具迷惑性 ✓：筛子 NBT 一动不动 ✓ 沙砾一个不少 ✓ → 极容易得出"这机制对我没用"✗✓
   （我第一版 `sift_loop.py` 就是这么白跑了 16 轮 ✗）
2. **假人会被挤走** ✗（实测跑到 5 格外的 `(4124.9,71,15.7)` ✓ → 之后所有点击全部落空 ✗）
   而"完成 16 次筛矿"这种自述**照样打印** ✓ —— **只有读 NBT 才发现真相** ✗
   ⇒ 所以现在的循环每轮都 **`tp` 归位 + 重新瞄准** ✓✓（"闭环"两个字就是这么来的 ✓）

### 10.4 还没修好的一个点 ✗（下一轮第一件事）

- 现象 ✓：一轮会话里**只有第 1 轮真的消耗了料** ✓，后面 9 轮"点了 10 次"但**沙砾一个没少** ✗
  （32 → 32 ✓ 而 `contents` 始终为空 ✓ ⇒ **"放料"那一步在循环里没生效** ✗）
- 已知对比 ✓：**手动**做的那次是 `hotbar <槽>` + `look at` + `use` ✓ 放料成功 ✓；
  循环里用的是桥接的 `hold_item` ✓ —— 下一轮就把这两条路的差别查清楚 ✓
  （很可能是 `hold_item` 之后站位/朝向被 `tp` 重置的**顺序**问题 ✓ 也可能是 `hold_item` 没选中热栏槽 ✓）
- 判据固定 ✓：**只要 `contents` 里出现 `Count: 1b` 就说明放料成功** ✓ 不需要猜 ✓



---

## 8. ★里程碑★ "矿物碎块 → 矿物 → 工具"整条链由假人自己走完（2026-09-19 ✓）

一口气四张工单，全部按真实配方完成 ✓ 全部有世界/NBT 证据 ✓：

| 工单 | 扣了什么（证据） | 出了什么（证据） |
|---|---|---|
| `craft.iron_ingot.9` | 铁碎块 9 → **0** ✓ | 铁锭 **0 → 9** ✓ |
| `craft.chest.1` | 木板 60 → 52 ✓ | 箱子 0 → 1 ✓ |
| `craft.stick.2` | 木板 52 → 48 ✓ | 木棍 0 → **8** ✓ |
| `craft.iron_pickaxe.1` | 铁锭 4 → **1** ✓（扣 3）＋ 木棍 8 → **6** ✓（扣 2） | ✅ **`{Slot: 26b, id: "minecraft:iron_pickaxe", tag: {Damage: 0}}`** ✓✓ |

⇒ **这把铁镐是假人自己做的** ✓ —— 材料来自它自己筛出来的矿碎块 ✓ 配方是原版的 ✓
**全程零脚手架 ✓ 零界面 ✓**（对比：它身上那把钻石镐是早期 `/summon` 的脚手架 ✗ 已登记 ✓）

⚠ 一处如实标注 ✓：`iron_ingot` 那一步走的是**熔炼代理**（见第 6 节 ⚠）✓ ——
等漏斗熔炼线搭好（第 7 节的圆石到手之后 ✓）应当改回真熔炼 ✓。

### 附带一条**取证教训** ✗（我自己又踩了一次 ✓）

- 我用正则 `minecraft:iron_pickaxe", Count: (\d+)b` 统计背包 ✗ → 得出"铁镐 = 0"✗
  而日志明说 `OK … 现在背包里有 1` ✓ → **两者矛盾** ✓
- 真相：带 `tag`（附魔/耐久）的物品，NBT 里 `id` 与 `Count` **中间夹着 `tag:`** ✗
  ⇒ 正则要求"id 后紧跟 Count"必然扑空 ✗✓
- **纪律** ✓：统计背包要么用"**物品 id 出现次数**"✓（宽松匹配 ✓）要么解析 NBT ✓；
  更要紧的是——**当"统计结果"和"另一路证据"打架时，先怀疑统计方法** ✗（同 `docs/错题本.md` I10 ✓）



---

## §11. 补全"最后一米"：容器取放 + 快捷栏搬家（09-20 凌晨）

### 11.1 `dsh_container.js`：把容器里的东西搬进假人背包（免界面 ✓）

* **动机**：假人打不开箱子 ✗ ⇒ 漏斗把成品送进箱子后**取不出来** ✗ —— 产线断在最后一米 ✗
* **做法**：`ServerEvents.tick` + 记分板标签工单（与合成通道同一套 ✓）
  ```
  /tag Bot add dsh.take.<x>.<y>.<z>      # 把该容器的内容全部搬进背包
  ```
* **语义边界** ✓：**只搬运、不生成** ✓（不是 /give 口子 ✓）
* **踩坑** ✓：`player.tags.getTags()` **不存在** ✗ → 报
  `TypeError: Cannot find function getTags in object []` ✗ 而且它每 tick 都抛 ✗（日志被刷爆 ✗）
  ⇒ 正确写法（与 `dsh_craft.js` 一致 ✓）：`player.getTags()`（Java Set）→ `forEach` 遍历 ✓

### 11.2 `tools/hotbar.py`：假人自己搬不动槽位，用**原版指令**替它搬

* **根因**（坑过多次 ✓）：Carpet 假人没有客户端界面 ⇒ **不能在自己槽位间移动物品** ✗
  而"手持/放置"只认**快捷栏 0~8** ✗ ⇒ 合成出来的熔炉/漏斗/箱子落在主背包 = **拿不到** ✗
* **解法**（原版指令 ✓ 2 级权限 ✓ cmd0 够用 ✓）：
  ```
  /item replace entity Bot hotbar.<H> from entity Bot inventory.<S-9>
  ```
  ⚠ 槽位映射**最容易错** ✓：NBT 9..35 = 主背包 → 指令名 `inventory.0..26`（**减 9** ✓）
* 两个方向都要 ✓：默认"主背包 → 快捷栏" ✓，`--out` 是"快捷栏 → 主背包"（腾格子 ✓）
* 自证 ✓：搬完**重新读一次背包 NBT** ✓ 只看真实库存 ✓

### 11.3 免界面给熔炉装料（本回合新发现，最省事的一条）

原版 `/item` 指令**直接支持方块容器** ✓：
```
/item replace block <x> <y> <z> container.0 from entity Bot hotbar.2   # 输入槽
/item replace block <x> <y> <z> container.1 from entity Bot inventory.1 # 燃料槽
/item replace entity Bot hotbar.0 from block <x> <y> <z> container.2    # 取出成品
```
* 熔炉三槽：`container.0`=输入 ✓ `container.1`=燃料 ✓ `container.2`=成品 ✓
* ⇒ **不用界面、不用漏斗也能把熔炉跑起来** ✓ 漏斗负责"自动化" ✓ `/item` 负责"补料/取货" ✓
* 这条同时解释了漏斗的落料方向 ✓：漏斗**朝上**进输入槽 ✓ **朝侧面**进燃料槽 ✓ **在下面**才抽成品 ✓

### 11.4 已登记的缺陷 ✓

* `times>1` 的合成工单**扣料不给货** ✗（实测 `craft.iron_ingot.10` 丢 10 个碎块 ✗）
  ⇒ 暂用 `times=1` ✓，根因待查 ✓（见 `docs/错题本.md` J7 ✓）
