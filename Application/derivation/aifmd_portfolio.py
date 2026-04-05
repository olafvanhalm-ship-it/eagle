"""
AIFMD Portfolio Derivation Engine
==================================
Standalone functions for portfolio-level calculations required by AIFMD
Annex IV reporting: AuM, NAV, position aggregation by sub-asset and asset
type, and geographic focus.

These functions are adapter-agnostic: they operate on position dicts
(regardless of whether the positions came from an M template, ESMA template,
XML re-import, or AI extraction).

Extracted from m_adapter.py (Phase 3 — derivation engine extraction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from shared.formatting import (
    _str, _float_val, _int_round, _macro_type, _asset_type,
    _fca_sovereign_sub_asset,
)
from shared.constants import REGION_MAP
from shared.reference_data import _COUNTRY_TO_REGION


# ── Position value resolution ───────────────────────────────────────────────

def pos_val(p: dict) -> float:
    """Get position value from a position record, trying multiple field name
    variants across M light, M full, and ESMA templates.

    This is the single source of truth for extracting a position's market value.
    """
    for key in (
        "Position value (Article 2 AIFMD)",
        "Instrument position value (as calculated under Article 3 AIFMD) in AIF Base Currency",
        "Instrument position value",
        "Position Value",
    ):
        v = p.get(key)
        if v is not None:
            return _float_val(v, 0.0)
    return 0.0


# ── AuM & NAV ──────────────────────────────────────────────────────────────

def calc_aum(positions: list[dict]) -> int:
    """Calculate Assets Under Management as sum of positive position values."""
    total = sum(pos_val(p) for p in positions if pos_val(p) > 0)
    return _int_round(total)


def calc_nav(positions: list[dict]) -> int:
    """Calculate Net Asset Value.

    Uses explicit NAV fields when available; falls back to position value.
    """
    total = 0.0
    for p in positions:
        nav_val = (
            p.get("Net Asset Value (NAV)")
            or p.get("Net Asset Value (NAV) at Reporting Period End Date in AIF Base Currency")
        )
        if nav_val is not None:
            total += _float_val(nav_val, 0.0)
        else:
            total += pos_val(p)
    return _int_round(total)


# ── Position sorting & filtering ────────────────────────────────────────────

def long_positions_sorted(positions: list[dict]) -> list[dict]:
    """Return only long (positive value) positions, sorted by value descending."""
    longs = [p for p in positions if pos_val(p) > 0]
    longs.sort(key=lambda p: pos_val(p), reverse=True)
    return longs


# ── Aggregation ─────────────────────────────────────────────────────────────

def aggregate_by_sub_asset(
    positions: list[dict],
    reporting_member_state: str = "",
) -> list[dict]:
    """Group positions by sub-asset type and sum their values.

    For FCA (GB) reporting, ESMA sovereign bond codes are converted to
    FCA equivalents based on the position's currency.

    Returns list of dicts sorted by amount descending:
        [{"sub_asset": str, "direction": str, "macro": str, "amount": float}, ...]
    """
    agg: dict[str, dict] = {}
    is_fca = reporting_member_state == "GB"

    for p in positions:
        val = pos_val(p)
        if val <= 0:
            continue
        sat = _str(
            p.get("Sub-Asset Type of Position", "")
            or p.get("Sub-Asset Type", "")
        )
        if is_fca and sat.startswith("SEC_SBD_EU"):
            ccy = _str(
                p.get("Currency of the exposure", "")
                or p.get("Instrument Currency", "")
            )
            sat = _fca_sovereign_sub_asset(sat, ccy)
        direction = _str(p.get("Long / Short", "L"))
        if sat not in agg:
            agg[sat] = {
                "sub_asset": sat,
                "direction": direction,
                "macro": _macro_type(sat),
                "amount": 0.0,
            }
        agg[sat]["amount"] += val

    return sorted(agg.values(), key=lambda x: x["amount"], reverse=True)


def aggregate_by_asset_type(
    positions: list[dict],
    reporting_member_state: str = "",
) -> list[dict]:
    """Group positions by asset type and sum their values.

    Returns list of dicts sorted by amount descending:
        [{"asset_type": str, "direction": str, "amount": float}, ...]
    """
    agg: dict[str, dict] = {}
    is_fca = reporting_member_state == "GB"

    for p in positions:
        val = pos_val(p)
        if val <= 0:
            continue
        sat = _str(
            p.get("Sub-Asset Type of Position", "")
            or p.get("Sub-Asset Type", "")
        )
        if is_fca and sat.startswith("SEC_SBD_EU"):
            ccy = _str(
                p.get("Currency of the exposure", "")
                or p.get("Instrument Currency", "")
            )
            sat = _fca_sovereign_sub_asset(sat, ccy)
        at = _asset_type(sat)
        direction = _str(p.get("Long / Short", "L"))
        if at not in agg:
            agg[at] = {"asset_type": at, "direction": direction, "amount": 0.0}
        agg[at]["amount"] += val

    return sorted(agg.values(), key=lambda x: x["amount"], reverse=True)


# ── Geographic focus ────────────────────────────────────────────────────────

@dataclass
class GeoFocusResult:
    """Result of geographic focus calculation.

    Contains both AuM-based percentages (for ESMA reporting) and raw NAV/AuM
    values (for XML builders that need the absolute amounts).
    """
    aum_pct: dict[str, float] = field(default_factory=dict)
    nav_raw: dict[str, float] = field(default_factory=dict)
    aum_raw: dict[str, float] = field(default_factory=dict)
    uk_nav: float = 0.0
    uk_aum: float = 0.0


def geo_focus(positions: list[dict], aum: int) -> GeoFocusResult:
    """Calculate geographic exposure percentages for AIFMD reporting.

    Uses AuM (long positions only) for percentage calculation.
    Also tracks NAV-based geographic focus (includes short positions)
    and UK-specific values for FCA reporting.

    Returns a GeoFocusResult with all computed values.
    """
    focus_nav = {r: 0.0 for r in REGION_MAP.values()}
    focus_aum = {r: 0.0 for r in REGION_MAP.values()}
    uk_nav = 0.0
    uk_aum = 0.0

    for p in positions:
        p_val = pos_val(p)
        nav_val = _float_val(
            p.get("Net Asset Value (NAV)", None)
            or p.get("Net Asset Value", None),
            None,
        )
        region = _str(p.get("Region", ""))
        country = region.upper() if len(region) == 2 else ""

        # First try direct REGION_MAP key match
        mapped = REGION_MAP.get(region, "")
        # Then try ISO country code lookup
        if not mapped and country:
            mapped = _COUNTRY_TO_REGION.get(country, "")

        if mapped:
            # NAV geographic focus uses NAV per position (includes negatives)
            if nav_val is not None:
                focus_nav[mapped] += nav_val
                if country == "GB":
                    uk_nav += nav_val
            elif p_val != 0:
                focus_nav[mapped] += p_val
                if country == "GB":
                    uk_nav += p_val
            # AuM geographic focus uses position value (long only)
            if p_val > 0:
                focus_aum[mapped] += p_val
                if country == "GB":
                    uk_aum += p_val

    # Build AuM percentages
    aum_pct = dict(focus_aum)  # copy before normalization
    aum_raw = dict(focus_aum)
    if aum > 0:
        for k in aum_pct:
            aum_pct[k] = round(aum_pct[k] / aum * 100, 2)

    return GeoFocusResult(
        aum_pct=aum_pct,
        nav_raw=focus_nav,
        aum_raw=aum_raw,
        uk_nav=uk_nav,
        uk_aum=uk_aum,
    )
