// dsh_probe.js —— 诊断用：把"右键方块"事件的真实字段打出来
//
// 为什么要这个文件（问题陈述）：
//   原版 ATM9 有 kubejs/server_scripts/mods/exdeorum/pebbles.js ✓
//   规则是：空手 + 潜行 + 右键 `minecraft:dirt` 标签方块 → 掉一颗石砾 ✓
//   但 Carpet 假人 Bot 照做**一颗都没掉** ✗ —— 而且不报任何错 ✗
//   三个条件里任意一个对假人失真，现象都一模一样 ✗ ⇒ 只能把真实字段打出来 ✓
//     a) item.isEmpty()        —— 假人手上到底是不是空的？
//     b) isShiftKeyDown()      —— `/player Bot sneak` 有没有真的生效？
//     c) block.hasTag('minecraft:dirt') —— 瞄的那格是不是真的 dirt 标签？
//   还有第 4 种可能：这个事件**对假人根本不触发** ✗
//   ⇒ 所以这里对"假人的每一次右键"都记一笔 ✓（能记到 = 事件确实触发 ✓）
//
// 只记日志，不改世界 ✓（副作用为零 ✓）—— 诊断脚本不许有副作用 ✓
// 用完即删：把本文件从 kubejs/server_scripts/ 删掉再 reload 即可 ✓

function dshProbeLine(player, hand, block, item, facing) {
    var cls = '?'
    try { cls = player.getClass().getName() } catch (e) { cls = 'n/a' }
    return '[dshprobe] who=' + player.username
        + ' hand=' + hand
        + ' item=' + item
        + ' empty=' + item.isEmpty()
        + ' block=' + block.id
        + ' dirtTag=' + block.hasTag('minecraft:dirt')
        + ' shift=' + player.isShiftKeyDown()
        + ' face=' + facing
        + ' cls=' + cls
        + ' pos=' + block.x + ',' + block.y + ',' + block.z
}

BlockEvents.rightClicked(event => {
    var hand = event.hand
    var player = event.player
    var block = event.block
    var item = event.item
    var facing = event.facing

    // 记两种情况：① 假人 Bot 的任何右键（验证事件是否触发）
    //           ② 任何人右键 dirt 标签方块（验证 pebbles.js 的前置条件）
    var isBot = (player.username == 'Bot')
    var isDirt = false
    try { isDirt = block.hasTag('minecraft:dirt') } catch (e) { isDirt = false }
    if (!isBot && !isDirt) return

    console.info(dshProbeLine(player, hand, block, item, facing))
})
