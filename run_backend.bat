@echo off
TITLE COI Management Matching Engine - Backend Server
echo ====================================================
echo      Starting AI Backend Server (FastAPI)
echo      COI Management Matching Engine
echo ====================================================

REM Navigate to the directory where this script is located
cd /d "%~dp0"

REM 1. Health Check
netstat -ano | findstr :8000 >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Port 8000 is occupied. Checking health...
    curl -s http://localhost:8000/ >nul 2>&1
    if %errorlevel% equ 0 (
        echo [SUCCESS] Backend is already running and HEALTHY.
        echo [INFO] API Documentation: http://localhost:8000/docs
        if "%~1"=="--background" exit /b
        echo.
        set /p RESTART="Do you want to restart the server anyway? (y/n): "
        if /i not "%RESTART%"=="y" exit /b
    ) else (
        echo [WARNING] Port 8000 is busy but the API is NOT responding.
    )
    
    echo [INFO] Freeing up port 8000...
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
        taskkill /F /PID %%a >nul 2>&1
    )
    timeout /t 2 >nul
)

REM 2. Background Option
if "%~1"=="--background" goto :START_SERVER

echo.
echo [1] Start server in this window
echo [2] Start server in background (Hidden)
echo.
set /p CHOICE="Choose an option (1/2): "

if "%CHOICE%"=="2" (
    echo [INFO] Starting backend in background via run_hidden.vbs...
    start wscript.exe run_hidden.vbs
    echo [SUCCESS] Backend launched! You can close this window.
    timeout /t 3 >nul
    exit /b
)

:START_SERVER
REM Check if venv exists
if not exist "backend\venv\Scripts\activate.bat" (
    echo [ERROR] Virtual Environment not found at backend\venv
    echo Please run 'setup_env.bat' first.
    pause
    exit /b
)

REM Activate Virtual Environment
echo [INFO] Activating Virtual Environment...
call backend\venv\Scripts\activate

REM Fast check for uvicorn
python -m uvicorn --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uvicorn not found in virtual environment.
    echo Please run 'setup_env.bat' to install dependencies.
    pause
    exit /b
)

REM Run Uvicorn Server
echo [INFO] Starting Uvicorn Server on port 8000...
echo [INFO] API Documentation: http://localhost:8000/docs
echo [INFO] Press Ctrl+C to stop the server.
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
echo.
pause
