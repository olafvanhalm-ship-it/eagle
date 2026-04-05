"""Fetch ECB euro reference exchange rates and store in reference data store.

Source: European Central Bank — https://www.ecb.europa.eu
Requirement: REQ-REF-001 (ecb_fx_rates)
Architecture: eagle_software_architecture.md §6.3, §5.4

Modes:
  - daily:    Fetches today's rates from eurofxref-daily.xml
  - backfill: Fetches full history (1999–present) from eurofxref-hist.xml
  - recent:   Fetches last 90 days from eurofxref-hist-90d.xml

Production schedule: EventBridge cron daily Mon–Fri at 16:30 CET.
"""

from __future__ import annotations

import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# Allow running as standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.reference_store import ReferenceStore

logger = logging.getLogger(__name__)

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
ECB_90D_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"

ECB_NS = {"gesmes": "http://www.gesmes.org/xml/2002-08-01",
           "ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}

MAX_RETRIES = 3


def _fetch_xml(url: str) -> ET.Element:
    """Download and parse ECB XML feed with retries."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(url, headers={"User-Agent": "Eagle/1.0 (reference-data-fetcher)"})
            with urlopen(req, timeout=60) as resp:
                return ET.parse(resp).getroot()
        except (URLError, ET.ParseError) as e:
            last_error = e
            logger.warning("ECB fetch attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
    raise RuntimeError(f"ECB fetch failed after {MAX_RETRIES} attempts: {last_error}")


def _parse_rates(root: ET.Element) -> list[dict]:
    """Parse ECB XML into list of {rate_date, target_currency, rate}."""
    rates = []
    for cube_time in root.findall(".//ecb:Cube/ecb:Cube[@time]", ECB_NS):
        rate_date = cube_time.attrib["time"]
        for cube_rate in cube_time.findall("ecb:Cube[@currency]", ECB_NS):
            rates.append({
                "rate_date": rate_date,
                "target_currency": cube_rate.attrib["currency"],
                "rate": float(cube_rate.attrib["rate"]),
            })
    return rates


def fetch_daily(store: ReferenceStore) -> dict:
    """Fetch today's ECB rates. Returns summary stats."""
    logger.info("Fetching ECB daily rates from %s", ECB_DAILY_URL)
    root = _fetch_xml(ECB_DAILY_URL)
    rates = _parse_rates(root)
    store.upsert_ecb_rates(rates)
    dates = sorted(set(r["rate_date"] for r in rates))
    logger.info("Stored %d rates for %d date(s): %s", len(rates), len(dates), dates)
    return {"mode": "daily", "rates_stored": len(rates), "dates": dates}


def fetch_recent(store: ReferenceStore) -> dict:
    """Fetch last 90 days of ECB rates."""
    logger.info("Fetching ECB 90-day history from %s", ECB_90D_URL)
    root = _fetch_xml(ECB_90D_URL)
    rates = _parse_rates(root)
    store.upsert_ecb_rates(rates)
    dates = sorted(set(r["rate_date"] for r in rates))
    logger.info("Stored %d rates across %d dates", len(rates), len(dates))
    return {"mode": "recent", "rates_stored": len(rates), "date_count": len(dates)}


def fetch_backfill(store: ReferenceStore) -> dict:
    """Fetch full ECB history (1999–present). ~200KB XML, ~170K rows."""
    logger.info("Fetching ECB full history from %s (this may take a moment)", ECB_HIST_URL)
    root = _fetch_xml(ECB_HIST_URL)
    rates = _parse_rates(root)
    # Batch upsert in chunks of 5000 for memory efficiency
    chunk_size = 5000
    for i in range(0, len(rates), chunk_size):
        store.upsert_ecb_rates(rates[i:i + chunk_size])
    dates = sorted(set(r["rate_date"] for r in rates))
    logger.info("Backfill complete: %d rates across %d dates (%s to %s)",
                len(rates), len(dates), dates[0], dates[-1])
    return {
        "mode": "backfill",
        "rates_stored": len(rates),
        "date_count": len(dates),
        "date_range": (dates[0], dates[-1]),
    }


# ── CLI entry point ───────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch ECB exchange rates")
    parser.add_argument("mode", choices=["daily", "recent", "backfill"],
                        help="daily=today, recent=90d, backfill=full history")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from reference_data.config import get_store
    store = get_store()
    try:
        result = {"daily": fetch_daily, "recent": fetch_recent, "backfill": fetch_backfill}[args.mode](store)
        print(f"\nResult: {result}")
        print(f"Total ECB rates in store: {store.get_ecb_rate_count()}")
        date_range = store.get_ecb_date_range()
        print(f"Date range: {date_range[0]} to {date_range[1]}")
        print(f"Currencies: {', '.join(store.get_ecb_currencies())}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
