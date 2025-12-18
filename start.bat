@echo off
TITLE COI Management Matching Engine - Quick Start
cd /d "%~dp0"

echo ====================================================
echo      COI Management Matching Engine
echo      Quick Start Launcher
echo ====================================================
echo.
echo [1] Run FULL SETUP (Install Python deps, Init DB, Start Server)
echo [2] Start BACKEND SERVER only
echo [3] Run AUTOMATED START (PowerShell version - Replaces VBS)
echo.

set /p CHOICE="Choose an option (1/2/3): "

if "%CHOICE%"=="1" (
    echo [INFO] Launching Simple Setup via PowerShell...
    powershell -ExecutionPolicy Bypass -File setup_simple.ps1
    goto :EOF
)

if "%CHOICE%"=="2" (
    call run_backend.bat
    goto :EOF
)

if "%CHOICE%"=="3" (
    echo [INFO] launching via PowerShell...
    powershell -ExecutionPolicy Bypass -File start_project.ps1
    goto :EOF
)

echo Invalid choice.
pause
