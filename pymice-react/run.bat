@echo off
rem ============================================================
rem .bat developed by Marcos Aurelio for PyMiceTracking
rem ============================================================

setlocal enabledelayedexpansion 

rem ============================================================
rem WEB APPLICATION PORTS and DIRS
rem ============================================================
set BACKEND_PORT=8000
set BACKEND_DIR=%~dp0backend
set FRONTEND_PORT=5173
set FRONTEND_DIR=%~dp0frontend
set LOGS_DIR=%~dp0logs
rem ============================================================


rem ============================================================
rem COMMANDS and GO TO
rem ============================================================
if "%1"=="" goto menu
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="status" goto status
if "%1"=="frontlogs" goto frontlogs
if "%1"=="backlogs" goto backlogs
if "%1"=="update" goto update
echo Invalid command...Try again...
exit /b
rem ============================================================

echo %LOGS_DIR%
echo %FRONTEND_DIR%
echo %BACKEND_DIR%

rem ============================================================
rem MAIN MENU
rem ============================================================
:menu
echo ====================================================================================================
echo x PyMiceTracking Web Application - Developed by Helton Maia, Marcos Aurelio and Richardson Menezes x
echo ====================================================================================================

echo Options available:
echo 1 - Start services
echo 2 - Stop services
echo 3 - Restart services
echo 4 - Check status
echo 5 - Check backend logs
echo 6 - Check frontend logs
echo 0 - Exit

set /p CHOICE=Choose a function: 
if "%CHOICE%"=="1" goto start
if "%CHOICE%"=="2" goto stop 
if "%CHOICE%"=="3" goto restart
if "%CHOICE%"=="4" goto status
if "%CHOICE%"=="5" goto backlogs
if "%CHOICE%"=="6" goto frontlogs
if "%CHOICE%"=="0" exit /b

echo %CHOICE
pause
exit /b
rem ============================================================
rem START
rem ============================================================
:start
echo Starting the system.....

cd /d "backend"
start "backend" cmd /c "uv-venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 2 >nul

cd /d "../"
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "uvicorn"') do set BACKEND_PID=%%a
echo %BACKEND_PID% > backend.pid
echo Backend started..... PID=%BACKEND_PID%


cd /d "frontend"
start "frontend" cmd /c npm run dev
timeout /t 2 >nul

cd /d "../"
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "node"') do set FRONTEND_PID=%%a
echo %FRONTEND_PID% > frontend.pid
echo Frontend started..... PID=%FRONTEND_PID%


echo ==== System started ====
exit /b


rem ============================================================
rem STOP
rem ============================================================
:stop
echo Stopping the system.....

if exist backend.pid (
    for /f %%p in (backend.pid) do taskkill /PID %%p /F
    del backend.pid
)

if exist frontend.pid (
    for /f %%p in (frontend.pid) do taskkill /PID %%p /F
    del frontend.pid
)

echo ==== System stopped ====
exit /b
rem ============================================================

rem ============================================================
rem RESTART
rem ============================================================
:restart
echo Restarting the system.....
call :stop
call :start
exit /b
rem ============================================================

rem ============================================================
rem STATUS
rem ============================================================
:status
echo ==== Application status ====

netstat -ano | findstr :%BACKEND_PORT% >nul
    if %errorlevel% equ 0 (
    echo Backend running in port: %BACKEND_PORT%
    ) else (
    echo Backend not running
    )

netstat -ano | findstr :%FRONTEND_PORT% >nul
    if %errorlevel% equ 0 (
    echo Frontend running in port: %FRONTEND_PORT%
    ) else (
    echo Frontend not running
    )
exit /b
rem ============================================================

rem ============================================================
rem BACKLOGS
rem ============================================================
:backlogs
echo backlogs
exit /b
rem ============================================================

rem ============================================================
rem FRONTLOGS
rem ============================================================
:frontlogs
echo frontlogs
exit /b
rem ============================================================

rem ============================================================
rem UPDATE
rem ============================================================
:update
echo Updating PyMiceTracking.....
git pull
echo Updated successfully.....
exit /b
rem ============================================================
