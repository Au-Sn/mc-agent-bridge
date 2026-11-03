@echo off
chcp 65001 >nul
rem ============================================================
rem  MC Agent Bridge - 网关启动脚本（Windows 双击即用）
rem ============================================================
cd /d "%~dp0"

echo.
echo  正在启动 MC Agent Bridge 网关...
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py -u gateway\agent_gateway.py --port 8765 --root cc-tweaked --cli
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    python -u gateway\agent_gateway.py --port 8765 --root cc-tweaked --cli
    goto :eof
)

echo  [错误] 没找到 Python。请先安装 Python 3.8+ 并加入 PATH。
echo         下载： https://www.python.org/downloads/
pause
