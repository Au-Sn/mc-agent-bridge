-- fetch_barrel.lua —— 从附近的容器里"只取需要的那一样，其余原样放回"
--
-- 为什么这样做（真实约束）：
--   1. 海龟从容器取物**不需要任何界面** ✓ 这是假人做不到的事情里最关键的一条 ✓
--   2. 但直接把桶掏空 = 动玩家的仓库 ✗ —— 所以本脚本**每取一组就检查一次**，
--      不是我们找的东西就**立刻 drop() 放回同一个容器** ✓（turtle.drop 会插进面前的容器）
--   3. 目标清单由参数给出（默认只要工作台）✓ 找到就停 ✓
--
-- 下发方式（经 cc0 转发到海龟，热加载，不需要 Ctrl+R）：
--   {"who":"cc0","cmd":"run_job","args":{"target":1,"name":"fetch_barrel.lua"}}
-- 参数（可选）：name = 目标物品（默认 minecraft:crafting_table），max = 最多取几组（默认 16）

local WANT = (a and a.name) or "minecraft:crafting_table"
local MAX = tonumber(a and a.max) or 16

local out = { want = WANT, scanned = {}, taken = {}, returned = {}, kept = {} }

-- 槽位快照：用来"取之前 / 取之后"做差，才能知道刚拿到的是什么 ✓
local function snapshot()
  local t = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    t[i] = d and { name = d.name, count = d.count } or nil
  end
  return t
end

local function diff(before, after)
  -- 返回 {slot, name, delta} 列表
  local res = {}
  for i = 1, 16 do
    local b = before[i]
    local f = after[i]
    local bn = b and b.name or nil
    local bc = b and b.count or 0
    local fn_ = f and f.name or nil
    local fc = f and f.count or 0
    if fn_ and (fn_ ~= bn or fc > bc) then
      res[#res + 1] = { slot = i, name = fn_, delta = fc - (fn_ == bn and bc or 0) }
    end
  end
  return res
end

local function find_want(inv)
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and d.name == WANT then return i, d.count end
  end
  return nil, 0
end

-- 逐组取；不是目标就放回
local function take_filtered(dir, suckfn, dropfn, label)
  local got = 0
  for _ = 1, MAX do
    local before = snapshot()
    local ok = suckfn()
    if not ok then
      -- 单独记到 notes ✓ 不要混进 scanned ✗
      -- （第一次写的时候我把两者写到同一个表里，结果 `out.scanned = seen` 在结尾把它覆盖掉了 ✗
      --   于是"为什么没取到"这条最关键的证据凭空消失 ✓ —— 教训：证据要写在不会被覆盖的地方 ✓）
      out.notes = out.notes or {}
      out.notes[#out.notes + 1] = { dir = label, note = "suck 返回 false（桶空了 / 取不动 / 朝向不对 / 容器被锁）" }
      break
    end
    local after = snapshot()
    local gained = diff(before, after)
    for _, g in ipairs(gained) do
      got = got + 1
      if g.name == WANT then
        out.kept[#out.kept + 1] = { dir = label, slot = g.slot, name = g.name, count = g.delta }
      else
        -- 不要的东西：原样放回容器 ✓
        turtle.select(g.slot)
        local back = dropfn()
        out.returned[#out.returned + 1] = { dir = label, slot = g.slot, name = g.name,
                                            count = g.delta, ok = back }
        turtle.select(1)
      end
    end
    local slot, cnt = find_want(snapshot())
    if slot then
      out.have_slot, out.have_count = slot, cnt
      break
    end
  end
  return got
end

-- 1) 前/后/左/右都试（海龟朝向不保证，先把四周看一圈，只对**是容器**的方向动手）
local seen = {}
for turn = 0, 3 do
  local ok, data = turtle.inspect()
  local nm = ok and data and data.name or nil
  seen[#seen + 1] = { turn = turn, block = nm }
  if nm and (nm:find("barrel") or nm:find("chest") or nm:find("shulker") or nm:find("crate")) then
    take_filtered("front", turtle.suck, turtle.drop, "front@" .. tostring(turn))
    if out.have_slot then break end
  end
  if turn < 3 then turtle.turnRight() end
end

-- 2) 上下也看一眼（角上的桶常常在斜上方/斜下方 ✓）
if not out.have_slot then
  local okU, dU = turtle.inspectUp()
  local nmU = okU and dU and dU.name or nil
  seen[#seen + 1] = { dir = "up", block = nmU }
  if nmU and (nmU:find("barrel") or nmU:find("chest") or nmU:find("shulker")) then
    take_filtered("up", turtle.suckUp, turtle.dropUp, "up")
  end
end
if not out.have_slot then
  local okD, dD = turtle.inspectDown()
  local nmD = okD and dD and dD.name or nil
  seen[#seen + 1] = { dir = "down", block = nmD }
  if nmD and (nmD:find("barrel") or nmD:find("chest") or nmD:find("shulker")) then
    take_filtered("down", turtle.suckDown, turtle.dropDown, "down")
  end
end

out.scanned = seen
local slot, cnt = find_want(snapshot())
out.have_slot, out.have_count = slot, cnt
if slot then
  turtle.select(slot)          -- 顺手选中它，方便后面 equip 直接用
  out.selected = slot
end
out.ok_want = (slot ~= nil)
return true, out
