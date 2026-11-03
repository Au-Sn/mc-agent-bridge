-- probe_neighbors.lua —— 让海龟自己报出"六个方向各是什么"，并给出每侧的外设
--
-- 为什么不用外部推断：我先前根据"面朝南则左=east"去推某格是不是 inventory_manager ✗
--   → 推出了一个**完全错误**的结论（还错误地怀疑了 survey 的坐标 ✗ 而它其实是准的 ✓）
--   → 教训：方位这种事，**问当事者** ✓ 不要靠我脑内坐标系推 ✗
--
-- 下发：{"who":"cc0","cmd":"run_job","args":{"target":1,"name":"probe_neighbors.lua"}}

local out = { dirs = {}, periph_by_side = {} }

for _, side in ipairs(peripheral.getNames()) do
  out.periph_by_side[side] = peripheral.getType(side)
end

local function rec(dir, ok, data)
  out.dirs[#out.dirs + 1] = { dir = dir, ok = ok, name = (ok and data and data.name) or nil }
end

local okF, dF = turtle.inspect();      rec("front", okF, dF)
local okU, dU = turtle.inspectUp();    rec("up", okU, dU)
local okD, dD = turtle.inspectDown();  rec("down", okD, dD)

-- 转向把右/后/左也看一遍，最后**用同样次数的反向动作转回原位** ✓
--
-- ⚠ 这里的教训（我自己踩的 ✓）：**绝对不要裸调 `turtle.turnRight()`** ✗
--   worker 内部的 facingIdx 只由 `ACT.turn_right` / `ACT.turn_left` 维护 ✓
--   裸调会让"真实朝向"和"内部索引"不一致 ✗ → 之后所有轴向移动都会走反 180° ✗
--   （上次我不仅裸调 ✗ 还用 3×right + 1×left 去"还原" ✗ = 净转 180°，两处都错 ✗）
local names = { "right", "back", "left" }
for i = 1, 3 do
  ACT.turn_right({})
  local ok, data = turtle.inspect()
  rec(names[i], ok, data)
end
for i = 1, 3 do
  ACT.turn_left({})   -- 与上面同次数 → 精确回到原朝向 ✓
end

-- 海龟自身信息
out.fuel = turtle.getFuelLevel()
out.selected = turtle.getSelectedSlot()
out.inv = {}
for slot = 1, 16 do
  local d = turtle.getItemDetail(slot)
  if d then out.inv[#out.inv + 1] = { slot = slot, name = d.name, count = d.count } end
end

return true, out
