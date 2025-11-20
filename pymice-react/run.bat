@echo off
setlocal enabledelayedexpansion

rem ==========================
rem CONFIG
rem ==========================
set BACKEND_PORT=8000
set FRONTEND_PORT=5173
set LOG_DIR=logs


rem ==========================
rem MAIN ENTRYPOINT
rem ==========================
if "%1"=="" goto menu

if "%1"=="start"   goto start
if "%1"=="stop"    goto stop
if "%1"=="restart" goto restart
if "%1"=="status"  goto status
if "%1"=="logs"    goto logs

echo Comando invalido.
exit /b


rem ==========================
rem CHECK PORT
rem ==========================
:check_port
set PORT_PID=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%1 ^| findstr LISTENING') do (
    set PORT_PID=%%a
)
exit /b


rem ==========================
rem STATUS
rem ==========================
:status
cls
echo ========= STATUS =========

call :check_port %BACKEND_PORT%
if defined PORT_PID (
    echo Backend: RUNNING (PID %PORT_PID%)
) else (
    echo Backend: STOPPED
)

call :check_port %FRONTEND_PORT%
if defined PORT_PID (
    echo Frontend: RUNNING (PID %PORT_PID%)
) else (
    echo Frontend: STOPPED
)

echo ==========================
echo.
pause
exit /b


rem ==========================
rem START
rem ==========================
:start
cls
echo Iniciando...

if not exist %LOG_DIR% mkdir %LOG_DIR%

rem --- backend ---
call :check_port %BACKEND_PORT%
if not defined PORT_PID (
    echo Iniciando Backend...
    pushd backend
    call ..\uv-env\Scripts\activate.bat
    start "" /b cmd /c "uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload > ..\%LOG_DIR%\backend.log 2>&1"
    popd
) else (
    echo Backend ja esta rodando.
)

rem --- frontend ---
call :check_port %FRONTEND_PORT%
if not defined PORT_PID (
    echo Iniciando Frontend...
    pushd frontend
    if not exist node_modules call npm install --silent
    start "" /b cmd /c "npm run dev -- --host 0.0.0.0 --port %FRONTEND_PORT% > ..\%LOG_DIR%\frontend.log 2>&1"
    popd
) else (
    echo Frontend ja esta rodando.
)

echo.
pause
exit /b


rem ==========================
rem STOP
rem ==========================
:stop
cls
echo Parando...

call :check_port %BACKEND_PORT%
if defined PORT_PID (
    taskkill /PID %PORT_PID% /F >nul
    echo Backend parado.
)

call :check_port %FRONTEND_PORT%
if defined PORT_PID (
    taskkill /PID %PORT_PID% /F >nul
    echo Frontend parado.
)

echo.
pause
exit /b


rem ==========================
rem RESTART
rem ==========================
:restart
call :stop
call :start
exit /b


rem ==========================
rem LOGS
rem ==========================
:logs
if "%2"=="backend" (
    notepad %LOG_DIR%\backend.log
    exit /b
)
if "%2"=="frontend" (
    notepad %LOG_DIR%\frontend.log
    exit /b
)
echo Uso: run.bat logs backend|frontend
pause
exit /b


rem ==========================
rem MENU
rem ==========================
:menu
cls
echo =====================================
echo        PyMiceTracking WEB (Windows)
echo =====================================
echo.
echo 1 - Start Services
echo 2 - Stop Services
echo 3 - Restart Services
echo 4 - Status
echo 5 - Logs Backend
echo 6 - Logs Frontend
echo 0 - Exit
echo.
set /p op="Escolha: "

if "%op%"=="1" goto start
if "%op%"=="2" goto stop
if "%op%"=="3" goto restart
if "%op%"=="4" goto status
if "%op%"=="5" goto logs backend
if "%op%"=="6" goto logs frontend
if "%op%"=="0" exit /b

goto menu
