@echo off
REM ============================================================
REM black_frame_detector 安装脚本 (Windows)
REM 版本: v1.0.0
REM 用法:
REM   install.bat          REM 安装
REM   install.bat --force  REM 强制覆盖安装
REM ============================================================

setlocal enabledelayedexpansion

set PLUGIN_NAME=black_frame_detector
set FORCE=0

if "%~1"=="--force" set FORCE=1
if "%~1"=="-f" set FORCE=1

echo ============================================
echo   黑帧夹帧检测插件 安装程序 v1.0.0
echo   兼容 DaVinci Resolve 17/18/19/20
echo ============================================

REM ============================================================
REM 检测Resolve安装路径
REM ============================================================
set INSTALL_BASE=%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit
set INSTALL_DIR=%INSTALL_BASE%\%PLUGIN_NAME%

echo.
echo 安装路径: %INSTALL_DIR%

if not exist "%INSTALL_BASE%" (
    echo.
    echo [警告] 未找到 DaVinci Resolve 脚本目录。
    echo 请确保已安装 DaVinci Resolve 并至少运行过一次。
    echo.
    set /p CONTINUE="是否手动指定安装路径? (y/N): "
    if /i "!CONTINUE!"=="y" (
        set /p INSTALL_BASE="请输入安装路径: "
        set INSTALL_DIR=!INSTALL_BASE!\%PLUGIN_NAME%
    ) else (
        exit /b 1
    )
)

REM ============================================================
REM 检测FFmpeg
REM ============================================================
echo.
echo [检查] 正在检查 FFmpeg...

where ffmpeg >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   [OK] FFmpeg 已安装
) else (
    echo   [WARN] FFmpeg 未安装
    echo   请先安装 FFmpeg:
    echo     winget install ffmpeg
    echo   或从 https://ffmpeg.org/download.html 下载
    echo   确保 ffmpeg.exe 所在目录已添加到 PATH 环境变量
)

REM ============================================================
REM 安装文件
REM ============================================================
echo.
echo [安装] 复制文件到 %INSTALL_DIR%...

if exist "%INSTALL_DIR%" (
    if %FORCE% EQU 1 (
        echo   [INFO] 强制覆盖已存在的安装...
        rmdir /s /q "%INSTALL_DIR%" 2>nul
    ) else (
        echo   [WARN] 目录已存在，使用 --force 强制覆盖安装
        pause
        exit /b 1
    )
)

REM 获取脚本所在目录
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

mkdir "%INSTALL_DIR%" 2>nul
mkdir "%INSTALL_DIR%\modules" 2>nul

copy "%PROJECT_DIR%\black_frame_detector.lua" "%INSTALL_DIR%\" >nul
copy "%PROJECT_DIR%\modules\config.lua" "%INSTALL_DIR%\modules\" >nul
copy "%PROJECT_DIR%\modules\version_compat.lua" "%INSTALL_DIR%\modules\" >nul
copy "%PROJECT_DIR%\modules\ffmpeg_runner.lua" "%INSTALL_DIR%\modules\" >nul
copy "%PROJECT_DIR%\modules\black_frame_analyzer.lua" "%INSTALL_DIR%\modules\" >nul
copy "%PROJECT_DIR%\modules\marker_manager.lua" "%INSTALL_DIR%\modules\" >nul
copy "%PROJECT_DIR%\modules\ui_bridge.lua" "%INSTALL_DIR%\modules\" >nul
copy "%PROJECT_DIR%\modules\report_generator.lua" "%INSTALL_DIR%\modules\" >nul

if exist "%PROJECT_DIR%\README.md" (
    copy "%PROJECT_DIR%\README.md" "%INSTALL_DIR%\" >nul
)

echo   [OK] 文件复制完成

REM ============================================================
REM 验证安装
REM ============================================================
echo.
echo [验证] 检查安装文件...

set ALL_OK=1

for %%f in (
    "black_frame_detector.lua"
    "modules\config.lua"
    "modules\version_compat.lua"
    "modules\ffmpeg_runner.lua"
    "modules\black_frame_analyzer.lua"
    "modules\marker_manager.lua"
    "modules\ui_bridge.lua"
    "modules\report_generator.lua"
) do (
    if exist "%INSTALL_DIR%\%%~f" (
        echo   [OK] %%~f
    ) else (
        echo   [FAIL] %%~f - 缺失
        set ALL_OK=0
    )
)

if %ALL_OK% EQU 1 (
    echo.
    echo ============================================
    echo   [OK] 安装成功!
    echo ============================================
    echo.
    echo   安装路径: %INSTALL_DIR%
    echo.
    echo   使用方法:
    echo     1. 启动 DaVinci Resolve
    echo     2. 打开一个项目和时间线
    echo     3. 菜单栏 - 工作区 - 脚本 - %PLUGIN_NAME%
    echo.
    echo   卸载方法:
    echo     删除目录 %INSTALL_DIR%
    echo.
) else (
    echo.
    echo [FAIL] 安装验证失败，部分文件缺失
    pause
    exit /b 1
)

pause
