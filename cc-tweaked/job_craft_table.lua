-- job_craft_table.lua —— 海龟**自己**合成出第一个工作台（4 木板 × 2×2）
--
-- 为什么这件事很关键（2026-09-18 晚，读 CC 源码得到的新事实）：
--   项目文档里长期写着"第一个工作台是不可约的外部输入"✗ —— 依据是"海龟必须装备工作台
--   （Crafty 升级）才能合成" ✗。**这条依据是错的** ✓：
--     `TurtleCraftCommand` → `TurtleInventoryCrafting`：WIDTH=HEIGHT=3 ✓
--     —— 海龟**一直**有一个 **3×3 合成窗口** ✓（窗口在自己的 4×4 背包上滑动 ✓）
--     而且源码里**没有任何**"需要 Crafty/工作台"的检查 ✓✓
--   ⇒ 只要 4 块木板 ✓ 海龟就能合成工作台 ✓（2×2 配方 ✓）；有了工作台再装备成 Crafty ✓
--     就能合成 3×3 的东西（筛子等 ✓）——**整条链从来不需要外部投入** ✓✓
--
-- ⚠ 但有一个硬约束（源码 `tryCrafting` 里逐格检查 ✗）：
--      **3×3 窗口之外的槽位必须全空** ✗；窗口之内、配方之外的格子也必须空 ✗
--   ⇒ 合成前背包必须"干净" ✓ —— 多余的东西只能**丢在地上**（不是销毁 ✓ 稍后吸回来 ✓）
--   ⇒ 所以本作业：走到有地面的地方 → 整理 → 丢多余的 → 摆 4 块木板 → craft → **把丢掉的全吸回来** ✓
--
-- 参数（都可省）：x/y/z = 作业点（默认 4124,71,11：下面 (4124,70,11) 是草方块 ✓ 掉落物不会掉进虚空 ✓）

local a = ...
local WX = tonumber(a and a.x) or 4124
local WY = tonumber(a and a.y) or 71
local WZ = tonumber(a and a.z) or 11

local LOG = "craft_table.log"
local function log(s)
  print(s)
  local f = fs.open(LOG, "a")
  if f then f.writeLine(os.date("%H:%M:%S ") .. tostring(s)); f.close() end
end

-- ── 定位与走位（只用标准 CC API ✓ 作业脚本里没有 ACT ✗）────────────────────
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

-- ⚠ 标定必须**四个方向都试** ✗（真实事故：海龟停在 (4124,71,7) ✓ 而正前方
--   (4124,71,8) 就是玩家自己的海龟 ✗ → 只试 forward 会直接判"无法标定" ✓
--   规则：只要**任一方向**能走通 ✓ 就能从坐标变化反推出 forward 的绝对方向 ✓）
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
    -- 四面都被挡 ⇒ 先升空 3 格（空中不会有方块挡路 ✓）再试第二轮
    if attempt == 1 then
      for _ = 1, 3 do turtle.up() end
    end
  end
  return false, "四个方向都走不动，无法标定朝向"
end

local function gotoXZ(tx, tz)
  for _ = 1, 80 do
    local cx, cy, cz = locate()
    if not cx then return false, "GPS 丢失" end
    if cx == tx and cz == tz then return true end
    local wx, wz = 0, 0
    if cx ~= tx then wx = (tx > cx) and 1 or -1 else wz = (tz > cz) and 1 or -1 end
    local moved = false
    for _ = 1, 4 do
      if facing[1] == wx and facing[2] == wz then moved = turtle.forward(); break end
      turnRight()
    end
    if not moved then return false, string.format("在 (%d,%d,%d) 走不动", cx, cy, cz) end
  end
  return false, "步数超限"
end

-- ★ 三维走位：**先升空、再平移、最后降落** ✓
--   为什么必须这样（真实事故 2026-09-18 晚）：
--     直线走过去时，在 (4124,71,7) 被挡死 ✗ —— 挡路的是**玩家自己的海龟**
--     （ComputerId 3，停在 (4124,71,8) ✓）。它是方块 ✓ 又不是我们的机器 ✗ 不能挖 ✗。
--   升空到 y=SAFE_Y（76 ✓ 比基地里一切设施都高 ✓）再平移 ✓ 就绕开了所有地面障碍 ✓
--   —— 这正是项目文档里早就写过的"先升空再平移" ✓（`agent/plans/clean_stray_3c.json`）
local SAFE_Y = tonumber(a and a.safe_y) or 76

local function gotoXYZ(tx, ty, tz)
  local cx, cy, cz = locate()
  if not cx then return false, "GPS 不可用" end
  -- 往上爬到安全高度
  while cy < SAFE_Y do
    if not turtle.up() then return false, string.format("在 (%d,%d,%d) 升不上去", cx, cy, cz) end
    cx, cy, cz = locate()
    if not cx then return false, "上升途中 GPS 丢失" end
  end
  local ok, err = gotoXZ(tx, tz)
  if not ok then return false, err end
  -- 降落到目标层
  cx, cy, cz = locate()
  while cx and cy > ty do
    if not turtle.down() then return false, string.format("降到 y=%d 被挡（(%d,%d,%d) 下方有东西）", cy - 1, cx, cy, cz) end
    cx, cy, cz = locate()
  end
  if not cx then return false, "降落途中 GPS 丢失" end
  return true
end

-- ── 背包工具 ──────────────────────────────────────────────────────────────
local function totalItems()
  local s = 0
  for i = 1, 16 do s = s + turtle.getItemCount(i) end
  return s
end

local function invList()
  local out = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d then out[#out + 1] = string.format("%d:%s x%d", i, d.name, turtle.getItemCount(i)) end
  end
  return table.concat(out, ", ")
end

local function findByName(pat)
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and tostring(d.name):find(pat, 1, true) then return i, d.name end
  end
  return nil
end

local function countName(pat)
  local n = 0
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and tostring(d.name):find(pat, 1, true) then n = n + turtle.getItemCount(i) end
  end
  return n
end

-- ── 主流程 ────────────────────────────────────────────────────────────────
-- ⚠ 走位可以交给 worker 的 `goto` ✓（它是**经过实战的** GPS 导航 ✓ 有卡住检测 ✓）
--   —— 本项目错题本 G5 的结论："自己能写 ≠ 该自己写" ✓
--   所以本作业支持 `skip_nav=true`：Agent 先用 `goto` 把它送到作业点 ✓ 再跑纯合成流程 ✓
local skipNav = (a and a.skip_nav == true)

log("=== START craft_table ===")
local before = totalItems()
log("起点物品数 " .. before .. " | 背包: " .. invList())

if not skipNav then
  local okC, errC = calibrate()
  if not okC then
    log("标定失败：" .. tostring(errC))
    return true, { job = "craft_table", ok = false, why = errC, items = before }
  end

  local okG, errG = gotoXYZ(WX, WY, WZ)
  if not okG then
    log("走位失败：" .. tostring(errG))
    return true, { job = "craft_table", ok = false, why = errG, items = before }
  end
  log("已到作业点 (" .. WX .. "," .. WY .. "," .. WZ .. ")")
else
  local cx, cy, cz = locate()
  log("跳过导航（由 worker 的 goto 送过来）当前 " ..
      tostring(cx) .. "," .. tostring(cy) .. "," .. tostring(cz))
  if cx ~= WX or cz ~= WZ then
    log("⚠ 但当前位置不是作业点 ✗ 继续执行（合成不依赖具体站位 ✓ 只依赖下方有没有地面 ✓）")
  end
end

-- ① 把木板归并到"窗口内的槽位"（用窗口 (1,0) ⇒ 1-based 槽位 {2,3,4,6,7,8,10,11,12} ✓
--    2×2 图案放在它的左上角 = 槽位 2,3,6,7 ✓ 其余窗口格与窗口外的 7 个槽位都必须空 ✓）
local PLANK = "minecraft:oak_planks"
local targetSlot = 2
if turtle.transferTo == nil then
  log("这台 CC 没有 turtle.transferTo ✗ 无法精确整理背包（放弃，不冒险）")
  return true, { job = "craft_table", ok = false, why = "no transferTo", items = before }
end

-- 先把所有木板挪到 2 号槽（它是窗口内的图案格 ✓）
for i = 1, 16 do
  if i ~= targetSlot then
    local d = turtle.getItemDetail(i)
    if d and tostring(d.name) == PLANK then
      turtle.select(i)
      local moved = turtle.transferTo(targetSlot)
      log(string.format("归并：槽%d -> 槽%d (%s)", i, targetSlot, tostring(moved)))
    end
  end
end
turtle.select(targetSlot)
log("归并后：槽" .. targetSlot .. " 有木板 " .. turtle.getItemCount(targetSlot) .. " 块")

-- ② 把非木板的东西**丢在下方地面**（可回收 ✓ 不销毁 ✓）
local dropped = {}
for i = 1, 16 do
  local d = turtle.getItemDetail(i)
  if d and tostring(d.name) ~= PLANK then
    turtle.select(i)
    local n = turtle.getItemCount(i)
    local okD = turtle.dropDown(n)
    dropped[#dropped + 1] = string.format("%s x%d@%d(%s)", d.name, n, i, tostring(okD))
    log(string.format("丢掉：槽%d %s x%d -> %s", i, d.name, n, tostring(okD)))
  end
end

-- ③ 摆 2×2：从 2 号槽各分 1 块到 3 / 6 / 7
turtle.select(targetSlot)
for _, s in ipairs({ 3, 6, 7 }) do
  local okT = turtle.transferTo(s, 1)
  log(string.format("分料：槽%d -> 槽%d (%s)", targetSlot, s, tostring(okT)))
end
log("摆好后背包: " .. invList())

-- ④ 先**无损探测**（craft(0) 只判断"这个布局能不能合成" ✓ 不消耗任何东西 ✓ 见 CC 源码 ✓）
local okP, errP = turtle.craft(0)
log("探测 craft(0) = " .. tostring(okP) .. " / " .. tostring(errP))
local crafted, craftErr = false, nil
if okP then
  crafted, craftErr = turtle.craft(1)
  log("合成 craft(1) = " .. tostring(crafted) .. " / " .. tostring(craftErr))
else
  craftErr = "布局不匹配：" .. tostring(errP)
end
log("合成后背包: " .. invList())

local tblSlot, tblName = findByName("crafting_table")
if tblSlot then log("★ 拿到工作台：槽" .. tblSlot .. " (" .. tblName .. ")") end

-- ⑤ 把丢在地上的东西**全部吸回来**（六个方向都试 ✓ 丢的是自己的材料 ✓ 不能丢 ✓）
local recovered = 0
for pass = 1, 3 do
  if turtle.suckDown() then recovered = recovered + 1 end
  if turtle.suckUp()  then recovered = recovered + 1 end
  for _ = 1, 4 do
    if turtle.suck() then recovered = recovered + 1 end
    turtle.turnRight()
  end
  sleep(0.2)
end
log(string.format("吸回 %d 次；最终背包: %s", recovered, invList()))

local after = totalItems()
local fx, fy, fz = locate()
local summary = {
  job = "craft_table", ok = (tblSlot ~= nil),
  crafted = crafted, craft_err = craftErr,
  crafting_table_slot = tblSlot, crafting_table_name = tblName,
  planks = countName("planks"),
  items_before = before, items_after = after, gained = after - before,
  dropped = dropped, recovered_sucks = recovered,
  inventory = invList(),
  at = { x = fx, y = fy, z = fz },
}
log("=== END ok=" .. tostring(summary.ok) .. " 物品 " .. before .. " -> " .. after .. " ===")
return true, summary
