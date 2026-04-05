"""Dependency graph for source-to-report field cascade.

When a source canonical entity field is edited (e.g. a position's market_value),
multiple report fields may need to update. This module maps source entity fields
to the report fields they affect, and provides a re-projection function that
updates a stored report's fields from an updated source canonical.

Design principles:
- Uses the existing AIFM_ENTITY_MAP and AIF_ENTITY_MAP from aifmd_projection.py
  as the authoritative source→report mapping
- Composite fields (aggregations like total NAV, top-5 counterparties) are
  flagged but not auto-computed — they require the full pipeline
- Returns a list of affected report field IDs so the UI can highlight cascaded
  changes with the yellow flash animation
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .aifmd_projection import AIFM_ENTITY_MAP, AIF_ENTITY_MAP

log = logging.getLogger(__name__)


# =============================================================================
# COMPOSITE FIELD RULES
# =============================================================================

# Composite fields are derived from multiple source entity fields (e.g.
# total NAV = sum of all position market values). These cannot be updated
# by a single field edit — they require re-aggregation across all entities.
#
# Maps report_field_id → { "depends_on": [(entity_type, field_name), ...], "aggregation": str }
AIFMD_COMPOSITE_RULES: dict[str, dict] = {
    # AIFM composite: total AuM across all AIFs
    "24": {
        "depends_on": [("fund_dynamic", "nav")],
        "aggregation": "sum_all_aifs",
        "description": "Total AuM under management",
    },
    # AIF composite: NAV (field 50) from positions
    "50": {
        "depends_on": [("positions", "market_value")],
        "aggregation": "sum",
        "description": "AIF NAV",
    },
    # AIF composite: gross asset value (field 51)
    "51": {
        "depends_on": [("positions", "market_value"), ("positions", "notional_value")],
        "aggregation": "sum_absolute",
        "description": "Gross asset value",
    },
    # Top 5 counterparties (fields 160-171) depend on counterparties collection
    "160": {
        "depends_on": [("counterparties", "exposure_value")],
        "aggregation": "top_n",
        "description": "Top 5 counterparties by exposure",
    },
}

# Collection entity types that affect repeating groups in the report
COLLECTION_ENTITY_GROUPS = {
    "positions": "positions",
    "transactions": "transactions",
    "share_classes": "share_classes",
    "counterparties": "counterparty_risks",
    "strategies": "strategies",
    "investors": "investor_groups",
    "risk_measures": "risks",
    "borrowing_sources": "borrow_sources",
    "controlled_companies": "dominant_influences",
    "controlled_structures": "controlled_structures",
}


# =============================================================================
# REVERSE INDEX: source field → report fields
# =============================================================================

def _build_reverse_index() -> dict[str, list[str]]:
    """Build a reverse index from (entity_type.field_name) → list of report field_ids.

    This allows quick lookup: "if I change positions[3].market_value,
    which report fields need updating?"
    """
    index: dict[str, list[str]] = {}

    for field_id, (entity_attr, field_name) in AIFM_ENTITY_MAP.items():
        key = f"{entity_attr}.{field_name}"
        index.setdefault(key, []).append(f"AIFM.{field_id}")

    for field_id, (entity_attr, field_name) in AIF_ENTITY_MAP.items():
        key = f"{entity_attr}.{field_name}"
        index.setdefault(key, []).append(f"AIF.{field_id}")

    # Add composite dependencies
    for field_id, rule in AIFMD_COMPOSITE_RULES.items():
        for entity_type, field_name in rule["depends_on"]:
            key = f"{entity_type}.{field_name}"
            index.setdefault(key, []).append(f"AIF.{field_id}")

    return index


# Singleton reverse index
_REVERSE_INDEX: dict[str, list[str]] | None = None


def get_reverse_index() -> dict[str, list[str]]:
    """Get or build the singleton reverse index."""
    global _REVERSE_INDEX
    if _REVERSE_INDEX is None:
        _REVERSE_INDEX = _build_reverse_index()
    return _REVERSE_INDEX


# =============================================================================
# CASCADE ANALYSIS
# =============================================================================

def find_affected_report_fields(
    entity_type: str,
    field_name: str,
) -> list[dict[str, str]]:
    """Find all report fields affected by changing a source entity field.

    Args:
        entity_type: Source entity type (e.g. "positions", "fund_static", "manager")
        field_name: Field name on the entity (e.g. "market_value", "name")

    Returns:
        List of dicts with keys:
            - report_type: "AIFM" or "AIF"
            - field_id: ESMA field ID
            - cascade_type: "direct" (1:1 mapping) or "composite" (aggregation)
    """
    index = get_reverse_index()
    key = f"{entity_type}.{field_name}"

    affected = []
    for report_ref in index.get(key, []):
        rtype, fid = report_ref.split(".", 1)
        cascade_type = "composite" if fid in AIFMD_COMPOSITE_RULES else "direct"
        affected.append({
            "report_type": rtype,
            "field_id": fid,
            "cascade_type": cascade_type,
        })

    return affected


def find_affected_by_collection_edit(
    entity_type: str,
) -> list[dict[str, str]]:
    """Find report fields affected by editing any field in a collection entity.

    For collection entities (positions, transactions, etc.), editing any row
    may affect the repeating group in the report plus any composite fields
    that aggregate over that collection.

    Args:
        entity_type: Collection entity type (e.g. "positions", "counterparties")

    Returns:
        List of affected field descriptors.
    """
    affected = []

    # Check composite rules for dependencies on this entity type
    for field_id, rule in AIFMD_COMPOSITE_RULES.items():
        for dep_entity, dep_field in rule["depends_on"]:
            if dep_entity == entity_type:
                affected.append({
                    "report_type": "AIF",
                    "field_id": field_id,
                    "cascade_type": "composite",
                })
                break  # Don't duplicate for same field_id

    # The repeating group itself
    if entity_type in COLLECTION_ENTITY_GROUPS:
        affected.append({
            "report_type": "AIF",
            "field_id": f"group:{COLLECTION_ENTITY_GROUPS[entity_type]}",
            "cascade_type": "group_update",
        })

    return affected


# =============================================================================
# RE-PROJECTION
# =============================================================================

def reproject_entity_fields(
    source_canonical_dict: dict,
    report_fields_json: dict,
    report_type: str,
    fund_index: int = 0,
) -> tuple[dict, list[str]]:
    """Re-project entity fields from source canonical into report fields.

    This is the core cascade function: after a source entity edit, we
    re-read the entity field values and update the corresponding report
    fields. Only entity-classified fields (direct 1:1 mappings) are
    updated. Composite fields are flagged but not recomputed.

    Args:
        source_canonical_dict: Serialized source canonical (from DB)
        report_fields_json: Current report fields dict (from DB)
        report_type: "AIFM" or "AIF"
        fund_index: Index of the AIF in source_canonical.aifs (for AIF reports)

    Returns:
        Tuple of (updated_fields_json, list_of_changed_field_ids)
    """
    entity_map = AIFM_ENTITY_MAP if report_type == "AIFM" else AIF_ENTITY_MAP
    changed_fields: list[str] = []

    for field_id, (entity_attr, field_name) in entity_map.items():
        # Resolve the entity value from source canonical
        value = _resolve_source_value(
            source_canonical_dict, entity_attr, field_name,
            report_type, fund_index,
        )

        if value is None:
            continue

        # Check if the report field value differs
        current = report_fields_json.get(field_id, {})
        current_value = current.get("value") if isinstance(current, dict) else current

        if str(value) != str(current_value) if current_value is not None else value is not None:
            from datetime import datetime, timezone
            report_fields_json[field_id] = {
                "value": value,
                "source": "cascade_reprojection",
                "priority": "DERIVED",
                "confidence": 1.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": f"Auto-cascaded from {entity_attr}.{field_name}",
            }
            changed_fields.append(field_id)

    return report_fields_json, changed_fields


def _resolve_source_value(
    sc_dict: dict,
    entity_attr: str,
    field_name: str,
    report_type: str,
    fund_index: int = 0,
) -> Any:
    """Resolve a single field value from the serialized source canonical.

    Args:
        sc_dict: Serialized source canonical dict
        entity_attr: Entity attribute name (e.g. "manager", "fund_static")
        field_name: Field name on the entity
        report_type: "AIFM" or "AIF"
        fund_index: Index into aifs[] for AIF reports

    Returns:
        The raw field value, or None if not found.
    """
    if report_type == "AIFM":
        # AIFM fields come from sc_dict["manager"]
        if entity_attr == "manager":
            manager = sc_dict.get("manager", {})
            fv = manager.get(field_name, {})
            return fv.get("value") if isinstance(fv, dict) else fv
    else:
        # AIF fields come from sc_dict["aifs"][fund_index]
        aifs = sc_dict.get("aifs", [])
        if fund_index >= len(aifs):
            return None
        aif = aifs[fund_index]

        if entity_attr == "fund_static":
            entity_data = aif.get("fund_static", {})
        elif entity_attr == "fund_dynamic":
            entity_data = aif.get("fund_dynamic", {})
        elif entity_attr in ("share_class", "counterparty"):
            # These map to collection items — not directly resolvable as scalars
            return None
        else:
            return None

        fv = entity_data.get(field_name, {})
        return fv.get("value") if isinstance(fv, dict) else fv

    return None
