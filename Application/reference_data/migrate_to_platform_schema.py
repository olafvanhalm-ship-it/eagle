"""Migrate reference data tables from aifmd schema to platform schema.

This migration:
  1. Creates the platform schema (if not exists)
  2. Moves ecb_rates, gleif_lei_cache, mic_codes from aifmd.* to platform.*
  3. Creates the new platform.nca_registered_entities table (REQ-REF-003)
  4. Recreates indexes on platform.* tables
  5. Drops the old aifmd.* reference tables (after data migration)

Usage (PowerShell):
    cd "C:\Dev\eagle"
    python Application\reference_data\migrate_to_platform_schema.py

Architecture reference: eagle_software_architecture.md §6.3
Rationale: P4 (single source of truth) + P15 (platform-first, product-second).
Reference data is product-agnostic — consumed by MOD-ADMIN, MOD-DATA, MOD-GTM,
MOD-TRIAL, and MOD-CLIENT. It must not live in a product-specific schema.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reference_data.config import PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


# ── Migration SQL statements ─────────────────────────────────────────

MIGRATION_STEPS = [
    # Step 1: Ensure platform schema exists
    (
        "Create platform schema",
        "CREATE SCHEMA IF NOT EXISTS platform;",
    ),

    # Step 2a: Create new platform.ecb_rates table
    (
        "Create platform.ecb_rates",
        """
        CREATE TABLE IF NOT EXISTS platform.ecb_rates (
            rate_date       DATE          NOT NULL,
            base_currency   CHAR(3)       NOT NULL DEFAULT 'EUR',
            target_currency CHAR(3)       NOT NULL,
            rate            NUMERIC(18,8) NOT NULL,
            source          VARCHAR(20)   NOT NULL DEFAULT 'ECB',
            fetched_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
            PRIMARY KEY (rate_date, target_currency)
        );
        """,
    ),

    # Step 2b: Create new platform.gleif_lei_cache table
    (
        "Create platform.gleif_lei_cache",
        """
        CREATE TABLE IF NOT EXISTS platform.gleif_lei_cache (
            lei                     CHAR(20) PRIMARY KEY,
            legal_name              VARCHAR(500) NOT NULL,
            normalized_name         VARCHAR(500) NOT NULL DEFAULT '',
            entity_status           VARCHAR(20)  NOT NULL,
            country                 CHAR(2)      NOT NULL DEFAULT '',
            registration_authority  VARCHAR(100),
            last_update             DATE,
            fetched_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
            expires_at              TIMESTAMPTZ  NOT NULL
        );
        """,
    ),

    # Step 2c: Create new platform.mic_codes table
    (
        "Create platform.mic_codes",
        """
        CREATE TABLE IF NOT EXISTS platform.mic_codes (
            mic             VARCHAR(10) PRIMARY KEY,
            operating_mic   VARCHAR(10) NOT NULL,
            name            VARCHAR(500) NOT NULL,
            country         CHAR(2)     NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,
    ),

    # Step 2d: Create new platform.nca_registered_entities table (REQ-REF-003)
    (
        "Create platform.nca_registered_entities",
        """
        CREATE TABLE IF NOT EXISTS platform.nca_registered_entities (
            entity_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type     VARCHAR(20) NOT NULL CHECK (entity_type IN ('AIFM', 'AIF', 'UCITS_MC', 'UCITS_FUND')),
            entity_name     VARCHAR(500) NOT NULL,
            lei             CHAR(20),
            national_code   VARCHAR(50),
            nca_code        VARCHAR(10) NOT NULL,
            auth_status     VARCHAR(20) NOT NULL,
            auth_date       DATE,
            source          VARCHAR(20) NOT NULL DEFAULT 'ESMA',
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            register_version VARCHAR(20) NOT NULL
        );
        """,
    ),

    # Step 3: Migrate data from aifmd.* to platform.* (INSERT ... SELECT)
    (
        "Migrate ecb_rates data (aifmd → platform)",
        """
        INSERT INTO platform.ecb_rates (rate_date, base_currency, target_currency, rate, source, fetched_at)
        SELECT rate_date, base_currency, target_currency, rate, source, fetched_at
        FROM aifmd.ecb_rates
        ON CONFLICT (rate_date, target_currency) DO NOTHING;
        """,
    ),
    (
        "Migrate gleif_lei_cache data (aifmd → platform)",
        """
        INSERT INTO platform.gleif_lei_cache (lei, legal_name, normalized_name, entity_status, country, registration_authority, last_update, fetched_at, expires_at)
        SELECT lei, legal_name, COALESCE(normalized_name, ''), entity_status, COALESCE(country, ''), registration_authority, last_update, fetched_at, expires_at
        FROM aifmd.gleif_lei_cache
        ON CONFLICT (lei) DO NOTHING;
        """,
    ),
    (
        "Migrate mic_codes data (aifmd → platform)",
        """
        INSERT INTO platform.mic_codes (mic, operating_mic, name, country, status, fetched_at)
        SELECT mic, operating_mic, name, country, status, fetched_at
        FROM aifmd.mic_codes
        ON CONFLICT (mic) DO NOTHING;
        """,
    ),

    # Step 4: Create indexes on platform tables
    (
        "Create index idx_platform_ecb_rates_currency",
        "CREATE INDEX IF NOT EXISTS idx_platform_ecb_rates_currency ON platform.ecb_rates(target_currency, rate_date);",
    ),
    (
        "Create index idx_platform_gleif_legal_name",
        "CREATE INDEX IF NOT EXISTS idx_platform_gleif_legal_name ON platform.gleif_lei_cache(legal_name);",
    ),
    (
        "Create index idx_platform_gleif_normalized_name",
        "CREATE INDEX IF NOT EXISTS idx_platform_gleif_normalized_name ON platform.gleif_lei_cache(normalized_name);",
    ),
    (
        "Create index idx_platform_mic_country",
        "CREATE INDEX IF NOT EXISTS idx_platform_mic_country ON platform.mic_codes(country);",
    ),
    (
        "Create index idx_platform_nca_entities_nca_code",
        "CREATE INDEX IF NOT EXISTS idx_platform_nca_entities_nca_code ON platform.nca_registered_entities(nca_code);",
    ),
    (
        "Create index idx_platform_nca_entities_lei",
        "CREATE INDEX IF NOT EXISTS idx_platform_nca_entities_lei ON platform.nca_registered_entities(lei) WHERE lei IS NOT NULL;",
    ),
    (
        "Create index idx_platform_nca_entities_type_status",
        "CREATE INDEX IF NOT EXISTS idx_platform_nca_entities_type_status ON platform.nca_registered_entities(entity_type, auth_status);",
    ),

    # Step 5: Drop old aifmd reference tables
    # (Only indexes first, then tables — safe order)
    (
        "Drop old index idx_ecb_rates_currency (aifmd)",
        "DROP INDEX IF EXISTS aifmd.idx_ecb_rates_currency;",
    ),
    (
        "Drop old index idx_gleif_legal_name (aifmd)",
        "DROP INDEX IF EXISTS aifmd.idx_gleif_legal_name;",
    ),
    (
        "Drop old index idx_gleif_normalized_name (aifmd)",
        "DROP INDEX IF EXISTS aifmd.idx_gleif_normalized_name;",
    ),
    (
        "Drop old index idx_mic_country (aifmd)",
        "DROP INDEX IF EXISTS aifmd.idx_mic_country;",
    ),
    (
        "Drop old table aifmd.ecb_rates",
        "DROP TABLE IF EXISTS aifmd.ecb_rates;",
    ),
    (
        "Drop old table aifmd.gleif_lei_cache",
        "DROP TABLE IF EXISTS aifmd.gleif_lei_cache;",
    ),
    (
        "Drop old table aifmd.mic_codes",
        "DROP TABLE IF EXISTS aifmd.mic_codes;",
    ),
]

# Also drop gtm.esma_aifm_register if it exists (superseded by platform.nca_registered_entities)
MIGRATION_STEPS.append((
    "Drop old table gtm.esma_aifm_register (superseded by platform.nca_registered_entities)",
    "DROP TABLE IF EXISTS gtm.esma_aifm_register;",
))


# ── Verification queries ─────────────────────────────────────────────

VERIFY_QUERIES = [
    ("platform.ecb_rates", "SELECT COUNT(*) FROM platform.ecb_rates"),
    ("platform.gleif_lei_cache", "SELECT COUNT(*) FROM platform.gleif_lei_cache"),
    ("platform.mic_codes", "SELECT COUNT(*) FROM platform.mic_codes"),
    ("platform.nca_registered_entities", "SELECT COUNT(*) FROM platform.nca_registered_entities"),
    ("old aifmd.ecb_rates (should not exist)", "SELECT COUNT(*) FROM aifmd.ecb_rates"),
    ("old aifmd.gleif_lei_cache (should not exist)", "SELECT COUNT(*) FROM aifmd.gleif_lei_cache"),
    ("old aifmd.mic_codes (should not exist)", "SELECT COUNT(*) FROM aifmd.mic_codes"),
]


def main():
    import psycopg2

    print("=" * 70)
    print("  Project Eagle — Reference Data Migration: aifmd/gtm → platform")
    print("=" * 70)
    print()
    print("  Rationale: P4 (single source of truth) + P15 (platform-first)")
    print("  Reference data is product-agnostic; it belongs in the platform schema.")
    print()

    # ── Connect ──────────────────────────────────────────────────────
    print(f"[0] Connecting to PostgreSQL ({PG_HOST}:{PG_PORT}/{PG_DBNAME})...")
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
            user=PG_USER, password=PG_PASSWORD,
        )
        conn.autocommit = False  # Run as single transaction for safety
        print("    Connected.\n")
    except Exception as e:
        print(f"    ERROR: {e}")
        sys.exit(1)

    cur = conn.cursor()

    # ── Pre-migration counts ─────────────────────────────────────────
    print("[1] Pre-migration record counts:")
    pre_counts = {}
    for table_name in ["aifmd.ecb_rates", "aifmd.gleif_lei_cache", "aifmd.mic_codes"]:
        cur.execute("SAVEPOINT pre_count")
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            cur.execute("RELEASE SAVEPOINT pre_count")
            pre_counts[table_name] = count
            print(f"    {table_name}: {count:,} records")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT pre_count")
            pre_counts[table_name] = 0
            print(f"    {table_name}: (does not exist yet)")
    print()

    # ── Execute migration steps ──────────────────────────────────────
    print("[2] Executing migration steps:")
    for i, (description, sql) in enumerate(MIGRATION_STEPS, 1):
        try:
            cur.execute(sql)
            print(f"    [{i:2d}/{len(MIGRATION_STEPS)}] OK  — {description}")
        except Exception as e:
            print(f"    [{i:2d}/{len(MIGRATION_STEPS)}] ERR — {description}: {e}")
            conn.rollback()
            print("\n    Migration ABORTED — all changes rolled back.")
            sys.exit(1)
    print()

    # ── Post-migration verification ──────────────────────────────────
    # Use SAVEPOINTs so that a failed query (expected for dropped tables)
    # doesn't roll back the entire migration transaction.
    print("[3] Post-migration verification:")
    all_ok = True
    for description, sql in VERIFY_QUERIES:
        cur.execute("SAVEPOINT verify_check")
        try:
            cur.execute(sql)
            count = cur.fetchone()[0]
            cur.execute("RELEASE SAVEPOINT verify_check")
            if "should not exist" in description:
                # Query succeeded → table still exists (bad)
                print(f"    WARN — {description}: table still exists ({count:,} records)")
                all_ok = False
            else:
                print(f"    OK   — {description}: {count:,} records")
        except Exception:
            # Query failed → roll back only to the savepoint, not the whole tx
            cur.execute("ROLLBACK TO SAVEPOINT verify_check")
            if "should not exist" in description:
                print(f"    OK   — {description}: correctly dropped")
            else:
                print(f"    FAIL — {description}: table missing!")
                all_ok = False
    print()

    # ── Validate counts match ────────────────────────────────────────
    print("[4] Data integrity check (pre vs post counts):")
    for old_table, new_table in [
        ("aifmd.ecb_rates", "platform.ecb_rates"),
        ("aifmd.gleif_lei_cache", "platform.gleif_lei_cache"),
        ("aifmd.mic_codes", "platform.mic_codes"),
    ]:
        cur.execute("SAVEPOINT count_check")
        try:
            cur.execute(f"SELECT COUNT(*) FROM {new_table}")
            new_count = cur.fetchone()[0]
            cur.execute("RELEASE SAVEPOINT count_check")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT count_check")
            new_count = 0
        old_count = pre_counts.get(old_table, 0)
        match = "MATCH" if new_count >= old_count else "MISMATCH"
        print(f"    {old_table} ({old_count:,}) → {new_table} ({new_count:,}): {match}")
        if new_count < old_count:
            all_ok = False
    print()

    # ── Commit or rollback ───────────────────────────────────────────
    if all_ok:
        conn.commit()
        print("[5] Migration COMMITTED successfully.")
    else:
        conn.rollback()
        print("[5] Migration ROLLED BACK due to verification failures.")
        print("    Review the warnings above and re-run.")
        sys.exit(1)

    cur.close()
    conn.close()

    print()
    print("=" * 70)
    print("  Migration complete!")
    print()
    print("  Tables now in platform schema:")
    print("    - platform.ecb_rates          (REQ-REF-001)")
    print("    - platform.gleif_lei_cache    (REQ-REF-002)")
    print("    - platform.mic_codes          (REQ-REF-001)")
    print("    - platform.nca_registered_entities (REQ-REF-003) — new, empty")
    print()
    print("  Removed:")
    print("    - aifmd.ecb_rates")
    print("    - aifmd.gleif_lei_cache")
    print("    - aifmd.mic_codes")
    print("    - gtm.esma_aifm_register")
    print()
    print("  Next steps:")
    print("    - Verify in pgAdmin: Schemas → platform → Tables")
    print("    - Run setup_and_fetch_all.py to confirm fetchers work with new schema")
    print("=" * 70)


if __name__ == "__main__":
    main()
