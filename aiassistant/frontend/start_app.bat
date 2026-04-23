@echo off
title Exam Mate - Flutter App
color 0B

echo ============================================
echo   EXAM MATE - Flutter App (Windows)
echo ============================================
echo.

cd /d "%~dp0"

echo [*] Getting Flutter packages...
flutter pub get

echo.
echo [+] Launching Exam Mate on Windows...
echo     Make sure the backend is running first (start_backend.bat)
echo.

flutter run -d windows

pause
