$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

Write-Host ""
Write-Host "============================================================"
Write-Host "  MEDPOV F.R.I.D.A.Y Command Center"
Write-Host "============================================================"
Write-Host ""

if (!(Test-Path "main.py")) {
    Write-Host "[ERROR] main.py bulunamadi. Bu dosyayi repo ana klasorunde calistirmalisin." -ForegroundColor Red
    Read-Host "Cikmak icin Enter"
    exit 1
}

if (!(Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[ERROR] .venv bulunamadi. Once install_friday.ps1 dosyasini calistir." -ForegroundColor Red
    Read-Host "Cikmak icin Enter"
    exit 1
}

Write-Host "F.R.I.D.A.Y baslatiliyor..."
Write-Host ""

& ".\.venv\Scripts\python.exe" ".\main.py"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] F.R.I.D.A.Y beklenmeyen sekilde kapandi." -ForegroundColor Red
    Read-Host "Cikmak icin Enter"
    exit 1
}

exit 0