@echo off
TITLE COI Management Matching Engine - Environment Setup
echo ====================================================
echo      Setting up AI Backend Environment
echo      COI Management Matching Engine
echo ====================================================

cd /d "%~dp0"

REM 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ and check "Add to PATH" during installation.
    pause
    exit /b
)

REM 2. Create Virtual Environment if it doesn't exist
if not exist "backend\venv" (
    echo [INFO] Creating Virtual Environment (backend/venv)...
    python -m venv backend\venv
    set NEEDS_INSTALL=true
) else (
    echo [INFO] Virtual Environment already exists.
    if "%~1"=="--auto" (
        set NEEDS_INSTALL=false
    ) else (
        set /p REINSTALL="Do you want to re-install/update dependencies? (y/n): "
    )
)

if /i "%REINSTALL%"=="y" set NEEDS_INSTALL=true

REM 3. Install Dependencies if needed
if "%NEEDS_INSTALL%"=="true" (
    echo [INFO] Installing/Updating requirements...
    call backend\venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install -r backend\requirements.txt
) else (
    echo [INFO] Skipping dependency installation for speed.
)

REM 4. Check .env
if not exist "backend\.env" (
    echo.
    echo [WARNING] backend\.env file is MISSING!
    echo Please create it using the template or copy your API keys.
) else (
    echo [INFO] .env file found.
)

echo.
echo ====================================================
echo      Setup Complete! 
echo ====================================================

if "%~1"=="--auto" exit /b

set /p RUN_INIT="Do you want to initialize the database now? (y/n): "
if /i "%RUN_INIT%"=="y" (
    call init_db.bat
)

echo.
echo You can now use 'run_backend.bat' to start the server.
pause
