@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM start.bat — Launch the Nifty Signal Analyzer on Windows
REM Usage:  start.bat
REM         start.bat --install   (also installs/updates dependencies first)
REM ─────────────────────────────────────────────────────────────────────────────
setlocal enabledelayedexpansion

set ROOT_DIR=%~dp0
set BACKEND_DIR=%ROOT_DIR%backend
set FRONTEND_DIR=%ROOT_DIR%frontend
set VENV_DIR=%BACKEND_DIR%\venv_new
set CA_BUNDLE=%BACKEND_DIR%\combined_ca.pem
set BACKEND_PORT=8001

echo [start] Nifty Signal Analyzer — Windows Launcher

REM ── Optional dependency install ──────────────────────────────────────────────
if "%1"=="--install" (
    echo [start] Creating/updating Python 3.11 virtual environment...
    py -3.11 -m venv "%VENV_DIR%"
    echo [start] Installing Python dependencies...
    "%VENV_DIR%\Scripts\pip.exe" install --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org -r "%BACKEND_DIR%\requirements.txt"
    if errorlevel 1 ( echo [error] pip install failed && exit /b 1 )
    echo [start] Installing Node dependencies...
    cd /d "%FRONTEND_DIR%" && npm install
    if errorlevel 1 ( echo [error] npm install failed && exit /b 1 )
    cd /d "%ROOT_DIR%"
)

REM ── Check prerequisites ───────────────────────────────────────────────────────
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [error] Python 3.11 virtual environment not found at %VENV_DIR%
    echo [error] Run: start.bat --install
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo [error] node not found. Install Node.js 18+ from https://nodejs.org and try again.
    exit /b 1
)

REM ── Check Node dependencies ───────────────────────────────────────────────────
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [warn] Node modules not found. Installing...
    cd /d "%FRONTEND_DIR%" && npm install && cd /d "%ROOT_DIR%"
)

REM ── Kill existing processes on backend port and 3000 ─────────────────────────
echo [start] Checking for existing processes on ports %BACKEND_PORT% and 3000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo [start] Port cleanup done
timeout /t 1 /nobreak >nul

REM ── Start backend ─────────────────────────────────────────────────────────────
REM NOTE: Runs on port 8001 (not 8000) because port 8000 is occupied by a
REM Windows system/endpoint-security process on this machine.
REM NOTE: CURL_CA_BUNDLE / SSL_CERT_FILE / REQUESTS_CA_BUNDLE point at a combined
REM CA bundle (certifi + corporate Netskope root CA) so yfinance/requests can
REM fetch live market data through the corporate SSL-inspecting proxy.
echo [start] Starting FastAPI backend on http://localhost:%BACKEND_PORT% ...
cd /d "%BACKEND_DIR%"
start "NiftyBackend" /min cmd /c "set CURL_CA_BUNDLE=%CA_BUNDLE%&& set SSL_CERT_FILE=%CA_BUNDLE%&& set REQUESTS_CA_BUNDLE=%CA_BUNDLE%&& "%VENV_DIR%\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload"
cd /d "%ROOT_DIR%"

REM Give the backend a moment to bind
timeout /t 4 /nobreak >nul

REM Quick health check
curl -sf http://localhost:%BACKEND_PORT%/api/health >nul 2>&1
if errorlevel 1 (
    echo [warn] Backend health check failed - it may still be starting up ^(CAS warm-start takes ~10s^)
) else (
    echo [start] Backend is up
)

REM ── Start frontend ────────────────────────────────────────────────────────────
echo [start] Starting React frontend on http://localhost:3000 ...
cd /d "%FRONTEND_DIR%"
set BROWSER=none
start "NiftyFrontend" /min cmd /c "npm start"
cd /d "%ROOT_DIR%"

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Nifty Signal Analyzer
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Frontend  -^>  http://localhost:3000
echo   Backend   -^>  http://localhost:%BACKEND_PORT%
echo   API docs  -^>  http://localhost:%BACKEND_PORT%/docs
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Two minimized windows opened: NiftyBackend + NiftyFrontend
echo   Run stop.bat to stop both servers.
echo.