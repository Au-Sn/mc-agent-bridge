-- job_craft_one.lua —— 按**指定布局**合成一样东西（通用合成作业）
--
-- 为什么需要一个通用作业，而不是每种配方写一个 ✗：
--   CC 的合成窗口有硬约束（源码 `tryCrafting` 逐格检查 ✓）：
--     **3×3 窗口之外的槽位必须全空** ✗；窗口之内、配方之外的格子也必须空 ✗
--   ⇒ 每次合成前都得"清场 + 精确摆位" ✓ —— 这套动作对**所有配方都一样** ✓
--   ⇒ 于是把它做成一个带参数的作业 ✓ 配方变了只改参数 ✓ 不改代码 ✓
--
-- 参数（都可省，但一般都要给 ✓）：
--   fill = "槽位:物品,槽位:物品,…"   精确摆位（1-based 槽位 ✓ 例如 "2:minecraft:oak_planks,3:minecraft:oak_slab"）
--   keep = "物品:数量,…"            只保留这么多（其余**全部丢到脚下**，干完再吸回来 ✓）
--   want = 期望产物名片段          用来验收（例如 "oak_sieve" ✓）
--   probe = false                 跳过 craft(0) 无损探测（默认会探测 ✓）
--
-- 安全 ✓：只丢自己的东西 ✓（丢在脚下那一格 ✓ 下面有地面 ✓）干完把六面都吸一遍 ✓。
-- ⚠ 作业前请确认**假人不在旁边** ✗（否则掉落物会被它捡走 ✓ 见 docs/错题本.md I12 ✓）

local a = ...
local FILL, KEEP = {}, {}
local want = (a and a.want) or ""
local log = function(s)
  print(s)
  local f = fs.open("craft_one.log", "a")
  if f then f.writeLine(os.date("%H:%M:%S ") .. tostring(s)); f.close() end
end

if a and type(a.fill) == "string" then
  for part in a.fill:gmatch("[^,]+") do
    local slot, item = part:match("^%s*(%d+)%s*:%s*([%w_:%.%-]+)%s*$")
    if slot and item then
      if not item:find(":", 1, true) then item = "minecraft:" .. item end
      FILL[#FILL + 1] = { slot = tonumber(slot), item = item }
    end
  end
end
if a and type(a.keep) == "string" then
  for part in a.keep:gmatch("[^,]+") do
    local item, n = part:match("^%s*([%w_:%.%-]+)%s*:%s*(%d+)%s*$")
    if item and n then
      if not item:find(":", 1, true) then item = "minecraft:" .. item end
      KEEP[item] = tonumber(n)
    end
  end
end
if #FILL == 0 then
  return true, { job = "craft_one", ok = false, why = "需要 fill=槽位:物品,…" }
end

local function invList()
  local out = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d then out[#out + 1] = string.format("%d:%s x%d", i, d.name, turtle.getItemCount(i)) end
  end
  return table.concat(out, ", ")
end

local function countOf(item)
  local n = 0
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and d.name == item then n = n + turtle.getItemCount(i) end
  end
  return n
end

local function hasName(pat)
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d and tostring(d.name):find(pat, 1, true) then return i, d.name end
  end
  return nil
end

log("=== START craft_one want=" .. want .. " ===")
log("起始背包: " .. invList())

-- ① 丢掉"不在 keep 清单里"的东西（整叠丢 ✓ 丢在脚下 ✓ 稍后吸回 ✓）
local dropped = {}
for i = 1, 16 do
  local d = turtle.getItemDetail(i)
  if d and not KEEP[d.name] then
    local n = turtle.getItemCount(i)
    turtle.select(i)
    if turtle.dropDown(n) then
      dropped[#dropped + 1] = string.format("%s x%d@s%d", d.name, n, i)
    end
  end
end
log("丢掉多余: " .. (#dropped > 0 and table.concat(dropped, ", ") or "（无）"))

-- ② keep 清单里的东西：只留需要的数量，多出来的也丢
for item, need in pairs(KEEP) do
  local have = countOf(item)
  if have > need then
    local excess = have - need
    for i = 1, 16 do
      if excess <= 0 then break end
      local d = turtle.getItemDetail(i)
      if d and d.name == item then
        local n = turtle.getItemCount(i)
        local take = math.min(n, excess)
        turtle.select(i)
        if turtle.dropDown(take) then
          excess = excess - take
          dropped[#dropped + 1] = string.format("%s x%d@s%d", item, take, i)
        end
      end
    end
  end
end
log("清场后背包: " .. invList())

-- ③ 精确摆位：每个 fill 槽位放**恰好 1 个**指定物品（从同样物品的堆里分）
-- ⚠ 必须**多轮**尝试（真实事故 ✓）：单轮会卡在"目的地被别的物品占着" ✗
--   例：木棍正躺在"该放木板"的那一格 ✓ → 单轮既搬不动它、也放不进木板 ✗
--   第 1 轮只填**空**的目的地（顺手把冲突格腾空 ✓）第 2..4 轮再收拾剩下的 ✓
local function fillOk(f)
  local d = turtle.getItemDetail(f.slot)
  return (d ~= nil) and (d.name == f.item)
end
for pass = 1, 4 do
  local pending = 0
  for _, f in ipairs(FILL) do
    if not fillOk(f) then
      pending = pending + 1
      local slotEmpty = (turtle.getItemDetail(f.slot) == nil)
      if pass > 1 or slotEmpty then
        local donor
        for i = 1, 16 do
          local di = turtle.getItemDetail(i)
          if di and di.name == f.item and i ~= f.slot then
            local claimed = false
            for _, g in ipairs(FILL) do
              if g.slot == i and g.item == f.item then claimed = true end
            end
            -- 供体可以是"非 fill 槽位" ✓ 或者"自己那一格还有富余" ✓
            if (not claimed) or turtle.getItemCount(i) > 1 then donor = i; break end
          end
        end
        if donor then
          turtle.select(donor)
          local ok = turtle.transferTo(f.slot, 1)
          log(string.format("摆位(第%d轮): 槽%d -> 槽%d (%s x1) %s",
            pass, donor, f.slot, f.item, tostring(ok)))
        end
      end
    end
  end
  if pending == 0 then break end
  sleep(0.1)
end
-- 摆完自检：把每个 fill 槽位实际是什么打出来（验收用 ✓ 不猜 ✓）
do
  local parts = {}
  for _, f in ipairs(FILL) do
    local d = turtle.getItemDetail(f.slot)
    parts[#parts + 1] = string.format("%d=%s%s", f.slot,
      d and d.name:gsub("minecraft:", "") or "空",
      (d and d.name == f.item) and "" or "✗")
  end
  log("摆位自检: " .. table.concat(parts, " "))
end
-- ③b 每个 fill 槽位若多余 1 个，也丢出去（窗口里只能有配方要的那几个 ✓）
for _, f in ipairs(FILL) do
  local d = turtle.getItemDetail(f.slot)
  if d and d.name == f.item and turtle.getItemCount(f.slot) > 1 then
    turtle.select(f.slot)
    local extra = turtle.getItemCount(f.slot) - 1
    turtle.dropDown(extra)
    log(string.format("槽%d 清到只剩 1 个（丢掉 %d）", f.slot, extra))
  end
end
log("摆位后背包: " .. invList())

-- ④ 无损探测 + 合成
local out = {}
if a and a.probe == false then
  out.probe = "skipped"
else
  local okP, errP = turtle.craft(0)
  out.probe = tostring(okP)
  out.probe_err = errP
  log("探测 craft(0) = " .. tostring(okP) .. " / " .. tostring(errP))
  if not okP then
    -- 探测失败就别硬来（省得把材料搞乱 ✓）
    log("布局不匹配 ✓ 不执行合成 ✓（先看上面的背包与 fill 清单 ✓）")
    -- 仍然把丢掉的吸回来 ✓ 不要亏材料 ✓
    for _ = 1, 3 do
      turtle.suckDown(); turtle.suckUp()
      for _ = 1, 4 do turtle.suck(); turtle.turnRight() end
      sleep(0.2)
    end
    return true, { job = "craft_one", ok = false, why = "布局不匹配", probe_err = errP,
                   inventory = invList(), dropped = dropped }
  end
end

local okC, errC = turtle.craft(tonumber(a and a.count) or 1)
out.crafted = okC
out.craft_err = errC
log("合成 craft = " .. tostring(okC) .. " / " .. tostring(errC))
log("合成后背包: " .. invList())

-- ⑤ 把丢在地上的材料**吸回来**（六面都试 ✓）
for _ = 1, 4 do
  turtle.suckDown(); turtle.suckUp()
  for _ = 1, 4 do turtle.suck(); turtle.turnRight() end
  sleep(0.2)
end

local slot, name = (want ~= "") and hasName(want) or nil, nil
if slot then name = select(2, hasName(want)) end
log("最终背包: " .. invList() .. " | 产物 " .. tostring(name))
return true, {
  job = "craft_one", ok = (want == "" or slot ~= nil),
  want = want, got_slot = slot, got_name = name,
  probe = out.probe, probe_err = out.probe_err,
  crafted = out.crafted, craft_err = out.craft_err,
  dropped = dropped,
  inventory = invList(),
}
