--[[
  turtle_worker.lua — 海龟执行端（MC Agent Bridge 集群模式）
  ==================================================================

  跑在每只海龟上，通过 rednet 接收主计算机转发的指令并执行，然后回传结果。

  安装（游戏内，每只海龟上执行一次）：
      wget run http://<网关IP>:8765/files/turtle_worker.lua

  与主程序的关系：
      Agent → 网关 → agent_bridge.lua（主计算机）
                        │  args.target=<海龟rednet id> 时转发
                        ▼
                   turtle_worker.lua（海龟本体执行）

  ⚠ 所有海龟与主计算机必须在同一维度，且都插了无线调制解调器、同一频道。
]]

local CFG_FILE = "worker.cfg"
local DEFAULTS = {
  rednet_chan = "4200",
  role        = "miner",
  gateway     = "http://127.0.0.1:8765",   -- 仅用于写开机自启（海龟本身只走 rednet）
  autostart   = "1",                        -- 1 = 首次运行时自动写入 startup（开机自启）
}

local cfg = {}
for k, v in pairs(DEFAULTS) do cfg[k] = v end
if fs.exists(CFG_FILE) then
  local f = fs.open(CFG_FILE, "r")
  if f then
    while true do
      local line = f.readLine(); if not line then break end
      local k, v = line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
      if k and v ~= "" then cfg[k] = v end
    end
    f.close()
  end
else
  local f = fs.open(CFG_FILE, "w")
  if f then
    f.writeLine("# 海龟执行端配置")
    for k, v in pairs(DEFAULTS) do f.writeLine(k .. "=" .. v) end
    f.close()
  end
end

local CHAN = tonumber(cfg.rednet_chan) or 4200
local ROLE = cfg.role

--------------------------------------------------------------------------------
-- 打开 modem
--------------------------------------------------------------------------------
-- 类型名归一化：各版本上报的类型名写法不一（"modem"/"wireless_modem"/"wirelessModem"…），
-- 不归一化就会漏检（教训：docs/lessons-learned.md B17）。
local function norm(s)
  return tostring(s or "?"):lower():gsub("[_%s%-]", "")
end
-- ★ 升级槽**记账文件**（必须自己记账 ✗ —— 这是本轮真实事故的直接产物 ✓）
--   为什么读不出来：CC 的 `turtle.getEquippedLeft/Right` 是 **1.116+** 的 API ✗，
--     ATM9 这台没有 ✗ → 于是"右边到底装着什么"在游戏内**完全查不到** ✓
--     （外部能看到 ✓：cmd0 的 `data get block <海龟位置>` 里有 RightUpgrade ✓
--       —— 但海龟自己看不到自己的方块 NBT ✗）
--   后果（真实事故 2026-09-18）：我装好镐子 ✓ 用它挖通了一整行木板 ✓
--     然后一次 `self_update` 重启 → 开机自动装备以为"右边是空的" ✗
--     → 把镐子挤回背包、换上了斧头 ✗（斧头挖不动石头/泥土 ✗ 又会回到 No tool to dig with ✗）
--   解决：把升级槽写进本机文件 ✓ 开机读回来 ✓ —— 文件就是海龟的长期记忆 ✓。
local EQUIP_FILE = "equipped_state"
local equipState = { left = nil, right = nil }

local function loadEquipState()
  if not fs.exists(EQUIP_FILE) then return end
  local f = fs.open(EQUIP_FILE, "r")
  if not f then return end
  local body = f.readAll()
  f.close()
  local ok, t = pcall(textutils.unserialize, body)
  if ok and type(t) == "table" then
    equipState.left, equipState.right = t.left, t.right
  end
end

local function saveEquipState()
  local f = fs.open(EQUIP_FILE, "w")
  if not f then return end
  f.write(textutils.serialize(equipState))
  f.close()
end

loadEquipState()

local function isToolName(n)
  n = tostring(n or "")
  return n:find("_axe$") or n:find("_pickaxe$") or n:find("_shovel$")
      or n:find("_sword$") or n:find("_hoe$")
end

-- 某一侧升级位是否被占用。
-- 注意：调制解调器/扬声器等会作为**外设**出现 ✓，但**工具类升级不会** ✗，
-- 所以：先看记账文件 ✓ → 再看外设 ✓ → 最后试 turtle.getEquippedLeft/Right（有就用）✓。
local function sideHasUpgrade(side)
  if equipState[side] then return true end
  for _, n in ipairs(peripheral.getNames()) do
    if n == side then return true end
  end
  local fn = (side == "left") and turtle.getEquippedLeft or turtle.getEquippedRight
  if type(fn) == "function" then
    local ok, item = pcall(fn)
    if ok and item ~= nil then return true end
  end
  return false
end
local function freeSide()
  if not sideHasUpgrade("left") then return "left" end
  if not sideHasUpgrade("right") then return "right" end
  return nil
end

-- 当前是否已装备工具（用于判断"挖不动"是不是缺工具）
local function equippedToolName()
  for _, side in ipairs({ "left", "right" }) do
    if isToolName(equipState[side]) then return equipState[side] end
  end
  for _, side in ipairs({ "left", "right" }) do
    local fn = (side == "left") and turtle.getEquippedLeft or turtle.getEquippedRight
    if type(fn) == "function" then
      local ok, item = pcall(fn)
      if ok and item and item.name and isToolName(item.name) then
        return tostring(item.name)
      end
    end
  end
  return nil
end

-- 从背包里找一个满足条件的物品，装到空闲升级位。
-- matcher(itemDetail) -> true/false
local function equipFromInventory(matcher, label)
  local side = freeSide()
  if not side then
    print("[worker] no free upgrade slot for " .. label .. " (both sides occupied)")
    return false
  end
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and matcher(d) then
      turtle.select(i)
      local ok = (side == "left") and turtle.equipLeft() or turtle.equipRight()
      if ok then
        -- ★ 开机自动装备**也必须记账** ✗ —— 否则下一次重启会以为右侧还是空的 ✓
        --   于是又去装一遍 ✓ 这次背包里没有镐了 ✓ 就退而装斧头 ✗✗
        --   （= 把好用的镐子换成挖不动石头的斧头 ✗ 这正是本轮的真实事故 ✓）
        equipState[side] = d.name
        saveEquipState()
        print("[worker] " .. label .. " equipped to " .. side .. " (slot " .. i .. ")")
        return true
      end
    end
  end
  return false
end

local function isModem(d)
  return d.name == "computercraft:wireless_modem_normal"
      or d.name == "computercraft:wireless_modem_advanced"
end

-- 砍树需要斧头；CC:Tweaked 里海龟挖方块**必须有对应工具**，
-- 否则报 "No tool to dig with"（真实踩过：找到原木却挖不动 ✗）。
--
-- ⚠⚠ 2026-09-18 查清的关键事实（**推翻了本条注释原来的说法** ✗）：
--   1) 海龟用的是**升级槽里的工具** ✓ **不是背包里的** ✗
--      （源码：`turtle.dig` → `TurtleToolCommand.dig(dir, side)` → 取 left/right 升级 ✓；
--        官方文档原话：dig "requires a turtle tool capable of breaking the block" ✓
--        而且 "Diamond pickaxes (mining turtles) can break any vanilla block breakable in
--        survival mode, but other tools (such as axes) are more limited" ✓）
--   2) "当前选中的槽位"只在**装备**时有用 ✗（equipLeft/Right 装的是选中槽位的物品 ✓）
--      —— 装好之后挖什么跟选中槽位无关 ✓
--   3) 所以**镐 > 斧**：镐子能挖原版一切可挖方块 ✓；斧头只对木头类有效 ✗（挖泥土/石头直接失败 ✗）
--   ⇒ 顺序改成 镐 → 斧 → 锹 → 剑 → 锄 ✓
local TOOL_ORDER = { "_pickaxe$", "_axe$", "_shovel$", "_sword$", "_hoe$" }

-- 打开 modem（先找现成的；找不到就尝试自愈装上再找）
local function openModem()
  for _, name in ipairs(peripheral.getNames()) do
    local nt = norm(peripheral.getType(name))
    if nt == "modem" or nt == "wirelessmodem" or nt == "wiredmodem" then
      if pcall(rednet.open, name) then return true, name end
    end
  end
  return false, nil
end

local opened, mside = openModem()
if not opened then
  print("[worker] MODEM NOT FOUND -- trying to equip one from the inventory...")
  if equipFromInventory(isModem, "modem") then
    opened, mside = openModem()
  end
end
if not opened then
  print("[worker] STILL NO MODEM. Put a Wireless Modem in the inventory and rerun worker_local.")
  print("[worker] (It will be auto-equipped on the next run.)")
  return
end
print("[worker] modem open on " .. tostring(mside))

-- 尝试自动装备工具（有就装，没有就明确提示）
do
  local tool = equippedToolName()
  if tool then
    print("[worker] tool already equipped: " .. tool)
  else
    -- ⚠⚠ 这里有一条**血换来的纪律**（2026-09-18 真实事故 ✓）：
    --   本版本没有 `turtle.getEquippedLeft/Right` ✗ ⇒ 如果**连记账文件都不在** ✗，
    --   那就是"状态未知" ✓ —— 此时**绝不能**按优先级"退而求其次"地装 ✗：
    --     背包里有镐子 ✓ 但镐子**正装在右边** ✗ ⇒ 找不到镐子 ⇒ 退而装斧头 ✗
    --     ⇒ `equipRight()` 会把镐子挤回背包 ✓ 换上挖不动石头的斧头 ✗✗
    --     （真实过程：我装好镐子挖通一整行木板 ✓ 两次重启后变回斧头 ✗）
    --   ⇒ 规矩：**未知状态时只装"万能工具"（镐）** ✓；没有镐子就**什么都别动** ✓。
    local trust = fs.exists(EQUIP_FILE)          -- 记账文件在 ⇒ 我们知道自己装过什么 ✓
    local order = trust and TOOL_ORDER or { "_pickaxe$" }
    local equipped = false
    for _, pat in ipairs(order) do
      if equipFromInventory(function(d) return tostring(d.name):find(pat) ~= nil end,
                            "tool(" .. pat .. ")") then
        equipped = true
        break
      end
    end
    if equipped then
      print("[worker] tool now equipped: " .. tostring(equippedToolName()))
    elseif trust then
      print("[worker] WARNING: no tool in inventory -- digging WILL fail (No tool to dig with).")
      print("[worker] Put a pickaxe/axe in the turtle inventory, then rerun worker_local.")
    else
      print("[worker] equip state UNKNOWN and no pickaxe in inventory -- leaving upgrades alone.")
      print("[worker] (从外部核对：data get block <x> <y> <z> 里的 LeftUpgrade/RightUpgrade ✓)")
    end
  end
end

--------------------------------------------------------------------------------
-- 朝向自维护
--------------------------------------------------------------------------------
local FACING = { "north", "east", "south", "west" }
local facingIdx, facingKnown = 1, false

local function turnToIdx(target)
  local guard = 0
  while facingIdx ~= target and guard < 4 do
    if ((target - facingIdx) % 4) <= 2 then
      turtle.turnRight(); facingIdx = facingIdx % 4 + 1
    else
      turtle.turnLeft();  facingIdx = (facingIdx - 2) % 4 + 1
    end
    guard = guard + 1
  end
  facingKnown = true
  return true
end

-- 前置声明：自动测定朝向要用到 locateMedian 与 ACT（两者都在下面才定义）
local autoCalibrate

--------------------------------------------------------------------------------
-- 动作
--------------------------------------------------------------------------------
local function fuelOk()
  local l = turtle.getFuelLevel()
  return l == "unlimited" or (tonumber(l) or 0) > 0
end

local function moveOne(fn, digFn)
  if not fuelOk() then return false, "燃料不足" end
  if fn() then return true end
  if digFn and digFn() and fn() then return true end
  return false, "被阻挡"
end

-- GPS 多次采样取中位数。
-- 为什么需要（实测）：同一个点位连续读数出现过 y=72.45（与真值 72 的误差仅 0.05）和
-- y=70.04（偏 2 格）两种结果 —— CC 的 GPS 靠调制解调器信号强度估算距离，
-- 偶尔会给出**坏解**。因此导航这类关键决策必须多采几次取中位数，不能只信一次。
local function locateMedian(samples, timeout)
  samples = samples or 1
  timeout = timeout or 2
  local xs, ys, zs = {}, {}, {}
  for _ = 1, samples do
    local x, y, z = gps.locate(timeout)
    if x then
      xs[#xs + 1] = x; ys[#ys + 1] = y; zs[#zs + 1] = z
    end
  end
  if #xs == 0 then return nil end
  table.sort(xs); table.sort(ys); table.sort(zs)
  local m = math.floor((#xs + 1) / 2)
  return xs[m], ys[m], zs[m], #xs
end

local ACT = {}

-- ⚠ 参数必须兜底：tonumber(nil) 是 nil，而 `for i = 1, nil` 会直接报
--    "bad 'for' limit"，害得整条指令失败（真实踩过，同 agent_bridge 里那处）。
local function steps(a)
  return tonumber(a and a.n) or 1
end

-- allow_dig 开关（JSON 里可能是 true/false/1/0/"0"/"false"）：
--   不传 = 沿用该方向的历史默认（前进/上/下会挖，后退不挖）
--   allow_dig=0 → **绝不挖**，被挡就干净地失败
-- 为什么需要：移动时自动挖方块是**不可逆**的（可能挖掉用户的建筑/机器），
-- Agent 在不确定前方是什么时必须能选择"只走不挖"。
local function truthy(v, fallback)   -- 参数名不用 default：会被本项目的 lint 规则误报
  if v == nil then return fallback end
  if v == false or v == 0 or v == "0" or v == "false" then return false end
  return true
end

local function useDig(a, digFn)
  if digFn == nil then return false end
  return truthy(a and a.allow_dig, true)
end

-- 关于"防坠落"：**实测证明海龟不受重力，可以悬空，因此不该默认拦截**。
--   实验记录：`up n=2` 后 GPS 的 y 从 70.04 升到 72.45（Δ+2.41，耗 2 燃料 = 2 次移动 ✓），
--   8 秒后再读仍是 72.45 —— **没有掉回来**。源码里也找不到任何重力/下落逻辑
--   （TurtleBlock / TurtleBlockEntity 中无 fall/onLand/checkSupport）。
-- 之前的误判来自：把 GPS 的 y 跳变 2 格当成"坠落"（坠落不耗燃料，而实测只耗 1 燃料/次移动）。
-- 真实原因是 CC 的 GPS 在**4 台主机高度相同时垂直精度很差**（水平误差仅 ~0.1 格，
-- 而 y 会偏 2 格）。教训：**用遥测数据推断物理机制前，先验证遥测本身的精度**。
-- 因此这里改成**按需开启**：需要"必须踩在实地上"的场景传 require_ground=1。
local function fallRisk(a)
  if not truthy(a and a.require_ground, false) then return false end
  return not turtle.detectDown()
end

local function makeMove(fn, digFn, horizontal)
  return function(a)
    local dig = useDig(a, digFn)
    for _ = 1, steps(a) do
      if horizontal and fallRisk(a) then
        return false, "下方无方块（require_ground=1 时拒绝移动；海龟本可悬空）"
      end
      local ok, e
      if dig then ok, e = moveOne(fn, digFn) else ok, e = moveOne(fn) end
      if not ok then return false, e end
    end
    return true
  end
end

ACT.forward = makeMove(turtle.forward, turtle.dig, true)
ACT.back    = makeMove(turtle.back, nil, true)          -- 后退永不挖
ACT.up      = makeMove(turtle.up, turtle.digUp, false)
ACT.down    = makeMove(turtle.down, turtle.digDown, false)

ACT.turn_left  = function() turtle.turnLeft();  facingIdx = (facingIdx - 2) % 4 + 1; return true end
ACT.turn_right = function() turtle.turnRight(); facingIdx = facingIdx % 4 + 1; return true end

ACT.calibrate = function(a)
  for i, d in ipairs(FACING) do
    if d == a.facing then facingIdx, facingKnown = i, true; return true end
  end
  return false, "facing 需为 north|east|south|west"
end

ACT.dig        = function() return turtle.dig() end
ACT.dig_up     = function() return turtle.digUp() end
ACT.dig_down   = function() return turtle.digDown() end
ACT.place      = function() return turtle.place() end
ACT.place_up   = function() return turtle.placeUp() end
ACT.place_down = function() return turtle.placeDown() end
ACT.attack     = function() return turtle.attack() end
ACT.drop       = function() return turtle.drop() end
ACT.suck       = function() return turtle.suck() end
ACT.suck_up    = function() return turtle.suckUp() end
ACT.suck_down  = function() return turtle.suckDown() end
ACT.select     = function(a) local s = tonumber(a.slot)
  if not s or s < 1 or s > 16 then return false, "slot 1..16" end
  return turtle.select(s) end
ACT.refuel     = function(a) return turtle.refuel(tonumber(a.n) or 1) end

-- GPS 定位：让海龟知道自己在世界里的**绝对坐标**。
-- 依据 CC 的 gps 库源码：需要**至少 4 台 GPS 主机**在调制解调器范围内
-- （`gps.lua` 注释：there must be at least 4 computers used as gps hosts）。
-- 有了坐标，"挖这一片/建到那里"才可能；没有坐标时海龟只能盲目相对移动。
ACT.locate = function(a)
  local samples = tonumber(a and a.samples) or 3
  local timeout = tonumber(a and a.timeout) or 2
  local x, y, z, n = locateMedian(samples, timeout)
  if not x then
    return false, "GPS 定位失败：需要至少 4 台 GPS 主机在范围内（且它们位置不共线、最好高度不同）"
  end
  return true, { x = x, y = y, z = z, samples_ok = n, samples_tried = samples }
end

-- 升级槽里到底装了什么 —— **这是必须能自证的一件事**（真实事故，2026-09-18）：
--   CC:Tweaked 的海龟**用升级槽里的工具挖方块** ✗ **不是用背包里的** ✗
--   （源码：`turtle.dig` → `TurtleToolCommand.dig(dir, side)` → 取 left/right 升级里的 tool ✓
--     官方文档原话：dig "requires a turtle tool capable of breaking the block" ✓）
--   ⇒ 背包里有斧头 ≠ 挖得动 ✗；升级槽里是斧头才 ✓
--   ⇒ 而且**斧头挖不动石头/泥土** ✗（镐/锹才行）→ 报 "No tool to dig with" ✗
--   我为这件事来回排查了好几轮 ✓ 根因就是"状态里看不见升级槽" ✗ —— 现在补上 ✓。
--   报告名取自 turtle.getEquippedLeft/Right()（CC 1.116+ ✓ 老版本没有就退回 nil ✓ 不报错 ✓）。
local function upgradeName(side)
  -- 先信**记账文件** ✓（1.116 以下没有 getEquippedLeft/Right ✗ 见文件头注释 ✓）
  if equipState[side] then return equipState[side] end
  local fn = (side == "left") and turtle.getEquippedLeft or turtle.getEquippedRight
  if type(fn) ~= "function" then return nil end
  local ok, d = pcall(fn)
  if not ok or type(d) ~= "table" then return nil end
  return d.name or d.displayName
end

ACT.status = function()
  -- 状态里附带坐标（拿不到就为 nil），这样 discover_turtles 能一次带回"每只海龟在哪"。
  -- 这里只用 2 次采样、每次 0.5 秒超时，避免拖慢状态回报。
  local x, y, z = locateMedian(2, 0.5)
  return true, {
    role = ROLE,
    facing = facingKnown and FACING[facingIdx] or "unknown",
    fuel = turtle.getFuelLevel(),
    label = os.getComputerLabel(),
    id = os.getComputerID(),
    pos = x and { x = x, y = y, z = z } or nil,
    -- 挖得动什么，完全由这两项决定 ✓（见上面的注释 ✓）
    left_upgrade = upgradeName("left"),
    right_upgrade = upgradeName("right"),
    selected = turtle.getSelectedSlot and turtle.getSelectedSlot() or nil,
  }
end

ACT.inv_list = function()
  local items = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d then items[#items + 1] = { slot = i, name = d.name, count = turtle.getItemCount(i) } end
  end
  return true, { items = items, fuel = turtle.getFuelLevel() }
end

-- 背包里所有物品的总个数（用来衡量"采集到没有""合成出没有"）
local function invCount()
  local n = 0
  for i = 1, 16 do n = n + turtle.getItemCount(i) end
  return n
end
ACT.inv_count = function() return true, { count = invCount(), fuel = turtle.getFuelLevel() } end

-- 看指定方向的方块（砍树/判断该不该挖，全靠它）
-- turtle.inspect() 返回 (是否成功, {name=..., state=...})
ACT.inspect = function(a)
  local dir = (a and a.dir) or "front"
  local fn = turtle.inspect
  if dir == "up" then fn = turtle.inspectUp
  elseif dir == "down" then fn = turtle.inspectDown end
  if not fn then return false, "inspect 不可用（版本不支持）" end
  local ok, data = fn()
  if not ok or not data then return false, "该方向没有方块或读取失败（dir=" .. tostring(dir) .. "）" end
  return true, { dir = dir, name = data.name, state = data.state }
end

-- 按物品名选中槽位；也可直接给 slot
ACT.select_item = function(a)
  local wantSlot = tonumber(a and a.slot)
  if wantSlot then
    if wantSlot < 1 or wantSlot > 16 then return false, "slot 需为 1..16" end
    return turtle.select(wantSlot), { slot = wantSlot }
  end
  local want = a and a.name
  if not want then return false, "需要 name=物品注册名 或 slot=槽位" end
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and d.name == want then
      turtle.select(i)
      return true, { slot = i, name = want, count = turtle.getItemCount(i) }
    end
  end
  return false, "背包里没有：" .. tostring(want)
end

-- 采集掉落物：吸上/下/前；turn=1 时再转身覆盖四个水平方向。
-- 返回"背包物品总数增量"，这是"到底捡到没有"的硬指标。
ACT.gather = function(a)
  local rounds = tonumber(a and a.rounds) or 1
  local spin = truthy(a and a.turn, false)
  local before = invCount()
  for _ = 1, rounds do
    pcall(turtle.suckUp); pcall(turtle.suckDown); pcall(turtle.suck)
    if spin then
      for _ = 1, 4 do
        ACT.turn_right({})
        pcall(turtle.suck)
      end
    end
    sleep(0.3)
  end
  local after = invCount()
  return true, { picked = after - before, inv_total = after }
end

-- 合成：**需要海龟带合成升级（Crafty Turtle）**，否则 turtle.craft 为 nil。
-- 依据：CC 的 ROM 程序 turtle/craft.lua 里 `if not turtle.craft then print("Requires a Crafty Turtle")`。
ACT.craft = function(a)
  if not turtle.craft then
    return false, "本海龟没有合成升级（Crafty Turtle）：把【工作台】放进它的背包，再 equip <槽位> left"
  end
  local limit = tonumber(a and a.limit) or 1
  local before = invCount()
  local ok, err = turtle.craft(limit)
  local after = invCount()
  return ok, {
    crafted = after - before,
    inv_total = after,
    err = (not ok) and tostring(err) or nil,
  }
end

-- 一边向上挖一边上升，直到上方不再是指定方块（砍树主干用）。
-- 为什么做成复合动作：砍一根 6 格的树干，若靠"挖→爬"逐条下发要十几轮往返，
-- 一次往返 3~5 秒，人（和 Agent）都受不了。
ACT.dig_up_while = function(a)
  local want = a and a.name
  if not want then return false, "需要 name=方块注册名（例如 minecraft:oak_log）" end
  local maxN = tonumber(a and a.max) or 32
  local dug, moved = 0, 0
  local stopReason = "上方不是目标方块"
  for _ = 1, maxN do
    local ok, data = turtle.inspectUp()
    if not ok or not data then stopReason = "上方没有方块"; break end
    if data.name ~= want then stopReason = "上方是 " .. tostring(data.name); break end
    if not turtle.digUp() then stopReason = "挖不动（工具/权限？）"; break end
    dug = dug + 1
    if not moveOne(turtle.up) then stopReason = "无法上升（被挡）"; break end
    moved = moved + 1
  end
  return true, { dug = dug, moved = moved, stop = stopReason }
end

-- 装备升级（工作台 / 调制解调器 / 扬声器等）。
-- 等价于 ROM 程序 equip.lua 的 `equip <slot> <side>`，但做成**可远程下发**的动作
-- （否则每次装升级都得人到海龟面前敲命令；本次给海龟装合成升级就卡在这）。
ACT.equip = function(a)
  local slot = tonumber(a and a.slot)
  local side = (a and a.side) or "left"
  local item = a and a.name
  if not slot and item then
    local ok, r = ACT.select_item({ name = item })
    if not ok then return false, tostring(r) end
    slot = r.slot
  end
  if not slot then return false, "需要 slot= 或 name=" end
  if slot < 1 or slot > 16 then return false, "slot 需为 1..16" end
  local fn = (side == "right") and turtle.equipRight or turtle.equipLeft
  if not fn then return false, "该海龟不支持 equip" end
  turtle.select(slot)
  local before = turtle.getItemCount(slot)
  local detail = turtle.getItemDetail(slot)          -- ★ 装之前先记住是哪件物品 ✓
  local ok, err = fn()
  local after = turtle.getItemCount(slot)
  if not ok then return false, "装备失败（这件物品可能不是升级）：" .. tostring(err) end
  -- ★ 记账（见文件头"升级槽记账文件"注释 ✓）：1.116 以下读不出升级槽 ✗ 只能自己记 ✓
  equipState[side] = detail and detail.name or nil
  saveEquipState()
  return true, { side = side, slot = slot, item = equipState[side],
                 count_before = before, count_after = after,
                 swapped = (after > 0), has_craft = (turtle.craft ~= nil),
                 state = equipState }
end

ACT.unequip = function(a)
  local side = (a and a.side) or "left"
  local fn = (side == "right") and turtle.equipRight or turtle.equipLeft
  if not fn then return false, "该海龟不支持 equip" end
  for i = 1, 16 do
    if turtle.getItemCount(i) == 0 then
      turtle.select(i)
      if fn() then
        -- ⚠ 记账要记**拆完之后那一侧是什么** ✗ —— 拆完就是**空的** ✓
        --   真实事故（2026-09-18 深夜）：这里原来记的是"被换下来的那件物品" ✗
        --   → 状态文件说右边还装着工作台 ✓ 而实际已经空了 ✗
        --   → 之后所有依赖"我挖得动什么 / 我现在装的是什么"的判断全部失真 ✗
        local returned = turtle.getItemDetail(i) and turtle.getItemDetail(i).name or nil
        equipState[side] = nil
        saveEquipState()
        return true, { side = side, slot = i, returned_item = returned, state = equipState }
      end
    end
  end
  return false, "没有空槽位可卸载"
end

-- 自我更新（海龟端）：拉最新 worker → **语法自检** → 覆盖本地副本 →（由主循环）重启计算机。
-- 目的：Agent 改完代码后**不需要人进游戏手动重载**（本项目最大的效率瓶颈）。
-- 语法自检保证"宁可不更新，也不把机器刷成砖"。
ACT.self_update = function(a)
  local remote = (a and a.name) or "turtle_worker.lua"
  -- ⚠ 不能用 a.local：`local` 是 Lua 保留字 ✗（会报 `<name> expected near 'local'`）
  local target = (a and a.localname) or "worker_local"
  local ok, res = pcall(http.get, tostring(cfg.gateway) .. "/files/" .. remote)
  if not ok or not res then return false, "下载失败：" .. tostring(res) end
  local src = res.readAll()
  res.close()
  if not src or #src < 100 then return false, "内容过短，放弃更新" end
  local fn, lerr = load(src, remote, "t", _ENV)
  if not fn then return false, "新版本语法错误，已放弃更新：" .. tostring(lerr) end
  local f = fs.open(target, "w")
  if not f then return false, "无法写入 " .. target end
  f.write(src)
  f.close()
  return true, { updated = target, bytes = #src, note = "回报后重启计算机以载入新版本" }
end

-- 运行作业脚本：从网关取一个作业脚本、在本地执行 —— **一个作业 = 一条指令**。
-- 这是"把智能放进游戏内"的关键：Agent 只写脚本 + 发一条启动指令，
-- 具体动作由脚本在游戏内自主完成（往返越少，失败机会越少）。
ACT.run_job = function(a)
  local name = a and a.name
  if not name then return false, "需要 name=<作业脚本名>（网关 /files/ 下的文件）" end
  local ok, res = pcall(http.get, tostring(cfg.gateway) .. "/files/" .. name)
  if not ok or not res then return false, "下载作业失败：" .. tostring(res) end
  local src = res.readAll()
  res.close()
  if not src or #src < 10 then return false, "作业内容为空" end
  local fn, lerr = load(src, name, "t", _ENV)
  if not fn then return false, "作业脚本语法错误：" .. tostring(lerr) end
  local ok2, r1, r2 = pcall(fn, a)
  if not ok2 then return false, "作业执行异常：" .. tostring(r1) end
  return r1, r2
end

-- 砍树（复合动作）：四周找原木 → 挖掉 → 进去 → 一路向上挖到顶 → 退回原高度 → 收掉落物。
--
-- 为什么必须做成"一条指令"（真实教训）：
--   拆成"转身/查看/挖/前进/上爬..."十几条独立指令时，
--   rednet 在偏慢或丢包的情况下会出现"指令执行了、回包丢了"，
--   Agent 侧只能看到超时，既无法确认也无法安全重试 ✗。
--   合成一条指令后，游戏内一次跑完，只回报一次结果 —— 稳定得多。
ACT.chop_log = function(a)
  local want  = (a and a.name) or "minecraft:oak_log"
  local maxUp = tonumber(a and a.max) or 32
  local scan  = {}

  -- 1) 四周找目标方块（每转一次右，看一次前方；最多转 3 次）
  local found = false
  for i = 0, 3 do
    if i > 0 then turtle.turnRight(); facingIdx = facingIdx % 4 + 1 end
    local ok, data = turtle.inspect()
    local name = (ok and data) and data.name or nil
    scan[#scan + 1] = { turn = i, block = name }
    if name == want then found = true; break end
  end
  if not found then
    return false, "四周没有找到 " .. tostring(want) .. "（已扫描 4 个方向）", { scan = scan }
  end

  -- 2) 挖掉并进入
  if not turtle.dig() then
    return false, "挖不动（工具/权限限制？）", { scan = scan }
  end
  local okFwd, fwdErr = ACT.forward({ n = 1, allow_dig = 1 })
  if not okFwd then
    return false, "挖开后无法前进：" .. tostring(fwdErr), { scan = scan }
  end

  -- 3) 向上挖，直到上方不再是目标方块
  local dug, climbed, stop = 0, 0, "上方不是目标方块"
  for _ = 1, maxUp do
    local ok, data = turtle.inspectUp()
    if not ok or not data then stop = "上方没有方块"; break end
    if data.name ~= want then stop = "上方是 " .. tostring(data.name); break end
    if not turtle.digUp() then stop = "挖不动"; break end
    dug = dug + 1
    if not moveOne(turtle.up) then stop = "无法上升"; break end
    climbed = climbed + 1
  end

  -- 4) 退回原高度（climbed 格）
  local back = 0
  for _ = 1, climbed do
    if moveOne(turtle.down) then back = back + 1 else break end
  end

  -- 5) 收掉落物
  local before = invCount()
  pcall(turtle.suckUp); pcall(turtle.suckDown); pcall(turtle.suck)
  for _ = 1, 4 do
    ACT.turn_right({})
    pcall(turtle.suck)
  end
  sleep(0.3)
  local after = invCount()

  return true, {
    chopped = dug, climbed = climbed, descended = back, stop = stop,
    gathered = after - before, inv_total = after,
    scan = scan, fuel = turtle.getFuelLevel(),
  }
end

-- 连续铺一行（用于开平台）：每格放下方块后前进一格。
-- 注意：放置需要相邻有方块可依附（和玩家一样），从岛边缘往外铺时要一格一格来。
ACT.place_row = function(a)
  local n = tonumber(a and a.n) or 1
  local dir = a and a.dir
  local up = truthy(a and a.place_up, false)
  local placed, failed = 0, 0
  for i = 1, n do
    local ok
    if up then ok = turtle.placeUp() else ok = turtle.placeDown() end
    if ok then placed = placed + 1 else failed = failed + 1 end
    if i < n then
      if dir then
        local idx = ({ north = 1, east = 2, south = 3, west = 4 })[dir]
        if idx then turnToIdx(idx) end
      end
      local okm, e = ACT.forward({ n = 1, allow_dig = 0 })
      if not okm then
        return false, "第 " .. i .. " 格后前进受阻：" .. tostring(e),
          { placed = placed, failed = failed }
      end
    end
  end
  return true, { placed = placed, failed = failed }
end

ACT.tunnel = function(a)
  local len = tonumber(a.length) or 4
  local i = a.dir and ({ north = 1, east = 2, south = 3, west = 4 })[a.dir]
  if i then
    if not facingKnown then autoCalibrate() end
    turnToIdx(i)
  end
  for k = 1, len do
    if fallRisk(a) then
      return false, "第 " .. k .. " 格：下方无方块（require_ground=1 时拒绝前进）"
    end
    local ok, e = moveOne(turtle.forward, turtle.dig)
    if not ok then return false, "第 " .. k .. " 格：" .. tostring(e) end
    pcall(turtle.digUp); pcall(turtle.dig)
  end
  return true, { length = len }
end

ACT.mine_column = function(a)
  local depth = tonumber(a.depth) or 5
  local dug = 0
  for _ = 1, depth do
    if not moveOne(turtle.down, turtle.digDown) then break end
    pcall(turtle.dig); dug = dug + 1
  end
  return true, { dug = dug }
end

-- 把连续坐标吸附到"所在方块的中心"。
-- 为什么需要：GPS 噪声实测 0.5~0.7 格（同一时刻两个读数能差 0.7），
-- 若直接用连续坐标和 0.6 的容差判断"到没到"，海龟会**来回抖动走不到**（真实踩过：
-- goto 走了 6 步仍未抵达）。吸附到方块后，判定粒度是 1 格，噪声折半就不会误判。
local function blockCenter(v) return math.floor(v) + 0.5 end

-- goto x y z：走到目标方块（需要 GPS）。
-- 每步重新定位（3 次采样取中位数），按**方块**判定是否抵达，并带"没进展就停"保护。
-- 安全默认：不挖（allow_dig 默认 0）；可悬空（海龟不受重力）。
-- 轴约定与 MC 一致：-z = north，+x = east，+z = south，-x = west。
ACT.goto = function(a)
  local tx, ty, tz = tonumber(a and a.x), tonumber(a and a.y), tonumber(a and a.z)
  if not (tx and ty and tz) then return false, "需要 x y z 三个坐标" end
  -- 朝向未知就先自测（启动时不测，避免刚启动无法响应 rednet）
  local cal = nil
  if not facingKnown then
    local okc, cres = autoCalibrate()
    cal = { ok = okc, detail = cres }
    if not okc then
      return false, "朝向未知且自动测定失败：" .. tostring(cres), { calibrate = cal }
    end
  end
  local maxSteps = tonumber(a and a.max_steps) or 40
  local tbx, tby, tbz = blockCenter(tx), blockCenter(ty), blockCenter(tz)
  local mv = { n = 1, allow_dig = a and a.allow_dig, require_ground = a and a.require_ground }
  if mv.allow_dig == nil then mv.allow_dig = 0 end        -- 导航默认不挖

  local steps, stuck, lastDist = 0, 0, nil
  local trace = {}
  while steps < maxSteps do
    local x, y, z = locateMedian(3, 2)
    if not x then return false, "GPS 定位失败，导航中止（已走 " .. steps .. " 步）" end
    local cx, cy, cz = blockCenter(x), blockCenter(y), blockCenter(z)
    local here = { x = x, y = y, z = z, block = { cx, cy, cz } }
    if #trace < 16 then trace[#trace + 1] = here end

    if cx == tbx and cy == tby and cz == tbz then
      return true, { steps = steps, pos = { x = x, y = y, z = z }, trace = trace, calibrate = cal }
    end

    -- 进度保护：连续 3 步没有靠近目标就停（避免在被挡住/噪声过大时死循环）
    local dist = math.abs(tbx - cx) + math.abs(tby - cy) + math.abs(tbz - cz)
    if lastDist ~= nil and dist >= lastDist then stuck = stuck + 1 else stuck = 0 end
    lastDist = dist
    if stuck >= 3 then
      return false, "连续 3 步没有靠近目标（已走 " .. steps .. " 步，停在 " ..
        string.format("%.2f,%.2f,%.2f", x, y, z) .. "；目标方块 " ..
        string.format("%d,%d,%d", math.floor(tbx), math.floor(tby), math.floor(tbz)) ..
        "；当前朝向 " .. tostring(facingKnown and FACING[facingIdx] or "unknown") ..
        "）—— 可能被挡住、朝向不准或 GPS 偏差过大", { trace = trace }
    end

    if cy ~= tby then
      local ok, e = (tby > cy) and ACT.up(mv) or ACT.down(mv)
      if not ok then return false, "y 方向受阻（已走 " .. steps .. " 步）：" .. tostring(e), { trace = trace } end
    else
      local ddx, ddz = tbx - cx, tbz - cz
      -- 先走差距大的轴；若那一轴被挡住，就试另一轴
      -- （斜向目标在杂乱地形里很常见，只试一轴容易"明明另一条路能走却失败"）
      local order = (math.abs(ddx) >= math.abs(ddz)) and { "x", "z" } or { "z", "x" }
      local moved, lastErr = false, nil
      for _, ax in ipairs(order) do
        local d = (ax == "x") and ddx or ddz
        if d ~= 0 then
          local want
          if ax == "x" then want = (d > 0) and 2 or 4 else want = (d > 0) and 3 or 1 end
          turnToIdx(want)
          local ok, e = ACT.forward(mv)
          if ok then moved = true; break end
          lastErr = e
        end
      end
      if not moved then
        return false, "两个轴都被挡住了（已走 " .. steps .. " 步）：" .. tostring(lastErr), { trace = trace }
      end
    end
    steps = steps + 1
  end
  return false, "达到最大步数仍未抵达（max_steps=" .. maxSteps .. "）", { trace = trace }
end

--------------------------------------------------------------------------------
-- 自动测定朝向（**必须**：worker 重启会丢掉内存里的朝向）
-- 真实事故：重启后 facingIdx 复位成"未知/北"，而 turnToIdx 仍按旧假设转向，
--   于是 goto 目标在东边、它却一路往西走了 3 格（方向整体反了）。
-- 做法：GPS 记位置 → 走一步（不挖；被挡就转 90° 再试，最多 4 个方向）→ 量位移
--   → 走回来（净位移 0）→ 由位移方向反推"前进"对应世界的哪个方向，写入 facingIdx。
--------------------------------------------------------------------------------
autoCalibrate = function()
  local x0, _, z0 = locateMedian(3, 2)
  if not x0 then return false, "GPS 不可用，无法自动测定朝向" end
  -- 走 2 格而不是 1 格：位移 Δ≈2 对上 GPS 0.7 格噪声才稳；
  -- 走 1 格（Δ≈1）时噪声足以判错轴向（真实踩过：两次自测得出 west / north 不一致）。
  local STEPS = 2
  local moved = false
  for i = 0, 3 do
    if i > 0 then ACT.turn_right({}) end
    if ACT.forward({ n = STEPS, allow_dig = 0 }) then moved = true; break end
  end
  if not moved then return false, "四个方向都被挡住，无法测定朝向（请挪到开阔处）" end
  local x1, _, z1 = locateMedian(3, 2)
  ACT.back({ n = STEPS, allow_dig = 0 })          -- 退回原位，净位移为 0
  local dx, dz = x1 - x0, z1 - z0
  if math.max(math.abs(dx), math.abs(dz)) < 1.0 then
    return false, "位移过小（GPS 噪声），无法判定朝向"
  end
  local dir
  if math.abs(dx) >= math.abs(dz) then dir = (dx > 0) and "east" or "west"
  else dir = (dz > 0) and "south" or "north" end
  for i, d in ipairs(FACING) do if d == dir then facingIdx = i end end
  facingKnown = true
  return true, { facing = dir, dx = dx, dz = dz }
end

ACT.calibrate_auto = function() return autoCalibrate() end

--------------------------------------------------------------------------------
-- 主循环
--------------------------------------------------------------------------------
print("[worker] 就绪  id=" .. os.getComputerID() .. "  role=" .. ROLE .. "  chan=" .. CHAN)
-- 说明：这里**不再**在启动时自动测向。
-- 原因：测向要占住 GPS 与移动约 8 秒，这段时间 worker 无法回应 rednet，
--   用户一重启就发指令必然超时（真实踩过）。
-- 改成"首次真正需要方向时再测"（goto / tunnel 内部会调用），启动即可立刻响应。

--------------------------------------------------------------------------------
-- 自安装开机自启（依据 CC 的 ROM startup.lua：根目录的 startup 文件每次开机自动运行）
-- 目的：让"重启游戏后忘记重新跑 worker"这件事不再发生 —— 跑一次即永久自动。
-- 可用 worker.cfg 里的 autostart=0 关掉。
--------------------------------------------------------------------------------
if truthy(cfg.autostart, true) then
  local line = 'shell.run("wget", "run", "' .. tostring(cfg.gateway) .. '/files/turtle_worker.lua")'
  local cur = ""
  if fs.exists("startup") then
    local f0 = fs.open("startup", "r")
    if f0 then cur = f0.readAll() or ""; f0.close() end
  end
  if cur:find(line, 1, true) then
    print("[worker] 开机自启：已存在，无需重复写入")
  else
    local f1 = fs.open("startup", "w")
    if f1 then
      if #cur > 0 then
        f1.write(cur)
        if cur:sub(-1) ~= "\n" then f1.write("\n") end
      end
      f1.write(line .. "\n")
      f1.close()
      print("[worker] 开机自启：已写入 startup —— 以后开机自动运行")
    else
      print("[worker] 开机自启：写入失败（磁盘只读？）")
    end
  end
end

while true do
  local sender, msg = rednet.receive("bridge")
  if type(msg) == "table" and msg.cmd then
    local fn = ACT[msg.cmd]
    local ok, result
    if not fn then
      ok, result = false, "未知指令：" .. tostring(msg.cmd)
    else
      -- 注意：动作函数统一返回 (ok, detail)，所以 pcall 的返回值是 (callOk, ok, detail)
      local callOk, r1, r2 = pcall(fn, msg.args or {})
      if callOk then
        ok, result = r1, r2
      else
        ok, result = false, "执行异常：" .. tostring(r1)
      end
    end
    rednet.send(sender, { ok = ok, result = result, id = msg.id }, "bridge_reply")

    -- 自我更新成功后重启计算机（先确保回包已经发出，否则 Agent 那边只会看到超时 ✗）
    if msg.cmd == "self_update" and ok then
      sleep(1)
      print("[worker] rebooting to load the new version...")
      os.reboot()
    end
  end
end
