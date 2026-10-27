@echo off
title Exam Mate - Web Frontend (Otto Theme)
color 0B

echo ============================================
echo   EXAM MATE - Web Frontend (Otto Theme)
echo ============================================
echo.

cd /d "%~dp0"

:: Check if backend is running on 5000
netstat -ano | findstr :5000 > nul
if %errorlevel% neq 0 (
    echo [INFO] Local Backend (Port 5000) not detected.
    echo        Frontend will connect to Cloud API or Local Demo Mode.
    echo        (To run local backend, run backend\start_backend.bat)
    echo.
)

set "WEB_DIR=frontend\assets"
if not exist "%WEB_DIR%" set "WEB_DIR=."

echo [*] Serving directory: %cd%\%WEB_DIR%
echo [*] Starting server on http://localhost:8080
echo.

:: Open browser
start "" "http://localhost:8080/index.html"

:: Run Python HTTP server
if exist "backend\venv\Scripts\python.exe" (
    backend\venv\Scripts\python.exe -m http.server 8080 --directory "%WEB_DIR%"
) else if exist "..\.venv\Scripts\python.exe" (
    ..\.venv\Scripts\python.exe -m http.server 8080 --directory "%WEB_DIR%"
) else if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m http.server 8080 --directory "%WEB_DIR%"
) else (
    python -m http.server 8080 --directory "%WEB_DIR%"
)

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start web server. Make sure Python is installed.
)

pause
