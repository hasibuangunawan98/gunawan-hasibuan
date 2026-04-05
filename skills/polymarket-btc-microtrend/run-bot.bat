@echo off
echo ========================================
echo   Polymarket BTC Microtrend Bot
echo   Real-Time Data Feed + Signal Bot
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Installing dependencies...
python -m pip install websocket-client -q

echo.
echo Starting WebSocket Bridge (real-time data feed)...
echo Press Ctrl+C to stop
echo.

REM Start WebSocket bridge in background
start "BTC WebSocket Bridge" cmd /k "python scripts/btc_ws_bridge.py"

REM Wait for WebSocket to connect
timeout /t 5 /nobreak >nul

echo.
echo Starting BTC Signal Bot...
echo.

REM Run signal bot
python scripts/btc_bot.py auto-btc

echo.
echo Bot finished. Check data/dashboard.html for results.
echo.
pause
