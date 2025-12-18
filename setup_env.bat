@echo off
SETLOCAL EnableDelayedExpansion
TITLE COI Management Matching Engine - Environment Setup
echo ====================================================
echo      Setting up AI Backend Environment
echo      COI Management Matching Engine
echo ====================================================

cd /d "%~dp0"

REM --- 1. Check Python ---
set PYTHON_EXE=
where python >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_EXE=python
    goto :PYTHON_FOUND
)
where py >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_EXE=py
    goto :PYTHON_FOUND
)
where python3 >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_EXE=python3
    goto :PYTHON_FOUND
)

:PYTHON_NOT_FOUND
echo [WARNING] Python is not installed. Attempting to install via winget...
where winget >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] winget not found. Cannot auto-install Python.
    goto :MANUAL_INSTALL
)

echo [INFO] Installing Python 3.12...
winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
if !errorlevel! equ 0 (
    echo [SUCCESS] Python installed. Please RESTART this script to refresh PATH.
    powershell -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::MsgBox('Python has been installed! Please restart this setup script to continue.', 'Information,OkOnly', 'Installation Success')"
    pause
    exit /b
)

:MANUAL_INSTALL
echo [ERROR] Automated installation failed or winget is missing.
echo Please install Python 3.10+ manually from python.org and check "Add to PATH".
goto :ERROR_EXIT

:PYTHON_FOUND
echo [INFO] Using %PYTHON_EXE% for setup.
%PYTHON_EXE% --version

REM --- 2. Create Virtual Environment ---
if not exist "backend\venv" (
    echo [INFO] Creating Virtual Environment (backend/venv)...
    %PYTHON_EXE% -m venv backend\venv || goto :ERROR_EXIT
    set NEEDS_INSTALL=true
) else (
    echo [INFO] Virtual Environment already exists.
    if "%~1"=="--auto" (
        set NEEDS_INSTALL=false
    ) else (
        set /p REINSTALL="Do you want to re-install/update dependencies? (y/n): "
        if /i "!REINSTALL!"=="y" set NEEDS_INSTALL=true
    )
)

REM --- 3. Install Dependencies ---
if "!NEEDS_INSTALL!"=="true" (
    echo [INFO] Installing/Updating requirements...
    call backend\venv\Scripts\activate || goto :ERROR_EXIT
    python -m pip install --upgrade pip || goto :ERROR_EXIT
    python -m pip install -r backend\requirements.txt || goto :ERROR_EXIT
) else (
    echo [INFO] Skipping dependency installation for speed.
)

REM --- 4. Check .env ---
if not exist "backend\.env" (
    echo.
    echo [WARNING] backend\.env file is MISSING!
    echo Please create it using the template or copy your API keys.
) else (
    echo [INFO] .env file found.
)

REM --- 5. Check Tesseract ---
where tesseract >nul 2>&1
if !errorlevel! neq 0 (
    echo [WARNING] Tesseract OCR not found. Attempting to install via winget...
    where winget >nul 2>&1
    if !errorlevel! equ 0 (
        echo [INFO] Installing Tesseract OCR...
        winget install --id UB.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements
        echo [INFO] Tesseract installed.
    ) else (
        echo [ERROR] Tesseract missing and winget not found.
    )
) else (
    echo [INFO] Tesseract OCR found.
)

echo.
echo ====================================================
echo      Setup Complete! 
echo ====================================================

powershell -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::MsgBox('Environment setup completed successfully!', 'Information,OkOnly', 'Setup Success')"

if "%~1"=="--auto" exit /b

set /p RUN_INIT="Do you want to initialize the database now? (y/n): "
if /i "!RUN_INIT!"=="y" (
    call init_db.bat
    if !errorlevel! neq 0 (
        powershell -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::MsgBox('Database initialization failed! Please check the console for errors.', 'Critical,OkOnly', 'Setup Error')"
        pause
        exit /b
    )
    powershell -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::MsgBox('Database initialized successfully!', 'Information,OkOnly', 'DB Success')"
)

echo.
echo You can now use 'run_backend.bat' to start the server.
pause
exit /b

:ERROR_EXIT
echo.
echo [ERROR] An error occurred during setup.
powershell -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::MsgBox('An error occurred during setup. Please check the console window for details.', 'Critical,OkOnly', 'Setup Error')"
pause
exit /b
