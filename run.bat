@echo off
REM ASCII-only on purpose: non-ASCII in a .bat can break on CP949 consoles.
cd /d "%~dp0"
if not defined PORT set "PORT=7085"

REM The app logs in Korean. Without these the console shows mojibake on CP949.
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

where python >nul 2>nul
if errorlevel 1 goto :noinstall
python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 goto :noinstall

REM ---------------------------------------------------------------------------
REM An older copy of this app may still hold the port. If we leave it, uvicorn
REM fails, the browser still opens, and you sit there looking at the OLD code.
REM Asking about that is noise for the person using this, so just clear it.
REM Only our own python is touched; anything else gets a free port instead.
REM ---------------------------------------------------------------------------
call :freeport
if defined ABORT goto :eof

echo.
echo ============================================================
echo    munjero
echo    http://127.0.0.1:%PORT%/
echo.
echo    Keep this window open while you work.
echo    Closing it stops the app.
echo ============================================================
echo.

start "" /b cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:%PORT%/"

python -m uvicorn server:app --host 127.0.0.1 --port %PORT% --log-level warning

echo.
echo Stopped.
timeout /t 3 >nul
goto :eof

REM ---------------------------------------------------------------------------
:freeport
set "BUSYPID="
for /f "tokens=5" %%p in ('netstat -ano -p TCP 2^>nul ^| findstr LISTENING ^| findstr /c:":%PORT% "') do set "BUSYPID=%%p"
if not defined BUSYPID goto :eof

set "BUSYNAME=?"
for /f "tokens=1 delims=," %%n in ('tasklist /fi "PID eq %BUSYPID%" /fo csv /nh 2^>nul') do set "BUSYNAME=%%~n"

echo %BUSYNAME% | findstr /i "python" >nul
if errorlevel 1 goto :otherapp

REM Our own older copy. Clear it without asking.
taskkill /PID %BUSYPID% /F >nul 2>nul
ping -n 3 127.0.0.1 >nul
goto :eof

:otherapp
REM Not us. Leave it alone and move to the next port.
set /a PORT=%PORT%+1
if %PORT% GTR 7099 (
    echo.
    echo   Could not find a free port between 7085 and 7099.
    echo   Close some programs and try again.
    echo.
    pause
    set "ABORT=1"
    goto :eof
)
goto :freeport

:noinstall
echo.
echo   Not installed yet. Please double-click setup.bat first.
echo.
pause
