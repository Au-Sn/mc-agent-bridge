-- job_sift.lua —— 海龟**自己**筛矿：对着筛子反复右击 + 把产物吸回来
--
-- 为什么换海龟来做（2026-09-18 深夜的诊断 ✓）：
--   假人用 `sift` 技能在筛子旁连点 25 秒 ✓ 结果筛子 NBT 里 **progress 仍然是 0.0** ✗
--   —— 也就是**右键根本没落到筛子上** ✗（不是"慢" ✓ 是"没生效" ✗）。
--   而海龟的 `turtle.place()` 走的是 CC 的"用物品右键方块"那条路 ✓
--   （装筛网、撒种子、喂动物都是它 ✓）→ 值得换一只手试 ✓。
--
-- 它怎么找筛子（**不靠坐标** ✓ 更稳 ✓）：
--   原地转 4 个方向 ✓ 每个方向 `inspect()` 一次 ✓ 谁报出 `exdeorum:oak_sieve` 就朝谁 ✓
--   —— 这样连"朝向记录过期"这个坑都绕开了 ✓（见 docs/错题本.md I11 ✓）
--
-- 参数：times = 最多右击几次（默认 40 ✓）  item = 手上要用的东西（默认自动找 gravel ✓）

local a = ...
local TIMES = tonumber(a and a.times) or 40
local WANT_ITEM = (a and a.item) or ""

local LOG = "sift.log"
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

local function findSlot(pat)
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and tostring(d.name):find(pat, 1, true) then return i, d.name end
  end
  return nil
end

-- ① 找到筛子在哪个方向（转 4 次，靠 inspect 认名 ✓）
log("=== START sift ===")
local dirName = { "front", "right", "back", "left" }
local foundDir = nil
for i = 0, 3 do
  if i > 0 then turtle.turnRight() end
  local ok, info = turtle.inspect()
  log(string.format("朝 %s 看：%s", dirName[i + 1], tostring(info and info.name)))
  if ok and info and tostring(info.name):find("sieve", 1, true) then
    foundDir = i
    break
  end
end
if not foundDir then
  log("四个方向都没有筛子 ✗（先把它放到海龟旁边 ✓）")
  return true, { job = "sift", ok = false, why = "附近没有筛子", inventory = invList() }
end
log("筛子在 " .. dirName[foundDir + 1] .. " 方向 ✓（已转向它 ✓）")

-- ② 手里要有能筛的东西（默认 gravel ✓）
local slot, name = findSlot(WANT_ITEM ~= "" and WANT_ITEM or "gravel")
if not slot then
  log("背包里没有可筛的东西 ✗（需要 gravel 之类 ✓）")
  return true, { job = "sift", ok = false, why = "没有原料", inventory = invList() }
end
turtle.select(slot)
log(string.format("手上是 槽%d %s x%d", slot, name, turtle.getItemCount(slot)))

-- ③ 反复"右击 + 吸产物"（CC 的 place 就是"用物品右键面前的方块" ✓）
local before = {}
for i = 1, 16 do
  local d = turtle.getItemDetail(i)
  if d then before[d.name] = (before[d.name] or 0) + turtle.getItemCount(i) end
end
local places, sucks = 0, 0
for n = 1, TIMES do
  local okP, errP = turtle.place()
  if okP then places = places + 1 end
  if n <= 3 or (not okP and n < 5) then
    log(string.format("第 %d 次 place = %s / %s", n, tostring(okP), tostring(errP)))
  end
  -- 产物会掉在筛子那一格（也可能落进背包 ✓）→ 六面都吸一遍 ✓
  if turtle.suck()     then sucks = sucks + 1 end
  if turtle.suckUp()   then sucks = sucks + 1 end
  if turtle.suckDown() then sucks = sucks + 1 end
  sleep(0.25)
  -- 手上没原料了就别硬点 ✓
  if turtle.getItemCount(slot) == 0 then
    local s2 = findSlot(WANT_ITEM ~= "" and WANT_ITEM or "gravel")
    if s2 then slot = s2; turtle.select(slot) else break end
  end
end

local after = {}
for i = 1, 16 do
  local d = turtle.getItemDetail(i)
  if d then after[d.name] = (after[d.name] or 0) + turtle.getItemCount(i) end
end
local gained = {}
for k, v in pairs(after) do
  local d = v - (before[k] or 0)
  if d > 0 then gained[k] = d end
end
local gs = {}
for k, v in pairs(gained) do gs[#gs + 1] = k .. " +" .. v end
table.sort(gs)
log(string.format("右击 %d 次 ✓ 吸到 %d 次 ✓ 新增：%s", places, sucks, table.concat(gs, ", ")))
log("最终背包: " .. invList())
return true, {
  job = "sift", ok = (#gs > 0), places = places, sucks = sucks,
  gained = gained, inventory = invList(),
}
