@echo off
rem Run hand tracking. See README.md.
rem Usage: run.bat                  auto-pick camera
rem        run.bat --camera 1       explicit camera index
rem        run.bat --no-connections --dot-radius 8
setlocal
cd /d "%~dp0"

rem utf-8 console so Chinese output is not garbled
chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8

rem this venv python cannot write to the system %TEMP%, point it inside the project
if not exist ".pip-tmp" mkdir ".pip-tmp" >nul 2>nul
set TMPDIR=%~dp0.pip-tmp
set TEMP=%~dp0.pip-tmp
set TMP=%~dp0.pip-tmp

if not exist ".venv\Scripts\python.exe" (
    echo [run] dependencies are not installed yet. Please run setup.bat first.
    exit /b 1
)

".venv\Scripts\python.exe" hand_tracker.py %*
exit /b %ERRORLEVEL%
