"""LEI validation module — format check, GLEIF lookup, and name matching.

Implements two validation paths per ESMA AIFMD requirements:

  Path 1 — LEI provided:
    1. Format check (20-char alphanumeric, ISO 7064 checkdigit)
    2. GLEIF lookup (cache-first, API fallback)
    3. Name similarity check between reported name and GLEIF legal name

  Path 2 — LEI missing:
    1. Normalize the reported entity name
    2. Search GLEIF cache by normalized name
    3. If match found → suggest LEI, flag as DQ warning

ESMA error codes mapped:
  - AIFMR_DQT_4040000_WARNING2: LEI completeness (GLEIF validation)
  - AIFMS_DQT_4040300_WARNING1: LEI fund (GLEIF validation)

Architecture: eagle_software_architecture.md §5.5 (L3 validation)
Requirements: REQ-REF-002, REQ-VAL-001
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from shared.reference_store import ReferenceStore, LEIRecord


# ── Name normalization ─────────────────────────────────────────────────

# Common legal suffixes to strip before comparison
_LEGAL_SUFFIXES = [
    "LIMITED", "LTD", "LLC", "LLP", "LP", "INC", "INCORPORATED",
    "CORP", "CORPORATION", "CO", "COMPANY", "PLC", "AG", "GMBH",
    "SA", "SAS", "SARL", "SRL", "BV", "NV", "SE", "AB", "OY",
    "OYJ", "AS", "ASA", "APS", "KG", "KGAA", "EV", "SICAV",
    "SICAF", "SCA", "SCS", "SPA", "SPRL", "CVBA", "VOF",
    "FCP", "FCPE", "FUND", "TRUST", "MANAGEMENT", "MGMT",
    "PARTNERS", "CAPITAL", "INVESTMENTS", "INVESTMENT",
    "ADVISORS", "ADVISORY", "ASSET", "ASSETS",
    "GESELLSCHAFT", "AKTIENGESELLSCHAFT", "VERWALTUNG", "BETEILIGUNG",
    "HOLDING", "HOLDINGS", "GROUP", "INTERNATIONAL", "INTL",
    "THE",
]

# Pre-compile pattern: match any suffix at word boundary at end of string
_SUFFIX_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in sorted(_LEGAL_SUFFIXES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def normalize_entity_name(name: str) -> str:
    """Normalize an entity name for comparison.

    Steps:
      1. Unicode NFKD decomposition → strip diacritics
      2. Uppercase
      3. Replace punctuation with spaces (so "S.A." → "S A" → matches "SA")
      4. Collapse multiple spaces
      5. Strip common legal suffixes (LTD, GMBH, SA, AKTIENGESELLSCHAFT, etc.)
      6. Remove all non-alphanumeric (including remaining spaces)
      7. Fallback: if stripping removed everything, use just alphanumeric

    Examples:
      "BlackRock, Inc."                     → "BLACKROCK"
      "Société Générale S.A."              → "SOCIETEGENERALE"
      "BNP Paribas Asset Mgmt"             → "BNPPARIBAS"
      "HSBC Holdings plc"                   → "HSBC"
      "Deutsche Bank Aktiengesellschaft"    → "DEUTSCHEBANK"
    """
    if not name:
        return ""

    # Step 1: Unicode normalize — decompose accented chars
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))

    # Step 2: Uppercase
    upper = ascii_only.upper()

    # Step 3: Replace all non-alphanumeric with spaces (so "S.A." → "S A")
    spaced = re.sub(r"[^A-Z0-9]+", " ", upper).strip()

    # Step 4: Collapse sequences of single letters into one token
    # "S A" → "SA", "S A S" → "SAS", so "S.A." suffix matching works
    spaced = re.sub(r"\b([A-Z])\s+(?=[A-Z]\b)", r"\1", spaced)

    # Step 5: Strip legal suffixes (word boundaries work because we preserved spaces)
    stripped = _SUFFIX_PATTERN.sub("", spaced)

    # Step 5: Remove all remaining non-alphanumeric (spaces, etc.)
    clean = re.sub(r"[^A-Z0-9]", "", stripped)

    # Step 6: If stripping suffixes removed everything, fall back to just alphanumeric
    if not clean:
        clean = re.sub(r"[^A-Z0-9]", "", spaced)

    return clean


# ── LEI format validation (ISO 17442 + ISO 7064 checkdigit) ───────────

_LEI_PATTERN = re.compile(r"^[0-9A-Z]{18}[0-9]{2}$")


def _iso7064_check(lei: str) -> bool:
    """Validate LEI check digits per ISO 7064 Mod 97-10."""
    # Convert letters to numbers: A=10, B=11, ..., Z=35
    numeric = ""
    for c in lei:
        if c.isdigit():
            numeric += c
        else:
            numeric += str(ord(c) - ord("A") + 10)
    return int(numeric) % 97 == 1


def validate_lei_format(lei: str) -> tuple[bool, str]:
    """Validate LEI format and checkdigit.

    Returns (is_valid, error_message).
    """
    if not lei:
        return False, "LEI is empty"

    lei = lei.strip().upper()

    if len(lei) != 20:
        return False, f"LEI must be 20 characters, got {len(lei)}"

    if not _LEI_PATTERN.match(lei):
        return False, "LEI contains invalid characters (must be alphanumeric, last 2 digits numeric)"

    if not _iso7064_check(lei):
        return False, "LEI check digits are not correct (ISO 7064 Mod 97-10)"

    return True, ""


# ── Name similarity ────────────────────────────────────────────────────

def _name_similarity(name_a: str, name_b: str) -> float:
    """Compute normalized name similarity score (0.0 to 1.0).

    Uses normalized forms for comparison. Returns 1.0 for exact match,
    0.0 for completely different. Intermediate scores based on:
      - Exact normalized match → 1.0
      - One is prefix of the other → 0.9
      - Shared character ratio (Dice coefficient on bigrams) → 0.0–0.8
    """
    norm_a = normalize_entity_name(name_a)
    norm_b = normalize_entity_name(name_b)

    if not norm_a or not norm_b:
        return 0.0

    # Exact match on normalized form
    if norm_a == norm_b:
        return 1.0

    # Prefix match (one contains the other)
    if norm_a.startswith(norm_b) or norm_b.startswith(norm_a):
        return 0.9

    # Bigram Dice coefficient
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s) - 1)) if len(s) > 1 else {s}

    bg_a = bigrams(norm_a)
    bg_b = bigrams(norm_b)
    if not bg_a or not bg_b:
        return 0.0

    intersection = len(bg_a & bg_b)
    return min((2.0 * intersection) / (len(bg_a) + len(bg_b)), 0.8)


# ── Validation result types ────────────────────────────────────────────

@dataclass
class LEIValidationResult:
    """Result of LEI validation for a single entity."""
    lei_provided: str          # Original LEI from report (may be empty)
    entity_name: str           # Reported entity name
    is_valid_format: bool      # ISO 17442 format + checkdigit
    format_error: str          # Format error message (if any)
    gleif_found: bool          # Whether LEI exists in GLEIF
    gleif_record: Optional[LEIRecord]  # GLEIF record (if found)
    name_match_score: float    # 0.0–1.0 similarity between reported and GLEIF name
    name_match_status: str     # MATCH, PARTIAL, MISMATCH, NOT_CHECKED
    suggested_lei: str         # Suggested LEI from name search (Path 2)
    severity: str              # PASS, WARNING, ERROR
    message: str               # Human-readable summary
    esma_error_code: str       # ESMA DQEF code if applicable


# Thresholds for name matching
NAME_MATCH_THRESHOLD = 0.7    # Score >= this → MATCH
NAME_PARTIAL_THRESHOLD = 0.4  # Score >= this → PARTIAL (warning)


# ── Main validation functions ──────────────────────────────────────────

def validate_lei_with_gleif(
    lei: str,
    reported_name: str,
    store: ReferenceStore,
) -> LEIValidationResult:
    """Path 1: LEI is provided — validate format, lookup GLEIF, compare names.

    This implements ESMA CAF checks for LEI fields (e.g., CAF-064, CAF-065).
    """
    lei = lei.strip().upper()

    # Step 1: Format validation
    is_valid, format_error = validate_lei_format(lei)
    if not is_valid:
        return LEIValidationResult(
            lei_provided=lei, entity_name=reported_name,
            is_valid_format=False, format_error=format_error,
            gleif_found=False, gleif_record=None,
            name_match_score=0.0, name_match_status="NOT_CHECKED",
            suggested_lei="", severity="ERROR",
            message=f"LEI format invalid: {format_error}",
            esma_error_code="CAF-065",
        )

    # Step 2: GLEIF lookup (cache-first)
    gleif_record = store.get_lei(lei)

    # If not in cache, try API
    if not gleif_record:
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from reference_data.fetch_gleif_lei import lookup_lei
            api_result = lookup_lei(store, lei)
            if api_result:
                gleif_record = store.get_lei(lei)  # Re-fetch from cache after API stored it
        except Exception:
            pass  # API failure is not a blocking error — produces warning

    if not gleif_record:
        return LEIValidationResult(
            lei_provided=lei, entity_name=reported_name,
            is_valid_format=True, format_error="",
            gleif_found=False, gleif_record=None,
            name_match_score=0.0, name_match_status="NOT_CHECKED",
            suggested_lei="", severity="WARNING",
            message=f"LEI {lei} has valid format but was not found in GLEIF register",
            esma_error_code="AIFMR_DQT_4040000_WARNING2",
        )

    # Step 3: Name comparison
    score = _name_similarity(reported_name, gleif_record.legal_name)

    if score >= NAME_MATCH_THRESHOLD:
        status, severity = "MATCH", "PASS"
        msg = (f"LEI {lei} valid. GLEIF name '{gleif_record.legal_name}' "
               f"matches reported name '{reported_name}' (score: {score:.2f})")
    elif score >= NAME_PARTIAL_THRESHOLD:
        status, severity = "PARTIAL", "WARNING"
        msg = (f"LEI {lei} valid but name match is partial. "
               f"GLEIF: '{gleif_record.legal_name}' vs reported: '{reported_name}' "
               f"(score: {score:.2f})")
    else:
        status, severity = "MISMATCH", "WARNING"
        msg = (f"LEI {lei} valid but name mismatch. "
               f"GLEIF: '{gleif_record.legal_name}' vs reported: '{reported_name}' "
               f"(score: {score:.2f})")

    return LEIValidationResult(
        lei_provided=lei, entity_name=reported_name,
        is_valid_format=True, format_error="",
        gleif_found=True, gleif_record=gleif_record,
        name_match_score=score, name_match_status=status,
        suggested_lei="", severity=severity, message=msg,
        esma_error_code="" if severity == "PASS" else "AIFMS_DQT_4040300_WARNING1",
    )


def validate_name_without_lei(
    reported_name: str,
    store: ReferenceStore,
    country: str = "",
) -> LEIValidationResult:
    """Path 2: No LEI provided — search GLEIF cache by normalized name.

    Normalizes the reported name and searches for exact matches on
    the normalized_name column in the GLEIF cache. When country is provided
    (ISO 3166-1 alpha-2), it is used as an additional filter to improve
    match reliability (e.g., distinguishing "BlackRock" in US vs UK).
    """
    normalized = normalize_entity_name(reported_name)

    if not normalized:
        return LEIValidationResult(
            lei_provided="", entity_name=reported_name,
            is_valid_format=False, format_error="No LEI provided",
            gleif_found=False, gleif_record=None,
            name_match_score=0.0, name_match_status="NOT_CHECKED",
            suggested_lei="", severity="WARNING",
            message=f"No LEI provided and entity name is empty or unparseable",
            esma_error_code="AIFMR_DQT_4040000_WARNING2",
        )

    # Search cache by normalized name (with optional country filter)
    matches = store.search_lei_by_normalized_name(normalized, country=country, limit=5)

    if matches:
        best = matches[0]  # First match (all have exact normalized name match)
        country_note = f", country={best.country}" if best.country else ""
        return LEIValidationResult(
            lei_provided="", entity_name=reported_name,
            is_valid_format=False, format_error="No LEI provided",
            gleif_found=True, gleif_record=best,
            name_match_score=1.0, name_match_status="MATCH",
            suggested_lei=best.lei,
            severity="WARNING",
            message=(f"No LEI provided but entity '{reported_name}' matches "
                     f"GLEIF record '{best.legal_name}' (LEI: {best.lei}{country_note}). "
                     f"Consider adding LEI to improve data quality."),
            esma_error_code="AIFMR_DQT_4040000_WARNING2",
        )

    return LEIValidationResult(
        lei_provided="", entity_name=reported_name,
        is_valid_format=False, format_error="No LEI provided",
        gleif_found=False, gleif_record=None,
        name_match_score=0.0, name_match_status="NOT_CHECKED",
        suggested_lei="", severity="WARNING",
        message=(f"No LEI provided and entity '{reported_name}' "
                 f"(normalized: '{normalized}') not found in GLEIF cache. "
                 f"Manual LEI assignment may be required."),
        esma_error_code="AIFMR_DQT_4040000_WARNING2",
    )


def validate_lei(
    lei: str,
    reported_name: str,
    store: ReferenceStore,
    country: str = "",
) -> LEIValidationResult:
    """Unified LEI validation — dispatches to Path 1 or Path 2.

    Args:
        lei: LEI code from the report (may be empty/None)
        reported_name: Entity name from the report
        store: Reference data store with GLEIF cache
        country: ISO 3166-1 alpha-2 country code (optional, improves Path 2 matching)

    Returns:
        LEIValidationResult with full validation details
    """
    if lei and lei.strip():
        return validate_lei_with_gleif(lei, reported_name, store)
    else:
        return validate_name_without_lei(reported_name, store, country=country)
