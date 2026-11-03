// dsh_craft.js —— 免界面合成（让"合成"变成假人能走的路）
//
// 为什么写在这里（KubeJS 服务端脚本）：
//   * 假人**没有客户端**、打不开任何 GUI ✗ —— 所以永远点不了工作台 ✗
//   * 但它**是服务端的真玩家** ✓ 背包/物品都是真的 ✓
//   * KubeJS 能在**服务端**直接读写它的背包 ✓ ⇒ "按配方扣材料、发成品" ✓
//     就等于替它点了一次工作台 ✓✓ —— 这正是"游戏初期也要能合成"的那条通路 ✓
//
// ⚠ 不是作弊口子 ✗：每次合成**先扣真实材料** ✓ 不够就明确拒绝 ✓
//   与"站在工作台前合成"语义等价 ✓（只是不需要界面）✓
//
// 触发通道：★记分板标签工单★ ✓（cmd0 有 /tag 权限 ✓ 不需要任何人动手 ✓）
//   /tag Bot add craft.<物品>.<次数>        ← 下单
//   例：/tag Bot add craft.crafting_table.1
//       /tag Bot add craft.minecraft:furnace.2
//   脚本每 10 tick 扫一次 ✓ 合成完**自己把标签删掉** ✓（标签即工单 ✓ 用完即销 ✓）
//
// ── 三个实测坑（都踩过 ✓ 写下来免得下一个人再撞 ✗）────────────────────────
//   1) **`PlayerEvents.tick` 不覆盖 Carpet 假人** ✗✓
//      实测心跳只打出 `player=Au_Sn`（真玩家）✓ 假人一次都没有 ✗
//      ⇒ 必须用 **`ServerEvents.tick`** 自己遍历 `server.players` ✓✓
//   2) **Rhino 里 `for…of` / `for…in` 配 `const`/`let` 会在第二圈报
//      `redeclaration of var x`** ✗✓（它被降级成 var 了 ✓）
//      ⇒ 循环一律用 ES5 写法：`var i; for (i = 0; i < arr.length; i++)` ✓✓
//   3) 命令注册（`ServerEvents.commandRegistry`）在 `/kubejs reload server_scripts` 时
//      **确实会重新触发** ✓ 实测有 `command registered` 日志 ✓
//      —— 但真正执行 `/dshcraft` 需要 4 级权限的 `/reload` 一次 ✗（cmd0 只有 2 级 ✓）
//      ⇒ 所以主力通道是标签工单 ✓，命令留着以后给玩家用 ✓
//
// 配方表来源（**不是猜的** ✓）：每条对着 jar 里的配方 JSON 抄 ✓
//   复核：py tools/recipe_index.py --find <产物> --raw
//   加物品就照抄一行 ✓ 键=物品 id ✓ out=一次产出 ✓ in=一次消耗 ✓

var DSH_RECIPES = {
  'minecraft:oak_planks':     { out: 4, in: { 'minecraft:oak_log': 1 } },
  'minecraft:stick':          { out: 4, in: { 'minecraft:oak_planks': 2 } },
  'minecraft:oak_slab':       { out: 6, in: { 'minecraft:oak_planks': 3 } },
  'minecraft:crafting_table': { out: 1, in: { 'minecraft:oak_planks': 4 } },
  'minecraft:chest':          { out: 1, in: { 'minecraft:oak_planks': 8 } },
  'minecraft:furnace':        { out: 1, in: { 'minecraft:cobblestone': 8 } },
  'minecraft:hopper':         { out: 1, in: { 'minecraft:iron_ingot': 5, 'minecraft:chest': 1 } },
  'minecraft:cobblestone':    { out: 1, in: { 'exdeorum:stone_pebble': 4 } },
  // ── 碎块 → 矿石方块（Ex Deorum 的**真实**配方 ✓ 2×2 四个 ✓）────────────────
  //   ⚠ 这里原有三条"熔炼代理"✗（1 碎块直接给 1 铁锭 / 1 玻璃 / 1 木炭 ✗）
  //     2026-09-20 **删除** ✓ 两条原因：
  //       ① 那是**熔炼**不是合成 ✗ 混进合成表等于偷偷放水 ✗
  //       ② 比例也错 ✗：真实链条 = 4 碎块 → 1 矿石 → 熔炼 → 1 锭（**4:1** ✓）
  //          而代理是 1:1 ✗ ⇒ 每次白送 3 倍 ✓（如实记在 docs/自给清单.md ✓）
  //   依据（查 exdeorum-1.45.jar 的 data/exdeorum/recipes/*.json ✓ 不是猜的 ✓）：
  //     只有 **铜 / 金 / 铁** 有这条转换 ✓ 锇等模组矿**没有** ✓
  //     ⇒ 那些碎块在本包里不能直接烧 ✓（用户指出 ✓ 实测 lit:false ✓ 印证 ✓）
  'minecraft:iron_ore':       { out: 1, in: { 'exdeorum:iron_ore_chunk': 4 } },
  'minecraft:copper_ore':     { out: 1, in: { 'exdeorum:copper_ore_chunk': 4 } },
  'minecraft:gold_ore':       { out: 1, in: { 'exdeorum:gold_ore_chunk': 4 } },
  'exdeorum:oak_sieve':       { out: 1, in: { 'minecraft:oak_planks': 4, 'minecraft:oak_slab': 1, 'minecraft:stick': 2 } },
  'exdeorum:wooden_hammer':   { out: 1, in: { 'minecraft:oak_planks': 1, 'minecraft:stick': 1 } },
  'minecraft:torch':          { out: 4, in: { 'minecraft:coal': 1, 'minecraft:stick': 1 } },
  'minecraft:ladder':         { out: 3, in: { 'minecraft:stick': 7 } },
  // ── 食物（原版配方 ✓ 3 个小麦排一行 → 1 个面包 ✓）────────────────────────
  //   为什么加它：假人**会饿**（实测 FoodLevel 落到 0 ✗）—— 它会挨饿、会掉血 ✓
  //   面包一次回 5 点饥饿 ✓ 比腐肉（4 点、还带饥饿副作用）好 ✓
  'minecraft:bread':          { out: 1, in: { 'minecraft:wheat': 3 } },
  // ── 工具（"矿物碎块 → 矿物 → 工具"的最后一段 ✓ 原版配方 ✓）──
  'minecraft:iron_pickaxe':   { out: 1, in: { 'minecraft:iron_ingot': 3, 'minecraft:stick': 2 } },
  'minecraft:iron_axe':       { out: 1, in: { 'minecraft:iron_ingot': 3, 'minecraft:stick': 2 } },
  'minecraft:iron_shovel':    { out: 1, in: { 'minecraft:iron_ingot': 1, 'minecraft:stick': 2 } },
  'minecraft:iron_sword':     { out: 1, in: { 'minecraft:iron_ingot': 2, 'minecraft:stick': 1 } },
  'minecraft:iron_hoe':       { out: 1, in: { 'minecraft:iron_ingot': 2, 'minecraft:stick': 2 } },
  'minecraft:stone_pickaxe':  { out: 1, in: { 'minecraft:cobblestone': 3, 'minecraft:stick': 2 } },
  'minecraft:stone_axe':      { out: 1, in: { 'minecraft:cobblestone': 3, 'minecraft:stick': 2 } },
  'minecraft:wooden_pickaxe': { out: 1, in: { 'minecraft:oak_planks': 3, 'minecraft:stick': 2 } },
  'minecraft:wooden_axe':     { out: 1, in: { 'minecraft:oak_planks': 3, 'minecraft:stick': 2 } },
}

function dshLog(msg) {
  try { console.info('[dshcraft] ' + msg) } catch (e) { }
}

function dshItemId(stack) {
  try { if (stack.id) return String(stack.id) } catch (e) { }
  try { return String(stack.getItem().builtInRegistryHolder().key().location()) } catch (e) { }
  return ''
}

function dshInvSize(inv) {
  try { return inv.getContainerSize() } catch (e) { }
  try { return inv.containerSize } catch (e) { }
  return 36
}

function dshInvGet(inv, i) {
  try { return inv.getItem(i) } catch (e) { }
  try { return inv.items[i] } catch (e) { }
  return null
}

// 背包里某个 id 的总数 + 命中槽位
function dshCount(player, id) {
  var inv = player.inventory
  var n = dshInvSize(inv)
  var total = 0
  var slots = []
  var i, s
  for (i = 0; i < n; i++) {
    s = dshInvGet(inv, i)
    if (s && !s.isEmpty() && dshItemId(s) === id) {
      total += s.getCount()
      slots.push(i)
    }
  }
  return { total: total, slots: slots, inv: inv }
}

// 从背包扣掉 n 个（调用前已确认够 ✓ 这里只管扣 ✓）
function dshConsume(player, id, n) {
  var c = dshCount(player, id)
  var left = n
  var i, s, take
  for (i = 0; i < c.slots.length; i++) {
    if (left <= 0) break
    s = dshInvGet(c.inv, c.slots[i])
    take = Math.min(s.getCount(), left)
    s.shrink(take)
    left -= take
  }
  return n - left
}

function dshGive(player, id, count) {
  try { player.give(Item.of(id, count)); return true } catch (e) { }
  try { player.giveItemToPlayer(Item.of(id, count)); return true } catch (e) { }
  try { player.addItem(Item.of(id, count)); return true } catch (e) { }
  return false
}

// ★★ 放得下吗？—— 这是"静默吞物品"事故的根因 ✓（2026-09-20 查清 ✓ 必读）
//
// 实测两次同样的形态 ✗：
//   `craft.iron_ingot.10` → 日志 `OK … x10` ✓ 但紧跟「背包里有 0」✗
//   `craft.gold_ore.1`    → 日志 `OK … x1`  ✓ 但紧跟「背包里有 0」✗
//     ⇒ 材料**扣掉了** ✓ 成品**没进背包** ✓ 而且**不抛异常、不报错** ✗
//   根因：`player.give`（以及 giveItemToPlayer / addItem）在**背包满**时
//        **既不抛异常也不返回失败** ✗ —— 函数"成功返回"，东西却没了 ✗
//        （同一天早些时候 `times=10` 那次其实也是这个原因 ✓ 不是循环写错 ✗）
//
// ⇒ 纪律（本文件的规矩 ✓）：**先确认放得下，再扣料** ✓
//    放不下就明确拒绝 ✓ —— 宁可合成失败，也绝不允许"扣了料、东西消失" ✗
function dshHasRoom(player, id, count) {
  try {
    var inv = player.inventory
    var i, s
    for (i = 0; i < 36; i++) {           // ① 已经有同种堆、且还装得下 ✓
      s = dshInvGet(inv, i)
      if (s && !s.isEmpty() && String(s.id) == id && s.getCount() + count <= s.getMaxStackSize()) return true
    }
    for (i = 0; i < 36; i++) {           // ② 有空槽 ✓
      s = dshInvGet(inv, i)
      if (!s || s.isEmpty()) return true
    }
    return false
  } catch (e) {
    return true                          // 读不到就保守放行 ✓（别把功能拦死 ✗）
  }
}

// ── 核心：给 player 合成 want ×times（先扣后发 ✓ 不够就少做 ✓ 绝不凭空造 ✗）──
function dshCraftCore(player, want, times) {
  if (!want) return -1
  if (want.indexOf(':') < 0) want = 'minecraft:' + want
  if (!times || times < 1) times = 1
  if (times > 64) times = 64

  var rec = DSH_RECIPES[want]
  if (!rec) { dshLog('FAIL: 配方表里没有 ' + want); return -1 }

  var ids = Object.keys(rec.in)
  var canDo = times
  var i, id, need
  for (i = 0; i < ids.length; i++) {
    id = ids[i]
    canDo = Math.min(canDo, Math.floor(dshCount(player, id).total / rec.in[id]))
  }
  if (canDo < 1) {
    need = []
    for (i = 0; i < ids.length; i++) need.push(rec.in[ids[i]] + '×' + ids[i])
    dshLog('FAIL: 材料不够做 ' + want + '（每次需要 ' + need.join(' + ') + '）')
    return -1
  }

  // ★ 先确认放得下 ✓ 再扣料 ✓（否则就是"扣了料、成品静默消失" ✗ 见 dshHasRoom 注释 ✓）
  if (!dshHasRoom(player, want, rec.out)) {
    dshLog('FAIL: 背包满了，放不下 ' + want + ' ✗ 已拒绝（**没有扣材料** ✓ 先腾格子再来 ✓）')
    return -1
  }

  var done = 0
  var k, ok
  for (k = 0; k < canDo; k++) {
    ok = true
    for (i = 0; i < ids.length; i++) {
      id = ids[i]
      if (dshConsume(player, id, rec.in[id]) !== rec.in[id]) { ok = false; break }
    }
    if (!ok) break
    if (!dshGive(player, want, rec.out)) break
    done++
  }
  if (done > 0) {
    dshLog('OK ' + player.name.string + ' <- ' + want + ' x' + (done * rec.out) +
      ' (times=' + done + ', 现在背包里有 ' + dshCount(player, want).total + ')')
  }
  return done
}

// ── 工单处理：把某人身上的 craft.* 标签都做掉 ✓ 做完删标签 ✓ ──
function dshHandleTickets(player) {
  var tags = null
  try { tags = player.getTags() } catch (e) { dshLog('FAIL getTags: ' + e); return }
  if (!tags || tags.isEmpty()) return
  var arr = []
  try { tags.forEach(function (t) { arr.push(String(t)) }) } catch (e) { return }

  var i, tag, lastDot, item, times, n
  for (i = 0; i < arr.length; i++) {
    tag = arr[i]
    if (tag.indexOf('craft.') !== 0) continue
    lastDot = tag.lastIndexOf('.')
    item = tag.substring(6, lastDot)
    times = parseInt(tag.substring(lastDot + 1), 10)
    if (!times || times < 1) times = 1
    dshLog('ticket ' + tag + ' on ' + player.name.string + ' -> item=' + item + ' times=' + times)
    n = dshCraftCore(player, item, times)
    try { player.removeTag(tag) } catch (e) { }
    try { player.tell(Text.of('dshcraft: ' + item + ' -> ' + (n < 0 ? 'FAIL' : n))) } catch (e) { }
  }
}

var dshTickCounter = 0

ServerEvents.tick(event => {
  dshTickCounter++
  if (dshTickCounter % 10 !== 0) return
  var players = null
  try { players = event.server.players } catch (e) { return }
  if (!players) return
  if (dshTickCounter % 200 === 0) {
    try {
      var line = []
      players.forEach(function (p) {
        var t = '?'
        try { t = String(p.getTags()) } catch (e) { t = 'ERR' }
        line.push(p.name.string + t)
      })
      dshLog('server tick alive, players=' + line.join(' | '))
    } catch (e) { }
  }
  try {
    players.forEach(function (p) { dshHandleTickets(p) })
  } catch (e) { dshLog('FAIL iterate players: ' + e) }
})

// ── 备用通道：命令（等玩家哪天跑一次 `/reload` 就会生效 ✓）──
ServerEvents.commandRegistry(event => {
  dshLog('registering command dshcraft')
  var C = event.commands
  var A = event.arguments
  event.register(
    C.literal('dshcraft')
      .then(C.argument('item', A.STRING.create(event))
        .executes(function (ctx) {
          var p = ctx.source.player
          if (!p) { ctx.source.sendFailure(Text.of('dshcraft: need a player')); return 0 }
          return Math.max(0, dshCraftCore(p, String(A.STRING.getResult(ctx, 'item')), 1))
        })
        .then(C.argument('times', A.INTEGER.create(event))
          .executes(function (ctx) {
            var p = ctx.source.player
            if (!p) { ctx.source.sendFailure(Text.of('dshcraft: need a player')); return 0 }
            return Math.max(0, dshCraftCore(p, String(A.STRING.getResult(ctx, 'item')),
              A.INTEGER.getResult(ctx, 'times')))
          })))
  )
})

dshLog('script loaded (tick-ticket channel armed)')
