#!/usr/bin/env powershell
<#
.SYNOPSIS
  soak_night.ps1 -- D3 "3h x 3 nights" unattended night runner (task-8, 2026-11-02)

.WHY
  D3 requires "3 continuous hours (or 2000 calls) without falling / losing items /
  getting stuck". A single 20/45 min run is only in-window evidence; to make it
  "3 nights" somebody must babysit it. This script is that babysitter:
  every night it checks preconditions (bridge health / Bot survival / platform
  anchor / idle off / placeable item), runs tools/soak_suite.py, reads the
  scorecard, and STOPS IMMEDIATELY on any non-PASS night. Only 3 PASS nights
  write state/soak_night_summary.json.

.FLOW (per night)
  1) health / dshver / freeze check (code freeze: "change implementation
     mid-series" aborts the whole night plan)
  2) digest: bot exists, mode=survival, start position within 16 blocks of anchor
  3) dshidle off (unattended: it must not stroll off the platform)
  4) record events cursor (oracle is incremental; no ring clear needed)
  5) run tools/soak_suite.py (default mixed 180 min / radius 3 / platform mode)
  6) read state/soak_scorecard.json:
       PASS   -> archive to state/soak_scorecard_night<N>_<ts>.json, continue
       FAIL/INCONCLUSIVE/nonzero exit -> archive ..._night<N>_FAIL_<ts>.json,
                                         print reason, exit 1 (failure-stop)
  7) all PASS -> write state/soak_night_summary.json (nights/calls/full_bar/evidence), exit 0

.USAGE
  # 0) code freeze manifest first (offline, no game):
  py tools/soak_suite.py --freeze write
  # 1) DRY-RUN: validate params/files/freeze only (offline; no game contact)
  powershell -NoProfile -ExecutionPolicy Bypass -File tools/soak_night.ps1 -DryRun -Offline
  # same, but also do read-only game preflight (does not run soak):
  powershell -NoProfile -ExecutionPolicy Bypass -File tools/soak_night.ps1 -DryRun
  # 2) real unattended run: 3 nights x 180 minutes
  powershell -NoProfile -ExecutionPolicy Bypass -File tools/soak_night.ps1
  # 3) Task Scheduler registration (example; this script does NOT register itself
  #    and never restarts the game):
  schtasks /Create /TN "dsh-soak-night" /SC DAILY /ST 02:00 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\tools\soak_night.ps1" /F
  #    Risk: the game must stay running with Bot on the platform anchor; D4
  #    (restart self-healing) is not done => a crash means a wasted night.
  #    This script does NOT restart/kill anything; on NIGHT FAIL a human fixes it.

.SAFETY
  Read-only preflight + only calls the EXISTING tools/soak_suite.py interface.
  It never kills processes, never restarts the game, never writes git, never
  touches mod sources; failure-stop means it cannot make things worse over night.
#>
[CmdletBinding()]
param(
    [int]$Nights = 3,
    [double]$Minutes = 180,
    [double]$Interval = 30,
    [int]$Radius = 3,
    [int]$Seed = 7,
    [string]$Anchor = "4152,71,13",
    [ValidateSet("mixed", "idle", "walk", "work")]
    [string]$Profile = "mixed",
    [int]$MaxCalls = 2000,
    [string]$PythonExe = "py",
    [string]$FreezeFile = "state/soak_freeze.json",
    [bool]$AllowVoidPlatform = $true,
    [switch]$DryRun,
    [switch]$Offline,
    # For OFFLINE JUDGES only: simulate night N failing => must failure-stop.
    [int]$SimulateFailNight = 0
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "tools/soak_suite.py"))) {
    $Root = (Get-Location).Path
}
Set-Location $Root
$LogDir = Join-Path $Root "logs"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$NightLog = Join-Path $LogDir ("soak_night_" + $Stamp + ".log")
$script:LogPath = $null

# ---------- logging (DryRun prints to console only, writes nothing) ----------
function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    if ($script:LogPath) {
        Add-Content -Path $script:LogPath -Value $line -Encoding utf8
    }
}

function Fail([string]$msg, [int]$code = 2) {
    Write-Log ("FAIL: " + $msg)
    if ($script:LogPath) {
        Add-Content -Path $script:LogPath -Value ("FAIL: " + $msg) -Encoding utf8
    }
    exit $code
}

function Say-Dry([string]$msg) {
    # offline judges match on this "DRYRUN " prefix
    Write-Host ("DRYRUN " + $msg)
}

# ---------- python bridge: read-only preflight returning one JSON line ----------
function Invoke-PyJson([string]$code) {
    $raw = & $PythonExe -B -u -X utf8 -c $code 2>&1
    $rc = $LASTEXITCODE
    $lines = @($raw | ForEach-Object { "$_" })
    $jsonLine = $lines | Where-Object { $_ -like "JSON:*" } | Select-Object -Last 1
    if (-not $jsonLine) {
        throw ("python produced no JSON: line (rc=" + $rc + "): " + ($lines -join " | "))
    }
    return ($jsonLine.Substring(5).Trim() | ConvertFrom-Json)
}

$PreflightPy = @'
import sys, json, re
sys.path.insert(0, "tools")
import direct as D
r = {}
try:
    r["health"] = D.health(timeout=2.0)
except Exception as exc:
    r["health"] = "ERR:%s" % (type(exc).__name__,)
h = r["health"] or ""
r["health_ok"] = ("ok" in h)
try:
    v = D.post("dshver") or ""
except Exception:
    v = ""
m = re.search(r"version=([\w.\-]+)", v)
r["version"] = m.group(1) if m else None
try:
    t = D.post("dshdigest 1") or ""
except Exception:
    t = ""

def g(k):
    m = re.search(k + r"=([^\s]+)", t)
    return m.group(1) if m else None

r["pos"] = g("pos")
r["mode"] = g("mode")
r["items"] = g("items")
r["hp"] = g("hp")
r["onground"] = g("onground")
try:
    e = D.post("dshevents") or ""
except Exception:
    e = ""
m = re.search(r"cursor=(\d+)", e)
r["cursor"] = int(m.group(1)) if m else None
try:
    r["idle"] = D.post("dshidle status") or ""
except Exception:
    r["idle"] = ""
print("JSON:" + json.dumps(r, ensure_ascii=False))
'@

$IdleOffPy = @'
import sys
sys.path.insert(0, "tools")
import direct as D
print(D.post("dshidle off"))
print(D.post("dshidle status"))
'@

function Get-Anchors {
    $parts = $Anchor -split ","
    return @([int]$parts[0], [int]$parts[1], [int]$parts[2])
}

function Test-Preflight([bool]$readOnly) {
    $axes = Get-Anchors
    $ax = $axes[0]
    $az = $axes[2]
    $pre = Invoke-PyJson $PreflightPy
    if (-not $pre.health_ok) { throw ("bridge 8766 not reachable: " + $pre.health) }
    if (-not $pre.version) { throw "dshver unavailable (/cmd lane broken)" }
    if (-not $pre.pos) { throw "dshdigest unavailable (Bot offline?)" }
    if ($pre.mode -ne "survival") { throw ("Bot mode=" + $pre.mode + " (survival required; Lead sets it)") }
    if ($null -eq $pre.cursor) { throw "dshevents unreadable (death oracle impossible)" }
    $p = ($pre.pos -split ",")
    $dx = [double]$p[0] - $ax
    $dz = [double]$p[2] - $az
    $dist = [math]::Sqrt($dx * $dx + $dz * $dz)
    if ($dist -gt 16.0) {
        throw ("Bot start " + $pre.pos + " is too far from anchor " + $Anchor +
            " (" + [math]::Round($dist, 1) + " > 16)")
    }
    if (-not $readOnly) {
        # unattended: idle MUST be off, otherwise it can stroll off the platform
        $null = & $PythonExe -B -u -X utf8 -c $IdleOffPy 2>&1
        if ($LASTEXITCODE -ne 0) { throw "dshidle off call failed" }
        $again = Invoke-PyJson $PreflightPy
        if ($again.idle -notmatch "humanoid=false") {
            throw ("after dshidle off, readback is not humanoid=false: " + $again.idle)
        }
    }
    return [pscustomobject]@{
        Version = $pre.version
        Pos     = $pre.pos
        Mode    = $pre.mode
        Items   = $pre.items
        Hp      = $pre.hp
        Cursor  = $pre.cursor
        Dist    = [math]::Round($dist, 2)
        Idle    = $pre.idle
    }
}

function Resolve-FreezePath {
    if ([System.IO.Path]::IsPathRooted($FreezeFile)) { return $FreezeFile }
    return (Join-Path $Root $FreezeFile)
}

function Test-Freeze {
    $freezePath = Resolve-FreezePath
    $out = & $PythonExe -B -u -X utf8 (Join-Path $Root "tools/soak_suite.py") --freeze check --freeze-file $freezePath 2>&1
    $rc = $LASTEXITCODE
    foreach ($ln in @($out)) { Write-Log ("  freeze| " + $ln) }
    if ($rc -ne 0) {
        throw ("code freeze check failed (rc=" + $rc + "); implementation changed mid-series?")
    }
}

function Get-SuiteArgs {
    $a = @(
        "-B", "-u", "-X", "utf8",
        (Join-Path $Root "tools/soak_suite.py"),
        "--profile", $Profile,
        "--minutes", ("{0}" -f $Minutes),
        "--interval", ("{0}" -f $Interval),
        "--radius", ("{0}" -f $Radius),
        "--seed", ("{0}" -f $Seed),
        "--anchor", $Anchor,
        "--max-calls", ("{0}" -f $MaxCalls)
    )
    if ($AllowVoidPlatform) { $a += "--allow-void-platform" }
    return $a
}

function Save-JsonNoBom([string]$path, $obj, [int]$depth = 8) {
    $json = $obj | ConvertTo-Json -Depth $depth
    try {
        [System.IO.File]::WriteAllText($path, $json, (New-Object System.Text.UTF8Encoding($false)))
    }
    catch {
        Set-Content -Path $path -Value $json -Encoding utf8
    }
}

# ==========================================================================
# parameter validation (DryRun must pass this too; a bad param wastes a night)
# ==========================================================================
function Assert-Params {
    if ($Nights -lt 1 -or $Nights -gt 7) { Fail ("-Nights must be 1..7 (got " + $Nights + ")") }
    if ($Minutes -lt 1 -or $Minutes -gt 480) { Fail ("-Minutes must be 1..480 (got " + $Minutes + ")") }
    if ($Interval -lt 5) { Fail ("-Interval must be >=5 (got " + $Interval + ")") }
    if ($Radius -lt 1 -or $Radius -gt 8) { Fail ("-Radius must be 1..8 (got " + $Radius + ")") }
    if ($MaxCalls -lt 1) { Fail ("-MaxCalls must be >=1 (got " + $MaxCalls + ")") }
    if ($Anchor -notmatch "^\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*$") {
        Fail ("-Anchor must be x,y,z (got '" + $Anchor + "')")
    }
    if ($SimulateFailNight -lt 0 -or $SimulateFailNight -gt $Nights) {
        Fail ("-SimulateFailNight must be 0..Nights (got " + $SimulateFailNight + ")")
    }
    if ($SimulateFailNight -gt 0 -and (-not $DryRun -or -not $Offline)) {
        Fail "-SimulateFailNight requires -DryRun -Offline (never touches the game)"
    }
    foreach ($rel in @("tools/soak_suite.py", "tools/soak_suite_test.py", "tools/d3_soak.py")) {
        if (-not (Test-Path (Join-Path $Root $rel))) { Fail ("missing implementation file " + $rel) }
    }
    $pyCmd = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if (-not $pyCmd) { Fail ("python executable not found: " + $PythonExe) }
    $ver = & $PythonExe --version 2>&1
    if ($LASTEXITCODE -ne 0) { Fail ("python does not start: " + $PythonExe) }
    Write-Log ("python: " + ($ver -join " "))
}

# ==========================================================================
# main
# ==========================================================================
Write-Host ("== soak_night.ps1: nights=$Nights minutes=$Minutes profile=$Profile radius=$Radius anchor=$Anchor ==")
if (-not $DryRun) {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
    $script:LogPath = $NightLog
    Write-Log ("night log: " + $NightLog)
}
Assert-Params
$expectedAction = [math]::Round(65.6 * $Minutes, 0)
Write-Log ("expected action calls ~ " + $expectedAction + " (full-bar gate " + $MaxCalls + ")")
Write-Log ("params: DryRun=" + $DryRun + " Offline=" + $Offline + " AllowVoidPlatform=" + $AllowVoidPlatform)

# code freeze check (both modes; DryRun is not allowed to bless a changing impl)
try {
    Test-Freeze
}
catch {
    Fail ("" + $_.Exception.Message)
}

# preflight
if ($Offline) {
    Write-Log "Offline mode: skip game preflight (local params/files/freeze only)"
}
else {
    try {
        $pre = Test-Preflight ([bool]$DryRun)
        Write-Log ("preflight OK Bot=" + $pre.Pos + " mode=" + $pre.Mode + " items=" + $pre.Items +
            " hp=" + $pre.Hp + " version=" + $pre.Version +
            " anchor_dist=" + $pre.Dist + " cursor=" + $pre.Cursor)
    }
    catch {
        Fail ("preflight failed: " + $_.Exception.Message)
    }
}

# DryRun / Simulate: print the plan only; run nothing; write no state
$suiteArgs = Get-SuiteArgs
$planCmd = ($PythonExe + " " + (($suiteArgs | ForEach-Object { "$_" }) -join " "))
if ($DryRun) {
    for ($i = 1; $i -le $Nights; $i++) {
        Say-Dry ("PLAN {0}/{1}: {2}" -f $i, $Nights, $planCmd)
        Say-Dry ("      archive -> state/soak_scorecard_night{0}_<ts>.json  (FAIL -> ..._FAIL_<ts>.json)" -f $i)
        if ($SimulateFailNight -eq $i) {
            Say-Dry ("STOP night {0}/{1} simulated FAIL => failure-stop (remaining nights skipped, exit 1)" -f $i, $Nights)
            Write-Host ("SIM: night {0} FAIL (H_STUCK simulated) => failure-stop, exit 1" -f $i)
            exit 1
        }
    }
    Say-Dry ("DRYRUN OK nights={0} minutes={1} radius={2} anchor={3} expected_action~{4} (sim_all_pass)" -f $Nights, $Minutes, $Radius, $Anchor, $expectedAction)
    Write-Host "NIGHT_DRYRUN ok=1"
    exit 0
}

# real run: nights sequentially; failure-stop
$results = @()
for ($night = 1; $night -le $Nights; $night++) {
    Write-Log ("================ NIGHT " + $night + "/" + $Nights + " START ================")
    try {
        Test-Freeze
        $pre = Test-Preflight $false
        Write-Log ("NIGHT " + $night + " preflight OK Bot=" + $pre.Pos + " mode=" + $pre.Mode +
            " items=" + $pre.Items + " cursor=" + $pre.Cursor +
            " anchor_dist=" + $pre.Dist + " (events cursor recorded; oracle is incremental)")
    }
    catch {
        Write-Log ("NIGHT " + $night + " preflight failed: " + $_.Exception.Message)
        $failArch = Join-Path $Root ("state/soak_scorecard_night" + $night + "_FAIL_" + $Stamp + ".json")
        $cur = Join-Path $Root "state/soak_scorecard.json"
        if (Test-Path $cur) { Copy-Item $cur $failArch -Force }
        Write-Log ("NIGHT FAIL night=" + $night + " reason=preflight archive=" + $failArch)
        exit 1
    }
    $t0 = Get-Date
    & $PythonExe @suiteArgs 2>&1 | Tee-Object -FilePath $NightLog -Append | Out-Host
    $rc = $LASTEXITCODE
    $durMin = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
    $scorePath = Join-Path $Root "state/soak_scorecard.json"
    if (-not (Test-Path $scorePath)) {
        Write-Log ("NIGHT FAIL night=" + $night + ": no scorecard (runner crashed?)")
        exit 1
    }
    $sc = Get-Content $scorePath -Raw -Encoding utf8 | ConvertFrom-Json
    $hardCodes = @($sc.hard_failures | ForEach-Object { $_.code }) -join ","
    $incCodes = @($sc.inconclusive_reasons | ForEach-Object { $_.code }) -join ","
    Write-Log ("NIGHT " + $night + " result: verdict=" + $sc.verdict + " exit=" + $sc.exit_code +
        " calls=" + $sc.calls + " action=" + $sc.calls_action +
        " full_bar=" + $sc.full_bar + " full_spec=" + $sc.full_spec_mixed_3h +
        " gaps=" + $sc.oracle.gaps + " hard=[" + $hardCodes + "] inc=[" + $incCodes + "] dur=" + $durMin + "min")
    $results += [pscustomobject]@{
        night       = $night
        verdict     = $sc.verdict
        exit_code   = $sc.exit_code
        calls       = $sc.calls
        calls_action = $sc.calls_action
        full_bar    = $sc.full_bar
        full_spec   = $sc.full_spec_mixed_3h
        gaps        = $sc.oracle.gaps
        hard        = $hardCodes
        inconclusive = $incCodes
        duration_sec = $sc.duration_sec
        generated_at = $sc.generated_at
    }
    if ($rc -ne 0 -or $sc.verdict -ne "PASS") {
        $failArch = Join-Path $Root ("state/soak_scorecard_night" + $night + "_FAIL_" + $Stamp + ".json")
        Copy-Item $scorePath $failArch -Force
        Write-Log ("NIGHT FAIL night=" + $night + " verdict=" + $sc.verdict +
            " rc=" + $rc + " reason: hard=[" + $hardCodes + "] inc=[" + $incCodes + "] archive=" + $failArch)
        Write-Log "FAILURE-STOP: remaining nights skipped (no retry-to-green, no masking)"
        exit 1
    }
    $okArch = Join-Path $Root ("state/soak_scorecard_night" + $night + "_" + $Stamp + ".json")
    Copy-Item $scorePath $okArch -Force
    Write-Log ("NIGHT PASS night=" + $night + " archive=" + $okArch)
}

# all nights passed -> summary (only a full 3-night PASS is "3-night mechanism green")
$passed = @($results | Where-Object { $_.verdict -eq "PASS" }).Count
$summary = [pscustomobject]@{
    schema            = "dshbridge/soak_night_summary@1"
    generated_at      = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
    nights            = $results
    nights_planned    = $Nights
    nights_passed     = $passed
    all_pass          = ($passed -eq $Nights)
    profile           = $Profile
    minutes_per_night = $Minutes
    radius            = $Radius
    anchor            = $Anchor
    max_calls         = $MaxCalls
    allow_void_platform = $AllowVoidPlatform
    freeze_file       = $FreezeFile
    night_log         = $NightLog}
$sumPath = Join-Path $Root "state/soak_night_summary.json"
Save-JsonNoBom $sumPath $summary 8
Write-Log ("NIGHT ALL PASS nights=" + $Nights + " summary=" + $sumPath)
Write-Host ("NIGHT_ALL_PASS ok=1 nights=" + $Nights)
exit 0
