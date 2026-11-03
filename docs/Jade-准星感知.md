# 准星感知（Jade 效果）—— 假人"正对着什么"

> 一句话：**给假人装上 Jade** ✓ —— 它现在能回答"我准星指着的这块是什么方块、挖它要用什么工具" ✓
> 而这件事**不需要 LLM 参与** ✓（游戏内的反射层每拍顺手就做了 ✓）。

---

## 1. 为什么必须补这一块

玩家有 **Jade**：准心一指 ✓ 方块名/属性/工具需求就显示出来 ✓。
假人**没有客户端** ✗ —— 它什么都看不见 ✗。

过去的做法是"人（或 LLM）先报坐标 ✓ 它再去读" ✓ —— 于是最基础的问题
**"我正前方是什么"反而答不上来** ✗。真实后果：

- 以为面前是木板、其实是泥土 ✗ → 挖错方块 ✓
- 少带一把工具就走过去 ✗ → 现场才发现挖不动 ✓
- **海龟挖矿卡了好几轮的根因就藏在这里** ✓（详见 `docs/错题本.md` H1 ✓：
  海龟用的是**升级槽里的工具** ✗ 而"我该用什么工具"当时**根本读不出来** ✗）

---

## 2. 它是什么（机制）

一次 `crosshair` 调用做的事（全部是**服务端真值** ✓ 不是渲染层猜的 ✗）：

1. 读假人的 `Pos` 与 `Rotation`（`data get entity <bot> Pos / Rotation` ✓ 只从方括号里取数字 ✓
   中文客户端把前缀全汉化了 ✓ 文案一概不可依赖 ✗）
2. 从**眼睛位置**（站立 1.62 ✓ 可用 `eye=` 覆盖 ✓）沿视线方向做
   **体素射线行进**（Amanatides & Woo ✓ 只在跨格子边界时前进一步 ✓）
   - 方向：`dx = -sin(yaw)·cos(pitch)` ✓ `dy = -sin(pitch)` ✓ `dz = cos(yaw)·cos(pitch)` ✓
     （yaw=0 → +Z ✓ yaw=90 → −X ✓ pitch 正 = 朝下 ✓ 这条**最容易记反** ✗）
3. 射线走到的**第一块非空气方块**就是"准星命中的方块" ✓ 同时给出：
   坐标 ✓ 距离 ✓ **入射面**（face ✓ = 玩家会点到的那一面 ✓）✓ 方块状态 ✓
4. **工具需求从方块自己的标签读** ✓（不是维护一张巨型名字表 ✗）：
   `minecraft:mineable/pickaxe|axe|shovel|hoe|shears` ✓ 以及
   `needs_stone_tool / needs_iron_tool / needs_diamond_tool` ✓
   —— 这正是原版判定"用什么工具、会不会掉东西"的依据 ✓
   （模组方块常常没有这些标签 ✗ → 退回**按名字猜** ✓ 并明确标注 `tool_from="guess"` ✓
     不和"读标签得到的结论"混为一谈 ✓）

### 缓存（只说一遍，因为它有安全含义）

一次射线要读十几格 ✓ 而反射层每拍都会重看同一片区域 ✓ → 没有缓存，"看一眼"就是几十条服务端指令 ✗。
所以射线读取走一个 **1.2 秒**的短缓存 ✓。

⚠ 但**放置/挖掘的验收绝不共享这个缓存** ✗ —— 验收必须读到"刚刚变化的世界" ✓，
缓存会让验收看到旧值 ✓ → 那正是最危险的**假阳性** ✗（所以 `block_state`/`sift` 一律走 `readBlock` 原路 ✓）。

---

## 3. 怎么用

```powershell
# ① Agent 视角：问一句"我现在看着什么"（只读 ✓ 装配/挖掘之前先问 ✓）
py agent/run.py do look_block
py agent/run.py do look_block reach=6 nbt=true raw=true

# ② 桥接动作（完整回传 ✓ 带 ray 逐格清单 ✓）
py tools/act.py crosshair raw=True
py tools/act.py crosshair nbt=True          # 附带方块实体数据（箱子/机器）
py tools/act.py crosshair yaw=0 pitch=-90   # 显式指定朝向（先算后看 / 测试）
py tools/act.py jade                        # 纯读 + 世界内 HUD 开关

# ③ 世界里打开/关闭真正的"Jade HUD"（一个原版 text_display 实体 ✓ 不需要资源包 ✓）
py tools/act.py jade hud=on
py tools/act.py jade hud=off
```

`A.status` 里也带了一份 `jade = { hud, last, updates }` ✓ → Agent 每一步都知道
"假人现在盯着什么"，**不必额外发一次指令** ✓。

### 返回长什么样

```json
{
  "eye": {"x": 4125.564, "y": 71.62, "z": 11.3},
  "rotation": {"yaw": -60.67, "pitch": 24.57},
  "hit": {"x": 4128, "y": 70, "z": 12, "name": "minecraft:oak_planks",
           "dist": 3.07, "face": "west", "fluid": false,
           "tool": "axe", "tool_from": "tags", "tier": null, "state": {}},
  "looking_at": "minecraft:oak_planks @ (4128,70,12) 距离 3.07 面 west",
  "cells_read": 9,
  "ray": ["4125,71,11=minecraft:air", "…"]
}
```

`cells_read` 是**这一拍真正发出去的读指令数** ✓（缓存命中的格子不计 ✓）—— 它是"感知有多贵"的度量 ✓。

---

## 4. 世界内的 HUD（"真·Jade"）

假人自己没有屏幕 ✗ 但**世界里可以有** ✓：

- 一个原版 `minecraft:text_display` 实体 ✓（`see_through=1b` ✓ 穿透方块可见 ✓ 亮度拉满 ✓）
- 由**反射层**每拍把它挪到"准星命中的方块上方" ✓ 并写上同一行信息 ✓
- 显示内容（实测读回来的 NBT 原文 ✓）：

```
minecraft:oak_planks
(4128, 70, 12)  距离 3.07  面 west
挖它要用: axe
```

- 「没变就不动世界」✓ —— 只在该目标**变化**时才更新 ✓（省指令 ✓ 也不会抖 ✗）
- 每次更新都写一行 `jade.look` 到 `job.log` ✓（**哪些方块被对准过**是可追溯的 ✓）

### ⚠ 它是实体 ⇒ 会被 `@e` 选中 ✗

所以：

1. 它带固定 tag **`dsh_jade`** ✓
2. **反射层的所有"最近实体"查询都排除它** ✓（`tag=!dsh_jade` ✓）
   —— 否则"最近的实体"永远是它 ✓ → 反射层永远判定"附近还有目标" ✓ → 永远不停止攻击 ✗
   （等于把保命逻辑弄瞎 ✗）
3. **Agent 侧的实体查询也排除它** ✓（`agent/world.py` ✓）

---

## 5. 踩过的坑（都记在 `docs/错题本.md` H3/H4/H5 ✓）

| 坑 | 现象 | 修法 |
|---|---|---|
| `textutils.serializeJSON` 把中文按**字节**转义成 `\u00XX` ✗ | HUD 文本永远停在占位符 ✓ 位置却更新成功 ✓ | 自己拼 JSON ✓ 只转义必须转义的 ✓ |
| **SNBT 自己也会解释转义** ✗ | 修完上一条仍然失败 ✗ | 交给 SNBT 前把 `\` **再补一层** ✓（`\n`→`\\n` ✓） |
| `data get block` **只读方块实体** ✗ | 普通方块一律 `success:false` ✗ → 把"有木板"读成"空" ✗ | 普通方块用 `commands.getBlockInfo`（`tools/block_at.py` ✓） |
| 只验"实体存在" ✗ | 位置更新成功 ✓ 文本却是旧的占位符 ✓ = 假阳性 ✓ | 必须**读回文本内容**验收 ✓（`tools/deploy.py --hud on` 会做 ✓） |

**教训总纲**：一个"看起来在工作"的 HUD，必须用**内容**验收 ✓ 不能用**存在性**验收 ✓。

---

## 6. 相关文件

| 文件 | 作用 |
|---|---|
| `cc-tweaked/agent_bridge.lua` | 准星射线（`A.crosshair`）＋ HUD（`A.jade` / `jadeTick`）＋ 反射层接线 |
| `agent/skills.py` | `look_block` 技能（给 LLM 用的一层 ✓） |
| `tools/deploy.py` | 部署新程序 + **在世界里验收**（sha1 / uptime / 看点 / HUD 文本 ✓） |
| `tools/act.py` | 直接下发桥接动作（不过滤参数 ✓ 完整回传 ✓） |
| `tools/raw.py` | 直接下发游戏指令（不过滤、不裁剪 ✓ 带引号就写文件用 `--file` ✓） |
| `tools/probe_jade.txt` | 本轮用于摸清"文本到底怎么写进去"的指令探测集 ✓ |
