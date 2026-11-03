# watchdog.ps1 -- keep the five services alive (added 2026-09-29, user audit)
#
# WHY: the gateway is the ONLY exit for every dsh* command. If it stops, the brain sees
# EMPTY for everything -- and "EMPTY" cannot tell "bridge down" from "fake player gone"
# (that cost a slow diagnosis once).
#
# DESIGN: do NOT re-implement service logic here. Call tools/start_all.ps1, which is
# already idempotent (probes ports, starts whatever is missing). The watchdog is just
# "run start_all on a timer and log it" -- least code, hardest to break.
#
# NOTE (ASCII only on purpose): Windows PowerShell 5.1 reads .ps1 files as ANSI unless
# they carry a BOM, so a UTF-8 file with CJK comments fails to PARSE here. Keep this
# file ASCII. (Recorded as errata P126.)
#
# USAGE:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\watchdog.ps1            # once, exit
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\watchdog.ps1 -Loop 300  # every 300s
#
param(
    [int]$Loop = 0,
    [int]$EverySec = 300
)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Log = Join-Path $Root "logs\watchdog.log"

function Write-Log([string]$m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    # Write-Host, NOT Write-Output: a function's Write-Output goes into the function's
    # return value, so `[void](One-Round)` swallowed every log line (measured: the run
    # took 7s -- start_all really ran -- but nothing was printed or written).
    Write-Host $line
    try { Add-Content -Path $Log -Value $line -Encoding UTF8 } catch { }
}

function Check-Port([int]$p) {
    try { return [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction Stop) }
    catch { return $false }
}

function One-Round {
    # start_all.ps1 is already idempotent (it probes ports and starts only what is
    # missing), so the watchdog does NOT need its own probing -- and keeping one copy
    # of "what should be running" is the whole point. Just call it and log the tail.
    $sa = Join-Path $Root "tools\start_all.ps1"
    try {
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $sa 2>&1 | Out-String
        $tail = $out.Substring([Math]::Max(0, $out.Length - 300)).Trim()
        Write-Log ("start_all -> " + ($tail -replace "`r?`n", " | "))
    } catch {
        Write-Log ("start_all itself failed: " + $_.Exception.Message)
    }
    return $true
}

Write-Log "watchdog start (Loop=$Loop EverySec=$EverySec)"
if ($Loop -le 0) {
    [void](One-Round)
    Write-Log "single round done, exit"
    exit 0
}
while ($true) {
    [void](One-Round)
    Start-Sleep -Seconds ([Math]::Max(30, $EverySec))
}
