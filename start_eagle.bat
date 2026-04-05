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
echo   Starting Eagle servers...
echo ============================================================
echo.

REM ── Start FastAPI backend in background ────────────────────
echo   [1/2] Starting FastAPI API on port 8000...
start "Eagle API" cmd /k "cd /d %LOCAL% && .venv\Scripts\activate.bat && uvicorn api.main:app --reload --port 8000"

REM ── Start Next.js frontend in background ───────────────────
echo   [2/2] Starting Next.js frontend on port 3000...
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
