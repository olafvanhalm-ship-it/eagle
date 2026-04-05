"""Fetch ISO 10383 MIC codes and store in reference data store.

Source: ISO 20022 — https://www.iso20022.org/market-identifier-codes
Requirement: REQ-REF-001 (mic_codes)
Architecture: eagle_software_architecture.md §6.3

Published: 2nd Monday of each month by SWIFT (ISO 10383 RA).
Format: XLSX direct download.
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.reference_store import ReferenceStore

logger = logging.getLogger(__name__)

MIC_XLSX_URL = "https://www.iso20022.org/sites/default/files/ISO10383_MIC/ISO10383_MIC.xlsx"
MAX_RETRIES = 3


def _download_mic_xlsx() -> bytes:
    """Download the MIC register XLSX file."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(MIC_XLSX_URL, headers={"User-Agent": "Eagle/1.0 (reference-data-fetcher)"})
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
                logger.info("Downloaded MIC register: %d bytes", len(data))
                return data
        except URLError as e:
            last_error = e
            logger.warning("MIC download attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
    raise RuntimeError(f"MIC download failed after {MAX_RETRIES} attempts: {last_error}")


def _parse_mic_xlsx(xlsx_bytes: bytes) -> list[dict]:
    """Parse MIC XLSX into list of records."""
    try:
        import openpyxl
    except ImportError:
        import pandas as pd
        df = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=0, dtype=str)
        df.columns = [c.strip().upper().replace(" ", "_").replace("-", "_") for c in df.columns]

        mic_col = next((c for c in df.columns if "MIC" in c and "OPERATING" not in c and "COMMENT" not in c), None)
        omic_col = next((c for c in df.columns if "OPERATING" in c and "MIC" in c), None)
        name_col = next((c for c in df.columns if "NAME" in c and "INSTITUTION" in c or "MARKET" in c and "NAME" in c), None)
        if not name_col:
            name_col = next((c for c in df.columns if "NAME" in c), None)
        country_col = next((c for c in df.columns if "COUNTRY" in c or "ISO" in c and "COUNTRY" in c), None)
        status_col = next((c for c in df.columns if "STATUS" in c), None)

        logger.info("MIC columns detected: mic=%s, omic=%s, name=%s, country=%s, status=%s",
                     mic_col, omic_col, name_col, country_col, status_col)

        records = []
        for _, row in df.iterrows():
            mic = str(row.get(mic_col, "")).strip()
            if not mic or len(mic) != 4:
                continue
            records.append({
                "mic": mic,
                "operating_mic": str(row.get(omic_col, mic)).strip() or mic,
                "name": str(row.get(name_col, "UNKNOWN")).strip()[:500],
                "country": str(row.get(country_col, "XX")).strip()[:2],
                "status": str(row.get(status_col, "ACTIVE")).strip(),
            })
        return records

    # openpyxl path
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return []

    header = [str(c or "").strip().upper().replace(" ", "_").replace("-", "_") for c in rows[0]]
    mic_idx = next((i for i, h in enumerate(header) if h == "MIC"), None)
    omic_idx = next((i for i, h in enumerate(header) if "OPERATING" in h and "MIC" in h), None)
    name_idx = next((i for i, h in enumerate(header) if "NAME" in h), None)
    country_idx = next((i for i, h in enumerate(header) if "COUNTRY" in h), None)
    status_idx = next((i for i, h in enumerate(header) if "STATUS" in h), None)

    if mic_idx is None:
        logger.error("Could not find MIC column in header: %s", header)
        return []

    records = []
    for row in rows[1:]:
        mic = str(row[mic_idx] or "").strip()
        if not mic or len(mic) != 4:
            continue
        records.append({
            "mic": mic,
            "operating_mic": str(row[omic_idx] or mic).strip() if omic_idx is not None else mic,
            "name": str(row[name_idx] or "UNKNOWN").strip()[:500] if name_idx is not None else "UNKNOWN",
            "country": str(row[country_idx] or "XX").strip()[:2] if country_idx is not None else "XX",
            "status": str(row[status_idx] or "ACTIVE").strip() if status_idx is not None else "ACTIVE",
        })
    return records


def fetch_mic_codes(store: ReferenceStore) -> dict:
    """Download and store the full MIC register."""
    logger.info("Fetching MIC codes from %s", MIC_XLSX_URL)
    xlsx_bytes = _download_mic_xlsx()
    records = _parse_mic_xlsx(xlsx_bytes)
    if not records:
        raise RuntimeError("No MIC records parsed from downloaded file")

    store.upsert_mic_codes(records)
    active = sum(1 for r in records if r["status"] == "ACTIVE")
    countries = len(set(r["country"] for r in records))
    logger.info("Stored %d MIC codes (%d active, %d countries)", len(records), active, countries)
    return {
        "total_records": len(records),
        "active": active,
        "countries": countries,
    }


# ── CLI entry point ───────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch ISO 10383 MIC codes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from reference_data.config import get_store
    store = get_store()
    try:
        result = fetch_mic_codes(store)
        print(f"\nResult: {result}")
        print(f"Total MICs in store: {store.get_mic_count()}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
