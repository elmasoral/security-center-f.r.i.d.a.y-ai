$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

Write-Host ""
Write-Host "============================================================"
Write-Host "  MEDPOV F.R.I.D.A.Y Command Center - Installer"
Write-Host "============================================================"
Write-Host ""

if (!(Test-Path "main.py")) {
    Write-Host "[ERROR] main.py bulunamadi. Bu dosyayi repo ana klasorunde calistirmalisin." -ForegroundColor Red
    Read-Host "Cikmak icin Enter"
    exit 1
}

if (!(Test-Path "setup.py")) {
    Write-Host "[ERROR] setup.py bulunamadi. Bu dosyayi repo ana klasorunde calistirmalisin." -ForegroundColor Red
    Read-Host "Cikmak icin Enter"
    exit 1
}

Write-Host "[1/4] Python kontrol ediliyor..."

$pythonCmd = $null

try {
    $pyCheck = Get-Command py -ErrorAction Stop
    $pythonCmd = @("py", "-3")
} catch {
    try {
        $pythonCheck = Get-Command python -ErrorAction Stop
        $pythonCmd = @("python")
    } catch {
        Write-Host "[ERROR] Python bulunamadi. Python 3.11 veya daha yeni surum kur." -ForegroundColor Red
        Write-Host "https://www.python.org/downloads/"
        Read-Host "Cikmak icin Enter"
        exit 1
    }
}

Write-Host "[OK] Python bulundu." -ForegroundColor Green

Write-Host ""
Write-Host "[2/4] Sanal ortam kontrol ediliyor..."

if (!(Test-Path ".venv\Scripts\python.exe")) {
    Write-Host ".venv olusturuluyor..."
    & $pythonCmd[0] $pythonCmd[1..($pythonCmd.Length - 1)] -m venv .venv

    if (!(Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "[ERROR] .venv olusturulamadi." -ForegroundColor Red
        Read-Host "Cikmak icin Enter"
        exit 1
    }
} else {
    Write-Host "[OK] .venv zaten mevcut." -ForegroundColor Green
}

Write-Host ""
Write-Host "[3/4] Kurulum baslatiliyor..."

& ".\.venv\Scripts\python.exe" ".\setup.py"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Kurulum tamamlanamadi." -ForegroundColor Red
    Read-Host "Cikmak icin Enter"
    exit 1
}

Write-Host ""
Write-Host "[4/4] Kurulum tamamlandi." -ForegroundColor Green
Write-Host ""
Write-Host "F.R.I.D.A.Y'i baslatmak icin:"
Write-Host ".\start_friday.ps1"
Write-Host ""

Read-Host "Cikmak icin Enter"
exit 0