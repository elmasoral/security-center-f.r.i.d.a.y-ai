@echo off
setlocal
title MEDPOV F.R.I.D.A.Y Command Center

cd /d "%~dp0"

echo.
echo ============================================================
echo   MEDPOV F.R.I.D.A.Y Command Center
echo ============================================================
echo.

if not exist "main.py" (
    echo [ERROR] main.py bulunamadi.
    echo Bu dosyayi repo ana klasorunde calistirmalisin.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv bulunamadi.
    echo Once install_friday.bat dosyasini calistir.
    pause
    exit /b 1
)

echo F.R.I.D.A.Y baslatiliyor...
echo.

".venv\Scripts\python.exe" main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] F.R.I.D.A.Y beklenmeyen sekilde kapandi.
    pause
    exit /b 1
)

exit /b 0