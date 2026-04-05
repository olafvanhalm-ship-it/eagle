"""M adapter formatting and conversion helper functions."""

import re
from datetime import datetime
from typing import Any, Optional
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, tostring

from .constants import EEA_COUNTRIES
from .aifmd_constants import STRATEGY_TO_AIF_TYPE
from .aifmd_reference_data import _SUBASSET_TO_TURNOVER


def _str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        if val == int(val):
            return str(int(val))
        return str(val)
    return str(val).strip()


def _int_round(val: Any) -> int:
    if val is None:
        return 0
    if isinstance(val, str):
        val = val.strip()
        if not val or val in ("-", "n/a", "N/A", "NA", "#N/A"):
            return 0
        try:
            val = float(val)
        except ValueError:
            return 0
    return int(round(float(val)))


def _float_val(val: Any, default: float = 0.0) -> float:
    """Safely convert any value to float. Returns default for None, empty, '-', 'n/a'."""
    if val is None:
        return default
    if isinstance(val, str):
        val = val.strip()
        if not val or val in ("-", "n/a", "N/A", "NA", "#N/A"):
            return default
        return float(val)
    return float(val)


def _rate_fmt(val: float, decimals: int = 2) -> str:
    result = f"{val:.{decimals}f}"
    # Avoid "-0.00" / "-0.0000" etc.
    if result.startswith("-") and float(result) == 0:
        result = result[1:]
    return result


def _bool_str(val: Any) -> str:
    if val is None:
        return "false"
    s = _str(val).lower()
    if s in ("yes", "true", "1"):
        return "true"
    return "false"


def _date_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = _str(val).strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return s


def _is_eea(country_code: str) -> bool:
    return (country_code or "").upper().strip() in EEA_COUNTRIES


def _sub(parent: Element, tag: str, text: Optional[str] = None) -> Element:
    el = SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def _macro_type(sub_asset: str) -> str:
    return sub_asset[:3] if sub_asset else "NTA"


def _asset_type(sub_asset: str) -> str:
    parts = sub_asset.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return sub_asset


def _turnover_sub_asset_type(sub_asset_code: str) -> str:
    """Convert a Position SubAssetType to a Turnover SubAssetType.

    Uses the complete ESMA Annex II Table 2 mapping. Falls back to the
    pattern part1_part2_part2 for unknown codes.
    """
    if not sub_asset_code:
        return ""
    code = sub_asset_code.strip()
    if code in _SUBASSET_TO_TURNOVER:
        return _SUBASSET_TO_TURNOVER[code]
    # Fallback: part1_part2_part2
    parts = code.split("_")
    if len(parts) >= 3:
        return f"{parts[0]}_{parts[1]}_{parts[1]}"
    return code


def _predominant_type(strategy_code: str) -> str:
    if not strategy_code:
        return "NONE"
    prefix = strategy_code.split("_")[0]
    if strategy_code in STRATEGY_TO_AIF_TYPE:
        return STRATEGY_TO_AIF_TYPE[strategy_code]
    if prefix in STRATEGY_TO_AIF_TYPE:
        return STRATEGY_TO_AIF_TYPE[prefix]
    return "OTHR"


def _pretty_xml(root: Element) -> str:
    raw = tostring(root, encoding="unicode", xml_declaration=False)
    raw = f'<?xml version="1.0" encoding="UTF-8"?>\n{raw}'
    dom = parseString(raw)
    pretty = dom.toprettyxml(indent="  ", encoding=None)
    lines = pretty.split("\n")
    # Remove the xml declaration from toprettyxml (we already have one)
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(
        line for line in lines if line.strip()
    )


def _reporting_period_dates(period_type: str, year: int) -> tuple[str, str]:
    """Derive start and end dates from period type and year."""
    year = int(year)
    if period_type == "Y1":
        return f"{year}-01-01", f"{year}-12-31"
    elif period_type == "H1":
        return f"{year}-01-01", f"{year}-06-30"
    elif period_type == "H2":
        return f"{year}-07-01", f"{year}-12-31"
    elif period_type == "Q1":
        return f"{year}-01-01", f"{year}-03-31"
    elif period_type == "Q2":
        return f"{year}-04-01", f"{year}-06-30"
    elif period_type == "Q3":
        return f"{year}-07-01", f"{year}-09-30"
    elif period_type == "Q4":
        return f"{year}-10-01", f"{year}-12-31"
    elif period_type == "X1":
        return f"{year}-01-01", f"{year}-09-30"
    elif period_type == "X2":
        return f"{year}-04-01", f"{year}-12-31"
    else:
        return f"{year}-01-01", f"{year}-12-31"


def _fca_sovereign_sub_asset(esma_code: str, currency: str = "") -> str:
    """Convert ESMA sovereign bond sub-asset type to FCA equivalent.

    Uses position currency (GBP → UK bond, else → G10 non-UK bond).
    """
    is_gbp = (currency.upper() == "GBP")
    if esma_code == "SEC_SBD_EUBY":
        return "SEC_SBD_UKBY" if is_gbp else "SEC_SBD_EUGY"
    if esma_code == "SEC_SBD_EUBM":
        return "SEC_SBD_UKBM" if is_gbp else "SEC_SBD_EUGM"
    return esma_code
