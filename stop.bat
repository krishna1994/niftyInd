@echo off
REM stop.bat — Stop the Nifty Signal Analyzer servers on Windows
echo [stop] Stopping Nifty Signal Analyzer...

REM Kill by window title
taskkill /FI "WINDOWTITLE eq NiftyBackend" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq NiftyFrontend" /F >nul 2>&1

REM Kill by port as fallback (backend runs on 8001, not 8000, on this machine
REM because port 8000 is occupied by a Windows system/endpoint-security process)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8001 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo [stop] All servers stopped.