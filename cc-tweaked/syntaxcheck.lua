--[[
  syntaxcheck.lua — 只做语法检查，不执行目标文件
  ==================================================================
  用途：Agent 改完代码后先确认"能不能被 Lua 加载"，避免把机器刷成加载失败 ✗

  在游戏内运行：
      wget run http://<网关IP>:8765/files/syntaxcheck.lua
      wget run http://<网关IP>:8765/files/syntaxcheck.lua agent_bridge.lua

  打印内容：下载到多少字节 + **准确的语法错误**（或 SYNTAX OK）
  全程 ASCII 输出，避免 CC 终端显示不了中文 ✓
]]

local tArgs = { ... }
local name = tArgs[1] or "agent_bridge.lua"

local GW = "http://127.0.0.1:8765"

local function checkOne(label, src)
  print("[check] " .. label .. " : " .. #src .. " bytes")
  local fn, err = load(src, label, "t", _ENV)
  if fn then
    print("[check]   SYNTAX OK")
    return true
  end
  print("[check]   SYNTAX ERROR:")
  print("        " .. tostring(err))
  return false
end

local anyBad = false

-- 1) 检查网关上的文件
local url = GW .. "/files/" .. name
print("[check] GET " .. url)
local res, gerr = http.get(url)
if not res then
  print("[check] DOWNLOAD FAILED: " .. tostring(gerr))
  anyBad = true
else
  local src = res.readAll()
  res.close()
  if not checkOne("gateway:" .. name, src) then anyBad = true end
end

-- 2) 检查本地副本
local localName = (name == "agent_bridge.lua") and "bridge_local" or "worker_local"
if fs.exists(localName) then
  local f = fs.open(localName, "r")
  if f then
    local src = f.readAll() or ""
    f.close()
    if not checkOne("local:" .. localName, src) then anyBad = true end
  end
else
  print("[check] (no local copy named " .. localName .. ")")
end

print("[check] RESULT: " .. (anyBad and "PROBLEMS FOUND" or "ALL OK"))
