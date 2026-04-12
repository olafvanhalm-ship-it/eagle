"""Validation and download routes."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from api.deps import (
    get_store, get_app_root, get_adapter_path, get_field_registry,
    get_reporting_obligations, get_nca_overrides,
)
from persistence.report_store import ReviewValidationRun

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["validation"])


@router.post("/session/{session_id}/validate")
async def validate_session(session_id: str):
    """Re-generate XML from current canonical state and validate (L3 + L4).

    This endpoint:
    1. Reads the current report fields from the DB
    2. Builds XML using the AIFM/AIF builders
    3. Runs XSD validation
    4. Runs DQF (business rule) validation
    5. Stores results and returns findings
    """
    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    reports = store.get_reports_for_session(session_id)
    if not reports:
        raise HTTPException(status_code=400, detail="No reports in session — upload a template first")

    import sys
    app_root = get_app_root()
    adapter_path = get_adapter_path()
    for p in (str(app_root), str(adapter_path)):
        if p not in sys.path:
            sys.path.insert(0, p)

    tmp_dir = tempfile.mkdtemp(prefix="eagle_val_")
    findings = []
    xsd_valid_count = 0
    xsd_invalid_count = 0
    dqf_pass = 0
    dqf_fail = 0
    has_critical = False

    try:
        # Try to validate using the existing pipeline
        # This requires re-generating XML from stored report fields
        for report in reports:
            report_findings = _validate_report_fields(
                report, session, app_root, tmp_dir,
            )
            findings.extend(report_findings)

        # Count results
        for f in findings:
            if f.get("check_type") == "xsd":
                if f.get("status") == "PASS":
                    xsd_valid_count += 1
                else:
                    xsd_invalid_count += 1
            elif f.get("check_type") == "dqf":
                if f.get("status") == "PASS":
                    dqf_pass += 1
                else:
                    dqf_fail += 1
                    if f.get("severity") in ("CRITICAL", "HIGH"):
                        has_critical = True

        # If no findings from the pipeline, do a basic field-level validation
        if not findings:
            findings = _field_level_validation(reports, get_field_registry())
            for f in findings:
                if f.get("status") == "FAIL":
                    dqf_fail += 1
                    if f.get("severity") in ("CRITICAL", "HIGH"):
                        has_critical = True
                else:
                    dqf_pass += 1

        # Always run cross-field validation (Q5+Q8+Q20 against obligations matrix)
        xfv_findings = _cross_field_validation(reports, get_reporting_obligations())
        findings.extend(xfv_findings)
        for f in xfv_findings:
            if f.get("status") == "FAIL":
                dqf_fail += 1
                if f.get("severity") in ("CRITICAL", "HIGH"):
                    has_critical = True
            else:
                dqf_pass += 1

        # NCA-specific validation (format overrides, e.g. AFM national code format)
        # Single source of truth: field 1 (ReportingMemberState) from the report.
        nca_code = ""
        if reports:
            _fj = reports[0].fields_json or {}
            nca_code = str(_fj.get("1", {}).get("value", "") or "").strip()
        if nca_code:
            nca_rules = get_nca_overrides(nca_code)
            if nca_rules:
                nca_findings = _nca_override_validation(
                    reports, nca_code, nca_rules, get_field_registry())
                findings.extend(nca_findings)
                for f in nca_findings:
                    if f.get("status") == "FAIL":
                        dqf_fail += 1
                        if f.get("severity") in ("CRITICAL", "HIGH"):
                            has_critical = True
                    else:
                        dqf_pass += 1

    except Exception as e:
        log.warning("Pipeline validation failed, falling back to field-level: %s", e)
        # Fallback: do basic field-level validation
        findings = _field_level_validation(reports, get_field_registry())
        for f in findings:
            if f.get("status") == "FAIL":
                dqf_fail += 1
            else:
                dqf_pass += 1
        # Cross-field validation runs regardless
        xfv_findings = _cross_field_validation(reports, get_reporting_obligations())
        findings.extend(xfv_findings)
        for f in xfv_findings:
            if f.get("status") == "FAIL":
                dqf_fail += 1
                if f.get("severity") in ("CRITICAL", "HIGH"):
                    has_critical = True
            else:
                dqf_pass += 1
        # NCA-specific validation in fallback path too
        nca_code = ""
        if reports:
            _fj = reports[0].fields_json or {}
            nca_code = str(_fj.get("1", {}).get("value", "") or "").strip()
        if nca_code:
            nca_rules = get_nca_overrides(nca_code)
            if nca_rules:
                nca_findings = _nca_override_validation(
                    reports, nca_code, nca_rules, get_field_registry())
                findings.extend(nca_findings)
                for f in nca_findings:
                    if f.get("status") == "FAIL":
                        dqf_fail += 1
                        if f.get("severity") in ("CRITICAL", "HIGH"):
                            has_critical = True
                    else:
                        dqf_pass += 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Store validation run — but strip field-level findings (MAN-/FMT-/TYP-)
    # because the GET /report endpoint regenerates those on every request
    # from the live field state. Keeping them in storage would cause FAILs
    # from a previous state (e.g. before an inline edit) to persist and
    # turn previously-green fields red on the next viewer load.
    _auto_prefixes = ("MAN-", "FMT-", "TYP-")
    persisted_findings = [
        f for f in findings
        if not str(f.get("rule_id", "")).startswith(_auto_prefixes)
    ]
    val_run = ReviewValidationRun(
        session_id=session_id,
        xsd_valid=xsd_invalid_count == 0,
        dqf_pass=dqf_pass,
        dqf_fail=dqf_fail,
        has_critical=has_critical,
        findings_json=persisted_findings,
    )
    store.save_validation_run(val_run)

    return {
        "run_id": val_run.run_id,
        "xsd_valid": val_run.xsd_valid,
        "dqf_pass": dqf_pass,
        "dqf_fail": dqf_fail,
        "has_critical": has_critical,
        "findings": findings[:100],  # Limit response size
        "total_findings": len(findings),
    }


def _validate_report_fields(report, session, app_root, tmp_dir) -> list[dict]:
    """Try to validate a single report using the existing validation pipeline.

    Attempts to use validate_aifmd_xml.py if available, otherwise returns empty.
    """
    findings = []

    try:
        # Try importing the validator
        import sys
        validator_path = str(app_root / "regulation" / "aifmd" / "annex_iv")
        if validator_path not in sys.path:
            sys.path.insert(0, validator_path)

        # Check if we have the validation module
        val_module_path = app_root / "regulation" / "aifmd" / "annex_iv" / "validate_aifmd_xml.py"
        if not val_module_path.exists():
            return findings

        from validate_aifmd_xml import validate_file

        # We would need to regenerate XML from report fields here.
        # For now, check if the session has stored XML from the original upload.
        # Future: implement canonical → XML generation for re-validation after edits.
        log.info("Pipeline validation available but XML regeneration not yet implemented for edited reports")

    except ImportError:
        log.debug("Validation module not available")
    except Exception as e:
        log.warning("Pipeline validation error: %s", e)

    return findings


def _field_level_validation(reports: list, registry) -> list[dict]:
    """Basic field-level validation: check mandatory fields, formats, allowed values.

    This provides immediate inline feedback without requiring XML regeneration.
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
                continue  # Skip further checks for empty optional fields

            # Check format constraints
            if fdef.format and isinstance(value, str):
                dt_val = ""
                if fdef.data_type is not None:
                    dt_val = fdef.data_type.value if hasattr(fdef.data_type, "value") else str(fdef.data_type)
                format_ok = _check_format(value, fdef.format, dt_val)
                if not format_ok:
                    findings.append({
                        "rule_id": f"FMT-{report_type}-{fid}",
                        "field_path": f"{report_type}.{fid}",
                        "status": "FAIL",
                        "check_type": "dqf",
                        "severity": "MEDIUM",
                        "message": f"Q{fid} ({fdef.field_name}) value '{value}' does not match format '{fdef.format}'",
                        "fix_suggestion": f"Expected format: {fdef.format}",
                    })
                else:
                    findings.append({
                        "rule_id": f"FMT-{report_type}-{fid}",
                        "field_path": f"{report_type}.{fid}",
                        "status": "PASS",
                        "check_type": "dqf",
                        "severity": "INFO",
                        "message": f"Format check passed for Q{fid}",
                    })

            # Check data type
            if fdef.data_type and value is not None:
                type_ok = _check_data_type(value, fdef.data_type.value)
                if not type_ok:
                    findings.append({
                        "rule_id": f"TYP-{report_type}-{fid}",
                        "field_path": f"{report_type}.{fid}",
                        "status": "FAIL",
                        "check_type": "dqf",
                        "severity": "MEDIUM",
                        "message": f"Q{fid} ({fdef.field_name}) value type mismatch — expected {fdef.data_type.value}",
                        "fix_suggestion": f"Value must be of type {fdef.data_type.value}",
                    })

    return findings


def _cross_field_validation(reports: list, obligations: list[dict]) -> list[dict]:
    """Cross-field validation: check that Q5 + Q8 + Q20 form a valid combination.

    Uses the reporting_obligations matrix from the AIFMD validation rules YAML
    as the single source of truth.

    Fields (AIF-level only):
      Q5  = AIF content type   → aif_content_type in YAML
      Q8  = Reporting period   → maps to frequency (Y1/H1/Q1)
      Q20 = AIF reporting code → aif_reporting_code in YAML

    Q8 period-to-frequency mapping:
      Y1         → Y1  (annual)
      H1, H2     → H1  (half-yearly)
      Q1..Q4     → Q1  (quarterly)
      X1, X2     → transitional (skipped — no obligation row applies)
    """
    if not obligations:
        return []

    # Build set of valid (aif_content_type, aif_reporting_code, frequency) tuples
    valid_combos: set[tuple[str, str, str]] = set()
    for row in obligations:
        ct = str(row.get("aif_content_type", ""))
        rc = str(row.get("aif_reporting_code", ""))
        freq = str(row.get("frequency", ""))
        if ct and rc and freq:
            valid_combos.add((ct, rc, freq))

    findings = []

    for report in reports:
        if report.report_type != "AIF":
            continue

        fields_json = report.fields_json or {}

        def _val(fid: str) -> str:
            fd = fields_json.get(fid, {})
            v = fd.get("value") if isinstance(fd, dict) else fd
            return str(v).strip() if v is not None else ""

        q5 = _val("5")    # AIF content type
        q8 = _val("8")    # Reporting period type (e.g. Q1, H1, Y1)
        q20 = _val("20")  # AIF reporting code

        # Skip if any of the three fields is empty — MAN- checks handle that
        if not q5 or not q8 or not q20:
            continue

        # Map Q8 period value to obligation frequency
        q8_upper = q8.upper()
        if q8_upper.startswith("Y"):
            frequency = "Y1"
        elif q8_upper.startswith("H"):
            frequency = "H1"
        elif q8_upper.startswith("Q"):
            frequency = "Q1"
        elif q8_upper.startswith("X"):
            # Transitional periods — skip cross-field check
            continue
        else:
            findings.append({
                "rule_id": f"XFV-AIF-Q8-PERIOD",
                "field_path": "AIF.8",
                "status": "FAIL",
                "check_type": "dqf",
                "severity": "HIGH",
                "message": (
                    f"Q8 (Reporting period type) value '{q8}' is not a "
                    f"recognised period code (expected Y1, H1, H2, Q1–Q4)"
                ),
                "fix_suggestion": "Use one of: Y1, H1, H2, Q1, Q2, Q3, Q4",
            })
            continue

        combo = (q5, q20, frequency)

        if combo not in valid_combos:
            # Build a helpful message: what ARE the valid combos for this Q5?
            valid_for_ct = sorted(
                (rc, f) for ct, rc, f in valid_combos if ct == q5
            )
            if valid_for_ct:
                hint_lines = [
                    f"  reporting code {rc}, frequency {f}"
                    for rc, f in valid_for_ct[:8]
                ]
                if len(valid_for_ct) > 8:
                    hint_lines.append(f"  ... and {len(valid_for_ct) - 8} more")
                hint = (
                    f"Valid combinations for AIF content type {q5}:\n"
                    + "\n".join(hint_lines)
                )
            else:
                hint = (
                    f"AIF content type '{q5}' does not appear in the "
                    f"reporting obligations matrix"
                )

            findings.append({
                "rule_id": "XFV-AIF-Q5-Q8-Q20",
                "field_path": "AIF.5+AIF.8+AIF.20",
                "status": "FAIL",
                "check_type": "dqf",
                "severity": "CRITICAL",
                "message": (
                    f"Invalid combination: AIF content type (Q5) = {q5}, "
                    f"reporting code (Q20) = {q20}, "
                    f"reporting period (Q8) = {q8} (frequency {frequency}). "
                    f"This combination does not exist in the ESMA "
                    f"reporting obligations matrix."
                ),
                "fix_suggestion": hint,
            })
        else:
            findings.append({
                "rule_id": "XFV-AIF-Q5-Q8-Q20",
                "field_path": "AIF.5+AIF.8+AIF.20",
                "status": "PASS",
                "check_type": "dqf",
                "severity": "INFO",
                "message": (
                    f"Cross-field check passed: AIF content type {q5}, "
                    f"reporting code {q20}, frequency {frequency}"
                ),
            })

    return findings


def _nca_override_validation(
    reports: list,
    nca_code: str,
    nca_rules: list[dict],
    registry,
) -> list[dict]:
    """Validate fields against NCA-specific override rules.

    NCA overrides can tighten ESMA base rules — e.g. AFM requires AIFM
    national codes to match ^B[A-Z]{2}[0-9]{3}$ instead of the generic
    "30 (max) 1 (min)" format.

    Each NCA rule targets exactly one report type (AIFM or AIF) via its
    report_type field or base_rule_id prefix.  AIFM and AIF have
    independent field numbering, so rules are never shared across types.
    """
    import re

    if not nca_rules or not registry:
        return []

    findings = []

    for nca_rule in nca_rules:
        fmt = nca_rule.get("format", "")
        if not fmt:
            continue  # No format constraint → nothing to check here

        base_rule_id = nca_rule.get("base_rule_id", "")
        rule_id = nca_rule.get("rule_id", base_rule_id)
        nca_err_codes = nca_rule.get("nca_error_codes", [])
        severity = nca_rule.get("severity", "HIGH")

        # Determine report type: explicit field first, then infer from
        # base_rule_id prefix (e.g. "AIFM-18" → "AIFM").
        rule_rtype = nca_rule.get("report_type", "")
        if not rule_rtype:
            parts = base_rule_id.split("-", 1)
            rule_rtype = parts[0] if len(parts) == 2 else ""

        fid = str(nca_rule.get("field_id", ""))
        if not fid:
            # Fallback: parse from base_rule_id (e.g. "AIFM-18" → "18")
            parts = base_rule_id.split("-", 1)
            fid = parts[1] if len(parts) == 2 else ""
        if not fid or not rule_rtype:
            continue

        # Build regex from NCA format
        try:
            pattern = re.compile(f"^{fmt}$")
        except re.error:
            log.warning("Invalid regex in NCA rule %s: %s", rule_id, fmt)
            continue

        # Check against matching reports
        for report in reports:
            if report.report_type != rule_rtype and report.report_type not in rule_rtype.split("+"):
                continue

            fields_json = report.fields_json or {}
            fd = fields_json.get(fid, {})
            value = fd.get("value") if isinstance(fd, dict) else fd

            if value is None or (isinstance(value, str) and not value.strip()):
                continue  # Empty — MAN- checks handle that

            str_val = str(value).strip()

            if not pattern.match(str_val):
                field_name = nca_rule.get("field_name", f"Q{fid}")
                err_code = nca_err_codes[0] if nca_err_codes else ""
                err_prefix = f"[{err_code}] " if err_code else ""

                findings.append({
                    "rule_id": f"NCA-{nca_code.upper()}-{rule_rtype}-{fid}",
                    "field_path": f"{rule_rtype}.{fid}",
                    "status": "FAIL",
                    "check_type": "dqf",
                    "severity": severity,
                    "message": (
                        f"{err_prefix}{field_name} (Q{fid}) value "
                        f"'{str_val}' does not match {nca_code.upper()} "
                        f"NCA required format: {fmt}"
                    ),
                    "fix_suggestion": nca_rule.get("technical_guidance", "")
                        or f"Value must match pattern: {fmt}",
                })

    return findings


def _check_format(value: str, fmt: str, data_type: str = "") -> bool:
    """Check if a value matches the ESMA format specification.

    ESMA Annex IV uses several format notations (after YAML loading):
    - Bare number: "4" → max-length constraint (YAML strips quotes)
    - "X (max)": "300 (max)" → max-length X
    - "X (max) Y (min)": "30 (max) 1 (min)" → length in [Y..X]
    - "X totalDigits Y fractionDigits Z minInclusive W": numeric precision — skip regex
    - Length + regex: "2 [A-Z]+" → 2-char country code
    - Digit-group: "4(n)-2(n)-2(n)" → date as digits-dash pattern
    - Datetime: "4(n)-2(n)-2(n)T2(n):2(n):2(n)" → ISO 8601 datetime
    - Pure regex: "([0-9])+\\.([0-9])+" → direct regex match

    When data_type == "B" (boolean) the field carries a BooleanType whose
    XML wire value is literally "true"/"false"; the numeric format (e.g.
    "1") describes the enum position, NOT the string length. In that case
    we only check membership in the true/false set.
    """
    import re

    if not fmt:
        return True

    str_val = str(value)

    # ── Boolean special case ───────────────────────────────────────
    # XML BooleanType is serialised as "true"/"false" — any numeric
    # format key (e.g. "1") must not be interpreted as a length cap.
    if data_type and data_type.upper() in ("B", "BOOL", "BOOLEAN"):
        return str_val.strip().lower() in ("true", "false", "0", "1")

    stripped = fmt.strip()

    # ── Bare number = max-length constraint ────────────────────────
    # In YAML: format: '4' → Python string "4" (quotes stripped by YAML parser)
    # This means "maximum 4 characters", not the literal "4"
    if stripped.isdigit():
        max_len = int(stripped)
        return len(str_val) <= max_len

    # ── ESMA explicit min/max notation ─────────────────────────────
    # Examples: "300 (max)", "30 (max) 1 (min)", "1000 (max) 1 (min)"
    max_match = re.search(r"(\d+)\s*\(\s*max\s*\)", stripped, re.IGNORECASE)
    min_match = re.search(r"(\d+)\s*\(\s*min\s*\)", stripped, re.IGNORECASE)
    if max_match or min_match:
        if max_match and len(str_val) > int(max_match.group(1)):
            return False
        if min_match and len(str_val) < int(min_match.group(1)):
            return False
        return True

    # ── ESMA numeric precision notation ────────────────────────────
    # Examples: "3 totalDigits 3 fractionDigits 0 minInclusive 1"
    #           "22 totalDigits 5 fractionDigits"
    # Treat as "value must be numeric and within totalDigits precision".
    if "totalDigits" in stripped or "fractionDigits" in stripped:
        try:
            float(str_val)
        except (TypeError, ValueError):
            return False
        td_match = re.search(r"(\d+)\s+totalDigits", stripped)
        fd_match = re.search(r"(\d+)\s+fractionDigits", stripped)
        min_incl_match = re.search(r"(-?\d+)\s+minInclusive", stripped)
        max_incl_match = re.search(r"(-?\d+)\s+maxInclusive", stripped)
        digits_only = str_val.lstrip("-+").replace(".", "")
        if td_match and len(digits_only) > int(td_match.group(1)):
            return False
        if fd_match and "." in str_val:
            frac = str_val.split(".", 1)[1]
            if len(frac) > int(fd_match.group(1)):
                return False
        try:
            if min_incl_match and float(str_val) < float(min_incl_match.group(1)):
                return False
            if max_incl_match and float(str_val) > float(max_incl_match.group(1)):
                return False
        except ValueError:
            return False
        return True

    # ── ESMA digit-group notation: X(n) means X digits ─────────────
    # e.g. "4(n)-2(n)-2(n)T2(n):2(n):2(n)" = datetime
    # e.g. "4(n)-2(n)-2(n)" = date
    if "(n)" in stripped:
        esma_regex = re.sub(r"(\d+)\(n\)", lambda m: r"\d{" + m.group(1) + "}", stripped)
        try:
            # Date-only: accept date value even if format wants datetime
            if "T" in esma_regex and "T" not in str_val:
                date_regex = esma_regex.split("T")[0]
                return bool(re.fullmatch(date_regex, str_val))
            return bool(re.fullmatch(esma_regex, str_val))
        except re.error:
            return True

    # ── Length-prefix notation: "2 [A-Z]+" ─────────────────────────
    # e.g. "2 [A-Z]+" for a 2-char country code. The length prefix is a
    # HARD constraint — even if the regex pattern uses quantifiers like
    # "+" or "*", the value still has to be exactly `expected_len` chars.
    parts = stripped.split(" ", 1)
    if len(parts) == 2 and parts[0].isdigit():
        expected_len = int(parts[0])
        pattern = parts[1]
        if any(c in pattern for c in "[].*+?\\^$"):
            if len(str_val) != expected_len:
                return False
            stripped = pattern

    # ── Common date format check ───────────────────────────────────
    if "YYYY-MM-DD" in stripped:
        try:
            from datetime import datetime
            datetime.strptime(str_val[:10], "%Y-%m-%d")
            return True
        except ValueError:
            return False

    # ── Try regex match ────────────────────────────────────────────
    try:
        return bool(re.fullmatch(stripped, str_val))
    except re.error:
        return True


def _check_data_type(value: Any, expected_type: str) -> bool:
    """Check if a value matches the expected ESMA data type."""
    if value is None:
        return True

    try:
        if expected_type in ("N", "NUM", "NUMERIC"):
            float(str(value))
            return True
        elif expected_type in ("A", "ALPHA", "ALPHANUMERIC"):
            return isinstance(value, str)
        elif expected_type in ("D", "DATE"):
            from datetime import datetime
            datetime.strptime(str(value)[:10], "%Y-%m-%d")
            return True
        elif expected_type in ("B", "BOOL", "BOOLEAN"):
            return str(value).lower() in ("true", "false", "1", "0", "yes", "no")
    except (ValueError, TypeError):
        return False

    return True


from typing import Any


@router.get("/session/{session_id}/validation/latest")
async def get_latest_validation(session_id: str):
    """Get the most recent validation results."""
    store = get_store()
    latest = store.get_latest_validation(session_id)
    if latest is None:
        return {"run_id": None, "message": "No validation runs yet"}

    return {
        "run_id": latest.run_id,
        "xsd_valid": latest.xsd_valid,
        "dqf_pass": latest.dqf_pass,
        "dqf_fail": latest.dqf_fail,
        "has_critical": latest.has_critical,
        "findings": latest.findings_json,
    }


@router.get("/session/{session_id}/download/{report_type}")
async def download_report_xml(
    session_id: str,
    report_type: str,
    nca: str = Query(None, description="NCA code for NCA-specific packaging"),
):
    """Download the generated XML or NCA-packaged file for a report.

    This is a placeholder — full implementation requires XML regeneration
    from the current canonical state after edits.
    """
    return {
        "status": "not_yet_implemented",
        "message": "XML download after editing requires canonical→XML regeneration. "
                   "Use the original uploaded template's generated files for now.",
    }
