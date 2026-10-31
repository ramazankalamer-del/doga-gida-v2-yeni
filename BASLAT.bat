@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 veya ustunu kurup tekrar deneyin. Kurulumda Add Python to PATH secin.
  pause
  exit /b 1
)
python baslat.py
if errorlevel 1 pause
