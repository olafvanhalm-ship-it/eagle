@echo off
REM ============================================================
REM sync_evidence_to_drive.bat
REM Copies all regression evidence from local dev to Google Drive
REM Run this AFTER a regression test run to archive results
REM ============================================================

set LOCAL=C:\Dev\eagle
set DRIVE=C:\Users\olafv\Mijn Drive (olaf.van.halm@maxxmanagement.nl)\Project Eagle\Testing\Test results

REM Create timestamped folder on Drive
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set DATESTR=%%c%%b%%a
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set TIMESTR=%%a%%b
set RUNFOLDER=%DATESTR%_%TIMESTR%

echo.
echo === Syncing evidence to Google Drive ===
echo Run folder: %RUNFOLDER%
echo.

REM M adapter evidence
if exist "%LOCAL%\Application\Adapters\Input adapters\M adapter\golden_set\evidence" (
    echo Copying M adapter evidence...
    robocopy "%LOCAL%\Application\Adapters\Input adapters\M adapter\golden_set\evidence" "%DRIVE%\%RUNFOLDER%\M adapter" /E /NJH /NJS
)

REM ESMA adapter evidence
if exist "%LOCAL%\Application\Adapters\Input adapters\ESMA 1.2 adapter\golden_set\evidence" (
    echo Copying ESMA adapter evidence...
    robocopy "%LOCAL%\Application\Adapters\Input adapters\ESMA 1.2 adapter\golden_set\evidence" "%DRIVE%\%RUNFOLDER%\ESMA adapter" /E /NJH /NJS
)

REM FCA adapter evidence
if exist "%LOCAL%\Application\Adapters\Input adapters\FCA 2.0 adapter\golden_set\evidence" (
    echo Copying FCA adapter evidence...
    robocopy "%LOCAL%\Application\Adapters\Input adapters\FCA 2.0 adapter\golden_set\evidence" "%DRIVE%\%RUNFOLDER%\FCA adapter" /E /NJH /NJS
)

echo.
echo === Done! Evidence saved to: ===
echo %DRIVE%\%RUNFOLDER%
echo.
pause
