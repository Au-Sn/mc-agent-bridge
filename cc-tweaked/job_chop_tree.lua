--[[
  job_chop_tree.lua — 作业：砍树 → 收掉落物 →（有树苗就）补种
  ==================================================================

  由海龟端 worker 的 `run_job` 载入执行：
      broadcast_cmd cmd=run_job args.name=job_chop_tree.lua

  返回值 (ok, detail) 会原样回报给 Agent ✓

  设计原则（本项目踩坑总结）：
    * **一个作业 = 一条指令**：游戏内自主跑完，往返越少失败机会越小
    * **不依赖 GPS**：只用相对动作（转身 + 看前方是不是目标方块）找树
    * **每步都记录**：失败时能说清"卡在哪一步、为什么"

  参数（可选）：
    block = 目标方块注册名（默认 minecraft:oak_log）
    max   = 最多向上挖多少格（默认 32）
]]

local a = ...
local want = (a and a.block) or "minecraft:oak_log"
local maxUp = tonumber(a and a.max) or 32

local rep = { target = want, scan = {} }

local function countInv()
  local n = 0
  for i = 1, 16 do n = n + turtle.getItemCount(i) end
  return n
end

local function invSummary()
  local out = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d then out[#out + 1] = { slot = i, name = d.name, count = turtle.getItemCount(i) } end
  end
  return out
end

-- 1) 四周找目标方块（每转一次右看一次前方，最多看 4 个方向）
local found = false
for i = 0, 3 do
  if i > 0 then turtle.turnRight() end
  local ok, d = turtle.inspect()
  local nm = (ok and d) and d.name or nil
  rep.scan[#rep.scan + 1] = { turn = i, block = nm }
  if nm == want then found = true break end
end
if not found then
  rep.step = "find"
  rep.inv_before = invSummary()
  return false, rep
end
rep.found_at_turn = rep.scan[#rep.scan].turn

-- 2) 挖掉底部并进入
if not turtle.dig() then
  rep.step = "dig_base"
  rep.error = "dig failed (no tool? \"No tool to dig with\")"
  return false, rep
end
if not turtle.forward() then
  rep.step = "move_in"
  rep.error = "cannot move into the gap"
  return false, rep
end

-- 3) 一路向上挖到不再是目标方块
local dug, stop = 0, "up is not target"
for _ = 1, maxUp do
  local ok, d = turtle.inspectUp()
  if not ok or not d then stop = "up is air" break end
  if d.name ~= want then stop = "up is " .. tostring(d.name) break end
  if not turtle.digUp() then stop = "digUp failed" break end
  dug = dug + 1
  if not turtle.up() then stop = "cannot move up" break end
end
rep.chopped = dug
rep.stop_reason = stop

-- 4) 退回原高度（回到树干底部那一格）
local back = 0
for _ = 1, dug do
  if turtle.down() then back = back + 1 else break end
end
rep.descended = back

-- 5) 收掉落物（上下 + 四个水平方向）
local before = countInv()
pcall(turtle.suckUp)
pcall(turtle.suckDown)
pcall(turtle.suck)
for _ = 1, 4 do
  turtle.turnRight()
  pcall(turtle.suck)
end
sleep(0.4)
rep.gathered = countInv() - before

-- 6) 有树苗就补种：站到"泥土上方一格"再向下放
local sapSlot = nil
for i = 1, 16 do
  local d = turtle.getItemDetail(i)
  if d and tostring(d.name):find("_sapling$") then sapSlot = i break end
end
if sapSlot then
  turtle.select(sapSlot)
  if turtle.up() then
    if turtle.placeDown() then rep.replanted = true else rep.replanted = "placeDown failed" end
    turtle.down()
  else
    rep.replanted = "cannot move up"
  end
else
  rep.replanted = "no sapling in inventory"
  rep.hint = "put an oak sapling in the turtle inventory to enable replanting"
end

rep.fuel = turtle.getFuelLevel()
rep.inv_after = invSummary()
return true, rep
