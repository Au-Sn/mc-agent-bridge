--[[
  gps_host.lua — 让一台计算机成为 GPS 主机（并自动装好开机自启）
  ==================================================================

  用法（在每台 GPS 主机上执行一次，带上**这台主机自己**的坐标）：

      wget run http://<网关IP>:8765/files/gps_host.lua <x> <y> <z>

  例：  wget run http://127.0.0.1:8765/files/gps_host.lua 4122 72 10

  坐标怎么取：站在该主机**正上方那一格**，按 F3 看 `Block:` 那一行，
            然后 **y 减 1** 就是主机自己的方块坐标。

  它会做两件事：
    1. 把 `gps host <x> <y> <z>` 写进根目录的 `startup` 文件
       → 以后**每次开机自动当 GPS 主机**，不用再手动跑（依据 CC 的 ROM `startup.lua`）
    2. 立刻以主机身份运行

  ⚠ 前置条件（源码里明确的）：
    * 这台计算机必须贴**无线调制解调器**，否则会打印 "No wireless modems found. 1 required."
    * **不能用口袋电脑**（会提示 GPS Hosts must be stationary）
    * 主机位置要**固定不动**，且所在区块被加载
    * 前 4 台必须手动给坐标（自动定位本身就需要 4 台已在跑的主机）
    * 若开机没有自动运行，检查 `set shell.allow_startup` 是否为 true
]]

local tArgs = { ... }
local x, y, z = tonumber(tArgs[1]), tonumber(tArgs[2]), tonumber(tArgs[3])

if not (x and y and z) then
  print("用法: wget run http://<网关IP>:8765/files/gps_host.lua <x> <y> <z>")
  print("坐标 = 这台主机【自己所在方块】的坐标（站它正上方按 F3 看 Block 行，再把 y 减 1）")
  print("")
  print("当前已有的 startup 内容：")
  if fs.exists("startup") then
    local f = fs.open("startup", "r")
    if f then print(f.readAll() or "(空)"); f.close() end
  else
    print("(还没有 startup 文件)")
  end
  return
end

local line = 'shell.run("gps", "host", ' .. x .. ', ' .. y .. ', ' .. z .. ')'

-- ---- 1) 写入开机自启 ----------------------------------------------------
local cur = ""
if fs.exists("startup") then
  local f0 = fs.open("startup", "r")
  if f0 then cur = f0.readAll() or ""; f0.close() end
end

if cur:find(line, 1, true) then
  print("[gps] 开机自启：已存在，无需重复写入")
else
  local f1 = fs.open("startup", "w")
  if f1 then
    if #cur > 0 then
      f1.write(cur)
      if cur:sub(-1) ~= "\n" then f1.write("\n") end
    end
    f1.write(line .. "\n")
    f1.close()
    print("[gps] 开机自启：已写入 startup —— 以后开机自动当 GPS 主机")
  else
    print("[gps] 开机自启：写入失败（磁盘只读？）")
  end
end

-- ---- 2) 立刻以主机身份运行 ----------------------------------------------
print("[gps] 以 GPS 主机身份运行，坐标 " .. x .. "," .. y .. "," .. z)
shell.run("gps", "host", x, y, z)
