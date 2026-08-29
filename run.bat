@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 문제로 - 시험지를 채점기로

echo.
echo ==========================================================
echo    문제로 ^| 시험지를 채점기로 바꿉니다
echo ==========================================================
echo.
echo    1. 문제 읽어내기      시험지에서 문항과 보기를 뽑습니다
echo       ^-^-^> 확인          제자리에 있는지 눈으로 봅니다
echo    2. 정답과 해설        AI 가 만듭니다 ^(10~15분^)
echo    3. 채점기 만들기      더블클릭으로 열리는 파일이 나옵니다
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo    Python 이 없습니다. setup.bat 을 먼저 실행해 주세요.
    echo.
    pause
    exit /b 1
)

REM ---------- 파일 고르기: 끌어다 놓기 또는 input 폴더 ----------
set "TARGET="
if not "%~1"=="" (
    set "TARGET=%~1"
    goto :picked
)

if not exist "input" mkdir "input"
set N=0
for %%f in ("input\*.html" "input\*.pdf" "input\*.hwp" "input\*.hwpx") do (
    if exist "%%~f" (
        set /a N+=1
        set "F!N!=%%~f"
        echo    !N!^) %%~nxf
    )
)
if %N%==0 (
    echo    시험지 파일이 없습니다.
    echo.
    echo    아래 폴더에 시험지를 넣어 주세요. HTML, PDF, 한글 파일 모두 됩니다.
    echo        %~dp0input
    echo.
    echo    또는 시험지 파일을 run.bat 위로 끌어다 놓으세요.
    echo.
    pause
    exit /b 1
)

echo.
set "PICK=1"
set /p PICK=   번호를 고르세요 (엔터 = 1) :
if "%PICK%"=="" set "PICK=1"
set "TARGET=!F%PICK%!"
if "%TARGET%"=="" (
    echo    그런 번호는 없습니다.
    echo.
    pause
    exit /b 1
)

:picked
echo.
echo ----------------------------------------------------------
echo    1 단계  문제 읽어내기
echo ----------------------------------------------------------
echo.
python -m munjero map "%TARGET%" --open
if errorlevel 1 (
    echo.
    echo    읽어내지 못했습니다. 위 메시지를 봐주세요.
    echo.
    pause
    exit /b 1
)

echo.
echo ----------------------------------------------------------
echo    확인  제자리에 있는지 봐주세요
echo ----------------------------------------------------------
echo.
echo    방금 브라우저에 시험지가 열렸습니다.
echo    문항 번호, 보기 4개, 지문이 제자리에 있는지 봐주세요.
echo.
echo    빨간 줄이 있으면 그 자리는 읽어내지 못한 곳입니다.
echo    그 HTML 파일을 직접 고치고 run.bat 을 다시 실행하면 됩니다.
echo.
echo    다음 단계는 100문항에 10~15분 걸립니다.
echo    지금 자리가 틀려 있으면 그 시간이 그대로 버려집니다.
echo.
set "GO=N"
set /p GO=   제자리에 있습니까? 정답 만들기로 넘어갈까요? (y / 엔터=중단) :
if /i not "%GO%"=="y" (
    echo.
    echo    여기서 멈췄습니다. 시험지 HTML 을 고치고 다시 실행해 주세요.
    echo    지금까지 읽어낸 내용은 그대로 남아 있습니다.
    echo.
    pause
    exit /b 0
)

echo.
echo ----------------------------------------------------------
echo    2 단계  정답과 해설 만들기
echo ----------------------------------------------------------
echo.
python -m munjero answer "%TARGET%"
if errorlevel 1 (
    echo.
    echo    만들지 못했습니다.
    echo    ChatGPT 로그인 문제라면 아래를 실행해 주세요.
    echo.
    echo        codex.cmd login
    echo.
    pause
    exit /b 1
)

echo.
echo ----------------------------------------------------------
echo    3 단계  채점기 만들기
echo ----------------------------------------------------------
echo.
python -m munjero build "%TARGET%"
if errorlevel 1 (
    echo.
    echo    만들지 못했습니다. 위 메시지를 봐주세요.
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo    끝났습니다.
echo ==========================================================
echo.
echo    04_grader 폴더 안의 HTML 이 채점기입니다. 더블클릭하면 열립니다.
echo.
echo    정답은 AI 가 만든 것입니다. 공식 정답표와 대조해 주세요.
echo    채점기 위쪽 버튼으로 확인이 필요한 문항만 골라 볼 수 있습니다.
echo.
for /f "delims=" %%d in ('python -c "from munjero import config;print(config.out_root())"') do start "" "%%d"
pause
