@echo off
REM PyMice Tracking Panel - Docker Management Script for Windows
REM Run with: docker.bat [start|stop|restart|status|logs|free-ports|menu]

setlocal enabledelayedexpansion

set BACKEND_PORT=8000
set FRONTEND_PORT=5173
set DATA_DIR=.\backend\temp

REM Colors (limited in CMD, but we can use some tricks)
set "ESC="

:MAIN
if "%~1"=="" (
    call :SHOW_MENU
    goto :EOF
) else (
    if /i "%~1"=="start" call :START_SERVICES
    if /i "%~1"=="stop" call :STOP_SERVICES
    if /i "%~1"=="restart" (
        call :STOP_SERVICES
        timeout /t 2 /nobreak >nul
        call :START_SERVICES
    )
    if /i "%~1"=="status" call :SHOW_STATUS
    if /i "%~1"=="logs" call :SHOW_LOGS
    if /i "%~1"=="free-ports" call :FREE_PORTS
    if /i "%~1"=="menu" call :SHOW_MENU
    if /i "%~1"=="help" call :SHOW_HELP
    goto :EOF
)

:SHOW_MENU
cls
echo.
echo ========================================
echo   PyMice Tracking Panel - Manager
echo ========================================
echo.
echo   1. Start services
echo   2. Stop services
echo   3. Restart services
echo   4. Show status
echo   5. View logs
echo   6. Free ports
echo   7. Exit
echo.
set /p choice="Enter your choice [1-7]: "

if "%choice%"=="1" call :START_SERVICES
if "%choice%"=="2" call :STOP_SERVICES
if "%choice%"=="3" (
    call :STOP_SERVICES
    timeout /t 2 /nobreak >nul
    call :START_SERVICES
)
if "%choice%"=="4" call :SHOW_STATUS
if "%choice%"=="5" call :SHOW_LOGS
if "%choice%"=="6" call :FREE_PORTS
if "%choice%"=="7" goto :EOF

if not "%choice%"=="7" (
    echo.
    pause
    call :SHOW_MENU
)
goto :EOF

:CHECK_DOCKER
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed or not in PATH
    echo         Visit: https://docs.docker.com/desktop/install/windows-install/
    pause
    exit /b 1
)
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Compose is not installed
    echo         Install Docker Desktop which includes Docker Compose
    pause
    exit /b 1
)
exit /b 0

:CHECK_PORT
set port=%~1
netstat -ano | findstr ":%port% " | findstr "LISTENING" >nul 2>&1
exit /b %errorlevel%

:KILL_PORT
set port=%~1
echo Checking port %port%...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%port% " ^| findstr "LISTENING"') do (
    echo Found process %%a on port %port%
    set /p confirm="Kill this process? (y/n): "
    if /i "!confirm!"=="y" (
        taskkill /PID %%a /F
        echo Process killed
    )
)
exit /b 0

:FREE_PORTS
cls
echo.
echo ========================================
echo   PyMice - Free Ports
echo ========================================
echo.

echo Checking ports...
echo.

echo Backend port %BACKEND_PORT%:
call :CHECK_PORT %BACKEND_PORT%
if %errorlevel%==0 (
    echo   IN USE
) else (
    echo   FREE
)

echo Frontend port %FRONTEND_PORT%:
call :CHECK_PORT %FRONTEND_PORT%
if %errorlevel%==0 (
    echo   IN USE
) else (
    echo   FREE
)

echo.
echo Options:
echo   1. Free backend port (%BACKEND_PORT%)
echo   2. Free frontend port (%FRONTEND_PORT%)
echo   3. Free both ports
echo   4. Back to menu
echo.
set /p port_choice="Enter choice [1-4]: "

if "%port_choice%"=="1" call :KILL_PORT %BACKEND_PORT%
if "%port_choice%"=="2" call :KILL_PORT %FRONTEND_PORT%
if "%port_choice%"=="3" (
    call :KILL_PORT %BACKEND_PORT%
    call :KILL_PORT %FRONTEND_PORT%
)
if "%port_choice%"=="4" goto :EOF

exit /b 0

:CREATE_DATA_DIRS
echo Creating data directories in %DATA_DIR%...
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\videos" mkdir "%DATA_DIR%\videos"
if not exist "%DATA_DIR%\models" mkdir "%DATA_DIR%\models"
if not exist "%DATA_DIR%\tracking" mkdir "%DATA_DIR%\tracking"
if not exist "%DATA_DIR%\roi_templates" mkdir "%DATA_DIR%\roi_templates"
echo [OK] Data directories created
exit /b 0

:START_SERVICES
cls
echo.
echo ========================================
echo   PyMice - Start Services
echo ========================================
echo.

call :CHECK_DOCKER
if %errorlevel% neq 0 exit /b 1

REM Check for existing containers
docker ps -a | findstr "pymice-" >nul 2>&1
if %errorlevel%==0 (
    echo [WARNING] Found existing PyMice containers
    docker ps -a | findstr "pymice-"
    echo.
    set /p stop_existing="Stop and remove these containers? (y/n): "
    if /i "!stop_existing!"=="y" (
        docker-compose down 2>nul
        docker-compose -f docker-compose.gpu.yml down 2>nul
        echo [OK] Containers stopped
    )
)

REM Check ports
echo.
echo Checking ports...
set ports_blocked=0

call :CHECK_PORT %BACKEND_PORT%
if %errorlevel%==0 (
    echo [WARNING] Backend port %BACKEND_PORT% is in use
    set ports_blocked=1
)

call :CHECK_PORT %FRONTEND_PORT%
if %errorlevel%==0 (
    echo [WARNING] Frontend port %FRONTEND_PORT% is in use
    set ports_blocked=1
)

if !ports_blocked!==1 (
    echo.
    set /p free_ports="Free ports automatically? (y/n): "
    if /i "!free_ports!"=="y" (
        call :KILL_PORT %BACKEND_PORT%
        call :KILL_PORT %FRONTEND_PORT%
    ) else (
        echo [ERROR] Cannot start with ports occupied
        pause
        exit /b 1
    )
)

REM Create data directories
echo.
call :CREATE_DATA_DIRS

REM Ask for CPU or GPU mode
echo.
echo Select mode:
echo   1. CPU mode (works everywhere)
echo   2. GPU mode (requires NVIDIA GPU + nvidia-docker)
set /p mode="Enter choice [1-2]: "

if "%mode%"=="2" (
    echo.
    echo Starting in GPU mode...
    docker-compose -f docker-compose.gpu.yml up --build -d
) else (
    echo.
    echo Starting in CPU mode...
    docker-compose up --build -d
)

echo.
echo ========================================
echo [OK] PyMice Tracking Panel is starting!
echo ========================================
echo.
echo   Frontend:    http://localhost:%FRONTEND_PORT%
echo   Backend API: http://localhost:%BACKEND_PORT%
echo   API Docs:    http://localhost:%BACKEND_PORT%/docs
echo.
exit /b 0

:STOP_SERVICES
cls
echo.
echo ========================================
echo   PyMice - Stop Services
echo ========================================
echo.

echo Stopping PyMice Tracking Panel...
docker-compose down 2>nul
docker-compose -f docker-compose.gpu.yml down 2>nul
echo [OK] PyMice Tracking Panel stopped
echo.
exit /b 0

:SHOW_STATUS
cls
echo.
echo ========================================
echo   PyMice - Status
echo ========================================
echo.

echo Container Status:
docker ps -a | findstr "pymice-" 2>nul
if %errorlevel% neq 0 (
    echo No PyMice containers found
)

echo.
echo Port Status:
call :CHECK_PORT %BACKEND_PORT%
if %errorlevel%==0 (
    echo Backend port %BACKEND_PORT%:  IN USE
) else (
    echo Backend port %BACKEND_PORT%:  FREE
)

call :CHECK_PORT %FRONTEND_PORT%
if %errorlevel%==0 (
    echo Frontend port %FRONTEND_PORT%: IN USE
) else (
    echo Frontend port %FRONTEND_PORT%: FREE
)

echo.
echo Data Directory:
if exist "%DATA_DIR%" (
    echo [OK] %DATA_DIR%
) else (
    echo [X] %DATA_DIR% (not created)
)

echo.
exit /b 0

:SHOW_LOGS
cls
echo.
echo ========================================
echo   PyMice - Logs
echo ========================================
echo.
echo Which logs do you want to see?
echo   1. All services
echo   2. Backend only
echo   3. Frontend only
echo   4. Back to menu
echo.
set /p log_choice="Enter choice [1-4]: "

if "%log_choice%"=="1" docker-compose logs -f
if "%log_choice%"=="2" docker-compose logs -f backend
if "%log_choice%"=="3" docker-compose logs -f frontend
if "%log_choice%"=="4" exit /b 0

exit /b 0

:SHOW_HELP
echo.
echo Usage: docker.bat [command]
echo.
echo Commands:
echo   start         - Start PyMice containers
echo   stop          - Stop PyMice containers
echo   restart       - Restart PyMice containers
echo   status        - Show container and port status
echo   logs          - Show logs
echo   free-ports    - Free occupied ports
echo   menu          - Open interactive menu
echo   help          - Show this help
echo.
echo Examples:
echo   docker.bat start
echo   docker.bat status
echo   docker.bat menu
echo.
exit /b 0

:EOF
endlocal
