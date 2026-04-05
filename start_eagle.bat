@echo off
REM ============================================================
REM  Eagle — Start API + Frontend
REM  Usage: double-click to start both servers
REM  API:      http://localhost:8000 (docs at /docs)
REM  Frontend: http://localhost:3000
REM ============================================================

set LOCAL=C:\Dev\eagle

echo.
echo ============================================================
echo   Eagle Report Viewer - Startup
echo ============================================================
echo.

REM ── Check Python venv ──────────────────────────────────────
if not exist "%LOCAL%\.venv\Scripts\activate.bat" (
    echo   ERROR: Python venv not found at %LOCAL%\.venv
    echo   Run: python -m venv .venv
    pause
    exit /b 1
)

REM ── Check Node.js ──────────────────────────────────────────
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo   ERROR: Node.js not found on PATH
    echo   Install from https://nodejs.org
    pause
    exit /b 1
)

REM ── Install frontend dependencies if needed ────────────────
if not exist "%LOCAL%\frontend\node_modules" (
    echo   [0/3] Installing frontend dependencies...
    cd /d "%LOCAL%\frontend" && npm install
    echo   Done.
    echo.
)

REM ── Run database schema migration ─────────────────────────
echo   [1/3] Initializing database schema...
cd /d "%LOCAL%" && .venv\Scripts\activate.bat && python -c "import sys; sys.path.insert(0,'Application'); from persistence.report_store import ReportStore; ReportStore(); print('    Database OK')"
echo.

REM ── Start FastAPI backend in background ────────────────────
echo   [2/3] Starting FastAPI API on port 8000...
start "Eagle API" cmd /k "cd /d %LOCAL% && .venv\Scripts\activate.bat && uvicorn api.main:app --reload --port 8000"

REM ── Start Next.js frontend in background ───────────────────
echo   [3/3] Starting Next.js frontend on port 3000...
start "Eagle Frontend" cmd /k "cd /d %LOCAL%\frontend && npm run dev"

REM ── Wait a moment then open browser ────────────────────────
timeout /t 5 /nobreak >nul
start http://localhost:3000

echo.
echo   Both servers started!
echo   API:      http://localhost:8000/docs
echo   Frontend: http://localhost:3000
echo.
echo   Close the two command windows to stop the servers.
echo ============================================================
