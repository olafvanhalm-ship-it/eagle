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
        else:
            parser.print_help()

        print(f"\nTotal LEIs in cache: {store.get_lei_count()}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
