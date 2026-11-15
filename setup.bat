@echo off
rem Create venv and install dependencies. See README.md.
setlocal
cd /d "%~dp0"

chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8

rem IMPORTANT: the venv python created here cannot write to the system %TEMP%.
rem pip would hang forever while unpacking downloads, so keep temp inside the project.
if not exist ".pip-tmp" mkdir ".pip-tmp" >nul 2>nul
set TMPDIR=%~dp0.pip-tmp
set TEMP=%~dp0.pip-tmp
set TMP=%~dp0.pip-tmp

if exist ".venv\Scripts\python.exe" goto install

echo [setup] creating virtual environment .venv ...
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3.12 -m venv .venv
) else (
    python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo [setup] failed to create venv. Python 3.9-3.12 is required.
    exit /b 1
)

:install
echo [setup] installing requirements.txt ^(mediapipe is about 100 MB, please wait^) ...
".venv\Scripts\python.exe" -m pip install --no-input --disable-pip-version-check --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo [setup] install failed. Check network and Python version ^(3.9-3.12^).
    exit /b 1
)

echo [setup] done. Now run run.bat
exit /b 0
