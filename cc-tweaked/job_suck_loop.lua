-- job_suck_loop.lua —— 站在原地吸 N 秒（六方向 + 四向旋转，**不移动** ✓）
--
-- 为什么单独写它（而不是复用 job_suck_around ✗）：
--   `job_suck_around` 会先**标定朝向** ✓ 而标定要"走一步看坐标变化" ✗
--   → 它会把海龟从"筛子旁边"挪开 ✗ 那就吸不到筛子上的掉落物了 ✗
--   本作业**不标定、不移动** ✓ 只在原地转着吸 ✓ —— 专用于"当别人在干活、我负责捡" ✓
--
-- 参数：seconds = 吸多少秒（默认 20 ✓）  want = 目标物品名片段（吸到就提前收工 ✓）

local a = ...
local seconds = tonumber(a and a.seconds) or 20
local want = (a and a.want) or ""

local LOG = "suck_loop.log"
local function log(s)
  print(s)
  local f = fs.open(LOG, "a")
  if f then f.writeLine(os.date("%H:%M:%S ") .. tostring(s)); f.close() end
end

local function invList()
  local out = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d then out[#out + 1] = string.format("%d:%s x%d", i, d.name, turtle.getItemCount(i)) end
  end
  return table.concat(out, ", ")
end

local function hasWant()
  if want == "" then return nil end
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and tostring(d.name):find(want, 1, true) then return d.name end
  end
  return nil
end

log("=== START suck_loop " .. seconds .. "s want=" .. want .. " ===")
local cx, cy, cz = gps.locate(2)
if cx then log(string.format("站位 (%d,%d,%d)", math.floor(cx), math.floor(cy), math.floor(cz))) end

local t0, sucks, found = os.clock(), 0, nil
while (os.clock() - t0) < seconds do
  if turtle.suck()     then sucks = sucks + 1 end
  if turtle.suckUp()   then sucks = sucks + 1 end
  if turtle.suckDown() then sucks = sucks + 1 end
  turtle.turnRight()
  sleep(0.15)
  found = hasWant()
  if found then break end
end

local fx, fy, fz = gps.locate(2)
log(string.format("吸了 %d 次 | 背包: %s", sucks, invList()))
return true, {
  job = "suck_loop", ok = (want == "" or found ~= nil),
  want = want, found = found, sucks = sucks,
  seconds = tonumber(string.format("%.1f", os.clock() - t0)),
  inventory = invList(),
  at = { x = fx and math.floor(fx), y = fy and math.floor(fy), z = fz and math.floor(fz) },
}
