param(
    [string]$ProjectRoot = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Join-Path $PatchRoot "PATCH_FILES"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $ProjectRoot "_backup_modern_ui_v2_$Stamp"

Write-Host "MEDPOV FRIDAY Modern UI v2 patch" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot" -ForegroundColor DarkCyan

if (!(Test-Path (Join-Path $ProjectRoot "ui.py"))) {
    throw "ui.py bulunamadı. Patch'i repo kök klasöründe çalıştır: C:\wamp64\www\med\medpov-friday-git"
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Copy-Item -Force (Join-Path $ProjectRoot "ui.py") (Join-Path $BackupDir "ui.py")

Copy-Item -Force (Join-Path $SourceDir "ui.py") (Join-Path $ProjectRoot "ui.py")

Write-Host "Syntax kontrolü yapılıyor..." -ForegroundColor Yellow
python -m py_compile (Join-Path $ProjectRoot "ui.py")

Write-Host "Tamamlandı." -ForegroundColor Green
Write-Host "Backup: $BackupDir" -ForegroundColor DarkGray
Write-Host "Test: .\.venv\Scripts\Activate.ps1 ; python main.py" -ForegroundColor Cyan
