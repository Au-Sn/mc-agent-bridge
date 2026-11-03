// dsh_eat.js —— 让假人"吃东西"（免界面 ✓）
//
// 为什么必须服务端做（实测 ✓ 不是猜的 ✗）：
//   Carpet 的右键（`use once` ✓ 甚至 `use continuous` 按住 5 秒 ✓）对**食物完全无效** ✗
//   —— 手持熟牛排、已解除潜行、持续右键 ⇒ `FoodLevel` 始终是 0 ✗
//   （与早期笔记"reflex.eat 从未在实地观察到触发"一致 ✓ 现在知道原因了 ✓）
//   ⇒ 假人会一直挨饿掉血 ✗ ⇒ 必须由服务端替它完成"吃"这个动作 ✓
//
// ⚠ 语义边界：**真的扣掉背包里那一个** ✓ 再按该食物的营养值加饥饿 ✓
//   不是白给 ✗ 也不是凭空回血 ✗ —— 与"真人吃掉一个"等价 ✓
//
// 通道：/tag Bot add dsh.eat.<食物名子串>      例：dsh.eat.cooked_beef
//
// 营养表：[营养值, **饱和度系数**] —— 注意第二项是 FoodData.eat 要求的"系数" ✓
// ⚠ 真实事故（必读 ✓）：一开始把这里写成"绝对饱和度"（如熟牛排 12.8 ✗）——
//    而 `eat(营养, 饱和度系数)` 的算法是 `饱食度 += 营养 × 系数 × 2` ✓
//    ⇒ 系数写错会让饱食度爆表或为 0 ✗ 记文档 ✓
var DSH_FOOD = {
    'cooked_beef': [8, 0.8], 'beef': [3, 0.3], 'porkchop': [3, 0.3], 'cooked_porkchop': [8, 0.8],
    'bread': [5, 0.6], 'rotten_flesh': [4, 0.1], 'apple': [4, 0.3], 'golden_apple': [4, 1.2],
    'carrot': [3, 0.6], 'potato': [1, 0.3], 'baked_potato': [5, 0.6],
    'wheat': [1, 0.0], 'chicken': [2, 0.3], 'cooked_chicken': [6, 0.6], 'egg': [0, 0.0],
}

function dshEatShort(id) {
    var m = String(id).match(':(.+)$')
    return m ? m[1] : String(id)
}

function dshEatTry(player, key) {
    var inv = player.inventory
    var i, s
    for (i = 0; i < 36; i++) {
        s = inv.getItem(i)
        if (s && !s.isEmpty() && String(s.id).indexOf(key) >= 0) {
            var short = dshEatShort(s.id)
            var f = DSH_FOOD[short]
            if (!f) {
                console.info('[dsheat] FAIL 没登记 ' + s.id + ' 的营养值 ✗ 明确拒绝（不乱加 ✗）')
                return -1
            }
            var before = 0
            try { before = player.getFoodData().getFoodLevel() } catch (e) { }
            // ★ 饱着就别吃 ✓（真实事故：先前不看饥饿值就扣 ✗ 白吃掉了 2 块熟牛排 ✗）
            //   真人吃东西的前提就是"饿" ✓ —— 这条不是优化 ✗ 是语义正确性 ✓
            if (before >= 20) {
                console.info('[dsheat] SKIP ' + player.username + ' 已经吃饱了（饥饿 '
                    + before + '/20 ✓）—— 不扣食物 ✓')
                return -1
            }
            s.shrink(1)                                  // ★ 先扣掉那一个 ✓
            // ⚠ 必须用原版 `FoodData.eat(营养, 饱和度系数)` ✓
            //   真实事故：先前写的是 `player.foodLevel = …` ✗
            //   —— 那个属性读出来是 **20** ✗ 而 NBT 里 `FoodLevel` 是 **0** ✗
            //   ⇒ 它不是"当前饥饿值"（多半是 lastFoodLevel ✓）⇒ 写它等于没写 ✗
            //   现象：食物扣掉了 ✓ 饥饿纹丝不动 ✗ —— 又一个"静默无效" ✗ 必记文档 ✓
            var ok = false
            try { player.getFoodData().eat(f[0], f[1]); ok = true } catch (e) { }
            if (!ok) { try { player.minecraftPlayer.getFoodData().eat(f[0], f[1]); ok = true } catch (e) { } }
            if (!ok) {
                console.info('[dsheat] FAIL 写不进饥饿值 ✗（物品已扣 ✗ 如实报告 ✓）')
                return -1
            }
            var after = 0
            try { after = player.getFoodData().getFoodLevel() } catch (e) { }
            console.info('[dsheat] OK ' + player.username + ' 吃了 1 个 ' + s.id
                + '（饥饿 ' + before + ' → ' + after + ' ✓ 剩余 ' + s.getCount() + ' ✓）')
            return after
        }
    }
    console.info('[dsheat] FAIL 背包里没有含 ' + key + ' 的食物 ✗')
    return -1
}

ServerEvents.tick(event => {
    var server = event.server
    if (server.getTickCount() % 10 != 0) return
    var players = server.players
    var i
    for (i = 0; i < players.length; i++) {
        var p = players[i]
        var arr = []
        try {
            var tags = p.getTags()
            if (tags && !tags.isEmpty()) tags.forEach(function (t) { arr.push(String(t)) })
        } catch (e) { continue }
        var j
        for (j = 0; j < arr.length; j++) {
            if (arr[j].indexOf('dsh.eat.') != 0) continue
            dshEatTry(p, arr[j].substring('dsh.eat.'.length))
            try { p.removeTag(arr[j]) } catch (e) { }
        }
    }
})
