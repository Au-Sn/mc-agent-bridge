--[[
  gps_probe.lua — 直接按 ROM 的 GPS 协议 ping 一次，数"到底有几台 GPS 主机在应答"

  为什么不能只靠 gps.locate()（依据：ROM `rom/apis/gps.lua` 实测源码 ✓）：
    · `gps.locate()` 需要 **3 个平面内的主机 + 1 个离开该平面** 才能解算 ✓；
      拿到 <4 个应答时它**只返回 nil，不告诉你收到了几个** ✗ →
      "0 台主机在跑" 和 "只差一台" 在外部看起来一模一样 ✗。
    · 协议本身很简单 ✓：向频道 **65534** 广播 "PING" ✓，
      主机回一个 `{x, y, z}` 的表 ✓（同一频道）✓，第 5 个事件参数是信号强度=距离 ✓。
  所以这个探针只做一件事：**广播 PING、把应答原样数出来** ✓ —— 主机有没有在跑，一眼可辨 ✓。

  返回：{ count = 应答台数, hosts = [{x,y,z,dist}...], modem = 用哪个面 }
]]

local a = ...
if type(a) ~= "table" then a = {} end

local CH = 65534
local wait = tonumber(a.wait) or 3

local side = a.side
if not side then
  for _, n in ipairs(peripheral.getNames()) do
    local t = peripheral.getType(n)
    if t == "modem" and peripheral.call(n, "isWireless") then
      side = n
      break
    end
  end
end
if not side then
  return false, { err = "没有无线调制解调器（GPS 需要无线 modem）", peripherals = peripheral.getNames() }
end

local m = peripheral.wrap(side)
m.open(CH)

local hosts = {}
local seen = {}
m.transmit(CH, CH, "PING")

local timer = os.startTimer(wait)
while true do
  local e, p1, p2, p3, p4, p5 = os.pullEvent()
  if e == "modem_message" then
    local msg, dist = p4, p5
    if p2 == CH and p3 == CH and type(msg) == "table" and #msg == 3 and tonumber(msg[1]) then
      local key = tostring(msg[1]) .. "," .. tostring(msg[2]) .. "," .. tostring(msg[3])
      if not seen[key] then
        seen[key] = true
        hosts[#hosts + 1] = { x = tonumber(msg[1]), y = tonumber(msg[2]), z = tonumber(msg[3]),
                              dist = dist }
      end
    end
  elseif e == "timer" and p1 == timer then
    break
  end
end

local lines = {}
for _, h in ipairs(hosts) do
  lines[#lines + 1] = string.format("host %d,%d,%d dist=%s", h.x, h.y, h.z, tostring(h.dist))
end
local f = fs.open(a.log or "gps_probe.log", "w")
if f then
  f.writeLine("modem=" .. tostring(side) .. " count=" .. tostring(#hosts))
  for _, l in ipairs(lines) do f.writeLine(l) end
  f.close()
end

return true, { count = #hosts, hosts = hosts, modem = side, waited_s = wait }
