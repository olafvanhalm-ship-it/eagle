"""Create NCA register tables in the platform schema (clean install).

Creates three tables:
  - platform.nca_aifm            — AIFM entities with manager-specific fields
  - platform.nca_aif             — AIF and SUB_AIF entities with fund-specific fields
  - platform.nca_registrations   — NCA registration details for both AIFMs and AIFs

Also updates:
  - platform.gleif_lei_cache     — adds address/jurisdiction/registeredAs columns (if missing)

Idempotent: drops existing tables and recreates from scratch.
Run once before the first fetch_nca_registers.py fetch-all.

Schema design:
  - Single home_country column (merged from country_code / home_country / jurisdiction)
  - Single address + address_source column (priority: KVK > Manual > AIFM inherit > ESMA > GLEIF)
  - lineage is always the last column
  - deleted_at for logical deletes (replaces disappeared_at)

Architecture reference: eagle_software_architecture.md §6.3

Usage:
    python Application/reference_data/setup_nca_tables.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reference_data.config import PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD


SETUP_STEPS = [
    # ── Drop existing tables (order matters: registrations first, then aif, then aifm) ──
    ("Drop platform.nca_registrations (if exists)",
     "DROP TABLE IF EXISTS platform.nca_registrations CASCADE;"),
    ("Drop platform.nca_aif (if exists)",
     "DROP TABLE IF EXISTS platform.nca_aif CASCADE;"),
    ("Drop platform.nca_aifm (if exists)",
     "DROP TABLE IF EXISTS platform.nca_aifm CASCADE;"),
    # Also clean up legacy table names from earlier designs
    ("Drop legacy platform.nca_funds (if exists)",
     "DROP TABLE IF EXISTS platform.nca_funds CASCADE;"),
    ("Drop legacy platform.nca_managers (if exists)",
     "DROP TABLE IF EXISTS platform.nca_managers CASCADE;"),
    ("Drop legacy platform.nca_entity_registrations (if exists)",
     "DROP TABLE IF EXISTS platform.nca_entity_registrations CASCADE;"),
    ("Drop legacy platform.nca_entities (if exists)",
     "DROP TABLE IF EXISTS platform.nca_entities CASCADE;"),
    ("Drop legacy platform.nca_registered_entities (if exists)",
     "DROP TABLE IF EXISTS platform.nca_registered_entities CASCADE;"),

    # ── Create tables ────────────────────────────────────────────────

    # AIFM: one row per Alternative Investment Fund Manager
    # - home_country: single ISO-2 country (merged from NCA, ESMA, GLEIF)
    # - address: single text field with best available address
    # - address_source: tracks which source the address came from (KVK, MANUAL, NCA, ESMA, GLEIF)
    # - registered_as: GLEIF registration identifier
    ("Create platform.nca_aifm", """
        CREATE TABLE platform.nca_aifm (
            aifm_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            aifm_name           VARCHAR(500) NOT NULL,
            aifm_clean_name     VARCHAR(500) NOT NULL,
            lei                 CHAR(20),
            home_country        CHAR(2),
            address             TEXT,
            address_source      VARCHAR(20),
            registered_as       VARCHAR(100),
            first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_updated        TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at          TIMESTAMPTZ,
            terminated_at       TIMESTAMPTZ,
            lineage             TEXT
        );
    """),

    # AIF: one row per AIF or SUB_AIF
    # - managing_aifm_id: FK to nca_aifm (technical key, not name)
    # - parent_aif_id: FK to nca_aif (for SUB_AIF → AIF link)
    # - fund_strategy: replaces fund_category (left empty for now)
    # - address: inherits from AIFM if no direct address (priority: KVK > Manual > AIFM > GLEIF)
    # - Removed: marketing_status, registered_as, management_structure, domicile_country
    ("Create platform.nca_aif", """
        CREATE TABLE platform.nca_aif (
            aif_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            aif_type            VARCHAR(10) NOT NULL CHECK (aif_type IN ('AIF', 'SUB_AIF')),
            managing_aifm_id    UUID REFERENCES platform.nca_aifm(aifm_id),
            parent_aif_id       UUID REFERENCES platform.nca_aif(aif_id),
            aif_name            VARCHAR(500) NOT NULL,
            aif_clean_name      VARCHAR(500) NOT NULL,
            lei                 CHAR(20),
            isin                VARCHAR(12),
            home_country        CHAR(2),
            custodian           VARCHAR(500),
            fund_strategy       VARCHAR(50),
            address             TEXT,
            address_source      VARCHAR(20),
            first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_updated        TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at          TIMESTAMPTZ,
            terminated_at       TIMESTAMPTZ,
            lineage             TEXT
        );
    """),

    # Registrations: one row per (entity + NCA + entity_code) combo
    # - auth_status: merged license_type + auth_status → single value
    # - auth_date: merged auth_date + registration_date → single date
    # - lineage: tracks source provenance
    # - deleted_at: logical delete
    ("Create platform.nca_registrations", """
        CREATE TABLE platform.nca_registrations (
            registration_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type         VARCHAR(10) NOT NULL CHECK (entity_type IN ('AIFM', 'AIF', 'SUB_AIF')),
            entity_id           UUID NOT NULL,
            nca_code            VARCHAR(10) NOT NULL,
            nca_entity_code     VARCHAR(50),
            auth_status         VARCHAR(20)
                                CHECK (auth_status IS NULL OR auth_status IN ('AUTHORISED','REGISTERED','NPPR','INACTIVE','WITHDRAWN')),
            auth_date           DATE,
            withdrawal_date     DATE,
            source              VARCHAR(20) NOT NULL,
            source_entity_id    VARCHAR(50),
            fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at          TIMESTAMPTZ,
            lineage             TEXT,
            UNIQUE (entity_type, entity_id, nca_code, nca_entity_code)
        );
    """),

    # ── Indexes ──────────────────────────────────────────────────────
    ("Index: nca_aifm aifm_clean_name",
     "CREATE INDEX idx_aifm_clean_name ON platform.nca_aifm(aifm_clean_name);"),
    ("Index: nca_aifm lei",
     "CREATE INDEX idx_aifm_lei ON platform.nca_aifm(lei) WHERE lei IS NOT NULL;"),
    ("Index: nca_aifm home_country",
     "CREATE INDEX idx_aifm_country ON platform.nca_aifm(home_country) WHERE home_country IS NOT NULL;"),

    ("Index: nca_aif aif_clean_name",
     "CREATE INDEX idx_aif_clean_name ON platform.nca_aif(aif_clean_name);"),
    ("Index: nca_aif lei",
     "CREATE INDEX idx_aif_lei ON platform.nca_aif(lei) WHERE lei IS NOT NULL;"),
    ("Index: nca_aif managing_aifm_id",
     "CREATE INDEX idx_aif_aifm ON platform.nca_aif(managing_aifm_id) WHERE managing_aifm_id IS NOT NULL;"),
    ("Index: nca_aif parent_aif_id",
     "CREATE INDEX idx_aif_parent ON platform.nca_aif(parent_aif_id) WHERE parent_aif_id IS NOT NULL;"),
    ("Index: nca_aif aif_type",
     "CREATE INDEX idx_aif_type ON platform.nca_aif(aif_type);"),
    ("Index: nca_aif home_country",
     "CREATE INDEX idx_aif_country ON platform.nca_aif(home_country) WHERE home_country IS NOT NULL;"),

    ("Index: nca_registrations entity lookup",
     "CREATE INDEX idx_reg_entity ON platform.nca_registrations(entity_type, entity_id);"),
    ("Index: nca_registrations nca_code",
     "CREATE INDEX idx_reg_nca_code ON platform.nca_registrations(nca_code);"),
    ("Index: nca_registrations nca_entity_code",
     "CREATE INDEX idx_reg_entity_code ON platform.nca_registrations(nca_entity_code) WHERE nca_entity_code IS NOT NULL;"),
    ("Index: nca_registrations source",
     "CREATE INDEX idx_reg_source ON platform.nca_registrations(source);"),
    ("Index: nca_registrations source + source_entity_id",
     "CREATE INDEX idx_reg_source_entity ON platform.nca_registrations(source, source_entity_id) WHERE source_entity_id IS NOT NULL;"),

    # ── Add terminated_at to nca_aifm and nca_aif (non-destructive) ──
    # terminated_at: date entity was terminated/withdrawn/deregistered.
    # - CSSF: populated from withdrawal_date (end_mgmt for funds, closing_date for sub-funds)
    # - Others: set when last_seen_at > 30 days in the past (entity disappeared from register)
    # - Separate from deleted_at which is for GUI logical deletes.
    ("Add nca_aifm terminated_at",
     "ALTER TABLE platform.nca_aifm ADD COLUMN IF NOT EXISTS terminated_at TIMESTAMPTZ;"),
    ("Add nca_aif terminated_at",
     "ALTER TABLE platform.nca_aif ADD COLUMN IF NOT EXISTS terminated_at TIMESTAMPTZ;"),

    # ── Expand gleif_lei_cache with address/jurisdiction fields (non-destructive) ──
    ("Expand gleif_lei_cache: headquarters_address",
     "ALTER TABLE platform.gleif_lei_cache ADD COLUMN IF NOT EXISTS headquarters_address TEXT;"),
    ("Expand gleif_lei_cache: legal_address",
     "ALTER TABLE platform.gleif_lei_cache ADD COLUMN IF NOT EXISTS legal_address TEXT;"),
    ("Expand gleif_lei_cache: jurisdiction",
     "ALTER TABLE platform.gleif_lei_cache ADD COLUMN IF NOT EXISTS jurisdiction CHAR(2);"),
    ("Fix gleif_lei_cache: ensure jurisdiction is CHAR(2)",
     "ALTER TABLE platform.gleif_lei_cache ALTER COLUMN jurisdiction TYPE CHAR(2);"),
    ("Expand gleif_lei_cache: registered_as",
     "ALTER TABLE platform.gleif_lei_cache ADD COLUMN IF NOT EXISTS registered_as TEXT;"),
    ("Widen gleif_lei_cache: registered_as to TEXT",
     "ALTER TABLE platform.gleif_lei_cache ALTER COLUMN registered_as TYPE TEXT;"),
]


def main():
    import psycopg2

    print("=" * 70)
    print("  Project Eagle — NCA Register Tables Setup")
    print("=" * 70)
    print()

    print(f"[0] Connecting to PostgreSQL ({PG_HOST}:{PG_PORT}/{PG_DBNAME})...")
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
            user=PG_USER, password=PG_PASSWORD,
        )
        conn.autocommit = False
        print("    Connected.\n")
    except Exception as e:
        print(f"    ERROR: {e}")
        sys.exit(1)

    cur = conn.cursor()

    print(f"[1] Executing {len(SETUP_STEPS)} steps:")
    for i, (description, sql) in enumerate(SETUP_STEPS, 1):
        try:
            cur.execute(sql)
            print(f"    [{i:2d}/{len(SETUP_STEPS)}] OK  — {description}")
        except Exception as e:
            print(f"    [{i:2d}/{len(SETUP_STEPS)}] ERR — {description}: {e}")
            conn.rollback()
            print("\n    Setup ABORTED — all changes rolled back.")
            sys.exit(1)
    print()

    # Verify
    print("[2] Verification:")
    for table in ["platform.nca_aifm", "platform.nca_aif", "platform.nca_registrations"]:
        cur.execute("SAVEPOINT verify")
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            cur.execute("RELEASE SAVEPOINT verify")
            print(f"    OK — {table} exists")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT verify")
            print(f"    FAIL — {table} does not exist!")
            conn.rollback()
            sys.exit(1)
    print()

    conn.commit()
    print("[3] Setup COMMITTED successfully.")
    print()
    print("  Tables created:")
    print("    - platform.nca_aifm           (AIFMs)")
    print("    - platform.nca_aif            (AIFs + SUB_AIFs)")
    print("    - platform.nca_registrations  (NCA registration details)")
    print()
    print("  Next: python fetch_nca_registers.py fetch-all")
    print("=" * 70)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
