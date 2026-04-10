@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  Eagle — Start Report Viewer (API + Frontend)
REM  Usage: double-click to start both servers
REM  API:      http://localhost:8000 (docs at /docs)
REM  Frontend: http://localhost:3000
REM ============================================================

set LOCAL=C:\Dev\eagle
set DATABASE_URL=postgresql://eagle_app:eagle_dev_local@localhost:5432/eagle_dev
set "DRIVE_ROOT=C:\Users\olafv\Mijn Drive (olaf.van.halm@maxxmanagement.nl)\Project Eagle"

echo.
echo ============================================================
echo   Eagle Report Viewer - Startup
echo ============================================================
echo.

REM ── Verify local directory exists ─────────────────────────────
if not exist "%LOCAL%" (
    echo   ERROR: Directory %LOCAL% does not exist.
    echo   Create it first and copy the project files there.
    pause
    exit /b 1
)
cd /d "%LOCAL%"

REM ── Kill old Eagle processes ───────────────────────────────
echo   Stopping old Eagle processes...

REM Kill process on port 8000 (API)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo     Killing API process PID %%a on port 8000
    taskkill /F /PID %%a >nul 2>nul
)

REM Kill process on port 3000 (Frontend)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo     Killing Frontend process PID %%a on port 3000
    taskkill /F /PID %%a >nul 2>nul
)

REM Also kill any lingering node/uvicorn windows
taskkill /FI "WINDOWTITLE eq Eagle API*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Eagle Frontend*" /F >nul 2>nul

echo   Done.
echo.

REM ── Check Python venv ──────────────────────────────────────
echo   Checking Python venv...
if not exist "%LOCAL%\.venv\Scripts\activate.bat" (
    echo   ERROR: Python venv not found at %LOCAL%\.venv
    echo   Run:  cd %LOCAL% ^&^& python -m venv .venv
    pause
    exit /b 1
)
echo   Python venv OK.

REM ── Check Node.js ──────────────────────────────────────────
echo   Checking Node.js...
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo   ERROR: Node.js not found on PATH
    echo   Install from https://nodejs.org
    pause
    exit /b 1
)
echo   Node.js OK.
echo.

REM ── Sync files from Google Drive to local dev ─────────────
echo   [0/4] Syncing files from Google Drive to %LOCAL%...
if not exist "!DRIVE_ROOT!\sync_to_local.bat" goto :skip_sync
echo   Running sync_to_local.bat...
call "!DRIVE_ROOT!\sync_to_local.bat"
cd /d "%LOCAL%"
echo   Sync complete.
goto :done_sync
:skip_sync
echo   WARNING: sync_to_local.bat not found. Skipping sync.
echo   Make sure files at %LOCAL% are up to date manually.
:done_sync
echo.

REM ── Install frontend dependencies if needed ────────────────
if not exist "%LOCAL%\frontend\node_modules" (
    echo   Installing frontend dependencies...
    cd /d "%LOCAL%\frontend"
    call npm install
    cd /d "%LOCAL%"
    echo   Done.
    echo.
)

REM ── Run database schema migration ─────────────────────────
echo   [1/4] Initializing database schema...
call .venv\Scripts\activate.bat
python -c "import sys,os;os.environ['DATABASE_URL']='postgresql://eagle_app:eagle_dev_local@localhost:5432/eagle_dev';sys.path.insert(0,'Application');from persistence.report_store import ReportStore;ReportStore();print('    Database OK')"
if %errorlevel% neq 0 (
    echo   WARNING: Database init returned an error. Continuing anyway...
)
echo.

REM ── Start FastAPI backend in background ────────────────────
echo   [2/4] Starting FastAPI API on port 8000...
REM  Note: --reload removed — it caused new endpoints to not be served.
REM  After code changes, restart the server manually (close + rerun this script).
start "Eagle API" cmd /k "cd /d %LOCAL% && set DATABASE_URL=postgresql://eagle_app:eagle_dev_local@localhost:5432/eagle_dev && call .venv\Scripts\activate.bat && python -m uvicorn api.main:app --port 8000"

REM ── Start Next.js frontend in background ───────────────────
echo   [3/4] Starting Next.js frontend on port 3000...
start "Eagle Frontend" cmd /k "cd /d %LOCAL%\frontend && call npm run dev"

REM ── Wait a moment then open browser ────────────────────────
echo.
echo   Waiting 5 seconds for servers to start...
timeout /t 5 /nobreak >nul
start http://localhost:3000

echo.
echo   Both servers started!
echo   API:      http://localhost:8000/docs
echo   Frontend: http://localhost:3000
echo.
echo   Close the two command windows to stop the servers.
echo ============================================================
echo.
pause
