"""
AIFMD Investor Derivation Engine
==================================
Standalone function for deriving investor group percentages from
INVESTOR_AMOUNT records.

Aggregates per-investor amounts into group percentages compatible with
the INVESTOR record format expected by the canonical model and XML builders.

Extracted from m_adapter.py (Phase 3 — derivation engine extraction).
"""

from __future__ import annotations

from shared.formatting import _str, _float_val


def derive_investor_pcts_from_amounts(
    investor_amounts: list[dict],
    aif_id: str,
) -> list[dict]:
    """Aggregate INVESTOR_AMOUNT records per AIF into investor group
    percentages, replacing the INVESTOR record.

    Groups by Investor Type, sums the absolute amounts, and calculates
    each group's percentage of the total.

    Args:
        investor_amounts: List of investor amount dicts (all AIFs, unfiltered).
        aif_id: AIF identifier to filter amounts for.

    Returns:
        List of dicts compatible with INVESTOR record format:
        [{"Investor Group Type": str,
          "Investor group NAV percentage": float}, ...]
    """
    amounts_for_aif = [
        ia for ia in investor_amounts
        if _str(ia.get("Custom AIF Identification", "")) == aif_id
    ]
    if not amounts_for_aif:
        return []

    # Sum by investor type
    type_totals: dict[str, float] = {}
    grand_total = 0.0
    for ia in amounts_for_aif:
        inv_type = _str(ia.get("Investor Type", ""))
        amount = _float_val(ia.get("Investor Amount", 0))
        if inv_type and amount:
            type_totals[inv_type] = type_totals.get(inv_type, 0) + abs(amount)
            grand_total += abs(amount)

    if not grand_total:
        return []

    return [
        {
            "Investor Group Type": inv_type,
            "Investor group NAV percentage": round(total / grand_total * 100, 2),
        }
        for inv_type, total in sorted(
            type_totals.items(), key=lambda x: x[1], reverse=True
        )
    ]
