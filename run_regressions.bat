@echo off
REM ============================================================================
REM run_regressions.bat — Run Project Eagle regression suite from project root
REM
REM Usage:
REM   run_regressions.bat                  — Run all adapters
REM   run_regressions.bat --adapter m      — Run only M adapter
REM   run_regressions.bat --compliance     — Include Excel compliance report
REM   run_regressions.bat --list           — List registered adapters
REM ============================================================================

setlocal EnableDelayedExpansion

set "SCRIPT=%~dp0Testing\run_all_regressions.py"

if not exist "!SCRIPT!" (
    echo [ERROR] Regression script not found: !SCRIPT!
    pause
    exit /b 1
)

python "!SCRIPT!" %*
set "RC=!errorlevel!"

echo.
if "!RC!"=="0" (
    echo  ALL PASS
) else (
    echo  FAILURES DETECTED — see Testing\Test results\ for details
)

REM Detect if called from another script (no pause) or double-clicked (pause)
set "INTERACTIVE=1"
echo %cmdcmdline% | findstr /i /c:"/c" >nul && set "INTERACTIVE=0"
if "!INTERACTIVE!"=="1" pause

exit /b !RC!
