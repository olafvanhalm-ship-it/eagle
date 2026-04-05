# Migration: Add normalized_name and country columns to gleif_lei_cache
# and backfill existing records.
#
# Required because the original schema did not include these columns,
# but LEI validation Path 2 needs normalized_name for name-based lookups
# and country for disambiguation.
#
# Run once:  python Application\reference_data\migrate_add_normalized_name.py

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _fetch_country_from_gleif(lei: str) -> str:
    """Fetch country code for a single LEI from GLEIF API."""
    try:
        req = Request(
            f"https://api.gleif.org/api/v1/lei-records/{lei}",
            headers={"Accept": "application/vnd.api+json", "User-Agent": "Eagle/1.0"},
        )
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        entity = data.get("data", {}).get("attributes", {}).get("entity", {})
        return entity.get("legalAddress", {}).get("country", "")
    except Exception as e:
        logger.warning("  Could not fetch country for %s: %s", lei, e)
        return ""


def main():
    from reference_data.config import get_store
    from shared.lei_validator import normalize_entity_name

    store = get_store()
    cur = store._conn.cursor()
    param = "?" if store._backend == "sqlite" else "%s"
    table = store._t("gleif_lei_cache")

    # Step 1: Add normalized_name column
    logger.info("Step 1: Adding normalized_name column (if not present)...")
    try:
        if store._backend == "postgresql":
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(500) NOT NULL DEFAULT ''")
        else:
            cur.execute("PRAGMA table_info(gleif_lei_cache)")
            cols = [row[1] for row in cur.fetchall()]
            if "normalized_name" not in cols:
                cur.execute("ALTER TABLE gleif_lei_cache ADD COLUMN normalized_name TEXT NOT NULL DEFAULT ''")
        logger.info("  Done.")
    except Exception as e:
        logger.info("  Already exists or error: %s", e)

    # Step 2: Add country column
    logger.info("Step 2: Adding country column (if not present)...")
    try:
        if store._backend == "postgresql":
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS country CHAR(2) NOT NULL DEFAULT ''")
        else:
            cur.execute("PRAGMA table_info(gleif_lei_cache)")
            cols = [row[1] for row in cur.fetchall()]
            if "country" not in cols:
                cur.execute("ALTER TABLE gleif_lei_cache ADD COLUMN country TEXT NOT NULL DEFAULT ''")
        logger.info("  Done.")
    except Exception as e:
        logger.info("  Already exists or error: %s", e)

    # Step 3: Create indexes
    logger.info("Step 3: Creating indexes...")
    try:
        if store._backend == "postgresql":
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_gleif_normalized_name ON {table}(normalized_name)")
        else:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_gleif_normalized_name ON gleif_lei_cache(normalized_name)")
        logger.info("  Index on normalized_name created.")
    except Exception as e:
        logger.info("  Index issue: %s", e)

    # Step 4: Backfill normalized_name
    logger.info("Step 4: Backfilling normalized_name for existing records...")
    cur.execute(f"SELECT lei, legal_name FROM {table} WHERE normalized_name = '' OR normalized_name IS NULL")
    rows = cur.fetchall()
    if not rows:
        logger.info("  All records already have normalized_name.")
    else:
        for lei, legal_name in rows:
            normalized = normalize_entity_name(legal_name)
            cur.execute(f"UPDATE {table} SET normalized_name = {param} WHERE lei = {param}", (normalized, lei.strip()))
            logger.info("  %s → '%s' → normalized: '%s'", lei.strip(), legal_name, normalized)
        if store._backend == "sqlite":
            store._conn.commit()
        logger.info("  Backfilled %d records.", len(rows))

    # Step 5: Backfill country from GLEIF API
    logger.info("Step 5: Backfilling country from GLEIF API for existing records...")
    cur.execute(f"SELECT lei FROM {table} WHERE country = '' OR country IS NULL")
    rows = cur.fetchall()
    if not rows:
        logger.info("  All records already have country.")
    else:
        for (lei,) in rows:
            lei = lei.strip()
            country = _fetch_country_from_gleif(lei)
            if country:
                cur.execute(f"UPDATE {table} SET country = {param} WHERE lei = {param}", (country, lei))
                logger.info("  %s → country: %s", lei, country)
            else:
                logger.warning("  %s → country: UNKNOWN (API failed or empty)", lei)
            time.sleep(1.1)  # GLEIF rate limit
        if store._backend == "sqlite":
            store._conn.commit()
        logger.info("  Processed %d records.", len(rows))

    # Step 6: Verify
    logger.info("Step 6: Verification...")
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    total = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE normalized_name != '' AND normalized_name IS NOT NULL")
    norm_filled = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE country != '' AND country IS NOT NULL")
    country_filled = cur.fetchone()[0]

    logger.info("  Total: %d, with normalized_name: %d, with country: %d", total, norm_filled, country_filled)

    cur.execute(f"SELECT lei, legal_name, normalized_name, country FROM {table} LIMIT 10")
    logger.info("  Sample records:")
    for row in cur.fetchall():
        logger.info("    LEI=%s  name='%s'  normalized='%s'  country='%s'",
                     row[0].strip(), row[1], row[2], row[3])

    cur.close()
    store.close()
    logger.info("Migration complete.")


if __name__ == "__main__":
    main()
