@echo off
TITLE COI Management Matching Engine - Database Init
echo ====================================================
echo      Initializing Database (PostgreSQL)
echo      COI Management Matching Engine
echo ====================================================

cd /d "%~dp0"

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

REM Run DB initialization
echo [INFO] Running init_db.py...
python backend/init_db.py

echo.
echo ====================================================
echo      Database Initialization Complete!
echo ====================================================
if "%~1"=="--auto" exit /b
pause
