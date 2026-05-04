@echo off
setlocal
title MEDPOV F.R.I.D.A.Y Installer

cd /d "%~dp0"

echo.
echo ============================================================
echo   MEDPOV F.R.I.D.A.Y Command Center - Installer
echo ============================================================
echo.

if not exist "main.py" (
    echo [ERROR] main.py bulunamadi.
    echo Bu dosyayi repo ana klasorunde calistirmalisin.
    pause
    exit /b 1
)

if not exist "setup.py" (
    echo [ERROR] setup.py bulunamadi.
    echo Bu dosyayi repo ana klasorunde calistirmalisin.
    pause
    exit /b 1
)

echo [1/4] Python kontrol ediliyor...

where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON_CMD=python"
    ) else (
        echo [ERROR] Python bulunamadi.
        echo Lutfen Python 3.11 veya daha yeni surum kur.
        echo https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

echo [OK] Python bulundu.

echo.
echo [2/4] Sanal ortam kontrol ediliyor...

if not exist ".venv\Scripts\python.exe" (
    echo .venv olusturuluyor...
    %PYTHON_CMD% -m venv .venv

    if not exist ".venv\Scripts\python.exe" (
        echo [ERROR] .venv olusturulamadi.
        pause
        exit /b 1
    )
) else (
    echo [OK] .venv zaten mevcut.
)

echo.
echo [3/4] Kurulum baslatiliyor...
".venv\Scripts\python.exe" setup.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Kurulum tamamlanamadi.
    pause
    exit /b 1
)

echo.
echo [4/4] Kurulum tamamlandi.
echo.
echo Masaustune FRIDAY AI kisayolu eklendi.
echo Gemini API key ilk acilista FRIDAY arayuzunden istenecek.
echo.
echo Baslatmak icin:
echo start_friday.bat
echo.
pause
exit /b 0