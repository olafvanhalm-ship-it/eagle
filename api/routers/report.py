"""Report retrieval and editing routes."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from api.deps import get_store, get_field_registry, get_field_classification
from api.models.requests import FieldEditRequest, SourceEntityEditRequest
from api.models.responses import (
    ReportDetailResponse, ReportFieldResponse, FieldValidationResponse,
    SourceDataResponse, SourceEntityResponse, EditResultResponse,
)
from persistence.report_store import ReviewEdit

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["report"])


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
    category = classification.get(field_id, {}).get("category", "report")
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

    return ReportFieldResponse(
        field_id=field_id,
        field_name=fdef.field_name if fdef else f"Field {field_id}",
        section=fdef.section if fdef else "Unknown",
        value=field_value.get("value"),
        source=field_value.get("source", "unknown"),
        priority=field_value.get("priority", "IMPORTED"),
        data_type=fdef.data_type.value if fdef else "A",
        obligation=fdef.obligation.value if fdef else "O",
        format=fdef.format if fdef else "",
        allowed_values_ref=fdef.allowed_values_ref if fdef else None,
        xsd_element=fdef.xsd_element if fdef else "",
        repetition=fdef.repetition if fdef else "[1..1]",
        editable=editable,
        category=category,
        nca_deviations={},
        validation=val_response,
    )


def _is_system_field(field_id: str, report_type: str) -> bool:
    """Check if a report field is system-generated (not user-editable)."""
    system_fields = {
        "AIFM": {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "16"},
        "AIF": {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "16", "17"},
    }
    return field_id in system_fields.get(report_type, set())


@router.get("/session/{session_id}/report/manager")
async def get_manager_report(
    session_id: str,
    show_all: bool = Query(False, description="Show all fields including empty optional"),
):
    """Get the AIFM (Manager) report for a session."""
    return await _get_report(session_id, "AIFM", 0, show_all)


@router.get("/session/{session_id}/report/fund/{index}")
async def get_fund_report(
    session_id: str,
    index: int,
    show_all: bool = Query(False, description="Show all fields including empty optional"),
):
    """Get a specific AIF (Fund) report by index."""
    return await _get_report(session_id, "AIF", index, show_all)


async def _get_report(session_id: str, report_type: str, index: int, show_all: bool):
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

    # Get latest validation results for inline indicators.
    # Findings have field_path like "AIFM.4" or "AIF.17" — filter by report_type.
    validation_map: dict[str, FieldValidationResponse] = {}
    validation_run = False
    latest_val = store.get_latest_validation(session_id)
    if latest_val and latest_val.findings_json is not None:
        validation_run = True
        for finding in latest_val.findings_json:
            field_path = finding.get("field_path", "")
            if not field_path or "." not in field_path:
                continue
            path_type, fid = field_path.rsplit(".", 1)
            # Only include findings for the current report type
            if path_type != report_type:
                continue
            fstatus = finding.get("status", "")
            if fid and fstatus in ("FAIL", "WARNING"):
                # Don't overwrite a FAIL with a WARNING for the same field
                if fid in validation_map and validation_map[fid].status == "FAIL":
                    continue
                validation_map[fid] = FieldValidationResponse(
                    status=fstatus,
                    rule_id=finding.get("rule_id", ""),
                    message=finding.get("message", ""),
                    fix_suggestion=_generate_fix_suggestion(finding, registry, report_type),
                    severity=finding.get("severity", "MEDIUM"),
                )

    # If validation has been run, add implicit PASS for valued fields without findings
    if validation_run:
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
    # These should be hidden for INIT filings even if mandatory in schema
    amnd_only_fields = {
        "AIFM": {"10", "11", "12", "CANC-AIFM-1", "CANC-AIFM-2", "CANC-AIFM-3", "CANC-AIFM-4"},
        "AIF": {"10", "11", "12", "CANC-AIF-1", "CANC-AIF-2", "CANC-AIF-3", "CANC-AIF-4", "CANC-AIF-5"},
    }

    # Sections that should be hidden entirely when empty for INIT filings
    # (e.g. Controlled Structure, Dominant Influence — only mandatory if applicable)
    _init_hide_when_empty_sections = {
        "AIF Cancellation Record",
        "AIFM Cancellation Record",
    }

    # Import content-type applicability from the registry (single source of truth)
    from canonical.aifmd_field_registry import FieldRegistry as _FR

    for fid, fdef in all_fields.items():
        has_value = fid in fields_data
        has_failure = fid in validation_map

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

        # Determine visibility in default view
        if not show_all:
            if not has_value and not has_failure:
                if fdef.obligation.value == "M":
                    pass  # Always show mandatory even when empty
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
    for gname, rows in groups_data.items():
        if not rows:
            continue
        col_map: dict[str, str] = {}
        for col_id in rows[0]:
            fdef_col = None
            if registry:
                fdef_col = (
                    registry.aifm_field(col_id) if report_type == "AIFM"
                    else registry.aif_field(col_id)
                )
            if fdef_col:
                col_map[col_id] = fdef_col.field_name
            else:
                # Synthetic columns (region, nav_pct, etc.) — prettify
                col_map[col_id] = col_id.replace("_", " ").title()
        group_columns[gname] = col_map

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

    return ReportDetailResponse(
        report_id=report.report_id,
        session_id=report.session_id,
        report_type=report.report_type,
        entity_name=report.entity_name,
        entity_index=report.entity_index,
        nca_codes=report.nca_codes,
        completeness=completeness,
        field_count=required_count,
        filled_count=required_count - error_count,
        sections=sections,
        groups=groups_data,
        group_columns=group_columns,
        empty_section_count=empty_section_count,
        validation_run=validation_run,
        no_reporting=is_no_reporting,
    )


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
async def get_source_data(session_id: str, fund_index: int = Query(0)):
    """Get source canonical entities for editing."""
    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    sc = session.source_canonical or {}
    manager = sc.get("manager", {})

    # Get AIF-level source data
    aifs = sc.get("aifs", [])
    if fund_index < len(aifs):
        aif = aifs[fund_index]
    else:
        aif = {}

    # Build entity responses
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

    entities = {}
    for key, label in entity_types.items():
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
    """Edit a report-level entity field value."""
    store = get_store()
    report_type = "AIFM"  # TODO: determine from field_id range
    classification = get_field_classification()
    cat = classification.get(req.field_id, {}).get("category", "report")

    if cat == "composite":
        raise HTTPException(
            status_code=400,
            detail="Composite fields cannot be edited directly. Edit the source data instead.",
        )

    # Find the appropriate report
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Determine report type from field_id
    registry = get_field_registry()
    if registry:
        if registry.aifm_field(req.field_id):
            report_type = "AIFM"
        elif registry.aif_field(req.field_id):
            report_type = "AIF"

    report = store.get_report_by_type_and_index(session_id, report_type, 0)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    # Record old value
    old_value = report.fields_json.get(req.field_id, {}).get("value")

    # Update field
    from datetime import datetime, timezone
    report.fields_json[req.field_id] = {
        "value": req.value,
        "source": "client_review",
        "priority": "MANUALLY_OVERRIDDEN",
        "confidence": 1.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": req.note,
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
