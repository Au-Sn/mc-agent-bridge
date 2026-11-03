# bootstrap_toolchain.ps1 -- download a JDK17 + Gradle 8.1.1 for building the dshbridge mod
#
# WHEN TO USE
#   You just cloned the repo and have Java/Gradle, but NOT the bundled toolchain under mod/.
#   (This project's git history does NOT ship the ~300 MB toolchain; see mod/README.md.)
#
# WHAT IT DOES (idempotent: skips what already exists)
#   1) JDK 17  -> mod\jdk\  (zip kept as mod\jdk17.zip until extraction succeeds)
#   2) Gradle 8.1.1 -> mod\gdist\gradle-8.1.1\  (zip kept as mod\gradle-8.1.1-bin.zip)
#
# CHECKSUMS
#   SHA-256 is verified when the upstream publishes a sidecar (.sha256 / .sha256.txt);
#   otherwise pass -ExpectedJdkSha256 / -ExpectedGradleSha256, or -AllowUnverified for a
#   LOUD but unverified install. Never silently skip the check.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap_toolchain.ps1
#   powershell ... -File tools\bootstrap_toolchain.ps1 -Force      # re-download everything
#   powershell ... -File tools\bootstrap_toolchain.ps1 -JdkUrl <zip-url> -ExpectedJdkSha256 <hex>
#
# AFTER IT SUCCEEDS
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_jar.ps1
#
# ASCII ONLY ON PURPOSE (errata P126).

param(
    [switch]$Force,
    [switch]$AllowUnverified,
    [string]$JdkUrl = "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse",
    [string]$JdkSha256 = "",
    [string]$GradleUrl = "https://services.gradle.org/distributions/gradle-8.1.1-bin.zip",
    [string]$GradleSha256 = "",
    [string[]]$GradleSha256Url = @(
        "https://services.gradle.org/distributions/gradle-8.1.1-bin.zip.sha256")
)

$ErrorActionPreference = "Continue"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$mod = Join-Path $root "mod"
$jdkDir = Join-Path $mod "jdk"
$gdistDir = Join-Path $mod "gdist"
$jdkZip = Join-Path $mod "jdk17.zip"
$gradleZip = Join-Path $mod "gradle-8.1.1-bin.zip"

Write-Host ("root = " + $root)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-Sha256([string]$path) {
    return (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLowerInvariant()
}

function Assert-Sha256([string]$path, [string]$expected, [string]$label) {
    $got = Get-Sha256 $path
    if (-not $expected) {
        if ($AllowUnverified) {
            Write-Host ("[WARN] " + $label + " sha256 NOT verified (AllowUnverified). got=" + $got)
            return $true
        }
        Write-Host ("[FAIL] " + $label + ": no checksum available and -AllowUnverified not set.")
        Write-Host "       pass -ExpectedJdkSha256/-ExpectedGradleSha256, or use -AllowUnverified."
        Write-Host ("       sha256(" + (Split-Path -Leaf $path) + ") = " + $got)
        return $false
    }
    if ($got -ne $expected.ToLowerInvariant()) {
        Write-Host ("[FAIL] " + $label + " sha256 mismatch")
        Write-Host ("       expected = " + $expected)
        Write-Host ("       actual   = " + $got)
        return $false
    }
    Write-Host ("[ok  ] " + $label + " sha256 verified = " + $got)
    return $true
}

function Download([string]$url, [string]$dest, [string]$label) {
    Write-Host ("[down] " + $label)
    Write-Host ("       " + $url)
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing -TimeoutSec 300
    } catch {
        Write-Host ("[FAIL] download failed: " + $_.Exception.Message)
        Write-Host ("       manual option: download " + $url)
        Write-Host ("       and save it as " + $dest + " then re-run this script.")
        return $false
    }
    if (-not (Test-Path $dest)) {
        Write-Host ("[FAIL] download produced no file: " + $dest)
        return $false
    }
    Write-Host ("[ok  ] saved " + $dest + " (" + (Get-Item $dest).Length + " B)")
    return $true
}

function Fetch-Sha256([string[]]$urls) {
    foreach ($u in $urls) {
        try {
            $txt = (Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 30).Content
            $m = [regex]::Match([string]$txt, "([0-9a-fA-F]{64})")
            if ($m.Success) {
                Write-Host ("[ok  ] checksum from " + $u)
                return $m.Groups[1].Value
            }
        } catch {
            Write-Host ("[info] no checksum at " + $u)
        }
    }
    return ""
}

function Expand-Zip([string]$zip, [string]$destDir, [string]$label) {
    Write-Host ("[unzip] " + $label + " -> " + $destDir)
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    try {
        Expand-Archive -LiteralPath $zip -DestinationPath $destDir -Force
    } catch {
        Write-Host ("[FAIL] unzip failed: " + $_.Exception.Message)
        return $false
    }
    return $true
}

# ---- JDK 17 ----------------------------------------------------------------------
$jdkReady = Get-ChildItem -Path $jdkDir -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "bin\javac.exe") } |
    Select-Object -First 1
if ($jdkReady -and -not $Force) {
    Write-Host ("[skip] JDK already present: " + $jdkReady.FullName)
} else {
    if (-not (Test-Path $jdkZip) -or $Force) {
        if (-not (Download $JdkUrl $jdkZip "JDK 17 (Adoptium Temurin, zip)")) { exit 1 }
    } else {
        Write-Host ("[skip] using existing " + $jdkZip)
    }
    if (-not $JdkSha256) {
        $JdkSha256 = Fetch-Sha256 @($JdkUrl + ".sha256.txt", $JdkUrl + ".sha256")
    }
    if (-not (Assert-Sha256 $jdkZip $JdkSha256 "JDK zip")) { exit 1 }
    New-Item -ItemType Directory -Force -Path $jdkDir | Out-Null
    if (-not (Expand-Zip $jdkZip $jdkDir "JDK")) { exit 1 }
    $jdkReady = Get-ChildItem -Path $jdkDir -Directory | Where-Object {
        Test-Path (Join-Path $_.FullName "bin\javac.exe")
    } | Select-Object -First 1
    if (-not $jdkReady) {
        Write-Host "[FAIL] JDK zip extracted but no bin\javac.exe found under mod\jdk"
        exit 1
    }
    Write-Host ("[ok  ] JDK ready: " + $jdkReady.FullName)
}

# ---- Gradle 8.1.1 ----------------------------------------------------------------
$gradleReady = Test-Path (Join-Path $gdistDir "gradle-8.1.1\bin\gradle.bat")
if ($gradleReady -and -not $Force) {
    Write-Host ("[skip] Gradle already present: " + (Join-Path $gdistDir "gradle-8.1.1"))
} else {
    if (-not (Test-Path $gradleZip) -or $Force) {
        if (-not (Download $GradleUrl $gradleZip "Gradle 8.1.1 (bin zip)")) { exit 1 }
    } else {
        Write-Host ("[skip] using existing " + $gradleZip)
    }
    if (-not $GradleSha256) {
        $GradleSha256 = Fetch-Sha256 $GradleSha256Url
    }
    if (-not (Assert-Sha256 $gradleZip $GradleSha256 "Gradle zip")) { exit 1 }
    if (-not (Expand-Zip $gradleZip $gdistDir "Gradle")) { exit 1 }
    if (-not (Test-Path (Join-Path $gdistDir "gradle-8.1.1\bin\gradle.bat"))) {
        Write-Host "[FAIL] Gradle zip extracted but bin\gradle.bat not found under mod\gdist\gradle-8.1.1"
        exit 1
    }
    Write-Host ("[ok  ] Gradle ready: " + (Join-Path $gdistDir "gradle-8.1.1"))
}

# ---- summary ---------------------------------------------------------------------
Write-Host ""
Write-Host "[done] toolchain is ready. Toolchain checksums are recorded in the download step above."
Write-Host "       next: powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_jar.ps1"
Write-Host "       (set env DSH_JDK_HOME / DSH_GRADLE_HOME to use a toolchain elsewhere)"
exit 0
