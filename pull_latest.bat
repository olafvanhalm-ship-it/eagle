@echo off
REM ============================================================
REM  Eagle — Pull latest changes from GitHub
REM  Usage: double-click or run from PowerShell
REM ============================================================

cd /d C:\Dev\eagle

echo.
echo ============================================================
echo   Pulling latest changes from GitHub...
echo ============================================================
echo.

git pull

echo.
echo ============================================================
echo   Current status:
echo ============================================================
echo.

git log --oneline -5

echo.
echo ============================================================
echo   Done!
echo ============================================================
pause
