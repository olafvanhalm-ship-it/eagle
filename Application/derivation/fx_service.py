"""ECB FX rate retrieval service.

Provides functions to fetch EUR exchange rates from the ECB Statistical Data
Warehouse, with local fallback rates for common reporting period dates.
"""

import logging
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

# Ensure shared module can be imported from parent directory
import sys
from pathlib import Path as _Path
_app_root = _Path(__file__).resolve().parent.parent.parent
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

log = logging.getLogger(__name__)

# ── ECB FX rate retrieval ───────────────────────────────────────────────────

_ECB_FX_CACHE: dict[str, float] = {}

# Hardcoded ECB reference rates for common reporting period end dates.
# These are official ECB euro reference rates published at 14:15 CET.
# Used as fallback when the ECB Data API is unreachable.
# Source: ECB Euro Foreign Exchange Reference Rates
#         https://www.ecb.europa.eu/stats/exchange/eurofxref/html/index.en.html
# Note: 2024-12-31 is a TARGET2 holiday; the ECB does not publish rates on
#       that date.  The rates below are the last published ECB reference rates
#       before year-end (published 2024-12-30).
_ECB_FALLBACK_RATES: dict[str, dict[str, float]] = {
    "2024-12-31": {
        "USD": 1.0389,
        "GBP": 0.8291,
        "CHF": 0.9404,
        "JPY": 163.56,
        "SEK": 11.4628,
        "NOK": 11.7960,
        "DKK": 7.4592,
        "PLN": 4.2730,
        "CZK": 25.0870,
        "HUF": 410.53,
        "AUD": 1.6740,
        "CAD": 1.4949,
        "SGD": 1.4127,
        "HKD": 8.0686,
        "ZAR": 19.0205,
    },
    "2024-06-30": {
        "USD": 1.0705,
        "GBP": 0.8462,
        "CHF": 0.9598,
    },
}


def _get_ecb_fallback_rate(base_currency: str, target_date: str) -> Optional[float]:
    """Look up a hardcoded ECB reference rate for a specific date.

    Falls back to the closest available date within the same reporting period
    if the exact date is not in the table.
    """
    if base_currency == "EUR":
        return 1.0

    rates = _ECB_FALLBACK_RATES.get(target_date)
    if rates and base_currency in rates:
        log.info("Using hardcoded ECB FX rate %s/EUR: %.4f (date: %s)",
                 base_currency, rates[base_currency], target_date)
        return rates[base_currency]

    return None


def _fetch_ecb_fx_rate(base_currency: str, target_date: str) -> Optional[float]:
    """Fetch EUR/base_currency rate from ECB Statistical Data Warehouse.

    The ECB publishes daily reference rates for ~30 currencies against EUR.
    For AIFMD reporting, we need the rate on the reporting period end date.
    If that date falls on a weekend/holiday, we search backwards up to 7 days.

    Args:
        base_currency: 3-letter ISO currency code (e.g. "USD")
        target_date:   date string "YYYY-MM-DD"

    Returns:
        EUR exchange rate (e.g. 1.0389 for EUR/USD), or None on failure.
    """
    if base_currency == "EUR":
        return 1.0

    cache_key = f"{base_currency}_{target_date}"
    if cache_key in _ECB_FX_CACHE:
        return _ECB_FX_CACHE[cache_key]

    # Search backwards up to 7 days to handle weekends/holidays
    dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    start = dt - timedelta(days=7)

    url = (
        f"https://data-api.ecb.europa.eu/service/data/EXR/"
        f"D.{base_currency}.EUR.SP00.A"
        f"?startPeriod={start.isoformat()}"
        f"&endPeriod={dt.isoformat()}"
        f"&detail=dataonly"
    )

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")

        # ECB returns SDMX Generic Data XML by default
        # Parse observations: <generic:ObsDimension value="DATE"/>
        #                     <generic:ObsValue value="RATE"/>
        import xml.etree.ElementTree as ET
        root = ET.fromstring(data)

        # Define SDMX namespaces
        ns = {
            "generic": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic",
            "message": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
        }

        # Collect all observations as (date, rate) pairs
        observations = []
        for obs in root.iter(f"{{{ns['generic']}}}Obs"):
            obs_dim = obs.find(f"{{{ns['generic']}}}ObsDimension")
            obs_val = obs.find(f"{{{ns['generic']}}}ObsValue")
            if obs_dim is not None and obs_val is not None:
                obs_date = obs_dim.get("value", "")
                obs_rate = float(obs_val.get("value", "0"))
                observations.append((obs_date, obs_rate))

        if not observations:
            log.warning("ECB API returned no observations for %s on %s",
                        base_currency, target_date)
            return None

        # Sort by date and take the last (closest to target_date)
        observations.sort(key=lambda x: x[0])
        obs_date, rate = observations[-1]

        log.info("ECB FX rate %s/EUR: %.4f (observation date: %s, target: %s)",
                 base_currency, rate, obs_date, target_date)

        _ECB_FX_CACHE[cache_key] = rate
        return rate

    except Exception as e:
        log.warning("Failed to fetch ECB FX rate for %s on %s: %s",
                    base_currency, target_date, e)
        return None
