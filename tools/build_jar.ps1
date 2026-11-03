# build_jar.ps1 -- build the dshbridge mod jar (portable recipe; see errata P150)
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_jar.ps1
#   powershell ... -File tools\build_jar.ps1 -SeedCache   # first time / after cache loss
#
# TOOLCHAIN RESOLUTION (79.534: works on other machines too)
#   JDK    : env DSH_JDK_HOME  ->  mod\jdk\jdk-17.0.20.1+1  ->  clear error
#   Gradle : env DSH_GRADLE_HOME ->  mod\gdist\gradle-8.1.1 ->  clear error
#   (no toolchain? run tools\bootstrap_toolchain.ps1 once, or read mod\README.md)
#
# MAVEN MIRROR IS OPTIONAL (79.534)
#   env DSH_MAVEN_MIRROR set     -> use that mirror (e.g. http://127.0.0.1:8789)
#   env not set + :8789 listening -> auto-use http://127.0.0.1:8789 (keeps the old local recipe)
#   env not set + no listener     -> NO mirror; Gradle uses public repositories
#                                   (maven.minecraftforge.net / Maven Central / BMCLAPI)
#
# WHY THIS SCRIPT EXISTS (measured 2026-10-01, errata P150):
#   Under this session's file sandbox, java.exe spawned by Gradle is DENIED writes to
#   C:\Users\Administrator\.gradle (native-platform.dll.lock access denied) -> Gradle dies
#   with "Could not initialize native services". So GRADLE_USER_HOME must be a REAL dir
#   inside this workspace (default: <workspace-parent>\.gradle-home, override with
#   env DSH_GRADLE_USER_HOME).
#
# AFTER A SUCCESSFUL BUILD
#   py tools\install_mod.py        # verifies the new strings are really in the jar
#   then restart Minecraft (mod changes only load on a full process restart)
#
# ASCII ONLY ON PURPOSE (errata P126): PowerShell 5.1 decodes a BOM-less .ps1 as
# ANSI, so non-ASCII comments corrupt the script itself ("Unexpected token '}'").

param([switch]$SeedCache)

$ErrorActionPreference = "Continue"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$mod  = Join-Path $root "mod"
$ws   = Split-Path -Parent $root
$log  = Join-Path $root "logs\build_jar.log"

Write-Host ("root   = " + $root)

# ---- 1) JDK: env DSH_JDK_HOME -> mod\jdk\jdk-17.0.20.1+1 -> error -----------------
$jdk = $null
if ($env:DSH_JDK_HOME -and (Test-Path (Join-Path $env:DSH_JDK_HOME "bin\javac.exe"))) {
    $jdk = $env:DSH_JDK_HOME
} elseif (Test-Path (Join-Path $mod "jdk\jdk-17.0.20.1+1")) {
    $jdk = Join-Path $mod "jdk\jdk-17.0.20.1+1"
} else {
    Write-Host "[FAIL] no JDK17 found."
    Write-Host "       set env DSH_JDK_HOME (a JDK 17 home, has bin\javac.exe)"
    Write-Host "       or run: powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap_toolchain.ps1"
    Write-Host "       see: INSTALL.md (repo root) / mod\README.md  (section: Build prerequisites)"
    exit 2
}
Write-Host ("jdk    = " + $jdk)

# ---- 2) Gradle: env DSH_GRADLE_HOME -> mod\gdist\gradle-8.1.1 -> error ------------
$gdistRoot = $null
if ($env:DSH_GRADLE_HOME -and (Test-Path (Join-Path $env:DSH_GRADLE_HOME "bin\gradle.bat"))) {
    $gdistRoot = $env:DSH_GRADLE_HOME
} elseif (Test-Path (Join-Path $mod "gdist\gradle-8.1.1\bin\gradle.bat")) {
    $gdistRoot = Join-Path $mod "gdist\gradle-8.1.1"
} else {
    Write-Host "[FAIL] no Gradle 8.1.1 found."
    Write-Host "       set env DSH_GRADLE_HOME (a Gradle 8.1.1 install, has bin\gradle.bat)"
    Write-Host "       or run: powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap_toolchain.ps1"
    Write-Host "       see: INSTALL.md (repo root) / mod\README.md  (section: Build prerequisites)"
    exit 2
}
$gradle = Join-Path $gdistRoot "bin\gradle.bat"
Write-Host ("gradle = " + $gradle)

# ---- 3) Gradle user home: env DSH_GRADLE_USER_HOME -> <ws>\.gradle-home -----------
if ($env:DSH_GRADLE_USER_HOME) {
    $ghome = $env:DSH_GRADLE_USER_HOME
} else {
    $ghome = Join-Path $ws ".gradle-home"
}
Write-Host ("ghome  = " + $ghome)

if ($SeedCache) {
    $src = Join-Path $env:USERPROFILE ".gradle\caches"
    if (Test-Path $src) {
        Write-Host ("[seed ] robocopy " + $src + " -> " + $ghome + "\caches")
        robocopy $src (Join-Path $ghome "caches") /MIR /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
        Write-Host ("[seed ] robocopy exit=" + $LASTEXITCODE + "  (0-7 = success)")
    } else {
        Write-Host ("[seed ] no cache at " + $src + " -- gradle will download instead")
    }
}

New-Item -ItemType Directory -Force -Path $ghome | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null

# ---- 4) optional maven mirror ----------------------------------------------------
$mirror = $env:DSH_MAVEN_MIRROR
if (-not $mirror) {
    $listening = Get-NetTCPConnection -State Listen -LocalPort 8789 -ErrorAction SilentlyContinue
    if ($listening) {
        $mirror = "http://127.0.0.1:8789"
        Write-Host "[mirror] :8789 up -> auto DSH_MAVEN_MIRROR=$mirror"
    } else {
        Write-Host "[mirror] none (public repositories: maven.minecraftforge.net / Maven Central / BMCLAPI)"
    }
} else {
    Write-Host ("[mirror] DSH_MAVEN_MIRROR=" + $mirror)
}

# ---- 5) run gradle ---------------------------------------------------------------
$env:JAVA_HOME = $jdk
$env:GRADLE_USER_HOME = $ghome
if ($mirror) {
    $env:DSH_MAVEN_MIRROR = $mirror
} else {
    Remove-Item Env:\DSH_MAVEN_MIRROR -ErrorAction SilentlyContinue
}

$gargs = @("build", "--no-daemon", "--console=plain",
    "-Dorg.gradle.internal.http.connectionTimeout=20000",
    "-Dorg.gradle.internal.http.socketTimeout=45000")
if ($mirror -and (Test-Path (Join-Path $mod "mirror.init.gradle"))) {
    $gargs += "--init-script"
    $gargs += "mirror.init.gradle"
    $gargs += ("-PdshMirror=" + $mirror)
}

Push-Location $mod
& $gradle @gargs *>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
Pop-Location

Write-Host ("GRADLE_EXIT=" + $code)
if ($code -ne 0) {
    Write-Host "[FAIL] build failed -- read the tail of logs/build_jar.log"
    Write-Host "       (a native-services error here means GRADLE_USER_HOME escaped the workspace: P150)"
    Write-Host "       (network/mirror errors: INSTALL.md section on the optional Maven mirror)"
    exit 1
}

$jars = Get-ChildItem (Join-Path $mod "build\libs\dshbridge-*.jar") -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime
if (-not $jars) { Write-Host "[FAIL] no jar produced"; exit 1 }
$new = $jars | Select-Object -Last 1
Write-Host ("[ok  ] " + $new.Name + "  " + $new.Length + " B  " + $new.LastWriteTime)
Write-Host "[next] py tools\install_mod.py    then restart Minecraft"
exit 0
