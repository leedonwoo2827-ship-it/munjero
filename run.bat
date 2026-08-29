@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"
title munjero - exam paper to grader

echo.
echo ==========================================================
echo   munjero  ^|  exam paper HTML  -^>  grader HTML
echo ==========================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python not found. Run setup.bat first.
    echo.
    pause
    exit /b 1
)

REM ---------- drag and drop ----------
if not "%~1"=="" (
    echo   Input: %~nx1
    echo.
    python -m munjero run "%~1"
    goto :done
)

REM ---------- pick from input folder ----------
if not exist "input" mkdir "input"
set N=0
for %%f in ("input\*.html") do (
    set /a N+=1
    set "F!N!=%%~f"
    echo   !N!^) %%~nxf
)
if %N%==0 (
    echo   No exam HTML found.
    echo.
    echo   Put your exam HTML in this folder:
    echo       %~dp0input
    echo   Or drag a HTML file onto run.bat
    echo.
    pause
    exit /b 1
)

echo.
set "PICK=1"
set /p PICK=  Choose a number (Enter = 1):
if "%PICK%"=="" set "PICK=1"
set "TARGET=!F%PICK%!"
if "%TARGET%"=="" (
    echo   Invalid number.
    echo.
    pause
    exit /b 1
)

echo.
echo   Input: %TARGET%
echo.
python -m munjero run "%TARGET%"

:done
if errorlevel 1 (
    echo.
    echo   Failed. See the message above.
    echo   If it is a login problem, run:  codex.cmd login
    echo.
    pause
    exit /b 1
)

echo.
echo   Opening the dist folder...
start "" "%~dp0dist"
echo.
pause
