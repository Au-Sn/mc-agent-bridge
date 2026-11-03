# 石砾农场：ATM9 泥土右键机制的完整拆解（含假人专属陷阱）

> 结论一句话 ✓：**这条机制对假人完全可用 ✓** —— 之前"没反应"不是事件投递问题 ✗，
> 而是**掉出来的石砾被它自己捡走、手不再空** ✗，而规则要求**空手** ✓。
>
> 本文记录：规则原文 ✓ 三个条件的实测真值 ✓ 拾取落点规则 ✓ 以及把它变成
> **一条指令**的机器人动作 `pebble_farm` ✓。

---

## 1. 规则原文（不是猜的 ✓ 直接读整合包脚本）

`<实例>/kubejs/server_scripts/mods/exdeorum/pebbles.js`：

```js
BlockEvents.rightClicked(event => {
    const { hand, block, player, item, facing } = event
    if (hand != 'MAIN_HAND') return
    if (!block.hasTag('minecraft:dirt')) return
    if (!item.isEmpty()) return          // ★ 必须空手
    if (!player.isShiftKeyDown()) return // ★ 必须潜行
    let loot = [ "exdeorum:andesite_pebble", "exdeorum:basalt_pebble",
                 "exdeorum:blackstone_pebble", "exdeorum:diorite_pebble",
                 "exdeorum:granite_pebble", "exdeorum:deepslate_pebble" ]
    let random = Math.floor(Math.random() * 2 * loot.length)   // 0..11
    let dropItem = Item.of(loot[random] ?? "exdeorum:stone_pebble")  // ★ 越界 → 石砾
    block.popItemFromFace(dropItem, facing)
    player.swing()
})
```

两条容易被忽略的推论 ✓：

1. **下标越界就是设计的一部分** ✓：`loot` 只有 6 项，`random` 取 0..11
   ⇒ 有 6 种情况落到 `?? "exdeorum:stone_pebble"` ✓
   ⇒ **石砾占 50%** ✓ 其余 6 种各 1/12 ✓（实测 16 次点击出 8 颗石砾 ✓ 完全吻合 ✓）
2. **掉落物从"被点的那个面"弹出** ✓（`popItemFromFace(dropItem, facing)`）
   ⇒ 点顶面就往上弹 ✓ 点侧面就往侧面弹 ✓ —— 这一点决定了"会不会被自己捡到" ✓

---

## 2. 三个条件的实测真值（KubeJS 探针，权威 ✓）

不能靠猜 ✗ —— 直接写一个诊断脚本把字段打出来 ✓
（仓库里是 `kubejs/dsh_probe.js` ✓ 只记日志、零副作用 ✓ 用完删掉即可 ✓）：

```
[dshprobe] who=Bot hand=MAIN_HAND item=0 air empty=true
           block=minecraft:grass_block dirtTag=true shift=true face=up
           cls=carpet.patches.EntityPlayerMPFake
```

三件事一次性确认 ✓：

| 疑问 | 真值 | 备注 |
|---|---|---|
| 假人会触发 KubeJS 的右键事件吗？ | **会** ✓ | `cls=carpet.patches.EntityPlayerMPFake` ✓ |
| `grass_block` 在 `minecraft:dirt` 标签里吗？ | **在** ✓ | 游戏自己回答：`/execute if block X Y Z #minecraft:dirt` → 1 ✓ |
| `/player Bot sneak` 真的生效吗？ | **生效** ✓ | `shift=true` ✓ |

---

## 3. 真正的坑：拾取落点 = 编号最小的空快捷栏槽

**现象**：第一次点击**确实掉出了石砾** ✓ 但第二次开始的日志变成 `item=1 stone_pebble empty=false` ✗
—— 手被自己捡的东西占了 ✗ → 之后每次点击都被 `!item.isEmpty()` 挡掉 ✓ **而且一声不响** ✗。

**机制**（源码 + 实测一致 ✓）：`Inventory.add(-1, stack)` 先找**同种物品的堆**合并 ✓
（`getSlotWithRemainingSpace`，全 36 格扫 ✓），没有才用 `getFreeSlot()`：
**返回下标最小的空格** ✓ 而快捷栏在 `items` 里就是 0..8 ✓ ⇒ **永远先占快捷栏** ✓。

由此得到两条可操作的结论 ✓：

* **站得远就捡不到** ✓：玩家拾取判定是"物品包围盒外扩 1 格与玩家碰撞盒相交" ✓
  ⇒ 水平距离 ≥1.5 格就安全 ✓（实测 2.3 格稳 ✓）
  ⇒ 但**必须确认射线真的落在土方块上** ✗（见 §5）
* **站正上方就一定被捡** ✗ ⇒ 必须清手 ✓：把手里那件**朝"低一格的走道沟"丢下去** ✓
  —— 沟底比脚底低 1 格 ⇒ 高度差让假人**够不到** ✓ 不会被再次捡回 ✓

---

## 4. 机器人动作 `pebble_farm`（一条指令做完一整件事）

```
py tools/act.py --wait 260 pebble_farm bot=Bot x=4124 y=70 z=11 clicks=72
```

实测输出（真实跑过 ✓）：

```json
{ "clicks": 72, "seconds": 65, "gained": 50,
  "by_type_after": { "exdeorum:stone_pebble": 34, "exdeorum:diorite_pebble": 9,
                     "exdeorum:blackstone_pebble": 6, "exdeorum:deepslate_pebble": 5,
                     "exdeorum:basalt_pebble": 4, "exdeorum:andesite_pebble": 4 },
  "clears": 22, "clear_failures": 1, "target_changed": 0 }
```

* `clicks`：真的点了几下 ✓（不是"发了几条指令"✗）
* `clears`：几次因为手被占而清手 ✓
* `target_changed`：目标方块有没有被搞坏 ✓（本次 0 ✓ 没有误伤玩家的世界 ✓）
* 每次点击**自证**：读一次背包 NBT ✓ 只看真实库存 ✓ 不看指令回显 ✓

它内部的两条安全设计（都来自真实事故 ✓）：

1. **动手前硬检查**：手必须是空的 ✓ 目标格必须真的是方块 ✓
   否则**直接拒绝** ✓ 而不是"照着点一通、把玩家的世界改坏" ✗
2. **每 8 次抽查目标方块** ✓ 一旦被换掉就记进报告 ✓

---

## 5. 两条反直觉的坑（都让"看起来正常"变成颗粒无收）

### 5.1 准星说打到了 ≠ 事件真的发生

从 3 格外的位置点那格草方块时：Jade 准星报
`looking_at: framedblocks:framed_slab_edge @ (4128,71,11) 距离 2.51 面 east` ✓
—— **射线被建筑装饰的台阶边挡住了** ✗ ✓ 而对那一格的右键**根本不触发 KubeJS 事件** ✗
（探针一条日志都没有 ✓）。

⇒ **纪律** ✓：判断"这一下点到了什么"，以**事件日志 / 掉落物 / 方块 NBT** 为准 ✓
   —— `crosshair`（Jade 射线）只是"我以为"✗（见 `docs/Jade-准星感知.md` ✓ 那里也要补这条 ✓）。

### 5.2 快照是旧的：世界正被真人玩家同时修改

摆熔炉产线时，我按两次旧探测（都是 `air` ✓）把箱子瞄向 `(4125,70,11)` 的顶面 ✓
结果箱子落到了**隔壁一格** ✗ —— 重新探发现那一格**刚刚变成了黑曜石**（玩家在施工 ✓）。

⇒ **纪律** ✓：**动手放方块前重新探一次落点** ✓（哪怕几分钟前刚探过 ✗）；
   放错了要**自己收回来** ✓（本次已挖掉误放的箱子 ✓）。

---

## 6. 与"自给"的关系

* 这条通路**完全自给** ✓：泥土是世界里本来就有的地形 ✓，假人自己蹲、自己点、自己捡 ✓
  全程 **零指令给予** ✓ —— 石砾 → 4 颗圆石（`craft.cobblestone.8` ✓ 先扣料再发成品 ✓）
  → 8 圆石熔炉 ✓ 这条链上没有任何"白给" ✓
* 代价与边界（如实记）✓：
  * 掉在地上没及时收的东西 **5 分钟消失** ✗（本文写作前又损失 32 砂砾 ✓ 见 `docs/自给清单.md`）
  * 垃圾石砾（另一半 50%）被丢进沟里 ✓ 可回收 ✓（也可留着做安山岩/闪长岩等 ✓）
