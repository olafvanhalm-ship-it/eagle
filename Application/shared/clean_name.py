"""Unified entity name normalization for matching across data sources.

Used by NCA register, GLEIF cache, Annex IV validation, and any future
entity matching.  Produces a clean uppercase name WITH legal form suffixes
preserved (BV, LP, LLC, SARL, etc.), suitable for deduplication and
matching.

Keeping the legal suffix is essential to avoid false matches between
different entity types (e.g. "Eagle B.V." vs "Eagle L.P.").

Examples:
    "3 Banken-Generali Investment-Gesellschaft m.b.H."  → "3 BANKEN GENERALI INVESTMENT GESELLSCHAFT MBH"
    "CARNE GLOBAL FUND MANAGERS (LUXEMBOURG) S.A."      → "CARNE GLOBAL FUND MANAGERS LUXEMBOURG SA"
    "Allianz Invest Kapitalanlagegesellschaft mbH"       → "ALLIANZ INVEST KAPITALANLAGEGESELLSCHAFT MBH"
    "Société Générale S.A."                              → "SOCIETE GENERALE SA"
    "EQT FUND MANAGEMENT S.A R.L."                      → "EQT FUND MANAGEMENT SARL"
    "BlackRock Asset Management Schweiz A/S"             → "BLACKROCK ASSET MANAGEMENT SCHWEIZ AS"
    "Marble Capital B.V."                                → "MARBLE CAPITAL BV"
    "MARBLE CAPITAL, L.P."                               → "MARBLE CAPITAL LP"
"""
from __future__ import annotations

import re
import unicodedata


def clean_name(name: str) -> str:
    """Normalize entity name for matching.

    Steps:
      1. Unicode NFKD decomposition → strip diacritics (ö→o, é→e)
      2. Uppercase
      3. Replace all non-alphanumeric with spaces
      4. Collapse single-letter sequences (S A R L → SARL, M B H → MBH)
      5. Collapse whitespace and trim
    """
    if not name:
        return ""

    # Step 1: strip diacritics
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))

    # Step 2: uppercase
    s = ascii_only.upper().strip()

    # Step 3: replace non-alphanumeric with spaces
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()

    # Step 4: collapse single-letter sequences (M B H → MBH, S A → SA)
    s = re.sub(r"\b([A-Z])\s+(?=[A-Z]\b)", r"\1", s)

    # Step 5: collapse whitespace and trim
    s = re.sub(r"\s+", " ", s).strip()

    return s
