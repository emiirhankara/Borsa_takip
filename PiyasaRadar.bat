@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Sanal ortam bulunamadi. Once README.md icindeki kurulum adimlarini uygulayin.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
