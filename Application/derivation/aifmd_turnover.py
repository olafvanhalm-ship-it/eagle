"""
AIFMD Turnover Derivation Engine
==================================
Standalone function for deriving turnover summaries from transaction records.

Aggregates TRANSACTION records within a reporting period into turnover
summaries per sub-asset type, compatible with the TURNOVER record format
expected by the canonical model and XML builders.

Extracted from m_adapter.py (Phase 3 — derivation engine extraction).
"""

from __future__ import annotations

import logging
from datetime import datetime as _dt
from typing import Optional

from shared.formatting import _str, _float_val, _turnover_sub_asset_type

log = logging.getLogger(__name__)


def derive_turnovers_from_transactions(
    transactions: list[dict],
    aif_id: str,
    period_start: str,
    period_end: str,
    instrument_lookup: Optional[dict[str, dict]] = None,
) -> list[dict]:
    """Aggregate TRANSACTION records within the reporting period into
    turnover summaries per sub-asset type.

    Only transactions whose Transaction Date falls within [period_start,
    period_end] are included. Sub-Asset Type is resolved from the linked
    INSTRUMENT record (via instrument_lookup) if not directly specified
    on the TRANSACTION.

    Args:
        transactions: List of transaction dicts (all AIFs, unfiltered).
        aif_id: AIF identifier to filter transactions for.
        period_start: Reporting period start date (YYYY-MM-DD).
        period_end: Reporting period end date (YYYY-MM-DD).
        instrument_lookup: Optional dict mapping instrument name → instrument
            record, used for sub-asset type resolution when not on the
            transaction directly.

    Returns:
        List of dicts compatible with TURNOVER record format:
        [{"Sub-Asset Type of Turnover": str,
          "Market Value of Turnover": float,
          "Notional Value of Turnover": float}, ...]
    """
    try:
        p_start = _dt.strptime(period_start, "%Y-%m-%d")
        p_end = _dt.strptime(period_end, "%Y-%m-%d")
    except (ValueError, TypeError):
        log.warning(
            "Cannot parse reporting period dates for transaction filtering: "
            "%s - %s", period_start, period_end,
        )
        return []

    if instrument_lookup is None:
        instrument_lookup = {}

    # Filter transactions for this AIF within the reporting period
    in_scope: list[dict] = []
    for tx in transactions:
        tx_aif = _str(tx.get("Custom AIF Identification", ""))
        if tx_aif != aif_id:
            continue
        tx_date = tx.get("Transaction Date")
        if tx_date is None:
            in_scope.append(tx)  # no date = include (conservative)
            continue
        if isinstance(tx_date, str):
            try:
                tx_date = _dt.strptime(tx_date, "%Y-%m-%d")
            except ValueError:
                in_scope.append(tx)
                continue
        if hasattr(tx_date, "date"):
            if p_start <= tx_date <= p_end:
                in_scope.append(tx)
        else:
            in_scope.append(tx)

    if not in_scope:
        return []

    # Aggregate by sub-asset type
    agg: dict[str, dict] = {}
    for tx in in_scope:
        sub_asset = _str(tx.get("Sub-Asset Type of Turnover", ""))
        if not sub_asset:
            instr_name = _str(tx.get("Instrument Name", ""))
            if instr_name and instr_name in instrument_lookup:
                instr = instrument_lookup[instr_name]
                pos_sub = _str(instr.get("Sub-Asset Type of Position", ""))
                if pos_sub:
                    sub_asset = _turnover_sub_asset_type(pos_sub)
        if not sub_asset:
            sub_asset = "UNKNOWN"

        if sub_asset not in agg:
            agg[sub_asset] = {"mv": 0.0, "nv": 0.0}
        mv = _float_val(tx.get("Market Value of Turnover", 0))
        nv = _float_val(tx.get("Notional Value of Turnover", 0))
        agg[sub_asset]["mv"] += abs(mv) if mv else 0
        agg[sub_asset]["nv"] += abs(nv) if nv else 0

    return [
        {
            "Sub-Asset Type of Turnover": sat,
            "Market Value of Turnover": vals["mv"],
            "Notional Value of Turnover": vals["nv"],
        }
        for sat, vals in sorted(agg.items())
    ]
