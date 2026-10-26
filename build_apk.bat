@echo off
setlocal enabledelayedexpansion
title Exam Mate - Build Android APK (Release)
color 0A

:: Ensure standard Windows System and PowerShell paths are available in PATH
set "PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0;%SystemRoot%\System32;%SystemRoot%;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Windows\System32;C:\Program Files\PowerShell\7;%PATH%"

echo ============================================
echo   EXAM MATE AI - Android APK Build
echo ============================================
echo.

set "FOUND_JDK="

:: 1. Search Eclipse Adoptium Temurin 17 (Freshly Installed!)
for /d %%D in ("C:\Program Files\Eclipse Adoptium\jdk-17*") do (
    if exist "%%~fD\bin\java.exe" (
        set "FOUND_JDK=%%~fD"
    )
)

:: 2. Search Microsoft JDK 17
if not defined FOUND_JDK (
    for /d %%D in ("C:\Program Files\Microsoft\jdk-17*") do (
        if exist "%%~fD\bin\java.exe" set "FOUND_JDK=%%~fD"
    )
)

:: 3. Search Standard Java JDK 17 / 21
if not defined FOUND_JDK (
    for /d %%D in ("C:\Program Files\Java\jdk-17*") do (
        if exist "%%~fD\bin\java.exe" set "FOUND_JDK=%%~fD"
    )
)
if not defined FOUND_JDK (
    for /d %%D in ("C:\Program Files\Java\jdk-21*") do (
        if exist "%%~fD\bin\java.exe" set "FOUND_JDK=%%~fD"
    )
)

:: 4. Search Android Studio JBR
if not defined FOUND_JDK (
    for %%P in (
        "C:\Program Files\Android\Android Studio\jbr"
        "C:\Program Files\Android\Android Studio\jre"
        "%LOCALAPPDATA%\Android\Android Studio\jbr"
    ) do (
        if exist "%%~fP\bin\java.exe" set "FOUND_JDK=%%~fP"
    )
)

if defined FOUND_JDK (
    echo [+] Configured Android-compatible JDK:
    echo     !FOUND_JDK!
    echo.
    set "JAVA_HOME=!FOUND_JDK!"
    set "PATH=!FOUND_JDK!\bin;!PATH!"
    echo [*] Setting Flutter JDK configuration...
    call flutter config --jdk-dir="!FOUND_JDK!"
) else (
    echo [ERROR] Could not locate JDK 17 in standard paths.
    pause
    exit /b 1
)

cd /d "%~dp0aiassistant\frontend"

echo.
echo [*] Cleaning previous build caches...
call flutter clean

echo.
echo [*] Resolving Flutter dependencies...
call flutter pub get

echo.
echo [*] Building optimized release APK (using JDK 17)...
call flutter build apk --release --android-skip-build-dependency-validation

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo [+] SUCCESS! Production Android APK is ready:
    echo     %cd%\build\app\outputs\flutter-apk\app-release.apk
    echo ========================================================
) else (
    echo.
    echo [ERROR] APK build encountered an issue.
)

pause
