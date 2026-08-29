@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
title munjero - setup

echo.
echo ==========================================================
echo   munjero  ^|  setup
echo ==========================================================
echo.

REM ---------- 1. Python ----------
echo [1/4] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERROR: Python not found.
    echo   Install Python 3.10+ from https://www.python.org/downloads/
    echo   Be sure to check "Add python.exe to PATH" during install.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYV=%%v
echo       Python %PYV%  OK
echo.

REM ---------- 2. Python packages ----------
echo [2/4] Installing Python packages...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo   ERROR: pip install failed.
    echo   Check your network or proxy settings and try again.
    echo.
    pause
    exit /b 1
)
echo       fastapi / uvicorn / pymupdf / bs4 / lxml / pillow  OK
echo.

REM ---------- 3. Codex CLI ----------
echo [3/4] Checking Codex CLI...
where codex.cmd >nul 2>&1
if errorlevel 1 (
    echo       Not installed. Installing now...
    where npm >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   ERROR: npm not found.
        echo   Install Node.js LTS from https://nodejs.org/ then run setup.bat again.
        echo.
        pause
        exit /b 1
    )
    call npm install -g @openai/codex
    if errorlevel 1 (
        echo.
        echo   ERROR: npm install failed.
        echo.
        pause
        exit /b 1
    )
)
echo       Codex CLI  OK
echo.

REM ---------- 4. ChatGPT login ----------
echo [4/4] Checking ChatGPT login...
echo       Running a real call. A file check cannot detect an expired token.
echo.
python -m munjero doctor --smoke
if errorlevel 1 (
    echo.
    echo   ----------------------------------------------------
    echo   Login required. Run this command:
    echo.
    echo       codex.cmd login
    echo.
    echo   A browser opens. Sign in with your ChatGPT account,
    echo   pick your workspace, and press Continue.
    echo   Then run setup.bat again.
    echo   ----------------------------------------------------
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   Setup complete. Now run:  run.bat
echo   It opens http://127.0.0.1:7085/ in your browser.
echo ==========================================================
echo.
pause
