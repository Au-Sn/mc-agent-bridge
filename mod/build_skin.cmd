@echo off
REM Temporary build script. ASCII only: cmd reads this file as GBK, so Chinese
REM comments here become garbage commands (measured 2026-09-20).
REM
REM 79.534: no absolute machine paths any more. Toolchain resolution:
REM   JDK    : env DSH_JDK_HOME   ->  <this script dir>\jdk\jdk-17.0.20.1+1  -> error
REM   Gradle : env DSH_GRADLE_HOME ->  <this script dir>\gdist\gradle-8.1.1 -> error
REM   Mirror : only when env DSH_MAVEN_MIRROR is set (init script passed then)
REM See INSTALL.md (repo root) / mod\README.md for prerequisites; tools\bootstrap_toolchain.ps1 can fetch the toolchain.
setlocal

set "MODDIR=%~dp0"
if "%MODDIR:~-1%"=="\" set "MODDIR=%MODDIR:~0,-1%"

if defined DSH_JDK_HOME (
  set "JAVA_HOME=%DSH_JDK_HOME%"
) else (
  if exist "%MODDIR%\jdk\jdk-17.0.20.1+1\bin\javac.exe" (
    set "JAVA_HOME=%MODDIR%\jdk\jdk-17.0.20.1+1"
  )
)
if not defined JAVA_HOME goto :nojdk

if defined DSH_GRADLE_HOME (
  set "GRADLE=%DSH_GRADLE_HOME%\bin\gradle.bat"
) else (
  if exist "%MODDIR%\gdist\gradle-8.1.1\bin\gradle.bat" (
    set "GRADLE=%MODDIR%\gdist\gradle-8.1.1\bin\gradle.bat"
  )
)
if not exist "%GRADLE%" goto :nogradle

cd /d "%MODDIR%"
if defined DSH_MAVEN_MIRROR (
  "%GRADLE%" build --no-daemon --console=plain --init-script "%MODDIR%\mirror.init.gradle" > build_skin.log 2>&1
) else (
  "%GRADLE%" build --no-daemon --console=plain > build_skin.log 2>&1
)
echo EXIT=%ERRORLEVEL%
exit /b %ERRORLEVEL%

:nodjk
echo [FAIL] no JDK17 found. Set DSH_JDK_HOME (dir with bin\javac.exe) or see INSTALL.md / mod\README.md
exit /b 2

:nogradle
echo [FAIL] no Gradle 8.1.1 found. Set DSH_GRADLE_HOME (dir with bin\gradle.bat) or see INSTALL.md / mod\README.md
exit /b 2
