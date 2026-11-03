-- peek_containers.lua —— 清点海龟外设，并列出能访问的容器内容
--
-- 设计原则（第二次修正后的写法）：
--   第一次我用 peripheral.find("inventory_manager") **硬猜类型名** ✗ → 找不到 ✓
--   而海龟身上明明挂着两个外设 ✓ —— 说明"猜名字"这件事本身就是错的 ✗
--   所以现在：**枚举每个方向 → 报出它的真实类型 → 用"有没有这些方法"来认功能** ✓
--   （鸭子类型 ✓：能 getItems/list 的就是库存管理器 ✓ 不管它自称什么 ✓）
--
-- 下发：{"who":"cc0","cmd":"run_job","args":{"target":1,"name":"peek_containers.lua"}}

local out = { sides = {}, probes = {}, containers = {} }

local function methods(p)
  local t = {}
  for _, m in ipairs({ "list", "getItems", "getItemInSlot", "getContainerSize",
                       "pullItemIntoSlot", "pushItems", "getOwner", "size" }) do
    t[m] = (type(p[m]) == "function")
  end
  return t
end

local candidate = nil
for _, side in ipairs(peripheral.getNames()) do
  local info = { side = side, type = peripheral.getType(side) }
  local ok, p = pcall(peripheral.wrap, side)
  if ok and p then
    info.methods = methods(p)
    -- 鸭子类型判定：有 getItems 或 list 就当它是库存管理器 ✓
    if info.methods.getItems or info.methods.list then candidate = p end
  end
  out.sides[#out.sides + 1] = info
end

if not candidate then
  out.error = "两个外设都不是库存管理器（看 sides 里的 methods 就知道它们是什么）"
  return false, out
end
out.found = true

-- 容器清单：不同版本方法名不同，逐个试并如实记录 ✓
for _, m in ipairs({ "list", "getContainers" }) do
  if type(candidate[m]) == "function" then
    local ok, res = pcall(candidate[m])
    out.probes[#out.probes + 1] = { method = m, ok = ok, result = ok and res or tostring(res) }
    if ok and type(res) == "table" then out.containers = res end
  end
end

-- 主容器内容（它贴着的那一格）
if type(candidate.getItems) == "function" then
  local ok, items = pcall(candidate.getItems)
  if ok then out.items = items else out.err_items = tostring(items) end
end

-- 逐容器：容量 + 每格内容
if type(candidate.getContainerSize) == "function" and type(candidate.getItemInSlot) == "function" then
  for _, nm in ipairs(out.containers) do
    local okS, sz = pcall(candidate.getContainerSize, nm)
    out["size_" .. tostring(nm)] = okS and sz or tostring(sz)
    if okS and type(sz) == "number" then
      local rows = {}
      for slot = 1, sz do
        local okG, it = pcall(candidate.getItemInSlot, nm, slot)
        if okG and type(it) == "table" and it.name then
          rows[#rows + 1] = { slot = slot, name = it.name, count = it.count }
        end
      end
      out["items_" .. tostring(nm)] = rows
    end
  end
end

-- 找"工作台"（本次任务的目标）
out.crafting_tables = {}
local function scan(tbl, where)
  if type(tbl) ~= "table" then return end
  for _, it in ipairs(tbl) do
    if type(it) == "table" and type(it.name) == "string" and it.name:find("crafting") then
      out.crafting_tables[#out.crafting_tables + 1] = { where = where, slot = it.slot,
                                                        name = it.name, count = it.count }
    end
  end
end
scan(out.items, "self")
for k, v in pairs(out) do
  if type(k) == "string" and k:find("^items_") and type(v) == "table" then scan(v, k) end
end

return true, out
