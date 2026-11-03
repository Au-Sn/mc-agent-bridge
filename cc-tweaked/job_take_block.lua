-- job_take_block.lua —— 让海龟**精确地**取走"指定的那一格方块"（放下→挖掉→吸走）
--
-- 为什么需要它（2026-09-18 晚的真实需求）：
--   玩家愿意把"第一个工作台"**放在地上**给海龟 ✓ 那海龟就需要一个动作：
--   "走过去 → 确认那一格确实是我要的东西（**先 inspect ✓ 不确认就不挖 ✗**）→ 挖掉 → 把掉落物吸回来" ✓
--   ⚠ 绝不能"朝四面乱挖" ✗ —— 那一带是**玩家的树**（原木+树冠 ✓）和他的平台 ✓
--     "挖错东西"是不可逆的 ✗ 所以本作业**只挖点名的那一格** ✓
--
-- 参数：x/y/z = 目标方块坐标（必填 ✓）want = 该方块名字里应含的片段（默认 crafting_table ✓）
--       recover = true 时，挖完前把丢在附近的东西也吸一遍（默认 true ✓）

local a = ...
local TX = tonumber(a and a.x)
local TY = tonumber(a and a.y)
local TZ = tonumber(a and a.z)
local WANT = (a and a.want) or "crafting_table"
if not (TX and TY and TZ) then
  return true, { job = "take_block", ok = false, why = "需要 x/y/z" }
end

local LOG = "take_block.log"
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
  return false, "四个方向都走不动"
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

log(string.format("=== START take_block 目标 (%d,%d,%d) want=%s ===", TX, TY, TZ, WANT))

local okC, errC = calibrate()
if not okC then
  log("标定失败：" .. tostring(errC))
  return true, { job = "take_block", ok = false, why = errC }
end

-- ① 先站到目标**旁边**（同一层，水平相邻一格：x 优先，其次 z）
local cx = select(1, locate())
if not cx then return true, { job = "take_block", ok = false, why = "GPS 丢失" } end
-- 目标必须在正前方：先对齐 y，再走到与目标相邻的那一格
local function stepTo(tx, tz)
  for _ = 1, 40 do
    local ax, ay, az = locate()
    if not ax then return false, "GPS 丢失" end
    if ax == tx and az == tz then return true end
    local wx, wz = 0, 0
    if ax ~= tx then wx = (tx > ax) and 1 or -1 else wz = (tz > az) and 1 or -1 end
    local moved = false
    for _ = 1, 4 do
      if facing[1] == wx and facing[2] == wz then moved = turtle.forward(); break end
      turnRight()
    end
    if not moved then return false, string.format("走到 (%d,%d,%d) 就过不去了", ax, ay, az) end
  end
  return false, "步数超限"
end

local cy = select(2, locate())
while cy and cy > TY do
  if not turtle.down() then break end
  cy = select(2, locate())
end
while cy and cy < TY do
  if not turtle.up() then break end
  cy = select(2, locate())
end
cx, cy = locate()
if cy ~= TY then
  log(string.format("高度没对齐：我在 y=%s，目标 y=%d", tostring(cy), TY))
  return true, { job = "take_block", ok = false, why = "y 对不齐", at = { cx, cy, select(3, locate()) } }
end

-- 站在目标的西侧或北侧相邻格，然后转过去面对它
local standX, standZ = TX - 1, TZ
local okS, errS = stepTo(standX, standZ)
if not okS then
  -- 退而求其次：站到北侧
  okS, errS = stepTo(TX, TZ - 1)
  standX, standZ = TX, TZ - 1
end
if not okS then
  log("走不到目标旁边：" .. tostring(errS))
  return true, { job = "take_block", ok = false, why = errS }
end

-- ② 转向目标，并用 inspect **确认那一格确实是要的东西**（不确认绝不挖 ✗）
local fx, fz = locate()
local want = { TX - fx, TZ - fz }
local turned = false
for _ = 1, 4 do
  if facing[1] == want[1] and facing[2] == want[2] then turned = true; break end
  turnRight()
end
if not turned then
  return true, { job = "take_block", ok = false, why = "转不到目标方向" }
end

local hasBlock, info = turtle.inspect()
log("前方方块：" .. tostring(hasBlock) .. " / " .. tostring(info and info.name))
if not hasBlock or not info or not tostring(info.name):find(WANT, 1, true) then
  log("前方不是 " .. WANT .. " ✗ —— 按纪律**不挖** ✓")
  return true, { job = "take_block", ok = false,
                 why = "前方不是目标方块：" .. tostring(info and info.name),
                 at = { fx, TY, fz } }
end

local dug, dugErr = turtle.dig()
log("挖掉：" .. tostring(dug) .. " / " .. tostring(dugErr))
sleep(0.4)
for _ = 1, 3 do
  if turtle.suck() then break end
  sleep(0.3)
end

local slot, name = hasWant()
local gx, gy, gz = locate()
log("结束：拿到 " .. tostring(name) .. " @槽 " .. tostring(slot) .. " | 背包: " .. invList())
return true, {
  job = "take_block", ok = (slot ~= nil),
  dug = dug, dug_err = dugErr,
  got_slot = slot, got_name = name,
  inventory = invList(),
  at = { x = gx, y = gy, z = gz },
}
