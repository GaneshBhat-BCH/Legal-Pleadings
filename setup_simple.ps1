# COI Management Matching Engine - Simple Setup Script
# This script handles all prerequisites and installations in one go.

function Show-MsgBox {
    param([string]$Message, [string]$Title, [string]$Icon = "Information")
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.Interaction]::MsgBox($Message, "$Icon,OkOnly", $Title)
}

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "      AI Backend Simple Setup" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Check/Install Python
Write-Host "[1/5] Checking Python..." -ForegroundColor White
$python = Get-Command python, py, python3 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $python) {
    Write-Host "[!] Python not found. Trying to install via winget..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Start-Process winget -ArgumentList "install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements" -Wait -NoNewWindow
        Write-Host "[INFO] Refreshing PATH..." -ForegroundColor Gray
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $python = Get-Command python, py, python3 -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $python) {
            Show-MsgBox "Python installation failed. Please restart your terminal or computer, then run this script again." "Setup Error" "Critical"
            exit
        }
    } else {
        Show-MsgBox "Python and winget are missing. Please install Python manually from python.org." "Setup Error" "Critical"
        exit
    }
}
Write-Host "[SUCCESS] Using Python: $($python.Source)" -ForegroundColor Green

# 2. Create Virtual Environment
Write-Host "[2/5] Setting up Virtual Environment..." -ForegroundColor White
if (-not (Test-Path "backend\venv")) {
    Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Gray
    & $python.Source -m venv backend\venv
    if ($LASTEXITCODE -ne 0) {
        Show-MsgBox "Failed to create virtual environment. Check Python installation." "Setup Error" "Critical"
        exit
    }
    Write-Host "[SUCCESS] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "[SUCCESS] Virtual environment already exists." -ForegroundColor Green
}

# 3. Check/Install Tesseract
Write-Host "[3/5] Checking Tesseract OCR..." -ForegroundColor White
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Tesseract not found. Trying to install via winget..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Start-Process winget -ArgumentList "install --id UB.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements" -Wait -NoNewWindow
        Write-Host "[INFO] Tesseract installed." -ForegroundColor Green
    }
} else {
    Write-Host "[SUCCESS] Tesseract OCR found." -ForegroundColor Green
}

# 4. Install Python Dependencies in venv
Write-Host "[4/5] Installing Required Libraries in Virtual Environment..." -ForegroundColor White
try {
    $venvPython = "backend\venv\Scripts\python.exe"
    & $venvPython -m pip install --upgrade pip --quiet
    & $venvPython -m pip install -r backend\requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    Write-Host "[SUCCESS] Libraries installed in venv." -ForegroundColor Green
} catch {
    Show-MsgBox "Failed to install Python libraries. Check your internet connection and try again." "Setup Error" "Critical"
    exit
}

# 5. Check .env
Write-Host "[5/5] Checking Configuration..." -ForegroundColor White
if (-not (Test-Path "backend\.env")) {
    Write-Host "[WARNING] backend\.env file is missing! Please configure it with your API keys." -ForegroundColor Yellow
} else {
    Write-Host "[SUCCESS] .env file found." -ForegroundColor Green
}

Show-MsgBox "Setup completed successfully! Virtual environment is ready. Next time, just activate it to run quickly!" "Setup Success"
Write-Host "`n====================================================" -ForegroundColor Cyan
Write-Host "      Setup Complete!" -ForegroundColor Cyan
Write-Host "      Virtual environment: backend\venv" -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Cyan
pause
