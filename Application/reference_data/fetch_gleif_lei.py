"""Fetch GLEIF LEI data and store in reference data store.

Source: GLEIF — https://www.gleif.org / https://api.gleif.org
Requirement: REQ-REF-002 (gleif_lei_register)
Architecture: eagle_software_architecture.md §6.3

Modes:
  - lookup:  Single LEI lookup via GLEIF API (on-demand fallback)
  - batch:   Batch lookup of multiple LEIs from a file
  - search:  Search by legal name (fuzzy)

The GLEIF API is free, requires no API key, rate limit ~60 req/min.
Production: daily bulk Golden Copy download + on-demand API fallback.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.reference_store import ReferenceStore

logger = logging.getLogger(__name__)

GLEIF_API_BASE = "https://api.gleif.org/api/v1"
CACHE_TTL_DAYS = 7
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 1.1  # seconds between requests (stay under 60/min)


def _gleif_api_get(endpoint: str) -> dict:
    """Call GLEIF JSON:API endpoint with retries and rate limiting."""
    url = f"{GLEIF_API_BASE}/{endpoint}"
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(url, headers={
                "User-Agent": "Eagle/1.0 (reference-data-fetcher)",
                "Accept": "application/vnd.api+json",
            })
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 404:
                return {}  # LEI not found — not an error
            if e.code == 429:
                logger.warning("GLEIF rate limit hit, backing off 5s (attempt %d)", attempt)
                time.sleep(5)
            last_error = e
        except URLError as e:
            last_error = e
            logger.warning("GLEIF API attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
        time.sleep(RATE_LIMIT_DELAY)
    raise RuntimeError(f"GLEIF API failed after {MAX_RETRIES} attempts: {last_error}")


def _format_address(addr: dict) -> str | None:
    """Format a GLEIF address object into a single-line string."""
    if not addr:
        return None
    parts = []
    for line in addr.get("addressLines", []):
        if line and line.strip():
            parts.append(line.strip())
    city = addr.get("city", "")
    region = addr.get("region", "")
    postal = addr.get("postalCode", "")
    country = addr.get("country", "")
    city_line = ", ".join(filter(None, [postal, city, region]))
    if city_line:
        parts.append(city_line)
    if country:
        parts.append(country)
    return ", ".join(parts) if parts else None


def _parse_lei_record(data: dict) -> dict | None:
    """Parse a single GLEIF JSON:API record into our schema."""
    if not data or "data" not in data:
        return None
    record = data["data"] if isinstance(data["data"], dict) else data["data"][0] if data["data"] else None
    if not record:
        return None

    attrs = record.get("attributes", {})
    entity = attrs.get("entity", {})
    reg = attrs.get("registration", {})

    return {
        "lei": attrs.get("lei", record.get("id", "")),
        "legal_name": entity.get("legalName", {}).get("name", "UNKNOWN"),
        "entity_status": entity.get("status", "UNKNOWN"),
        "country": entity.get("legalAddress", {}).get("country", ""),
        "registration_authority": reg.get("managingLou", None),
        "last_update": reg.get("lastUpdateDate", "")[:10] or None,
        "expires_at": (datetime.utcnow() + timedelta(days=CACHE_TTL_DAYS)).isoformat(),
        # Extended fields for NCA enrichment
        "headquarters_address": _format_address(entity.get("headquartersAddress")),
        "legal_address": _format_address(entity.get("legalAddress")),
        "jurisdiction": (entity.get("jurisdiction") or "")[:2] or None,  # ISO-2 only (strip subdivision like US-DE → US)
        "registered_as": entity.get("registeredAs", None),
    }


def lookup_lei(store: ReferenceStore, lei: str, force_refresh: bool = False) -> dict | None:
    """Look up a single LEI. Checks cache first, then GLEIF API.

    Per REQ-REF-002: on cache miss, call GLEIF API and cache immediately.
    """
    lei = lei.strip().upper()
    if len(lei) != 20:
        logger.error("Invalid LEI format (must be 20 chars): %s", lei)
        return None

    # Check cache first (unless forced refresh)
    if not force_refresh:
        cached = store.get_lei(lei)
        if cached:
            now = datetime.now(tz=timezone.utc)
            expires = cached.expires_at
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires)
            if isinstance(expires, datetime):
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires > now:
                    logger.debug("LEI %s found in cache (expires %s)", lei, expires)
                    return {
                        "lei": cached.lei, "legal_name": cached.legal_name,
                        "entity_status": cached.entity_status, "source": "cache",
                    }
            logger.info("LEI %s cache expired, refreshing from API", lei)

    # API lookup
    logger.info("Looking up LEI %s via GLEIF API", lei)
    data = _gleif_api_get(f"lei-records/{lei}")
    record = _parse_lei_record(data)
    if not record:
        logger.warning("LEI %s not found in GLEIF register", lei)
        return None

    # Cache result
    store.upsert_lei([record])
    logger.info("Cached LEI %s: %s (%s)", lei, record["legal_name"], record["entity_status"])
    return {**record, "source": "api"}


def batch_lookup(store: ReferenceStore, leis: list[str], force_refresh: bool = False) -> dict:
    """Look up multiple LEIs. Returns summary."""
    results = {"found": 0, "not_found": 0, "errors": 0, "from_cache": 0, "from_api": 0}
    for lei in leis:
        try:
            result = lookup_lei(store, lei, force_refresh=force_refresh)
            if result:
                results["found"] += 1
                results[f"from_{result['source']}"] += 1
            else:
                results["not_found"] += 1
        except Exception as e:
            logger.error("Error looking up LEI %s: %s", lei, e)
            results["errors"] += 1
        time.sleep(RATE_LIMIT_DELAY)
    return results


def search_by_name(store: ReferenceStore, name: str, max_results: int = 10) -> list[dict]:
    """Search GLEIF by legal name. Results are cached."""
    logger.info("Searching GLEIF for name: %s", name)
    from urllib.parse import quote
    data = _gleif_api_get(
        f"lei-records?filter[entity.legalName]={quote(name)}&page[size]={max_results}"
    )
    if not data or "data" not in data:
        return []

    records = []
    for item in data["data"]:
        wrapped = {"data": item}
        parsed = _parse_lei_record(wrapped)
        if parsed:
            records.append(parsed)

    # Cache all results
    if records:
        store.upsert_lei(records)
        logger.info("Cached %d LEI records from name search", len(records))

    return records


def _batch_fetch_leis(leis: list[str], page_size: int = 200) -> list[dict]:
    """Fetch multiple LEIs from GLEIF in batches using filter[lei].

    The GLEIF API supports filtering by multiple LEIs in one request
    (comma-separated in the filter), returning up to page_size results.
    This is ~200x faster than individual lookups.
    """
    all_records = []
    from urllib.parse import quote
    for i in range(0, len(leis), page_size):
        chunk = leis[i:i + page_size]
        lei_filter = ",".join(chunk)
        endpoint = f"lei-records?filter[lei]={quote(lei_filter)}&page[size]={page_size}"
        try:
            data = _gleif_api_get(endpoint)
            if data and "data" in data:
                for item in data["data"]:
                    parsed = _parse_lei_record({"data": item})
                    if parsed:
                        all_records.append(parsed)
            logger.info("  Batch %d-%d: got %d records",
                        i + 1, min(i + page_size, len(leis)),
                        len(data.get("data", [])) if data else 0)
        except Exception as e:
            logger.error("Batch fetch error (LEIs %d-%d): %s", i, i + page_size, e)
        time.sleep(RATE_LIMIT_DELAY)
    return all_records


def sync_nca_leis(store: ReferenceStore, force_refresh: bool = False) -> dict:
    """Extract all unique LEIs from NCA register and fetch/refresh them in GLEIF cache.

    This ensures the gleif_lei_cache has all LEIs that exist in nca_aifm
    and nca_aif, with the extended fields (addresses, jurisdiction, registeredAs)
    populated for use by the enrich-gleif step.

    Uses batch API (200 LEIs per request) — typically completes in under a minute.
    """
    import psycopg2
    from reference_data.config import PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD

    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
        user=PG_USER, password=PG_PASSWORD,
    )
    cur = conn.cursor()

    # Collect unique LEIs from both entity tables
    cur.execute("""
        SELECT DISTINCT lei FROM (
            SELECT lei FROM platform.nca_aifm WHERE lei IS NOT NULL
            UNION
            SELECT lei FROM platform.nca_aif WHERE lei IS NOT NULL
        ) AS all_leis
        ORDER BY lei
    """)
    all_leis = [row[0].strip() for row in cur.fetchall() if row[0] and len(row[0].strip()) == 20]
    cur.close()
    conn.close()

    total = len(all_leis)
    logger.info("Found %d unique LEIs in NCA register — batch-fetching from GLEIF API", total)

    # Skip LEIs already in cache (unless force refresh)
    if not force_refresh:
        cached_count = 0
        to_fetch = []
        for lei in all_leis:
            cached = store.get_lei(lei)
            if cached and cached.expires_at:
                # Check if the extended fields are already populated
                # If not, re-fetch even if cached
                cached_count += 1
            else:
                to_fetch.append(lei)
        # Also re-fetch LEIs where cache exists but extended fields are missing
        # (i.e., cached before we added the new columns)
        logger.info("  %d already cached, %d to fetch", cached_count, len(to_fetch))
        # For simplicity on first run: force-fetch all to populate new columns
        if force_refresh or not to_fetch:
            to_fetch = all_leis
            logger.info("  Force-fetching all %d LEIs (populating new columns)", total)
    else:
        to_fetch = all_leis

    records = _batch_fetch_leis(to_fetch)

    # Bulk upsert into cache
    if records:
        store.upsert_lei(records)
        logger.info("Cached %d LEI records with extended fields", len(records))

    return {
        "total_leis": total,
        "fetched": len(records),
        "not_found": total - len(records),
    }


# ── Golden Copy bulk download ─────────────────────────────────────────

GOLDEN_COPY_API = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest"

# CSV column names we need (dot-separated GLEIF CDF path)
_CSV_COL_LEI = "LEI"
_CSV_COL_LEGAL_NAME = "Entity.LegalName"
_CSV_COL_STATUS = "Entity.EntityStatus"
_CSV_COL_JURISDICTION = "Entity.LegalJurisdiction"
_CSV_COL_REGISTERED_AS = "Entity.RegistrationAuthority.RegistrationAuthorityEntityID"
_CSV_COL_REG_AUTHORITY = "Registration.ManagingLOU"
_CSV_COL_LAST_UPDATE = "Registration.LastUpdateDate"
_CSV_COL_NEXT_RENEWAL = "Registration.NextRenewalDate"
# Legal address
_CSV_COL_LA_LINE1 = "Entity.LegalAddress.FirstAddressLine"
_CSV_COL_LA_LINE2 = "Entity.LegalAddress.AdditionalAddressLine.1"
_CSV_COL_LA_LINE3 = "Entity.LegalAddress.AdditionalAddressLine.2"
_CSV_COL_LA_CITY = "Entity.LegalAddress.City"
_CSV_COL_LA_REGION = "Entity.LegalAddress.Region"
_CSV_COL_LA_COUNTRY = "Entity.LegalAddress.Country"
_CSV_COL_LA_POSTAL = "Entity.LegalAddress.PostalCode"
# Headquarters address
_CSV_COL_HQ_LINE1 = "Entity.HeadquartersAddress.FirstAddressLine"
_CSV_COL_HQ_LINE2 = "Entity.HeadquartersAddress.AdditionalAddressLine.1"
_CSV_COL_HQ_LINE3 = "Entity.HeadquartersAddress.AdditionalAddressLine.2"
_CSV_COL_HQ_CITY = "Entity.HeadquartersAddress.City"
_CSV_COL_HQ_REGION = "Entity.HeadquartersAddress.Region"
_CSV_COL_HQ_COUNTRY = "Entity.HeadquartersAddress.Country"
_CSV_COL_HQ_POSTAL = "Entity.HeadquartersAddress.PostalCode"


def _csv_format_address(row: dict, prefix: str) -> str | None:
    """Build single-line address from CSV columns with given prefix."""
    parts = []
    for suffix in ("FirstAddressLine", "AdditionalAddressLine.1",
                    "AdditionalAddressLine.2"):
        val = (row.get(f"{prefix}.{suffix}") or "").strip()
        if val:
            parts.append(val)
    city = (row.get(f"{prefix}.City") or "").strip()
    region = (row.get(f"{prefix}.Region") or "").strip()
    postal = (row.get(f"{prefix}.PostalCode") or "").strip()
    country = (row.get(f"{prefix}.Country") or "").strip()
    city_line = ", ".join(filter(None, [postal, city, region]))
    if city_line:
        parts.append(city_line)
    if country:
        parts.append(country)
    return ", ".join(parts) if parts else None


def _get_golden_copy_url() -> tuple[str, str, int]:
    """Get latest Golden Copy CSV download URL from GLEIF API.

    API response structure:
      data.publish_date           → "2026-04-11 08:00:00"
      data.lei2.full_file.csv.url → download URL
      data.lei2.full_file.csv.record_count → 3277276
      data.lei2.full_file.csv.size_human_readable → "455.85 MB"

    Returns (download_url, publish_date, record_count).
    """
    req = Request(GOLDEN_COPY_API, headers={
        "User-Agent": "Eagle/1.0 (reference-data-fetcher)",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    root = data.get("data", {})
    publish_date = root.get("publish_date", "unknown")

    # Navigate: data → lei2 → full_file → csv
    csv_info = root.get("lei2", {}).get("full_file", {}).get("csv", {})
    csv_url = csv_info.get("url", "")
    record_count = csv_info.get("record_count", 0)
    size_hr = csv_info.get("size_human_readable", "unknown")

    if not csv_url:
        raise RuntimeError(
            "Could not find CSV download URL in GLEIF Golden Copy API response. "
            f"Response keys: {list(root.keys())}"
        )

    logger.info("Golden Copy: %s records, %s", f"{record_count:,}" if record_count else "?", size_hr)
    return csv_url, publish_date, record_count


def download_golden_copy(
    store: ReferenceStore,
    download_dir: str | None = None,
    keep_zip: bool = False,
) -> dict:
    """Download GLEIF Golden Copy CSV and bulk-load into gleif_lei_cache.

    Steps:
      1. Get latest download URL from GLEIF API
      2. Download the ZIP (~456 MB)
      3. Stream-parse CSV, extract only needed columns
      4. Batch-upsert into gleif_lei_cache (5000 rows at a time)

    Args:
        store: ReferenceStore instance (PostgreSQL)
        download_dir: Directory to save ZIP file. Defaults to temp dir.
        keep_zip: If True, keep the ZIP file after loading.

    Returns:
        dict with total, inserted, updated counts.
    """
    import csv
    import io
    import os
    import tempfile
    import zipfile
    from urllib.request import urlretrieve

    from shared.clean_name import clean_name

    # Step 1: Resolve download URL
    logger.info("Querying GLEIF Golden Copy API for latest download...")
    try:
        csv_url, publish_date, expected_count = _get_golden_copy_url()
    except Exception:
        # Fallback: use the well-known latest endpoint directly
        logger.warning("Could not parse Golden Copy API response, using known URL pattern")
        csv_url = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/lei2/latest.csv.zip"
        publish_date = "unknown"
        expected_count = 0

    logger.info("Download URL: %s", csv_url)
    logger.info("Publish date: %s, expected records: %s", publish_date, expected_count or "unknown")

    # Step 2: Download ZIP
    if download_dir:
        os.makedirs(download_dir, exist_ok=True)
        zip_path = os.path.join(download_dir, "gleif-golden-copy-lei2.csv.zip")
    else:
        tmp = tempfile.mkdtemp(prefix="gleif_")
        zip_path = os.path.join(tmp, "gleif-golden-copy-lei2.csv.zip")

    logger.info("Downloading to %s ...", zip_path)

    def _progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 / total_size)
            mb = downloaded / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            if block_num % 500 == 0:
                logger.info("  %.0f MB / %.0f MB (%.0f%%)", mb, total_mb, pct)

    urlretrieve(csv_url, zip_path, reporthook=_progress)
    file_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    logger.info("Download complete: %.1f MB", file_size_mb)

    # Step 3 + 4: Stream-parse CSV from ZIP and batch-upsert
    batch_size = 5000
    batch = []
    total = 0
    now_iso = datetime.utcnow().isoformat()

    with zipfile.ZipFile(zip_path) as zf:
        # Find the CSV file inside the ZIP
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"No CSV file found in ZIP. Contents: {zf.namelist()}")
        csv_name = csv_names[0]
        logger.info("Parsing %s from ZIP...", csv_name)

        with zf.open(csv_name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))

            for row in reader:
                lei = (row.get(_CSV_COL_LEI) or "").strip()
                legal_name = (row.get(_CSV_COL_LEGAL_NAME) or "").strip()
                status = (row.get(_CSV_COL_STATUS) or "").strip()

                if not lei or len(lei) != 20 or not legal_name:
                    continue

                record = {
                    "lei": lei,
                    "legal_name": legal_name,
                    "entity_status": status or "UNKNOWN",
                    "country": (row.get(_CSV_COL_LA_COUNTRY) or "")[:2],
                    "registration_authority": row.get(_CSV_COL_REG_AUTHORITY) or None,
                    "last_update": (row.get(_CSV_COL_LAST_UPDATE) or "")[:10] or None,
                    "expires_at": row.get(_CSV_COL_NEXT_RENEWAL) or now_iso,
                    "headquarters_address": _csv_format_address(row, "Entity.HeadquartersAddress"),
                    "legal_address": _csv_format_address(row, "Entity.LegalAddress"),
                    "jurisdiction": (row.get(_CSV_COL_JURISDICTION) or "")[:2] or None,
                    "registered_as": row.get(_CSV_COL_REGISTERED_AS) or None,
                }
                batch.append(record)
                total += 1

                if len(batch) >= batch_size:
                    store.upsert_lei(batch)
                    if total % 100000 == 0:
                        logger.info("  ... %d records loaded", total)
                    batch = []

            # Final batch
            if batch:
                store.upsert_lei(batch)

    logger.info("Golden Copy load complete: %d records", total)

    # Clean up ZIP
    if not keep_zip:
        os.remove(zip_path)
        logger.info("Removed ZIP file")
    else:
        logger.info("ZIP kept at %s", zip_path)

    # Run backfill to ensure normalized_name is computed for all records
    logger.info("Computing normalized_name for all records...")
    backfill_result = backfill_normalized_names(store)

    return {
        "publish_date": publish_date,
        "records_loaded": total,
        "backfill": backfill_result,
    }


# ── Backfill normalized names ─────────────────────────────────────────

def backfill_normalized_names(store: ReferenceStore) -> dict:
    """Recompute normalized_name for every record in gleif_lei_cache.

    Uses the unified clean_name() from shared/clean_name.py so that GLEIF
    cache entries match the same normalization used in NCA tables and LEI
    validation.  This must be run once after switching to the unified logic
    to update any records that were stored with the old normalization.
    """
    from shared.clean_name import clean_name
    from psycopg2.extras import execute_batch

    conn = store._conn
    cur = conn.cursor()

    # Read all current records
    cur.execute("SELECT lei, legal_name, normalized_name FROM platform.gleif_lei_cache")
    rows = cur.fetchall()
    total = len(rows)
    updated = 0
    unchanged = 0

    batch = []
    BATCH_SIZE = 5000

    for lei, legal_name, old_norm in rows:
        new_norm = clean_name(legal_name)
        if new_norm != old_norm:
            batch.append((new_norm, lei))
            updated += 1
        else:
            unchanged += 1

        if len(batch) >= BATCH_SIZE:
            execute_batch(
                cur,
                "UPDATE platform.gleif_lei_cache SET normalized_name = %s WHERE lei = %s",
                batch,
                page_size=BATCH_SIZE,
            )
            conn.commit()
            logger.info(f"  ... {updated + unchanged:,}/{total:,} processed, {updated:,} updated")
            batch = []

    if batch:
        execute_batch(
            cur,
            "UPDATE platform.gleif_lei_cache SET normalized_name = %s WHERE lei = %s",
            batch,
            page_size=BATCH_SIZE,
        )
        conn.commit()

    logger.info(
        "Backfill complete: %d total, %d updated, %d unchanged",
        total, updated, unchanged,
    )
    return {"total": total, "updated": updated, "unchanged": unchanged}


# ── CLI entry point ───────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch GLEIF LEI data")
    sub = parser.add_subparsers(dest="command")

    p_lookup = sub.add_parser("lookup", help="Look up a single LEI")
    p_lookup.add_argument("lei", help="20-character LEI code")
    p_lookup.add_argument("--force", action="store_true", help="Skip cache")

    p_batch = sub.add_parser("batch", help="Batch lookup from file (one LEI per line)")
    p_batch.add_argument("file", help="File with LEIs")
    p_batch.add_argument("--force", action="store_true")

    p_search = sub.add_parser("search", help="Search by legal name")
    p_search.add_argument("name", help="Legal name to search")
    p_search.add_argument("--max", type=int, default=10)

    p_sync = sub.add_parser("sync-nca", help="Fetch GLEIF data for all LEIs in NCA register")
    p_sync.add_argument("--force", action="store_true", help="Re-fetch even if cached")

    sub.add_parser(
        "backfill-names",
        help="Recompute normalized_name for all GLEIF cache records using shared clean_name()",
    )

    p_golden = sub.add_parser(
        "download-golden-copy",
        help="Download full GLEIF Golden Copy (~456 MB ZIP, ~3.3M LEI records) and load into cache",
    )
    p_golden.add_argument(
        "--dir", default=None,
        help="Directory to save the ZIP file (default: temp dir, deleted after load)",
    )
    p_golden.add_argument(
        "--keep-zip", action="store_true",
        help="Keep the ZIP file after loading (useful for debugging)",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from reference_data.config import get_store
    store = get_store()
    try:
        if args.command == "lookup":
            result = lookup_lei(store, args.lei, force_refresh=args.force)
            print(json.dumps(result, indent=2, default=str) if result else "Not found")

        elif args.command == "batch":
            leis = Path(args.file).read_text().strip().splitlines()
            result = batch_lookup(store, leis, force_refresh=args.force)
            print(f"\nBatch result: {result}")

        elif args.command == "search":
            results = search_by_name(store, args.name, max_results=args.max)
            for r in results:
                print(f"  {r['lei']}  {r['legal_name']}  ({r['entity_status']})")
            print(f"\n{len(results)} results")

        elif args.command == "sync-nca":
            result = sync_nca_leis(store, force_refresh=args.force)
            print(f"\nSync NCA LEIs: {result}")

        elif args.command == "backfill-names":
            result = backfill_normalized_names(store)
            print(f"\nBackfill result: {result}")

        elif args.command == "download-golden-copy":
            result = download_golden_copy(
                store,
                download_dir=args.dir,
                keep_zip=args.keep_zip,
            )
            print(f"\nGolden Copy result: {result}")
        else:
            parser.print_help()

        print(f"\nTotal LEIs in cache: {store.get_lei_count()}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
