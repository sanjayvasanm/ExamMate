@echo off
title Exam Mate - Web Frontend
color 0B

echo ============================================
echo   EXAM MATE - Web Frontend (Edge)
echo ============================================
echo.

cd /d "%~dp0"

:: Check if backend is likely running
netstat -ano | findstr :5000 > nul
if %errorlevel% neq 0 (
    echo [WARNING] Backend (Port 5000) does not seem to be running.
    echo           Please run start_backend.bat first!
    echo.
)

echo [*] Starting local web server on http://localhost:8080
echo [*] Project Root: %cd%\aiassistant\frontend\assets
echo.

:: Open Edge browser
echo [*] Opening Microsoft Edge...
start msedge "http://localhost:8080/login_exam_mate/code.html"

:: Run Python's HTTP server
:: Uses the Python from the backend venv if available, or system python
if exist "aiassistant\backend\venv\Scripts\python.exe" (
    aiassistant\backend\venv\Scripts\python.exe -m http.server 8080 --directory aiassistant\frontend\assets
) else (
    python -m http.server 8080 --directory aiassistant\frontend\assets
)

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start web server. 
    echo         Make sure Python is installed and Port 8080 is free.
)

pause
