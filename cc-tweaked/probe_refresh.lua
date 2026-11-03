-- probe_refresh.lua —— 验证"外设注册表是否过期"，并用"能否调用方法"来认功能
--
-- 背景（真实矛盾）：
--   海龟 turtle.inspect() 说它左边是 `advancedperipherals:inventory_manager` ✓（方块读取，权威）
--   但 peripheral.getType("left") 说那是 `modem` ✗
--   → 两个都来自同一台机器、同一时刻 ✓ 只能是**外设注册表没刷新** ✓
--   本脚本做两件事：
--     1) 先记录刷新前的探测结果 ✓
--     2) 往上走一格再下来（强制 CC 重新扫描外设）✓ 再记录一次 ✓
--   如果刷新后出现了库存管理器 ✓ 那结论就成立 ✓ 而且以后**移动后必须重扫**就成了硬规则 ✓
--
-- 下发：{"who":"cc0","cmd":"run_job","args":{"target":1,"name":"probe_refresh.lua"}}

local METHODS = { "list", "getItems", "getItemInSlot", "getContainerSize",
                  "pullItemIntoSlot", "pushItems", "getOwner" }

local function probe_all(tag)
  local res = { tag = tag, sides = {} }
  for _, side in ipairs(peripheral.getNames()) do
    local row = { side = side, type = peripheral.getType(side), has = {}, calls = {} }
    local ok, p = pcall(peripheral.wrap, side)
    if ok and p then
      for _, m in ipairs(METHODS) do
        if type(p[m]) == "function" then
          row.has[#row.has + 1] = m
        end
      end
      -- 真正的功能测试：能被调用成功的才算 ✓
      if type(p.list) == "function" then
        local okL, r = pcall(p.list)
        row.calls.list = okL and r or ("ERR: " .. tostring(r))
      end
      if type(p.getItems) == "function" then
        local okI, r = pcall(p.getItems)
        row.calls.getItems = okI and r or ("ERR: " .. tostring(r))
      end
    end
    res.sides[#res.sides + 1] = row
  end
  return res
end

local out = {}
out.before = probe_all("before")

-- 强制刷新：移动一格再回来（上下都是空气时最安全 ✓）
local moved = {}
if turtle.up() then
  moved.up = true
  if not turtle.down() then moved.down = false end
else
  moved.up = false
end
out.moved = moved
sleep(0.5)

out.after = probe_all("after")

-- 如果刷新后真的出现了库存管理器，就直接把容器清单读出来 ✓
for _, row in ipairs(out.after.sides) do
  if type(row.calls.list) == "table" then
    out.containers_on = row.side
    out.containers = row.calls.list
    break
  end
end

return true, out
