@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0apply_patch.ps1"
pause
