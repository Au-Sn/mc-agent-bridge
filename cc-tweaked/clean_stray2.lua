-- clean_stray2.lua —— 只用 CC 标准 API 的"自主导航 + 回收"
--
-- 为什么重写（上一版第一行就崩了 ✗）：
--   `ACT` 是 worker 的**局部表** ✓ 作业脚本拿到的是全局环境 ✓ 看不到它 ✗
--   → 所以脚本里只能自己实现导航 ✓ 标准 API 足够：`gps.locate()` + `turtle.forward/up/down/turnX` ✓
--
-- 自校准思路（可复用 ✓）：
--   不知道朝向时 → **先前进一格** ✓ 再定位一次 ✓ 坐标差 = "前方"的方向向量 ✓ 然后退回来 ✓
--   之后按右手系旋转维护 4 个方向 ✓：右转 (dx,dz) → (-dz,dx) ✓
--
-- 下发：{"who":"cc0","cmd":"run_job","args":{"target":1,"name":"clean_stray2.lua"}}

local x0 = tonumber(a and a.x0) or 4109
local x1 = tonumber(a and a.x1) or 4121
local y  = tonumber(a and a.y)  or 70
local z  = tonumber(a and a.z)  or 1

local function loc()
  local ok, a1, b1, c1 = pcall(gps.locate, 3)
  if ok and a1 and b1 and c1 then return a1, b1, c1 end
  return nil
end

local out = { cells = {}, dug = 0, collected = 0 }

-- 进度日志写到磁盘 ✓
-- 为什么必须写（我自己违反过的规矩 ✓）：长作业一旦跑起来 ✓ 海龟的 rednet 就被自己占住 ✗
-- → 外面只能看到"无响应" ✗ 完全分不清"在推进"和"卡死" ✗
-- 而**磁盘是唯一不会被丢包影响的通道** ✓ → 每处理一格就追加一行 ✓ 外面直接读文件 ✓
local LOG = "clean_stray.log"
local function note(s)
  local f = fs.open(LOG, "a")
  if f then f.writeLine(tostring(os.epoch and os.epoch("utc") or os.time()) .. " " .. s); f.close() end
end
note("START x0=" .. x0 .. " x1=" .. x1 .. " y=" .. y .. " z=" .. z)

-- 0) **先脱离原地再校准** ✓
--    真实教训：它停在平台角落 ✓ 旁边是玩家的墙与花盆 ✓ → `turtle.forward()` 直接失败 ✗
--    → 自校准拿不到"前方"向量 ✓ 整个作业第一行就退出 ✓（所以先往上飞到开阔空域 ✓）
local climbed = 0
for _ = 1, 6 do
  if turtle.up() then climbed = climbed + 1 else break end
end
out.climbed = climbed

-- 自校准：拿到"前方"向量；某个方向被挡就转 90° 再试 ✓（最多试 4 个方向）
local fx, fz
do
  local base = { loc() }
  if not base[1] then out.error = "GPS 定位失败"; return false, out end
  for _ = 1, 4 do
    if turtle.forward() then
      local p = { loc() }
      if p[1] then fx = p[1] - base[1]; fz = p[3] - base[3] end
      turtle.back()
      if fx and (fx ~= 0 or fz ~= 0) then break end
    end
    turtle.turnRight()
  end
end
if not fx or (fx == 0 and fz == 0) then
  out.error = "无法自校准朝向（前进失败或定位没变化）"
  out.home = home
  return false, out
end
out.forward_vec = { fx, fz }

-- 2) 四个方向（右转 = (-dz, dx)）
local dirs = {}
do
  local d = { fx, fz }
  for i = 1, 4 do dirs[i] = { d[1], d[2] }; d = { -d[2], d[1] } end
end
local hd = 1

local function turnR() turtle.turnRight(); hd = hd % 4 + 1 end

local function faceTo(vx, vz)
  for _ = 1, 4 do
    if dirs[hd][1] == vx and dirs[hd][2] == vz then return true end
    turnR()
  end
  return false
end

-- 3) 定点导航（先对齐 y ✓ 再水平 ✓ 两个轴都试 ✓ 有防卡死 ✓）
local function goTo(tx, ty, tz, budget)
  budget = budget or 140
  for _ = 1, budget do
    local x, yy, zz = loc()
    if not x then return false, "导航中定位失败" end
    if x == tx and yy == ty and zz == tz then return true end
    if yy < ty then
      if not turtle.up() then return false, "上升被挡" end
    elseif yy > ty then
      if not turtle.down() then return false, "下降被挡" end
    else
      local dx, dz = tx - x, tz - zz
      local first = (math.abs(dx) >= math.abs(dz)) and "x" or "z"
      local order = { first, (first == "x") and "z" or "x" }
      local moved = false
      for _, ax in ipairs(order) do
        local del = (ax == "x") and dx or dz
        if del ~= 0 then
          local vx = (ax == "x") and ((del > 0) and 1 or -1) or 0
          local vz = (ax == "z") and ((del > 0) and 1 or -1) or 0
          faceTo(vx, vz)
          if turtle.forward() then moved = true; break end
        end
      end
      if not moved then return false, "水平被挡" end
    end
  end
  return false, "步数用尽"
end

-- 4) 逐格回收
for x = x0, x1 do
  local okG, why = goTo(x, y + 1, z)
  if not okG then
    out.cells[#out.cells + 1] = { x = x, ok = false, why = why }
  else
    local okI, data = turtle.inspectDown()
    local nm = okI and data and data.name or nil
    local dug, got = false, false
    if nm and nm:find("planks") then
      dug = turtle.digDown()
      if dug then got = turtle.suckDown() end
    end
    if dug then out.dug = out.dug + 1 end
    if got then out.collected = out.collected + 1 end
    out.cells[#out.cells + 1] = { x = x, ok = true, below = nm, dug = dug, got = got }
    note("x=" .. x .. " below=" .. tostring(nm) .. " dug=" .. tostring(dug) .. " got=" .. tostring(got))
  end
end

out.inv = {}
for slot = 1, 16 do
  local d = turtle.getItemDetail(slot)
  if d then out.inv[#out.inv + 1] = { slot = slot, name = d.name, count = d.count } end
end
out.fuel = turtle.getFuelLevel()
local ex, ey, ez = loc()
out.end_pos = ex and { x = ex, y = ey, z = ez } or nil

return true, out
