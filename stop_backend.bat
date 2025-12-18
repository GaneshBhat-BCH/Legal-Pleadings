@echo off
TITLE COI Management Matching Engine - Stopping Server
echo ====================================================
echo      Stopping AI Backend Server
echo      COI Management Matching Engine
echo ====================================================

REM Navigate to the directory where this script is located
cd /d "%~dp0"

REM Check if port 8000 is occupied
netstat -ano | findstr :8000 >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Found process running on port 8000.
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
        echo [INFO] Terminating process with PID %%a...
        taskkill /F /PID %%a >nul 2>&1
    )
    timeout /t 1 >nul
    echo [SUCCESS] Backend server has been stopped.
) else (
    echo [INFO] No backend server found running on port 8000.
)

echo.
echo Press any key to exit . . .
pause >nul
