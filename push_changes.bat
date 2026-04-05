@echo off
REM ============================================================
REM  Eagle — Commit and push all changes to GitHub
REM  Usage: double-click or run from PowerShell
REM ============================================================

cd /d C:\Dev\eagle

echo.
echo ============================================================
echo   Eagle — Push changes to GitHub
echo ============================================================
echo.

REM ── Show what changed ──────────────────────────────────────
echo   Changed files:
echo   ---
git status --short
echo.

REM ── Ask for commit message ─────────────────────────────────
set /p MSG="  Commit message: "

if "%MSG%"=="" (
    echo   No message entered. Aborting.
    pause
    exit /b
)

REM ── Stage, commit, push ────────────────────────────────────
git add -A
git commit -m "%MSG%"
git push

echo.
echo ============================================================
echo   Done! Latest commits:
echo ============================================================
echo.

git log --oneline -5

echo.
pause
