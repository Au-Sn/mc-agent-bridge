--[[
  agent_bridge.lua — MC Agent Bridge 游戏内主程序（CC:Tweaked / Minecraft 1.20.1）
  ==================================================================================

  跑在一台「Advanced Computer」上，负责：
    1. 轮询网关取指令   GET  /api/next?who=<who>
    2. 执行（本地执行，或通过 rednet 转发给海龟）
    3. 回报结果与感知   POST /api/state

  一键安装（游戏内）：
      wget run http://<网关IP>:8765/files/agent_bridge.lua

  首次运行会在当前目录生成 bridge.cfg，可直接 edit bridge.cfg 修改。
  建议先保持 dry_run=true 跑通通路，再改成 false 真执行。

  ⚠ 重要：CC:Tweaked 默认可能禁止访问私有网段，
     需在服务端 config/computercraft-server.toml 放行 $private（见 docs/plan-c-1.20.1.md 第 6 节）
]]

--------------------------------------------------------------------------------
-- 配置
--------------------------------------------------------------------------------
-- ⚠ 命令行参数必须在【主 chunk】捕获：
--    Lua 里函数体内的 `...` 是该函数**自己的**可变参数（此处为空），
--    程序启动参数只存在于主 chunk 的 `...`；写成 main() 里取 `...` 会永远得到 nil。
--    依据（已核对）：CC 的 wget.lua run 分支是 `pcall(func, table.unpack(tArgs))`，
--    即用 pcall 执行 chunk，额外参数就成为该 chunk 的 `...`。
local ARGV = { ... }

local CFG_FILE = "bridge.cfg"

local DEFAULTS = {
  gateway     = "http://127.0.0.1:8765",  -- 网关地址（本机开服可写 127.0.0.1；远程服写本机内网 IP）
  who         = "",                       -- 留空 = 自动用 cc<计算机ID>（保证多台不重名）；也可手写固定名字
  dry_run     = "true",                   -- true=只回报不真执行（首次调试用）
  poll_ms     = "100",                    -- ★★§79.448✗★★：★500 → **100**✗★
                                           --   ★实测（★2026-10-30✗★）：★所有命令都 **604~660 ms**
                                           --   （★连最便宜的 dshdo status 也一样✗★）
                                           --   ⇒ ★**瓶颈是轮询间隔 ✗ 不是命令本身**✗★
                                           --   ★⇒ 500 ms 的轮询占了 **绝大部分** ✗ 改 100 应该砍到 ~200 ms✗★ ✓
  report_every= "10",                     -- 每 N 次轮询上报一次状态
  rednet_chan = "4200",                   -- 海龟通信频道
}

local cfg = {}
local function loadCfg()
  for k, v in pairs(DEFAULTS) do cfg[k] = v end
  if fs.exists(CFG_FILE) then
    local f = fs.open(CFG_FILE, "r")
    if f then
      while true do
        local line = f.readLine()
        if not line then break end
        local k, v = line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
        if k and v ~= "" then cfg[k] = v end
      end
      f.close()
    end
  else
    local f = fs.open(CFG_FILE, "w")
    if f then
      f.writeLine("# MC Agent Bridge 配置（改完重启程序生效）")
      for k, v in pairs(DEFAULTS) do
        f.writeLine(k .. "=" .. v)
      end
      f.close()
    end
    print("[bridge] 已生成 " .. CFG_FILE .. "（默认 dry_run=true）")
  end
end

loadCfg()

local BASE        = (cfg.gateway:gsub("/+$", ""))
-- ⚠ 身份唯一化（真实事故）：
--   原来默认 who="mine1"，于是**任何**一台跑了本程序的机器都自称 mine1。
--   当多台机器同时轮询时，指令会被"随机一方"取走、状态互相覆盖，
--   现场表现是"指令时好时坏、结果对不上、外设列表忽多忽少"（真实踩过两次）。
--   现在默认按**计算机 ID** 生成唯一名字（cc0 / cc1 / …），配置里显式写了才覆盖。
local WHO         = (cfg.who ~= "" and cfg.who) or ("cc" .. tostring(os.getComputerID()))
local DRY_RUN     = (tostring(cfg.dry_run) == "true")
local POLL_S      = (tonumber(cfg.poll_ms) or 500) / 1000
local REPORT_EVERY= tonumber(cfg.report_every) or 10
local CHAN        = tonumber(cfg.rednet_chan) or 4200

local IS_TURTLE = (turtle ~= nil)

--------------------------------------------------------------------------------
-- HTTP 小工具
--------------------------------------------------------------------------------
local function httpGet(url)
  local ok, res = pcall(http.get, url)
  if not ok then return nil, tostring(res) end
  if not res then return nil, "http.get 失败（检查 computercraft-server.toml 是否放行该地址）" end
  local body = res.readAll()
  res.close()
  return body
end

--------------------------------------------------------------------------------
-- JSON 净化：把任意 Lua 结构深拷贝成"纯数组/纯对象 + 基本类型"
--
-- 为什么必须做（真实事故）：
--   CC 的 textutils.serializeJSON 遇到**同一个表对象出现两次**会直接报
--   "Cannot serialize table with repeated entries"（见其 textutils.lua 的
--   tracking[t] == false 分支）。而 buildState 里 st.peripherals = P.names，
--   status 的结果里又有 result.peripherals = P.names —— 同一个对象被引用两次，
--   于是第一条 status 指令的结果就整条序列化失败。
--   另外外设（Advanced Peripherals）返回的表结构五花八门，
--   直接丢给 serializeJSON 随时可能踩到混合键/循环引用。
-- 做法：递归复制成新表；数组→数组，其它→字符串键对象；非基本类型→字符串。
--------------------------------------------------------------------------------
local function jsonSafe(v, depth, seen)
  depth = depth or 0
  seen = seen or {}
  local t = type(v)
  if t == "string" or t == "number" or t == "boolean" then return v end
  if v == nil then return nil end
  if t ~= "table" then return tostring(v) end
  if depth > 12 then return "(超过深度上限)" end
  if seen[v] then return "(循环引用)" end
  seen[v] = true

  local n = #v
  local isArray = true
  for k in pairs(v) do
    if type(k) ~= "number" or k < 1 or k > n or k % 1 ~= 0 then isArray = false; break end
  end

  local out = {}
  if isArray then
    for i = 1, n do out[i] = jsonSafe(v[i], depth + 1, seen) end
  else
    for k, val in pairs(v) do
      out[type(k) == "string" and k or tostring(k)] = jsonSafe(val, depth + 1, seen)
    end
  end
  seen[v] = nil   -- 离开时释放：兄弟位置出现的同一张表各自得到独立副本
  return out
end

local function httpPostJSON(url, tbl)
  local safe = jsonSafe(tbl)
  local okS, payload = pcall(textutils.serializeJSON, safe)
  if not okS then return nil, "状态序列化失败：" .. tostring(payload) end
  local ok, res = pcall(http.post, url, payload, { ["Content-Type"] = "application/json" })
  if not ok then return nil, tostring(res) end
  if not res then return nil, "http.post 失败" end
  local body = res.readAll()
  res.close()
  return body
end

local function decode(s)
  if not s or s == "" then return nil end
  local ok, t = pcall(textutils.unserializeJSON, s)
  if ok then return t end
  return nil
end

--------------------------------------------------------------------------------
-- 外设发现（Advanced Peripherals 的 API 名称在各版本略有差异，这里做容错探测）
--------------------------------------------------------------------------------
local P = { modems = {} }

local function callFirst(obj, names, ...)
  if not obj then return nil, "peripheral 不存在" end
  local lastErr
  for _, n in ipairs(names) do
    local fn = obj[n]
    if type(fn) == "function" then
      local ok, r1, r2 = pcall(fn, ...)
      if ok and r1 ~= nil then return r1, r2 end
      -- 记录"调用了但没拿到值"的原因：很多外设方法存在、但调用会失败
      -- （例如 Inventory Manager 没贴容器、Geo Scanner 没燃料）
      -- 不记录的话就会错报成"无可用的 API"，把人带偏。
      if ok then
        lastErr = n .. "() 返回 nil"
      else
        lastErr = n .. "() 报错：" .. tostring(r1)
      end
    elseif lastErr == nil then
      lastErr = n .. " 不是方法"
    end
  end
  return nil, lastErr or ("无可用的 API：" .. table.concat(names, "/"))
end

local function discover()
  P = { modems = {}, names = {} }
  -- 外设类型名在各版本/各模组里写法不一：
  -- AP 实测上报的是 "chatBox"/"geoScanner"/"blockReader"/"playerDetector"/"inventoryManager"
  -- （驼峰），而有些版本是 "chat_box"（下划线）。统一归一化后再比对，
  -- 否则某个外设会静默识别不到（真实踩过：inventory_manager 因大小写不匹配没被识别）。
  local function norm(s)
    return tostring(s or "?"):lower():gsub("[_%s%-]", "")
  end
  for _, name in ipairs(peripheral.getNames()) do
    local t = peripheral.getType(name) or "?"
    table.insert(P.names, name .. "(" .. t .. ")")
    local w = peripheral.wrap(name)
    local nt = norm(t)
    if peripheral.hasType(name, "modem") or nt == "modem" or nt == "wirelessmodem" or nt == "wiredmodem" then
      table.insert(P.modems, name)
      if w and w.open then pcall(w.open, CHAN) end
    end
    if nt == "chatbox" or (w and w.sendMessage) then P.chat = P.chat or w end
    if nt == "geoscanner" or (w and w.scan and not w.getBlockData) then P.geo = P.geo or w end
    if nt == "blockreader" or (w and w.getBlockData) then P.blockReader = P.blockReader or w end
    if nt == "playerdetector" or (w and w.getOnlinePlayers) then P.playerDet = P.playerDet or w end
    if nt == "inventorymanager" or (w and w.list and w.getItem) then P.invMan = P.invMan or w end
  end
  -- rednet 只在有调制解调器时打开
  if #P.modems > 0 then
    for _, side in ipairs(P.modems) do pcall(rednet.open, side) end
  end
end

--------------------------------------------------------------------------------
-- 朝向跟踪（CC 的海龟没有可靠的"当前朝向"读取，这里自维护 + 提供校准指令）
--------------------------------------------------------------------------------
local FACING = { "north", "east", "south", "west" }   -- 顺时针；north=-z, east=+x
local facingIdx = 1
local facingKnown = false

local DIRVEC = {
  north = { x = 0,  z = -1 },
  east  = { x = 1,  z = 0 },
  south = { x = 0,  z = 1 },
  west  = { x = -1, z = 0 },
}

local function turnToIdx(target)
  if not IS_TURTLE then return false, "非海龟本体" end
  local guard = 0
  while facingIdx ~= target and guard < 4 do
    if ((target - facingIdx) % 4) <= 2 then
      if not turtle.turnRight() then return false, "turnRight 失败" end
      facingIdx = facingIdx % 4 + 1
    else
      if not turtle.turnLeft() then return false, "turnLeft 失败" end
      facingIdx = (facingIdx - 2) % 4 + 1
    end
    guard = guard + 1
  end
  facingKnown = true
  return true
end

local function idxOf(dir)
  for i, d in ipairs(FACING) do if d == dir then return i end end
  return nil
end

--------------------------------------------------------------------------------
-- 动作原语
--------------------------------------------------------------------------------
local function fuelOk(need)
  if not IS_TURTLE then return true end
  local lvl = turtle.getFuelLevel()
  if lvl == "unlimited" then return true end
  return (tonumber(lvl) or 0) >= (need or 1)
end

local function moveOne(fn, digFn)
  if not fuelOk(1) then return false, "燃料不足" end
  local ok, why = fn()
  if ok then return true end
  -- 被挡住就先挖再走
  if digFn then
    local dug = digFn()
    if dug then
      local ok2 = fn()
      if ok2 then return true end
    end
  end
  return false, tostring(why or "blocked")
end

local A = {}
local geoTel   -- 前置声明：A.status 与 A.scan 都要用它（具体定义在下面），
               -- 不前置的话 A.status 里引用到的是 nil 全局 → 运行期 "attempt to call a nil value"

-- 远程退出/关机标志（由 A.quit / A.shutdown 置位，主循环在回报之后执行）
local WANT_QUIT = false
local WANT_SHUTDOWN = false
local WANT_REBOOT = false

-- EXIT_NOW：告诉最外层的"看门狗"这次是**故意**停的，别再自动重启。
-- 为什么需要它（真实事故）：
--   看门狗必须能兜住一切异常并自动重启，否则机器一旦退出就停在那里等人进游戏重敲命令
--   ——那是无人值守场景下最贵的失败模式。
--   但 os.shutdown() / os.reboot() 在 Lua 层是"抛异常式"地终止程序的，
--   没有这个标志的话，看门狗会把"我要求它关机"理解成"它崩了，重启它"，
--   于是关机/重启功能被自己的自愈机制干掉。
local EXIT_NOW = false

-- --- 移动 ---------------------------------------------------------------- --
local function makeMove(name, fn, digFn)
  A[name] = function(args)
    local n = tonumber(args and args.n) or 1
    if not IS_TURTLE then return false, "该指令需要海龟本体" end
    for i = 1, n do
      local ok, err = moveOne(fn, digFn)
      if not ok then return false, string.format("%s 第 %d 步失败：%s", name, i, tostring(err)) end
    end
    return true, { moved = n }
  end
end

makeMove("forward", function() return turtle.forward() end, function() return turtle.dig() end)
makeMove("back",    function() return turtle.back() end, nil)
makeMove("up",      function() return turtle.up() end,      function() return turtle.digUp() end)
makeMove("down",    function() return turtle.down() end,    function() return turtle.digDown() end)

A.turn_left = function()
  if not IS_TURTLE then return false, "该指令需要海龟本体" end
  local ok = turtle.turnLeft()
  if ok then facingIdx = (facingIdx - 2) % 4 + 1 end
  return ok, { facing = FACING[facingIdx] }
end

A.turn_right = function()
  if not IS_TURTLE then return false, "该指令需要海龟本体" end
  local ok = turtle.turnRight()
  if ok then facingIdx = facingIdx % 4 + 1 end
  return ok, { facing = FACING[facingIdx] }
end

A.calibrate = function(args)
  local d = args and args.facing
  local i = d and idxOf(d)
  if not i then return false, "需要 facing=north|east|south|west" end
  facingIdx, facingKnown = i, true
  return true, { facing = d }
end

-- --- 指令电脑通道（Carpet 假人 / 原版指令）-------------------------------- --
-- 只有"指令电脑"（computercraft:computer_command）才有全局 commands API。
-- 这条通道的意义：/player <名字> <动作> 生成的是**服务端真实玩家实体**——
-- 拿真工具、能打架、有背包，因此不必为每种工作单独造一台海龟。
-- 需要世界配置 config/…/computercraft-server.toml 里 command_block_enabled=true。
local function hasCommandsAPI()
  return type(commands) == "table" and type(commands.exec) == "function"
end

local function cmdText(args)
  local t = args and (args.text or args.cmd or args.line)
  if type(t) ~= "string" or t == "" then return nil, "需要 text=<要执行的指令>" end
  return (t:gsub("^/", ""))   -- 带不带斜杠都接受，统一去掉
end

-- Lua 的一个经典坑：pcall 只声明两个变量时，被调用函数多出来的返回值会被丢掉。
-- CC 的 commands.exec 正是多返回值（成功标志 + 输出表）。
-- 真实事故：list / time query daytime / player Bot stop 三条完全不同的指令，
-- 回传到 Agent 的结果全都是 "true"——因为输出表在 pcall 那一行就被丢了。
-- 所以凡是"被调用者可能有多个返回值"的地方，一律用这个打包函数接全。
local function packReturns(...)
  return { n = select("#", ...), ... }
end

-- 单点读方块——**读方块只有这一个入口**。
-- ⚠ 索引陷阱（同一类错误已经犯了三次，值得写进纪律）：
--   packReturns 之后，值的下标取决于被调用者返回几个值：
--     commands.exec          → (ok?, 成功标志, 输出表, 结果码)  值在 p[2] 与 p[3]
--     commands.getBlockInfo  → (ok?, 方块表)                    值在 p[2]
--   于是"照抄上一处的 p[3]"就会静默拿到 nil——不报错，只是结果看起来是"没做成"，
--   最容易被误读成"游戏里没生效"。与其在每个调用点记下标，不如只留这一个入口。
--
-- ⚠ 位置也很关键：它必须是**最靠前**的局部函数。
--   真实事故：这两个函数一开始写在文件后半段，而 plant_sapling 在它们之前定义，
--   Lua 的局部变量只在其声明之后可见 → 运行期 "attempt to call global 'readBlock' (a nil value)"。
--   （同一个坑在 A.status 引用 geoTel 时也踩过一次。）
local function readBlock(x, y, z)
  local p = packReturns(pcall(commands.getBlockInfo, x, y, z))
  if not p[1] or type(p[2]) ~= "table" then return nil end
  return p[2].name or p[2].block, p[2]
end

-- 装饰性小方块（不完整方块）：草、蕨、花、花瓣、树苗、火把、铁轨、按钮、雪层…
-- ⚠ 玩家指出来的真实问题：这类方块**没有完整碰撞箱**，不能当"地面/支撑"用 ✗。
--   我原来的判断只看"是不是空气" ✗ → 于是把长着草的一格当成实地 ✓ →
--   拿它当参照放方块 → 放出来就是**悬空** ✗；走路时也会误判"脚下有地" ✗（防坠被削弱）。
-- 所以拆成两个概念：
--   cellIsOpen : 这格能不能收下一块方块（空气，或可被替换掉的装饰）
--   standable  : 这格算不算真正的落脚/支撑面（必须是完整方块）
local DECOR = {
  "grass", "fern", "flower", "petal", "_sapling", "torch", "rail", "_button",
  "pressure_plate", "sign", "snow", "vine", "lichen", "mushroom", "wheat",
  "carrots", "potatoes", "beetroots", "bush", "lily", "dripleaf", "kelp",
  "seagrass", "banner", "carpet", "roots", "sprouts", "azalea", "berry",
  "coral", "crop",
}
local function isDecor(nm)
  if type(nm) ~= "string" then return false end
  if nm == "minecraft:air" or nm == "minecraft:cave_air" or nm == "minecraft:void_air" then return false end
  -- ⚠ 真实事故（自己引入的回归）：装饰表里有 "grass" ✗，而 `minecraft:grass_block`
  --   也**包含** "grass" ✗ → 于是所有草方块被判定成"不完整方块" →
  --   walk_to 直接拒绝走上草地 ✗（机器人连正常走路都被自己的安全检查拦住）。
  --   修法：先按"名字里带 block 的都算完整方块"排除（grass_block / moss_block / snow_block…）✓，
  --   再匹配装饰关键词。短的草是 minecraft:grass ✓、草方块是 minecraft:grass_block ✓，必须区分开。
  local bare = nm:match(":(.+)$") or nm
  if bare:find("block", 1, true) then return false end
  for _, k in ipairs(DECOR) do
    if bare:find(k, 1, true) then return true end
  end
  return false
end

local function blockIsAir(x, y, z)
  local nm = readBlock(x, y, z)
  return nm == "minecraft:air" or nm == "minecraft:cave_air" or nm == "minecraft:void_air"
end

-- 这格能不能放方块：空气，或只是可替换的装饰（放了会被自动替换掉 ✓）
local function cellIsOpen(x, y, z)
  local nm = readBlock(x, y, z)
  if type(nm) ~= "string" then return false end
  return blockIsAir(x, y, z) or isDecor(nm)
end

-- 作业进度**落盘**：CC 电脑的文件系统就在主机磁盘上
-- （saves/<世界>/computercraft/computer/<id>/），所以"写进自己机器上的文件"
-- 等于给 Agent 留了一份**不依赖网络回传**的记录。
--
-- 为什么非要有它（真实事故）：
--   一次"往外扩平台"作业跑了 9 分钟、一块都没铺、而且**回传完全丢失**——
--   没有 Lua 报错、机器心跳正常、外部看到的是一切正常，只有世界毫无变化 ✗。
--   这类失败无法靠"等回传"发现，必须靠磁盘上的进度记录 + 世界普查双重核对。
local function jobNote(name, data)
  local okS, line = pcall(textutils.serializeJSON, jsonSafe(data or {}))
  local f = fs.open("job.log", "a")
  if not f then return false end
  f.writeLine(string.format("%s %s %s", os.date("%H:%M:%S"), name, okS and line or "?"))
  f.close()
  return true
end

A.cmd = function(args)
  if not hasCommandsAPI() then
    return false, "本机不是指令电脑（没有 commands API）：请把程序放到 computercraft:computer_command 上"
  end
  local text, err = cmdText(args)
  if not text then return false, err end
  if DRY_RUN then return true, { dry_run = true, text = text } end
  -- pcall 包住：指令本身报错（如权限不足）不应该让整台电脑崩掉。
  local p = packReturns(pcall(commands.exec, text))
  if not p[1] then return false, "指令执行异常：" .. tostring(p[2]) end
  -- p[1]=pcall 是否成功，p[2]=指令是否成功（boolean），p[3..]=输出
  local lines, types = {}, {}
  for i = 2, p.n do
    local v = p[i]
    types[#types + 1] = type(v)
    if type(v) == "table" then
      for _, l in ipairs(v) do lines[#lines + 1] = tostring(l) end
    elseif v ~= nil and i > 2 then
      lines[#lines + 1] = tostring(v)
    end
  end
  return true, {
    text      = text,
    success   = p[2],
    lines     = lines,
    count     = #lines,
    -- 回传返回值的类型构成：这一项让"输出被吞掉"这类问题下次能一眼看出来
    ret_types = table.concat(types, ","),
  }
end

-- /player Bot attack 这类是"持续动作"，exec 会一直阻塞到动作结束才返回，
-- 对键盘/移动这类动作就是"永远不返回"。所以另给一个不等结果的版本。
A.cmd_async = function(args)
  if not hasCommandsAPI() then
    return false, "本机不是指令电脑（没有 commands API）"
  end
  if type(commands.execAsync) ~= "function" then
    return false, "本版本 CC 没有 commands.execAsync"
  end
  local text, err = cmdText(args)
  if not text then return false, err end
  if DRY_RUN then return true, { dry_run = true, text = text } end
  local ok, res = pcall(commands.execAsync, text)
  if not ok then return false, "指令投递异常：" .. tostring(res) end
  return true, { text = text, async = true }
end

-- --- 地形普查：指令电脑自带的"眼睛" ---------------------------------------- --
-- 为什么不用现成外设：这台基地里的 Geo Scanner 燃料是 0（上限也是 0），等于废的。
-- 而指令电脑的 commands.getBlockInfo(x, y, z) 能直接读**任意位置**的方块，
-- 不要外设、不要燃料——挖矿/建造/砍树要的正是这种"点哪读哪"的能力。
--
-- 返回值里刻意带上 sample（前两条原始结构的序列化文本）：
-- 不同 CC 版本里这个表的字段名可能有差异（name / block / id），
-- 与其按键名猜，不如让第一次真实调用把结构回传上来，照着写。
local SURVEY_KEYS = { "log", "leaves", "sapling", "dirt", "grass_block", "podzol", "sand", "water" }

local function surveyInteresting(name)
  if type(name) ~= "string" then return false end
  for _, k in ipairs(SURVEY_KEYS) do
    if name:find(k, 1, true) then return true end
  end
  return false
end

local function blockNameOf(info)
  if type(info) ~= "table" then return nil end
  if type(info.name) == "string" then return info.name end
  if type(info.block) == "string" then return info.block end
  if type(info.id) == "string" then return info.id end
  return nil
end

A.survey = function(args)
  if not hasCommandsAPI() then
    return false, "survey 需要指令电脑（只有命令电脑才有 commands 表）"
  end
  if type(commands.getBlockInfo) ~= "function" then
    return false, "本版本 CC 没有 commands.getBlockInfo，无法普查"
  end
  local a = args or {}
  local cx, cy, cz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (cx and cy and cz) then return false, "需要 x / y / z（普查中心点）" end
  local r  = math.floor(tonumber(a.radius) or 6)
  local ry = math.floor(tonumber(a.radius_y) or math.min(r, 6))
  if r  < 0 then r  = 0 end
  if r  > 12 then r  = 12 end
  if ry < 0 then ry = 0 end
  if ry > 8 then ry = 8 end
  local maxList = math.floor(tonumber(a.max_list) or 400)

  local x0, x1 = cx - r,  cx + r
  local y0, y1 = cy - ry, cy + ry
  local z0, z1 = cz - r,  cz + r
  local t0 = os.clock()

  -- optional：only="oak_log" 时只关心该子串，便于"找树/找矿"直接聚焦
  local only = a.only
  -- 分块扫描。CC 的 getBlockInfos 有内置体积上限，实测 17³=4913 会被直接拒绝，
  -- 报错原文 "Too many blocks"。正确做法不是缩小扫描范围（范围是作业需求，
  -- 不能因为工具限制就妥协），而是把大箱子切成安全小块、多发几次调用。
  -- 默认 4×4×4=64 方块/次：稳、且单次往返开销很小。
  local tile = math.floor(tonumber(a.tile) or 4)
  if tile < 1 then tile = 1 end
  if tile > 16 then tile = 16 end

  local counts, list, capped = {}, {}, false
  local scanned, interesting, calls = 0, 0, 0
  local failed = {}

  -- 把一块的结果并入统计。顺序按实测结论 y（最外）→ z → x（最内）解码。
  local function absorb(arr, tx, ty, tz, tny, tnz, tnx)
    local idx = 0
    for yy = 0, tny - 1 do
      for zz = 0, tnz - 1 do
        for xx = 0, tnx - 1 do
          idx = idx + 1
          local e = arr[idx]
          if type(e) == "table" then
            local nm = e.name or e.block
            if type(nm) == "string" then
              scanned = scanned + 1
              local keep
              if only then keep = (nm:find(only, 1, true) ~= nil)
              else keep = surveyInteresting(nm) end
              if keep then
                interesting = interesting + 1
                counts[nm] = (counts[nm] or 0) + 1
                if #list < maxList then
                  list[#list + 1] = { x = tx + xx, y = ty + yy, z = tz + zz, name = nm }
                else
                  capped = true
                end
              end
            end
          end
        end
      end
    end
  end

  for ty = y0, y1, tile do
    local tyEnd = math.min(ty + tile - 1, y1)
    for tz = z0, z1, tile do
      local tzEnd = math.min(tz + tile - 1, z1)
      for tx = x0, x1, tile do
        local txEnd = math.min(tx + tile - 1, x1)
        calls = calls + 1
        local q = packReturns(pcall(commands.getBlockInfos, tx, ty, tz, txEnd, tyEnd, tzEnd))
        if q[1] and type(q[2]) == "table" then
          absorb(q[2], tx, ty, tz, tyEnd - ty + 1, tzEnd - tz + 1, txEnd - tx + 1)
        else
          failed[#failed + 1] = { x = tx, y = ty, z = tz, error = tostring(q[2]) }
        end
      end
    end
  end
  return true, {
    center    = { x = cx, y = cy, z = cz },
    box       = { x0 = x0, y0 = y0, z0 = z0, x1 = x1, y1 = y1, z1 = z1 },
    radius    = r,
    radius_y  = ry,
    returned  = scanned,
    scanned   = scanned,
    calls     = calls,
    failed    = failed,
    tile      = tile,
    found     = interesting,
    counts    = counts,
    blocks    = list,
    capped    = capped,
    order     = "y,z,x",
    elapsed_s = tonumber(string.format("%.2f", os.clock() - t0)),
  }
end

-- --- 一次性探针：确定 commands.getBlockInfos 的调用形式 --------------------- --
-- 背景：单点 getBlockInfo 实测约 50ms/次（走服务器线程），扫一片区域要几分钟，
-- 不可用。而 getBlockInfos 是批量接口——这才是"机器人的眼睛"该用的东西。
-- 字节码里的 LocalVariableTable 只告诉我们参数名
-- （minX/minY/minZ/maxX/maxY/maxZ 和一个 dimension），
-- 但参数顺序、dimension 是否必需，从字节码读不出来。
-- 与其猜（猜错就是一次"按键名猜 API"的老错），不如把候选形式都试一遍，
-- 让它把真实的成功/报错原样回传，照着写。
A.probe_bulk = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑（没有 commands 表）" end
  if type(commands.getBlockInfos) ~= "function" then return false, "本版本没有 commands.getBlockInfos" end
  local a   = args or {}
  local x   = tonumber(a.x) or 0
  local y   = tonumber(a.y) or 0
  local z   = tonumber(a.z) or 0
  local dim = a.dim or "minecraft:overworld"
  local attempts = {}

  local function attemptCall(label, ...)
    local p = packReturns(pcall(commands.getBlockInfos, ...))
    local entry = { label = label, pcall_ok = p[1] }
    if not p[1] then
      entry.error = tostring(p[2])
    else
      local types = {}
      for i = 2, p.n do types[#types + 1] = type(p[i]) end
      entry.ret_types = table.concat(types, ",")
      local first = p[2]
      if type(first) == "table" then
        entry.count = #first
        local okS, s = pcall(textutils.serialize, first[1])
        entry.first_entry = okS and s or "(序列化失败)"
      elseif first ~= nil then
        entry.first_value = tostring(first)
      end
    end
    attempts[#attempts + 1] = entry
  end

  attemptCall("6ints", x, y, z, x, y, z)
  attemptCall("6ints+dim_last", x, y, z, x, y, z, dim)
  attemptCall("dim_first+6ints", dim, x, y, z, x, y, z)
  return true, { at = { x = x, y = y, z = z }, dim = dim, attempts = attempts }
end

-- --- 排列顺序对照实验 ------------------------------------------------------- --
-- getBlockInfos 返回的每一项只有 name/state/tags，**不带坐标**。
-- 那么"第 i 项对应哪个方块"就完全取决于 Java 侧的遍历顺序，而这在文档里没有。
-- 猜错的后果很严重：会把 A 位置的方块名安到 B 位置上，据此下指令就是乱挖。
-- 做法：同一个箱子，既用批量拿一遍（names），又用单点逐格拿一遍（grid，带坐标），
-- 两边一起回传，由外部比对反推出真实顺序。用数据说话，不靠假定。
A.probe_order = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑（没有 commands 表）" end
  if type(commands.getBlockInfos) ~= "function" then return false, "本版本没有 commands.getBlockInfos" end
  local a  = args or {}
  local x0 = math.floor(tonumber(a.x) or 0)
  local y0 = math.floor(tonumber(a.y) or 0)
  local z0 = math.floor(tonumber(a.z) or 0)
  local nx = math.min(math.floor(tonumber(a.nx) or 3), 8)
  local ny = math.min(math.floor(tonumber(a.ny) or 2), 4)
  local nz = math.min(math.floor(tonumber(a.nz) or 2), 8)
  local x1, y1, z1 = x0 + nx - 1, y0 + ny - 1, z0 + nz - 1

  -- 批量（快）：整箱一次拿
  local bp   = packReturns(pcall(commands.getBlockInfos, x0, y0, z0, x1, y1, z1))
  local bulk = { ok = bp[1] }
  if bp[1] and type(bp[2]) == "table" then
    local names = {}
    for i, e in ipairs(bp[2]) do
      names[i] = (type(e) == "table" and (e.name or e.block)) or tostring(e)
    end
    bulk.count = #names
    bulk.names = names
  else
    bulk.error = tostring(bp[2])
  end

  -- 单点（慢）：作为真值，带坐标
  local t0, grid = os.clock(), {}
  for y = y0, y1 do
    for x = x0, x1 do
      for z = z0, z1 do
        local ok, info = pcall(commands.getBlockInfo, x, y, z)
        local nm = "ERR"
        if ok and type(info) == "table" then nm = info.name or info.block or "?" end
        grid[#grid + 1] = { x = x, y = y, z = z, name = nm }
      end
    end
  end
  return true, {
    box    = { x0 = x0, y0 = y0, z0 = z0, x1 = x1, y1 = y1, z1 = z1, nx = nx, ny = ny, nz = nz },
    bulk   = bulk,
    grid   = grid,
    single_elapsed_s = tonumber(string.format("%.2f", os.clock() - t0)),
  }
end

-- --- 读假人背包 ------------------------------------------------------------- --
-- Carpet 的 /player 没有"查背包"子命令，但假人是**真玩家**，原版 /data 就能读到：
--   data get entity <bot> Inventory        → [{Slot: 0b, id: "...", Count: 1b}, ...]
--   data get entity <bot> SelectedItemSlot → 当前手持槽位（0-8）
-- 为什么必须解析而不是让人肉读：假人会继承真人的背包（实测：火把/洒水壶/手册…），
-- 于是"手上拿的是不是斧头"完全不确定——这直接决定砍树是 1 秒还是 3 秒。
-- 而且后面"木头变木板"必须核对数量，读背包是硬前提。
--
-- 解析要点：物品可能带嵌套 tag（洒水壶里就有 {Fluid:{...}}），
-- 所以不能用一个 [^}] 的通配扫到底；做法是"定位每项开头，再往后找它自己的 Count"。
A.bot_inv = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑（假人是靠原版 /data 读的）" end
  local a   = args or {}
  local bot = a.bot or "Bot"

  local function joinLines(v)
    if type(v) == "table" then
      local parts = {}
      for _, l in ipairs(v) do parts[#parts + 1] = tostring(l) end
      return table.concat(parts, " ")
    end
    return tostring(v)
  end

  -- ⚠ 这里必须 packReturns：commands.exec 返回 (成功标志, 输出表, 结果码) 三个值，
  --   写成 `local ok, out = pcall(commands.exec, ...)` 只会接住**第一个**返回值，
  --   于是 text 变成 "true"、背包永远解析出 0 件物品。
  --   这个错在 A.cmd 上犯过一次，这里又犯了一次——所以本次同时给 lua_lint 加了
  --   对应规则（见 tools/lua_lint.py），靠工具而不是靠记性来防复发。
  local pI = packReturns(pcall(commands.exec, "data get entity " .. bot .. " Inventory"))
  if not pI[1] then return false, "读取失败：" .. tostring(pI[2]) end
  local text = joinLines(pI[3])
  local items, init = {}, 1
  while true do
    -- ⚠ 槽位号可能是**负数**：玩家 NBT 里副手是 Slot: -106b。
    --   一开始写成 (%d+) 就把副手整个漏掉了，于是"副手放了筛网吗"这个问题
    --   永远答不上来（而它恰好是判断筛网机制的关键）。改成 (-?%d+)。
    local s, e, slotNo, idv = text:find('{Slot:%s*(-?%d+)b, id:%s*"([^"]+)"', init)
    if not s then break end
    local _, cEnd, cnt = text:find("Count:%s*(%d+)b", e)
    items[#items + 1] = {
      slot  = tonumber(slotNo),
      id    = idv,
      count = cnt and tonumber(cnt) or nil,
    }
    init = cEnd or e
  end

  -- 手持槽位：输出前缀会被客户端本地化（中文），所以只取结尾的数字，
  -- 不依赖任何固定文案——这是吃过"按键名猜 API"的亏之后的习惯。
  local held = nil
  local pS = packReturns(pcall(commands.exec, "data get entity " .. bot .. " SelectedItemSlot"))
  if pS[1] then
    local h = joinLines(pS[3]):match("(%d+)%s*$")
    if h then held = tonumber(h) end
  end

  local heldItem = nil
  for _, it in ipairs(items) do
    if it.slot == held then heldItem = it end
  end
  return true, {
    bot       = bot,
    held_slot = held,
    held_item = heldItem and heldItem.id or nil,
    count     = #items,
    items     = items,
    -- 回传原文片段：解析规则万一没覆盖某种物品格式，这里能直接看出来
    raw_head  = text:sub(1, 300),
  }
end

-- --- 手持物品 / 右键使用 / 种树苗 ------------------------------------------- --
-- 让假人手持指定物品（按名字子串找槽位）。
-- 为什么需要：假人继承真人背包，手上可能是火把（实测就是）。而"种树苗/放方块"
-- 都要求手上拿的正是那个东西，否则 use 只是对着地面空右键。
-- 槽位不猜：先用 A.bot_inv 读出真实槽位再切（斧头实际在第 5 槽，不是想当然的第 1 槽）。
A.hold_item = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a    = args or {}
  local bot  = a.bot or "Bot"
  local want = a.item
  if type(want) ~= "string" or want == "" then return false, "需要 item=<物品名子串>" end
  local ok, inv = A.bot_inv({ bot = bot })
  if not ok or type(inv) ~= "table" then return false, "读背包失败：" .. tostring(inv) end
  local pick = nil
  for _, it in ipairs(inv.items or {}) do
    if type(it.id) == "string" and it.id:find(want, 1, true)
       and type(it.slot) == "number" and it.slot >= 0 and it.slot <= 8 then
      pick = it
      break
    end
  end
  if not pick then
    return false, "快捷栏里没有含 '" .. want .. "' 的物品（现在手上是 " ..
           tostring(inv.held_item) .. "）"
  end
  -- ⚠ hotbar 是 **1 起算**（实测：发 `hotbar 5` 后 SelectedItemSlot = 4）。
  --   真实事故：这里一开始直接传 0 起的槽位号，于是"手持斧头"实际拿到的是上一个槽
  --   （槽 4 = 拴绳），Bot 用**徒手**砍完整棵树——而且不报错，只是慢，
  --   报告里 tool 还写着 diamond_axe，看起来完全正常。这类"静默差一位"最难查。
  local p = packReturns(pcall(commands.exec, "player " .. bot .. " hotbar " .. tostring(pick.slot + 1)))
  if not p[1] then return false, "切换槽位异常：" .. tostring(p[2]) end
  -- 自检：读回当前手持槽，确认真的切过去了（差一位的错就该在这里被抓住）
  sleep(0.25)
  local okV, after = A.bot_inv({ bot = bot })
  local landed = (okV and type(after) == "table") and after.held_slot or nil
  return true, {
    bot = bot, item = pick.id, requested_slot = pick.slot,
    held_slot = landed, held_item = (okV and type(after) == "table") and after.held_item or nil,
    was_holding = inv.held_item,
    switched = (landed == pick.slot),
  }
end

-- 右键使用一次。
-- ⚠ 必须带 once：不带修饰的 use 可能变成"一直按住右键"，放置类操作会乱放一地。
A.use_once = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local p = packReturns(pcall(commands.exec, "player " .. bot .. " use once"))
  if not p[1] then return false, "异常：" .. tostring(p[2]) end
  return true, { bot = bot, success = p[2] }
end

-- 种树苗并**自我验证**：种完立刻读那个方块，确认真的出现了 sapling。
-- 参数 x/y/z 是"树苗要占据的那一格"（通常是空气）；视线对准它下面的方块。
A.plant_sapling = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a = args or {}
  local bot = a.bot or "Bot"
  local x, y, z = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (x and y and z) then return false, "需要 x / y / z（树苗所在格）" end
  local item = a.item or "sapling"
  -- 幂等：如果那一格已经是树苗，就别再点一次（重跑作业时不该破坏现场）
  local here = readBlock(x, y, z)
  if type(here) == "string" and here:find("sapling", 1, true) then
    return true, { bot = bot, at = { x = x, y = y, z = z }, now_block = here,
                   planted = true, note = "already planted" }
  end
  local okH, hold = A.hold_item({ bot = bot, item = item })
  if not okH then return false, "拿不到树苗：" .. tostring(hold) end
  local pL = packReturns(pcall(commands.exec,
    string.format("player %s look at %d %.1f %d", bot, x, y - 0.5, z)))
  if not pL[1] or pL[2] == false then return false, "look 失败：" .. tostring(pL[2]) end
  sleep(0.3)
  local okU = A.use_once({ bot = bot })
  sleep(0.5)
  -- 验证：读回那一格（走 readBlock 这个唯一入口，避免下标再次搞错）
  local now = readBlock(x, y, z)
  return true, {
    bot = bot, at = { x = x, y = y, z = z }, held = hold.item,
    use_ok = (okU and true or false),
    now_block = now,
    planted = (type(now) == "string" and now:find("sapling", 1, true) ~= nil) or false,
  }
end

-- --- 砍树作业：一条指令做完一整件事 ---------------------------------------- --
-- 设计意图（这是"机器人"和"遥控玩具"的分界线）：
--   之前每一步（瞄准、挥击、停止）都要外部下一次指令，中间还夹着"等它挖完"的
--   人工判断——那不是机器人，那是遥控。这里把整套流程封成一个动作：
--   普查找树 → 从最低那段往上逐段瞄准 → 持续攻击 → 轮询确认方块消失 → 收工。
--   外部只需发一条指令，拿回一份带证据的作业报告。
--
-- 关键实现细节（都是踩过或推演过的坑）：
--   * attack 必须用 execAsync：`/player Bot attack continuous` 是**持续动作**，
--     用同步 exec 会一直阻塞（等于永远不返回）。
--   * 持续攻击可以在不停止的情况下**改瞄准**：重新 look at 下一个目标即可，
--     不必 stop/attack 反复切换。
--   * 轮询用 getBlockInfo（单点，约 50ms）：判断"这一段是否已经被挖掉"。
--     而不是靠 sleep 猜时间——猜时间就是"看起来在工作"，实际没动。
-- 读假人坐标：`data get entity <bot> Pos` → [4122.8d, 71.0d, 11.3d]
-- 同样只从方括号里取数字，不依赖任何本地化文案（中文客户端把前缀全部汉化了）。
local function botPos(bot)
  local p = packReturns(pcall(commands.exec, "data get entity " .. bot .. " Pos"))
  if not p[1] then return nil end
  local text
  if type(p[3]) == "table" then
    local parts = {}
    for _, l in ipairs(p[3]) do parts[#parts + 1] = tostring(l) end
    text = table.concat(parts, " ")
  else
    text = tostring(p[3])
  end
  local inside = text:match("%[([^%]]+)%]")
  if not inside then return nil end
  local n = {}
  for num in inside:gmatch("[-%d%.]+") do
    local v = tonumber(num)
    if v then n[#n + 1] = v end
  end
  if #n >= 3 then return n[1], n[2], n[3] end
  return nil
end

-- --- 安全走位 walk_to ------------------------------------------------------- --
-- 为什么"走路"必须单独写一个动作，而不能直接用 Carpet 的 move forward：
--   这里是天空岛，一步踏空 = 掉进虚空 = 身上东西全没。而 `move forward` 是**持续**前进，
--   它会一路走进空里，没有任何"看路"的概念。
-- 规则（宁可停手也不赌）：
--   1. 每一步之前，先读"前方那一格的**下面**是不是实心可站"——不是就立刻停手报告；
--   2. 前方脚下/头部空间被挡也停手（不做复杂的绕行，先把"不摔死"做对）；
--   3. 连续几步位置几乎没变 → 判定卡住并报告（真实事故：卡住却不报，看起来像在工作）；
--   4. 察觉 y 突然下降 → 立刻报告"正在坠落"（救不回来，但绝不瞒着）；
--   5. 任何出口都先 `player <bot> stop`，绝不把假人留在"一直往前走"的状态。
local DANGEROUS = { "lava", "water", "fire", "cactus", "magma", "sweet_berry", "powder_snow", "campfire" }
local PASSABLE_EXTRA = { "grass", "fern", "flower", "_sapling", "torch", "sign", "carpet", "snow", "rail", "_button", "pressure_plate" }

local function standable(nm)
  if type(nm) ~= "string" then return false end          -- 读不到就当作不可站（未知≠安全）
  if nm == "minecraft:air" or nm == "minecraft:cave_air" or nm == "minecraft:void_air" then return false end
  -- ⚠ 装饰性小方块（草/花瓣/树苗/火把…）没有完整碰撞箱，**不能当落脚面** ✗
  --   （玩家直接指出：把长草的一格当实地，放出来的方块就是悬空，走路也会误判脚下有地）
  if isDecor(nm) then return false end
  for _, bad in ipairs(DANGEROUS) do
    if nm:find(bad, 1, true) then return false end
  end
  return true
end

local function passable(nm)
  if type(nm) ~= "string" then return false end
  if nm == "minecraft:air" or nm == "minecraft:cave_air" or nm == "minecraft:void_air" then return true end
  for _, ok in ipairs(PASSABLE_EXTRA) do
    if nm:find(ok, 1, true) then return true end
  end
  return false
end

A.walk_to = function(args)
  if not hasCommandsAPI() then return false, "walk_to 需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local tx, ty, tz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (tx and tz) then return false, "需要 x / z（y 可省）" end
  local stopRange = tonumber(a.range) or 2.0
  local maxTime   = tonumber(a.timeout) or 60
  -- 清障：挡路的方块可以挖开继续走（地面除外——见下方底线说明）
  local clearMode = (a.clear ~= false)
  local maxClear  = math.floor(tonumber(a.max_clear) or 6)
  local cleared   = 0
  local t0  = os.clock()
  local trace, steps, blocked = {}, 0, nil
  local stillCount, prevX, prevZ = 0, nil, nil

  local bx0, by0, bz0 = botPos(bot)
  if not bx0 then return false, "读不到假人坐标（data get entity <bot> Pos）" end
  local result = {
    bot = bot, target = { x = tx, y = ty, z = tz },
    start = { x = bx0, y = by0, z = bz0 }, trace = trace,
  }
  local lastY = by0

  while (os.clock() - t0) < maxTime do
    local cx, cy, cz = botPos(bot)
    if not cx then blocked = "读坐标失败"; break end

    local dx, dz = tx - cx, tz - cz
    local dist = math.sqrt(dx * dx + dz * dz)
    if dist <= stopRange then
      pcall(commands.execAsync, "player " .. bot .. " stop")
      result.reached   = true
      result.at        = { x = cx, y = cy, z = cz }
      result.steps     = steps
      result.elapsed_s = tonumber(string.format("%.2f", os.clock() - t0))
      return true, result
    end

    if cy < lastY - 1.0 then
      blocked = string.format("检测到坠落：y %.2f -> %.2f", lastY, cy)
      break
    end
    lastY = cy

    -- 朝目标看：y+1 让视线接近水平，Carpet 的 move forward 沿朝向前进
    pcall(commands.exec, string.format("player %s look at %d %.1f %d", bot, tx, cy + 1.0, tz))
    sleep(0.12)

    local ux, uz = dx / dist, dz / dist
    local fx = math.floor(cx + ux * 1.2)
    local fz = math.floor(cz + uz * 1.2)
    -- ⚠ 层级算法（踩过一次 off-by-one，写清楚以免重犯）：
    --   Pos 的 y 是**脚所在的那一格**的底部。假人站在草地上时 y=71.0，
    --   意味着它占据 y=71 这一格，而地面方块在 y=70。
    --   一开始写成 floor(cy - 0.2) 得到 70，于是把"地面"当成"挡路方块"去检查，
    --   报出"前方被 minecraft:dirt_path 挡住"这种一眼就错的结论（土径是路，不挡人）。
    local baseY = math.floor(cy + 0.05)
    local floorNm = readBlock(fx, baseY - 1, fz)
    local feetNm  = readBlock(fx, baseY, fz)
    local headNm  = readBlock(fx, baseY + 1, fz)

    trace[#trace + 1] = {
      at = { x = cx, y = cy, z = cz },
      ahead = { x = fx, y = baseY, z = fz },
      floor = tostring(floorNm), feet = tostring(feetNm), head = tostring(headNm),
    }
    if #trace > 16 then table.remove(trace, 1) end

    -- 判定前方是否可走；不可走时，允许**清障**（挖掉挡路方块）后继续。
    -- ⚠ 底线：地面（floor）不可清 —— 那等于自己给自己挖个洞掉进虚空。
    --   真实事故：走去岛屿东侧时被橡树树叶挡住头部，walk_to 正确地停下并报告，
    --   但它不会清障，于是后续所有"需要走过去"的作业全部因为"够不着"而失败。
    local blockedBy = nil
    if not standable(floorNm) then blockedBy = "floor"
    elseif not passable(feetNm) then blockedBy = "feet"
    elseif not passable(headNm) then blockedBy = "head" end

    if blockedBy == "floor" then
      blocked = string.format("前方 (%d,%d,%d) 下方是 %s —— 没有落脚点，拒绝继续", fx, baseY - 1, fz, tostring(floorNm))
      break
    end

    if blockedBy then
      if clearMode and cleared < maxClear then
        local cx2, cy2, cz2 = fx, baseY, fz
        if blockedBy == "head" then cy2 = baseY + 1 end
        local okC = A.dig_at({ bot = bot, x = cx2, y = cy2, z = cz2, timeout = 5 })
        trace[#trace + 1] = { cleared = { x = cx2, y = cy2, z = cz2 }, kind = blockedBy, ok = okC }
        if #trace > 16 then table.remove(trace, 1) end
        if not okC then
          blocked = string.format("清障失败：前方 (%d,%d,%d) 的 %s 挖不掉", cx2, cy2, cz2, tostring(blockedBy == "head" and headNm or feetNm))
          break
        end
        cleared = cleared + 1
        sleep(0.25)
      else
        blocked = string.format("前方 (%d,%d,%d) 被 %s 挡住（未开启清障或已达上限 %d）",
          fx, baseY, fz, tostring(blockedBy == "head" and headNm or feetNm), maxClear)
        break
      end
    else
      -- 迈一小步：0.2 秒（约一格），然后立刻停手重新判断。
      -- 步子故意迈小：宁可多循环几次，也不要"一次冲过头冲进空里"。
      pcall(commands.execAsync, "player " .. bot .. " move forward")
      sleep(0.2)
      pcall(commands.execAsync, "player " .. bot .. " stop")
      sleep(0.1)
      steps = steps + 1
    end

    local nx, _, nz = botPos(bot)
    if nx and prevX then
      if math.abs(nx - prevX) < 0.15 and math.abs(nz - prevZ) < 0.15 then
        stillCount = stillCount + 1
        if stillCount >= 3 then
          blocked = "连续 3 步位置几乎没变：被卡住（可能前方不可通行）"
          break
        end
      else
        stillCount = 0
      end
    end
    prevX, prevZ = nx, nz
  end

  pcall(commands.execAsync, "player " .. bot .. " stop")
  local cx, cy, cz = botPos(bot)
  result.at = cx and { x = cx, y = cy, z = cz } or nil
  result.steps = steps
  result.reached = false
  result.blocked_reason = blocked or "超时"
  result.elapsed_s = tonumber(string.format("%.2f", os.clock() - t0))
  return true, result
end

-- --- 读方块状态（blockstate）与方块实体数据 --------------------------------- --
-- 为什么必须分开读两样：
--   /data get block 只能读**方块实体**（箱子、筛子这类有库存/进度的方块）；
--   而很多"交互到底有没有发生"的证据只存在于**方块状态**里——
--   拉杆有没有拉下、门开没开、筛子装没装筛网。
--   commands.getBlockInfo 会回传 state，正好补上这一块。
-- 用途：判断假人的右键是否真的产生了方块交互。放置方块能成功不代表方块交互能成功，
--       两者走的是不同代码路径（放置靠物品的 use，交互靠方块的 use）。
A.block_state = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a = args or {}
  local x, y, z = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (x and y and z) then return false, "需要 x/y/z" end
  local p = packReturns(pcall(commands.getBlockInfo, x, y, z))
  local name, state = nil, nil
  if p[1] and type(p[2]) == "table" then
    name  = p[2].name or p[2].block
    state = p[2].state
  end
  -- 方块实体数据：普通方块会失败，失败就留空（不是错误）
  local pD = packReturns(pcall(commands.exec, string.format("data get block %d %d %d", x, y, z)))
  local be = nil
  if pD[1] and pD[2] == true and type(pD[3]) == "table" then
    be = table.concat(pD[3], " ")
  end
  return true, { at = { x = x, y = y, z = z }, name = name, state = state, block_entity = be }
end

-- ═══ 准星感知（Jade 效果）—— "假人正对着的是哪块方块" ═══════════════════════
-- 玩家有 Jade：准心一指 ✓ 方块名/属性/需要什么工具就显示出来了 ✓
-- 假人**没有客户端** ✗ 它什么都看不见 ✗ —— 过去只能"人先报坐标、它再去读" ✗
-- 于是最基础的问题"我正前方是什么"反而答不上来 ✗（真实后果：挖错方块、
-- 以为面前是木板其实是泥土、少带一把工具就走过去 ✗✗）。
--
-- 这一节补的就是这件事 ✓：用假人自己的 Pos + Rotation ✓ 做**体素射线行进**（DDA ✓），
-- 从眼睛沿视线走到第一块非空气方块 ✓ 把 名字/状态/标签/所需工具/距离/入射面
-- 全部报出来 ✓ —— 等价于 Jade 显示的那一行 ✓ 而且是**服务端真值** ✓（不是渲染层猜的 ✗）。
--
-- 它同时是"肌肉记忆"的一半：反射层每拍顺手更新一次（见 jadeTick ✓），
-- 于是"盯着方块看"这件事**不需要 LLM 参与** ✓。

local JADE_AIR = {
  ["minecraft:air"] = true, ["minecraft:cave_air"] = true, ["minecraft:void_air"] = true,
  ["minecraft:light"] = true, ["minecraft:moving_piston"] = true,
}
local function jadeIsAir(nm)
  return (nm ~= nil) and (JADE_AIR[nm] == true)
end
local function jadeIsFluid(nm)
  if type(nm) ~= "string" then return false end
  local bare = nm:match(":(.+)$") or nm
  return (bare == "water") or (bare == "lava") or (bare:find("flow") ~= nil)
end

-- 方块缓存：一次射线要读十几格 ✓ 而反射层每拍都重看同一片区域 ✓。
-- 没有缓存 → "看一眼"就变成几十条服务端指令 ✗；有缓存 → 原地不动时几乎零成本 ✓✓
-- ⚠ 只给**射线**用（ttl 极短 ✓）✗ **绝不给"放置/挖掘的验收"用** ✗ ——
--   验收必须读到刚刚变化的世界 ✓ 缓存会让验收看到旧值 ✓ → 那正是最危险的假阳性 ✗
--   （所以 A.block_state / A.sift 一律走 readBlock 原路 ✓ 不共享这里的缓存 ✓）。
local jadeCache, jadeCacheN = {}, 0
local function jadeRead(x, y, z)
  local k = x .. "," .. y .. "," .. z
  local now = os.clock()
  local e = jadeCache[k]
  if e and (now - e.t) < 1.2 then return e.name, e.info, true end
  local nm, info = readBlock(x, y, z)
  if jadeCacheN > 800 then jadeCache, jadeCacheN = {}, 0 end
  jadeCache[k] = { name = nm, info = info, t = now }
  jadeCacheN = jadeCacheN + 1
  return nm, info, false
end

-- 读朝向：`data get entity <bot> Rotation` → [yaw, pitch]（**角度制**）
-- 与 botPos 同一条纪律：只从方括号里取数字 ✓ 不认任何文案 ✗（中文客户端全汉化）。
local function botLook(bot)
  local p = packReturns(pcall(commands.exec, "data get entity " .. bot .. " Rotation"))
  if not p[1] then return nil end
  local text
  if type(p[3]) == "table" then
    local parts = {}
    for _, l in ipairs(p[3]) do parts[#parts + 1] = tostring(l) end
    text = table.concat(parts, " ")
  else
    text = tostring(p[3])
  end
  local inside = text:match("%[([^%]]+)%]")
  if not inside then return nil end
  local n = {}
  for num in inside:gmatch("[-%d%.]+") do
    local v = tonumber(num)
    if v then n[#n + 1] = v end
  end
  if n[1] and n[2] then return n[1], n[2] end
  return nil
end

-- 视线方向（Minecraft 的角度约定）：
--   dx = -sin(yaw)·cos(pitch)   dy = -sin(pitch)   dz = cos(yaw)·cos(pitch)
--   yaw=0 → +Z ✓  yaw=90 → -X ✓  pitch=+90 → 朝下 ✓（pitch 正 = 向下 ✓ 容易记反 ✗）
local function jadeDir(yaw, pitch)
  local ry, rp = math.rad(yaw), math.rad(pitch)
  local cp = math.cos(rp)
  return -math.sin(ry) * cp, -math.sin(rp), math.cos(ry) * cp
end

-- 体素行进（Amanatides & Woo 的格子遍历 ✓）：只在**跨格子边界**时前进一步 ✓
--   5 格视距最多十几个格子 ✓；而"每 0.1 格采样一次"要 50 次 ✗（差 4 倍以上 ✓）。
-- 返回的每一项带 t（沿视线的距离 ✓）与 face（**入射面** ✓ = 玩家会点到的那一面 ✓）。
local function jadeWalk(ox, oy, oz, dx, dy, dz, maxd, maxCells)
  local cx, cy, cz = math.floor(ox), math.floor(oy), math.floor(oz)
  local sx = (dx > 0) and 1 or ((dx < 0) and -1 or 0)
  local sy = (dy > 0) and 1 or ((dy < 0) and -1 or 0)
  local sz = (dz > 0) and 1 or ((dz < 0) and -1 or 0)
  local adx, ady, adz = math.abs(dx), math.abs(dy), math.abs(dz)
  local okx, oky, okz = (adx > 1e-9), (ady > 1e-9), (adz > 1e-9)
  local tdx = okx and (1 / adx) or math.huge
  local tdy = oky and (1 / ady) or math.huge
  local tdz = okz and (1 / adz) or math.huge
  local tmx = okx and (((sx > 0) and (cx + 1 - ox) or (ox - cx)) / adx) or math.huge
  local tmy = oky and (((sy > 0) and (cy + 1 - oy) or (oy - cy)) / ady) or math.huge
  local tmz = okz and (((sz > 0) and (cz + 1 - oz) or (oz - cz)) / adz) or math.huge
  local out, t, guard = { { x = cx, y = cy, z = cz, t = 0, face = nil } }, 0, 0
  while t <= maxd and #out < (maxCells or 48) and guard < 256 do
    guard = guard + 1
    local axis
    if tmx <= tmy and tmx <= tmz then axis = "x"
    elseif tmy <= tmz then axis = "y"
    else axis = "z" end
    if axis == "x" then t = tmx; cx = cx + sx; tmx = tmx + tdx
    elseif axis == "y" then t = tmy; cy = cy + sy; tmy = tmy + tdy
    else t = tmz; cz = cz + sz; tmz = tmz + tdz end
    if t > maxd then break end
    local face
    if axis == "x" then face = (sx > 0) and "west" or "east"
    elseif axis == "y" then face = (sy > 0) and "down" or "up"
    else face = (sz > 0) and "north" or "south" end
    out[#out + 1] = { x = cx, y = cy, z = cz, t = t, face = face }
  end
  return out
end

-- 需要什么工具：**优先读方块自己的标签** ✓ 而不是维护一张巨型名字表 ✗。
--   CC 的 getBlockInfo / inspect 会带回 `tags`（`minecraft:mineable/pickaxe` 之类 ✓），
--   而那正是原版"该用什么工具、会不会掉东西"的判定依据 ✓。
-- ⚠ 对**海龟**尤其关键（已核对 CC:Tweaked 源码与文档）：
--   海龟挖方块用的是它**升级槽里的那把工具** ✗ **不是背包里的** ✗
--   （`turtle.dig` → `TurtleToolCommand` → 取 left/right 升级里的 tool ✓）
--   ⇒ 斧头升级挖得动木板/原木 ✓ 挖不动泥土/石头 ✗（回报 "No tool to dig with" ✓）
--   ⇒ "该用什么工具"必须能**在挖之前**看出来 ✓ —— 这就是这一节最实际的价值 ✓
local JADE_TOOL_TAGS = {
  ["minecraft:mineable/pickaxe"] = "pickaxe",
  ["minecraft:mineable/axe"]     = "axe",
  ["minecraft:mineable/shovel"]  = "shovel",
  ["minecraft:mineable/hoe"]     = "hoe",
  ["minecraft:mineable/shears"]  = "shears",
}
local JADE_TIER_TAGS = {
  ["minecraft:needs_stone_tool"]   = "needs_stone",
  ["minecraft:needs_iron_tool"]    = "needs_iron",
  ["minecraft:needs_diamond_tool"] = "needs_diamond",
}
local function jadeToolFromTags(info)
  local tags = info and info.tags
  if type(tags) ~= "table" then return nil, nil end
  local want, tier = nil, nil
  for k, v in pairs(tags) do
    if v then
      local key = tostring(k)
      if JADE_TOOL_TAGS[key] and not want then want = JADE_TOOL_TAGS[key] end
      if JADE_TIER_TAGS[key] then tier = JADE_TIER_TAGS[key] end
    end
  end
  return want, tier
end

-- 兜底：没有标签时（很多模组方块没有原版标签 ✗）按名字猜 ✓
-- ⚠ 明确标注为**猜**（tool_from="guess" ✓）✗ 不和读标签得到的结论混为一谈 ✗。
local JADE_GUESS = {
  { "shovel",  { "dirt", "grass_block", "sand", "gravel", "clay", "soul_soil", "mud",
                 "podzol", "mycelium", "farmland", "snow" } },
  { "axe",     { "_log", "_wood", "_planks", "leaves", "fence", "door", "chest",
                 "crafting_table", "barrel", "bookshelf", "ladder" } },
  { "pickaxe", { "stone", "cobble", "deepslate", "_ore", "obsidian", "brick",
                 "concrete", "terracotta", "glass", "_block" } },
}
local function jadeToolGuess(nm)
  if type(nm) ~= "string" then return nil end
  local bare = nm:match(":(.+)$") or nm
  for _, row in ipairs(JADE_GUESS) do
    for _, key in ipairs(row[2]) do
      if bare:find(key, 1, true) then return row[1] end
    end
  end
  return nil
end

-- 准星查询：**假人正对着什么**（= Jade 那一行 ✓）
-- 参数：bot ✓ / reach（视距，默认 5 ✓ = 玩家交互距离 ✓）/ eye（眼睛高度 1.62 ✓）
--       yaw,pitch（显式覆盖 ✓ 用于"先算后看"或测试 ✓）/ nbt（附带方块实体数据 ✓）
--       raw（附带原始方块信息表 ✓ 用来确认上游到底给了哪些字段 ✓）
A.crosshair = function(args)
  if not hasCommandsAPI() then return false, "crosshair 需要指令电脑（commands API）" end
  local a = args or {}
  local bot = a.bot or (cfg and cfg.bot) or "Bot"
  local reach = tonumber(a.reach) or 5.0
  if reach < 1 then reach = 1 end
  if reach > 8 then reach = 8 end
  local x, y, z = botPos(bot)
  if not x then return false, "读不到假人坐标：假人 " .. tostring(bot) .. " 在线吗？" end
  local yaw, pitch = botLook(bot)
  if tonumber(a.yaw) then yaw = tonumber(a.yaw) end
  if tonumber(a.pitch) then pitch = tonumber(a.pitch) end
  if not (yaw and pitch) then
    return false, "读不到假人朝向（data get entity " .. bot .. " Rotation）"
  end
  -- 眼睛高度：站立玩家 1.62 ✓（潜行 1.27 / 游泳 0.4 ✗）——需要时用 eye= 显式覆盖 ✓
  local eyeH = tonumber(a.eye) or 1.62
  local ox, oy, oz = x, y + eyeH, z
  local dx, dy, dz = jadeDir(yaw, pitch)
  local cells = jadeWalk(ox, oy, oz, dx, dy, dz, reach, tonumber(a.max_cells) or 48)

  local hit, seen, reads = nil, {}, 0
  for _, c in ipairs(cells) do
    local nm, info, cached = jadeRead(c.x, c.y, c.z)
    if not cached then reads = reads + 1 end
    seen[#seen + 1] = string.format("%d,%d,%d=%s", c.x, c.y, c.z, tostring(nm))
    if (not hit) and nm and (not jadeIsAir(nm)) then
      local tool, tier = jadeToolFromTags(info)
      local guess = tool and nil or jadeToolGuess(nm)
      hit = {
        x = c.x, y = c.y, z = c.z,
        name = nm,
        dist = tonumber(string.format("%.2f", c.t)),
        face = c.face,
        fluid = jadeIsFluid(nm),
        decor = isDecor(nm),
        tool = tool or guess,
        tool_from = tool and "tags" or (guess and "guess" or nil),
        tier = tier,
        state = info and info.state or nil,
      }
      if a.raw and info then
        local okS, raw = pcall(textutils.serializeJSON, info)
        hit.raw = okS and raw or "(无法序列化)"
      end
      if a.nbt then
        local pD = packReturns(pcall(commands.exec,
          string.format("data get block %d %d %d", c.x, c.y, c.z)))
        if pD[1] and pD[2] == true and type(pD[3]) == "table" then
          local b = table.concat(pD[3], " ")
          hit.block_entity = (#b > 900) and (b:sub(1, 900) .. "…") or b
        end
      end
    end
  end

  local desc
  if hit then
    desc = string.format("%s @ (%d,%d,%d) 距离 %.2f 面 %s",
      hit.name, hit.x, hit.y, hit.z, hit.dist, tostring(hit.face))
  else
    desc = string.format("空（视线 %.1f 格内没有方块）", reach)
  end
  return true, {
    bot = bot,
    eye = { x = tonumber(string.format("%.3f", ox)),
            y = tonumber(string.format("%.3f", oy)),
            z = tonumber(string.format("%.3f", oz)) },
    rotation = { yaw = yaw, pitch = pitch },
    reach = reach,
    hit = hit,
    looking_at = desc,
    cells_read = reads,
    ray = seen,
  }
end

-- ── 世界内的可见 HUD（"真·Jade"）─────────────────────────────────────────
-- 假人自己没有屏幕 ✗ 但**世界里可以有** ✓：一个原版 text_display 实体 ✓
-- 反射层每拍把它挪到"准星命中的方块上方" ✓ 并写上同一行信息 ✓
-- 效果：**玩家进游戏就能直接看到假人正对着什么** ✓（调试与交接时特别值钱 ✓）
-- ⚠ 它是实体 ⇒ 会进入 `@e` 选择器 ✗ → 必须打 tag ✓ 并在所有"最近实体"查询里排除 ✗
--   否则反射层的"最近的实体"永远是它 ✓ 敌人永远发现不了 ✓（等于把保命逻辑弄瞎 ✓）。
local JADE_TAG = "dsh_jade"
local jadeState = { hud = false, lastKey = nil, lastAt = 0, updated = 0 }
if cfg and cfg.jade_hud == true then jadeState.hud = true end

local function jadeExec(text)
  local p = packReturns(pcall(commands.exec, text))
  if not p[1] then return false, tostring(p[2]) end
  local out = ""
  if type(p[3]) == "table" then out = table.concat(p[3], " ")
  elseif p[3] ~= nil then out = tostring(p[3]) end
  return (p[2] == true), out
end

local function jadeHudAlive()
  local ok, out = jadeExec("data get entity @e[tag=" .. JADE_TAG .. ",limit=1] Pos")
  return ok and (out:find("%[") ~= nil)
end

local function jadeHudEnsure(bx, by, bz)
  if jadeHudAlive() then return true end
  -- 悬浮文字（原版实体 ✓ 不需要资源包 ✓ 中文由渲染层处理 ✓ 不经过 CC 终端的字体 ✗）
  local json = '{"text":"[Jade] ...","color":"aqua"}'
  local cmd = string.format(
    "summon minecraft:text_display %.2f %.2f %.2f {Tags:[\"%s\"],text:'%s'," ..
    "billboard:\"center\",see_through:1b,background:1073741824,alignment:\"center\"," ..
    "brightness:{sky:15,block:15},view_range:1.0f,line_width:400}",
    bx, by + 2.0, bz, JADE_TAG, json)
  return jadeExec(cmd)
end

-- 组装显示文本：**自己拼组件 JSON** ✓ 不用 `textutils.serializeJSON` ✗
-- ⚠ 真实事故（就在写这一节的当天踩到 ✗，靠 job.log 里的 `jade.hud.err` 才看见 ✓）：
--   `textutils.serializeJSON` 会把**非 ASCII 字节逐个转义**成 `\u00XX` ✗ ——
--   因为 CC 的 Lua 字符串是**字节串** ✓ 它根本不知道 UTF-8 的存在 ✗：
--   中文"距离"（E8 B7 9D）变成 `\u00E8\u00B7\u009D` ✔ JSON 合法 ✗ 但语义已经烂了 ✗
--   → 交给服务端解析 NBT 时整条 `data merge` **失败** ✗ → HUD 永远停在占位符 ✗
--   （世界里的表现是"什么都没发生" ✓ 而真实原因在磁盘日志里 ✓ 这就是"把错误写盘"的价值 ✓）。
-- 修法：只转义**必须转义**的字符（\ " 换行 ✓）其余字节原样输出 ✓ —— 中文直接以 UTF-8 过去 ✓
-- 实测（tools/raw.py 回读 NBT ✓）：`{"text":"中文测试"}` 能**原样**写入并原样读回 ✓✓
local function jadeJsonStr(s)
  s = tostring(s):gsub("\\", "\\\\")
  s = s:gsub('"', '\\"')
  s = s:gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
  return '"' .. s .. '"'
end

local function jadeHudText(hit)
  local parts = {}
  local function seg(text, color)
    parts[#parts + 1] = '{"text":' .. jadeJsonStr(text) ..
      (color and (',"color":"' .. color .. '"') or "") .. '}'
  end
  if hit then
    seg(hit.name, hit.fluid and "aqua" or "white")
    seg("\n")
    seg(string.format("(%d, %d, %d)  距离 %.2f  面 %s",
      hit.x, hit.y, hit.z, hit.dist, tostring(hit.face)), "gray")
    if hit.tool or hit.tier then
      seg("\n")
      seg("挖它要用: " .. tostring(hit.tool or "?") ..
        (hit.tier and ("  " .. tostring(hit.tier)) or ""), "yellow")
    end
  else
    seg("[Jade] 准星: 空（看到天了）", "dark_gray")
  end
  return '{"text":"","extra":[' .. table.concat(parts, ",") .. ']}'
end

-- ⚠ **两层转义必须分清楚**（真实事故 ✗，HUD 文本第二次没更新就是它 ✗）：
--   第 1 层 JSON：换行要写成 `\n`（反斜杠 + n 两个字符 ✓ 这是 JSON 自己的语法 ✓）
--   第 2 层 SNBT：**它自己也会解释转义** ✗ —— `'...\n...'` 里的 `\n` 会变成**真换行** ✗
--                 → JSON 里出现一个裸换行 ✗ → JSON 解析失败 ✗ → `data merge` 整条失败 ✗
--   ⇒ 交给 SNBT 之前，把 JSON 里的每个反斜杠**再补一层** ✓（`\n` → `\\n` ✓）
--   ⇒ 单引号是我们用来包 JSON 的定界符 ✗ 也要转义 ✓（顺序：先补反斜杠 ✓ 再加引号转义 ✓）
local function jadeForSnbt(json)
  json = json:gsub("\\", "\\\\")
  json = json:gsub("'", "\\'")
  return json
end

local function jadeHudShow(hit)
  local json = jadeHudText(hit)
  local ok, out = jadeExec("data merge entity @e[tag=" .. JADE_TAG ..
    ",limit=1] {text:'" .. jadeForSnbt(json) .. "'}")
  return ok, out, json
end

-- 反射层每拍调用：**只做感知** ✓ 不做决策 ✗（决策在 Agent 那边 ✓）
-- 「没变就不动世界」——HUD 只在**命中目标变化**时更新 ✓ 省指令 ✓ 也不抖 ✗
local function jadeTick(now)
  if not jadeState.hud then return end
  local period = tonumber(cfg and cfg.jade_ms) or 750
  if (now - (jadeState.lastAt or 0)) < period then return end
  jadeState.lastAt = now
  local ok, res = A.crosshair({ bot = (cfg and cfg.bot) or "Bot",
    reach = tonumber(cfg and cfg.jade_reach) or 5 })
  if not ok or type(res) ~= "table" then return end
  local h = res.hit
  local key = h and string.format("%s@%d,%d,%d", h.name, h.x, h.y, h.z) or "air"
  if key == jadeState.lastKey then return end
  jadeState.lastKey = key
  jadeHudEnsure(res.eye.x, res.eye.y, res.eye.z)
  local tx = h and (h.x + 0.5) or res.eye.x
  local ty = h and (h.y + 1.25) or (res.eye.y + 0.5)
  local tz = h and (h.z + 0.5) or res.eye.z
  jadeExec(string.format("tp @e[tag=%s,limit=1] %.2f %.2f %.2f", JADE_TAG, tx, ty, tz))
  local ok2, err2 = jadeHudShow(h)
  jadeState.updated = (jadeState.updated or 0) + 1
  if h then
    jobNote("jade.look", { at = { h.x, h.y, h.z }, name = h.name, dist = h.dist,
      tool = h.tool, tool_from = h.tool_from, tier = h.tier })
  else
    jobNote("jade.look", { name = "air" })
  end
  if not ok2 then jobNote("jade.hud.err", { err = tostring(err2) }) end
end

-- 开关 + 读一次：`jade { hud = true }` 打开世界内 HUD ✓；不带 hud 就是纯读 ✓
A.jade = function(args)
  local a = args or {}
  if a.hud ~= nil then
    local want = (a.hud == true) or (a.hud == "on") or (a.hud == 1)
    if DRY_RUN then
      return true, { dry_run = true, would_set_hud = want, note = "演练模式不改世界" }
    end
    jadeState.hud = want
    jadeState.lastKey = nil
    if want then
      local x, y, z = botPos(a.bot or (cfg and cfg.bot) or "Bot")
      if x then jadeHudEnsure(x, y, z) end
    else
      jadeExec("kill @e[tag=" .. JADE_TAG .. "]")
    end
    jobNote("jade.hud", { hud = want })
  end
  local ok, res = A.crosshair({ bot = a.bot, reach = a.reach, nbt = a.nbt, raw = a.raw })
  if not ok then return false, res end
  res.hud = jadeState.hud
  res.hud_updates = jadeState.updated
  return true, res
end

-- ═══ 周边方块读取（"增强版 Jade"：不是只看准星那一格，而是把四周看清楚）═══
-- 为什么必须有它（用户 2026-09-18 晚明确要求 ✓）：
--   假人过去只会两种"看"：
--     ① `survey` —— 只给**计数** ✓ 不给具体位置 ✗（"附近有 3 个箱子" ✗ 在哪？✗）
--     ② `crosshair` —— 只看**准星那一格** ✗
--   ⇒ "我旁边有没有什么不寻常的东西"这个问题**答不上来** ✗ —— 而它恰恰是最常用的 ✓
--   真实事故：玩家明明在假人旁边放了一个工作台 ✓ 我们却绕了好几轮、还一度断言"世界上没有" ✗
--   （缺的不是工具也不是流程 ✓ 缺的是**就近的、带坐标的、一眼看懂**的方块读取 ✓）
--
-- 参数：
--   bot     假人名（默认 Bot ✓）
--   r       水平半径（默认 3 ⇒ 7×7 ✓；4 ⇒ 9×9 更慢 ✓）
--   dy0/dy1 垂直范围（默认 -2..+1 ✓ —— 脚下两层、头上两层，正好覆盖"能踩/能撞/能放" ✓）
--   dy      只读某一层（给了就忽略 dy0/dy1 ✓）
--   plain   "无聊方块"清单（逗号分隔 ✓）—— 只有**不在这里面**的才进 notable ✓
--   limit   notable 最多列几条（默认 40 ✓）
--
-- ⚠ 一律走 `readBlock`（**不共享 Jade 的缓存** ✗）—— 这种读取常常是在问"我刚放的东西在不在" ✓
--   缓存会让它看到旧值 ✓（那正是最危险的假阳性 ✓ 见 Jade 那一节 ✓）
A.blocks_around = function(args)
  if not hasCommandsAPI() then return false, "blocks_around 需要指令电脑" end
  local a = args or {}
  local bot = a.bot or (cfg and cfg.bot) or "Bot"
  local bx, by, bz = botPos(bot)
  if not bx then return false, "读不到假人坐标：假人 " .. tostring(bot) .. " 在线吗？" end
  local r = math.floor(tonumber(a.r) or 3)
  if r < 1 then r = 1 end
  if r > 6 then r = 6 end
  local y0, y1
  if tonumber(a.dy) then
    y0 = math.floor(tonumber(a.dy)); y1 = y0
  else
    y0 = math.floor(tonumber(a.dy0) or -2)
    y1 = math.floor(tonumber(a.dy1) or 1)
  end
  if y1 - y0 > 6 then y1 = y0 + 6 end
  local limit = math.floor(tonumber(a.limit) or 40)

  -- "无聊方块" = 自然地形 + 空气 + 植物 ✓
  -- 为什么必须有这张表 ✗：7×7×4 的区域里 90% 是空气和泥土 ✓ 全列出来等于没看 ✓
  --   （真实教训：把"计数"当"感知"用 ✗ 结果什么都看不见 ✓）
  local BORING = {
    ["minecraft:air"] = true, ["minecraft:cave_air"] = true, ["minecraft:void_air"] = true,
    ["minecraft:dirt"] = true, ["minecraft:grass_block"] = true, ["minecraft:dirt_path"] = true,
    ["minecraft:stone"] = true, ["minecraft:cobblestone"] = true, ["minecraft:deepslate"] = true,
    ["minecraft:sand"] = true, ["minecraft:sandstone"] = true, ["minecraft:gravel"] = true,
    ["minecraft:clay"] = true, ["minecraft:water"] = true, ["minecraft:lava"] = true,
    ["minecraft:bedrock"] = true, ["minecraft:snow_block"] = true, ["minecraft:ice"] = true,
    ["minecraft:oak_leaves"] = true, ["minecraft:oak_log"] = true, ["minecraft:grass"] = true,
    ["minecraft:short_grass"] = true, ["minecraft:tall_grass"] = true, ["minecraft:fern"] = true,
    ["minecraft:moss_block"] = true, ["minecraft:vine"] = true,
  }
  if type(a.plain) == "string" and a.plain ~= "" then
    BORING = {}
    for nm in a.plain:gmatch("[^,]+") do
      nm = nm:gsub("^%s+", ""):gsub("%s+$", "")
      if nm ~= "" then
        if not nm:find(":", 1, true) then nm = "minecraft:" .. nm end
        BORING[nm] = true
      end
    end
  end

  local codes, legend = {}, {}
  local function codeOf(nm)
    if not codes[nm] then
      local c = string.char(65 + #legend)     -- A, B, C, …
      codes[nm] = c
      legend[#legend + 1] = c .. "=" .. nm
    end
    return codes[nm]
  end

  local counts, notable, cells, layers = {}, {}, 0, {}
  local fbx, fbz = math.floor(bx), math.floor(bz)
  for y = by + y1, by + y0, -1 do          -- 从上往下打印（跟玩家看世界的方向一致 ✓）
    local rows = {}
    for dz = -r, r do
      local row = ""
      for dx = -r, r do
        local wx, wz = fbx + dx, fbz + dz
        local nm = readBlock(wx, y, wz) or "?"
        cells = cells + 1
        counts[nm] = (counts[nm] or 0) + 1
        row = row .. codeOf(nm)
        if not BORING[nm] and #notable < limit then
          notable[#notable + 1] = {
            name = nm, x = wx, y = y, z = wz,
            rel = { dx = dx, dy = y - math.floor(by), dz = dz },
            dist = tonumber(string.format("%.1f",
              math.sqrt(dx * dx + (y - by) * (y - by) + dz * dz))),
          }
        end
      end
      rows[#rows + 1] = row
    end
    layers[#layers + 1] = { y = y, rows = rows }
  end

  -- 文字版（给人一眼看懂 ✓）：把方向也标出来 ✓ 免得搞反 ✗
  local lines = {}
  lines[#lines + 1] = string.format("以 %s 为中心 半径 %d（x %d..%d, y %d..%d, z %d..%d）",
    bot, r, fbx - r, fbx + r, by + y0, by + y1, fbz - r, fbz + r)
  lines[#lines + 1] = "列=西→东(-x→+x) ✓ 行=北→南(-z→+z) ✓"
  for _, L in ipairs(layers) do
    lines[#lines + 1] = string.format("y=%d%s", L.y,
      (L.y == math.floor(by)) and "  ← 脚所在层" or "")
    for i, row in ipairs(L.rows) do
      lines[#lines + 1] = "   " .. row .. ((i - 1 == r) and "   ← 假人所在行" or "")
    end
  end
  lines[#lines + 1] = "图例: " .. table.concat(legend, "  ")

  return true, {
    bot = bot,
    center = { x = fbx, y = math.floor(by), z = fbz },
    radius = r, cells_read = cells,
    notable = notable, notable_count = #notable,
    counts = counts, layers = layers, legend = legend,
    ascii = table.concat(lines, "\n"),
  }
end

-- --- 把物品放进假人的**指定快捷栏槽位** ------------------------------------- --
-- 为什么必须能指定槽位（实测撞到的限制）：
--   /give 会先填快捷栏，快捷栏满了就丢进背包；而 Carpet 的 hotbar 子命令**只能选快捷栏**
--   （0-8），假人没有任何办法把背包里的东西拿到手上（它没有客户端、打不开背包界面）。
--   于是"给了筛子和沙砾"却报"快捷栏里没有该物品"——东西确实给了，只是够不着。
-- 用原版 /item replace entity <bot> hotbar.<n> with <item> <count> 精确落到指定格，
-- 既不覆盖别的东西，也不需要整理背包。
A.give_slot = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a = args or {}
  local bot = a.bot or "Bot"
  local slot = tonumber(a.slot)
  if not (slot and slot >= 0 and slot <= 8) then return false, "slot 需为 0..8（快捷栏）" end
  local item = a.item
  if type(item) ~= "string" or item == "" then return false, "需要 item" end
  if not item:find(":", 1, true) then item = "minecraft:" .. item end
  local count = math.floor(tonumber(a.count) or 1)
  local cmd = string.format("item replace entity %s hotbar.%d with %s %d", bot, slot, item, count)
  local p = packReturns(pcall(commands.exec, cmd))
  if not p[1] then return false, "指令异常：" .. tostring(p[2]) end
  sleep(0.25)
  -- 自检：读回那个槽位，确认真的放进去了（而不是"指令成功、东西没到"）
  local ok, inv = A.bot_inv({ bot = bot })
  local landed = nil
  if ok and type(inv) == "table" then
    for _, it in ipairs(inv.items or {}) do
      if it.slot == slot then landed = it.id end
    end
  end
  return true, {
    bot = bot, slot = slot, item = item, count = count,
    command_success = p[2], landed = landed, ok = (landed ~= nil),
  }
end

-- --- 给筛子装筛网 ------------------------------------------------------------
-- 这是查了十几轮才查清的一件事，必须固化成动作，而不是每次手工拼指令：
--   * 交互在基类 EBlock.use（SieveBlock 自己没有 use）；
--   * 装满靠右击筛子，且**必须瞄准碗内**（筛子是矮碗形，瞄方块顶面会完全打空）；
--   * 每个筛子各自需要一个筛网（任务书原文），5×5 同步点击时 25 个都要有；
--   * 装好后方块实体的 NBT 会出现 mesh 字段——**用它作为判定**，不猜。
A.install_mesh = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local x, y, z = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (x and y and z) then return false, "需要 x/y/z（筛子坐标）" end
  local item = a.item or "mesh"

  local function meshInSieve()
    local p = packReturns(pcall(commands.exec, string.format("data get block %d %d %d", x, y, z)))
    if not p[1] or p[2] ~= true or type(p[3]) ~= "table" then return nil end
    local s = table.concat(p[3], " ")
    return s:find("mesh", 1, true) ~= nil, s
  end

  local has, before = meshInSieve()
  if has then
    return true, { bot = bot, at = { x = x, y = y, z = z }, already = true, nbt = before }
  end

  local okH, hold = A.hold_item({ bot = bot, item = item })
  if not okH then return false, "拿不到筛网（" .. tostring(item) .. "）：" .. tostring(hold) end
  -- 瞄碗内多个高度：矮碗形方块的可点击面不在方块顶上（真实事故）
  for _, aimY in ipairs({ 0.2, 0.35, 0.15, 0.5 }) do
    pcall(commands.exec,
      string.format("player %s look at %d %.2f %d", bot, x + 0.5, y + aimY, z + 0.5))
    sleep(0.25)
    A.use_once({ bot = bot })
    sleep(0.4)
    local nowHas, nbt = meshInSieve()
    if nowHas then
      return true, {
        bot = bot, at = { x = x, y = y, z = z }, item = item,
        installed = true, aim = aimY, nbt = nbt,
      }
    end
  end
  return false, "四个瞄准高度都没能装入筛网（筛子坐标或方块类型可能不对）"
end

-- --- 放置方块 --------------------------------------------------------------- --
-- 把手上的物品放到地面方块 (x,y,z) 的**上面一格**，并读回验证。
-- 为什么不用 /setblock：那是作弊，不算"机器人自己建起来的"。这里走真玩家的右键路径，
-- 和真人放置完全同一条代码链（代价是可能被视线角度影响，所以必须读回验证）。
A.place_at = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local gx, gy, gz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (gx and gy and gz) then return false, "需要 x/y/z（地面方块坐标）" end
  if a.item then
    local okH, hold = A.hold_item({ bot = bot, item = a.item })
    if not okH then return false, "拿不到 " .. tostring(a.item) .. "：" .. tostring(hold) end
  end
  local ty = gy + 1
  local existing = readBlock(gx, ty, gz)
  if not passable(existing) then
    return false, string.format("目标格 (%d,%d,%d) 已被 %s 占用", gx, ty, gz, tostring(existing))
  end
  local pL = packReturns(pcall(commands.exec,
    string.format("player %s look at %d %.1f %d", bot, gx, gy + 0.5, gz)))
  if not pL[1] or pL[2] == false then return false, "look 失败：" .. tostring(pL[2]) end
  sleep(0.3)
  local okU = A.use_once({ bot = bot })
  sleep(0.6)
  local now = readBlock(gx, ty, gz)
  return true, {
    bot = bot, ground = { x = gx, y = gy, z = gz }, target = { x = gx, y = ty, z = gz },
    item = a.item, use_ok = (okU and true or false), now_block = now,
    placed = (type(now) == "string" and now ~= "minecraft:air"),
  }
end

-- --- 筛矿作业（阶段①的核心）------------------------------------------------ --
-- 一条指令筛完一批：手持可筛方块 → 对着筛子连续右键 → 用**背包前后差异**证明收获。
-- 为什么必须用背包差异证明：右键的返回值只说明"指令执行成功"，不代表筛出了东西
-- （真实教训：hotbar 差一位那次，指令全部成功但世界里什么都没发生）。
-- 产出必须从背包里读出来才算数。
A.sift = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local sx, sy, sz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (sx and sy and sz) then return false, "需要 x/y/z（筛子坐标）" end
  local want = math.floor(tonumber(a.count) or 16)
  local item = a.item or "gravel"
  local t0   = os.clock()

  local function invCounts()
    local ok, inv = A.bot_inv({ bot = bot })
    local m = {}
    if ok and type(inv) == "table" then
      for _, it in ipairs(inv.items or {}) do
        m[it.id] = (m[it.id] or 0) + (it.count or 1)
      end
    end
    return m, inv
  end

  -- 参数里给的是"名字子串"（gravel），而背包表的键是完整 id（minecraft:gravel）。
  -- 实测踩过：直接 m["gravel"] 永远是 nil，把"手上还有 64 个"误判成"原料用尽"，
  -- 结果作业 8 次点击就自我终止、还给出一个完全错误的理由。
  local function resolveId(map, want)
    if map[want] then return want end
    for id in pairs(map) do
      if id:find(want, 1, true) then return id end
    end
    return want
  end

  local okH, hold = A.hold_item({ bot = bot, item = item })
  if not okH then return false, "拿不到 " .. item .. "：" .. tostring(hold) end
  local before, inv0 = invCounts()
  local fullId = resolveId(before, item)

  -- ⚠ 动手前先做两项"能不能"检查 ✗（真实事故，代价是被清理两次的砂砾堆 ✓）
  --   事故：假人离筛子 5~7 格时 ✓ 每次都"右键成功"✓ 但射线打在**地面**上 ✗
  --        → 把手里那一整组砂砾**放到地上** ✗ 甚至堆成 2 格高把自己埋进去 ✗
  --   旧逻辑只在"原料有没有被消耗"上判成败 ✗ —— 可那时方块**早就放下去了** ✗ 来不及了 ✓
  --   所以：① 距离超过 reach 直接拒绝 ✓ ② 目标格不是筛子直接拒绝 ✓
  --   两条都宁可失败也不要在玩家的世界里乱放方块 ✓
  do
    local p1, p2, p3 = botPos(bot)
    local bx, by, bz
    if type(p1) == "number" then
      bx, by, bz = p1, p2, p3
    elseif type(p1) == "table" then
      bx, by, bz = (p1[1] or p1.x), (p1[2] or p1.y), (p1[3] or p1.z)
    end
    if type(bx) ~= "number" then
      return false, "取不到假人坐标，为安全起见拒绝执行（离得远时右键会把物品放到地上 ✗）",
        { sieve = { x = sx, y = sy, z = sz } }
    end
    local dx, dy, dz = bx - (sx + 0.5), by - (sy + 0.5), bz - (sz + 0.5)
    local dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    local reach = tonumber(a and a.reach) or 4.0
    if dist > reach then
      return false, string.format(
        "拒绝执行：假人离筛子 %.2f 格（上限 %.2f）✗ 离得远时右键会打在地面上、" ..
        "把手里物品放到地上。请先用 walk_to 走到筛子旁边再 sift。",
        dist, reach),
        { bot = { x = bx, y = by, z = bz }, sieve = { x = sx, y = sy, z = sz },
          dist = dist, reach = reach }
    end
    local target = readBlock(sx, sy, sz)
    if not target or not tostring(target):find("sieve") then
      return false, "拒绝执行：(" .. sx .. "," .. sy .. "," .. sz .. ") 不是筛子，而是 "
        .. tostring(target) .. " ✗（坐标错了？还是筛子被拆了？）",
        { sieve = { x = sx, y = sy, z = sz }, found = tostring(target) }
    end
  end

  -- 瞄准：筛子是**矮碗形**方块（SieveBlock 有自定义 SHAPE），顶面远低于 y+1。
  -- 真实事故：一直瞄 sy+0.99（方块顶部）→ 射线从筛子上方掠过、完全打不中 →
  -- 右键"毫无反应"，而指令本身每次都返回成功。这类失败最难查，代价是十几轮往返。
  -- 结论：不要假定方块的顶面在哪。先按多个高度试，并用"原料是否被消耗"作为判定，
  -- 一旦某个高度生效就沿用它把整批做完；全都不生效才报失败，并列出试过哪些高度。
  local aims = { tonumber(a.aim) or 0.2, 0.35, 0.5, 0.8 }
  local clicks, stopped, workingAim = 0, nil, nil
  local seconds = tonumber(a.seconds)
  local function aimAt(aimY)
    return pcall(commands.exec,
      string.format("player %s look at %d %.2f %d", bot, sx + 0.5, sy + aimY, sz + 0.5))
  end
  local function left() return (invCounts())[fullId] or 0 end

  if seconds then
    -- 连续模式（默认推荐）：让 Carpet 自己按 `interval 1` 持续右键，
    -- 而不是"每点一次都要走一遍 Lua→服务器往返"。
    -- 实测差一个数量级（约 3.5 次/秒 → 约 20 次/秒），这是 5×5 同步点击方案能成立的前提。
    for _, aimY in ipairs(aims) do
      if left() <= 0 then stopped = "原料用尽"; break end
      aimAt(aimY)
      sleep(0.3)
      local l0 = left()
      pcall(commands.execAsync, string.format("player %s use interval 1", bot))
      local deadline = os.clock() + seconds
      while os.clock() < deadline do
        sleep(1)
        if left() <= 0 then stopped = "原料用尽"; break end
      end
      pcall(commands.execAsync, "player " .. bot .. " stop")
      sleep(0.3)
      if left() < l0 then
        workingAim = aimY
        break
      end
    end
  else
    for _, aimY in ipairs(aims) do
      if clicks >= want then break end
      if aimAt(aimY) then
        sleep(0.25)
        local leftBefore = left()
        if leftBefore <= 0 then stopped = "原料用尽"; break end
        for _ = 1, 8 do
          if clicks >= want then break end
          A.use_once({ bot = bot })
          sleep(0.28)
          clicks = clicks + 1
        end
        if left() < leftBefore then
          workingAim = aimY
          while clicks < want do
            A.use_once({ bot = bot })
            sleep(0.28)
            clicks = clicks + 1
            if clicks % 16 == 0 and left() <= 0 then stopped = "原料用尽"; break end
          end
          break
        end
      end
    end
  end
  if not workingAim and not stopped then
    stopped = "所有瞄准高度都无效（试过 " .. table.concat(aims, "/") ..
              "）：右键没有消耗任何原料，请检查筛子是否已装入筛网"
  end
  sleep(0.4)

  local after = invCounts()
  local gained, spent = {}, {}
  for id, n in pairs(after) do
    local d = n - (before[id] or 0)
    if d > 0 then gained[id] = d end
  end
  for id, n in pairs(before) do
    local d = n - (after[id] or 0)
    if d > 0 then spent[id] = d end
  end
  return true, {
    bot = bot, sieve = { x = sx, y = sy, z = sz }, item = item,
    requested = want, clicks = clicks, stopped = stopped,
    gained = gained, spent = spent,
    held_at_start = inv0 and inv0.held_item or nil,
    elapsed_s = tonumber(string.format("%.2f", os.clock() - t0)),
  }
end

-- --- 挖掉一个方块 ------------------------------------------------------------
-- 走真玩家的左键路径（attack continuous）+ 轮询确认方块真的变成空气。
-- 不像"挖一下就算成功"：必须读回空气才作数（本项目反复出现的教训）。
A.dig_at = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local x, y, z = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (x and y and z) then return false, "需要 x/y/z" end
  local timeout = tonumber(a.timeout) or 8
  local was = readBlock(x, y, z)
  if blockIsAir(x, y, z) then
    return true, { at = { x = x, y = y, z = z }, already_air = true, was = was }
  end
  -- 有铲子就换铲子（挖沙砾/泥土快得多），没有就徒手
  pcall(A.hold_item, { bot = bot, item = a.tool or "_shovel" })
  for _, aimY in ipairs({ 0.5, 0.2, 0.8 }) do
    pcall(commands.exec,
      string.format("player %s look at %d %.2f %d", bot, x + 0.5, y + aimY, z + 0.5))
    sleep(0.25)
    pcall(commands.execAsync, "player " .. bot .. " attack continuous")
    local deadline = os.clock() + timeout
    while os.clock() < deadline do
      sleep(0.2)
      if blockIsAir(x, y, z) then
        pcall(commands.execAsync, "player " .. bot .. " stop")
        return true, { at = { x = x, y = y, z = z }, dug = true, was = was, aim = aimY }
      end
    end
    pcall(commands.execAsync, "player " .. bot .. " stop")
    sleep(0.2)
  end
  return false, string.format("没能挖掉 (%d,%d,%d)：现在仍是 %s（可能够不着或瞄不中）",
    x, y, z, tostring(readBlock(x, y, z)))
end

-- --- 贴着已有方块放一块 ------------------------------------------------------
-- 与 place_at 的区别：place_at 是"放在某方块顶上"；这里只要求"贴着一个已有方块放下"，
-- 具体落到哪个相邻格由射线决定。所以**放完扫描六个邻格找出新方块**，
-- 而不是预测它会落在哪——预测面朝方向很容易错，而且错了还不报错。
A.place_adjacent = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a = args or {}
  local bot = a.bot or "Bot"
  local rx, ry, rz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (rx and ry and rz) then return false, "需要 x/y/z（参照方块）" end
  if a.item then
    local okH, hold = A.hold_item({ bot = bot, item = a.item })
    if not okH then return false, "拿不到 " .. tostring(a.item) .. "：" .. tostring(hold) end
  end
  local faces = {
    { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 },
    { 0, -1, 0 }, { 0, 0, 1 }, { 0, 0, -1 },
  }
  local function snapshot()
    local s = {}
    for _, f in ipairs(faces) do
      local kx, ky, kz = rx + f[1], ry + f[2], rz + f[3]
      s[kx .. "," .. ky .. "," .. kz] = tostring(readBlock(kx, ky, kz))
    end
    return s
  end
  local b0 = snapshot()

  -- ⚠ 关键：先走近再放。
  --   真实事故：机器人站在距边缘 3 格外就想"往外接一块"，结果方块落到了**上一层**
  --   （(4127,71,10) 而不是 (4128,70,10)）——因为射线太陡，先穿过顶面而不是侧面 ✗。
  --   几何是硬的：眼高 1.62、目标低 2 格时，要打到侧面必须站到距该面 1.3 格以内。
  --   所以这里先走过去（walk_to 本身带防坠守卫），再瞄再放。
  if a.walk_closer ~= false then
    local bx, by, bz = botPos(bot)
    if bx then
      local dxz = math.sqrt((rx + 0.5 - bx) ^ 2 + (rz + 0.5 - bz) ^ 2)
      if dxz > 1.3 then
        -- clear=false：内部走位**不挖方块**。真实事故：place_adjacent → walk_to → dig_at
        -- 层层嵌套，每层都有 5~20 秒超时，叠加起来能把一次放置拖成好几分钟。
        pcall(A.walk_to, { bot = bot, x = rx, y = ry + 1, z = rz, range = 1.2, timeout = 12, clear = false })
      end
    end
  end

  -- ⚠ 瞄"朝向机器人的那个**侧面**"，而不是方块中心。
  --   真实事故（玩家直接从游戏里看出来的）：瞄中心时射线常常先打到**顶面** →
  --   方块被叠到上一层 → 世界里出现**悬空方块** ✗，而作业报告里它只是"落点不符" ✓，
  --   两者同时为真 —— 只按"落点对不对"记账会完全掩盖"世界里多了不该有的方块"。
  --   做法：算出机器人相对参照方块的方位，把瞄点贴到那个侧面上（x 或 z ±0.48）。
  local aimX, aimZ = rx + 0.5, rz + 0.5
  local bx0, by0, bz0 = botPos(bot)
  if bx0 then
    local ddx, ddz = bx0 - (rx + 0.5), bz0 - (rz + 0.5)
    if math.abs(ddx) >= math.abs(ddz) then
      aimX = (ddx > 0) and (rx + 0.04) or (rx + 0.96)
    else
      aimZ = (ddz > 0) and (rz + 0.04) or (rz + 0.96)
    end
  end
  pcall(commands.exec,
    string.format("player %s look at %.2f %.2f %.2f", bot, aimX, ry + 0.55, aimZ))
  sleep(0.3)
  A.use_once({ bot = bot })
  sleep(0.6)
  local b1 = snapshot()
  for k, v in pairs(b1) do
    if b0[k] ~= v and type(v) == "string" and not v:find("air", 1, true) then
      local cx, cy, cz = k:match("(-?%d+),(-?%d+),(-?%d+)")
      return true, {
        bot = bot, placed = v,
        at = { x = tonumber(cx), y = tonumber(cy), z = tonumber(cz) },
        ref = { x = rx, y = ry, z = rz },
      }
    end
  end
  return false, "参照方块四周没有出现新方块（可能没瞄准，或手上不是可放置的方块）"
end

-- --- 搭一块平台 --------------------------------------------------------------
-- 以给定位置为中心铺 size×size（奇数，机器人站正中）。
-- 刻意只铺"够得着"的范围（默认 3×3，最大 5×5）：放置距离只有 4.5 格，
-- 铺更大必须靠机器人移动 + 逐块推进，不能在这里假装做得到。
A.build_platform = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local size = math.floor(tonumber(a.size) or 3)
  if size % 2 == 0 then size = size + 1 end
  if size > 5 then size = 5 end
  if size < 1 then size = 1 end

  local cx, cy, cz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (cx and cz) then
    local bx, by, bz = botPos(bot)
    if not bx then return false, "未给坐标，且读不到假人位置" end
    cx, cz = math.floor(bx), math.floor(bz)
    if not cy then cy = math.floor(by) - 1 end     -- 脚所在格的下一格 = 地面层
  end
  if not cy then
    local _, by = botPos(bot)
    if not by then return false, "需要 y（或让机器人站好再调用）" end
    cy = math.floor(by) - 1
  end

  local item = a.item or "oak_planks"
  local half = (size - 1) / 2
  local placed, failed, skipped = {}, {}, {}
  for dx = -half, half do
    for dz = -half, half do
      local tx, tz = cx + dx, cz + dz
      -- 用 cellIsOpen：长草/花瓣的格子也算"可放"（放下去会自动替换掉那些装饰 ✓），
      -- 否则整片草地都会被当成"已占用"而跳过，平台就出现莫名其妙的空洞 ✗
      if cellIsOpen(tx, cy, tz) then
        local ref = nil
        for _, f in ipairs({ { 1, 0, 0 }, { -1, 0, 0 }, { 0, 0, 1 }, { 0, 0, -1 } }) do
          local nm = readBlock(tx + f[1], cy, tz + f[3])
          -- 参照必须是**完整方块**：草/花瓣做不了支撑，拿它当参照就会放出悬空方块 ✗
          if standable(nm) then
            ref = { tx + f[1], cy, tz + f[3] }
            break
          end
        end
        if ref then
          local ok, res = A.place_adjacent({ bot = bot, x = ref[1], y = ref[2], z = ref[3], item = item })
          if ok and type(res) == "table" and res.at
             and res.at.x == tx and res.at.z == tz and res.at.y == cy then
            placed[#placed + 1] = { x = tx, y = cy, z = tz }
          elseif ok and type(res) == "table" then
            -- 落到别处去了：如实记录，不算成功
            failed[#failed + 1] = { x = tx, y = cy, z = tz, landed = res.at }
          else
            failed[#failed + 1] = { x = tx, y = cy, z = tz, why = tostring(res) }
          end
        else
          skipped[#skipped + 1] = { x = tx, y = cy, z = tz, why = "四周没有可贴的实心方块" }
        end
      end
    end
  end
  return true, {
    center = { x = cx, y = cy, z = cz }, size = size, item = item,
    placed = placed, failed = failed, skipped = skipped,
    placed_n = #placed, failed_n = #failed, skipped_n = #skipped,
  }
end

-- --- 往外扩平台（造桥式推进）-------------------------------------------------
-- build_platform 是"以某点为中心铺一块"（受 4.5 格放置距离限制），
-- 要真正把平台**往外延伸**，需要的是反复做同一件事：
--   找前线空格 → 贴着已有方块放一块（与地面同层）→ 走到新块上 → 再来一次。
-- 这就是真人搭桥的方式，也是唯一不受放置距离限制的做法。
A.extend_platform = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a    = args or {}
  local bot  = a.bot or "Bot"
  local dir  = a.dir or "east"
  local n    = math.floor(tonumber(a.rows) or 3)
  local item = a.item or "oak_planks"
  -- ⚠ Lua 语法坑（真实事故，代价是整台机器停摆十几分钟）：
  --   表构造式**不能直接取下标**：`{a=1}[k]` 是语法错误（unexpected symbol near '['），
  --   必须写成 `({a=1})[k]`。这类错误是**解析级**的，lua_lint 的词法检查抓不到，
  --   表现为"程序一行都没跑、startup 回退到旧版本、机器停在 shell"。
  local vec  = ({ east = { 1, 0 }, west = { -1, 0 }, south = { 0, 1 }, north = { 0, -1 } })[dir]
  if not vec then return false, "dir 需要 north/south/east/west" end

  local placed, failed, trace = {}, {}, {}
  local t0 = os.clock()
  local budget = tonumber(a.budget) or 90      -- 硬预算：到点就带着"做到哪儿了"返回
  jobNote("extend_platform.start", { dir = dir, rows = n, item = item, budget = budget })
  for i = 1, n do
    -- ⚠ 真实事故：本作业曾经跑了 9 分钟、一块没铺、而且**没有任何回传**——
    --   外部完全分不清它是"还在跑"、"卡死了"还是"崩了自愈了"，只能事后数方块才知道。
    --   长作业必须自带进度与预算：到点正常返回，把已经做到哪一步如实报出来。
    if (os.clock() - t0) > budget then
      failed[#failed + 1] = {
        why = string.format("超过时间预算 %.0f 秒，停在已完成 %d 块（未完成 %d 行）", budget, #placed, n - i + 1),
      }
      break
    end
    local bx, by, bz = botPos(bot)
    if not bx then failed[#failed + 1] = { why = "读不到坐标" }; break end
    local fx, fz = math.floor(bx), math.floor(bz)
    local y = math.floor(by) - 1                     -- 地面层（脚下一格）

    -- 站位：必须站在"边缘**内侧**"，让正前方那一格（同层）是实心 —— 只有它的**顶面**可见，
    -- 往它顶面放，新块才会落在"自己脚这一层的前方一格"。
    -- 真实事故：站在边缘那一格上时，顶面被自己占着 → 放不进去（0.1 秒就拒绝）✗。
    -- 做法：先前线 F = 从脚下往外第一格"可放"的位置；边缘 E = F 的后一格；
    --       机器人应站在 E 的后一格（= F 再后一格），距 E 约 1 格。
    local fx, fz = math.floor(bx), math.floor(bz)
    local y = math.floor(by) - 1                     -- 脚下的地面层
    local tx, tz = nil, nil
    for d = 1, 6 do
      local qx, qz = fx + vec[1] * d, fz + vec[2] * d
      if cellIsOpen(qx, y, qz) then tx, tz = qx, qz; break end
    end
    if not tx then
      -- ⚠ 真实教训（玩家在游戏里直接看出来的）：原设计是"先找前线、找到才走" ✗，
      --   而站在基地内部时 6 格内全是实地 → 找不到前线 → 直接 break → **机器人一步没动** ✗，
      --   外部看来就是"作业跑了但什么都没发生"。改成：沿该方向**走出去直到看见边界** ✓。
      local walked = 0
      while walked < 8 do
        local nx, nz = fx + vec[1] * 2, fz + vec[2] * 2
        pcall(A.walk_to, { bot = bot, x = nx, y = y + 1, z = nz, range = 0.9, timeout = 15, clear = false })
        walked = walked + 1
        bx, by, bz = botPos(bot)
        if not bx then break end
        fx, fz = math.floor(bx), math.floor(bz)
        y = math.floor(by) - 1
        for d = 1, 6 do
          local qx, qz = fx + vec[1] * d, fz + vec[2] * d
          if cellIsOpen(qx, y, qz) then tx, tz = qx, qz; break end
        end
        if tx then break end
      end
      jobNote("extend_platform.walkout", { dir = dir, walked = walked, at = { x = fx, y = y, z = fz }, found = (tx ~= nil) })
    end
    if not tx then
      failed[#failed + 1] = {
        why = string.format("沿 %s 走出去仍未找到可扩的格子（该方向一直实心）", dir),
        at = { x = fx, y = y, z = fz },
      }
      break
    end
    local ex, ez = tx - vec[1], tz - vec[2]          -- 边缘格（实心，可作参照）
    local standX, standZ = ex - vec[1], ez - vec[2]  -- 应站的位置（边缘内侧一格）
    local curX, curZ = math.floor(bx), math.floor(bz)
    -- ⚠ 必须**严格**站在"边缘内侧那一格"：站在边缘格上时，它的顶面被自己占着 ✗，
    --   而放置目标恰好就是自己脚下那一格 → 必然失败（本轮实测：bot z=8.54、edge z=8 ✓）。
    --   range 因此必须收紧到 0.4：否则"差半格"会被当成"已到位" ✗ → 然后静默放不出来 ✓。
    local standingOnEdge = (math.floor(bz) == ez and math.floor(bx) == ex)
    if curX ~= standX or curZ ~= standZ or standingOnEdge then
      local okW, w = pcall(A.walk_to, { bot = bot, x = standX, y = y + 1, z = standZ,
                                        range = 0.4, timeout = 20, clear = false })
      trace[#trace + 1] = { reposition = { x = standX, y = y + 1, z = standZ },
                            on_edge = standingOnEdge,
                            ok = (okW and type(w) == "table" and w.reached) or false }
      local bx2, by2, bz2 = botPos(bot)
      if bx2 then bx, by, bz = bx2, by2, bz2 end
      curX, curZ = math.floor(bx), math.floor(bz)
    end

    local tx2, ty2, tz2 = tx, y + 1, tz           -- 落点 = 脚层、前线那一格
    -- 把"站位 / 参照 / 落点 / 手持物品"一起落盘：
    -- 三种可能的失败（站错位 ✗、瞄错面 ✗、手上没方块 ✗）必须一眼可分，
    -- 否则又只能靠猜 —— 这正是本项目反复踩的坑（曾经为此耗掉好几轮）。
    local okHeld, invNow = A.bot_inv({ bot = bot })
    local heldName, heldSlot = "?", nil
    if okHeld and type(invNow) == "table" then
      heldName, heldSlot = invNow.held_item, invNow.held_slot
    end
    jobNote("extend_platform.try", {
      bot = { x = bx, y = by, z = bz },
      floorY = y,
      edge = { x = ex, y = y, z = ez },
      stand = { x = standX, y = y + 1, z = standZ },
      target = { x = tx2, y = ty2, z = tz2 },
      held = heldName, held_slot = heldSlot,
    })
    local ok, res = A.place_at({ bot = bot, x = ex, y = y, z = ez, item = item })
    if ok and type(res) == "table" and res.placed
       and res.now_block and res.now_block ~= "minecraft:air" then
      placed[#placed + 1] = { x = tx2, y = ty2, z = tz2 }
      -- 落盘 + 聊天栏双重留痕：磁盘给 Agent，聊天栏给人类
      jobNote("extend_platform.placed", { n = #placed, at = { x = tx, y = ty, z = tz }, row = i,
                                          elapsed = tonumber(string.format("%.1f", os.clock() - t0)) })
      pcall(commands.execAsync, string.format("say [agent] platform +%d at %d %d %d", #placed, tx, ty, tz))
      -- 新块在脚这一层 → 需要跳一格站上去
      pcall(commands.exec, "player " .. bot .. " jump")
      sleep(0.5)
      pcall(A.walk_to, { bot = bot, x = tx, y = ty + 1, z = tz, range = 0.8, timeout = 15, clear = false })
    else
      failed[#failed + 1] = {
        x = tx, y = ty, z = tz,
        why = tostring(ok and (type(res) == "table" and res.now_block or res) or res),
      }
      break
    end
  end
  jobNote("extend_platform.done", { placed_n = #placed, failed_n = #failed,
                                    elapsed = tonumber(string.format("%.1f", os.clock() - t0)) })
  return true, {
    dir = dir, rows = n, item = item,
    placed = placed, failed = failed, placed_n = #placed,
    elapsed_s = tonumber(string.format("%.1f", os.clock() - t0)),
  }
end

-- --- 潜行贴边放置（玩家确认可行的方法）--------------------------------------- --
-- 玩家原话："用潜行贴边放"。潜行时不会掉下边缘，且能在**自己脚这一层**把方块放到外侧，
-- 这是真人搭平桥/扩平台的标准手法。
-- 关键设计：**不预测落点** ✗ —— 只负责"潜行 → 瞄准 → 右键"，然后扫周围把**真实落点**读出来 ✓。
-- 瞄准高度做成参数（aim），因为"瞄顶面还是瞄侧面"必须用实测数据定死，不能靠推演 ✗。
A.sneak_place = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a = args or {}
  local bot = a.bot or "Bot"
  local x, y, z = tonumber(a.x), tonumber(a.y), tonumber(a.z)   -- 期望落点
  if not (x and y and z) then return false, "需要 x/y/z（期望落点）" end
  if a.item then
    local okH, h = A.hold_item({ bot = bot, item = a.item })
    if not okH then return false, "拿不到 " .. tostring(a.item) .. "：" .. tostring(h) end
  end
  local aim = tonumber(a.aim) or 0.5      -- 瞄"落点下方那一格"的顶面比例（0.5=中心）

  local faces = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 }, { 0, -1, 0 }, { 0, 0, 1 }, { 0, 0, -1 } }
  local function snap()
    local s = {}
    s[x .. "," .. y .. "," .. z] = tostring(readBlock(x, y, z))
    for _, f in ipairs(faces) do
      local kx, ky, kz = x + f[1], y + f[2], z + f[3]
      s[kx .. "," .. ky .. "," .. kz] = tostring(readBlock(kx, ky, kz))
    end
    return s
  end

  local b0 = snap()
  pcall(commands.exec, "player " .. bot .. " sneak")
  sleep(0.3)
  -- ⚠ 关键一步（查证后的机制，来源 MC-93117）：**潜行时玩家可以把身体探出边缘**，
  --   位置能越过格子边界 ✓ —— 搭桥就是靠这个"探出去"完成的。
  --   我此前一直让机器人站在边缘**内侧一格** ✗，差了一整格 → 朝向/落点全错 ✗。
  --   做法：潜行状态下用 move forward 小幅前进，让它的坐标真正越过边缘（或至少贴到边界）✓，
  --   然后再瞄准、放置；结束统一 stop（避免它一直往前走 ✓）。
  local edgeWalk = a.edge_walk
  if edgeWalk == nil then edgeWalk = 0.25 end
  if edgeWalk and edgeWalk > 0 then
    -- ⚠ 绝不盲走（真实事故，代价是假人死亡 ✗）：
    --   之前这里是"直接 move forward 一段时间"，而**潜行的边缘保护是客户端逻辑** ✗
    --   （MC-93117）—— 假人没有客户端 ✓ 于是它径直走出边缘、坠入虚空身亡 ✗，
    --   连背包里的矿物碎块一起没了 ✓。
    --   改成：每 0.15 秒走一小步，**走之前先确认自己脚下那一格还有地面** ✓，
    --   一旦悬空就立刻停手并落盘说明 ✓ —— 宁可少走，绝不再摔死 ✓。
    local t0w = os.clock()
    while (os.clock() - t0w) < edgeWalk do
      local bx1, by1, bz1 = botPos(bot)
      if not bx1 then break end
      local fy1 = math.floor(by1) - 1
      local cx1, cz1 = math.floor(bx1), math.floor(bz1)
      if not standable(readBlock(cx1, fy1, cz1)) then
        jobNote("sneak_place.edge_stop", {
          why = "脚下已无地面（已在边缘外），停止前探以免坠落",
          bot = { x = bx1, y = by1, z = bz1 },
        })
        break
      end
      pcall(commands.execAsync, "player " .. bot .. " move forward")
      sleep(0.15)
      pcall(commands.execAsync, "player " .. bot .. " stop")
    end
    sleep(0.15)
  end
  local bx0, by0, bz0 = botPos(bot)
  jobNote("sneak_place.pos", { bot = { x = bx0, y = by0, z = bz0 }, edge_walk = edgeWalk })
  -- 瞄准"期望落点下方那一格"的顶面（潜行探边后射线会落到边缘外沿 → 方块进到外侧）
  pcall(commands.exec, string.format("player %s look at %.2f %.2f %.2f",
    bot, x + 0.5, (y - 1) + aim, z + 0.5))
  sleep(0.3)
  local okU = A.use_once({ bot = bot })
  sleep(0.6)
  pcall(commands.exec, "player " .. bot .. " unsneak")

  local b1 = snap()
  local landed, landedName = nil, nil
  for k, v in pairs(b1) do
    if b0[k] ~= v and type(v) == "string" and not v:find("air", 1, true) then
      landed, landedName = k, v
    end
  end
  local cx, cy, cz = nil, nil, nil
  if landed then cx, cy, cz = landed:match("(-?%d+),(-?%d+),(-?%d+)") end
  local at = cx and { x = tonumber(cx), y = tonumber(cy), z = tonumber(cz) } or nil
  jobNote("sneak_place", { want = { x = x, y = y, z = z }, aim = aim, use_ok = (okU and true or false),
                            landed = at, block = landedName })
  return true, {
    bot = bot, want = { x = x, y = y, z = z }, aim = aim,
    use_ok = (okU and true or false), block = landedName, at = at,
    hit = (at ~= nil and at.x == x and at.y == y and at.z == z) or false,
  }
end

A.chop_tree = function(args)
  if not hasCommandsAPI() then return false, "chop_tree 需要指令电脑（要能执行 /player）" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local cx, cy, cz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (cx and cy and cz) then return false, "需要 x / y / z（作业中心点）" end
  local r       = math.floor(tonumber(a.radius) or 6)
  local timeout = tonumber(a.timeout) or 8       -- 每段木头的破坏超时（秒）
  local settle  = tonumber(a.settle) or 1        -- 开工前的稳定等待
  local t0      = os.clock()
  local report  = { bot = bot, chopped = {}, failed = {}, note = {} }

  -- 1) 找木头：复用 survey 的批量普查（分块 + 实测顺序解码）
  local okS, res = A.survey({
    x = cx, y = cy, z = cz,
    radius = r, radius_y = math.min(r, 10),
    only = "log",
  })
  if not okS or type(res) ~= "table" then
    return false, "普查失败：" .. tostring(res)
  end
  local logs = res.blocks or {}
  report.found = #logs
  report.survey_calls = res.calls
  if #logs == 0 then return false, "在半径 " .. r .. " 内没有找到任何木头" end

  -- 从低到高：先砍最下面那段。这样上面的木头不会因为"够不着"而白等
  table.sort(logs, function(p, q) return p.y < q.y end)

  commands.execAsync("player " .. bot .. " stop")
  sleep(settle)

  -- 顺手在聊天栏报一句：让人类看得见机器人在干什么（而不是神秘地改世界）
  pcall(commands.execAsync, string.format("say [agent] Bot chopping %d logs near %d %d %d",
        #logs, cx, cy, cz))

  -- 3) 自动换工具：假人会继承真人的背包（实测手上是火把），
  --    不换工具也能砍，但速度差好几倍。优先斧头，其次剑。
  local okInv, inv = A.bot_inv({ bot = bot })
  if okInv and type(inv) == "table" then
    report.held_before = inv.held_item
    local pick, rank = nil, 0
    for _, it in ipairs(inv.items or {}) do
      local rr = 0
      if type(it.id) == "string" then
        if it.id:find("_axe", 1, true) then rr = 3
        elseif it.id:find("_sword", 1, true) then rr = 2
        elseif it.id:find("_shovel", 1, true) or it.id:find("_pickaxe", 1, true) then rr = 1 end
      end
      -- 只有 0-8 是快捷栏，hotbar 子命令只能选这一段
      if rr > rank and type(it.slot) == "number" and it.slot >= 0 and it.slot <= 8 then
        pick, rank = it, rr
      end
    end
    if pick then
      -- hotbar 是 1 起算（实测），所以 +1；否则会静默拿错槽（详见 A.hold_item 注释）
      pcall(commands.exec, "player " .. bot .. " hotbar " .. tostring(pick.slot + 1))
      report.tool, report.tool_slot = pick.id, pick.slot
    else
      report.tool = "none(徒手)"
    end
  end

  -- 2) 先分清"够得着"和"够不着"。
  --    真实事故：9 个失败里有 8 个是 8 格外的另外两棵树——Bot 站在原地伸不到 4.5 格，
  --    却仍然每格白等 10 秒超时（多花 90 秒，而且报告读起来像"这里挖不动"）。
  --    够不着就必须如实标成 out_of_reach，让它成为一个"待补的能力"而不是假故障。
  local bx, by, bz = botPos(bot)
  report.bot_pos = bx and { x = bx, y = by, z = bz } or nil
  local reach = tonumber(a.reach) or 4.2

  -- 瞄准点取 y+0.2（而不是方块中心的 y+0.5）：
  -- 真实事故：Bot 站在树干正下方时瞄中心，视线太陡，射线先碰到**上面那一格**，
  -- 于是"要砍 y=71"实际砍掉了 y=72（报告里 y=72 显示 already air 就是铁证）。
  local function chopOne(p, tmo)
    local lookCmd = string.format("player %s look at %d %.1f %d", bot, p.x, p.y + 0.2, p.z)
    -- 用 packReturns：exec 的第二个返回值是"指令是否执行成功"，
    -- 不是错误信息——写成 local ok, err = pcall(commands.exec, ...) 的话，
    -- 失败时会打印出 "错误：true" 这种自相矛盾的东西。
    local pL = packReturns(pcall(commands.exec, lookCmd))
    if not pL[1] then return false, "look 异常：" .. tostring(pL[2]) end
    if pL[2] == false then return false, "look 被拒绝（权限或参数问题）" end
    -- 持续攻击：投递即返回（同步 exec 会一直阻塞，等于永远不返回）
    pcall(commands.execAsync, "player " .. bot .. " attack continuous")
    local deadline = os.clock() + tmo
    while os.clock() < deadline do
      sleep(0.15)
      if blockIsAir(p.x, p.y, p.z) then return true end
    end
    return false, "超时未破坏"
  end

  local pending = {}
  for _, p in ipairs(logs) do
    if blockIsAir(p.x, p.y, p.z) then
      report.chopped[#report.chopped + 1] = { x = p.x, y = p.y, z = p.z, note = "already air" }
    else
      local d = nil
      if bx then d = math.sqrt((p.x - bx) ^ 2 + (p.y + 0.5 - by) ^ 2 + (p.z - bz) ^ 2) end
      if d and d > reach then
        report.failed[#report.failed + 1] = {
          x = p.x, y = p.y, z = p.z,
          dist = tonumber(string.format("%.1f", d)),
          why = "out_of_reach（够不着，需要先走过去）",
        }
      else
        pending[#pending + 1] = p
      end
    end
  end

  -- 3) 两轮：先按从低到高砍一遍，再对失败的补一轮。
  --    重试不是碰运气：第一轮把下方木头砍掉之后，原本偏陡的视线会落到正确的格子上，
  --    所以第二轮命中率明显更高（这正是"y=71 超时"的实际成因）。
  for round = 1, 2 do
    local again = {}
    for _, p in ipairs(pending) do
      if blockIsAir(p.x, p.y, p.z) then
        report.chopped[#report.chopped + 1] = { x = p.x, y = p.y, z = p.z, round = round }
      else
        local okC, why = chopOne(p, timeout)
        if okC then
          report.chopped[#report.chopped + 1] = { x = p.x, y = p.y, z = p.z, round = round }
        else
          again[#again + 1] = { p = p, why = why }
        end
      end
    end
    if #again == 0 then break end
    pending = {}
    if round == 2 then
      for _, it in ipairs(again) do
        report.failed[#report.failed + 1] = { x = it.p.x, y = it.p.y, z = it.p.z, why = it.why }
      end
    else
      for _, it in ipairs(again) do pending[#pending + 1] = it.p end
    end
  end

  -- 4) 收工：停手 + 复查（不靠"应该挖完了"，靠再读一遍方块）
  pcall(commands.execAsync, "player " .. bot .. " stop")
  sleep(0.5)
  local okV, after = A.survey({
    x = cx, y = cy, z = cz,
    radius = r, radius_y = math.min(r, 10),
    only = "log",
  })
  if okV and type(after) == "table" then
    report.remaining = #(after.blocks or {})
  else
    report.remaining = "复查失败：" .. tostring(after)
  end
  report.elapsed_s = tonumber(string.format("%.2f", os.clock() - t0))
  pcall(commands.execAsync, string.format("say [agent] done: chopped %d, failed %d, remaining %s",
        #report.chopped, #report.failed, tostring(report.remaining)))
  return true, report
end

-- --- 作业 ---------------------------------------------------------------- --
A.dig       = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.dig(), {} end
A.dig_up    = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.digUp(), {} end
A.dig_down  = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.digDown(), {} end
A.place     = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.place(), {} end
A.place_up  = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.placeUp(), {} end
A.place_down= function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.placeDown(), {} end
A.attack    = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.attack(), {} end
A.drop      = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.drop(), {} end
A.suck      = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.suck(), {} end
A.suck_up   = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.suckUp(), {} end
A.suck_down = function() if not IS_TURTLE then return false, "需要海龟" end
                            return turtle.suckDown(), {} end

A.select = function(args)
  if not IS_TURTLE then return false, "需要海龟" end
  local s = tonumber(args and args.slot)
  if not s or s < 1 or s > 16 then return false, "slot 需为 1..16" end
  return turtle.select(s), { slot = s }
end

A.refuel = function(args)
  if not IS_TURTLE then return false, "需要海龟" end
  local n = tonumber(args and args.n) or 1
  return turtle.refuel(n), { fuel = turtle.getFuelLevel() }
end

-- --- 感知 ---------------------------------------------------------------- --
A.status = function()
  local out = {
    is_turtle   = IS_TURTLE,
    facing      = facingKnown and FACING[facingIdx] or "unknown",
    peripherals = P.names,
    dry_run     = DRY_RUN,
    -- 身份自证（真实事故驱动）：曾经出现"多台机器都用同一个 who 上报"，
    -- 从外部无法分辨到底哪台在回答。带上 ID / 标签 / 运行时长，
    -- 就能一眼看出"这条状态来自哪台机器"。
    id          = os.getComputerID(),
    label       = os.getComputerLabel(),
    who         = WHO,
    uptime_s    = math.floor(os.clock()),
    -- 准星感知状态：让 Agent 每一步都能知道"假人现在盯着什么"（不必额外发一次指令 ✓）
    jade        = { hud = jadeState.hud, last = jadeState.lastKey,
                    updates = jadeState.updated or 0 },
  }
  if IS_TURTLE then
    -- 注意：CC 海龟没有绝对坐标，位置需要外部锚点（例如"从某个已知点出发"）
    out.fuel     = turtle.getFuelLevel()
    out.selected = turtle.getSelectedSlot and turtle.getSelectedSlot() or nil
    out.label    = os.getComputerLabel()
    out.id       = os.getComputerID()
  end
  if P.geo then out.geo = geoTel() end
  if P.playerDet then
    -- 真实方法名：getOnlinePlayers（getPlayers 不存在，去掉以免误导）
    out.online = callFirst(P.playerDet, { "getOnlinePlayers" })
  end
  return true, out
end

A.players = function(args)
  if not P.playerDet then return false, "缺少 Player Detector 外设" end
  local r = tonumber(args and args.radius)
  if r then
    local list, err = callFirst(P.playerDet, { "getPlayersInRange", "getPlayersInRadius" }, r)
    if list then return true, { players = list, radius = r } end
    return false, err
  end
  local list, err = callFirst(P.playerDet, { "getOnlinePlayers", "getPlayers" })
  if list then return true, { players = list } end
  return false, err
end

-- Geo Scanner 的运行状态（燃料/冷却）。
-- 真实方法名由 peripheral_api 从游戏里问出来：getFuelLevel / getMaxFuelLevel / cost /
-- getFuelConsumptionRate / getOperationCooldown。**扫描是要消耗燃料的**，
-- 这正是之前 scan 时好时坏的根因（没燃料/在冷却就会失败）。
geoTel = function()
  local lvl  = callFirst(P.geo, { "getFuelLevel" })
  local mx   = callFirst(P.geo, { "getMaxFuelLevel" })
  local cost = callFirst(P.geo, { "cost" })
  local cd   = callFirst(P.geo, { "getOperationCooldown" })
  return { fuel = lvl, max_fuel = mx, cost_per_scan = cost, cooldown = cd }
end

A.scan = function(args)
  if not P.geo then return false, "缺少 Geo Scanner 外设（模组方块感知靠它）" end
  local r = tonumber(args and args.radius) or 8
  local blocks, err = callFirst(P.geo, { "scan" }, r)
  if not blocks then return false, "scan 失败（可能是燃料不足或正在冷却）：" .. tostring(err) .. "  运行状态=" .. textutils.serialize(geoTel()) end
  -- 压缩：按方块名聚合，避免回传过大。
  -- AP 的 scan 每一项通常带 count 字段（同类方块的堆叠数），按 count 累加才准确。
  local agg, total = {}, 0
  for _, b in ipairs(blocks) do
    local name, cnt
    if type(b) == "table" then
      name = b.name or b.block or "?"
      cnt  = tonumber(b.count) or 1
    else
      name, cnt = tostring(b), 1
    end
    agg[name] = (agg[name] or 0) + cnt
    total = total + cnt
  end
  local out = { radius = r, entries = #blocks, blocks = total, by_name = agg }
  local tel = geoTel()
  out.geo = tel
  return true, out
end

A.block_info = function(args)
  if not P.blockReader then return false, "缺少 Block Reader 外设" end
  -- 真实方法名（peripheral_api 问出来的）：getBlockData / getBlockName / getBlockStates / isTileEntity
  local data, err = callFirst(P.blockReader, { "getBlockData" })
  if data ~= nil then return true, { block = data } end
  -- 退一步：至少给出名称与状态
  local name, err2 = callFirst(P.blockReader, { "getBlockName" })
  if name == nil then
    return false, "读不到方块：Block Reader 前方可能不是方块（" .. tostring(err) .. " / " .. tostring(err2) .. "）"
  end
  local states = callFirst(P.blockReader, { "getBlockStates" })
  local tile   = callFirst(P.blockReader, { "isTileEntity" })
  return true, { block = { name = name, states = states, is_tile_entity = tile },
                 note = "getBlockData 返回 nil，退化为名称/状态" }
end

A.inv_list = function()
  if not IS_TURTLE then return false, "该指令需要海龟本体" end
  local items = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d then
      items[#items + 1] = { slot = i, name = d.name, count = turtle.getItemCount(i) }
    end
  end
  return true, { items = items, fuel = turtle.getFuelLevel() }
end

A.inv_man = function(args)
  if not P.invMan then return false, "缺少 Inventory Manager 外设" end
  local op = (args and args.op) or "list"
  if op == "list" then
    -- 真实方法名（peripheral_api 问出来的）：
    --   listChest / getItemsChest  -> 读**相邻容器**（本项目的目标用法）
    --   list / getItems            -> 读**绑定的玩家**，需要记忆卡绑定
    -- 先把"相邻容器"这条路走通，并且把两条路的失败原因分开报，
    -- 否则会拿"没有记忆卡"的报错去误导人（真实踩过）。
    local l, cerr = callFirst(P.invMan, { "listChest", "getItemsChest" })
    if l then return true, { items = l, source = "相邻容器" } end
    local p, perr = callFirst(P.invMan, { "list", "getItems" })
    if p then return true, { items = p, source = "绑定玩家" } end
    return false, "读库存失败｜相邻容器：" .. tostring(cerr) ..
                  "｜绑定玩家：" .. tostring(perr) ..
                  "（要读容器请让 Inventory Manager 紧贴一个箱子/桶；要读玩家背包需放入记忆卡绑定）"
  end
  return false, "暂不支持的 inventory 操作：" .. tostring(op)
end

-- 玩家绝对坐标。
-- 这台计算机自己不知道自己在哪（CC 没有绝对坐标），但 Player Detector 能给出
-- 玩家的坐标 —— 有了它，Agent 就能把"相对移动"锚定到世界坐标上。
A.player_pos = function(args)
  if not P.playerDet then return false, "缺少 Player Detector 外设" end
  local name = args and args.name
  if not name then
    local online, err = callFirst(P.playerDet, { "getOnlinePlayers" })
    if type(online) == "table" then name = online[1] end
    if not name then return false, "没有在线玩家可定位（" .. tostring(err) .. "）" end
  end
  local pos, err = callFirst(P.playerDet, { "getPlayerPos" }, name)
  if not pos then return false, "取位置失败：" .. tostring(err) end
  return true, { name = name, pos = pos }
end

-- 外设运行状态（燃料/冷却），便于 Agent 判断"为什么某条指令失败了"
A.geo_status = function()
  if not P.geo then return false, "缺少 Geo Scanner 外设" end
  return true, geoTel()
end

-- GPS 定位：主计算机自己的绝对坐标。
-- 依据 CC 的 gps 库源码：需要至少 4 台 GPS 主机在范围内。
A.locate = function(args)
  local timeout = tonumber(args and args.timeout) or 2
  local x, y, z = gps.locate(timeout)
  if not x then
    return false, "GPS 定位失败：需要至少 4 台 GPS 主机在范围内（且位置不共线）"
  end
  return true, { x = x, y = y, z = z }
end

-- 发现海龟：广播一次，收集应答。
-- 为什么需要：海龟的 rednet id 是它自己的 computer id，服务端侧无从"登记"，
-- 与其让用户手工抄 id，不如每次现问（问出来的 id 直接用于 args.target）。
A.discover_turtles = function(args)
  if #P.modems == 0 then
    return false, "本机没有调制解调器：需要在计算机相邻面放一个 Wireless Modem"
  end
  local wait = tonumber(args and args.wait) or 2
  rednet.broadcast({ cmd = "status" }, "bridge")
  local found = {}
  local deadline = os.clock() + wait
  while os.clock() < deadline do
    local remain = deadline - os.clock()
    if remain <= 0 then break end
    local sender, msg = rednet.receive("bridge_reply", remain)
    if sender and type(msg) == "table" then
      found[#found + 1] = { id = sender, ok = msg.ok, result = msg.result }
    end
  end
  table.sort(found, function(a, b) return (a.id or 0) < (b.id or 0) end)
  return true, { count = #found, turtles = found }
end

A.say = function(args)
  if not P.chat then return false, "缺少 Chat Box 外设" end
  local text = (args and args.text) or ""
  local res, err = callFirst(P.chat, { "sendMessage", "sendChat" }, text, WHO)
  if res == nil and err then return false, tostring(err) end
  return true, { said = text }
end

A.chat_read = function()
  if not P.chat then return false, "缺少 Chat Box 外设" end
  -- 实测（peripheral_api）：AP 0.7.44 的 Chat Box **只有发送类方法**
  -- （sendMessage / sendMessageToPlayer / sendToastToPlayer / sendFormatted* 等），
  -- **没有任何读取聊天的 API** —— 所以"读聊天"这件事在这个版本上做不到。
  local msgs, err = callFirst(P.chat, { "getMessages", "readMessages" })
  if msgs then return true, { messages = msgs } end
  return false, "本版 Chat Box 不支持读取聊天（只有发送类 API）：" .. tostring(err)
end

-- 远程退出 / 远程关机（清理"跑错程序"的机器用）。
-- 背景：曾经因为把主程序误跑在其他机器上，导致多台机器抢同一个 who，
-- 而从外部既看不到是哪台、也停不掉它。有了这两个动作就能自己收拾现场。
A.quit = function()
  WANT_QUIT = true
  EXIT_NOW = true          -- 故意退出，看门狗不要重启
  return true, { note = "本程序将在回报后退出（回到 shell 提示符）" }
end

A.shutdown = function()
  WANT_SHUTDOWN = true
  EXIT_NOW = true          -- 故意关机，看门狗不要重启
  return true, { note = "本计算机将在回报后关机（需重新开机/重载才会启动）" }
end

-- 自我更新：从网关拉最新版 → **先做语法自检** → 覆盖本地副本 → 重启计算机。
-- 目的：让"Agent 改完代码"不再需要人到游戏里手动重载 —— 这是本项目最大的效率瓶颈
-- （每改一行都要人肉重载，半小时的活被拖成几小时）。
-- 语法自检很重要：宁可不更新，也不能把机器刷成砖 ✗。
-- --- 按指定面精确放置 ------------------------------------------------------- --
-- 与 place_adjacent 的分工：
--   place_adjacent 让**射线自己决定**贴在哪个面 ✗ —— 摆产线时不行 ✗（落点会飘 ✓）
--   这里给定"落点 + 要点的那个邻居方块" ✓ ⇒ 点的是哪一面、方块朝向是什么，全确定 ✓
--
-- 为什么朝向能确定（查过 1.20.1 源）：
--   漏斗/发射器这类方块 `getStateForPlacement` = `clickedFace.getOpposite()` ✓
--   ⇒ **方块朝向 = 指向你点的那个方块** ✓
--   所以"让漏斗朝东"的做法是：点它**东边那个方块**的西面 ✓（不是点西边的方块 ✗）
--   ⇒ 参数故意用 ref（被点的方块）而不是面编号 ✓ —— 少一层心智负担 ✓
--
-- 自证：放完读回落点，`placed` 只看**格子真的变了** ✓ 不看指令回显 ✓
A.place_face = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local x, y, z = tonumber(a.x), tonumber(a.y), tonumber(a.z)              -- 落点
  local rx, ry, rz = tonumber(a.refx), tonumber(a.refy), tonumber(a.refz)  -- 被点的邻居
  if not (x and y and z and rx and ry and rz) then
    return false, "需要 x/y/z（落点）与 refx/refy/refz（要点的那个邻居方块）"
  end
  local nx, ny, nz = rx - x, ry - y, rz - z
  if math.abs(nx) + math.abs(ny) + math.abs(nz) ~= 1 then
    return false, "落点与 ref 必须**相邻**（三个方向差之和为 1，实际 "
      .. tostring(nx + ny + nz) .. "）"
  end
  if a.item then
    local okH, h = A.hold_item({ bot = bot, item = a.item })
    if not okH then return false, "拿不到 " .. tostring(a.item) .. "：" .. tostring(h) end
  end
  -- 共享面的中心 = 落点中心 + 0.5 ×（落点→ref 的方向）✓
  local ax = x + 0.5 + nx * 0.5
  local ay = y + 0.5 + ny * 0.5
  local az = z + 0.5 + nz * 0.5
  local before = readBlock(x, y, z)
  if before ~= nil and before ~= "minecraft:air" then
    return false, "落点 (" .. x .. "," .. y .. "," .. z .. ") 已经有 " .. tostring(before) .. " 了"
  end
  -- ★ 必须先潜行再右键（真实事故 ✓ 两处放置连续失败都栽在这 ✗）：
  --   目标旁边如果是**可交互方块**（熔炉/箱子/工作台…）✗，普通右键是"开界面"✗
  --   —— 假人没有界面 ✓ 于是这一下什么也没放 ✗ 而且**指令回显还是成功的** ✗
  --   真人的做法：**潜行**右键 ✓（潜行时不与世界交互 ✓ 只放方块 ✓）⇒ 照做 ✓
  pcall(commands.exec, "player " .. bot .. " sneak")
  sleep(0.15)
  pcall(commands.exec, string.format("player %s look at %.3f %.3f %.3f", bot, ax, ay, az))
  sleep(0.25)
  pcall(commands.exec, "player " .. bot .. " use once")
  sleep(0.45)
  local after = readBlock(x, y, z)
  local refNow = readBlock(rx, ry, rz)
  return true, {
    bot = bot, at = { x = x, y = y, z = z }, ref = { x = rx, y = ry, z = rz },
    aim = { x = ax, y = ay, z = az },
    before = before, after = after,
    placed = (after ~= before),
    ref_block = refNow,
  }
end

-- --- 石砾农场：把 ATM9 那条"潜行空手右键泥土掉石砾"变成**一条指令** --------- --
--
-- 规则出处（不是猜的 ✓）：实例里的
--   kubejs/server_scripts/mods/exdeorum/pebbles.js ✓
--   条件三条：主手**空** ✓ 玩家**潜行** ✓ 方块带 `minecraft:dirt` 标签 ✓
--   掉落：`block.popItemFromFace(dropItem, facing)` —— 从**被点的那个面**弹出来 ✓
--   ⚠ 这个整合包里 `minecraft:dirt` 标签**包含 grass_block** ✓
--     （让游戏自己回答：`/execute if block x y z #minecraft:dirt` ✓ 返回 1 ✓）
--   ⚠ 战利品表的随机下标会**越界**：`loot[Math.floor(random*12)]` 只有 6 项 ✓
--     ⇒ 越界的 6 种情况落到 `?? "exdeorum:stone_pebble"` ✓
--     ⇒ **石砾恰好占 50%** ✓ 其余 6 种各 1/12 ✓（做圆石只要 stone_pebble ✓）
--
-- ── 四个实测坑（每个都表现为"看起来正常但颗粒无收" ✗）────────────────────
--   1) 假人**能**触发这个事件 ✓ —— KubeJS 探针实测：
--      `cls=carpet.patches.EntityPlayerMPFake … empty=true dirtTag=true shift=true` ✓
--      之前"没反应"跟事件投递无关 ✗ 是下面 2/3 条 ✗
--   2) **弹出来的石砾会被自己捡走** ✗ → 手不再空 ✗ → 之后每次点击都被
--      `!item.isEmpty()` 挡掉 ✓ **而且一声不响** ✗ —— 这才是"机制失效"的真相 ✓
--      拾取落点（实测 + 源码）：**编号最小的空快捷槽** ✓
--      ⇒ 站方块正上方点：必被捡 ✓ 必须清手 ✓
--      ⇒ 清手手法：把手里的东西**朝走道沟丢下去** ✓
--        沟底比脚底低 1 格 ⇒ 高度差让假人**够不到** ✓（不用担心又被捡回来 ✓）
--      附：若那只手的下一格正好是同种石砾 → 会**并进那一堆** ✓ 手保持空 ✓
--          ⇒ 只要低号槽里已有同种，就能连点 ✓✓（本动作因此不必每次都清 ✓）
--   3) 从 3 格外点能避免被捡 ✓ 但**射线必须真的落在土方块上** ✗
--      实测：射线被 framedblocks 的台阶边挡住 ✗ 而对那格的右键**根本不触发事件** ✗
--      （探针一条日志都没有 ✓）而 Jade 准星却报"打在台阶边上" ✓
--      ⇒ **"准星说打到了"不能当依据** ✗ 以事件日志/掉落物为准 ✓
--   4) 潜行状态要**每次重设** ✓（tp / 丢东西之后不要假定它还蹲着 ✓）
--
-- 自证：每轮读一次背包（NBT 权威 ✓），返回前后石砾总数与分类 ✓
A.pebble_farm = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local x, y, z = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (x and y and z) then
    return false, "需要 x/y/z（要点的那块土/草方块坐标；假人应站在它正上方）"
  end
  local clicks = math.floor(tonumber(a.clicks) or 20)
  local t0 = os.clock()

  -- 丢东西的瞄准点：默认取被点方块 "+1.5格X、略低" —— 那个方向正是走道沟 ✓
  local vx = tonumber(a.dumpx) or (x + 1.5)
  local vy = tonumber(a.dumpy) or (y + 0.2)
  local vz = tonumber(a.dumpz) or (z + 0.5)

  local function readInv()
    local ok, inv = A.bot_inv({ bot = bot })
    if not ok or type(inv) ~= "table" then return nil, nil end
    return inv.held_item, inv
  end

  local function pebbleCounts(inv)
    local m, total = {}, 0
    for _, it in ipairs((inv and inv.items) or {}) do
      if type(it.id) == "string" and it.id:find("_pebble", 1, true) then
        m[it.id] = (m[it.id] or 0) + (it.count or 1)
        total = total + (it.count or 1)
      end
    end
    return m, total
  end

  -- 动手前的两项硬检查 ✓（宁可拒绝，也不要在玩家世界里白点一通 ✓）
  local held, inv0 = readInv()
  if held ~= nil and held ~= "" then
    return false, "手上还拿着 " .. tostring(held) .. "（这条规则要求空手 ✓，先清空再点）"
  end
  local before = readBlock(x, y, z)
  if type(before) ~= "string" or before == "minecraft:air" then
    return false, "目标格 (" .. x .. "," .. y .. "," .. z .. ") 是 " .. tostring(before) .. "，不是方块"
  end

  pcall(commands.exec, "player " .. bot .. " sneak")
  local clears, clearFail, targetChanged = 0, 0, 0
  for i = 1, clicks do
    pcall(commands.exec,
      string.format("player %s look at %d %.2f %d", bot, x, y + 0.4, z))
    sleep(0.15)
    pcall(commands.exec, "player " .. bot .. " use once")
    sleep(0.35)
    local h = readInv()
    if h ~= nil and h ~= "" then
      -- 手被占 ⇒ 被自己捡了 ✓ 朝走道沟丢下去 ✓ 丢完手就空 ✓
      pcall(commands.exec,
        string.format("player %s look at %.2f %.2f %.2f", bot, vx, vy, vz))
      sleep(0.15)
      pcall(commands.exec, "player " .. bot .. " dropStack")
      clears = clears + 1
      sleep(0.25)
      local h2 = readInv()
      if h2 ~= nil and h2 ~= "" then clearFail = clearFail + 1 end
      pcall(commands.exec, "player " .. bot .. " sneak")
    end
    -- 每 8 次抽查一次目标方块：万一被自己挖掉/换掉，立刻停 ✓ 而不是白点到底 ✓
    if i % 8 == 0 then
      local now = readBlock(x, y, z)
      if now ~= before then targetChanged = targetChanged + 1 end
      jobNote("pebble_farm.progress", { i = i, clears = clears, block = now })
    end
  end

  local _, inv1 = readInv()
  local m0, n0 = pebbleCounts(inv0)
  local m1, n1 = pebbleCounts(inv1)
  return true, {
    bot = bot, at = { x = x, y = y, z = z }, block = before,
    clicks = clicks, clears = clears, clear_failures = clearFail,
    target_changed = targetChanged,
    pebbles_before = n0, pebbles_after = n1, gained = n1 - n0,
    by_type_after = m1,
    seconds = math.floor(os.clock() - t0),
  }
end

-- --- 区域快照：把"读世界"从零散射线升级成**结构化快照** --------------------- --
-- 参考对象（用户点名的方向 ✓）：Create 的蓝图与蓝图大炮 ✓
--   蓝图大炮有**两半** ✓：① 一份蓝图（结构化数据 ✓）② 一门会飞过去逐块放的炮 ✓
--   这个动作是"①读图"的那一半 ✓ `A.blueprint_build` 是"②放图"那一半 ✓
--
-- 为什么不再一格一格 readBlock ✗：
--   实测一片 16×4×16 逐格读要几十秒 ✗ 而 `commands.getBlockInfos` **一次读一整块** ✓
--   两条既有结论（都验证过 ✓ 见 docs/carpet-route-progress.md）：
--     a) 体积上限：17³ 直接 `Too many blocks` ✗ ⇒ 按 **4³ 分块** ✓
--     b) 返回项**不带坐标** ✗ ⇒ 顺序 = **y（最外）→ z（中）→ x（最内）** ✓
--        （用"批量 vs 单点逐格"对照 + 穷举 6 种排列定下来的 ✓ 不能靠猜 ✗）
--
-- 自证：返回 solid_n + air_n + 逐类 counts ✓ 外部还能与单点读法抽查比对 ✓
A.snapshot = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  if type(commands.getBlockInfos) ~= "function" then return false, "本版本没有 commands.getBlockInfos" end
  local a = args or {}
  local x0, y0, z0 = math.floor(tonumber(a.x0) or 0), math.floor(tonumber(a.y0) or 0), math.floor(tonumber(a.z0) or 0)
  local x1, y1, z1 = math.floor(tonumber(a.x1) or 0), math.floor(tonumber(a.y1) or 0), math.floor(tonumber(a.z1) or 0)
  if x1 < x0 then x0, x1 = x1, x0 end
  if y1 < y0 then y0, y1 = y1, y0 end
  if z1 < z0 then z0, z1 = z1, z0 end
  local maxCells = math.floor(tonumber(a.maxcells) or 900)
  local wantAll  = (a.air == true)
  -- ★ 按方块名筛选（子串 ✓）：找"岛上的小麦田"这类问题就靠它 ✓
  --   为什么必须加：整片区域读回来是几千格 ✗ 而我只关心 `minecraft:wheat` ✓
  --   有了它，一次扫描就能定位农田/矿脉/机方块 ✓ 也是"读世界"能力的关键一步 ✓
  local match = a.match
  if type(match) ~= "string" or match == "" then match = nil end
  local vol = (x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1)
  if vol > 32768 then return false, "区域太大（" .. vol .. " 格 ✗ 上限 32768）" end

  local cells, counts, airN, matched = {}, {}, 0, 0
  local chunk = 4                      -- ★ 必须 ≤4³ ✓ 否则 Too many blocks ✗
  for cy = y0, y1, chunk do
    for cz = z0, z1, chunk do
      for cx = x0, x1, chunk do
        local ex = math.min(cx + chunk - 1, x1)
        local ey = math.min(cy + chunk - 1, y1)
        local ez = math.min(cz + chunk - 1, z1)
        local p = packReturns(pcall(commands.getBlockInfos, cx, cy, cz, ex, ey, ez))
        if not p[1] or type(p[2]) ~= "table" then
          return false, "getBlockInfos 失败（" .. cx .. "," .. cy .. "," .. cz .. "）：" .. tostring(p[2])
        end
        local i = 0
        for y = cy, ey do
          for z = cz, ez do
            for x = cx, ex do
              i = i + 1
              local e  = p[2][i]
              local nm = (type(e) == "table" and (e.name or e.block)) or tostring(e)
              if nm == "minecraft:air" or nm == "air" then
                airN = airN + 1
                if wantAll then cells[#cells + 1] = { x = x, y = y, z = z, n = "minecraft:air" } end
              else
                counts[nm] = (counts[nm] or 0) + 1
                -- 状态也要带上（如小麦的 age=7 = 成熟 ✓ 决定"该不该收" ✓）
                local st = nil
                if type(e) == "table" and type(e.state) == "table" then st = e.state end
                local hit = (match == nil) or (string.find(nm, match, 1, true) ~= nil)
                if hit then
                  if st then
                    cells[#cells + 1] = { x = x, y = y, z = z, n = nm, state = st }
                  else
                    cells[#cells + 1] = { x = x, y = y, z = z, n = nm }
                  end
                  if match then matched = matched + 1 end
                end
              end
            end
          end
        end
      end
    end
  end
  if #cells > maxCells then
    return false, "非空气格太多（" .. #cells .. " ✗ 上限 " .. maxCells .. "）⇒ 缩小范围、调大 maxcells，或用 match= 筛选"
  end
  -- solid_n 要按**全部**非空气格算 ✓（cells 可能已被 match 过滤 ✓ 用 #cells 会误导 ✗）
  local solidTotal = 0
  for _, v in pairs(counts) do solidTotal = solidTotal + v end
  return true, {
    box = { x0 = x0, y0 = y0, z0 = z0, x1 = x1, y1 = y1, z1 = z1,
            nx = x1 - x0 + 1, ny = y1 - y0 + 1, nz = z1 - z0 + 1 },
    counts = counts, cells = cells,
    match = match, matched_n = matched,
    solid_n = solidTotal, air_n = airN, volume = vol,
  }
end

-- --- 蓝图大炮（放图那一半）：读蓝图 → 查缺料 → 飞过去逐块放 ----------------- --
-- 蓝图形状（子路径由网关 /files/blueprints/<名>.json 下发 ✓ 见 gateway §files）：
--   { "name":"x", "cells":[ {"dx":0,"dy":0,"dz":0,"block":"minecraft:oak_planks"}, … ] }
--
-- 与 Create 蓝图大炮逐条对照（这就是"仿照"的具体内容 ✓）：
--   * 炮要装一份蓝图 ✓ → 我们从网关**下载 JSON** ✓（`url=` ✓）
--   * 炮有**缺料清单** ✓ → 开工前先比对背包 ✓ 不够就**拒绝**并列出缺什么 ✓（不是硬试 ✗）
--   * 炮**跳过已经对的地方** ✓ → 每格先读回 ✓ 已经一致就跳过 ✓
--   * 炮会**沿着轨道飞** ✓ → 我们让假人 **tp 到可站的观察位** ✓（悬空平台上这就是唯一可行解 ✓）
--   * 炮**慢慢来、可中断** ✓ → `max=` 限制本次放几块 ✓ 再跑一次自动接着放 ✓（幂等 ✓）
--
-- ⚠ 观察位必须"脚下有支撑" ✓ 否则假人会直接坠入虚空 ✗（真实风险 ✓ 所以硬校验 ✓）
A.blueprint_build = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local plan = a.plan
  if type(plan) ~= "table" then
    local url = a.url
    if type(url) ~= "string" or url == "" then
      return false, "需要 url=<蓝图JSON地址>（或直接给 plan 表）"
    end
    local body, err = httpGet(url)
    if not body then return false, "下载蓝图失败：" .. tostring(err) end
    local okP, parsed = pcall(textutils.unserializeJSON, body)
    if not okP or type(parsed) ~= "table" then return false, "蓝图 JSON 解析失败（" .. tostring(parsed) .. "）" end
    plan = parsed
  end

  local ax = math.floor(tonumber(a.x) or 0)
  local ay = math.floor(tonumber(a.y) or 0)
  local az = math.floor(tonumber(a.z) or 0)
  local fly    = (a.fly ~= false)
  local maxPut = math.floor(tonumber(a.max) or 48)
  local t0     = os.clock()

  local targets = {}
  for _, c in ipairs(plan.cells or {}) do
    local blk = c.block or c.n
    if type(blk) == "string" and blk ~= "" then
      targets[#targets + 1] = {
        x = ax + (tonumber(c.dx) or 0),
        y = ay + (tonumber(c.dy) or 0),
        z = az + (tonumber(c.dz) or 0),
        block = blk,
      }
    end
  end
  if #targets == 0 then return false, "蓝图里没有 cells" end

  -- ① 缺料清单（开炮前先算账 ✓）
  local _, inv = A.bot_inv({ bot = bot })
  local have = {}
  for _, it in ipairs((inv and inv.items) or {}) do
    have[it.id] = (have[it.id] or 0) + (it.count or 1)
  end
  local need, already, missing = {}, 0, {}
  for _, t in ipairs(targets) do
    local now = readBlock(t.x, t.y, t.z)
    if now == t.block then
      already = already + 1
    else
      need[t.block] = (need[t.block] or 0) + 1
    end
  end
  for id, n in pairs(need) do
    local h = have[id] or 0
    if h < n then missing[#missing + 1] = { block = id, need = n, have = h } end
  end
  if #missing > 0 and a.force ~= true then
    return true, {
      ok = false, stage = "materials",
      already = already, need = need, missing = missing,
      hint = "先补齐缺料再开炮（或 force=true 硬跑，多半会中途失败 ✗）",
    }
  end

  -- ② 施工顺序：y 升序 ✓ 再按"离锚点水平距离" ✓ —— 像炮一样从锚点一圈圈长出去 ✓
  --    为什么不是随便排：每块都要"贴着已存在的方块放" ✓ 乱序会出现够不着的孤立块 ✗
  table.sort(targets, function(p, q)
    if p.y ~= q.y then return p.y < q.y end
    local dp = math.abs(p.x - ax) + math.abs(p.z - az)
    local dq = math.abs(q.x - ax) + math.abs(q.z - az)
    if dp ~= dq then return dp < dq end
    if p.x ~= q.x then return p.x < q.x end
    return p.z < q.z
  end)

  local function refFor(t)
    -- 六个邻居里挑一个**完整方块**当参照 ✓（与 build_platform 同一套判据 ✓）
    local faces = { { 0, -1, 0 }, { 0, 0, -1 }, { 0, 0, 1 }, { -1, 0, 0 }, { 1, 0, 0 }, { 0, 1, 0 } }
    for _, f in ipairs(faces) do
      local nx, ny, nz = t.x + f[1], t.y + f[2], t.z + f[3]
      if standable(readBlock(nx, ny, nz)) then return { nx, ny, nz } end
    end
    return nil
  end

  -- ★ 站位几何（这门炮最关键的一处 ✓ 结论是推出来的，然后实测印证 ✓）
  --   事实：**站在平台顶面时，同高度方块的侧面永远点不到** ✗ —— 这是几何上无解 ✗ 不是参数没调好 ✗：
  --     设脚下那块为 ref（顶面 y=Y+1），目标在它旁边、同一层 ✓
  --     眼睛在 Y+2.62 ✓ 想打中目标侧面（y∈[Y,Y+1]）就得在 x=X+1 处下降 ≤1.62 ✓
  --     可射线在到达 x=X+1 **之前**必然先穿过平面 y=Y+1 ✓（那正是脚下那块方块的顶面 ✓）
  --     ⇒ 落点永远是自己脚下那块方块的顶面 ✓
  --   真人的解法（MC-93117）：**潜行把身体探出边缘** ✓ 让眼睛越过那个面 ✓
  --   ⇒ 照做：tp 到 ref 顶上、**越过共享面 0.05 格** ✓ 再回看侧面 ✓
  --     此时约 55% 悬空、但与 ref 仍有重叠 ⇒ 服务端判定"站在地上" ✓ 不会掉 ✗
  local function sideShot(ref, t)
    local dx, dz = t.x - ref[1], t.z - ref[3]
    if math.abs(dx) + math.abs(dz) ~= 1 then return nil end    -- 只处理"左右相邻"这一种 ✓
    return { x = ref[1] + 0.5 + dx * 0.55, y = ref[2] + 1, z = ref[3] + 0.5 + dz * 0.55 }
  end

  -- 纵向情形（ref 在目标下方 ⇒ 点它的顶面 ✓）：不能站在 ref 上 ✗（那等于放进自己脚下 ✗）
  -- ⇒ 站到**旁边有支撑**的格子上 ✓（半径 1~2 搜 ✓ 虚空边缘时那块"岸上地形"往往就在 2 格外 ✓）
  local function standingSpot(t)
    for r = 1, 2 do
      local offs
      if r == 1 then
        offs = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }
      else
        offs = { { 2, 0 }, { -2, 0 }, { 0, 2 }, { 0, -2 }, { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 } }
      end
      for _, o in ipairs(offs) do
        for _, dy in ipairs({ 0, -1, 1 }) do
          local cx, cy, cz = t.x + o[1], t.y + dy, t.z + o[2]
          if blockIsAir(cx, cy, cz) and blockIsAir(cx, cy + 1, cz)
             and standable(readBlock(cx, cy - 1, cz)) then
            return { x = cx + 0.5, y = cy, z = cz + 0.5 }
          end
        end
      end
    end
    return nil
  end

  local placed, skipped, failed, outOfReach = 0, 0, {}, 0
  local tried = 0
  for _, t in ipairs(targets) do
    if tried >= maxPut then break end
    local now = readBlock(t.x, t.y, t.z)
    if now == t.block then
      skipped = skipped + 1
    else
      -- 参照优先级：① 左右邻居（点侧面 ✓ 平台外扩就是这种 ✓）② 下方（点顶面 ✓）③ 上方（点底面 ✓）
      local shot = nil
      for _, f in ipairs({ { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }) do
        local ref = { t.x + f[1], t.y, t.z + f[2] }
        if standable(readBlock(ref[1], ref[2], ref[3])) then
          local pos = sideShot(ref, t)
          if pos then shot = { ref = ref, pos = pos, kind = "side" } end
          break
        end
      end
      if not shot and standable(readBlock(t.x, t.y - 1, t.z)) then
        local pos = standingSpot(t)
        if pos then shot = { ref = { t.x, t.y - 1, t.z }, pos = pos, kind = "top" } end
      end
      if not shot and standable(readBlock(t.x, t.y + 1, t.z)) then
        local pos = standingSpot(t)
        if pos then shot = { ref = { t.x, t.y + 1, t.z }, pos = pos, kind = "bottom" } end
      end

      if not shot then
        outOfReach = outOfReach + 1
        failed[#failed + 1] = { x = t.x, y = t.y, z = t.z,
          why = "没有可用参照（四周既无完整方块，也没有脚下有支撑的观察位）" }
      else
        local key = t.block:match(":(.+)$") or t.block
        local okH, held = A.hold_item({ bot = bot, item = key })
        if not okH then
          failed[#failed + 1] = { x = t.x, y = t.y, z = t.z,
                                  why = "拿不到 " .. key .. "：" .. tostring(held) }
        else
          -- ★ "炮会飞" ✓：悬空平台上的观察位本身就在尚未长出来的格子上 ✓
          --   走过去要先造路 ✗ ⇒ 只能飞 ✓（与蓝图大炮沿轨道飞行同构 ✓）
          if fly then
            pcall(commands.exec,
              string.format("tp %s %.3f %.3f %.3f", bot, shot.pos.x, shot.pos.y, shot.pos.z))
            sleep(0.12)
          end
          -- 瞄准**共享面的中心** = 目标中心 + 0.5 ×（指向参照的方向）✓
          local ax = t.x + 0.5 + (shot.ref[1] - t.x) * 0.5
          local ay = t.y + 0.5 + (shot.ref[2] - t.y) * 0.5
          local az = t.z + 0.5 + (shot.ref[3] - t.z) * 0.5
          -- ★ 潜行再放 ✓（参照若是熔炉/箱子这类可交互方块 ✗ 普通右键会变成"开界面" ✗
          --   结果是什么也没放、指令回显却是成功的 ✗ —— 真实事故，见 docs/错题本.md L1 ✓）
          pcall(commands.exec, "player " .. bot .. " sneak")
          sleep(0.12)
          pcall(commands.exec,
            string.format("player %s look at %.3f %.3f %.3f", bot, ax, ay, az))
          sleep(0.12)
          pcall(commands.exec, "player " .. bot .. " use once")
          sleep(0.3)
          tried = tried + 1
          local after = readBlock(t.x, t.y, t.z)
          if after == t.block then
            placed = placed + 1
          else
            failed[#failed + 1] = { x = t.x, y = t.y, z = t.z, kind = shot.kind,
                                    why = "打偏/回读仍是 " .. tostring(after) }
          end
        end
      end
      if tried % 8 == 0 then jobNote("blueprint.progress", { tried = tried, placed = placed }) end
    end
  end

  -- 收尾：把剩余要放的格子数如实报出来 ✓（再跑一次即可接着干 ✓ 幂等 ✓）
  local left = 0
  for _, t in ipairs(targets) do
    if readBlock(t.x, t.y, t.z) ~= t.block then left = left + 1 end
  end
  return true, {
    ok = true, blueprint = plan.name or "(未命名)",
    anchor = { x = ax, y = ay, z = az },
    cells_n = #targets, already = already, skipped = skipped,
    placed = placed, remaining = left, out_of_reach = outOfReach,
    failed = failed, missing = missing,
    seconds = tonumber(string.format("%.1f", os.clock() - t0)),
  }
end

-- --- 寻路（仿 mineflayer-pathfinder + 车万女仆的分层退化）------------------- --
-- 参考与取舍（详见 docs/寻路-参考与设计.md ✓）：
--   * **mineflayer-pathfinder**：目标抽象（GoalBlock / GoalNear / GoalXZ）+ **代价模型**
--     （走平/上台阶/下落/跨沟/挖穿/搭桥各自计价 ✓）+ A* ✓ + `thinkTimeout` ✓
--     ⇒ 我们照搬它的**代价模型与目标抽象** ✓
--   * **车万女仆（Touhou Little Maid）**：用原版 `GroundPathNavigation` 做 A* ✓
--     但真正值得学的是**分层退化** ✓ —— 卡住/离得太远时**直接传送回主人身边** ✓
--     ⇒ 我们照搬它的**兜底策略**：走 → 挖/搭 → 都不行才"回传" ✓ 且**如实报告** ✓
--
-- ⚠ 与 `A.walk_to` 的关系：walk_to 是**反应式直线走** ✗（朝目标看、move forward ✓
--   带防坠崖守卫 ✓）——遇到 U 形障碍必卡在局部极值 ✗ 那正是它做不到的部分 ✓
--   新动作负责"**先想清楚再走**" ✓；walk_to 保留作短距离/最后一段 ✓
--
-- 性能设计（CC 的 Lua 很慢 ✗ 必须这么设计）：
--   ① **批量读一次**（getBlockInfos 按 4³ ✓ 顺序 y→z→x ✓）⇒ 地图进内存 ✓
--      搜索全程**不再发任何指令** ✓（逐格 readBlock 会慢到不可用 ✗）
--   ② 手写二叉堆 ✓ 节点上限 + 时间上限 ✓（搜不动就如实报"没找到路" ✗ 别假装 ✗）

-- 站在哪、能不能穿（v1 判据 ✓ 这一版是"**默认实心 + 例外表**" ✓ 不是白名单 ✗）：
--   ⚠ 真实教训：一开始用 `standable()`（一张"完整方块"白名单 ✗）当判据 ✓
--     结果 309 个模组的方块（土径 dirt_path ✓ 耕地 farmland ✓ 各种模组地板…）**全不在名单里** ✗
--     ⇒ 假人周围全被判成"站不住" ✗ ⇒ A* 只扩了 37 个节点就枯死 ✗
--     现象是 `found:false` ✓ 看起来像"没路" ✗ 其实是"判据把世界判没了" ✗ —— 必记文档 ✓
--   ⇒ 改成**默认实心**：只有"明确的非实体方块"才可穿 ✓（空气/草花/作物/火把… ✓）
local PATH_NOT_SOLID = {
  ["air"] = true, ["cave_air"] = true, ["void_air"] = true,
  ["short_grass"] = true, ["grass"] = true, ["tall_grass"] = true, ["fern"] = true, ["large_fern"] = true,
  ["dandelion"] = true, ["poppy"] = true, ["red_tulip"] = true, ["orange_tulip"] = true,
  ["white_tulip"] = true, ["pink_tulip"] = true, ["oxeye_daisy"] = true, ["cornflower"] = true,
  ["azure_bluet"] = true, ["allium"] = true, ["blue_orchid"] = true, ["lily_of_the_valley"] = true,
  ["wheat"] = true, ["carrots"] = true, ["potatoes"] = true, ["beetroots"] = true, ["pumpkin_stem"] = true,
  ["melon_stem"] = true, ["attached_pumpkin_stem"] = true, ["attached_melon_stem"] = true,
  ["torch"] = true, ["wall_torch"] = true, ["soul_torch"] = true, ["redstone_torch"] = true,
  ["rail"] = true, ["powered_rail"] = true, ["detector_rail"] = true, ["activator_rail"] = true,
  ["redstone_wire"] = true, ["tripwire"] = true, ["tripwire_hook"] = true, ["string"] = true,
  ["stone_pressure_plate"] = true, ["oak_pressure_plate"] = true, ["light_weighted_pressure_plate"] = true,
  ["heavy_weighted_pressure_plate"] = true, ["lever"] = true,
  ["sugar_cane"] = true, ["lily_pad"] = true, ["vine"] = true, ["glow_lichen"] = true,
  ["snow"] = true, ["carpet"] = true, ["moss_carpet"] = true,
  ["sapling"] = true, ["oak_sapling"] = true, ["flowering_azalea"] = true, ["azalea"] = true,
  ["dead_bush"] = true, ["seagrass"] = true, ["kelp"] = true, ["kelp_plant"] = true,
  ["structure_void"] = true, ["light"] = true,
}
local PATH_HAZARD = {
  ["minecraft:lava"] = true, ["minecraft:fire"] = true, ["minecraft:soul_fire"] = true,
  ["minecraft:cactus"] = true, ["minecraft:magma_block"] = true, ["minecraft:powder_snow"] = true,
  ["minecraft:sweet_berry_bush"] = true, ["minecraft:water"] = true,
}

local function pathKey(x, y, z) return x .. "," .. y .. "," .. z end

-- 这个方块"实心"吗（默认实心 ✓ 例外表里的才可穿 ✓）
local function pathSolid(nm)
  if type(nm) ~= "string" then return true end
  local short = nm:match(":(.+)$") or nm
  if PATH_NOT_SOLID[short] == true or PATH_NOT_SOLID[nm] == true then return false end
  return true
end

-- "可穿"就是"非实心" ✓——用 __index 元表让原有写法 `PATH_PASSABLE[x] == true` 一行不改 ✓
-- （少改一处就少一个手滑 ✗ 这是本轮唯一"省下来"的复杂度 ✓）
local PATH_PASSABLE = setmetatable({}, {
  __index = function(_, k) return not pathSolid(k) end,
})

-- 批量把一片区域读进内存 ✓（顺序已由 probe_order 穷举确认为 y→z→x ✓）
local function pathScan(x0, y0, z0, x1, y1, z1, deadline)
  local map, n, chunks = {}, 0, 0
  for cy = y0, y1, 4 do
    for cz = z0, z1, 4 do
      for cx = x0, x1, 4 do
        local ex = math.min(cx + 3, x1)
        local ey = math.min(cy + 3, y1)
        local ez = math.min(cz + 3, z1)
        -- ★ 扫描预算（2026-09-20 ✓ 真修 ✓）：
        --   实测（13:27:18）6851 格 / 120 块 ⇒ **8.05 秒** ✓ 而**搜索只有 0 秒** ✓
        --   ⇒ 规划的开销**全在扫描**（约 67ms/块 ✓ getBlockInfos 一次 4³ ✓）
        --   而原来的 `timeout` **只管搜索** ✗（计时 `ts` 是扫描**之后**才起的 ✗）
        --   ⇒ 调用方以为"超时 8 秒"✓ 实际可能先扫 30 秒 ✗ —— 这是**预算的谎** ✗
        --   ⇒ 现在扫描自己也有 deadline ✓ 超了如实报 ✗ 不硬撑 ✓
        chunks = chunks + 1
        if deadline and os.clock() > deadline then
          return nil, "扫描超时 ⏱（已读 " .. n .. " 格 / " .. chunks .. " 块）⇒ 缩小 radius ✓ 或分段走 ✓"
        end
        if chunks % 60 == 0 then jobNote("path_plan.scan_chunk", { chunks = chunks, cells = n }) end
        local p = packReturns(pcall(commands.getBlockInfos, cx, cy, cz, ex, ey, ez))
        if not p[1] or type(p[2]) ~= "table" then
          return nil, "getBlockInfos 失败（" .. cx .. "," .. cy .. "," .. cz .. "）：" .. tostring(p[2])
        end
        local i = 0
        for y = cy, ey do
          for z = cz, ez do
            for x = cx, ex do
              i = i + 1
              local e = p[2][i]
              map[pathKey(x, y, z)] = (type(e) == "table" and (e.name or e.block)) or "minecraft:air"
              n = n + 1
            end
          end
        end
      end
    end
  end
  return map, nil, n
end

local function pathBlock(map, x, y, z)
  return map[pathKey(x, y, z)] or "minecraft:air"
end

-- 能站稳吗：脚下是实心方块 ✓ 自己与头部可穿 ✓ 且不是危险方块 ✓
local function pathCanStand(map, x, y, z)
  local below = pathBlock(map, x, y - 1, z)
  if not pathSolid(below) then return false end          -- ★ 判据用 pathSolid ✓ 不是 standable ✗
  if PATH_HAZARD[below] then return false end
  local here, head = pathBlock(map, x, y, z), pathBlock(map, x, y + 1, z)
  if PATH_HAZARD[here] or PATH_HAZARD[head] then return false end
  return (PATH_PASSABLE[here] == true) and (PATH_PASSABLE[head] == true)
end

-- 极简二叉堆 ✓（按 f 值 ✓）
local function heapPush(h, node)
  h[#h + 1] = node
  local i = #h
  while i > 1 do
    local p = math.floor(i / 2)
    if h[p].f <= h[i].f then break end
    h[p], h[i] = h[i], h[p]
    i = p
  end
end

local function heapPop(h)
  local top = h[1]
  h[1] = h[#h]
  h[#h] = nil
  local i, n = 1, #h
  while true do
    local l, r, m = i * 2, i * 2 + 1, i
    if l <= n and h[l].f < h[m].f then m = l end
    if r <= n and h[r].f < h[m].f then m = r end
    if m == i then break end
    h[m], h[i] = h[i], h[m]
    i = m
  end
  return top
end

-- A*：节点 = "能站的格子" ✓ 边 = 移动基元（走平/上台阶/下落/挖穿/搭桥 ✓）
A.path_plan = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local tx, ty, tz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (tx and tz) then return false, "需要 x / z（y 可省，省了就自动找落脚点）" end
  local pad       = math.floor(tonumber(a.radius) or 6)      -- 包围盒半径 ✓
  local maxDrop   = math.floor(tonumber(a.max_drop) or 3)    -- 最多下落几格 ✓
  local canDig    = (a.dig == true)                          -- 挖穿（默认关 ✓ 保守）
  local canPlace  = (a.place == true)                        -- 搭桥（默认关 ✓）
  local maxNodes  = math.floor(tonumber(a.max_nodes) or 3000)
  local maxTime   = tonumber(a.timeout) or 12
  -- ★ 扫描预算（2026-09-20 ✓ 新增 ✓）：默认与搜索预算同量级 ✓
  --   为什么要单独一个旋钮 ✗：扫描按**格数**走 ✓ 与搜索的节点数**毫无关系** ✗
  --   实测（13:27 与 13:30 两次）：扫描 2730 格 = 3.25s ✓ 6851 格 = 8.05s ✓
  --   而两次的搜索都是 **0 秒**（visited 6 / 49 ✓）⇒ 唯一的开销就是它 ✓
  local scanTime  = tonumber(a.scan_timeout) or maxTime
  local maxScan   = math.floor(tonumber(a.max_scan) or 24000)
  -- ★ 精确模式 = **GoalBlock 语义** ✓（2026-09-20 新增 ✓ 真实需求逼出来的 ✓）
  --   为什么需要它 ✗：GoalNear（±1 格）在"相邻但不同层"时会**误判已到达** ✗
  --   实测（14:5x ✓ 两次）：
  --     人要站 (4128,71,12) ✓ 而实际停在 **(4127,70,12)** ✗
  --       ⇒ |4127-4128| = 1 ✓ |70-71| = 1 ✓ ⇒ **规划器自己判"已经到了"** ✗
  --       ⇒ `steps: 1, cost: 0, waypoints: 0` ✓ 一步不走 ✗ 而外部以为成功了 ✗
  --   这类需求很常见 ✓：**"站到那一格才能打到顶面"**（筛矿就是 ✗ 见 P16 ✓）、
  --     "站到那一格才能放下方块"✓、"站到那一格才够得着容器"✓
  --   ⇒ 所以保留 GoalNear（默认 ✓ 松 ✓ 好用 ✓）**并新增** `exact=true`（钉死那一格 ✓）
  local exact     = (a.exact == true)
  local t0        = os.clock()

  local sx, sy, sz = botPos(bot)
  if not sx then return false, "读不到假人坐标" end
  sy = math.floor(sy + 0.05)                                 -- 脚所在格 ✓（见 walk_to 的层级注释 ✓）

  local x0 = math.max(math.floor(math.min(sx, tx)) - pad, -30000000)
  local x1 = math.floor(math.max(sx, tx)) + pad
  local z0 = math.max(math.floor(math.min(sz, tz)) - pad, -30000000)
  local z1 = math.floor(math.max(sz, tz)) + pad
  local y0 = math.max(sy - 5, -64)
  local y1 = math.min(sy + 7, 320)

  -- ★ 先算扫描量 ✓ 太大就直接拒绝 ✗（真实教训：默认半径 20 时扫了 66822 格 ⏱ 62 秒 ✓
  --   而"时间上限"当时是从**函数入口**算的 ✗ ⇒ 搜索还没开始就已经超时 ✗
  --   现象是 `visited: 0` ✓ 看起来像"没路" ✗ 其实是"根本没搜" ✗ —— 极难误中 ✓ 记文档 ✓）
  local scanVol = (x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1)
  if scanVol > maxScan then
    return false, "要扫的格子太多（" .. scanVol .. " > " .. maxScan ..
      "）⇒ 缩小 radius 或把目标拆成几段走 ✓（批量读很贵 ⏱ 一次约 60ms/64格 ✓）"
  end

  local map, err, cells = pathScan(x0, y0, z0, x1, y1, z1, t0 + scanTime)
  if not map then
    jobNote("path_plan.scan_fail", { err = tostring(err) })
    return false, err
  end
  local ts = os.clock()        -- ★ 搜索计时**从扫描之后**开始 ✓（否则必然误判超时 ✗）
  -- ★ 诊断打点（2026-09-20 ✓ 临时 ✓）：扫描 vs 搜索的分水岭 ✓
  jobNote("path_plan.scan_done", { cells = cells, chunks = math.ceil(cells / 64),
                                   scan_s = tonumber(string.format("%.2f", ts - t0)),
                                   box = { x0, y0, z0, x1, y1, z1 } })

  local function h(x, y, z)
    local dx, dz = math.abs(x - tx), math.abs(z - tz)
    return math.max(dx, dz) + 0.4 * math.min(dx, dz) + math.abs(y - (ty or sy))
  end

  local startKey = pathKey(math.floor(sx), sy, math.floor(sz))
  local open, seen = {}, {}
  local start = { x = math.floor(sx), y = sy, z = math.floor(sz), g = 0, f = h(math.floor(sx), sy, math.floor(sz)) }
  heapPush(open, start)
  seen[startKey] = start
  local best, visited = nil, 0

  -- 8 个水平方向（斜向要两侧都通 ✓ 与 mineflayer 同规矩 ✓）
  local dirs = {
    { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 },
    { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 },
  }

  while #open > 0 do
    if visited >= maxNodes or (os.clock() - ts) > maxTime then break end
    local cur = heapPop(open)
    visited = visited + 1
    -- 到达判据：水平够近 ✓ 且 y 相差 ≤1 ✓（像 GoalNear ✓）
    -- ⚠ `exact=true` 时改成 **GoalBlock 语义**（那一格就是那一格 ✓ 见上面的注释 ✓）
    local arrived
    if exact then
      arrived = (cur.x == tx) and (cur.z == tz) and ((not ty) or (cur.y == ty))
    else
      arrived = math.abs(cur.x - tx) <= 1 and math.abs(cur.z - tz) <= 1
                and ((not ty) or math.abs(cur.y - ty) <= 1)
    end
    if arrived then
      best = cur
      break
    end
    for _, d in ipairs(dirs) do
      local diag = (d[1] ~= 0 and d[2] ~= 0)
      local diagBlocked = false
      local nx, nz = cur.x + d[1], cur.z + d[2]
      -- 斜向的两条正交边也要能穿 ✓ 否则会"卡在墙角"✗
      if diag then
        local s1 = pathBlock(map, cur.x + d[1], cur.y, cur.z)
        local s2 = pathBlock(map, cur.x, cur.y, cur.z + d[2])
        local s1h = pathBlock(map, cur.x + d[1], cur.y + 1, cur.z)
        local s2h = pathBlock(map, cur.x, cur.y + 1, cur.z + d[2])
        if not (PATH_PASSABLE[s1] and PATH_PASSABLE[s1h] and PATH_PASSABLE[s2] and PATH_PASSABLE[s2h]) then
          -- ⚠ 这里**不能用 goto** ✗：CC 的 Cobalt 是 Lua 5.1 语义 ✓ 没有 goto ✓
          --   （顺手写 5.2+ 的 goto ⇒ 一上机就是语法错误 ✗ 这条记在文档里 ✓）
          --   改用"空区间"天然跳过 ✓：下面把 dy 的循环范围置空即可 ✓
          diagBlocked = true
        end
      end
      local dyFrom, dyTo = -maxDrop, 2
      if diagBlocked then dyFrom, dyTo = 1, 0 end
      for dy = dyFrom, dyTo do
        local ny = cur.y + dy
        if ny >= y0 and ny <= y1 then
          local cost = nil
          if dy == 0 then
            if pathCanStand(map, nx, ny, nz) then cost = diag and 1.41 or 1.0 end
          elseif dy == 1 then                        -- 上台阶 ✓
            if pathCanStand(map, nx, ny, nz) and PATH_PASSABLE[pathBlock(map, cur.x, cur.y + 2, cur.z)] then
              cost = diag and 1.9 or 1.5
            end
          elseif dy == 2 then                        -- 跳两格 ✓（代价更高 ✓）
            if pathCanStand(map, nx, ny, nz) and pathCanStand(map, cur.x, cur.y + 1, cur.z)
               and PATH_PASSABLE[pathBlock(map, nx, ny - 1, nz)] then
              cost = 2.6
            end
          else                                       -- 下落 ✓（每格加一点代价 ✓）
            if pathCanStand(map, nx, ny, nz) then cost = 1.0 + 0.3 * (-dy) end
          end
          -- 挖穿：目标格被挡但可以挖开 ✓（v1 只判"不是危险方块"✗ 硬度留给执行时 ✓）
          if not cost and canDig then
            local blocker = pathBlock(map, nx, cur.y, nz)
            local blockerHead = pathBlock(map, nx, cur.y + 1, nz)
            if PATH_PASSABLE[blocker] ~= true or PATH_PASSABLE[blockerHead] ~= true then
              if not PATH_HAZARD[blocker] and not PATH_HAZARD[blockerHead]
                 and not standable(pathBlock(map, nx, cur.y - 1, nz)) then
                cost = 1.6 + (diag and 0.4 or 0)
              end
            end
          end
          -- 搭桥：目标下方是空的 ⇒ 需要放一块 ✓
          if not cost and canPlace then
            if PATH_PASSABLE[pathBlock(map, nx, cur.y, nz)] and PATH_PASSABLE[pathBlock(map, nx, cur.y + 1, nz)]
               and not standable(pathBlock(map, nx, cur.y - 1, nz))
               and not PATH_HAZARD[pathBlock(map, nx, cur.y - 1, nz)] then
              cost = 2.2
            end
          end
          if cost then
            local nk = pathKey(nx, ny, nz)
            local g = cur.g + cost
            local node = seen[nk]
            if not node then
              node = { x = nx, y = ny, z = nz, g = g, f = g + h(nx, ny, nz), parent = cur }
              seen[nk] = node
              heapPush(open, node)
            elseif g < node.g - 0.001 then
              node.g, node.f, node.parent = g, g + h(nx, ny, nz), cur
              heapPush(open, node)
            end
          end
        end
      end
    end
  end

  -- ★ 诊断打点（2026-09-20 ✓ 临时 ✓）：搜了多久、访问了多少节点 ✓
  jobNote("path_plan.search_done", { visited = visited, found = (best ~= nil),
                                     search_s = tonumber(string.format("%.2f", os.clock() - ts)) })

  if not best then
    return true, { found = false, start = { x = sx, y = sy, z = sz },
                   goal = { x = tx, y = ty, z = tz }, visited = visited,
                   scanned = cells, seconds = tonumber(string.format("%.2f", os.clock() - t0)),
                   hint = "没找到路 ✗（可试 dig=true / place=true，或放宽 max_drop ✓）" }
  end
  local path, n = {}, best
  while n do path[#path + 1] = { x = n.x, y = n.y, z = n.z }; n = n.parent end
  -- 反转成"起点在前" ✓
  for i = 1, math.floor(#path / 2) do path[i], path[#path - i + 1] = path[#path - i + 1], path[i] end
  return true, {
    found = true, start = { x = sx, y = sy, z = sz }, goal = { x = tx, y = ty, z = tz },
    cost = tonumber(string.format("%.2f", best.g)), steps = #path,
    visited = visited, scanned = cells,
    seconds = tonumber(string.format("%.2f", os.clock() - t0)),
    path = path,
  }
end

-- --- 沿路走（执行器）：逐格走过去 ✓ 卡住就重规划 ✓ 最后才允许"回传" ✓ ---------- --
A.path_follow = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a    = args or {}
  local bot  = a.bot or "Bot"
  local tx, ty, tz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (tx and tz) then return false, "需要 x / z" end
  local maxTime  = tonumber(a.timeout) or 120
  local allowTp  = (a.warp ~= false)                 -- 兜底"回传"（车万女仆那一手 ✓）
  local replans  = math.floor(tonumber(a.replans) or 2)
  local t0       = os.clock()
  local warped, replanCount, waypoints = false, 0, 0
  local trace = {}

  -- ★ 硬看门狗 + 阶段标记（真实教训 ✓ 必读）
  --   事故：执行器曾经"调用 90 秒不返回、假人一步没动" ✗
  --   事后完全不知道它卡在哪一段 ✗ —— 这比"做错"更难查 ✗
  --   ⇒ 两道保险：① 每段更新 `stage` ✓ ② **硬超时一定返回** ✓ 并把 stage 带回去 ✓
  --   纪律（与 dig_at / step_to 同源 ✓）：**任何动作都不许"无声地不回话"** ✗
  local stage = "init"
  local hardDeadline = t0 + maxTime + 20

  -- ★ 走路前**必须解除潜行** ✓（真实事故，差点又归因错 ✗）
  --   前面摆方块时为了"不对着熔炉开界面"给假人按了 sneak ✓ 之后再没松开 ✗
  --   潜行状态会拖慢/卡住 `move forward` ✗ ⇒ 现象是"规划成功、但一步没动" ✗
  --   判别方法 ✓：手动 `unsneak` + `look` + `move forward` 两秒 ⇒ 位置真的变了 ✓
  --   ⇒ 说明**基元是好的 ✗ 是执行器漏了这一步** ✓ —— 先动手试一次，比反复读代码快 ✓
  pcall(commands.exec, "player " .. bot .. " unsneak")

  local function arrive()
    pcall(commands.execAsync, "player " .. bot .. " stop")
    local cx, cy, cz = botPos(bot)
    return cx, cy, cz
  end

  local function report(extra)
    extra = extra or {}
    extra.stage = stage
    extra.waypoints = waypoints
    extra.replans = replanCount
    extra.warped = warped
    extra.seconds = tonumber(string.format("%.2f", os.clock() - t0))
    extra.trace = trace
    return extra
  end

  for attempt = 1, replans + 1 do
    if os.clock() > hardDeadline then
      arrive()
      return true, report({ reached = false, why = "硬超时（整段超限 ⏱）" })
    end
    stage = "plan(" .. attempt .. ")"
    -- ⚠ 给规划**明确的小超时** ✓ 否则它可能在 CC 的慢 Lua 上跑很久 ✗
    -- ══════════════════════════════════════════════════════════════════════════
    -- ★★ 2026-09-20 真根因（实测 ✓ 铁证 ✓）：**多返回值被截断** ✗★
    --
    --   原来是这一句 ✗：
    --       local plan = A.path_plan({ ... })
    --       local okP, res = plan
    --   ⇒ `A.path_plan` 返回的是 **两个值** `true, {found=…}` ✓
    --     而 `local plan = f()` 只接**第一个** ✗ ⇒ plan = `true`（布尔 ✓）
    --   ⇒ 下一句 okP = true ✓ res = **nil** ✗
    --   ⇒ 于是必然走到 `return false, "规划失败：nil"` ✗ —— **一次都没走成** ✓
    --
    --   实测铁证（13:30:46 ✓ 两条时间线对得上 ✓）：
    --     act.py 侧：4.2 秒返回 `{"ok": false, "result": "规划失败：nil"}` ✓
    --     job.log 侧：`path_plan.scan_done {scan_s:3.25}` ✓
    --                 `path_plan.search_done {found:true, visited:6}` ✓
    --     ⇒ **规划成功了** ✓ 是执行器把结果**扔了** ✗（不是规划失败 ✗）
    --
    --   教训（与错题本 B1「pcall 吞掉多余返回值」**同源** ✗）：
    --     ① Lua 里**返回值的个数与形状**必须逐个数清 ✗ 别凭"看起来像" ✗
    --     ② 现场症状会**指向完全错误的方向** ✗：
    --        "规划失败：nil" 会让人去查规划器 ✗ 而规划器是好的 ✓
    --     ③ 反过来说 ✓：**先看 job.log 再读代码** ✓ 一眼就分清了 ✓（这就是本轮的做法 ✓）
    --
    --   ⚠ 顺带纠正一条更早的误判 ✗：交接文档里写的"调用后 **90 秒**不返回"✗ ——
    --     那个 90 秒是 **Python 侧** `tools/act.py` 的 `ch.wait(timeout=90.0)` ✓（见该文件第 99 行 ✓）
    --     它只说明"**客户端等不到回传**"✗ **不等于**"机器卡了 90 秒"✗
    --     （真实现场是：4.2 秒就回了 ✗ 只是内容是一句错的 "规划失败：nil" ✗）
    -- ══════════════════════════════════════════════════════════════════════════
    jobNote("path_follow.plan_begin", { attempt = attempt, to = { tx, ty, tz },
                                        radius = a.radius, dig = a.dig, place = a.place })
    local okP, res = A.path_plan({
      bot = bot, x = tx, y = ty, z = tz,
      dig = a.dig, place = a.place, max_drop = a.max_drop, radius = a.radius,
      timeout = tonumber(a.plan_timeout) or 8,
      -- ★ 扫描也要有预算 ✓（见 pathScan 的注释 ✓）——不设它，"超时"就是一句谎 ✗
      scan_timeout = tonumber(a.scan_timeout) or (tonumber(a.plan_timeout) or 8),
      -- ★ 精确模式要**透传** ✓ 否则"规划按 ±1 判到达、收尾按精确判" ⇒ 永远不一致 ✗
      exact = a.exact,
    })
    jobNote("path_follow.plan_done", { attempt = attempt, pcall_ok = okP, res_type = type(res),
      found = (type(res) == "table") and res.found or nil,
      steps = (type(res) == "table") and res.steps or nil,
      visited = (type(res) == "table") and res.visited or nil,
      err = (not okP) and tostring(res) or nil })
    if not okP or type(res) ~= "table" then
      return false, "规划失败：" .. tostring(res)
    end
    if not res.found then
      if attempt > replans then
        -- 走不通 ⇒ 学车万女仆：**回传**（但要如实报 ✓ 不能假装走过去了 ✗）
        if allowTp then
          pcall(commands.exec, string.format("tp %s %.2f %d.00 %.2f", bot, tx + 0.5, ty or 71, tz + 0.5))
          sleep(0.4)
          warped = true
          local cx, cy, cz = arrive()
          return true, { reached = true, warped = true, at = { x = cx, y = cy, z = cz },
                         note = "没找到路 ⇒ 按兜底策略回传 ✓（**不是走过去的** ✗ 如实记录）",
                         seconds = tonumber(string.format("%.2f", os.clock() - t0)) }
        end
        return true, { reached = false, why = "没找到路且不允许回传 ✗", plan = res }
      end
      replanCount = replanCount + 1
    else
      local path = res.path or {}
      -- 起点那格跳过 ✓ 从第 2 格开始走 ✓
      local i = 2
      local lastProgress = os.clock()
      -- ★ 打点（2026-09-20 ✓ 按错题本 O2 的方案 ✓）：走路这段也要在磁盘上留痕 ✓
      --   为什么必须 ✗：Path_follow 最容易"静默地什么都不做"✗ ——
      --   一旦回传丢了 ✓ 外部完全分不清"在走"与"卡死"✗（D2/G6 都吃过这个亏 ✓）
      jobNote("path_follow.walk_begin", { attempt = attempt, steps = #path, cost = res.cost,
                                          from = res.start, to = res.goal })
      while i <= #path do
        if (os.clock() - t0) > maxTime then
          arrive()
          jobNote("path_follow.walk_timeout", { waypoints = waypoints, at_wp = i, total = #path })
          return true, { reached = false, why = "总时长超限 ⏱", at = select(1, botPos(bot)),
                         waypoints = waypoints, warped = warped }
        end
        local wp = path[i]
        local cx, cy, cz = botPos(bot)
        if not cx then break end
        local dx, dz = (wp.x + 0.5) - cx, (wp.z + 0.5) - cz
        local horiz = math.sqrt(dx * dx + dz * dz)
        if horiz < 0.45 and math.abs(cy - wp.y) < 1.1 then
          i = i + 1
          waypoints = waypoints + 1
          lastProgress = os.clock()
        else
          -- ★ 走一格交给**自证**的原子动作 ✓（它自己判定"位置真的变了" ✓）
          --   原先这里是"发指令 + 祈祷" ✗ ⇒ 现象就是"规划成功、人一步没动" ✗
          --   教训与 dig_at 同源 ✓：**每个动作都要能自己判定成败** ✓
          local okS, st = A.step_to({ bot = bot, x = wp.x, y = wp.y, z = wp.z, timeout = 5 })
          if okS and type(st) == "table" then
            if st.moved then
              waypoints = waypoints + 1
              lastProgress = os.clock()
              if st.after and math.abs(st.after.x - (wp.x + 0.5)) < 1.6
                 and math.abs(st.after.z - (wp.z + 0.5)) < 1.6
                 and math.abs(st.after.y - wp.y) < 1.6 then
                i = i + 1
              end
            else
              trace[#trace + 1] = { stuck_at = st.after, wp = wp, why = st.why }
              jobNote("path_follow.stuck", { at = st.after, wp = wp, why = tostring(st.why),
                                             waypoints = waypoints, at_wp = i, total = #path })
              break
            end
          else
            trace[#trace + 1] = { stuck_at = { x = cx, y = cy, z = cz }, wp = wp, why = tostring(st) }
            jobNote("path_follow.step_err", { at = { x = cx, y = cy, z = cz }, wp = wp,
                                              err = tostring(st) })
            break
          end
        end
      end
      if i > #path then
        arrive()
        local cx, cy, cz = botPos(bot)
        -- ★ 到达判据必须**自己再核一遍** ✗（2026-09-20 补 ✓ 实测抓到的 ✓）
        --   为什么 ✗：原来 `reached` **只由"路径计数器走完了"推出来** ✗
        --     而逐格推进用的是 `step_to` 的**宽松**验收（1.6 格 ✓）
        --   ⇒ 两者一旦不一致，就会**报成功但人没到** ✗（本项目最忌讳的一类 ✗）
        --   ⚠ 我第一版修得**过严** ✗（真实教训 ✓ 当场被实验打回 ✗）：
        --     我写成"到目标格**中心**的浮点距离 ≤1"✗
        --     而规划器用的是 **GoalNear 语义**：**取整后的格子**水平差 ≤1 ✓（见文档 §1 ✓）
        --     ⇒ 人站在 (4121.77) 时：规划器说"已经到了"✓ 我的检查说"差 1.27 格"✗
        --       于是**明明到了却一直重规划** ✗（job.log 里连报两次 not_arrived ✓）
        --   ⇒ 正确姿势 ✓：**判据与规划器保持一致**（取整格 ≤1 ✓ y 差 ≤1 ✓）✓
        --     但**必须是对"真实坐标"取值** ✗ 不是对循环计数器取值 ✗ ——这才是修的东西 ✓
        local fx  = cx and math.floor(cx) or 99999
        local fz  = cz and math.floor(cz) or 99999
        local dh  = math.max(math.abs(fx - tx), math.abs(fz - tz))       -- GoalNear：格差 ✓
        local dyv = (cy and ty) and math.abs(cy - ty) or 0
        -- ★ 收尾判据必须**与规划器同口径** ✗（真实教训 P10 ✓）
        --   `exact=true` ⇒ 容差 0 ✓（格差 0 且同层 ✓）；否则 GoalNear 容差 1 ✓
        local tol = (a.exact == true) and 0 or 1
        if dh > tol or dyv > tol then
          trace[#trace + 1] = { not_arrived = { x = cx, y = cy, z = cz },
                                want = { x = tx, y = ty, z = tz }, cells_off = dh }
          jobNote("path_follow.not_arrived", { at = { x = cx, y = cy, z = cz }, want = { tx, ty, tz },
                                               cells_off = dh, dy = dyv,
                                               waypoints = waypoints, total = #path })
          if replanCount + 1 <= replans and (os.clock() - t0) + 3 < maxTime then
            replanCount = replanCount + 1          -- 还有预算 ⇒ 重规划，再来一轮 ✓
          else
            return true, { reached = false,
                           why = string.format("路径走完了，但离目标还差 %d 格 ✗（如实报 ✓ 不假装到了 ✗）", dh),
                           at = { x = cx, y = cy, z = cz }, waypoints = waypoints,
                           warped = warped, trace = trace }
          end
        else
          jobNote("path_follow.walk_done", { waypoints = waypoints, total = #path,
                                             at = { x = cx, y = cy, z = cz } })
          return true, { reached = true, warped = warped, waypoints = waypoints, replans = replanCount,
                         at = { x = cx, y = cy, z = cz }, cost = res.cost,
                         seconds = tonumber(string.format("%.2f", os.clock() - t0)), trace = trace }
        end
      end
      replanCount = replanCount + 1
      jobNote("path_follow.replan", { attempt = attempt, waypoints = waypoints, at_wp = i, total = #path })
      -- ★ 重规划前先看预算 ✓：每次重规划都要**再扫一遍地图** ✗（实测约 3~8 秒 ✓）
      --   不看预算就重规划 ⇒ 总时长会超出调用方给的上限 ✗（"超时"又成了一句谎 ✗）
      if (os.clock() - t0) + 2 > maxTime then
        arrive()
        jobNote("path_follow.budget_stop", { waypoints = waypoints, at_wp = i, total = #path })
        return true, { reached = false, why = "预算不够再重规划一次 ⏱（已走 " .. waypoints .. " 格）",
                       at = select(1, botPos(bot)), waypoints = waypoints, warped = warped }
      end
    end
  end
  arrive()
  local cx, cy, cz = botPos(bot)
  return true, { reached = false, why = "重规划次数用尽 ✗", at = { x = cx, y = cy, z = cz },
                 waypoints = waypoints, replans = replanCount, trace = trace }
end

-- --- 走一格（寻路执行器的**原子操作** ✓ 自带成败判定）------------------------ --
-- 为什么要单独做成一个动作（真实教训 ✓）：
--   一开始我让执行器"发一条 move forward 然后祈祷" ✗ ⇒ 现象是**规划成功、人一步没动** ✗
--   而这正是 `dig_at` 早就解决过的问题 ✓：**每个动作都要能自己判定成败** ✓
--   ⇒ 走路也一样：下指令 → 轮询位置 → **位置真的变了才算成功** ✓ 否则如实报失败 ✗
--
-- 踩过的三个细节（都写在这里免得再犯 ✓）：
--   1) 走之前必须 `unsneak` ✓（摆方块时按下的潜行会拖慢/卡住移动 ✓）
--   2) 每轮都要**重新** look + move ✓（与 walk_to 同一手法 ✓
--      —— 只发一次时它只会挪一点点就停 ✗）
--   3) 防坠崖 ✓：y 掉超过 1.2 立刻停手 ✓（天空岛铁律 ✓）
A.step_to = function(args)
  if not hasCommandsAPI() then return false, "需要指令电脑" end
  local a   = args or {}
  local bot = a.bot or "Bot"
  local tx, ty, tz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  if not (tx and ty and tz) then return false, "需要 x/y/z（目标格）" end
  local timeout = tonumber(a.timeout) or 6
  local reach   = tonumber(a.reach) or 0.6
  local t0 = os.clock()

  pcall(commands.exec, "player " .. bot .. " unsneak")
  local bx, by, bz = botPos(bot)
  if not bx then return false, "读不到假人坐标" end
  local before = { x = bx, y = by, z = bz }

  pcall(commands.execAsync, "player " .. bot .. " move forward")
  while (os.clock() - t0) < timeout do
    local cx, cy, cz = botPos(bot)
    if not cx then break end
    local dx, dz = (tx + 0.5) - cx, (tz + 0.5) - cz
    local horiz = math.sqrt(dx * dx + dz * dz)
    if horiz <= reach and math.abs(cy - ty) < 1.2 then
      pcall(commands.execAsync, "player " .. bot .. " stop")
      return true, { moved = true, before = before, after = { x = cx, y = cy, z = cz },
                     target = { x = tx, y = ty, z = tz },
                     seconds = tonumber(string.format("%.2f", os.clock() - t0)) }
    end
    if cy < by - 1.2 then
      pcall(commands.execAsync, "player " .. bot .. " stop")
      return true, { moved = false, why = "检测到坠落 ✓ 已停手（宁可不动 ✗ 也不能掉进虚空 ✓）",
                     before = before, after = { x = cx, y = cy, z = cz } }
    end
    -- ★ 每轮重新 look + move ✓（只发一次只会挪一点点就停 ✗）
    pcall(commands.exec, string.format("player %s look at %.2f %.1f %.2f", bot, tx + 0.5, ty + 1.0, tz + 0.5))
    pcall(commands.execAsync, "player " .. bot .. " move forward")
    if ty > cy + 0.6 then pcall(commands.exec, "player " .. bot .. " jump") end
    sleep(0.12)
  end
  pcall(commands.execAsync, "player " .. bot .. " stop")
  local cx, cy, cz = botPos(bot)
  local moved = (math.abs((cx or bx) - bx) + math.abs((cz or bz) - bz)) > 0.05
  return true, { moved = moved, why = moved and "走了但没到（超时）" or "一步没动 ✗",
                 before = before, after = { x = cx, y = cy, z = cz },
                 target = { x = tx, y = ty, z = tz },
                 seconds = tonumber(string.format("%.2f", os.clock() - t0)) }
end

-- ═══ 临时动作 nest_probe（"嵌套调用"的最小实验 ✓ 2026-09-20 ✓ 诊断完就删 ✗）═══════
-- 要回答的唯一问题（别夹带别的 ✗）：**动作内部调用另一个动作，到底跑不跑得通** ✓
--   现场现象（真实事故 ✓）：`path_follow` 一调用 **90 秒不返回** ✗ 假人**一步没动** ✗
--     而新加的"硬看门狗"**根本没触发** ✗
--   为什么看门狗没触发 ✓（读代码得出的假设 ✗ 待验证 ✓）：
--     `hardDeadline` 只在 **attempt 循环的开头**判一次 ✗
--     ⇒ 只要卡在 `A.path_plan(...)` 这一句里面，看门狗就永远轮不到 ✗
--   ⇒ 所以先别改执行器 ✗：**先问清"卡在哪一段"** ✓
-- 纪律（本项目最值钱的一条 ✓）：**先让程序自己报位置，再读代码** ✗ 不要反过来 ✗
--
-- 打点去处 = 机器本地 `job.log` ✓（真实教训 D2/G6 ✓）：
--   回传会丢 ✗ 网关会挂 ✗ 但**机器自己写的磁盘文件不会骗人** ✓
--   读法：`py tools/cc_logs.py 2`    或   `py tools/read_joblog.py 2 20`
--   ⚠ 判读法 ✓：**有哪几行、缺哪一行** ✗ 比"最后一行是什么"更重要 ✓
--     例：只有 `nest.plan_begin` 没有 `nest.plan_done` ⇒ **就卡在 path_plan 里** ✓✓
--
-- 用法：
--   py tools/act.py nest_probe x=<tx> z=<tz> radius=6 plan_timeout=8
--   （想更小：radius=2 ⇒ 扫描量掉到 1/27 ✓ 先证明"通路"✓ 再谈"性能"✗）
A.nest_probe = function(args)
  local a  = args or {}
  local t0 = os.clock()
  local out = { steps = {} }

  local function mark(name, data)
    data = data or {}
    data.t = tonumber(string.format("%.2f", os.clock() - t0))
    out.steps[#out.steps + 1] = { name = name, data = data }
    jobNote("nest." .. name, data)
    print("[nest] " .. name .. "  t=" .. tostring(data.t) .. "s")
  end

  mark("begin", { has_commands = hasCommandsAPI() })

  -- ① 对照组：普通局部函数 ✓（证明"调用函数"这件事本身没问题 ✓）
  local function twice(x) return x * 2 end
  mark("local_fn", { twice21 = twice(21) })

  -- ② 嵌套调用**兄弟动作** A.status ✓（只读 ✓ 便宜 ✓ 内层也要用 commands 吗？不用 ✓）
  local okS, s1, s2 = pcall(A.status)
  mark("nested_status", { pcall_ok = okS, t1 = type(s1), t2 = type(s2),
                          err = (not okS) and tostring(s1) or nil })

  -- ③ 关键一步：**嵌套调用 A.path_plan** ✓ = path_follow 里那一句的复制品 ✓
  local tx, ty, tz = tonumber(a.x), tonumber(a.y), tonumber(a.z)
  local okB, bx, by, bz = pcall(botPos, a.bot or "Bot")
  mark("botpos", { ok = okB, x = bx, y = by, z = bz })
  mark("plan_begin", { from = { bx, by, bz }, to = { tx, ty, tz },
                       radius = tonumber(a.radius), plan_timeout = tonumber(a.plan_timeout) or 8 })
  if tx and tz then
    local okP, p1, p2 = pcall(A.path_plan, {
      bot = a.bot or "Bot", x = tx, y = ty, z = tz,
      dig = a.dig, place = a.place, max_drop = a.max_drop,
      radius = a.radius, timeout = tonumber(a.plan_timeout) or 8,
    })
    -- ⚠ 返回"信封"形状**不止一种** ✗（真实教训 H9 / J5 ✓）⇒ 逐个 type 判 ✓ 别硬下标 ✗
    if not okP then
      mark("plan_done", { pcall_ok = false, err = tostring(p1) })
    elseif type(p1) ~= "table" then
      mark("plan_done", { pcall_ok = true, first = tostring(p1), second = tostring(p2) })
    else
      mark("plan_done", { pcall_ok = true, found = p1.found, steps = p1.steps, cost = p1.cost,
                          visited = p1.visited, scanned = p1.scanned,
                          seconds = p1.seconds, hint = p1.hint })
    end
  else
    mark("plan_skipped", { why = "没给 x/z ⇒ 只测①②（仍然有诊断价值 ✓）" })
  end

  mark("done", {})
  return true, out
end

A.self_update = function(args)
  local remote = (args and args.name) or "agent_bridge.lua"
  -- ⚠ 不能用 args.local：`local` 是 Lua 保留字，点号后面必须跟"名字" ✗
  --   写成 args.local 会得到 `<name> expected near 'local'`（真实事故，卡了很久）。
  local target = (args and args.localname) or "bridge_local"
  local body, err = httpGet(BASE .. "/files/" .. remote)
  if not body or #body < 100 then return false, "下载失败：" .. tostring(err) end
  local fn, lerr = load(body, remote, "t", _ENV)
  if not fn then return false, "新版本语法错误，已放弃更新：" .. tostring(lerr) end
  local f = fs.open(target, "w")
  if not f then return false, "无法写入 " .. target end
  f.write(body)
  f.close()
  WANT_REBOOT = true
  EXIT_NOW = true          -- 重启是故意行为，别被看门狗当成崩溃
  return true, { updated = target, bytes = #body, note = "回报后重启计算机以载入新版本" }
end

-- 远程重启（配合 self_update 使用）
A.reboot = function()
  WANT_REBOOT = true
  EXIT_NOW = true
  return true, { note = "回报后重启计算机" }
end

-- 强制重新发现外设。
-- 真实事故：开机自启那一刻 discover() 只看到 1 个 modem，5 个 Advanced Peripherals
-- 全部"消失"；而手动启动时完全正常 —— 因为计算机的方块实体比相邻外设更早被创建，
-- 开机瞬间扫描存在**时序竞争**。主循环里也会定期重扫（见 tick % 20），
-- 这个动作用于需要立刻刷新时（例如刚放好外设）。
A.rediscover = function()
  local before = #P.names
  discover()
  return true, { before = before, after = #P.names, peripherals = P.names }
end

-- 广播下发：把一条指令通过 rednet **广播**发给所有海龟并收集应答。
--
-- 为什么需要（实测）：本项目的 **广播 + 应答** 一直可靠，而 rednet 的
-- **定向发送**（按 id 发）在实测中不稳定 —— 广播能收到、定向却超时 ✗。
-- 用广播 + 按 id 过滤应答，就能达到"定向"的效果，且走的是那条可靠的路径。
-- 长指令（如 chop_log）请把 wait 调大（默认 8 秒）。
A.broadcast_cmd = function(args)
  local cmd = args and args.cmd
  if not cmd then return false, "需要 cmd=<要广播的指令>" end
  local target = tonumber(args and args.target)
  local sub = {}
  for k, v in pairs(args or {}) do
    if k ~= "cmd" and k ~= "target" and k ~= "wait" and k ~= "wait_ms" then sub[k] = v end
  end
  local want = tonumber(args and args.wait) or 8
  rednet.broadcast({ cmd = cmd, args = sub }, "bridge")
  local got = {}
  local deadline = os.clock() + want
  while true do
    local remain = deadline - os.clock()
    if remain <= 0 then break end
    local sender, msg = rednet.receive("bridge_reply", remain)
    if not msg then break end
    if sender and type(msg) == "table" and (not target or sender == target) then
      got[#got + 1] = { id = sender, ok = msg.ok, result = msg.result }
    end
  end
  table.sort(got, function(a, b) return (a.id or 0) < (b.id or 0) end)
  return true, { cmd = cmd, count = #got, replies = got }
end

-- 自省：让游戏把外设**真正提供的方法名**报上来。
-- 为什么需要：外设 API 名在各版本/各模组间有差异（本次 block_info 返回 nil 就是候选名不对），
-- 与其在外部猜方法名，不如直接从游戏里问一次（纪律：接口语法必须来自权威来源）。
A.peripheral_api = function(args)
  if args and args.name then
    return true, { name = args.name, methods = peripheral.getMethods(args.name) or {} }
  end
  local out = {}
  for _, n in ipairs(peripheral.getNames()) do
    local m = peripheral.getMethods(n) or {}
    table.sort(m)
    out[n] = m
  end
  return true, { by_peripheral = out }
end

A.sleep = function(args)
  local ms = tonumber(args and args.ms) or 500
  sleep(math.min(ms, 10000) / 1000)
  return true, { slept_ms = ms }
end

-- --- 高层动作 ------------------------------------------------------------ --
A.go_relative = function(args)
  if not IS_TURTLE then return false, "需要海龟" end
  local dx = tonumber(args and args.dx) or 0
  local dz = tonumber(args and args.dz) or 0
  local dy = tonumber(args and args.dy) or 0
  local steps = 0
  local function axisMove(stepFn, count)
    for _ = 1, math.abs(count) do
      local ok, err = stepFn()
      if not ok then return false, err end
      steps = steps + 1
    end
    return true
  end
  -- 先转朝向再走（基于自维护朝向，转的是"下标"）
  if dz ~= 0 then
    local want = idxOf(dz < 0 and "north" or "south")
    local ok, err = turnToIdx(want); if not ok then return false, err end
    local ok2, err2 = axisMove(function() return moveOne(turtle.forward, turtle.dig) end, dz)
    if not ok2 then return false, err2 end
  end
  if dx ~= 0 then
    local want = idxOf(dx > 0 and "east" or "west")
    local ok, err = turnToIdx(want); if not ok then return false, err end
    local ok2, err2 = axisMove(function() return moveOne(turtle.forward, turtle.dig) end, dx)
    if not ok2 then return false, err2 end
  end
  if dy > 0 then
    local ok, err = axisMove(function() return moveOne(turtle.up, turtle.digUp) end, dy)
    if not ok then return false, err end
  elseif dy < 0 then
    local ok, err = axisMove(function() return moveOne(turtle.down, turtle.digDown) end, dy)
    if not ok then return false, err end
  end
  return true, { steps = steps, facing = FACING[facingIdx] }
end

A.tunnel = function(args)
  if not IS_TURTLE then return false, "需要海龟" end
  local dir   = (args and args.dir) or "forward"
  local len   = tonumber(args and args.length) or 4
  if dir ~= "forward" then
    local i = idxOf(dir)
    if i then
      local ok, err = turnToIdx(i); if not ok then return false, err end
    end
  end
  for i = 1, len do
    local ok, err = moveOne(turtle.forward, turtle.dig)
    if not ok then return false, string.format("第 %d 格失败：%s", i, tostring(err)) end
    -- 挖宽一点（2 高 3 宽），更像人能走的通道
    for _ = 1, 2 do
      pcall(turtle.digUp)
      if not moveOne(turtle.up, turtle.digUp) then break end
      pcall(turtle.dig)
    end
    for _ = 1, 2 do
      if not moveOne(turtle.down, turtle.digDown) then break end
      pcall(turtle.dig)
    end
  end
  return true, { length = len }
end

A.mine_column = function(args)
  if not IS_TURTLE then return false, "需要海龟" end
  local depth = tonumber(args and args.depth) or 5
  local dug = 0
  for _ = 1, depth do
    if not moveOne(turtle.down, turtle.digDown) then break end
    pcall(turtle.dig)
    dug = dug + 1
  end
  return true, { dug = dug }
end

--------------------------------------------------------------------------------
-- rednet 转发（把指令交给某只海龟执行）
--------------------------------------------------------------------------------
local dispatchSeq = 0
local function nextDispatchId()
  dispatchSeq = dispatchSeq + 1
  return tostring(os.epoch and os.epoch("utc") or os.time()) .. "-" .. tostring(dispatchSeq)
end

local function dispatchToTurtle(targetId, cmd, args)
  -- ⚠ 必须带 id 握手（真实事故）：
  --   原来只发 {cmd=...}、只等"任意一个" bridge_reply。若某条指令耗时超过等待上限，
  --   它迟到的回包会被**当成下一条指令的结果**，从此整条链路的结果全部错位
  --   （现场表现就是"指令时好时坏、结果对不上"）。
  --   现在每条指令带唯一 id，只认 id 相同的回包，其它一律丢弃继续等。
  local myId = nextDispatchId()
  local ok = rednet.send(tonumber(targetId), { id = myId, cmd = cmd, args = args or {} }, "bridge")
  if not ok then return false, "rednet 发送失败（检查频道与 modem）" end

  -- 默认 30 秒（locate 要多次 GPS 采样、dig_up_while 这类长活更久）
  local waitS = 30
  if args and tonumber(args.wait_ms) then waitS = tonumber(args.wait_ms) / 1000 end
  local deadline = os.clock() + waitS
  while true do
    local remain = deadline - os.clock()
    if remain <= 0 then break end
    local sender, msg = rednet.receive("bridge_reply", remain)
    if not msg then break end
    if type(msg) == "table" and msg.id == myId then
      return msg.ok, msg.result
    end
    -- 不是本次的回包：丢弃，继续等待（不要把它当成结果）
  end
  return false, "海龟无响应（超过 " .. tostring(math.floor(waitS)) ..
                " 秒；长任务可用 wait_ms 调大，或先确认 worker 是否刚启动完）"
end

--------------------------------------------------------------------------------
-- 状态回报
--------------------------------------------------------------------------------
local function buildState(extra)
  local st = {
    who    = WHO,
    ts     = os.epoch and os.epoch("utc") or os.time(),
    is_turtle = IS_TURTLE,
    facing = facingKnown and FACING[facingIdx] or "unknown",
    peripherals = P.names,
    dry_run = DRY_RUN,
  }
  if extra then for k, v in pairs(extra) do st[k] = v end end
  return st
end

local function report(extra)
  local body, err = httpPostJSON(BASE .. "/api/state", buildState(extra))
  if not body then return false, err end
  return true
end

--------------------------------------------------------------------------------
-- 主循环
--------------------------------------------------------------------------------
-- dry_run 只拦截"会改变世界"的指令。
-- 只读/感知类指令（以及 say）始终执行，这样 dry_run=true 时也能完整跑通冒烟测试，
-- 否则首次调试会陷入"什么都验证不了"的死角。
local READONLY = {
  status = true, scan = true, players = true, block_info = true,
  -- 准星感知是**纯读** ✓（只读 Pos/Rotation 与方块信息 ✓ 不改世界 ✓）
  -- ⚠ 但 A.jade **带 hud=true 时会召唤/删除显示实体** ✗ → 不列为只读 ✓
  --   dry_run 下由 A.jade 自己拦住（并如实回报 would_set_hud ✓）。
  crosshair = true,
  -- 周边方块读取也是纯读 ✓（只读方块状态 ✓ 不改世界 ✓）
  blocks_around = true,
  inv_list = true, inv_man = true, chat_read = true, say = true, sleep = true,
  peripheral_api = true, player_pos = true, geo_status = true,
  discover_turtles = true, locate = true,
  -- 控制类（不改动世界，但需要随时可用，尤其用于清理跑错程序的机器）
  quit = true, shutdown = true, rediscover = true, self_update = true, reboot = true,
  broadcast_cmd = true,
}

-- 转发给海龟时，这些指令**只读**、不改变世界，因此 dry_run 也放行。
-- 好处：演练模式下仍能查海龟的状态/库存，不必为了"看一眼"而解锁动作能力。
local TURTLE_READONLY = { status = true, inv_list = true, calibrate = true }

local function execute(cmd, args)
  if cmd == "idle" or cmd == nil then return nil end

  -- 指定了海龟目标就转发。
  -- ⚠ dry_run 必须同样管住转发：否则"演练模式"下海龟照样会真的挖/走，
  --    安全开关形同虚设（海龟的动作为不可逆）。
  if args and args.target then
    if DRY_RUN and not TURTLE_READONLY[cmd] then
      return true, { dry_run = true, would_dispatch = cmd, target = args.target,
                     note = "只读指令（status/inv_list/calibrate）不受 dry_run 限制" }
    end
    return dispatchToTurtle(args.target, cmd, args)
  end

  local fn = A[cmd]
  if not fn then return false, "未知指令：" .. tostring(cmd) end

  if DRY_RUN and not READONLY[cmd] then
    return true, { dry_run = true, would_run = cmd, note = "只读指令不受 dry_run 限制" }
  end

  local ok, r1, r2 = pcall(fn, args)
  if not ok then return false, "执行异常：" .. tostring(r1) end
  return r1, r2
end

-- ═══ 肌肉记忆（反射层）══════════════════════════════════════════════════════
-- 为什么必须长在**游戏里** ✗（而不是 Agent 那边 ✓）：
--   这些判定要比人的反应更快 ✓ —— 等 Python 走一圈网关再回来 ✓ 假人早就死了 ✗
--   而**命令计算机执行 `/player` 是本机进程内**的 ✓ 所以能做到接近 tick 级 ✓✓
--   Agent 那边只留"思考"（建产线/找资源/规划 ✓）；保命交给这里 ✓
--
-- 规则（都可在 `bridge.cfg` 里关掉或调阈值 ✓）：
--   1) **血量比上一拍下降 → 判定"被打了"** ✓ → 转头看最近的实体 + 连续攻击 ✓
--      （用"掉血"而不是"识别怪物种类" ✓ 这样不需要维护怪物名单 ✓ 而且更通用 ✓）
--   2) 危险解除（附近已无目标）→ 自动停手 ✓
--   3) 血低 → 吃东西（连续右键 ✓ 吃完/脱离后由 (2) 收尾 ✓）
--   4) 位置长时间不变 → 记一笔"可能卡住" ✓（**只记录** ✓ 不做激进干预 ✗）
--   5) 所有动作都写 job.log ✓ 而且**失败也写** ✓ 绝不静默 ✗
local REFLEX_BOT = (cfg and cfg.bot) or "Bot"
local reflexState = { lastHealth = nil, lastPos = nil, stillSince = nil,
                      lastTick = 0, fighting = false }

local function reflexNum(txt)
  local out = {}
  for n in tostring(txt):gmatch("(-?%d+%.?%d*)") do out[#out + 1] = tonumber(n) end
  return out
end

local function reflexGet(cmdtext)
  local p = packReturns(pcall(commands.exec, cmdtext))
  if not p[1] then return nil end
  if type(p[3]) == "table" then return table.concat(p[3], " ") end
  return tostring(p[3])
end

local function reflexTick(now)
  if cfg and cfg.reflex == false then return end
  local period = tonumber(cfg and cfg.reflex_ms) or 500
  if (now - (reflexState.lastTick or 0)) < period then return end
  reflexState.lastTick = now

  local hp = tonumber((reflexGet("data get entity " .. REFLEX_BOT .. " Health") or "")
                      :match("([%d%.]+)f"))
  if not hp then return end

  local hurt = (reflexState.lastHealth ~= nil) and (hp < reflexState.lastHealth)
  reflexState.lastHealth = hp

  -- 危险解除 → 停手 ✓（否则会一直砍空气 ✗）
  if reflexState.fighting and not hurt then
    -- ⚠ tag=!dsh_jade：排除 Jade HUD 那个悬浮文字实体（它是实体 ✗）
    --   否则"最近的实体"永远是它 ✓ → 永远判定"附近还有目标" ✓ → 永远不停止攻击 ✗✗
    local near = reflexGet("data get entity @e[distance=..6,type=!player,type=!item,tag=!dsh_jade,limit=1,sort=nearest] Pos")
    if not (near and near:find("%[")) then
      pcall(commands.execAsync, "player " .. REFLEX_BOT .. " stop")
      reflexState.fighting = false
      jobNote("reflex.stop", { hp = hp, why = "附近已无目标" })
    end
  end

  local lowHp = tonumber(cfg and cfg.reflex_low_health) or 10
  if (hurt or hp <= lowHp) and hp > 6 then
    -- ⚠⚠ 安全红线：**只能打敌人** ✗
    --   我第一版是"打最近的**非玩家、非掉落物**实体" ✓ —— 那会去砍**玩家养的牛羊** ✗✗
    --   （触发场景很现实：假人被火烧到掉血 ✓ 它就会去杀旁边的动物 ✗）
    --   所以改成**白名单**：先取最近实体的完整 NBT ✓ 只有 id 在名单里才动手 ✓
    local HOSTILE = { zombie = true, husk = true, drowned = true, skeleton = true, stray = true,
                      creeper = true, spider = true, cave_spider = true, witch = true,
                      enderman = true, slime = true, magma_cube = true, blaze = true,
                      ghast = true, phantom = true, pillager = true, vindicator = true,
                      evoker = true, ravager = true, silverfish = true, piglin = true,
                      hoglin = true, zoglin = true, wither_skeleton = true, guardian = true,
                      elder_guardian = true, warden = true, breeze = true, bogged = true }
    local nbt = reflexGet("data get entity @e[distance=..12,type=!player,type=!item,tag=!dsh_jade,limit=1,sort=nearest]")
    local eid = nbt and nbt:match('id:%s*"([^"]+)"')
    local short = eid and eid:match(":(.+)$")
    local isFoe = (short ~= nil) and (HOSTILE[short] == true)
    if isFoe then
      local pn = reflexNum((nbt or ""):match("Pos:%s*(%[[^%]]*%])") or "")
      if pn[1] and pn[2] and pn[3] then
        pcall(commands.exec, string.format("player %s look at %.2f %.2f %.2f",
          REFLEX_BOT, pn[1], pn[2] + 1.0, pn[3]))
      end
      if not reflexState.fighting then
        pcall(commands.execAsync, "player " .. REFLEX_BOT .. " attack continuous")
        reflexState.fighting = true
        jobNote("reflex.attack", { hp = hp, hurt = hurt, foe = short })
      end
      return
    end
    -- 不是敌人（被火烧/摔伤/中毒等 ✓）→ 吃东西回血 ✓ 绝不动玩家的动物 ✓
    pcall(commands.execAsync, "player " .. REFLEX_BOT .. " use interval 4")
    jobNote("reflex.eat", { hp = hp, hurt = hurt, nearest = short })
  end

  -- 卡住检测（只记录 ✓ 30 秒阈值 ✓）
  local n2 = reflexNum(reflexGet("data get entity " .. REFLEX_BOT .. " Pos") or "")
  if n2[1] and n2[2] and n2[3] then
    local p2 = { n2[1], n2[2], n2[3] }
    if reflexState.lastPos then
      local d = math.abs(p2[1] - reflexState.lastPos[1]) + math.abs(p2[2] - reflexState.lastPos[2])
              + math.abs(p2[3] - reflexState.lastPos[3])
      if d < 0.05 then
        reflexState.stillSince = reflexState.stillSince or now
        if (now - reflexState.stillSince) > 30000 then
          jobNote("reflex.stuck", { at = p2 })
          reflexState.stillSince = now
        end
      else
        reflexState.stillSince = nil
      end
    end
    reflexState.lastPos = p2
  end

  -- 准星感知（Jade）：HUD 开着时，顺手把"假人正对着什么"更新到世界里 ✓
  -- 顺序放在最后：保命逻辑（打/吃/停）先跑 ✓ 感知不抢在它前面 ✗。
  -- ⚠ 这里只感知、不决策 ✓ 决策仍然在 Agent 那边 ✓（肌肉记忆也只管"不需要思考"的那部分 ✓）
  if jadeState.hud then
    local okJ, errJ = pcall(jadeTick, now)
    if not okJ then jobNote("jade.error", { err = tostring(errJ) }) end
  end
end

local function main()
  -- 模式可由命令行参数覆盖：`wget run <url> live` / `wget run <url> dry`。
  -- 依据已核对的 CC 源码 (`rom/programs/http/wget.lua`)：run 分支是
  --   pcall(func, table.unpack(tArgs))  —— 即 <url> 之后的额外参数会传进程序。
  -- 为什么不用"改配置文件"：CC 的 wget **拒绝覆盖已存在的文件**
  --   (wget.lua 里 `if fs.exists(sPath) then print("File already exists") return end`)，
  --   让用户删文件再下载、还要重启，既别扭又容易失败。一个词切换最可靠。
  local mode = ARGV[1]
  if mode == "live" then
    DRY_RUN = false
  elseif mode == "dry" then
    DRY_RUN = true
  elseif mode ~= nil and mode ~= "force" then
    print("[bridge] 未知参数（忽略）：" .. tostring(mode) .. "  可用：live / dry")
  end

  -- ⚠ 身份保护（真实踩过）：
  --   把本程序误跑在海龟上 → 两台机器都用 who=mine1 轮询网关，
  --   指令会被"随机一方"取走（我发给主计算机的 goto 被海龟抢去执行），
  --   而且 discover_turtles 广播也收不到应答（海龟上的 worker 根本没在跑）。
  --   这里直接拒绝启动，并指出正确的程序名。
  local force = false
  for _, v in ipairs(ARGV) do if v == "force" then force = true end end
  if IS_TURTLE and not force then
    print("")
    print("⚠ 这是一只海龟！本程序应运行在【计算机】上。")
    print("   海龟请运行: wget run http://<网关IP>:8765/files/turtle_worker.lua")
    print("   确实要强行运行请加参数 force（不建议：会与主计算机争抢同一个 who）")
    return
  end

  ----------------------------------------------------------------------------
  -- 自安装开机自启
  -- 依据（已核对 CC 的 ROM `startup.lua`）：根目录下名为 `startup` 的文件
  -- 会在每次开机时被 shell.run 执行（受 settings.shell.allow_startup 管）。
  -- 为什么程序自己写：CC 计算机重启后前台程序**不会**自动恢复，
  --   现场表现为"所有指令超时 + discover_turtles 返回 count:0"（真实踩过多次）。
  --   让它第一次运行就写好 startup，用户跑一次即可永久自动。
  ----------------------------------------------------------------------------
  local function ensureStartup(cmd)
    local cur = ""
    if fs.exists("startup") then
      local f0 = fs.open("startup", "r")
      if f0 then cur = f0.readAll() or ""; f0.close() end
      if cur:find(cmd, 1, true) then return false, "已存在，无需重复写入" end
    end
    local f1 = fs.open("startup", "w")
    if not f1 then return false, "无法写入 startup（磁盘只读？）" end
    if #cur > 0 then
      f1.write(cur)
      if cur:sub(-1) ~= "\n" then f1.write("\n") end
    end
    f1.write(cmd .. "\n")
    f1.close()
    return true, "已写入 startup —— 以后开机自动运行"
  end

  -- ⚠ Lua 没有"字符串 × 数字"这种写法！Python/PowerShell 的 "=" * 52 在 Lua 里是
  --    "attempt to perform arithmetic on a string value"。必须用 string.rep。
  local BAR = string.rep("=", 52)
  print(BAR)
  print(" MC Agent Bridge")
  print("   gateway : " .. BASE)
  print("   who     : " .. WHO)
  print("   turtle  : " .. tostring(IS_TURTLE))
  print("   dry_run : " .. tostring(DRY_RUN) .. "   (只读指令不受 dry_run 影响)")
  print("   切换模式: 重启时加参数  live (真动手) / dry (演练)")
  print(BAR)

  local okSt, stMsg = ensureStartup(
    'shell.run("wget", "run", "' .. BASE .. '/files/agent_bridge.lua", "' ..
    (DRY_RUN and "dry" or "live") .. '")')
  print("[bridge] 开机自启：" .. tostring(stMsg))

  discover()
  print("[bridge] 外设：" .. (#P.names > 0 and table.concat(P.names, ", ") or "（无）"))

  local ok0, err0 = report({ event = "boot" })
  if ok0 then
    print("[bridge] 已连接网关，开始轮询指令（Ctrl+T 可退出）")
  else
    print("[bridge] ⚠ 上报失败：" .. tostring(err0))
  end

  local tick = 0
  while true do
    tick = tick + 1

    -- ★ 肌肉记忆先跑 ✓（保命优先于一切指令 ✗）
    --   放在最前面：即使网关挂了 / 队列里压着一堆活 ✓ 反射照样工作 ✓✓
    -- ⚠ 反射层里的错误**必须留痕** ✗ —— 之前用裸 pcall 包着，
    --   一旦规则代码写错（比如字段名拼错 ✗）它会**静默地**什么都不做 ✗，
    --   现场表现是"肌肉记忆好像没生效 ✓"而且**没有任何线索** ✓（真实踩过）。
    --   现在：异常写进 job.log ✓ 磁盘上能查到 ✓ 不依赖任何网络通道 ✓。
    local okR, errR = pcall(reflexTick, os.clock() * 1000)
    if not okR then jobNote("reflex.error", { err = tostring(errR) }) end

    -- 整轮包一层 pcall：任何意外异常只影响这一轮，不会让程序整体退出。
    -- （现场调试时"脚本一崩就退出"最浪费时间——你在游戏里还得重新敲一遍命令）
    local roundOk, roundErr = pcall(function()
      -- ── 本地直连通道（快路）─────────────────────────────────────────────
      -- CC 的文件系统就在主机磁盘上，所以 Agent 可以直接把指令文件写进本机
      -- `inbox/*.json`，不必绕网关。效果：
      --   · 延迟从"网关 0.5s + 电脑轮询 0.5s"降到**一个轮询周期**（~0.1s）
      --   · 不依赖网关存活，也不存在"回传在中间环节丢失"这类问题
      -- 这是为了解决"操作机器人反应太慢"而加的 —— 但注意：**真正的墙钟时间大头
      -- 仍是作业内部的步进等待与 Agent 自己的往返**，快路只是把通道那 1 秒抹掉。
      if fs.isDir("inbox") then
        for _, fname in ipairs(fs.list("inbox")) do
          if type(fname) == "string" and fname:sub(-5) == ".json" then
            local path = "inbox/" .. fname
            local fh = fs.open(path, "r")
            local body = fh and fh.readAll() or nil
            if fh then fh.close() end
            local spec = body and decode(body) or nil
            if type(spec) == "table" and spec.cmd then
              local okL, resL = execute(spec.cmd, spec.args)
              jobNote("local.dispatch", { file = fname, cmd = tostring(spec.cmd), ok = okL })
              report({ id = spec.id or fname, cmd = spec.cmd, ok = okL, result = resL, via = "local" })
            else
              jobNote("local.dispatch.bad", { file = fname, body = tostring(body):sub(1, 120) })
            end
            fs.delete(path)
          end
        end
      end

      local body, err = httpGet(BASE .. "/api/next?who=" .. textutils.urlEncode(WHO))
      local req = decode(body)

      if not req and err then
        print("[bridge] 网关不可达：" .. tostring(err))
      elseif req and req.cmd and req.cmd ~= "idle" then
        local ok, result = execute(req.cmd, req.args)
        report({ id = req.id, cmd = req.cmd, ok = ok, result = result })
        -- 结果里可能含无法序列化的表，打印失败也不该拖垮整轮
        local okS, shown = pcall(textutils.serializeJSON, result or {})
        print(string.format("[bridge] %s -> %s %s", tostring(req.cmd), tostring(ok),
          okS and shown or "(结果无法序列化)"))
      end

      -- 定期重新发现外设（每 20 轮 ≈ 10 秒）。
      -- 开机自启时计算机的方块实体可能比相邻外设更早创建，discover() 会漏掉它们
      -- （真实事故：自启后 5 个 AP 外设全部"消失"，手动启动却完全正常）。
      -- 重扫同时也顺带支持"运行中增删外设"。
      if tick % 20 == 0 then
        local before = #P.names
        discover()
        if #P.names ~= before then
          print("[bridge] 外设变化：" .. before .. " -> " .. #P.names ..
                "  (" .. (#P.names > 0 and table.concat(P.names, ", ") or "无") .. ")")
        end
      end

      if tick % REPORT_EVERY == 0 then
        if P.geo and not IS_TURTLE then          -- 定期附带一次地形感知，让 Agent 有"眼睛"。
          -- 但扫描要烧燃料且带冷却，先问冷却值，避免每轮打无效扫描（之前 scan 时好时坏就是这个）。
          local cd = callFirst(P.geo, { "getOperationCooldown" })
          if cd == nil or (tonumber(cd) or 0) <= 0 then
            local _, scanOk, scanRes = pcall(A.scan, { radius = 6 })
            report({ event = "heartbeat", scan_ok = scanOk, scan = scanRes })
          else
            report({ event = "heartbeat", scan_skipped = "冷却中", cooldown = cd })
          end
        else
          report({ event = "heartbeat" })
        end
      end
    end)

    if not roundOk then
      print("[bridge] ⚠ 本轮异常（已忽略，继续运行）：" .. tostring(roundErr))
      pcall(function() report({ event = "error", error = tostring(roundErr) }) end)
    end

    -- 远程控制（在回报之后执行，保证结果已经发出）
    if WANT_SHUTDOWN then
      print("[bridge] 收到远程关机指令，正在关机")
      os.shutdown()
    end
    if WANT_REBOOT then
      print("[bridge] 正在重启计算机以载入新版本…")
      os.reboot()
    end
    if WANT_QUIT then
      print("[bridge] 收到远程退出指令，回到 shell 提示符")
      break
    end

    -- sleep 也要护住：它是主循环里唯一还在 pcall 之外的一步，
    -- 一旦被中断（终止事件等）就会抛错、跳出整轮循环。
    pcall(sleep, POLL_S)
  end
end

-- ---------------------------------------------------------------------------
-- 最外层看门狗：绝不停在 shell 提示符上等人来敲
--
-- 真实事故（值得记住）：网关重启的瞬间打断了两台机器的 HTTP 请求，
-- 两台机器随后全部沉默，state 里空空如也——它们退回了 shell 提示符，
-- 而外部既看不到、也重启不了它们，只能等人进游戏手动敲 Ctrl+R。
-- 对一个跑在基地里的无人值守机器人来说，这是最贵的失败模式。
-- 所以：只要不是"我故意让它停"，任何退出都要自动拉起来。
-- ---------------------------------------------------------------------------
local restarts = 0
while true do
  local ok, err = pcall(main)
  if EXIT_NOW then
    print("[bridge] stopped on request")
    break
  end
  restarts = restarts + 1
  print(string.format("[bridge] main exited (%s) - auto-restart #%d in 5s",
    tostring(err), restarts))
  pcall(sleep, 5)
end
