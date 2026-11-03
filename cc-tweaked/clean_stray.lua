-- clean_stray.lua —— 把海龟自己误放的木板收回来
--
-- 为什么写它（诚实交代）：
--   上一轮我下了一次 goto 但海龟停在别处 ✓ 结果 place_row 把它 13 块木板
--   铺在了 (4109..4121, 70, z=1) 的空中 ✗ —— 那是"我造成的痕迹" ✓ 要自己收拾 ✓
--
-- 顺带它满足目标第 4 条：**一次多步 GPS 作业** ✓（13 次导航 + 挖掘 + 收集 ✓）
--
-- 下发：{"who":"cc0","cmd":"run_job","args":{"target":1,"name":"clean_stray.lua"}}

local x0 = tonumber(a and a.x0) or 4109
local x1 = tonumber(a and a.x1) or 4121
local y  = tonumber(a and a.y)  or 70
local z  = tonumber(a and a.z)  or 1

local out = { cells = {}, dug = 0, collected = 0 }

for x = x0, x1 do
  -- 导航到目标格**正上方**（goto 先走 y 轴 ✓ 所以会自动飞过去 ✓）
  local okG, g = ACT.goto({ x = x, y = y + 1, z = z, max_steps = 40 })
  if not okG then
    out.cells[#out.cells + 1] = { x = x, goto_ok = false, why = tostring(g) }
  else
    local okI, data = turtle.inspectDown()
    local nm = okI and data and data.name or nil
    local dug = false
    if nm and nm:find("planks") then dug = turtle.digDown() end
    local got = false
    if dug then got = turtle.suckDown() end   -- 挖下来的东西会掉在正下方那格 ✓ 直接吸上来 ✓
    if dug then out.dug = out.dug + 1 end
    if got then out.collected = out.collected + 1 end
    out.cells[#out.cells + 1] = { x = x, goto_ok = true, below = nm, dug = dug, collected = got }
  end
end

out.inv = {}
for slot = 1, 16 do
  local d = turtle.getItemDetail(slot)
  if d then out.inv[#out.inv + 1] = { slot = slot, name = d.name, count = d.count } end
end
out.fuel = turtle.getFuelLevel()

return true, out
