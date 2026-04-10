"""Report retrieval and editing routes."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from api.deps import get_store, get_field_registry, get_field_classification
from api.models.requests import FieldEditRequest, GroupCellEditRequest, SourceEntityEditRequest
try:
    from api.models.requests import SourceEntityAddRequest
    print("[Eagle] SourceEntityAddRequest imported OK")
except ImportError:
    # Fallback: define inline if requests.py hasn't been synced yet
    from pydantic import BaseModel, Field as PydField
    class SourceEntityAddRequest(BaseModel):
        values: dict = PydField(default_factory=dict)
        fund_index: int = PydField(0)
    print("[Eagle] WARNING: SourceEntityAddRequest not found in requests.py — using inline fallback")

from api.models.responses import (
    ReportDetailResponse, ReportFieldResponse, FieldValidationResponse,
    FieldValidationFinding,
    SourceDataResponse, SourceEntityResponse, EditResultResponse,
)
from persistence.report_store import ReviewEdit

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["report"])

# ISO-2 country codes in the EEA — used to auto-derive AIFM EEA Flag (AFM20)
# and AIF EEA Flag (Q19) when the XML extractor didn't emit a value
# (e.g. FCA-format reports, or templates that don't include the field).
_EEA_COUNTRY_CODES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
    "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT",
    "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK",
}


def _derive_eea_flag(country_code: str | None) -> str:
    return "true" if (country_code or "").strip().upper() in _EEA_COUNTRY_CODES else "false"

# ── Startup diagnostic ──────────────────────────────────────────────────────
print("[Eagle] report.py loaded — version: session-10 (source add/delete endpoints)")


@router.get("/version")
async def get_version():
    """Test endpoint — open http://localhost:8000/api/v1/version in your browser."""
    return {"version": "session-10", "endpoints": ["POST source add", "DELETE source delete"]}


def _field_level_validation(reports: list, registry) -> list[dict]:
    """Canonical field-level validation: mandatory, format, type checks.

    Runs on every report load so fields always have traffic-light colours.
    This validates the *canonical* data, not XML.
    """
    findings = []
    if not registry:
        return findings

    for report in reports:
        report_type = report.report_type
        all_fields = (
            registry.aifm_fields() if report_type == "AIFM"
            else registry.aif_fields()
        )
        fields_json = report.fields_json or {}

        for fid, fdef in all_fields.items():
            field_data = fields_json.get(fid, {})
            value = field_data.get("value") if isinstance(field_data, dict) else field_data

            # Check mandatory fields
            if fdef.mandatory and not fdef.is_repeating:
                if value is None or (isinstance(value, str) and not value.strip()):
                    findings.append({
                        "rule_id": f"MAN-{report_type}-{fid}",
                        "field_path": f"{report_type}.{fid}",
                        "status": "FAIL",
                        "check_type": "dqf",
                        "severity": "HIGH",
                        "message": f"Mandatory field Q{fid} ({fdef.field_name}) is empty",
                        "fix_suggestion": f"Provide a value for {fdef.field_name}",
                    })
                    continue

            if value is None or (isinstance(value, str) and not value.strip()):
                continue

            # Skip format check for fields validated via allowed_values_ref
            # (booleans, enums, country codes etc. are validated against the
            # reference table, not the ESMA format string which often specifies
            # a max-length that doesn't apply to the human-readable values)
            has_ref = bool(fdef.allowed_values_ref)

            # Check format constraints (skip for enum/boolean/reference fields)
            if fdef.format and isinstance(value, str) and not has_ref:
                format_ok = _check_format_quick(value, fdef.format)
                if not format_ok:
                    findings.append({
                        "rule_id": f"FMT-{report_type}-{fid}",
                        "field_path": f"{report_type}.{fid}",
                        "status": "FAIL",
                        "check_type": "dqf",
                        "severity": "MEDIUM",
                        "message": f"Q{fid} ({fdef.field_name}) value '{value}' does not match expected format '{fdef.format}'",
                    })

            # Check allowed values (for fields with reference tables)
            if has_ref and registry:
                allowed = registry.reference_table(fdef.allowed_values_ref)
                if allowed and str(value) not in [str(v) for v in allowed]:
                    findings.append({
                        "rule_id": f"REF-{report_type}-{fid}",
                        "field_path": f"{report_type}.{fid}",
                        "status": "WARNING",
                        "check_type": "dqf",
                        "severity": "LOW",
                        "message": f"Q{fid} ({fdef.field_name}) value '{value}' not in reference table '{fdef.allowed_values_ref}'",
                    })

            # Check data type (skip for booleans with allowed_values_ref)
            if fdef.data_type and value is not None and not has_ref:
                type_ok = _check_data_type_quick(value, fdef.data_type.value)
                if not type_ok:
                    findings.append({
                        "rule_id": f"TYP-{report_type}-{fid}",
                        "field_path": f"{report_type}.{fid}",
                        "status": "FAIL",
                        "check_type": "dqf",
                        "severity": "MEDIUM",
                        "message": f"Q{fid} ({fdef.field_name}) type mismatch — expected {fdef.data_type.value}",
                    })

    return findings


def _check_format_quick(value: str, fmt: str) -> bool:
    """Quick format check (subset of the full validator)."""
    import re
    if not fmt:
        return True
    stripped = fmt.strip()
    if stripped.isdigit():
        return len(str(value)) <= int(stripped)
    if "(n)" in stripped:
        esma_regex = re.sub(r"(\d+)\(n\)", lambda m: r"\d{" + m.group(1) + "}", stripped)
        try:
            if "T" in esma_regex and "T" not in str(value):
                date_regex = esma_regex.split("T")[0]
                return bool(re.fullmatch(date_regex, str(value)))
            return bool(re.fullmatch(esma_regex, str(value)))
        except re.error:
            return True
    return True  # Skip complex patterns for auto-validation


def _check_data_type_quick(value, expected_type: str) -> bool:
    """Quick data type check."""
    if value is None:
        return True
    try:
        if expected_type in ("N", "NUM", "NUMERIC"):
            float(str(value))
            return True
        elif expected_type in ("D", "DATE"):
            from datetime import datetime
            datetime.strptime(str(value)[:10], "%Y-%m-%d")
            return True
        elif expected_type in ("B", "BOOL", "BOOLEAN"):
            return str(value).lower() in ("true", "false", "1", "0", "yes", "no")
    except (ValueError, TypeError):
        return False
    return True


def _build_field_response(
    field_id: str,
    field_value: dict,
    registry,
    classification: dict,
    report_type: str,
    validation_map: dict | None = None,
) -> ReportFieldResponse:
    """Build a ReportFieldResponse from stored field data + registry metadata."""
    # Get field definition from registry
    fdef = None
    if registry:
        if report_type == "AIFM":
            fdef = registry.aifm_field(field_id)
        else:
            fdef = registry.aif_field(field_id)

    # Get classification (entity, composite, report)
    # MUST use namespaced key "AIFM.33" / "AIF.33" — field IDs are NOT
    # globally unique (e.g., field 33 = AuM in AIFM, share class in AIF).
    category = classification.get(f"{report_type}.{field_id}", {}).get("category", "report")
    has_value = field_value.get("value") is not None and field_value.get("value") != ""

    # Editable: entity fields and non-system report fields WITH data, or mandatory/conditional
    # Empty optional/conditional fields that are derived/calculated should not be editable
    is_system = _is_system_field(field_id, report_type)
    if category == "entity":
        editable = True
    elif is_system:
        editable = False
    elif category == "composite":
        editable = False
    elif fdef and fdef.obligation.value == "O" and not has_value:
        # Empty optional fields: not editable (data must come from source)
        editable = False
    else:
        editable = True

    # Validation status
    val_response = None
    if validation_map and field_id in validation_map:
        val_response = validation_map[field_id]

    # Load reference values for dropdown fields
    ref_values: list = []
    if fdef and fdef.allowed_values_ref and registry:
        ref_values = registry.reference_table(fdef.allowed_values_ref)

    # Determine source/priority: if manually overridden keep that;
    # otherwise, composite/derived fields get DERIVED, directly-mapped fields get IMPORTED.
    raw_priority = field_value.get("priority", "")
    raw_source = field_value.get("source", "unknown")
    if raw_priority == "MANUALLY_OVERRIDDEN":
        priority = "MANUALLY_OVERRIDDEN"
        source = raw_source
    elif category == "composite":
        priority = "DERIVED"
        source = "Calculated from source data"
    elif is_system:
        priority = "IMPORTED"
        source = "Imported from source file"
    else:
        # Non-system, non-composite fields: check if it's a repeating/calculated field
        # Fields in header sections are imported; others may be derived
        is_header_section = fdef and ("Header" in (fdef.section or "") or "Identifier" in (fdef.section or ""))
        if is_header_section:
            priority = "IMPORTED"
            source = "Imported from source file"
        else:
            priority = raw_priority or "IMPORTED"
            source = raw_source

    return ReportFieldResponse(
        field_id=field_id,
        field_name=fdef.field_name if fdef else f"Field {field_id}",
        section=fdef.section if fdef else "Unknown",
        value=field_value.get("value"),
        source=source,
        priority=priority,
        data_type=fdef.data_type.value if fdef else "A",
        obligation=fdef.obligation.value if fdef else "O",
        format=fdef.format if fdef else "",
        allowed_values_ref=fdef.allowed_values_ref if fdef else None,
        reference_values=ref_values,
        xsd_element=fdef.xsd_element if fdef else "",
        repetition=fdef.repetition if fdef else "[1..1]",
        editable=editable,
        category=category,
        report_type=report_type,
        technical_guidance=fdef.technical_guidance if fdef else "",
        nca_deviations={},
        validation=val_response,
    )


def _is_system_field(field_id: str, report_type: str) -> bool:
    """Check if a report field is system-generated (not user-editable).

    Fields driven by enumerated values (4, 5, 8, 13, 16 for both AIFM and AIF)
    are deliberately NOT listed here — they must be editable so the user can
    pick from the dropdown rendered by `EditableCell`. Purely derived-from-
    metadata fields (reporting dates, version, creation date) stay system.
    """
    system_fields = {
        # Keep: 1 = Member state (derived from NCA), 2 = Version,
        #       3 = Creation date (auto-updated), 6/7 = Period start/end,
        #       9 = Period year, 10/11/12 = Change metadata
        "AIFM": {"1", "2", "3", "6", "7", "9", "10", "11", "12"},
        # Same principle for AIF. 17 stays system (AIF national code comes
        # from the NCA override block).
        "AIF": {"1", "2", "3", "6", "7", "9", "10", "11", "12", "17"},
    }
    return field_id in system_fields.get(report_type, set())


@router.get("/session/{session_id}/report/manager")
async def get_manager_report(
    session_id: str,
    show_all: bool = Query(False, description="Show all fields including empty optional"),
    nca: str = Query(None, description="NCA code to show NCA-specific overrides"),
):
    """Get the AIFM (Manager) report for a session."""
    return await _get_report(session_id, "AIFM", 0, show_all, nca=nca)


@router.get("/session/{session_id}/report/fund/{index}")
async def get_fund_report(
    session_id: str,
    index: int,
    show_all: bool = Query(False, description="Show all fields including empty optional"),
    nca: str = Query(None, description="NCA code to show NCA-specific overrides"),
):
    """Get a specific AIF (Fund) report by index."""
    return await _get_report(session_id, "AIF", index, show_all, nca=nca)


async def _get_report(session_id: str, report_type: str, index: int, show_all: bool, nca: str | None = None):
    """Internal: build and return a report detail response."""
    store = get_store()
    report = store.get_report_by_type_and_index(session_id, report_type, index)
    if report is None:
        raise HTTPException(status_code=404, detail=f"{report_type} report index {index} not found")

    # Get session to know filing type (affects field visibility)
    session = store.get_session(session_id)
    filing_type = session.filing_type if session else "INIT"

    registry = get_field_registry()
    classification = get_field_classification()

    # Determine content type from extracted field data (field 5 = AIFContentType / AIFMContentType)
    fields_data_raw = report.fields_json or {}

    # ── Migrate old AIFM field IDs if needed ───────────────────────────
    # The XML extractor previously assigned wrong ESMA field IDs for AIFM
    # currency (24-30 instead of 33-38) and principal markets/instruments
    # (31-37 instead of 26-32).  Detect and remap on load.
    if report_type == "AIFM" and fields_data_raw:
        _needs_migration = False
        # Detection: if field "24" has a numeric value > 1000, it's AuM data
        # (under correct mapping, field 24 is a country code or empty)
        f24_val = str(fields_data_raw.get("24", {}).get("value", "") or "")
        if f24_val.isdigit() and int(f24_val) > 1000:
            _needs_migration = True

        if _needs_migration:
            _AIFM_FIELD_MIGRATION = {
                # Old currency IDs → correct ESMA IDs
                "24": "33",  # AUMAmountInEuro
                "27": "34",  # AUMAmountInBaseCurrency
                "26": "35",  # BaseCurrency
                "28": "36",  # FXEURReferenceRateType
                "29": "37",  # FXEURRate
                "30": "38",  # FXEUROtherReferenceRateDescription
                # Old principal markets IDs → correct ESMA IDs
                "31": "26",  # Ranking (markets)
                "32": "27",  # MarketCodeType
                "33": "28",  # MarketCode
                "34": "29",  # AggregatedValueAmount (markets)
                # Old principal instruments IDs → correct ESMA IDs
                "35": "30",  # Ranking (instruments)
                "36": "31",  # SubAssetType
                "37": "32",  # AggregatedValueAmount (instruments)
            }
            # Two-pass remap to avoid key collisions
            migrated: dict = {}
            for old_id, data in fields_data_raw.items():
                new_id = _AIFM_FIELD_MIGRATION.get(old_id, old_id)
                migrated[new_id] = data
            report.fields_json = migrated
            fields_data_raw = migrated

            # Also remap groups_json column keys
            _groups = report.groups_json or {}
            for gname in ("aifm_principal_markets", "aifm_principal_instruments"):
                if gname in _groups:
                    new_rows = []
                    for row in _groups[gname]:
                        new_row = {}
                        for k, v in row.items():
                            new_key = _AIFM_FIELD_MIGRATION.get(k, k)
                            new_row[new_key] = v
                        new_rows.append(new_row)
                    _groups[gname] = new_rows
            report.groups_json = _groups

            # Persist the migration so it only happens once
            store.save_report(report)
            log.info("Migrated AIFM field IDs for session %s", session_id)

    ct_val = fields_data_raw.get("5", {}).get("value", "2")
    try:
        content_type = int(ct_val)
    except (ValueError, TypeError):
        content_type = 2  # default to Art 24(1) if unknown

    # Detect no-reporting flag: AIF field 23 or AIFM field 21
    # When true, only header fields apply (1-23 for AIF, 1-21 for AIFM)
    _no_reporting_field = "23" if report_type == "AIF" else "21"
    _no_reporting_val = fields_data_raw.get(_no_reporting_field, {}).get("value", "")
    is_no_reporting = str(_no_reporting_val).strip().lower() in ("true", "t", "yes", "1")
    _no_reporting_max = int(_no_reporting_field)  # 23 for AIF, 21 for AIFM

    # ── Auto-validate on canonical (not XML) ────────────────────────────
    # Always run field-level validation on load so every field gets a
    # traffic-light colour.  This replaces the old "only after Validate
    # button" approach and validates the canonical, not the XML.
    validation_run = True  # Always true now — we auto-validate on every load
    validation_map: dict[str, FieldValidationResponse] = {}

    # Step 1: run canonical field-level validation (mandatory, format, type)
    # This is the *authoritative* source for MAN-/FMT-/TYP- findings because
    # it always reflects the current state of the report after any inline
    # edits the user has made.
    auto_findings = _field_level_validation([report], registry)
    _auto_rule_prefixes = ("MAN-", "FMT-", "TYP-")

    # Step 2: merge any previously-stored validation run (YAML business rules,
    # XSD findings) — but DROP any field-level findings from storage because
    # `auto_findings` already regenerated those from the live state. Keeping
    # stored field-level findings would re-surface FAILs from before the
    # user fixed a value, or from a prior buggy version of _check_format.
    latest_val = store.get_latest_validation(session_id)
    stored_findings: list[dict] = []
    if latest_val and latest_val.findings_json:
        for f in latest_val.findings_json:
            rid = str(f.get("rule_id", ""))
            if rid.startswith(_auto_rule_prefixes):
                continue
            stored_findings.append(f)

    # Combine auto + stored findings into per-field lists
    _all_findings: dict[str, list[dict]] = {}
    for finding in auto_findings + stored_findings:
        field_path = finding.get("field_path", "")
        if not field_path or "." not in field_path:
            continue
        path_type, fid = field_path.rsplit(".", 1)
        if path_type != report_type:
            continue
        if fid:
            _all_findings.setdefault(fid, []).append(finding)

    # Build FieldValidationResponse with multiple findings per field
    for fid, flist in _all_findings.items():
        # De-duplicate by rule_id
        seen_rules: set[str] = set()
        unique: list[FieldValidationFinding] = []
        for f in flist:
            rid = f.get("rule_id", "")
            if rid and rid in seen_rules:
                continue
            seen_rules.add(rid)
            unique.append(FieldValidationFinding(
                rule_id=rid,
                status=f.get("status", "PASS"),
                severity=f.get("severity", "INFO"),
                message=f.get("message", ""),
                fix_suggestion=_generate_fix_suggestion(f, registry, report_type),
            ))
        # Aggregate status: FAIL > WARNING > PASS
        agg = "PASS"
        for u in unique:
            if u.status == "FAIL":
                agg = "FAIL"
                break
            if u.status == "WARNING":
                agg = "WARNING"
        # Legacy fields from worst finding
        worst = next((u for u in unique if u.status == agg and agg != "PASS"), None)
        validation_map[fid] = FieldValidationResponse(
            status=agg,
            findings=unique,
            rule_id=worst.rule_id if worst else None,
            message=worst.message if worst else None,
            fix_suggestion=worst.fix_suggestion if worst else None,
            severity=worst.severity if worst else None,
        )

    # Implicit PASS for valued fields without any findings
    for fid in (report.fields_json or {}):
        if fid not in validation_map:
            validation_map[fid] = FieldValidationResponse(status="PASS")

    # Build sections from fields
    sections: dict[str, list[ReportFieldResponse]] = {}
    fields_data = report.fields_json or {}

    # Get all field definitions for this report type
    if registry:
        all_fields = registry.aifm_fields() if report_type == "AIFM" else registry.aif_fields()
    else:
        all_fields = {}

    # Fields that only apply to AMND/CANCEL filings (change codes, obligation changes)
    # These should be hidden for INIT filings even if mandatory in schema.
    #
    # NOTE: AIFM fields 10/11/12 (AIFM reporting obligation change codes +
    # change quarter) were previously hidden for INIT filings. They belong
    # to the AIFM header section and must be visible so the user can
    # populate them during normal reviews. Keeping them in this list hid
    # them entirely for INIT — removed.
    amnd_only_fields = {
        "AIFM": {"CANC-AIFM-1", "CANC-AIFM-2", "CANC-AIFM-3", "CANC-AIFM-4"},
        "AIF": {"10", "11", "12", "CANC-AIF-1", "CANC-AIF-2", "CANC-AIF-3", "CANC-AIF-4", "CANC-AIF-5"},
    }

    # Header-section fields that must always be shown even when empty and
    # optional (default view would otherwise hide them).
    _always_show = {
        "AIFM": {"10", "11", "12"},
        "AIF": set(),
    }

    # Sections that should be hidden entirely when empty for INIT filings
    # (e.g. Controlled Structure, Dominant Influence — only mandatory if applicable)
    _init_hide_when_empty_sections = {
        "AIF Cancellation Record",
        "AIFM Cancellation Record",
    }

    # Import content-type applicability from the registry (single source of truth)
    from canonical.aifmd_field_registry import FieldRegistry as _FR

    # ── Gate-value helpers (used by both field-level and group-level gates) ──
    def _gate_val(fid_arg: str) -> str:
        return str(fields_data.get(fid_arg, {}).get("value", "")).strip().lower()

    def _gate_is_true(fid_arg: str) -> bool:
        return _gate_val(fid_arg) in ("true", "t", "1", "yes")

    def _gate_is_false_or_empty(fid_arg: str) -> bool:
        return _gate_val(fid_arg) in ("false", "f", "0", "no", "")

    for fid, fdef in all_fields.items():
        has_value = fid in fields_data
        has_failure = fid in validation_map and validation_map[fid].status in ("FAIL", "WARNING")

        # Hide AMND/CANCEL-only fields for INIT filings
        if filing_type == "INIT" and fid in amnd_only_fields.get(report_type, set()):
            if not has_value:
                continue

        # No-reporting filing: only header fields apply (1-23 for AIF, 1-21 for AIFM)
        if is_no_reporting:
            try:
                fid_num = int(fid)
                if fid_num > _no_reporting_max:
                    continue  # skip all fields beyond the header
            except ValueError:
                continue  # skip non-numeric fields (CANC-*, etc.)

        # Hide entire cancellation sections for INIT filings
        if filing_type == "INIT" and fdef.section in _init_hide_when_empty_sections:
            if not has_value:
                continue

        # Hide fields whose section does not apply to this content type
        # (e.g. Art 24(2) sections hidden for CT=2 reports)
        if report_type == "AIF" and not _FR.is_section_applicable(fdef.section, content_type):
            if not has_value:
                continue  # skip inapplicable empty fields

        # ── Dynamic field-level visibility gates (AIF) ─────────────────
        # Hide empty fields whose gate condition is not met.
        # Fields WITH values are always shown (the user entered them).
        if report_type == "AIF" and not has_value:
            try:
                fid_num = int(fid)
            except ValueError:
                fid_num = -1

            # Q33 (ShareClassFlag) → share class identifiers (Q34-Q40)
            # Q41 is not gated by Q33 per ESMA guidelines
            if 34 <= fid_num <= 40 and _gate_is_false_or_empty("33"):
                continue

            # Q57 (PredominantAIFType) → dominant influence (Q131-Q136)
            # Q137-Q138 are not gated by Q57 per ESMA guidelines
            if 131 <= fid_num <= 136 and _gate_val("57") != "peqf":
                continue

            # REMOVED: Q57→Q286-Q296 gate — ESMA does not gate these fields on Q57
            # REMOVED: Q203→Q204-Q213 gate — independent optional flags per ESMA
            # REMOVED: CT→Q279-Q280 gate — redundant with CT section filtering

            # Q172 (DirectClearingFlag) → CCP details (Q173-Q177)
            if 173 <= fid_num <= 177 and _gate_is_false_or_empty("172"):
                continue

            # Q161 (CounterpartyExposureFlag, AIF→counterparty) →
            # counterparty details (Q162-Q165)
            if 162 <= fid_num <= 165 and _gate_is_false_or_empty("161"):
                continue

            # Q167 (CounterpartyExposureFlag, counterparty→AIF) →
            # counterparty details (Q168-Q171)
            if 168 <= fid_num <= 171 and _gate_is_false_or_empty("167"):
                continue

            # Q297 (BorrowingSourceFlag) → borrowing source details (Q298-Q301)
            if 298 <= fid_num <= 301 and _gate_is_false_or_empty("297"):
                continue

            # Prime broker section (Q45-Q47): optional, but only relevant
            # when the fund actually uses prime brokers.  Hide when the
            # entire section is empty AND no prime broker data exists in
            # source canonical (no explicit flag — presence-based gate).
            # This is handled by the standard "hide empty optional" logic
            # below, so no extra gate needed here.

        # Determine visibility in default view
        if not show_all:
            if not has_value and not has_failure:
                if fdef.obligation.value == "M":
                    pass  # Always show mandatory even when empty
                elif fid in _always_show.get(report_type, set()):
                    pass  # Always show header-section fields
                else:
                    continue  # Hide all empty non-mandatory (C, O, F)

        field_value = fields_data.get(fid, {"value": None, "source": "", "priority": "IMPORTED"})
        field_resp = _build_field_response(fid, field_value, registry, classification, report_type, validation_map)

        section_name = field_resp.section
        if section_name not in sections:
            sections[section_name] = []
        sections[section_name].append(field_resp)

    # Sort fields within sections by field_id (numeric)
    for section_name in sections:
        sections[section_name].sort(key=lambda f: _sort_key(f.field_id))

    # Count empty sections (for the "N empty sections" badge)
    all_sections = set(fdef.section for fdef in all_fields.values())
    visible_sections = set(sections.keys())
    empty_section_count = len(all_sections - visible_sections)

    # Groups — resolve field_id column headers to human-readable names
    # For no-reporting filings, suppress all groups (they're all post-header data)
    groups_data = {} if is_no_reporting else dict(report.groups_json or {})

    # Create synthetic groups for geographical focus (scalar fields → table rows)
    # These are fixed-size arrays in the schema, not XML repeating groups,
    # so we synthesise them here for tabular display.
    _synthetic_field_ids: set[str] = set()
    if report_type == "AIF" and fields_data:
        _GEO_REGIONS = [
            "Africa", "Asia Pacific", "Europe (non-EEA)", "Europe EEA",
            "Middle East", "North America", "South America", "Supra National",
        ]
        _nav_ids = [str(i) for i in range(78, 86)]
        _aum_ids = [str(i) for i in range(86, 94)]
        nav_rows = []
        for region, fid in zip(_GEO_REGIONS, _nav_ids):
            val = fields_data.get(fid, {}).get("value")
            if val is not None:
                nav_rows.append({"region": region, "nav_pct": val})
        if nav_rows:
            groups_data["nav_geographical_focus"] = nav_rows
            _synthetic_field_ids.update(_nav_ids)
        aum_rows = []
        for region, fid in zip(_GEO_REGIONS, _aum_ids):
            val = fields_data.get(fid, {}).get("value")
            if val is not None:
                aum_rows.append({"region": region, "aum_pct": val})
        if aum_rows:
            groups_data["aum_geographical_focus"] = aum_rows
            _synthetic_field_ids.update(_aum_ids)

        # Monthly data table: 12 months × 5 metrics (Q219-Q278)
        _MONTHS = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        _monthly_metrics = [
            ("gross_return", 219),   # Q219-Q230: Gross investment return %
            ("net_return", 231),     # Q231-Q242: Net investment return %
            ("nav_change", 243),     # Q243-Q254: NAV change %
            ("subscriptions", 255),  # Q255-Q266: Number of subscriptions
            ("redemptions", 267),    # Q267-Q278: Number of redemptions
        ]
        monthly_rows = []
        monthly_field_ids: set[str] = set()
        for month_idx, month_name in enumerate(_MONTHS):
            row: dict[str, Any] = {"month": month_name}
            has_any = False
            for metric_name, start_fid in _monthly_metrics:
                fid = str(start_fid + month_idx)
                val = fields_data.get(fid, {}).get("value")
                row[metric_name] = val
                monthly_field_ids.add(fid)
                if val is not None:
                    has_any = True
            if has_any:
                monthly_rows.append(row)
        if monthly_rows:
            groups_data["monthly_data"] = monthly_rows
            _synthetic_field_ids.update(monthly_field_ids)

    # ── Dynamic visibility gates (group-level) ──────────────────────────
    if report_type == "AIF":
        # Q33 (ShareClassFlag): if false/empty, hide the share_classes group
        if _gate_is_false_or_empty("33"):
            groups_data.pop("share_classes", None)

        # Q57 (PredominantAIFType): dominant influence section only for PEQF
        _predominant_type = _gate_val("57")
        if _predominant_type != "peqf":
            # Hide dominant_influence group and the section
            groups_data.pop("dominant_influence", None)
            sections.pop("Dominant Influence [see Article 1 of Directive 83/349/EEC]", None)
        else:
            # PEQF: ensure dominant_influence always appears as a group table,
            # even when there's no data yet (so users can fill it in).
            _DOM_INF_FIELDS = [
                ("131", "company_name"), ("132", "lei_code"), ("133", "bic_code"),
                ("134", "transaction_type"), ("135", "other_transaction_desc"), ("136", "voting_rights_pct"),
            ]
            if "dominant_influence" not in groups_data:
                # Build from scalar fields if any have values
                row: dict[str, Any] = {}
                has_any = False
                for fid, col_name in _DOM_INF_FIELDS:
                    val = fields_data.get(fid, {}).get("value")
                    row[col_name] = val
                    if val is not None:
                        has_any = True
                # Always create at least an empty row for the table structure
                groups_data["dominant_influence"] = [row]
                _synthetic_field_ids.update(fid for fid, _ in _DOM_INF_FIELDS)
            # Remove the section so fields aren't shown both as section AND group
            sections.pop("Dominant Influence [see Article 1 of Directive 83/349/EEC]", None)

        # Q57: controlled_structures group only for PEQF
        if _predominant_type != "peqf":
            groups_data.pop("controlled_structures", None)

        # Q172 (DirectClearingFlag): if false/empty, hide CCP exposures group
        if _gate_is_false_or_empty("172"):
            groups_data.pop("ccp_exposures", None)

        # Q161 (CounterpartyExposureFlag, AIF→counterparty): if false/empty,
        # hide fund_to_counterparty group
        if _gate_is_false_or_empty("161"):
            groups_data.pop("fund_to_counterparty", None)

        # Q167 (CounterpartyExposureFlag, counterparty→AIF): if false/empty,
        # hide counterparty_to_fund group
        if _gate_is_false_or_empty("167"):
            groups_data.pop("counterparty_to_fund", None)

        # Q297 (BorrowingSourceFlag): if false/empty, hide borrowing_sources group
        if _gate_is_false_or_empty("297"):
            groups_data.pop("borrowing_sources", None)

        # Monthly data visibility: only for certain reporting periods
        # Q8 = reporting period type. Monthly fields (Q219-Q278) are only
        # relevant for H1, H2, Y1, X1, X2 (not Q1-Q4 single quarter)
        _period_type = _gate_val("8")
        if _period_type in ("q1", "q2", "q3", "q4"):
            # For quarterly reporting, only 3 months of data are relevant
            # Don't hide the group — the backend already filters by which months have values
            pass

    # Collect field IDs covered by groups → exclude from section display
    group_field_ids: set[str] = set(_synthetic_field_ids)
    for gname, rows in groups_data.items():
        if not rows:
            continue
        for row in rows:
            for key in row:
                # Only exclude numeric field IDs (not synthetic keys like "region")
                try:
                    int(key)
                    group_field_ids.add(key)
                except ValueError:
                    pass

    # Remove group-covered fields from sections
    for sec_name in list(sections.keys()):
        sections[sec_name] = [f for f in sections[sec_name] if f.field_id not in group_field_ids]
        if not sections[sec_name]:
            del sections[sec_name]

    group_columns: dict[str, dict[str, str]] = {}
    group_obligations: dict[str, dict[str, str]] = {}
    for gname, rows in groups_data.items():
        if not rows:
            continue
        col_map: dict[str, str] = {}
        ob_map: dict[str, str] = {}
        for col_id in rows[0]:
            fdef_col = None
            if registry:
                fdef_col = (
                    registry.aifm_field(col_id) if report_type == "AIFM"
                    else registry.aif_field(col_id)
                )
            if fdef_col:
                col_map[col_id] = fdef_col.field_name
                ob_map[col_id] = fdef_col.obligation.value
            else:
                # Synthetic columns (region, nav_pct, etc.) — prettify
                col_map[col_id] = col_id.replace("_", " ").title()
        group_columns[gname] = col_map
        if ob_map:
            group_obligations[gname] = ob_map

    # Compute completeness dynamically:
    # (applicable required fields − errors) / applicable required fields × 100
    #
    # "Required" means:
    # - M (mandatory) fields that apply to this filing type AND content type
    # - C (conditional) fields in sections that are active (have data)
    # - Only sections applicable to this content type count

    active_sections: set[str] = set()
    for fid, fdef in all_fields.items():
        if fid in fields_data:
            active_sections.add(fdef.section)

    required_ids: set[str] = set()
    for fid, fdef in all_fields.items():
        if filing_type == "INIT" and fid.startswith("CANC-"):
            continue
        # No-reporting: only header fields count
        if is_no_reporting:
            try:
                if int(fid) > _no_reporting_max:
                    continue
            except ValueError:
                continue
        # Skip sections not applicable to this content type
        if report_type == "AIF" and not _FR.is_section_applicable(fdef.section, content_type):
            continue
        ob = fdef.obligation.value
        if ob == "M":
            if fdef.section in active_sections or fdef.mandatory:
                required_ids.add(fid)
        elif ob == "C" and fdef.section in active_sections:
            required_ids.add(fid)

    error_count = sum(
        1 for fid in required_ids
        if fid in validation_map and validation_map[fid].status == "FAIL"
    )
    required_count = len(required_ids) if required_ids else 1
    completeness = round(100.0 * (required_count - error_count) / required_count, 1)

    # ── Apply NCA-specific overrides when nca parameter is set ──────────
    if nca:
        _apply_nca_overrides(sections, validation_map, nca, report_type, fields_data, registry)
        # Override NCA-specific fields with the selected NCA's values.
        # The stored fields come from whichever NCA XML was extracted during
        # upload; when the user switches NCA in the sidebar, these must
        # reflect the selected NCA.
        #
        # Report-type-aware mapping (field IDs are NOT globally unique):
        #   AIF  field 1  = Reporting Member State      → NCA country code
        #   AIF  field 17 = AIF National Code           → NCA national code
        #   AIFM field 1  = Reporting Member State      → NCA country code
        #   AIFM field 17 = AIFM Jurisdiction            → preserve from upload
        #   AIFM field 18 = AIFM National Code          → NCA national code
        #
        # NOTE: AIFM field 17 is the AIFM's home/establishment jurisdiction —
        # a property of the firm itself, NOT of the filing relationship. For
        # EU-authorised AIFMs it is their home member state (may differ from
        # the filing NCA if they use a passport). For non-EU AIFMs filing via
        # NPPR it is their actual non-EU country (e.g. 747 Capital → US). It
        # must NEVER be overwritten with the filing NCA code.
        _nca_nc = report.nca_national_codes.get(nca, "")

        def _clear_validation(_fr):
            """Reset validation for an overridden field so stale failures
            from a previously extracted NCA XML don't turn the cell red."""
            _fr.validation = FieldValidationResponse(
                status="PASS", findings=[], rule_id="", message="",
                fix_suggestion="", severity="",
            )
            validation_map.pop(_fr.field_id, None)

        for _sec_fields in sections.values():
            for fr in _sec_fields:
                if fr.field_id == "1":
                    fr.value = nca
                    _clear_validation(fr)
                elif report_type == "AIF" and fr.field_id == "17" and _nca_nc:
                    fr.value = _nca_nc
                    _clear_validation(fr)
                # AIFM field 17 is intentionally NOT overridden — see note above.
                elif report_type == "AIFM" and fr.field_id == "18" and _nca_nc:
                    fr.value = _nca_nc
                    _clear_validation(fr)

    # ── Auto-derive EEA flags when empty ────────────────────────────────
    # AFM20 (AIFM EEA Flag) is derivable from AFM17 (AIFM jurisdiction).
    # Q19  (AIF EEA Flag)  is derivable from Q21 (AIF domicile) on AIF reports.
    # The XML extractor doesn't always emit these (e.g. FCA format), so fill
    # them in here and clear the stale "empty mandatory" validation error.
    def _clear_validation_simple(_fr):
        _fr.validation = FieldValidationResponse(
            status="PASS", findings=[], rule_id="", message="",
            fix_suggestion="", severity="",
        )
        validation_map.pop(_fr.field_id, None)

    # Build a quick (field_id → field_response) lookup for this report
    _field_lookup: dict[str, ReportFieldResponse] = {}
    for _sec in sections.values():
        for _fr in _sec:
            _field_lookup[_fr.field_id] = _fr

    if report_type == "AIFM":
        jurisdiction_fr = _field_lookup.get("17")
        eea_fr = _field_lookup.get("20")
        if eea_fr and (eea_fr.value is None or str(eea_fr.value).strip() == ""):
            derived = _derive_eea_flag(jurisdiction_fr.value if jurisdiction_fr else None)
            eea_fr.value = derived
            eea_fr.source = "Derived from AIFM jurisdiction"
            eea_fr.priority = "DERIVED"
            _clear_validation_simple(eea_fr)

    if report_type == "AIF":
        # AIF domicile lives at Q21 in the AIF schema; Q19 is the flag.
        domicile_fr = _field_lookup.get("21")
        eea_fr = _field_lookup.get("19")
        if eea_fr and (eea_fr.value is None or str(eea_fr.value).strip() == ""):
            derived = _derive_eea_flag(domicile_fr.value if domicile_fr else None)
            eea_fr.value = derived
            eea_fr.source = "Derived from AIF domicile"
            eea_fr.priority = "DERIVED"
            _clear_validation_simple(eea_fr)

    return ReportDetailResponse(
        report_id=report.report_id,
        session_id=report.session_id,
        report_type=report.report_type,
        entity_name=report.entity_name,
        entity_index=report.entity_index,
        nca_codes=report.nca_codes,
        nca_national_codes=report.nca_national_codes,
        completeness=completeness,
        field_count=required_count,
        filled_count=required_count - error_count,
        sections=sections,
        groups=groups_data,
        group_columns=group_columns,
        group_obligations=group_obligations,
        empty_section_count=empty_section_count,
        validation_run=validation_run,
        no_reporting=is_no_reporting,
    )


def _load_nca_overrides(nca_code: str) -> list[dict]:
    """Load NCA-specific override rules from the NCA YAML file.

    Searches for the file matching the given NCA code (country code)
    in the NCA overrides directory.  Returns a list of rule dicts,
    or empty list if file not found.
    """
    import os, yaml, glob as _glob

    nca_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..",
        "Application", "regulation", "aifmd", "annex_iv", "nca_overrides",
    )
    nca_dir = os.path.normpath(nca_dir)

    # Search for file matching the country code (case-insensitive)
    cc = nca_code.lower()
    pattern = os.path.join(nca_dir, f"aifmd_nca_overrides_{cc}_*.yaml")
    matches = _glob.glob(pattern)
    if not matches:
        log.warning("No NCA override file found for %s (pattern: %s)", nca_code, pattern)
        return []

    try:
        with open(matches[0], "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        overrides = data.get("nca_overrides", {})
        return overrides.get("nca_rules", [])
    except Exception as e:
        log.error("Failed to load NCA overrides for %s: %s", nca_code, e)
        return []


def _apply_nca_overrides(
    sections: dict[str, list[ReportFieldResponse]],
    validation_map: dict[str, FieldValidationResponse],
    nca_code: str,
    report_type: str,
    fields_data: dict,
    registry=None,
) -> None:
    """Apply NCA-specific overrides to field responses in-place.

    For each NCA override rule that applies to the given report_type:
    - Update nca_deviations with the NCA-specific values
    - If the NCA has a different format/validation_rules, run NCA validation
      and add findings to the field's validation
    - Override technical_guidance with NCA-specific guidance
    """
    import re

    rules = _load_nca_overrides(nca_code)
    if not rules:
        return

    # Build a flat lookup: field_id → field_response
    field_map: dict[str, ReportFieldResponse] = {}
    for section_fields in sections.values():
        for fr in section_fields:
            field_map[fr.field_id] = fr

    for rule in rules:
        # Check if rule applies to this report type
        rule_report_type = rule.get("report_type", "")
        if rule_report_type not in (report_type, f"AIF+AIFM", "AIF+AIFM"):
            if rule_report_type != report_type:
                continue

        fid = str(rule.get("field_id", ""))
        fr = field_map.get(fid)
        if not fr:
            continue  # field not in current view

        nca_key = nca_code.upper()

        # Store NCA deviation info
        fr.nca_deviations[nca_key] = {
            "rule_id": rule.get("rule_id", ""),
            "format": rule.get("format", ""),
            "technical_guidance": rule.get("technical_guidance", ""),
            "validation_rules": rule.get("validation_rules", ""),
            "severity": rule.get("severity", "HIGH"),
        }

        # Override technical_guidance with NCA-specific guidance
        nca_guidance = rule.get("technical_guidance", "")
        if nca_guidance:
            fr.technical_guidance = f"[NCA {nca_key}] {nca_guidance}"

        # Run NCA-specific validation.
        #
        # Skip the format regex check when the field is an enumerated value
        # (has `allowed_values_ref` at the base level, OR the override itself
        # supplies an `allowed_values` list/dict). In that case the base YAML
        # enum check already validated membership, and re-interpreting
        # `format: '1'` ("exactly 1 character") as a regex pattern would
        # spuriously reject every code except literal '1'.
        value = fields_data.get(fid, {}).get("value")
        override_allowed = rule.get("allowed_values")
        base_fdef = None
        if registry:
            base_fdef = (
                registry.aifm_field(fid) if report_type == "AIFM"
                else registry.aif_field(fid)
            )
        base_has_enum = bool(base_fdef and base_fdef.allowed_values_ref)

        nca_format = rule.get("format", "")
        format_ok = True

        if override_allowed is not None and value is not None and str(value).strip():
            # Override declares its own enum — validate membership.
            val_str = str(value).strip()
            if isinstance(override_allowed, dict):
                allowed_set = {str(k) for k in override_allowed.keys()}
            elif isinstance(override_allowed, (list, tuple, set)):
                allowed_set = {str(v) for v in override_allowed}
            else:
                allowed_set = set()
            if allowed_set and val_str not in allowed_set:
                format_ok = False
                nca_format = f"one of {sorted(allowed_set)}"
        elif nca_format and not base_has_enum and value is not None and str(value).strip():
            val_str = str(value).strip()
            try:
                if not re.fullmatch(nca_format, val_str):
                    format_ok = False
            except re.error:
                try:
                    if len(val_str) > int(nca_format):
                        format_ok = False
                except ValueError:
                    pass

        if nca_format or override_allowed is not None:
            if not format_ok:
                nca_finding = FieldValidationFinding(
                    rule_id=rule.get("rule_id", f"NCA-{nca_key}-{fid}"),
                    status="FAIL",
                    severity=rule.get("severity", "HIGH"),
                    message=f"NCA {nca_key}: value '{val_str}' does not match required format '{nca_format}'",
                    fix_suggestion=f"Value must match NCA format: {nca_format}",
                )

                # Update field validation
                if fid in validation_map:
                    existing = validation_map[fid]
                    existing.findings.append(nca_finding)
                    if nca_finding.status == "FAIL":
                        existing.status = "FAIL"
                        existing.rule_id = nca_finding.rule_id
                        existing.message = nca_finding.message
                        existing.fix_suggestion = nca_finding.fix_suggestion
                        existing.severity = nca_finding.severity
                else:
                    validation_map[fid] = FieldValidationResponse(
                        status="FAIL",
                        findings=[nca_finding],
                        rule_id=nca_finding.rule_id,
                        message=nca_finding.message,
                        fix_suggestion=nca_finding.fix_suggestion,
                        severity=nca_finding.severity,
                    )
                # Update the field's validation reference
                fr.validation = validation_map[fid]


def _sort_key(field_id: str) -> tuple:
    """Sort key: numeric fields first, then alpha."""
    try:
        return (0, int(field_id))
    except ValueError:
        return (1, 0)


def _generate_fix_suggestion(finding: dict, registry, report_type: str) -> str:
    """Generate a concrete fix suggestion for a validation failure."""
    rule_id = finding.get("rule_id", "")
    message = finding.get("message", "")
    field_path = finding.get("field_path", "")

    # Extract field_id from path
    fid = field_path.split(".")[-1] if field_path else ""

    fdef = None
    if registry and fid:
        fdef = registry.aifm_field(fid) if report_type == "AIFM" else registry.aif_field(fid)

    if fdef and fdef.format:
        return f"Expected format: {fdef.format}. {message}"
    if fdef and fdef.allowed_values_ref:
        return f"Must be one of the allowed values in '{fdef.allowed_values_ref}'. {message}"
    if "mandatory" in message.lower() or "required" in message.lower():
        return f"This field is required. Please provide a value."
    return message


@router.get("/session/{session_id}/source")
async def get_source_data(
    session_id: str,
    fund_index: int = Query(0),
    aggregate: bool = Query(False),
):
    """Get source canonical entities for editing.

    When ``aggregate=True`` (used for the AIFM manager view), positions,
    transactions, counterparties, and risk_measures are collected from
    **all** funds instead of just one.  This gives the manager-level
    overview across the full portfolio.
    """
    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    sc = session.source_canonical or {}
    manager = sc.get("manager", {})

    # Get AIF-level source data
    aifs = sc.get("aifs", [])

    # Entity keys relevant to the AIFM aggregate view
    aifm_aggregate_keys = {"positions", "transactions", "counterparties", "risk_measures"}

    entity_types = {
        "positions": "positions",
        "transactions": "transactions",
        "share_classes": "share_classes",
        "counterparties": "counterparties",
        "strategies": "strategies",
        "investors": "investors",
        "risk_measures": "risk_measures",
        "borrowing_sources": "borrowing_sources",
    }

    # Build a single AIF dict for per-fund view
    if fund_index < len(aifs):
        aif = aifs[fund_index]
    else:
        aif = {}

    entities = {}
    for key, label in entity_types.items():
        # Aggregate from ALL funds for AIFM-relevant entity types
        if aggregate and key in aifm_aggregate_keys:
            items = []
            for fund_idx, fund_data in enumerate(aifs):
                fund_name = fund_data.get("fund_static", {}).get("name", {})
                if isinstance(fund_name, dict):
                    fund_name = fund_name.get("value", f"Fund {fund_idx + 1}")
                elif not fund_name:
                    fund_name = f"Fund {fund_idx + 1}"
                for item in fund_data.get(key, []):
                    enriched = dict(item)
                    enriched["_fund"] = fund_name
                    items.append(enriched)
        else:
            items = aif.get(key, [])

        # Extract field names from items
        field_names = set()
        for item in items:
            field_names.update(item.keys())

        entities[key] = SourceEntityResponse(
            entity_type=key,
            items=[
                {fname: fv.get("value") if isinstance(fv, dict) else fv for fname, fv in item.items()}
                for item in items
            ],
            field_names=sorted(field_names),
        )

    return SourceDataResponse(
        manager={k: v.get("value") if isinstance(v, dict) else v for k, v in manager.items()},
        fund_static={k: v.get("value") if isinstance(v, dict) else v for k, v in aif.get("fund_static", {}).items()},
        fund_dynamic={k: v.get("value") if isinstance(v, dict) else v for k, v in aif.get("fund_dynamic", {}).items()},
        entities=entities,
    )


@router.put("/session/{session_id}/field")
async def edit_field(session_id: str, req: FieldEditRequest):
    """Edit a report-level entity field value.

    The frontend MUST send report_type ("AIFM" or "AIF") and fund_index
    so the edit targets the correct report.  This fixes the old behaviour
    where every edit silently went to AIFM index 0.
    """
    store = get_store()
    classification = get_field_classification()
    # Use namespaced key to avoid AIF/AIFM field ID collisions (e.g., field 33)
    cat = classification.get(f"{req.report_type}.{req.field_id}", {}).get("category", "report")

    if cat == "composite":
        raise HTTPException(
            status_code=400,
            detail="Composite fields cannot be edited directly. Edit the source data instead.",
        )

    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Use report_type and fund_index from the request (sent by frontend)
    report_type = req.report_type  # "AIFM" or "AIF"
    fund_index = req.fund_index    # 0 for AIFM, 0-N for AIF

    report = store.get_report_by_type_and_index(session_id, report_type, fund_index)
    if report is None:
        raise HTTPException(status_code=404, detail=f"{report_type} report index {fund_index} not found")

    # Record old value
    old_value = report.fields_json.get(req.field_id, {}).get("value")

    # Update field
    from datetime import datetime, timezone
    _now = datetime.now(timezone.utc)
    report.fields_json[req.field_id] = {
        "value": req.value,
        "source": "client_review",
        "priority": "MANUALLY_OVERRIDDEN",
        "confidence": 1.0,
        "timestamp": _now.isoformat(),
        "note": req.note,
    }

    # Field 3 (CreationDateAndTime) must reflect the most recent save.
    # Format: 4(n)-2(n)-2(n)T2(n):2(n):2(n) — no timezone suffix.
    if req.field_id != "3":
        _creation_ts = _now.strftime("%Y-%m-%dT%H:%M:%S")
        report.fields_json["3"] = {
            "value": _creation_ts,
            "source": "system",
            "priority": "SYSTEM",
            "confidence": 1.0,
            "timestamp": _now.isoformat(),
            "note": "Auto-updated on save",
        }

    report.filled_count = len([v for v in report.fields_json.values() if v.get("value") is not None])
    report.completeness = round(100.0 * report.filled_count / max(report.field_count, 1), 1)
    store.save_report(report)

    # Log edit
    edit = ReviewEdit(
        session_id=session_id,
        report_id=report.report_id,
        edit_type="field",
        target=req.field_id,
        old_value=old_value,
        new_value=req.value,
        cascaded_fields=[],
    )
    edit_id = store.log_edit(edit)

    return EditResultResponse(
        edit_id=edit_id,
        updated_fields=[req.field_id],
        field_snapshots={req.field_id: {"old": old_value, "new": req.value}},
    )


@router.put("/session/{session_id}/group")
async def edit_group_cell(session_id: str, req: GroupCellEditRequest):
    """Edit a single cell in a repeating group table.

    Updates groups_json[group_name][row_index][column_id].
    If row_index == 0 and column_id is a numeric field_id, also
    updates fields_json[column_id] to keep both stores in sync.
    """
    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    report = store.get_report_by_type_and_index(session_id, req.report_type, req.fund_index)
    if report is None:
        raise HTTPException(status_code=404, detail=f"{req.report_type} report index {req.fund_index} not found")

    groups = report.groups_json or {}

    # ── Synthetic group handling ───────────────────────────────────────
    # nav_geographical_focus, aum_geographical_focus, and monthly_data are
    # built on-the-fly from scalar fields in fields_json. They don't exist
    # in groups_json, so edits must be mapped back to the underlying field.
    _SYNTHETIC_GEO = {
        "nav_geographical_focus": {
            "field_ids": [str(i) for i in range(78, 86)],
            "value_col": "nav_pct",
        },
        "aum_geographical_focus": {
            "field_ids": [str(i) for i in range(86, 94)],
            "value_col": "aum_pct",
        },
    }
    _MONTHLY_METRICS = {
        "gross_return": 219, "net_return": 231, "nav_change": 243,
        "subscriptions": 255, "redemptions": 267,
    }

    # Groups derived from source data — reject edits with a clear message
    _DERIVED_GROUPS = {
        "main_instruments", "principal_exposures", "portfolio_concentrations",
        "asset_type_exposures", "currency_exposures",
        "nav_geographical_focus", "aum_geographical_focus",
        "asset_type_turnovers", "aif_principal_markets",
        "investor_groups", "strategies", "market_risk_measures",
        "monthly_data",
        # AIFM groups (aggregated across all AIFs)
        "aifm_principal_markets", "aifm_principal_instruments",
    }
    if req.group_name in _DERIVED_GROUPS:
        raise HTTPException(
            status_code=400,
            detail=f"Group '{req.group_name}' is derived from source data and cannot be edited directly. Edit the underlying source records instead.",
        )

    # ── Regular (non-synthetic) group edit ─────────────────────────────
    if req.group_name not in groups:
        raise HTTPException(status_code=404, detail=f"Group '{req.group_name}' not found")

    rows = groups[req.group_name]
    if req.row_index < 0 or req.row_index >= len(rows):
        raise HTTPException(status_code=400, detail=f"Row index {req.row_index} out of range (0..{len(rows)-1})")

    old_value = rows[req.row_index].get(req.column_id)
    rows[req.row_index][req.column_id] = req.value
    report.groups_json = groups

    # Sync to fields_json for row 0 (first item is also stored as scalar)
    if req.row_index == 0:
        try:
            int(req.column_id)  # Only sync numeric field IDs
            from datetime import datetime, timezone
            report.fields_json[req.column_id] = {
                "value": req.value,
                "source": "client_review",
                "priority": "MANUALLY_OVERRIDDEN",
                "confidence": 1.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": req.note,
            }
        except ValueError:
            pass  # Synthetic columns (region, month) — no field_json sync

    # Always refresh field 3 (CreationDateAndTime) on any save
    from datetime import datetime as _dt2, timezone as _tz2
    _now2 = _dt2.now(_tz2.utc)
    report.fields_json["3"] = {
        "value": _now2.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "system",
        "priority": "SYSTEM",
        "confidence": 1.0,
        "timestamp": _now2.isoformat(),
        "note": "Auto-updated on save",
    }

    store.save_report(report)

    edit = ReviewEdit(
        session_id=session_id,
        report_id=report.report_id,
        edit_type="group",
        target=f"{req.group_name}[{req.row_index}].{req.column_id}",
        old_value=old_value,
        new_value=req.value,
        cascaded_fields=[],
    )
    edit_id = store.log_edit(edit)

    return EditResultResponse(
        edit_id=edit_id,
        updated_fields=[f"{req.group_name}[{req.row_index}].{req.column_id}"],
        field_snapshots={req.column_id: {"old": old_value, "new": req.value}},
    )


@router.put("/session/{session_id}/source/{entity_type}/{index}")
async def edit_source_entity(
    session_id: str,
    entity_type: str,
    index: int,
    req: SourceEntityEditRequest,
):
    """Edit a source entity field (e.g. position market_value). Triggers re-projection."""
    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    sc = session.source_canonical or {}
    fund_index = req.fund_index if hasattr(req, "fund_index") else 0

    # Determine where the entity lives
    if entity_type in ("manager",):
        # Manager-level entity
        entity_data = sc.get("manager", {})
        old_fv = entity_data.get(req.field, {})
        old_value = old_fv.get("value") if isinstance(old_fv, dict) else old_fv
        from datetime import datetime, timezone
        entity_data[req.field] = {
            "value": req.value,
            "source": "client_review",
            "priority": "MANUALLY_OVERRIDDEN",
            "confidence": 1.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": req.note,
        }
    elif entity_type in ("fund_static", "fund_dynamic"):
        # Fund-level scalar entity
        aifs = sc.get("aifs", [])
        if fund_index >= len(aifs):
            raise HTTPException(status_code=404, detail="Fund index out of range")
        aif = aifs[fund_index]
        entity_data = aif.get(entity_type, {})
        old_fv = entity_data.get(req.field, {})
        old_value = old_fv.get("value") if isinstance(old_fv, dict) else old_fv
        from datetime import datetime, timezone
        entity_data[req.field] = {
            "value": req.value,
            "source": "client_review",
            "priority": "MANUALLY_OVERRIDDEN",
            "confidence": 1.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": req.note,
        }
    else:
        # Collection entity (positions, transactions, etc.)
        aifs = sc.get("aifs", [])
        if not aifs:
            raise HTTPException(status_code=404, detail="No fund data in source canonical")
        aif = aifs[fund_index]
        collection = aif.get(entity_type, [])
        if index >= len(collection):
            raise HTTPException(status_code=404, detail=f"{entity_type}[{index}] not found")
        item = collection[index]
        old_fv = item.get(req.field, {})
        old_value = old_fv.get("value") if isinstance(old_fv, dict) else old_fv
        from datetime import datetime, timezone
        item[req.field] = {
            "value": req.value,
            "source": "client_review",
            "priority": "MANUALLY_OVERRIDDEN",
            "confidence": 1.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": req.note,
        }

    # Save updated source canonical
    session.source_canonical = sc
    store.save_session(session)

    # --- CASCADE: re-project affected report fields ---
    cascaded_fields = []
    try:
        from canonical.dependency_graph import (
            find_affected_report_fields,
            find_affected_by_collection_edit,
            reproject_entity_fields,
        )

        # Find which report fields are affected
        if entity_type in ("manager", "fund_static", "fund_dynamic"):
            affected = find_affected_report_fields(entity_type, req.field)
        else:
            affected = find_affected_by_collection_edit(entity_type)

        # Re-project entity fields for each affected report type
        for report_type in ("AIFM", "AIF"):
            report = store.get_report_by_type_and_index(
                session_id, report_type,
                0 if report_type == "AIFM" else fund_index,
            )
            if report is None:
                continue

            updated_fields, changed = reproject_entity_fields(
                sc, report.fields_json, report_type, fund_index,
            )
            if changed:
                report.fields_json = updated_fields
                report.filled_count = len([
                    v for v in report.fields_json.values()
                    if isinstance(v, dict) and v.get("value") is not None
                ])
                report.completeness = round(
                    100.0 * report.filled_count / max(report.field_count, 1), 1,
                )
                store.save_report(report)
                cascaded_fields.extend(
                    f"{report_type}.{fid}" for fid in changed
                )

    except Exception as e:
        log.warning("Cascade re-projection failed (non-fatal): %s", e)

    # Log edit
    edit = ReviewEdit(
        session_id=session_id,
        edit_type="source_entity",
        target=f"{entity_type}.{index}.{req.field}",
        old_value=old_value,
        new_value=req.value,
        cascaded_fields=cascaded_fields,
    )
    edit_id = store.log_edit(edit)

    # Build field snapshots including cascaded changes
    snapshots = {f"{entity_type}.{index}.{req.field}": {"old": old_value, "new": req.value}}
    for cf in cascaded_fields:
        snapshots[cf] = {"cascaded": True}

    return EditResultResponse(
        edit_id=edit_id,
        updated_fields=cascaded_fields,
        field_snapshots=snapshots,
    )


@router.post("/session/{session_id}/source/{entity_type}")
async def add_source_entity(
    session_id: str,
    entity_type: str,
    req: SourceEntityAddRequest,
):
    """Add a new row to a source entity collection (positions, transactions, etc.)."""
    print(f"[Eagle] POST add_source_entity called: session={session_id}, entity={entity_type}, req={req}")
    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    sc = session.source_canonical
    if sc is None:
        sc = {}
        session.source_canonical = sc

    fund_index = req.fund_index

    aifs = sc.get("aifs", [])
    if not aifs:
        # Initialise a minimal aifs list so we can store data
        aifs = [{}]
        sc["aifs"] = aifs
    if fund_index >= len(aifs):
        raise HTTPException(status_code=404, detail="Fund index out of range")

    aif = aifs[fund_index]
    collection = aif.get(entity_type)
    if collection is None:
        collection = []
        aif[entity_type] = collection

    # Build new item — copy field structure from first existing item if possible
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    new_item: dict = {}
    if collection:
        # Use field names from the first existing item as template
        for field_name in collection[0]:
            if field_name.startswith("_"):
                continue  # skip internal fields like _fund
            val = req.values.get(field_name, "")
            new_item[field_name] = {
                "value": val,
                "source": "client_review",
                "priority": "MANUALLY_OVERRIDDEN",
                "confidence": 1.0,
                "timestamp": ts,
            }
    else:
        # No template — just use whatever was provided
        for field_name, value in req.values.items():
            new_item[field_name] = {
                "value": value,
                "source": "client_review",
                "priority": "MANUALLY_OVERRIDDEN",
                "confidence": 1.0,
                "timestamp": ts,
            }

    collection.append(new_item)

    session.source_canonical = sc
    store.save_session(session)

    return {"status": "ok", "new_index": len(collection) - 1, "total": len(collection)}


@router.delete("/session/{session_id}/source/{entity_type}/{index}")
async def delete_source_entity(
    session_id: str,
    entity_type: str,
    index: int,
    fund_index: int = Query(0),
):
    """Delete a row from a source entity collection."""
    print(f"[Eagle] DELETE delete_source_entity called: session={session_id}, entity={entity_type}, index={index}, fund_index={fund_index}")
    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    sc = session.source_canonical or {}

    aifs = sc.get("aifs", [])
    if not aifs:
        raise HTTPException(status_code=404, detail="No fund data in source canonical")
    if fund_index >= len(aifs):
        raise HTTPException(status_code=404, detail="Fund index out of range")

    aif = aifs[fund_index]
    collection = aif.get(entity_type, [])
    if index < 0 or index >= len(collection):
        raise HTTPException(status_code=404, detail=f"{entity_type}[{index}] not found")

    collection.pop(index)
    aif[entity_type] = collection

    session.source_canonical = sc
    store.save_session(session)

    return {"status": "ok", "deleted_index": index, "total": len(collection)}


@router.get("/session/{session_id}/diff")
async def get_diff(session_id: str):
    """Get all edits since upload (for the diff panel)."""
    store = get_store()
    edits = store.get_edits(session_id)

    total_cascaded = sum(len(e.cascaded_fields) for e in edits)

    return {
        "total_direct_edits": len(edits),
        "total_cascaded": total_cascaded,
        "entries": [
            {
                "edit_id": e.edit_id,
                "edit_type": e.edit_type,
                "target": e.target,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "cascaded_fields": e.cascaded_fields,
                "edited_at": e.edited_at,
            }
            for e in edits
        ],
    }


@router.post("/session/{session_id}/undo")
async def undo_last_edit(session_id: str):
    """Undo the most recent edit (batch undo for cascaded changes)."""
    store = get_store()
    edit = store.delete_last_edit(session_id)
    if edit is None:
        raise HTTPException(status_code=404, detail="No edits to undo")

    # Revert the field value
    if edit.edit_type == "field" and edit.report_id:
        report = store.get_report(edit.report_id)
        if report and edit.target in report.fields_json:
            if edit.old_value is not None:
                report.fields_json[edit.target]["value"] = edit.old_value
            else:
                del report.fields_json[edit.target]
            report.filled_count = len([v for v in report.fields_json.values() if v.get("value") is not None])
            report.completeness = round(100.0 * report.filled_count / max(report.field_count, 1), 1)
            store.save_report(report)

    return {"undone": True, "edit_id": edit.edit_id, "target": edit.target}
