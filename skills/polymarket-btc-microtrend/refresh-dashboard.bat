@echo off
echo ========================================
echo   Refresh BTC Polymarket Dashboard
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

echo Running BTC signal scan...
python scripts/btc_bot.py scan-btc

echo.
echo Dashboard refreshed!
echo Opening dashboard in browser...
start data/dashboard.html

echo.
echo Done.
pause
