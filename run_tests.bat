@echo off
REM ============================================================
REM  Eagle — Run regression tests + sync evidence to Google Drive
REM  Usage: double-click or run from PowerShell
REM ============================================================

set LOCAL=C:\Dev\eagle
set DRIVE=C:\Users\olafv\Mijn Drive (olaf.van.halm@maxxmanagement.nl)\Project Eagle

REM ── Activate venv ──────────────────────────────────────────
call "%LOCAL%\.venv\Scripts\activate.bat"

REM ── Parse argument (default: realdata) ─────────────────────
set SCOPE=%1
if "%SCOPE%"=="" set SCOPE=realdata

echo.
echo ============================================================
echo   Running %SCOPE% regression suite...
echo ============================================================
echo.

if "%SCOPE%"=="realdata" (
    python "%LOCAL%\Application\Adapters\Input adapters\M adapter\run_regression_realdata.py"
)
if "%SCOPE%"=="synthetic" (
    python "%LOCAL%\Application\Adapters\Input adapters\M adapter\run_regression_synthetic.py"
)
if "%SCOPE%"=="all" (
    python "%LOCAL%\Application\Adapters\Input adapters\M adapter\run_regression_suite.py"
)
if "%SCOPE%"=="review" (
    python "%LOCAL%\Testing\test_review_api.py"
)

REM ── Sync evidence to Google Drive ──────────────────────────
echo.
echo ============================================================
echo   Syncing evidence to Google Drive...
echo ============================================================

REM Create timestamped folder
for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value') do set DT=%%a
set RUNFOLDER=%DT:~0,8%_%DT:~8,4%

set EVIDENCE_DEST=%DRIVE%\Testing\Test results\%RUNFOLDER%

REM Copy M adapter evidence
if exist "%LOCAL%\Application\Adapters\Input adapters\M adapter\golden_set\evidence" (
    robocopy "%LOCAL%\Application\Adapters\Input adapters\M adapter\golden_set\evidence" "%EVIDENCE_DEST%\M adapter" /E /NJH /NJS /NDL >nul
    echo   [OK] M adapter evidence copied
)

REM Copy ESMA adapter evidence
if exist "%LOCAL%\Application\Adapters\Input adapters\ESMA adapter\evidence" (
    robocopy "%LOCAL%\Application\Adapters\Input adapters\ESMA adapter\evidence" "%EVIDENCE_DEST%\ESMA adapter" /E /NJH /NJS /NDL >nul
    echo   [OK] ESMA adapter evidence copied
)

REM Copy FCA adapter evidence
if exist "%LOCAL%\Application\Adapters\Input adapters\FCA adapter\evidence" (
    robocopy "%LOCAL%\Application\Adapters\Input adapters\FCA adapter\evidence" "%EVIDENCE_DEST%\FCA adapter" /E /NJH /NJS /NDL >nul
    echo   [OK] FCA adapter evidence copied
)

REM Copy regression YAML summary
for %%f in ("%LOCAL%\Application\Adapters\Input adapters\M adapter\regression_*.yaml") do (
    copy "%%f" "%EVIDENCE_DEST%\" >nul 2>nul
    echo   [OK] Regression summary copied
)

echo.
echo   Evidence saved to: %EVIDENCE_DEST%
echo ============================================================
echo   Done!
echo ============================================================
pause
