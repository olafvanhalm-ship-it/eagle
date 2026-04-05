"""Session management routes — upload, retrieve, list sessions."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import traceback
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from api.deps import get_store, get_app_root, get_adapter_path
from api.models.responses import UploadResponse, SessionSummary, SessionDetail, ReportSummary
from persistence.report_store import (
    ReportStore, ReviewSession, ReviewReport, ReviewValidationRun,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["session"])


def _serialize_source_canonical(adapter) -> dict:
    """Extract source canonical data from MAdapter into serializable dict."""
    result = {
        "manager": {},
        "aifs": [],
    }

    # Manager static
    if hasattr(adapter, "source_canonical") and adapter.source_canonical:
        sc = adapter.source_canonical
        if hasattr(sc, "manager") and sc.manager:
            result["manager"] = sc.manager.to_dict()
        if hasattr(sc, "aifs") and sc.aifs:
            for aif in sc.aifs:
                aif_data = {
                    "fund_static": aif.fund_static.to_dict() if hasattr(aif, "fund_static") and aif.fund_static else {},
                    "fund_dynamic": aif.fund_dynamic.to_dict() if hasattr(aif, "fund_dynamic") and aif.fund_dynamic else {},
                    "positions": [p.to_dict() for p in (aif.positions if hasattr(aif, "positions") else [])],
                    "transactions": [t.to_dict() for t in (aif.transactions if hasattr(aif, "transactions") else [])],
                    "share_classes": [s.to_dict() for s in (aif.share_classes if hasattr(aif, "share_classes") else [])],
                    "counterparties": [c.to_dict() for c in (aif.counterparties if hasattr(aif, "counterparties") else [])],
                    "strategies": [s.to_dict() for s in (aif.strategies if hasattr(aif, "strategies") else [])],
                    "investors": [i.to_dict() for i in (aif.investors if hasattr(aif, "investors") else [])],
                    "risk_measures": [r.to_dict() for r in (aif.risk_measures if hasattr(aif, "risk_measures") else [])],
                    "borrowing_sources": [b.to_dict() for b in (aif.borrowing_sources if hasattr(aif, "borrowing_sources") else [])],
                }
                result["aifs"].append(aif_data)
    return result


def _serialize_report(report) -> dict:
    """Convert CanonicalReport to serializable dict for storage."""
    return report.to_dict() if hasattr(report, "to_dict") else {}


def _calc_completeness(
    report_type: str,
    filing_type: str,
    error_field_ids: set[str],
    fields_json: dict | None = None,
) -> float:
    """Calculate completeness as (required − errors) / required × 100.

    Completeness answers: "of the fields I MUST submit, how many are error-free?"
    - required = M fields + C fields in active sections
    - Only sections applicable to this content type count
    - A section is active if at least one field in it has data
    - errors   = required fields that have a DQF FAIL
    - CANC fields excluded for INIT filings
    """
    from api.deps import get_field_registry
    from canonical.aifmd_field_registry import FieldRegistry as _FR

    registry = get_field_registry()
    if registry is None:
        return 0.0

    all_fields = registry.aifm_fields() if report_type == "AIFM" else registry.aif_fields()
    fields_json = fields_json or {}

    # Get content type from field 5 (AIFContentType / AIFMContentType)
    ct_val = fields_json.get("5", {}).get("value", "2")
    try:
        content_type = int(ct_val)
    except (ValueError, TypeError):
        content_type = 2

    # Determine which sections are active (have at least one filled field)
    active_sections: set[str] = set()
    for fid, fdef in all_fields.items():
        if fid in fields_json:
            active_sections.add(fdef.section)

    # Count applicable required fields
    required_ids: set[str] = set()
    for fid, fdef in all_fields.items():
        if filing_type == "INIT" and fid.startswith("CANC-"):
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

    if not required_ids:
        return 100.0

    errors_on_required = required_ids & error_field_ids
    ok_count = len(required_ids) - len(errors_on_required)
    return round(100.0 * ok_count / len(required_ids), 1)


@router.post("/upload", response_model=UploadResponse)
async def upload_and_validate(file: UploadFile = File(...)):
    """Upload an Excel template, parse, persist to DB, and return session ID."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xls files are supported")

    store = get_store()
    tmp_dir = tempfile.mkdtemp(prefix="eagle_")

    try:
        # Save uploaded file
        tmp_path = Path(tmp_dir) / file.filename
        with open(tmp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Import and run adapter
        import sys
        adapter_path = get_adapter_path()
        if str(adapter_path) not in sys.path:
            sys.path.insert(0, str(adapter_path))
        app_root = get_app_root()
        if str(app_root) not in sys.path:
            sys.path.insert(0, str(app_root))

        from m_adapter import MAdapter
        adapter = MAdapter(str(tmp_path))

        # Extract metadata
        aifm_name = getattr(adapter, "aifm_name", "unknown")
        filing_type = getattr(adapter, "filing_type", "INIT")
        rms = getattr(adapter, "reporting_member_state", "unknown")
        num_aifs = len(adapter.aifs) if hasattr(adapter, "aifs") else 0
        template_type = getattr(adapter, "template_type", "FULL")

        # Archive previous sessions
        store.archive_active_sessions()

        # Create session
        session = ReviewSession(
            filename=file.filename,
            aifm_name=aifm_name,
            filing_type=filing_type,
            template_type=template_type,
            reporting_member_state=rms,
            num_aifs=num_aifs,
        )

        # Serialize source canonical
        try:
            session.source_canonical = _serialize_source_canonical(adapter)
        except Exception as e:
            log.warning("Could not serialize source canonical: %s", e)
            session.source_canonical = {}

        store.save_session(session)

        # Generate XMLs + validate
        output_dir = str(Path(tmp_dir) / "output")
        Path(output_dir).mkdir(exist_ok=True)
        result = adapter.generate_and_validate(output_dir=output_dir)

        # ── Extract field values from generated XML ──────────────────
        # The XML builders produce fully-populated XML with all derived,
        # aggregated and ranking data.  We parse the XML back to extract
        # every field value, giving the Report Viewer 100% coverage
        # instead of the limited scalar set from to_canonical_*().
        from canonical.aifmd_xml_field_extractor import extract_aifm_fields, extract_aif_fields

        # Collect validation errors per report type for completeness calc
        validation_obj = result.get("validation")
        _val_errors: dict[str, set[str]] = {"AIFM": set(), "AIF": set()}
        if validation_obj:
            import re as _re
            for f in validation_obj.all_findings:
                if f.status != "FAIL":
                    continue
                rm = _re.match(r"(AIFM?|AIF)-(\d+)", f.rule_id or "")
                if rm:
                    rtype = "AIFM" if "AIFM" in rm.group(1) else "AIF"
                    _val_errors[rtype].add(rm.group(2))

        # Save AIFM report — extract fields from generated AIFM XML
        try:
            aifm_xmls = result.get("aifm_xmls", [])
            if aifm_xmls:
                aifm_fields, aifm_groups = extract_aifm_fields(aifm_xmls[0])
                aifm_report = ReviewReport(
                    session_id=session.session_id,
                    report_type="AIFM",
                    entity_name=aifm_name,
                    entity_index=0,
                    nca_codes=[rms],
                    fields_json=aifm_fields,
                    groups_json=aifm_groups,
                    history_json={},
                )
                fcount = len(aifm_fields)
                aifm_report.filled_count = fcount
                aifm_report.field_count = 38
                # Completeness = (required fields - errors) / required fields
                aifm_report.completeness = _calc_completeness(
                    "AIFM", filing_type, _val_errors["AIFM"], aifm_fields)
                store.save_report(aifm_report)
                log.info("Saved AIFM report from XML: %d fields, %d groups, %.1f%% complete",
                         fcount, len(aifm_groups), aifm_report.completeness)
        except Exception as e:
            log.warning("Could not extract AIFM fields from XML: %s", e)

        # Save AIF reports — extract fields from generated AIF XMLs
        try:
            aif_xmls = result.get("aif_xmls", [])
            for idx, aif_xml_path in enumerate(aif_xmls):
                aif_fields, aif_groups = extract_aif_fields(aif_xml_path)

                aif_name = ""
                if hasattr(adapter, "aifs") and idx < len(adapter.aifs):
                    aif = adapter.aifs[idx]
                    aif_name = getattr(aif, "name", "") or getattr(aif, "aif_name", f"AIF {idx+1}")

                # Collect NCA codes for this AIF
                nca_list = [rms]
                if hasattr(adapter, "aifs") and idx < len(adapter.aifs):
                    aif_obj = adapter.aifs[idx]
                    if hasattr(aif_obj, "nca_codes") and aif_obj.nca_codes:
                        nca_list = list(set(nca_list + aif_obj.nca_codes))

                aif_report = ReviewReport(
                    session_id=session.session_id,
                    report_type="AIF",
                    entity_name=aif_name,
                    entity_index=idx,
                    nca_codes=nca_list,
                    fields_json=aif_fields,
                    groups_json=aif_groups,
                    history_json={},
                )
                fcount = len(aif_fields)
                aif_report.filled_count = fcount
                aif_report.field_count = 302
                # Completeness = (required fields - errors) / required fields
                aif_report.completeness = _calc_completeness(
                    "AIF", filing_type, _val_errors["AIF"], aif_fields)
                store.save_report(aif_report)
                log.info("Saved AIF report %d (%s) from XML: %d fields, %d groups, %.1f%% complete",
                         idx, aif_name, fcount, len(aif_groups), aif_report.completeness)
        except Exception as e:
            log.warning("Could not extract AIF fields from XML: %s", e)

        # ── Store real validation results from generate_and_validate() ──
        # The pipeline validator (validate_aifmd_xml.py) already ran above.
        # Store its findings so the DQF column is populated from the first view.
        validation_data = None
        validation_obj = result.get("validation")
        if validation_obj:
            try:
                # Convert ValidationFinding objects to storable dicts.
                # report.py looks up findings by field_id extracted from rule_id.
                # Rule IDs are "AIFM-4", "AIF-17", etc. — the number IS the field_id.
                import re as _re
                stored_findings = []
                for f in validation_obj.all_findings:
                    # Extract field_id from rule_id: "AIFM-4" → "4", "AIF-101" → "101"
                    rule_match = _re.match(r"(AIFM?|AIF)-(\d+)", f.rule_id or "")
                    report_prefix = rule_match.group(1) if rule_match else ""
                    field_num = rule_match.group(2) if rule_match else ""

                    # Build field_path as "REPORT_TYPE.FIELD_ID" for report.py lookup
                    # report.py does: fid = finding["field_path"].split(".")[-1]
                    if report_prefix and field_num:
                        rtype = "AIFM" if "AIFM" in report_prefix else "AIF"
                        field_path = f"{rtype}.{field_num}"
                    else:
                        field_path = f.field_path or ""

                    stored_findings.append({
                        "rule_id": f.rule_id,
                        "field_path": field_path,
                        "status": f.status,
                        "severity": f.severity,
                        "message": f.message,
                        "check_type": "dqf",
                        "nca_applied": getattr(f, "nca_applied", False),
                        "nca_error_code": getattr(f, "nca_error_code", ""),
                    })

                dqf_pass = validation_obj.total_dqf_pass
                dqf_fail = validation_obj.total_dqf_fail
                xsd_valid = validation_obj.xsd_invalid_count == 0
                has_crit = validation_obj.has_critical_failures

                val_run = ReviewValidationRun(
                    session_id=session.session_id,
                    xsd_valid=xsd_valid,
                    dqf_pass=dqf_pass,
                    dqf_fail=dqf_fail,
                    has_critical=has_crit,
                    findings_json=stored_findings,
                )
                store.save_validation_run(val_run)
                log.info("Stored pipeline validation: XSD %s, DQF %d pass / %d fail",
                        "valid" if xsd_valid else "INVALID", dqf_pass, dqf_fail)

                failures = [
                    {"rule": f["rule_id"], "field": f["field_path"],
                     "message": f["message"], "severity": f["severity"]}
                    for f in stored_findings if f["status"] == "FAIL"
                ][:50]
                validation_data = {
                    "xsd": {
                        "valid": validation_obj.xsd_valid_count,
                        "invalid": validation_obj.xsd_invalid_count,
                    },
                    "dqf": {"pass": dqf_pass, "fail": dqf_fail},
                    "failures": failures,
                    "has_critical": has_crit,
                }
            except Exception as e:
                log.warning("Could not store pipeline validation: %s", e)
                validation_data = {"error": str(e)}

        return UploadResponse(
            status="success",
            session_id=session.session_id,
            adapter={
                "filename": file.filename,
                "filing_type": filing_type,
                "reporting_member_state": rms,
                "aifm_name": aifm_name,
                "num_aifs": num_aifs,
            },
            generated={
                "aifm_xmls": len(result.get("aifm_xmls", [])),
                "aif_xmls": len(result.get("aif_xmls", [])),
                "packages": len(result.get("aif_zips", []) + result.get("gz_files", [])),
            },
            validation=validation_data,
        )

    except Exception as e:
        log.exception("Upload failed")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "session_id": "",
                "adapter": {},
                "generated": {},
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """Get session details with report list."""
    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    reports = store.get_reports_for_session(session_id)
    report_summaries = [
        ReportSummary(
            report_id=r.report_id,
            report_type=r.report_type,
            entity_name=r.entity_name,
            entity_index=r.entity_index,
            nca_codes=r.nca_codes,
            completeness=r.completeness,
            field_count=r.field_count,
            filled_count=r.filled_count,
        )
        for r in reports
    ]

    return SessionDetail(
        session_id=session.session_id,
        filename=session.filename,
        uploaded_at=session.uploaded_at,
        aifm_name=session.aifm_name,
        filing_type=session.filing_type,
        template_type=session.template_type,
        reporting_period=session.reporting_period,
        reporting_member_state=session.reporting_member_state,
        num_aifs=session.num_aifs,
        status=session.status,
        product_id=session.product_id,
        reports=report_summaries,
    )


@router.get("/session/active/current")
async def get_active_session():
    """Get the currently active (non-archived) session."""
    store = get_store()
    session = store.get_active_session()
    if session is None:
        return {"session_id": None}

    reports = store.get_reports_for_session(session.session_id)
    report_summaries = [
        {
            "report_id": r.report_id,
            "report_type": r.report_type,
            "entity_name": r.entity_name,
            "entity_index": r.entity_index,
            "nca_codes": r.nca_codes,
            "completeness": r.completeness,
            "field_count": r.field_count,
            "filled_count": r.filled_count,
        }
        for r in reports
    ]

    return {
        "session_id": session.session_id,
        "filename": session.filename,
        "uploaded_at": session.uploaded_at,
        "aifm_name": session.aifm_name,
        "filing_type": session.filing_type,
        "template_type": session.template_type,
        "reporting_period": session.reporting_period,
        "reporting_member_state": session.reporting_member_state,
        "num_aifs": session.num_aifs,
        "status": session.status,
        "product_id": session.product_id,
        "reports": report_summaries,
    }


@router.get("/sessions")
async def list_sessions():
    """List all sessions (most recent first)."""
    store = get_store()
    return store.list_sessions()
