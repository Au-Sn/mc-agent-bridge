# start_all.ps1 -- bring up the resident pieces (idempotent).
#
# What each piece does / what breaks without it:
#   1) gateway   :8765  channel for all dsh* commands   -> without it: BridgeError everywhere
#   2) skin srv  :8791  serves skins/*.png              -> without it: skin falls off (dead URL)
#   3) acp serve        resident harness session memory -> without it: chat loses memory
#   4) acp talk         EARS+MOUTH: game chat -> inbox -> session -> tools -> /dshsay
#                       -> without it: it will not reply and will not do the work
#   5) maven mir :8789  path-prefixed maven mirror      -> needed to REBUILD the mod
#                       (gradle deps come from 127.0.0.1:8789; without it a build needs
#                        the internet, and this box currently cannot reach it -- see docs)
#
param([switch]$ReloadMcp)
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_all.ps1
#        powershell ... -File tools\start_all.ps1 -ReloadMcp    # AFTER EDITING tools/mc_mcp.py
#
# WHY -ReloadMcp exists (measured 2026-09-23):
#   The harness keeps ONE mcp server process alive for the whole profile, and it does NOT
#   respawn it when acp_serve restarts. So after adding tools to tools/mc_mcp.py the brain
#   kept seeing the OLD list (26 tools) while the file had 31 -- and the "missing" tools were
#   exactly the ones added last, which looks like a code bug but is a process-lifetime bug.
#   Killing the mc_mcp.py process here makes the next session spawn a fresh one (31 tools).
#
# NOTE: ASCII-only on purpose. Windows PowerShell 5.1 decodes BOM-less scripts as ANSI,
#       so non-ASCII comments corrupt the script itself (seen: "Unexpected token '}'").

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$logs = Join-Path $root "logs"
if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Force -Path $logs | Out-Null }

function Test-Port([int]$p) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue)
}

function Test-PyScript([string]$pat) {
    try {
        $hit = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like ("*" + $pat + "*") }
        return [bool]$hit
    } catch { return $false }
}

function Start-Svc([string]$name, [string]$file, [string]$tag) {
    try {
        $o = Join-Path $logs ($tag + ".log")
        $e = Join-Path $logs ($tag + ".err")
        Start-Process -FilePath "py" -ArgumentList @($file) -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $o -RedirectStandardError $e
        Write-Output ("[start] " + $name + "   -> logs/" + $tag + ".log")
    } catch {
        Write-Output ("[FAIL ] " + $name + " : " + $_.Exception.Message)
    }
}

Write-Output ("root = " + $root)

if ($ReloadMcp) {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*mc_mcp.py*" } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Output ("[kill ] stale mcp server pid=" + $_.ProcessId + " (next session respawns it)")
        }
}

if (Test-Port 8765) { Write-Output "[ok   ] gateway   :8765 up" }
else { Start-Svc "gateway :8765" "gateway/agent_gateway.py" "gateway" }

if (Test-Port 8791) { Write-Output "[ok   ] skin srv  :8791 up" }
else { Start-Svc "skin srv :8791" "tools/skin_server.py" "skin_server" }

# maven mirror :8789 -- only needed when REBUILDING the mod. It is harmless when the box has
# no internet (it just answers 502 to everything), so we start it unconditionally and never
# let its failure stop the other pieces.
if (Test-Port 8789) { Write-Output "[ok   ] maven mir :8789 up" }
else { Start-Svc "maven mir :8789" "tools/maven_mirror.py" "maven_mirror" }

$meta = Join-Path $logs "acp_session.json"
$alive = $false
if (Test-Path $meta) {
    try {
        $j = Get-Content $meta -Raw | ConvertFrom-Json
        $pid0 = [int]$j.pid                       # 会话子进程（node ... dsh --profile mcacp）
        $serve = 0
        if ($j.PSObject.Properties.Name -contains "serve_pid") { $serve = [int]$j.serve_pid }
        $p0 = Get-CimInstance Win32_Process -Filter "ProcessId=$pid0" -ErrorAction SilentlyContinue
        # ★"这个 pid 存在"不等于"大脑活着"★ ✗（2026-09-28 实测栽过 ✓）：
        #   本机 pid 会**被复用** ✗ ⇒ stale pidfile 撞上新进程 ⇒ 原来这里报 `alive` ✗
        #   而实际 `acp_serve.py` 早没了 ✗ —— 我据此以为有大脑 ✓ 其实是聋的 ✗
        #   ⇒ 现在两条一起判 ✓：
        #     ① 记的会话子进程 pid ✓ 真的是一条 `dsh --profile mcacp`（或 acp_serve 自己）✓
        #     ② 若 pidfile 里有 `serve_pid`（v2.16 起会写 ✓）⇒ 会话子进程必须是**它的孩子** ✓
        #        （pid 复用**满足不了父子关系** ✓ 这条最硬 ✓）
        $okPid = [bool]($p0 -and (($p0.CommandLine -like "*mcacp*") -or ($p0.CommandLine -like "*acp_serve.py*")))
        if ($serve -gt 0) {
            $ps_ = Get-CimInstance Win32_Process -Filter "ProcessId=$serve" -ErrorAction SilentlyContinue
            $okServe = [bool]($ps_ -and ($ps_.CommandLine -like "*acp_serve.py*"))
            $okParent = [bool]($p0 -and ($p0.ParentProcessId -eq $serve))
            $alive = $okPid -and $okServe -and $okParent
        } else {
            $alive = $okPid
        }
    } catch { $alive = $false }
}
if ($alive) { Write-Output "[ok   ] acp serve alive" }
else {
    if (Test-Path $meta) { Write-Output "[stale] acp_session.json does not describe a live session (pid reuse / dead serve) -- restarting" }
    Start-Svc "acp serve" "tools/acp_serve.py" "acp_serve"
    # ★★必须先等"会话文件真的写出来"，再拉中继★★ ✗（2026-09-29 ✓ 电脑重启后实测栽过 ✓）
    #   现象 ✗：整机重启后跑 start_all ⇒ 三个端口都起来了 ✓ 而 **中继没起来** ✗
    #   真因 ✓：中继开头有个 **PRECHECK** ✗ 它要求 `logs/acp_session.json` **已经存在** ✓
    #     （见 `acp_talk.py`：`if not META.is_file(): print("PRECHECK FAIL: no acp_session.json")` ✓）
    #     ⇒ 而那张文件是 **acp_serve 起来之后才写** 的 ✓ ⇒ 两个进程**抢跑**✗ ⇒ 中继看到"文件还没有"
    #       ⇒ 直接退出 ✗ ⇒ 假人就**听不见也答不出** ✗（最坏的情况：看起来一切正常 ✗）
    #   ⇒ 口径 ✓：**等文件出现（最多 90 秒 ✓）** 再拉中继 ✓ 等不到就**大声说** ✗ 不许静默 ✓
    $waited = 0
    while ($waited -lt 90) {
        if (Test-Path $meta) { break }
        Start-Sleep -Seconds 3
        $waited += 3
    }
    if (Test-Path $meta) { Write-Output ("[wait ] session file appeared after " + $waited + "s -- now starting the relay") }
    else { Write-Output "[warn ] session file still missing after 90s -- starting the relay anyway (watch logs/acp_talk.err)" }
}

if (Test-PyScript "acp_talk.py") { Write-Output "[ok   ] acp talk  running" }
else { Start-Svc "acp talk (ears+mouth)" "tools/acp_talk.py" "acp_talk" }

Start-Sleep -Seconds 4
Write-Output "---- after ----"
foreach ($p in 8765, 8791, 8789) {
    if (Test-Port $p) { Write-Output ("[up   ] port " + $p) } else { Write-Output ("[down ] port " + $p) }
}
if (Test-PyScript "acp_talk.py") { Write-Output "[up   ] acp_talk process" } else { Write-Output "[down ] acp_talk process" }
if (Test-PyScript "acp_serve.py") { Write-Output "[up   ] acp_serve process" } else { Write-Output "[down ] acp_serve process" }
