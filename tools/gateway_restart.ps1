# gateway_restart.ps1 -- restart the gateway safely: KILL THE OLD ONE FIRST, then start one.
#
# User instruction (2026-11-01): "when starting a new gateway, remember to kill the old one".
#
# Why: a leftover gateway keeps port 8765 busy, and two gateways connected to the same
# CC computer fight over the single command lane -> fake timeouts / mixed-up replies.
#
# NOTE: this file is deliberately ASCII-only. PowerShell 5.1 reads a BOM-less UTF-8 file
#       as ANSI, and non-ASCII text breaks the parser (hit once already).
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\gateway_restart.ps1
#   powershell ... -File tools\gateway_restart.ps1 -Check
param(
    [switch]$Check,
    [int]$Port = 8765
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Get-Gateways {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match 'agent_gateway\.py') } |
        Select-Object ProcessId, CommandLine
}

$found = @(Get-Gateways)
Write-Output ("gateways running: {0}" -f $found.Count)
foreach ($p in $found) {
    $cmd = ($p.CommandLine -replace '\s+', ' ')
    if ($cmd.Length -gt 110) { $cmd = $cmd.Substring(0, 110) }
    Write-Output ("  PID {0}: {1}" -f $p.ProcessId, $cmd)
}

if ($Check) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conn) { Write-Output ("port {0} listening (PID {1})" -f $Port, ($conn.OwningProcess -join ',')) }
    else { Write-Output ("port {0} not listening" -f $Port) }
    return
}

# step 1: kill the old ones
foreach ($p in $found) {
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        Write-Output ("  [kill] PID {0}" -f $p.ProcessId)
    } catch {
        Write-Output ("  [kill-failed] PID {0}: {1}" -f $p.ProcessId, $_.Exception.Message)
    }
}
Start-Sleep -Milliseconds 700
$left = @(Get-Gateways).Count
Write-Output ("remaining after kill: {0}" -f $left)
if ($left -gt 0) {
    Write-Output '[FAIL] old gateway still alive; handle it manually before starting a new one'
    exit 1
}

# step 2: the port must be free
$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Write-Output ("[FAIL] port {0} still held by PID {1}" -f $Port, ($conn.OwningProcess -join ','))
    exit 1
}
Write-Output ("port {0} is free" -f $Port)

# step 3: start exactly one
$log = Join-Path $root 'logs\gateway.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$argList = @('-u', '-X', 'utf8', 'gateway\agent_gateway.py', '--port', "$Port",
             '--root', 'cc-tweaked', '--quiet')
$proc = Start-Process -FilePath 'py' -ArgumentList $argList -WorkingDirectory $root `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru -WindowStyle Hidden
Write-Output ("  [start] PID {0} -> log {1}" -f $proc.Id, $log)

Start-Sleep -Seconds 8
$alive = @(Get-Gateways).Count
Write-Output ("gateways running now: {0} (must be exactly 1)" -f $alive)
if ($alive -ne 1) { exit 1 }
Write-Output 'GW OK'
exit 0
