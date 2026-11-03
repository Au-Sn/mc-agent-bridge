// dsh_container.js —— 免界面容器取放（把"假人的手"补全）
//
// 为什么需要（问题陈述）：
//   * 假人**没有客户端** ⇒ 打不开箱子/熔炉/木桶的任何界面 ✗
//   * 于是整条产线的最后一米断掉：漏斗把成品送进箱子 ✓ 假人却拿不出来 ✗
//   * 但 KubeJS 在服务端能直接读写**方块的容器库存** ✓
//     ⇒ "把容器里的东西搬进假人背包"就是一个纯服务端动作 ✓ 不需要界面 ✓
//
// ⚠ 语义边界（重要）：
//   这里做的是"**替假人把箱子里的东西拿出来**" ✓ —— 等价于它打开箱子、把东西拖进背包 ✓
//   不做无中生有 ✗（不发任何物品 ✓ 只做搬运 ✓）⇒ 不是作弊口子 ✓
//
// 触发通道：记分板标签工单 ✓（与 dsh_craft.js 同一套思路 ✓ cmd0 有 /tag 权限 ✓）
//   /tag Bot add dsh.take.<x>.<y>.<z>      把该容器里的东西全部搬进背包 ✓
//   坐标里请**不要**出现负号以外的小数 ✗（标签名不能带 '-' 之外的符号 ✓）；
//   方块坐标都是整数 ✓ 够用 ✓
//   （负数目前不支持 ⚠ —— 本包这片区域全是正坐标 ✓ 需要时再扩 ✓）
//
// 三个实测坑（写下来免得下一个人再撞 ✗）：
//   1) `PlayerEvents.tick` 不覆盖假人 ✗ ⇒ 必须 `ServerEvents.tick` + 自己遍历 players ✓
//      （与 dsh_craft.js 同因 ✓）
//   2) Rhino 里 `for…of`/`for…in` 配 const/let 会在第二圈报 redeclaration ✗
//      ⇒ 一律 ES5 循环 ✓
//   3) `block.inventory` 只对**真的方块实体**存在 ✓ —— 对石头/空气取它会得到 null ✓
//      ⇒ 每次都要判空 ✓ 否则一取就是 "cannot read property of null" ✗
//
// 复核方式：`console.info('[dshbox] …')` 写日志 ✓（CC 终端显示中文是 ? ✗ 所以走日志 ✓）

var DSH_BOX_TAG_PREFIX = 'dsh.take.'

// ⚠ 取标签的正确写法（第一版写错了 ✓ 记下来）：
//   错：`player.tags.getTags()` / `player.tags` 迭代 ✗
//       实测报 `TypeError: Cannot find function getTags in object []` ✗
//       而且它是 **ServerEvents.tick 每 tick 必抛** ✗ ⇒ 日志被刷爆 ✗
//   对：`player.getTags()` 拿到一个 Java Set ✓ 用 `forEach` 遍历 ✓
//       （与 dsh_craft.js 里的写法完全一致 ✓ 那边是跑通过的 ✓）
function dshBoxPlayerTags(player) {
    var arr = []
    try {
        var tags = player.getTags()
        if (!tags || tags.isEmpty()) return arr
        tags.forEach(function (t) { arr.push(String(t)) })
    } catch (e) {
        return arr
    }
    return arr
}

function dshBoxFindContainers(server, tagPrefix) {
    // 返回 [{player, x, y, z, tag}] —— 一次 tick 里可能有多条工单 ✓
    var out = []
    var players = server.players
    var i
    for (i = 0; i < players.length; i++) {
        var p = players[i]
        var all = dshBoxPlayerTags(p)
        var hits = []
        var k
        for (k = 0; k < all.length; k++) {
            if (all[k].indexOf(tagPrefix) == 0) hits.push(all[k])
        }
        var j
        for (j = 0; j < hits.length; j++) {
            var parts = hits[j].substring(tagPrefix.length).split('.')
            out.push({
                player: p,
                tag: hits[j],
                x: parseInt(parts[0], 10),
                y: parseInt(parts[1], 10),
                z: parseInt(parts[2], 10)
            })
        }
    }
    return out
}

function dshBoxTake(player, x, y, z) {
    var level = player.level
    var pos = new BlockPos(x, y, z)
    var block = level.getBlock(pos)
    var id = String(block.id)
    var inv = null
    try { inv = block.inventory } catch (e) { inv = null }
    if (inv === null || inv === undefined) {
        console.info('[dshbox] ' + player.username + ' (' + x + ',' + y + ',' + z + ') ' + id + ' 没有容器库存 ✗')
        return
    }
    var size = inv.getSlots ? inv.getSlots() : 27
    var movedTypes = 0
    var movedCount = 0
    var s
    for (s = 0; s < size; s++) {
        var st = inv.getStackInSlot(s)
        if (st === null || st === undefined || st.isEmpty()) continue
        var n = st.getCount()
        player.give(st)                      // 先给假人 ✓
        inv.setStackInSlot(s, Item.of('minecraft:air'))   // 再清空槽位 ✓
        movedTypes = movedTypes + 1
        movedCount = movedCount + n
    }
    console.info('[dshbox] ' + player.username + ' 从 (' + x + ',' + y + ',' + z + ') '
        + id + ' 取出 ' + movedTypes + ' 种 / ' + movedCount + ' 个')
}

ServerEvents.tick(event => {
    var server = event.server
    if (server.getTickCount() % 10 != 0) return
    var jobs = dshBoxFindContainers(server, DSH_BOX_TAG_PREFIX)
    var i
    for (i = 0; i < jobs.length; i++) {
        var j = jobs[i]
        if (isNaN(j.x) || isNaN(j.y) || isNaN(j.z)) {
            j.player.tags.remove(j.tag)
            continue
        }
        dshBoxTake(j.player, j.x, j.y, j.z)
        j.player.tags.remove(j.tag)          // 标签即工单 ✓ 用完即销 ✓
    }
})
