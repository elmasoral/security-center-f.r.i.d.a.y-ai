$ErrorActionPreference = "Stop"

$RepoRoot = Get-Location
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $RepoRoot "_backup_camera_fix_v3_$Stamp"

Write-Host "MEDPOV FRIDAY Camera Vision Fix v3" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host "Backup: $BackupDir"

$Required = @(
    "main.py",
    "ui.py",
    "actions\screen_processor.py"
)

foreach ($file in $Required) {
    $src = Join-Path $PatchRoot ("PATCH_FILES\" + $file)
    if (!(Test-Path $src)) {
        throw "Patch file missing: $src"
    }
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BackupDir "actions") | Out-Null

foreach ($file in $Required) {
    $dst = Join-Path $RepoRoot $file
    if (Test-Path $dst) {
        $backupPath = Join-Path $BackupDir $file
        $backupParent = Split-Path -Parent $backupPath
        New-Item -ItemType Directory -Force -Path $backupParent | Out-Null
        Copy-Item $dst $backupPath -Force
    }
}

foreach ($file in $Required) {
    $src = Join-Path $PatchRoot ("PATCH_FILES\" + $file)
    $dst = Join-Path $RepoRoot $file
    $dstParent = Split-Path -Parent $dst
    New-Item -ItemType Directory -Force -Path $dstParent | Out-Null
    Copy-Item $src $dst -Force
    Write-Host "Patched: $file" -ForegroundColor Green
}

Write-Host "Running syntax check..." -ForegroundColor Yellow
python -m py_compile main.py ui.py actions\screen_processor.py

Write-Host "Patch applied successfully." -ForegroundColor Green
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  pip install -r requirements.txt"
Write-Host "  python main.py"
