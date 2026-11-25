@echo off
setlocal
cd /d "%~dp0"
title PokeQR2 Studio (Python)

set "OPEN_BROWSER=1"
if not defined PORT set "PORT=3001"

:parse_args
if "%~1"=="" goto after_args
if /i "%~1"=="--no-browser" set "OPEN_BROWSER=0"
shift
goto parse_args

:after_args
if not exist ".venv\Scripts\python.exe" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python 3.10+ was not found in PATH.
        pause
        exit /b 1
    )
    echo Creating Python virtual environment and installing dependencies...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv
        pause
        exit /b 1
    )
    .venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
)

echo Starting PokeQR2 (Python FastAPI + Pillow + OpenCV) on http://localhost:%PORT% ...
if "%OPEN_BROWSER%"=="1" (
    start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:%PORT%"
)
.venv\Scripts\python.exe -m app.main

if errorlevel 1 (
    echo.
    echo Server exited with an error.
    pause
)
endlocal
