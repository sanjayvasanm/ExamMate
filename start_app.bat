@echo off
title Exam Mate AI - Flutter App
color 0B

set "PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0;%SystemRoot%\System32;%SystemRoot%;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Windows\System32;C:\Program Files\PowerShell\7;%PATH%"

cd /d "%~dp0aiassistant\frontend"

call start_app.bat
