$ErrorActionPreference = "Stop"

$Root = Get-Location
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Files = Join-Path $PatchRoot "PATCH_FILES"

Write-Host "MEDPOV FRIDAY Camera/Vision Fix v2 patch applying..." -ForegroundColor Cyan
Write-Host "Target: $Root" -ForegroundColor DarkCyan

$backup = Join-Path $Root ("_backup_camera_fix_v2_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $backup | Out-Null

$targets = @(
    "main.py",
    "ui.py",
    "actions\screen_processor.py"
)

foreach ($rel in $targets) {
    $src = Join-Path $Root $rel
    if (Test-Path $src) {
        $dest = Join-Path $backup $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
        Copy-Item $src $dest -Force
    }
}

Copy-Item (Join-Path $Files "main.py") (Join-Path $Root "main.py") -Force
Copy-Item (Join-Path $Files "ui.py") (Join-Path $Root "ui.py") -Force
Copy-Item (Join-Path $Files "actions\screen_processor.py") (Join-Path $Root "actions\screen_processor.py") -Force

Write-Host "Patch files copied." -ForegroundColor Green
Write-Host "Backup created: $backup" -ForegroundColor Yellow

if (Test-Path ".\.venv\Scripts\python.exe") {
    & .\.venv\Scripts\python.exe -m py_compile main.py ui.py actions\screen_processor.py
} else {
    python -m py_compile main.py ui.py actions\screen_processor.py
}

Write-Host "Syntax check OK." -ForegroundColor Green
Write-Host "Now run: python main.py" -ForegroundColor Cyan
