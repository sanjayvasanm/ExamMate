@echo off
title Exam Mate - Flutter App
color 0B

set "PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0;%SystemRoot%\System32;%SystemRoot%;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Windows\System32;C:\Program Files\PowerShell\7;%PATH%"

:: Detect Android Studio bundled Java (JBR 17/21) or standard JDK 17/21
if exist "C:\Program Files\Android\Android Studio\jbr\bin\java.exe" (
    set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
    set "PATH=C:\Program Files\Android\Android Studio\jbr\bin;%PATH%"
) else if exist "C:\Program Files\Android\Android Studio\jre\bin\java.exe" (
    set "JAVA_HOME=C:\Program Files\Android\Android Studio\jre"
    set "PATH=C:\Program Files\Android\Android Studio\jre\bin;%PATH%"
) else if exist "C:\Program Files\Java\jdk-17\bin\java.exe" (
    set "JAVA_HOME=C:\Program Files\Java\jdk-17"
    set "PATH=C:\Program Files\Java\jdk-17\bin;%PATH%"
) else if exist "C:\Program Files\Java\jdk-21\bin\java.exe" (
    set "JAVA_HOME=C:\Program Files\Java\jdk-21"
    set "PATH=C:\Program Files\Java\jdk-21\bin;%PATH%"
)

cd /d "%~dp0"

echo [*] Getting Flutter packages...
call flutter pub get

echo.
echo [+] Launching Exam Mate...
echo.

call flutter run

pause
