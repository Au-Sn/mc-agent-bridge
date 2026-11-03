-- job_clean_row.lua —— 回收"误放的一行木板"（(4109..4121, 70, 1)），木板要**吸回背包** ✓
--
-- 为什么写成"作业脚本"而不是远程一条条下发：
--   13 格 × (走位 + 挖 + 吸) ≈ 40 个动作 ✗ —— 远程逐条下发要 40 多次往返 ✗
--   在游戏内跑则**只占一次通道** ✓（作业脚本 / 肌肉记忆的价值就在这里 ✓）
--
-- 本脚本自带的安全措施（不需要外部盯着）：
--   1. **只信 GPS 的闭环** ✓：朝向未知也没关系 ✓（先"试走一步"标定 forward 的绝对方向 ✓）
--   2. 每格先 inspectDown 确认**确实是原木/木板** ✓ 不是就跳过 ✗（绝不乱挖 ✓）
--   3. 挖完立刻 suckDown 把掉落物吸回来 ✓（这一行**下面就是虚空** ✓ 慢一步就没了 ✗）
--   4. 每 4 格用 GPS 复核一次位置 ✓ 偏了就修 ✗（GPS 偶尔给坏解 ✓ 不能全程裸信航位推算 ✓）
--   5. 返回一份**可验收**的摘要（挖了几格 / 跳过几格 / 物品总数前后）✓
--
-- 参数（可省）：cells = 目标格数（默认 13 ✓）

local a = ...                      -- run_job 会把参数表传进来 ✓
local X0, X1, Y, Z = 4109, 4121, 70, 1

local n = tonumber(a and a.count) or (X1 - X0 + 1)

-- ── 定位（GPS ✓ 取整）──────────────────────────────────────────────────────
local function locate()
  local x, y, z = gps.locate(2)
  if not x then return nil end
  return math.floor(x), math.floor(y), math.floor(z)
end

-- ── 标定 forward 的绝对方向（(dx,dz) ✓ 不猜朝向 ✗）─────────────────────────
local facing = { 0, 1 }
local function calibrate()
  local ax, ay, az = locate()
  if not ax then return false, "GPS 不可用（先确认 4 台基站都在跑）" end
  if not turtle.forward() then return false, "前方被挡，无法标定朝向" end
  local bx, by, bz = locate()
  if not bx then return false, "标定途中 GPS 丢失" end
  local dx, dz = bx - ax, bz - az
  if dx == 0 and dz == 0 then return false, "走了但坐标没变：GPS 解有问题" end
  facing = { dx, dz }
  return true
end

-- 右转 90°：实测约定 (dx,dz) -> (-dz,dx) ✓（yaw 顺时针 ✓）
local function turnRight()
  turtle.turnRight()
  facing = { -facing[2], facing[1] }
end

-- ── 走到 (tx, tz)：每步都读 GPS ✓ 闭环 ✓（走不动会如实报错 ✗ 不静默 ✗）──
local function gotoXZ(tx, tz)
  for _ = 1, 60 do
    local cx, cy, cz = locate()
    if not cx then return false, "GPS 丢失" end
    if cx == tx and cz == tz then return true end
    local wx, wz = 0, 0
    if cx ~= tx then wx = (tx > cx) and 1 or -1 else wz = (tz > cz) and 1 or -1 end
    local moved = false
    for _ = 1, 4 do
      if facing[1] == wx and facing[2] == wz then
        moved = turtle.forward()
        break
      end
      turnRight()
    end
    if not moved then
      return false, string.format("在 (%d,%d,%d) 走不动（被挡或没燃料）", cx, cy, cz)
    end
  end
  return false, "走位步数超限"
end

local function totalItems()
  local s = 0
  for i = 1, 16 do s = s + turtle.getItemCount(i) end
  return s
end

-- ── 主流程 ────────────────────────────────────────────────────────────────
local before = totalItems()

local okC, errC = calibrate()
if not okC then
  return true, { job = "clean_row", ok = false, why = errC, items_before = before }
end

local okG, errG = gotoXZ(X0, Z)
if not okG then
  return true, { job = "clean_row", ok = false, why = errG, items_before = before,
                 at = { locate() } }
end

local dug, skipped, stuck = 0, 0, nil
for i = 0, n - 1 do
  local x = X0 + i
  if i > 0 and i % 4 == 0 then
    -- 位置复核（GPS 偶尔给坏解 ✓ 每 4 格校一次 ✓ 偏了就走回去 ✓）
    local cx, cy, cz = locate()
    if not cx then stuck = "第 " .. i .. " 格：GPS 丢失"; break end
    if cx ~= x or cz ~= Z then
      local ok, err = gotoXZ(x, Z)
      if not ok then stuck = err; break end
    end
  end

  local hasBlock, info = turtle.inspectDown()
  if hasBlock and info and (info.name == "minecraft:oak_planks" or info.name == "minecraft:oak_log") then
    if turtle.digDown() then
      dug = dug + 1
      turtle.suckDown()                 -- ★ 立刻回收（下面就是虚空 ✗）
      sleep(0.15)
    else
      stuck = string.format("(%d,%d,%d) 挖不动：升级槽里有没有镐/斧？", x, Y, Z)
      break
    end
  else
    skipped = skipped + 1
  end

  -- 走向下一格（最后一格不用走 ✓）
  if i < n - 1 then
    local walked = false
    for _ = 1, 4 do
      if facing[1] == 1 and facing[2] == 0 then walked = turtle.forward(); break end
      turnRight()
    end
    if not walked then
      local ok, err = gotoXZ(x + 1, Z)
      if not ok then stuck = err; break end
    end
  end
end

local after = totalItems()
local fx, fy, fz = locate()
return true, {
  job = "clean_row", ok = (stuck == nil),
  dug = dug, skipped = skipped, why = stuck,
  items_before = before, items_after = after, gained = after - before,
  cells = { X0, Y, Z, "..", X1, Y, Z },
  at = { x = fx, y = fy, z = fz },
}
