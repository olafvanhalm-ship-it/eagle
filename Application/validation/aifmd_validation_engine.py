"""
AIFMD Pipeline Validation Engine
==================================
Programmatic entry point for validating generated XML files within the
Eagle pipeline. Wraps validate_aifmd_xml.py functions into a structured
API that returns machine-readable results (not console output).

This is the L3+L4 validation gate: it runs between XML generation (L6)
and delivery (L7), or can be used pre-packaging against canonical data.

Usage:
    from validation.aifmd_validation_engine import validate_pipeline_output

    results = validate_pipeline_output(
        xml_files=["AIFM_NL_A01234_20251231.xml", "AIF_NL_A56789_20251231.xml"],
        nca_code="NL",
    )

    if results.has_critical_failures:
        # Block submission
        ...
    for f in results.findings:
        print(f"{f.rule_id}: {f.status} — {f.message}")

Extracted as part of Phase 5 — wiring validation engine into pipeline.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

# ── Ensure validation module can be imported ────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_APP_ROOT = _SCRIPT_DIR.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# Import from the existing validator
from validate_aifmd_xml import (
    load_rules,
    load_nca_overrides,
    detect_report_type,
    extract_metadata,
    validate_xml,
    validate_xsd,
    validate_file_naming,
    DEFAULT_RULES_PATH,
)


# ── Result data model ──────────────────────────────────────────────────────

@dataclass
class ValidationFinding:
    """Single validation finding for pipeline consumption."""
    file_name: str
    rule_id: str
    status: str          # PASS, FAIL, MISSING, WARNING, N_A
    severity: str        # CRITICAL, HIGH, MEDIUM, LOW, INFO
    field_path: str      # XSD element path
    message: str
    nca_applied: bool = False
    nca_error_code: str = ""


@dataclass
class XsdFinding:
    """Single XSD validation finding."""
    file_name: str
    line: int
    message: str


@dataclass
class FileNamingFinding:
    """Single file naming / packaging finding."""
    file_name: str
    check: str
    status: str          # PASS, FAIL, WARNING
    message: str


@dataclass
class FileValidationResult:
    """Validation result for a single XML file."""
    file_path: str
    report_type: str     # AIFM or AIF
    nca_code: str
    xsd_valid: bool
    xsd_source: str      # Which schema was used
    xsd_findings: list[XsdFinding] = field(default_factory=list)
    dqf_findings: list[ValidationFinding] = field(default_factory=list)
    file_findings: list[FileNamingFinding] = field(default_factory=list)

    @property
    def dqf_pass_count(self) -> int:
        return sum(1 for f in self.dqf_findings if f.status == "PASS")

    @property
    def dqf_fail_count(self) -> int:
        return sum(1 for f in self.dqf_findings if f.status == "FAIL")

    @property
    def dqf_missing_count(self) -> int:
        return sum(1 for f in self.dqf_findings if f.status == "MISSING")

    @property
    def dqf_warning_count(self) -> int:
        return sum(1 for f in self.dqf_findings if f.status == "WARNING")

    @property
    def has_critical_failures(self) -> bool:
        """True if any FAIL finding has CRITICAL or HIGH severity."""
        return any(
            f.status == "FAIL" and f.severity in ("CRITICAL", "HIGH")
            for f in self.dqf_findings
        )


@dataclass
class PipelineValidationResult:
    """Aggregated validation result across all XML files in a pipeline run."""
    file_results: list[FileValidationResult] = field(default_factory=list)
    nca_code: str = ""
    rules_path: str = ""
    rules_integrity: str = ""  # VERIFIED, UNVERIFIED, FIRST_RUN

    @property
    def total_files(self) -> int:
        return len(self.file_results)

    @property
    def xsd_valid_count(self) -> int:
        return sum(1 for r in self.file_results if r.xsd_valid)

    @property
    def xsd_invalid_count(self) -> int:
        return sum(1 for r in self.file_results if not r.xsd_valid)

    @property
    def total_dqf_pass(self) -> int:
        return sum(r.dqf_pass_count for r in self.file_results)

    @property
    def total_dqf_fail(self) -> int:
        return sum(r.dqf_fail_count for r in self.file_results)

    @property
    def has_critical_failures(self) -> bool:
        """True if any file has critical failures — blocks submission."""
        return any(r.has_critical_failures for r in self.file_results)

    @property
    def all_findings(self) -> list[ValidationFinding]:
        """Flat list of all DQF findings across all files."""
        return [f for r in self.file_results for f in r.dqf_findings]

    def summary_line(self) -> str:
        """One-line summary suitable for logging."""
        return (
            f"XSD {self.xsd_valid_count} valid, {self.xsd_invalid_count} invalid | "
            f"DQF {self.total_dqf_pass} pass, {self.total_dqf_fail} fail"
        )


# ── Main validation entry point ────────────────────────────────────────────

def validate_pipeline_output(
    xml_files: list[str | Path],
    nca_code: str = "",
    rules_path: Optional[str | Path] = None,
) -> PipelineValidationResult:
    """Validate a set of generated XML files as a pipeline step.

    This is the programmatic API for L3+L4 validation. It loads rules once,
    auto-detects NCA from the first file if not specified, and validates
    all files against the base ESMA rules + NCA overrides.

    Args:
        xml_files: List of XML file paths to validate.
        nca_code: NCA country code (e.g., "NL", "DE", "GB"). Auto-detected
            from XML if omitted.
        rules_path: Path to base rules YAML. Uses default if omitted.

    Returns:
        PipelineValidationResult with structured per-file and aggregate results.
    """
    rp = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
    if not rp.exists():
        log.error("Rules file not found: %s", rp)
        return PipelineValidationResult(rules_path=str(rp))

    # Load rules once
    base = load_rules(rp)
    aif_rules = base.get("aif_rules", [])
    aifm_rules = base.get("aifm_rules", [])
    ref_tables = base.get("reference_tables", {})

    detected_nca = nca_code
    nca_overrides_cache: Optional[dict] = None

    result = PipelineValidationResult(
        nca_code=nca_code,
        rules_path=str(rp),
    )

    for xml_file in xml_files:
        fp = Path(xml_file)
        if not fp.exists():
            log.warning("Skipping (not found): %s", fp)
            continue

        # Parse XML
        try:
            root = ET.parse(str(fp)).getroot()
        except ET.ParseError as e:
            log.error("XML parse error in %s: %s", fp.name, e)
            result.file_results.append(FileValidationResult(
                file_path=str(fp),
                report_type="UNKNOWN",
                nca_code=detected_nca,
                xsd_valid=False,
                xsd_source="PARSE_ERROR",
            ))
            continue

        rtype = detect_report_type(root)
        meta = extract_metadata(root, rtype)
        meta["file_name"] = fp.name
        meta["_report_type"] = rtype

        # Auto-detect NCA
        if not detected_nca:
            detected_nca = meta.get("ReportingMemberState", "")
            result.nca_code = detected_nca

        # Content type
        ct_str = meta.get("AIFContentType") or meta.get("AIFMContentType") or "1"
        try:
            ct = int(ct_str)
        except ValueError:
            ct = 1

        # ── File naming validation ─────────────────────────────────────
        raw_file_findings = validate_file_naming(fp, rtype, detected_nca, meta)
        file_findings = [
            FileNamingFinding(
                file_name=fp.name,
                check=ff.check,
                status=ff.status,
                message=ff.message,
            )
            for ff in raw_file_findings
        ]

        # ── XSD validation ─────────────────────────────────────────────
        raw_xsd_findings, xsd_source = validate_xsd(fp, rtype)
        xsd_valid = len(raw_xsd_findings) == 0 and not xsd_source.startswith("SKIPPED")
        xsd_findings = [
            XsdFinding(file_name=fp.name, line=xf.line, message=xf.message)
            for xf in raw_xsd_findings
        ]

        # ── DQF validation ─────────────────────────────────────────────
        rules = aifm_rules if rtype == "AIFM" else aif_rules

        # Load NCA overrides (once per NCA)
        if nca_overrides_cache is None and detected_nca:
            nca_overrides_cache = load_nca_overrides(detected_nca)
        nca_ovr = nca_overrides_cache or {}

        raw_findings, _ = validate_xml(
            fp, rules, ref_tables, nca_ovr, rtype, ct, root, meta,
        )

        dqf_findings = [
            ValidationFinding(
                file_name=fp.name,
                rule_id=f.rule_id,
                status=f.status,
                severity=getattr(f, "severity", "MEDIUM"),
                field_path=getattr(f, "xsd_element", ""),
                message=getattr(f, "message", ""),
                nca_applied=getattr(f, "nca_applied", False),
                nca_error_code=getattr(f, "nca_error_code", ""),
            )
            for f in raw_findings
        ]

        result.file_results.append(FileValidationResult(
            file_path=str(fp),
            report_type=rtype,
            nca_code=detected_nca,
            xsd_valid=xsd_valid,
            xsd_source=xsd_source,
            xsd_findings=xsd_findings,
            dqf_findings=dqf_findings,
            file_findings=file_findings,
        ))

    return result
