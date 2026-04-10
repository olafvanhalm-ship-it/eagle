@echo off
REM ============================================================================
REM sync_to_local.bat — Copy Project Eagle files from Google Drive to C:\Dev\eagle
REM
REM Usage:
REM   Double-click            — sync + pause at end
REM   call sync_to_local.bat  — sync + return immediately (used by start_UI_eagle)
REM ============================================================================

setlocal EnableDelayedExpansion

REM --- Configuration ---------------------------------------------------------
set "DRIVE_ROOT=C:\Users\olafv\Mijn Drive (olaf.van.halm@maxxmanagement.nl)\Project Eagle"
set "LOCAL_ROOT=C:\Dev\eagle"

REM Detect if called from another script (no pause) or double-clicked (pause)
set "INTERACTIVE=1"
echo %cmdcmdline% | findstr /i /c:"/c" >nul && set "INTERACTIVE=0"

REM Check if paths exist
if not exist "!DRIVE_ROOT!\" (
    echo [ERROR] Google Drive path not found: !DRIVE_ROOT!
    if "!INTERACTIVE!"=="1" pause
    exit /b 1
)
if not exist "!LOCAL_ROOT!\" (
    echo [ERROR] Local dev path not found: !LOCAL_ROOT!
    if "!INTERACTIVE!"=="1" pause
    exit /b 1
)

echo.
echo ============================================================================
echo  Project Eagle — Sync Google Drive to Local Dev  [v2 2026-04-10]
echo ============================================================================
echo  Source: !DRIVE_ROOT!
echo  Target: !LOCAL_ROOT!
echo.

REM --- All project files (deduplicated, one copy per file) --------------------

echo --- API backend ---
call :cp "api\__init__.py"
call :cp "api\main.py"
call :cp "api\deps.py"
call :cp "api\routers\__init__.py"
call :cp "api\models\__init__.py"
call :cp "api\routers\report.py"
call :cp "api\routers\session.py"
call :cp "api\routers\validation.py"
call :cp "api\routers\registry.py"
call :cp "api\models\requests.py"
call :cp "api\models\responses.py"

echo.
echo --- Frontend ---
call :cp "frontend\app\page.js"
call :cp "frontend\app\layout.js"

echo.
echo --- Persistence ---
call :cp "Application\persistence\report_store.py"
call :cp "Application\persistence\schema.sql"

echo.
echo --- Application core ---
call :cp "Application\canonical\aifmd_xml_field_extractor.py"
call :cp "Application\canonical\aifmd_field_registry.py"
call :cp "Application\validation\validate_aifmd_xml.py"
call :cp "Application\validation\aifmd_approved_rule_hashes.yaml"
call :cp "Application\lessons_learned.md"

echo.
echo --- Regulation YAML ---
call :cp "Application\regulation\aifmd\annex_iv\aifmd_validation_rules.yaml"

echo.
echo --- NCA overrides ---
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_at_fma.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_be_fsma.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_bg_fsc.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_cy_cysec.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_cz_cnb.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_de_bafin.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_dk_finanstilsynet.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_ee_fsa.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_es_cnmv.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_fi_finfsa.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_fr_amf.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_gb_fca.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_gr_hcmc.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_hr_hanfa.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_hu_mnb.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_ie_cbi.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_is_cbi.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_it_consob.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_li_fma.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_lt_lb.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_lu_cssf.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_lv_lb.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_mt_mfsa.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_nl_afm.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_no_finanstilsynet.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_pl_knf.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_pt_cmvm.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_ro_asf.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_se_fi.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_si_atvp.yaml"
call :cp "Application\regulation\aifmd\annex_iv\nca_overrides\aifmd_nca_overrides_sk_nbs.yaml"

echo.
echo --- M adapter ---
call :cp "Application\Adapters\Input adapters\M adapter\m_adapter.py"
call :cp "Application\Adapters\Input adapters\M adapter\m_column_schema_v1.yaml"
call :cp "Application\Adapters\Input adapters\M adapter\m_parser\__init__.py"
call :cp "Application\Adapters\Input adapters\M adapter\m_parser\record.py"
call :cp "Application\Adapters\Input adapters\M adapter\m_parser\schema_loader.py"
call :cp "Application\Adapters\Input adapters\M adapter\run_regression_suite.py"
call :cp "Application\Adapters\Input adapters\M adapter\run_regression_realdata.py"
call :cp "Application\Adapters\Input adapters\M adapter\run_regression_synthetic.py"

echo.
echo --- Testing ---
call :cp "Testing\run_all_regressions.py"
call :cp "run_regressions.bat"

echo.
echo --- Startup scripts ---
call :cp "start_UI_eagle.bat"
call :cp "start_eagle.bat"
call :cp "sync_to_local.bat"
call :cp "run_tests.bat"

echo.
echo ============================================================================
echo  Sync complete.
echo ============================================================================
echo.

if "!INTERACTIVE!"=="1" (
    echo  Next: run start_UI_eagle.bat to start the servers.
    echo.
    pause
)
exit /b 0

REM ============================================================================
REM Subroutine: copy one file from Drive to Local
REM ============================================================================
:cp
set "REL=%~1"
set "SRC=!DRIVE_ROOT!\!REL!"
set "DST=!LOCAL_ROOT!\!REL!"

REM Create target directory if needed
for %%F in ("!DST!") do if not exist "%%~dpF" mkdir "%%~dpF" 2>nul

if not exist "!SRC!" (
    echo   [SKIP] !REL!
    exit /b
)

copy /Y "!SRC!" "!DST!" >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK]   !REL!
) else (
    echo   [FAIL] !REL!
)
exit /b
