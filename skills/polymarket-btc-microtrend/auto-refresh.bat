@echo off
echo ========================================
echo   BTC Polymarket - Auto Refresh Mode
echo   Continuous data update (5s interval)
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

echo Starting auto-refresh loop...
echo Press Ctrl+C to stop
echo.

:loop
python scripts/btc_bot.py scan-btc >nul 2>&1
timeout /t 5 /nobreak >nul
goto loop
