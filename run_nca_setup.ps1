# ── Project Eagle: NCA Register Setup & Backfill ─────────────────────
# Run from C:\Dev\eagle after sync_to_local.bat
# ─────────────────────────────────────────────────────────────────────

# Step 1: Create/recreate NCA tables (nca_aifm, nca_aif, nca_registrations)
#         Also extends gleif_lei_cache with new columns
Write-Host "`n=== Step 1: Setup NCA tables ===" -ForegroundColor Cyan
python Application/reference_data/setup_nca_tables.py

# Step 2: Backfill normalized_name in GLEIF cache using unified clean_name()
Write-Host "`n=== Step 2: Backfill GLEIF normalized names ===" -ForegroundColor Cyan
python Application/reference_data/fetch_gleif_lei.py backfill-names

# Step 3: Fetch NCA register data (AFM, CSSF, ESMA)
Write-Host "`n=== Step 3: Fetch NCA registers ===" -ForegroundColor Cyan
python Application/reference_data/fetch_nca_registers.py fetch-all

# Step 4: Enrich from GLEIF (addresses + inherit AIFM address to AIFs)
Write-Host "`n=== Step 4: Enrich from GLEIF ===" -ForegroundColor Cyan
python Application/reference_data/fetch_nca_registers.py enrich-gleif

# Step 5: LEI lookup for entities without LEI (clean_name + country → GLEIF)
Write-Host "`n=== Step 5: Enrich LEI by name ===" -ForegroundColor Cyan
python Application/reference_data/fetch_nca_registers.py enrich-lei

# Step 6: Report
Write-Host "`n=== Step 6: NCA Register Report ===" -ForegroundColor Cyan
python Application/reference_data/fetch_nca_registers.py report

Write-Host "`n=== Done ===" -ForegroundColor Green
