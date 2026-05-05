@echo off
title Exam Mate - Backend Server
color 0A

echo ============================================
echo   EXAM MATE - Flask Backend (Port 5000)
echo ============================================
echo.

cd /d "%~dp0"

:: Check if venv exists, create if not
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment...
    python -m venv venv
    echo [+] Virtual environment created.
)

:: Activate venv
set PYTHONUTF8=1
call venv\Scripts\activate.bat

:: Install / upgrade dependencies
echo [*] Installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo [+] Dependencies ready.
echo [+] Starting Flask server on http://0.0.0.0:5000
echo [+] Accessible at: http://10.174.238.113:5000 (Same Wi-Fi)
echo [+] Database: Supabase (cxhxgtmedbldfmofortm.supabase.co)
echo [+] AI Engine: Groq (llama-3.3-70b-versatile)
echo.
echo     Make sure SUPABASE_URL and SUPABASE_KEY in .env are valid.
echo     Make sure GROQ_API_KEY in .env is valid.
echo.
echo Press Ctrl+C to stop the server.
echo ============================================
echo.

python app.py

pause
