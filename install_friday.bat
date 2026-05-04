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

set "PYTHON_CMD="

where py >nul 2>&1
if %errorlevel%==0 (
    py -3.12 --version >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON_CMD=py -3.12"
    ) else (
        py -3.11 --version >nul 2>&1
        if %errorlevel%==0 (
            set "PYTHON_CMD=py -3.11"
        )
    )
)

if "%PYTHON_CMD%"=="" (
    where python >nul 2>&1
    if %errorlevel%==0 (
        for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
        echo Detected Python version: %PY_VER%

        echo %PY_VER% | findstr /r "^3\.12\." >nul
        if %errorlevel%==0 set "PYTHON_CMD=python"

        echo %PY_VER% | findstr /r "^3\.11\." >nul
        if %errorlevel%==0 set "PYTHON_CMD=python"
    )
)

if "%PYTHON_CMD%"=="" (
    echo.
    echo [ERROR] Supported Python bulunamadi.
    echo.
    echo F.R.I.D.A.Y icin Python 3.11 veya Python 3.12 kullan.
    echo Python 3.13 / 3.14 / 3.15 kullanma.
    echo Bu surumlerde numpy gibi paketler wheel bulamayip source build'e dusebilir.
    echo.
    echo Python 3.12 indir:
    echo https://www.python.org/downloads/release/python-312/
    echo.
    pause
    exit /b 1
)

echo [OK] Kullanilacak Python:
%PYTHON_CMD% --version

echo.
echo [2/4] Sanal ortam kontrol ediliyor...

if exist ".venv\Scripts\python.exe" (
    echo [OK] .venv zaten mevcut.
) else (
    echo .venv olusturuluyor...
    %PYTHON_CMD% -m venv .venv

    if not exist ".venv\Scripts\python.exe" (
        echo [ERROR] .venv olusturulamadi.
        pause
        exit /b 1
    )
)

echo.
echo [3/4] Kurulum baslatiliyor...
".venv\Scripts\python.exe" --version
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