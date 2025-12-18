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
Write-Host "[1/4] Checking Python..." -ForegroundColor White
$python = Get-Command python, py, python3 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $python) {
    Write-Host "[!] Python not found. Trying to install via winget..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Start-Process winget -ArgumentList "install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements" -Wait
        $python = Get-Command python, py, python3 -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $python) {
            Show-MsgBox "Python installation failed via winget. Please install it manually from python.org and check 'Add to PATH'." "Setup Error" "Critical"
            exit
        }
    } else {
        Show-MsgBox "Python and winget are missing. Please install Python manually." "Setup Error" "Critical"
        exit
    }
}
Write-Host "[SUCCESS] Using Python: $($python.Source)" -ForegroundColor Green

# 2. Check/Install Tesseract
Write-Host "[2/4] Checking Tesseract OCR..." -ForegroundColor White
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Tesseract not found. Trying to install via winget..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Start-Process winget -ArgumentList "install --id UB.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements" -Wait
        Write-Host "[INFO] Tesseract installed. It might need a terminal restart to show up in PATH." -ForegroundColor Green
    }
} else {
    Write-Host "[SUCCESS] Tesseract OCR found." -ForegroundColor Green
}

# 3. Install Python Dependencies
Write-Host "[3/4] Installing Required Libraries..." -ForegroundColor White
try {
    & $python.Source -m pip install --upgrade pip
    & $python.Source -m pip install -r backend/requirements.txt
    Write-Host "[SUCCESS] Libraries installed." -ForegroundColor Green
} catch {
    Show-MsgBox "Failed to install Python libraries. Check your internet connection." "Setup Error" "Critical"
    exit
}

# 4. Check .env
Write-Host "[4/4] Checking Configuration..." -ForegroundColor White
if (-not (Test-Path "backend/.env")) {
    Write-Host "[WARNING] backend/.env file is missing! Creating template..." -ForegroundColor Yellow
    "OPENAI_API_KEY=your_key_here`nDATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname" | Out-File "backend/.env" -Encoding utf8
}

Show-MsgBox "Setup completed successfully! Everyting is ready to run." "Setup Success"
Write-Host "`n====================================================" -ForegroundColor Cyan
Write-Host "      Setup Complete! You can now start the server." -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
pause
