-- job_suck_around.lua —— 把海龟**周围六个方向**的掉落物全部吸进来（"吸尘器"）
--
-- 为什么需要它（2026-09-18 晚）：
--   玩家把工作台丢给假人 ✓ 假人捡到了 ✓ 但它落在**主背包**
--   （`/player` 的动作表里只有 `hotbar`（选快捷栏）✗ 没有"把某格挪到手上" ✗
--     而 `drop`/`dropStack` 只能丢**手持**的那一格 ✗）→ 假人**没法把它交出来** ✗
--   ⇒ 换一条**诚实的游戏机制**：让假人用生存模式死亡把背包掉在地上 ✓
--     （不是指令凭空造物 ✓ 物品是**掉落**的 ✓）然后**海龟自己把地上的东西吸走** ✓✓
--
-- 它同时是一个通用能力 ✓：以后玩家丢任何东西给海龟、或海龟自己挖出来的掉落物
--   散在四周时，都用这一条指令收干净 ✓（CC 的 suck 只覆盖**相邻一格** ✓
--   所以必须"转一圈 + 上下都试" ✓ 这是踩过的细节 ✓）
--
-- 参数：
--   want = 目标物品名片段（默认 minecraft:crafting_table ✓ 一旦吸到就提前结束 ✓）
--   passes = 最多转几圈（默认 4 ✓）

local a = ...
local WANT = (a and a.want) or "minecraft:crafting_table"
local PASSES = tonumber(a and a.passes) or 4

local LOG = "suck_around.log"
local function log(s)
  print(s)
  local f = fs.open(LOG, "a")
  if f then f.writeLine(os.date("%H:%M:%S ") .. tostring(s)); f.close() end
end

local function locate()
  local x, y, z = gps.locate(2)
  if not x then return nil end
  return math.floor(x), math.floor(y), math.floor(z)
end

local facing = { 0, 1 }
local function turnRight()
  turtle.turnRight()
  facing = { -facing[2], facing[1] }
end

-- 标定 forward 的绝对方向：**四个方向都试** ✓（真实事故：只试 forward 会在被夹住时失败 ✗）
local function calibrate()
  for attempt = 1, 2 do
    for _ = 1, 4 do
      local ax, ay, az = locate()
      if not ax then return false, "GPS 不可用" end
      if turtle.forward() then
        local bx, by, bz = locate()
        if not bx then return false, "标定途中 GPS 丢失" end
        local dx, dz = bx - ax, bz - az
        if dx ~= 0 or dz ~= 0 then facing = { dx, dz }; return true end
        return false, "走了但坐标没变"
      end
      turnRight()
    end
    if attempt == 1 then for _ = 1, 3 do turtle.up() end end
  end
  return false, "四个方向都走不动，无法标定朝向"
end

local function hasWant()
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and tostring(d.name):find(WANT, 1, true) then return i, d.name end
  end
  return nil
end

local function invList()
  local out = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d then out[#out + 1] = string.format("%d:%s x%d", i, d.name, turtle.getItemCount(i)) end
  end
  return table.concat(out, ", ")
end

log("=== START suck_around want=" .. WANT .. " ===")
local pre = hasWant()
if pre then
  log("本来就有（槽 " .. pre .. "）→ 直接收工")
  return true, { job = "suck_around", ok = true, already = true, slot = pre, inventory = invList() }
end

local okC, errC = calibrate()
if not okC then
  log("标定失败：" .. tostring(errC))
  return true, { job = "suck_around", ok = false, why = errC }
end

local sucked = 0
local found, foundName = nil, nil
for pass = 1, PASSES do
  for dir = 1, 4 do
    if turtle.suck()     then sucked = sucked + 1 end
    if turtle.suckUp()   then sucked = sucked + 1 end
    if turtle.suckDown() then sucked = sucked + 1 end
    found, foundName = hasWant()
    if found then break end
    turnRight()
    sleep(0.15)
  end
  if found then break end
  sleep(0.3)
end

local cx, cy, cz = locate()
log(string.format("吸了 %d 次；背包: %s", sucked, invList()))
log("=== END found=" .. tostring(found) .. " (" .. tostring(foundName) .. ") ===")
return true, {
  job = "suck_around", ok = (found ~= nil),
  want = WANT, found_slot = found, found_name = foundName,
  sucks = sucked, inventory = invList(),
  at = { x = cx, y = cy, z = cz },
}
