--[[
  fill_ring.lua — 执行一条**离线算好的**「走路 + 放置」序列（海龟）
  ===========================================================================
  为什么这样分工（本轮实测得出的结论）：
    · 海龟没有 GPS ✗，但**每一步都返回成功与否** ✓ → 可以用"步数推算位置" ✓。
    · 岛内 y=71 全是玩家建筑 ✗，直线走必被挡 → 路线必须**离线用 BFS 在 y=71 的空气格上算好** ✓
      （tools/ring_path.py），游戏内只负责"照走、如实报错" ✓。
      这不算"盲目长脚本"：路线是算出来的、每格都有位置自检、失败会带现场数据停下 ✓（教训 D1）。

  关键几何事实（本探针实测确认 ✓）：
    turtle.placeDown() 能放进「下方是空气、上方是空气、只有水平邻居实心」的格子 ✓
    —— 平台边界环要填的正是这种格子。

  参数：
    steps   [ {t="f", d="north", n=3}, {t="p", x=4121, z=2}, {t="u"|"d", n=1}, ... ]
    y        行走层（默认 71；放置目标在 y-1）
    x0, z0   起始格（Agent 从世界里读到，不是猜的）
    facing   起始朝向（同样从方块状态 facing 读到）
    log      本机日志文件名（默认 ring_run.log，Agent 可直接读磁盘 ✓）
    max_moves / budget_s  硬预算 ✓

  返回：{ placed, already, failed, moves, x, z, y, facing, stop, elapsed_s, fuel }
]]

local a = ...
if type(a) ~= "table" then a = {} end

local steps    = a.steps or {}
local Y        = tonumber(a.y) or 71
local x        = tonumber(a.x0)
local z        = tonumber(a.z0)
local logName  = a.log or "ring_run.log"
local maxMoves = tonumber(a.max_moves) or 800
local budgetS  = tonumber(a.budget_s) or 120

if not (x and z) then
  return false, { err = "need x0 / z0 (start cell)" }
end

local FACING = { "north", "east", "south", "west" }
local fidx = 1
do
  local f = a.facing or "north"
  for i, d in ipairs(FACING) do if d == f then fidx = i end end
end

local y = Y
local t0 = os.epoch("utc")

local function note(s)
  local f = fs.open(logName, "a")
  if f then
    f.writeLine(string.format("[%d] %s", os.epoch("utc") - t0, s))
    f.close()
  end
end

local function idxOf(n)
  for i, d in ipairs(FACING) do if d == n then return i end end
  return nil
end

local function turnToIdx(i)
  local guard = 0
  while fidx ~= i and guard < 4 do
    if ((i - fidx) % 4) <= 2 then
      turtle.turnRight(); fidx = fidx % 4 + 1
    else
      turtle.turnLeft();  fidx = (fidx - 2) % 4 + 1
    end
    guard = guard + 1
  end
  return fidx == i
end

local function shift(d)
  if d == "north" then z = z - 1
  elseif d == "south" then z = z + 1
  elseif d == "east" then x = x + 1
  else x = x - 1 end
end

local function nameBelow()
  local ok, data = turtle.inspectDown()
  if ok and type(data) == "table" then return tostring(data.name) end
  return "none"
end

local function nameFront()
  local ok, data = turtle.inspect()
  if ok and type(data) == "table" then return tostring(data.name) end
  return "none"
end

local moves, placed, already, failed = 0, 0, 0, 0
local stopReason = nil
local cellsTouched = 0

note(string.format("START x=%d z=%d y=%d facing=%s steps=%d fuel=%s",
     x, y, z, FACING[fidx], #steps, tostring(turtle.getFuelLevel())))

for si, s in ipairs(steps) do
  local t = s.t

  if t == "f" then
    local di = idxOf(s.d)
    if not di then stopReason = "bad dir: " .. tostring(s.d); break end
    turnToIdx(di)
    local want = tonumber(s.n) or 1
    local done = 0
    for _ = 1, want do
      if moves >= maxMoves then stopReason = "move budget exhausted"; break end
      if turtle.forward() then
        moves = moves + 1; done = done + 1; shift(s.d)
      else
        stopReason = string.format(
          "BLOCKED step=%d moved=%d/%d dir=%s pos=%d,%d,%d front=%s down=%s",
          si, done, want, s.d, x, y, z, nameFront(), nameBelow())
        break
      end
    end
    if stopReason then break end

  elseif t == "p" then
    local tx, tz = tonumber(s.x), tonumber(s.z)
    if x ~= tx or z ~= tz then
      stopReason = string.format("DRIFT step=%d want=%d,%d reckoned=%d,%d,%d",
                                 si, tx, tz, x, y, z)
      break
    end
    cellsTouched = cellsTouched + 1
    local nm = nameBelow()
    if nm ~= "none" then
      already = already + 1
      note(string.format("cell %d %d ALREADY %s", tx, tz, nm))
    else
      local pok, perr = turtle.placeDown()
      if pok then
        placed = placed + 1
        note(string.format("cell %d %d PLACED moves=%d", tx, tz, moves))
      else
        failed = failed + 1
        note(string.format("cell %d %d PLACE_FAIL %s", tx, tz, tostring(perr)))
      end
    end

  elseif t == "u" then
    for _ = 1, (tonumber(s.n) or 1) do
      if turtle.up() then y = y - 1; moves = moves + 1 else stopReason = "up blocked"; break end
    end
    if stopReason then break end

  elseif t == "d" then
    -- ⚠ y 轴向上为正：往下走是 y **减 1**。
    --   这个符号本轮写反过一次 ✓：海龟真的下降到 y=70，推算值却成了 72 ✗
    --   （因为那次放的是水平格 pf，落点不受影响 ✓，才没有立刻暴露 ✗）。
    for _ = 1, (tonumber(s.n) or 1) do
      if turtle.down() then y = y - 1; moves = moves + 1 else stopReason = "down blocked"; break end
    end
    if stopReason then break end

  elseif t == "pf" then
    -- 往前（水平）放一格。
    -- 为什么需要：有些目标格的**正上方被玩家的方块占了** ✗（本轮实测：(4122,3) 上方是
    -- storage barrel、(4122,6) 上方是 block_reader 外设）→ 从上方 placeDown 物理上做不到 ✓。
    -- 若它在 y 层有一个空的水平邻居，就能"站到那一格的同层、面朝目标、place()" ✓。
    -- ⚠ 这里不写死目标格，只记录"落点应当在 x,z 对面的那一格"，真相仍以世界普查为准 ✓。
    if s.d then
      local di = idxOf(s.d)
      if not di then stopReason = "pf bad dir: " .. tostring(s.d); break end
      turnToIdx(di)
    end
    local tx, tz = x, z
    if FACING[fidx] == "north" then tz = tz - 1
    elseif FACING[fidx] == "south" then tz = tz + 1
    elseif FACING[fidx] == "east" then tx = tx + 1
    else tx = tx - 1 end
    local nm = nameFront()
    if nm ~= "none" then
      already = already + 1
      note(string.format("cell %d %d ALREADY(front) %s", tx, tz, nm))
    else
      local pok, perr = turtle.place()
      if pok then
        placed = placed + 1
        note(string.format("cell %d %d PLACED_FRONT from=%d,%d,%d face=%s moves=%d",
                           tx, tz, x, y, z, FACING[fidx], moves))
      else
        failed = failed + 1
        note(string.format("cell %d %d PLACE_FRONT_FAIL %s from=%d,%d,%d face=%s",
                           tx, tz, tostring(perr), x, y, z, FACING[fidx]))
      end
    end

  elseif t == "mark" then
    note(string.format("mark x=%d z=%d y=%d facing=%s moves=%d", x, z, y, FACING[fidx], moves))
  end

  if (os.epoch("utc") - t0) > budgetS * 1000 then
    stopReason = "time budget reached"
    break
  end
end

note(string.format("END x=%d z=%d y=%d facing=%s moves=%d placed=%d already=%d failed=%d stop=%s fuel=%s",
     x, y, z, FACING[fidx], moves, placed, already, failed,
     tostring(stopReason), tostring(turtle.getFuelLevel())))

return true, {
  placed = placed, already = already, failed = failed,
  moves = moves, cells = cellsTouched,
  x = x, z = z, y = y, facing = FACING[fidx],
  stop = stopReason,
  elapsed_s = math.floor((os.epoch("utc") - t0) / 100) / 10,
  fuel = turtle.getFuelLevel(),
}
