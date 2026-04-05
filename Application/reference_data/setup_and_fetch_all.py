# One-click setup: create schema + fetch all public reference data.
#
# Usage (PowerShell):
#     cd "C:\Users\olafv\Mijn Drive (olaf.van.halm@maxxmanagement.nl)\Project Eagle"
#     pip install psycopg2-binary requests openpyxl
#     python Application\reference_data\setup_and_fetch_all.py
#
# This will:
#   1. Connect to your local PostgreSQL (localhost:5432, database 'postgres')
#   2. Create the aifmd schema + reference data tables
#   3. Fetch ECB exchange rates (full history since 1999)
#   4. Fetch MIC codes (ISO 10383)
#   5. Print a freshness report
#
# For GLEIF LEI lookups, run separately:
#     python Application\reference_data\fetch_gleif_lei.py lookup <LEI>

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.reference_store import ReferenceStore
from reference_data.fetch_ecb_rates import fetch_backfill
from reference_data.fetch_mic_codes import fetch_mic_codes
from reference_data.config import PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    print("=" * 60)
    print("  Project Eagle — Reference Data Setup")
    print("=" * 60)

    # ── Step 1: Connect + create schema ───────────────────────────
    print("\n[1/4] Connecting to PostgreSQL...")
    try:
        store = ReferenceStore.postgresql(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DBNAME,
            user=PG_USER,
            password=PG_PASSWORD,
        )
        print(f"  Connected to {PG_HOST}:{PG_PORT}/{PG_DBNAME}")
        print("  Schema 'aifmd' created (or already exists)")
    except Exception as e:
        print(f"\n  ERROR: Could not connect to PostgreSQL: {e}")
        print(f"\n  Check that PostgreSQL is running and these settings are correct:")
        print(f"    host={PG_HOST} port={PG_PORT} dbname={PG_DBNAME} user={PG_USER}")
        print(f"\n  If your password is set, edit PG_PASSWORD in this script.")
        sys.exit(1)

    # ── Step 2: ECB exchange rates ────────────────────────────────
    print("\n[2/4] Fetching ECB exchange rates (full history since 1999)...")
    print("  This fetches ~200KB of XML and inserts ~217K rows. Takes ~30 seconds.")
    try:
        result = fetch_backfill(store)
        print(f"  Done: {result['rates_stored']} rates, "
              f"{result['date_count']} dates, "
              f"range {result['date_range'][0]} to {result['date_range'][1]}")
    except Exception as e:
        print(f"  WARNING: ECB fetch failed: {e}")
        print("  You can retry later: python Application/reference_data/fetch_ecb_rates.py backfill")

    # ── Step 3: MIC codes ─────────────────────────────────────────
    print("\n[3/4] Fetching ISO 10383 MIC codes...")
    try:
        result = fetch_mic_codes(store)
        print(f"  Done: {result['total_records']} codes, "
              f"{result['active']} active, "
              f"{result['countries']} countries")
    except Exception as e:
        print(f"  WARNING: MIC fetch failed: {e}")
        print("  You can retry later: python Application/reference_data/fetch_mic_codes.py")

    # ── Step 4: Freshness report ──────────────────────────────────
    print("\n[4/4] Freshness report (REQ-REF-002):")
    report = store.get_freshness_report()
    for name, info in report.items():
        count = info.get("record_count", 0)
        fetched = info.get("last_fetched", "never")
        print(f"  {name:20s}  {count:>8,} records  last fetched: {fetched}")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Setup complete!")
    print()
    print("  Tables created in schema 'aifmd':")
    print("    - aifmd.ecb_rates")
    print("    - aifmd.gleif_lei_cache")
    print("    - aifmd.mic_codes")
    print()
    print("  Next steps:")
    print("    - Open pgAdmin 4 → Project Eagle local → Databases → postgres → Schemas → aifmd")
    print("    - GLEIF lookups: python Application/reference_data/fetch_gleif_lei.py lookup <LEI>")
    print("    - Daily ECB refresh: python Application/reference_data/fetch_ecb_rates.py daily")
    print("=" * 60)

    store.close()


if __name__ == "__main__":
    main()
