--[[
  probe_place.lua — 一次性几何探针（海龟）
  ---------------------------------------------------------------------------
  要回答的唯一关键问题（本阶段卡点）：
    「平台边界环」那些格子，几何是 **下方是空气、上方是空气、只有水平邻居是实心** ✗。
    那么 turtle.placeDown() 到底能不能放进去？(即：放置的依附面能不能取水平邻居)

  为什么要做成"一次跑完、带回全部现场数据"：
    每条 rednet 往返 1~3 秒，拆成"转/走/瞄/放/读"五条指令要十几秒且中途丢包无法确认 ✗；
    而它只是**一次放置**，不是长作业，所以不算"盲目长脚本" ✓（教训 D1 针对的是无进度长作业）。

  参数（全部可选）：
    facing       本机真实朝向（由 Agent 从世界里读到方块状态 facing 得到）
    face         先转到这个方向再走
    fwd          前进几格（不挖；被挡就如实记录在第几格停下）
    probe_front  1 = 额外试一次水平 place()（测"前方空气格、下方空气"的几何）
    log          本机日志文件名（默认 probe_result.txt，Agent 可从磁盘直接读 ✓）

  返回：{ trace = {...}, facing = ..., fuel = ... }，同时在磁盘留一份同样的记录。
]]

local a = ...
if type(a) ~= "table" then a = {} end

local FACING = { "north", "east", "south", "west" }
local facingIdx = 1

local function idxOf(n)
  for i, d in ipairs(FACING) do
    if d == n then return i end
  end
  return nil
end

local function turnTo(idx)
  local guard = 0
  while facingIdx ~= idx and guard < 4 do
    if ((idx - facingIdx) % 4) <= 2 then
      turtle.turnRight(); facingIdx = facingIdx % 4 + 1
    else
      turtle.turnLeft();  facingIdx = (facingIdx - 2) % 4 + 1
    end
    guard = guard + 1
  end
  return facingIdx == idx
end

local trace = {}
local function rec(k, v) trace[#trace + 1] = { k = k, v = v } end
local function inspectDir(fn)
  if type(fn) ~= "function" then return "unsupported" end
  local ok, data = fn()
  if ok and type(data) == "table" then return tostring(data.name) end
  return "none"
end

rec("fuel", turtle.getFuelLevel())
rec("sel_slot", turtle.getSelectedSlot())
rec("sel_count", turtle.getItemCount(turtle.getSelectedSlot()))
local det = turtle.getItemDetail(turtle.getSelectedSlot())
rec("sel_name", det and tostring(det.name) or "empty")
rec("crafty", turtle.craft ~= nil)

local want = a.facing or "north"
local wi = idxOf(want)
if not wi then
  return false, { err = "facing must be north|east|south|west", got = tostring(want), trace = trace }
end
facingIdx = wi
rec("facing_claimed", want)

if a.face then
  local ti = idxOf(a.face)
  rec("turn_to", tostring(a.face))
  rec("turn_ok", ti ~= nil and turnTo(ti) or false)
end

local n = tonumber(a.fwd) or 0
if n > 0 then
  local moved = 0
  for _ = 1, n do
    if turtle.forward() then
      moved = moved + 1
    else
      rec("fwd_stopped_at", moved)
      break
    end
  end
  rec("fwd_moved", moved)
end

rec("up_name",    inspectDir(turtle.inspectUp))
rec("front_name", inspectDir(turtle.inspect))
rec("down_before", inspectDir(turtle.inspectDown))

-- ── 正式探针：往"下方那一格"放方块 ────────────────────────────────────────
local pOk, pErr = turtle.placeDown()
rec("placeDown_ok",  pOk and true or false)
rec("placeDown_err", pOk and "" or tostring(pErr))
rec("down_after",    inspectDir(turtle.inspectDown))
rec("sel_count_after", turtle.getItemCount(turtle.getSelectedSlot()))

-- ── 附加探针：往"前方那一格"水平放 ────────────────────────────────────────
if a.probe_front then
  local qOk, qErr = turtle.place()
  rec("place_ok",  qOk and true or false)
  rec("place_err", qOk and "" or tostring(qErr))
  rec("front_after", inspectDir(turtle.inspect))
end

local fn = fs.open(a.log or "probe_result.txt", "w")
if fn then
  for _, e in ipairs(trace) do
    fn.writeLine(tostring(e.k) .. "=" .. tostring(e.v))
  end
  fn.close()
end

return true, { trace = trace, facing = FACING[facingIdx], fuel = turtle.getFuelLevel() }
