@echo off
cd /d "%~dp0"
TITLE Legal Pleadings Processing - One-Click Launcher

echo ====================================================
echo      LEGAL PLEADINGS RAG ^& PROCESSING ENGINE
echo ====================================================
echo.
echo Starting automated setup...
echo.

REM Check Python
echo [1/5] Checking Python...
where python >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :PYTHON_OK
)
where py >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    goto :PYTHON_OK
)

echo ERROR: Python not found!
echo Please install Python from python.org
pause
exit /b

:PYTHON_OK
echo SUCCESS: Python found
echo.

REM Create venv if needed
echo [2/5] Checking Virtual Environment...
if not exist "backend\venv" (
    echo Creating virtual environment... Please wait...
    %PYTHON_CMD% -m venv backend\venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create venv
        pause
        exit /b
    )
    echo SUCCESS: Virtual environment created
    set INSTALL_DEPS=1
) else (
    echo SUCCESS: Virtual environment exists
    set INSTALL_DEPS=0
)
echo.

REM Install dependencies if needed
echo [3/5] Checking Dependencies...
if "%INSTALL_DEPS%"=="1" (
    echo Installing packages... This may take 2-5 minutes...
    call backend\venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -r backend\requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install packages
        pause
        exit /b
    )
    echo SUCCESS: Packages installed
) else (
    echo SUCCESS: Dependencies already installed
)
echo.

REM Initialize database
echo [4/5] Checking Database Initialization...
call backend\venv\Scripts\activate.bat
if exist "backend\scripts\setup_schema.py" (
    echo Running schema checks...
    python backend\scripts\setup_schema.py
)
echo Database checks complete.
echo.

REM Start server
echo [5/5] Starting Server...
echo Cleaning up port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo Launching server...
start /B python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

echo Waiting for server to start...
timeout /t 15 /nobreak >nul

REM Check if server is running
curl -s http://localhost:8000/ >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo ====================================================
    echo      SERVER IS RUNNING!
    echo      http://localhost:8000/docs
    echo ====================================================
    echo.
    powershell -Command "& {Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::MsgBox('Server is UP and RUNNING!\n\nAPI: http://localhost:8000/docs\n\nClick OK to keep running', 'Information', 'SUCCESS')}"
    echo.
    echo Press any key to STOP the server...
    pause >nul
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
    echo Server stopped.
) else (
    echo ERROR: Server failed to start
    powershell -Command "& {Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::MsgBox('Server failed to start!', 'Critical', 'ERROR')}"
)

pause
