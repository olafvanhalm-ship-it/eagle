"""Field registry and reference table routes (static, cached)."""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from api.deps import get_field_registry

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["registry"])


@router.get("/registry/{product_id}/fields/{report_type}")
async def get_field_definitions(product_id: str, report_type: str):
    """Get all field definitions for a report type (cached)."""
    registry = get_field_registry()
    if registry is None:
        raise HTTPException(status_code=503, detail="Field registry not available")

    rt = report_type.upper()
    if rt == "AIFM":
        fields = registry.aifm_fields()
    elif rt == "AIF":
        fields = registry.aif_fields()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report_type}")

    return {
        "product_id": product_id,
        "report_type": rt,
        "field_count": len(fields),
        "fields": [
            {
                "field_id": f.field_id,
                "field_name": f.field_name,
                "section": f.section,
                "data_type": f.data_type.value,
                "format": f.format,
                "obligation": f.obligation.value,
                "mandatory": f.mandatory,
                "repetition": f.repetition,
                "xsd_element": f.xsd_element,
                "severity": f.severity,
                "allowed_values_ref": f.allowed_values_ref,
            }
            for f in fields.values()
        ],
    }


@router.get("/registry/{product_id}/sections/{report_type}")
async def get_sections(product_id: str, report_type: str):
    """Get section names and field counts for a report type."""
    registry = get_field_registry()
    if registry is None:
        raise HTTPException(status_code=503, detail="Field registry not available")

    from canonical.aifmd_field_registry import ReportType
    rt = ReportType.AIFM if report_type.upper() == "AIFM" else ReportType.AIF
    sections = registry.sections(rt)

    return {
        "product_id": product_id,
        "report_type": report_type.upper(),
        "sections": [
            {
                "name": name,
                "field_count": len(fields),
                "mandatory_count": sum(1 for f in fields if f.mandatory),
            }
            for name, fields in sections.items()
        ],
    }


@router.get("/registry/{product_id}/reference/{table_name}")
async def get_reference_table(product_id: str, table_name: str):
    """Get values from a reference table (for dropdown population)."""
    registry = get_field_registry()
    if registry is None:
        raise HTTPException(status_code=503, detail="Field registry not available")

    values = registry.reference_table(table_name)
    if not values:
        raise HTTPException(status_code=404, detail=f"Reference table '{table_name}' not found")

    return {
        "table_name": table_name,
        "count": len(values),
        "values": values,
    }
